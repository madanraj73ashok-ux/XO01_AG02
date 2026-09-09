"""EvidenceHire HTTP API.

A thin exposure layer over the existing screening engine. It computes nothing
of its own: every value returned here comes from a module in `engine/`, which
remains the single source of truth and stays independently testable.

Run with:  uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import routes as product_routes

from engine.assessment import assess_pool
from engine.claims import load_applications
from engine.contradictions import find_contradictions
from engine.models import (
    Application,
    CandidateAssessment,
    Contradiction,
    FitStatus,
    PoolCoverage,
    RequirementFit,
    Requisition,
)
from engine.poolgap import analyse_pool, gaps
from engine.requisition import detect_conflicts, load_requisition
from engine.tradeoffs import build_shortlist, compare, full_requisition_message

DATA = Path(__file__).parent / "data"

app = FastAPI(title="EvidenceHire API", version="1.0.0")

# The React dev server runs on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    # POST is needed now that recruiters create requisitions and candidates
    # submit applications; the original console was read-only.
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# The two-sided product lives in `routes.py`. It is mounted rather than merged
# so the original console's endpoints keep their exact shape.
app.include_router(product_routes.router)


@lru_cache(maxsize=1)
def _state() -> tuple[Requisition, list[Application], list[CandidateAssessment]]:
    """Load and assess once; the demo dataset does not change at runtime."""
    requisition = load_requisition(DATA / "requisition.json")
    applications = load_applications(DATA / "applications")
    return requisition, applications, assess_pool(applications, requisition)


def _application(application_id: str) -> Application:
    _, applications, _ = _state()
    found = next((a for a in applications if a.id == application_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No application {application_id}")
    return found


def _assessment(application_id: str) -> CandidateAssessment:
    _, _, assessments = _state()
    found = next((a for a in assessments if a.application_id == application_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No assessment {application_id}")
    return found


def _fit_payload(fit: RequirementFit) -> dict[str, Any]:
    """One requirement verdict, with everything needed to justify it."""
    return {
        "requirementId": fit.requirement_id,
        "skill": fit.skill,
        "necessity": fit.necessity.value,
        "status": fit.status.value,
        "statusLabel": fit.status.label,
        "evidenceLevel": fit.evidence_level.value,
        "evidenceLabel": fit.evidence_level.label,
        "evidenceRank": fit.evidence_level.rank,
        "matchKind": fit.match_kind.value,
        "claimedStrength": fit.claimed_strength.value,
        "isOverclaimed": fit.is_overclaimed,
        "isMet": fit.is_met,
        "confidence": round(fit.confidence, 3),
        "confidenceFactors": [
            {"reason": reason, "delta": round(delta, 3)}
            for reason, delta in fit.confidence_factors
        ],
        "reasons": fit.reasons,
        "closestEvidence": fit.closest_evidence,
        "supporting": [
            {
                "section": item.section.value,
                "sourceText": item.source_text,
                "note": item.note,
                "weight": item.weight,
            }
            for item in fit.supporting
        ],
    }


def _coverage_payload(entry: PoolCoverage) -> dict[str, Any]:
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
    }


def _shortlist_payload() -> list[dict[str, Any]]:
    _, _, assessments = _state()
    return [
        {
            "applicationId": entry.application_id,
            "candidateName": entry.candidate_name,
            "rank": entry.rank,
            "bestFit": entry.best_fit,
            "tradeoff": entry.tradeoff,
            "strengths": entry.strengths,
            "gaps": entry.gaps,
            "risks": entry.risks,
            "dimensions": [
                {
                    "dimension": d.dimension.value,
                    "label": d.dimension.label,
                    "value": round(d.value, 3),
                    "detail": d.detail,
                }
                for d in entry.dimensions
            ],
        }
        for entry in build_shortlist(assessments)
    ]


def _stage(assessment: CandidateAssessment, contradictions: list[Contradiction]) -> str:
    """Where this application sits in the review pipeline.

    Derived from the assessment rather than stored, so it can never drift out
    of step with the evidence. Nothing here auto-rejects: the terminal states
    are reached by a recruiter, not by the system.
    """
    if contradictions or assessment.overclaims:
        return "evidence_verification"
    if len(assessment.strong_required) == len(assessment.required_fits):
        return "recruiter_review"
    if assessment.strong_required:
        return "screening"
    return "applied"


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    requisition, applications, _ = _state()
    return {
        "status": "ok",
        "requisition": requisition.id,
        "applications": len(applications),
    }


@app.get("/api/requisition")
def get_requisition() -> dict[str, Any]:
    requisition, _, _ = _state()

    return {
        "id": requisition.id,
        "title": requisition.title,
        "seniority": requisition.seniority.value,
        "requirements": [
            {
                "id": r.id,
                "skill": r.skill,
                "necessity": r.necessity.value,
                "minYears": r.min_years,
                "maxSalaryLpa": r.max_salary_lpa,
                "description": r.description,
            }
            for r in requisition.requirements
        ],
        "conflicts": [
            {
                "kind": c.kind.value,
                "requirementIds": c.requirement_ids,
                "detail": c.detail,
                "recommendation": c.recommendation,
            }
            for c in detect_conflicts(requisition)
        ],
    }


@app.get("/api/candidates")
def list_candidates() -> list[dict[str, Any]]:
    _, _, assessments = _state()
    shortlist = {e["applicationId"]: e for e in _shortlist_payload()}

    payload = []
    for assessment in assessments:
        entry = shortlist[assessment.application_id]
        contradictions = find_contradictions(_application(assessment.application_id))
        payload.append(
            {
                "applicationId": assessment.application_id,
                "candidateName": assessment.candidate_name,
                "rank": entry["rank"],
                "summary": assessment.summary,
                "bestFit": entry["bestFit"],
                "tradeoff": entry["tradeoff"],
                "strengths": entry["strengths"],
                "gaps": entry["gaps"],
                "risks": entry["risks"],
                "dimensions": entry["dimensions"],
                "requiredTotal": len(assessment.required_fits),
                "requiredStrong": len(assessment.strong_required),
                "unaddressed": len(assessment.unaddressed_required),
                "overclaims": len(assessment.overclaims),
                "contradictions": len(contradictions),
                "stage": _stage(assessment, contradictions),
                "fullyQualified": len(assessment.strong_required)
                == len(assessment.required_fits),
            }
        )
    return sorted(payload, key=lambda item: item["rank"])


@app.get("/api/candidates/{application_id}")
def get_candidate(application_id: str) -> dict[str, Any]:
    application = _application(application_id)
    assessment = _assessment(application_id)
    contradictions = find_contradictions(application)
    requisition, _, _ = _state()

    return {
        "applicationId": assessment.application_id,
        "candidateName": assessment.candidate_name,
        "summary": assessment.summary,
        "requiredTotal": len(assessment.required_fits),
        "requiredStrong": len(assessment.strong_required),
        "unaddressed": len(assessment.unaddressed_required),
        "overclaims": len(assessment.overclaims),
        "stage": _stage(assessment, contradictions),
        "fullyQualified": len(assessment.strong_required)
        == len(assessment.required_fits),
        "requisitionIssues": [
            {
                "kind": issue.kind.value,
                "requirementIds": issue.requirement_ids,
                "detail": issue.detail,
                "recommendation": issue.recommendation,
            }
            for issue in detect_conflicts(requisition)
        ],
        "sections": [
            {"kind": s.kind.value, "text": s.text} for s in application.sections
        ],
        "fits": [_fit_payload(fit) for fit in assessment.fits],
        "contradictions": [
            {
                "kind": c.kind.value,
                "label": c.kind.label,
                "subject": c.subject,
                "claimText": c.claim_text,
                "claimSection": c.claim_section.value,
                "evidenceNote": c.evidence_note,
                "assessment": c.assessment,
                "confidenceEffect": c.confidence_effect,
                "flag": c.flag,
                "counterEvidence": [
                    {
                        "section": item.section.value,
                        "sourceText": item.source_text,
                        "note": item.note,
                    }
                    for item in c.counter_evidence
                ],
                "rendered": c.render(),
            }
            for c in contradictions
        ],
    }


@app.get("/api/shortlist")
def get_shortlist() -> list[dict[str, Any]]:
    return _shortlist_payload()


@app.get("/api/pool")
def get_pool() -> dict[str, Any]:
    requisition, _, assessments = _state()
    coverage = analyse_pool(assessments, requisition)

    return {
        "coverage": [_coverage_payload(entry) for entry in coverage],
        "gaps": [_coverage_payload(entry) for entry in gaps(coverage)],
    }


@app.get("/api/compare")
def get_comparison(left: str, right: str) -> dict[str, Any]:
    result = compare(_assessment(left), _assessment(right))

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


@app.get("/api/dashboard")
def get_dashboard() -> dict[str, Any]:
    requisition, applications, assessments = _state()
    coverage = analyse_pool(assessments, requisition)
    detected = gaps(coverage)

    graded = [
        fit
        for a in assessments
        for fit in a.fits
        if fit.status is not FitStatus.UNADDRESSED
    ]
    spread: dict[str, int] = {}
    for fit in graded:
        spread[fit.evidence_level.value] = spread.get(fit.evidence_level.value, 0) + 1

    return {
        "requisitionTitle": requisition.title,
        "requisitionId": requisition.id,
        "applications": len(applications),
        "requisitionConflicts": len(detect_conflicts(requisition)),
        "poolGaps": len(detected),
        "gapSkills": [entry.skill for entry in detected],
        "overclaims": sum(len(a.overclaims) for a in assessments),
        "contradictions": sum(len(find_contradictions(a)) for a in applications),
        "fullyQualified": sum(
            1 for a in assessments if len(a.strong_required) == len(a.required_fits)
        ),
        "fullRequisitionMessage": full_requisition_message(assessments),
        "evidenceSpread": [
            {"level": level, "count": spread.get(level, 0)}
            for level in ("E0", "E1", "E2", "E3", "E4")
        ],
        "coverage": [_coverage_payload(entry) for entry in coverage],
    }
