"""The normalized layer: readable text that still knows where it came from.

Normalization is where a document becomes usable and where provenance is most
easily lost. Joining wrapped lines, repairing hyphenation and collapsing
whitespace all produce text that no longer appears anywhere in the original -
so every span records the raw line ids it was built from, and the pipeline
refuses to construct a document whose spans cite lines that do not exist.

Everything here is deterministic. The same raw pages always produce the same
spans, which is what lets a reviewer re-run an ingest and get an identical
trace rather than a plausible-looking different one.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from engine.ingest.layers import NormalizedSpan, RawDocument, RawLine, RawPage

# Whether a line, on its own, announces a section. Supplied by the caller
# rather than hardcoded here: which words count as headings is a question about
# how documents are interpreted, which belongs to the derived layer. Passing it
# in keeps normalization structural while still letting it cut a span in the
# right place - a heading set two points larger than its body sits too close to
# be separated by geometry alone.
HeadingTest = Callable[[str], bool]

_WHITESPACE = re.compile(r"\s+")

# A line ending in a hyphen preceded by a letter is a word broken across the
# line break, not a compound. "well-" at the end of a line rejoins; a hyphen
# inside a line is left alone, because we never saw it break.
_TRAILING_HYPHEN = re.compile(r"(?<=[A-Za-z])-$")

# Text sitting in these bands is page furniture - running headers, footers,
# page numbers, watermarks. It is part of the file but not part of what the
# candidate wrote, so it is kept and marked rather than silently deleted.
HEADER_BAND = 0.045
FOOTER_BAND = 0.925

# Two lines belong to the same span when the gap between them is small
# relative to their own height. Expressed as a ratio so it holds at any DPI.
PARAGRAPH_GAP_RATIO = 0.75

# A paragraph is set in one type size. Where consecutive lines differ in height
# by more than this, the second is a heading, a title or a footnote rather than
# a continuation - a name set at 20pt and the metadata line at 9.5pt beneath it
# sit close enough to pass the gap test, and merging them would attribute text
# to the candidate's name that they did not write there.
LINE_HEIGHT_CHANGE_RATIO = 1.4


def normalize_text(value: str) -> str:
    """NFKC plus whitespace collapse.

    NFKC folds the ligatures and full-width forms OCR emits, so "fi" typed as a
    ligature and as two letters become one token downstream. It changes how
    text is spelled, never which line it came from.
    """
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def is_page_furniture(line: RawLine, page: RawPage) -> bool:
    """Whether a line is running header, footer or watermark rather than content.

    Decided geometrically rather than by matching known strings: a rule that
    recognised this project's own watermark would silently fail on any real
    document, which is worse than a rule that is merely approximate.
    """
    top = line.bbox.y / page.height
    bottom = (line.bbox.y + line.bbox.height) / page.height
    return bottom <= HEADER_BAND or top >= FOOTER_BAND


def normalize_document(
    raw: RawDocument, *, is_heading: HeadingTest | None = None
) -> list[NormalizedSpan]:
    """Group raw lines into readable spans, each citing its sources."""
    spans: list[NormalizedSpan] = []

    for page in raw.pages:
        for group in _group_page(page, is_heading):
            span = _span_from(group, index=len(spans) + 1)
            if span is not None:
                spans.append(span)

    return spans


def _group_page(
    page: RawPage, is_heading: HeadingTest | None = None
) -> list[list[RawLine]]:
    """Split one page's lines into paragraph-sized groups, in reading order.

    Two kinds of line are always cut out on their own: page furniture, and
    anything the caller recognises as a heading. Both would otherwise be glued
    onto whichever paragraph happens to sit nearest, which for a heading means
    the section it announces silently disappears into its own body text.
    """
    ordered = sorted(page.lines, key=lambda line: (round(line.bbox.y, 1), line.bbox.x))

    groups: list[list[RawLine]] = []
    current: list[RawLine] = []

    for line in ordered:
        standalone = is_page_furniture(line, page) or (
            is_heading is not None and is_heading(normalize_text(line.text))
        )

        if standalone:
            if current:
                groups.append(current)
                current = []
            groups.append([line])
            continue

        if current and _starts_new_paragraph(current[-1], line):
            groups.append(current)
            current = []

        current.append(line)

    if current:
        groups.append(current)

    return groups


def _starts_new_paragraph(previous: RawLine, line: RawLine) -> bool:
    """Whether two consecutive lines belong to different paragraphs.

    Two independent signals, because either one alone is fooled by real
    documents: a wide vertical gap, or a marked change in type size. A title
    sitting tight above its subtitle passes the gap test but is plainly not the
    same paragraph.
    """
    gap = line.bbox.y - (previous.bbox.y + previous.bbox.height)
    reference = max(previous.bbox.height, line.bbox.height)
    if gap > reference * PARAGRAPH_GAP_RATIO:
        return True

    taller = max(previous.bbox.height, line.bbox.height)
    shorter = min(previous.bbox.height, line.bbox.height)
    if shorter <= 0:
        return False
    return taller / shorter > LINE_HEIGHT_CHANGE_RATIO


def _span_from(group: list[RawLine], *, index: int) -> NormalizedSpan | None:
    """Join one group of lines into a span, repairing wrapped words.

    Returns None when the group normalizes to nothing at all - an empty span
    would be a citation pointing at no text.
    """
    parts: list[str] = []
    joined_hyphenation = False

    for position, line in enumerate(group):
        text = normalize_text(line.text)
        if not text:
            continue

        is_last = position == len(group) - 1
        if not is_last and _TRAILING_HYPHEN.search(text):
            parts.append(_TRAILING_HYPHEN.sub("", text))
            joined_hyphenation = True
        else:
            parts.append(text if is_last else text + " ")

    text = "".join(parts).strip()
    if not text:
        return None

    return NormalizedSpan(
        id=f"s{index:03d}",
        text=text,
        raw_line_ids=[line.id for line in group],
        joined_hyphenation=joined_hyphenation,
        low_confidence=any(line.is_low_confidence for line in group),
    )
