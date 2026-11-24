import asyncio
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

    import src.api.app as api_app
    import src.db.connection as connection

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
        conn.execute("CREATE TABLE sentiment_predictions (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO sentiment_predictions (id) VALUES ('a')")
        conn.execute("CREATE TABLE topics (topic_id INTEGER, coherence_score REAL)")
        conn.execute("CREATE TABLE sentiment_forecast (subreddit TEXT)")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_POOLED", raising=False)
    monkeypatch.setenv("REDDIT_DB_PATH", str(db_path))

    import src.api.routes.pipeline as pipeline
    import src.db.connection as connection

    importlib.reload(connection)
    pipeline = importlib.reload(pipeline)

    assert pipeline._db_count("SELECT COUNT(*) FROM sentiment_predictions") == 1


def test_pipeline_run_generator_rejects_overlapping_runs(monkeypatch, tmp_path):
    import src.api.routes.pipeline as pipeline

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)

    async def scenario():
        lock = asyncio.Lock()
        monkeypatch.setattr(pipeline, "_PIPELINE_RUN_LOCK", lock)
        started = asyncio.Event()
        finish = asyncio.Event()

        async def fake_stream_step(step_num, queue):
            await queue.put(f"data: started {step_num}\n\n")
            started.set()
            await finish.wait()
            await queue.put(f"data: finished {step_num}\n\n")
            return True

        monkeypatch.setattr(pipeline, "_stream_step", fake_stream_step)

        active_run = pipeline._run_generator([1])
        first_event = await anext(active_run)
        await asyncio.wait_for(started.wait(), timeout=1)

        busy_events = [event async for event in pipeline._run_generator([2])]

        finish.set()
        remaining_events = [event async for event in active_run]

        assert first_event == "data: started 1\n\n"
        assert busy_events == [pipeline.BUSY_EVENT]
        assert remaining_events == ["data: finished 1\n\n", "event: result\ndata: succeeded\n\n"]
        assert lock.locked() is False

    asyncio.run(scenario())


def test_pipeline_run_generator_releases_lock_after_failed_step(monkeypatch, tmp_path):
    import src.api.routes.pipeline as pipeline

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)

    async def scenario():
        lock = asyncio.Lock()
        monkeypatch.setattr(pipeline, "_PIPELINE_RUN_LOCK", lock)

        async def fake_stream_step(step_num, queue):
            await queue.put(f"data: failed {step_num}\n\n")
            return False

        monkeypatch.setattr(pipeline, "_stream_step", fake_stream_step)

        events = [event async for event in pipeline._run_generator([1, 2])]

        assert events == ["data: failed 1\n\n", "event: result\ndata: failed\n\n"]
        assert lock.locked() is False

    asyncio.run(scenario())


def test_dashboard_full_run_prunes_and_syncs_before_success(monkeypatch, tmp_path):
    from src.api.routes import pipeline

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_PIPELINE_RUN_LOCK", asyncio.Lock())
    monkeypatch.setattr(pipeline, "get_backend", lambda: "sqlite")
    monkeypatch.setenv("NEON_DATABASE_URL", "fixture")
    operations = []

    async def step(step_num, queue):
        operations.append(("step", step_num))
        return True

    async def command(args, queue, label):
        operations.append((args[3], args[-1]))
        return label != "Neon mirror"

    monkeypatch.setattr(pipeline, "_stream_step", step)
    monkeypatch.setattr(pipeline, "_stream_command", command)

    async def run():
        return [event async for event in pipeline._run_generator([2], full_run=True)]

    assert asyncio.run(run()) == ["event: result\ndata: failed\n\n"]
    assert [action for action, _ in operations] == ["step", "prune", "sync"]
    assert operations[1][1] == operations[2][1]


def test_env_example_does_not_contain_real_neon_secret():
    env_example = Path(".env.example").read_text()

    assert "DATABASE_URL=postgresql://user:password@" in env_example
    assert "DATABASE_URL_POOLED=postgresql://user:password@" in env_example
    assert "neon.tech" not in env_example.lower()


def test_pipeline_execution_requires_post_and_operator_token(monkeypatch, tmp_path):
    from src.api.app import app
    from src.api.routes import pipeline

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)

    async def stub_step(step, queue):
        await queue.put(f"data: ran {step}\n\n")
        return True

    monkeypatch.setattr(pipeline, "_stream_step", stub_step)
    client = TestClient(app)
    url = "/pipeline/run/1"
    monkeypatch.delenv("PIPELINE_OPERATOR_TOKEN", raising=False)
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 503
    monkeypatch.setenv("PIPELINE_OPERATOR_TOKEN", "fixture-token")
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer incorrect"}).status_code == 401
    response = client.post(url, headers={"Authorization": "Bearer fixture-token"})
    assert response.status_code == 200
    assert "event: result\ndata: succeeded" in response.text
