#!/usr/bin/env python3
# @dependency-start
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
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from agent_team import resolve_report_root
from report_artifact_checks import (
    check_schedule_artifact,
    check_work_log_artifact,
    section_has_content,
)

DEFAULT_MIN_SCORE = 85
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
DEFAULT_BEHAVIOR_MANIFEST = "agents/evals/agent_behavior_eval.toml"


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
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(value)


def markdown_section_text(text: str, heading: str) -> str:
    """Return one level-2 Markdown section without comments."""
    lines = markdown_without_comments(text).splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
        if in_section:
            collected.append(line)
    return "\n".join(collected).lower()


def load_behavior_manifest(path: Path) -> tuple[BehaviorCriterion, ...]:
    """Load manifest-defined behavior criteria."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_criteria = data.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ValueError("behavior manifest must define at least one [[criteria]] entry")
    criteria: list[BehaviorCriterion] = []
    for index, entry in enumerate(raw_criteria, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"behavior criterion {index} must be a table")
        name = str(entry["name"])
        source = str(entry.get("source", "behavior_events"))
        if source not in {"behavior_events", "bundle"}:
            raise ValueError(f"behavior criterion {name} has invalid source={source}")
        feedback = str(
            entry.get("feedback", f"Record behavior evidence for {name}.")
        )
        criteria.append(
            BehaviorCriterion(
                name=name,
                max_score=int(str(entry.get("max_score", 5))),
                feedback=feedback,
                source=source,
                required_all=string_tuple(
                    entry.get("required_all"), f"{name}.required_all"
                ),
                required_any=string_tuple(
                    entry.get("required_any"), f"{name}.required_any"
                ),
            )
        )
    return tuple(criteria)


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
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def bundle_text(report_dir: Path) -> str:
    """Return normalized text from all markdown and text run artifacts."""
    parts: list[str] = []
    for path in sorted(report_dir.glob("*")):
        if path.suffix not in {".md", ".txt", ".yaml", ".yml"}:
            continue
        parts.append(markdown_without_comments(path.read_text(encoding="utf-8")))
    return "\n".join(parts).lower()


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
    )


def monitoring_sections_complete(evidence: RunEvidence) -> bool:
    """Return whether required monitoring sections contain content."""
    return all(
        section_has_content(evidence.monitoring_text, heading)
        for heading in (
            "## Signals",
            "## Behavior Events",
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


def orchestration_evidence_present(evidence: RunEvidence) -> bool:
    """Return whether pre-design orchestration signals are present."""
    signals_text = evidence.signals_text
    return (
        has_any(signals_text, ("skills=", "$agent-orchestration"))
        and has_any(
            signals_text,
            ("subagent", "stage owner", "parent_direct_reason", "trivial_direct_edit"),
        )
        and has_any(
            signals_text,
            (
                "mcp_inventory=pass",
                "check_mcp_inventory",
                "mcp_preflight_not_required",
                "mcp not required",
            ),
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


def build_base_criteria(evidence: RunEvidence) -> list[CriterionResult]:
    """Build non-manifest run evaluation criteria."""
    schedule_blockers = check_schedule_artifact(evidence.schedule_text)
    work_log_blockers = check_work_log_artifact(evidence.work_log_text)
    request_contract = evidence.request_contract
    closeout = evidence.closeout
    criteria = [
        criterion(
            "artifact_completeness",
            8,
            not evidence.missing_artifacts,
            f"Create missing run artifacts: {', '.join(evidence.missing_artifacts)}.",
        ),
        criterion(
            "request_traceability",
            10,
            request_contract.get("all_clauses_resolved") == "yes"
            and request_contract.get("forbidden_drift_detected") == "no"
            and not request_contract.get("unresolved_clause_ids", "").strip(),
            "Resolve all request clauses, clear unresolved ids, and confirm "
            "forbidden drift is absent.",
        ),
        criterion(
            "planned_work_and_chronology",
            10,
            not schedule_blockers and not work_log_blockers,
            "Fill schedule stage/coverage/work-unit tables and add meaningful work-log entries.",
        ),
        criterion(
            "workflow_monitoring",
            12,
            monitoring_sections_complete(evidence),
            "Fill workflow_monitoring.md with signals, Behavior Events, "
            "interventions, and improvement decisions from the active workflow.",
        ),
        criterion(
            "orchestration_and_pre_design_intake",
            12,
            orchestration_evidence_present(evidence),
            "Record skills, stage/subagent or parent-direct routing, MCP preflight "
            "or explicit opt-out, repo dependency intake, web research decision, "
            "review status, validation status, and drift risk before implementation.",
        ),
        criterion(
            "review_feedback_loop",
            10,
            "approve" in evidence.final_decision
            and not has_open_review_findings(
                evidence.change_review_text,
                evidence.final_review_text,
            ),
            "Resolve or escalate review feedback and record an approving final review decision.",
        ),
        criterion(
            "validation_and_closeout_evidence",
            12,
            evidence.verification.get("status") == "pass"
            and closeout.get("validation_complete") == "yes"
            and closeout.get("commit_created") == "yes"
            and closeout.get("push_completed") == "yes",
            "Record passing verification, validation_complete=yes, commit evidence, "
            "and push evidence.",
        ),
        criterion(
            "dependency_and_canonical_evidence",
            10,
            closeout.get("dependency_headers_complete") == "yes"
            and closeout.get("repo_wide_dependency_tools_complete") == "yes"
            and closeout.get("repo_wide_static_analysis_complete") == "yes"
            and closeout.get("canonical_tree_head_complete") == "yes",
            "Record changed-file dependency evidence, repo-wide dependency review "
            "evidence, repo-wide static analysis evidence, and canonical tree-head "
            "evidence in closeout_gate.md.",
        ),
        criterion(
            "self_improvement_feedback_capture",
            16,
            section_has_content(evidence.retrospective_text, "## What Worked")
            and section_has_content(evidence.retrospective_text, "## What Hurt")
            and section_has_content(evidence.retrospective_text, "## Follow-ups")
            and improvement_decisions_complete(evidence),
            "Fill retrospective sections and mark skill/config/workflow/memory "
            "improvement decisions as applied, recorded, or not_applicable.",
            partial_score=8 if improvement_decisions_complete(evidence) else 0,
        ),
    ]
    return criteria


def evaluate(
    report_dir: Path,
    behavior_criteria: tuple[BehaviorCriterion, ...],
) -> tuple[list[CriterionResult], list[str]]:
    """Evaluate one report directory."""
    evidence = read_run_evidence(report_dir)
    criteria = build_base_criteria(evidence)
    criteria.extend(
        evaluate_behavior_criteria(
            {
                "behavior_events": evidence.behavior_events_text,
                "bundle": evidence.normalized_bundle,
            },
            behavior_criteria,
        )
    )
    blockers = [item.feedback for item in criteria if item.status != "pass"]
    return criteria, blockers


def evaluate_behavior_criteria(
    source_texts: dict[str, str],
    behavior_criteria: tuple[BehaviorCriterion, ...],
) -> list[CriterionResult]:
    """Evaluate manifest-defined behavior evidence criteria."""
    results: list[CriterionResult] = []
    for item in behavior_criteria:
        text = source_texts[item.source]
        missing_all = tuple(
            token for token in item.required_all if token.lower() not in text
        )
        any_passed = not item.required_any or has_any(text, item.required_any)
        passed = not missing_all and any_passed
        details: list[str] = []
        if missing_all:
            details.append("missing all-required tokens: " + ", ".join(missing_all))
        if not any_passed:
            details.append(
                "missing any-required token: " + " OR ".join(item.required_any)
            )
        feedback = (
            item.feedback if not details else f"{item.feedback} ({'; '.join(details)})"
        )
        results.append(
            criterion(
                f"behavior::{item.name}",
                item.max_score,
                passed,
                feedback,
            )
        )
    return results


def render_markdown(
    report_dir: Path,
    criteria: list[CriterionResult],
    blockers: list[str],
    min_score: int,
) -> str:
    """Render the evaluation artifact."""
    score = sum(item.score for item in criteria)
    max_score = sum(item.max_score for item in criteria)
    status = "pass" if score >= min_score and not blockers else "revise"
    feedback_resolved = "yes" if status == "pass" else "no"
    learning_criteria = {
        "learning_and_feedback_capture",
        "self_improvement_feedback_capture",
    }
    learning_complete = (
        "yes"
        if any(
            item.name in learning_criteria and item.status == "pass"
            for item in criteria
        )
        else "no"
    )
    lines = [
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
        f"- evaluation_status: {status}",
        f"- score: {score}",
        f"- max_score: {max_score}",
        f"- threshold: {min_score}",
        f"- feedback_actions_resolved: {feedback_resolved}",
        f"- learning_capture_complete: {learning_complete}",
        "",
        "## Scope",
        "",
        f"- report_dir: {report_dir}",
        "",
        "## Rubric",
        "",
        "| Criterion | Score | Max | Status | Feedback |",
        "| --------- | ----- | --- | ------ | -------- |",
    ]
    for item in criteria:
        lines.append(
            f"| {item.name} | {item.score} | {item.max_score} | "
            f"{item.status} | {item.feedback} |"
        )
    lines.extend(
        [
            "",
            "## Feedback Actions",
            "",
            "| Action ID | Severity | Action | Status |",
            "| --------- | -------- | ------ | ------ |",
        ]
    )
    if blockers:
        for index, blocker in enumerate(blockers, start=1):
            lines.append(f"| F{index} | fix-now | {blocker} | open |")
    else:
        lines.append("| F0 | none | No open feedback actions. | resolved |")
    lines.extend(
        [
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
    )
    return "\n".join(lines)


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

    behavior_manifest = Path(args.behavior_manifest)
    if not behavior_manifest.is_absolute():
        behavior_manifest = workspace_root / behavior_manifest
    behavior_criteria = load_behavior_manifest(behavior_manifest)
    criteria, blockers = evaluate(report_dir, behavior_criteria)
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
