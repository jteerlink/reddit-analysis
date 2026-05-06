"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import analysis, dashboard, health, pipeline

app = FastAPI(title="Reddit Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(analysis.router, prefix="/analysis")
app.include_router(health.router)
app.include_router(pipeline.router, prefix="/pipeline")
