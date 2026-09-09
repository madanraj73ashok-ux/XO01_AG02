"""Provenance is the foundation both stages rest on.

These tests pin down the two properties everything downstream assumes: a source
reference cannot be built unless it actually points somewhere, and a stored
snapshot cannot be rewritten after the fact.
"""

from __future__ import annotations

import hashlib
from datetime import timezone

import pytest
from pydantic import ValidationError

from engine.provenance import (
    BoundingBox,
    SnapshotStore,
    SourceKind,
    SourceRef,
    now_utc,
    sha256_of,
)

BODY = b'{"full_name": "example/demo"}'


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------


def test_sha256_matches_the_reference_implementation():
    payload = b"evidence, not assertion"
    assert sha256_of(payload) == hashlib.sha256(payload).hexdigest()


def test_sha256_is_stable_across_calls():
    payload = b"the same bytes must always hash the same way"
    assert sha256_of(payload) == sha256_of(payload)


def test_different_bytes_hash_differently():
    assert sha256_of(b"public repo") != sha256_of(b"private repo")


def test_now_utc_is_timezone_aware():
    """A naive timestamp cannot be audited across machines."""
    assert now_utc().tzinfo is timezone.utc


# --------------------------------------------------------------------------
# Source references - R1: a reference cannot point at nothing
# --------------------------------------------------------------------------


def test_document_ref_carries_page_bbox_and_extractor():
    ref = SourceRef(
        kind=SourceKind.DOCUMENT_PAGE,
        locator="A-01.pdf p.2",
        content_hash=sha256_of(b"pdf bytes"),
        document_id="A-01",
        page_number=2,
        bbox=BoundingBox(x=72.0, y=140.5, width=310.0, height=12.0),
        extractor="paddleocr",
    )
    assert ref.page_number == 2
    assert ref.extractor == "paddleocr"


def test_document_ref_rejects_a_missing_page_number():
    """A page number the extractor did not report may never be invented."""
    with pytest.raises(ValidationError):
        SourceRef(
            kind=SourceKind.DOCUMENT_PAGE,
            locator="A-01.pdf",
            content_hash=sha256_of(b"pdf bytes"),
            document_id="A-01",
            extractor="paddleocr",
        )


def test_document_ref_rejects_a_missing_extractor():
    """Every page must say which engine read it, never a generic 'extracted'."""
    with pytest.raises(ValidationError):
        SourceRef(
            kind=SourceKind.DOCUMENT_PAGE,
            locator="A-01.pdf p.1",
            content_hash=sha256_of(b"pdf bytes"),
            document_id="A-01",
            page_number=1,
        )


def test_document_ref_rejects_a_zero_page_number():
    with pytest.raises(ValidationError):
        SourceRef(
            kind=SourceKind.DOCUMENT_PAGE,
            locator="A-01.pdf p.0",
            content_hash=sha256_of(b"pdf bytes"),
            document_id="A-01",
            page_number=0,
            extractor="paddleocr",
        )


def test_http_ref_carries_url_and_retrieval_time():
    ref = SourceRef(
        kind=SourceKind.HTTP_RESPONSE,
        locator="https://api.github.com/repos/example/demo",
        content_hash=sha256_of(BODY),
        url="https://api.github.com/repos/example/demo",
        retrieved_at=now_utc(),
    )
    assert ref.url.endswith("/example/demo")


def test_http_ref_rejects_a_missing_retrieval_time():
    """What a page said is meaningless without when it said it."""
    with pytest.raises(ValidationError):
        SourceRef(
            kind=SourceKind.HTTP_RESPONSE,
            locator="https://example.invalid/",
            content_hash=sha256_of(BODY),
            url="https://example.invalid/",
        )


def test_source_ref_rejects_a_malformed_content_hash():
    with pytest.raises(ValidationError):
        SourceRef(
            kind=SourceKind.HTTP_RESPONSE,
            locator="https://example.invalid/",
            content_hash="not-a-digest",
            url="https://example.invalid/",
            retrieved_at=now_utc(),
        )


# --------------------------------------------------------------------------
# Snapshot store - write-once and content-addressed
# --------------------------------------------------------------------------


def _put(store: SnapshotStore, content: bytes, url: str = "https://example.invalid/a"):
    return store.put(
        content,
        url=url,
        method="GET",
        http_status=200,
        engine="github_api",
        media_type="application/json",
    )


def test_put_returns_a_snapshot_whose_hash_matches_the_bytes(tmp_path):
    store = SnapshotStore(tmp_path)
    snapshot = _put(store, BODY)

    assert snapshot.content_hash == sha256_of(BODY)
    assert snapshot.content_length == len(BODY)
    assert store.read(snapshot.content_hash) == BODY


def test_stored_bytes_verify_against_the_recorded_digest(tmp_path):
    store = SnapshotStore(tmp_path)
    snapshot = _put(store, b"exact response body")
    assert store.verify(snapshot.content_hash) is True


def test_verify_detects_a_tampered_blob(tmp_path):
    """The digest is only worth something if a mismatch is actually caught."""
    store = SnapshotStore(tmp_path)
    snapshot = _put(store, b"original body")

    store.path_for(snapshot.content_hash).write_bytes(b"substituted body")

    assert store.verify(snapshot.content_hash) is False


def test_identical_content_is_stored_once_but_observed_twice(tmp_path):
    """Re-fetching unchanged content must not duplicate the blob.

    Two observations of the same bytes are two facts about time, not two
    documents, so the manifest grows and the blob store does not.
    """
    store = SnapshotStore(tmp_path)
    first = _put(store, b"unchanged body")
    second = _put(store, b"unchanged body")

    assert first.content_hash == second.content_hash
    assert first.storage_path == second.storage_path
    assert len(store.blobs()) == 1
    assert len(store.observations()) == 2


def test_changed_content_for_the_same_url_creates_a_second_snapshot(tmp_path):
    """A snapshot is never overwritten, so history stays auditable."""
    store = SnapshotStore(tmp_path)
    url = "https://example.invalid/profile"
    first = _put(store, b"body as at monday", url=url)
    second = _put(store, b"body as at tuesday", url=url)

    assert first.content_hash != second.content_hash
    assert len(store.blobs()) == 2
    assert store.read(first.content_hash) == b"body as at monday"
    assert store.read(second.content_hash) == b"body as at tuesday"


def test_snapshots_for_returns_every_observation_of_one_url(tmp_path):
    store = SnapshotStore(tmp_path)
    url = "https://example.invalid/profile"
    _put(store, b"body as at monday", url=url)
    _put(store, b"body as at tuesday", url=url)
    _put(store, b"unrelated", url="https://example.invalid/other")

    assert len(store.snapshots_for(url)) == 2


def test_a_snapshot_cannot_be_mutated_after_creation(tmp_path):
    """Immutable in the type system, not merely by convention."""
    store = SnapshotStore(tmp_path)
    snapshot = _put(store, b"sealed")

    with pytest.raises(ValidationError):
        snapshot.http_status = 404


def test_the_store_exposes_no_update_or_delete(tmp_path):
    """Write-once is enforced by the absence of an API to do otherwise."""
    store = SnapshotStore(tmp_path)
    for forbidden in ("update", "delete", "remove", "overwrite"):
        assert not hasattr(store, forbidden)


def test_a_failed_fetch_can_be_snapshotted_with_no_body(tmp_path):
    """A 404 is an observation too, and must be recorded like any other."""
    store = SnapshotStore(tmp_path)
    snapshot = store.put(
        b"",
        url="https://api.github.com/repos/example/missing",
        method="GET",
        http_status=404,
        engine="github_api",
        media_type="application/json",
    )

    assert snapshot.http_status == 404
    assert snapshot.content_length == 0
    assert store.verify(snapshot.content_hash) is True


def test_the_store_survives_a_reopen(tmp_path):
    """The manifest is on disk, so a later process can audit earlier fetches."""
    first = SnapshotStore(tmp_path)
    snapshot = _put(first, b"persisted across processes")

    reopened = SnapshotStore(tmp_path)
    assert reopened.read(snapshot.content_hash) == b"persisted across processes"
    assert len(reopened.observations()) == 1


def test_snapshot_yields_a_source_ref_pointing_at_itself(tmp_path):
    """Every stored response can address itself, so no citation dangles."""
    store = SnapshotStore(tmp_path)
    snapshot = _put(store, b"body")

    ref = snapshot.as_source_ref()
    assert ref.kind is SourceKind.HTTP_RESPONSE
    assert ref.content_hash == snapshot.content_hash
    assert ref.retrieved_at == snapshot.requested_at
