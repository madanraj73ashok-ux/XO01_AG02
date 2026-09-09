"""Tests for talent-pool gap detection."""

from __future__ import annotations

from pathlib import Path

from engine.assessment import assess_pool
from engine.claims import load_applications
from engine.models import Necessity
from engine.poolgap import analyse_pool, gaps
from engine.requisition import load_requisition

DATA = Path(__file__).parent.parent / "data"


def _pool():
    requisition = load_requisition(DATA / "requisition.json")
    applications = load_applications(DATA / "applications")
    coverage = analyse_pool(assess_pool(applications, requisition), requisition)
    return coverage, applications


def test_reports_coverage_for_every_requirement() -> None:
    coverage, applications = _pool()

    assert len(coverage) == 7
    assert all(entry.total_candidates == len(applications) for entry in coverage)


def test_detects_the_requirement_nobody_satisfies() -> None:
    coverage, _ = _pool()

    skills = [entry.skill for entry in gaps(coverage)]

    # Cloud Deployment is the criterion the demo pool deliberately fails.
    assert "Cloud Deployment" in skills


def test_a_gap_means_zero_satisfying_candidates() -> None:
    coverage, _ = _pool()

    gap = next(entry for entry in coverage if entry.skill == "Cloud Deployment")

    assert gap.is_gap
    assert gap.satisfied_count == 0
    assert gap.coverage_ratio == 0.0
    assert gap.conclusion == "No applicant fully demonstrates the required experience."


def test_a_met_requirement_is_not_a_gap() -> None:
    coverage, _ = _pool()

    ros2 = next(entry for entry in coverage if entry.skill == "ROS 2")

    assert not ros2.is_gap
    assert "A-07" in ros2.satisfied


def test_near_misses_are_ranked_strongest_first() -> None:
    coverage, _ = _pool()

    gap = next(entry for entry in coverage if entry.skill == "Cloud Deployment")
    ranks = [miss.evidence_level.rank for miss in gap.near_misses]

    assert ranks == sorted(ranks, reverse=True)


def test_near_misses_describe_real_evidence_only() -> None:
    coverage, _ = _pool()

    gap = next(entry for entry in coverage if entry.skill == "Cloud Deployment")

    assert gap.near_misses
    # Every note says what the candidate actually has - no speculation.
    assert all(miss.note for miss in gap.near_misses)
    assert all(miss.application_id.startswith("A-") for miss in gap.near_misses)


def test_satisfied_requirement_lists_no_near_misses() -> None:
    coverage, _ = _pool()

    ros2 = next(entry for entry in coverage if entry.skill == "ROS 2")

    assert ros2.near_misses == []


def test_required_gaps_are_listed_before_preferred() -> None:
    coverage, _ = _pool()

    necessities = [entry.necessity for entry in gaps(coverage)]

    required = [i for i, n in enumerate(necessities) if n is Necessity.REQUIRED]
    preferred = [i for i, n in enumerate(necessities) if n is Necessity.PREFERRED]

    if required and preferred:
        assert max(required) < min(preferred)


def test_render_produces_the_reviewer_block() -> None:
    coverage, _ = _pool()

    rendered = next(
        entry for entry in coverage if entry.skill == "Cloud Deployment"
    ).render()

    assert "POOL GAP DETECTED" in rendered
    assert "Cloud Deployment" in rendered
    assert "Closest evidence:" in rendered
    assert "No applicant fully demonstrates" in rendered
