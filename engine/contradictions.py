"""Contradiction detection within a single application.

Surprise Challenge 01. A screening agent that trusts the strongest claim in a
document is trivially gamed: write "5 years of Python" at the top and the rest
of the resume is never consulted. This module consults the rest of the resume.

Four conflicts are detected, all *within one document*:

  duration_unsupported   claimed years exceed the experience actually described
  timeline_implausible   claimed professional years do not fit the stated dates
  expertise_unsupported  claimed mastery the evidence does not carry
  cover_note_only        asserted about oneself and nowhere demonstrated

The binding constraint: **never invent missing evidence**. Every flag quotes
the claim, and quotes whatever conflicting text was actually found. Where the
conflict is an absence, it is reported as an absence and the sections that were
searched are named - not dressed up as a discovery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.claims import extract_claims
from engine.evidence import SECTION_WEIGHT, grade_claims
from engine.models import (
    Application,
    Contradiction,
    ContradictionKind,
    EvidenceItem,
    SectionKind,
)

# A claim may exceed demonstrable experience by this much before it is flagged.
# Resumes round; a year of slack keeps honest rounding from reading as a lie.
DURATION_TOLERANCE_YEARS = 1.0

MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "5 years", "3+ years", "18 months"
_DURATION_CLAIM = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(years?|months?)", re.IGNORECASE
)

# "2021 - 2025", "Jan 2024 - Dec 2024", "2024 to present"
_DATE_RANGE = re.compile(
    r"(?:([A-Za-z]{3,9})\s+)?(\d{4})\s*(?:-|–|—|to)\s*"
    r"(?:(?:([A-Za-z]{3,9})\s+)?(\d{4})|(present|current|now))",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Treated as "today" for open-ended ranges. Kept explicit rather than reading
# the clock so a test run in any year produces the same verdict.
REFERENCE_YEAR = 2026
REFERENCE_MONTH = 9


@dataclass(frozen=True)
class _DurationClaim:
    """A stated span of experience, with the sentence it came from."""

    years: float
    section: SectionKind
    text: str


@dataclass(frozen=True)
class _DatedSpan:
    """One date range found in the application, with its duration."""

    text: str
    years: float


def find_contradictions(application: Application) -> list[Contradiction]:
    """Return every internal conflict found in one application."""
    return [
        *_duration_conflicts(application),
        *_evidence_conflicts(application),
    ]


# --------------------------------------------------------------------------
# Duration and timeline
# --------------------------------------------------------------------------


def _duration_conflicts(application: Application) -> list[Contradiction]:
    """Compare stated years of experience against the dates actually listed."""
    claims = _duration_claims(application)
    if not claims:
        return []

    experience = _dated_spans(application, SectionKind.EXPERIENCE)
    evidenced_years = _total_years(experience)

    conflicts: list[Contradiction] = []
    for claim in claims:
        if claim.years - evidenced_years <= DURATION_TOLERANCE_YEARS:
            continue

        counter = [
            EvidenceItem(
                section=SectionKind.EXPERIENCE,
                source_text=span.text,
                weight=SECTION_WEIGHT[SectionKind.EXPERIENCE],
                note=f"Dated experience: about {span.years:.1f} year(s)",
            )
            for span in experience
        ]
        counter.extend(_education_context(application))

        conflicts.append(
            Contradiction(
                kind=(
                    ContradictionKind.DURATION_UNSUPPORTED
                    if experience
                    else ContradictionKind.TIMELINE_IMPLAUSIBLE
                ),
                subject=f"{claim.years:g} years of experience",
                claim_text=claim.text,
                claim_section=claim.section,
                counter_evidence=counter,
                evidence_note=_duration_note(claim.years, evidenced_years, experience),
                assessment="Claim insufficiently supported.",
            )
        )
    return conflicts


def _duration_note(
    claimed: float, evidenced: float, spans: list[_DatedSpan]
) -> str:
    """State what the dates actually show, without overstating the finding."""
    if not spans:
        return (
            f"No dated professional experience is listed anywhere in the "
            f"application, so nothing supports {claimed:g} years."
        )
    return (
        f"The dated experience totals about {evidenced:.1f} year(s), which does "
        f"not support a claim of {claimed:g} years."
    )


def _duration_claims(application: Application) -> list[_DurationClaim]:
    """Find every stated span of experience in the application."""
    claims: list[_DurationClaim] = []
    for section in application.sections:
        for sentence in _sentences(section.text):
            if "experience" not in sentence.casefold():
                continue
            for amount, unit in _DURATION_CLAIM.findall(sentence):
                years = float(amount)
                if unit.casefold().startswith("month"):
                    years /= 12.0
                claims.append(
                    _DurationClaim(
                        years=years, section=section.kind, text=sentence.strip()
                    )
                )
    return claims


def _dated_spans(application: Application, kind: SectionKind) -> list[_DatedSpan]:
    """Extract every date range from one section, with its duration."""
    section = application.section(kind)
    if section is None:
        return []

    spans: list[_DatedSpan] = []
    for sentence in _sentences(section.text):
        for match in _DATE_RANGE.finditer(sentence):
            years = _range_years(match)
            if years is not None:
                spans.append(_DatedSpan(text=sentence.strip(), years=years))
    return spans


def _range_years(match: re.Match[str]) -> float | None:
    """Convert one matched date range into a duration in years."""
    start_month, start_year, end_month, end_year, open_ended = match.groups()

    start = _to_months(start_year, start_month)
    if start is None:
        return None

    if open_ended:
        end = REFERENCE_YEAR * 12 + REFERENCE_MONTH
    else:
        end = _to_months(end_year, end_month)
        if end is None:
            return None

    return max(0.0, (end - start) / 12.0)


def _to_months(year: str | None, month: str | None) -> int | None:
    """Absolute month index, so two dates can be subtracted."""
    if not year:
        return None
    index = MONTHS.get((month or "").casefold()[:3], 1)
    return int(year) * 12 + index


def _total_years(spans: list[_DatedSpan]) -> float:
    return sum(span.years for span in spans)


def _education_context(application: Application) -> list[EvidenceItem]:
    """Quote education dates when they bear on a professional-duration claim."""
    return [
        EvidenceItem(
            section=SectionKind.EDUCATION,
            source_text=span.text,
            weight=SECTION_WEIGHT[SectionKind.EDUCATION],
            note="Education timeline, for context",
        )
        for span in _dated_spans(application, SectionKind.EDUCATION)
    ]


# --------------------------------------------------------------------------
# Claimed mastery vs. evidence
# --------------------------------------------------------------------------


def _evidence_conflicts(application: Application) -> list[Contradiction]:
    """Flag asserted mastery the graded evidence does not carry."""
    conflicts: list[Contradiction] = []

    for assessment in grade_claims(extract_claims(application)):
        assertion = next(iter(assessment.assertions), None)
        if assertion is None:
            continue

        if not assessment.supporting:
            conflicts.append(
                Contradiction(
                    kind=ContradictionKind.COVER_NOTE_ONLY,
                    subject=assessment.skill,
                    claim_text=assertion.source_text,
                    claim_section=assertion.section,
                    counter_evidence=[],
                    evidence_note=(
                        f"'{assessment.skill}' appears only in the cover note. "
                        f"No skills entry, project, work history or coursework "
                        f"in this application mentions it."
                    ),
                    assessment="Claim insufficiently supported.",
                )
            )
            continue

        if assessment.is_overclaimed:
            conflicts.append(
                Contradiction(
                    kind=ContradictionKind.EXPERTISE_UNSUPPORTED,
                    subject=assessment.skill,
                    claim_text=assertion.source_text,
                    claim_section=assertion.section,
                    counter_evidence=assessment.supporting,
                    evidence_note=(
                        f"Claimed '{assessment.claimed_strength.value}', but the "
                        f"supporting evidence reaches only "
                        f"{assessment.evidence_level.value} "
                        f"({assessment.evidence_level.label.lower()}). The "
                        f"support that was found is quoted below."
                    ),
                    assessment="Claim insufficiently supported.",
                )
            )

    return conflicts


def _sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT.split(text) if part.strip()]
