"""
main.py — FastAPI application entry point.

Run locally:
    uvicorn main:app --reload --port 8000

Set required env vars first (or create a .env file):
    AZURE_OPENAI_API_KEY=...
    AZURE_OPENAI_ENDPOINT=...
    AZURE_OPENAI_API_VERSION=2024-02-01
"""

import structlog
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router
from config import settings
from skills.loader import list_all_skills  # warm up skill registry at startup


# ── Logging setup ─────────────────────────────────────────────────────────────

log_level = settings["logging"].get("level", "INFO").upper()

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, log_level, logging.INFO)
    ),
)

log = structlog.get_logger()


# ── Lifespan: startup / shutdown ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm up skill registry so first request isn't slow
    skills = list_all_skills()
    log.info("startup.skills_loaded", count=len(skills), skills=[s["name"] for s in skills])
    log.info("startup.ready", host="0.0.0.0", port=8000)
    yield
    # Shutdown (nothing to clean up with InMemorySaver)
    log.info("shutdown")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Service Desk AI",
    description="Standalone AI-powered IT service desk with multi-model routing, skill-based tool loading, and built-in evaluation.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)

# Serve the chat UI at /
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")

@app.get("/", include_in_schema=False)
async def ui():
    return FileResponse(_static / "index.html")
