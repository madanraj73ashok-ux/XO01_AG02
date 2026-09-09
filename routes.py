"""The product API: recruiters, candidates, applications, investigations.

Additive to `api.py`. Every route the original console depends on keeps its
shape; these sit alongside them and cover the two-sided product.

Two things here are deliberate rather than incidental.

`/api/config` reports which backends are actually live - Firebase or the local
store, Cloudinary or local disk. The UI renders that verbatim, so a demo can
never imply cloud persistence it does not have.

The investigation stream sends real state. It polls the stored investigation
record and forwards it when it changes; if the pipeline stalls, the stream
stalls with it. Nothing on the client advances a step on a timer.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from engine.activity import ActivityLog
from engine.assessment import assess_pool
from engine.auth import AuthError, Principal, auth_mode, verify_token
from engine.documents import UPLOAD_ROOT, UploadRejected, get_document_storage
from engine.investigation import InvestigationRunner, support_level
from engine.jobs import analyze_job, to_requisition
from engine.models import Application, Section, SectionKind
from engine.poolgap import analyse_pool, gaps
from engine.provenance import now_utc
from engine.store import (
    ApplicationStatus,
    Job,
    JobStatus,
    Role,
    SkillSpec,
    StoredApplication,
    User,
    get_store,
)
from engine.tradeoffs import build_shortlist, compare, full_requisition_message

router = APIRouter()

ROOT = Path(__file__).resolve().parent
ACTIVITY_LOG = ActivityLog(ROOT / "data" / "activity" / "events.jsonl")
_RUNNER: InvestigationRunner | None = None

_UPLOAD_NAME = re.compile(r"^[0-9a-f]{64}\.[A-Za-z0-9]{2,5}$")


def runner() -> InvestigationRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = InvestigationRunner(get_store(), ACTIVITY_LOG)
    return _RUNNER


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


def current_user(authorization: str = Header(default="")) -> Principal:
    """Authenticate the caller and overlay the role we hold for them.

    The role is read from our own user record rather than from the token. A
    client that could name its own role could promote itself to recruiter and
    read every candidate's assessment.
    """
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    try:
        principal = verify_token(token)
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error

    stored = get_store().user(principal.uid)
    if stored is not None:
        principal = principal.model_copy(update={"role": stored.role})
    return principal


def recruiter_only(principal: Principal = Depends(current_user)) -> Principal:
    if not principal.is_recruiter:
        raise HTTPException(
            status_code=403, detail="this action is available to recruiters only"
        )
    return principal


class SessionRequest(BaseModel):
    name: str = ""
    email: str = ""
    role: Role = Role.JOB_SEEKER


@router.get("/api/config")
def configuration() -> dict[str, Any]:
    """What is actually running, so the UI never overstates it."""
    store = get_store()
    storage = get_document_storage()
    return {
        "authMode": auth_mode(),
        "authIsVerified": auth_mode() == "firebase",
        "storeBackend": store.backend,
        "storeReason": store.reason,
        "fileBackend": storage.backend,
        "fileReason": storage.reason,
    }


@router.post("/api/auth/session")
def open_session(
    body: SessionRequest, principal: Principal = Depends(current_user)
) -> dict[str, Any]:
    """Create or refresh the caller's user record and settle their role."""
    store = get_store()
    existing = store.user(principal.uid)

    user = User(
        uid=principal.uid,
        email=body.email or principal.email,
        name=body.name or principal.name,
        # A role, once set, is not reassignable by the client on a later call.
        role=existing.role if existing else body.role,
        created_at=existing.created_at if existing else now_utc(),
        updated_at=now_utc(),
    )
    store.save_user(user)
    return {
        "uid": user.uid,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "home": user.role.home_route,
        "authMode": principal.method,
        "verified": principal.verified,
    }


@router.get("/api/me")
def me(principal: Principal = Depends(current_user)) -> dict[str, Any]:
    return {
        "uid": principal.uid,
        "name": principal.name,
        "email": principal.email,
        "role": principal.role.value,
        "authMode": principal.method,
        "verified": principal.verified,
    }


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


class JobRequest(BaseModel):
    title: str
    company: str = ""
    description: str = ""
    location: str = ""
    job_type: str = "full_time"
    seniority: str = "junior"
    required_skills: list[SkillSpec] = []
    preferred_skills: list[SkillSpec] = []
    min_years_total: float | None = None
    max_salary_lpa: float | None = None


def _job_payload(job: Job, *, analyzed: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "description": job.description,
        "location": job.location,
        "jobType": job.job_type,
        "seniority": job.seniority,
        "requiredSkills": [spec.model_dump() for spec in job.required_skills],
        "preferredSkills": [spec.model_dump() for spec in job.preferred_skills],
        "minYearsTotal": job.min_years_total,
        "maxSalaryLpa": job.max_salary_lpa,
        "status": job.status.value,
        "recruiterId": job.recruiter_id,
        "createdAt": job.created_at.isoformat(),
        "publishedAt": job.published_at.isoformat() if job.published_at else None,
    }

    if analyzed:
        analysis = analyze_job(job)
        payload["requirements"] = [
            {
                "id": requirement.id,
                "skill": requirement.skill,
                "necessity": requirement.necessity.value,
                "minYears": requirement.min_years,
                "maxSalaryLpa": requirement.max_salary_lpa,
                "description": requirement.description,
            }
            for requirement in analysis.requisition.requirements
        ]
        payload["conflicts"] = [
            {
                "kind": conflict.kind.value,
                "requirementIds": conflict.requirement_ids,
                "detail": conflict.detail,
                "recommendation": conflict.recommendation,
            }
            for conflict in analysis.conflicts
        ]
    return payload


@router.post("/api/jobs")
def create_job(
    body: JobRequest, principal: Principal = Depends(recruiter_only)
) -> dict[str, Any]:
    job = Job(recruiter_id=principal.uid, **body.model_dump())
    get_store().save_job(job)
    return _job_payload(job)


@router.get("/api/jobs")
def list_jobs(principal: Principal = Depends(current_user)) -> list[dict[str, Any]]:
    """Recruiters see their own requisitions; candidates see published ones."""
    store = get_store()
    if principal.is_recruiter:
        found = store.jobs(recruiter_id=principal.uid)
    else:
        found = store.jobs(published_only=True)
    return [_job_payload(job, analyzed=False) for job in found]


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, principal: Principal = Depends(current_user)) -> dict[str, Any]:
    job = get_store().job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")
    if not principal.is_recruiter and job.status is not JobStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")
    return _job_payload(job)


@router.post("/api/jobs/{job_id}/analyze")
def analyze(job_id: str, principal: Principal = Depends(recruiter_only)) -> dict[str, Any]:
    """Structure the requisition and surface conflicts without resolving them."""
    store = get_store()
    job = store.job(job_id)
    if job is None or job.recruiter_id != principal.uid:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")

    if job.status is JobStatus.DRAFT:
        job.status = JobStatus.ANALYZED
        job.updated_at = now_utc()
        store.save_job(job)

    return _job_payload(job)


@router.post("/api/jobs/{job_id}/publish")
def publish(
    job_id: str,
    acknowledge_conflicts: bool = False,
    principal: Principal = Depends(recruiter_only),
) -> dict[str, Any]:
    """Publish, but not over an unacknowledged conflict.

    The conflict is not resolved for the recruiter and it is not ignored. They
    must say explicitly that they have seen it, which is what "recruiter review
    required" has to mean if it means anything.
    """
    store = get_store()
    job = store.job(job_id)
    if job is None or job.recruiter_id != principal.uid:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")

    analysis = analyze_job(job)
    if analysis.has_conflicts and not acknowledge_conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "This requisition has an unresolved conflict. Review it, then "
                    "publish again confirming you have seen it."
                ),
                "conflicts": [
                    {
                        "kind": conflict.kind.value,
                        "detail": conflict.detail,
                        "recommendation": conflict.recommendation,
                    }
                    for conflict in analysis.conflicts
                ],
            },
        )

    job.status = JobStatus.PUBLISHED
    job.conflicts_acknowledged = analysis.has_conflicts
    job.published_at = now_utc()
    job.updated_at = now_utc()
    store.save_job(job)
    return _job_payload(job)


# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------


def _application_payload(record: StoredApplication) -> dict[str, Any]:
    assessment = get_store().assessment(record.id)
    return {
        "id": record.id,
        "jobId": record.job_id,
        "candidateUid": record.candidate_uid,
        "candidateName": record.candidate_name,
        "email": record.email,
        "resumeFilename": record.resume_filename,
        "resumeUrl": record.resume_url,
        "storageBackend": record.storage_backend,
        "githubUrl": record.github_url,
        "portfolioUrl": record.portfolio_url,
        "status": record.status.value,
        "investigationId": record.investigation_id,
        "createdAt": record.created_at.isoformat(),
        "level": assessment.get("level") if assessment else None,
        "levelLabel": assessment.get("levelLabel") if assessment else None,
        "requiredSupported": assessment.get("requiredSupported") if assessment else None,
        "requiredTotal": assessment.get("requiredTotal") if assessment else None,
    }


@router.post("/api/applications")
async def submit_application(
    job_id: str = Form(...),
    candidate_name: str = Form(""),
    email: str = Form(""),
    github_url: str = Form(""),
    portfolio_url: str = Form(""),
    resume: UploadFile = File(...),
    principal: Principal = Depends(current_user),
) -> dict[str, Any]:
    """Accept a resume, store it, and register the application."""
    store = get_store()
    job = store.job(job_id)
    if job is None or job.status is not JobStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="that job is not open")

    payload = await resume.read()
    try:
        document = get_document_storage().store(resume.filename or "resume.pdf", payload)
    except UploadRejected as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    record = StoredApplication(
        job_id=job_id,
        candidate_uid=principal.uid,
        candidate_name=candidate_name or principal.name,
        email=email or principal.email,
        resume_url=document.url,
        resume_filename=document.filename,
        resume_public_id=document.public_id,
        storage_backend=document.backend,
        github_url=github_url.strip(),
        portfolio_url=portfolio_url.strip(),
    )
    store.save_application(record)
    return _application_payload(record)


@router.get("/api/applications")
def list_applications(
    job_id: str | None = None, principal: Principal = Depends(current_user)
) -> list[dict[str, Any]]:
    store = get_store()
    if principal.is_recruiter:
        if job_id is None:
            owned = {job.id for job in store.jobs(recruiter_id=principal.uid)}
            found = [record for record in store.applications() if record.job_id in owned]
        else:
            job = store.job(job_id)
            if job is None or job.recruiter_id != principal.uid:
                raise HTTPException(status_code=404, detail=f"no job {job_id}")
            found = store.applications(job_id=job_id)
    else:
        found = store.applications(candidate_uid=principal.uid)
        if job_id is not None:
            found = [record for record in found if record.job_id == job_id]

    return [_application_payload(record) for record in found]


def _authorised_application(
    application_id: str, principal: Principal
) -> StoredApplication:
    store = get_store()
    record = store.application(application_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no application {application_id}")

    if principal.is_recruiter:
        job = store.job(record.job_id)
        if job is None or job.recruiter_id != principal.uid:
            raise HTTPException(status_code=403, detail="not your requisition")
    elif record.candidate_uid != principal.uid:
        raise HTTPException(status_code=403, detail="not your application")

    return record


@router.get("/api/applications/{application_id}")
def get_application(
    application_id: str, principal: Principal = Depends(current_user)
) -> dict[str, Any]:
    return _application_payload(_authorised_application(application_id, principal))


@router.post("/api/applications/{application_id}/investigate")
def investigate(
    application_id: str, principal: Principal = Depends(current_user)
) -> dict[str, Any]:
    """Start the pipeline. Returns at once; progress arrives over the stream."""
    record = _authorised_application(application_id, principal)
    investigation = runner().start(record.id)
    return _investigation_payload(investigation.id)


# --------------------------------------------------------------------------
# Investigations
# --------------------------------------------------------------------------


def _investigation_payload(investigation_id: str) -> dict[str, Any]:
    investigation = get_store().investigation(investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail=f"no investigation {investigation_id}")
    return {
        "id": investigation.id,
        "applicationId": investigation.application_id,
        "jobId": investigation.job_id,
        "state": investigation.state.value,
        "isTerminal": investigation.state.is_terminal,
        "progress": round(investigation.progress, 3),
        "errorCode": investigation.error_code,
        "errorDetail": investigation.error_detail,
        "documentId": investigation.document_id,
        "startedAt": investigation.started_at.isoformat(),
        "completedAt": (
            investigation.completed_at.isoformat() if investigation.completed_at else None
        ),
        "steps": [
            {
                "key": step.key,
                "label": step.label,
                "state": step.state.value,
                "detail": step.detail,
                "at": step.at.isoformat() if step.at else None,
            }
            for step in investigation.steps
        ],
    }


@router.get("/api/investigations/{investigation_id}")
def get_investigation(
    investigation_id: str, principal: Principal = Depends(current_user)
) -> dict[str, Any]:
    payload = _investigation_payload(investigation_id)
    _authorised_application(payload["applicationId"], principal)
    return payload


@router.get("/api/investigations/{investigation_id}/stream")
async def stream_investigation(
    investigation_id: str, token: str = ""
) -> StreamingResponse:
    """Server-sent events carrying the real investigation record.

    The token arrives as a query parameter because `EventSource` cannot set
    headers. It is verified exactly as a bearer token would be.
    """
    try:
        principal = verify_token(token)
    except AuthError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error

    stored = get_store().user(principal.uid)
    if stored is not None:
        principal = principal.model_copy(update={"role": stored.role})

    payload = _investigation_payload(investigation_id)
    _authorised_application(payload["applicationId"], principal)

    async def events():
        seen = ""
        # Bounded so a stalled pipeline closes the stream rather than holding
        # the connection open indefinitely.
        for _ in range(1200):
            current = _investigation_payload(investigation_id)
            fingerprint = json.dumps(current, sort_keys=True)
            if fingerprint != seen:
                seen = fingerprint
                yield f"data: {fingerprint}\n\n"
            if current["isTerminal"]:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/assessments/{application_id}")
def get_assessment(
    application_id: str, principal: Principal = Depends(current_user)
) -> dict[str, Any]:
    _authorised_application(application_id, principal)
    payload = get_store().assessment(application_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="this application has not produced an assessment yet",
        )
    return payload


# --------------------------------------------------------------------------
# Recruiter review across a whole requisition
# --------------------------------------------------------------------------


def _rebuild(payload: dict[str, Any]) -> Application:
    """Reconstruct the assessed application from its stored sections.

    Cheaper and more faithful than re-reading the PDF: these are exactly the
    sections the original assessment ran on.
    """
    return Application(
        id=payload["applicationId"],
        candidate_name=payload.get("candidateName", ""),
        sections=[
            Section(kind=SectionKind(entry["kind"]), text=entry["text"])
            for entry in payload.get("sections", [])
        ],
    )


def _coverage(entry) -> dict[str, Any]:
    return {
        "requirementId": entry.requirement_id,
        "skill": entry.skill,
        "necessity": entry.necessity.value,
        "satisfied": entry.satisfied,
        "satisfiedCount": entry.satisfied_count,
        "totalCandidates": entry.total_candidates,
        "coverageRatio": round(entry.coverage_ratio, 3),
        "isGap": entry.is_gap,
        "conclusion": entry.conclusion,
        "nearMisses": [
            {
                "applicationId": miss.application_id,
                "candidateName": miss.candidate_name,
                "evidenceLevel": miss.evidence_level.value,
                "note": miss.note,
            }
            for miss in entry.near_misses
        ],
        "rendered": entry.render() if entry.is_gap else "",
    }


@router.get("/api/recruiter/jobs/{job_id}/review")
def review(job_id: str, principal: Principal = Depends(recruiter_only)) -> dict[str, Any]:
    """Shortlist, trade-offs and pool gaps across everyone who applied."""
    store = get_store()
    job = store.job(job_id)
    if job is None or job.recruiter_id != principal.uid:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")

    requisition = to_requisition(job)
    records = store.applications(job_id=job_id)
    payloads = [
        store.assessment(record.id)
        for record in records
        if record.status is ApplicationStatus.ASSESSED
    ]
    payloads = [entry for entry in payloads if entry]

    if not payloads:
        return {
            "job": _job_payload(job),
            "applications": len(records),
            "assessed": 0,
            "shortlist": [],
            "coverage": [],
            "gaps": [],
            "matrix": [],
            "message": "No application has completed an investigation yet.",
        }

    applications = [_rebuild(entry) for entry in payloads]
    assessments = assess_pool(applications, requisition)
    coverage = analyse_pool(assessments, requisition)
    detected = gaps(coverage)
    by_id = {assessment.application_id: assessment for assessment in assessments}

    return {
        "job": _job_payload(job),
        "applications": len(records),
        "assessed": len(payloads),
        "message": full_requisition_message(assessments),
        "shortlist": [
            {
                "applicationId": entry.application_id,
                "candidateName": entry.candidate_name,
                "rank": entry.rank,
                "bestFit": entry.best_fit,
                "tradeoff": entry.tradeoff,
                "strengths": entry.strengths,
                "gaps": entry.gaps,
                "risks": entry.risks,
                "level": support_level(by_id[entry.application_id])[0],
                "levelLabel": support_level(by_id[entry.application_id])[1],
                "dimensions": [
                    {
                        "dimension": score.dimension.value,
                        "label": score.dimension.label,
                        "value": round(score.value, 3),
                        "detail": score.detail,
                    }
                    for score in entry.dimensions
                ],
            }
            for entry in build_shortlist(assessments)
        ],
        "coverage": [_coverage(entry) for entry in coverage],
        "gaps": [_coverage(entry) for entry in detected],
        "matrix": [
            {
                "applicationId": assessment.application_id,
                "candidateName": assessment.candidate_name,
                "cells": [
                    {
                        "requirementId": fit.requirement_id,
                        "skill": fit.skill,
                        "evidenceLevel": fit.evidence_level.value,
                        "status": fit.status.value,
                    }
                    for fit in assessment.fits
                ],
            }
            for assessment in assessments
        ],
    }


@router.get("/api/recruiter/compare")
def compare_candidates(
    job_id: str, left: str, right: str, principal: Principal = Depends(recruiter_only)
) -> dict[str, Any]:
    store = get_store()
    job = store.job(job_id)
    if job is None or job.recruiter_id != principal.uid:
        raise HTTPException(status_code=404, detail=f"no job {job_id}")

    requisition = to_requisition(job)
    payloads = {}
    for application_id in (left, right):
        entry = store.assessment(application_id)
        if entry is None:
            raise HTTPException(
                status_code=404, detail=f"{application_id} has no assessment yet"
            )
        payloads[application_id] = entry

    assessments = assess_pool(
        [_rebuild(payloads[left]), _rebuild(payloads[right])], requisition
    )
    result = compare(assessments[0], assessments[1])

    return {
        "leftId": result.left_id,
        "rightId": result.right_id,
        "verdict": result.verdict,
        "lines": [
            {
                "dimension": line.dimension.value,
                "label": line.dimension.label,
                "leftValue": round(line.left_value, 3),
                "rightValue": round(line.right_value, 3),
                "stronger": line.stronger,
                "detail": line.detail,
            }
            for line in result.lines
        ],
    }


# --------------------------------------------------------------------------
# Files and activity
# --------------------------------------------------------------------------


@router.get("/api/files/{name}")
def serve_file(name: str) -> FileResponse:
    """Serve a stored upload by its content hash.

    The name must be a digest plus an extension. Anything else is refused
    rather than joined onto a path.
    """
    if not _UPLOAD_NAME.match(name):
        raise HTTPException(status_code=400, detail="not a valid document reference")
    path = UPLOAD_ROOT / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="no such document")
    return FileResponse(path)


@router.get("/api/activity")
def activity(
    limit: int = 100, after: int = 0, principal: Principal = Depends(current_user)
) -> list[dict[str, Any]]:
    """The investigation activity trail."""
    return [
        {
            "sequence": event.sequence,
            "at": event.at.isoformat(),
            "stage": event.stage.value,
            "stageLabel": event.stage.label,
            "action": event.action,
            "subject": event.subject,
            "outcome": event.outcome.value,
            "outcomeLabel": event.outcome.label,
            "detail": event.detail,
            "contentHash": event.source.content_hash if event.source else None,
            "page": event.source.page_number if event.source else None,
        }
        for event in ACTIVITY_LOG.events(after=after, limit=limit)
    ]
