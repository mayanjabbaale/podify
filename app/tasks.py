"""Celery application and task definitions.

M1 scope: a working Celery app + one no-op ping task to verify the broker
connection.

M2 scope: ``extract_pdf`` task that opens the uploaded PDF from
``storage/pdfs``, runs extraction + chapter detection, persists chapters,
and updates Book.status. Errors are caught and surfaced on the Book row so
the UI can show a meaningful failure state instead of "uploaded" forever.

M3 scope: ``synthesize_audiobook`` task — single-voice Kokoro TTS over a
chapter's cleaned_text, encoded to mp3 via pydub, persisted as an
Episode row. Updates Job.status through queued → synthesizing →
assembling → done (or failed at any step).

Run with: celery -A app.tasks.celery_app worker -P solo -l info
(The `-P solo` flag is required on Windows.)
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from celery import Celery
from sqlalchemy.orm import Session

from app.chapters import detect_chapters
from app.config import get_settings
from app.db import task_session
from app.extraction import clean_text, extract_text
from app.models import Book, Chapter, Episode, EpisodeFormat, Job, JobMode, JobStatus

logger = logging.getLogger(__name__)


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


@celery_app.task(
    name="app.tasks.extract_pdf",
    bind=True,
    autoretry_for=(),  # no automatic retries — failures should be visible to the user
    acks_late=True,
)
def extract_pdf(self, book_id: int) -> dict:
    """Extract text + chapter boundaries for an uploaded book.

    Idempotent-ish: re-running will replace the book's chapters. That lets
    us recover from a worker crash without leaving the book stuck in
    "extracting" — the user just re-uploads or the cleanup task does.

    Returns a small dict (serialized to the Celery result backend) with the
    chapter count and detection strategy. The UI doesn't read this directly;
    it polls GET /api/books/{id} instead.
    """
    session: Session = task_session()
    try:
        book = session.get(Book, book_id)
        if book is None:
            logger.warning("extract_pdf: book %s not found", book_id)
            return {"book_id": book_id, "error": "not_found"}

        book.status = "extracting"
        session.flush()

        pdf_path = Path(book.storage_path)
        try:
            raw = extract_text(pdf_path)
            cleaned = clean_text(raw)
        except FileNotFoundError:
            book.status = "failed"
            book.title = book.title + " (PDF missing on disk)"
            session.commit()
            logger.exception("extract_pdf: PDF missing for book %s", book_id)
            return {"book_id": book_id, "error": "pdf_missing"}
        except Exception:
            book.status = "failed"
            session.commit()
            logger.exception("extract_pdf: extraction failed for book %s", book_id)
            return {"book_id": book_id, "error": "extraction_failed"}

        detected = detect_chapters(pdf_path, cleaned)

        # Wipe existing chapters so a re-run starts clean. Cascade through
        # jobs (none should exist yet at this stage, but be safe).
        for existing in list(book.chapters):
            session.delete(existing)
        session.flush()

        if not detected:
            book.status = "failed"
            session.commit()
            logger.warning(
                "extract_pdf: no chapters detected for book %s (empty text?)",
                book_id,
            )
            return {"book_id": book_id, "error": "no_chapters"}

        for ch in detected:
            session.add(
                Chapter(
                    book_id=book.id,
                    index=ch.index,
                    title=ch.title[:512],  # schema ceiling
                    raw_text=ch.raw_text,
                    cleaned_text=ch.cleaned_text,
                    char_count=ch.char_count,
                    detection_strategy=ch.detection_strategy,
                )
            )

        book.status = "ready"
        session.commit()

        logger.info(
            "extract_pdf: book %s -> %d chapters (strategy=%s)",
            book_id,
            len(detected),
            detected[0].detection_strategy,
        )
        return {
            "book_id": book_id,
            "chapter_count": len(detected),
            "detection_strategy": detected[0].detection_strategy,
        }
    except Exception:
        session.rollback()
        # Best-effort status update — don't let a failed status write mask the real error.
        try:
            book = session.get(Book, book_id)
            if book is not None:
                book.status = "failed"
                session.commit()
        except Exception:
            session.rollback()
        logger.exception("extract_pdf: unhandled error for book %s", book_id)
        raise
    finally:
        session.close()


# --- M3: single-voice audiobook synthesis -------------------------------------


# Job.status values during which a second POST to create a job should be
# rejected with 409. ``done`` and ``failed`` are terminal — the user can
# create a new job (a retry). Used by the API layer; duplicated here so
# the rule lives next to the job lifecycle documentation.
_NON_TERMINAL_JOB_STATUSES = frozenset(
    {
        JobStatus.queued,
        JobStatus.extracting,
        JobStatus.scripting,
        JobStatus.synthesizing,
        JobStatus.assembling,
    }
)


@celery_app.task(
    name="app.tasks.synthesize_audiobook",
    bind=True,
    autoretry_for=(),  # no automatic retries — failures should be visible
    acks_late=True,
)
def synthesize_audiobook(self, job_id: int) -> dict:
    """Synthesize one chapter's text with Kokoro and persist an Episode.

    Lifecycle:
        queued → synthesizing → assembling → done   (happy path)
        * → failed                                        (any error)

    Returns a small dict for the Celery result backend. The UI polls
    ``GET /api/jobs/{id}`` instead of reading this directly.
    """
    settings = get_settings()
    session: Session = task_session()
    audio_path: Path | None = None
    try:
        job = session.get(Job, job_id)
        if job is None:
            logger.warning("synthesize_audiobook: job %s not found", job_id)
            return {"job_id": job_id, "error": "not_found"}

        chapter = session.get(Chapter, job.chapter_id)
        if chapter is None:
            job.status = JobStatus.failed
            job.error_message = "Chapter no longer exists"
            session.commit()
            return {"job_id": job_id, "error": "chapter_missing"}

        # --- synthesizing ------------------------------------------------
        job.status = JobStatus.synthesizing
        job.progress_pct = 5
        job.current_stage_detail = "synthesizing chapter"
        session.flush()

        # Lazy import: keeps worker boot fast when no TTS task is running,
        # and lets tests monkeypatch app.tts.synthesize_text without ever
        # importing kokoro_onnx (which needs model files on disk).
        from app.tts import synthesize_text

        try:
            samples, sample_rate = synthesize_text(
                chapter.cleaned_text, voice=settings.kokoro_voice_narrator, speed=1.0
            )
        except ValueError as e:
            # Empty text, etc. — fail the job with a meaningful message.
            job.status = JobStatus.failed
            job.error_message = str(e)
            session.commit()
            logger.warning(
                "synthesize_audiobook: synthesis rejected for job %s: %s", job_id, e
            )
            return {"job_id": job_id, "error": "synthesis_rejected"}
        except FileNotFoundError as e:
            # Kokoro model files missing on disk.
            job.status = JobStatus.failed
            job.error_message = str(e)
            session.commit()
            logger.error("synthesize_audiobook: %s", e)
            return {"job_id": job_id, "error": "model_missing"}

        if samples.size == 0:
            job.status = JobStatus.failed
            job.error_message = "Kokoro returned no audio"
            session.commit()
            return {"job_id": job_id, "error": "no_audio"}

        audio_seconds = float(samples.shape[0]) / float(sample_rate)

        # --- assembling --------------------------------------------------
        job.status = JobStatus.assembling
        job.progress_pct = 80
        job.current_stage_detail = "encoding mp3"
        session.flush()

        audio_dir: Path = settings.storage_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = audio_dir / f"episode_{job_id}.mp3"

        # pydub is imported lazily so an import failure (e.g. pyaudioop
        # missing on Python 3.13) doesn't kill the worker at boot — it
        # only surfaces when an actual synthesis task runs, and we want
        # a clean failed-job update rather than a worker crash.
        try:
            from pydub import AudioSegment  # type: ignore[import-untyped]
        except Exception as e:
            job.status = JobStatus.failed
            job.error_message = (
                f"pydub could not be imported ({type(e).__name__}: {e}). "
                "Run `pip install audioop-lts` (provides `pyaudioop` on Python 3.13)."
            )
            session.commit()
            logger.exception("synthesize_audiobook: pydub import failed")
            return {"job_id": job_id, "error": "pydub_unavailable"}

        segment = AudioSegment(
            samples.tobytes(),
            frame_rate=sample_rate,
            sample_width=4,  # float32 = 4 bytes
            channels=1,
        )
        try:
            segment.export(str(audio_path), format="mp3", bitrate="128k")
        except Exception as e:
            # pydub's CouldntInvokeError for missing ffmpeg has a long,
            # unfriendly default message — keep the original but note the
            # most common cause.
            hint = ""
            if shutil.which("ffmpeg") is None:
                hint = " (ffmpeg not found on PATH)"
            job.status = JobStatus.failed
            job.error_message = f"mp3 export failed{hint}: {e}"
            session.commit()
            logger.exception("synthesize_audiobook: mp3 export failed for job %s", job_id)
            return {"job_id": job_id, "error": "export_failed"}

        # --- Episode row -------------------------------------------------
        now = datetime.utcnow()
        episode = Episode(
            job_id=job.id,
            storage_path=str(audio_path),
            duration_seconds=audio_seconds,
            format=EpisodeFormat.mp3,
            metadata_json={
                "voice": settings.kokoro_voice_narrator,
                "sample_rate": sample_rate,
                "audio_seconds": audio_seconds,
                "mode": JobMode.audiobook.value,
            },
            created_at=now,
            retention_until=now + timedelta(days=settings.retention_days),
        )
        session.add(episode)
        session.flush()

        job.status = JobStatus.done
        job.progress_pct = 100
        job.current_stage_detail = None
        job.completed_at = datetime.utcnow()
        session.commit()

        logger.info(
            "synthesize_audiobook: job %s done (%.1fs, episode %s)",
            job_id,
            audio_seconds,
            episode.id,
        )
        return {
            "job_id": job_id,
            "episode_id": episode.id,
            "duration_seconds": audio_seconds,
        }
    except Exception:
        session.rollback()
        # Best-effort status write so the UI sees the failure.
        try:
            job = session.get(Job, job_id)
            if job is not None and job.status not in (JobStatus.done, JobStatus.failed):
                job.status = JobStatus.failed
                session.commit()
        except Exception:
            session.rollback()
        # Clean up a half-written mp3 so it doesn't accumulate on retry failures.
        if audio_path is not None and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                logger.warning("Could not remove partial mp3 at %s", audio_path)
        logger.exception("synthesize_audiobook: unhandled error for job %s", job_id)
        raise
    finally:
        session.close()
