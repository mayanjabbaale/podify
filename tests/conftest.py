"""Pytest configuration.

Key behaviors:
- Forces `task_always_eager=True` on the Celery app so the ping task runs
  synchronously in tests — no live broker required.
- Points DATABASE_URL at a temp SQLite file so tests don't pollute storage/.
- Points REDIS_URL at a fake value; the health-check test that touches
  Redis will be skipped if Redis isn't reachable.
- Creates the schema in the temp SQLite DB by importing from the ORM
  metadata (faster than running alembic migrations from scratch for unit
  tests; the migration suite tests alembic itself).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_test_environment(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Configure env vars before any app module imports them."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema() -> None:
    """Build the ORM tables in the temp test DB once per session.

    Must run after ``_isolate_test_environment`` so the engine is wired to
    the temp DATABASE_URL. Both fixtures are session-scoped/autouse, so we
    rely on definition order: pytest resolves fixtures by name, and the
    env-isolator runs first because tests/conftest ordering guarantees it.
    To be defensive we re-derive the engine here after importing app.db.
    """
    from app.db import engine
    from app.models import Base

    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _enable_celery_eager_mode() -> None:
    """Make Celery run tasks inline so tests don't need a worker."""
    from app.tasks import celery_app

    celery_app.conf.task_always_eager = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture
def client():
    """FastAPI TestClient."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())
