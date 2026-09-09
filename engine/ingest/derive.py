"""The derived layer: interpretation, always cited and always attributed.

This is the only layer that guesses, so it is the layer that has to be most
explicit about guessing. Every item carries a `basis` naming the rule that
produced it, and a confidence for that rule. Nothing is emitted that cannot
name the spans it rests on.

The important negative case is `UNCLASSIFIED`. A block of text that matches no
section heading is reported as unclassified rather than filed under whichever
section happens to be open. Inventing structure a document does not have would
put words into a candidate's Experience section that they never wrote there,
and everything downstream depends on trusting which section a sentence came
from.
"""

from __future__ import annotations

import re

from engine.ingest.layers import (
    DerivedItem,
    DerivedKind,
    NormalizedSpan,
    RawDocument,
    RawPage,
)
from engine.ingest.normalize import is_page_furniture
from engine.models import SectionKind

# Headings this pipeline recognises, mapped to the sections the screening
# engine already understands. Matching is on the normalized, lowercased text
# with trailing punctuation removed.
HEADING_VOCABULARY: dict[str, SectionKind] = {
    "skills": SectionKind.SKILLS,
    "technical skills": SectionKind.SKILLS,
    "core skills": SectionKind.SKILLS,
    "key skills": SectionKind.SKILLS,
    "experience": SectionKind.EXPERIENCE,
    "work experience": SectionKind.EXPERIENCE,
    "professional experience": SectionKind.EXPERIENCE,
    "employment": SectionKind.EXPERIENCE,
    "employment history": SectionKind.EXPERIENCE,
    "projects": SectionKind.PROJECTS,
    "personal projects": SectionKind.PROJECTS,
    "academic projects": SectionKind.PROJECTS,
    "selected projects": SectionKind.PROJECTS,
    "education": SectionKind.EDUCATION,
    "academic background": SectionKind.EDUCATION,
    "qualifications": SectionKind.EDUCATION,
    "cover note": SectionKind.COVER_NOTE,
    "cover letter": SectionKind.COVER_NOTE,
    "summary": SectionKind.COVER_NOTE,
    "personal statement": SectionKind.COVER_NOTE,
    "about me": SectionKind.COVER_NOTE,
}

# A heading is short. Anything longer is prose that happens to begin with a
# heading word, and treating it as a heading would swallow real content.
HEADING_MAX_WORDS = 4

# A name is short too, and sits above everything else on the first page.
NAME_MAX_WORDS = 6

_TRAILING_PUNCTUATION = re.compile(r"[\s:;.-]+$")

_URL = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_GITHUB = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"
    r"(?:/(?P<repo>[A-Za-z0-9._-]{1,100}))?",
    re.IGNORECASE,
)


class _Counter:
    """Stable, readable ids for derived items within one document."""

    def __init__(self) -> None:
        self._value = 0

    def next(self) -> str:
        self._value += 1
        return f"d{self._value:03d}"


def heading_kind(text: str) -> SectionKind | None:
    """The section a span announces, if it is a heading at all."""
    candidate = _TRAILING_PUNCTUATION.sub("", text).strip().lower()
    if len(candidate.split()) > HEADING_MAX_WORDS:
        return None
    return HEADING_VOCABULARY.get(candidate)


def is_heading(text: str) -> bool:
    """Heading test in the shape `normalize_document` expects.

    Passed into normalization so a heading is cut into its own span. Typeset
    resumes routinely set a heading only a point or two larger than the body
    beneath it, which no purely geometric rule can separate reliably.
    """
    return heading_kind(text) is not None


def derive_items(raw: RawDocument, spans: list[NormalizedSpan]) -> list[DerivedItem]:
    """Interpret normalized spans into sections, a name, and links."""
    pages = {page.page_number: page for page in raw.pages}
    furniture = {span.id for span in spans if _is_furniture(span, raw, pages)}

    items: list[DerivedItem] = []
    counter = _Counter()

    name_span = _name_span(spans, raw, furniture)
    if name_span is not None:
        items.append(
            DerivedItem(
                id=counter.next(),
                kind=DerivedKind.CANDIDATE_NAME,
                label="candidate_name",
                text=name_span.text,
                span_ids=[name_span.id],
                basis=(
                    "first content span on page 1, above any recognised "
                    "section heading"
                ),
                confidence=0.9,
            )
        )

    items.extend(_section_items(spans, furniture, name_span, counter))
    items.extend(_link_items(spans, furniture, counter))
    items.extend(_unclassified_items(spans, furniture, name_span, counter))

    return items


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _section_items(
    spans: list[NormalizedSpan],
    furniture: set[str],
    name_span: NormalizedSpan | None,
    counter: _Counter,
) -> list[DerivedItem]:
    """One item per section, built from the spans that follow its heading."""
    collected: dict[SectionKind, list[NormalizedSpan]] = {}
    headings: dict[SectionKind, str] = {}
    current: SectionKind | None = None

    for span in spans:
        if span.id in furniture:
            continue

        announced = heading_kind(span.text)
        if announced is not None:
            current = announced
            headings.setdefault(announced, span.text)
            collected.setdefault(announced, [])
            continue

        if current is None:
            continue
        if name_span is not None and span.id == name_span.id:
            continue

        collected[current].append(span)

    return [
        DerivedItem(
            id=counter.next(),
            kind=DerivedKind.SECTION,
            label=kind.value,
            text="\n".join(span.text for span in members),
            span_ids=[span.id for span in members],
            basis=(
                f"follows the heading {headings[kind]!r} and precedes the next "
                "recognised heading"
            ),
            confidence=0.95,
        )
        for kind, members in collected.items()
        if members
    ]


# --------------------------------------------------------------------------
# Links - the handoff into Stage B
# --------------------------------------------------------------------------


def _link_items(
    spans: list[NormalizedSpan], furniture: set[str], counter: _Counter
) -> list[DerivedItem]:
    """Every URL the document offers, as candidates for external checking.

    Extraction only. Whether a repository exists, is private, or cannot be
    reached is Stage B's question, and nothing here presumes an answer.
    """
    items: list[DerivedItem] = []
    seen: set[str] = set()

    for span in spans:
        if span.id in furniture:
            continue

        for match in _GITHUB.finditer(span.text):
            owner = match.group("owner")
            repo = match.group("repo")
            target = f"{owner}/{repo}" if repo else owner
            if target in seen:
                continue
            seen.add(target)

            items.append(
                DerivedItem(
                    id=counter.next(),
                    kind=DerivedKind.LINK,
                    label="github_repository" if repo else "github_profile",
                    text=target,
                    span_ids=[span.id],
                    basis=f"matched a github.com URL in {span.id}",
                    confidence=0.98,
                )
            )

        for match in _URL.finditer(span.text):
            url = match.group(0).rstrip(".,;")
            if "github.com" in url.lower() or url in seen:
                continue
            seen.add(url)

            items.append(
                DerivedItem(
                    id=counter.next(),
                    kind=DerivedKind.LINK,
                    label="url",
                    text=url,
                    span_ids=[span.id],
                    basis=f"matched an http(s) URL in {span.id}",
                    confidence=0.98,
                )
            )

    return items


# --------------------------------------------------------------------------
# Everything the rules could not place
# --------------------------------------------------------------------------


def _unclassified_items(
    spans: list[NormalizedSpan],
    furniture: set[str],
    name_span: NormalizedSpan | None,
    counter: _Counter,
) -> list[DerivedItem]:
    """Report unplaced text as unplaced, rather than filing it somewhere.

    Two reasons a span lands here: it is page furniture, or it appeared before
    any heading the pipeline recognises. Both are stated explicitly so a
    reviewer can see what the document contained that the system did not use.
    """
    items: list[DerivedItem] = []
    seen_heading = False

    for span in spans:
        if span.id in furniture:
            items.append(
                DerivedItem(
                    id=counter.next(),
                    kind=DerivedKind.UNCLASSIFIED,
                    label="page_furniture",
                    text=span.text,
                    span_ids=[span.id],
                    basis=(
                        "sits in the page header or footer band, so it is "
                        "running page furniture rather than authored content"
                    ),
                    confidence=0.85,
                )
            )
            continue

        if heading_kind(span.text) is not None:
            seen_heading = True
            continue

        if seen_heading:
            continue
        if name_span is not None and span.id == name_span.id:
            continue

        items.append(
            DerivedItem(
                id=counter.next(),
                kind=DerivedKind.UNCLASSIFIED,
                label="preamble",
                text=span.text,
                span_ids=[span.id],
                basis="appears before any recognised section heading",
                confidence=0.8,
            )
        )

    return items


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _is_furniture(
    span: NormalizedSpan, raw: RawDocument, pages: dict[int, RawPage]
) -> bool:
    """Whether every raw line behind a span is header/footer furniture."""
    wanted = set(span.raw_line_ids)
    lines = [line for line in raw.lines() if line.id in wanted]
    if not lines:
        return False
    return all(
        is_page_furniture(line, pages[line.page_number])
        for line in lines
        if line.page_number in pages
    )


def _name_span(
    spans: list[NormalizedSpan], raw: RawDocument, furniture: set[str]
) -> NormalizedSpan | None:
    """The span holding the candidate's name, if the document offers one.

    Returns None rather than falling back to a filename or a best guess. A
    wrong name attached to a real assessment is worse than an absent one, so
    the pipeline reports the absence instead of covering it.
    """
    first_page_lines = {line.id for line in raw.lines() if line.page_number == 1}

    for span in spans:
        if span.id in furniture:
            continue
        if not set(span.raw_line_ids) & first_page_lines:
            continue
        if heading_kind(span.text) is not None:
            return None
        if len(span.text.split()) > NAME_MAX_WORDS:
            return None
        if _URL.search(span.text) or "@" in span.text:
            return None
        return span

    return None
