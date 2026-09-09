"""Run PaddleOCR over one document, in a process of its own.

This exists because PaddleOCR is not stable in-process here. On this machine it
intermittently takes SIGSEGV during `predict` - not on a particular file, and
not on a particular call, but often enough that hosting it inside the API
server would mean a scanned resume could take the whole server down mid-request.

Isolating it fixes that honestly. If the worker dies, the parent sees a
non-zero exit, and the page is recorded as `OCR_UNAVAILABLE` with the reason.
The pipeline then reports that it could not read the page, which is true,
instead of pretending the page was blank.

The environment guards below are set before Paddle is imported, because they
only take effect at load time. `KMP_DUPLICATE_LIB_OK` is the one that matters:
several OpenMP runtimes end up loaded in this Anaconda environment, and that
clash is what most of the crashes trace back to.

Usage:  python -m tools.ocr_worker <document> [--dpi 200] [--pages 1,3,4]
Output: one JSON object on stdout.
"""

from __future__ import annotations

import os

# Must precede any import that pulls in a native OpenMP runtime.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("GLOG_minloglevel", "2")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402

import fitz  # noqa: E402
import numpy as np  # noqa: E402

DEFAULT_DPI = 200


def rasterise(page: fitz.Page, dpi: int) -> np.ndarray:
    """Render a page to the BGR array PaddleOCR expects."""
    pixmap = page.get_pixmap(dpi=dpi)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    if pixmap.n == 4:
        image = image[:, :, :3]
    elif pixmap.n == 1:
        image = np.repeat(image, 3, axis=2)
    return np.ascontiguousarray(image[:, :, ::-1])


def build_engine(lang: str):
    from paddleocr import PaddleOCR

    # `enable_mkldnn=False` is required, not tuning: with Paddle 3.3.1 the
    # oneDNN CPU path raises ConvertPirAttribute2RuntimeAttribute during
    # predict and kills the run outright.
    return PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        lang=lang,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR one document.")
    parser.add_argument("document")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--pages",
        default="",
        help="comma-separated 1-based page numbers; all pages when omitted",
    )
    parser.add_argument("--lang", default="en")
    arguments = parser.parse_args()

    wanted: set[int] | None = None
    if arguments.pages.strip():
        wanted = {int(part) for part in arguments.pages.split(",") if part.strip()}

    engine = build_engine(arguments.lang)
    pages: list[dict] = []

    with fitz.open(arguments.document) as document:
        for number, page in enumerate(document, start=1):
            if wanted is not None and number not in wanted:
                continue

            image = rasterise(page, arguments.dpi)
            prediction = engine.predict(input=image)
            lines: list[dict] = []

            if prediction:
                result = prediction[0]
                texts = result.get("rec_texts") or []
                scores = result.get("rec_scores") or []
                polygons = result.get("rec_polys")
                if polygons is None:
                    polygons = result.get("dt_polys") or []

                for index, text in enumerate(texts):
                    if index >= len(polygons) or not str(text).strip():
                        continue
                    polygon = np.asarray(polygons[index], dtype=float).reshape(-1, 2)
                    lines.append(
                        {
                            "text": str(text),
                            "score": (
                                float(scores[index]) if index < len(scores) else None
                            ),
                            "poly": polygon.tolist(),
                        }
                    )

            pages.append({"page_number": number, "lines": lines})

    json.dump({"dpi": arguments.dpi, "pages": pages}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
