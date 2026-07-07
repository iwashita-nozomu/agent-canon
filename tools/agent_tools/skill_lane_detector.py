#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Detects structural project-owned skill lane routing concepts.
# upstream design ../../agents/skills/task-routing.md task routing skill contract
# upstream design ../../agents/skills/structure-refactor.md project .codex/.agents boundary contract
# downstream implementation ./route.py selects public skills from structural concepts
# downstream implementation ../../.codex/hooks/skill_usage_logger.py logs prompt routing signals
# @dependency-end

"""Detect route-owned prompt concepts that should not live in catalog keywords."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

EvidenceGroup = tuple[str, ...]
EvidenceGroupsByCategory = Mapping[str, tuple[EvidenceGroup, ...]]


class EvidenceConcept(Protocol):
    """Shared concept shape used by route-owned evidence matching."""

    @property
    def required_evidence_categories(self) -> tuple[str, ...]:
        """Return categories required for this concept to match."""
        ...

    @property
    def evidence_groups(self) -> EvidenceGroupsByCategory:
        """Return keyword groups by evidence category."""
        ...



@dataclass(frozen=True)
class StructuralSkillLaneConcept:
    """Structural routing concept with typed evidence requirements."""

    name: str
    required_evidence_categories: tuple[str, ...]
    route_skills: tuple[str, ...]
    evidence_groups: EvidenceGroupsByCategory


@dataclass(frozen=True)
class StructuralSkillLaneMatch:
    """One detected structural skill-lane concept."""

    concept: StructuralSkillLaneConcept
    observed_evidence_categories: tuple[str, ...]

    def reason(self) -> str:
        """Return a stable route reason for tests and hook evidence."""
        observed = ",".join(self.observed_evidence_categories)
        required = ",".join(self.concept.required_evidence_categories)
        return (
            f"structural_concept={self.concept.name};"
            f"required_evidence={required};observed_evidence={observed}"
        )


@dataclass(frozen=True)
class ValidationFailureRepairConcept:
    """Route concept for same-intent validation failure repair."""

    name: str
    required_evidence_categories: tuple[str, ...]
    owner_skill: str
    secondary_skills: tuple[str, ...]
    evidence_groups: EvidenceGroupsByCategory


@dataclass(frozen=True)
class ValidationFailureRepairMatch:
    """One detected validation-failure repair concept."""

    concept: ValidationFailureRepairConcept
    observed_evidence_categories: tuple[str, ...]

    def reason(self) -> str:
        """Return a stable route reason for repair-owner selection."""
        observed = ",".join(self.observed_evidence_categories)
        required = ",".join(self.concept.required_evidence_categories)
        return (
            f"structural_concept={self.concept.name};"
            f"required_evidence={required};observed_evidence={observed};"
            "repair_contract=classify cause then proceed to owning repair surface;"
            "tests_are=validation_control_surface_not_default_work_owner"
        )


PROJECT_SKILL_LANE_CONCEPTS: tuple[StructuralSkillLaneConcept, ...] = (
    StructuralSkillLaneConcept(
        name="parent_repo_project_skill_lane",
        required_evidence_categories=("project_owner", "skill_lane_surface"),
        route_skills=("task-routing", "structure-refactor"),
        evidence_groups={
            "project_owner": (
                (".codex/project-skills",),
                ("project-skills",),
                ("parent", "repo"),
                ("parent-repo",),
                ("project-owned",),
                ("repo-specific",),
                ("親レポ",),
            ),
            "skill_lane_surface": (
                ("skill", "lane"),
                ("skill", "surface"),
                ("skill", "config"),
                ("skills.config",),
                ("[[skills.config]]",),
                ("skill.md",),
                ("固有スキル",),
                ("スキル", "置"),
            ),
            "runtime_boundary_surface": (
                (".codex", ".agents"),
                (".codex/config.toml",),
                (".agents/skills",),
                ("shared", "public", "catalog"),
            ),
        },
    ),
)

VALIDATION_FAILURE_REPAIR_CONCEPTS: tuple[ValidationFailureRepairConcept, ...] = (
    ValidationFailureRepairConcept(
        name="validation_failure_same_intent_repair",
        required_evidence_categories=("validation_failure",),
        owner_skill="codex-task-workflow",
        secondary_skills=("test-design",),
        evidence_groups={
            "validation_failure": (
                ("failed", "validation"),
                ("validation", "failure"),
                ("validation", "failing"),
                ("failing", "test"),
                ("failing", "tests"),
                ("tests", "failing"),
                ("failed", "test"),
                ("failed", "tests"),
                ("test", "failure"),
                ("tests", "failure"),
                ("failing", "contract"),
                ("cause_classification",),
                ("same-intent", "repair"),
                ("preserved-intent", "repair"),
            ),
        },
    ),
)


def text_matches_evidence_group(text: str, group: EvidenceGroup) -> bool:
    """Return whether all terms in one structural evidence group are present."""
    return all(term.casefold() in text for term in group)


def observed_evidence_categories(
    text: str,
    concept: EvidenceConcept,
) -> tuple[str, ...]:
    """Return evidence categories observed for one structural concept."""
    observed: list[str] = []
    for category, groups in concept.evidence_groups.items():
        if any(text_matches_evidence_group(text, group) for group in groups):
            observed.append(category)
    return tuple(observed)


def structural_skill_lane_concept_matches(
    text: str,
) -> tuple[StructuralSkillLaneMatch, ...]:
    """Return project-owned skill-lane concept matches for prompt text."""
    normalized = text.casefold()
    matches: list[StructuralSkillLaneMatch] = []
    for concept in PROJECT_SKILL_LANE_CONCEPTS:
        observed = observed_evidence_categories(normalized, concept)
        if all(category in observed for category in concept.required_evidence_categories):
            matches.append(StructuralSkillLaneMatch(concept, observed))
    return tuple(matches)


def validation_failure_repair_concept_matches(
    text: str,
) -> tuple[ValidationFailureRepairMatch, ...]:
    """Return same-intent repair concept matches for validation failures."""
    normalized = text.casefold()
    matches: list[ValidationFailureRepairMatch] = []
    for concept in VALIDATION_FAILURE_REPAIR_CONCEPTS:
        observed = observed_evidence_categories(normalized, concept)
        if all(category in observed for category in concept.required_evidence_categories):
            matches.append(ValidationFailureRepairMatch(concept, observed))
    return tuple(matches)
