"""The investigation activity log.

Both stages narrate themselves here: every page read, every URL fetched, every
step that did not work. The portal renders this log, so what a reviewer watches
is the actual record of the investigation rather than a summary written after
the fact.

Two decisions carry most of the weight:

  Failure is recorded, not swallowed. An investigation that logs only its
  successes is a sales pitch. A page that yielded no text and a repository that
  could not be reached are both events.

  `INCONCLUSIVE` is a first-class outcome, separate from `FAILED`. This is R2
  surfacing in the log's own vocabulary: not being able to check something is
  not the same as something going wrong, and neither is evidence against a
  candidate. Collapsing the two would make the portal read as an accusation.

The durable log is lossless; the live stream deliberately is not. A slow viewer
drops events rather than stalling the investigation, and reports how many it
dropped so it can never quietly show an incomplete picture.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, ConfigDict, Field

from engine.provenance import SourceRef, now_utc


class Stage(str, Enum):
    """Which part of the investigation produced an event."""

    INGESTION = "ingestion"
    EXTERNAL = "external_evidence"
    ASSESSMENT = "assessment"

    @property
    def label(self) -> str:
        return _STAGE_LABELS[self]


_STAGE_LABELS: dict[Stage, str] = {
    Stage.INGESTION: "Document ingestion",
    Stage.EXTERNAL: "External evidence",
    Stage.ASSESSMENT: "Assessment",
}


class Outcome(str, Enum):
    """How a step ended.

    `INCONCLUSIVE` exists so that "we could not establish this" has somewhere
    to go that is neither success nor failure. A rate-limited GitHub call and a
    timed-out page fetch are inconclusive: they tell us about our own reach,
    not about the candidate.
    """

    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"

    @property
    def label(self) -> str:
        return _OUTCOME_LABELS[self]

    @property
    def is_about_the_candidate(self) -> bool:
        """Whether this outcome says anything at all about the applicant.

        Always False, including for `FAILED` and `INCONCLUSIVE`: those describe
        the system's own reach. Present so the portal cannot accidentally
        render a tooling problem as a finding.
        """
        return False


_OUTCOME_LABELS: dict[Outcome, str] = {
    Outcome.STARTED: "Started",
    Outcome.SUCCEEDED: "Succeeded",
    Outcome.FAILED: "Failed",
    Outcome.INCONCLUSIVE: "Could not establish",
    Outcome.SKIPPED: "Skipped",
}


class ActivityEvent(BaseModel):
    """One recorded step of an investigation.

    Frozen: the record of what happened is not revisable. `source` is optional
    because plenty of steps (starting a document, skipping a section) have no
    artefact behind them - but when a step *does* rest on an artefact, it cites
    it, so the portal can always offer the reviewer the underlying bytes.
    """

    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    at: datetime
    stage: Stage
    action: str
    subject: str
    outcome: Outcome
    detail: str = ""
    source: SourceRef | None = None


class EventStream:
    """A live, deliberately lossy view of the log for one viewer.

    Bounded on purpose. If a viewer cannot keep up, the investigation must not
    slow down to wait for it, so events are dropped and counted. `dropped` is
    part of the public surface precisely so the UI can say "you missed 12
    events, reload" instead of showing a gap it never mentions.
    """

    # Rebound per instance by ActivityLog.subscribe, so leaving a `with` block
    # detaches the viewer cleanly.
    _unsubscribe = None

    def __init__(self, maxsize: int = 512) -> None:
        self._queue: queue.Queue[ActivityEvent] = queue.Queue(maxsize=maxsize)
        self._closed = False
        self.dropped = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def offer(self, event: ActivityEvent) -> None:
        """Deliver if there is room; otherwise count the drop and move on."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1

    def get(self, timeout: float | None = None) -> ActivityEvent:
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> ActivityEvent:
        return self._queue.get_nowait()

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> EventStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
        if self._unsubscribe is not None:
            self._unsubscribe(self)


class ActivityLog:
    """Append-only record of an investigation, with live fan-out.

    There is no update, delete or clear method. As with the snapshot store,
    that absence is the guarantee rather than a comment asking callers to
    behave.
    """

    def __init__(self, path: str | Path | None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._subscribers: list[EventStream] = []
        self._events: list[ActivityEvent] = []

        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._events = self._load()

    # ----------------------------------------------------------------
    # Recording
    # ----------------------------------------------------------------

    def emit(
        self,
        *,
        stage: Stage,
        action: str,
        subject: str,
        outcome: Outcome,
        detail: str = "",
        source: SourceRef | None = None,
    ) -> ActivityEvent:
        """Record one step and hand it to every attached viewer."""
        with self._lock:
            event = ActivityEvent(
                sequence=len(self._events) + 1,
                at=now_utc(),
                stage=stage,
                action=action,
                subject=subject,
                outcome=outcome,
                detail=detail,
                source=source,
            )
            self._events.append(event)

            if self._path is not None:
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(event.model_dump_json() + "\n")

            subscribers = list(self._subscribers)

        # Outside the lock: a viewer must never be able to stall a recording.
        for subscriber in subscribers:
            subscriber.offer(event)

        return event

    # ----------------------------------------------------------------
    # Reading
    # ----------------------------------------------------------------

    def events(
        self,
        *,
        stage: Stage | None = None,
        after: int = 0,
        limit: int | None = None,
    ) -> list[ActivityEvent]:
        """Recorded events, oldest first.

        `after` is how the portal reconnects without re-rendering history it
        already holds: it asks for everything past the last sequence it saw.
        """
        with self._lock:
            selected = [
                event
                for event in self._events
                if event.sequence > after and (stage is None or event.stage is stage)
            ]

        if limit is not None:
            selected = selected[-limit:]
        return selected

    @property
    def last_sequence(self) -> int:
        with self._lock:
            return self._events[-1].sequence if self._events else 0

    # ----------------------------------------------------------------
    # Live fan-out
    # ----------------------------------------------------------------

    def subscribe(self, maxsize: int = 512) -> EventStream:
        """Attach a viewer. Usable directly or as a context manager."""
        stream = EventStream(maxsize=maxsize)
        stream._unsubscribe = self.unsubscribe
        with self._lock:
            self._subscribers.append(stream)
        return stream

    def unsubscribe(self, stream: EventStream) -> None:
        with self._lock:
            if stream in self._subscribers:
                self._subscribers.remove(stream)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # ----------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------

    def _load(self) -> list[ActivityEvent]:
        """Read an existing log so numbering continues instead of restarting.

        A restarted process that began again at sequence 1 would produce two
        different events sharing one id, quietly corrupting the audit trail.
        """
        assert self._path is not None
        if not self._path.exists():
            return []
        return [
            ActivityEvent.model_validate_json(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def default_activity_log() -> ActivityLog:
    """The log the application uses, so every module writes to one place."""
    root = Path(__file__).resolve().parent.parent / "data" / "activity"
    return ActivityLog(root / "events.jsonl")
