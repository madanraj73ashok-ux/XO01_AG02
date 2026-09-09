"""Trade-off analysis and shortlisting.

PS02's fourth objective: "surfaces genuine trade-offs between candidates rather
than collapsing to one score".

So this module produces a ranked list without ever producing a rating. Each
candidate is measured on four independent axes, and the ordering is a reading
order for the recruiter - not a verdict. Where two candidates are close, the
trade-off sentence says what each buys and what each costs, and the comparison
view refuses to name a winner at all.
"""

from __future__ import annotations

from engine.models import (
    CandidateAssessment,
    Comparison,
    ComparisonLine,
    Dimension,
    DimensionScore,
    FitStatus,
    ShortlistEntry,
)

# Two candidates within this much on an axis are treated as equivalent there.
# Without it, a rounding difference would be reported as a real advantage.
MATERIAL_DIFFERENCE = 0.10


def build_shortlist(assessments: list[CandidateAssessment]) -> list[ShortlistEntry]:
    """Rank candidates for reading order, with the case for and against each."""
    scored = [(assessment, _dimensions(assessment)) for assessment in assessments]
    scored.sort(key=lambda pair: _ordering_key(pair[1]), reverse=True)

    return [
        _entry(assessment, dimensions, rank)
        for rank, (assessment, dimensions) in enumerate(scored, start=1)
    ]


def full_requisition_message(assessments: list[CandidateAssessment]) -> str:
    """State the full-requisition result without turning it into a match score."""
    qualified = [assessment.candidate_name for assessment in assessments if _fully_qualified(assessment)]
    if not qualified:
        return "No candidate fully satisfies all required criteria."
    if len(qualified) == 1:
        return f"{qualified[0]} fully satisfies all required criteria."
    return f"{', '.join(qualified)} fully satisfy all required criteria."


def _fully_qualified(assessment: CandidateAssessment) -> bool:
    return len(assessment.strong_required) == len(assessment.required_fits)


def compare(left: CandidateAssessment, right: CandidateAssessment) -> Comparison:
    """Compare two candidates axis by axis, without declaring a winner."""
    left_scores = {d.dimension: d for d in _dimensions(left)}
    right_scores = {d.dimension: d for d in _dimensions(right)}

    lines = [
        _comparison_line(dimension, left, right, left_scores, right_scores)
        for dimension in Dimension
    ]

    return Comparison(
        left_id=left.application_id,
        right_id=right.application_id,
        lines=lines,
        verdict=_verdict(left, right, lines),
    )


# --------------------------------------------------------------------------
# Dimensions
# --------------------------------------------------------------------------


def _dimensions(assessment: CandidateAssessment) -> list[DimensionScore]:
    """Measure a candidate on each axis, each with its own explanation."""
    return [
        _required_coverage(assessment),
        _evidence_depth(assessment),
        _breadth(assessment),
        _claim_integrity(assessment),
    ]


def _required_coverage(assessment: CandidateAssessment) -> DimensionScore:
    required = assessment.required_fits
    met = len(assessment.strong_required)
    total = len(required) or 1

    return DimensionScore(
        dimension=Dimension.REQUIRED_COVERAGE,
        value=met / total,
        detail=f"{met} of {len(required)} required criteria demonstrated.",
    )


def _evidence_depth(assessment: CandidateAssessment) -> DimensionScore:
    """How strong the supporting evidence is where it exists at all."""
    graded = [
        fit for fit in assessment.fits if fit.status is not FitStatus.UNADDRESSED
    ]
    if not graded:
        return DimensionScore(
            dimension=Dimension.EVIDENCE_DEPTH,
            value=0.0,
            detail="No criterion in this requisition is addressed at all.",
        )

    average = sum(fit.evidence_level.rank for fit in graded) / (4 * len(graded))
    best = max(graded, key=lambda fit: fit.evidence_level.rank)

    return DimensionScore(
        dimension=Dimension.EVIDENCE_DEPTH,
        value=average,
        detail=(
            f"Across {len(graded)} addressed criteria; strongest is "
            f"{best.skill} at {best.evidence_level.value}."
        ),
    )


def _breadth(assessment: CandidateAssessment) -> DimensionScore:
    """Coverage of the preferred criteria - the nice-to-haves."""
    preferred = [fit for fit in assessment.fits if not fit.is_required]
    if not preferred:
        return DimensionScore(
            dimension=Dimension.BREADTH,
            value=0.0,
            detail="This requisition lists no preferred criteria.",
        )

    addressed = [
        fit for fit in preferred if fit.status is not FitStatus.UNADDRESSED
    ]
    return DimensionScore(
        dimension=Dimension.BREADTH,
        value=len(addressed) / len(preferred),
        detail=f"{len(addressed)} of {len(preferred)} preferred criteria addressed.",
    )


def _claim_integrity(assessment: CandidateAssessment) -> DimensionScore:
    """How closely what the candidate claimed matches what they showed.

    A candidate who claims nothing they cannot show scores full marks here,
    regardless of how skilled they are. It measures honesty of presentation,
    not ability - and is reported separately for exactly that reason.
    """
    total = len(assessment.fits) or 1
    overclaimed = len(assessment.overclaims)

    if overclaimed == 0:
        detail = "No claim exceeds the evidence supporting it."
    else:
        names = ", ".join(fit.skill for fit in assessment.overclaims)
        detail = f"{overclaimed} claim(s) exceed their evidence: {names}."

    return DimensionScore(
        dimension=Dimension.CLAIM_INTEGRITY,
        value=1.0 - (overclaimed / total),
        detail=detail,
    )


def _ordering_key(dimensions: list[DimensionScore]) -> tuple[float, float, float]:
    """Reading order: required coverage first, then depth, then integrity.

    Deliberately a tuple rather than a weighted sum. There is no single number
    anywhere in this module that could be mistaken for a candidate rating.
    """
    scores = {d.dimension: d.value for d in dimensions}
    return (
        scores[Dimension.REQUIRED_COVERAGE],
        scores[Dimension.EVIDENCE_DEPTH],
        scores[Dimension.CLAIM_INTEGRITY],
    )


# --------------------------------------------------------------------------
# Narrative
# --------------------------------------------------------------------------


def _entry(
    assessment: CandidateAssessment, dimensions: list[DimensionScore], rank: int
) -> ShortlistEntry:
    strengths = [
        fit.skill for fit in assessment.fits if fit.status is FitStatus.STRONG
    ]
    gaps = [
        f"{fit.skill} ({fit.status.label.lower()})"
        for fit in assessment.required_fits
        if not fit.is_met
    ]
    risks = [
        f"{fit.skill}: claimed '{fit.claimed_strength.value}', evidence "
        f"{fit.evidence_level.value}"
        for fit in assessment.overclaims
    ]

    return ShortlistEntry(
        application_id=assessment.application_id,
        candidate_name=assessment.candidate_name,
        rank=rank,
        dimensions=dimensions,
        strengths=strengths,
        gaps=gaps,
        risks=risks,
        best_fit=_best_fit(strengths),
        tradeoff=_tradeoff(strengths, gaps, risks),
    )


def _best_fit(strengths: list[str]) -> str:
    if not strengths:
        return "No criterion is demonstrated strongly enough to place this candidate."
    if len(strengths) == 1:
        return f"Narrow fit: {strengths[0]} only."
    return f"Best suited to work centred on {', '.join(strengths[:3])}."


def _tradeoff(strengths: list[str], gaps: list[str], risks: list[str]) -> str:
    """State what this candidate buys and what they cost, in one sentence."""
    if not strengths and not gaps:
        return "Not enough addressed criteria to describe a trade-off."

    parts = []
    if strengths:
        parts.append(f"Brings demonstrated {', '.join(strengths[:3])}")
    if gaps:
        parts.append(f"but does not demonstrate {', '.join(gaps[:3])}")
    if risks:
        parts.append(f"and carries {len(risks)} unsupported claim(s)")

    return "; ".join(parts) + "."


def _comparison_line(
    dimension: Dimension,
    left: CandidateAssessment,
    right: CandidateAssessment,
    left_scores: dict[Dimension, DimensionScore],
    right_scores: dict[Dimension, DimensionScore],
) -> ComparisonLine:
    left_score = left_scores[dimension]
    right_score = right_scores[dimension]
    difference = left_score.value - right_score.value

    if abs(difference) < MATERIAL_DIFFERENCE:
        stronger = None
        detail = f"Comparable. {left_score.detail} {right_score.detail}"
    elif difference > 0:
        stronger = left.application_id
        detail = f"{left.application_id} stronger here. {left_score.detail}"
    else:
        stronger = right.application_id
        detail = f"{right.application_id} stronger here. {right_score.detail}"

    return ComparisonLine(
        dimension=dimension,
        left_value=left_score.value,
        right_value=right_score.value,
        stronger=stronger,
        detail=detail,
    )


def _verdict(
    left: CandidateAssessment,
    right: CandidateAssessment,
    lines: list[ComparisonLine],
) -> str:
    """Describe the shape of the difference. Never name a winner."""
    left_wins = [line for line in lines if line.stronger == left.application_id]
    right_wins = [line for line in lines if line.stronger == right.application_id]

    if not left_wins and not right_wins:
        return (
            f"{left.application_id} and {right.application_id} are comparable on "
            f"every axis measured. The choice rests on factors outside this "
            f"assessment."
        )

    if left_wins and right_wins:
        left_axes = ", ".join(line.dimension.label.lower() for line in left_wins)
        right_axes = ", ".join(line.dimension.label.lower() for line in right_wins)
        return (
            f"A genuine trade-off: {left.application_id} is stronger on "
            f"{left_axes}, while {right.application_id} is stronger on "
            f"{right_axes}. Which matters more is the recruiter's call."
        )

    ahead = left if left_wins else right
    behind = right if left_wins else left
    axes = ", ".join(
        line.dimension.label.lower() for line in (left_wins or right_wins)
    )
    return (
        f"{ahead.application_id} leads on {axes}, and {behind.application_id} "
        f"does not lead on any axis measured - but neither is disqualified by "
        f"this comparison alone."
    )
