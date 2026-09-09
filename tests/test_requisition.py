"""Tests for requisition parsing and conflict detection."""

from __future__ import annotations

from engine.models import (
    ConflictKind,
    Necessity,
    Requirement,
    Requisition,
    Seniority,
)
from engine.requisition import detect_conflicts


def _requisition(seniority: Seniority, *requirements: Requirement) -> Requisition:
    return Requisition(
        id="REQ-TEST",
        title="Test Role",
        seniority=seniority,
        requirements=list(requirements),
    )


def test_flags_experience_beyond_junior_ceiling() -> None:
    # Arrange - the PS02 example: a must-have skill demanding senior-level
    # experience on a role advertised as junior.
    requisition = _requisition(
        Seniority.JUNIOR,
        Requirement(
            id="R1", skill="ROS 2", necessity=Necessity.REQUIRED, min_years=5
        ),
    )

    # Act
    conflicts = detect_conflicts(requisition)

    # Assert
    assert len(conflicts) == 1
    assert conflicts[0].kind is ConflictKind.SENIORITY_EXPERIENCE_MISMATCH
    assert conflicts[0].requirement_ids == ["R1"]


def test_accepts_experience_within_the_level() -> None:
    requisition = _requisition(
        Seniority.JUNIOR,
        Requirement(
            id="R1", skill="Python", necessity=Necessity.REQUIRED, min_years=1
        ),
    )

    assert detect_conflicts(requisition) == []


def test_unspecified_experience_is_not_a_conflict() -> None:
    requisition = _requisition(
        Seniority.JUNIOR,
        Requirement(id="R1", skill="Robotics", necessity=Necessity.REQUIRED),
    )

    assert detect_conflicts(requisition) == []


def test_same_threshold_is_allowed_at_a_higher_level() -> None:
    # 5 years is a conflict for a junior role but fine for a mid-level one.
    requisition = _requisition(
        Seniority.MID,
        Requirement(
            id="R1", skill="ROS 2", necessity=Necessity.REQUIRED, min_years=5
        ),
    )

    assert detect_conflicts(requisition) == []


def test_flags_a_skill_listed_twice() -> None:
    requisition = _requisition(
        Seniority.JUNIOR,
        Requirement(id="R1", skill="Python", necessity=Necessity.REQUIRED),
        Requirement(id="R2", skill="python", necessity=Necessity.PREFERRED),
    )

    conflicts = detect_conflicts(requisition)

    assert len(conflicts) == 1
    assert conflicts[0].kind is ConflictKind.DUPLICATE_REQUIREMENT
    assert set(conflicts[0].requirement_ids) == {"R1", "R2"}


def test_splits_required_and_preferred() -> None:
    requisition = _requisition(
        Seniority.JUNIOR,
        Requirement(id="R1", skill="Python", necessity=Necessity.REQUIRED),
        Requirement(id="R2", skill="Computer Vision", necessity=Necessity.PREFERRED),
    )

    assert [r.id for r in requisition.required] == ["R1"]
    assert [r.id for r in requisition.preferred] == ["R2"]
