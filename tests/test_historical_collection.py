from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest

from reddit_api.historical import HistoricalRedditCollector, TimeFrame
from reddit_api.models import RedditPost
from reddit_api.storage import RedditDataStorage


def test_identical_titles_never_delete_distinct_threads_or_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    storage = RedditDataStorage(str(tmp_path / "reddit.db"))
    with sqlite3.connect(storage.db_path) as conn:
        conn.executemany("INSERT INTO posts (id, title, subreddit, author) VALUES (?, 'weekly', 'x', 'mod')",
                         [("one",), ("two",)])
        conn.execute("INSERT INTO comments (id, content, post_id) VALUES ('reply', 'hello', 'two')")
    storage.deduplicate_database()
    with sqlite3.connect(storage.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1


def historical_fixture():
    collector = HistoricalRedditCollector.__new__(HistoricalRedditCollector)
    collector.config = SimpleNamespace(target_subreddits=["example"], target_keywords=[])
    collector.collector = Mock()
    collector.storage = Mock()
    collector.storage.store_posts.side_effect = len
    collector.storage.get_post_candidates.return_value = []
    collector._apply_request_delay = Mock()
    collector._handle_request_error = Mock()
    return collector


def test_oldest_unfiltered_timestamp_and_comment_retry():
    frame = TimeFrame.from_strings("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z")
    collector = historical_fixture()
    moment = frame.start_date
    post = RedditPost("one", "title", "", 0, moment, "example", "author", 0, "", 1)
    collector.collector.fetch_new_submissions.return_value = [SimpleNamespace(created_utc=moment.timestamp())]
    collector.collector._extract_post_data.return_value = post
    collector.collector.collect_post_comments.side_effect = [RuntimeError("offline"), []]
    assert collector.collect_historical_data(frame)["status"] == "partial"
    collector.collector.fetch_new_submissions.return_value = []
    collector.storage.get_post_candidates.return_value = [(post.id, post.title, post.content, moment.isoformat())]
    assert collector.collect_historical_data(frame)["status"] == "complete"
    assert collector.collector.collect_post_comments.call_count == 2


def test_listing_failure_empty_listing_and_uncovered_window():
    frame = TimeFrame.from_strings("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z")
    collector = historical_fixture()
    collector.collector.fetch_new_submissions.side_effect = RuntimeError("offline")
    assert collector.collect_historical_data(frame)["status"] == "failed"
    collector.collector.fetch_new_submissions.side_effect = None
    collector.collector.fetch_new_submissions.return_value = []
    assert collector.collect_historical_data(frame)["success"]
    collector.collector.fetch_new_submissions.return_value = [
        SimpleNamespace(created_utc=datetime(2020, 1, 3, tzinfo=timezone.utc).timestamp())
    ]
    result = collector.collect_historical_data(frame)
    assert not result["success"]
    assert result["uncovered_intervals"][0]["start"] == frame.start_date.isoformat()
    with pytest.raises(ValueError, match="positive"):
        frame.split_into_chunks(0)


def test_legacy_local_inputs_and_adjacent_chunks(monkeypatch):
    monkeypatch.setenv("REDDIT_COLLECTION_TIMEZONE", "America/Chicago")
    frame = TimeFrame.from_strings("2020-01-01", "2020-01-03")
    first, second = frame.split_into_chunks(1)
    assert first.start_date.hour == 6
    assert first.end_date == second.start_date

    collector = historical_fixture()
    boundary = second.start_date
    collector.collector.fetch_new_submissions.return_value = [SimpleNamespace(created_utc=boundary.timestamp())]
    collector.collector._extract_post_data.return_value = RedditPost(
        "boundary", "title", "", 0, boundary, "example", "author", 0, "", 0
    )
    assert collector._collect_time_filtered_posts("example", first, 10, [])[0] == []
    assert [post.id for post in collector._collect_time_filtered_posts("example", second, 10, [])[0]] == ["boundary"]
