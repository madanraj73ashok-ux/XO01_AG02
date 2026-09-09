"""Tests for claim extraction."""

from __future__ import annotations

from pathlib import Path

from engine.claims import extract_claims, load_application, load_applications
from engine.models import Application, ClaimStrength, Section, SectionKind

DATA = Path(__file__).parent.parent / "data" / "applications"


def _application(*sections: Section) -> Application:
    return Application(id="A-TEST", candidate_name="Test", sections=list(sections))


def test_extracts_a_skill_from_a_skills_list() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="Python, ROS 2, Git")
    )

    skills = {claim.skill for claim in extract_claims(application)}

    assert {"Python", "ROS 2", "Version Control"} <= skills


def test_records_claimed_strength_without_treating_it_as_evidence() -> None:
    application = _application(
        Section(kind=SectionKind.COVER_NOTE, text="I am an expert in AWS.")
    )

    claims = extract_claims(application)
    aws = next(c for c in claims if c.skill == "Cloud Deployment")

    assert aws.strength is ClaimStrength.EXPERT
    # The claim carries its own wording as provenance, nothing more.
    assert "expert in AWS" in aws.source_text


def test_unstated_strength_is_unspecified() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="Python, ROS 2")
    )

    assert all(
        claim.strength is ClaimStrength.UNSPECIFIED
        for claim in extract_claims(application)
    )


def test_claim_keeps_the_section_it_came_from() -> None:
    application = _application(
        Section(
            kind=SectionKind.PROJECTS,
            text="Built a ROS 2 navigation stack for a mobile robot.",
        )
    )

    claim = next(c for c in extract_claims(application) if c.skill == "ROS 2")

    assert claim.section is SectionKind.PROJECTS


def test_does_not_match_a_skill_inside_a_longer_word() -> None:
    # 'ml' must not match inside 'html'.
    application = _application(
        Section(kind=SectionKind.SKILLS, text="HTML and CSS")
    )

    assert [c for c in extract_claims(application) if c.skill == "Machine Learning"] == []


def test_loads_the_demo_applications() -> None:
    applications = load_applications(DATA)

    assert [a.id for a in applications] == ["A-03", "A-07"]


def test_hero_candidate_claims_cloud_only_in_the_cover_note() -> None:
    # A-07 asserts AWS expertise but never demonstrates it anywhere else.
    # This is the case the evidence grader must catch next.
    application = load_application(DATA / "A-07.json")
    claims = extract_claims(application)

    cloud_sections = {
        claim.section for claim in claims if claim.skill == "Cloud Deployment"
    }

    assert SectionKind.COVER_NOTE in cloud_sections
    assert SectionKind.EXPERIENCE not in cloud_sections
    assert SectionKind.PROJECTS not in cloud_sections
