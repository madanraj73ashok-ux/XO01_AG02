"""Product-level records: users, jobs, applications, investigations.

These are deliberately separate from `engine/models.py`. That module holds the
screening domain - claims, evidence, fits - and must stay usable without any
notion of accounts or storage. This one holds the things a two-sided product
needs in order to have two sides.

The one type here that carries real weight is `InvestigationStep`. The UI
timeline renders these and nothing else, so a step can only reach `DONE` when
the backend stage that owns it actually finished. There is no code path that
advances the timeline on a timer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from engine.provenance import now_utc


def new_id(prefix: str) -> str:
    """Short, readable, collision-safe identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Role(str, Enum):
    """Which side of the product a user is on."""

    RECRUITER = "RECRUITER"
    JOB_SEEKER = "JOB_SEEKER"

    @property
    def home_route(self) -> str:
        return "/recruiter" if self is Role.RECRUITER else "/jobs"


class User(BaseModel):
    """An authenticated account.

    `uid` comes from the identity provider, never from us. Nothing here is
    used in screening: a candidate's account details must not reach the
    evidence engine, which assesses documents and nothing else.
    """

    uid: str
    email: str = ""
    name: str = ""
    role: Role = Role.JOB_SEEKER
    photo_url: str = ""
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class SkillSpec(BaseModel):
    """One skill a job asks for, and optionally how long for."""

    skill: str
    min_years: float | None = None


class JobStatus(str, Enum):
    """Where a requisition is in the recruiter's own workflow.

    `ANALYZED` is distinct from `PUBLISHED` on purpose: a requisition whose
    conflicts have been surfaced but not yet resolved must not be silently
    visible to candidates.
    """

    DRAFT = "draft"
    ANALYZED = "analyzed"
    PUBLISHED = "published"
    CLOSED = "closed"


class Job(BaseModel):
    """A requisition as the recruiter authored it.

    Kept as the recruiter's own words. The structured `Requisition` the engine
    screens against is derived from this on demand rather than stored, so the
    original text can never drift out of step with what is being assessed.
    """

    id: str = Field(default_factory=lambda: new_id("job"))
    recruiter_id: str
    title: str
    company: str = ""
    description: str = ""
    location: str = ""
    job_type: str = "full_time"
    seniority: str = "junior"
    required_skills: list[SkillSpec] = Field(default_factory=list)
    preferred_skills: list[SkillSpec] = Field(default_factory=list)
    min_years_total: float | None = None
    max_salary_lpa: float | None = None
    status: JobStatus = JobStatus.DRAFT
    conflicts_acknowledged: bool = False
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    published_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status is JobStatus.PUBLISHED


class ApplicationStatus(str, Enum):
    """Where one candidate's application has got to."""

    SUBMITTED = "submitted"
    INVESTIGATING = "investigating"
    ASSESSED = "assessed"
    FAILED = "failed"


class StoredApplication(BaseModel):
    """A candidate's submission against one job.

    The resume itself lives in document storage; only a reference is kept
    here. `storage_backend` records which store actually holds it, so a
    reviewer is never shown a Cloudinary badge for a file that is sitting on
    local disk.
    """

    id: str = Field(default_factory=lambda: new_id("app"))
    job_id: str
    candidate_uid: str
    candidate_name: str = ""
    email: str = ""
    resume_url: str = ""
    resume_filename: str = ""
    resume_public_id: str = ""
    storage_backend: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    status: ApplicationStatus = ApplicationStatus.SUBMITTED
    investigation_id: str = ""
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class InvestigationState(str, Enum):
    """The overall phase of one investigation."""

    RECEIVED = "RECEIVED"
    EXTRACTING = "EXTRACTING"
    STRUCTURING = "STRUCTURING"
    ANALYZING = "ANALYZING"
    INVESTIGATING = "INVESTIGATING"
    VERIFYING = "VERIFYING"
    ASSESSING = "ASSESSING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (InvestigationState.COMPLETE, InvestigationState.FAILED)


class StepState(str, Enum):
    """How one timeline step stands.

    `SKIPPED` exists so an investigation that could not run a stage - no GitHub
    URL was supplied, the network was down - shows that plainly instead of
    leaving a step that never resolves, or worse, ticking it.
    """

    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationStep(BaseModel):
    """One line of the investigation timeline the candidate watches.

    Only advanced by the stage that owns it, when that stage actually
    finishes. The build plan is explicit that this screen must reflect real
    backend progress, so there is deliberately no way to set these from a
    timer or from the frontend.
    """

    key: str
    label: str
    state: StepState = StepState.PENDING
    detail: str = ""
    at: datetime | None = None


class Investigation(BaseModel):
    """One run of the pipeline over one application.

    `error_code` uses the vocabulary from the build plan's error-state list
    (OCR_FAILED, GITHUB_RATE_LIMITED, LLM_UNAVAILABLE and so on) so a failure
    is reported as the specific thing that went wrong rather than as a generic
    problem.
    """

    id: str = Field(default_factory=lambda: new_id("inv"))
    application_id: str
    job_id: str
    candidate_uid: str = ""
    state: InvestigationState = InvestigationState.RECEIVED
    steps: list[InvestigationStep] = Field(default_factory=list)
    document_id: str = ""
    error_code: str = ""
    error_detail: str = ""
    started_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    completed_at: datetime | None = None

    def step(self, key: str) -> InvestigationStep | None:
        return next((entry for entry in self.steps if entry.key == key), None)

    @property
    def progress(self) -> float:
        """Fraction of steps that have actually resolved.

        Skipped steps count as resolved - the pipeline is not still waiting on
        them - and so do failed ones, because the run has moved past them.
        """
        if not self.steps:
            return 0.0
        resolved = sum(
            1
            for entry in self.steps
            if entry.state in (StepState.DONE, StepState.SKIPPED, StepState.FAILED)
        )
        return resolved / len(self.steps)
