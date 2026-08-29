"""Job creation + status endpoints (M3).

POST /api/books/{book_id}/chapters/{chapter_id}/jobs
    Body: ``{"mode": "audiobook" | "podcast"}``
    202 + JobOut, enqueues the Celery task.
    404 if book or chapter missing, or chapter not in book.
    409 if a non-terminal job already exists for that chapter.

GET /api/jobs/{job_id}
    JobOut. 404 if not found.

Only ``audiobook`` mode is supported in M3. ``podcast`` is rejected with
400 because M4/M5 haven't landed the script generation and two-voice
synthesis tasks yet; the API exists now so M5 only has to flip the
allowed-mode set.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Book, Chapter, Job, JobMode, JobStatus, PodcastScript
from app.schemas import JobCreateRequest, JobOut, PodcastScriptOut
from app.tasks import _NON_TERMINAL_JOB_STATUSES, synthesize_audiobook, generate_podcast_script_task


router = APIRouter()


# Modes the API will accept right now. Extend this set as M4/M5 land.
_SUPPORTED_MODES_FOR_NOW: frozenset[JobMode] = frozenset({JobMode.audiobook, JobMode.podcast})


def _serialize_job(job: Job, episode_id: int | None) -> dict:
    script_id = None
    if hasattr(job, "script") and job.script is not None:
        script_id = job.script.id

    res = {
        "id": job.id,
        "chapter_id": job.chapter_id,
        "mode": job.mode,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "current_stage_detail": job.current_stage_detail,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "episode_id": episode_id,
        "script_id": script_id,
    }
    print(f"DEBUG: _serialize_job result: {res}")
    return res


@router.post(
    "/api/books/{book_id}/chapters/{chapter_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    book_id: int,
    chapter_id: int,
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
) -> JobOut:
    """Create a generation job for one chapter and enqueue the Celery task."""
    if payload.mode not in _SUPPORTED_MODES_FOR_NOW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Mode {payload.mode.value!r} is not enabled in this build. "
                f"Supported: {sorted(m.value for m in _SUPPORTED_MODES_FOR_NOW)}"
            ),
        )

    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    chapter = db.get(Chapter, chapter_id)
    if chapter is None or chapter.book_id != book_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found in this book",
        )

    # Reject if a non-terminal job already exists for this chapter.
    # ``first()`` is fine — even with multiple in-flight jobs (shouldn't
    # happen given this check) we only need to know "any exists".
    in_flight = db.execute(
        select(Job)
        .where(Job.chapter_id == chapter_id)
        .where(Job.status.in_([s.value for s in _NON_TERMINAL_JOB_STATUSES]))
        .order_by(Job.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if in_flight is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A {in_flight.status.value} job already exists for this chapter "
                f"(job_id={in_flight.id}). Wait for it to finish or fail."
            ),
        )

    job = Job(
        chapter_id=chapter_id,
        mode=payload.mode,
        status=JobStatus.queued,
        progress_pct=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if payload.mode == JobMode.audiobook:
        synthesize_audiobook.delay(job.id)
    elif payload.mode == JobMode.podcast:
        generate_podcast_script_task.delay(job.id)


    # Eager-mode Celery (tests) runs the task synchronously and mutates the
    # DB row in a separate session. Our ``db`` session's identity map still
    # holds the stale ``job`` we just committed. Expire it so the response
    # reflects post-task state (e.g. status="done" + episode_id populated).
    db.expire(job)

    fresh = db.get(Job, job.id)
    episode_id = fresh.episode.id if fresh.episode is not None else None
    return _serialize_job(fresh, episode_id=episode_id)


@router.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobOut:
    """Read current state of a generation job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    episode_id = job.episode.id if job.episode is not None else None
    return _serialize_job(job, episode_id)


@router.get("/api/jobs/{job_id}/script", response_model=PodcastScriptOut)
def get_job_script(job_id: int, db: Session = Depends(get_db)) -> PodcastScriptOut:
    """Retrieve the generated podcast script for a job."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.mode != JobMode.podcast:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not in podcast mode")
    if job.script is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not yet generated")

    return PodcastScriptOut.model_validate(job.script)
