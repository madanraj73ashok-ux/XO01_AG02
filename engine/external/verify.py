"""Checking the public links a candidate supplied.

GitHub through its REST API, anything else through Scrapling. Both routes
snapshot the exact bytes they received before interpreting them, so every
conclusion drawn here can be re-checked against a hash on disk.

The governing rule is the one this package exists for: a link that could not
be read produces `UNABLE_TO_VERIFY`, and that is not a finding about the
candidate. Only `PUBLIC` can ever add support. Nothing here can subtract any.

Fetched content is data. A README that says "ignore previous instructions" is
a string in a file, and is treated as one.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from engine.activity import ActivityLog, Outcome, Stage
from engine.documents import UnsafeUrl, assert_fetchable
from engine.external.states import (
    ExternalCheck,
    ExternalSourceKind,
    VerificationState,
    classify,
)
from engine.provenance import SnapshotStore, default_snapshot_store, now_utc

GITHUB_API = "https://api.github.com"
USER_AGENT = "EvidenceHire/1.0 (evidence verification)"
TIMEOUT = 12.0

_GITHUB_PATH = re.compile(
    r"^/(?P<owner>[A-Za-z0-9][A-Za-z0-9-]{0,38})(?:/(?P<repo>[A-Za-z0-9._-]{1,100}))?/?$"
)


def github_token() -> str:
    """The token, if one is configured. Never logged, never returned onward."""
    return os.environ.get("GITHUB_TOKEN", "").strip()


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_rate_limited(response: httpx.Response) -> bool:
    """A 403 that is really a quota problem, not a permission one."""
    if response.status_code not in (403, 429):
        return False
    if response.headers.get("X-RateLimit-Remaining") == "0":
        return True
    if "Retry-After" in response.headers:
        return True
    return "rate limit" in response.text.lower()


def parse_github(url: str) -> tuple[str, str | None] | None:
    """Split a GitHub URL into owner and optional repository."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.netloc.lower().replace("www.", "") != "github.com":
        return None
    match = _GITHUB_PATH.match(parsed.path or "/")
    if not match:
        return None
    return match.group("owner"), match.group("repo")


def check_github(
    url: str, *, store: SnapshotStore | None = None, client: httpx.Client | None = None
) -> ExternalCheck:
    """Verify one GitHub profile or repository."""
    store = store if store is not None else default_snapshot_store()
    parsed = parse_github(url)
    if parsed is None:
        raise ValueError(f"not a GitHub URL: {url}")

    owner, repo = parsed
    target = f"{owner}/{repo}" if repo else owner
    kind = (
        ExternalSourceKind.GITHUB_REPOSITORY
        if repo
        else ExternalSourceKind.GITHUB_PROFILE
    )
    api_url = (
        f"{GITHUB_API}/repos/{owner}/{repo}" if repo else f"{GITHUB_API}/users/{owner}"
    )
    authenticated = bool(github_token())

    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    started = time.perf_counter()

    try:
        response = client.get(api_url, headers=_headers())
    except Exception as error:
        state, note = classify(
            status_code=None, authenticated=authenticated, transport_error=str(error)
        )
        return ExternalCheck(
            target=target,
            kind=kind,
            url=api_url,
            state=state,
            note=note,
            authenticated=authenticated,
            checked_at=now_utc(),
        )
    finally:
        if owns_client:
            client.close()

    elapsed = int((time.perf_counter() - started) * 1000)

    # Snapshot before interpreting: the bytes are the evidence.
    snapshot = store.put(
        response.content,
        url=api_url,
        method="GET",
        http_status=response.status_code,
        engine="github_api",
        media_type=response.headers.get("content-type", ""),
        fetch_duration_ms=elapsed,
    )

    state, note = classify(
        status_code=response.status_code,
        authenticated=authenticated,
        rate_limited=_is_rate_limited(response),
    )

    observed: dict[str, Any] = {}
    if state is VerificationState.PUBLIC:
        try:
            body = response.json()
        except Exception:
            body = {}
        if repo:
            observed = {
                "fullName": body.get("full_name", ""),
                "description": body.get("description") or "",
                "language": body.get("language") or "",
                "topics": body.get("topics") or [],
                "stars": body.get("stargazers_count", 0),
                "forks": body.get("forks_count", 0),
                "isFork": bool(body.get("fork")),
                "archived": bool(body.get("archived")),
                "createdAt": body.get("created_at", ""),
                "pushedAt": body.get("pushed_at", ""),
            }
        else:
            observed = {
                "login": body.get("login", ""),
                "name": body.get("name") or "",
                "publicRepos": body.get("public_repos", 0),
                "createdAt": body.get("created_at", ""),
            }

    return ExternalCheck(
        target=target,
        kind=kind,
        url=api_url,
        state=state,
        note=note,
        authenticated=authenticated,
        checked_at=now_utc(),
        snapshot=snapshot,
        observed=observed,
    )


def check_page(url: str, *, store: SnapshotStore | None = None) -> ExternalCheck:
    """Fetch a non-GitHub public page through Scrapling.

    Scrapling is used for real here rather than declared as a dependency. If it
    is unavailable the check reports `UNABLE_TO_VERIFY` naming that reason,
    rather than silently substituting a plain HTTP get and calling it the same
    thing.
    """
    store = store if store is not None else default_snapshot_store()

    try:
        assert_fetchable(url)
    except UnsafeUrl as error:
        return ExternalCheck(
            target=url,
            kind=ExternalSourceKind.WEB_PAGE,
            url=url,
            state=VerificationState.UNABLE_TO_VERIFY,
            note=f"the URL was refused before any request was made: {error}",
            authenticated=False,
            checked_at=now_utc(),
        )

    started = time.perf_counter()
    try:
        from scrapling.fetchers import Fetcher

        page = Fetcher.get(url, timeout=int(TIMEOUT))
        status = getattr(page, "status", 200)
        body = getattr(page, "body", "") or ""
        content = body.encode("utf-8") if isinstance(body, str) else bytes(body)
        text = page.get_all_text() if hasattr(page, "get_all_text") else ""
    except Exception as error:
        state, note = classify(
            status_code=None, authenticated=False, transport_error=str(error)
        )
        return ExternalCheck(
            target=url,
            kind=ExternalSourceKind.WEB_PAGE,
            url=url,
            state=state,
            note=note,
            authenticated=False,
            checked_at=now_utc(),
        )

    elapsed = int((time.perf_counter() - started) * 1000)
    snapshot = store.put(
        content,
        url=url,
        method="GET",
        http_status=int(status),
        engine="scrapling",
        media_type="text/html",
        fetch_duration_ms=elapsed,
    )
    state, note = classify(status_code=int(status), authenticated=False)

    observed: dict[str, Any] = {}
    if state is VerificationState.PUBLIC:
        # Extracted text only, and explicitly labelled untrusted. Nothing read
        # from a candidate-supplied page is ever executed or followed.
        excerpt = re.sub(r"\s+", " ", str(text)).strip()[:1200]
        observed = {"textExcerpt": excerpt, "untrusted": True}

    return ExternalCheck(
        target=url,
        kind=ExternalSourceKind.WEB_PAGE,
        url=url,
        state=state,
        note=note,
        authenticated=False,
        checked_at=now_utc(),
        snapshot=snapshot,
        observed=observed,
    )


def verify_links(urls: list[str], *, log: ActivityLog | None = None) -> list[dict]:
    """Check every supplied link and return reviewer-facing records."""
    store = default_snapshot_store()
    results: list[dict] = []

    for url in urls:
        try:
            check = (
                check_github(url, store=store)
                if parse_github(url) is not None
                else check_page(url, store=store)
            )
        except Exception as error:  # pragma: no cover - defensive
            check = ExternalCheck(
                target=url,
                kind=ExternalSourceKind.WEB_PAGE,
                url=url,
                state=VerificationState.UNABLE_TO_VERIFY,
                note=f"the check could not be completed: {error}",
                authenticated=False,
                checked_at=now_utc(),
            )

        if log is not None:
            log.emit(
                stage=Stage.EXTERNAL,
                action="verify_link",
                subject=check.target,
                outcome=(
                    Outcome.SUCCEEDED
                    if check.state is VerificationState.PUBLIC
                    else Outcome.INCONCLUSIVE
                ),
                detail=f"{check.state.value}: {check.note}",
                source=check.as_source_ref(),
            )

        results.append(
            {
                "target": check.target,
                "kind": check.kind.value,
                "kindLabel": check.kind.label,
                "url": check.url,
                "state": check.state.value,
                "stateLabel": check.state.label,
                "note": check.note,
                "authenticated": check.authenticated,
                "canCorroborate": check.state.can_corroborate,
                "isNegativeEvidence": check.state.is_negative_evidence,
                "needsHumanReview": check.state.needs_human_review,
                "contentHash": check.content_hash,
                "observed": check.observed,
                "checkedAt": check.checked_at.isoformat(),
            }
        )

    return results
