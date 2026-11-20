#!/usr/bin/env python3
"""Report topic concentration and representative original documents.

This is an inspection report only: it does not refit a topic model or promote
labels.  Human topic review fields remain empty until a reviewer completes the
8-of-10 representative-example gate.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def build_report(db_path: str, representative_count: int = 10, run_version: str = "unknown") -> dict:
    if representative_count < 1:
        raise ValueError("representative_count must be positive")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        topics = [dict(row) for row in conn.execute("SELECT topic_id, keywords, doc_count, coherence_score, created_at FROM topics ORDER BY topic_id")]
        assignments = [dict(row) for row in conn.execute("SELECT topic_id, probability FROM topic_assignments")]
        total = len(assignments)
        by_topic = Counter(int(row["topic_id"]) for row in assignments)
        topics_report = []
        for topic in topics:
            topic_id = int(topic["topic_id"])
            if topic_id == -1:
                continue
            docs = conn.execute(
                """
                SELECT ta.id, ta.probability, p.content_type, p.raw_text, p.clean_text,
                       COALESCE(posts.title, '') AS title,
                       COALESCE(posts.content, comments.content, p.raw_text, '') AS original_text,
                       COALESCE(posts.subreddit, comments.subreddit, '') AS subreddit,
                       COALESCE(posts.timestamp, comments.timestamp) AS timestamp,
                       COALESCE(comments.post_id, comments.parent_id, posts.id, ta.id) AS thread_id
                FROM topic_assignments ta
                JOIN preprocessed p ON p.id = ta.id
                LEFT JOIN posts ON p.content_type = 'post' AND posts.id = p.id
                LEFT JOIN comments ON p.content_type = 'comment' AND comments.id = p.id
                WHERE ta.topic_id = ?
                ORDER BY COALESCE(ta.probability, 0) DESC, ta.id
                LIMIT ?
                """,
                (topic_id, representative_count),
            ).fetchall()
            topics_report.append({
                "topic_id": topic_id,
                "keywords": topic.get("keywords"),
                "doc_count": int(topic.get("doc_count") or by_topic.get(topic_id, 0)),
                "share": (by_topic.get(topic_id, 0) / total) if total else 0.0,
                "coherence_score": topic.get("coherence_score"),
                "created_at": topic.get("created_at"),
                "representatives": [dict(doc) for doc in docs],
                "human_label": "",
                "reviewed_examples": None,
                "review_notes": "",
                "promotion_eligible": False,
            })
        outliers = by_topic.get(-1, 0)
        return {
            "status": "review_required",
            "database": str(db_path),
            "topic_model_version": run_version,
            "topic_run_created_at": max((topic.get("created_at") or "" for topic in topics), default=None),
            "assignment_count": total,
            "topic_count": len(topics_report),
            "outlier_count": outliers,
            "outlier_share": outliers / total if total else 0.0,
            "size_distribution": sorted((item["doc_count"] for item in topics_report), reverse=True),
            "review_gate": "At least 8 of 10 representative original examples must support each human label; this is a manual operational gate.",
            "human_review_complete": False,
            "topics": topics_report,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="historical_reddit_data.db")
    parser.add_argument("--output", default="data/topic_diagnostics.json")
    parser.add_argument("--representatives", type=int, default=10)
    parser.add_argument("--run-version", default="unknown", help="Immutable version recorded by the training run")
    args = parser.parse_args()
    if not Path(args.db).exists():
        parser.error(f"database not found: {args.db}")
    result = build_report(args.db, args.representatives, args.run_version)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
