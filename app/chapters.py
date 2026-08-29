"""Chapter detection for Podify.

PDFs vary wildly in structure — books from Project Gutenberg look nothing
like a scanned monograph — so the detector runs a series of strategies and
returns the first one that produces a sensible chapter list. A fixed-length
chunk fallback guarantees we always return at least one chapter.

Strategies (in order):
1. **toc**: explicit "Contents"-style outline. PyMuPDF's ``get_toc()`` returns
   a hierarchical outline with page numbers; we use top-level entries.
2. **regex**: detect "Chapter N", "CHAPTER N", "Chapter N: Title", etc.
3. **heading_lines**: lines that look like titles — short, mostly capital,
   surrounded by blank lines.
4. **fallback**: fixed-length ~20k-character chunks, titled "Part N".

Each returned :class:`DetectedChapter` records the strategy that produced
it, so the UI / logs can flag when a book was chunked by fallback only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # type: ignore[import-untyped]


# --- Strategy 1: explicit TOC -------------------------------------------------


@dataclass
class DetectedChapter:
    index: int
    title: str
    raw_text: str
    cleaned_text: str
    char_count: int
    detection_strategy: str


def _detect_via_toc(pdf_path) -> list[DetectedChapter] | None:
    """Use PyMuPDF's outline as a chapter map.

    Returns ``None`` if there's no outline, if it has fewer than two
    top-level entries (a single TOC entry isn't a chapter list, it's a
    section heading), or if the file isn't a readable PDF (we fall through
    to the next strategy in that case rather than crashing the caller).
    """
    try:
        with fitz.open(pdf_path) as doc:
            toc = doc.get_toc(simple=True)  # [(level, title, page), ...]
            top_level = [entry for entry in toc if entry[0] == 1]
            if len(top_level) < 2:
                return None

            # Build (start_page, title) pairs. The last chapter runs to end-of-doc.
            starts: list[tuple[int, str]] = [
                (max(1, entry[2]), entry[1]) for entry in top_level
            ]

            chapters: list[DetectedChapter] = []
            for i, (start_page, title) in enumerate(starts):
                end_page = (
                    starts[i + 1][0] if i + 1 < len(starts) else doc.page_count + 1
                )
                text = _extract_page_range(doc, start_page, end_page)
                cleaned = _normalize_whitespace(text)
                if not cleaned:
                    continue
                chapters.append(
                    DetectedChapter(
                        index=len(chapters),
                        title=title.strip() or f"Chapter {len(chapters) + 1}",
                        raw_text=text,
                        cleaned_text=cleaned,
                        char_count=len(cleaned),
                        detection_strategy="toc",
                    )
                )
    except Exception:
        # Unreadable PDF, encrypted PDF, or PyMuPDF internals failing —
        # fall through to the text-based strategies.
        return None

    return chapters or None


def _extract_page_range(doc: fitz.Document, start: int, end: int) -> str:
    """Extract text from a half-open [start, end) page range (1-indexed)."""
    parts: list[str] = []
    for page_num in range(start - 1, min(end - 1, doc.page_count)):
        parts.append(doc.load_page(page_num).get_text("text"))
    return "\n\n".join(p.strip() for p in parts if p.strip())


# --- Strategy 2: regex heading detection -------------------------------------


# Matches "Chapter 1", "CHAPTER 12", "Chapter Three", "Chapter XII",
# "Chapter 1: The Beginning", "Chapter 1 - The Beginning".
# Allows an optional Roman numeral or word-number for older books.
_CHAPTER_HEADING_RE = re.compile(
    r"""^\s*
        (?:chapter|ch\.?|chap\.?)\s+
        (                          # the "N" group:
            \d+                     #   1, 12
            |[ivxlcdm]+             #   I, IV, XII (Roman)
            |one|two|three|four|five|six|seven|eight|nine|ten
            |eleven|twelve|thirteen|fourteen|fifteen|sixteen
            |seventeen|eighteen|nineteen|twenty
        )
        ([\s:.\-—][^\n]{0,120})?    # optional ": subtitle" or "- subtitle"
        \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Numeric-to-int for word-form numerals, so chapter ordering stays sane.
_WORD_NUMS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def _parse_chapter_heading(line: str) -> tuple[int, str] | None:
    """Parse a line as 'Chapter N [subtitle]'; return (n, full_title) or None."""
    m = _CHAPTER_HEADING_RE.match(line)
    if not m:
        return None
    token = m.group(1).lower()
    if token.isdigit():
        n = int(token)
    elif token in _WORD_NUMS:
        n = _WORD_NUMS[token]
    else:
        # Roman numeral.
        n = _roman_to_int(token)
        if n is None:
            return None
    subtitle = (m.group(2) or "").strip(" :.\t-—")
    title = f"Chapter {n}"
    if subtitle:
        title = f"{title}: {subtitle[:120]}"
    return n, title


def _roman_to_int(s: str) -> int | None:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total, prev = 0, 0
    for ch in reversed(s):
        v = values.get(ch, 0)
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total if total > 0 and s else None


def _detect_via_regex(cleaned_text: str) -> list[DetectedChapter] | None:
    """Split on lines that match the chapter-heading regex."""
    lines = cleaned_text.splitlines()
    matches: list[tuple[int, str]] = []  # (line_index, title)

    for idx, line in enumerate(lines):
        parsed = _parse_chapter_heading(line)
        if parsed is None:
            continue
        # Reject mid-paragraph false positives: the matched line should be
        # visually a heading (short, surrounded by blank lines). The "short"
        # check guards against a sentence like "Chapter 1 was the worst"
        # mid-paragraph being mis-detected.
        if len(line) > 140:
            continue
        # Require a blank line immediately before (or be the very first line).
        if idx > 0 and lines[idx - 1].strip():
            continue
        matches.append((idx, parsed[1]))

    if len(matches) < 2:
        return None

    chapters: list[DetectedChapter] = []
    for i, (line_idx, title) in enumerate(matches):
        next_idx = matches[i + 1][0] if i + 1 < len(matches) else len(lines)
        body_lines = lines[line_idx + 1 : next_idx]
        body = "\n".join(body_lines).strip()
        if not body:
            # No body text after this heading — skip rather than emit an empty chapter.
            continue
        chapters.append(
            DetectedChapter(
                index=len(chapters),
                title=title,
                raw_text="\n".join(lines[line_idx:next_idx]),
                cleaned_text=body,
                char_count=len(body),
                detection_strategy="regex",
            )
        )

    return chapters or None


# --- Strategy 3: heading-line heuristic ---------------------------------------


# A "heading line" is short, mostly alpha, not sentence-punctuated,
# and surrounded by blank lines. We additionally require ALLCAPS or
# Title Case to weed out mid-paragraph sentence fragments.
def _looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not (4 <= len(s) <= 80):
        return False
    if s.endswith((".", "?", "!", ",", ";", ":")):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters or len(letters) < len(s) * 0.6:
        return False
    upper = sum(1 for c in letters if c.isupper())
    title_case = s.istitle()
    return upper >= len(letters) * 0.7 or title_case


def _detect_via_heading_lines(cleaned_text: str) -> list[DetectedChapter] | None:
    """Split on visually-prominent heading lines."""
    lines = cleaned_text.splitlines()
    headings: list[tuple[int, str]] = []

    for idx, line in enumerate(lines):
        if not _looks_like_heading(line):
            continue
        if idx > 0 and lines[idx - 1].strip():
            continue
        if idx + 1 < len(lines) and lines[idx + 1].strip():
            continue
        headings.append((idx, line.strip()))

    if len(headings) < 2:
        return None

    chapters: list[DetectedChapter] = []
    for i, (line_idx, title) in enumerate(headings):
        next_idx = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        body_lines = lines[line_idx + 1 : next_idx]
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        chapters.append(
            DetectedChapter(
                index=len(chapters),
                title=title,
                raw_text="\n".join(lines[line_idx:next_idx]),
                cleaned_text=body,
                char_count=len(body),
                detection_strategy="heading_lines",
            )
        )
    return chapters or None


# --- Strategy 4: fixed-length fallback ----------------------------------------


_FALLBACK_CHUNK_CHARS = 20_000


def _detect_via_fallback(cleaned_text: str) -> list[DetectedChapter]:
    """Greedy fixed-length chunks. Always returns at least one chapter."""
    text = cleaned_text.strip()
    if not text:
        return []

    chapters: list[DetectedChapter] = []
    pos = 0
    while pos < len(text):
        end = min(pos + _FALLBACK_CHUNK_CHARS, len(text))
        # Prefer to break on a paragraph boundary (double newline) within
        # the last 10% of the chunk — keeps chunks readable.
        if end < len(text):
            window_start = end - _FALLBACK_CHUNK_CHARS // 10
            boundary = text.rfind("\n\n", window_start, end)
            if boundary > pos + _FALLBACK_CHUNK_CHARS // 2:
                end = boundary
        chunk = text[pos:end].strip()
        if chunk:
            chapters.append(
                DetectedChapter(
                    index=len(chapters),
                    title=f"Part {len(chapters) + 1}",
                    raw_text=chunk,
                    cleaned_text=chunk,
                    char_count=len(chunk),
                    detection_strategy="fallback",
                )
            )
        pos = end
    return chapters


# --- Public entry point -------------------------------------------------------


def _normalize_whitespace(text: str) -> str:
    """Collapse 3+ blank lines into one blank line; strip ends."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def detect_chapters(pdf_path, cleaned_text: str) -> list[DetectedChapter]:
    """Run strategies in order and return the first non-empty result.

    The fallback strategy is the only one that is guaranteed to return
    something, so this function always returns a list with at least one
    chapter when ``cleaned_text`` is non-empty.
    """
    toc_chapters = _detect_via_toc(pdf_path)
    if toc_chapters:
        return toc_chapters

    regex_chapters = _detect_via_regex(cleaned_text)
    if regex_chapters:
        return regex_chapters

    heading_chapters = _detect_via_heading_lines(cleaned_text)
    if heading_chapters:
        return heading_chapters

    return _detect_via_fallback(cleaned_text)
