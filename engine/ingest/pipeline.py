"""Stage A orchestration: document in, assessable application out.

This module owns the order of the three layers and the narration of them. It
adds no interpretation of its own; each layer is asked for its output and the
result is recorded, including the pages that could not be read.

The one judgement it makes is when to refuse. `build_application` will not
manufacture a candidate name from a filename, so a document whose name could
not be located yields no `Application` and an explicit reason instead. A
screening record attached to the wrong person is worse than a missing one.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from engine.activity import ActivityLog, Outcome, Stage
from engine.ingest.derive import derive_items, is_heading
from engine.ingest.extract import DocumentReader
from engine.ingest.layers import (
    DerivedKind,
    IngestedDocument,
    PageStatus,
    RawDocument,
    RawPage,
)
from engine.ingest.normalize import normalize_document
from engine.models import Application, Section, SectionKind
from engine.provenance import SourceKind, SourceRef, now_utc

# The order the screening engine expects to read an application in. Derived
# sections arrive in document order, which varies between candidates.
SECTION_ORDER: tuple[SectionKind, ...] = (
    SectionKind.SKILLS,
    SectionKind.EXPERIENCE,
    SectionKind.PROJECTS,
    SectionKind.EDUCATION,
    SectionKind.COVER_NOTE,
)

DOCUMENT_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"})


class CannotBuildApplication(RuntimeError):
    """The document was read, but cannot honestly become an application."""


class IngestionResult(BaseModel):
    """One document's ingest, and whether it produced an application.

    `blocked_reason` is populated instead of `application` when the pipeline
    refused. Carrying both fields means a caller cannot silently miss the
    refusal by reading a default-empty application.
    """

    document: IngestedDocument
    application: Application | None = None
    blocked_reason: str | None = None

    @property
    def produced_application(self) -> bool:
        return self.application is not None


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------


def ingest_document(
    path: str | Path,
    *,
    reader: DocumentReader | None = None,
    log: ActivityLog | None = None,
    document_id: str | None = None,
) -> IngestionResult:
    """Read one document through all three layers, narrating as it goes."""
    source = Path(path)
    reader = reader if reader is not None else DocumentReader()
    log = log if log is not None else ActivityLog(None)

    log.emit(
        stage=Stage.INGESTION,
        action="read_document",
        subject=source.name,
        outcome=Outcome.STARTED,
    )

    raw = reader.read(source, document_id=document_id)
    for page in raw.pages:
        _record_page(log, raw, page)

    spans = normalize_document(raw, is_heading=is_heading)
    log.emit(
        stage=Stage.INGESTION,
        action="normalize",
        subject=source.name,
        outcome=Outcome.SUCCEEDED,
        detail=(
            f"{len(spans)} spans built from {len(raw.lines())} raw lines; "
            f"{sum(1 for span in spans if span.low_confidence)} carry a "
            "low-confidence line"
        ),
    )

    items = derive_items(raw, spans)
    counts = {
        kind: sum(1 for item in items if item.kind is kind) for kind in DerivedKind
    }
    log.emit(
        stage=Stage.INGESTION,
        action="derive",
        subject=source.name,
        outcome=Outcome.SUCCEEDED,
        detail=(
            f"{counts[DerivedKind.SECTION]} sections, "
            f"{counts[DerivedKind.LINK]} links, "
            f"{counts[DerivedKind.UNCLASSIFIED]} unclassified blocks"
        ),
    )

    document = IngestedDocument(
        document_id=raw.document_id,
        source_filename=raw.filename,
        source_hash=raw.source_hash,
        ingested_at=now_utc(),
        raw=raw,
        normalized=spans,
        derived=items,
    )

    try:
        application = build_application(document)
    except CannotBuildApplication as refusal:
        log.emit(
            stage=Stage.INGESTION,
            action="build_application",
            subject=source.name,
            outcome=Outcome.FAILED,
            detail=str(refusal),
        )
        return IngestionResult(document=document, blocked_reason=str(refusal))

    log.emit(
        stage=Stage.INGESTION,
        action="build_application",
        subject=f"{application.id} ({application.candidate_name})",
        outcome=Outcome.SUCCEEDED,
        detail=f"{len(application.sections)} sections available for screening",
    )
    return IngestionResult(document=document, application=application)


def _record_page(log: ActivityLog, raw: RawDocument, page: RawPage) -> None:
    """Narrate one page, success or otherwise.

    A page that produced nothing is `INCONCLUSIVE`, not `FAILED`: the document
    may simply carry a blank page, and nothing about it reflects on the
    candidate. Only a genuine extractor error is a failure.
    """
    reference = SourceRef(
        kind=SourceKind.DOCUMENT_PAGE,
        locator=f"{raw.filename} p.{page.page_number}",
        content_hash=raw.source_hash,
        document_id=raw.document_id,
        page_number=page.page_number,
        extractor=page.extractor.value,
    )

    if page.status.yielded_text:
        measured = [line for line in page.lines if line.confidence is not None]
        detail = f"{len(page.lines)} lines via {page.extractor.label}"
        if measured:
            average = sum(line.confidence for line in measured) / len(measured)
            detail += f"; mean confidence {average:.3f}"
        if page.low_confidence_lines:
            detail += (
                f"; {len(page.low_confidence_lines)} lines below the confidence "
                "threshold, kept and flagged"
            )
        outcome = Outcome.SUCCEEDED
    else:
        detail = page.note or page.status.label
        outcome = (
            Outcome.FAILED
            if page.status is PageStatus.EXTRACTION_FAILED
            else Outcome.INCONCLUSIVE
        )

    log.emit(
        stage=Stage.INGESTION,
        action="read_page",
        subject=f"{raw.filename} p.{page.page_number}",
        outcome=outcome,
        detail=detail,
        source=reference,
    )


# --------------------------------------------------------------------------
# Application construction
# --------------------------------------------------------------------------


def build_application(document: IngestedDocument) -> Application:
    """Turn a read document into the shape the screening engine consumes.

    Refuses rather than guesses. Without a located name there is no honest way
    to say whose application this is, and without any recognised section there
    is nothing for the evidence grader to read.
    """
    names = [
        item for item in document.derived if item.kind is DerivedKind.CANDIDATE_NAME
    ]
    if not names:
        raise CannotBuildApplication(
            f"no candidate name could be located in {document.source_filename}; "
            "the pipeline will not substitute the filename for a person"
        )

    sections = {
        item.label: item.text
        for item in document.derived
        if item.kind is DerivedKind.SECTION
    }
    if not sections:
        raise CannotBuildApplication(
            "no recognised section headings were found in "
            f"{document.source_filename}; there is nothing to assess"
        )

    return Application(
        id=document.document_id,
        candidate_name=names[0].text,
        sections=[
            Section(kind=kind, text=sections[kind.value])
            for kind in SECTION_ORDER
            if kind.value in sections
        ],
    )


# --------------------------------------------------------------------------
# Batch
# --------------------------------------------------------------------------


def ingest_directory(
    directory: str | Path,
    *,
    reader: DocumentReader | None = None,
    log: ActivityLog | None = None,
    output: str | Path | None = None,
) -> list[IngestionResult]:
    """Ingest every document in a directory, in filename order."""
    root = Path(directory)
    reader = reader if reader is not None else DocumentReader()

    results: list[IngestionResult] = []
    for source in sorted(root.iterdir()):
        if source.suffix.lower() not in DOCUMENT_SUFFIXES:
            continue

        result = ingest_document(source, reader=reader, log=log)
        results.append(result)

        if output is not None:
            save(result.document, output)

    return results


def save(document: IngestedDocument, directory: str | Path) -> Path:
    """Write the full three-layer record so a reviewer can audit it later."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{document.document_id}.json"
    path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return path


def load(path: str | Path) -> IngestedDocument:
    """Read back a stored ingest record, revalidating the trace contract."""
    return IngestedDocument.model_validate_json(Path(path).read_text(encoding="utf-8"))
