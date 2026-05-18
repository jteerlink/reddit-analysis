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
