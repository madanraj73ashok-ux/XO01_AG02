"""Surprise Challenge 02: requirement conflicts and trade-off shortlisting.

These cases exercise the challenge as a recruiter sees it: every criterion is
visible, constraints are never silently converted into a score, and a missing
statement is reported as insufficient evidence rather than a candidate defect.
"""

from __future__ import annotations

from engine.assessment import assess_candidate, assess_pool
from engine.contradictions import find_contradictions
from engine.models import (
    Application,
    FitStatus,
    MatchKind,
    Necessity,
    Requirement,
    Requisition,
    Section,
    SectionKind,
    Seniority,
)
from engine.poolgap import analyse_pool, gaps
from engine.requisition import detect_conflicts
from engine.tradeoffs import build_shortlist, full_requisition_message


def _requirements() -> list[Requirement]:
    return [
        Requirement(
            id="EXP",
            skill="Experience",
            necessity=Necessity.REQUIRED,
            min_years=5,
            description="At least five years of professional experience.",
        ),
        Requirement(id="ML", skill="Machine Learning", necessity=Necessity.REQUIRED),
        Requirement(id="K8S", skill="Kubernetes", necessity=Necessity.REQUIRED),
        Requirement(
            id="PAY",
            skill="Salary expectation",
            necessity=Necessity.REQUIRED,
            max_salary_lpa=8,
            description="Compensation must not exceed ₹8 LPA.",
        ),
    ]


def _requisition(*, seniority: Seniority = Seniority.JUNIOR) -> Requisition:
    return Requisition(
        id="REQ-CH02",
        title="Junior ML Platform Engineer",
        seniority=seniority,
        requirements=_requirements(),
    )


def _candidate(identifier: str, text: str, *, cover: str = "") -> Application:
    return Application(
        id=identifier,
        candidate_name=f"Candidate {identifier}",
        sections=[
            Section(kind=SectionKind.EXPERIENCE, text=text),
            Section(kind=SectionKind.COVER_NOTE, text=cover),
        ],
    )


def _fit(assessment, requirement_id: str):
    return next(fit for fit in assessment.fits if fit.requirement_id == requirement_id)


def test_a_candidate_satisfying_every_requirement_is_called_fully_qualified() -> None:
    candidate = _candidate(
        "A-FULL",
        "Senior engineer with 6 years of experience. Built Machine Learning "
        "services and deployed them to Kubernetes.",
        cover="My expected salary is ₹8 LPA.",
    )

    assessments = assess_pool([candidate], _requisition())

    assert all(fit.is_met for fit in assessments[0].required_fits)
    assert "Candidate A-FULL fully satisfies all required criteria." == full_requisition_message(assessments)


def test_b_no_candidate_fully_qualified_has_the_required_explicit_message() -> None:
    candidate = _candidate(
        "A-NONE",
        "Engineer with 2 years of experience. Built Machine Learning services.",
        cover="My expected salary is ₹10 LPA.",
    )

    assert full_requisition_message(assess_pool([candidate], _requisition())) == (
        "No candidate fully satisfies all required criteria."
    )


def test_c_strongest_candidate_still_names_every_unmet_required_criterion() -> None:
    candidate = _candidate(
        "A-CLOSE",
        "Engineer with 6 years of experience. Built Machine Learning services "
        "and deployed them to Kubernetes.",
        cover="My expected salary is ₹10 LPA.",
    )

    assessment = assess_candidate(candidate, _requisition())
    entry = build_shortlist([assessment])[0]

    assert entry.strengths == ["Experience", "Machine Learning", "Kubernetes"]
    assert entry.gaps == ["Salary expectation (weak)"]
    assert "Salary expectation (weak)" in entry.tradeoff
    assert "100%" not in entry.tradeoff


def test_d_experience_and_ml_do_not_hide_kubernetes_or_salary_tradeoffs() -> None:
    candidate = _candidate(
        "A-D",
        "Engineer with 5 years of experience. Built Machine Learning services.",
        cover="Expected salary: ₹10 LPA.",
    )

    entry = build_shortlist([assess_candidate(candidate, _requisition())])[0]

    assert entry.strengths == ["Experience", "Machine Learning"]
    assert entry.gaps == ["Kubernetes (unaddressed)", "Salary expectation (weak)"]
    assert "Kubernetes" in entry.tradeoff
    assert "Salary expectation" in entry.tradeoff


def test_e_kubernetes_salary_and_ml_do_not_hide_the_experience_gap() -> None:
    candidate = _candidate(
        "A-E",
        "Engineer with 3 years of experience. Built Machine Learning services "
        "and operated Kubernetes clusters.",
        cover="Expected salary: ₹8 LPA.",
    )

    assessment = assess_candidate(candidate, _requisition())
    entry = build_shortlist([assessment])[0]

    assert _fit(assessment, "EXP").status is FitStatus.WEAK
    assert entry.gaps == ["Experience (weak)"]
    assert "Experience (weak)" in entry.tradeoff


def test_f_restrictive_requirements_and_zero_coverage_are_reported_separately() -> None:
    candidate = _candidate(
        "A-F",
        "Engineer with 5 years of experience. Built Machine Learning services.",
        cover="Expected salary: ₹8 LPA.",
    )
    requisition = _requisition()

    conflicts = detect_conflicts(requisition)
    coverage = analyse_pool(assess_pool([candidate], requisition), requisition)
    kubernetes = next(item for item in coverage if item.requirement_id == "K8S")

    assert {conflict.kind.value for conflict in conflicts} >= {
        "seniority_experience_mismatch",
        "restrictive_salary_cap",
    }
    assert kubernetes.is_gap
    assert kubernetes.satisfied_count == 0
    assert kubernetes.conclusion.startswith("No applicant fully demonstrates")


def test_g_missing_constraint_evidence_is_not_treated_as_proof_of_absence() -> None:
    candidate = _candidate("A-G", "Built Machine Learning services on Kubernetes.")

    assessment = assess_candidate(candidate, _requisition())

    assert _fit(assessment, "EXP").status is FitStatus.UNADDRESSED
    assert _fit(assessment, "PAY").status is FitStatus.UNADDRESSED
    assert "insufficient evidence, not proof" in _fit(assessment, "EXP").reasons[0]
    assert "insufficient evidence, not proof" in _fit(assessment, "PAY").reasons[0]


def test_h_equivalent_ai_ml_terminology_remains_accepted() -> None:
    candidate = _candidate(
        "A-H",
        "Engineer with 5 years of experience. Built AI/ML services and deployed "
        "them to Kubernetes.",
        cover="Expected salary: ₹8 LPA.",
    )

    fit = _fit(assess_candidate(candidate, _requisition()), "ML")

    assert fit.status is FitStatus.STRONG
    assert fit.match_kind is MatchKind.EQUIVALENT


def test_i_challenge_one_contradictions_remain_visible_and_reduce_confidence() -> None:
    candidate = _candidate(
        "A-I",
        "Software Engineer, 2024 - 2025. Built Machine Learning services and "
        "deployed them to Kubernetes.",
        cover="I have 5 years of experience. Expected salary: ₹8 LPA.",
    )

    assessment = assess_candidate(candidate, _requisition())
    experience = _fit(assessment, "EXP")

    assert find_contradictions(candidate)
    assert experience.contradiction_count == 1
    assert experience.confidence < 0.25
    assert any("contradiction" in reason.lower() for reason, _ in experience.confidence_factors)


def test_pool_coverage_includes_every_constraint_and_never_uses_an_opaque_score() -> None:
    assessments = assess_pool(
        [
            _candidate(
                "A-1",
                "Engineer with 6 years of experience. Built Machine Learning and Kubernetes systems.",
                cover="Expected salary: ₹8 LPA.",
            ),
            _candidate(
                "A-2",
                "Engineer with 3 years of experience. Built Machine Learning systems.",
                cover="Expected salary: ₹10 LPA.",
            ),
        ],
        _requisition(),
    )
    coverage = analyse_pool(assessments, _requisition())

    assert {item.requirement_id for item in coverage} == {"EXP", "ML", "K8S", "PAY"}
    assert all(item.total_candidates == 2 for item in coverage)
    assert gaps(coverage) == []
    assert "score" not in build_shortlist(assessments)[0].model_dump()
