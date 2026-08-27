"""Pydantic request/response schemas for the API surface.

Minimal for M1 (skeleton). M2+ will add BookCreate, ChapterOut, JobCreate,
JobOut, EpisodeOut, etc.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response shape for GET /health."""

    status: str
    db: str
    redis: str
