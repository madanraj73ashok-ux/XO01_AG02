"""Persistence for the two-sided product.

The screening engine is pure: applications in, assessments out. Everything
this package holds is the surrounding product state - who the recruiter is,
which job they published, which candidate applied, and how far their
investigation has run.

Two backends implement the same interface. Firestore is used when it is
configured; a local JSON store is used otherwise. The fallback is not a stub -
it is a working store that keeps the whole product usable offline, which is
what the demo actually depends on. Whichever is live says so out loud through
`Store.backend`, so no screen can imply cloud persistence that is not running.
"""

from engine.store.models import (
    ApplicationStatus,
    Investigation,
    InvestigationState,
    InvestigationStep,
    Job,
    JobStatus,
    Role,
    SkillSpec,
    StepState,
    StoredApplication,
    User,
)
from engine.store.repository import Store, get_store

__all__ = [
    "ApplicationStatus",
    "Investigation",
    "InvestigationState",
    "InvestigationStep",
    "Job",
    "JobStatus",
    "Role",
    "SkillSpec",
    "StepState",
    "Store",
    "StoredApplication",
    "User",
    "get_store",
]
