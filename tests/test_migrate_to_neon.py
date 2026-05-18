import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.migrate_to_neon import EXCLUDED_TABLES, MIGRATION_ORDER, _transform


def test_migrate_to_neon_dry_run_reports_runtime_tables(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE posts (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE comments (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE posts_other (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE embedding_2d (post_id TEXT PRIMARY KEY)")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_to_neon.py",
            "--source",
            str(source),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "posts: 0 row(s)" in result.stdout
    assert "comments: 0 row(s)" in result.stdout
    assert "posts_other" in result.stdout
    assert "embedding_2d" in result.stdout
    assert "excluded from v1" in result.stdout


def test_analysis_tables_are_in_neon_migration_order():
    for table in ["analysis_artifacts", "embedding_2d", "cluster_labels", "narrative_events"]:
        assert table in MIGRATION_ORDER
        assert table not in EXCLUDED_TABLES


def test_neon_schema_accepts_subreddit_parent_columns_from_sqlite():
    schema_sql = Path("scripts/neon_schema.sql").read_text()

    assert "subreddit_parent_id TEXT DEFAULT 'OTHER'" in schema_sql
    assert "ALTER TABLE posts ADD COLUMN IF NOT EXISTS subreddit_parent_id" in schema_sql
    assert "ALTER TABLE comments ADD COLUMN IF NOT EXISTS subreddit_parent_id" in schema_sql
    assert "ALTER TABLE narrative_events ADD COLUMN IF NOT EXISTS llm_label" in schema_sql
    assert "ALTER TABLE narrative_events ADD COLUMN IF NOT EXISTS llm_summary" in schema_sql


def test_transform_converts_missing_timestamps_to_none():
    df = pd.DataFrame(
        {
            "freshness_timestamp": [pd.NaT],
            "lease_expires_at": [""],
            "retry_after": [None],
            "created_at": ["2026-05-18T12:00:00Z"],
            "updated_at": [pd.NaT],
        }
    )

    transformed = _transform("analysis_artifacts", df)

    assert transformed.loc[0, "freshness_timestamp"] is None
    assert transformed.loc[0, "lease_expires_at"] is None
    assert transformed.loc[0, "retry_after"] is None
    assert transformed.loc[0, "updated_at"] is None
