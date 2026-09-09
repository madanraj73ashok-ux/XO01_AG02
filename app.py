"""EvidenceHire - recruiter console.

Run with:  streamlit run app.py

Everything shown here is produced by the engine at load time. Nothing is
hard-coded for display, and every judgement can be expanded to the exact
sentence in the candidate's own application that produced it.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.assessment import assess_pool
from engine.claims import load_applications
from engine.contradictions import find_contradictions
from engine.models import (
    Application,
    CandidateAssessment,
    FitStatus,
    PoolCoverage,
    RequirementFit,
    Requisition,
)
from engine.poolgap import analyse_pool, gaps
from engine.requisition import detect_conflicts, load_requisition

DATA = Path(__file__).parent / "data"

STATUS_COLOUR: dict[FitStatus, str] = {
    FitStatus.STRONG: "green",
    FitStatus.MODERATE: "blue",
    FitStatus.WEAK: "orange",
    FitStatus.UNADDRESSED: "red",
}

st.set_page_config(page_title="EvidenceHire", layout="wide")


def coloured(fit: RequirementFit) -> str:
    """Status label in its severity colour."""
    return f":{STATUS_COLOUR[fit.status]}[{fit.status.label}]"


def render_requisition_conflicts(requisition: Requisition) -> None:
    conflicts = detect_conflicts(requisition)
    if not conflicts:
        st.success("No internal conflicts found in this requisition.")
        return

    st.warning(
        f"{len(conflicts)} conflict(s) found in the requisition itself. "
        "Surfaced for recruiter review, not resolved automatically."
    )
    for conflict in conflicts:
        with st.container(border=True):
            st.markdown(
                f"**{', '.join(conflict.requirement_ids)}** - `{conflict.kind.value}`"
            )
            st.write(conflict.detail)
            st.caption(conflict.recommendation)


def render_coverage(coverage: list[PoolCoverage]) -> None:
    """Per-requirement coverage across the whole pool."""
    for entry in coverage:
        left, middle, right = st.columns([3, 5, 2])
        with left:
            st.markdown(f"**{entry.skill}**" if entry.is_required else entry.skill)
            st.caption(entry.necessity.value)
        with middle:
            st.progress(entry.coverage_ratio)
        with right:
            text = f"{entry.satisfied_count} / {entry.total_candidates}"
            st.markdown(f":red[{text} - GAP]" if entry.is_gap else text)


def render_candidate_list(assessments: list[CandidateAssessment]) -> None:
    for assessment in assessments:
        with st.container(border=True):
            st.markdown(
                f"**{assessment.application_id} - {assessment.candidate_name}**"
            )
            st.write(assessment.summary)


def render_requirement_matrix(assessment: CandidateAssessment) -> None:
    """Per-criterion verdict, expandable to the evidence behind it."""
    for fit in assessment.fits:
        flag = "  ·  :red[claim not supported]" if fit.is_overclaimed else ""
        header = f"{fit.skill}  -  {fit.status.label}  ({fit.evidence_level.value})"

        with st.expander(header):
            st.markdown(
                f"{coloured(fit)}  ·  {fit.necessity.value}  ·  "
                f"evidence **{fit.evidence_level.value}** "
                f"({fit.evidence_level.label}){flag}"
            )

            if fit.claimed_strength.value != "unspecified":
                st.caption(f"Candidate claimed: {fit.claimed_strength.value}")

            st.markdown("**Why**")
            for reason in fit.reasons:
                st.markdown(f"- {reason}")

            if fit.supporting:
                st.markdown("**Evidence quoted from the application**")
                for item in fit.supporting:
                    st.markdown(f"- *{item.section.value}* - \"{item.source_text}\"")


def render_contradictions(application: Application) -> None:
    conflicts = find_contradictions(application)
    if not conflicts:
        st.success("No internal contradictions found in this application.")
        return

    st.warning(f"{len(conflicts)} contradiction(s) found within this application.")
    for conflict in conflicts:
        st.code(conflict.render(), language=None)


def render_pool_gaps(coverage: list[PoolCoverage]) -> None:
    detected = gaps(coverage)
    if not detected:
        st.success("Every requirement is demonstrated by at least one candidate.")
        return

    st.warning(
        f"{len(detected)} requirement(s) that no candidate in this pool "
        "demonstrates. This is a finding about the requisition and the market, "
        "not a failing of any individual candidate."
    )
    for entry in detected:
        st.code(entry.render(), language=None)


def main() -> None:
    requisition = load_requisition(DATA / "requisition.json")
    applications = load_applications(DATA / "applications")
    assessments = assess_pool(applications, requisition)
    coverage = analyse_pool(assessments, requisition)

    by_id = {a.id: a for a in applications}
    assessment_by_id = {a.application_id: a for a in assessments}

    with st.sidebar:
        st.title("EvidenceHire")
        st.caption(
            "Don't just read what candidates claim. "
            "Verify what the evidence supports."
        )
        st.divider()
        st.markdown(f"**{requisition.title}**")
        st.caption(f"{requisition.id} · {requisition.seniority.value}-level")
        st.metric("Applications", len(applications))
        st.metric("Required criteria", len(requisition.required))
        selected_id = st.selectbox("Inspect candidate", sorted(by_id))

    overview, candidate, pool = st.tabs(["Overview", "Candidate detail", "Pool gaps"])

    with overview:
        st.header(requisition.title)
        st.caption(
            f"{requisition.id} · advertised as {requisition.seniority.value}-level"
        )

        st.subheader("Requisition conflicts")
        render_requisition_conflicts(requisition)

        st.subheader("Requirement coverage across the pool")
        render_coverage(coverage)

        st.subheader("Candidates")
        render_candidate_list(assessments)

    with candidate:
        assessment = assessment_by_id[selected_id]
        st.header(f"{assessment.application_id} - {assessment.candidate_name}")
        st.markdown(f"**{assessment.summary}**")

        left, middle, right = st.columns(3)
        left.metric(
            "Required areas strong",
            f"{len(assessment.strong_required)} / {len(assessment.required_fits)}",
        )
        middle.metric("Unaddressed", len(assessment.unaddressed_required))
        right.metric("Unsupported claims", len(assessment.overclaims))

        st.divider()
        st.subheader("Requirement fit")
        st.caption("Expand any row to see the evidence that produced the verdict.")
        render_requirement_matrix(assessment)

        st.divider()
        st.subheader("Contradictions within this application")
        render_contradictions(by_id[selected_id])

    with pool:
        st.header("Talent-pool gaps")
        render_pool_gaps(coverage)


main()
