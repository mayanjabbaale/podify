"""Episode streaming endpoint (M3).

GET /api/episodes/{episode_id}/audio
    Returns the local mp3 (or wav) file via FastAPI's ``FileResponse``,
    which honors HTTP Range requests so browsers can seek.

404 if the Episode row is missing, or if the file is missing on disk
(typically because the cleanup task deleted it; landing in M5/M6).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Episode, EpisodeFormat

router = APIRouter()

_MEDIA_TYPES: dict[EpisodeFormat, str] = {
    EpisodeFormat.mp3: "audio/mpeg",
    EpisodeFormat.wav: "audio/wav",
}


@router.get("/api/episodes/{episode_id}/audio")
def stream_episode(episode_id: int, db: Session = Depends(get_db)) -> FileResponse:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")

    path = Path(episode.storage_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Episode file is no longer available on disk",
        )

    media_type = _MEDIA_TYPES.get(episode.format, "application/octet-stream")
    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
    )
