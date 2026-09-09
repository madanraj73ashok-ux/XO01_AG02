"""Domain models for evidence-first candidate screening.

The central distinction this system is built on: a *claim* is what a candidate
asserts, and *evidence* is what supports it. They are modelled separately and
never merged, so an unsupported claim can never be mistaken for a proven one.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Necessity(str, Enum):
    """Whether a requisition treats a requirement as mandatory."""

    REQUIRED = "required"
    PREFERRED = "preferred"


class Seniority(str, Enum):
    """Advertised level of the role."""

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class EvidenceLevel(str, Enum):
    """The evidence ladder - how well-supported a claim actually is.

    Deliberately independent of how strongly the candidate phrased the claim.
    A candidate may write "expert" and land at E0.
    """

    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"

    @property
    def label(self) -> str:
        return _EVIDENCE_LABELS[self]

    @property
    def description(self) -> str:
        return _EVIDENCE_DESCRIPTIONS[self]

    @property
    def rank(self) -> int:
        """Position on the ladder, for comparison."""
        return _EVIDENCE_RANKS[self]


_EVIDENCE_LABELS: dict[EvidenceLevel, str] = {
    EvidenceLevel.E0: "No evidence",
    EvidenceLevel.E1: "Weak",
    EvidenceLevel.E2: "Moderate",
    EvidenceLevel.E3: "Strong",
    EvidenceLevel.E4: "Very strong",
}

_EVIDENCE_DESCRIPTIONS: dict[EvidenceLevel, str] = {
    EvidenceLevel.E0: "Claim appears with nothing supporting it",
    EvidenceLevel.E1: "Skill listed only, a course, or a generic mention",
    EvidenceLevel.E2: "Academic or personal project with real description",
    EvidenceLevel.E3: "Work or internship project with implementation detail",
    EvidenceLevel.E4: "Multiple independent supporting signals, consistent timeline",
}

_EVIDENCE_RANKS: dict[EvidenceLevel, int] = {
    EvidenceLevel.E0: 0,
    EvidenceLevel.E1: 1,
    EvidenceLevel.E2: 2,
    EvidenceLevel.E3: 3,
    EvidenceLevel.E4: 4,
}


class ConflictKind(str, Enum):
    """Categories of internal inconsistency found in a requisition itself."""

    SENIORITY_EXPERIENCE_MISMATCH = "seniority_experience_mismatch"
    DUPLICATE_REQUIREMENT = "duplicate_requirement"


class Requirement(BaseModel):
    """A single criterion the requisition screens against."""

    id: str
    skill: str
    necessity: Necessity
    min_years: float | None = None
    description: str = ""

    @property
    def is_required(self) -> bool:
        return self.necessity is Necessity.REQUIRED


class RequirementConflict(BaseModel):
    """An internal inconsistency in the requisition, surfaced for human review.

    Conflicts are reported, never silently resolved - the recruiter decides.
    """

    kind: ConflictKind
    requirement_ids: list[str]
    detail: str
    recommendation: str


class Requisition(BaseModel):
    """A job requisition and the criteria it screens candidates against."""

    id: str
    title: str
    seniority: Seniority
    requirements: list[Requirement] = Field(default_factory=list)

    @property
    def required(self) -> list[Requirement]:
        return [r for r in self.requirements if r.is_required]

    @property
    def preferred(self) -> list[Requirement]:
        return [r for r in self.requirements if not r.is_required]


# --------------------------------------------------------------------------
# Applications and claims
# --------------------------------------------------------------------------


class SectionKind(str, Enum):
    """Where in an application a piece of text came from.

    The section matters: the same skill named in a Skills list and demonstrated
    in a work project are very different grades of support.
    """

    SKILLS = "skills"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    EDUCATION = "education"
    COVER_NOTE = "cover_note"


class Section(BaseModel):
    """One labelled block of an application's text."""

    kind: SectionKind
    text: str


class Application(BaseModel):
    """A candidate's submitted application."""

    id: str
    candidate_name: str
    sections: list[Section] = Field(default_factory=list)

    def section(self, kind: SectionKind) -> Section | None:
        return next((s for s in self.sections if s.kind is kind), None)

    @property
    def full_text(self) -> str:
        """All section text joined - used when scanning for adjacent skills."""
        return "\n".join(section.text for section in self.sections)


class ClaimStrength(str, Enum):
    """How strongly the candidate phrased the claim.

    Never treated as evidence. It is recorded so the system can show the gap
    between what was asserted and what is actually supported.
    """

    EXPERT = "expert"
    PROFICIENT = "proficient"
    FAMILIAR = "familiar"
    UNSPECIFIED = "unspecified"


class MatchKind(str, Enum):
    """How a phrase in an application relates to a requisition skill."""

    EXACT = "exact"
    EQUIVALENT = "equivalent"
    RELATED = "related"
    NONE = "none"

    @property
    def satisfies_requirement(self) -> bool:
        """Only exact and equivalent matches count toward a requirement.

        A related technology is surfaced to the recruiter but never silently
        accepted as the required skill.
        """
        return self in (MatchKind.EXACT, MatchKind.EQUIVALENT)


class SkillMatch(BaseModel):
    """The relationship between a candidate's wording and a canonical skill."""

    surface_form: str
    canonical_skill: str
    kind: MatchKind
    explanation: str


class Claim(BaseModel):
    """A skill a candidate asserts, with where and how they asserted it.

    `source_text` is the sentence the claim was found in, kept so every
    downstream assessment can cite the exact wording it relied on.
    """

    skill: str
    surface_form: str
    strength: ClaimStrength
    section: SectionKind
    source_text: str


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """One piece of support found for a claim, with its provenance.

    `source_text` is always quoted from the application. Nothing here is
    generated - if the system cannot point at real text, there is no evidence.
    """

    section: SectionKind
    source_text: str
    weight: int
    note: str


class ClaimAssessment(BaseModel):
    """The graded verdict on one skill claim.

    Holds the asserted strength and the earned evidence level side by side,
    so the gap between them is always visible rather than averaged away.
    """

    skill: str
    claimed_strength: ClaimStrength
    evidence_level: EvidenceLevel
    supporting: list[EvidenceItem] = Field(default_factory=list)
    assertions: list[EvidenceItem] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """Whether any real support was found at all."""
        return self.evidence_level is not EvidenceLevel.E0

    @property
    def is_overclaimed(self) -> bool:
        """True when the candidate asserted more than the evidence carries.

        This is the PS02 failure case: "expert" backed by nothing.
        """
        expected = _MINIMUM_EVIDENCE_FOR_CLAIM.get(self.claimed_strength)
        if expected is None:
            return False
        return self.evidence_level.rank < expected.rank


# The evidence level a given claimed strength ought to be able to show.
# Used only to flag a gap for review - never to reject a candidate.
_MINIMUM_EVIDENCE_FOR_CLAIM: dict[ClaimStrength, EvidenceLevel] = {
    ClaimStrength.EXPERT: EvidenceLevel.E3,
    ClaimStrength.PROFICIENT: EvidenceLevel.E2,
}


# --------------------------------------------------------------------------
# Requirement fit
# --------------------------------------------------------------------------


class FitStatus(str, Enum):
    """How well a candidate meets one requirement.

    `UNADDRESSED` is deliberately distinct from a low score: the candidate did
    not speak to this criterion at all, which is a different fact about them
    than having spoken to it weakly.
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNADDRESSED = "unaddressed"

    @property
    def label(self) -> str:
        return _FIT_LABELS[self]


_FIT_LABELS: dict[FitStatus, str] = {
    FitStatus.STRONG: "Strong",
    FitStatus.MODERATE: "Moderate",
    FitStatus.WEAK: "Weak",
    FitStatus.UNADDRESSED: "Unaddressed",
}


class RequirementFit(BaseModel):
    """How one candidate measures against one requirement, and why."""

    requirement_id: str
    skill: str
    necessity: Necessity
    status: FitStatus
    evidence_level: EvidenceLevel
    match_kind: MatchKind
    claimed_strength: ClaimStrength = ClaimStrength.UNSPECIFIED
    is_overclaimed: bool = False
    supporting: list[EvidenceItem] = Field(default_factory=list)
    closest_evidence: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @property
    def is_required(self) -> bool:
        return self.necessity is Necessity.REQUIRED

    @property
    def is_met(self) -> bool:
        """Whether this counts as genuinely satisfied.

        Moderate is not counted as met: an academic project alone does not
        demonstrate a required professional capability.
        """
        return self.status is FitStatus.STRONG


class CandidateAssessment(BaseModel):
    """A candidate measured against every criterion in the requisition.

    Deliberately exposes a breakdown rather than one number. PS02 forbids
    collapsing multi-dimensional fit into a single opaque score.
    """

    application_id: str
    candidate_name: str
    fits: list[RequirementFit] = Field(default_factory=list)

    @property
    def required_fits(self) -> list[RequirementFit]:
        return [fit for fit in self.fits if fit.is_required]

    @property
    def strong_required(self) -> list[RequirementFit]:
        return [fit for fit in self.required_fits if fit.is_met]

    @property
    def unaddressed_required(self) -> list[RequirementFit]:
        return [
            fit
            for fit in self.required_fits
            if fit.status is FitStatus.UNADDRESSED
        ]

    @property
    def overclaims(self) -> list[RequirementFit]:
        """Requirements where the candidate asserted more than they showed."""
        return [fit for fit in self.fits if fit.is_overclaimed]

    @property
    def below_bar_required(self) -> list[RequirementFit]:
        """Required criteria the candidate spoke to, but did not demonstrate."""
        return [
            fit
            for fit in self.required_fits
            if not fit.is_met and fit.status is not FitStatus.UNADDRESSED
        ]

    @property
    def summary(self) -> str:
        """A one-line breakdown - never a bare score.

        Names every required criterion that is not met, and says so separately
        for "never addressed" and "addressed but not demonstrated". A summary
        that reported only a count would hide the case PS02 exists to catch:
        a required area resting on an unsupported claim.
        """
        parts = [
            f"{len(self.strong_required)} of {len(self.required_fits)} "
            f"required areas strong"
        ]

        unaddressed = self.unaddressed_required
        if unaddressed:
            names = ", ".join(fit.skill for fit in unaddressed)
            parts.append(f"{len(unaddressed)} unaddressed ({names})")

        below = self.below_bar_required
        if below:
            names = ", ".join(fit.skill for fit in below)
            parts.append(f"{len(below)} below bar ({names})")

        overclaims = self.overclaims
        if overclaims:
            plural = "s" if len(overclaims) > 1 else ""
            parts.append(f"{len(overclaims)} unsupported claim{plural} flagged")

        return "; ".join(parts)
