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
from engine.contradictions import find_contradictions
from engine.equivalence import RELATED_SKILLS, canonical_for, normalize
from engine.evidence import grade_claims
from engine.models import (
    Application,
    CandidateAssessment,
    ClaimAssessment,
    EvidenceItem,
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

_EXPERIENCE_REQUIREMENTS = {
    "experience",
    "professional experience",
    "years of experience",
}
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\b", re.IGNORECASE)
_SALARY = re.compile(
    r"(?:₹|rs\.?\s*)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?(?:\s+per\s+annum)?)\b",
    re.IGNORECASE,
)


def assess_candidate(
    application: Application, requisition: Requisition
) -> CandidateAssessment:
    """Measure one application against every criterion in the requisition."""
    graded = {
        assessment.skill: assessment
        for assessment in grade_claims(extract_claims(application))
    }

    contradictions = find_contradictions(application)
    fits = [
        _with_contradiction_context(
            _fit_for(requirement, graded, application), contradictions
        )
        for requirement in requisition.requirements
    ]

    return CandidateAssessment(
        application_id=application.id,
        candidate_name=application.candidate_name,
        fits=fits,
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
    if requirement.max_salary_lpa is not None:
        return _salary_fit(requirement, application)
    if (
        requirement.min_years is not None
        and normalize(requirement.skill) in _EXPERIENCE_REQUIREMENTS
    ):
        return _experience_fit(requirement, application)

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


def _experience_fit(requirement: Requirement, application: Application) -> RequirementFit:
    """Assess an explicitly stated total-experience constraint.

    This intentionally uses only a number the candidate actually supplied. If
    none is present, the outcome is insufficient evidence, not a claim that
    the candidate lacks experience.
    """
    stated = _stated_numbers(application, _YEARS)
    if not stated:
        return _constraint_unaddressed(
            requirement,
            "The application does not state verifiable years of experience; "
            "this is insufficient evidence, not proof the candidate lacks it.",
        )

    years, evidence = max(stated, key=lambda item: item[0])
    minimum = requirement.min_years or 0.0
    met = years >= minimum
    return _constraint_fit(
        requirement,
        met=met,
        evidence=evidence,
        reason=(
            f"Candidate states {years:g} year(s) of experience, meeting the "
            f"{minimum:g}+ year requirement."
            if met
            else f"Candidate states {years:g} year(s) of experience, below the "
            f"{minimum:g}+ year requirement."
        ),
    )


def _salary_fit(requirement: Requirement, application: Application) -> RequirementFit:
    """Assess a stated compensation expectation without treating silence as lack."""
    stated = _stated_numbers(application, _SALARY)
    if not stated:
        return _constraint_unaddressed(
            requirement,
            "The application does not state a salary expectation; this is "
            "insufficient evidence, not proof the candidate exceeds the cap.",
        )

    cap = requirement.max_salary_lpa or 0.0
    amount, evidence = max(stated, key=lambda item: item[0])
    met = amount <= cap
    return _constraint_fit(
        requirement,
        met=met,
        evidence=evidence,
        reason=(
            f"Candidate states ₹{amount:g} LPA, within the ₹{cap:g} LPA cap."
            if met
            else f"Candidate states ₹{amount:g} LPA, above the ₹{cap:g} LPA cap."
        ),
    )


def _stated_numbers(
    application: Application, pattern: re.Pattern[str]
) -> list[tuple[float, EvidenceItem]]:
    values: list[tuple[float, EvidenceItem]] = []
    for section in application.sections:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", section.text):
            for match in pattern.finditer(sentence):
                values.append(
                    (
                        float(match.group(1)),
                        EvidenceItem(
                            section=section.kind,
                            source_text=sentence.strip(),
                            weight=1,
                            note="Candidate-stated constraint; confirm during recruiter review",
                        ),
                    )
                )
    return values


def _constraint_unaddressed(requirement: Requirement, reason: str) -> RequirementFit:
    return RequirementFit(
        requirement_id=requirement.id,
        skill=requirement.skill,
        necessity=requirement.necessity,
        status=FitStatus.UNADDRESSED,
        evidence_level=EvidenceLevel.E0,
        match_kind=MatchKind.NONE,
        reasons=[reason],
    )


def _constraint_fit(
    requirement: Requirement,
    *,
    met: bool,
    evidence: EvidenceItem,
    reason: str,
) -> RequirementFit:
    return RequirementFit(
        requirement_id=requirement.id,
        skill=requirement.skill,
        necessity=requirement.necessity,
        status=FitStatus.STRONG if met else FitStatus.WEAK,
        evidence_level=EvidenceLevel.E1,
        match_kind=MatchKind.EXACT,
        supporting=[evidence],
        reasons=[reason, evidence.note],
    )


def _with_contradiction_context(fit: RequirementFit, contradictions) -> RequirementFit:
    """Lower confidence, never the evidence grade, for a related contradiction."""
    skill = normalize(fit.skill)
    related = [
        contradiction
        for contradiction in contradictions
        if skill in normalize(contradiction.subject)
        or normalize(contradiction.subject) in skill
    ]
    if not related:
        return fit
    return fit.model_copy(update={"contradiction_count": len(related)})


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
