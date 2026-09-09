"""Per-requirement assessment.

Brings the pieces together: for every criterion in the requisition, decide how
well this candidate meets it, using the evidence grade rather than the presence
of a keyword.

Two rules shape everything here:

1. A requirement met only by *adjacent* technology is not met. Arduino is not
   ROS 2. The adjacent skill is still reported as the closest thing found, so
   the recruiter can judge it themselves - but it never silently counts.

2. "Unaddressed" is not the same as "weak". A candidate who never mentions a
   criterion has told you something different from one who mentions it badly,
   and collapsing the two loses information the recruiter needs.
"""

from __future__ import annotations

import re

from engine.claims import extract_claims
from engine.equivalence import RELATED_SKILLS, canonical_for, normalize
from engine.evidence import grade_claims
from engine.models import (
    Application,
    CandidateAssessment,
    ClaimAssessment,
    EvidenceLevel,
    FitStatus,
    MatchKind,
    Requirement,
    RequirementFit,
    Requisition,
)

# Evidence level required to call a criterion genuinely satisfied. E2 - a
# personal or academic project - is real but is not professional demonstration,
# so it reads as moderate rather than strong.
STATUS_FOR_LEVEL: dict[EvidenceLevel, FitStatus] = {
    EvidenceLevel.E0: FitStatus.WEAK,
    EvidenceLevel.E1: FitStatus.WEAK,
    EvidenceLevel.E2: FitStatus.MODERATE,
    EvidenceLevel.E3: FitStatus.STRONG,
    EvidenceLevel.E4: FitStatus.STRONG,
}


def assess_candidate(
    application: Application, requisition: Requisition
) -> CandidateAssessment:
    """Measure one application against every criterion in the requisition."""
    graded = {
        assessment.skill: assessment
        for assessment in grade_claims(extract_claims(application))
    }

    return CandidateAssessment(
        application_id=application.id,
        candidate_name=application.candidate_name,
        fits=[
            _fit_for(requirement, graded, application)
            for requirement in requisition.requirements
        ],
    )


def assess_pool(
    applications: list[Application], requisition: Requisition
) -> list[CandidateAssessment]:
    """Assess every candidate against the same requisition."""
    return [assess_candidate(app, requisition) for app in applications]


def _fit_for(
    requirement: Requirement,
    graded: dict[str, ClaimAssessment],
    application: Application,
) -> RequirementFit:
    """Decide how a candidate measures against one requirement."""
    canonical = canonical_for(requirement.skill) or requirement.skill
    assessment = graded.get(canonical)

    if assessment is None:
        return _unaddressed(requirement, canonical, application)

    status = STATUS_FOR_LEVEL[assessment.evidence_level]
    match_kind = _match_kind(assessment, requirement)

    return RequirementFit(
        requirement_id=requirement.id,
        skill=requirement.skill,
        necessity=requirement.necessity,
        status=status,
        evidence_level=assessment.evidence_level,
        match_kind=match_kind,
        claimed_strength=assessment.claimed_strength,
        is_overclaimed=assessment.is_overclaimed,
        supporting=assessment.supporting,
        reasons=_reasons(assessment, match_kind, status),
    )


def _unaddressed(
    requirement: Requirement, canonical: str, application: Application
) -> RequirementFit:
    """Build the verdict for a criterion the candidate never spoke to."""
    closest = _adjacent_terms(canonical, application)

    reasons = ["The application does not address this requirement."]
    if closest:
        reasons.append(
            f"Closest thing found: {', '.join(closest)} - adjacent technology, "
            f"not the same capability, so it does not satisfy this criterion."
        )

    return RequirementFit(
        requirement_id=requirement.id,
        skill=requirement.skill,
        necessity=requirement.necessity,
        status=FitStatus.UNADDRESSED,
        evidence_level=EvidenceLevel.E0,
        match_kind=MatchKind.RELATED if closest else MatchKind.NONE,
        closest_evidence=closest,
        reasons=reasons,
    )


def _adjacent_terms(canonical: str, application: Application) -> list[str]:
    """Find adjacent-but-not-equivalent technology mentioned in the text.

    Reported so an unaddressed requirement still shows the recruiter what the
    candidate *does* have nearby - which is exactly what pool-gap reporting
    needs when nobody satisfies a criterion.
    """
    text = normalize(application.full_text)
    return sorted(
        term
        for term in RELATED_SKILLS.get(canonical, set())
        if re.search(rf"(?<![a-z0-9]){re.escape(normalize(term))}(?![a-z0-9])", text)
    )


def _match_kind(assessment: ClaimAssessment, requirement: Requirement) -> MatchKind:
    """Whether the candidate used the requisition's own wording, or a synonym."""
    required = normalize(requirement.skill)
    used_exact_wording = any(
        required in normalize(item.source_text)
        for item in [*assessment.supporting, *assessment.assertions]
    )
    return MatchKind.EXACT if used_exact_wording else MatchKind.EQUIVALENT


def _reasons(
    assessment: ClaimAssessment, match_kind: MatchKind, status: FitStatus
) -> list[str]:
    """Explain the verdict, carrying the evidence grade's own reasoning."""
    reasons = [
        f"{status.label} fit on {assessment.evidence_level.value} evidence "
        f"({assessment.evidence_level.label.lower()})."
    ]

    if match_kind is MatchKind.EQUIVALENT:
        reasons.append(
            "Matched on equivalent terminology, not the requisition's exact "
            "wording - not penalised for phrasing."
        )

    if assessment.is_overclaimed:
        reasons.append(
            f"Claimed '{assessment.claimed_strength.value}' but the evidence "
            f"reaches only {assessment.evidence_level.value} - flagged for review."
        )

    reasons.extend(assessment.reasons)
    return reasons
