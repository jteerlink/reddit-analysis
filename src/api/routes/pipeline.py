"""Pipeline status and run endpoints with SSE streaming."""

import asyncio
import hmac
import fcntl
import os
import sys
from asyncio import Queue
from pathlib import Path
from typing import AsyncGenerator, List, Optional, TypedDict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import StreamingResponse

from src.db.connection import connection, database_reachable, execute, get_backend

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = os.environ.get("REDDIT_DB_PATH") or os.environ.get("DATABASE_PATH") or "historical_reddit_data.db"
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
BUSY_EVENT = (
    "event: busy\ndata: Pipeline already running. Wait for current run to finish.\n\n"
)
_PIPELINE_RUN_LOCK = asyncio.Lock()

class PipelineStep(TypedDict):
    num: int
    name: str
    description: str
    prereq: int | None


STEPS: list[PipelineStep] = [
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
    {
        "num": 8,
        "name": "Analysis Artifacts",
        "description": "Backfill persisted dashboard intelligence artifacts",
        "prereq": 7,
    },
    {
        "num": 9,
        "name": "LLM Enrichment",
        "description": "Ollama narrative summaries, thread analysis, analyst brief, topic labels",
        "prereq": 8,
    },
]


def _db_count(query: str) -> int:
    try:
        with connection(readonly=True) as conn:
            row = execute(conn, query).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _llm_topic_labels_done() -> bool:
    total = _db_count("SELECT COUNT(*) FROM topics WHERE topic_id != -1")
    if total <= 0:
        return (
            _db_count(
                "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded' AND provider = 'ollama'"
            )
            > 0
        )
    labeled = _db_count(
        "SELECT COUNT(*) FROM topics WHERE topic_id != -1 AND llm_label IS NOT NULL AND llm_label != ''"
    )
    return labeled >= total


def _pipeline_db_path() -> Path:
    path = Path(DB_PATH)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _sentiment_model_ready(*, include_candidate: bool = False) -> bool:
    from src.ml.sentiment import pipeline_candidate_dir, pipeline_model_dir

    db = str(_pipeline_db_path())
    try:
        if get_backend() == "sqlite" and not Path(db).is_file():
            return False
        if include_candidate and pipeline_candidate_dir(db):
            return True
        return (PROJECT_ROOT / pipeline_model_dir(db) / "config.json").is_file()
    except Exception:
        return False


def _step_done(step_num: int) -> bool:
    abs_db = _pipeline_db_path()
    if step_num == 1:
        if get_backend() == "postgres":
            return database_reachable(readonly=True)
        return abs_db.exists()
    if step_num == 2:
        from src.ml.embedding_cache import published_embedding_paths

        try:
            return all(path.exists() for path in published_embedding_paths(PROJECT_ROOT / "models"))
        except (OSError, ValueError, KeyError):
            return False
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
        return _sentiment_model_ready(include_candidate=True)
    if step_num == 5:
        return _db_count("SELECT COUNT(*) FROM sentiment_predictions") > 0
    if step_num == 6:
        return (
            _db_count("SELECT COUNT(*) FROM topics WHERE coherence_score >= 0.50") >= 20
        )
    if step_num == 7:
        return _db_count("SELECT COUNT(*) FROM sentiment_forecast") > 0
    if step_num == 8:
        return (
            _db_count(
                "SELECT COUNT(*) FROM analysis_artifacts WHERE status = 'succeeded'"
            )
            > 0
        )
    if step_num == 9:
        return _llm_topic_labels_done()
    return False


def _step_command(step_num: int, promote_candidate: bool = False) -> List[str]:
    py = sys.executable
    abs_db = str(_pipeline_db_path())

    if step_num == 1:
        return ["uv", "pip", "install", "-e", ".[ml,production]", "-q"]
    if step_num == 2:
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from src.ml.preprocessing import run_preprocessing;"
            f"r = run_preprocessing(db_path={abs_db!r}, cache_dir='models/',"
            "batch_size=1000, embed_batch_size=256, mlflow_tracking=True);"
            "print(f\"Total: {{r['total']:,}}  Filtered: {{r['filtered']:,}}"
            "  Kept: {{r['kept']:,}}  Device: {{r['device']}}\")"
        )
        return [py, "-c", code]
    if step_num == 3:
        return [
            py,
            "scripts/generate_weak_labels.py",
            "--db",
            abs_db,
            "--output",
            "data/weak_labels.csv",
            "--threshold",
            "0.5",
            "--include-neutral",
            "--neutral-threshold",
            "0.1",
        ]
    if step_num == 4:
        return [py, "scripts/batch_inference.py", "--db", abs_db, "--train-candidate"]
    if step_num == 5:
        return [
            py, "scripts/batch_inference.py", "--db", abs_db, "--batch-size", "1000",
            *(["--promote-candidate"] if promote_candidate else []),
        ]
    if step_num == 6:
        return [
            py,
            "scripts/train_topic_model.py",
            "--db",
            abs_db,
            "--cache-dir",
            "models/",
            "--days",
            "90",
            "--min-cluster-size",
            "30",
            "--min-topic-size",
            "30",
            "--nr-topics",
            "auto",
        ]
    if step_num == 7:
        return [
            py,
            "scripts/run_timeseries.py",
            "--db",
            abs_db,
            "--days",
            "90",
            "--forecast-days",
            "14",
        ]
    if step_num == 8:
        return [py, "scripts/run_analysis_jobs.py", "--db", abs_db]
    if step_num == 9:
        return [py, "scripts/run_enrichment.py", "--db", abs_db, "--all"]
    raise ValueError(f"Unknown step: {step_num}")


@router.get("/status")
def pipeline_status() -> list[dict]:
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


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _stream_step(step_num: int, queue: Queue, promote_candidate: bool = False) -> bool:
    step = STEPS[step_num - 1]
    await queue.put(f"data: === Step {step_num}: {step['name']} ===\n\n")
    cmd = _step_command(step_num, promote_candidate)
    proc: Optional[asyncio.subprocess.Process] = None
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
    finally:
        if proc is not None:
            await _terminate_process(proc)


async def _run_generator(steps: List[int], promote_candidate: bool = False, refresh: bool = False) -> AsyncGenerator[str, None]:
    if _PIPELINE_RUN_LOCK.locked():
        yield BUSY_EVENT
        return

    lock_path = PROJECT_ROOT / ".pipeline_status" / "workspace.lock"
    lock_path.parent.mkdir(exist_ok=True)
    lock = lock_path.open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        yield BUSY_EVENT
        return

    await _PIPELINE_RUN_LOCK.acquire()
    queue: Queue = Queue(maxsize=100)

    async def _worker() -> None:
        cancelled = False
        try:
            for step_num in steps:
                if refresh and step_num == 6:
                    current = await asyncio.to_thread(_db_count, "SELECT COUNT(*) FROM topics")
                    pending = await asyncio.to_thread(_db_count, "SELECT COUNT(*) FROM topic_refit_required")
                    if current and not pending:
                        continue
                if promote_candidate and step_num == 5:
                    ok = await _stream_step(step_num, queue, True)
                else:
                    ok = await _stream_step(step_num, queue)
                if not ok:
                    await queue.put("event: result\ndata: failed\n\n")
                    break
            else:
                await queue.put("event: result\ndata: succeeded\n\n")
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            await queue.put(f"data: [ERROR] {exc}\n\n")
            await queue.put("event: result\ndata: failed\n\n")
        finally:
            if not cancelled:
                await queue.put(None)

    worker = asyncio.create_task(_worker())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    except asyncio.CancelledError:
        worker.cancel()
        raise
    finally:
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        lock.close()
        _PIPELINE_RUN_LOCK.release()


_bearer = HTTPBearer(auto_error=False)


def authorize_operator(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    token = os.environ.get("PIPELINE_OPERATOR_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Pipeline execution is disabled")
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode(), token.encode()
    ):
        raise HTTPException(
            status_code=401, detail="Invalid operator token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/run/{step_num}", dependencies=[Depends(authorize_operator)])
async def run_step(step_num: int) -> StreamingResponse:
    if not 1 <= step_num <= len(STEPS):
        raise HTTPException(status_code=400, detail=f"step_num must be 1–{len(STEPS)}")
    prereq = STEPS[step_num - 1]["prereq"]
    prereq_ok = prereq is None or await asyncio.to_thread(_step_done, prereq)
    if not prereq_ok:
        raise HTTPException(status_code=409, detail="Pipeline prerequisite is incomplete")
    return StreamingResponse(
        _run_generator([step_num], promote_candidate=step_num == 5),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/run-all", dependencies=[Depends(authorize_operator)])
async def run_all(rebuild: bool = False) -> StreamingResponse:
    steps = list(range(1, len(STEPS) + 1))
    if not rebuild:
        if await asyncio.to_thread(_step_done, 1):
            steps.remove(1)
        if await asyncio.to_thread(_sentiment_model_ready):
            steps.remove(4)
    return StreamingResponse(
        _run_generator(steps, promote_candidate=4 in steps, refresh=not rebuild),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
