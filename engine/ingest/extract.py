"""Extractors: the only place raw text enters the system.

Two engines, and the difference between them is never blurred:

  `PdfTextLayerExtractor` reads characters the PDF already contains. It is
  exact, and it reports no confidence because nothing was recognised.

  `PaddleOcrExtractor` recognises characters from an image of the page. It is
  approximate, and it reports the confidence it measured for every line.

Which one read a page is recorded on that page. A document is allowed to be
read by both - a scanned appendix bound onto a digital resume genuinely is -
and calling either of them merely "extracted" would throw away the one fact a
reviewer most needs when a quote looks wrong.

Failure is reported, never substituted. If OCR cannot run, the page comes back
with `OCR_UNAVAILABLE` and no lines. It does not quietly fall through to a
different engine and present the result as though the intended one had worked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

import fitz  # PyMuPDF
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# On Windows the worker must not try to attach to a console: under a server
# process there is not one to attach to, and the attempt hangs the child.
_SPAWN_FLAGS: dict[str, int] = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if hasattr(subprocess, "CREATE_NO_WINDOW")
    else {}
)

from engine.ingest.layers import (
    ExtractorName,
    PageStatus,
    RawDocument,
    RawLine,
    RawPage,
)
from engine.provenance import BoundingBox, sha256_of

# Rasterisation resolution for OCR. 200 DPI is the usual floor for reliable
# small-text recognition; below it, confidence drops sharply on 9pt body text.
DEFAULT_OCR_DPI = 200

# PDF user space is 72 units to the inch. OCR reports pixels at the DPI we
# rasterised at, so every OCR box is scaled into points - the same space the
# text-layer boxes already use. This is a unit conversion of a measured value,
# not an estimate, and `dpi` is recorded on the page so the original pixel
# coordinates stay recoverable.
POINTS_PER_INCH = 72.0


class ExtractionUnavailable(RuntimeError):
    """An extractor could not run at all, as distinct from finding nothing."""


class PageExtractor(Protocol):
    """What the reader needs from any engine that can read a page."""

    name: ExtractorName

    def read_page(self, page: fitz.Page, page_number: int) -> list[RawLine]: ...


class PdfTextLayerExtractor:
    """Reads the characters a PDF already carries.

    Reports no confidence, because there is no recognition step to be
    confident about. `RawLine` rejects a confidence from this extractor
    outright, so the omission cannot be undone by a careless caller.
    """

    name = ExtractorName.PDF_TEXT_LAYER

    def read_page(self, page: fitz.Page, page_number: int) -> list[RawLine]:
        lines: list[RawLine] = []

        for block in page.get_text("dict").get("blocks", []):
            for entry in block.get("lines", []):
                text = "".join(span.get("text", "") for span in entry.get("spans", []))
                if not text.strip():
                    continue

                x0, y0, x1, y1 = entry["bbox"]
                if x1 <= x0 or y1 <= y0:
                    continue

                lines.append(
                    RawLine(
                        id=f"p{page_number}-l{len(lines) + 1:03d}",
                        page_number=page_number,
                        bbox=BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0),
                        text=text,
                        extractor=self.name,
                    )
                )

        return lines


class PaddleOcrExtractor:
    """Recognises text from page images, in a subprocess.

    PaddleOCR runs out-of-process deliberately. In this environment it
    intermittently segfaults during `predict`, and a native crash inside the
    API server would take the server down mid-request rather than failing one
    page. Isolated, a crash becomes a non-zero exit code that this class turns
    into `ExtractionUnavailable`, and the page is honestly recorded as
    unreadable.

    One worker handles a whole document, so the models load once per document
    rather than once per page.
    """

    name = ExtractorName.PADDLEOCR

    def __init__(
        self,
        *,
        dpi: int = DEFAULT_OCR_DPI,
        lang: str = "en",
        timeout: float = 600.0,
    ) -> None:
        self.dpi = dpi
        self.lang = lang
        self.timeout = timeout

    def read_document(
        self, path: Path, pages: list[int] | None = None
    ) -> dict[int, list[RawLine]]:
        """OCR the requested pages, returning raw lines keyed by page number."""
        command = [
            sys.executable,
            "-m",
            "tools.ocr_worker",
            str(path),
            "--dpi",
            str(self.dpi),
            "--lang",
            self.lang,
        ]
        if pages:
            command += ["--pages", ",".join(str(number) for number in pages)]

        environment = dict(os.environ)
        environment.setdefault("PYTHONPATH", str(PROJECT_ROOT))

        try:
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                # Detach stdin explicitly. Spawned from a server thread the
                # child would otherwise inherit the parent's console handle and
                # can block forever waiting on a stream nobody writes to.
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
                env=environment,
                check=False,
                **_SPAWN_FLAGS,
            )
        except subprocess.TimeoutExpired as error:
            raise ExtractionUnavailable(
                f"the OCR worker did not finish within {self.timeout:g}s"
            ) from error

        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
            tail = detail[-1] if detail else "no diagnostic output"
            raise ExtractionUnavailable(
                f"the OCR worker exited with code {completed.returncode} "
                f"({tail}); the page was not read"
            )

        try:
            payload = json.loads(completed.stdout.decode("utf-8", "replace"))
        except json.JSONDecodeError as error:
            raise ExtractionUnavailable(
                f"the OCR worker returned output that could not be parsed: {error}"
            ) from error

        scale = POINTS_PER_INCH / max(payload.get("dpi", self.dpi), 1)
        recognised: dict[int, list[RawLine]] = {}

        for entry in payload.get("pages", []):
            number = int(entry["page_number"])
            lines: list[RawLine] = []
            for item in entry.get("lines", []):
                box = _bbox_from_polygon(item.get("poly"), scale)
                if box is None:
                    # A recognised string with no usable box cannot be cited to
                    # a place on the page, so it is not admitted as
                    # provenance-bearing text.
                    continue
                lines.append(
                    RawLine(
                        id=f"p{number}-l{len(lines) + 1:03d}",
                        page_number=number,
                        bbox=box,
                        text=str(item.get("text", "")),
                        extractor=self.name,
                        confidence=item.get("score"),
                    )
                )
            recognised[number] = lines

        return recognised


class DocumentReader:
    """Reads a whole document, choosing an engine per page.

    The text layer is preferred where it exists: it is exact, and running OCR
    over text we can already read verbatim would substitute an approximation
    for a certainty. Pages with no text layer go to OCR. Each page records
    which of the two actually ran.
    """

    def __init__(
        self,
        *,
        ocr: PaddleOcrExtractor | None = None,
        text_layer: PdfTextLayerExtractor | None = None,
    ) -> None:
        self.ocr = ocr if ocr is not None else PaddleOcrExtractor()
        self.text_layer = (
            text_layer if text_layer is not None else PdfTextLayerExtractor()
        )

    def read(self, path: str | Path, *, document_id: str | None = None) -> RawDocument:
        """Read a whole document: text layer first, then one OCR pass.

        The two passes are separate because OCR is expensive and, here, fragile.
        Reading the text layer for every page first means the OCR worker is only
        started when some page actually needs it, and is started exactly once.
        """
        source = Path(path)
        payload = source.read_bytes()

        geometry: dict[int, tuple[float, float]] = {}
        embedded: dict[int, list[RawLine]] = {}
        failures: dict[int, str] = {}

        with fitz.open(source) as document:
            for number, page in enumerate(document, start=1):
                geometry[number] = (page.rect.width, page.rect.height)
                try:
                    lines = self.text_layer.read_page(page, number)
                except Exception as error:
                    failures[number] = str(error)
                    continue
                if lines:
                    embedded[number] = lines

        needs_ocr = [
            number
            for number in sorted(geometry)
            if number not in embedded and number not in failures
        ]

        recognised: dict[int, list[RawLine]] = {}
        ocr_error = ""
        if needs_ocr:
            try:
                recognised = self.ocr.read_document(source, needs_ocr)
            except ExtractionUnavailable as error:
                ocr_error = str(error)
            except Exception as error:  # pragma: no cover - defensive
                ocr_error = f"the OCR pass failed unexpectedly: {error}"

            # A recogniser that returns nothing at all, for every page it was
            # given, has far more likely failed than read a document that was
            # blank throughout. Reporting that as "no text detected" would make
            # a broken engine indistinguishable from an empty page, so the
            # inference is stated rather than quietly resolved the wrong way.
            if not ocr_error and not any(recognised.get(n) for n in needs_ocr):
                ocr_error = (
                    "the OCR engine returned no text for any of the "
                    f"{len(needs_ocr)} page(s) it was given; that more likely "
                    "means recognition failed than that every page was blank, "
                    "so the pages are reported as unread rather than empty"
                )

        pages = [
            self._assemble(
                number,
                geometry[number],
                embedded=embedded.get(number),
                recognised=recognised.get(number),
                failure=failures.get(number),
                ocr_attempted=number in needs_ocr,
                ocr_error=ocr_error,
            )
            for number in sorted(geometry)
        ]

        return RawDocument(
            document_id=document_id or source.stem,
            filename=source.name,
            source_hash=sha256_of(payload),
            pages=pages,
        )

    def _assemble(
        self,
        number: int,
        size: tuple[float, float],
        *,
        embedded: list[RawLine] | None,
        recognised: list[RawLine] | None,
        failure: str | None,
        ocr_attempted: bool,
        ocr_error: str,
    ) -> RawPage:
        """Turn one page's outcome into a `RawPage` that states what happened."""
        width, height = size

        if failure is not None:
            return RawPage(
                page_number=number,
                width=width,
                height=height,
                extractor=ExtractorName.PDF_TEXT_LAYER,
                status=PageStatus.EXTRACTION_FAILED,
                lines=[],
                note=failure,
            )

        if embedded:
            return RawPage(
                page_number=number,
                width=width,
                height=height,
                extractor=ExtractorName.PDF_TEXT_LAYER,
                status=PageStatus.TEXT_EXTRACTED,
                lines=embedded,
            )

        if not ocr_attempted:
            return RawPage(
                page_number=number,
                width=width,
                height=height,
                extractor=ExtractorName.PDF_TEXT_LAYER,
                status=PageStatus.NO_TEXT_DETECTED,
                lines=[],
                note="the page carries no embedded text",
            )

        if ocr_error:
            return RawPage(
                page_number=number,
                width=width,
                height=height,
                extractor=ExtractorName.PADDLEOCR,
                status=PageStatus.OCR_UNAVAILABLE,
                lines=[],
                dpi=self.ocr.dpi,
                note=ocr_error,
            )

        if not recognised:
            return RawPage(
                page_number=number,
                width=width,
                height=height,
                extractor=ExtractorName.PADDLEOCR,
                status=PageStatus.NO_TEXT_DETECTED,
                lines=[],
                dpi=self.ocr.dpi,
                note="no text regions were detected on this page",
            )

        return RawPage(
            page_number=number,
            width=width,
            height=height,
            extractor=ExtractorName.PADDLEOCR,
            status=PageStatus.TEXT_EXTRACTED,
            lines=recognised,
            dpi=self.ocr.dpi,
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _bbox_from_polygon(polygon, scale: float) -> BoundingBox | None:
    """The axis-aligned box around a recognition polygon, in PDF points.

    Returns None for a degenerate polygon rather than padding it to a valid
    size: a box that was not measured is not a box.
    """
    points = np.asarray(polygon, dtype=float).reshape(-1, 2)
    if points.size == 0:
        return None

    x0, y0 = points[:, 0].min() * scale, points[:, 1].min() * scale
    x1, y1 = points[:, 0].max() * scale, points[:, 1].max() * scale
    if x1 <= x0 or y1 <= y0:
        return None

    return BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
