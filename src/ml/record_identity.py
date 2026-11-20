"""Upgrade derived record keys while keeping raw Reddit IDs intact."""

import re
from typing import Any, Collection

from src.db.connection import is_postgres_connection

TABLE_KEYS = {
    "preprocessed": "id",
    "sentiment_predictions": "id",
    "topic_assignments": "id",
    "embedding_2d": "post_id",
}


def migrate_record_identity(conn: Any) -> None:
    """Upgrade legacy derived keys in one transaction on either backend."""
    if is_postgres_connection(conn):
        _migrate_postgres(conn)
    else:
        _migrate_sqlite(conn)


def _migrate_sqlite(conn: Any) -> None:
    from .db import _execute

    tables = {}
    for table, key in TABLE_KEYS.items():
        columns = _execute(conn, f"PRAGMA table_info({table})").fetchall()
        if any(row[1] == key and row[5] for row in columns) and not any(
            row[1] == "content_type" and row[5] for row in columns
        ):
            tables[table] = [row[1] for row in columns]
    if not tables:
        return

    foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if conn.in_transaction:
        raise RuntimeError("Record identity migration needs an idle SQLite connection")
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table, columns in tables.items():
            key = TABLE_KEYS[table]
            ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
            indexes = conn.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = 'index' AND sql IS NOT NULL",
                (table,),
            ).fetchall()
            ddl = re.sub(rf"\b{key}\s+TEXT\s+PRIMARY\s+KEY\b", f"{key} TEXT NOT NULL", ddl, flags=re.I)
            ddl = re.sub(r",\s*FOREIGN KEY\s*\(id\)\s*REFERENCES\s+preprocessed\s*\(id\)", "", ddl, flags=re.I)
            temp = f"{table}_typed"
            ddl = f"CREATE TABLE {temp} (" + ddl.split("(", 1)[1].rstrip().removesuffix(")")
            if "content_type" not in columns:
                ddl += ", content_type TEXT NOT NULL"
            ddl += f", PRIMARY KEY ({key}, content_type)"
            if table == "topic_assignments" and conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'preprocessed'").fetchone():
                ddl += ", FOREIGN KEY (id, content_type) REFERENCES preprocessed(id, content_type)"
            conn.execute(ddl + ")")
            identity = _legacy_kind(table, key, columns, "old")
            target = [column for column in columns if column != "content_type"] + ["content_type"]
            source = ", ".join(f'old."{column}"' for column in target[:-1])
            conn.execute(
                f"INSERT INTO {temp} ({', '.join(target)}) "
                f"SELECT {source}, {identity} FROM {table} old WHERE {identity} IS NOT NULL"
            )
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {temp} RENAME TO {table}")
            for index in indexes:
                conn.execute(index[0])
        _invalidate_collisions(conn, tables, postgres=False)
        if foreign_keys and "topic_assignments" in tables:
            if conn.execute("PRAGMA foreign_key_check(topic_assignments)").fetchone():
                raise ValueError("Migrated topic assignments reference missing records")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys={foreign_keys}")


def _legacy_kind(table: str, key: str, columns: list[str], alias: str) -> str:
    if table == "preprocessed":
        return f"{alias}.content_type"
    prepared = f"(SELECT p.content_type FROM preprocessed p WHERE p.id = {alias}.{key} LIMIT 1)"
    if "content_type" in columns:
        return f"COALESCE({alias}.content_type, {prepared})"
    return prepared


def _migrate_postgres(conn: Any) -> None:
    from .db import _execute

    tables = {}
    for table, key in TABLE_KEYS.items():
        primary = _execute(conn, """
            SELECT conname, cardinality(conkey) FROM pg_constraint
            WHERE conrelid = to_regclass(%s) AND contype = 'p'
        """, (table,)).fetchone()
        if primary and primary[1] == 1:
            tables[table] = (key, primary[0])
    if not tables:
        return

    try:
        # Drop the legacy single-column FK before upgrading its parent key.
        if "topic_assignments" in tables:
            foreign = _execute(conn, """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'topic_assignments'::regclass AND contype = 'f'
                  AND confrelid = 'preprocessed'::regclass
            """).fetchall()
            for row in foreign:
                _drop_constraint(conn, "topic_assignments", row[0])
        for table, (key, constraint) in tables.items():
            _execute(conn, f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS content_type TEXT")
            kind = _legacy_kind(table, key, ["content_type"], "old")
            _execute(conn, f"UPDATE {table} old SET content_type = {kind} WHERE content_type IS NULL")
            _execute(conn, f"DELETE FROM {table} WHERE content_type IS NULL")
            _drop_constraint(conn, table, constraint)
            _execute(conn, f"ALTER TABLE {table} ADD PRIMARY KEY ({key}, content_type)")
        if "topic_assignments" in tables:
            _execute(conn, """ALTER TABLE topic_assignments ADD FOREIGN KEY (id, content_type)
                REFERENCES preprocessed (id, content_type)""")
        _invalidate_collisions(conn, tables, postgres=True)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _invalidate_collisions(conn: Any, upgraded: Collection[str], *, postgres: bool) -> None:
    """Regenerate ambiguous legacy records from their two original sources."""
    from .db import _execute

    if "preprocessed" not in upgraded:
        return
    if postgres:
        def exists(table: str) -> bool:
            return _execute(conn, "SELECT to_regclass(%s)", (table,)).fetchone()[0] is not None
    else:
        def exists(table: str) -> bool:
            return _execute(conn, "SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone() is not None

    if not (exists("posts") and exists("comments")):
        return
    collisions = """SELECT posts.id FROM posts JOIN comments ON posts.id = comments.id
        JOIN preprocessed p ON p.id = posts.id"""
    if not _execute(conn, f"{collisions} LIMIT 1").fetchone():
        return
    _execute(conn, f"CREATE TEMP TABLE ambiguous_legacy_ids AS {collisions}")
    for table, key in reversed(tuple(TABLE_KEYS.items())):
        if exists(table):
            _execute(conn, f"DELETE FROM {table} WHERE {key} IN (SELECT id FROM ambiguous_legacy_ids)")
    _execute(conn, "DROP TABLE ambiguous_legacy_ids")
    _execute(conn, "CREATE TABLE IF NOT EXISTS topic_refit_required (slot INTEGER PRIMARY KEY)")
    _execute(conn, "INSERT INTO topic_refit_required VALUES (1) ON CONFLICT (slot) DO NOTHING")


def clear_topic_refit_requirement(conn: Any) -> None:
    from .db import _execute

    _execute(conn, "DROP TABLE IF EXISTS topic_refit_required")


def _drop_constraint(conn: Any, table: str, constraint: str) -> None:
    from psycopg2 import sql  # type: ignore[import-untyped]

    with conn.cursor() as cursor:
        cursor.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
            sql.Identifier(table), sql.Identifier(constraint)
        ))


def normalize_topic_rows(conn: Any, rows: list[tuple]) -> list[tuple]:
    """Resolve old assignment input only when the bare ID is unambiguous."""
    from .db import _execute, _marker

    normalized = []
    for row in rows:
        if len(row) == 5:
            normalized.append(row)
            continue
        identifier, topic, probability, *version = row
        types = _execute(conn, f"SELECT content_type FROM preprocessed WHERE id = {_marker(conn)}",
                         (identifier,)).fetchall()
        if len(types) != 1:
            raise ValueError(f"Topic assignment requires content type for {identifier}")
        normalized.append((identifier, types[0][0], topic, probability, version[0] if version else None))
    return normalized
