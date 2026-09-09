"""The investigation pipeline: one application, start to explained result.

This is the module the signature screen watches. Every step it publishes is a
step that actually ran - a stage is marked done when the work behind it
returned, and marked failed or skipped when it did not. Nothing here advances
on a timer, because a progress bar that moves while nothing is happening is a
lie told in an interface.

The order is the one the build plan sets out, and it is deliberate:

    extract -> structure -> requirements -> terminology -> claims
            -> evidence -> external -> assess -> explain

Structure and interpretation come first; judgement comes last. The evidence
grader is never asked what it thinks about a skill until the text supporting
that skill has been located and quoted.
"""

from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from engine.activity import ActivityLog, Outcome, Stage
from engine.assessment import assess_candidate
from engine.claims import extract_claims
from engine.contradictions import find_contradictions
from engine.equivalence import canonical_for, classify, known_surface_forms, normalize
from engine.evidence import grade_claims
from engine.ingest.extract import DocumentReader
from engine.ingest.pipeline import ingest_document
from engine.jobs import analyze_job
from engine.models import (
    Application,
    CandidateAssessment,
    EvidenceLevel,
    FitStatus,
    MatchKind,
    RequirementFit,
    Requisition,
)
from engine.provenance import now_utc
from engine.store import (
    ApplicationStatus,
    Investigation,
    InvestigationState,
    InvestigationStep,
    StepState,
    Store,
)

# The timeline the candidate watches. Keys are stable; labels are the words
# shown on screen.
STEP_DEFINITIONS: tuple[tuple[str, str], ...] = (
    ("received", "Application received"),
    ("document", "Document detected"),
    ("extract", "Text extracted"),
    ("structure", "Candidate profile structured"),
    ("requirements", "Job requirements understood"),
    ("terminology", "Terminology normalized"),
    ("claims", "Candidate claims identified"),
    ("evidence", "Evidence verification"),
    ("external", "External evidence"),
    ("assess", "Requirement assessment"),
    ("explain", "Final assessment"),
)

# Sections the grader consults. Named explicitly so an E0 verdict can say
# where it looked rather than merely that it found nothing.
SEARCHED_SOURCES = (
    "skills list",
    "experience",
    "projects",
    "education",
    "cover note",
    "external evidence",
)


class Relationship(str, Enum):
    """How a candidate's vocabulary relates to a required skill.

    Five values, because the build plan and the evaluator both ask for the
    distinction. `UNKNOWN` means the candidate said nothing comparable;
    `NOT_EQUIVALENT` means they did, and it is not the same capability. Those
    are different facts and must not be merged.
    """

    EXACT = "EXACT"
    EQUIVALENT = "EQUIVALENT"
    RELATED = "RELATED"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    UNKNOWN = "UNKNOWN"

    @property
    def satisfies(self) -> bool:
        return self in (Relationship.EXACT, Relationship.EQUIVALENT)


class TerminologyFinding(BaseModel):
    """What the candidate called a required skill, and how that was judged."""

    requirement_id: str
    required_skill: str
    candidate_terms: list[str] = Field(default_factory=list)
    relationship: Relationship
    explanation: str


class WhyExplanation(BaseModel):
    """The answer to "why did you conclude that?" for one requirement.

    `searched` is populated even - especially - when nothing was found, so an
    E0 can state where it looked. `caveat` carries the sentence that stops an
    absence of evidence from reading as evidence of absence.
    """

    verdict: str
    evidence_level: str
    reasons: list[str] = Field(default_factory=list)
    quotes: list[dict] = Field(default_factory=list)
    searched: list[str] = Field(default_factory=list)
    caveat: str = ""


class InvestigationFailure(Exception):
    """A stage failed in a way that stops the run, carrying an error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------
# Terminology
# --------------------------------------------------------------------------


def _mentions(text: str, surface: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", text) is not None


def candidate_vocabulary(application: Application) -> dict[str, list[str]]:
    """Every recognised skill term the candidate actually used.

    Returns canonical skill -> the surface forms they wrote, so the UI can
    show "you wrote 'Robot Operating System 2'" rather than only the canonical
    name the system normalised it to.
    """
    text = normalize(application.full_text)
    found: dict[str, list[str]] = {}

    for surface, canonical in known_surface_forms().items():
        if _mentions(text, surface):
            found.setdefault(canonical, []).append(surface)

    return found


def _adjacent_terms(canonical: str, application: Application) -> list[str]:
    from engine.equivalence import RELATED_SKILLS

    text = normalize(application.full_text)
    return [
        term
        for term in sorted(RELATED_SKILLS.get(canonical, set()))
        if _mentions(text, normalize(term))
    ]


def _rank(relationship: Relationship) -> int:
    return {
        Relationship.UNKNOWN: 0,
        Relationship.NOT_EQUIVALENT: 1,
        Relationship.RELATED: 2,
        Relationship.EQUIVALENT: 3,
        Relationship.EXACT: 4,
    }[relationship]


def terminology_matrix(
    application: Application, requisition: Requisition
) -> list[TerminologyFinding]:
    """Classify the candidate's wording against every required skill.

    This is where ECS-versus-container-orchestration is settled. The engine's
    `classify` decides; this function reports the decision together with the
    wording that produced it.
    """
    vocabulary = candidate_vocabulary(application)
    findings: list[TerminologyFinding] = []

    for requirement in requisition.requirements:
        canonical = canonical_for(requirement.skill) or requirement.skill
        best: tuple[Relationship, str, list[str]] | None = None

        for surfaces in vocabulary.values():
            for surface in surfaces:
                match = classify(surface, requirement.skill)
                relationship = {
                    MatchKind.EXACT: Relationship.EXACT,
                    MatchKind.EQUIVALENT: Relationship.EQUIVALENT,
                    MatchKind.RELATED: Relationship.RELATED,
                    MatchKind.NONE: Relationship.NOT_EQUIVALENT,
                }[match.kind]

                if relationship is Relationship.NOT_EQUIVALENT:
                    # An unrelated skill is not a judgement about this
                    # requirement, so it is not reported as one.
                    continue

                if best is None or _rank(relationship) > _rank(best[0]):
                    best = (relationship, match.explanation, [surface])

        if best is not None:
            relationship, explanation, terms = best
            findings.append(
                TerminologyFinding(
                    requirement_id=requirement.id,
                    required_skill=requirement.skill,
                    candidate_terms=terms,
                    relationship=relationship,
                    explanation=explanation,
                )
            )
            continue

        adjacent = _adjacent_terms(canonical, application)
        if adjacent:
            findings.append(
                TerminologyFinding(
                    requirement_id=requirement.id,
                    required_skill=requirement.skill,
                    candidate_terms=adjacent,
                    relationship=Relationship.NOT_EQUIVALENT,
                    explanation=(
                        f"The candidate wrote {', '.join(adjacent)}, which is "
                        f"adjacent to {requirement.skill} but is not the same "
                        "capability, so evidence has to decide it."
                    ),
                )
            )
        else:
            findings.append(
                TerminologyFinding(
                    requirement_id=requirement.id,
                    required_skill=requirement.skill,
                    candidate_terms=[],
                    relationship=Relationship.UNKNOWN,
                    explanation=(
                        f"The application contains no term comparable to "
                        f"{requirement.skill}, so no relationship could be "
                        "established either way."
                    ),
                )
            )

    return findings


# --------------------------------------------------------------------------
# WHY
# --------------------------------------------------------------------------


def explain(
    fit: RequirementFit, terminology: TerminologyFinding | None
) -> WhyExplanation:
    """Build the WHY panel for one requirement.

    The unsupported branch is the one that matters. It states what was
    searched, that nothing was found, and - explicitly - that this is not a
    finding about the candidate's actual ability. Without that last sentence
    the screen reads as an accusation.
    """
    quotes = [
        {
            "section": item.section.value,
            "text": item.source_text,
            "note": item.note,
            "weight": item.weight,
        }
        for item in fit.supporting
    ]

    reasons = list(fit.reasons)
    if terminology is not None and terminology.relationship is not Relationship.UNKNOWN:
        reasons.append(terminology.explanation)

    if fit.evidence_level is EvidenceLevel.E0 or fit.status is FitStatus.UNADDRESSED:
        return WhyExplanation(
            verdict=f"{fit.skill}: no supporting evidence found",
            evidence_level=fit.evidence_level.value,
            reasons=reasons,
            quotes=quotes,
            searched=list(SEARCHED_SOURCES),
            caveat=(
                "This does not prove the candidate lacks this skill. It means "
                "the evidence available to this system does not currently "
                "support the claim."
            ),
        )

    return WhyExplanation(
        verdict=f"{fit.skill}: {fit.evidence_level.value} - {fit.evidence_level.label}",
        evidence_level=fit.evidence_level.value,
        reasons=reasons,
        quotes=quotes,
        searched=list(SEARCHED_SOURCES),
        caveat=(
            "Evidence found in an application supports the claim; it does not "
            "independently prove professional employment."
        ),
    )


# --------------------------------------------------------------------------
# Overall level
# --------------------------------------------------------------------------


def support_level(assessment: CandidateAssessment) -> tuple[int, str]:
    """A coarse, evidence-derived band - never a percentage.

    The build plan is explicit that a fabricated precision like 87.3% must not
    be the headline. This is derived from how many required criteria are
    actually supported, and the requirement matrix underneath it remains the
    real explanation.
    """
    required = assessment.required_fits
    if not required:
        return 0, "No required criteria"

    supported = len(assessment.strong_required)
    ratio = supported / len(required)

    if ratio == 1.0:
        return 4, "Strongly supported"
    if ratio >= 0.7:
        return 3, "Well supported"
    if ratio >= 0.4:
        return 2, "Partially supported"
    if supported:
        return 1, "Weakly supported"
    return 0, "Not supported by available evidence"


# --------------------------------------------------------------------------
# Evidence graph
# --------------------------------------------------------------------------


def evidence_graph(
    assessment: CandidateAssessment, terminology: list[TerminologyFinding]
) -> dict:
    """Nodes and edges built only from things that were actually found.

    Every edge corresponds to a relationship the engine computed. No node is
    invented to make the picture look fuller.
    """
    nodes: list[dict] = [
        {"id": "candidate", "kind": "candidate", "label": assessment.candidate_name}
    ]
    edges: list[dict] = []
    findings = {entry.requirement_id: entry for entry in terminology}

    for fit in assessment.fits:
        requirement_node = f"req::{fit.requirement_id}"
        nodes.append(
            {
                "id": requirement_node,
                "kind": "requirement",
                "label": fit.skill,
                "necessity": fit.necessity.value,
                "evidenceLevel": fit.evidence_level.value,
                "status": fit.status.value,
            }
        )

        finding = findings.get(fit.requirement_id)
        if finding and finding.candidate_terms:
            claim_node = f"claim::{fit.requirement_id}"
            nodes.append(
                {
                    "id": claim_node,
                    "kind": "claim",
                    "label": finding.candidate_terms[0],
                    "evidenceLevel": fit.evidence_level.value,
                }
            )
            edges.append(
                {"source": "candidate", "target": claim_node, "kind": "CLAIMS"}
            )
            edges.append(
                {
                    "source": claim_node,
                    "target": requirement_node,
                    "kind": (
                        "EQUIVALENT_TO"
                        if finding.relationship is Relationship.EQUIVALENT
                        else "RELATED_TO"
                        if finding.relationship
                        in (Relationship.RELATED, Relationship.NOT_EQUIVALENT)
                        else "SUPPORTS"
                    ),
                    "label": finding.relationship.value,
                }
            )

        for index, item in enumerate(fit.supporting):
            evidence_node = f"ev::{fit.requirement_id}::{index}"
            nodes.append(
                {
                    "id": evidence_node,
                    "kind": "evidence",
                    "label": item.section.value,
                    "text": item.source_text,
                    "weight": item.weight,
                }
            )
            edges.append(
                {"source": evidence_node, "target": requirement_node, "kind": "SUPPORTS"}
            )

    return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------


class InvestigationRunner:
    """Runs the pipeline and reports honestly on every stage."""

    def __init__(
        self,
        store: Store,
        log: ActivityLog,
        *,
        reader: DocumentReader | None = None,
        max_workers: int = 2,
    ) -> None:
        self._store = store
        self._log = log
        self._reader = reader
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------

    def create(self, application_id: str) -> Investigation:
        """Register an investigation with every step still pending."""
        application = self._store.application(application_id)
        if application is None:
            raise InvestigationFailure(
                "APPLICATION_NOT_FOUND", f"no application {application_id}"
            )

        investigation = Investigation(
            application_id=application_id,
            job_id=application.job_id,
            candidate_uid=application.candidate_uid,
            steps=[
                InvestigationStep(key=key, label=label) for key, label in STEP_DEFINITIONS
            ],
        )
        self._store.save_investigation(investigation)

        application.investigation_id = investigation.id
        application.status = ApplicationStatus.INVESTIGATING
        application.updated_at = now_utc()
        self._store.save_application(application)

        return investigation

    def start(self, application_id: str) -> Investigation:
        """Create and run in the background, returning immediately."""
        investigation = self.create(application_id)
        self._pool.submit(self._run, investigation.id)
        return investigation

    def run_sync(self, application_id: str) -> Investigation:
        """Create and run to completion on the calling thread."""
        investigation = self.create(application_id)
        return self._run(investigation.id)

    # -- step bookkeeping -------------------------------------------------

    def _mark(
        self,
        investigation: Investigation,
        key: str,
        state: StepState,
        detail: str = "",
    ) -> Investigation:
        with self._lock:
            step = investigation.step(key)
            if step is not None:
                step.state = state
                step.detail = detail
                step.at = now_utc()
            investigation.updated_at = now_utc()
            self._store.save_investigation(investigation)

        outcome = {
            StepState.ACTIVE: Outcome.STARTED,
            StepState.DONE: Outcome.SUCCEEDED,
            StepState.FAILED: Outcome.FAILED,
            StepState.SKIPPED: Outcome.SKIPPED,
            StepState.PENDING: Outcome.STARTED,
        }[state]

        self._log.emit(
            stage=Stage.ASSESSMENT,
            action=key,
            subject=investigation.application_id,
            outcome=outcome,
            detail=detail,
        )
        return investigation

    def _advance(
        self, investigation: Investigation, state: InvestigationState
    ) -> Investigation:
        investigation.state = state
        investigation.updated_at = now_utc()
        self._store.save_investigation(investigation)
        return investigation

    # -- the pipeline -----------------------------------------------------

    def _run(self, investigation_id: str) -> Investigation:
        investigation = self._store.investigation(investigation_id)
        if investigation is None:
            raise InvestigationFailure(
                "INVESTIGATION_NOT_FOUND", f"no investigation {investigation_id}"
            )

        try:
            return self._pipeline(investigation)
        except InvestigationFailure as failure:
            return self._fail(investigation, failure.code, failure.detail)
        except Exception as error:  # pragma: no cover - defensive
            return self._fail(investigation, "PIPELINE_ERROR", str(error))

    def _fail(
        self, investigation: Investigation, code: str, detail: str
    ) -> Investigation:
        investigation.error_code = code
        investigation.error_detail = detail
        investigation.state = InvestigationState.FAILED
        investigation.completed_at = now_utc()
        self._store.save_investigation(investigation)

        application = self._store.application(investigation.application_id)
        if application is not None:
            application.status = ApplicationStatus.FAILED
            self._store.save_application(application)

        self._log.emit(
            stage=Stage.ASSESSMENT,
            action="investigation_failed",
            subject=investigation.application_id,
            outcome=Outcome.FAILED,
            detail=f"{code}: {detail}",
        )
        return investigation

    def _pipeline(self, investigation: Investigation) -> Investigation:
        from engine.documents import StoredDocument, read_document

        store = self._store
        stored = store.application(investigation.application_id)
        if stored is None:
            raise InvestigationFailure("APPLICATION_NOT_FOUND", "application vanished")

        job = store.job(stored.job_id)
        if job is None:
            raise InvestigationFailure("JOB_NOT_FOUND", f"no job {stored.job_id}")

        # 1. received
        self._mark(investigation, "received", StepState.DONE, "Application accepted")

        # 2. document
        self._advance(investigation, InvestigationState.EXTRACTING)
        self._mark(investigation, "document", StepState.ACTIVE)
        document = StoredDocument(
            filename=stored.resume_filename,
            backend=stored.storage_backend,
            url=stored.resume_url,
            public_id=stored.resume_public_id,
            local_path=self._local_path(stored),
            content_hash="0" * 64,
            bytes=0,
        )
        try:
            payload = read_document(document)
        except Exception as error:
            self._mark(investigation, "document", StepState.FAILED, str(error))
            raise InvestigationFailure("DOCUMENT_UNREADABLE", str(error)) from error

        self._mark(
            investigation,
            "document",
            StepState.DONE,
            f"{stored.resume_filename} ({len(payload) / 1024:.0f} KB) via "
            f"{stored.storage_backend}",
        )

        # 3. extract
        self._mark(investigation, "extract", StepState.ACTIVE)
        temp = self._materialise(stored, payload)
        try:
            result = ingest_document(
                temp, reader=self._reader, log=self._log, document_id=stored.id
            )
        except Exception as error:
            self._mark(investigation, "extract", StepState.FAILED, str(error))
            raise InvestigationFailure("OCR_FAILED", str(error)) from error

        ingested = result.document
        engines = ", ".join(name.value for name in ingested.raw.extractors_used)
        detail = (
            f"{len(ingested.raw.lines())} lines from {ingested.raw.page_count} "
            f"pages via {engines}"
        )
        if ingested.unread_pages:
            detail += f"; {len(ingested.unread_pages)} page(s) produced no text"
        self._mark(investigation, "extract", StepState.DONE, detail)
        investigation.document_id = ingested.document_id

        # 4. structure
        self._advance(investigation, InvestigationState.STRUCTURING)
        self._mark(investigation, "structure", StepState.ACTIVE)
        if result.application is None:
            self._mark(
                investigation,
                "structure",
                StepState.FAILED,
                result.blocked_reason or "",
            )
            raise InvestigationFailure(
                "INSUFFICIENT_EVIDENCE",
                result.blocked_reason or "the document could not be structured",
            )

        application = result.application
        if stored.candidate_name and not application.candidate_name.strip():
            application = application.model_copy(
                update={"candidate_name": stored.candidate_name}
            )
        self._mark(
            investigation,
            "structure",
            StepState.DONE,
            f"{len(application.sections)} sections: "
            + ", ".join(section.kind.value for section in application.sections),
        )

        # 5. requirements
        self._advance(investigation, InvestigationState.ANALYZING)
        self._mark(investigation, "requirements", StepState.ACTIVE)
        analysis = analyze_job(job)
        requisition = analysis.requisition
        note = f"{analysis.required_count} required, {analysis.preferred_count} preferred"
        if analysis.has_conflicts:
            note += f"; {len(analysis.conflicts)} requisition conflict(s)"
        self._mark(investigation, "requirements", StepState.DONE, note)

        # 6. terminology
        self._mark(investigation, "terminology", StepState.ACTIVE)
        terminology = terminology_matrix(application, requisition)
        counts: dict[str, int] = {}
        for finding in terminology:
            counts[finding.relationship.value] = counts.get(finding.relationship.value, 0) + 1
        self._mark(
            investigation,
            "terminology",
            StepState.DONE,
            ", ".join(f"{key} x{value}" for key, value in sorted(counts.items())),
        )

        # 7. claims
        self._advance(investigation, InvestigationState.INVESTIGATING)
        self._mark(investigation, "claims", StepState.ACTIVE)
        claims = extract_claims(application)
        self._mark(
            investigation,
            "claims",
            StepState.DONE,
            f"{len(claims)} claims across "
            f"{len({claim.skill for claim in claims})} distinct skills",
        )

        # 8. evidence
        self._advance(investigation, InvestigationState.VERIFYING)
        self._mark(investigation, "evidence", StepState.ACTIVE)
        graded = grade_claims(claims)
        spread: dict[str, int] = {}
        for entry in graded:
            spread[entry.evidence_level.value] = spread.get(entry.evidence_level.value, 0) + 1
        self._mark(
            investigation,
            "evidence",
            StepState.DONE,
            ", ".join(f"{key} x{value}" for key, value in sorted(spread.items()))
            or "no gradable claims",
        )

        # 9. external
        external = self._external_stage(investigation, stored)

        # 10. assess
        self._advance(investigation, InvestigationState.ASSESSING)
        self._mark(investigation, "assess", StepState.ACTIVE)
        assessment = assess_candidate(application, requisition)
        contradictions = find_contradictions(application)
        self._mark(
            investigation,
            "assess",
            StepState.DONE,
            f"{len(assessment.strong_required)} of {len(assessment.required_fits)} "
            f"required areas supported; {len(assessment.overclaims)} unsupported "
            f"claim(s), {len(contradictions)} discrepancy(ies)",
        )

        # 11. explain
        self._mark(investigation, "explain", StepState.ACTIVE)
        payload_out = self._payload(
            stored_id=stored.id,
            job_id=job.id,
            application=application,
            assessment=assessment,
            terminology=terminology,
            contradictions=contradictions,
            external=external,
            ingested=ingested,
            conflicts=analysis.conflicts,
        )
        store.save_assessment(stored.id, payload_out)
        level, label = support_level(assessment)
        self._mark(investigation, "explain", StepState.DONE, f"Level {level} - {label}")

        investigation.state = InvestigationState.COMPLETE
        investigation.completed_at = now_utc()
        store.save_investigation(investigation)

        stored.status = ApplicationStatus.ASSESSED
        stored.updated_at = now_utc()
        store.save_application(stored)

        return investigation

    # -- helpers ----------------------------------------------------------

    def _local_path(self, stored) -> str:
        from engine.documents import UPLOAD_ROOT

        if not stored.resume_url.startswith("/api/files/"):
            return ""
        candidate = UPLOAD_ROOT / stored.resume_url.rsplit("/", 1)[-1]
        return str(candidate) if candidate.exists() else ""

    def _materialise(self, stored, payload: bytes) -> Path:
        """Ensure the bytes exist as a file the ingester can open."""
        from engine.documents import UPLOAD_ROOT
        from engine.provenance import sha256_of

        suffix = Path(stored.resume_filename).suffix.lower() or ".pdf"
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        path = UPLOAD_ROOT / f"{sha256_of(payload)}{suffix}"
        if not path.exists():
            path.write_bytes(payload)
        return path

    def _external_stage(self, investigation: Investigation, stored) -> list[dict]:
        """Check the candidate's public links, or say plainly that we did not."""
        targets = [url for url in (stored.github_url, stored.portfolio_url) if url]
        if not targets:
            self._mark(
                investigation,
                "external",
                StepState.SKIPPED,
                "no public links were supplied with this application",
            )
            return []

        self._mark(investigation, "external", StepState.ACTIVE)
        from engine.external.verify import verify_links

        checks = verify_links(targets, log=self._log)
        summary = "; ".join(f"{check['target']}: {check['state']}" for check in checks)
        resolved = [check for check in checks if check["state"] == "public"]
        self._mark(
            investigation,
            "external",
            StepState.DONE if resolved else StepState.SKIPPED,
            summary or "nothing could be established",
        )
        return checks

    def _payload(
        self,
        *,
        stored_id: str,
        job_id: str,
        application: Application,
        assessment: CandidateAssessment,
        terminology: list[TerminologyFinding],
        contradictions: list,
        external: list[dict],
        ingested,
        conflicts: list,
    ) -> dict:
        findings = {entry.requirement_id: entry for entry in terminology}
        level, label = support_level(assessment)

        return {
            "applicationId": stored_id,
            "jobId": job_id,
            "candidateName": assessment.candidate_name,
            "level": level,
            "levelLabel": label,
            "summary": assessment.summary,
            "requiredTotal": len(assessment.required_fits),
            "requiredSupported": len(assessment.strong_required),
            "unaddressed": len(assessment.unaddressed_required),
            "overclaims": len(assessment.overclaims),
            "documentId": ingested.document_id,
            "sourceFilename": ingested.source_filename,
            "sourceHash": ingested.source_hash,
            "pageCount": ingested.raw.page_count,
            "extractors": [name.value for name in ingested.raw.extractors_used],
            "requisitionConflicts": [
                {
                    "kind": conflict.kind.value,
                    "requirementIds": conflict.requirement_ids,
                    "detail": conflict.detail,
                    "recommendation": conflict.recommendation,
                }
                for conflict in conflicts
            ],
            "fits": [
                {
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
                    "terminology": (
                        findings[fit.requirement_id].model_dump(mode="json")
                        if fit.requirement_id in findings
                        else None
                    ),
                    "why": explain(
                        fit, findings.get(fit.requirement_id)
                    ).model_dump(mode="json"),
                }
                for fit in assessment.fits
            ],
            "terminology": [entry.model_dump(mode="json") for entry in terminology],
            "contradictions": [
                {
                    "kind": item.kind.value,
                    "label": item.kind.label,
                    "subject": item.subject,
                    "claimText": item.claim_text,
                    "claimSection": item.claim_section.value,
                    "evidenceNote": item.evidence_note,
                    "assessment": item.assessment,
                    "confidenceEffect": item.confidence_effect,
                    "flag": item.flag,
                    "rendered": item.render(),
                }
                for item in contradictions
            ],
            "external": external,
            "graph": evidence_graph(assessment, terminology),
            "sections": [
                {"kind": section.kind.value, "text": section.text}
                for section in application.sections
            ],
            "generatedAt": now_utc().isoformat(),
        }


_RUNNER: InvestigationRunner | None = None


def get_runner(store: Store, log: ActivityLog) -> InvestigationRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = InvestigationRunner(store, log)
    return _RUNNER
