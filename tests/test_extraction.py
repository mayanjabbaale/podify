"""Tests for app.extraction — header/footer/page-number stripping."""

from __future__ import annotations

from app.extraction import clean_text


def test_strips_bare_page_numbers() -> None:
    raw = "Chapter body.\n\n12\n\nMore body text."
    assert "12" not in clean_text(raw)


def test_strips_dash_wrapped_page_numbers() -> None:
    raw = "Chapter body.\n\n- 42 -\n\nMore body."
    out = clean_text(raw)
    assert "42" not in out


def test_strips_page_n_of_m_format() -> None:
    raw = "Body of text.\n\nPage 3 of 200\n\nMore body."
    assert "Page 3 of 200" not in clean_text(raw)


def test_keeps_inline_numbers() -> None:
    # The number "12" should stay when it's not on a line by itself.
    raw = "There were 12 knights in the round table and they all agreed.\n\nBody continues."
    out = clean_text(raw)
    assert "12" in out


def test_collapses_repeating_header() -> None:
    raw = ""
    for i in range(5):
        raw += "Project Gutenberg footer line\n\n"
        raw += f"Body text on page {i + 1}.\n\n"
    out = clean_text(raw)
    assert "Project Gutenberg" not in out
    assert "Body text on page 1." in out
    assert "Body text on page 5." in out


def test_collapses_excess_blank_lines() -> None:
    raw = "First paragraph.\n\n\n\n\nSecond paragraph."
    out = clean_text(raw)
    # Three or more newlines should collapse to exactly two (one blank line).
    assert "\n\n\n" not in out
    assert "First paragraph." in out
    assert "Second paragraph." in out


def test_strips_trailing_blanks_per_page() -> None:
    raw = "Page one body.\n\n\n\nPage two body.\n\n\n\n"
    out = clean_text(raw)
    assert "Page one body." in out
    assert "Page two body." in out
    # No trailing whitespace.
    assert out == out.rstrip()
