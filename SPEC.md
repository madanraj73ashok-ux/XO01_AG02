# Spec: EvidenceHire — Stage A, Stage B, Investigation Portal

Status: proposed
Date: 2026-09-09
Extends the shipped engine (9 modules, 68 tests), `api.py`, and `frontend/` —
none of which are rebuilt by this work.

---

## Capability Map

This initiative bundles four independently testable capabilities. Module ids are
stable and are how downstream tasks select work.

| Module id | Responsibility | Depends on |
|---|---|---|
| `provenance` | Content hashing, write-once snapshot store, source references, UTC clock. The single place "where did this come from" is defined and enforced. | — |
| `activity` | Append-only investigation event log + live stream. Every step either stage takes is recorded here, successes and failures alike. | `provenance` |
| `ingestion` | **Stage A.** Source document to raw / normalized / derived layers to `Application`, carrying real page provenance. | `provenance`, `activity` |
| `external-evidence` | **Stage B.** GitHub API + Scrapling fetches to immutable snapshots, content hashes, and honest verification states. | `provenance`, `activity` |

**Build order:** `provenance` then `activity` then (`ingestion` and
`external-evidence`, which are independent of each other) then API + portal wiring.

**Why these boundaries.** `ingestion` and `external-evidence` share nothing but
the notion of a verifiable source, so that notion is extracted into `provenance`
rather than duplicated as two subtly different hash schemes. `activity` is
separate because it must observe both stages without either stage depending on
the other. The arrows point one way; there are no cycles.

---

## Objective

The shipped system grades claims against evidence found **inside** one
application. Two things are currently taken on faith:

1. The application text is assumed to already exist as clean JSON. Real
   applications arrive as PDFs and scans.
2. Evidence is confined to the document. A candidate's public repositories are
   the strongest available corroboration and are never consulted.

This work closes both gaps **without weakening the project's central
discipline**: a claim is not evidence, and absent evidence is not counter-evidence.

### The two rules that govern every design decision here

> **R1 — Never fabricate evidence or provenance.**
> If the system cannot point at a real page, a real bounding box, or a real
> stored response body, it reports that it cannot, and shows nothing.

> **R2 — Unavailable evidence is not negative evidence.**
> A repository we could not read is not a repository that does not exist. A
> fetch that timed out says nothing about the candidate. External evidence may
> only *raise* an assessment; it may never lower one.

R2 has a concrete architectural consequence: `external-evidence` writes to a
corroboration channel that is additive-only. There is no code path by which a
failed fetch reduces an evidence level. That is enforced by test, not by
convention.

### Users

- **Recruiter** — sees where every quoted span physically came from (page,
  bounding box, OCR confidence) and which external claims were verified,
  unverifiable, or private.
- **Reviewer / judge** — can audit any conclusion back to a stored artefact: an
  OCR line on a page, or a hashed HTTP response body on disk.

---

## Tech Stack

Existing, unchanged: Python 3.12, Pydantic 2.12, FastAPI 0.115, React 18 + Vite 5
+ Tailwind 3, pytest 8.

Added by this work:

| Dependency | Version | Used for |
|---|---|---|
| `paddleocr` | 3.7.0 (installed) | Stage A OCR of scanned and image pages |
| `paddlepaddle` | 3.3.1 (installed) | PaddleOCR runtime |
| `PyMuPDF` | 1.27.2 (installed) | PDF page rasterisation; embedded text-layer extraction |
| `scrapling` | 0.4.15 (installed) | Stage B general web retrieval |
| `httpx` | 0.27.2 (installed) | Stage B GitHub REST calls |
| `python-dotenv` | installed | reads optional `GITHUB_TOKEN` from `.env` |
| `reportlab` | to install | renders the synthetic demo resume PDFs |

`scikit-learn` and `pandas` are upgraded to repair the NumPy 2 ABI break that
currently makes `import paddleocr` fail. Both were compiled against NumPy 1.x
while NumPy 2.3.5 is installed. That is a pre-existing environment fault being
fixed, not a feature.

---

## Commands

```bash
# Backend
uvicorn api:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
python -m pytest -q
python -m pytest tests/test_ingestion.py -q          # Stage A only
python -m pytest tests/test_external_evidence.py -q  # Stage B only
python -m pytest -q -m "not slow"                    # skips real OCR runs

# One-off generators
python -m tools.make_demo_pdfs      # renders 12 synthetic resume PDFs
python -m tools.ingest_documents    # OCRs data/source_documents -> data/ingested
```

---

## Project Structure

```
engine/
  provenance.py           # content hashing, snapshot store, source refs
  activity.py             # append-only investigation event log
  ingest/
    layers.py             # RawLine / RawPage / NormalizedSpan / DerivedItem
    extract.py            # PaddleOCR + PDF text-layer extractors
    normalize.py          # raw -> normalized, with backward pointers
    derive.py             # normalized -> sections, name, links
    pipeline.py           # orchestrates the three layers, emits activity
  external/
    states.py             # VerificationState + the rules that assign it
    github.py             # GitHub REST adapter
    web.py                # Scrapling adapter
    corroborate.py        # additive-only merge into assessments
tools/
  make_demo_pdfs.py       # JSON application -> real PDF (demo fixtures)
  ingest_documents.py     # CLI entry for the ingestion pipeline
data/
  source_documents/       # drop-in PDFs and images (input)
  ingested/               # three-layer ingest records (output, git-ignored)
  snapshots/              # content-addressed external fetches (git-ignored)
  activity/               # append-only JSONL event log (git-ignored)
frontend/src/screens/
  Investigation.tsx       # live activity portal
  DocumentProvenance.tsx  # page / bbox / confidence viewer
tests/
  test_provenance.py  test_activity.py
  test_ingestion.py   test_external_evidence.py  test_corroboration.py
```

---

## Code Style

Matches the existing engine exactly: `from __future__ import annotations`,
Pydantic models whose docstrings explain *why the type exists*, module
docstrings that state the discipline the module enforces, and comments reserved
for non-obvious reasoning rather than restating code.

```python
class VerificationState(str, Enum):
    """What we actually established about an external source.

    The four states are deliberately not collapsible into a boolean. Three of
    them mean "not confirmed present", and exactly one of those three
    (`NOT_FOUND`) is an authoritative negative. Merging them would let a
    timeout read as a missing repository, which is the failure R2 forbids.
    """

    PUBLIC = "public"
    PRIVATE_AUTH_REQUIRED = "private_auth_required"
    NOT_FOUND = "not_found"
    UNABLE_TO_VERIFY = "unable_to_verify"

    @property
    def is_negative_evidence(self) -> bool:
        """Always False. Present so the rule is greppable and testable.

        No verification state is evidence against a candidate. `NOT_FOUND`
        raises a discrepancy for a human to review; it never lowers a grade.
        """
        return False
```

---

## Testing Strategy

pytest, in `tests/`, mirroring the existing file-per-module convention.

| Level | Applies to | Approach |
|---|---|---|
| Unit | layer transforms, state rules, hashing | Pure functions on fixtures. No network, no OCR. |
| Contract | GitHub + Scrapling adapters | Replayed HTTP fixtures via `httpx.MockTransport`. Every status path (200 / 401 / 403+ratelimit / 404 authed / 404 unauthed / timeout) gets its own test. |
| Integration | full ingest of one real PDF | Marked `@pytest.mark.slow`. Runs real PaddleOCR against a committed fixture PDF. |
| Invariant | R1 and R2 | Dedicated tests asserting no code path lowers an evidence level, and that every derived item resolves to a raw line carrying a page number. |

The existing 68 tests must continue to pass unmodified. New code targets >=80%.

**No network in the default test run.** Real GitHub calls live behind
`@pytest.mark.network` and are excluded by default, so the demo stays
reproducible offline exactly as the README promises.

---

## Boundaries

**Always**
- Record the extractor that produced every page (`paddleocr`, `pdf_text_layer`),
  never a generic "extracted".
- Keep low-confidence OCR lines, flagged. Dropping them silently rewrites the
  document.
- Write snapshots content-addressed and write-once. Re-fetching creates a new
  snapshot; nothing is overwritten.
- Emit an activity event for failures, not only successes.
- Run the full suite before declaring a task complete.

**Ask first**
- Adding any dependency beyond those listed in Tech Stack.
- Changing an existing engine model in a way that is not additive-with-default.
- Anything that would make the offline demo depend on network access.

**Never**
- Commit `GITHUB_TOKEN`, `.env`, snapshots, or OCR model weights.
- Infer a page number, bounding box, or confidence the extractor did not return.
- Let `UNABLE_TO_VERIFY`, `NOT_FOUND`, or `PRIVATE_AUTH_REQUIRED` reduce an
  evidence level, fit status, or confidence figure.
- Describe a PDF text-layer extraction as OCR, or vice versa.
- Auto-reject a candidate. Terminal decisions remain human.

---

## Success Criteria

Testable, in the order they will be verified.

1. `import paddleocr` succeeds; `python -m pytest -q` reports >=68 passed.
2. Twelve synthetic resume PDFs exist under `data/source_documents/`, each a
   real multi-page PDF rendered from its corresponding JSON application.
3. Ingesting any one of them produces a record with all three layers, and every
   derived section resolves to at least one normalized span, which resolves to at
   least one raw line carrying a page number, bounding box, and extractor name.
4. `Application` objects built by the pipeline drive the existing engine
   unchanged — the same assessments are produced from the ingested PDFs as from
   the hand-authored JSON, or every difference is attributable to a named OCR line.
5. A GitHub fetch of a known-public repo yields `PUBLIC` plus a snapshot whose
   sha256 matches the bytes on disk.
6. Each of the four verification states is reachable and covered by a test that
   asserts the state *and* asserts the resulting evidence level is unchanged or
   higher than it was without the fetch.
7. Without `GITHUB_TOKEN`, a 404 yields `UNABLE_TO_VERIFY` with an explicit note
   that an unauthenticated request cannot distinguish private from missing.
   With a token, the same 404 yields `NOT_FOUND`.
8. `GET /api/activity` returns the event log; `GET /api/activity/stream` pushes
   new events over SSE; the Investigation screen renders them live.
9. Every activity event referencing external content shows a content hash the
   reviewer can match against a file in `data/snapshots/`.

---

## Open Questions

None blocking. Three decisions were taken with the user on 2026-09-09:

- **OCR repair** — upgrade the NumPy-1-era binaries in the base Anaconda
  environment (`scikit-learn`, and `pandas` once the same fault surfaced there).
- **GitHub auth** — build for both authenticated and unauthenticated operation
  and degrade honestly; do not require a token.
- **Stage A inputs** — render 12 synthetic resume PDFs from the existing JSON
  applications so OCR runs against genuine documents and the demo narrative is
  preserved end to end.
