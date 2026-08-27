"""SQLAlchemy engine, session factory, and Celery task-scoped helpers.

SQLite needs:
- WAL journal mode (set once at engine init) so Celery workers don't see
  'database is locked' errors
- A connection per task — never share a connection across worker forks
- The parent directory to exist before the engine is created

Postgres needs none of this, but we keep the entry point uniform.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a SQLite file before engine init."""
    if not database_url.startswith("sqlite"):
        return
    # Strip the sqlite:/// prefix; the rest is the filesystem path.
    # Handle both sqlite:///./relative.db and sqlite:////absolute.db forms.
    path_part = database_url.split("sqlite:///")[-1]
    db_path = Path(path_part)
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _make_engine() -> Engine:
    settings = get_settings()
    _ensure_sqlite_dir(settings.database_url)

    connect_args: dict = {}
    if settings.is_sqlite:
        # check_same_thread=False lets a Celery worker thread use the engine.
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        future=True,
    )

    if settings.is_sqlite:
        # WAL mode is per-connection, so apply on every new connection.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine: Engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def task_session() -> Session:
    """Celery task-scoped session.

    Celery's solo pool runs tasks in the worker process; one session per task
    is safe. If we ever move to prefork or threads, this becomes the seam
    where we'd add per-thread/per-process engine creation.
    """
    return SessionLocal()
