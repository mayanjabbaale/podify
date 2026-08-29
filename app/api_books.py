"""Book upload + detail endpoints.

M2 surface:
- POST /api/books         multipart PDF upload -> 202 + BookUploadResponse,
                            kicks off the Celery extract_pdf task
- GET  /api/books/{id}    JSON book detail with chapter list
- GET  /books/{id}        Server-rendered chapter list page
- GET  /api/books/{id}/chapters

M3 additions:
- Each ``ChapterOut`` now carries ``latest_job`` (the chapter's most
  recently created Job, regardless of status) so the frontend can render
  the Generate / Generating / Listen control from a single poll response.

PDFs are saved to ``storage/pdfs/{book_id}.pdf``. Reusing the book id as
the filename avoids name collisions and keeps disk cleanup trivial
(deleting the book row + the file is enough).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Book, Chapter, Job
from app.schemas import BookOut, BookUploadResponse, ChapterOut, JobOut
from app.tasks import extract_pdf

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB ceiling — adjust if real books exceed this
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]+")


def _chapter_out(chapter: Chapter) -> ChapterOut:
    """Build a ChapterOut for ``chapter`` with its most-recent Job attached.

    "Most-recent" means highest ``created_at`` regardless of status. A
    failed job stays attached so the UI can offer a Retry control; a
    successful job exposes its ``episode_id`` via ``latest_job.episode_id``.
    """
    latest_job: Job | None = None
    if chapter.jobs:
        # Sort by created_at descending and take the first.
        latest_job = sorted(chapter.jobs, key=lambda j: j.created_at, reverse=True)[0]

    job_out: JobOut | None = None
    if latest_job is not None:
        job_out = JobOut(
            id=latest_job.id,
            chapter_id=latest_job.chapter_id,
            mode=latest_job.mode,
            status=latest_job.status,
            progress_pct=latest_job.progress_pct,
            current_stage_detail=latest_job.current_stage_detail,
            error_message=latest_job.error_message,
            created_at=latest_job.created_at,
            completed_at=latest_job.completed_at,
            episode_id=latest_job.episode.id if latest_job.episode is not None else None,
            script_id=latest_job.script.id if latest_job.script is not None else None,
        )

    return ChapterOut(
        id=chapter.id,
        book_id=chapter.book_id,
        index=chapter.index,
        title=chapter.title,
        char_count=chapter.char_count,
        detection_strategy=chapter.detection_strategy,
        latest_job=job_out,
    )


def _safe_display_title(original_filename: str) -> str:
    """Derive a book title from the upload filename.

    Strips the extension and replaces unsafe characters; falls back to a
    sensible default if nothing usable remains.
    """
    stem = Path(original_filename).stem
    cleaned = _SAFE_FILENAME_RE.sub(" ", stem).strip()
    return cleaned or "Untitled"


@router.post(
    "/api/books",
    response_model=BookUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_book(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> BookUploadResponse:
    """Accept a PDF, persist it, and enqueue the extraction task."""
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected application/pdf, got {file.content_type}",
        )

    pdfs_dir: Path = settings.storage_dir / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    # Persist the row first so the book has an id we can use as the filename.
    book = Book(
        title=_safe_display_title(file.filename or "upload.pdf"),
        original_filename=file.filename or "upload.pdf",
        storage_path="",  # placeholder; updated below
        status="uploaded",
    )
    db.add(book)
    db.flush()  # populate book.id without committing yet

    dest = pdfs_dir / f"{book.id}.pdf"
    bytes_written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > _MAX_UPLOAD_BYTES:
                    # Bail — the open file handle and partial row will be
                    # cleaned up by the outer except block.
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"PDF exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                    )
                out.write(chunk)
    except HTTPException:
        db.rollback()
        # Best-effort cleanup of any partial file.
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                logger.warning("Failed to remove partial upload %s", dest)
        raise
    except Exception:
        db.rollback()
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                logger.warning("Failed to remove partial upload %s", dest)
        logger.exception("Failed to write uploaded PDF for book %s", book.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist uploaded PDF",
        )

    if bytes_written == 0:
        db.rollback()
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    book.storage_path = str(dest)
    db.commit()
    db.refresh(book)

    # Enqueue extraction. ``.delay()`` returns an AsyncResult; we don't
    # expose its id — the UI polls the book endpoint instead.
    try:
        extract_pdf.delay(book.id)
    except Exception:
        # Broker down — mark the book failed so the UI can surface that
        # instead of leaving it stuck in "uploaded".
        book.status = "failed"
        db.commit()
        logger.exception("Failed to enqueue extract_pdf for book %s", book.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Extraction queue unavailable; please retry shortly",
        )

    return BookUploadResponse(
        id=book.id,
        title=book.title,
        status=book.status,
        detail_url=str(request.url_for("book_page", book_id=book.id)),
    )


@router.get("/api/books/{book_id}", response_model=BookOut)
def get_book(book_id: int, db: Session = Depends(get_db)) -> BookOut:
    """JSON book detail including chapter list with each chapter's latest job."""
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    chapters = [_chapter_out(ch) for ch in book.chapters]
    return BookOut(
        id=book.id,
        title=book.title,
        original_filename=book.original_filename,
        status=book.status,
        uploaded_at=book.uploaded_at,
        chapters=chapters,
    )


@router.get("/books/{book_id}", response_class=HTMLResponse, name="book_page")
def book_page(
    book_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Server-rendered chapter list page.

    Polled by the upload page after the upload completes; also directly
    bookmarkable. The page polls the JSON endpoint above every couple of
    seconds while the book is still being extracted so the chapter list
    appears without a manual refresh.
    """
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")

    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "book_detail.html",
        {
            "book": book,
            "chapters": book.chapters,
        },
    )


# A JSON-accepting variant of the book detail endpoint that returns the
# raw row rather than the read schema. Useful for the frontend's polling
# loop and for debugging. Kept here so the chapter list stays close to
# the data it reads.
@router.get("/api/books/{book_id}/chapters", response_model=list[ChapterOut])
def list_chapters(book_id: int, db: Session = Depends(get_db)) -> list[ChapterOut]:
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return [_chapter_out(ch) for ch in book.chapters]
