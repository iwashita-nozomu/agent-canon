#!/usr/bin/env python3
# @dependency-start
# responsibility Appends workflow monitoring evidence to run bundles.
# upstream design ../../agents/templates/workflow_monitoring.md defines monitor sections
# downstream implementation ../../tests/agent_tools/test_workflow_monitor.py tests it
# @dependency-end
"""Append machine-readable workflow monitoring evidence to one run bundle."""

from __future__ import annotations

import argparse
import fcntl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO, cast

from agent_team import resolve_report_root

DECISION_KEYS = (
    "skill_improvement_decision",
    "config_improvement_decision",
    "workflow_improvement_decision",
    "memory_learning_decision",
)
DECISION_VALUES = {"applied", "recorded", "not_applicable", "pending"}
TOOL_WARNING_REQUIRED_KEYS = (
    "warning_id",
    "source_tool",
    "severity",
    "status",
    "message",
    "repair_command",
)
TOOL_WARNING_STATUS_VALUES = {
    "open",
    "resolved",
    "accepted_with_reason",
    "deferred_with_issue",
    "not_applicable",
}
TOOL_WARNING_LEDGER_STATUS_VALUES = {"pending", "open", "resolved", "none"}
STANDARD_CLOSEOUT_BEHAVIOR_EVENTS = (
    "skill_invocation=$agent-orchestration status=observed",
    "subagent_lifecycle=closed subagents_closed=yes fresh_subagents_required=true",
    (
        "tool_call=run_repo_dependency_review.sh repo_dependency_review=pass "
        "scope=repo-wide"
    ),
    "tool_call=make ci static_analysis=pass scope=repo-wide",
    "tool_call=pyright code_checker=pass checker=pyright scope=repo-wide",
    "tool_call=ruff code_checker=pass checker=ruff scope=repo-wide",
    (
        "tool_call=oop-readability-check code_checker=pass "
        "checker=oop-readability scope=changed-paths"
    ),
    "tool_call=check_convention_compliance.py CONVENTION_COMPLIANCE=pass",
    "static_analysis_feedback=recorded target=review-backlog-scan",
    (
        "hook_tool_feedback=reviewed parent_protocol_update=not_required "
        "subagent_protocol_update=not_required "
        "protocol_feedback_reason=standard-closeout-no-new-protocol-change"
    ),
    (
        "pre_edit_rejection_prediction=reviewed "
        "predicted_tool_rejection_gates=recorded"
    ),
    "execution_path_comparison_not_required reason=single-active-route",
    "token_efficiency_not_required reason=no-comparable-session",
    "prompt_eval_required action=run_evaluate_skill_workflow_prompts_with_accumulate",
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


def empty_decisions() -> dict[str, str]:
    """Return an empty decision mapping."""
    return {}


@dataclass(frozen=True)
class MonitoringEntries:
    """Structured inputs for one workflow monitoring append."""

    signals: tuple[str, ...] = ()
    behavior_events: tuple[str, ...] = ()
    runtime_feedback: tuple[str, ...] = ()
    tool_warnings: tuple[str, ...] = ()
    tool_warning_status: str = ""
    interventions: tuple[str, ...] = ()
    decisions: Mapping[str, str] = field(default_factory=empty_decisions)
    timestamp: str = ""


EMPTY_MONITORING_ENTRIES = MonitoringEntries()
MONITORING_LEGACY_KEYS = {
    "signals",
    "behavior_events",
    "runtime_feedback",
    "tool_warnings",
    "tool_warning_status",
    "interventions",
    "decisions",
    "timestamp",
}


@contextmanager
def locked_monitoring_artifact(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive lock while updating the monitoring artifact."""
    path.touch(exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            yield handle
        finally:
            handle.flush()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        "--tool-warning",
        action="append",
        default=[],
        help=(
            "Observed non-blocking tool, hook, checker, or wrapper warning as "
            "key=value tokens. Required keys: warning_id, source_tool, severity, "
            "status, message, repair_command. Status values: open, resolved, "
            "accepted_with_reason, deferred_with_issue, not_applicable."
        ),
    )
    parser.add_argument(
        "--tool-warning-status",
        choices=sorted(TOOL_WARNING_LEDGER_STATUS_VALUES),
        default="",
        help=(
            "Set the aggregate Tool Warnings ledger status. Use none when no "
            "tool warnings were observed, open while any warning is unresolved, "
            "and resolved only after all warning_ids are closed."
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
            "## Tool Warnings",
            "",
            "- tool_warnings_status: pending",
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


def parse_token_fields(entry: str) -> dict[str, str]:
    """Parse whitespace-separated key=value tokens."""
    data: dict[str, str] = {}
    for token in entry.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def normalize_tool_warning(entry: str) -> str:
    """Render one tool warning ledger item with required routing fields."""
    stripped = entry.strip()
    if not stripped:
        raise ValueError("tool warning entries must not be empty")
    fields = parse_token_fields(stripped)
    missing = [key for key in TOOL_WARNING_REQUIRED_KEYS if key not in fields]
    if missing:
        raise ValueError(
            "tool warning must include required keys: " + ",".join(missing)
        )
    status = fields["status"]
    if status not in TOOL_WARNING_STATUS_VALUES:
        raise ValueError(
            "tool warning status must be one of: "
            + ",".join(sorted(TOOL_WARNING_STATUS_VALUES))
        )
    return f"tool_warning=recorded {stripped}"


def set_section_status(
    lines: list[str],
    heading: str,
    key: str,
    value: str,
) -> None:
    """Set or insert one '- key: value' line under a section."""
    if not value:
        return
    ensure_section(lines, heading)
    start, end = section_bounds(lines, heading)
    prefix = f"- {key}:"
    for index in range(start + 1, end):
        if lines[index].strip().startswith(prefix):
            lines[index] = f"- {key}: {value}"
            return
    insert_at = start + 1
    while insert_at < end and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, f"- {key}: {value}")


def infer_tool_warning_status(lines: list[str]) -> str:
    """Infer aggregate ledger status from the latest row for each warning_id."""
    start = section_start(lines, "## Tool Warnings")
    if start == -1:
        return ""
    section = "\n".join(markdown_section_lines(lines, "## Tool Warnings"))
    latest: dict[str, str] = {}
    for line in section.splitlines():
        if "tool_warning=recorded" not in line:
            continue
        fields = parse_token_fields(line)
        warning_id = fields.get("warning_id", "")
        status = fields.get("status", "")
        if warning_id and status:
            latest[warning_id] = status
    if not latest:
        return ""
    if any(status == "open" for status in latest.values()):
        return "open"
    return "resolved"


def markdown_section_lines(lines: list[str], heading: str) -> list[str]:
    """Return raw lines for one existing level-2 markdown section."""
    start = section_start(lines, heading)
    if start == -1:
        return []
    _, end = section_bounds(lines, heading)
    return lines[start:end]


def section_start(lines: list[str], heading: str) -> int:
    """Return the heading index for one level-2 section, or -1 when absent."""
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    return -1


def ensure_section(lines: list[str], heading: str) -> None:
    """Append a level-2 section when the artifact does not contain it yet."""
    if section_start(lines, heading) == -1:
        lines.extend(["", heading, ""])


def section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    """Return insertion bounds for one existing level-2 section."""
    start = section_start(lines, heading)
    if start == -1:
        raise ValueError(f"missing workflow monitoring section: {heading}")
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
    ensure_section(lines, heading)
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
    ensure_section(lines, "## Improvement Decisions")
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


def string_entries(value: object) -> tuple[str, ...]:
    """Return one legacy entry field as a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        items = cast("list[object] | tuple[object, ...]", value)
        return tuple(str(item) for item in items)
    raise TypeError(f"expected string entries, got {type(value).__name__}")


def decision_entries(value: object) -> Mapping[str, str]:
    """Return one legacy decision field as a string mapping."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        items = cast("Mapping[object, object]", value)
        return {str(key): str(item) for key, item in items.items()}
    raise TypeError(f"expected decision mapping, got {type(value).__name__}")


def entries_from_legacy(kwargs: dict[str, object]) -> MonitoringEntries:
    """Build structured monitoring entries from the pre-dataclass keyword API."""
    unknown = set(kwargs) - MONITORING_LEGACY_KEYS
    if unknown:
        raise TypeError(f"unknown monitoring entry keys: {','.join(sorted(unknown))}")
    return MonitoringEntries(
        signals=string_entries(kwargs.get("signals")),
        behavior_events=string_entries(kwargs.get("behavior_events")),
        runtime_feedback=string_entries(kwargs.get("runtime_feedback")),
        tool_warnings=string_entries(kwargs.get("tool_warnings")),
        tool_warning_status=str(kwargs.get("tool_warning_status", "")),
        interventions=string_entries(kwargs.get("interventions")),
        decisions=decision_entries(kwargs.get("decisions")),
        timestamp=str(kwargs.get("timestamp", "")),
    )


def append_monitoring(
    report_dir: Path,
    entries: MonitoringEntries = EMPTY_MONITORING_ENTRIES,
    **legacy_entries: object,
) -> Path:
    """Append monitoring evidence and return the artifact path."""
    active_entries = entries_from_legacy(legacy_entries) if legacy_entries else entries
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "workflow_monitoring.md"
    with locked_monitoring_artifact(path) as handle:
        text = handle.read()
        if not text.strip():
            text = default_monitoring_text(report_dir)
        lines = text.splitlines()
        signal_entries = [
            normalize_entry(item, active_entries.timestamp)
            for item in active_entries.signals
        ]
        behavior_entries = [
            normalize_entry(item, active_entries.timestamp)
            for item in active_entries.behavior_events
        ]
        behavior_entries.extend(
            normalize_entry(normalize_runtime_feedback(item), active_entries.timestamp)
            for item in active_entries.runtime_feedback
        )
        tool_warning_entries = [
            normalize_entry(normalize_tool_warning(item), active_entries.timestamp)
            for item in active_entries.tool_warnings
        ]
        intervention_entries = [
            normalize_entry(item, active_entries.timestamp)
            for item in active_entries.interventions
        ]
        insert_entries(lines, "## Signals", signal_entries)
        insert_entries(lines, "## Behavior Events", behavior_entries)
        insert_entries(lines, "## Tool Warnings", tool_warning_entries)
        inferred_tool_warning_status = (
            active_entries.tool_warning_status or infer_tool_warning_status(lines)
        )
        set_section_status(
            lines,
            "## Tool Warnings",
            "tool_warnings_status",
            inferred_tool_warning_status,
        )
        insert_entries(lines, "## Interventions", intervention_entries)
        apply_decisions(lines, dict(active_entries.decisions))
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(lines).rstrip() + "\n")
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
        MonitoringEntries(
            signals=tuple(signals),
            behavior_events=tuple(behavior_events),
            runtime_feedback=tuple(args.runtime_feedback),
            tool_warnings=tuple(args.tool_warning),
            tool_warning_status=str(args.tool_warning_status),
            interventions=tuple(args.intervention),
            decisions=decisions,
            timestamp=str(args.timestamp),
        ),
    )
    print(f"WORKFLOW_MONITORING={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
