import sys

from scripts import train_topic_model


def test_cli_passes_umap_tuning_args(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / "reddit.db"
    db_path.write_text("")
    captured = {}

    def fake_run_topic_modeling(**kwargs):
        captured.update(kwargs)
        return {
            "total_docs": 100,
            "n_topics": 20,
            "n_outliers": 5,
            "coherent_topic_count": 20,
            "mean_coherence": 0.61,
            "gate_passed": True,
            "device": "cpu",
        }

    monkeypatch.setattr(train_topic_model, "run_topic_modeling", fake_run_topic_modeling)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_topic_model.py",
            "--db",
            str(db_path),
            "--n-neighbors",
            "10",
            "--n-components",
            "3",
        ],
    )

    train_topic_model.main()

    assert captured["n_neighbors"] == 10
    assert captured["n_components"] == 3
    assert "Gate:               PASSED" in capsys.readouterr().out


def test_cli_accepts_no_topic_reduction(monkeypatch, tmp_path):
    db_path = tmp_path / "reddit.db"
    db_path.write_text("")
    captured = {}

    def fake_run_topic_modeling(**kwargs):
        captured.update(kwargs)
        return {
            "total_docs": 100,
            "n_topics": 20,
            "n_outliers": 5,
            "coherent_topic_count": 20,
            "mean_coherence": 0.61,
            "gate_passed": True,
            "device": "cpu",
        }

    monkeypatch.setattr(train_topic_model, "run_topic_modeling", fake_run_topic_modeling)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_topic_model.py",
            "--db",
            str(db_path),
            "--nr-topics",
            "none",
        ],
    )

    train_topic_model.main()

    assert captured["nr_topics"] is None
