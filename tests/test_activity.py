"""The activity log is the audit trail for both investigation stages.

Two things are pinned down here. First, the log records what happened including
the parts that did not work - an investigation that only logs its successes is
a sales pitch, not a record. Second, the live stream is explicitly a lossy view
of a lossless log, and says so when it drops.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.activity import ActivityEvent, ActivityLog, Outcome, Stage
from engine.provenance import SourceKind, SourceRef, now_utc, sha256_of


def _ref() -> SourceRef:
    return SourceRef(
        kind=SourceKind.HTTP_RESPONSE,
        locator="https://api.github.com/repos/example/demo",
        content_hash=sha256_of(b"body"),
        url="https://api.github.com/repos/example/demo",
        retrieved_at=now_utc(),
    )


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def test_emit_returns_the_event_it_recorded(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.INGESTION,
        action="ocr_page",
        subject="A-01.pdf p.1",
        outcome=Outcome.SUCCEEDED,
        detail="18 lines recognised",
    )

    assert isinstance(event, ActivityEvent)
    assert event.action == "ocr_page"
    assert event.outcome is Outcome.SUCCEEDED


def test_events_are_numbered_in_the_order_they_happened(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    first = log.emit(
        stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.STARTED
    )
    second = log.emit(
        stage=Stage.INGESTION, action="b", subject="s", outcome=Outcome.SUCCEEDED
    )

    assert first.sequence == 1
    assert second.sequence == 2


def test_event_timestamps_are_timezone_aware(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.STARTED
    )
    assert event.at.tzinfo is not None


def test_failures_are_recorded_as_events(tmp_path):
    """An investigation that logs only its successes is not a record."""
    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.INGESTION,
        action="ocr_page",
        subject="A-04.pdf p.3",
        outcome=Outcome.FAILED,
        detail="extractor raised: image could not be decoded",
    )

    assert event.outcome is Outcome.FAILED
    assert log.events()[-1].outcome is Outcome.FAILED


def test_inconclusive_is_distinct_from_failed(tmp_path):
    """Not being able to check something is not the same as it going wrong.

    This is the R2 rule showing up in the log's own vocabulary: an
    UNABLE_TO_VERIFY fetch is inconclusive, and collapsing it into `FAILED`
    would let the portal read as if the candidate were at fault.
    """
    assert Outcome.INCONCLUSIVE is not Outcome.FAILED

    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.EXTERNAL,
        action="fetch_repository",
        subject="example/demo",
        outcome=Outcome.INCONCLUSIVE,
        detail="unauthenticated request cannot distinguish private from missing",
    )

    assert event.outcome is Outcome.INCONCLUSIVE


def test_an_event_can_cite_the_artefact_it_came_from(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.EXTERNAL,
        action="fetch_repository",
        subject="example/demo",
        outcome=Outcome.SUCCEEDED,
        source=_ref(),
    )

    assert event.source is not None
    assert event.source.content_hash == sha256_of(b"body")


def test_an_event_cannot_be_mutated_after_recording(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    event = log.emit(
        stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.STARTED
    )

    with pytest.raises(ValidationError):
        event.outcome = Outcome.SUCCEEDED


def test_the_log_exposes_no_update_or_delete(tmp_path):
    """Append-only is enforced by the absence of any other verb."""
    log = ActivityLog(tmp_path / "events.jsonl")
    for forbidden in ("update", "delete", "remove", "clear", "truncate"):
        assert not hasattr(log, forbidden)


# --------------------------------------------------------------------------
# Persistence and reading
# --------------------------------------------------------------------------


def test_events_persist_across_a_reopen(tmp_path):
    path = tmp_path / "events.jsonl"
    first = ActivityLog(path)
    first.emit(
        stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED
    )
    first.emit(
        stage=Stage.EXTERNAL, action="b", subject="s", outcome=Outcome.INCONCLUSIVE
    )

    reopened = ActivityLog(path)
    assert len(reopened.events()) == 2
    assert reopened.events()[1].outcome is Outcome.INCONCLUSIVE


def test_sequence_continues_after_a_reopen(tmp_path):
    """Restarting must not restart the numbering and overwrite history."""
    path = tmp_path / "events.jsonl"
    ActivityLog(path).emit(
        stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED
    )

    resumed = ActivityLog(path)
    later = resumed.emit(
        stage=Stage.INGESTION, action="b", subject="s", outcome=Outcome.SUCCEEDED
    )
    assert later.sequence == 2


def test_events_can_be_filtered_by_stage(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    log.emit(stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED)
    log.emit(stage=Stage.EXTERNAL, action="b", subject="s", outcome=Outcome.SUCCEEDED)
    log.emit(stage=Stage.EXTERNAL, action="c", subject="s", outcome=Outcome.SUCCEEDED)

    assert len(log.events(stage=Stage.EXTERNAL)) == 2


def test_events_can_be_read_from_a_sequence_onward(tmp_path):
    """The portal reconnects by asking for everything after what it has."""
    log = ActivityLog(tmp_path / "events.jsonl")
    for index in range(5):
        log.emit(
            stage=Stage.INGESTION,
            action=f"step-{index}",
            subject="s",
            outcome=Outcome.SUCCEEDED,
        )

    later = log.events(after=3)
    assert [event.sequence for event in later] == [4, 5]


def test_an_in_memory_log_records_without_a_file(tmp_path):
    """Dry runs should not have to write to disk to observe behaviour."""
    log = ActivityLog(None)
    log.emit(stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED)
    assert len(log.events()) == 1


# --------------------------------------------------------------------------
# Live fan-out
# --------------------------------------------------------------------------


def test_a_subscriber_receives_events_emitted_after_it_subscribes(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    with log.subscribe() as stream:
        log.emit(
            stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED
        )
        assert stream.get(timeout=1).action == "a"


def test_a_subscriber_does_not_receive_events_from_before_it_subscribed(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    log.emit(
        stage=Stage.INGESTION, action="earlier", subject="s", outcome=Outcome.SUCCEEDED
    )

    with log.subscribe() as stream:
        log.emit(
            stage=Stage.INGESTION,
            action="later",
            subject="s",
            outcome=Outcome.SUCCEEDED,
        )
        assert stream.get(timeout=1).action == "later"


def test_unsubscribing_stops_delivery(tmp_path):
    log = ActivityLog(tmp_path / "events.jsonl")
    with log.subscribe():
        pass

    log.emit(stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED)
    assert log.subscriber_count == 0


def test_a_full_subscriber_queue_never_blocks_the_emitter(tmp_path):
    """The stream is a lossy view of a lossless log, and must never stall it."""
    log = ActivityLog(tmp_path / "events.jsonl")

    with log.subscribe(maxsize=2) as stream:
        for index in range(10):
            log.emit(
                stage=Stage.INGESTION,
                action=f"step-{index}",
                subject="s",
                outcome=Outcome.SUCCEEDED,
            )

        assert stream.dropped > 0

    # The durable log kept every single one.
    assert len(log.events()) == 10


def test_a_dropping_subscriber_reports_how_many_it_missed(tmp_path):
    """A viewer that silently skipped events would misrepresent the run."""
    log = ActivityLog(tmp_path / "events.jsonl")

    with log.subscribe(maxsize=1) as stream:
        for index in range(6):
            log.emit(
                stage=Stage.INGESTION,
                action=f"step-{index}",
                subject="s",
                outcome=Outcome.SUCCEEDED,
            )
        assert stream.dropped == 5


def test_a_closed_subscriber_cannot_break_the_emitter(tmp_path):
    """One broken viewer must not stop the investigation being recorded."""
    log = ActivityLog(tmp_path / "events.jsonl")

    with log.subscribe(maxsize=1) as stream:
        stream.close()
        log.emit(
            stage=Stage.INGESTION, action="a", subject="s", outcome=Outcome.SUCCEEDED
        )

    assert len(log.events()) == 1
