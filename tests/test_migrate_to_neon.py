import sqlite3
import subprocess
import sys


def test_migrate_to_neon_dry_run_reports_runtime_tables(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE posts (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE comments (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE posts_other (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE embedding_2d (post_id TEXT PRIMARY KEY)")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_to_neon.py",
            "--source",
            str(source),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "posts: 0 row(s)" in result.stdout
    assert "comments: 0 row(s)" in result.stdout
    assert "posts_other" in result.stdout
    assert "embedding_2d" in result.stdout
    assert "excluded from v1" in result.stdout
