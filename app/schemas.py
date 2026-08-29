"""Pydantic request/response schemas for the API surface.

M1: HealthResponse.
M2: BookOut, ChapterOut, BookUploadResponse.
M3: JobOut, JobCreateRequest; ChapterOut.latest_job for the polling-driven
    three-state chapter row in book_detail.html.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import JobMode, JobStatus


class HealthResponse(BaseModel):
    """Response shape for GET /health."""

    status: str
    db: str
    redis: str


class ChapterOut(BaseModel):
    """Read shape for a chapter row.

    ``latest_job`` is the most recently created Job for this chapter,
    regardless of status. The frontend uses this to render a three-state
    control (Generate / Generating / Listen) without a second fetch.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    index: int
    title: str
    char_count: int
    detection_strategy: str | None
    latest_job: "JobOut | None" = None


class BookOut(BaseModel):
    """Read shape for a book row, including its chapter list."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    original_filename: str
    status: str
    uploaded_at: datetime
    chapters: list[ChapterOut]


class BookUploadResponse(BaseModel):
    """Returned from POST /api/books so the client can navigate to the book page."""

    id: int
    title: str
    status: str
    detail_url: str


class JobOut(BaseModel):
    """Read shape for a Job row.

    ``episode_id`` is populated when the job has produced an Episode row
    (i.e. status == done); ``None`` otherwise.
    ``script_id`` is populated for podcast-mode jobs once the script is generated.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    mode: JobMode
    status: JobStatus
    progress_pct: int
    current_stage_detail: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    episode_id: int | None = None
    script_id: int | None = None


class PodcastScriptTurn(BaseModel):
    """A single turn in a podcast script."""
    speaker: str
    text: str


class PodcastScriptOut(BaseModel):
    """Read shape for a generated podcast script."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    job_id: int
    turns: list[PodcastScriptTurn]
    created_at: datetime



class JobCreateRequest(BaseModel):
    """Body for POST /api/books/{book_id}/chapters/{chapter_id}/jobs.

    M3 only supports ``audiobook``; ``podcast`` is rejected until M4/M5 land.
    """

    mode: JobMode


# Pydantic 2 resolves forward refs at module import when the type is used.
# ``ChapterOut`` references ``JobOut`` and vice versa via ``latest_job``,
# so we re-build the model after both are defined.
ChapterOut.model_rebuild()
