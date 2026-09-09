"""Tests for trade-off analysis and shortlisting.

The constraint under test: PS02 forbids collapsing fit into one opaque score.
These tests check that the module ranks without rating, and that a comparison
between two differently-strong candidates reports a trade-off rather than a
winner.
"""

from __future__ import annotations

from pathlib import Path

from engine.assessment import assess_pool
from engine.claims import load_applications
from engine.models import Dimension
from engine.requisition import load_requisition
from engine.tradeoffs import build_shortlist, compare

DATA = Path(__file__).parent.parent / "data"


def _assessments():
    requisition = load_requisition(DATA / "requisition.json")
    applications = load_applications(DATA / "applications")
    return assess_pool(applications, requisition)


def test_shortlist_covers_every_candidate() -> None:
    assessments = _assessments()

    shortlist = build_shortlist(assessments)

    assert len(shortlist) == len(assessments)
    assert [entry.rank for entry in shortlist] == list(range(1, len(shortlist) + 1))


def test_every_entry_reports_all_four_dimensions() -> None:
    shortlist = build_shortlist(_assessments())

    for entry in shortlist:
        assert {d.dimension for d in entry.dimensions} == set(Dimension)
        # Each axis carries its own explanation - no bare numbers.
        assert all(d.detail for d in entry.dimensions)


def test_entry_states_a_best_fit_and_a_tradeoff() -> None:
    top = build_shortlist(_assessments())[0]

    assert top.best_fit
    assert top.tradeoff


def test_ranking_is_by_required_coverage_first() -> None:
    shortlist = build_shortlist(_assessments())

    coverage = [entry.score_for(Dimension.REQUIRED_COVERAGE) for entry in shortlist]

    assert coverage == sorted(coverage, reverse=True)


def test_shortlist_entry_has_no_single_overall_score() -> None:
    # The guard against the thing PS02 forbids: no field aggregates the
    # dimensions into one rating.
    fields = set(build_shortlist(_assessments())[0].model_dump().keys())

    assert "score" not in fields
    assert "overall" not in fields
    assert "rating" not in fields


def test_comparison_reports_a_trade_off_not_a_winner() -> None:
    assessments = {a.application_id: a for a in _assessments()}

    result = compare(assessments["A-07"], assessments["A-03"])

    assert result.left_id == "A-07"
    assert result.right_id == "A-03"
    assert len(result.lines) == len(Dimension)
    assert result.verdict
    assert "winner" not in result.verdict.lower()


def test_identical_candidates_are_comparable_on_every_axis() -> None:
    assessments = {a.application_id: a for a in _assessments()}

    result = compare(assessments["A-07"], assessments["A-07"])

    assert all(line.stronger is None for line in result.lines)
    assert "comparable on every axis" in result.verdict


def test_claim_integrity_is_reported_separately_from_ability() -> None:
    shortlist = {e.application_id: e for e in build_shortlist(_assessments())}

    overclaimer = shortlist["A-07"]
    honest = shortlist["A-01"]

    # Both demonstrate the same core criteria, so their ability is comparable.
    assert overclaimer.score_for(Dimension.REQUIRED_COVERAGE) == honest.score_for(
        Dimension.REQUIRED_COVERAGE
    )
    # But A-07 asserts cloud expertise it cannot show, and only the integrity
    # axis records that - it is never folded into an overall rating.
    assert overclaimer.score_for(Dimension.CLAIM_INTEGRITY) < 1.0
    assert honest.score_for(Dimension.CLAIM_INTEGRITY) == 1.0
    assert overclaimer.risks
    assert not honest.risks
