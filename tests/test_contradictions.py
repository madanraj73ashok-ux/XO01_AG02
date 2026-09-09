"""Tests for contradiction detection (Surprise Challenge 01).

The binding constraint under test: the agent must never invent evidence, and
every flag must reference the text that caused it.
"""

from __future__ import annotations

from pathlib import Path

from engine.claims import load_application
from engine.contradictions import find_contradictions
from engine.models import Application, ContradictionKind, Section, SectionKind

DATA = Path(__file__).parent.parent / "data" / "applications"


def _application(*sections: Section) -> Application:
    return Application(id="A-TEST", candidate_name="Test", sections=list(sections))


def test_detects_the_worked_example() -> None:
    # The exact case from the challenge brief: 5 years claimed, one year of
    # internship listed, degree running 2021-2025.
    application = _application(
        Section(kind=SectionKind.SKILLS, text="5 years of Python experience."),
        Section(
            kind=SectionKind.EXPERIENCE,
            text="Software Engineering Intern, 2024 - 2025.",
        ),
        Section(kind=SectionKind.EDUCATION, text="B.Tech, 2021 - 2025."),
    )

    duration = [
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.DURATION_UNSUPPORTED
    ]

    assert len(duration) == 1
    assert duration[0].assessment == "Claim insufficiently supported."
    assert duration[0].confidence_effect == "Reduced"
    assert duration[0].flag == "CONTRADICTORY / UNSUPPORTED CLAIM"


def test_flag_quotes_the_claim_and_the_conflicting_dates() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="5 years of Python experience."),
        Section(
            kind=SectionKind.EXPERIENCE,
            text="Software Engineering Intern, 2024 - 2025.",
        ),
        Section(kind=SectionKind.EDUCATION, text="B.Tech, 2021 - 2025."),
    )

    conflict = next(
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.DURATION_UNSUPPORTED
    )

    # The claim itself is quoted, not paraphrased.
    assert "5 years of Python experience" in conflict.claim_text
    # And the dates that caused the flag are quoted too.
    quoted = [item.source_text for item in conflict.counter_evidence]
    assert any("2024 - 2025" in text for text in quoted)
    assert any("2021 - 2025" in text for text in quoted)


def test_honest_duration_claim_is_not_flagged() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="2 years of Python experience."),
        Section(kind=SectionKind.EXPERIENCE, text="Software Engineer, 2023 - 2025."),
    )

    assert [
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.DURATION_UNSUPPORTED
    ] == []


def test_rounding_is_tolerated() -> None:
    # 18 months of work described as "2 years" is rounding, not a contradiction.
    application = _application(
        Section(kind=SectionKind.SKILLS, text="2 years of experience."),
        Section(kind=SectionKind.EXPERIENCE, text="Engineer, Jan 2024 - Jun 2025."),
    )

    assert [
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.DURATION_UNSUPPORTED
    ] == []


def test_duration_claim_with_no_dated_experience_is_timeline_implausible() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="4 years of Python experience."),
        Section(kind=SectionKind.EXPERIENCE, text="No professional experience yet."),
    )

    conflict = next(
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.TIMELINE_IMPLAUSIBLE
    )

    assert "No dated professional experience" in conflict.evidence_note
    # Absence is reported as absence - no invented counter-evidence.
    assert conflict.counter_evidence == []


def test_cover_note_only_claim_is_flagged_without_inventing_evidence() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="Python, Git"),
        Section(
            kind=SectionKind.COVER_NOTE,
            text="I am an expert in cloud deployment.",
        ),
    )

    conflict = next(
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.COVER_NOTE_ONLY
    )

    assert conflict.subject == "Cloud Deployment"
    assert "expert in cloud deployment" in conflict.claim_text
    assert "appears only in the cover note" in conflict.evidence_note
    assert conflict.counter_evidence == []


def test_overclaimed_expertise_quotes_its_support() -> None:
    application = _application(
        Section(kind=SectionKind.SKILLS, text="Machine Learning"),
        Section(
            kind=SectionKind.COVER_NOTE,
            text="I have advanced machine learning skills.",
        ),
    )

    conflict = next(
        c
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.EXPERTISE_UNSUPPORTED
    )

    assert conflict.counter_evidence
    assert all(item.source_text for item in conflict.counter_evidence)


def test_well_evidenced_claim_raises_no_expertise_conflict() -> None:
    application = load_application(DATA / "A-07.json")

    subjects = {
        c.subject
        for c in find_contradictions(application)
        if c.kind is ContradictionKind.EXPERTISE_UNSUPPORTED
    }

    # ROS 2 is claimed proficient and evidenced at E4 - no conflict there.
    assert "ROS 2" not in subjects


def test_render_produces_the_reviewer_block() -> None:
    application = load_application(DATA / "A-11.json")

    rendered = find_contradictions(application)[0].render()

    assert "Claim:" in rendered
    assert "Evidence:" in rendered
    assert "Assessment:" in rendered
    assert "Confidence: Reduced" in rendered
    assert "CONTRADICTORY / UNSUPPORTED CLAIM" in rendered
