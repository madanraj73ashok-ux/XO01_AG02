"""The three ingestion layers and the contract that binds them.

The contract is one sentence: **every derived item must be traceable to a raw
line on a numbered page**. It is enforced by a validator on `IngestedDocument`
rather than by discipline, so a pipeline that loses track of where a sentence
came from fails loudly at construction instead of quietly presenting an
untraceable quote to a recruiter.

Two smaller decisions follow from the same principle:

  A text-layer extraction has `confidence = None`, not `1.0`. PyMuPDF reports
  no confidence because there is no recognition step to be confident about.
  Writing 1.0 there would be inventing a measurement.

  A page that produced nothing gets a `PageStatus` saying which kind of nothing
  it was. "No text was detected on this page" and "OCR was not available" are
  different facts, and neither of them is "this page was empty".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.provenance import BoundingBox, SourceKind, SourceRef

# Below this, a recognised line is flagged for review rather than trusted.
# Chosen to make lines visible in the UI, never to drop them.
LOW_CONFIDENCE_THRESHOLD = 0.80


class ExtractorName(str, Enum):
    """Which engine actually read a page.

    Recorded per page, never per document: a scanned appendix bound onto a
    digital resume is genuinely read by two different engines, and flattening
    that would misdescribe both.
    """

    PADDLEOCR = "paddleocr"
    PDF_TEXT_LAYER = "pdf_text_layer"

    @property
    def label(self) -> str:
        return _EXTRACTOR_LABELS[self]

    @property
    def reports_confidence(self) -> bool:
        """Whether this extractor measures how sure it is.

        Only recognition does. A text layer is read, not recognised, so there
        is no confidence to report and none is fabricated.
        """
        return self is ExtractorName.PADDLEOCR


_EXTRACTOR_LABELS: dict[ExtractorName, str] = {
    ExtractorName.PADDLEOCR: "PaddleOCR (recognised)",
    ExtractorName.PDF_TEXT_LAYER: "PDF text layer (embedded)",
}


class PageStatus(str, Enum):
    """What happened when this page was read.

    The three non-success values are deliberately distinct. Collapsing them
    into "empty" would let a missing OCR install look identical to a genuinely
    blank page, which is the kind of silent substitution R1 forbids.
    """

    TEXT_EXTRACTED = "text_extracted"
    NO_TEXT_DETECTED = "no_text_detected"
    OCR_UNAVAILABLE = "ocr_unavailable"
    EXTRACTION_FAILED = "extraction_failed"

    @property
    def label(self) -> str:
        return _PAGE_STATUS_LABELS[self]

    @property
    def yielded_text(self) -> bool:
        return self is PageStatus.TEXT_EXTRACTED


_PAGE_STATUS_LABELS: dict[PageStatus, str] = {
    PageStatus.TEXT_EXTRACTED: "Text extracted",
    PageStatus.NO_TEXT_DETECTED: "No text detected on this page",
    PageStatus.OCR_UNAVAILABLE: "OCR engine unavailable - page not read",
    PageStatus.EXTRACTION_FAILED: "Extraction failed",
}


# --------------------------------------------------------------------------
# Raw layer - what the machine saw
# --------------------------------------------------------------------------


class RawLine(BaseModel):
    """One line of text exactly as an extractor reported it.

    Frozen. This layer is the ground truth every later claim resolves back to;
    if it can be edited, nothing above it means anything.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    page_number: int = Field(ge=1)
    bbox: BoundingBox
    text: str
    extractor: ExtractorName
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _confidence_only_where_it_was_measured(self) -> RawLine:
        if self.confidence is not None and not self.extractor.reports_confidence:
            raise ValueError(
                f"{self.extractor.value} reports no confidence; recording one "
                "would invent a measurement that was never taken"
            )
        return self

    @property
    def is_low_confidence(self) -> bool:
        """True only where a confidence was actually measured and is low.

        An unmeasured line is not a low-confidence line. Returning True here
        for text-layer output would flag perfectly reliable text as doubtful.
        """
        if self.confidence is None:
            return False
        return self.confidence < LOW_CONFIDENCE_THRESHOLD


class RawPage(BaseModel):
    """One page as read, including the pages that yielded nothing."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    extractor: ExtractorName
    status: PageStatus
    lines: list[RawLine] = Field(default_factory=list)
    dpi: int | None = None
    note: str = ""

    @model_validator(mode="after")
    def _status_must_match_the_content(self) -> RawPage:
        if self.status.yielded_text and not self.lines:
            raise ValueError(
                f"page {self.page_number} claims text was extracted but "
                "carries no lines"
            )
        if not self.status.yielded_text and self.lines:
            raise ValueError(
                f"page {self.page_number} carries lines but its status says no "
                f"text was produced ({self.status.value})"
            )
        return self

    @property
    def low_confidence_lines(self) -> list[RawLine]:
        return [line for line in self.lines if line.is_low_confidence]


class RawDocument(BaseModel):
    """Every page of one source file, as read."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    filename: str
    source_hash: str
    pages: list[RawPage] = Field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def extractors_used(self) -> list[ExtractorName]:
        """Distinct engines that read this document, in page order."""
        seen: list[ExtractorName] = []
        for page in self.pages:
            if page.extractor not in seen:
                seen.append(page.extractor)
        return seen

    def lines(self) -> list[RawLine]:
        return [line for page in self.pages for line in page.lines]


# --------------------------------------------------------------------------
# Normalized layer - cleaned, but still pointing back
# --------------------------------------------------------------------------


class NormalizedSpan(BaseModel):
    """A readable span of text and the raw lines it was built from.

    `raw_line_ids` is mandatory and non-empty. A normalized span that cannot
    name its sources is untraceable text, which this pipeline has no way to
    justify showing anyone.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    raw_line_ids: list[str] = Field(min_length=1)
    joined_hyphenation: bool = False
    low_confidence: bool = False


# --------------------------------------------------------------------------
# Derived layer - interpretation, always cited
# --------------------------------------------------------------------------


class DerivedKind(str, Enum):
    """What a derived item is claiming to be.

    `UNCLASSIFIED` exists so a block the rules could not place has somewhere
    honest to go. Guessing it into the nearest section would manufacture
    structure the document does not have.
    """

    SECTION = "section"
    CANDIDATE_NAME = "candidate_name"
    LINK = "link"
    UNCLASSIFIED = "unclassified"


class DerivedItem(BaseModel):
    """One interpreted element, with the rule that produced it.

    `basis` is required. Every derived item has to be able to answer "why do
    you think that", and the answer is stored next to the conclusion rather
    than reconstructed afterwards.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    kind: DerivedKind
    label: str
    text: str
    span_ids: list[str] = Field(min_length=1)
    basis: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


# --------------------------------------------------------------------------
# The whole record
# --------------------------------------------------------------------------


class IngestedDocument(BaseModel):
    """All three layers of one document, with the trace contract enforced.

    The validator is the point of this type. It refuses to construct a record
    in which a derived item cites a span that does not exist, or a span cites a
    raw line that does not exist. Either would produce a quote a reviewer could
    not follow back to a page, and an untraceable quote is exactly what this
    project exists not to produce.
    """

    document_id: str
    source_filename: str
    source_hash: str
    ingested_at: datetime
    raw: RawDocument
    normalized: list[NormalizedSpan] = Field(default_factory=list)
    derived: list[DerivedItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _every_citation_must_resolve(self) -> IngestedDocument:
        known_lines = {line.id for line in self.raw.lines()}
        for span in self.normalized:
            missing = [ref for ref in span.raw_line_ids if ref not in known_lines]
            if missing:
                raise ValueError(
                    f"normalized span {span.id} cites raw lines that do not "
                    f"exist: {', '.join(missing)}"
                )

        known_spans = {span.id for span in self.normalized}
        for item in self.derived:
            missing = [ref for ref in item.span_ids if ref not in known_spans]
            if missing:
                raise ValueError(
                    f"derived item {item.id} cites spans that do not exist: "
                    f"{', '.join(missing)}"
                )

        return self

    # ----------------------------------------------------------------
    # Resolution - walking the trace back down the layers
    # ----------------------------------------------------------------

    def raw_line(self, line_id: str) -> RawLine | None:
        return next((line for line in self.raw.lines() if line.id == line_id), None)

    def span(self, span_id: str) -> NormalizedSpan | None:
        return next((span for span in self.normalized if span.id == span_id), None)

    def item(self, item_id: str) -> DerivedItem | None:
        return next((item for item in self.derived if item.id == item_id), None)

    def raw_lines_for_span(self, span_id: str) -> list[RawLine]:
        span = self.span(span_id)
        if span is None:
            return []
        return [
            line
            for line in (self.raw_line(ref) for ref in span.raw_line_ids)
            if line is not None
        ]

    def raw_lines_for_item(self, item_id: str) -> list[RawLine]:
        """Every raw line behind one derived item, in document order."""
        item = self.item(item_id)
        if item is None:
            return []
        lines: list[RawLine] = []
        for span_id in item.span_ids:
            lines.extend(self.raw_lines_for_span(span_id))
        return lines

    def pages_for_item(self, item_id: str) -> list[int]:
        """Which pages a derived item physically came from."""
        return sorted({line.page_number for line in self.raw_lines_for_item(item_id)})

    def source_refs_for_item(self, item_id: str) -> list[SourceRef]:
        """Citable references for everything behind one derived item."""
        return [
            SourceRef(
                kind=SourceKind.DOCUMENT_PAGE,
                locator=f"{self.source_filename} p.{line.page_number}",
                content_hash=self.source_hash,
                document_id=self.document_id,
                page_number=line.page_number,
                bbox=line.bbox,
                extractor=line.extractor.value,
            )
            for line in self.raw_lines_for_item(item_id)
        ]

    # ----------------------------------------------------------------
    # Reporting
    # ----------------------------------------------------------------

    @property
    def unread_pages(self) -> list[RawPage]:
        """Pages that produced no text, whatever the reason.

        Surfaced rather than hidden: a document half of whose pages could not
        be read is a materially different input, and the reviewer is told.
        """
        return [page for page in self.raw.pages if not page.status.yielded_text]

    @property
    def low_confidence_lines(self) -> list[RawLine]:
        return [line for line in self.raw.lines() if line.is_low_confidence]
