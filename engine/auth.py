"""Who is calling, and what they are allowed to do.

Firebase ID tokens are verified properly when Firebase is configured. When it
is not, a clearly-labelled development identity is accepted instead so the
product stays runnable - but that mode is reported in every `Principal` it
issues and through `/api/config`.

The distinction matters more than it looks. A demo that silently accepts
`Authorization: Bearer dev:someone` while claiming to use Firebase
authentication is exactly the kind of unverified claim this whole project is
built to argue against.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel

from engine.store.models import Role

DEV_TOKEN_PREFIX = "dev:"

# Tolerance for local clock drift when validating a token's issued-at time.
CLOCK_SKEW_SECONDS = 60


class AuthError(Exception):
    """The caller could not be authenticated."""


class Principal(BaseModel):
    """An authenticated caller.

    `method` is either `firebase` or `development`, and is surfaced to the UI.
    `verified` is True only when a real identity provider vouched for the uid.
    """

    uid: str
    email: str = ""
    name: str = ""
    role: Role = Role.JOB_SEEKER
    method: str = "development"
    verified: bool = False

    @property
    def is_recruiter(self) -> bool:
        return self.role is Role.RECRUITER


@lru_cache(maxsize=1)
def firebase_enabled() -> bool:
    """Whether real token verification is available."""
    if os.environ.get("EVIDENCEHIRE_FORCE_DEV_AUTH", "").strip() == "1":
        return False
    if not (
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        or os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    ):
        return False
    try:
        # google-auth is enough for the verify-only path; the Admin SDK is
        # only needed when a service account is configured.
        from google.oauth2 import id_token  # noqa: F401
    except Exception:
        return False
    return True


def auth_mode() -> str:
    return "firebase" if firebase_enabled() else "development"


def _verify_with_service_account(token: str) -> dict:
    """Full Admin SDK verification, when a service account is configured."""
    import firebase_admin
    from firebase_admin import auth, credentials

    if not firebase_admin._apps:
        path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"].strip()
        firebase_admin.initialize_app(credentials.Certificate(path))

    return auth.verify_id_token(token)


def _verify_with_project_id(token: str, project: str) -> dict:
    """Verify an ID token using only the project id.

    A Firebase ID token is a JWT signed by Google. Checking it needs the
    project id (the audience) and Google's public signing certificates, which
    are served from a public endpoint - it does not need a service account.
    `firebase_admin.initialize_app` insists on a credential it can resolve
    even when the operation would not use one, so this path uses google-auth's
    Firebase verifier directly rather than working around the SDK.

    The signature, issuer, audience and expiry are all checked by the library.
    Nothing here trusts an unverified claim.
    """
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    # A little leeway on the clock. This machine's time drifts a few seconds
    # from Google's, which is enough to make a token that was just issued look
    # like it comes from the future and be rejected as "used too early". Sixty
    # seconds is the conventional allowance for JWT validation and does not
    # meaningfully widen the window an expired token could be replayed in.
    return id_token.verify_firebase_token(
        token,
        google_requests.Request(),
        audience=project,
        clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
    )


def _verify_firebase(token: str) -> Principal:
    project = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    has_service_account = bool(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )

    try:
        claims = (
            _verify_with_service_account(token)
            if has_service_account
            else _verify_with_project_id(token, project)
        )
    except Exception as error:
        raise AuthError(f"the Firebase ID token was rejected: {error}") from error

    if not claims:
        raise AuthError("the Firebase ID token carried no claims")

    # `sub` is the subject in a raw JWT; the Admin SDK spells it `uid`.
    uid = claims.get("uid") or claims.get("sub") or ""
    if not uid:
        raise AuthError("the Firebase ID token identified no user")

    return Principal(
        uid=uid,
        email=claims.get("email", ""),
        name=claims.get("name", ""),
        # The role lives in our own user record, not in the token, so a client
        # cannot promote itself to recruiter by editing a claim it controls.
        # Callers overlay the stored role after verification.
        role=Role.JOB_SEEKER,
        method="firebase",
        verified=True,
    )


def _verify_development(token: str) -> Principal:
    """Accept `dev:<uid>:<ROLE>[:<name>]`, and never pretend it was verified."""
    if not token.startswith(DEV_TOKEN_PREFIX):
        raise AuthError(
            "development auth expects a token of the form "
            "'dev:<uid>:<RECRUITER|JOB_SEEKER>'"
        )

    parts = token[len(DEV_TOKEN_PREFIX) :].split(":")
    if len(parts) < 2 or not parts[0]:
        raise AuthError("development token is missing a uid or a role")

    try:
        role = Role(parts[1].strip().upper())
    except ValueError as error:
        raise AuthError(f"unknown role {parts[1]!r}") from error

    name = parts[2] if len(parts) > 2 else parts[0]
    return Principal(
        uid=parts[0],
        name=name,
        email=f"{parts[0]}@demo.invalid",
        role=role,
        method="development",
        verified=False,
    )


def verify_token(token: str) -> Principal:
    """Authenticate a bearer token using whichever mode is actually active."""
    token = (token or "").strip()
    if not token:
        raise AuthError("no credentials were supplied")

    if firebase_enabled():
        return _verify_firebase(token)
    return _verify_development(token)
