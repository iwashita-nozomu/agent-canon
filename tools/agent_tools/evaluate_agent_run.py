#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides evaluate agent run agent workflow automation.
# upstream design ../../agents/workflows/agent-learning-workflow.md behavior feedback
# upstream design ../../agents/templates/agent_evaluation.md defines evaluation artifact shape
# upstream design ../../agents/templates/workflow_monitoring.md monitoring evidence
# upstream implementation ./report_artifact_checks.py validates schedule and work log completeness
# downstream implementation ../../tests/agent_tools/test_evaluate_agent_run.py verifies scoring
# @dependency-end
"""Evaluate one run bundle and write actionable agent feedback."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from agent_team import resolve_report_root
from eval_manifest_paths import eval_manifest_path, resolve_eval_manifest
from report_artifact_checks import (
    check_final_review_artifact,
    check_schedule_artifact,
    check_work_log_artifact,
    has_approve_decision,
    section_has_content,
)

DEFAULT_MIN_SCORE = 85
DEFAULT_BEHAVIOR_CRITERION_MAX_SCORE = 5
ARTIFACT_COMPLETENESS_SCORE = 8
REQUEST_TRACEABILITY_SCORE = 10
PLANNED_WORK_AND_CHRONOLOGY_SCORE = 10
WORKFLOW_MONITORING_SCORE = 12
TOOL_WARNING_OBLIGATION_SCORE = 8
ORCHESTRATION_INTAKE_SCORE = 12
PROMPT_EVAL_ARTIFACT_SCORE = 8
REVIEW_FEEDBACK_LOOP_SCORE = 10
VALIDATION_AND_CLOSEOUT_SCORE = 12
DEPENDENCY_AND_CANONICAL_SCORE = 10
SELF_IMPROVEMENT_FEEDBACK_SCORE = 16
SELF_IMPROVEMENT_FEEDBACK_PARTIAL_SCORE = 8
MARKDOWN_COMMENT_PATTERN = re.compile(r"<!--.*?-->", flags=re.DOTALL)
SKILL_INVOCATION_PATTERN = re.compile(r"\bskill_invocation=\$?([A-Za-z0-9_-]+)")
EVAL_FIELD_PATTERN = re.compile(r"\b(EVAL_RUN_ID|EVAL_ACCUMULATED_REPORT|EVAL_USED_SKILLS)=([^\s]+)")
REQUIRED_ARTIFACTS = (
    "user_request_contract.md",
    "schedule.md",
    "work_log.md",
    "workflow_monitoring.md",
    "change_review.md",
    "final_review.md",
    "verification.txt",
    "closeout_gate.md",
    "retrospective.md",
)
DEFAULT_BEHAVIOR_MANIFEST = eval_manifest_path("agent_behavior_eval.toml")
RUNTIME_PROFILE_INVENTORY_PATH = (
    Path(__file__).resolve().parents[2]
    / "documents"
    / "runtime-profiles-and-check-matrix.json"
)


def validation_failure_taxonomy_values(field: str) -> frozenset[str]:
    """Load one validation-failure slug set from the runtime profile inventory."""
    raw_data = json.loads(RUNTIME_PROFILE_INVENTORY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw_data, dict):
        raise ValueError("runtime profile inventory must be a JSON object")
    data = cast(dict[str, object], raw_data)
    raw_response = data.get("validation_failure_response")
    if not isinstance(raw_response, dict):
        raise ValueError("runtime profile inventory missing validation_failure_response")
    response = cast(dict[str, object], raw_response)
    raw_values = response.get(field)
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError(
            f"runtime profile inventory missing validation_failure_response.{field}"
        )
    values = cast(list[object], raw_values)
    slugs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"validation_failure_response.{field} must contain strings"
            )
        slugs.append(value)
    return frozenset(slugs)


def validation_failure_taxonomy_slug(
    field: str,
    values: frozenset[str],
    slug: str,
) -> str:
    """Return one route slug only when the runtime inventory owns it."""
    if slug not in values:
        raise ValueError(
            f"runtime profile inventory missing validation_failure_response.{field} "
            f"slug: {slug}"
        )
    return slug


def validation_failure_taxonomy_slug_subset(
    field: str,
    values: frozenset[str],
    slugs: tuple[str, ...],
) -> frozenset[str]:
    """Return route-specific slugs after validating them against the inventory."""
    return frozenset(
        validation_failure_taxonomy_slug(field, values, slug) for slug in slugs
    )


def validation_failure_slug_hint(values: frozenset[str]) -> str:
    """Return a feedback hint from the inventory-owned slug set."""
    return "<" + "|".join(sorted(values)) + ">"


VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES = validation_failure_taxonomy_values(
    "cause_classes"
)
VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES = validation_failure_taxonomy_values(
    "intent_preservation"
)
VALIDATION_FAILURE_IMPLEMENTATION_BUG = validation_failure_taxonomy_slug(
    "cause_classes",
    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES,
    "implementation_bug",
)
VALIDATION_FAILURE_REPAIR_SAME_INTENT = validation_failure_taxonomy_slug(
    "intent_preservation",
    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES,
    "repair_same_intent",
)
VALIDATION_FAILURE_DESIGN_CONFLICT = validation_failure_taxonomy_slug(
    "cause_classes",
    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES,
    "approved_design_user_request_conflict",
)
VALIDATION_FAILURE_ESCALATE_DESIGN_CONFLICT = validation_failure_taxonomy_slug(
    "intent_preservation",
    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES,
    "escalate_design_conflict",
)
VALIDATION_FAILURE_FORBIDDEN_TOKENS = (
    "oracle_weakening=",
    "oracle_deleted=",
    "test_deleted=",
    "behavior_simplified=",
    "validation_downscope=",
)
RESIDUAL_CHECKER_FAILURE_CAUSES = validation_failure_taxonomy_slug_subset(
    "cause_classes",
    VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES,
    ("fixture_environment_issue", "pre_existing_unrelated_failure"),
)


@dataclass(frozen=True)
class CriterionResult:
    """One rubric criterion result."""

    name: str
    score: int
    max_score: int
    status: str
    feedback: str


@dataclass(frozen=True)
class BehaviorCriterion:
    """One manifest-defined behavior criterion."""

    name: str
    max_score: int
    feedback: str
    source: str
    required_all: tuple[str, ...]
    required_any: tuple[str, ...]
    forbidden_any: tuple[str, ...]


@dataclass(frozen=True)
class RunEvidence:
    """Text and status evidence collected from one run bundle."""

    missing_artifacts: tuple[str, ...]
    request_contract: dict[str, str]
    verification: dict[str, str]
    closeout: dict[str, str]
    schedule_text: str
    work_log_text: str
    monitoring_text: str
    monitoring_status: dict[str, str]
    retrospective_text: str
    final_decision: str
    change_review_text: str
    final_review_text: str
    normalized_bundle: str
    signals_text: str
    behavior_events_text: str
    behavior_events_raw_text: str
    tool_warnings_text: str


@dataclass(frozen=True)
class PromptEvalEvent:
    """One accumulated prompt eval event recorded in workflow monitoring."""

    eval_run_id: str
    report_path: str
    used_skills: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Grade a run bundle and produce agent feedback actions."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", help="Run id under reports/agents/.")
    group.add_argument("--report-dir", help="Explicit run directory to inspect.")
    parser.add_argument(
        "--report-root",
        help="Optional report root. Defaults to ./reports/agents under the workspace.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used with --run-id and relative report roots.",
    )
    parser.add_argument(
        "--output",
        default="agent_evaluation.md",
        help="Evaluation artifact path relative to report dir, or an absolute path.",
    )
    parser.add_argument(
        "--behavior-manifest",
        default=DEFAULT_BEHAVIOR_MANIFEST,
        help="Behavior eval TOML manifest, relative to workspace root unless absolute.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the evaluation artifact. Without this, only print status lines.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"Minimum passing score. Defaults to {DEFAULT_MIN_SCORE}.",
    )
    return parser


def string_tuple(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of strings from a manifest value."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    strings: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise ValueError(f"{field} must be a list of strings")
        strings.append(item)
    return tuple(strings)


def markdown_section_text(text: str, heading: str) -> str:
    """Return one level-2 Markdown section without comments."""
    return markdown_section_text_raw(text, heading).lower()


def markdown_section_text_raw(text: str, heading: str) -> str:
    """Return one level-2 Markdown section without lowercasing."""
    lines = markdown_without_comments(text).splitlines()
    return "\n".join(markdown_section_lines(lines, heading))


def markdown_section_lines(lines: list[str], heading: str) -> Iterator[str]:
    """Yield lines from one level-2 Markdown section."""
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
        if in_section:
            yield line


def load_behavior_manifest(path: Path) -> tuple[BehaviorCriterion, ...]:
    """Load manifest-defined behavior criteria."""
    data = cast(dict[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    raw_criteria = data.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ValueError("behavior manifest must define at least one [[criteria]] entry")
    criteria = cast(list[object], raw_criteria)
    return tuple(
        behavior_criterion_from_manifest_entry(index, entry)
        for index, entry in enumerate(criteria, 1)
    )


def behavior_criterion_from_manifest_entry(
    index: int,
    entry: object,
) -> BehaviorCriterion:
    """Build one behavior criterion from a manifest entry."""
    if not isinstance(entry, dict):
        raise ValueError(f"behavior criterion {index} must be a table")
    mapping = cast(dict[str, object], entry)
    name = str(mapping["name"])
    source = str(mapping.get("source", "behavior_events"))
    if source not in {"behavior_events", "bundle"}:
        raise ValueError(f"behavior criterion {name} has invalid source={source}")
    feedback = str(mapping.get("feedback", f"Record behavior evidence for {name}."))
    return BehaviorCriterion(
        name=name,
        max_score=int(
            str(mapping.get("max_score", DEFAULT_BEHAVIOR_CRITERION_MAX_SCORE))
        ),
        feedback=feedback,
        source=source,
        required_all=string_tuple(mapping.get("required_all"), f"{name}.required_all"),
        required_any=string_tuple(mapping.get("required_any"), f"{name}.required_any"),
        forbidden_any=string_tuple(
            mapping.get("forbidden_any"),
            f"{name}.forbidden_any",
        ),
    )


def parse_kv_lines(path: Path) -> dict[str, str]:
    """Parse a simple key=value file."""
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def parse_markdown_status(path: Path) -> dict[str, str]:
    """Parse '- key: value' status lines from a markdown artifact."""
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def markdown_decision(path: Path) -> str:
    """Return the first non-empty line under a Decision section."""
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_decision = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_decision = stripped == "## Decision"
            continue
        if in_decision and stripped and not stripped.startswith("<!--"):
            return stripped.lower()
    return ""


def artifact_text(report_dir: Path, name: str) -> str:
    """Return artifact text or an empty string."""
    path = report_dir / name
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def markdown_without_comments(text: str) -> str:
    """Return markdown text without HTML comments."""
    cleaned = MARKDOWN_COMMENT_PATTERN.sub("", text)
    return cleaned


def bundle_text(report_dir: Path) -> str:
    """Return normalized text from all markdown and text run artifacts."""
    return "\n".join(
        markdown_without_comments(path.read_text(encoding="utf-8"))
        for path in sorted(report_dir.glob("*"))
        if path.suffix in {".md", ".txt", ".yaml", ".yml"}
    ).lower()


def has_any(text: str, needles: tuple[str, ...]) -> bool:
    """Return whether normalized text contains any evidence token."""
    return any(needle.lower() in text for needle in needles)


def status_in(status: dict[str, str], key: str, allowed: set[str]) -> bool:
    """Return whether one markdown status key has an allowed value."""
    return status.get(key, "").strip().lower() in allowed


def has_open_review_findings(*texts: str) -> bool:
    """Return whether review artifacts still carry open fix-now findings."""
    for text in texts:
        cleaned = markdown_without_comments(text).lower()
        for line in cleaned.splitlines():
            if re.search(r"\b(no|none)\b.*\b(fix-now|required_change|open)\b", line):
                continue
            if "fix-now" in line and any(token in line for token in ("open", "pending")):
                return True
            if "required_change" in line and not any(
                token in line for token in ("resolved", "applied", "fixed", "closed")
            ):
                return True
    return False


def criterion(
    name: str,
    max_score: int,
    passed: bool,
    feedback: str,
    partial_score: int = 0,
) -> CriterionResult:
    """Build one criterion result."""
    if passed:
        return CriterionResult(name, max_score, max_score, "pass", "No action required.")
    return CriterionResult(name, partial_score, max_score, "revise", feedback)


def read_run_evidence(report_dir: Path) -> RunEvidence:
    """Read one run bundle into typed evidence."""
    missing = [name for name in REQUIRED_ARTIFACTS if not (report_dir / name).is_file()]
    monitoring_text = artifact_text(report_dir, "workflow_monitoring.md")
    behavior_events_raw_text = markdown_section_text_raw(
        monitoring_text,
        "## Behavior Events",
    )
    tool_warnings_text = markdown_section_text_raw(
        monitoring_text,
        "## Tool Warnings",
    )
    return RunEvidence(
        missing_artifacts=tuple(missing),
        request_contract=parse_markdown_status(
            report_dir / "user_request_contract.md"
        ),
        verification=parse_kv_lines(report_dir / "verification.txt"),
        closeout=parse_markdown_status(report_dir / "closeout_gate.md"),
        schedule_text=artifact_text(report_dir, "schedule.md"),
        work_log_text=artifact_text(report_dir, "work_log.md"),
        monitoring_text=monitoring_text,
        monitoring_status=parse_markdown_status(
            report_dir / "workflow_monitoring.md"
        ),
        retrospective_text=artifact_text(report_dir, "retrospective.md"),
        final_decision=markdown_decision(report_dir / "final_review.md"),
        change_review_text=artifact_text(report_dir, "change_review.md"),
        final_review_text=artifact_text(report_dir, "final_review.md"),
        normalized_bundle=bundle_text(report_dir),
        signals_text=markdown_section_text(monitoring_text, "## Signals"),
        behavior_events_text=markdown_section_text(
            monitoring_text,
            "## Behavior Events",
        ),
        behavior_events_raw_text=behavior_events_raw_text,
        tool_warnings_text=tool_warnings_text,
    )


def monitoring_sections_complete(evidence: RunEvidence) -> bool:
    """Return whether required monitoring sections contain content."""
    return all(
        section_has_content(evidence.monitoring_text, heading)
        for heading in (
            "## Signals",
            "## Behavior Events",
            "## Tool Warnings",
            "## Interventions",
            "## Improvement Decisions",
        )
    )


def improvement_decisions_complete(evidence: RunEvidence) -> bool:
    """Return whether improvement decisions are closed."""
    return all(
        status_in(
            evidence.monitoring_status,
            key,
            {"applied", "recorded", "not_applicable"},
        )
        for key in (
            "skill_improvement_decision",
            "config_improvement_decision",
            "workflow_improvement_decision",
            "memory_learning_decision",
        )
    )


def improvement_decision_applied_or_recorded(evidence: RunEvidence) -> bool:
    """Return whether at least one improvement decision changed durable state."""
    return any(
        status_in(evidence.monitoring_status, key, {"applied", "recorded"})
        for key in (
            "skill_improvement_decision",
            "config_improvement_decision",
            "workflow_improvement_decision",
            "memory_learning_decision",
        )
    )


def runtime_feedback_requires_improvement(evidence: RunEvidence) -> bool:
    """Return whether observed runtime feedback requires a non-no-op decision."""
    text = evidence.behavior_events_text
    return "runtime_feedback=observed" in text and "action=no_op" not in text


def runtime_feedback_closure_complete(evidence: RunEvidence) -> bool:
    """Return whether observed runtime feedback was closed into an action route."""
    if not runtime_feedback_requires_improvement(evidence):
        return True
    return improvement_decisions_complete(evidence) and improvement_decision_applied_or_recorded(evidence)


def token_fields(line: str) -> dict[str, str]:
    """Parse whitespace-separated key=value fields from one evidence line."""
    data: dict[str, str] = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip("`'\"")
    return data


def tool_warning_problems(evidence: RunEvidence) -> tuple[str, ...]:
    """Return unresolved tool warning closure problems."""
    problems: list[str] = []
    status = evidence.monitoring_status.get("tool_warnings_status", "").strip().lower()
    if status not in {"none", "resolved"}:
        problems.append(
            "tool_warnings_status must be none or resolved in workflow_monitoring.md"
        )

    latest_by_id: dict[str, dict[str, str]] = {}
    for line in evidence.tool_warnings_text.splitlines():
        if "tool_warning=recorded" not in line:
            continue
        fields = token_fields(line)
        warning_id = fields.get("warning_id", "")
        if not warning_id:
            problems.append("tool_warning entry missing warning_id")
            continue
        latest_by_id[warning_id] = fields

    for warning_id, fields in sorted(latest_by_id.items()):
        warning_status = fields.get("status", "").lower()
        severity = fields.get("severity", "").lower()
        if warning_status in {"", "open", "pending", "observed", "unresolved"}:
            problems.append(f"tool warning remains open: {warning_id}")
        if severity in {"fix-now", "s0", "s1", "blocker"} and warning_status != "resolved":
            problems.append(f"fix-now tool warning must be resolved: {warning_id}")
        if warning_status in {"resolved", "accepted_with_reason", "deferred_with_issue"}:
            if not fields.get("evidence") and not fields.get("issue"):
                problems.append(
                    f"closed tool warning lacks evidence or issue: {warning_id}"
                )
    return tuple(problems)


def tool_warnings_closed(evidence: RunEvidence) -> bool:
    """Return whether tool warning obligations are explicitly closed."""
    return not tool_warning_problems(evidence)


def orchestration_evidence_present(evidence: RunEvidence) -> bool:
    """Return whether pre-design orchestration signals are present."""
    signals_text = evidence.signals_text
    behavior_events_text = evidence.behavior_events_text
    return (
        has_any(signals_text, ("skills=", "$agent-orchestration"))
        and has_any(
            behavior_events_text,
            ("skill_invocation=", "skill_invocation_not_required"),
        )
        and has_any(
            signals_text,
            ("subagent", "stage owner", "parent_direct_reason", "trivial_direct_edit"),
        )
        and has_any(
            signals_text,
            (
                "repo_dependency_review=pass",
                "run_repo_dependency_review.sh",
                "repo_dependency_intake_not_required",
                "dependency review",
            ),
        )
        and has_any(
            signals_text,
            (
                "web_research",
                "external_research",
                "internet research",
                "web_research_not_required",
                "internet_research_not_required",
            ),
        )
        and has_any(
            signals_text,
            ("review_status=", "review_decision=", "review_not_required"),
        )
        and has_any(
            signals_text,
            ("validation_status=", "validation_complete: yes", "validation_not_required"),
        )
        and has_any(
            signals_text,
            ("drift_risk=", "drift_risk_not_required", "forbidden_drift_detected"),
        )
    )


def build_base_criteria(
    evidence: RunEvidence,
    report_dir: Path,
    workspace_root: Path,
) -> list[CriterionResult]:
    """Build non-manifest run evaluation criteria."""
    return [
        *build_artifact_and_traceability_criteria(evidence),
        *build_workflow_execution_criteria(evidence, report_dir, workspace_root),
        *build_review_and_closeout_criteria(evidence),
        build_self_improvement_feedback_criterion(evidence),
    ]


def build_artifact_and_traceability_criteria(
    evidence: RunEvidence,
) -> list[CriterionResult]:
    """Build artifact completeness and request traceability criteria."""
    request_contract = evidence.request_contract
    return [
        criterion(
            "artifact_completeness",
            ARTIFACT_COMPLETENESS_SCORE,
            not evidence.missing_artifacts,
            f"Create missing run artifacts: {', '.join(evidence.missing_artifacts)}.",
        ),
        criterion(
            "request_traceability",
            REQUEST_TRACEABILITY_SCORE,
            request_contract.get("all_clauses_resolved") == "yes"
            and request_contract.get("forbidden_drift_detected") == "no"
            and not request_contract.get("unresolved_clause_ids", "").strip(),
            "Resolve all request clauses, clear unresolved ids, and confirm "
            "forbidden drift is absent.",
        ),
    ]


def build_workflow_execution_criteria(
    evidence: RunEvidence,
    report_dir: Path,
    workspace_root: Path,
) -> list[CriterionResult]:
    """Build planned work, monitoring, and intake criteria."""
    schedule_blockers = check_schedule_artifact(evidence.schedule_text)
    work_log_blockers = check_work_log_artifact(evidence.work_log_text)
    return [
        criterion(
            "planned_work_and_chronology",
            PLANNED_WORK_AND_CHRONOLOGY_SCORE,
            not schedule_blockers and not work_log_blockers,
            "Fill schedule stage/coverage/work-unit tables and add meaningful work-log entries.",
        ),
        criterion(
            "workflow_monitoring",
            WORKFLOW_MONITORING_SCORE,
            monitoring_sections_complete(evidence),
            "Fill workflow_monitoring.md with signals, Behavior Events, "
            "Tool Warnings, interventions, and improvement decisions from the "
            "active workflow.",
        ),
        criterion(
            "tool_warning_obligation_closure",
            TOOL_WARNING_OBLIGATION_SCORE,
            tool_warnings_closed(evidence),
            "Record every non-blocking tool, hook, checker, and wrapper warning "
            "in ## Tool Warnings and close each item with resolved, "
            "accepted_with_reason, deferred_with_issue, not_applicable, or "
            "tool_warnings_status=none. Problems: "
            + "; ".join(tool_warning_problems(evidence)),
        ),
        criterion(
            "orchestration_and_pre_design_intake",
            ORCHESTRATION_INTAKE_SCORE,
            orchestration_evidence_present(evidence),
            "Record skills, stage/subagent or parent-direct routing, MCP preflight "
            "or explicit opt-out, repo dependency intake, web research decision, "
            "review status, validation status, and drift risk before implementation.",
        ),
        build_prompt_eval_artifact_criterion(evidence, report_dir, workspace_root),
    ]


def build_prompt_eval_artifact_criterion(
    evidence: RunEvidence,
    report_dir: Path,
    workspace_root: Path,
) -> CriterionResult:
    """Require skill-use prompt eval events to cite real matching reports."""
    invoked_skills = extract_invoked_skills(evidence.behavior_events_raw_text)
    if not invoked_skills:
        return criterion(
            "prompt_eval_artifact_integrity",
            PROMPT_EVAL_ARTIFACT_SCORE,
            True,
            "No action required.",
        )
    events = extract_prompt_eval_events(evidence.behavior_events_raw_text)
    problems: list[str] = []
    covered_skills: set[str] = set()
    if not events:
        problems.append("accumulated prompt eval event missing")
    for event in events:
        report_path = resolve_eval_report_path(event.report_path, report_dir, workspace_root)
        if report_path is None:
            problems.append(f"accumulated prompt eval report missing: {event.report_path}")
            continue
        report_text = report_path.read_text(encoding="utf-8")
        if event.eval_run_id and not report_contains_eval_run_id(report_text, event.eval_run_id):
            problems.append(
                f"accumulated prompt eval run-id mismatch: {event.eval_run_id} -> {event.report_path}"
            )
        covered_skills.update(event.used_skills)
        covered_skills.update(extract_report_used_skills(report_text))
    missing_skills = sorted(invoked_skills - covered_skills)
    if missing_skills:
        problems.append("missing accumulated prompt eval skills: " + ",".join(missing_skills))
    return criterion(
        "prompt_eval_artifact_integrity",
        PROMPT_EVAL_ARTIFACT_SCORE,
        not problems,
        "; ".join(problems) if problems else "No action required.",
    )


def extract_invoked_skills(text: str) -> set[str]:
    """Return skill ids observed as runtime invocations."""
    if "skill_invocation_not_required" in text:
        return set()
    return {match.group(1).removeprefix("$") for match in SKILL_INVOCATION_PATTERN.finditer(text)}


def extract_prompt_eval_events(text: str) -> tuple[PromptEvalEvent, ...]:
    """Return accumulated prompt eval events recorded in behavior monitoring."""
    events: list[PromptEvalEvent] = []
    for line in text.splitlines():
        if "evaluate_skill_workflow_prompts.py" not in line:
            continue
        fields = {match.group(1): match.group(2).strip("`'\"") for match in EVAL_FIELD_PATTERN.finditer(line)}
        report_path = fields.get("EVAL_ACCUMULATED_REPORT", "")
        if not report_path:
            continue
        used_skills = tuple(
            skill.strip().removeprefix("$")
            for skill in fields.get("EVAL_USED_SKILLS", "").split(",")
            if skill.strip() and skill.strip() != "-"
        )
        events.append(
            PromptEvalEvent(
                eval_run_id=fields.get("EVAL_RUN_ID", ""),
                report_path=report_path,
                used_skills=used_skills,
            )
        )
    return tuple(events)


def resolve_eval_report_path(
    report_text_path: str,
    report_dir: Path,
    workspace_root: Path,
) -> Path | None:
    """Resolve an accumulated eval report path from report-dir or workspace context."""
    candidate = Path(report_text_path)
    candidates = (candidate,) if candidate.is_absolute() else (report_dir / candidate, workspace_root / candidate)
    for path in candidates:
        if path.is_file():
            return path
    return None


def report_contains_eval_run_id(report_text: str, eval_run_id: str) -> bool:
    """Return whether one report contains the expected eval run id."""
    return f"eval_run_id: `{eval_run_id}`" in report_text or f"EVAL_RUN_ID={eval_run_id}" in report_text


def extract_report_used_skills(report_text: str) -> set[str]:
    """Extract used skill ids from one accumulated prompt eval report."""
    for line in report_text.splitlines():
        if "used_skills:" not in line:
            continue
        _, _, value = line.partition("used_skills:")
        value = value.strip().strip("`")
        return {skill.strip().removeprefix("$") for skill in value.split(",") if skill.strip() and skill.strip() != "-"}
    return set()


def build_review_and_closeout_criteria(
    evidence: RunEvidence,
) -> list[CriterionResult]:
    """Build review feedback and closeout criteria."""
    final_review_blockers = check_final_review_artifact(evidence.final_review_text)
    return [
        criterion(
            "review_feedback_loop",
            REVIEW_FEEDBACK_LOOP_SCORE,
            has_approve_decision(evidence.final_review_text)
            and not final_review_blockers
            and not has_open_review_findings(
                evidence.change_review_text,
                evidence.final_review_text,
            ),
            "Resolve or escalate review feedback and record a concrete approving final review decision.",
        ),
        *build_closeout_criteria(evidence),
    ]


def build_closeout_criteria(evidence: RunEvidence) -> list[CriterionResult]:
    """Build validation, dependency, and canonical closeout criteria."""
    closeout = evidence.closeout
    return [
        criterion(
            "validation_and_closeout_evidence",
            VALIDATION_AND_CLOSEOUT_SCORE,
            evidence.verification.get("status") == "pass"
            and closeout.get("validation_complete") == "yes"
            and closeout.get("commit_created") == "yes"
            and closeout.get("push_completed") == "yes",
            "Record passing verification, validation_complete=yes, commit evidence, "
            "and push evidence.",
        ),
        criterion(
            "dependency_and_canonical_evidence",
            DEPENDENCY_AND_CANONICAL_SCORE,
            closeout.get("dependency_headers_complete") == "yes"
            and closeout.get("repo_wide_dependency_tools_complete") == "yes"
            and closeout.get("repo_wide_static_analysis_complete") == "yes"
            and closeout.get("canonical_tree_head_complete") == "yes",
            "Record changed-file dependency evidence, repo-wide dependency review "
            "evidence, repo-wide static analysis evidence, and canonical tree-head "
            "evidence in closeout_gate.md.",
        ),
    ]


def build_self_improvement_feedback_criterion(evidence: RunEvidence) -> CriterionResult:
    """Build the self-improvement feedback capture criterion."""
    return criterion(
        "self_improvement_feedback_capture",
        SELF_IMPROVEMENT_FEEDBACK_SCORE,
        section_has_content(evidence.retrospective_text, "## What Worked")
        and section_has_content(evidence.retrospective_text, "## What Hurt")
        and section_has_content(evidence.retrospective_text, "## Follow-ups")
        and improvement_decisions_complete(evidence)
        and runtime_feedback_closure_complete(evidence),
        "Fill retrospective sections and mark skill/config/workflow/memory "
        "improvement decisions as applied, recorded, or not_applicable. "
        "When runtime_feedback=observed is not action=no_op, at least one "
        "improvement decision must be applied or recorded.",
        partial_score=SELF_IMPROVEMENT_FEEDBACK_PARTIAL_SCORE
        if improvement_decisions_complete(evidence)
        and runtime_feedback_closure_complete(evidence)
        else 0,
    )


def evaluate(
    report_dir: Path,
    behavior_criteria: tuple[BehaviorCriterion, ...],
    workspace_root: Path,
) -> tuple[list[CriterionResult], list[str]]:
    """Evaluate one report directory."""
    evidence = read_run_evidence(report_dir)
    criteria = [
        *build_base_criteria(evidence, report_dir, workspace_root),
        *evaluate_behavior_criteria(
            {
                "behavior_events": evidence.behavior_events_text,
                "bundle": evidence.normalized_bundle,
            },
            behavior_criteria,
        ),
    ]
    blockers = [item.feedback for item in criteria if item.status != "pass"]
    blockers.extend(unresolved_checker_failure_blockers(evidence.behavior_events_raw_text))
    return criteria, blockers


def unresolved_checker_failure_blockers(text: str) -> list[str]:
    """Return blockers for checker failures that still need same-intent repair."""
    latest_by_checker: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    for line in text.splitlines():
        fields = token_fields(line)
        status = fields.get("code_checker", "")
        if status not in {"pass", "fail"}:
            continue
        checker = checker_identity(fields)
        latest_by_checker[checker] = fields
        if status == "fail" and not validation_failure_fields_complete(fields):
            blockers.append(
                f"{checker} code_checker=fail missing validation-failure "
                "field packet: failing_contract=, observation_level=, "
                "cause_classification=<canonical_slug>, "
                "intent_preservation=<canonical_slug>, evidence="
            )

    for checker, fields in sorted(latest_by_checker.items()):
        if fields.get("code_checker") != "fail":
            continue
        if not validation_failure_fields_complete(fields):
            continue
        cause = fields.get("cause_classification", "")
        intent = fields.get("intent_preservation", "")
        if (
            cause == VALIDATION_FAILURE_IMPLEMENTATION_BUG
            and intent == VALIDATION_FAILURE_REPAIR_SAME_INTENT
        ):
            blockers.append(
                f"{checker} still reports code_checker=fail after "
                f"cause_classification={VALIDATION_FAILURE_IMPLEMENTATION_BUG} "
                f"intent_preservation={VALIDATION_FAILURE_REPAIR_SAME_INTENT}; "
                "rerun the same checker "
                "to a later code_checker=pass or keep repairing the owning surface"
            )
            continue
        if cause in RESIDUAL_CHECKER_FAILURE_CAUSES and fields.get("evidence"):
            continue
        if cause or intent:
            blockers.append(
                f"{checker} code_checker=fail has unresolved validation-failure "
                f"route cause_classification={cause or '<missing>'} "
                f"intent_preservation={intent or '<missing>'}"
            )
    return blockers


def checker_identity(fields: dict[str, str]) -> str:
    """Return the stable checker id for one code_checker evidence line."""
    return fields.get("checker") or fields.get("tool_call") or "unknown-checker"


def evaluate_behavior_criteria(
    source_texts: dict[str, str],
    behavior_criteria: tuple[BehaviorCriterion, ...],
) -> list[CriterionResult]:
    """Evaluate manifest-defined behavior evidence criteria."""
    return [
        evaluate_behavior_criterion(source_texts[item.source], item)
        for item in behavior_criteria
    ]


def evaluate_behavior_criterion(
    text: str,
    item: BehaviorCriterion,
) -> CriterionResult:
    """Evaluate one manifest-defined behavior criterion."""
    if item.name == "token_efficiency_recorded":
        return evaluate_token_efficiency_criterion(text, item)
    if item.name == "validation_failure_response_recorded":
        return evaluate_validation_failure_response_criterion(text, item)
    missing_all = tuple(token for token in item.required_all if token.lower() not in text)
    any_passed = not item.required_any or has_any(text, item.required_any)
    forbidden_hits = tuple(
        token for token in item.forbidden_any if token.lower() in text
    )
    passed = not missing_all and any_passed and not forbidden_hits
    return criterion(
        f"behavior::{item.name}",
        item.max_score,
        passed,
        behavior_feedback(item, missing_all, any_passed, forbidden_hits),
    )


def evaluate_validation_failure_response_criterion(
    text: str,
    item: BehaviorCriterion,
) -> CriterionResult:
    """Require diagnostic evidence before scoring failure-driven simplification."""
    failure_tokens = tuple(
        token
        for token in item.required_any
        if token != "validation_failure_not_observed"
    )
    not_observed = "validation_failure_not_observed" in text
    failure_observed = has_any(text, failure_tokens)
    observation_recorded = not_observed or failure_observed
    contradictory = not_observed and failure_observed
    forbidden_violations = validation_failure_forbidden_violations(
        text,
        (*item.forbidden_any, *VALIDATION_FAILURE_FORBIDDEN_TOKENS),
    )
    evidence_complete = validation_failure_evidence_complete(text, failure_tokens)
    passed = (
        observation_recorded
        and not contradictory
        and (not failure_observed or evidence_complete)
        and not forbidden_violations
    )
    missing_all = validation_failure_missing_tokens(
        observation_recorded,
        failure_observed,
        evidence_complete,
        forbidden_violations,
        contradictory,
    )
    return criterion(
        f"behavior::{item.name}",
        item.max_score,
        passed,
        behavior_feedback(item, missing_all, True, forbidden_violations),
    )


def validation_failure_evidence_complete(
    text: str,
    failure_tokens: tuple[str, ...],
) -> bool:
    """Return whether validation-failure evidence uses the monitor contract."""
    failure_events = validation_failure_event_fields(text, failure_tokens)
    return bool(failure_events) and all(
        validation_failure_fields_complete(fields) for fields in failure_events
    )


def validation_failure_event_fields(
    text: str,
    failure_tokens: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    """Return field packets from observed validation/checker failure events."""
    events: list[dict[str, str]] = []
    normalized_tokens = tuple(token.lower() for token in failure_tokens)
    for line in text.splitlines():
        line_lower = line.lower()
        if any(token in line_lower for token in normalized_tokens):
            events.append(token_fields(line))
    return tuple(events)


def validation_failure_fields_complete(fields: dict[str, str]) -> bool:
    """Return whether one validation/checker failure event has required fields."""
    cause = fields.get("cause_classification", "")
    intent = fields.get("intent_preservation", "")
    return (
        bool(fields.get("failing_contract"))
        and bool(fields.get("observation_level"))
        and cause in VALIDATION_FAILURE_CAUSE_CLASSIFICATION_VALUES
        and intent in VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES
        and bool(fields.get("evidence"))
    )


def validation_failure_forbidden_violations(
    text: str,
    forbidden_tokens: tuple[str, ...],
) -> tuple[str, ...]:
    """Return forbidden validation-repair tokens without same-event escalation."""
    violations: list[str] = []
    normalized_tokens = tuple(
        dict.fromkeys(token.lower() for token in forbidden_tokens)
    )
    for line in text.splitlines():
        line_lower = line.lower()
        line_hits = tuple(token for token in normalized_tokens if token in line_lower)
        if not line_hits:
            continue
        fields = token_fields(line)
        if validation_failure_fields_escalated(fields):
            continue
        violations.extend(line_hits)
    return tuple(dict.fromkeys(violations))


def validation_failure_fields_escalated(fields: dict[str, str]) -> bool:
    """Return whether one field packet escalates a design/user conflict."""
    return (
        fields.get("cause_classification")
        == VALIDATION_FAILURE_DESIGN_CONFLICT
        and fields.get("intent_preservation")
        == VALIDATION_FAILURE_ESCALATE_DESIGN_CONFLICT
        and bool(fields.get("evidence"))
    )


def validation_failure_missing_tokens(
    observation_recorded: bool,
    failure_observed: bool,
    evidence_complete: bool,
    forbidden_violations: tuple[str, ...],
    contradictory: bool,
) -> tuple[str, ...]:
    """Return validation-failure-specific missing or contradictory evidence."""
    missing: list[str] = []
    if not observation_recorded:
        missing.append(
            "validation_failure_not_observed or observed validation failure token"
        )
    if contradictory:
        missing.append(
            "remove validation_failure_not_observed when later failure evidence exists"
        )
    if failure_observed and not evidence_complete:
        missing.extend(
            [
                "failing_contract=",
                "observation_level=",
                "cause_classification=<canonical_slug>",
                "intent_preservation="
                + validation_failure_slug_hint(
                    VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES
                ),
                "evidence=",
            ]
        )
    if forbidden_violations:
        missing.append(
            f"intent_preservation={VALIDATION_FAILURE_ESCALATE_DESIGN_CONFLICT} "
            f"with cause_classification={VALIDATION_FAILURE_DESIGN_CONFLICT} "
            "on the same event"
        )
    return tuple(missing)


def evaluate_token_efficiency_criterion(
    text: str,
    item: BehaviorCriterion,
) -> CriterionResult:
    """Evaluate token-efficiency evidence with an explicit opt-out."""
    active_tokens = (
        "token_efficiency_protocol=active",
        "token_footprint_comparison=",
        "TOKEN_FOOTPRINT_COMPARISON=",
        "token_ratio=",
        "TOKEN_FOOTPRINT_RATIO=",
    )
    if has_any(text, active_tokens):
        missing_all = tuple(
            token for token in item.required_all if token.lower() not in text
        )
        any_passed = not item.required_any or has_any(text, item.required_any)
        forbidden_hits = tuple(
            token for token in item.forbidden_any if token.lower() in text
        )
        passed = not missing_all and any_passed and not forbidden_hits
        return criterion(
            f"behavior::{item.name}",
            item.max_score,
            passed,
            behavior_feedback(item, missing_all, any_passed, forbidden_hits),
        )
    opt_out_passed = has_any(text, ("token_efficiency_not_required",))
    return criterion(
        f"behavior::{item.name}",
        item.max_score,
        opt_out_passed,
        item.feedback
        if opt_out_passed
        else f"{item.feedback} (missing opt-out token: token_efficiency_not_required)",
    )


def behavior_feedback(
    item: BehaviorCriterion,
    missing_all: tuple[str, ...],
    any_passed: bool,
    forbidden_hits: tuple[str, ...],
) -> str:
    """Render behavior criterion feedback with missing-token details."""
    details = behavior_feedback_details(
        item,
        missing_all,
        any_passed,
        forbidden_hits,
    )
    return item.feedback if not details else f"{item.feedback} ({'; '.join(details)})"


def behavior_feedback_details(
    item: BehaviorCriterion,
    missing_all: tuple[str, ...],
    any_passed: bool,
    forbidden_hits: tuple[str, ...],
) -> tuple[str, ...]:
    """Return missing-token details for one behavior criterion."""
    return tuple(
        detail
        for detail in (
            "missing all-required tokens: " + ", ".join(missing_all)
            if missing_all
            else "",
            "missing any-required token: " + " OR ".join(item.required_any)
            if not any_passed
            else "",
            "forbidden token present: " + ", ".join(forbidden_hits)
            if forbidden_hits
            else "",
        )
        if detail
    )


def render_markdown(
    report_dir: Path,
    criteria: list[CriterionResult],
    blockers: list[str],
    min_score: int,
) -> str:
    """Render the evaluation artifact."""
    return "\n".join(
        [
            *render_markdown_header(report_dir, criteria, blockers, min_score),
            *render_rubric_lines(criteria),
            *render_feedback_action_lines(blockers),
            *render_learning_capture_lines(),
        ]
    )


def render_markdown_header(
    report_dir: Path,
    criteria: list[CriterionResult],
    blockers: list[str],
    min_score: int,
) -> list[str]:
    """Render the evaluation summary and rubric header lines."""
    summary = markdown_summary(criteria, blockers, min_score)
    return [
        *render_markdown_title_lines(),
        *render_markdown_status_lines(summary),
        *render_markdown_scope_lines(report_dir),
        *render_rubric_header_lines(),
    ]


def markdown_summary(
    criteria: list[CriterionResult],
    blockers: list[str],
    min_score: int,
) -> dict[str, str]:
    """Build rendered status values for the evaluation header."""
    score = sum(item.score for item in criteria)
    max_score = sum(item.max_score for item in criteria)
    status = "pass" if score >= min_score and not blockers else "revise"
    return {
        "evaluation_status": status,
        "score": str(score),
        "max_score": str(max_score),
        "threshold": str(min_score),
        "feedback_actions_resolved": "yes" if status == "pass" else "no",
        "learning_capture_complete": learning_capture_complete(criteria),
    }


def render_markdown_title_lines() -> list[str]:
    """Render the title and dependency manifest lines."""
    return [
        "# Agent Evaluation",
        "",
        "<!--",
        "@dependency-start",
        "upstream design ../../../../vendor/agent-canon/agents/workflows/"
        "agent-learning-workflow.md agent feedback workflow",
        "upstream implementation ../../../../vendor/agent-canon/tools/agent_tools/"
        "evaluate_agent_run.py generates this artifact",
        "@dependency-end",
        "-->",
        "",
    ]


def render_markdown_status_lines(summary: dict[str, str]) -> list[str]:
    """Render the status summary lines."""
    return [
        f"- evaluation_status: {summary['evaluation_status']}",
        f"- score: {summary['score']}",
        f"- max_score: {summary['max_score']}",
        f"- threshold: {summary['threshold']}",
        f"- feedback_actions_resolved: {summary['feedback_actions_resolved']}",
        f"- learning_capture_complete: {summary['learning_capture_complete']}",
        "",
    ]


def render_markdown_scope_lines(report_dir: Path) -> list[str]:
    """Render the scope section lines."""
    return [
        "## Scope",
        "",
        f"- report_dir: {report_dir}",
        "",
    ]


def render_rubric_header_lines() -> list[str]:
    """Render the rubric table header lines."""
    return [
        "## Rubric",
        "",
        "| Criterion | Score | Max | Status | Feedback |",
        "| --------- | ----- | --- | ------ | -------- |",
    ]


def learning_capture_complete(criteria: list[CriterionResult]) -> str:
    """Return whether any learning capture criterion passed."""
    learning_criteria = {
        "learning_and_feedback_capture",
        "self_improvement_feedback_capture",
    }
    if any(
        item.name in learning_criteria and item.status == "pass"
        for item in criteria
    ):
        return "yes"
    return "no"


def render_rubric_lines(criteria: list[CriterionResult]) -> list[str]:
    """Render criterion result rows."""
    return [
        f"| {item.name} | {item.score} | {item.max_score} | "
        f"{item.status} | {item.feedback} |"
        for item in criteria
    ]


def render_feedback_action_lines(blockers: list[str]) -> list[str]:
    """Render feedback action table lines."""
    action_lines = (
        [
            f"| F{index} | fix-now | {blocker} | open |"
            for index, blocker in enumerate(blockers, start=1)
        ]
        if blockers
        else ["| F0 | none | No open feedback actions. | resolved |"]
    )
    return [
        "",
        "## Feedback Actions",
        "",
        "| Action ID | Severity | Action | Status |",
        "| --------- | -------- | ------ | ------ |",
        *action_lines,
    ]


def render_learning_capture_lines() -> list[str]:
    """Render learning capture guidance lines."""
    return [
        "",
        "## Learning Capture",
        "",
        "If this evaluation exposed a durable agent-side lesson, record it with "
        "`tools/agent_tools/log_agent_learning.py` and cite the evidence. "
        "If the lesson requires a durable process change, update the relevant "
        "skill, config, or workflow "
        "before marking the monitoring decision as applied. Do not copy raw chat.",
        "",
    ]


def main() -> int:
    """Run the agent evaluation."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = resolve_report_root(args.report_root, workspace_root) / str(
            args.run_id
        )
        report_dir = report_dir.resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = report_dir / output_path

    behavior_manifest = resolve_eval_manifest(workspace_root, args.behavior_manifest)
    behavior_criteria = load_behavior_manifest(behavior_manifest)
    criteria, blockers = evaluate(report_dir, behavior_criteria, workspace_root)
    score = sum(item.score for item in criteria)
    max_score = sum(item.max_score for item in criteria)
    status = "pass" if score >= args.min_score and not blockers else "revise"
    report = render_markdown(report_dir, criteria, blockers, args.min_score)
    if args.write:
        output_path.write_text(report, encoding="utf-8")

    print(f"AGENT_EVALUATION_REPORT={output_path}")
    print(f"AGENT_EVALUATION_STATUS={status}")
    print(f"AGENT_EVALUATION_SCORE={score}")
    print(f"AGENT_EVALUATION_MAX_SCORE={max_score}")
    print(f"AGENT_EVALUATION_THRESHOLD={args.min_score}")
    print(f"AGENT_EVALUATION_FEEDBACK_ACTIONS_OPEN={len(blockers)}")
    if blockers:
        print("AGENT_EVALUATION_BLOCKERS=" + "|".join(blockers))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
