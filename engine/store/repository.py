"""Two storage backends behind one interface.

Firestore when it is configured, local JSON otherwise. The local backend is a
real store, not a placeholder: the whole product has to remain demonstrable
with no network, and the build plan requires that the offline demo stay
useful.

What matters is that the choice is never hidden. `Store.backend` reports which
one is live and `Store.reason` says why, so the UI can label local persistence
as local rather than implying a cloud write that never happened.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from engine.store.models import Investigation, Job, JobStatus, StoredApplication, User

ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_ROOT = ROOT / "data" / "store"

USERS = "users"
JOBS = "jobs"
APPLICATIONS = "applications"
INVESTIGATIONS = "investigations"
ASSESSMENTS = "assessments"


class LocalBackend:
    """JSON documents on disk, one file per record.

    Human-inspectable on purpose, for the same reason the rest of this project
    stores readable JSON: a reviewer can open the file and check what the
    system actually holds.
    """

    name = "local-json"

    def __init__(self, root: Path | str = LOCAL_ROOT) -> None:
        self._root = Path(root)
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, collection: str, doc_id: str) -> Path:
        folder = self._root / collection
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{doc_id}.json"

    def put(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._path(collection, doc_id).write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        path = self._path(collection, doc_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, collection: str) -> list[dict[str, Any]]:
        folder = self._root / collection
        if not folder.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("*.json"))
        ]


class FirestoreBackend:
    """Google Firestore via firebase-admin.

    Constructed only when credentials are actually present. Raising here is
    the point: the factory catches it and falls back, rather than leaving the
    product half-connected to a database that will fail on first write.
    """

    name = "firestore"

    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            if path and Path(path).exists():
                firebase_admin.initialize_app(credentials.Certificate(path))
            else:
                firebase_admin.initialize_app()

        self._db = firestore.client()

    def put(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        self._db.collection(collection).document(doc_id).set(data)

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snapshot = self._db.collection(collection).document(doc_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list(self, collection: str) -> list[dict[str, Any]]:
        return [doc.to_dict() for doc in self._db.collection(collection).stream()]


def _build_backend() -> tuple[Any, str]:
    """Pick a backend, and remember why."""
    if os.environ.get("EVIDENCEHIRE_FORCE_LOCAL_STORE", "").strip() == "1":
        return LocalBackend(), "local store forced by EVIDENCEHIRE_FORCE_LOCAL_STORE"

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    project = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    if not credentials_path and not project:
        return (
            LocalBackend(),
            "no Firebase credentials configured (set GOOGLE_APPLICATION_CREDENTIALS "
            "or FIREBASE_PROJECT_ID to use Firestore)",
        )

    try:
        return FirestoreBackend(), "Firestore credentials found and initialised"
    except Exception as error:  # pragma: no cover - depends on deployment
        return (
            LocalBackend(),
            f"Firestore was configured but could not be initialised ({error}); "
            "falling back to the local store",
        )


class Store:
    """Typed access to the product's records."""

    def __init__(self, backend: Any | None = None, reason: str = "") -> None:
        if backend is None:
            backend, reason = _build_backend()
        self._backend = backend
        self.reason = reason

    @property
    def backend(self) -> str:
        return self._backend.name

    @property
    def is_cloud(self) -> bool:
        return self._backend.name == "firestore"

    # -- users ------------------------------------------------------------

    def save_user(self, user: User) -> User:
        self._backend.put(USERS, user.uid, user.model_dump(mode="json"))
        return user

    def user(self, uid: str) -> User | None:
        raw = self._backend.get(USERS, uid)
        return User.model_validate(raw) if raw else None

    # -- jobs -------------------------------------------------------------

    def save_job(self, job: Job) -> Job:
        self._backend.put(JOBS, job.id, job.model_dump(mode="json"))
        return job

    def job(self, job_id: str) -> Job | None:
        raw = self._backend.get(JOBS, job_id)
        return Job.model_validate(raw) if raw else None

    def jobs(
        self, *, recruiter_id: str | None = None, published_only: bool = False
    ) -> list[Job]:
        found = [Job.model_validate(raw) for raw in self._backend.list(JOBS)]
        if recruiter_id is not None:
            found = [job for job in found if job.recruiter_id == recruiter_id]
        if published_only:
            found = [job for job in found if job.status is JobStatus.PUBLISHED]
        return sorted(found, key=lambda job: job.created_at, reverse=True)

    # -- applications -----------------------------------------------------

    def save_application(self, application: StoredApplication) -> StoredApplication:
        self._backend.put(
            APPLICATIONS, application.id, application.model_dump(mode="json")
        )
        return application

    def application(self, application_id: str) -> StoredApplication | None:
        raw = self._backend.get(APPLICATIONS, application_id)
        return StoredApplication.model_validate(raw) if raw else None

    def applications(
        self, *, job_id: str | None = None, candidate_uid: str | None = None
    ) -> list[StoredApplication]:
        found = [
            StoredApplication.model_validate(raw)
            for raw in self._backend.list(APPLICATIONS)
        ]
        if job_id is not None:
            found = [entry for entry in found if entry.job_id == job_id]
        if candidate_uid is not None:
            found = [entry for entry in found if entry.candidate_uid == candidate_uid]
        return sorted(found, key=lambda entry: entry.created_at, reverse=True)

    # -- investigations ---------------------------------------------------

    def save_investigation(self, investigation: Investigation) -> Investigation:
        self._backend.put(
            INVESTIGATIONS, investigation.id, investigation.model_dump(mode="json")
        )
        return investigation

    def investigation(self, investigation_id: str) -> Investigation | None:
        raw = self._backend.get(INVESTIGATIONS, investigation_id)
        return Investigation.model_validate(raw) if raw else None

    # -- assessments ------------------------------------------------------

    def save_assessment(self, application_id: str, payload: dict[str, Any]) -> None:
        self._backend.put(ASSESSMENTS, application_id, payload)

    def assessment(self, application_id: str) -> dict[str, Any] | None:
        return self._backend.get(ASSESSMENTS, application_id)


_STORE: Store | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> Store:
    """The process-wide store, built once."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE
