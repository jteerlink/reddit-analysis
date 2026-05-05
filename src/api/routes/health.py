"""Health endpoint for API and database reachability."""

from fastapi import APIRouter

from src.db.connection import (
    current_target,
    database_reachable,
    get_backend,
    redact_target,
)

router = APIRouter()


@router.get("/health")
def health():
    reachable = database_reachable(readonly=True)
    return {
        "status": "ok" if reachable else "degraded",
        "backend": get_backend(),
        "db_reachable": reachable,
        "db_path_or_url": redact_target(current_target(readonly=True)),
    }
