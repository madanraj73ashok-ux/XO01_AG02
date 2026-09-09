"""Stage A: the three layers and the trace contract between them.

The tests that matter most here are the refusals. It is easy to build a
pipeline that produces clean text; the hard part is guaranteeing that every
sentence it produces can still be pointed back at a numbered page, and that it
says so plainly when it cannot read something.

Real OCR is exercised separately and marked `slow`, so the default run stays
offline and fast exactly as the README promises.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.ingest.derive import derive_items, heading_kind
from engine.ingest.layers import (
    DerivedItem,
    DerivedKind,
    ExtractorName,
    IngestedDocument,
    NormalizedSpan,
    PageStatus,
    RawDocument,
    RawLine,
    RawPage,
)
from engine.ingest.normalize import normalize_document, normalize_text
from engine.models import SectionKind
from engine.provenance import BoundingBox, SourceKind, now_utc, sha256_of

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0
SOURCE_HASH = sha256_of(b"pretend pdf bytes")


def line(
    line_id: str,
    text: str,
    *,
    page_number: int = 1,
    y: float = 100.0,
    x: float = 56.0,
    height: float = 12.0,
    width: float = 300.0,
    extractor: ExtractorName = ExtractorName.PDF_TEXT_LAYER,
    confidence: float | None = None,
) -> RawLine:
    return RawLine(
        id=line_id,
        page_number=page_number,
        bbox=BoundingBox(x=x, y=y, width=width, height=height),
        text=text,
        extractor=extractor,
        confidence=confidence,
    )


def page(number: int, lines: list[RawLine]) -> RawPage:
    return RawPage(
        page_number=number,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        extractor=lines[0].extractor if lines else ExtractorName.PDF_TEXT_LAYER,
        status=PageStatus.TEXT_EXTRACTED if lines else PageStatus.NO_TEXT_DETECTED,
        lines=lines,
    )


def document(pages: list[RawPage], doc_id: str = "A-01") -> RawDocument:
    return RawDocument(
        document_id=doc_id,
        filename=f"{doc_id}.pdf",
        source_hash=SOURCE_HASH,
        pages=pages,
    )


# --------------------------------------------------------------------------
# Raw layer - honest about what was measured
# --------------------------------------------------------------------------


def test_text_layer_lines_carry_no_confidence():
    """PyMuPDF does not recognise, so it has no confidence to report."""
    assert ExtractorName.PDF_TEXT_LAYER.reports_confidence is False
    assert line("p1-l001", "Meera Krishnan").confidence is None


def test_a_text_layer_line_rejects_an_invented_confidence():
    """Writing 1.0 here would be recording a measurement never taken."""
    with pytest.raises(ValidationError):
        line("p1-l001", "text", extractor=ExtractorName.PDF_TEXT_LAYER, confidence=1.0)


def test_an_ocr_line_may_carry_the_confidence_it_measured():
    recognised = line(
        "p1-l001", "ROS 2", extractor=ExtractorName.PADDLEOCR, confidence=0.93
    )
    assert recognised.confidence == pytest.approx(0.93)


def test_an_unmeasured_line_is_not_a_low_confidence_line():
    """Absent confidence is not low confidence."""
    assert line("p1-l001", "text").is_low_confidence is False


def test_a_poorly_recognised_line_is_flagged_but_kept():
    """Dropping it silently would rewrite the candidate's document."""
    weak = line("p1-l001", "R0S 2", extractor=ExtractorName.PADDLEOCR, confidence=0.41)
    holder = page(1, [weak])

    assert weak.is_low_confidence is True
    assert weak in holder.lines
    assert holder.low_confidence_lines == [weak]


def test_a_page_claiming_text_must_actually_carry_lines():
    with pytest.raises(ValidationError):
        RawPage(
            page_number=1,
            width=PAGE_WIDTH,
            height=PAGE_HEIGHT,
            extractor=ExtractorName.PADDLEOCR,
            status=PageStatus.TEXT_EXTRACTED,
            lines=[],
        )


def test_a_page_with_lines_cannot_claim_nothing_was_read():
    with pytest.raises(ValidationError):
        RawPage(
            page_number=1,
            width=PAGE_WIDTH,
            height=PAGE_HEIGHT,
            extractor=ExtractorName.PADDLEOCR,
            status=PageStatus.OCR_UNAVAILABLE,
            lines=[line("p1-l001", "text", extractor=ExtractorName.PADDLEOCR)],
        )


def test_the_three_failure_statuses_stay_distinct():
    """A missing OCR install must never look like a blank page."""
    assert PageStatus.NO_TEXT_DETECTED is not PageStatus.OCR_UNAVAILABLE
    assert PageStatus.OCR_UNAVAILABLE is not PageStatus.EXTRACTION_FAILED
    assert all(
        status.yielded_text is False
        for status in (
            PageStatus.NO_TEXT_DETECTED,
            PageStatus.OCR_UNAVAILABLE,
            PageStatus.EXTRACTION_FAILED,
        )
    )


def test_a_document_reports_every_extractor_that_read_it():
    """A scan bound onto a digital resume is genuinely read two ways."""
    raw = document(
        [
            page(1, [line("p1-l001", "digital")]),
            page(
                2,
                [
                    line(
                        "p2-l001",
                        "scanned",
                        page_number=2,
                        extractor=ExtractorName.PADDLEOCR,
                        confidence=0.95,
                    )
                ],
            ),
        ]
    )

    assert raw.extractors_used == [
        ExtractorName.PDF_TEXT_LAYER,
        ExtractorName.PADDLEOCR,
    ]


# --------------------------------------------------------------------------
# The trace contract
# --------------------------------------------------------------------------


def _ingested(raw: RawDocument, spans, derived) -> IngestedDocument:
    return IngestedDocument(
        document_id=raw.document_id,
        source_filename=raw.filename,
        source_hash=raw.source_hash,
        ingested_at=now_utc(),
        raw=raw,
        normalized=spans,
        derived=derived,
    )


def test_a_span_citing_a_nonexistent_raw_line_is_rejected():
    raw = document([page(1, [line("p1-l001", "real line")])])
    span = NormalizedSpan(id="s001", text="real line", raw_line_ids=["p9-l999"])

    with pytest.raises(ValidationError):
        _ingested(raw, [span], [])


def test_a_derived_item_citing_a_nonexistent_span_is_rejected():
    raw = document([page(1, [line("p1-l001", "real line")])])
    span = NormalizedSpan(id="s001", text="real line", raw_line_ids=["p1-l001"])
    item = DerivedItem(
        id="d001",
        kind=DerivedKind.SECTION,
        label="skills",
        text="real line",
        span_ids=["s999"],
        basis="test",
        confidence=0.9,
    )

    with pytest.raises(ValidationError):
        _ingested(raw, [span], [item])


def test_a_span_must_cite_at_least_one_raw_line():
    with pytest.raises(ValidationError):
        NormalizedSpan(id="s001", text="untraceable", raw_line_ids=[])


def test_a_derived_item_must_state_its_basis():
    with pytest.raises(ValidationError):
        DerivedItem(
            id="d001",
            kind=DerivedKind.SECTION,
            label="skills",
            text="x",
            span_ids=["s001"],
            basis="",
            confidence=0.9,
        )


def test_a_derived_item_resolves_all_the_way_down_to_a_page():
    """The whole point of the three layers: text to span to line to page."""
    raw = document(
        [
            page(1, [line("p1-l001", "Developed ROS 2 nodes", y=200.0)]),
            page(
                2, [line("p2-l001", "for a warehouse robot.", page_number=2, y=100.0)]
            ),
        ]
    )
    span = NormalizedSpan(
        id="s001",
        text="Developed ROS 2 nodes for a warehouse robot.",
        raw_line_ids=["p1-l001", "p2-l001"],
    )
    item = DerivedItem(
        id="d001",
        kind=DerivedKind.SECTION,
        label="experience",
        text=span.text,
        span_ids=["s001"],
        basis="follows the heading 'Experience'",
        confidence=0.95,
    )
    ingested = _ingested(raw, [span], [item])

    assert ingested.pages_for_item("d001") == [1, 2]

    refs = ingested.source_refs_for_item("d001")
    assert [ref.page_number for ref in refs] == [1, 2]
    assert all(ref.kind is SourceKind.DOCUMENT_PAGE for ref in refs)
    assert all(ref.extractor == "pdf_text_layer" for ref in refs)
    assert all(ref.bbox is not None for ref in refs)


def test_unread_pages_are_reported_rather_than_hidden():
    raw = RawDocument(
        document_id="A-01",
        filename="A-01.pdf",
        source_hash=SOURCE_HASH,
        pages=[
            page(1, [line("p1-l001", "read fine")]),
            RawPage(
                page_number=2,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                extractor=ExtractorName.PADDLEOCR,
                status=PageStatus.NO_TEXT_DETECTED,
                lines=[],
                note="no text regions detected",
            ),
        ],
    )
    ingested = _ingested(raw, [], [])

    assert [p.page_number for p in ingested.unread_pages] == [2]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------


def test_normalize_text_collapses_whitespace_and_applies_nfkc():
    assert normalize_text("  ROS   2\n\tnodes ") == "ROS 2 nodes"
    assert normalize_text("ﬁle") == "file"


def test_wrapped_lines_join_into_one_span():
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Developed ROS 2 nodes for a", y=200.0),
                    line("p1-l002", "warehouse mobile robot.", y=214.0),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert len(spans) == 1
    assert spans[0].text == "Developed ROS 2 nodes for a warehouse mobile robot."
    assert spans[0].raw_line_ids == ["p1-l001", "p1-l002"]


def test_a_word_broken_across_a_line_break_is_rejoined():
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "autonomous navi-", y=200.0),
                    line("p1-l002", "gation stack", y=214.0),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert spans[0].text == "autonomous navigation stack"
    assert spans[0].joined_hyphenation is True


def test_a_large_vertical_gap_starts_a_new_span():
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Skills", y=200.0),
                    line("p1-l002", "Python, ROS 2", y=260.0),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert [span.text for span in spans] == ["Skills", "Python, ROS 2"]


def test_a_change_of_type_size_starts_a_new_span():
    """A 20pt name sits tight above a 9.5pt metadata line, but is not part of it.

    The gap test alone would merge them, which would attach text to the
    candidate's name that they never wrote there.
    """
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Meera Krishnan", y=60.0, height=20.0),
                    line("p1-l002", "Application A-01 REQ-2026-014", y=95.0),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert [span.text for span in spans] == [
        "Meera Krishnan",
        "Application A-01 REQ-2026-014",
    ]


def test_a_span_is_flagged_when_any_line_behind_it_was_poorly_recognised():
    raw = document(
        [
            page(
                1,
                [
                    line(
                        "p1-l001",
                        "Developed R0S 2",
                        y=200.0,
                        extractor=ExtractorName.PADDLEOCR,
                        confidence=0.42,
                    ),
                    line(
                        "p1-l002",
                        "nodes.",
                        y=214.0,
                        extractor=ExtractorName.PADDLEOCR,
                        confidence=0.99,
                    ),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert spans[0].low_confidence is True


def test_footer_furniture_is_separated_from_body_text():
    """A watermark must not be glued onto the last real paragraph."""
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Real content here.", y=700.0),
                    line("p1-l002", "SYNTHETIC DEMO DATA", y=800.0, height=8.0),
                ],
            )
        ]
    )
    spans = normalize_document(raw)

    assert [span.text for span in spans] == [
        "Real content here.",
        "SYNTHETIC DEMO DATA",
    ]


def test_normalization_is_deterministic():
    """Re-running an ingest must reproduce the trace, not a similar one."""
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Developed ROS 2 nodes for a", y=200.0),
                    line("p1-l002", "warehouse mobile robot.", y=214.0),
                ],
            )
        ]
    )
    assert normalize_document(raw) == normalize_document(raw)


# --------------------------------------------------------------------------
# Derivation
# --------------------------------------------------------------------------


def _resume_document() -> RawDocument:
    return document(
        [
            page(
                1,
                [
                    line("p1-l001", "Meera Krishnan", y=60.0, height=20.0),
                    line("p1-l002", "Skills", y=140.0),
                    line("p1-l003", "Python, ROS 2, Git", y=170.0),
                    line("p1-l004", "Experience", y=230.0),
                    line("p1-l005", "Developed ROS 2 nodes at", y=260.0),
                    line("p1-l006", "Tarang Automation.", y=274.0),
                    line("p1-l007", "See github.com/meerak/nav2-tuning", y=330.0),
                    line("p1-l008", "SYNTHETIC DEMO DATA", y=800.0, height=8.0),
                ],
            )
        ]
    )


def test_heading_vocabulary_matches_case_and_punctuation_insensitively():
    assert heading_kind("Experience") is SectionKind.EXPERIENCE
    assert heading_kind("WORK EXPERIENCE:") is SectionKind.EXPERIENCE
    assert heading_kind("Cover Note") is SectionKind.COVER_NOTE


def test_a_long_sentence_beginning_with_a_heading_word_is_not_a_heading():
    """Otherwise a real sentence would swallow the section it sits in."""
    assert heading_kind("Experience with distributed robotics systems at scale") is None


def test_sections_collect_the_spans_that_follow_their_heading():
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    sections = {item.label: item for item in items if item.kind is DerivedKind.SECTION}
    assert "skills" in sections
    assert "experience" in sections
    assert "Python, ROS 2, Git" in sections["skills"].text
    assert "Tarang Automation" in sections["experience"].text


def test_every_section_names_the_heading_that_produced_it():
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    for item in items:
        if item.kind is DerivedKind.SECTION:
            assert "follows the heading" in item.basis


def test_the_candidate_name_is_taken_from_the_top_of_page_one():
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    names = [item for item in items if item.kind is DerivedKind.CANDIDATE_NAME]
    assert len(names) == 1
    assert names[0].text == "Meera Krishnan"


def test_no_name_is_invented_when_the_document_does_not_offer_one():
    """An absent name is reported as absent, not filled in from the filename."""
    raw = document(
        [
            page(
                1,
                [
                    line(
                        "p1-l001",
                        "To whom it may concern, I write about the advertised role",
                        y=60.0,
                    )
                ],
            )
        ]
    )
    items = derive_items(raw, normalize_document(raw))

    assert not [item for item in items if item.kind is DerivedKind.CANDIDATE_NAME]


def test_github_links_are_extracted_for_stage_b():
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    links = [item for item in items if item.kind is DerivedKind.LINK]
    assert any(item.text == "meerak/nav2-tuning" for item in links)
    assert any(item.label == "github_repository" for item in links)


def test_link_extraction_does_not_presume_the_link_resolves():
    """Stage A extracts; only Stage B may say whether anything is there."""
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    for item in items:
        if item.kind is DerivedKind.LINK:
            assert "matched" in item.basis
            assert "exists" not in item.basis.lower()


def test_page_furniture_is_unclassified_not_filed_into_a_section():
    raw = _resume_document()
    items = derive_items(raw, normalize_document(raw))

    furniture = [
        item
        for item in items
        if item.kind is DerivedKind.UNCLASSIFIED and item.label == "page_furniture"
    ]
    assert any("SYNTHETIC DEMO DATA" in item.text for item in furniture)

    sections = [item for item in items if item.kind is DerivedKind.SECTION]
    assert not any("SYNTHETIC DEMO DATA" in item.text for item in sections)


def test_text_before_any_heading_is_reported_as_unplaced():
    raw = document(
        [
            page(
                1,
                [
                    line("p1-l001", "Meera Krishnan", y=60.0, height=20.0),
                    line("p1-l002", "Application A-01 REQ-2026-014", y=95.0),
                    line("p1-l003", "Skills", y=160.0),
                    line("p1-l004", "Python", y=190.0),
                ],
            )
        ]
    )
    items = derive_items(raw, normalize_document(raw))

    preamble = [
        item
        for item in items
        if item.kind is DerivedKind.UNCLASSIFIED and item.label == "preamble"
    ]
    assert any("REQ-2026-014" in item.text for item in preamble)


def test_a_derived_document_satisfies_the_trace_contract_end_to_end():
    raw = _resume_document()
    spans = normalize_document(raw)
    items = derive_items(raw, spans)

    ingested = _ingested(raw, spans, items)

    for item in ingested.derived:
        lines = ingested.raw_lines_for_item(item.id)
        assert lines, f"{item.id} resolves to no raw line"
        assert all(entry.page_number >= 1 for entry in lines)
