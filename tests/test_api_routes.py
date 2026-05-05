import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.app import app


def test_dashboard_routes_forward_to_db_layer(monkeypatch):
    from src.api import db

    monkeypatch.setattr(
        db,
        "get_collection_summary",
        lambda: {"total_posts": 1, "total_comments": 2, "last_timestamp": "now"},
    )
    monkeypatch.setattr(db, "get_trending_topics", lambda n=3: [{"topic_id": 1}])
    monkeypatch.setattr(
        db,
        "get_sentiment_summary",
        lambda: [{"label": "positive", "count": 1}],
    )
    monkeypatch.setattr(
        db,
        "get_sentiment_daily",
        lambda subreddits=(), days=90: [
            {"subreddit": subreddits[0] if subreddits else "all", "mean_score": 0.2}
        ],
    )
    monkeypatch.setattr(db, "get_change_points", lambda subreddits=(): [])
    monkeypatch.setattr(db, "get_forecast", lambda subreddits=(): [])
    monkeypatch.setattr(db, "get_daily_volume", lambda subreddits=(), days=30: [])
    monkeypatch.setattr(
        db,
        "get_topic_graph",
        lambda n=50, min_similarity=0.15, subreddits=(): {
            "nodes": [{"topic_id": 1, "keywords": "ai, policy"}],
            "edges": [{"source": 1, "target": 2, "similarity": 0.5, "shared_keywords": ["ai"]}],
            "subreddits": list(subreddits),
        },
    )

    client = TestClient(app)

    summary = client.get("/summary")
    assert summary.status_code == 200
    assert summary.json()["trending_topics"] == [{"topic_id": 1}]

    sentiment = client.get("/sentiment/summary")
    assert sentiment.status_code == 200
    assert sentiment.json()[0]["label"] == "positive"

    daily = client.get("/sentiment/daily?subreddits=ChatGPT")
    assert daily.status_code == 200
    assert daily.json()[0]["subreddit"] == "ChatGPT"

    assert client.get("/sentiment/change-points").status_code == 200
    assert client.get("/sentiment/forecast").status_code == 200
    assert client.get("/volume/daily").status_code == 200

    graph = client.get("/topics/graph?n=12&min_similarity=0.2&subreddits=ChatGPT")
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["topic_id"] == 1
    assert graph.json()["edges"][0]["shared_keywords"] == ["ai"]
    assert graph.json()["subreddits"] == ["ChatGPT"]
