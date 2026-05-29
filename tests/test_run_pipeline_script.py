from pathlib import Path


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


def test_run_pipeline_loads_neon_url_from_dotenv_without_exporting_it():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert 'load_dotenv(dotenv_path=Path("$PROJECT_ROOT") / ".env")' in script
    assert 'os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL")' in script
    assert "from scripts import migrate_to_neon" in script


def test_run_pipeline_prepares_environment_before_any_step_runner():
    script = Path("scripts/run_pipeline.sh").read_text()

    assert "ENVIRONMENT_READY=false" in script
    assert "ensure_pipeline_environment() {" in script

    run_step_body = script.split("run_step() {", 1)[1].split("run_step_1() {", 1)[0]
    assert 'ensure_pipeline_environment "$step"' in run_step_body
    assert run_step_body.index('ensure_pipeline_environment "$step"') < run_step_body.index('case "$step" in')
