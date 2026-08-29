"""FastAPI application factory and top-level routes.

M1 scope: app factory, Jinja2 mount, /health, and a placeholder upload page
so the root URL renders something.

M2 scope: book upload + detail endpoints (see app.api_books), with the
upload page now posting to the real handler and the book detail page
polling for chapters while extraction is in flight.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api_books import router as books_router
from app.api_episodes import router as episodes_router
from app.api_jobs import router as jobs_router
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_redis_client
from app.schemas import HealthResponse


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Podify",
        version="0.1.0",
        description="PDF -> Audiobook / Podcast converter",
    )

    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))
    app.state.templates = templates

    @app.get("/health", response_model=HealthResponse)
    def health(
        db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        db_status = "ok"
        redis_status = "ok"

        try:
            db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — health endpoint must never 500
            db_status = "error"

        try:
            client = get_redis_client(settings)
            client.ping()
        except Exception:  # noqa: BLE001
            redis_status = "error"

        overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
        body = HealthResponse(status=overall, db=db_status, redis=redis_status)
        status_code = 200 if overall == "ok" else 503
        return JSONResponse(content=body.model_dump(), status_code=status_code)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "upload.html", {})

    app.include_router(books_router)
    app.include_router(jobs_router)
    app.include_router(episodes_router)

    return app


app = create_app()
