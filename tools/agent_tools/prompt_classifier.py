#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Classifies prompt routing signals from immutable injected evidence.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md owns the pure classifier contract.
# downstream implementation ../agent_tools/evaluate_workflow_selection.py supplies frozen catalog/routing inputs.
# downstream implementation ./behavior_event_assembly.py consumes PromptIntakeSignals.
# downstream test ../../tests/agent_tools/test_prompt_classifier.py validates purity and field parity.
# @dependency-end
"""Pure prompt-intake classifier.

The classifier deliberately has no repository discovery, environment access, subprocess,
Git, network, or log side effects. Repository-dependent evidence is injected by callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import FrozenSet, Mapping, TypeAlias

from skill_lane_detector import SkillLaneEvidence

FrozenValue: TypeAlias = str | int | float | bool | None | tuple["FrozenValue", ...] | Mapping[str, "FrozenValue"]
FrozenMapping = Mapping[str, FrozenValue]

SKILL_TOKEN_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9_-]*)")
FIELD_RE = re.compile(
    r"(?:^|\s)(skills?|skill_invocation|workflow|workflow_family|selected_workflow|"
    r"candidate_skills?|candidate_workflows?|candidate_tools?|feedback_labels?|"
    r"feedback_action|tool)=([^\s]+)"
)
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

DEFAULT_SKILLS: FrozenSet[str] = frozenset(
    {
        "academic-writing", "adaptive-improvement-loop", "agent-canon-update",
        "agent-learning", "agent-log-analysis", "agent-orchestration",
        "change-review", "codex-task-workflow", "comprehensive-development",
        "computational-optimization", "dependency-analysis", "document-canon-cleanup",
        "environment-maintenance", "experiment-lifecycle", "experiment-review",
        "gpu-execution", "html-output", "literature-survey", "long-form-writing",
        "md-style-check", "oop-readability-check", "owner-bounded-routing",
        "paper-writing", "refactor-loop", "report-writing", "result-artifact-writeout",
        "research-workflow", "structure-planning", "structure-refactor", "subagent-bootstrap",
        "task-routing", "test-design", "tool-finding-report", "worktree-health",
    }
)

KEYWORD_SKILLS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("agentcanon", "update"), "agent-canon-update"),
    (("agent-canon", "update"), "agent-canon-update"),
    (("repo-wide",), "comprehensive-development"),
    (("workflow", "routing"), "task-routing"),
    (("skill", "selection"), "task-routing"),
    (("subagent", "routing"), "agent-orchestration"),
    (("refactor",), "refactor-loop"),
    (("structure",), "structure-refactor"),
    (("dependency",), "dependency-analysis"),
    (("markdown",), "md-style-check"),
    (("gpu",), "gpu-execution"),
    (("optimizer",), "computational-optimization"),
    (("solver",), "computational-optimization"),
    (("experiment",), "experiment-lifecycle"),
    (("review",), "change-review"),
)


@dataclass(frozen=True)
class PromptClassifierInputs:
    prompt: str
    repo_root: Path
    catalog: FrozenMapping
    routing_rules: FrozenMapping
    structural_lane_evidence: tuple[SkillLaneEvidence, ...] = ()
    validation_repair_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptIntakeSignals:
    skills: tuple[str, ...] = ()
    selected_workflows: tuple[str, ...] = ()
    candidate_skills: tuple[str, ...] = ()
    candidate_skill_reasons: tuple[str, ...] = ()
    candidate_workflows: tuple[str, ...] = ()
    candidate_tools: tuple[str, ...] = ()
    feedback_labels: tuple[str, ...] = ()
    feedback_action: str = ""

    def should_log(self) -> bool:
        return bool(
            self.skills
            or self.selected_workflows
            or self.candidate_skills
            or self.candidate_workflows
            or self.candidate_tools
            or self.feedback_labels
        )

    def feedback_targets(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.feedback_labels))


def freeze(value: object) -> FrozenValue:
    """Recursively freeze caller-provided data without reading it from disk."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in value.items()})  # type: ignore[return-value]
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        result: list[str] = []
        for item in value.values():
            result.extend(_strings(item))
        return tuple(result)
    if isinstance(value, (tuple, list)):
        result = []
        for item in value:
            result.extend(_strings(item))
        return tuple(result)
    return ()


def _catalog_skill_ids(inputs: PromptClassifierInputs) -> frozenset[str]:
    values = {value for value in _strings(inputs.catalog) if SKILL_ID_RE.fullmatch(value)}
    return frozenset(values | set(DEFAULT_SKILLS))


def _field_values(prompt: str) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for match in FIELD_RE.finditer(prompt):
        values.setdefault(match.group(1), []).append(match.group(2).strip("[](),"))
    return {key: tuple(item for item in items if item) for key, items in values.items()}


def _split_values(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in re.split(r"[,;]", value) if part.strip())
    return tuple(dict.fromkeys(result))


def _known_skill(value: str, known: frozenset[str]) -> bool:
    return value in known or value in DEFAULT_SKILLS


def prompt_intake_signals(inputs: PromptClassifierInputs) -> PromptIntakeSignals:
    """Classify one immutable prompt input into the eight parity fields."""
    prompt = inputs.prompt if isinstance(inputs.prompt, str) else ""
    lowered = prompt.casefold()
    fields = _field_values(prompt)
    known = _catalog_skill_ids(inputs)
    skills: list[str] = []
    for value in _split_values(fields.get("skill", ()) + fields.get("skills", ()) + fields.get("skill_invocation", ())):
        value = value.removeprefix("$")
        if _known_skill(value, known):
            skills.append(value)
    for value in SKILL_TOKEN_RE.findall(prompt):
        if _known_skill(value, known):
            skills.append(value)
    selected_workflows = list(_split_values(fields.get("workflow", ()) + fields.get("workflow_family", ()) + fields.get("selected_workflow", ())))
    selected_workflows = [value for value in selected_workflows if value and not value.startswith("$")]
    candidate_skills: list[str] = []
    reasons: list[str] = []
    for needles, skill in KEYWORD_SKILLS:
        if all(needle.casefold() in lowered for needle in needles):
            if skill not in skills:
                candidate_skills.append(skill)
                reasons.append("keyword=" + "+".join(needles))
    for lane in inputs.structural_lane_evidence:
        if lane.status not in {"observed", "candidate"}:
            continue
        reasons.append("structural_concept=" + lane.lane)
        destination = skills if lane.status == "observed" else candidate_skills
        destination.extend(lane.route_skills)
    for evidence in inputs.validation_repair_evidence:
        if evidence:
            reasons.append("validation_repair=" + evidence)
    candidate_skills.extend(_split_values(fields.get("candidate_skill", ()) + fields.get("candidate_skills", ())))
    candidate_workflows = list(_split_values(fields.get("candidate_workflow", ()) + fields.get("candidate_workflows", ())))
    if "repo-wide" in lowered and "comprehensive-development" not in selected_workflows:
        candidate_workflows.append("comprehensive-development")
    candidate_tools = list(_split_values(fields.get("candidate_tool", ()) + fields.get("candidate_tools", ()) + fields.get("tool", ())))
    if any(token in lowered for token in ("pytest", "python3", "python ")):
        candidate_tools.append("python3")
    feedback_labels = list(_split_values(fields.get("feedback", ()) + fields.get("feedback_label", ()) + fields.get("feedback_labels", ())))
    feedback_action = next(iter(_split_values(fields.get("feedback_action", ()))), "")
    return PromptIntakeSignals(
        skills=tuple(dict.fromkeys(skills)),
        selected_workflows=tuple(dict.fromkeys(selected_workflows)),
        candidate_skills=tuple(dict.fromkeys(item for item in candidate_skills if item not in skills)),
        candidate_skill_reasons=tuple(dict.fromkeys(reasons)),
        candidate_workflows=tuple(dict.fromkeys(candidate_workflows)),
        candidate_tools=tuple(dict.fromkeys(candidate_tools)),
        feedback_labels=tuple(dict.fromkeys(feedback_labels)),
        feedback_action=feedback_action,
    )


def feedback_targets(signals: PromptIntakeSignals) -> tuple[str, ...]:
    return signals.feedback_targets()


def should_log(signals: PromptIntakeSignals) -> bool:
    return signals.should_log()
