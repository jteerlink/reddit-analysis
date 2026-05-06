"""Deterministic artifact production jobs for dashboard intelligence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from src.analysis.db import artifact_checksum, complete_artifact, enqueue_artifact, ensure_analysis_tables
from src.db.connection import execute, is_postgres_connection


def _keywords(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [part.strip() for part in text.replace("[", " ").replace("]", " ").replace('"', " ").split(",") if part.strip()]


def _label_from_keywords(keywords: list[str]) -> str:
    stopwords = {
        "the",
        "and",
        "for",
        "that",
        "with",
        "this",
        "you",
        "are",
        "from",
        "have",
        "was",
        "but",
        "not",
        "can",
        "all",
        "just",
    }
    useful = [word for word in keywords if word.lower() not in stopwords and len(word) > 2]
    return " / ".join(useful[:3]) if useful else "Unlabeled cluster"


def _insert_or_replace(conn, sql: str, params: tuple) -> None:
    execute(conn, sql.replace("INSERT OR REPLACE", "INSERT") if is_postgres_connection(conn) else sql, params)


def backfill_cluster_labels(conn) -> int:
    rows = execute(
        conn,
        "SELECT topic_id, keywords, doc_count FROM topics WHERE topic_id != -1 ORDER BY doc_count DESC",
    ).fetchall()
    count = 0
    for row in rows:
        topic_id = row["topic_id"] if hasattr(row, "keys") else row[0]
        keywords_raw = row["keywords"] if hasattr(row, "keys") else row[1]
        doc_count = row["doc_count"] if hasattr(row, "keys") else row[2]
        keywords = _keywords(keywords_raw)
        label = _label_from_keywords(keywords)
        if is_postgres_connection(conn):
            execute(
                conn,
                """
                INSERT INTO cluster_labels (cluster_id, label, keywords, doc_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (cluster_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    keywords = EXCLUDED.keywords,
                    doc_count = EXCLUDED.doc_count
                """,
                (topic_id, label, json.dumps(keywords), doc_count),
            )
        else:
            execute(
                conn,
                "INSERT OR REPLACE INTO cluster_labels (cluster_id, label, keywords, doc_count) VALUES (?, ?, ?, ?)",
                (topic_id, label, json.dumps(keywords), doc_count),
            )
        count += 1
    conn.commit()
    artifact = enqueue_artifact(
        conn,
        kind="cluster_labels",
        source_input_hash=artifact_checksum({"topics": count}),
        payload={"cluster_count": count},
        provider="deterministic",
        model_name="keyword-labeler",
        prompt_version="v1",
    )
    complete_artifact(conn, artifact["artifact_id"], {"cluster_count": count})
    return count


def backfill_embedding_2d(conn, limit: int = 2000) -> int:
    rows = execute(
        conn,
        f"""
        SELECT ta.id, ta.topic_id, p.embedding_key
        FROM topic_assignments ta
        JOIN preprocessed p ON ta.id = p.id
        WHERE ta.topic_id >= 0
          AND p.embedding_key IS NOT NULL
        ORDER BY ta.topic_id, ta.id
        LIMIT {limit}
        """,
    ).fetchall()
    index_path = Path("models/embeddings_index.json")
    cache_path = Path("models/embeddings_cache.npy")
    if not rows or not index_path.exists() or not cache_path.exists():
        artifact = enqueue_artifact(
            conn,
            kind="embedding_map",
            source_input_hash=artifact_checksum({"embedding_points": 0, "reason": "missing_embedding_cache"}),
            payload={"point_count": 0, "state": "missing_config"},
            provider="deterministic",
            model_name="minilm-svd-projection",
            prompt_version="v2",
        )
        complete_artifact(conn, artifact["artifact_id"], {"point_count": 0, "state": "missing_config"})
        return 0

    index = json.loads(index_path.read_text())
    cache = np.load(cache_path, mmap_mode="r")
    selected: list[tuple[str, int, np.ndarray]] = []
    for row in rows:
        rid = row["id"] if hasattr(row, "keys") else row[0]
        topic_id = int(row["topic_id"] if hasattr(row, "keys") else row[1])
        embedding_key = row["embedding_key"] if hasattr(row, "keys") else row[2]
        position = index.get(embedding_key)
        if position is None:
            continue
        selected.append((rid, topic_id, np.asarray(cache[int(position)], dtype=np.float64)))

    if not selected:
        artifact = enqueue_artifact(
            conn,
            kind="embedding_map",
            source_input_hash=artifact_checksum({"embedding_points": 0, "reason": "no_matching_embeddings"}),
            payload={"point_count": 0, "state": "unpopulated"},
            provider="deterministic",
            model_name="minilm-svd-projection",
            prompt_version="v2",
        )
        complete_artifact(conn, artifact["artifact_id"], {"point_count": 0, "state": "unpopulated"})
        return 0

    matrix = np.vstack([item[2] for item in selected])
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    if len(selected) == 1:
        coords = np.zeros((1, 2), dtype=np.float64)
    else:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[:2].T
        coords = centered @ components
        if coords.shape[1] == 1:
            coords = np.column_stack([coords[:, 0], np.zeros(len(selected))])
    max_abs = np.maximum(np.max(np.abs(coords), axis=0), 1e-9)
    coords = coords / max_abs
    count = 0
    for index, (rid, topic_id, _) in enumerate(selected):
        x = float(coords[index, 0])
        y = float(coords[index, 1])
        if is_postgres_connection(conn):
            execute(
                conn,
                """
                INSERT INTO embedding_2d (post_id, x, y, cluster_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (post_id) DO UPDATE SET
                    x = EXCLUDED.x, y = EXCLUDED.y, cluster_id = EXCLUDED.cluster_id
                """,
                (rid, x, y, topic_id),
            )
        else:
            execute(
                conn,
                "INSERT OR REPLACE INTO embedding_2d (post_id, x, y, cluster_id) VALUES (?, ?, ?, ?)",
                (rid, x, y, topic_id),
            )
        count += 1
    conn.commit()
    artifact = enqueue_artifact(
        conn,
        kind="embedding_map",
        source_input_hash=artifact_checksum({"embedding_points": count}),
        payload={"point_count": count},
        provider="deterministic",
        model_name="minilm-svd-projection",
        prompt_version="v2",
    )
    complete_artifact(conn, artifact["artifact_id"], {"point_count": count, "algorithm": "svd"})
    return count


def _top_posts_for_event(conn, subreddit: str, date: str, limit: int = 3) -> list[str]:
    try:
        rows = execute(
            conn,
            "SELECT id FROM posts WHERE subreddit = ? AND DATE(timestamp) = ? ORDER BY (COALESCE(upvotes, 0) + COALESCE(num_comments, 0)) DESC LIMIT ?"
            if not is_postgres_connection(conn)
            else "SELECT id FROM posts WHERE subreddit = %s AND DATE(timestamp) = %s ORDER BY (COALESCE(upvotes, 0) + COALESCE(num_comments, 0)) DESC LIMIT %s",
            (subreddit, date, limit),
        ).fetchall()
    except Exception:
        return []
    return [row["id"] if hasattr(row, "keys") else row[0] for row in rows]


def _topic_terms_for_event(conn, subreddit: str, date: str, limit: int = 5) -> list[str]:
    try:
        rows = execute(
            conn,
            f"""
            SELECT t.keywords, COUNT(*) AS n
            FROM topic_assignments ta
            JOIN topics t ON ta.topic_id = t.topic_id
            JOIN (
                SELECT id, subreddit, timestamp FROM posts
                UNION ALL
                SELECT id, subreddit, timestamp FROM comments
            ) src ON ta.id = src.id
            WHERE src.subreddit = {'%s' if is_postgres_connection(conn) else '?'}
              AND DATE(src.timestamp) = {'%s' if is_postgres_connection(conn) else '?'}
              AND ta.topic_id >= 0
            GROUP BY t.keywords
            ORDER BY n DESC
            LIMIT {'%s' if is_postgres_connection(conn) else '?'}
            """,
            (subreddit, date, limit),
        ).fetchall()
    except Exception:
        return []
    terms: list[str] = []
    for row in rows:
        for keyword in _keywords(row["keywords"] if hasattr(row, "keys") else row[0]):
            if keyword not in terms:
                terms.append(keyword)
            if len(terms) >= limit:
                return terms
    return terms


def backfill_narrative_events(conn, limit: int = 20) -> int:
    rows = execute(
        conn,
        f"""
        SELECT subreddit, date, magnitude
        FROM change_points
        ORDER BY ABS(magnitude) DESC
        LIMIT {limit}
        """,
    ).fetchall()
    count = 0
    for row in rows:
        subreddit = row["subreddit"] if hasattr(row, "keys") else row[0]
        date = row["date"] if hasattr(row, "keys") else row[1]
        magnitude = float((row["magnitude"] if hasattr(row, "keys") else row[2]) or 0)
        label = f"{'Positive' if magnitude >= 0 else 'Negative'} sentiment shift in r/{subreddit}"
        terms = json.dumps(_topic_terms_for_event(conn, subreddit, date) or [subreddit, "sentiment", "change"])
        subs = json.dumps([subreddit])
        top_posts = json.dumps(_top_posts_for_event(conn, subreddit, date))
        source_key = f"{date}:{label}"
        source_hash = artifact_checksum({"narrative_event": source_key})
        existing = execute(
            conn,
            "SELECT artifact_id FROM analysis_artifacts WHERE kind = %s AND source_input_hash = %s"
            if is_postgres_connection(conn)
            else "SELECT artifact_id FROM analysis_artifacts WHERE kind = ? AND source_input_hash = ?",
            ("narrative_event_row", source_hash),
        ).fetchone()
        if existing:
            continue

        if is_postgres_connection(conn):
            execute(
                conn,
                """
                INSERT INTO narrative_events (
                    start_date, end_date, peak_date, peak_anomaly_score,
                    sentiment_delta, dominant_subreddits, top_terms, top_post_ids, auto_label
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (date, date, date, abs(magnitude), magnitude, subs, terms, top_posts, label),
            )
        else:
            execute(
                conn,
                """
                INSERT INTO narrative_events (
                    start_date, end_date, peak_date, peak_anomaly_score,
                    sentiment_delta, dominant_subreddits, top_terms, top_post_ids, auto_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date, date, date, abs(magnitude), magnitude, subs, terms, top_posts, label),
            )
        row_artifact = enqueue_artifact(
            conn,
            kind="narrative_event_row",
            source_input_hash=source_hash,
            payload={"peak_date": date, "label": label, "top_post_ids": json.loads(top_posts)},
            provider="deterministic",
            model_name="change-point-labeler",
            prompt_version="v1",
        )
        complete_artifact(conn, row_artifact["artifact_id"], {"peak_date": date, "label": label, "top_post_ids": json.loads(top_posts)})
        count += 1
    conn.commit()
    persisted_count = int(execute(conn, "SELECT COUNT(*) FROM narrative_events").fetchone()[0] or 0)
    event_rows = execute(
        conn,
        "SELECT event_id, peak_date, auto_label FROM narrative_events ORDER BY peak_date, event_id",
    ).fetchall()
    event_set = [
        {
            "event_id": row["event_id"] if hasattr(row, "keys") else row[0],
            "peak_date": row["peak_date"] if hasattr(row, "keys") else row[1],
            "label": row["auto_label"] if hasattr(row, "keys") else row[2],
        }
        for row in event_rows
    ]
    artifact = enqueue_artifact(
        conn,
        kind="narrative_events",
        source_input_hash=artifact_checksum({"events": event_set}),
        payload={"event_count": persisted_count},
        provider="deterministic",
        model_name="change-point-labeler",
        prompt_version="v1",
    )
    if artifact.get("status") != "succeeded":
        complete_artifact(conn, artifact["artifact_id"], {"event_count": persisted_count})
    return count


def backfill_brief(conn) -> int:
    event_count = execute(conn, "SELECT COUNT(*) FROM narrative_events").fetchone()[0]
    topic_count = execute(conn, "SELECT COUNT(*) FROM cluster_labels").fetchone()[0]
    model_count = execute(conn, "SELECT COUNT(*) FROM llm_model_registry WHERE available = 1").fetchone()[0]
    source_events = [
        row["event_id"] if hasattr(row, "keys") else row[0]
        for row in execute(
            conn,
            "SELECT event_id FROM narrative_events ORDER BY peak_date DESC, event_id DESC LIMIT 5",
        ).fetchall()
    ]
    payload = {
        "brief_id": "latest",
        "period": "latest",
        "headline": "Latest Reddit intelligence snapshot",
        "sections": [
            {"title": "Narrative events", "body": f"{int(event_count)} persisted event signals are available."},
            {"title": "Topic labels", "body": f"{int(topic_count)} topic labels are available."},
            {"title": "Model enrichment", "body": f"{int(model_count)} configured LLM models are currently registered."},
        ],
        "source_events": source_events,
    }
    artifact = enqueue_artifact(
        conn,
        kind="analyst_brief",
        source_input_hash=artifact_checksum({"event_count": int(event_count), "topic_count": int(topic_count)}),
        payload=payload,
        provider="deterministic",
        model_name="brief-template",
        prompt_version="v1",
    )
    if artifact.get("status") != "succeeded":
        complete_artifact(conn, artifact["artifact_id"], payload)
    return 1


def run_analysis_backfill(conn) -> dict[str, int]:
    ensure_analysis_tables(conn)
    result = {
        "cluster_labels": backfill_cluster_labels(conn),
        "embedding_points": backfill_embedding_2d(conn),
        "narrative_events": backfill_narrative_events(conn),
        "analyst_briefs": backfill_brief(conn),
    }
    return result
