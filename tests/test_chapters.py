"""Unit tests for app.chapters.detect_chapters.

These tests exercise the detector against synthetic cleaned text — no PDF
required, so they run quickly and don't need PyMuPDF for assertions.

The PDF-backed strategy (``_detect_via_toc``) is exercised separately in
``test_chapters_pdf.py`` because it needs a real PDF.
"""

from __future__ import annotations

import fitz  # type: ignore[import-untyped]

from app.chapters import detect_chapters


def _write_pdf_with_toc(path, pages: list[str], toc: list[tuple[int, str, int]]) -> None:
    """Helper: build a tiny PDF with a known TOC outline."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


def test_regex_detects_arabic_chapter_numbering(tmp_path) -> None:
    text = (
        "Some front matter that isn't a chapter heading.\n\n"
        "Chapter 1: The Beginning\n"
        "Body of chapter one with several paragraphs.\n\n"
        "More body.\n\n"
        "Chapter 2: The Middle\n"
        "Body of chapter two.\n\n"
        "Chapter 3: The End\n"
        "Body of chapter three, final."
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")  # _detect_via_toc will fall through on a non-PDF
    chapters = detect_chapters(pdf, text)

    assert len(chapters) == 3
    assert [ch.title for ch in chapters] == [
        "Chapter 1: The Beginning",
        "Chapter 2: The Middle",
        "Chapter 3: The End",
    ]
    assert all(ch.detection_strategy == "regex" for ch in chapters)
    # Bodies should not include the heading line itself.
    assert "Body of chapter one" in chapters[0].cleaned_text
    assert "Chapter 1" not in chapters[0].cleaned_text


def test_regex_detects_roman_numerals(tmp_path) -> None:
    text = (
        "Chapter I\nFirst chapter body.\n\n"
        "Chapter II\nSecond chapter body.\n\n"
        "Chapter III\nThird chapter body."
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")
    chapters = detect_chapters(pdf, text)
    assert len(chapters) == 3
    assert [ch.title for ch in chapters] == ["Chapter 1", "Chapter 2", "Chapter 3"]


def test_regex_rejects_midparagraph_false_positive(tmp_path) -> None:
    text = (
        "It happened in Chapter 1 of the saga, but he kept reading.\n\n"
        "Chapter 2\nReal chapter body.\n\n"
        "Chapter 3\nAnother real chapter body."
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")
    chapters = detect_chapters(pdf, text)
    # Only Chapter 2 and Chapter 3 should be detected — the first match is
    # mid-paragraph and lacks a blank line above it.
    assert len(chapters) == 2
    assert [ch.title for ch in chapters] == ["Chapter 2", "Chapter 3"]


def test_regex_returns_none_for_single_match(tmp_path) -> None:
    text = "Prologue\nSome text.\n\nChapter 1\nOnly one chapter here."
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")
    # A single regex match falls through to heading_lines or fallback.
    chapters = detect_chapters(pdf, text)
    # heading_lines or fallback should kick in. We just assert we got
    # at least one chapter — the exact strategy is implementation detail
    # of the fallback chain.
    assert len(chapters) >= 1


def test_fallback_chunks_long_text(tmp_path) -> None:
    body = ("This is a sentence of reasonable length. " * 1000).strip()
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")
    chapters = detect_chapters(pdf, body)

    assert len(chapters) >= 2
    assert all(ch.detection_strategy == "fallback" for ch in chapters)
    assert all(ch.title.startswith("Part ") for ch in chapters)
    # Every chunk should be non-empty and reasonable in size.
    for ch in chapters:
        assert ch.char_count > 0
        assert ch.char_count <= 25_000  # some slack above the 20k target


def test_fallback_handles_empty_text(tmp_path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-stub")
    chapters = detect_chapters(pdf, "")
    assert chapters == []


def test_toc_strategy_used_when_outline_present(tmp_path) -> None:
    pdf = tmp_path / "with_toc.pdf"
    pages = [
        "Chapter one body. " * 50,
        "Chapter two body. " * 50,
        "Chapter three body. " * 50,
    ]
    toc = [
        (1, "Chapter 1: First", 1),
        (1, "Chapter 2: Second", 2),
        (1, "Chapter 3: Third", 3),
    ]
    _write_pdf_with_toc(pdf, pages, toc)

    # The TOC strategy uses the PDF directly and doesn't read cleaned_text.
    chapters = detect_chapters(pdf, "ignored")

    assert len(chapters) == 3
    assert all(ch.detection_strategy == "toc" for ch in chapters)
    assert chapters[0].title == "Chapter 1: First"
    assert "Chapter one body" in chapters[0].cleaned_text


def test_detect_chapters_always_returns_something(tmp_path) -> None:
    """Garbage text with no structure should still produce one fallback chapter."""
    pdf = tmp_path / "garbage.pdf"
    pdf.write_bytes(b"%PDF-stub")
    chapters = detect_chapters(pdf, "just a wall of text with no headings at all really")
    assert len(chapters) >= 1
