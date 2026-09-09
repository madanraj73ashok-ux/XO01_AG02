# Task List

Spec: [SPEC.md](../SPEC.md) | Plan: [plan.md](plan.md)
Module ids come from the capability map. Order is by dependency, not importance.

---

## Slice 0 - environment repair  [module: -]

- [x] Task: Repair the NumPy 2 ABI break blocking `import paddleocr`
  - Acceptance: paddleocr, paddle, pymupdf, scrapling, pandas, sklearn all import
  - Verify: `python -m pytest -q` still reports 68 passed
  - Files: none in-repo (environment only)

---

## Slice 1 - provenance  [module: provenance]

- [ ] Task: Content hashing and source references
  - Acceptance: `sha256_of(bytes)` is stable; `SourceRef` can address a document
    page+bbox or a stored HTTP response, and cannot be constructed without one
  - Verify: `pytest tests/test_provenance.py -q`
  - Files: engine/provenance.py, tests/test_provenance.py

- [ ] Task: Write-once content-addressed snapshot store
  - Acceptance: storing the same bytes twice returns the same path and does not
    rewrite the file; storing different bytes for the same URL creates a second
    snapshot; stored bytes re-hash to the recorded digest
  - Verify: `pytest tests/test_provenance.py -q`
  - Files: engine/provenance.py, tests/test_provenance.py

---

## Slice 2 - activity  [module: activity]

- [ ] Task: Append-only investigation event log
  - Acceptance: events carry UTC timestamp, stage, action, subject, outcome and
    an optional SourceRef; the log is append-only (no update/delete API);
    failures are recorded as events with a failure outcome
  - Verify: `pytest tests/test_activity.py -q`
  - Files: engine/activity.py, tests/test_activity.py

- [ ] Task: In-process subscriber fan-out for live streaming
  - Acceptance: a subscriber registered before an emit receives it; a slow
    subscriber cannot block the emitter; unsubscribing stops delivery
  - Verify: `pytest tests/test_activity.py -q`
  - Files: engine/activity.py, tests/test_activity.py

---

## Slice 3 - demo documents  [module: ingestion]

- [ ] Task: Render the 12 JSON applications as real PDFs
  - Acceptance: 12 PDFs exist under data/source_documents/; at least 4 are
    rasterised image-only so the OCR path is genuinely exercised; each PDF is
    watermarked as synthetic demo data
  - Verify: `python -m tools.make_demo_pdfs` then confirm page counts and that
    the image-only ones expose no extractable text layer
  - Files: tools/make_demo_pdfs.py

---

## Slice 4 - ingestion (Stage A)  [module: ingestion]

- [ ] Task: Three-layer models with an enforced backward-pointer contract
  - Acceptance: a DerivedItem cites normalized span ids; a NormalizedSpan cites
    raw line ids; a RawLine carries page number, bbox, confidence and extractor.
    A DerivedItem with no resolvable raw line fails validation.
  - Verify: `pytest tests/test_ingestion.py -q`
  - Files: engine/ingest/layers.py, tests/test_ingestion.py

- [ ] Task: PaddleOCR and PDF text-layer extractors
  - Acceptance: each returns RawPages labelled with its own extractor name; a
    page yielding nothing is recorded as NO_TEXT_DETECTED, not as empty success;
    when OCR is unavailable the pipeline reports OCR_UNAVAILABLE and emits no
    derived content
  - Verify: `pytest tests/test_ingestion.py -q` and `pytest -m slow -q`
  - Files: engine/ingest/extract.py, tests/test_ingestion.py

- [ ] Task: Normalization that preserves raw line ids
  - Acceptance: NFKC, whitespace collapse, end-of-line hyphen joining and
    reading-order grouping; every output span lists the raw line ids it came
    from; low-confidence lines are kept and flagged, never dropped
  - Verify: `pytest tests/test_ingestion.py -q`
  - Files: engine/ingest/normalize.py, tests/test_ingestion.py

- [ ] Task: Derivation into sections, candidate name and links
  - Acceptance: each derived section carries the rule that produced it and the
    span ids it cites; an unclassifiable block is reported as unclassified
    rather than guessed into a section
  - Verify: `pytest tests/test_ingestion.py -q`
  - Files: engine/ingest/derive.py, tests/test_ingestion.py

- [ ] Task: Pipeline orchestration and Application construction
  - Acceptance: produces an Application the existing engine assesses unchanged;
    emits an activity event per page and per layer; writes the full three-layer
    record to data/ingested/
  - Verify: `pytest -q` (all, no regression) and `python -m tools.ingest_documents`
  - Files: engine/ingest/pipeline.py, tools/ingest_documents.py, engine/models.py

---

## Slice 5 - external evidence (Stage B)  [module: external-evidence]

- [ ] Task: Verification states and the status-to-state rules
  - Acceptance: 200 -> PUBLIC; 401 or 403-without-ratelimit -> PRIVATE_AUTH_REQUIRED;
    403-with-ratelimit -> UNABLE_TO_VERIFY; 404 authenticated -> NOT_FOUND;
    404 unauthenticated -> UNABLE_TO_VERIFY with the ambiguity note; timeout or
    transport error -> UNABLE_TO_VERIFY. `is_negative_evidence` is False for all four.
  - Verify: `pytest tests/test_external_evidence.py -q`
  - Files: engine/external/states.py, tests/test_external_evidence.py

- [ ] Task: GitHub REST adapter over httpx
  - Acceptance: every response is snapshotted with its content hash before it is
    parsed; token presence is detected at runtime; no token is ever logged or
    included in an activity event
  - Verify: `pytest tests/test_external_evidence.py -q` (httpx.MockTransport)
  - Files: engine/external/github.py, tests/test_external_evidence.py

- [ ] Task: Scrapling adapter for non-GitHub URLs
  - Acceptance: fetched bytes are snapshotted and hashed; only text is extracted;
    fetched content is treated as untrusted data and never as instructions
  - Verify: `pytest tests/test_external_evidence.py -q`
  - Files: engine/external/web.py, tests/test_external_evidence.py

- [ ] Task: Additive-only corroboration merge
  - Acceptance: applying any external result to an assessment never lowers an
    evidence level, fit status or confidence; NOT_FOUND raises a review flag and
    changes no grade; a property test asserts this across all four states
  - Verify: `pytest tests/test_corroboration.py -q`
  - Files: engine/external/corroborate.py, tests/test_corroboration.py

---

## Slice 6 - API wiring  [module: activity, ingestion, external-evidence]

- [ ] Task: Activity, document and external routes
  - Acceptance: GET /api/activity returns the log; GET /api/activity/stream
    pushes events over SSE; GET /api/documents/{id} returns the three layers;
    GET /api/external/{id} returns states with hashes. No existing route changes shape.
  - Verify: `pytest -q` and manual curl against a running uvicorn
  - Files: api.py

---

## Slice 7 - portal UI  [module: activity, ingestion, external-evidence]

- [ ] Task: Investigation portal and provenance viewer
  - Acceptance: live event feed renders over SSE and reconnects on drop; each
    external event shows a content hash; the provenance viewer shows page, bbox
    and OCR confidence for a selected span; existing screens are untouched
  - Verify: `cd frontend && npm run build` then drive the running app
  - Files: frontend/src/screens/Investigation.tsx,
    frontend/src/screens/DocumentProvenance.tsx, frontend/src/App.tsx,
    frontend/src/api.ts, frontend/src/types.ts
