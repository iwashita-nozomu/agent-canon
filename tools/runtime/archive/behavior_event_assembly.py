#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Assembles, deduplicates, and appends one canonical behavior event per eligible hook invocation.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md owns event identity, cardinality, and write order.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns coordination receipt semantics.
# upstream implementation ./prompt_capture.py owns prompt evidence.
# upstream implementation ./prompt_classifier.py owns pure prompt routing.
# upstream implementation ./tool_selection.py owns tool evidence.
# upstream implementation ./subagent_selection.py owns subagent evidence.
# upstream implementation ./workflow_context.py owns context load/store.
# upstream implementation ../../.codex/hooks/hook_event_log.py owns append-only transport primitives.
# downstream implementation ./workflow_monitor.py emits the post-append projection.
# downstream implementation ./generate_agent_runtime_dashboard.py reads canonical events.
# downstream implementation ../../tests/agent_tools/test_behavior_event_assembly.py validates cardinality and fail-open behavior.
# @dependency-end
"""Canonical behavior-event assembly and readback owner."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from tools.agent.orchestration.prompt_capture import PromptCapture, capture_prompt  # noqa: E402
from tools.agent.orchestration.prompt_classifier import (  # noqa: E402
    PromptClassifierInputs,
    PromptIntakeSignals,
    prompt_intake_signals,
)
from tools.agent.orchestration.subagent_selection import SubagentSelection  # noqa: E402
from tools.agent.orchestration.tool_selection import ToolSelection  # noqa: E402
from tools.agent.orchestration.workflow_context import WorkflowContext  # noqa: E402

SCHEMA = "agent-canon.behavior-event.v1"
RECORD_KIND = "behavior_event"
EVENT_KIND = "behavior_snapshot"
ACTIVE_EVENTS = frozenset({"UserPromptSubmit", "PreToolUse", "PostToolUse"})
EVENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")

PARITY_FIELDS = (
    "hook_log_namespace", "root", "event_declared", "skills", "selected_skills", "skill_selection_kind", "skill_count",
    "selected_workflow", "selected_workflows", "workflow", "workflow_family", "workflow_selection_kind", "workflow_attribution_kind",
    "workflow_owner", "workflow_owner_workflows", "workflow_context_kind", "workflow_context_source", "workflow_context_workflows",
    "workflow_context_timestamp", "workflow_context_source_event", "selected_workflow_count", "candidate_skills", "candidate_skill_reasons",
    "candidate_skill_count", "candidate_workflows", "candidate_workflow_count", "candidate_tools", "candidate_tool_count", "prompt_capture_status",
    "prompt_excerpt_redacted", "prompt_fingerprint", "prompt_char_count", "prompt_excerpt_truncated", "tool_name", "tool_selection_kind",
    "tool_input_fingerprint", "tool_input_key_count", "tool_input_keys", "tool_command_verb", "selected_tools", "selected_tool_count",
    "subagent_invoked", "subagent_event_kind", "subagent_tool_name", "subagent_agent_type", "subagent_target", "subagent_targets",
    "subagent_target_count", "subagent_model", "subagent_reasoning_effort", "subagent_fork_context", "subagent_prompt_fingerprint",
    "subagent_prompt_char_count", "subagent_item_count", "prompt_feedback_detected", "feedback_labels", "feedback_targets", "feedback_action",
    "skill_source_fields", "observed_text_field_count", "observed_text_value_count", "payload_key_count", "payload_fingerprint",
    "tool_input_fingerprint", "workflow_monitor_event_count", "workflow_monitor_feedback_count", "workflow_monitor_subagent_event_count",
    "workflow_monitor_report_dir",
)

# These values are consumed by the accumulation checker and dashboard.  Keep
# the attribution decision in this assembler so downstream readers do not
# have to reconstruct it from legacy candidate/selection fields.
WORKFLOW_ATTRIBUTION_KINDS = frozenset({"owner", "context", "missing"})
PROMPT_CAPTURE_STATUSES = frozenset({"present", "missing"})


@dataclass(frozen=True)
class HookInvocationParts:
    hook_event_name: str
    hook_invocation_id: str
    hook_payload: Mapping[str, object] | None = None
    payload_status: str = "parsed"
    handler_result: "FinalHandlerResult" = field(default_factory=lambda: FinalHandlerResult())
    classifier_rules: PromptClassifierInputs | None = None
    tool_selection: ToolSelection | None = None
    subagent_selection: SubagentSelection | None = None
    workflow_context: WorkflowContext = field(default_factory=WorkflowContext)
    payload_fingerprint: str = ""
    timestamp: str = ""
    root: Path = Path(".")
    hook_log_namespace: str = ""
    report_dir: Path | None = None


@dataclass(frozen=True)
class FinalHandlerResult:
    """Final safe dispatcher result; it deliberately excludes raw hook material."""

    status: str = "pass"
    output_kind: str = ""
    safe_fields: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BehaviorEvent:
    data: Mapping[str, object]

    @property
    def event_id(self) -> str:
        return str(self.data["event_id"])

    def as_dict(self) -> dict[str, object]:
        return dict(self.data)

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.data, allow_nan=False, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class BehaviorReadback:
    accepted_count: int = 0
    duplicate_count: int = 0
    malformed_count: int = 0
    ignored_count: int = 0
    malformed_by_reason: Mapping[str, int] = field(default_factory=dict)
    events: tuple[dict[str, object], ...] = ()
    status: str = "missing"


def _canonical(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _default_fields() -> dict[str, object]:
    fields: dict[str, object] = {}
    for name in PARITY_FIELDS:
        fields[name] = [] if name.endswith("s") or name in {"selected_tools", "skills", "workflow", "tool_input_keys", "feedback_labels", "feedback_targets"} else 0 if name.endswith("count") else False if name.endswith("invoked") or name.endswith("context") or name.endswith("truncated") or name.startswith("prompt_feedback") or name == "event_declared" else ""
    return fields


def _parts_payload(parts: HookInvocationParts) -> dict[str, object]:
    return dict(parts.hook_payload) if isinstance(parts.hook_payload, Mapping) else {}


def _signal_bundle(parts: HookInvocationParts) -> tuple[PromptCapture, PromptIntakeSignals, ToolSelection, SubagentSelection, WorkflowContext]:
    payload = _parts_payload(parts)
    prompt = capture_prompt(payload)
    rules = parts.classifier_rules or PromptClassifierInputs(
        prompt="",
        repo_root=parts.root,
        catalog=MappingProxyType({}),
        routing_rules=MappingProxyType({}),
    )
    classifier = prompt_intake_signals(rules)
    tool = parts.tool_selection or ToolSelection()
    subagent = parts.subagent_selection or SubagentSelection()
    context = parts.workflow_context
    return prompt, classifier, tool, subagent, context


def eligible_hook_invocation(parts: HookInvocationParts) -> bool:
    if parts.hook_event_name not in ACTIVE_EVENTS:
        return False
    if parts.payload_status != "parsed" or parts.handler_result.status in {"malformed_payload", "blocked_secret", "blocked_destructive_git", "blocked_parent_mutation", "invalid_projection"}:
        return False
    prompt, classifier, tool, subagent, context = _signal_bundle(parts)
    return bool(prompt.should_log() or classifier.should_log() or tool.should_log() or subagent.should_log() or context.has_workflow())


def _workflow_context_fields(
    attribution_kind: str,
    context: WorkflowContext,
) -> dict[str, object]:
    """Return context carriers only when context owns attribution."""
    if attribution_kind == "owner":
        return {
            "workflow_context_kind": "",
            "workflow_context_source": "",
            "workflow_context_workflows": [],
            "workflow_context_timestamp": "",
            "workflow_context_source_event": "",
        }
    return {
        "workflow_context_kind": "context_workflow" if context.workflows else "",
        "workflow_context_source": "recent_log" if context.workflows else "",
        "workflow_context_workflows": list(context.workflows),
        "workflow_context_timestamp": context.timestamp,
        "workflow_context_source_event": context.source_event,
    }


def _assemble_fields(parts: HookInvocationParts) -> dict[str, object]:
    prompt, classifier, tool, subagent, context = _signal_bundle(parts)
    payload = _parts_payload(parts)
    fields = _default_fields()
    workflow_attribution_kind = (
        "owner"
        if classifier.selected_workflows
        else "context"
        if context.workflows
        else "missing"
    )
    prompt_capture_status = prompt.status if prompt.status in PROMPT_CAPTURE_STATUSES else "missing"
    fields.update({
        "hook_log_namespace": parts.hook_log_namespace,
        "root": str(parts.root),
        "event_declared": True,
        "skills": list(classifier.skills), "selected_skills": list(classifier.skills), "skill_selection_kind": "declared_skill" if classifier.skills else "", "skill_count": len(classifier.skills),
        "selected_workflow": classifier.selected_workflows[0] if classifier.selected_workflows else "",
        "selected_workflows": list(classifier.selected_workflows), "workflow": list(classifier.selected_workflows), "workflow_family": classifier.selected_workflows[0] if classifier.selected_workflows else "",
        "workflow_selection_kind": "declared_workflow" if classifier.selected_workflows else "context_workflow" if context.workflows else "",
        "workflow_attribution_kind": workflow_attribution_kind,
        "workflow_owner": classifier.selected_workflows[0] if classifier.selected_workflows else "",
        "workflow_owner_workflows": list(classifier.selected_workflows), **_workflow_context_fields(workflow_attribution_kind, context), "selected_workflow_count": len(classifier.selected_workflows),
        "candidate_skills": list(classifier.candidate_skills), "candidate_skill_reasons": list(classifier.candidate_skill_reasons), "candidate_skill_count": len(classifier.candidate_skills),
        "candidate_workflows": list(classifier.candidate_workflows), "candidate_workflow_count": len(classifier.candidate_workflows), "candidate_tools": list(classifier.candidate_tools), "candidate_tool_count": len(classifier.candidate_tools),
        "prompt_capture_status": prompt_capture_status, "prompt_excerpt_redacted": prompt.excerpt_redacted if prompt_capture_status == "present" else "", "prompt_fingerprint": prompt.fingerprint if prompt_capture_status == "present" else "", "prompt_char_count": prompt.char_count if prompt_capture_status == "present" else 0, "prompt_excerpt_truncated": prompt.truncated if prompt_capture_status == "present" else False,
        "tool_name": tool.tool_name, "tool_selection_kind": tool.selection_kind, "tool_input_fingerprint": tool.tool_input_fingerprint, "tool_input_key_count": tool.tool_input_key_count, "tool_input_keys": list(tool.tool_input_keys), "tool_command_verb": tool.command_verb, "selected_tools": list(tool.selected_tools), "selected_tool_count": len(tool.selected_tools),
        "subagent_invoked": subagent.invoked, "subagent_event_kind": subagent.action, "subagent_tool_name": subagent.tool_name, "subagent_agent_type": subagent.agent_type, "subagent_target": subagent.target, "subagent_targets": list(subagent.targets), "subagent_target_count": len(subagent.targets) + int(bool(subagent.target)), "subagent_model": subagent.model, "subagent_reasoning_effort": subagent.reasoning_effort, "subagent_fork_context": subagent.fork_context, "subagent_prompt_fingerprint": subagent.prompt_fingerprint, "subagent_prompt_char_count": subagent.prompt_char_count, "subagent_item_count": subagent.item_count,
        "prompt_feedback_detected": bool(classifier.feedback_labels), "feedback_labels": list(classifier.feedback_labels), "feedback_targets": list(classifier.feedback_targets()), "feedback_action": classifier.feedback_action,
        "payload_key_count": len(payload), "payload_fingerprint": parts.payload_fingerprint or _fingerprint(payload), "workflow_monitor_report_dir": str(parts.report_dir) if parts.report_dir is not None else "",
    })
    return fields


def assemble_behavior_event(parts: HookInvocationParts) -> BehaviorEvent:
    """Assemble one canonical event; callers decide eligibility before writing."""
    if parts.hook_event_name not in ACTIVE_EVENTS:
        raise ValueError("hook_event_name")
    fields = _assemble_fields(parts)
    event: dict[str, object] = {
        "schema": SCHEMA, "record_kind": RECORD_KIND, "hook_invocation_id": parts.hook_invocation_id,
        "hook_event_name": parts.hook_event_name, "event_kind": EVENT_KIND, "timestamp": parts.timestamp,
        "source": "behavior_event_assembly", "status": parts.handler_result.status, **fields,
    }
    behavior_fields = {key: value for key, value in event.items() if key not in {"event_id", "timestamp"}}
    preimage = {
        "schema": SCHEMA,
        "record_kind": RECORD_KIND,
        "hook_invocation_id": parts.hook_invocation_id,
        "hook_event_name": parts.hook_event_name,
        "event_kind": EVENT_KIND,
        "payload_fingerprint": fields["payload_fingerprint"],
        "behavior_fields": behavior_fields,
    }
    event["event_id"] = hashlib.sha256(_canonical(preimage)).hexdigest()
    return BehaviorEvent(event)


def record_hook_invocation(parts: HookInvocationParts) -> BehaviorEvent | None:
    """Return one pure behavior candidate or ``None``; this function never writes."""
    try:
        if not eligible_hook_invocation(parts):
            return None
        return assemble_behavior_event(parts)
    except Exception:
        return None


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def parse_behavior_events(path: Path) -> BehaviorReadback:
    """Parse active behavior events with aggregation and deterministic ordering."""
    if not path.exists():
        return BehaviorReadback(status="missing")
    accepted: list[tuple[datetime, int, dict[str, object], bytes]] = []
    ids: dict[str, bytes] = {}
    invocations: set[str] = set()
    duplicate = malformed = ignored = 0
    reasons: dict[str, int] = {}
    def bad(reason: str) -> None:
        nonlocal malformed
        malformed += 1
        reasons[reason] = reasons.get(reason, 0) + 1
    try:
        lines = path.read_bytes().splitlines()
    except OSError:
        bad("line_encoding")
        return BehaviorReadback(0, 0, malformed, 0, reasons, (), "malformed")
    for sequence, raw in enumerate(lines):
        if not raw.strip():
            ignored += 1
            continue
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("json")))
        except UnicodeDecodeError:
            bad("line_encoding"); continue
        except ValueError as exc:
            bad(str(exc) if str(exc) in {"duplicate_key", "json"} else "json"); continue
        except json.JSONDecodeError:
            bad("json"); continue
        if not isinstance(value, dict):
            bad("schema"); continue
        canonical = _canonical(value)
        if raw != canonical:
            bad("noncanonical_json"); continue
        if value.get("schema") != SCHEMA or value.get("record_kind") != RECORD_KIND or value.get("event_kind") != EVENT_KIND:
            bad("schema"); continue
        event_id = value.get("event_id")
        hook_id = value.get("hook_invocation_id")
        timestamp = value.get("timestamp")
        if not isinstance(event_id, str) or EVENT_ID_RE.fullmatch(event_id) is None or not isinstance(hook_id, str) or not isinstance(timestamp, str):
            bad("field_type"); continue
        if not UTC_RE.fullmatch(timestamp):
            bad("timestamp"); continue
        payload_fingerprint = value.get("payload_fingerprint")
        behavior_fields = {key: item for key, item in value.items() if key not in {"event_id", "timestamp"}}
        expected_id = hashlib.sha256(_canonical({
            "schema": SCHEMA,
            "record_kind": RECORD_KIND,
            "hook_invocation_id": hook_id,
            "hook_event_name": value.get("hook_event_name"),
            "event_kind": value.get("event_kind"),
            "payload_fingerprint": payload_fingerprint,
            "behavior_fields": behavior_fields,
        })).hexdigest()
        if event_id != expected_id:
            bad("field_domain"); continue
        try:
            parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            bad("timestamp"); continue
        existing = ids.get(event_id)
        if existing is not None:
            if existing == raw:
                duplicate += 1
            else:
                bad("conflicting_event_id")
            continue
        if hook_id in invocations:
            bad("schema"); continue
        ids[event_id] = raw; invocations.add(hook_id)
        accepted.append((parsed_time, sequence, value, raw))
    accepted.sort(key=lambda item: (item[0], item[1]))
    return BehaviorReadback(len(accepted), duplicate, malformed, ignored, reasons, tuple(item[2] for item in accepted), "malformed" if malformed else "present")
