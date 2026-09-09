"""Terminology equivalence.

PS02 requires that the agent "must not penalize equivalent skills described in
different wording" - while still not blindly accepting anything that merely
looks adjacent. Someone who writes "built ROS 2 navigation packages" has the
skill; someone whose only robotics exposure is Arduino does not, even though
both sit in the same broad field.

This module therefore answers a four-way question, not a yes/no one:
exact, equivalent, related (surfaced but not accepted), or none.
"""

from __future__ import annotations

import re

from engine.models import MatchKind, SkillMatch

# Canonical skill -> alternative wordings that mean the same capability.
# Curated deliberately: every entry here is a claim that two phrasings are
# interchangeable for screening purposes, and each one is defensible.
SKILL_ALIASES: dict[str, set[str]] = {
    "ROS 2": {"ros2", "ros 2", "ros-2", "robot operating system 2", "ros 2 humble",
              "ros2 humble", "ros 2 foxy", "rclpy", "rclcpp"},
    "Python": {"python", "python 3", "python3", "cpython"},
    "Computer Vision": {"computer vision", "opencv", "image processing",
                        "visual perception", "cv pipeline"},
    "Version Control": {"version control", "git", "github", "gitlab",
                        "source control", "branching workflow"},
    "Robotics": {"robotics", "mobile robotics", "autonomous robots",
                 "autonomous mobile robot", "robot development", "amr"},
    "Cloud Deployment": {"cloud deployment", "aws", "amazon web services",
                         "azure", "gcp", "google cloud", "cloud infrastructure"},
    "Containerization": {"containerization", "docker", "podman", "containers"},
    "Kubernetes": {"kubernetes", "k8s", "kube"},
    "Container Orchestration": {"container orchestration", "container orchestrator",
                                "orchestration platform", "workload orchestration"},
    "Simulation": {"simulation", "gazebo", "rviz", "isaac sim", "webots"},
    "Machine Learning": {"machine learning", "ml", "supervised learning",
                         "scikit-learn", "sklearn", "ai/ml", "ai ml",
                         "artificial intelligence"},
    "Deep Learning": {"deep learning", "neural networks", "pytorch",
                      "tensorflow", "cnn"},
}

# Pairs that are adjacent but NOT interchangeable. Encoded explicitly so the
# system can say *why* something was not accepted, instead of silently
# returning "no match" and looking like a keyword matcher that missed.
RELATED_SKILLS: dict[str, set[str]] = {
    "ROS 2": {"ros", "ros 1", "ros1", "arduino", "raspberry pi", "microros"},
    "Cloud Deployment": {"docker", "containerization", "kubernetes", "k8s",
                         "ci/cd", "localhost deployment"},
    "Computer Vision": {"image annotation", "photoshop", "matplotlib"},
    "Machine Learning": {"data analysis", "pandas", "statistics"},
    "Deep Learning": {"machine learning", "ml"},
    "Robotics": {"arduino", "embedded systems", "iot", "mechatronics"},
    "Simulation": {"cad", "solidworks", "blender"},
    # The case an evaluator asked about directly. A managed container service
    # is genuinely adjacent to container orchestration, and a great many
    # candidates who have used ECS have never configured a scheduler, written
    # a manifest, or handled a rollout. Accepting it as equivalent would let a
    # keyword do the work the evidence is supposed to do - so it lands here,
    # is surfaced to the recruiter with the reason, and must be argued for by
    # actual evidence rather than by vocabulary.
    "Container Orchestration": {"ecs", "aws ecs", "elastic container service",
                                "fargate", "aws fargate", "ecr", "docker",
                                "docker compose", "docker-compose",
                                "containerization", "containers", "podman"},
    "Kubernetes": {"ecs", "aws ecs", "elastic container service", "docker",
                   "docker compose", "docker swarm", "nomad"},
}

# Canonical skills that genuinely denote the same capability. Kept separate
# from SKILL_ALIASES because both names are first-class requirements a
# requisition might ask for by either wording, and folding one into the other
# would silently rename what the recruiter actually wrote.
EQUIVALENT_CANONICALS: dict[str, set[str]] = {
    "Container Orchestration": {"Kubernetes"},
    "Kubernetes": {"Container Orchestration"},
}

_PUNCTUATION = re.compile(r"[^a-z0-9+#. ]+")
_WHITESPACE = re.compile(r"\s+")


def normalize(phrase: str) -> str:
    """Reduce a phrase to a comparable form.

    Lowercases, strips punctuation and collapses whitespace so that
    "ROS-2", "ros 2" and "ROS 2  " all compare equal.
    """
    lowered = phrase.strip().casefold()
    cleaned = _PUNCTUATION.sub(" ", lowered)
    return _WHITESPACE.sub(" ", cleaned).strip()


def known_surface_forms() -> dict[str, str]:
    """Map every recognised wording to its canonical skill.

    Used by claim extraction to know what vocabulary to look for.
    """
    return {
        normalize(alias): canonical
        for canonical, aliases in SKILL_ALIASES.items()
        for alias in aliases
    }


def canonical_for(phrase: str) -> str | None:
    """Return the canonical skill a phrase denotes, if it is recognised."""
    return known_surface_forms().get(normalize(phrase))


def classify(candidate_phrase: str, required_skill: str) -> SkillMatch:
    """Classify how a candidate's wording relates to a required skill."""
    normalized_phrase = normalize(candidate_phrase)
    normalized_required = normalize(required_skill)
    canonical = canonical_for(required_skill) or required_skill

    if normalized_phrase == normalized_required:
        return SkillMatch(
            surface_form=candidate_phrase,
            canonical_skill=canonical,
            kind=MatchKind.EXACT,
            explanation=f"'{candidate_phrase}' matches the requirement wording exactly.",
        )

    if canonical_for(candidate_phrase) == canonical:
        return SkillMatch(
            surface_form=candidate_phrase,
            canonical_skill=canonical,
            kind=MatchKind.EQUIVALENT,
            explanation=(
                f"'{candidate_phrase}' is recognised terminology for "
                f"'{canonical}' and is accepted as equivalent."
            ),
        )

    if canonical_for(candidate_phrase) in EQUIVALENT_CANONICALS.get(canonical, set()):
        return SkillMatch(
            surface_form=candidate_phrase,
            canonical_skill=canonical,
            kind=MatchKind.EQUIVALENT,
            explanation=(
                f"'{candidate_phrase}' denotes the same capability as "
                f"'{canonical}' and is accepted as equivalent."
            ),
        )

    if normalized_phrase in {normalize(s) for s in RELATED_SKILLS.get(canonical, set())}:
        return SkillMatch(
            surface_form=candidate_phrase,
            canonical_skill=canonical,
            kind=MatchKind.RELATED,
            explanation=(
                f"'{candidate_phrase}' is adjacent to '{canonical}' but is not "
                f"the same capability, so it does not satisfy the requirement."
            ),
        )

    return SkillMatch(
        surface_form=candidate_phrase,
        canonical_skill=canonical,
        kind=MatchKind.NONE,
        explanation=(
            f"No recognised relationship between '{candidate_phrase}' and "
            f"'{canonical}'."
        ),
    )
