"""SQLAlchemy 2.x ORM models for Podify.

Schema mirrors idea.md §4 plus three columns added for operations/debugging:
- Chapter.detection_strategy: which chapter-detection strategy succeeded
- Job.current_stage_detail: free-text sub-status (e.g. "synthesizing turn 7/12")
- Episode.retention_until: timestamp at which the cleanup task should delete it
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    """Lifecycle states of a generation job."""

    queued = "queued"
    extracting = "extracting"
    scripting = "scripting"
    synthesizing = "synthesizing"
    assembling = "assembling"
    done = "done"
    failed = "failed"


class JobMode(str, enum.Enum):
    audiobook = "audiobook"
    podcast = "podcast"


class EpisodeFormat(str, enum.Enum):
    mp3 = "mp3"
    wav = "wav"


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(64), default="uploaded")

    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.index",
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    raw_text: Mapped[str] = mapped_column(Text)
    cleaned_text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    # Strategy that successfully detected this chapter's boundaries.
    # Populated by M2's multi-strategy detector. Nullable until then.
    detection_strategy: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    book: Mapped["Book"] = relationship(back_populates="chapters")
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    mode: Mapped[JobMode] = mapped_column(Enum(JobMode))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.queued
    )
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    # Free-text sub-status shown to the user (e.g. "synthesizing turn 7/12").
    current_stage_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    chapter: Mapped["Chapter"] = relationship(back_populates="jobs")
    episode: Mapped[Optional["Episode"]] = relationship(
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )
    script: Mapped[Optional["PodcastScript"]] = relationship(
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    storage_path: Mapped[str] = mapped_column(String(1024))
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    format: Mapped[EpisodeFormat] = mapped_column(
        Enum(EpisodeFormat), default=EpisodeFormat.mp3
    )
    # Free-form metadata for debugging/UI: skipped segments, voice IDs used, etc.
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Set at creation to created_at + retention_days. The cleanup task deletes
    # any episode whose retention_until has passed.
    retention_until: Mapped[datetime] = mapped_column(DateTime)

    job: Mapped["Job"] = relationship(back_populates="episode")


class PodcastScript(Base):
    """Only populated for podcast-mode jobs. Useful for debugging and
    regenerating TTS without re-prompting the LLM."""

    __tablename__ = "podcast_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True
    )
    # JSON shape: [{"speaker": "host_a"|"host_b", "voice": "af_bella"|...,
    #               "text": "..."}, ...]
    turns: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="script")
