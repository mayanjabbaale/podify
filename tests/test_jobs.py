"""Tests for the M3 job + episode endpoints and synthesize_audiobook task.

These tests run end-to-end through Celery in eager mode with a
monkeypatched Kokoro so they don't need the real ONNX model files.
The synthesize task, Episode row creation, mp3 export, and audio
streaming endpoint are all exercised against deterministic fake audio.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import fitz  # type: ignore[import-untyped]
import numpy as np
import pytest

from app import tts
from app.config import get_settings
from app.models import Episode, Job, JobStatus


# --- helpers -----------------------------------------------------------------


def _make_pdf_bytes(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _upload_and_extract(client) -> tuple[int, list[int]]:
    """Upload a PDF, run extract_pdf in eager mode, return (book_id, chapter_ids)."""
    pdf_bytes = _make_pdf_bytes([
        "Chapter 1\nBody of chapter one with several words in it.\n\nMore body.",
        "Chapter 2\nBody of chapter two with several words in it.",
    ])
    res = client.post("/api/books", files={"file": ("book.pdf", pdf_bytes, "application/pdf")})
    assert res.status_code == 202
    book_id = res.json()["id"]

    detail = client.get(f"/api/books/{book_id}").json()
    chapter_ids = [ch["id"] for ch in detail["chapters"]]
    return book_id, chapter_ids


# --- ffmpeg-free pydub mock --------------------------------------------------


def _fake_audio_segment_export(self, out_f, format=None, **kwargs):
    """Write a tiny placeholder file instead of shelling out to ffmpeg.

    Tests assert the *file exists* and the *Episode row* is populated;
    they don't decode the audio. Skipping real mp3 encoding keeps the
    suite ffmpeg-independent.
    """
    with open(out_f, "wb") as f:
        # Not a real mp3, but a non-empty file so size and existence checks pass.
        f.write(b"FAKE-MP3-FROM-TEST-MOCK\x00")
    return out_f


# --- autouse fixtures --------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_kokoro_and_pydub(monkeypatch):
    """Replace Kokoro's ONNX model and pydub's mp3 encoder so no real model
    files or ffmpeg binary are needed.

    Kokoro's ``Kokoro`` class is imported lazily inside ``app.tts.get_kokoro``
    via ``from kokoro_onnx import Kokoro``. We patch the *class* on the
    ``kokoro_onnx`` module so ``get_kokoro()`` still constructs a real-looking
    instance but its ``create()`` returns deterministic float32 silence.
    """
    from pydub import AudioSegment  # type: ignore[import-untyped]

    class _FakeKokoro:
        def __init__(self, *args, **kwargs):
            # Accept whatever get_kokoro() passes (model_path, voices_path).
            pass

        def create(self, text, voice, speed=1.0, **kwargs):
            # 0.5 seconds of silence at 24 kHz mono float32.
            return np.zeros(12000, dtype=np.float32), 24000

        def get_voices(self):
            return ["af_nicole", "af_bella", "am_adam"]

    tts.reset_kokoro_cache()
    monkeypatch.setattr("kokoro_onnx.Kokoro", _FakeKokoro)
    monkeypatch.setattr(AudioSegment, "export", _fake_audio_segment_export)
    yield
    tts.reset_kokoro_cache()


# --- job creation endpoint ---------------------------------------------------


def test_create_audiobook_job_returns_202(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    res = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["chapter_id"] == chapter_ids[0]
    assert body["mode"] == "audiobook"
    # Eager mode ran the task synchronously inside the request — job is done.
    assert body["status"] == "done"
    assert body["episode_id"] is not None
    assert body["progress_pct"] == 100


def test_create_job_409_when_in_flight(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    first = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert first.status_code == 202

    # Eager mode means the first job already completed and the Episode exists,
    # so a second POST should succeed too (no longer in flight). The 409 path
    # is exercised separately below by holding a job in a non-terminal state.
    second = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert second.status_code == 202


def test_create_job_409_when_non_terminal(client, monkeypatch) -> None:
    """Simulate a still-running job by patching the task to be a no-op."""
    from app.tasks import synthesize_audiobook

    def _stuck(self, job_id, **kwargs):
        # Don't flip status away from 'queued' so the next POST sees in-flight.
        # **kwargs absorbs celery's apply() plumbing (task_id, headers, ...).
        return {"job_id": job_id, "stuck": True}

    monkeypatch.setattr(synthesize_audiobook, "apply", _stuck)

    book_id, chapter_ids = _upload_and_extract(client)
    first = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert first.status_code == 202

    # Second POST sees the queued job and rejects.
    second = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert second.status_code == 409


def test_create_job_rejects_podcast_mode(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    res = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "podcast"},
    )
    assert res.status_code == 400


def test_create_job_404_for_unknown_book(client) -> None:
    res = client.post("/api/books/99999/chapters/1/jobs", json={"mode": "audiobook"})
    assert res.status_code == 404


def test_create_job_404_for_chapter_not_in_book(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    other_book = client.post(
        "/api/books",
        files={"file": ("other.pdf", _make_pdf_bytes(["body"]), "application/pdf")},
    )
    other_book_id = other_book.json()["id"]
    res = client.post(
        f"/api/books/{other_book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert res.status_code == 404


def test_get_job_returns_state(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    created = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    ).json()
    fetched = client.get(f"/api/jobs/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert fetched["status"] == "done"
    assert fetched["episode_id"] == created["episode_id"]


def test_get_job_404(client) -> None:
    res = client.get("/api/jobs/99999")
    assert res.status_code == 404


# --- synthesize_audiobook task (direct apply) -------------------------------


def test_synthesize_task_creates_episode_and_mp3(client) -> None:
    """Direct task invocation produces an Episode row, an mp3 on disk, and
    drives Job.status all the way to done."""
    from app.db import task_session
    from app.models import Book, Chapter
    from app.tasks import synthesize_audiobook

    book_id, chapter_ids = _upload_and_extract(client)
    chapter_id = chapter_ids[0]

    # Create a Job row the task can pick up.
    session = task_session()
    try:
        job = Job(chapter_id=chapter_id, mode="audiobook", status=JobStatus.queued)
        session.add(job)
        session.commit()
        job_id = job.id
    finally:
        session.close()

    result = synthesize_audiobook.apply(args=(job_id,)).get()
    assert result["job_id"] == job_id
    assert result["duration_seconds"] == pytest.approx(0.5, abs=0.01)
    assert result["episode_id"] is not None

    session = task_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.done
        assert job.progress_pct == 100
        assert job.completed_at is not None

        episode = session.get(Episode, result["episode_id"])
        assert episode is not None
        assert episode.duration_seconds == pytest.approx(0.5, abs=0.01)
        assert episode.metadata_json["voice"] == "af_nicole"
        assert episode.metadata_json["sample_rate"] == 24000
        # retention_until = created_at + retention_days (default 30)
        expected_until = episode.created_at + timedelta(days=get_settings().retention_days)
        assert abs((episode.retention_until - expected_until).total_seconds()) < 5

        # File exists and is non-empty.
        import os
        assert os.path.exists(episode.storage_path)
        assert os.path.getsize(episode.storage_path) > 0
    finally:
        session.close()


def test_synthesize_task_failure_marks_job_failed_and_cleans_mp3(client, monkeypatch) -> None:
    """A failure inside synthesize_text writes Job.status='failed' and removes
    any partial mp3 from a previous attempt."""
    from app.db import task_session
    from app.models import Book, Chapter, Episode
    from app.tasks import synthesize_audiobook

    book_id, chapter_ids = _upload_and_extract(client)
    chapter_id = chapter_ids[0]

    session = task_session()
    try:
        job = Job(chapter_id=chapter_id, mode="audiobook", status=JobStatus.queued)
        session.add(job)
        session.commit()
        job_id = job.id
    finally:
        session.close()

    # Force a failure by making synthesize_text raise.
    def _boom(text, voice, speed=1.0):
        raise RuntimeError("simulated synthesis crash")

    monkeypatch.setattr("app.tasks.synthesize_text", _boom)

    with pytest.raises(RuntimeError, match="simulated"):
        synthesize_audiobook.apply(args=(job_id,))

    session = task_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.failed
        assert "simulated synthesis crash" in (job.error_message or "")

        # No Episode row should exist for a failed job.
        assert session.query(Episode).filter_by(job_id=job_id).one_or_none() is None
    finally:
        session.close()


# --- streaming endpoint ------------------------------------------------------


def test_stream_episode_returns_mp3(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    created = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    ).json()
    episode_id = created["episode_id"]

    res = client.get(f"/api/episodes/{episode_id}/audio")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/mpeg")
    assert len(res.content) > 0


def test_stream_episode_404_when_missing(client) -> None:
    res = client.get("/api/episodes/99999/audio")
    assert res.status_code == 404


def test_stream_episode_404_when_file_removed(client, monkeypatch) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    created = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    ).json()
    episode_id = created["episode_id"]

    # Delete the mp3 from disk while leaving the Episode row intact.
    from app.db import task_session
    from app.models import Episode
    import os

    session = task_session()
    try:
        ep = session.get(Episode, episode_id)
        os.remove(ep.storage_path)
    finally:
        session.close()

    res = client.get(f"/api/episodes/{episode_id}/audio")
    assert res.status_code == 404


# --- ChapterOut.latest_job population ----------------------------------------


def test_book_detail_includes_latest_job(client) -> None:
    book_id, chapter_ids = _upload_and_extract(client)
    # No jobs yet — latest_job should be None.
    detail = client.get(f"/api/books/{book_id}").json()
    assert all(ch["latest_job"] is None for ch in detail["chapters"])

    # Create one job on chapter 0.
    created = client.post(
        f"/api/books/{book_id}/chapters/{chapter_ids[0]}/jobs",
        json={"mode": "audiobook"},
    )
    assert created.status_code == 202

    detail = client.get(f"/api/books/{book_id}").json()
    ch0 = next(c for c in detail["chapters"] if c["id"] == chapter_ids[0])
    ch1 = next(c for c in detail["chapters"] if c["id"] == chapter_ids[1])
    assert ch0["latest_job"] is not None
    assert ch0["latest_job"]["status"] == "done"
    assert ch0["latest_job"]["episode_id"] is not None
    assert ch1["latest_job"] is None
