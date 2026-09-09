"""Tests for the terminology equivalence engine.

The negative cases matter as much as the positive ones: PS02 requires that
equivalent wording is accepted *and* that merely adjacent technology is not.
"""

from __future__ import annotations

from engine.equivalence import canonical_for, classify, normalize
from engine.models import MatchKind


def test_normalizes_punctuation_and_case() -> None:
    assert normalize("ROS-2") == normalize("ros 2") == "ros 2"


def test_exact_wording_is_an_exact_match() -> None:
    match = classify("ROS 2", "ROS 2")

    assert match.kind is MatchKind.EXACT
    assert match.kind.satisfies_requirement


def test_different_wording_for_the_same_skill_is_equivalent() -> None:
    # The core PS02 requirement: don't penalize different phrasing.
    match = classify("Robot Operating System 2", "ROS 2")

    assert match.kind is MatchKind.EQUIVALENT
    assert match.kind.satisfies_requirement
    assert "equivalent" in match.explanation


def test_opencv_is_equivalent_to_computer_vision() -> None:
    assert classify("OpenCV", "Computer Vision").kind is MatchKind.EQUIVALENT


def test_git_is_equivalent_to_version_control() -> None:
    assert classify("Git", "Version Control").kind is MatchKind.EQUIVALENT


def test_arduino_is_related_but_does_not_satisfy_ros2() -> None:
    # The negative case a judge will probe: adjacent, not interchangeable.
    match = classify("Arduino", "ROS 2")

    assert match.kind is MatchKind.RELATED
    assert not match.kind.satisfies_requirement
    assert "not the same capability" in match.explanation


def test_docker_is_related_but_does_not_satisfy_cloud_deployment() -> None:
    match = classify("Docker", "Cloud Deployment")

    assert match.kind is MatchKind.RELATED
    assert not match.kind.satisfies_requirement


def test_unrelated_skill_returns_no_match() -> None:
    match = classify("Photoshop", "ROS 2")

    assert match.kind is MatchKind.NONE
    assert not match.kind.satisfies_requirement


def test_canonical_lookup_resolves_aliases() -> None:
    assert canonical_for("ros2 humble") == "ROS 2"
    assert canonical_for("amazon web services") == "Cloud Deployment"
    assert canonical_for("something unrecognised") is None
