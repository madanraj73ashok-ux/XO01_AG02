"""The product layer: jobs, terminology verdicts, states, storage, explanations.

These cover the behaviours an evaluator asks about directly, and the ones that
would be easy to regress quietly - a related technology drifting into
"equivalent", or an unreachable repository starting to count against someone.
"""

from __future__ import annotations

import pytest

from engine.equivalence import classify
from engine.external.states import UNAUTHENTICATED_404_NOTE, VerificationState
from engine.external.states import classify as classify_state
from engine.investigation import Relationship, explain, support_level, terminology_matrix
from engine.jobs import analyze_job, to_requisition
from engine.models import (
    Application,
    CandidateAssessment,
    EvidenceLevel,
    FitStatus,
    MatchKind,
    Necessity,
    RequirementFit,
    Section,
    SectionKind,
)
from engine.store import Job, JobStatus, Role, SkillSpec, StoredApplication, User
from engine.store.repository import LocalBackend, Store


# --------------------------------------------------------------------------
# Evaluator case 2: container orchestration is not ECS
# --------------------------------------------------------------------------


def test_ecs_is_related_to_container_orchestration_not_equivalent():
    """The question an evaluator asked. Vocabulary must not do evidence's job."""
    match = classify("ECS", "Container Orchestration")
    assert match.kind is MatchKind.RELATED
    assert match.kind.satisfies_requirement is False


def test_managed_container_services_are_all_related_only():
    for phrase in ("AWS ECS", "Elastic Container Service", "Fargate", "Docker"):
        assert classify(phrase, "Container Orchestration").kind is MatchKind.RELATED


def test_kubernetes_is_equivalent_to_container_orchestration():
    """Adjacency is not the same as refusing every synonym."""
    assert classify("Kubernetes", "Container Orchestration").kind is MatchKind.EQUIVALENT
    assert classify("k8s", "Container Orchestration").kind is MatchKind.EQUIVALENT


def test_the_original_equivalences_still_hold():
    assert classify("Robot Operating System 2", "ROS 2").kind is MatchKind.EQUIVALENT
    assert classify("Arduino", "ROS 2").kind is MatchKind.RELATED


# --------------------------------------------------------------------------
# Evaluator case 1: junior plus five years
# --------------------------------------------------------------------------


def _junior_job(**overrides) -> Job:
    defaults = dict(
        recruiter_id="rec",
        title="Junior Robotics Software Engineer",
        seniority="junior",
        required_skills=[SkillSpec(skill="ROS 2"), SkillSpec(skill="Python")],
        preferred_skills=[SkillSpec(skill="Computer Vision")],
        min_years_total=5.0,
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_junior_role_demanding_five_years_raises_a_conflict():
    analysis = analyze_job(_junior_job())
    assert analysis.has_conflicts
    assert "junior" in analysis.conflicts[0].detail.lower()
    assert "review" in analysis.conflicts[0].recommendation.lower()


def test_the_conflict_is_reported_not_resolved():
    """Neither half of the contradiction may be quietly relaxed."""
    analysis = analyze_job(_junior_job())
    experience = [
        requirement
        for requirement in analysis.requisition.requirements
        if requirement.min_years == 5.0
    ]
    assert experience, "the five-year requirement must survive analysis intact"
    assert analysis.requisition.seniority.value == "junior"


def test_a_senior_role_asking_for_five_years_is_not_a_conflict():
    assert not analyze_job(_junior_job(seniority="senior")).has_conflicts


def test_an_unrecognised_seniority_does_not_silently_become_senior():
    """Defaulting upward would make the conflict disappear."""
    assert to_requisition(_junior_job(seniority="wizard")).seniority.value == "junior"


def test_required_and_preferred_survive_the_conversion():
    requisition = to_requisition(_junior_job())
    assert [r.skill for r in requisition.required] == [
        "ROS 2",
        "Python",
        "Professional Experience",
    ]
    assert [r.skill for r in requisition.preferred] == ["Computer Vision"]


# --------------------------------------------------------------------------
# Evaluator case 4: no evidence is not the same as unable to verify
# --------------------------------------------------------------------------


def test_unauthenticated_404_cannot_be_reported_as_missing():
    state, note = classify_state(status_code=404, authenticated=False)
    assert state is VerificationState.UNABLE_TO_VERIFY
    assert note == UNAUTHENTICATED_404_NOTE


def test_authenticated_404_is_an_authoritative_negative():
    state, _ = classify_state(status_code=404, authenticated=True)
    assert state is VerificationState.NOT_FOUND


def test_rate_limiting_is_never_reported_as_private():
    state, note = classify_state(status_code=403, authenticated=True, rate_limited=True)
    assert state is VerificationState.UNABLE_TO_VERIFY
    assert "rate limited" in note


def test_forbidden_without_rate_limiting_is_private():
    state, _ = classify_state(status_code=403, authenticated=True)
    assert state is VerificationState.PRIVATE_AUTH_REQUIRED


def test_a_transport_failure_establishes_nothing():
    state, _ = classify_state(
        status_code=None, authenticated=True, transport_error="timed out"
    )
    assert state is VerificationState.UNABLE_TO_VERIFY


def test_no_verification_state_is_evidence_against_a_candidate():
    """The rule the whole external package exists to protect."""
    assert all(not state.is_negative_evidence for state in VerificationState)


def test_only_a_readable_source_can_corroborate():
    assert VerificationState.PUBLIC.can_corroborate
    assert not VerificationState.PRIVATE_AUTH_REQUIRED.can_corroborate
    assert not VerificationState.NOT_FOUND.can_corroborate
    assert not VerificationState.UNABLE_TO_VERIFY.can_corroborate


# --------------------------------------------------------------------------
# Evaluator case 3: an unsupported claim, explained without accusation
# --------------------------------------------------------------------------


def _fit(level: EvidenceLevel, status: FitStatus) -> RequirementFit:
    return RequirementFit(
        requirement_id="R1",
        skill="Cloud Deployment",
        necessity=Necessity.REQUIRED,
        status=status,
        evidence_level=level,
        match_kind=MatchKind.EXACT,
    )


def test_an_unsupported_requirement_states_where_it_looked():
    why = explain(_fit(EvidenceLevel.E0, FitStatus.WEAK), None)
    assert "skills list" in why.searched
    assert "experience" in why.searched
    assert "external evidence" in why.searched


def test_an_unsupported_requirement_refuses_to_read_as_an_accusation():
    why = explain(_fit(EvidenceLevel.E0, FitStatus.WEAK), None)
    assert "does not prove" in why.caveat


def test_a_supported_requirement_still_limits_what_it_claims():
    why = explain(_fit(EvidenceLevel.E3, FitStatus.STRONG), None)
    assert "does not independently prove professional employment" in why.caveat


def test_evidence_found_in_a_document_is_quoted_not_summarised():
    fit = _fit(EvidenceLevel.E0, FitStatus.UNADDRESSED)
    assert explain(fit, None).quotes == []


# --------------------------------------------------------------------------
# Terminology across a whole requisition
# --------------------------------------------------------------------------


def _application(text: str) -> Application:
    return Application(
        id="A-TEST",
        candidate_name="Test Candidate",
        sections=[Section(kind=SectionKind.EXPERIENCE, text=text)],
    )


def test_a_candidate_writing_ecs_is_reported_as_related_not_equivalent():
    job = _junior_job(
        required_skills=[SkillSpec(skill="Container Orchestration")],
        preferred_skills=[],
        min_years_total=None,
    )
    findings = terminology_matrix(
        _application("Deployed services on AWS ECS with Fargate."), to_requisition(job)
    )
    entry = next(f for f in findings if f.required_skill == "Container Orchestration")
    assert entry.relationship in (Relationship.RELATED, Relationship.NOT_EQUIVALENT)
    assert entry.relationship.satisfies is False


def test_a_requirement_the_candidate_never_mentions_is_unknown_not_negative():
    """Saying nothing is different from saying something that does not match."""
    job = _junior_job(
        required_skills=[SkillSpec(skill="Container Orchestration")],
        preferred_skills=[],
        min_years_total=None,
    )
    findings = terminology_matrix(
        _application("Wrote data pipelines and reports."), to_requisition(job)
    )
    entry = next(f for f in findings if f.required_skill == "Container Orchestration")
    assert entry.relationship is Relationship.UNKNOWN
    assert entry.candidate_terms == []


def test_equivalent_wording_is_recognised_across_the_requisition():
    job = _junior_job(
        required_skills=[SkillSpec(skill="ROS 2")],
        preferred_skills=[],
        min_years_total=None,
    )
    findings = terminology_matrix(
        _application("Built Robot Operating System 2 navigation packages."),
        to_requisition(job),
    )
    entry = next(f for f in findings if f.required_skill == "ROS 2")
    assert entry.relationship in (Relationship.EXACT, Relationship.EQUIVALENT)
    assert entry.relationship.satisfies


# --------------------------------------------------------------------------
# The headline level is a band, never a fabricated percentage
# --------------------------------------------------------------------------


def _assessment(levels: list[tuple[EvidenceLevel, FitStatus]]) -> CandidateAssessment:
    return CandidateAssessment(
        application_id="A-TEST",
        candidate_name="Test Candidate",
        fits=[
            RequirementFit(
                requirement_id=f"R{index + 1}",
                skill=f"Skill {index + 1}",
                necessity=Necessity.REQUIRED,
                status=status,
                evidence_level=level,
                match_kind=MatchKind.EXACT,
            )
            for index, (level, status) in enumerate(levels)
        ],
    )


def test_every_required_area_supported_is_the_top_band():
    level, label = support_level(_assessment([(EvidenceLevel.E3, FitStatus.STRONG)] * 3))
    assert level == 4
    assert "Strongly" in label


def test_nothing_supported_is_the_bottom_band():
    level, _ = support_level(
        _assessment([(EvidenceLevel.E0, FitStatus.UNADDRESSED)] * 3)
    )
    assert level == 0


def test_a_requisition_with_no_required_criteria_produces_no_level():
    assert support_level(_assessment([])) == (0, "No required criteria")


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(LocalBackend(tmp_path), "test backend")


def test_a_job_round_trips_through_the_store(store):
    job = _junior_job()
    store.save_job(job)
    assert store.job(job.id).title == job.title


def test_candidates_only_see_published_requisitions(store):
    store.save_job(_junior_job())
    store.save_job(_junior_job(title="Published Role", status=JobStatus.PUBLISHED))

    visible = store.jobs(published_only=True)
    assert [job.title for job in visible] == ["Published Role"]


def test_applications_are_scoped_to_their_candidate(store):
    store.save_application(
        StoredApplication(job_id="job_1", candidate_uid="alice", resume_filename="a.pdf")
    )
    store.save_application(
        StoredApplication(job_id="job_1", candidate_uid="bob", resume_filename="b.pdf")
    )

    assert len(store.applications(candidate_uid="alice")) == 1
    assert len(store.applications(job_id="job_1")) == 2


def test_a_stored_user_keeps_its_role(store):
    store.save_user(User(uid="rec", name="Anita", role=Role.RECRUITER))
    assert store.user("rec").role is Role.RECRUITER


# --------------------------------------------------------------------------
# Server-side request safety
# --------------------------------------------------------------------------


def test_the_server_refuses_to_fetch_a_loopback_url():
    """A candidate-supplied URL must never reach an internal service."""
    from engine.documents import UnsafeUrl, assert_fetchable

    with pytest.raises(UnsafeUrl):
        assert_fetchable("http://127.0.0.1:8000/api/config")


def test_the_server_refuses_non_http_schemes():
    from engine.documents import UnsafeUrl, assert_fetchable

    with pytest.raises(UnsafeUrl):
        assert_fetchable("file:///etc/passwd")


def test_uploads_are_restricted_to_documents():
    from engine.documents import UploadRejected, validate_upload

    with pytest.raises(UploadRejected):
        validate_upload("payload.exe", b"MZ")


def test_an_empty_upload_is_rejected():
    from engine.documents import UploadRejected, validate_upload

    with pytest.raises(UploadRejected):
        validate_upload("resume.pdf", b"")
