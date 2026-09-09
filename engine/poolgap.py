"""Talent-pool gap detection.

PS02 asks the system to "identify requisition requirements that the applicant
pool does not meet well". That is a different kind of finding from a candidate
assessment: when nobody satisfies a criterion, the useful conclusion is about
the *requisition* - it may be mis-scoped, or the market may simply not hold
that skill at this level - not about twelve individual failures.

So the gap is reported once, at pool level, with the closest evidence anyone
offered. That gives the recruiter something to act on: relax the criterion,
re-scope the role, or go and source differently.
"""

from __future__ import annotations

from engine.models import (
    CandidateAssessment,
    NearMiss,
    Necessity,
    PoolCoverage,
    RequirementFit,
    Requisition,
)


def analyse_pool(
    assessments: list[CandidateAssessment], requisition: Requisition
) -> list[PoolCoverage]:
    """Report how the whole pool measures against every criterion."""
    return [
        _coverage_for(
            requirement.id, requirement.skill, requirement.necessity, assessments
        )
        for requirement in requisition.requirements
    ]


def gaps(coverage: list[PoolCoverage]) -> list[PoolCoverage]:
    """Only the criteria no candidate demonstrates, required ones first."""
    return sorted(
        (entry for entry in coverage if entry.is_gap),
        key=lambda entry: (not entry.is_required, entry.skill),
    )


def _coverage_for(
    requirement_id: str,
    skill: str,
    necessity: Necessity,
    assessments: list[CandidateAssessment],
) -> PoolCoverage:
    """Count who satisfies one criterion, and who came closest."""
    pairs = [
        (assessment, fit)
        for assessment in assessments
        for fit in assessment.fits
        if fit.requirement_id == requirement_id
    ]

    satisfied = [a.application_id for a, fit in pairs if fit.is_met]

    return PoolCoverage(
        requirement_id=requirement_id,
        skill=skill,
        necessity=necessity,
        satisfied=satisfied,
        total_candidates=len(assessments),
        near_misses=[] if satisfied else _near_misses(pairs),
    )


def _near_misses(
    pairs: list[tuple[CandidateAssessment, RequirementFit]],
) -> list[NearMiss]:
    """Rank the candidates who came closest, strongest evidence first.

    Only candidates who offered *something* are listed. A candidate who said
    nothing relevant is not a near miss, and padding the list with them would
    misrepresent the pool.
    """
    misses = [
        NearMiss(
            application_id=assessment.application_id,
            candidate_name=assessment.candidate_name,
            evidence_level=fit.evidence_level,
            note=_describe(fit),
        )
        for assessment, fit in pairs
        if _has_something(fit)
    ]

    return sorted(misses, key=lambda miss: -miss.evidence_level.rank)


def _has_something(fit: RequirementFit) -> bool:
    """Whether this candidate offered anything at all toward the criterion."""
    return bool(fit.supporting) or bool(fit.closest_evidence)


def _describe(fit: RequirementFit) -> str:
    """Say what the candidate actually has, in checkable terms."""
    if fit.closest_evidence:
        return (
            f"{', '.join(fit.closest_evidence)} - adjacent technology, "
            f"not the required capability"
        )

    strongest = max(fit.supporting, key=lambda item: item.weight)
    detail = f"{strongest.note.lower()} ({fit.evidence_level.value})"

    if fit.is_overclaimed:
        return f"{detail}; claimed more than the evidence carries"
    return detail
