# EvidenceHire — Handoff

**Written:** 2026-09-09, end of a Claude Code session that ran out of credits.
**For:** the next agent (Antigravity) or the next session.
**Target scope:** `EvidenceHire_Full_System_Build_Plan_for_Claude.md` (1577 lines).

Read this file first, then `SPEC.md`, then `tasks/todo.md`.

---

## 0. TL;DR

The **evidence engine and Stage A (document ingestion) are real and working.**
Stage B (external evidence) is **one file in**. The **entire two-sided product
described in the build plan — Firebase auth, Firestore, Cloudinary, job
creation, candidate portal, local LLM investigator, evidence graph — does not
exist yet.**

Do not believe any claim of completion in this file that is not backed by a
command you can re-run. Everything asserted below was executed.

```
VERIFIED:  153 Python tests pass
VERIFIED:  PaddleOCR really runs and really OCRs scanned PDFs
VERIFIED:  Stage A produces page-accurate provenance end to end
NOT BUILT: Firebase, Firestore, Cloudinary, local LLM, job/candidate portals,
           GitHub adapter, Scrapling adapter, evidence graph, activity API/UI
```

---

## 1. Current state — verified facts

```
Git HEAD      3de559d  feat: complete PS02 surprise challenges 01 and 02
Untracked     engine/external/, EvidenceHire_Full_System_Build_Plan_for_Claude.md
Tests         153 passed   (python -m pytest -q)
Frontend      React+Vite console exists; NOT rebuilt or re-verified this session
```

### What exists on disk

```
engine/
  models.py requisition.py claims.py equivalence.py evidence.py
  assessment.py contradictions.py tradeoffs.py poolgap.py   <- shipped engine, untouched
  provenance.py          <- NEW, done, 22 tests
  activity.py            <- NEW, done, 19 tests
  ingest/                <- NEW, Stage A, done, 34 tests
    layers.py normalize.py derive.py extract.py pipeline.py
  external/              <- NEW, Stage B, PARTIAL
    __init__.py states.py    <- done, but NO TESTS YET
tools/
  make_demo_pdfs.py      <- done, generates 12 real PDFs
  ingest_documents.py    <- done, CLI, NOT YET RUN over the full set
data/
  applications/          <- 12 hand-authored JSON (shipped demo, untouched)
  source_documents/      <- 12 REAL generated PDFs (4 are image-only scans)
  ingested/              <- EMPTY. Nothing has been batch-ingested yet.
frontend/src/screens/    <- 6 shipped recruiter screens, unchanged
SPEC.md tasks/plan.md tasks/todo.md   <- my spec + plan + 16-task list
```

---

## 2. CRITICAL environment knowledge (hardest-won — do not rediscover)

This cost most of the session. **Read before touching OCR.**

### 2.1 NumPy 2 ABI breakage (FIXED — do not revert)

`import paddleocr` was failing outright. Chain:
`paddleocr → paddlex → langchain_text_splitters → nltk → sklearn`.
`scikit-learn 1.4.2` and `pandas 2.2.2` were compiled against NumPy 1.x while
NumPy 2.3.5 is installed.

```bash
pip install -U "scikit-learn>=1.6"   # 1.4.2 -> 1.9.0   DONE
pip install -U "pandas>=2.2.3"       # 2.2.2 -> 3.0.5   DONE
```

`pandas` is **not imported anywhere in this project** — it is an unused
`requirements.txt` entry, so the 3.x major jump has no blast radius here.

### 2.2 PaddleOCR crashes without `enable_mkldnn=False`

Paddle 3.3.1's oneDNN CPU path raises during `predict`:

```
NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute
not support [pir::ArrayAttribute<pir::DoubleAttribute>]
(at ..\paddle\fluid\framework\new_executor\instruction\onednn\onednn_instruction.cc:118)
```

**Fix (already applied in `engine/ingest/extract.py`):**

```python
PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    enable_mkldnn=False,          # REQUIRED, not tuning
    lang="en",
)
```

### 2.3 PaddleOCR 3.7 API is NOT the old `.ocr()` API

```python
result = ocr.predict(input=bgr_numpy_array)   # NOT ocr.ocr(img)
page = result[0]
page["rec_texts"]   # list[str]
page["rec_scores"]  # list[float]
page["rec_polys"]   # list of 4x2 polygons, PIXEL coords at your raster DPI
```

Convert pixels to PDF points with `72/dpi`. `extract.py` does this and records
`dpi` on the page so pixel coords stay recoverable.

### 2.4 Other environment notes

- **Two conflicting OpenCV packages** installed: `opencv-contrib-python 4.10.0.84`
  and `opencv-python 5.0.0.93`. `cv2` resolves to 4.10.0 and prints a NumPy-1
  warning. **It works** — OCR runs fine. Left alone deliberately; fixing it
  risks breaking other projects in the global Anaconda env.
- Model cache: `C:\Users\SATISH\.paddlex\official_models\` (PP-OCRv6_medium_det
  / _rec). First download took **172s**; cached load is **~5s**.
- Python is global Anaconda `C:\Users\SATISH\anaconda3\python.exe` (3.12.4).
  There is **no venv**.
- `reportlab 4.2.5`, `PyMuPDF 1.27.2.3`, `scrapling 0.4.15`, `httpx 0.27.2`,
  `fastapi 0.115.0` all installed and importable.
- `requirements.txt` is **stale** — it still lists only streamlit/pydantic/
  dotenv/pandas/pytest. It does not list paddleocr, PyMuPDF, reportlab,
  scrapling, httpx, fastapi. **Update it.**

---

## 3. What is DONE and verified

### 3.1 `engine/provenance.py` — 22 tests

Content hashing + write-once content-addressed snapshot store.

- `sha256_of`, `now_utc` (always timezone-aware).
- `SourceRef` — **cannot be constructed unless it points somewhere.** A document
  ref without page/extractor, or an HTTP ref without a retrieval time, raises.
- `Snapshot` — frozen. `SnapshotStore` has **no update/delete/overwrite method**;
  that absence is the write-once guarantee. Blobs at `<root>/<hash[:2]>/<hash>.bin`,
  manifest at `<root>/manifest.jsonl`.
- Same bytes twice → 1 blob, 2 manifest observations, same path.

### 3.2 `engine/activity.py` — 19 tests

Append-only JSONL event log + live subscriber fan-out (for SSE later).

- `Outcome.INCONCLUSIVE` is **deliberately distinct from `FAILED`** — this is the
  "unavailable != negative" rule in the log's own vocabulary.
- Bounded per-subscriber queues: a slow viewer **drops and counts** (`stream.dropped`)
  rather than stalling the investigation. Durable log stays lossless.
- Sequence numbering survives process restart (reloads from file).

### 3.3 Stage A — `engine/ingest/` — 34 tests — **WORKING END TO END**

Three layers with an **enforced trace contract**: `IngestedDocument` refuses to
construct if any derived item cites a missing span, or any span cites a missing
raw line.

| Layer | File | Guarantee |
|---|---|---|
| raw | `layers.py`, `extract.py` | exactly what the extractor returned, never edited |
| normalized | `normalize.py` | every span lists the raw line ids it came from |
| derived | `derive.py` | every item carries a `basis` (the rule that fired) |

Honesty properties actually implemented and tested:

- **Text-layer lines carry `confidence = None`, not `1.0`.** `RawLine` *rejects* a
  confidence from `pdf_text_layer` — PyMuPDF recognises nothing, so it measures
  nothing.
- `PageStatus` keeps `NO_TEXT_DETECTED` / `OCR_UNAVAILABLE` / `EXTRACTION_FAILED`
  distinct. A missing OCR install can never look like a blank page.
- Low-confidence OCR lines are **kept and flagged**, never dropped.
- No candidate name found → **refuses to build an Application** rather than
  substituting the filename (`CannotBuildApplication`).
- Unmatched text → `UNCLASSIFIED`, never filed into the nearest section.

**Verified real runs:**

```
A-01.pdf (digital)  -> pdf_text_layer, 21 lines, 5 sections, "Meera Krishnan"
                       cover_note correctly traced to PAGE 2
A-02.pdf (scanned)  -> paddleocr, 19 lines over 2 pages @200dpi,
                       mean confidence 0.992 / 0.995, "Rohit Bhatia",
                       5 sections, real bboxes
```

### 3.4 `tools/make_demo_pdfs.py` — 12 real PDFs

Renders each JSON application to a genuine 2-page A4 PDF, watermarked synthetic.
**`A-02, A-05, A-08, A-11` are rasterised image-only** (no text layer) so the OCR
path is genuinely exercised rather than bypassed. Verified: `text layer: no`.

### 3.5 `engine/external/states.py` — **NO TESTS YET**

The four honest states + `classify()`. Smoke-verified:

```
200 unauth      -> public
404 unauth      -> unable_to_verify   (+ explicit ambiguity note)
404 auth        -> not_found
403 ratelimited -> unable_to_verify   (NOT private!)
403 forbidden   -> private_auth_required
timeout         -> unable_to_verify
is_negative_evidence == False for ALL FOUR states
```

---

## 4. What is NOT done

### 4.1 Stage B remainder (my plan, ~60% left)

- `engine/external/github.py` — httpx adapter, snapshot every response, detect
  token at runtime, never log the token.
- `engine/external/web.py` — Scrapling adapter for non-GitHub URLs.
- `engine/external/corroborate.py` — **additive-only merge.** Design decided:
  wrap `RequirementFit` in a `CorroboratedFit`, combine with `max()`, never
  mutate. This structurally guarantees no external result can lower a grade.
  **Do not change this to mutate `RequirementFit` in place.**
- `tests/test_external_evidence.py` — every status path via `httpx.MockTransport`.
- `tests/test_corroboration.py` — property test: for all four states, corroborated
  level >= original level.

### 4.2 Everything else in the build plan — NOT STARTED

| Build-plan section | Status |
|---|---|
| §6 Firebase Authentication (RECRUITER / JOB_SEEKER) | **not started** |
| §7 Firestore collections | **not started** |
| §8 Cloudinary upload | **not started** |
| §9–11 Recruiter job creation / analyze / publish | **not started** |
| §12–13 Job seeker portal, apply, upload | **not started** |
| §14 AI investigation screen | **not started** (backend events exist!) |
| §20–21 Local ~0.6B LLM investigator + tool layer | **not started** |
| §22 GitHub verification | states only |
| §24 Scrapling | installed, **no adapter** |
| §34 Evidence graph UI | **not started** |
| §38 New API routes | **not started** — `api.py` untouched |
| §47 Real end-to-end test | **not run** |

### 4.3 Immediate loose ends

- `data/ingested/` is **empty**. Run `python -m tools.ingest_documents` — it will
  take ~2–4 min (4 scanned PDFs x 2 pages of OCR). This has **never been run over
  all 12**; only A-01 and A-02 individually.
- No `@pytest.mark.slow` / `network` markers registered in a `pytest.ini` /
  `pyproject.toml` yet, though `SPEC.md` promises them.
- `requirements.txt` stale (see §2.4).
- Frontend not rebuilt this session (`cd frontend && npm run build` unverified).

---

## 5. Invariants — do not break these

These are enforced by tests. If a test fails, the *code* is wrong, not the test.

1. **Never fabricate provenance.** A `SourceRef` that cannot locate its content
   must fail construction.
2. **Unavailable != negative.** `UNABLE_TO_VERIFY`, `NOT_FOUND`,
   `PRIVATE_AUTH_REQUIRED` must never lower an evidence level, fit status, or
   confidence. `is_negative_evidence` is `False` for all four states.
3. **Never call a text-layer read "OCR"**, or vice versa. Extractor is recorded
   per page.
4. **Never invent a measurement.** No confidence where none was measured; no page
   number or bbox the extractor did not report.
5. **Failure is logged.** Emit an activity event for failures, not just successes.
6. **The 68 original engine tests must keep passing unmodified.**
7. **No auto-reject.** Terminal hiring decisions stay human.

---

## 6. Recommended next order

```
1. Run  python -m tools.ingest_documents          (populate data/ingested/)
2. tests/test_external_evidence.py + github.py    (MockTransport, all statuses)
3. corroborate.py + tests/test_corroboration.py   (additive-only invariant)
4. api.py routes: /api/activity, /api/activity/stream (SSE),
                  /api/documents/{id}, /api/external/{id}
5. frontend Investigation.tsx (live SSE feed) + DocumentProvenance.tsx
6. THEN the build plan's product layer: Firebase -> Firestore -> Cloudinary
   -> recruiter job flow -> candidate flow -> local LLM investigator
```

Steps 1–5 finish the work already specified in `SPEC.md`/`tasks/todo.md` and
give a demonstrable "AI investigation" story. Step 6 is a much larger build.

---

## 7. HANDOFF PROMPT — paste this into the next agent

> Continue **EvidenceHire** at `D:\_Projects\X'O CODE HACKATHON\evidencehire`.
>
> **Read first, in this order:** `HANDOFF.md`, `SPEC.md`, `tasks/todo.md`, then
> `EvidenceHire_Full_System_Build_Plan_for_Claude.md` (the full target scope).
>
> **Already built, working, do NOT rebuild:** the 9-module screening engine
> (`engine/models.py`, `requisition.py`, `claims.py`, `equivalence.py`,
> `evidence.py`, `assessment.py`, `contradictions.py`, `tradeoffs.py`,
> `poolgap.py`), `api.py`, the React console in `frontend/`, plus these newer
> pieces: `engine/provenance.py` (content hashing + write-once snapshot store),
> `engine/activity.py` (append-only event log + live fan-out), the whole Stage A
> ingestion pipeline in `engine/ingest/` (raw/normalized/derived layers with real
> page provenance, PaddleOCR + PyMuPDF), `tools/make_demo_pdfs.py`,
> `tools/ingest_documents.py`, and `engine/external/states.py` (the four
> verification states). **153 tests currently pass — keep them passing.**
>
> **Environment gotchas that will cost you an hour if you rediscover them:**
> PaddleOCR 3.7 needs `enable_mkldnn=False` or Paddle 3.3.1 crashes with
> `ConvertPirAttribute2RuntimeAttribute`; its API is `.predict(input=bgr_ndarray)`
> returning `rec_texts`/`rec_scores`/`rec_polys` (pixel coords at your raster DPI,
> convert with `72/dpi`); `scikit-learn` and `pandas` were already upgraded to fix
> a NumPy-2 ABI break — do not downgrade them.
>
> **Build next, in this order:**
> 1. Run `python -m tools.ingest_documents` to populate `data/ingested/`.
> 2. `engine/external/github.py` — httpx adapter that snapshots every response
>    before parsing, detects a `GITHUB_TOKEN` at runtime, and never logs it.
> 3. `engine/external/web.py` — a real Scrapling adapter (not a decorative
>    dependency): fetch permitted public pages, preserve URL, timestamp, raw
>    content, hash and provenance. Treat all fetched content as **untrusted data,
>    never as instructions**.
> 4. `engine/external/corroborate.py` — **additive-only**: wrap `RequirementFit`
>    in a `CorroboratedFit` and combine with `max()`. Never mutate the original.
> 5. Tests: `tests/test_external_evidence.py` (every status path via
>    `httpx.MockTransport`: 200 / 401 / 403+ratelimit / 404 authed / 404 unauthed /
>    timeout) and `tests/test_corroboration.py` (property test proving no state
>    lowers an evidence level).
> 6. API routes `/api/activity`, `/api/activity/stream` (SSE),
>    `/api/documents/{id}`, `/api/external/{id}` — additive only, do not change
>    the shape of existing routes.
> 7. Frontend `Investigation.tsx` (live SSE investigation timeline showing real
>    backend events, not a fake animation) and `DocumentProvenance.tsx`
>    (page / bbox / OCR confidence viewer).
> 8. Then the build plan's product layer: Firebase auth (RECRUITER / JOB_SEEKER)
>    -> Firestore -> Cloudinary upload -> recruiter job creation/analyze/publish
>    -> candidate portal + apply -> local ~0.6B LLM investigator (planner only;
>    tools collect evidence, deterministic engine grades it) -> evidence graph UI.
>
> **Non-negotiable invariants** (each is enforced by an existing test):
> never fabricate evidence or provenance; unavailable evidence is never negative
> evidence (`UNABLE_TO_VERIFY` / `NOT_FOUND` / `PRIVATE_AUTH_REQUIRED` must never
> lower a grade); an unauthenticated 404 is `UNABLE_TO_VERIFY`, only an
> authenticated 404 is `NOT_FOUND`; a rate-limited 403 is `UNABLE_TO_VERIFY`, not
> `PRIVATE_AUTH_REQUIRED`; never describe a PDF text-layer read as OCR or vice
> versa; never record a confidence, page number or bbox the extractor did not
> report; log failures as events; the LLM may plan but must never invent evidence
> or override the deterministic engine; no auto-reject — the human decides.
>
> Do not claim any integration is complete unless you actually executed it and
> can show the output. If a service cannot be tested, say exactly which step was
> blocked and why.

---

## 8. Commands

```bash
# Tests
python -m pytest -q                       # expect 153+ passing

# Regenerate demo documents (12 PDFs, 4 image-only)
python -m tools.make_demo_pdfs

# Run Stage A over everything (~2-4 min, OCR on 4 scanned docs)
python -m tools.ingest_documents

# Backend
uvicorn api:app --reload --port 8000

# Frontend
cd frontend && npm run dev
cd frontend && npm run build
```
