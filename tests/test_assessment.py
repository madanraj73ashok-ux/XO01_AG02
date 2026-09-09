"""Tests for per-requirement assessment."""

from __future__ import annotations

from pathlib import Path

from engine.assessment import assess_candidate
from engine.claims import load_application
from engine.models import (
    FitStatus,
    MatchKind,
    Necessity,
    Requirement,
    Requisition,
    Seniority,
)
from engine.requisition import load_requisition

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


def _requisition(*requirements: Requirement) -> Requisition:
    return Requisition(
        id="REQ-TEST",
        title="Test Role",
        seniority=Seniority.JUNIOR,
        requirements=list(requirements),
    )


def _hero():
    return load_application(DATA / "applications" / "A-07.json")


def _coursework_candidate():
    return load_application(DATA / "applications" / "A-03.json")


def test_professional_evidence_reads_as_strong() -> None:
    assessment = assess_candidate(
        _hero(),
        _requisition(
            Requirement(id="R1", skill="ROS 2", necessity=Necessity.REQUIRED)
        ),
    )

    fit = assessment.fits[0]

    assert fit.status is FitStatus.STRONG
    assert fit.is_met


def test_claim_without_support_does_not_read_as_strong() -> None:
    # A-07 claims "expert in AWS" but never demonstrates it.
    assessment = assess_candidate(
        _hero(),
        _requisition(
            Requirement(
                id="R1", skill="Cloud Deployment", necessity=Necessity.REQUIRED
            )
        ),
    )

    fit = assessment.fits[0]

    assert fit.status is FitStatus.WEAK
    assert not fit.is_met
    assert fit.is_overclaimed


def test_equivalent_terminology_is_matched_not_penalised() -> None:
    # The candidate writes OpenCV; the requisition says Computer Vision.
    assessment = assess_candidate(
        _hero(),
        _requisition(
            Requirement(
                id="R1", skill="Computer Vision", necessity=Necessity.REQUIRED
            )
        ),
    )

    fit = assessment.fits[0]

    assert fit.status is not FitStatus.UNADDRESSED
    assert fit.match_kind.satisfies_requirement


def test_unmentioned_requirement_is_unaddressed_not_weak() -> None:
    assessment = assess_candidate(
        _hero(),
        _requisition(
            Requirement(id="R1", skill="Deep Learning", necessity=Necessity.REQUIRED)
        ),
    )

    fit = assessment.fits[0]

    assert fit.status is FitStatus.UNADDRESSED
    assert not fit.is_met


def test_adjacent_technology_is_reported_but_does_not_satisfy() -> None:
    # A-03 has Arduino, never ROS 2. Arduino must not count, but must be shown.
    assessment = assess_candidate(
        _coursework_candidate(),
        _requisition(
            Requirement(id="R1", skill="ROS 2", necessity=Necessity.REQUIRED)
        ),
    )

    fit = assessment.fits[0]

    assert fit.status is FitStatus.UNADDRESSED
    assert not fit.is_met
    assert "arduino" in fit.closest_evidence
    assert fit.match_kind is MatchKind.RELATED
    assert any("not the same capability" in reason for reason in fit.reasons)


def test_every_fit_carries_reasons() -> None:
    assessment = assess_candidate(_hero(), load_requisition(DATA / "requisition.json"))

    assert all(fit.reasons for fit in assessment.fits)


def test_summary_is_a_breakdown_not_a_single_score() -> None:
    assessment = assess_candidate(_hero(), load_requisition(DATA / "requisition.json"))

    summary = assessment.summary

    assert "required areas strong" in summary
    # Every required criterion that is not met must be named, not hidden
    # inside a count. A-07's cloud claim is weak AND overclaimed.
    assert "Cloud Deployment" in summary
    assert "unsupported claim" in summary


def test_required_and_preferred_are_kept_separate() -> None:
    assessment = assess_candidate(_hero(), load_requisition(DATA / "requisition.json"))

    assert len(assessment.required_fits) == 5
    assert len(assessment.fits) == 7
