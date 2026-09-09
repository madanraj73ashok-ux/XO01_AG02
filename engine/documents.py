"""Where uploaded resumes are kept, and how they are safely fetched back.

Cloudinary when it is configured, local disk otherwise - and, as with the
record store, the active backend is reported rather than assumed. A badge
saying "Cloudinary" over a file sitting in `data/uploads/` would be a small
lie that makes every other claim in the product less believable.

The other job here is not trusting URLs. A candidate supplies a link and the
server fetches it, which is textbook SSRF territory: `http://169.254.169.254/`
is a cloud metadata endpoint, not a resume. `assert_fetchable` refuses
anything that does not resolve to a public address, before any request is
made.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from engine.provenance import sha256_of

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = ROOT / "data" / "uploads"

# Resumes only. An unrestricted upload endpoint is an unrestricted file drop.
ALLOWED_SUFFIXES = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class UploadRejected(ValueError):
    """The file was not something this system is willing to store."""


class UnsafeUrl(ValueError):
    """The URL points somewhere the server must not fetch from."""


class StoredDocument(BaseModel):
    """A resume that has been accepted and stored somewhere retrievable."""

    filename: str
    backend: str
    url: str = ""
    public_id: str = ""
    local_path: str = ""
    content_hash: str
    bytes: int

    @property
    def is_cloud(self) -> bool:
        return self.backend == "cloudinary"


def validate_upload(filename: str, payload: bytes) -> str:
    """Check an upload before it is written anywhere. Returns the suffix."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadRejected(
            f"{suffix or 'this file type'} is not accepted; upload a PDF or an "
            f"image ({', '.join(sorted(ALLOWED_SUFFIXES))})"
        )
    if not payload:
        raise UploadRejected("the uploaded file was empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            f"the file is {len(payload) / 1_048_576:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB"
        )
    return suffix


class LocalDocumentStorage:
    """Content-addressed files on disk."""

    name = "local-disk"

    def __init__(self, root: Path | str = UPLOAD_ROOT) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def store(self, filename: str, payload: bytes) -> StoredDocument:
        suffix = validate_upload(filename, payload)
        digest = sha256_of(payload)
        path = self._root / f"{digest}{suffix}"
        if not path.exists():
            path.write_bytes(payload)

        return StoredDocument(
            filename=filename,
            backend=self.name,
            url=f"/api/files/{digest}{suffix}",
            local_path=str(path),
            content_hash=digest,
            bytes=len(payload),
        )


class CloudinaryStorage:
    """Cloudinary, used only when it is actually configured."""

    name = "cloudinary"

    def __init__(self) -> None:
        import cloudinary
        import cloudinary.uploader

        url = os.environ.get("CLOUDINARY_URL", "").strip()
        cloud = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        key = os.environ.get("CLOUDINARY_API_KEY", "").strip()
        secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip()

        if url:
            cloudinary.config(cloudinary_url=url)
        elif cloud and key and secret:
            cloudinary.config(cloud_name=cloud, api_key=key, api_secret=secret)
        else:
            raise RuntimeError("Cloudinary credentials are not configured")

        self._uploader = cloudinary.uploader

    def store(self, filename: str, payload: bytes) -> StoredDocument:
        validate_upload(filename, payload)
        digest = sha256_of(payload)

        # `raw` rather than `auto`. Cloudinary blocks PDF and ZIP delivery by
        # default on new accounts, so a resume uploaded as an image-type asset
        # uploads fine and then returns 401 when fetched back - the pipeline
        # would hold a URL it cannot read. Raw assets are delivered without
        # that restriction, and raw is the honest description anyway: what we
        # want back is the original bytes, not a transformed image.
        result = self._uploader.upload(
            payload,
            resource_type="raw",
            folder="evidencehire/resumes",
            public_id=digest,
            overwrite=False,
        )

        return StoredDocument(
            filename=filename,
            backend=self.name,
            url=result.get("secure_url", ""),
            public_id=result.get("public_id", ""),
            content_hash=digest,
            bytes=len(payload),
        )


def _build_storage() -> tuple[object, str]:
    if os.environ.get("EVIDENCEHIRE_FORCE_LOCAL_FILES", "").strip() == "1":
        return LocalDocumentStorage(), "local files forced by environment"

    configured = os.environ.get("CLOUDINARY_URL", "").strip() or (
        os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        and os.environ.get("CLOUDINARY_API_KEY", "").strip()
    )
    if not configured:
        return (
            LocalDocumentStorage(),
            "no Cloudinary credentials configured (set CLOUDINARY_URL to use it)",
        )

    try:
        return CloudinaryStorage(), "Cloudinary credentials found and initialised"
    except Exception as error:  # pragma: no cover - depends on deployment
        return (
            LocalDocumentStorage(),
            f"Cloudinary was configured but could not start ({error}); using "
            "local files",
        )


class DocumentStorage:
    """The active document backend, and why it is the active one."""

    def __init__(self) -> None:
        self._backend, self.reason = _build_storage()

    @property
    def backend(self) -> str:
        return self._backend.name

    @property
    def is_cloud(self) -> bool:
        return self._backend.name == "cloudinary"

    def store(self, filename: str, payload: bytes) -> StoredDocument:
        return self._backend.store(filename, payload)


_STORAGE: DocumentStorage | None = None


def get_document_storage() -> DocumentStorage:
    global _STORAGE
    if _STORAGE is None:
        _STORAGE = DocumentStorage()
    return _STORAGE


# --------------------------------------------------------------------------
# Fetching back, safely
# --------------------------------------------------------------------------


def assert_fetchable(url: str) -> None:
    """Refuse any URL that is not a public http(s) address.

    Checked before the request, and against the *resolved* address rather than
    the hostname, because a hostname can resolve to 127.0.0.1 no matter how
    external it looks.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrl(f"only http and https are fetched; got {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeUrl("the URL has no host")

    try:
        resolved = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as error:
        raise UnsafeUrl(f"{parsed.hostname} could not be resolved: {error}") from error

    for entry in resolved:
        address = ipaddress.ip_address(entry[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise UnsafeUrl(
                f"{parsed.hostname} resolves to the non-public address "
                f"{address}, which the server will not fetch"
            )


def read_document(document: StoredDocument, *, timeout: float = 20.0) -> bytes:
    """Get the bytes back, from disk or from the cloud."""
    if document.local_path and Path(document.local_path).exists():
        return Path(document.local_path).read_bytes()

    if not document.url:
        raise FileNotFoundError(f"{document.filename} has no retrievable location")

    assert_fetchable(document.url)
    response = httpx.get(document.url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.content
