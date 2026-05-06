#!/usr/bin/env python3
# @dependency-start
# responsibility Appends workflow monitoring evidence to run bundles.
# upstream design ../../agents/templates/workflow_monitoring.md defines monitor sections
# downstream implementation ../../tests/agent_tools/test_workflow_monitor.py tests it
# @dependency-end
"""Append machine-readable workflow monitoring evidence to one run bundle."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from agent_team import resolve_report_root

DECISION_KEYS = (
    "skill_improvement_decision",
    "config_improvement_decision",
    "workflow_improvement_decision",
    "memory_learning_decision",
)
DECISION_VALUES = {"applied", "recorded", "not_applicable", "pending"}
STANDARD_CLOSEOUT_BEHAVIOR_EVENTS = (
    "skill_invocation=$agent-orchestration status=observed",
    "subagent_lifecycle=closed subagents_closed=yes fresh_subagents_required=true",
    (
        "tool_call=run_repo_dependency_review.sh repo_dependency_review=pass "
        "scope=repo-wide"
    ),
    "tool_call=make ci static_analysis=pass scope=repo-wide",
    "tool_call=check_convention_compliance.py CONVENTION_COMPLIANCE=pass",
    "static_analysis_feedback=recorded target=review-backlog-scan",
    "execution_path_comparison_not_required reason=single-active-route",
    "token_efficiency_not_required reason=no-comparable-session",
    "prompt_eval_not_required reason=no-skill-workflow-prompt-change",
    "runtime_feedback_not_observed",
    "review_decision=approve review_findings_integrated=yes",
    "diff_check_agent_decision=approve diff_check_agent_complete=yes",
)
STANDARD_CLOSEOUT_SIGNALS = (
    "mcp_inventory=pass",
    "repo_dependency_review=pass scope=repo-wide",
    "web_research_not_required reason=not-needed-for-closeout-token-recording",
    "review_status=approve",
    "validation_status=pass",
    "drift_risk=checked",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Append signals, interventions, and improvement decisions."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--report-dir", help="Explicit run bundle directory.")
    target.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument(
        "--report-root",
        help="Optional report root. Defaults to <workspace-root>/reports/agents.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used with --run-id and relative report roots.",
    )
    parser.add_argument(
        "--signal",
        action="append",
        default=[],
        help="Signal to append.",
    )
    parser.add_argument(
        "--intervention",
        action="append",
        default=[],
        help="Intervention to append.",
    )
    parser.add_argument(
        "--behavior-event",
        action="append",
        default=[],
        help=(
            "Agent behavior event to append, such as skill invocation, subagent routing, "
            "tool call, review decision, prompt eval result, or feedback action."
        ),
    )
    parser.add_argument(
        "--runtime-feedback",
        action="append",
        default=[],
        help=(
            "User- or reviewer-observed runtime feedback as key=value tokens, for "
            "example 'source=user target=.agents/skills/foo/SKILL.md action=prompt_repair'."
        ),
    )
    parser.add_argument(
        "--closeout-token-preset",
        action="store_true",
        help=(
            "Append the standard closeout behavior tokens consumed by "
            "evaluate_agent_run.py. Use only after the corresponding evidence "
            "has already been verified in the run bundle."
        ),
    )
    parser.add_argument(
        "--decision",
        action="append",
        default=[],
        help=(
            "Improvement decision as key=value. Keys are "
            "skill_improvement_decision, config_improvement_decision, "
            "workflow_improvement_decision, memory_learning_decision."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="Optional timestamp prefix. Defaults to current local time.",
    )
    return parser


def default_monitoring_text(report_dir: Path) -> str:
    """Return a minimal monitoring artifact when one is missing."""
    return "\n".join(
        [
            "# Workflow Monitoring",
            "<!--",
            "@dependency-start",
            "responsibility Records workflow monitoring for this run bundle.",
            "upstream design ../../../agents/templates/"
            "workflow_monitoring.md template",
            "@dependency-end",
            "-->",
            "",
            f"- Run ID: {report_dir.name}",
            "",
            "## Signals",
            "",
            "## Behavior Events",
            "",
            "## Interventions",
            "",
            "## Improvement Decisions",
            "",
            "- skill_improvement_decision: pending",
            "- config_improvement_decision: pending",
            "- workflow_improvement_decision: pending",
            "- memory_learning_decision: pending",
            "",
        ]
    )


def resolve_report_dir(args: argparse.Namespace) -> Path:
    """Resolve the target run bundle directory."""
    workspace_root = Path(str(args.workspace_root)).resolve()
    if args.report_dir:
        return Path(str(args.report_dir)).resolve()
    return (
        resolve_report_root(args.report_root, workspace_root) / str(args.run_id)
    ).resolve()


def timestamp_prefix(timestamp: str) -> str:
    """Return a stable timestamp prefix for an appended line."""
    value = timestamp.strip() or datetime.now().strftime("%Y-%m-%d %H:%M JST")
    return f"`{value}` "


def normalize_entry(entry: str, timestamp: str) -> str:
    """Render one markdown list item."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("workflow monitoring entries must not be empty")
    return f"- {timestamp_prefix(timestamp)}{stripped}"


def normalize_runtime_feedback(entry: str) -> str:
    """Render one runtime feedback event with stable machine-readable tokens."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("runtime feedback entries must not be empty")
    if "target=" not in stripped or "action=" not in stripped:
        raise ValueError("runtime feedback must include target=... and action=...")
    return f"runtime_feedback=observed {stripped}"


def section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    """Return insertion bounds for one level-2 section."""
    start = -1
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break
    if start == -1:
        lines.extend(["", heading, ""])
        start = len(lines) - 2
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def insert_entries(lines: list[str], heading: str, entries: list[str]) -> None:
    """Append entries to one markdown section if they are not already present."""
    if not entries:
        return
    _, end = section_bounds(lines, heading)
    insert_at = end
    if insert_at > 0 and lines[insert_at - 1].strip():
        lines.insert(insert_at, "")
        insert_at += 1
    existing = set(lines)
    for entry in entries:
        if entry in existing:
            continue
        lines.insert(insert_at, entry)
        existing.add(entry)
        insert_at += 1


def parse_decision(raw: str) -> tuple[str, str]:
    """Parse and validate one decision key=value pair."""
    if "=" not in raw:
        raise ValueError(f"invalid decision, expected key=value: {raw}")
    key, value = (part.strip() for part in raw.split("=", 1))
    if key not in DECISION_KEYS:
        raise ValueError(f"unknown decision key: {key}")
    if value not in DECISION_VALUES:
        raise ValueError(f"invalid decision value for {key}: {value}")
    return key, value


def apply_decisions(lines: list[str], decisions: dict[str, str]) -> None:
    """Set improvement decision values in the monitoring artifact."""
    if not decisions:
        return
    start, end = section_bounds(lines, "## Improvement Decisions")
    present: set[str] = set()
    for index in range(start + 1, end):
        stripped = lines[index].strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key = stripped.removeprefix("- ").split(":", 1)[0].strip()
        if key in decisions:
            lines[index] = f"- {key}: {decisions[key]}"
            present.add(key)
    insert_at = end
    for key, value in decisions.items():
        if key in present:
            continue
        lines.insert(insert_at, f"- {key}: {value}")
        insert_at += 1


def append_monitoring(
    report_dir: Path,
    *,
    signals: list[str] | None = None,
    behavior_events: list[str] | None = None,
    runtime_feedback: list[str] | None = None,
    interventions: list[str] | None = None,
    decisions: dict[str, str] | None = None,
    timestamp: str = "",
) -> Path:
    """Append monitoring evidence and return the artifact path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "workflow_monitoring.md"
    if not path.is_file():
        path.write_text(default_monitoring_text(report_dir), encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    signal_entries = [normalize_entry(item, timestamp) for item in signals or []]
    behavior_entries = [
        normalize_entry(item, timestamp) for item in behavior_events or []
    ]
    behavior_entries.extend(
        normalize_entry(normalize_runtime_feedback(item), timestamp)
        for item in runtime_feedback or []
    )
    intervention_entries = [
        normalize_entry(item, timestamp) for item in interventions or []
    ]
    insert_entries(lines, "## Signals", signal_entries)
    insert_entries(lines, "## Behavior Events", behavior_entries)
    insert_entries(lines, "## Interventions", intervention_entries)
    apply_decisions(lines, decisions or {})
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    decisions = dict(parse_decision(item) for item in args.decision)
    signals = list(args.signal)
    behavior_events = list(args.behavior_event)
    if args.closeout_token_preset:
        signals.extend(STANDARD_CLOSEOUT_SIGNALS)
        behavior_events.extend(STANDARD_CLOSEOUT_BEHAVIOR_EVENTS)
    path = append_monitoring(
        resolve_report_dir(args),
        signals=signals,
        behavior_events=behavior_events,
        runtime_feedback=list(args.runtime_feedback),
        interventions=list(args.intervention),
        decisions=decisions,
        timestamp=str(args.timestamp),
    )
    print(f"WORKFLOW_MONITORING={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
