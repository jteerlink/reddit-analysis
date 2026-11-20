import sqlite3
from datetime import date

from scripts.backtest_forecasts import backtest
from scripts.evaluate_sentiment import evaluate_rows
from scripts.report_topic_diagnostics import build_report
from scripts.sample_evaluation_set import build_sample


def _sample_rows(count=40):
    rows = []
    for index in range(count):
        rows.append(
            {
                "id": f"p{index:03d}",
                "content_type": "post" if index % 2 else "comment",
                "subreddit": f"r{index % 2}",
                "thread_id": f"thread-{index // 2}",
                "timestamp": f"2025-01-{(index % 28) + 1:02d}T00:00:00",
                "clean_text": "This is excellent" if index % 3 else "This is awful",
                "model_label": None,
                "model_confidence": None,
            }
        )
    return rows


def test_sample_is_deterministic_and_leaves_human_labels_blank():
    first, manifest = build_sample(_sample_rows(), size=25)
    second, _ = build_sample(_sample_rows(), size=25)
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert len(first) == 25
    assert all(row.get("human_label", "") == "" for row in first)
    assert {row["holdout_split"] for row in first} <= {"development", "holdout"}
    assert manifest["status"] == "unverified_until_human_labels"


def test_sentiment_evaluation_reports_unverified_without_human_labels():
    result = evaluate_rows([{"id": "a", "human_label": "", "model_label": "positive"}])
    assert result["status"] == "unverified"
    assert result["metrics"] is None
    assert result["promotion"]["eligible"] is False


def test_sentiment_evaluation_separates_vader_agreement_from_model_metrics():
    rows = [
        {"id": "a", "human_label": "positive", "model_label": "positive", "vader_label": "negative"},
        {"id": "b", "human_label": "negative", "model_label": "positive", "vader_label": "negative"},
    ]
    result = evaluate_rows(rows)
    assert result["status"] == "verified"
    assert result["metrics"]["sample_size"] == 2
    assert result["vader_agreement"]["agreement"] == 0.5
    assert result["errors"][0]["id"] == "b"


def test_forecast_backtest_is_time_ordered_and_reproducible():
    series = {"r": [(date(2025, 1, day), float(day)) for day in range(1, 16)]}
    result = backtest(series, horizon=3, min_train_days=6, recent_days=3, splits=2)
    assert result["status"] == "complete"
    assert len(result["splits"]) == 2
    assert result["splits"][0]["training_through"] < result["splits"][0]["target_start"]
    assert result["metrics"]["persistence"]["n"] == 3
    assert result["splits"][0]["target_end"] > result["splits"][0]["target_start"]


def test_topic_diagnostics_keeps_original_representatives_and_version(tmp_path):
    db = tmp_path / "topics.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE topics(topic_id INTEGER PRIMARY KEY, keywords TEXT, doc_count INTEGER, coherence_score REAL, created_at TEXT);
        CREATE TABLE topic_assignments(id TEXT PRIMARY KEY, topic_id INTEGER, probability REAL);
        CREATE TABLE preprocessed(id TEXT PRIMARY KEY, content_type TEXT, raw_text TEXT, clean_text TEXT);
        CREATE TABLE posts(id TEXT PRIMARY KEY, title TEXT, content TEXT, subreddit TEXT, timestamp TEXT);
        CREATE TABLE comments(id TEXT PRIMARY KEY, content TEXT, subreddit TEXT, timestamp TEXT, post_id TEXT, parent_id TEXT);
        INSERT INTO topics VALUES (1, '["launch"]', 1, 0.8, '2025-01-01');
        INSERT INTO preprocessed VALUES ('p1', 'post', 'Cleaned text', 'Cleaned text');
        INSERT INTO posts VALUES ('p1', 'Original title', 'Original punctuation!', 'r/test', '2025-01-01');
        INSERT INTO topic_assignments VALUES ('p1', 1, 0.9);
        """
    )
    conn.commit()
    conn.close()
    result = build_report(str(db), run_version="runtime_luna-v1")
    assert result["topic_model_version"] == "runtime_luna-v1"
    assert result["topics"][0]["representatives"][0]["original_text"] == "Original punctuation!"
    assert result["topics"][0]["human_label"] == ""
    assert result["human_review_complete"] is False



def test_sentiment_evaluation_uses_typed_predictions(tmp_path):
    from scripts.evaluate_sentiment import _predictions

    db = tmp_path / "evaluation.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE sentiment_predictions (id TEXT, content_type TEXT, label TEXT,
                confidence REAL, model_version TEXT);
            INSERT INTO sentiment_predictions VALUES
              ('both', 'post', 'positive', 0.9, 'v'),
              ('both', 'comment', 'negative', 0.9, 'v');
        """)
    rows = [
        {"id": "both", "content_type": "post", "human_label": "positive"},
        {"id": "both", "content_type": "comment", "human_label": "negative"},
    ]
    assert evaluate_rows(rows, _predictions(str(db), ["both"]))["metrics"]["accuracy"] == 1
