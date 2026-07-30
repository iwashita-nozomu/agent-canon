#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Dispatches the bounded active hook contract in-process without child processes, Git, or network access.
# upstream implementation ../hooks.json invokes this dispatcher once per active event.
# upstream implementation ../../tools/agent_tools/hook_safety.py owns pure secret and destructive Git safety leaves.
# upstream implementation ../../tools/agent_tools/execution_resource_projection.py validates producer projection bytes.
# upstream implementation ./hook_event_log.py provides one bounded local spool context per event.
# downstream implementation ../../tools/agent_tools/behavior_event_assembly.py records one behavior snapshot.
# downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates the active/inactive contract.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates dispatch, redaction, malformed input, and no-subprocess behavior.
# @dependency-end

"""Run the canonical in-process Codex lifecycle hook contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = SOURCE_ROOT / "tools" / "agent_tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from hook_safety import (  # noqa: E402
    SHELL_TOOL_NAMES,
    branch_block_payload,
    first_block,
    payload_prompt,
    payload_tool_command,
    payload_tool_name,
    secret_block_payload,
    secret_kind,
)
from execution_resource_projection import (  # noqa: E402
    ProjectionError,
    validate_normalized_input,
    validate_projection_bytes,
)
from hook_event_log import HookLogContext, utc_now  # noqa: E402
from hook_retirement import (  # noqa: E402
    MOVED_SOURCE_ABSENCES,
    RETIRED_CHILD_TOMBSTONES,
    TOMBSTONE_SCHEMA,
    source_digest,
)
from behavior_event_assembly import (  # noqa: E402
    FinalHandlerResult,
    HookInvocationParts,
    record_hook_invocation,
)
from prompt_classifier import PromptClassifierInputs, freeze  # noqa: E402
from subagent_selection import select_subagents  # noqa: E402
from tool_selection import select_tools  # noqa: E402
from workflow_context import WorkflowContext, load_workflow_context  # noqa: E402
from workflow_monitor import emit_behavior_projection  # noqa: E402

OFFICIAL_HOOK_SCHEMA = "agent-canon.posttooluse-stop.v1"
HOOK_CONTRACT_SCHEMA = "agent-canon.hook-contract.v1"
POST_TOOL_USE_INPUT_SCHEMA = "agent-canon-post-tool-use-input/v1"
DISPATCHER_SOURCE_ROOT_ENV = "AGENT_CANON_HOOK_SOURCE_ROOT"
MAX_HOOK_PAYLOAD_BYTES = 256 * 1024


@dataclass(frozen=True)
class HookEventContract:
    """Typed contract for one lifecycle event, including legacy inactive events."""

    active: bool
    matchers: tuple[str, ...]
    failure: str
    telemetry: str


HOOK_EVENT_CONTRACTS: dict[str, HookEventContract] = {
    "UserPromptSubmit": HookEventContract(
        active=True,
        matchers=(),
        failure="secret_match=block; malformed_payload=fail_open; spool_failure=fail_open",
        telemetry="one bounded fingerprint-only local spool event",
    ),
    "PreToolUse": HookEventContract(
        active=True,
        matchers=("Bash|apply_patch|python|python3",),
        failure="unauthorized_destructive_git=block; malformed_payload=fail_open; spool_failure=fail_open",
        telemetry="one bounded fingerprint-only local spool event",
    ),
    "PostToolUse": HookEventContract(
        active=True,
        matchers=("Bash|apply_patch|python|python3|Task|spawn_agent|send_input|wait_agent|close_agent|resume_agent",),
        failure="invalid_projection=fail_open; malformed_payload=fail_open; spool_failure=fail_open",
        telemetry="one bounded fingerprint-only local spool event",
    ),
    "Stop": HookEventContract(
        active=False,
        matchers=(),
        failure="legacy_event_inactive_no_op",
        telemetry="no active hook telemetry",
    ),
}

ACTIVE_HOOK_HANDLERS = frozenset(
    {
        "UserPromptSubmit.secret_safety",
        "PreToolUse.destructive_git_safety",
        "PostToolUse.execution_resource_projection",
    }
)

EVENT_ALIASES = {event.casefold(): event for event in HOOK_EVENT_CONTRACTS} | {
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}


def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def parse_payload(raw_payload: bytes) -> dict[str, object] | None:
    """Parse the bounded lifecycle payload exactly once."""
    if len(raw_payload) > MAX_HOOK_PAYLOAD_BYTES:
        return None
    if not raw_payload.strip():
        return {}
    try:
        loaded = json.loads(
            raw_payload.decode("utf-8"),
            object_pairs_hook=unique_json_object,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    return loaded if isinstance(loaded, dict) else None


def normalize_post_tool_use_input(payload: dict[str, object]) -> dict[str, object]:
    """Build the exact projection-validator input from the one parsed payload."""
    if set(payload) != {"hookEventName", "tool_name", "tool_input", "tool_response"}:
        raise ProjectionError("raw PostToolUse keys are not exact")
    if payload["hookEventName"] != "PostToolUse":
        raise ProjectionError("raw Hook event is not PostToolUse")
    tool_name = payload["tool_name"]
    tool_input = payload["tool_input"]
    tool_response = payload["tool_response"]
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        raise ProjectionError("raw PostToolUse tool fields have invalid types")
    if not isinstance(tool_response, dict) or set(tool_response) != {"exit_code", "stderr", "stdout"}:
        raise ProjectionError("raw PostToolUse response keys are not exact")
    if (
        type(tool_response["exit_code"]) is not int
        or not isinstance(tool_response["stderr"], str)
        or not isinstance(tool_response["stdout"], str)
    ):
        raise ProjectionError("raw PostToolUse response fields have invalid types")
    normalized = {
        "hook_event_name": "PostToolUse",
        "schema_version": POST_TOOL_USE_INPUT_SCHEMA,
        "tool_input_fingerprint": hashlib.sha256(canonical_json_bytes(tool_input)).hexdigest(),
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
    }
    validate_normalized_input(normalized)
    return normalized


def official_payload(event: str, payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    normalized["schema"] = OFFICIAL_HOOK_SCHEMA
    reason = normalized.get("reason") or normalized.get("systemMessage") or ""
    normalized["hookSpecificOutput"] = {
        "hookEventName": event,
        "additionalContext": str(reason),
    }
    return normalized


def projection_payload(stdout: str) -> dict[str, object]:
    return {
        "schema": OFFICIAL_HOOK_SCHEMA,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": stdout,
        },
    }


def root_for_spool() -> Path:
    override = os.environ.get(DISPATCHER_SOURCE_ROOT_ENV, "").strip()
    return Path(override).resolve() if override else SOURCE_ROOT


def spool_event(event: str, raw_payload: bytes, status: str, **telemetry: str) -> tuple[dict[str, object], HookLogContext]:
    """Build one base transport entry; the caller appends it exactly once."""
    timestamp = utc_now()
    payload_fingerprint = hashlib.sha256(raw_payload).hexdigest()
    context = HookLogContext(root_for_spool(), event)
    entry: dict[str, object] = {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "timestamp": timestamp,
        "payload_fingerprint": payload_fingerprint,
        "status": status,
        "hook_event_name": event,
    }
    entry.update({key: value for key, value in telemetry.items() if value})
    return entry, context


def prepare_parts(
    event: str,
    payload: dict[str, object] | None,
    status: str,
    output: dict[str, object] | None,
    entry: dict[str, object],
    root: Path,
) -> HookInvocationParts:
    """Construct typed assembly inputs without writing an artifact."""
    parsed = payload is not None
    safe_payload = payload if parsed else None
    payload_data = payload or {}
    try:
        context = load_workflow_context(root / "skill_usage_context.json")
    except Exception:
        context = WorkflowContext()
    try:
        tools = select_tools(payload_data)
        subagents = select_subagents(payload_data, context)
        rules = PromptClassifierInputs(
            prompt=payload_data.get("prompt", "") if isinstance(payload_data.get("prompt"), str) else "",
            repo_root=root,
            catalog=freeze({}),
            routing_rules=freeze({}),
        )
    except Exception:
        tools = None
        subagents = None
        rules = None
    return HookInvocationParts(
        hook_event_name=event,
        hook_invocation_id=str(entry["hook_run_id"]),
        hook_payload=safe_payload,
        payload_status="parsed" if parsed else "malformed_payload",
        handler_result=FinalHandlerResult(
            status=status,
            output_kind="block" if output else "additional_context" if status == "projection_forwarded" else "",
            safe_fields={"safety_decision": "block"} if status.startswith("blocked_") else {},
        ),
        classifier_rules=rules,
        tool_selection=tools,
        subagent_selection=subagents,
        workflow_context=context,
        payload_fingerprint=str(entry["payload_fingerprint"]),
        timestamp=str(entry["timestamp"]),
        root=root,
        report_dir=root,
    )


def dispatch_event(event: str, raw_payload: bytes) -> int:
    """Dispatch one active event after one bounded parse; legacy Stop is a no-op."""
    if event == "Stop":
        return 0
    payload = parse_payload(raw_payload)
    output: dict[str, object] | None = None
    status = "malformed_payload" if payload is None else "pass"
    telemetry: dict[str, str] = {}
    if payload is not None:
        if event == "UserPromptSubmit":
            matched_kind = secret_kind(payload_prompt(payload))
            if matched_kind is not None:
                output = official_payload(event, secret_block_payload(matched_kind))
                status = "blocked_secret"
                telemetry["safety_decision"] = "block"
        elif event == "PreToolUse":
            if payload_tool_name(payload) in SHELL_TOOL_NAMES:
                command = payload_tool_command(payload)
                intent = first_block(command)
                if intent is not None:
                    safety = branch_block_payload(command, intent)
                    output = official_payload(event, safety)
                    status = "blocked_destructive_git"
                    telemetry["safety_decision"] = "block"
                    telemetry["operation"] = str(safety["operation"])
        elif event == "PostToolUse":
            try:
                normalized = normalize_post_tool_use_input(payload)
                if normalized["tool_name"] == "Bash":
                    response = normalized["tool_response"]
                    assert isinstance(response, dict)
                    if response["exit_code"] == 0:
                        stdout = response["stdout"]
                        assert isinstance(stdout, str)
                        validate_projection_bytes(stdout)
                        output = projection_payload(stdout)
                        status = "projection_forwarded"
                    else:
                        status = "unsuccessful_tool_response"
            except (ProjectionError, TypeError, ValueError, AssertionError):
                status = "invalid_projection"
    root = root_for_spool()
    spool_entry, context = spool_event(event, raw_payload, status, **telemetry)
    behavior = record_hook_invocation(prepare_parts(event, payload, status, output, spool_entry, root))
    if behavior is not None:
        spool_entry.update(behavior.as_dict())
    try:
        append_result = context.append(spool_entry)
    except Exception:
        append_result = None
    if behavior is not None and append_result is not None and getattr(append_result, "status", "") == "spooled":
        try:
            emit_behavior_projection(root, behavior.as_dict())
        except Exception:
            pass
    if output is not None:
        json.dump(output, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    return 0


def normalize_event(raw_event: str) -> str:
    event = EVENT_ALIASES.get(raw_event.casefold())
    if event is None:
        choices = ", ".join(HOOK_EVENT_CONTRACTS)
        raise SystemExit(f"unknown hook event {raw_event!r}; expected one of: {choices}")
    return event


def contract_payload(event: str | None = None) -> dict[str, object]:
    names = [event] if event is not None else list(HOOK_EVENT_CONTRACTS)
    return {
        "schema": HOOK_CONTRACT_SCHEMA,
        "events": {
            name: {
                "active": HOOK_EVENT_CONTRACTS[name].active,
                "matchers": list(HOOK_EVENT_CONTRACTS[name].matchers),
                "failure": HOOK_EVENT_CONTRACTS[name].failure,
                "telemetry": HOOK_EVENT_CONTRACTS[name].telemetry,
            }
            for name in names
        },
        "active_events": [name for name in names if HOOK_EVENT_CONTRACTS[name].active],
        "inactive_events": [name for name in names if not HOOK_EVENT_CONTRACTS[name].active],
        "active_handlers": sorted(ACTIVE_HOOK_HANDLERS),
        "retired_child_tombstones": [
            {
                "filename": row.filename,
                "owner": row.owner,
                "command_or_skill": row.command_or_skill,
                "profile_trigger": row.profile_trigger,
                "decision_semantics": row.decision_semantics,
                "artifact": row.artifact,
            }
            for row in RETIRED_CHILD_TOMBSTONES
        ],
        "moved_source_absences": [
            {
                "filename": row.filename,
                "moved_to": row.moved_to,
                "import_contract": row.import_contract,
                "reason": row.reason,
                "artifact": row.artifact,
            }
            for row in MOVED_SOURCE_ABSENCES
        ],
        "counts": {
            "retired_child_tombstones": len(RETIRED_CHILD_TOMBSTONES),
            "moved_source_absences": len(MOVED_SOURCE_ABSENCES),
            "retired_filenames": len(RETIRED_CHILD_TOMBSTONES) + len(MOVED_SOURCE_ABSENCES),
        },
        "source_digest": source_digest(),
    }


def command_list_payload(event: str | None = None) -> dict[str, object]:
    """Keep --list as a contract-compatible read-only alias."""
    return contract_payload(event)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", nargs="?", help="Codex hook event to dispatch")
    parser.add_argument("--group", dest="group", help="Alias for the event argument")
    parser.add_argument("--list", action="store_true", help="Print the active/inactive hook contract")
    parser.add_argument("--contract", action="store_true", help="Print the canonical typed hook contract")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    raw_event = args.group or args.event
    if args.list or args.contract:
        event = normalize_event(raw_event) if raw_event else None
        json.dump(contract_payload(event), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if not raw_event:
        raise SystemExit("hook event is required")
    return dispatch_event(normalize_event(raw_event), sys.stdin.buffer.read())


if __name__ == "__main__":
    raise SystemExit(main())
