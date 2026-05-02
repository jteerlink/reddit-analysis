"""Pipeline status and run endpoints with SSE streaming."""

import asyncio
import os
import sqlite3
import sys
from asyncio import Queue
from pathlib import Path
from typing import AsyncGenerator, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = os.environ.get("REDDIT_DB_PATH", "historical_reddit_data.db")

STEPS = [
    {"num": 1, "name": "Prerequisites", "description": "Install dependencies, verify DB, create directories", "prereq": None},
    {"num": 2, "name": "Preprocessing", "description": "Clean text, generate sentence embeddings", "prereq": 1},
    {"num": 3, "name": "Weak Labels", "description": "VADER scoring → data/weak_labels.csv (≥30k rows)", "prereq": 2},
    {"num": 4, "name": "Train Sentiment Model", "description": "Fine-tune DistilBERT on weak labels (20–40 min on MPS)", "prereq": 3},
    {"num": 5, "name": "Batch Inference", "description": "Run trained model on all preprocessed records", "prereq": 4},
    {"num": 6, "name": "Topic Modeling", "description": "BERTopic discovery, coherence scoring, week-over-week tracking", "prereq": 5},
    {"num": 7, "name": "Time Series & Forecast", "description": "Daily aggregation + 14-day Prophet forecast", "prereq": 6},
]


def _db_count(query: str) -> int:
    abs_db = Path(DB_PATH) if Path(DB_PATH).is_absolute() else PROJECT_ROOT / DB_PATH
    try:
        conn = sqlite3.connect(str(abs_db))
        row = conn.execute(query).fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _step_done(step_num: int) -> bool:
    abs_db = Path(DB_PATH) if Path(DB_PATH).is_absolute() else PROJECT_ROOT / DB_PATH
    if step_num == 1:
        return abs_db.exists()
    if step_num == 2:
        return (PROJECT_ROOT / "models" / "embeddings_cache.npy").exists()
    if step_num == 3:
        csv = PROJECT_ROOT / "data" / "weak_labels.csv"
        if not csv.exists():
            return False
        try:
            with open(csv) as f:
                return sum(1 for _ in f) - 1 >= 30000
        except Exception:
            return False
    if step_num == 4:
        return (PROJECT_ROOT / "models" / "sentiment_v1" / "config.json").exists()
    if step_num == 5:
        return _db_count("SELECT COUNT(*) FROM sentiment_predictions") > 0
    if step_num == 6:
        return _db_count("SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50") >= 20
    if step_num == 7:
        return _db_count("SELECT COUNT(*) FROM sentiment_forecast") > 0
    return False


def _step_command(step_num: int) -> List[str]:
    py = sys.executable
    abs_db = str(Path(DB_PATH) if Path(DB_PATH).is_absolute() else PROJECT_ROOT / DB_PATH)

    if step_num == 1:
        return ["uv", "pip", "install", "-e", ".[ml,production]", "-q"]
    if step_num == 2:
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from src.ml.preprocessing import run_preprocessing;"
            f"r = run_preprocessing(db_path='{abs_db}', cache_dir='models/',"
            "batch_size=1000, embed_batch_size=256, mlflow_tracking=True);"
            "print(f\"Total: {{r['total']:,}}  Filtered: {{r['filtered']:,}}"
            "  Kept: {{r['kept']:,}}  Device: {{r['device']}}\")"
        )
        return [py, "-c", code]
    if step_num == 3:
        return [py, "scripts/generate_weak_labels.py", "--db", abs_db,
                "--output", "data/weak_labels.csv", "--threshold", "0.5",
                "--include-neutral", "--neutral-threshold", "0.1"]
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
        return [py, "scripts/batch_inference.py", "--db", abs_db,
                "--model-dir", "models/sentiment_v1", "--batch-size", "1000"]
    if step_num == 6:
        return [py, "scripts/train_topic_model.py", "--db", abs_db,
                "--cache-dir", "models/", "--days", "90",
                "--min-cluster-size", "30", "--min-topic-size", "30", "--nr-topics", "auto"]
    if step_num == 7:
        return [py, "scripts/run_timeseries.py", "--db", abs_db,
                "--days", "90", "--forecast-days", "14"]
    raise ValueError(f"Unknown step: {step_num}")


@router.get("/status")
def pipeline_status():
    statuses = {}
    for step in STEPS:
        num = step["num"]
        done = _step_done(num)
        prereq = step["prereq"]
        prereq_ok = prereq is None or _step_done(prereq)
        statuses[num] = {
            "num": num,
            "name": step["name"],
            "description": step["description"],
            "done": done,
            "prereq": prereq,
            "prereq_ok": prereq_ok,
            "state": "done" if done else ("idle" if prereq_ok else "locked"),
        }
    return list(statuses.values())


async def _stream_step(step_num: int, queue: Queue) -> bool:
    step = STEPS[step_num - 1]
    await queue.put(f"data: === Step {step_num}: {step['name']} ===\n\n")
    cmd = _step_command(step_num)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
        )
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            await queue.put(f"data: {line}\n\n")
        await proc.wait()
        rc = proc.returncode
        status = f"[Step {step_num} {'OK' if rc == 0 else f'FAILED (exit {rc})'}]"
        await queue.put(f"data: {status}\n\n")
        return rc == 0
    except FileNotFoundError as exc:
        await queue.put(f"data: [ERROR] {exc}\n\n")
        return False


async def _run_generator(steps: List[int]) -> AsyncGenerator[str, None]:
    queue: Queue = Queue()

    async def _worker():
        for step_num in steps:
            ok = await _stream_step(step_num, queue)
            if not ok:
                break
        await queue.put(None)

    asyncio.create_task(_worker())
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


@router.get("/run/{step_num}")
async def run_step(step_num: int):
    if step_num < 1 or step_num > 7:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="step_num must be 1–7")
    return StreamingResponse(
        _run_generator([step_num]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/run-all")
async def run_all():
    return StreamingResponse(
        _run_generator(list(range(1, 8))),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
