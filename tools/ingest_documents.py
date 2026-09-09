"""Run Stage A over a folder of documents.

Reports per document what was read and how, including the pages that produced
nothing. A run that quietly skipped an unreadable page would leave a reviewer
believing the whole application had been considered.

Run with:  python -m tools.ingest_documents
           python -m tools.ingest_documents --source data/source_documents
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.activity import ActivityLog, Stage
from engine.ingest.layers import ExtractorName
from engine.ingest.pipeline import IngestionResult, ingest_directory

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "data" / "source_documents"
DEFAULT_OUTPUT = ROOT / "data" / "ingested"
DEFAULT_LOG = ROOT / "data" / "activity" / "events.jsonl"


def describe(result: IngestionResult) -> str:
    """One line per document, naming the engine that actually read it."""
    document = result.document
    engines = "+".join(name.value for name in document.raw.extractors_used)
    unread = len(document.unread_pages)
    weak = len(document.low_confidence_lines)

    status = (
        result.application.candidate_name
        if result.produced_application
        else "NO APPLICATION"
    )

    parts = [
        f"{document.document_id:6s}",
        f"{document.raw.page_count}p",
        f"{len(document.raw.lines()):4d} lines",
        f"{engines:24s}",
        f"{len(document.normalized):3d} spans",
        status,
    ]
    if unread:
        parts.append(f"[{unread} page(s) unread]")
    if weak:
        parts.append(f"[{weak} low-confidence line(s)]")
    return "  ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage A document ingestion.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    arguments = parser.parse_args()

    if not arguments.source.exists():
        parser.error(
            f"{arguments.source} does not exist. Run "
            "'python -m tools.make_demo_pdfs' first, or point --source at your "
            "own documents."
        )

    log = ActivityLog(arguments.log)
    results = ingest_directory(arguments.source, log=log, output=arguments.output)

    for result in results:
        print(describe(result))

    ocr_pages = sum(
        1
        for result in results
        for page in result.document.raw.pages
        if page.extractor is ExtractorName.PADDLEOCR and page.status.yielded_text
    )
    blocked = [result for result in results if not result.produced_application]

    print(
        f"\n{len(results)} documents read; "
        f"{len(results) - len(blocked)} produced applications; "
        f"{ocr_pages} pages required OCR."
    )
    for result in blocked:
        print(f"  {result.document.document_id}: {result.blocked_reason}")

    print(
        f"\nRecords: {arguments.output}"
        f"\nActivity: {arguments.log} "
        f"({len(log.events(stage=Stage.INGESTION))} ingestion events)"
    )


if __name__ == "__main__":
    main()
