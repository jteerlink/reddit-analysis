"""Pipeline Runner tab — stream subprocess output for each ML pipeline step."""

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st

from src.dashboard.theme import (
    progress_ribbon,
    section_header,
    step_card,
    terminal_header,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

STEPS: List[Dict] = [
    {
        "num": 1,
        "name": "Prerequisites",
        "description": "Install dependencies, verify DB, create directories",
        "prereq": None,
    },
    {
        "num": 2,
        "name": "Preprocessing",
        "description": "Clean text, generate sentence embeddings",
        "prereq": 1,
    },
    {
        "num": 3,
        "name": "Weak Labels",
        "description": "VADER scoring → data/weak_labels.csv (≥30k rows)",
        "prereq": 2,
    },
    {
        "num": 4,
        "name": "Train Sentiment Model",
        "description": "Fine-tune DistilBERT on weak labels (20–40 min on MPS)",
        "prereq": 3,
    },
    {
        "num": 5,
        "name": "Batch Inference",
        "description": "Run trained model on all preprocessed records",
        "prereq": 4,
    },
    {
        "num": 6,
        "name": "Topic Modeling",
        "description": "BERTopic discovery, coherence scoring, week-over-week tracking",
        "prereq": 5,
    },
    {
        "num": 7,
        "name": "Time Series & Forecast",
        "description": "Daily aggregation + 14-day Prophet forecast",
        "prereq": 6,
    },
]


# ---------------------------------------------------------------------------
# Gate checks
# ---------------------------------------------------------------------------

def _db_count(db_path: str, query: str) -> int:
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(query).fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _step_done(step_num: int, db_path: str) -> bool:
    root = PROJECT_ROOT
    abs_db = Path(db_path) if Path(db_path).is_absolute() else PROJECT_ROOT / db_path

    if step_num == 1:
        return abs_db.exists()
    if step_num == 2:
        return (root / "models" / "embeddings_cache.npy").exists()
    if step_num == 3:
        csv = root / "data" / "weak_labels.csv"
        if not csv.exists():
            return False
        try:
            with open(csv) as f:
                return sum(1 for _ in f) - 1 >= 30000
        except Exception:
            return False
    if step_num == 4:
        return (root / "models" / "sentiment_v1" / "config.json").exists()
    if step_num == 5:
        return _db_count(db_path, "SELECT COUNT(*) FROM sentiment_predictions") > 0
    if step_num == 6:
        return _db_count(
            db_path, "SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50"
        ) >= 20
    if step_num == 7:
        return _db_count(db_path, "SELECT COUNT(*) FROM sentiment_forecast") > 0
    return False


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

def _step_command(step_num: int, db_path: str) -> List[str]:
    py = sys.executable

    if step_num == 1:
        return ["uv", "pip", "install", "-e", ".[ml,production]", "-q"]

    if step_num == 2:
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from src.ml.preprocessing import run_preprocessing;"
            f"r = run_preprocessing(db_path='{db_path}', cache_dir='models/',"
            "batch_size=1000, embed_batch_size=256, mlflow_tracking=True);"
            "print(f\"Total: {{r['total']:,}}  Filtered: {{r['filtered']:,}}"
            "  Kept: {{r['kept']:,}}  Device: {{r['device']}}\")"
        )
        return [py, "-c", code]

    if step_num == 3:
        return [
            py, "scripts/generate_weak_labels.py",
            "--db", db_path,
            "--output", "data/weak_labels.csv",
            "--threshold", "0.5",
            "--include-neutral",
            "--neutral-threshold", "0.1",
        ]

    if step_num == 4:
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from src.ml.sentiment import train;"
            "r = train(weak_labels_path='data/weak_labels.csv',"
            "model_dir='models/sentiment_v1', val_split=0.2, epochs=3,"
            "lr=2e-5, batch_size=16, max_length=256, mlflow_tracking=True);"
            "print(f\"Val F1 (macro): {{r['val_f1']:.4f}}  Device: {{r['device']}}\")"
        )
        return [py, "-c", code]

    if step_num == 5:
        return [
            py, "scripts/batch_inference.py",
            "--db", db_path,
            "--model-dir", "models/sentiment_v1",
            "--batch-size", "1000",
        ]

    if step_num == 6:
        return [
            py, "scripts/train_topic_model.py",
            "--db", db_path,
            "--cache-dir", "models/",
            "--days", "90",
            "--min-cluster-size", "30",
            "--min-topic-size", "30",
            "--nr-topics", "auto",
        ]

    if step_num == 7:
        return [
            py, "scripts/run_timeseries.py",
            "--db", db_path,
            "--days", "90",
            "--forecast-days", "14",
        ]

    raise ValueError(f"Unknown step number: {step_num}")


# ---------------------------------------------------------------------------
# Streaming runner
# ---------------------------------------------------------------------------

def _run_step(step_num: int, db_path: str, output_lines: List[str], placeholder) -> bool:
    """Run one step, streaming output into placeholder. Returns True on success."""
    step = STEPS[step_num - 1]
    output_lines += [
        f"\n{'=' * 52}",
        f"  Step {step_num}: {step['name']}",
        f"{'=' * 52}",
    ]
    placeholder.code("\n".join(output_lines), language="bash")

    cmd = _step_command(step_num, db_path)
    try:
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            text=True,
            bufsize=1,
        ) as proc:
            for line in (proc.stdout or []):
                output_lines.append(line.rstrip())
                if len(output_lines) > 200:
                    del output_lines[:-200]
                placeholder.code("\n".join(output_lines), language="bash")
            proc.wait()
            rc = proc.returncode

        if rc == 0:
            output_lines.append(f"\n[Step {step_num} completed OK]")
        else:
            output_lines.append(f"\n[Step {step_num} FAILED — exit code {rc}]")
        placeholder.code("\n".join(output_lines), language="bash")
        return rc == 0

    except FileNotFoundError as exc:
        output_lines.append(f"[ERROR] Command not found: {exc}")
        placeholder.code("\n".join(output_lines), language="bash")
        return False


# ---------------------------------------------------------------------------
# Tab renderer
# ---------------------------------------------------------------------------

def render_pipeline(db_path: str) -> None:
    section_header(
        "Pipeline runner",
        "Run each step in sequence to build the full ML pipeline. "
        "Steps with unmet prerequisites stay locked until their predecessor completes.",
        eyebrow="Operations",
    )

    if "pl_running" not in st.session_state:
        st.session_state.pl_running = False
    if "pl_output" not in st.session_state:
        st.session_state.pl_output = []

    statuses = {s["num"]: _step_done(s["num"], db_path) for s in STEPS}
    done_count = sum(1 for v in statuses.values() if v)
    progress_ribbon(
        statuses,
        caption=f"{done_count} / {len(STEPS)} complete",
    )

    run_triggered: Optional[int] = None  # step to run, or 0 for "run all"

    for step in STEPS:
        num = step["num"]
        prereq = step["prereq"]
        prereq_ok = prereq is None or statuses.get(prereq, False)
        state = "done" if statuses[num] else "waiting"

        c_card, c_btn = st.columns([8, 2])
        with c_card:
            step_card(
                step_num=num,
                name=step["name"],
                description=step["description"],
                state=state,
            )
        with c_btn:
            if st.button(
                "Run",
                key=f"pl_run_{num}",
                disabled=st.session_state.pl_running or not prereq_ok,
                use_container_width=True,
            ):
                run_triggered = num

    st.markdown("")  # spacer

    col_btn, _ = st.columns([3, 7])
    with col_btn:
        if st.button(
            "Run all steps",
            type="primary",
            disabled=st.session_state.pl_running,
            use_container_width=True,
        ):
            run_triggered = 0

    st.markdown("")  # spacer

    # --- Output window ---
    with st.container(border=True):
        terminal_header("Output")
        placeholder = st.empty()

        if not run_triggered and st.session_state.pl_output:
            placeholder.code("\n".join(st.session_state.pl_output), language="bash")
        elif not run_triggered and not st.session_state.pl_output:
            placeholder.code(
                "No runs yet. Select a step above to begin.", language="bash"
            )

        if run_triggered is not None:
            st.session_state.pl_running = True
            output: List[str] = []

            steps_to_run = (
                [s["num"] for s in STEPS] if run_triggered == 0 else [run_triggered]
            )

            for step_num in steps_to_run:
                if run_triggered == 0 and statuses.get(step_num, False):
                    output.append(f"--- Step {step_num}: already done, skipping ---")
                    placeholder.code("\n".join(output), language="bash")
                    continue

                success = _run_step(step_num, db_path, output, placeholder)
                if not success:
                    break

            st.session_state.pl_output = output
            st.session_state.pl_running = False
            st.rerun()
