"""Requisition loading and conflict detection.

PS02 notes that requisition requirements "sometimes conflict (a 'must-have'
skill combined with a junior-level experience requirement)". Screening that
only looks at candidates will silently produce a weak pool in that case and
blame the applicants. This module inspects the requisition itself and flags
the inconsistency instead.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from engine.models import (
    ConflictKind,
    Requirement,
    RequirementConflict,
    Requisition,
    Seniority,
)

# Upper bound on professional experience that is plausible for each advertised
# level. A requirement demanding more than this contradicts the role's own
# seniority label.
PLAUSIBLE_MAX_YEARS: dict[Seniority, float] = {
    Seniority.INTERN: 0.0,
    Seniority.JUNIOR: 2.0,
    Seniority.MID: 5.0,
    Seniority.SENIOR: 8.0,
    Seniority.LEAD: 12.0,
}


def load_requisition(path: str | Path) -> Requisition:
    """Load and validate a requisition from JSON.

    Raises FileNotFoundError if the path does not exist, and pydantic's
    ValidationError if the file does not match the expected shape. Both are
    left to surface rather than being swallowed - a malformed requisition
    must not screen candidates against silently wrong criteria.
    """
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    return Requisition.model_validate(raw)


def detect_conflicts(requisition: Requisition) -> list[RequirementConflict]:
    """Return every internal inconsistency found in the requisition."""
    return [
        *_detect_seniority_mismatches(requisition),
        *_detect_duplicates(requisition),
        *_detect_salary_caps(requisition),
    ]


def _detect_seniority_mismatches(
    requisition: Requisition,
) -> list[RequirementConflict]:
    """Flag requirements demanding more experience than the role level implies."""
    ceiling = PLAUSIBLE_MAX_YEARS[requisition.seniority]
    level = requisition.seniority.value

    return [
        RequirementConflict(
            kind=ConflictKind.SENIORITY_EXPERIENCE_MISMATCH,
            requirement_ids=[requirement.id],
            detail=(
                f"'{requirement.skill}' asks for {_years(requirement.min_years)} "
                f"of experience, but the role is advertised as {level}-level, "
                f"where {_years(ceiling)} is the plausible ceiling."
            ),
            recommendation=(
                "Recruiter review required: lower the experience threshold, "
                "raise the advertised level, or move this to preferred."
            ),
        )
        for requirement in requisition.requirements
        if requirement.min_years is not None and requirement.min_years > ceiling
    ]


def _detect_duplicates(requisition: Requisition) -> list[RequirementConflict]:
    """Flag one skill appearing more than once across the criteria."""
    by_skill: dict[str, list[Requirement]] = defaultdict(list)
    for requirement in requisition.requirements:
        by_skill[requirement.skill.strip().casefold()].append(requirement)

    return [
        RequirementConflict(
            kind=ConflictKind.DUPLICATE_REQUIREMENT,
            requirement_ids=[r.id for r in group],
            detail=(
                f"'{group[0].skill}' is listed {len(group)} times, as "
                f"{', '.join(r.necessity.value for r in group)}."
            ),
            recommendation=(
                "Recruiter review required: keep a single entry so the "
                "criterion is weighted once."
            ),
        )
        for group in by_skill.values()
        if len(group) > 1
    ]


def _detect_salary_caps(requisition: Requisition) -> list[RequirementConflict]:
    """Surface a compensation ceiling as a recruiter-owned restriction.

    A cap is not a judgement about an applicant. It is a restrictive condition
    on the requisition that has to remain visible next to technical criteria.
    """
    return [
        RequirementConflict(
            kind=ConflictKind.RESTRICTIVE_SALARY_CAP,
            requirement_ids=[requirement.id],
            detail=(
                f"'{requirement.skill}' caps compensation at "
                f"₹{requirement.max_salary_lpa:g} LPA."
            ),
            recommendation=(
                "Recruiter review required: confirm this ceiling is compatible "
                "with the required experience and skills."
            ),
        )
        for requirement in requisition.requirements
        if requirement.max_salary_lpa is not None
    ]


def _years(value: float | None) -> str:
    """Render a year count for human-readable conflict messages."""
    if value is None:
        return "an unspecified amount"
    if value == 0:
        return "no professional experience"
    rendered = int(value) if float(value).is_integer() else value
    unit = "year" if value == 1 else "years"
    return f"{rendered}+ {unit}"
