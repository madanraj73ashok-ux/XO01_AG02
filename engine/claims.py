"""Claim extraction.

Finds every skill a candidate asserts, records how strongly they asserted it,
and keeps the sentence it came from. Nothing here judges whether the claim is
justified - that is the evidence grader's job. Keeping the two apart is what
stops a confidently-worded claim from being mistaken for a supported one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine.equivalence import known_surface_forms, normalize
from engine.models import Application, Claim, ClaimStrength, Section

# Wording candidates use to assert a level of mastery. Recorded, never
# treated as evidence.
STRENGTH_MARKERS: dict[ClaimStrength, tuple[str, ...]] = {
    ClaimStrength.EXPERT: ("expert", "expertise", "mastery", "advanced",
                           "deep expertise", "highly experienced"),
    ClaimStrength.PROFICIENT: ("proficient", "strong", "solid", "experienced",
                               "hands-on", "competent"),
    ClaimStrength.FAMILIAR: ("familiar", "basic", "exposure", "beginner",
                             "coursework", "introductory", "some experience"),
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def load_application(path: str | Path) -> Application:
    """Load and validate one application from JSON."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Application.model_validate(raw)


def load_applications(directory: str | Path) -> list[Application]:
    """Load every application in a directory, ordered by id."""
    files = sorted(Path(directory).glob("*.json"))
    return sorted(
        (load_application(path) for path in files),
        key=lambda application: application.id,
    )


def extract_claims(application: Application) -> list[Claim]:
    """Extract every recognised skill claim from an application."""
    return [
        claim
        for section in application.sections
        for claim in _claims_in_section(section)
    ]


def _claims_in_section(section: Section) -> list[Claim]:
    """Find skill mentions in one section, one claim per skill per sentence."""
    vocabulary = known_surface_forms()
    claims: list[Claim] = []
    seen: set[tuple[str, str]] = set()

    for sentence in _sentences(section.text):
        normalized_sentence = normalize(sentence)
        strength = _detect_strength(normalized_sentence)

        for surface_form, canonical in vocabulary.items():
            if not _mentions(normalized_sentence, surface_form):
                continue

            key = (canonical, sentence)
            if key in seen:
                continue
            seen.add(key)

            claims.append(
                Claim(
                    skill=canonical,
                    surface_form=surface_form,
                    strength=strength,
                    section=section.kind,
                    source_text=sentence.strip(),
                )
            )

    return claims


def _sentences(text: str) -> list[str]:
    """Split a block of text into sentence-sized provenance spans."""
    return [part for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _mentions(normalized_sentence: str, surface_form: str) -> bool:
    """Whole-token containment check.

    Guards against 'ml' matching inside 'html' and similar false positives
    that would make the extractor look like a naive substring matcher.
    """
    pattern = rf"(?<![a-z0-9]){re.escape(surface_form)}(?![a-z0-9])"
    return re.search(pattern, normalized_sentence) is not None


def _detect_strength(normalized_sentence: str) -> ClaimStrength:
    """Read the mastery wording the candidate used, if any."""
    for strength, markers in STRENGTH_MARKERS.items():
        if any(_mentions(normalized_sentence, normalize(m)) for m in markers):
            return strength
    return ClaimStrength.UNSPECIFIED
