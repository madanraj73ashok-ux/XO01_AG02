"""EvidenceHire - recruiter console.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from engine.models import Requirement, Requisition
from engine.requisition import detect_conflicts, load_requisition

REQUISITION_PATH = Path(__file__).parent / "data" / "requisition.json"

st.set_page_config(page_title="EvidenceHire", layout="wide")


def render_header() -> None:
    st.title("EvidenceHire")
    st.caption(
        "Don't just read what candidates claim. Verify what the evidence supports."
    )


def render_requirements(title: str, requirements: list[Requirement]) -> None:
    st.subheader(title)
    if not requirements:
        st.write("None specified.")
        return

    st.dataframe(
        [
            {
                "ID": r.id,
                "Skill": r.skill,
                "Min years": "-" if r.min_years is None else r.min_years,
                "Description": r.description,
            }
            for r in requirements
        ],
        hide_index=True,
    )


def render_conflicts(requisition: Requisition) -> None:
    st.subheader("Requisition conflict detection")
    conflicts = detect_conflicts(requisition)

    if not conflicts:
        st.success("No internal conflicts found in this requisition.")
        return

    st.warning(
        f"{len(conflicts)} potential conflict(s) found in the requisition itself. "
        "These are surfaced for recruiter review, not resolved automatically."
    )
    for conflict in conflicts:
        with st.container(border=True):
            st.markdown(
                f"**{', '.join(conflict.requirement_ids)}** - "
                f"`{conflict.kind.value}`"
            )
            st.write(conflict.detail)
            st.caption(conflict.recommendation)


def main() -> None:
    render_header()

    requisition = load_requisition(REQUISITION_PATH)

    st.header(requisition.title)
    st.caption(f"{requisition.id} - advertised as {requisition.seniority.value}-level")

    left, right = st.columns(2)
    with left:
        st.metric("Required criteria", len(requisition.required))
    with right:
        st.metric("Preferred criteria", len(requisition.preferred))

    render_conflicts(requisition)
    render_requirements("Required", requisition.required)
    render_requirements("Preferred", requisition.preferred)

    st.divider()
    st.info(
        "Next stage: candidate applications, claim extraction, and "
        "evidence grading against these criteria."
    )


main()
