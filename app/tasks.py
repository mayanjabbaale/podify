"""Celery application and stub task definitions.

M1 scope: a working Celery app + one no-op ping task to verify the broker
connection. M2+ will add extract_pdf, generate_script, synthesize_turns,
assemble_episode, cleanup_old_episodes.

Run with: celery -A app.tasks.celery_app worker -P solo -l info
(The `-P solo` flag is required on Windows.)
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    celery_app = Celery(
        "podify",
        broker=settings.redis_url,
        backend=settings.redis_url,
    )
    celery_app.conf.update(
        task_time_limit=settings.celery_task_time_limit,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # Solo pool is single-threaded; bump visibility_timeout so long-running
        # tasks don't get redelivered while still in flight.
        broker_transport_options={"visibility_timeout": settings.celery_task_time_limit},
    )
    return celery_app


celery_app = make_celery()


@celery_app.task(name="app.tasks.ping")
def ping() -> str:
    """No-op task used by the M1 smoke test to verify the broker connection."""
    return "pong"
