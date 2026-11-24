import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess


def test_run_pipeline_mirrors_after_single_steps_and_once_after_full_run():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "sync_neon \"step $step\"" in script
    assert "run_step \"$i\" false" in script
    assert "sync_neon \"full pipeline\"" in script


def test_run_pipeline_supports_disabling_neon_sync():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "NEON_SYNC=true" in script
    assert "--no-neon-sync) NEON_SYNC=false ;;" in script
    assert "Skip post-step/post-run SQLite→Neon mirror" in script


def test_run_pipeline_defaults_to_all_steps_without_per_step_approval():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert 'MODE="all"' in script
    assert "CONFIRM_STEPS=false" in script

    mode_all = script.split("mode_all() {", 1)[1].split("# ── Argument parsing", 1)[0]
    assert 'if [[ "$CONFIRM_STEPS" == "true" ]]; then' in mode_all
    assert mode_all.index('if [[ "$CONFIRM_STEPS" == "true" ]]; then') < mode_all.index('run_step "$i" false')
    assert 'prompt_step "$i"' in mode_all


def test_run_pipeline_can_opt_back_into_interactive_confirmations():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "--interactive) MODE=\"interactive\" ;;" in script
    assert "--confirm-steps) CONFIRM_STEPS=true ;;" in script
    assert "Show interactive menu instead of default all-step run" in script
    assert "Ask before each step during all-step runs" in script


def test_run_pipeline_loads_neon_url_from_dotenv_without_exporting_it():
    script = Path("scripts/run_pipeline.sh").read_text()
    maintenance = Path("scripts/pipeline_data.py").read_text()

    assert 'scripts/pipeline_data.py sync --db "$DB"' in script
    assert 'load_dotenv(PROJECT_ROOT / ".env")' in maintenance
    assert 'os.environ.get("NEON_DATABASE_URL")' in maintenance


def test_full_pipeline_prunes_before_mirroring_with_the_same_cutoff():
    script = Path("scripts/run_pipeline.sh").read_text()
    full_run = script.split("mode_all() {", 1)[1].split("should_skip_refresh() {", 1)[0]

    assert full_run.index('scripts/pipeline_data.py cutoff') < full_run.index('run_step "$i" false')
    assert full_run.index('run_step "$i" false') < full_run.index('prune --db "$DB" --cutoff "$cutoff"')
    assert full_run.index('prune --db "$DB" --cutoff "$cutoff"') < full_run.index('sync_neon "full pipeline" "$cutoff"')


def test_run_pipeline_prepares_environment_before_any_step_runner():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "ENVIRONMENT_READY=false" in script
    assert "ensure_pipeline_environment() {" in script

    run_step_body = script.split("run_step() {", 1)[1].split("run_step_1() {", 1)[0]
    assert 'ensure_pipeline_environment "$step"' in run_step_body
    assert run_step_body.index('ensure_pipeline_environment "$step"') < run_step_body.index('case "$step" in')


def test_run_pipeline_extracts_val_f1_without_grep_p(tmp_path):
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "grep -oP" not in script

    match = re.search(r"extract_val_f1\(\) \{.*?^\}", script, re.DOTALL | re.MULTILINE)
    assert match is not None

    log_file = tmp_path / "step_4.log"
    log_file.write_text(
        "\n".join(
            [
                "Val F1 (macro):  0.9004",
                "  F1 positive:   0.9577",
                "  F1 neutral:    0.8770",
                "  F1 negative:   0.8664",
            ]
        )
    )

    result = subprocess.run(
        ["bash", "-c", f"{match.group(0)}\nextract_val_f1 {log_file}"],
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "0.9004"


def test_run_pipeline_bootstraps_environment_at_startup_before_modes():
    script = Path("scripts/run_pipeline.sh").read_text()

    entrypoint = script.split("# ── Entry point", 1)[1]
    assert 'ensure_pipeline_environment "startup"' in entrypoint
    assert entrypoint.index('ensure_pipeline_environment "startup"') < entrypoint.index('case "$MODE" in')


def test_run_pipeline_verifies_step_6_and_7_imports_during_environment_setup():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "verify_pipeline_dependencies() {" in script
    assert "import bertopic" in script
    assert "from prophet import Prophet" in script
    assert "import ruptures" in script
    assert 'verify_pipeline_dependencies "$logfile"' in script


def test_run_pipeline_has_incremental_refresh_and_explicit_rebuild_modes():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "--refresh) MODE=\"all\"; FULL_REBUILD=false ;;" in script
    assert "--full-rebuild|--rebuild) FULL_REBUILD=true ;;" in script
    assert "should_skip_refresh()" in script
    assert "use --full-rebuild to rerun" in script
    assert "Python dependencies already available; skipping installation" in script


def test_run_pipeline_requires_explicit_rescore_for_model_replacement():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "PIPELINE_RESCORE_EXISTING" in script
    assert "--rescore-existing" in script
    assert "replacing the active model generation" in script


def test_routine_inference_runs_with_nounset_and_no_rescore_flags():
    script = Path("scripts/run_pipeline.sh").read_text()
    function = script.split("run_step_5() {", 1)[1].split("run_step_6() {", 1)[0]
    result = subprocess.run(
        ["bash", "-eu", "-o", "pipefail", "-c", "run_step_5() {" + function + """
MODE=all FULL_REBUILD=false VERBOSE=true DB=test.db PROJECT_ROOT=.
PYTHON=print_args
print_args() { printf '%s\n' "$@"; }
info() { :; }
success() { :; }
gate_5_batch_inference() { :; }
python_query() { echo 1; }
mark_done() { :; }
run_step_5 /dev/null
"""],
        capture_output=True,
        check=True,
        text=True,
    )
    assert result.stdout.split() == ["scripts/batch_inference.py", "--db", "test.db", "--batch-size", "1000"]


def test_failed_step_does_not_trigger_neon_sync(tmp_path):
    script = Path("scripts/run_pipeline.sh").read_text()
    function = script.split("run_step() {", 1)[1].split("run_step_1() {", 1)[0]
    result = subprocess.run(
        ["bash", "-eu", "-c", "run_step() {" + function + """
LOG_DIR=$1
header() { :; }
dim() { :; }
step_name() { :; }
step_desc() { :; }
ensure_pipeline_environment() { :; }
run_step_5() { return 42; }
sync_neon() { echo 'unexpected sync'; }
run_step 5 true || exit "$?"
""", "bash", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 42
    assert "unexpected sync" not in result.stdout


def test_retention_uses_calendar_months_and_clamps_month_end():
    from src.reddit_api.retention import retention_cutoff

    assert retention_cutoff(datetime(2025, 8, 31, 12, tzinfo=timezone.utc)) == datetime(
        2024, 2, 29, 12, tzinfo=timezone.utc
    )


def test_retention_removes_expired_records_without_confusing_typed_ids(tmp_path, monkeypatch):
    from scripts.pipeline_data import prune

    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE posts (id TEXT PRIMARY KEY, timestamp TEXT);
            CREATE TABLE comments (id TEXT PRIMARY KEY, timestamp TEXT, post_id TEXT REFERENCES posts(id));
            CREATE TABLE posts_other (id TEXT PRIMARY KEY, timestamp TEXT);
            CREATE TABLE comments_other (id TEXT PRIMARY KEY, timestamp TEXT, post_id TEXT);
            CREATE TABLE preprocessed (id TEXT, content_type TEXT, PRIMARY KEY (id, content_type));
            CREATE TABLE topic_assignments (id TEXT, content_type TEXT,
                FOREIGN KEY (id, content_type) REFERENCES preprocessed(id, content_type));
            CREATE TABLE sentiment_daily (date TEXT);
            INSERT INTO posts VALUES ('same-id', '2025-04-30T23:59:59Z'), ('keep', '2025-05-01'), ('undated', NULL);
            INSERT INTO comments VALUES ('same-id', '2025-04-30T19:00:00-05:00', 'keep'),
                ('old-reply', '2025-04-20', 'keep'), ('recent-reply', '2026-01-01', 'same-id');
            INSERT INTO posts_other VALUES ('archived', '2024-01-01');
            INSERT INTO comments_other VALUES ('archived-reply', NULL, 'archived');
            INSERT INTO preprocessed VALUES ('same-id', 'post'), ('same-id', 'comment'), ('recent-reply', 'comment');
            INSERT INTO topic_assignments SELECT * FROM preprocessed;
            INSERT INTO sentiment_daily VALUES ('2025-04-30'), ('2025-05-01');
        """)

    cutoff = datetime(2025, 5, 1, tzinfo=timezone.utc)
    result = prune(str(db), cutoff)
    assert result["posts"] == 1
    assert result["comments"] == 2
    assert result["posts_other"] == result["comments_other"] == 1
    assert not any(prune(str(db), cutoff).values())
    with sqlite3.connect(db) as conn:
        assert {row[0] for row in conn.execute("SELECT id FROM posts")} == {"keep", "undated"}
        assert conn.execute("SELECT id FROM comments").fetchall() == [("same-id",)]
        assert conn.execute("SELECT * FROM topic_assignments").fetchall() == [("same-id", "comment")]
        assert conn.execute("SELECT * FROM sentiment_daily").fetchall() == [("2025-05-01",)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ml_extra_pins_regex_floor_required_by_transformers():
    pyproject = Path("pyproject.toml").read_text()

    assert '"regex>=2025.10.22"' in pyproject
