import importlib
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient


def test_connection_module_uses_sqlite_fallback(monkeypatch, tmp_path):
    db_path = tmp_path / "fallback.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE posts (id TEXT PRIMARY KEY)")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(db_path))

    import src.db.connection as connection

    connection = importlib.reload(connection)
    conn = connection.get_read_connection()
    try:
        assert connection.get_backend() == "sqlite"
        assert connection.database_reachable() is True
        assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 0
    finally:
        connection.release_connection(conn)


def test_redact_target_hides_postgres_credentials():
    from src.db.connection import redact_target

    redacted = redact_target(
        "postgresql://user:secret@example.neon.tech/reddit?sslmode=require"
    )

    assert "secret" not in redacted
    assert "user" not in redacted
    assert redacted.startswith("postgresql://")
    assert redacted.endswith("ddit")


def test_health_endpoint_reports_degraded_without_raising(monkeypatch, tmp_path):
    missing_db = tmp_path / "missing.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(missing_db))

    import src.db.connection as connection
    import src.api.app as api_app

    importlib.reload(connection)
    api_app = importlib.reload(api_app)

    response = TestClient(api_app.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["backend"] == "sqlite"
    assert payload["db_reachable"] is False
    assert str(missing_db) not in payload["db_path_or_url"]


def test_pipeline_status_uses_shared_db_boundary(monkeypatch, tmp_path):
    db_path = tmp_path / "pipeline.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE sentiment_predictions (id TEXT PRIMARY KEY)"
        )
        conn.execute("INSERT INTO sentiment_predictions (id) VALUES ('a')")
        conn.execute("CREATE TABLE topics (topic_id INTEGER, coherence_score REAL)")
        conn.execute("CREATE TABLE sentiment_forecast (subreddit TEXT)")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(db_path))

    import src.db.connection as connection
    import src.api.routes.pipeline as pipeline

    importlib.reload(connection)
    pipeline = importlib.reload(pipeline)

    assert pipeline._db_count("SELECT COUNT(*) FROM sentiment_predictions") == 1


def test_env_example_does_not_contain_real_neon_secret():
    env_example = Path(".env.example").read_text()

    assert "DATABASE_URL=postgresql://user:password@" in env_example
    assert "DATABASE_URL_POOLED=postgresql://user:password@" in env_example
    assert "neon.tech" not in env_example.lower()
