"""Provenance: where a piece of content actually came from.

Every statement this system makes about a candidate has to resolve to something
a reviewer can independently re-check - a line on a page of a real document, or
the exact bytes of a real HTTP response sitting on disk. This module is the one
place that notion is defined, so the document pipeline and the external evidence
fetchers address their sources the same way instead of inventing two subtly
different schemes.

Two rules are enforced here rather than left to callers:

  R1  A `SourceRef` cannot be constructed unless it points at something. A
      document reference without a page number, or an HTTP reference without a
      retrieval time, is rejected by validation. There is deliberately no way
      to express "somewhere in this file, probably".

  Write-once  The snapshot store is content-addressed and append-only. Fetching
      a URL again never overwrites what was seen before; it records a second
      observation. Identical bytes yield an identical digest, so "unchanged
      since Monday" becomes something a reviewer can verify rather than trust.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_NAME = "manifest.jsonl"


def sha256_of(data: bytes) -> str:
    """The digest used everywhere content identity matters."""
    return hashlib.sha256(data).hexdigest()


def now_utc() -> datetime:
    """Timezone-aware UTC.

    Naive timestamps cannot be compared across machines, which makes them
    useless in an audit trail. Nothing in this system records a naive one.
    """
    return datetime.now(timezone.utc)


class SourceKind(str, Enum):
    """The kinds of artefact a reference can point into.

    Kept closed deliberately. A third kind would mean a third way of proving
    where something came from, and that decision should be explicit.
    """

    DOCUMENT_PAGE = "document_page"
    HTTP_RESPONSE = "http_response"


class BoundingBox(BaseModel):
    """Where on a page a span of text physically sits.

    Held in the coordinate space the extractor reported, not a normalised one.
    A converted box is a derived number; the point of this type is to carry the
    measured one.
    """

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SourceRef(BaseModel):
    """A pointer to the artefact that backs a piece of evidence.

    Frozen, because a citation that can be edited after the fact is not a
    citation. The validator below is the enforcement point for R1: the fields
    needed to actually locate the content are mandatory for their kind.
    """

    model_config = ConfigDict(frozen=True)

    kind: SourceKind
    locator: str
    content_hash: str

    # Document references
    document_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    bbox: BoundingBox | None = None
    extractor: str | None = None

    # HTTP references
    url: str | None = None
    retrieved_at: datetime | None = None

    @field_validator("content_hash")
    @classmethod
    def _must_be_a_sha256_digest(cls, value: str) -> str:
        if not _HEX_DIGEST.match(value):
            raise ValueError(
                "content_hash must be a 64-character lowercase sha256 digest; "
                f"got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _must_actually_locate_something(self) -> SourceRef:
        """Reject any reference that cannot be followed back to its source."""
        if self.kind is SourceKind.DOCUMENT_PAGE:
            missing = [
                name
                for name, value in (
                    ("document_id", self.document_id),
                    ("page_number", self.page_number),
                    ("extractor", self.extractor),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "a document reference must name the document, the page it "
                    "was read from, and the extractor that read it; missing: "
                    f"{', '.join(missing)}"
                )

        if self.kind is SourceKind.HTTP_RESPONSE:
            missing = [
                name
                for name, value in (
                    ("url", self.url),
                    ("retrieved_at", self.retrieved_at),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "an HTTP reference must name the URL and when it was "
                    f"retrieved; missing: {', '.join(missing)}"
                )

        return self


class Snapshot(BaseModel):
    """One observation of one URL at one moment, with its content hash.

    Frozen for the same reason `SourceRef` is: a record of what a page said is
    worthless if it can be revised afterwards. A later fetch produces a new
    `Snapshot`, never an edit to this one.

    A snapshot records the observation, not a judgement about it. A 404 with an
    empty body is as legitimate a snapshot as a 200 - deciding what that 404
    *means* belongs to `engine.external.states`, not here.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    method: str
    http_status: int
    engine: str
    media_type: str = ""
    content_hash: str
    content_length: int
    requested_at: datetime
    storage_path: str
    fetch_duration_ms: int | None = None
    note: str = ""

    def as_source_ref(self) -> SourceRef:
        """Address this stored response, so nothing citing it dangles."""
        return SourceRef(
            kind=SourceKind.HTTP_RESPONSE,
            locator=self.url,
            content_hash=self.content_hash,
            url=self.url,
            retrieved_at=self.requested_at,
        )


class SnapshotStore:
    """Content-addressed, append-only storage for fetched bytes.

    There is no update, delete or overwrite method, and that absence *is* the
    write-once guarantee - not a comment asking callers to behave. Blobs are
    keyed by digest, so storing the same content twice is a no-op on disk while
    still recording a second observation in the manifest.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def manifest_path(self) -> Path:
        return self._root / MANIFEST_NAME

    def path_for(self, content_hash: str) -> Path:
        """Where bytes with this digest live, whether or not they exist yet."""
        if not _HEX_DIGEST.match(content_hash):
            raise ValueError(f"not a sha256 digest: {content_hash!r}")
        return self._root / content_hash[:2] / f"{content_hash}.bin"

    def put(
        self,
        content: bytes,
        *,
        url: str,
        method: str,
        http_status: int,
        engine: str,
        media_type: str = "",
        requested_at: datetime | None = None,
        fetch_duration_ms: int | None = None,
        note: str = "",
    ) -> Snapshot:
        """Record one observation, storing its bytes if they are new.

        Two calls with identical bytes return equal digests and the same
        storage path: the blob is written once, and the manifest gains two
        lines. That is what makes "fetched again, nothing had changed" a
        checkable statement.
        """
        digest = sha256_of(content)
        blob = self.path_for(digest)

        if not blob.exists():
            blob.parent.mkdir(parents=True, exist_ok=True)
            blob.write_bytes(content)

        snapshot = Snapshot(
            url=url,
            method=method,
            http_status=http_status,
            engine=engine,
            media_type=media_type,
            content_hash=digest,
            content_length=len(content),
            requested_at=requested_at or now_utc(),
            storage_path=blob.relative_to(self._root).as_posix(),
            fetch_duration_ms=fetch_duration_ms,
            note=note,
        )

        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(snapshot.model_dump_json() + "\n")

        return snapshot

    def read(self, content_hash: str) -> bytes:
        """The exact bytes stored under this digest."""
        return self.path_for(content_hash).read_bytes()

    def verify(self, content_hash: str) -> bool:
        """Re-hash the stored bytes and confirm they still match.

        A digest nobody ever re-checks proves nothing, so this is what the
        reviewer-facing surfaces call before displaying a hash as verified.
        """
        blob = self.path_for(content_hash)
        if not blob.exists():
            return False
        return sha256_of(blob.read_bytes()) == content_hash

    def blobs(self) -> list[Path]:
        """Every distinct piece of content held, one entry per digest."""
        return sorted(self._root.glob("*/*.bin"))

    def observations(self) -> list[Snapshot]:
        """Every recorded fetch, in the order it happened."""
        if not self.manifest_path.exists():
            return []
        return [
            Snapshot.model_validate_json(line)
            for line in self.manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def snapshots_for(self, url: str) -> list[Snapshot]:
        """Every observation of one URL, oldest first.

        More than one entry means the content was fetched repeatedly; differing
        digests across those entries mean it actually changed between fetches.
        """
        return [entry for entry in self.observations() if entry.url == url]


def default_snapshot_store() -> SnapshotStore:
    """The store the application uses, so no two modules pick different roots."""
    return SnapshotStore(Path(__file__).resolve().parent.parent / "data" / "snapshots")
