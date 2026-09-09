"""What we actually established about an external source, and how we decided.

Four states, deliberately not collapsible into a boolean. Three of them mean
"not confirmed present", and only one of those three is an authoritative
negative:

    PUBLIC                 we read it
    PRIVATE_AUTH_REQUIRED  it is there, and we are not allowed to see it
    NOT_FOUND              an authorised request was told it does not exist
    UNABLE_TO_VERIFY       we did not establish anything either way

The distinction that does the most work is the 404. GitHub answers 404 to an
unauthenticated caller for a *private* repository as well as a missing one, so
an unauthenticated 404 carries no information about which it was. Reporting it
as NOT_FOUND would manufacture a finding out of our own lack of credentials.
Authenticated, the same 404 is meaningful, and is reported as NOT_FOUND.

The second distinction is 403. A rate-limited 403 says something about our own
quota, not about the repository's visibility, so it maps to UNABLE_TO_VERIFY
and never to PRIVATE_AUTH_REQUIRED.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from engine.provenance import Snapshot, SourceRef

UNAUTHENTICATED_404_NOTE = (
    "an unauthenticated request cannot distinguish a private repository from a "
    "missing one - GitHub answers 404 to both, so nothing was established"
)


class VerificationState(str, Enum):
    """What we established about an external source.

    Merging any two of these would let one situation read as another: a
    timeout as a missing repository, or a rate limit as a private one. Both
    misreadings would reach a recruiter looking like a fact about the
    candidate.
    """

    PUBLIC = "public"
    PRIVATE_AUTH_REQUIRED = "private_auth_required"
    NOT_FOUND = "not_found"
    UNABLE_TO_VERIFY = "unable_to_verify"

    @property
    def label(self) -> str:
        return _STATE_LABELS[self]

    @property
    def is_negative_evidence(self) -> bool:
        """Always False. Present so the rule is greppable and testable.

        No verification state is evidence against a candidate. `NOT_FOUND`
        raises a discrepancy for a human to review - a repository may have been
        renamed, made private, or transferred - and it never lowers a grade.
        """
        return False

    @property
    def can_corroborate(self) -> bool:
        """Whether this state can raise an assessment.

        Only `PUBLIC` can. Knowing a repository exists but cannot be read tells
        us nothing about what is in it, so `PRIVATE_AUTH_REQUIRED` is recorded
        for the reviewer and contributes no uplift.
        """
        return self is VerificationState.PUBLIC

    @property
    def needs_human_review(self) -> bool:
        """Whether a reviewer should look at this themselves."""
        return self in (
            VerificationState.NOT_FOUND,
            VerificationState.PRIVATE_AUTH_REQUIRED,
        )


_STATE_LABELS: dict[VerificationState, str] = {
    VerificationState.PUBLIC: "Public - content retrieved",
    VerificationState.PRIVATE_AUTH_REQUIRED: "Private - authentication required",
    VerificationState.NOT_FOUND: "Not found at the URL given",
    VerificationState.UNABLE_TO_VERIFY: "Unable to verify",
}


class ExternalSourceKind(str, Enum):
    """What sort of thing was checked."""

    GITHUB_REPOSITORY = "github_repository"
    GITHUB_PROFILE = "github_profile"
    WEB_PAGE = "web_page"

    @property
    def label(self) -> str:
        return _KIND_LABELS[self]


_KIND_LABELS: dict[ExternalSourceKind, str] = {
    ExternalSourceKind.GITHUB_REPOSITORY: "GitHub repository",
    ExternalSourceKind.GITHUB_PROFILE: "GitHub profile",
    ExternalSourceKind.WEB_PAGE: "Web page",
}


class ExternalCheck(BaseModel):
    """One attempt to verify one external source, and what came of it.

    Frozen. `snapshot` is the stored bytes the conclusion rests on, so a
    reviewer can re-hash the response rather than take this record's word for
    it. `observed` is populated only when the content was actually read - there
    is nothing to observe about a page we could not fetch.
    """

    model_config = ConfigDict(frozen=True)

    target: str
    kind: ExternalSourceKind
    url: str
    state: VerificationState
    note: str
    authenticated: bool
    checked_at: datetime
    snapshot: Snapshot | None = None
    observed: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str | None:
        return self.snapshot.content_hash if self.snapshot else None

    def as_source_ref(self) -> SourceRef | None:
        """The citable reference for this check, when bytes were stored."""
        return self.snapshot.as_source_ref() if self.snapshot else None


def classify(
    *,
    status_code: int | None,
    authenticated: bool,
    rate_limited: bool = False,
    transport_error: str | None = None,
) -> tuple[VerificationState, str]:
    """Decide what an HTTP outcome actually established.

    Returns the state and the sentence explaining it, because a state shown
    without its reasoning is exactly the kind of unexplained verdict this
    project refuses to produce.
    """
    if transport_error is not None:
        return (
            VerificationState.UNABLE_TO_VERIFY,
            f"the request did not complete: {transport_error}",
        )

    if status_code is None:
        return (VerificationState.UNABLE_TO_VERIFY, "no response was received")

    if 200 <= status_code < 300:
        return (
            VerificationState.PUBLIC,
            f"the resource was retrieved successfully (HTTP {status_code})",
        )

    if rate_limited:
        return (
            VerificationState.UNABLE_TO_VERIFY,
            f"the request was rate limited (HTTP {status_code}); this says "
            "nothing about whether the resource exists",
        )

    if status_code == 401:
        return (
            VerificationState.PRIVATE_AUTH_REQUIRED,
            "the server requires authentication for this resource (HTTP 401)",
        )

    if status_code == 403:
        return (
            VerificationState.PRIVATE_AUTH_REQUIRED,
            "access to this resource is forbidden with the credentials used "
            "(HTTP 403)",
        )

    if status_code == 404:
        if authenticated:
            return (
                VerificationState.NOT_FOUND,
                "an authenticated request was told this resource does not "
                "exist (HTTP 404); it may have been renamed, deleted or "
                "transferred, so this is a discrepancy to review rather than a "
                "finding about the candidate",
            )
        return (VerificationState.UNABLE_TO_VERIFY, UNAUTHENTICATED_404_NOTE)

    if 500 <= status_code < 600:
        return (
            VerificationState.UNABLE_TO_VERIFY,
            f"the server failed to answer (HTTP {status_code})",
        )

    return (
        VerificationState.UNABLE_TO_VERIFY,
        f"the response (HTTP {status_code}) did not establish anything",
    )
