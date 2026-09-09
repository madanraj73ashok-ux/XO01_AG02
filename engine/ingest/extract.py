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

from pathlib import Path
from typing import Protocol

import fitz  # PyMuPDF
import numpy as np

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
    """Recognises text from a rasterised image of the page.

    The engine is constructed lazily on first use: importing PaddleOCR pulls in
    Paddle and loads several models, which should not happen merely because
    something imported this module.
    """

    name = ExtractorName.PADDLEOCR

    def __init__(self, *, dpi: int = DEFAULT_OCR_DPI, lang: str = "en") -> None:
        self.dpi = dpi
        self.lang = lang
        self._engine = None

    def engine(self):
        """Build the recognition pipeline, once.

        `enable_mkldnn=False` is required, not tuning. With Paddle 3.3.1 the
        oneDNN CPU path raises `ConvertPirAttribute2RuntimeAttribute not
        support [pir::ArrayAttribute<pir::DoubleAttribute>]` during predict,
        which kills the run outright. Orientation classification and unwarping
        are off because these are flat, upright pages and both stages cost
        time without changing the result.
        """
        if self._engine is not None:
            return self._engine

        try:
            from paddleocr import PaddleOCR
        except Exception as error:  # pragma: no cover - environment dependent
            raise ExtractionUnavailable(
                f"PaddleOCR could not be imported: {error}"
            ) from error

        try:
            self._engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
                lang=self.lang,
            )
        except Exception as error:  # pragma: no cover - environment dependent
            raise ExtractionUnavailable(
                f"PaddleOCR could not be initialised: {error}"
            ) from error

        return self._engine

    def read_page(self, page: fitz.Page, page_number: int) -> list[RawLine]:
        engine = self.engine()
        image = _rasterise(page, self.dpi)
        scale = POINTS_PER_INCH / self.dpi

        try:
            prediction = engine.predict(input=image)
        except Exception as error:
            raise ExtractionUnavailable(
                f"PaddleOCR failed while reading page {page_number}: {error}"
            ) from error

        if not prediction:
            return []

        result = prediction[0]
        texts = result.get("rec_texts") or []
        scores = result.get("rec_scores") or []
        polygons = result.get("rec_polys")
        if polygons is None:
            polygons = result.get("dt_polys") or []

        lines: list[RawLine] = []
        for index, text in enumerate(texts):
            if not str(text).strip():
                continue
            if index >= len(polygons):
                # A recognised string with no box cannot be cited to a place on
                # the page, so it is not admitted as provenance-bearing text.
                continue

            box = _bbox_from_polygon(polygons[index], scale)
            if box is None:
                continue

            lines.append(
                RawLine(
                    id=f"p{page_number}-l{len(lines) + 1:03d}",
                    page_number=page_number,
                    bbox=box,
                    text=str(text),
                    extractor=self.name,
                    confidence=float(scores[index]) if index < len(scores) else None,
                )
            )

        return lines


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
        source = Path(path)
        payload = source.read_bytes()

        with fitz.open(source) as document:
            pages = [
                self._read_page(page, number)
                for number, page in enumerate(document, start=1)
            ]

        return RawDocument(
            document_id=document_id or source.stem,
            filename=source.name,
            source_hash=sha256_of(payload),
            pages=pages,
        )

    def _read_page(self, page: fitz.Page, number: int) -> RawPage:
        """Read one page, reporting precisely how it went."""
        try:
            lines = self.text_layer.read_page(page, number)
        except Exception as error:
            return _failed_page(page, number, ExtractorName.PDF_TEXT_LAYER, str(error))

        if lines:
            return RawPage(
                page_number=number,
                width=page.rect.width,
                height=page.rect.height,
                extractor=ExtractorName.PDF_TEXT_LAYER,
                status=PageStatus.TEXT_EXTRACTED,
                lines=lines,
            )

        # No embedded text. This is where OCR earns its place.
        try:
            recognised = self.ocr.read_page(page, number)
        except ExtractionUnavailable as error:
            return RawPage(
                page_number=number,
                width=page.rect.width,
                height=page.rect.height,
                extractor=ExtractorName.PADDLEOCR,
                status=PageStatus.OCR_UNAVAILABLE,
                lines=[],
                dpi=self.ocr.dpi,
                note=str(error),
            )
        except Exception as error:
            return _failed_page(page, number, ExtractorName.PADDLEOCR, str(error))

        if not recognised:
            return RawPage(
                page_number=number,
                width=page.rect.width,
                height=page.rect.height,
                extractor=ExtractorName.PADDLEOCR,
                status=PageStatus.NO_TEXT_DETECTED,
                lines=[],
                dpi=self.ocr.dpi,
                note="no text regions were detected on this page",
            )

        return RawPage(
            page_number=number,
            width=page.rect.width,
            height=page.rect.height,
            extractor=ExtractorName.PADDLEOCR,
            status=PageStatus.TEXT_EXTRACTED,
            lines=recognised,
            dpi=self.ocr.dpi,
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _failed_page(
    page: fitz.Page, number: int, extractor: ExtractorName, reason: str
) -> RawPage:
    return RawPage(
        page_number=number,
        width=page.rect.width,
        height=page.rect.height,
        extractor=extractor,
        status=PageStatus.EXTRACTION_FAILED,
        lines=[],
        note=reason,
    )


def _rasterise(page: fitz.Page, dpi: int) -> np.ndarray:
    """Render a page to the BGR array PaddleOCR expects."""
    pixmap = page.get_pixmap(dpi=dpi)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    if pixmap.n == 4:
        image = image[:, :, :3]
    return np.ascontiguousarray(image[:, :, ::-1])


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
