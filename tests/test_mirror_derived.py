"""Mirror publication must not mix model generations or retain obsolete rows."""

from contextlib import contextmanager
from copy import deepcopy

import pandas as pd
import pytest

from scripts.mirror_derived import publish_snapshot


class Disconnected(Exception):
    pass


class Connection:
    def __init__(self, store):
        self.store = store
        self.pending = deepcopy(store)
        self.commits = 0

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql):
        table = sql.split('"')[1]
        self.pending[table] = []

    def commit(self):
        self.store.clear()
        self.store.update(deepcopy(self.pending))
        self.commits += 1

    def rollback(self):
        self.pending = deepcopy(self.store)

    def close(self):
        self.rollback()


def insert(connection, table, batch):
    connection.pending[table].extend(batch.to_dict("records"))


def test_publication_replaces_values_and_clears_obsolete_forecasts():
    store = {
        "posts": [{"id": "raw"}],
        "sentiment_predictions": [{"id": "p", "label": "negative"}],
        "sentiment_forecast": [{"date": "2025-01-01"}],
    }
    conn = Connection(store)
    publish_snapshot(conn, {
        "sentiment_predictions": pd.DataFrame([{"id": "p", "label": "positive"}]),
        "sentiment_forecast": pd.DataFrame(),
    }, insert, lambda: Connection(store), Disconnected, 20)
    assert store["posts"] == [{"id": "raw"}]
    assert store["sentiment_predictions"] == [{"id": "p", "label": "positive"}]
    assert store["sentiment_forecast"] == []
    assert conn.commits == 1


def test_disconnect_restarts_whole_generation_without_partial_publish():
    store = {"topics": [{"topic_id": 9}], "topic_assignments": [{"id": "old"}]}
    original = deepcopy(store)
    failures = []

    def flaky_insert(conn, table, batch):
        assert store == original
        if table == "topic_assignments" and not failures:
            failures.append(True)
            raise Disconnected()
        insert(conn, table, batch)

    frames = {
        "topics": pd.DataFrame([{"topic_id": 1}]),
        "topic_assignments": pd.DataFrame([{"id": "new"}]),
    }
    conn = publish_snapshot(Connection(store), frames, flaky_insert,
                            lambda: Connection(store), Disconnected, 10)
    assert store == {"topics": [{"topic_id": 1}], "topic_assignments": [{"id": "new"}]}
    assert conn.commits == 1


def test_failed_validation_rolls_back_and_raw_table_is_rejected():
    store = {"topics": [{"topic_id": 9}]}
    conn = Connection(store)

    def fail(*args):
        raise ValueError("invalid row")

    with pytest.raises(ValueError, match="invalid row"):
        publish_snapshot(conn, {"topics": pd.DataFrame([{"topic_id": 1}])},
                         fail, lambda: conn, Disconnected, 10)
    assert store == {"topics": [{"topic_id": 9}]}
    with pytest.raises(ValueError, match="Invalid derived"):
        publish_snapshot(conn, {"posts": pd.DataFrame()}, insert,
                         lambda: conn, Disconnected, 10)
