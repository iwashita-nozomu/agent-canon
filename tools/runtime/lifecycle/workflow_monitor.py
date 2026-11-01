#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Appends workflow monitoring evidence to run bundles.
# upstream design ../../../templates/agents/workflow_monitoring.md defines monitor sections
# upstream implementation ../archive/work_log.py owns canonical semantic-ledger append/read
# upstream implementation ../archive/work_log.py appends canonical logical-ledger events
# upstream implementation ./update_lifecycle_contract.py owns update states and evidence identity.
# upstream implementation ../dispatch/agent-canon/src/private_feedback.rs owns native private capture.
# downstream implementation ../../../tests/agent_tools/test_workflow_monitor.py tests it
# @dependency-end
"""Append machine-readable workflow monitoring evidence to one run bundle."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.repository.workspace.workspace_scope import (
    resolve_report_root,
    resolve_runtime_artifact_path,
)
from tools.runtime.lifecycle.update_lifecycle_contract import TRANSACTION_STATES
from tools.runtime.archive.work_log import (
    MONITOR_PASSTHROUGH_FIELDS,
    append_ledger_event,
)

DECISION_KEYS = (
    "skill_improvement_decision",
    "config_improvement_decision",
    "workflow_improvement_decision",
    "knowledge_learning_decision",
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
COMPLETION_SEMANTIC_KINDS = {
    "request_clause",
    "responsibility_unit",
    "decision",
    "change",
    "review_finding",
    "validation",
    "failure",
    "publication_state",
    "deferral",
}
SEMANTIC_EVENT_REQUIRED_KEYS = (
    "event_id",
    "context_id",
    "semantic_kind",
    "owner",
    "state_owner",
    "api_owner",
    "dependency_owner",
    "responsibility_unit",
    "intent_id",
    "outcome",
    "evidence_refs",
    "artifact_refs",
)
STANDARD_CLOSEOUT_BEHAVIOR_EVENTS = (
    "skill_invocation=$agent-orchestration status=observed",
    (
        "close_agent_tool_call=machine_token_required "
        "schema=agent-canon.close-agent-tool-call.v1 prose_substitute=forbidden"
    ),
    (
        "tool_call=run_repo_dependency_review.sh repo_dependency_review=pass "
        "scope=repo-wide"
    ),
    "tool_call=canonical-format-check code_checker=pass checker=markdown-math-mermaid scope=changed-paths",
    "hook_dispatcher=official schema=agent-canon.posttooluse-stop.v1 events=PostToolUse,Stop",
    "static_analysis_feedback=recorded target=review-backlog-scan",
    "validation_failure_not_observed reason=standard-closeout-preset",
    "token_efficiency_not_required reason=no-comparable-session",
    "runtime_feedback_not_observed",
    "review_decision=approve review_findings_integrated=yes",
    "diff_check_agent_decision=approve diff_check_agent_complete=yes",
)
STANDARD_CLOSEOUT_SIGNALS = (
    "repo_dependency_review=pass scope=repo-wide",
    "web_research_not_required reason=not-needed-for-closeout-token-recording",
    "review_status=approve",
    "validation_status=pass",
    "drift_risk=checked",
)
UPDATE_LIFECYCLE_MONITORING_SCHEMA = "agent-canon.update-lifecycle-monitoring.v1"
EVIDENCE_REF_RE = re.compile(r"^evidence:[0-9a-f]{64}$")


def empty_decisions() -> dict[str, str]:
    """Return an empty decision mapping."""
    return {}


@dataclass(frozen=True)
class LifecycleMonitoringEvidence:
    """Pointer-only update lifecycle evidence consumed by the monitor."""

    decision_sufficiency_packet_ref: str
    decision_sufficiency_rejection_ref: str | None
    lifecycle_state: str
    evidence_refs: tuple[str, ...]
    close_agent_tool_call_ref: str | None


@dataclass(frozen=True)
class MonitoringEntries:
    """Structured inputs for one workflow monitoring append."""

    signals: tuple[str, ...] = ()
    behavior_events: tuple[str, ...] = ()
    semantic_events: tuple[str, ...] = ()
    runtime_feedback: tuple[str, ...] = ()
    tool_warnings: tuple[str, ...] = ()
    tool_warning_status: str = ""
    interventions: tuple[str, ...] = ()
    decisions: Mapping[str, str] = field(default_factory=empty_decisions)
    timestamp: str = ""
    lifecycle_evidence: LifecycleMonitoringEvidence | None = None


@dataclass(frozen=True)
class MonitorProjectionResult:
    """Describe the monitor-only projection written after a canonical event."""

    status: str
    path: Path
    error: str = ""


EMPTY_MONITORING_ENTRIES = MonitoringEntries()
MONITORING_LEGACY_KEYS = {
    "signals",
    "behavior_events",
    "semantic_events",
    "runtime_feedback",
    "tool_warnings",
    "tool_warning_status",
    "interventions",
    "decisions",
    "timestamp",
}


@contextmanager
def locked_monitoring_artifact(
    path: Path,
    runtime_root: Path | str | None = None,
) -> Iterator[IO[str]]:
    """Hold an exclusive lock while updating an external monitoring artifact."""
    target = resolve_runtime_artifact_path(path, runtime_root=runtime_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked_existing_artifact(
    path: Path,
    runtime_root: Path | str | None = None,
) -> Iterator[IO[str]]:
    """Hold an exclusive lock while updating an existing artifact."""
    target = resolve_runtime_artifact_path(path, runtime_root=runtime_root)
    with target.open("r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Append signals, interventions, and improvement decisions."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--report-dir", help="Explicit run bundle directory.")
    target.add_argument(
        "--run-id", help="Run id under the external reports/agents root."
    )
    parser.add_argument(
        "--report-root",
        help="Optional external report root. Defaults below --runtime-root.",
    )
    parser.add_argument(
        "--runtime-root",
        help="Explicit external runtime root; defaults to AGENT_CANON_RUNTIME_ROOT.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used with --run-id and relative report roots.",
    )
    add_monitoring_entry_arguments(parser)
    add_tool_warning_arguments(parser)
    add_closeout_decision_arguments(parser)
    return parser


def add_monitoring_entry_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common monitoring entry arguments."""
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
            "tool call, review decision, or feedback action."
        ),
    )
    parser.add_argument(
        "--semantic-event",
        action="append",
        default=[],
        help=(
            "Append one typed logical-ledger event. Required keys: event_id, "
            "semantic_kind, owner, state_owner, api_owner, dependency_owner, "
            "intent_id, outcome, evidence_refs, artifact_refs."
        ),
    )
    parser.add_argument(
        "--runtime-feedback",
        action="append",
        default=[],
        help=(
            "User- or reviewer-observed runtime feedback as key=value tokens, for "
            "example 'source=user target=.codex/personal/skills/foo/SKILL.md action=prompt_repair'."
        ),
    )


def add_tool_warning_arguments(parser: argparse.ArgumentParser) -> None:
    """Add tool warning ledger arguments."""
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


def add_closeout_decision_arguments(parser: argparse.ArgumentParser) -> None:
    """Add closeout preset and improvement decision arguments."""
    parser.add_argument(
        "--closeout-token-preset",
        action="store_true",
        help=(
            "Append standard closeout observations consumed by "
            "the native `agent-canon run-evaluation` command. This preset never substitutes for a canonical "
            "CloseAgentToolCall; use only after lifecycle evidence and the token "
            "reference have been recorded through append_monitoring."
        ),
    )
    parser.add_argument(
        "--decision",
        action="append",
        default=[],
        help=(
            "Improvement decision as key=value. Keys are "
            "skill_improvement_decision, config_improvement_decision, "
            "workflow_improvement_decision, knowledge_learning_decision."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help="Optional timestamp prefix. Defaults to current local time.",
    )


def default_monitoring_text(report_dir: Path) -> str:
    """Return a minimal monitoring artifact when one is missing."""
    return "\n".join(
        [
            "# Workflow Monitoring",
            "<!--",
            "@dependency-start",
            "responsibility Records workflow monitoring for this run bundle.",
            "upstream design ../../../templates/agents/workflow_monitoring.md template",
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
            "- knowledge_learning_decision: pending",
            "",
        ]
    )


def resolve_report_dir(args: argparse.Namespace) -> Path:
    """Resolve the target run bundle directory."""
    if args.report_dir:
        return resolve_runtime_artifact_path(
            Path(str(args.report_dir)).resolve(), runtime_root=args.runtime_root
        )
    return (
        resolve_report_root(
            args.report_root,
            runtime_root=args.runtime_root,
        )
        / str(args.run_id)
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


def normalize_semantic_event(entry: str) -> str:
    """Validate one semantic ledger event before monitoring records it."""
    fields = parse_token_fields(entry.strip())
    missing = [key for key in SEMANTIC_EVENT_REQUIRED_KEYS if not fields.get(key)]
    if missing:
        raise ValueError(
            "semantic event must include required keys: " + ",".join(missing)
        )
    if fields["semantic_kind"] not in COMPLETION_SEMANTIC_KINDS:
        raise ValueError(
            "semantic_kind must be one of: "
            + ",".join(sorted(COMPLETION_SEMANTIC_KINDS))
        )
    for field_name in MONITOR_PASSTHROUGH_FIELDS:
        _structured_semantic_field(fields, field_name)
    return f"ledger_event=projected {entry.strip()}"


def semantic_event_record(entry: str, report_dir: Path) -> dict[str, object]:
    """Convert one monitor token event into the canonical work-ledger record."""
    fields = parse_token_fields(entry.strip())
    missing = [key for key in SEMANTIC_EVENT_REQUIRED_KEYS if not fields.get(key)]
    if missing:
        raise ValueError(
            "semantic event must include required keys: " + ",".join(missing)
        )

    def refs(name: str) -> list[str]:
        values = [
            item.strip() for item in fields.get(name, "").split(",") if item.strip()
        ]
        if not values:
            raise ValueError(f"semantic event requires non-empty {name}")
        return values

    event: dict[str, object] = {
        "run_id": report_dir.name,
        "context_id": fields["context_id"],
        "event_id": fields["event_id"],
        "semantic_kind": fields["semantic_kind"],
        "owner": fields["owner"],
        "state_owner": fields["state_owner"],
        "api_owner": fields["api_owner"],
        "dependency_owner": fields["dependency_owner"],
        "responsibility_unit": fields["responsibility_unit"],
        "intent_id": fields["intent_id"],
        "outcome": fields["outcome"],
        "evidence_refs": refs("evidence_refs"),
        "artifact_refs": refs("artifact_refs"),
    }
    for optional in ("sequence", "clause_id", "mapping_mode"):
        if fields.get(optional):
            event[optional] = fields[optional]
    if fields.get("member_clause_ids"):
        event["member_clause_ids"] = refs("member_clause_ids")
    for field_name in MONITOR_PASSTHROUGH_FIELDS:
        value = _structured_semantic_field(fields, field_name)
        if value is not None:
            event[field_name] = value
    return event


def _structured_semantic_field(
    fields: Mapping[str, str], field: str
) -> Mapping[str, object] | list[object] | None:
    """Decode schema-owned structured evidence without dropping it at the monitor boundary."""
    raw = fields.get(field, "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"semantic event {field} must be compact JSON") from exc
    if not isinstance(value, (dict, list)):
        raise ValueError(f"semantic event {field} must be an object or list")
    return cast(Mapping[str, object] | list[object], value)


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
        semantic_events=string_entries(kwargs.get("semantic_events")),
        tool_warnings=string_entries(kwargs.get("tool_warnings")),
        tool_warning_status=str(kwargs.get("tool_warning_status", "")),
        interventions=string_entries(kwargs.get("interventions")),
        decisions=decision_entries(kwargs.get("decisions")),
        timestamp=str(kwargs.get("timestamp", "")),
    )


def lifecycle_monitoring_record(
    evidence: LifecycleMonitoringEvidence,
) -> dict[str, object]:
    """Validate and return one pointer-only lifecycle monitor record."""
    if not evidence.decision_sufficiency_packet_ref:
        raise ValueError("lifecycle_monitoring:decision_packet_ref_missing")
    if evidence.lifecycle_state not in TRANSACTION_STATES:
        raise ValueError("lifecycle_monitoring:state_invalid")
    if not evidence.evidence_refs:
        raise ValueError("lifecycle_monitoring:evidence_refs_missing")
    if any(EVIDENCE_REF_RE.fullmatch(ref) is None for ref in evidence.evidence_refs):
        raise ValueError("lifecycle_monitoring:evidence_ref_invalid")
    if len(evidence.evidence_refs) != len(set(evidence.evidence_refs)):
        raise ValueError("lifecycle_monitoring:evidence_ref_duplicate")
    if evidence.lifecycle_state == "closed" and not evidence.close_agent_tool_call_ref:
        raise ValueError("lifecycle_monitoring:close_tool_call_ref_missing")
    return {
        "schema": UPDATE_LIFECYCLE_MONITORING_SCHEMA,
        "decision_sufficiency_packet_ref": evidence.decision_sufficiency_packet_ref,
        "decision_sufficiency_rejection_ref": evidence.decision_sufficiency_rejection_ref,
        "lifecycle_state": evidence.lifecycle_state,
        "evidence_refs": list(evidence.evidence_refs),
        "close_agent_tool_call_ref": evidence.close_agent_tool_call_ref,
    }


def append_lifecycle_monitoring_record(
    lines: list[str],
    evidence: LifecycleMonitoringEvidence | None,
) -> None:
    """Append one canonical JSON record through the locked monitor path."""
    if evidence is None:
        return
    record = lifecycle_monitoring_record(evidence)
    insert_entries(
        lines,
        "## Update Lifecycle Evidence",
        [json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))],
    )


def append_monitoring_sections(
    lines: list[str],
    entries: MonitoringEntries,
) -> None:
    """Apply actual monitoring entries to workflow_monitoring.md sections."""
    signal_entries = [
        normalize_entry(item, entries.timestamp) for item in entries.signals
    ]
    behavior_entries = [
        normalize_entry(item, entries.timestamp) for item in entries.behavior_events
    ]
    behavior_entries.extend(
        normalize_entry(normalize_semantic_event(item), entries.timestamp)
        for item in entries.semantic_events
    )
    behavior_entries.extend(
        normalize_entry(normalize_runtime_feedback(item), entries.timestamp)
        for item in entries.runtime_feedback
    )
    tool_warning_entries = [
        normalize_entry(normalize_tool_warning(item), entries.timestamp)
        for item in entries.tool_warnings
    ]
    intervention_entries = [
        normalize_entry(item, entries.timestamp) for item in entries.interventions
    ]
    insert_entries(lines, "## Signals", signal_entries)
    insert_entries(lines, "## Behavior Events", behavior_entries)
    insert_entries(lines, "## Tool Warnings", tool_warning_entries)
    inferred_tool_warning_status = (
        entries.tool_warning_status or infer_tool_warning_status(lines)
    )
    set_section_status(
        lines,
        "## Tool Warnings",
        "tool_warnings_status",
        inferred_tool_warning_status,
    )
    insert_entries(lines, "## Interventions", intervention_entries)
    append_lifecycle_monitoring_record(lines, entries.lifecycle_evidence)
    apply_decisions(lines, dict(entries.decisions))


def append_monitoring(
    report_dir: Path,
    entries: MonitoringEntries = EMPTY_MONITORING_ENTRIES,
    *,
    runtime_root: Path | str | None = None,
    **legacy_entries: object,
) -> Path:
    """Append monitoring evidence and return the artifact path."""
    active_entries = entries_from_legacy(legacy_entries) if legacy_entries else entries
    resolve_runtime_artifact_path(
        report_dir / "workflow_monitoring.md", runtime_root=runtime_root
    ).parent.mkdir(parents=True, exist_ok=True)
    for semantic_event in active_entries.semantic_events:
        append_ledger_event(
            report_dir,
            semantic_event_record(semantic_event, report_dir),
            runtime_root=runtime_root,
        )
    path = resolve_runtime_artifact_path(
        report_dir / "workflow_monitoring.md", runtime_root=runtime_root
    )
    with locked_monitoring_artifact(path, runtime_root) as handle:
        text = handle.read()
        if not text.strip():
            text = default_monitoring_text(report_dir)
        lines = text.splitlines()
        append_monitoring_sections(lines, active_entries)
        handle.seek(0)
        handle.truncate()
        handle.write("\n".join(lines).rstrip() + "\n")
    return path


def emit_behavior_projection(
    report_dir: Path,
    event: dict[str, object],
    runtime_root: Path | str | None = None,
) -> MonitorProjectionResult:
    """Project one already-assembled event without writing the canonical JSONL artifact."""
    try:
        encoded = json.dumps(
            event, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        path = append_monitoring(
            report_dir,
            MonitoringEntries(behavior_events=(f"behavior_event_json={encoded}",)),
            runtime_root=runtime_root,
        )
        return MonitorProjectionResult("spooled", path)
    except Exception as exc:
        return MonitorProjectionResult(
            "failed", report_dir / "workflow_monitoring.md", type(exc).__name__
        )


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    effective_runtime_root = (
        args.runtime_root
        or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
        or None
    )
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
            semantic_events=tuple(args.semantic_event),
            runtime_feedback=tuple(args.runtime_feedback),
            tool_warnings=tuple(args.tool_warning),
            tool_warning_status=str(args.tool_warning_status),
            interventions=tuple(args.intervention),
            decisions=decisions,
            timestamp=str(args.timestamp),
        ),
        runtime_root=effective_runtime_root,
    )
    # Structured runtime feedback is also accumulated in the private log
    # spool.  This is deliberately best-effort: monitoring remains usable
    # when private feedback is not configured, while the feedback body never
    # enters the monitoring receipt or dashboard.
    if args.runtime_feedback and effective_runtime_root:
        # The monitor remains Python until its own port. Private feedback has one
        # native owner; stdin preserves structured-log provenance without putting
        # private bodies in command arguments or the monitoring receipt.
        executable = os.environ.get("AGENT_CANON_NATIVE_BIN") or "agent-canon"
        for entry in args.runtime_feedback:
            try:
                subprocess.run(
                    [
                        executable,
                        "f",
                        "capture",
                        "--structured-log",
                        "--stdin",
                        "--runtime-root",
                        str(effective_runtime_root),
                        "--run",
                        path.parent.name,
                    ],
                    input=entry,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except Exception:
                # The canonical monitoring artifact has already been written;
                # the host sync route will retain any successful private spool.
                continue
    print(f"WORKFLOW_MONITORING={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
