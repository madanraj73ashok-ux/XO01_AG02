"""Turning a recruiter's job posting into something the engine can screen against.

The conversion is deliberately thin. `engine/requisition.py` already knows how
to find conflicts in a requisition, and `engine/assessment.py` already knows
how to measure a candidate against one - so this module's only job is to put
the recruiter's words into that shape without deciding anything on their
behalf.

In particular it does not resolve conflicts. A junior role asking for five
years is passed through intact so that `detect_conflicts` can surface it and a
human can decide. Quietly relaxing either half would make the requisition look
coherent when it is not, which is the failure the conflict detector exists to
prevent.
"""

from __future__ import annotations

from pydantic import BaseModel

from engine.models import (
    Necessity,
    Requirement,
    RequirementConflict,
    Requisition,
    Seniority,
)
from engine.requisition import detect_conflicts
from engine.store.models import Job

# The wording `engine.assessment` recognises as a duration requirement rather
# than a skill. Reusing its vocabulary instead of inventing a parallel one is
# what keeps experience assessed by the existing code path.
EXPERIENCE_SKILL = "Professional Experience"

# Same reasoning for the salary constraint: the engine keys on the presence of
# `max_salary_lpa`, so the requirement simply carries it.
SALARY_SKILL = "Salary Expectation"


class JobAnalysis(BaseModel):
    """The structured reading of a job, plus anything wrong with it."""

    requisition: Requisition
    conflicts: list[RequirementConflict]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def required_count(self) -> int:
        return len(self.requisition.required)

    @property
    def preferred_count(self) -> int:
        return len(self.requisition.preferred)


def _seniority(value: str) -> Seniority:
    """Read the advertised level, defaulting to junior rather than guessing up.

    An unrecognised level must not silently become `senior`: that would make a
    junior-versus-experience conflict disappear, which is precisely the thing
    an evaluator asks about.
    """
    try:
        return Seniority(value.strip().lower())
    except ValueError:
        return Seniority.JUNIOR


def to_requisition(job: Job) -> Requisition:
    """Express a job posting in the engine's requisition vocabulary."""
    requirements: list[Requirement] = []

    for spec in job.required_skills:
        if not spec.skill.strip():
            continue
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1}",
                skill=spec.skill.strip(),
                necessity=Necessity.REQUIRED,
                min_years=spec.min_years,
                description=f"Required for {job.title}.",
            )
        )

    for spec in job.preferred_skills:
        if not spec.skill.strip():
            continue
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1}",
                skill=spec.skill.strip(),
                necessity=Necessity.PREFERRED,
                min_years=spec.min_years,
                description=f"Preferred for {job.title}.",
            )
        )

    if job.min_years_total is not None:
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1}",
                skill=EXPERIENCE_SKILL,
                necessity=Necessity.REQUIRED,
                min_years=job.min_years_total,
                description=(
                    f"{job.min_years_total:g}+ years of professional experience."
                ),
            )
        )

    if job.max_salary_lpa is not None:
        requirements.append(
            Requirement(
                id=f"R{len(requirements) + 1}",
                skill=SALARY_SKILL,
                necessity=Necessity.REQUIRED,
                max_salary_lpa=job.max_salary_lpa,
                description=f"Budget is capped at {job.max_salary_lpa:g} LPA.",
            )
        )

    return Requisition(
        id=job.id,
        title=job.title,
        seniority=_seniority(job.seniority),
        requirements=requirements,
    )


def analyze_job(job: Job) -> JobAnalysis:
    """Structure a job and report any internal conflict, without resolving it."""
    requisition = to_requisition(job)
    return JobAnalysis(
        requisition=requisition,
        conflicts=detect_conflicts(requisition),
    )
