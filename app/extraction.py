"""PDF text extraction for Podify.

M2 scope:
- Open a PDF from local storage with PyMuPDF (fitz).
- Pull per-page text into a single string, preserving paragraph breaks
  via PyMuPDF's default block-level layout output.
- Strip headers/footers/page numbers using a two-pass approach:
    1. Detect repeating top/bottom short lines across pages (heuristic).
    2. Apply regex cleanup for common patterns: "Page N", "N", "- N -",
       trailing/leading page numbers on otherwise blank-line-bounded text.

The cleaner is intentionally conservative: it errs on the side of keeping
text rather than deleting content, so a botched PDF doesn't end up with
missing paragraphs. Chapter detection (app/chapters.py) is responsible for
structural splits; this module only normalizes whitespace and removes the
most obvious boilerplate.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # type: ignore[import-untyped]  # PyMuPDF


def extract_text(pdf_path: Path) -> str:
    """Extract raw per-page text from a PDF.

    Returns text with one blank line between pages. No header/footer
    stripping at this stage — call :func:`clean_text` for that.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    page_texts: list[str] = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            # "text" preserves layout (spaces between words, line breaks
            # within blocks). We don't use "blocks"/"dict" here because we
            # want readable paragraph text, not bounding boxes.
            page_texts.append(page.get_text("text").strip())

    # Join pages with a blank line so cross-page paragraph flow stays
    # visually obvious without polluting the text with hard page breaks.
    return "\n\n".join(t for t in page_texts if t)


# Matches common page-number footer patterns: "12", "- 12 -", "Page 12",
# "Page 12 of 300". Anchored on a line of its own.
_PAGE_NUMBER_RE = re.compile(
    r"""^\s*(?:[-—]?\s*)            # optional dashes
        (?:\d{1,4}                   # bare number
         |page\s+\d{1,4}             # "page 12"
         |page\s+\d{1,4}\s+of\s+\d{1,4}  # "page 12 of 300"
        )
        \s*(?:[-—]?\s*)$""",
    re.IGNORECASE | re.VERBOSE,
)


def _find_repeating_boilerplate(page_texts: list[str]) -> set[str]:
    """Return short lines that appear on a majority of pages (likely headers/footers).

    A "short line" is one with fewer than 80 characters of non-whitespace
    text, so we don't accidentally delete legitimate body paragraphs that
    happen to repeat (rare, but possible in poetry collections).
    """
    line_counts: Counter[str] = Counter()
    per_page_line_sets: list[set[str]] = []

    for text in page_texts:
        lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
        per_page_line_sets.append(lines)
        for line in lines:
            if len(line) <= 80:
                line_counts[line] += 1

    if len(page_texts) < 3:
        # Too few pages to call anything "repeating" — bail.
        return set()

    threshold = max(2, len(page_texts) // 2)
    boilerplate = {
        line for line, count in line_counts.items() if count >= threshold
    }
    return boilerplate


def clean_text(raw_text: str) -> str:
    """Strip headers, footers, and page numbers; normalize whitespace.

    Takes the already page-joined output of :func:`extract_text`. We re-split
    on the page-separator blank line so we can run header/footer detection
    on a per-page basis.
    """
    # Reconstruct per-page chunks. ``extract_text`` joined pages with "\n\n",
    # so split back on two-or-more newlines that we treat as page breaks.
    # In practice every page chunk contains its own internal newlines, so
    # we split on a unique sentinel instead.
    sentinel = "\f\f\f"
    rejoined = raw_text.replace("\n\n", sentinel)
    pages = [p for p in rejoined.split(sentinel) if p.strip()]

    boilerplate = _find_repeating_boilerplate(pages)

    cleaned_pages: list[str] = []
    for page in pages:
        out_lines: list[str] = []
        for line in page.splitlines():
            stripped = line.strip()
            if not stripped:
                # Collapse runs of blank lines into a single blank line —
                # but emit the blank so paragraph breaks survive.
                if out_lines and out_lines[-1] != "":
                    out_lines.append("")
                continue
            if stripped in boilerplate:
                continue
            if _PAGE_NUMBER_RE.match(stripped):
                continue
            out_lines.append(stripped)
        # Strip trailing blank lines inside the page chunk.
        while out_lines and out_lines[-1] == "":
            out_lines.pop()
        if out_lines:
            cleaned_pages.append("\n".join(out_lines))

    # Join pages back with a single blank line, then collapse runs of
    # 3+ blank lines to exactly 2 (one visual paragraph gap).
    joined = "\n\n".join(cleaned_pages)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()
