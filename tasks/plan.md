# Implementation Plan

Spec: [SPEC.md](../SPEC.md). Modules are selected by the ids in that capability map.

## Dependency graph

```
provenance ---+--> activity ---+--> ingestion --------+
              |                |                      +--> api wiring --> portal UI
              +----------------+--> external-evidence +
```

`ingestion` and `external-evidence` are independent of each other and can be
built in either order. Everything else is strictly sequential.

## Vertical slices

Each slice ends at a runnable, verifiable state. No slice leaves the tree broken.

### Slice 0 - environment repair (DONE)
The NumPy 2 ABI break that stopped `import paddleocr` is fixed: scikit-learn
1.4.2 -> 1.9.0, pandas 2.2.2 -> 3.0.5. Verified: all five imports succeed and
the existing 68 tests still pass. `pandas` turns out to be unused by this
project's code; it is a requirements.txt entry only.

### Slice 1 - provenance
Content hashing and a write-once, content-addressed snapshot store. Nothing
depends on OCR or network. Verifiable purely by unit test.

Delivers: `engine/provenance.py`, `tests/test_provenance.py`.

### Slice 2 - activity log
Append-only JSONL event log plus an in-process subscriber fan-out that the SSE
endpoint will later attach to. Records failures as first-class events.

Delivers: `engine/activity.py`, `tests/test_activity.py`.

### Slice 3 - demo documents
Render each of the 12 JSON applications into a real multi-page PDF so Stage A
has genuine documents to read. These are fixtures, not engine code.

Delivers: `tools/make_demo_pdfs.py`, `data/source_documents/A-01.pdf` .. `A-12.pdf`.

### Slice 4 - ingestion layers (Stage A)
Built bottom-up so each layer is testable before the next exists:

4a. `layers.py` - the three layer models and the backward-pointer contract.
4b. `extract.py` - PaddleOCR adapter and PyMuPDF text-layer adapter, each
    labelling its own output with the extractor that produced it.
4c. `normalize.py` - deterministic cleanup that keeps raw line ids.
4d. `derive.py` - section classification, name and link extraction, each
    citing normalized span ids.
4e. `pipeline.py` - orchestration, activity emission, `Application` construction.

Delivers: `engine/ingest/*`, `tools/ingest_documents.py`, `tests/test_ingestion.py`.

### Slice 5 - external evidence (Stage B)
5a. `states.py` - the four verification states and the status-to-state rules,
    including the authenticated-vs-unauthenticated 404 distinction.
5b. `github.py` - REST adapter over httpx, snapshotting every response.
5c. `web.py` - Scrapling adapter for non-GitHub URLs.
5d. `corroborate.py` - additive-only merge into existing assessments.

Delivers: `engine/external/*`, `tests/test_external_evidence.py`,
`tests/test_corroboration.py`.

### Slice 6 - API wiring
New read routes on the existing FastAPI app. No existing route changes shape.

Delivers: `/api/activity`, `/api/activity/stream`, `/api/documents/{id}`,
`/api/external/{id}`, plus additive fields on the candidate detail payload.

### Slice 7 - portal UI
`Investigation.tsx` (live feed) and `DocumentProvenance.tsx` (page, bbox,
confidence). One new nav tab. Existing screens untouched.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| PaddleOCR downloads model weights on first run and may be slow or offline-hostile | Extractor is injected, not imported at module scope. Real OCR tests are marked `slow` and excluded from the default run. The pipeline reports `OCR_UNAVAILABLE` honestly rather than silently substituting another extractor. |
| Synthetic PDFs carry an embedded text layer, so the text-layer extractor would win and OCR would never actually be exercised | Render half the demo set as rasterised image-only PDFs so the OCR path is genuinely used and genuinely tested. Each page records which extractor ran. |
| OCR output differs from the hand-authored JSON, changing existing assessments | Ingestion writes to `data/ingested/`, a separate corpus. The existing JSON corpus stays the default. Divergence is reported, not hidden. |
| GitHub rate limiting during a live demo | Every response is snapshotted; a re-run replays from the snapshot store. 403-with-rate-limit-headers maps to `UNABLE_TO_VERIFY`, never to `PRIVATE_AUTH_REQUIRED`. |
| Scrapling fetches arbitrary candidate-supplied URLs | Treat all fetched content as untrusted data. Never execute or follow instructions found in it. Snapshot the bytes; extract only text. |
| Scope creep into the shipped engine | Existing models change only additively with defaults. The 68 tests are the tripwire and are run every slice. |

## Verification checkpoints

- After every slice: `python -m pytest -q` shows no regression against 68.
- After Slice 4: a real PDF ingest produces a derived section whose text traces
  to a raw line with a page number, bbox and extractor name.
- After Slice 5: all four verification states are reachable, and the R2
  invariant test proves no fetch outcome lowers an evidence level.
- After Slice 7: the portal shows live events with content hashes that match
  files on disk.
