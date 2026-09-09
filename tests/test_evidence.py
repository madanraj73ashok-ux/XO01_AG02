"""Tests for evidence grading.

The load-bearing case is the last one: a claim of "expert" that the evidence
does not carry must not be graded as though it were proven.
"""

from __future__ import annotations

from pathlib import Path

from engine.claims import extract_claims, load_application
from engine.evidence import grade_claims, grade_skill
from engine.models import Claim, ClaimStrength, EvidenceLevel, SectionKind

DATA = Path(__file__).parent.parent / "data" / "applications"


def _claim(
    section: SectionKind,
    text: str,
    strength: ClaimStrength = ClaimStrength.UNSPECIFIED,
    skill: str = "ROS 2",
) -> Claim:
    return Claim(
        skill=skill,
        surface_form=skill.casefold(),
        strength=strength,
        section=section,
        source_text=text,
    )


def test_cover_note_assertion_alone_is_e0() -> None:
    # A candidate vouching for themselves is the claim, not evidence for it.
    assessment = grade_skill(
        "Cloud Deployment",
        [
            _claim(
                SectionKind.COVER_NOTE,
                "I am an expert in AWS.",
                ClaimStrength.EXPERT,
                "Cloud Deployment",
            )
        ],
    )

    assert assessment.evidence_level is EvidenceLevel.E0
    assert not assessment.is_supported
    assert assessment.supporting == []


def test_skills_listing_alone_is_e1() -> None:
    assessment = grade_skill("ROS 2", [_claim(SectionKind.SKILLS, "Python, ROS 2")])

    assert assessment.evidence_level is EvidenceLevel.E1


def test_coursework_is_e1() -> None:
    assessment = grade_skill(
        "ROS 2", [_claim(SectionKind.EDUCATION, "Coursework included Robotics.")]
    )

    assert assessment.evidence_level is EvidenceLevel.E1


def test_project_is_e2() -> None:
    assessment = grade_skill(
        "ROS 2",
        [_claim(SectionKind.PROJECTS, "Built a ROS 2 navigation stack.")],
    )

    assert assessment.evidence_level is EvidenceLevel.E2


def test_professional_work_is_e3() -> None:
    assessment = grade_skill(
        "ROS 2",
        [_claim(SectionKind.EXPERIENCE, "Maintained ROS 2 nodes at work.")],
    )

    assert assessment.evidence_level is EvidenceLevel.E3


def test_corroborated_professional_work_is_e4() -> None:
    # Professional use, echoed in a project, describing what was implemented.
    assessment = grade_skill(
        "ROS 2",
        [
            _claim(SectionKind.EXPERIENCE, "Developed ROS 2 Humble nodes."),
            _claim(SectionKind.PROJECTS, "Built a robot running ROS 2 Humble."),
        ],
    )

    assert assessment.evidence_level is EvidenceLevel.E4


def test_professional_mention_without_detail_stays_e3() -> None:
    # Named in two sections but never described as work done.
    assessment = grade_skill(
        "ROS 2",
        [
            _claim(SectionKind.EXPERIENCE, "ROS 2."),
            _claim(SectionKind.SKILLS, "ROS 2"),
        ],
    )

    assert assessment.evidence_level is EvidenceLevel.E3


def test_grade_carries_reasons_a_recruiter_can_check() -> None:
    assessment = grade_skill(
        "ROS 2",
        [_claim(SectionKind.EXPERIENCE, "Maintained ROS 2 nodes at work.")],
    )

    assert assessment.reasons
    assert any("professional work" in reason for reason in assessment.reasons)


def test_evidence_quotes_real_source_text() -> None:
    sentence = "Built a ROS 2 navigation stack."
    assessment = grade_skill("ROS 2", [_claim(SectionKind.PROJECTS, sentence)])

    assert assessment.supporting[0].source_text == sentence


def test_expert_claim_without_support_is_flagged_as_overclaimed() -> None:
    assessment = grade_skill(
        "Cloud Deployment",
        [
            _claim(
                SectionKind.COVER_NOTE,
                "I am an expert in AWS.",
                ClaimStrength.EXPERT,
                "Cloud Deployment",
            ),
            _claim(SectionKind.SKILLS, "AWS", skill="Cloud Deployment"),
        ],
    )

    assert assessment.claimed_strength is ClaimStrength.EXPERT
    assert assessment.evidence_level is EvidenceLevel.E1
    assert assessment.is_overclaimed


def test_modest_claim_with_strong_evidence_is_not_overclaimed() -> None:
    # The mirror case: under-claimed but well evidenced.
    assessment = grade_skill(
        "ROS 2",
        [
            _claim(
                SectionKind.EXPERIENCE,
                "Developed ROS 2 nodes.",
                ClaimStrength.PROFICIENT,
            ),
            _claim(SectionKind.PROJECTS, "Built a ROS 2 robot."),
        ],
    )

    assert assessment.evidence_level is EvidenceLevel.E4
    assert not assessment.is_overclaimed


def test_hero_candidate_overclaims_cloud_but_not_ros2() -> None:
    # End to end on the real demo application.
    application = load_application(DATA / "A-07.json")
    assessments = {a.skill: a for a in grade_claims(extract_claims(application))}

    cloud = assessments["Cloud Deployment"]
    ros2 = assessments["ROS 2"]

    assert cloud.claimed_strength is ClaimStrength.EXPERT
    assert cloud.evidence_level.rank <= EvidenceLevel.E1.rank
    assert cloud.is_overclaimed

    assert ros2.evidence_level is EvidenceLevel.E4
    assert not ros2.is_overclaimed
