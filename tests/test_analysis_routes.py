from contextlib import contextmanager
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.app import app


@contextmanager
def fake_connection(readonly=True):
    assert readonly is True
    yield object()


def test_analysis_routes_are_read_only_and_typed(monkeypatch):
    from src.api.routes import analysis

    monkeypatch.setattr(analysis, "connection", fake_connection)
    monkeypatch.setattr(
        analysis.queries,
        "activity",
        lambda conn, limit: [
            {
                "timestamp": "2026-05-05T00:00:00Z",
                "type": "analyst_brief",
                "severity": "success",
                "title": "Brief succeeded",
                "detail": "Artifact ready",
                "source_ids": ["a1"],
            }
        ],
    )
    monkeypatch.setattr(
        analysis.queries,
        "freshness",
        lambda conn: {"queued": 0, "running": 0, "failed": 0, "succeeded": 1, "latest_artifact_at": "now", "latest_success_at": "now"},
    )
    monkeypatch.setattr(analysis.queries, "model_registry", lambda conn: [])
    monkeypatch.setattr(analysis.queries, "artifacts", lambda conn, kind=None, limit=100: [])
    monkeypatch.setattr(analysis.queries, "narrative_events", lambda conn, limit=50: [])
    monkeypatch.setattr(analysis.queries, "embedding_map", lambda conn, limit=1000: [])
    monkeypatch.setattr(analysis.queries, "semantic_search", lambda conn, q, limit=50: [])
    monkeypatch.setattr(analysis.queries, "thread_analysis", lambda conn, post_id: {"post_id": post_id})
    monkeypatch.setattr(analysis.queries, "latest_brief", lambda conn: None)
    monkeypatch.setattr(analysis.queries, "briefs", lambda conn, limit=10: [])
    monkeypatch.setattr(analysis, "missing_analysis_tables", lambda conn, tables: [])

    client = TestClient(app)

    assert client.get("/analysis/activity").json()[0]["title"] == "Brief succeeded"
    assert client.get("/analysis/freshness").json()["succeeded"] == 1
    assert client.get("/analysis/model-registry").status_code == 200
    assert client.get("/analysis/artifacts").json() == {"artifacts": []}
    assert client.get("/analysis/narrative-events").json()["items"] == []
    assert client.get("/analysis/embedding-map").json()["items"] == []
    assert client.get("/analysis/semantic-search?q=ai").json()["items"] == []
    assert client.get("/analysis/thread-analysis/p1").json()["post_id"] == "p1"
    assert client.get("/analysis/briefs/latest").json()["brief_id"] == "none"
    assert client.get("/analysis/briefs").json()["items"] == []


def test_analysis_routes_report_query_errors_as_error_state(monkeypatch):
    from src.api.routes import analysis

    monkeypatch.setattr(analysis, "connection", fake_connection)
    monkeypatch.setattr(analysis, "missing_analysis_tables", lambda conn, tables: [])

    def raise_query_error(conn, limit=1000):
        raise analysis.queries.AnalysisQueryError("bad projection")

    monkeypatch.setattr(analysis.queries, "embedding_map", raise_query_error)

    client = TestClient(app)
    response = client.get("/analysis/embedding-map")

    assert response.status_code == 200
    assert response.json()["state"] == "error"
    assert response.json()["provenance"]["detail"] == "bad projection"


def test_semantic_route_reports_degraded_rows_as_missing_config(monkeypatch):
    from src.api.routes import analysis

    monkeypatch.setattr(analysis, "connection", fake_connection)
    monkeypatch.setattr(analysis, "missing_analysis_tables", lambda conn, tables: [])
    monkeypatch.setattr(
        analysis.queries,
        "semantic_search",
        lambda conn, q, limit: [
            {
                "id": "p1",
                "score": 0.25,
                "date": "2026-05-01",
                "subreddit": "ChatGPT",
                "content_type": "post",
                "label": "neutral",
                "confidence": 0.5,
                "text_preview": "lexical match",
                "state": "missing_config",
                "provenance": {"algorithm": "lexical_overlap_fallback"},
            }
        ],
    )
    monkeypatch.setattr(analysis.queries, "semantic_vector_backend_ready", lambda: True)

    client = TestClient(app)
    response = client.get("/analysis/semantic-search?q=ai")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "missing_config"
    assert payload["provenance"]["algorithm"] == "lexical_overlap_fallback"
    assert "degraded" in payload["provenance"]["detail"]
