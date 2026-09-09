"""Render the demo applications as real documents for Stage A to read.

The twelve applications in `data/applications/` are hand-authored JSON. Stage A
claims to ingest documents, so it needs documents - not a shortcut that reads
the JSON and calls the result "ingested".

Two details matter more than they look:

  Some of these are deliberately rasterised to image-only PDFs. A PDF carrying
  an embedded text layer is read by the text-layer extractor, which is both
  faster and more accurate - but it means PaddleOCR never runs. A Stage A demo
  where every page took the text-layer path would be a claim about a pipeline
  that was never actually exercised.

  Every page is watermarked as synthetic. These are fabricated candidates for a
  hackathon dataset, and a document that did not say so could later be mistaken
  for a real application.

Run with:  python -m tools.make_demo_pdfs
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS = ROOT / "data" / "applications"
OUTPUT = ROOT / "data" / "source_documents"

WATERMARK = "SYNTHETIC DEMO DATA - X'O Code 2026 PS02 - not a real application"

# Rendered as scans rather than digital PDFs, so the OCR path is genuinely
# used. A third of the set is enough to exercise it without making the whole
# demo slow.
SCANNED_IDS = frozenset({"A-02", "A-05", "A-08", "A-11"})

SCAN_DPI = 200

# High enough that recognition stays reliable, low enough that a two-page scan
# lands in the few-megabyte range a real upload would.
JPEG_QUALITY = 75

SECTION_HEADINGS = {
    "skills": "Skills",
    "experience": "Experience",
    "projects": "Projects",
    "education": "Education",
    "cover_note": "Cover Note",
}

# The cover note starts a new page so every document is genuinely multi-page
# and page provenance has something to distinguish.
PAGE_BREAK_BEFORE = "cover_note"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "name", parent=base["Title"], fontSize=20, leading=24, spaceAfter=2
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=9.5,
            textColor="#4f5d75",
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base["Heading2"],
            fontSize=12,
            leading=15,
            spaceBefore=12,
            spaceAfter=5,
            textColor="#2d3142",
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontSize=10.5,
            leading=15.5,
            alignment=TA_JUSTIFY,
        ),
        "mark": ParagraphStyle(
            "mark", parent=base["Normal"], fontSize=7.5, textColor="#9aa1b1"
        ),
    }


def _stamp(canvas, document) -> None:
    """Mark every page as synthetic, and number it.

    The page number is drawn for the human reader only. Stage A never reads it
    back - a page number the extractor did not itself report is exactly the
    kind of detail this project refuses to infer.
    """
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColorRGB(0.62, 0.64, 0.70)
    canvas.drawString(20 * mm, 12 * mm, WATERMARK)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_pdf(application: dict, path: Path) -> None:
    """Render one application as a digital, text-layer PDF."""
    style = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"{application['candidate_name']} - {application['id']}",
        author="EvidenceHire synthetic dataset",
    )

    flow = [
        Paragraph(application["candidate_name"], style["name"]),
        # Plain ASCII separators on purpose: the base-14 PDF fonts encode a
        # middot in a way PyMuPDF reads back as U+FFFD, which would put a
        # replacement character into the raw layer and make it look like an
        # extraction fault rather than a generator choice.
        Paragraph(
            f"Application {application['id']} - "
            "Junior Robotics Software Engineer - REQ-2026-014",
            style["meta"],
        ),
    ]

    for section in application["sections"]:
        kind = section["kind"]
        if kind == PAGE_BREAK_BEFORE:
            flow.append(PageBreak())
        flow.append(
            Paragraph(SECTION_HEADINGS.get(kind, kind.title()), style["heading"])
        )
        flow.append(Paragraph(section["text"], style["body"]))

    flow.append(Spacer(1, 10 * mm))
    flow.append(
        Paragraph(
            "This document is synthetic demo data generated for the X'O Code "
            "2026 hackathon. It does not describe a real person.",
            style["mark"],
        )
    )

    document.build(flow, onFirstPage=_stamp, onLaterPages=_stamp)


def rasterise(path: Path, dpi: int = SCAN_DPI) -> None:
    """Replace a PDF with an image-only version of itself.

    This is what makes the OCR path real. Afterwards the file holds pictures of
    pages and no extractable text, so the text-layer extractor finds nothing
    and PaddleOCR has to do the work.
    """
    temporary = path.with_suffix(".scan.tmp")

    source = fitz.open(path)
    scanned = fitz.open()
    for page in source:
        pixmap = page.get_pixmap(dpi=dpi)
        # JPEG rather than a raw pixmap. A lossless 200 DPI page runs to about
        # 11 MB, which no real scanner produces and no sane upload limit should
        # have to accommodate. Real scans are compressed, and the artefacts
        # that introduces are also what OCR has to cope with in production.
        target = scanned.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(
            target.rect, stream=pixmap.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
        )
    scanned.save(temporary, deflate=True, garbage=4)
    scanned.close()
    source.close()

    path.unlink()
    temporary.rename(path)


def has_text_layer(path: Path) -> bool:
    """Whether any page exposes extractable text without OCR."""
    with fitz.open(path) as document:
        return any(page.get_text().strip() for page in document)


def page_count(path: Path) -> int:
    with fitz.open(path) as document:
        return document.page_count


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for source in sorted(APPLICATIONS.glob("*.json")):
        application = json.loads(source.read_text(encoding="utf-8"))
        target = OUTPUT / f"{application['id']}.pdf"

        build_pdf(application, target)
        scanned = application["id"] in SCANNED_IDS
        if scanned:
            rasterise(target)

        kind = "scanned image" if scanned else "digital text"
        print(
            f"{application['id']}  {page_count(target)} pages  {kind:<13} "
            f"text layer: {'yes' if has_text_layer(target) else 'no'}"
        )

    print(f"\nWrote {len(list(OUTPUT.glob('*.pdf')))} documents to {OUTPUT}")


if __name__ == "__main__":
    main()
