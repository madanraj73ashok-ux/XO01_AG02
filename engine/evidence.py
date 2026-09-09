"""Evidence grading.

This is the module that answers PS02's actual question: not "is the skill
mentioned?" but "how well-supported is the claim before we trust it?"

A mention is not evidence. Where the mention appears is what matters:

  cover note   an assertion about oneself, supports nothing
  skills list  a listing, the weakest possible signal
  education    coursework - exposure, not application
  projects     the skill actually applied to something
  experience   applied in professional work

Nothing here is generated. Every piece of evidence quotes text that is
genuinely in the application, because an assessment the system cannot point
at is an assessment it has no right to make.
"""

from __future__ import annotations

import re

from engine.models import (
    Claim,
    ClaimAssessment,
    ClaimStrength,
    EvidenceItem,
    EvidenceLevel,
    SectionKind,
)

# How much support each section can confer. Cover notes score zero by design:
# a candidate asserting their own competence is the claim, not evidence for it.
SECTION_WEIGHT: dict[SectionKind, int] = {
    SectionKind.COVER_NOTE: 0,
    SectionKind.SKILLS: 1,
    SectionKind.EDUCATION: 1,
    SectionKind.PROJECTS: 2,
    SectionKind.EXPERIENCE: 3,
}

SECTION_NOTE: dict[SectionKind, str] = {
    SectionKind.COVER_NOTE: "Asserted in the cover note - a claim, not support",
    SectionKind.SKILLS: "Listed in the skills section only",
    SectionKind.EDUCATION: "Coursework or academic exposure",
    SectionKind.PROJECTS: "Applied in a project",
    SectionKind.EXPERIENCE: "Applied in professional work",
}

# Verbs that indicate the candidate described *doing* something, rather than
# only naming a technology.
IMPLEMENTATION_VERBS: tuple[str, ...] = (
    "built", "developed", "implemented", "designed", "maintained", "wrote",
    "deployed", "integrated", "created", "programmed", "containerised",
    "containerized", "engineered", "automated", "optimised", "optimized",
)

WEIGHT_TO_LEVEL: dict[int, EvidenceLevel] = {
    0: EvidenceLevel.E0,
    1: EvidenceLevel.E1,
    2: EvidenceLevel.E2,
    3: EvidenceLevel.E3,
}


def grade_claims(claims: list[Claim]) -> list[ClaimAssessment]:
    """Grade every distinct skill claimed in an application."""
    skills = sorted({claim.skill for claim in claims})
    return [
        grade_skill(skill, [c for c in claims if c.skill == skill])
        for skill in skills
    ]


def grade_skill(skill: str, claims: list[Claim]) -> ClaimAssessment:
    """Grade one skill from every mention of it in the application."""
    supporting = [
        _as_evidence(claim)
        for claim in claims
        if SECTION_WEIGHT[claim.section] > 0
    ]
    assertions = [
        _as_evidence(claim)
        for claim in claims
        if SECTION_WEIGHT[claim.section] == 0
    ]

    level = _level_for(supporting)

    return ClaimAssessment(
        skill=skill,
        claimed_strength=_strongest_claim(claims),
        evidence_level=level,
        supporting=supporting,
        assertions=assertions,
        reasons=_reasons(level, supporting, assertions),
    )


def _as_evidence(claim: Claim) -> EvidenceItem:
    """Turn a mention into an evidence record, quoting its source."""
    return EvidenceItem(
        section=claim.section,
        source_text=claim.source_text,
        weight=SECTION_WEIGHT[claim.section],
        note=SECTION_NOTE[claim.section],
    )


def _level_for(supporting: list[EvidenceItem]) -> EvidenceLevel:
    """Place the claim on the ladder from the support found.

    The base level is the strongest single kind of support. E4 is reserved
    for support that is both professional and corroborated somewhere else,
    with the candidate describing what they actually did.
    """
    if not supporting:
        return EvidenceLevel.E0

    base = WEIGHT_TO_LEVEL[max(item.weight for item in supporting)]

    if base is EvidenceLevel.E3 and _is_corroborated(supporting):
        return EvidenceLevel.E4
    return base


def _is_corroborated(supporting: list[EvidenceItem]) -> bool:
    """Whether professional support is independently backed up.

    Requires the skill to appear in more than one section *and* for the
    candidate to have described implementing something, not just named it.
    """
    sections = {item.section for item in supporting}
    return len(sections) >= 2 and any(
        _describes_implementation(item.source_text) for item in supporting
    )


def _describes_implementation(text: str) -> bool:
    """Whether a span describes doing the work, rather than naming a tool."""
    lowered = text.casefold()
    return any(
        re.search(rf"(?<![a-z]){verb}(?![a-z])", lowered)
        for verb in IMPLEMENTATION_VERBS
    )


def _strongest_claim(claims: list[Claim]) -> ClaimStrength:
    """The boldest phrasing the candidate used anywhere for this skill."""
    order = [
        ClaimStrength.EXPERT,
        ClaimStrength.PROFICIENT,
        ClaimStrength.FAMILIAR,
    ]
    strengths = {claim.strength for claim in claims}
    return next(
        (strength for strength in order if strength in strengths),
        ClaimStrength.UNSPECIFIED,
    )


def _reasons(
    level: EvidenceLevel,
    supporting: list[EvidenceItem],
    assertions: list[EvidenceItem],
) -> list[str]:
    """Explain the grade in terms a recruiter can check against the document."""
    if not supporting:
        where = ", ".join(sorted({item.section.value for item in assertions}))
        return [
            f"No supporting evidence found; the skill appears only in: {where}."
            if assertions
            else "No mention of this skill was found in the application."
        ]

    reasons = [
        f"{item.note} ({item.section.value})"
        for item in sorted(supporting, key=lambda i: -i.weight)
    ]

    if level is EvidenceLevel.E4:
        reasons.append(
            "Corroborated across more than one section, with the candidate "
            "describing what they implemented."
        )
    if assertions:
        reasons.append(
            "Note: also asserted in the cover note, which is not counted as "
            "support."
        )
    return reasons
