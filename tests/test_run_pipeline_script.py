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


def test_ml_extra_pins_regex_floor_required_by_transformers():
    pyproject = Path("pyproject.toml").read_text()

    assert '"regex>=2025.10.22"' in pyproject
