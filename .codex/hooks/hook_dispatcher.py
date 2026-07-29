#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Dispatches the bounded active hook contract in-process without child processes, Git, or network access.
# upstream implementation ../hooks.json invokes this dispatcher once per active event.
# upstream implementation ./hook_safety.py owns pure secret and destructive Git safety leaves.
# upstream implementation ./execution_resource_plan_projection_guard.py validates producer projection bytes.
# upstream implementation ./hook_event_log.py provides one bounded local spool context per event.
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
from dataclasses import asdict, dataclass
from pathlib import Path

from execution_resource_plan_projection_guard import (  # noqa: E402
    ProjectionError,
    validate_normalized_input,
    validate_projection_bytes,
)
from hook_event_log import HookLogContext, utc_now  # noqa: E402
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

FORMER_ACTIVE_HOOK_CHILDREN = frozenset(
    {
        "log_archive_mount_warning.py",
        "prompt_secret_guard.py",
        "skill_usage_logger.py",
        "reference_capture_guard.py",
        "branch_worktree_guard.py",
        "direct_rg_context_guard.py",
        "cause_investigation_guard.py",
        "task_authority_schema_guard.py",
        "execution_resource_plan_projection_guard.py",
        "role_write_policy_guard.py",
        "oop_readability_guard.py",
        "module_boundary_guard.py",
        "library_implementation_guard.py",
        "first_party_library_guard.py",
        "helper_inventory_guard.py",
        "helper_first_guard.py",
        "style_checker_guard.py",
        "log_surface_inventory_guard.py",
        "notebook_quality_guard.py",
        "completion_review_guard.py",
        "goal_completion_guard.py",
        "codex_runtime_summary_logger.py",
        "runtime_log_auto_sync.py",
    }
)


@dataclass(frozen=True)
class RetiredHookRoute:
    """Explicit owner and migration route for one former child hook."""

    owner: str
    command_or_skill: str
    profile_trigger: str
    decision_semantics: str
    artifact: str


RETIRED_HOOK_ROUTES: dict[str, RetiredHookRoute] = {
    "log_archive_mount_warning.py": RetiredHookRoute("runtime-log-archive owner", "python3 tools/agent_tools/runtime_log_archive_git.py ensure", "explicit archive checkpoint", "fail-open mount preparation warning", "runtime log archive checkpoint evidence"),
    "prompt_secret_guard.py": RetiredHookRoute("hook_safety.py", "python3 .codex/hooks/prompt_secret_guard.py", "UserPromptSubmit compatibility invocation", "standalone wrapper delegates pure secret block", "hook safety decision"),
    "skill_usage_logger.py": RetiredHookRoute("workflow_monitor.py", "python3 tools/agent_tools/workflow_monitor.py --behavior-event", "explicit workflow monitoring", "route observation, not hook blocking", "behavior-event record"),
    "reference_capture_guard.py": RetiredHookRoute("reference_materializer.py", "python3 tools/agent_tools/reference_materializer.py", "literature-survey or reference capture", "reference registration belongs to source materialization", "references/ materialized artifact"),
    "branch_worktree_guard.py": RetiredHookRoute("hook_safety.py", "python3 .codex/hooks/branch_worktree_guard.py", "PreToolUse compatibility invocation", "standalone wrapper delegates pure destructive Git block", "redacted safety payload"),
    "direct_rg_context_guard.py": RetiredHookRoute("task-routing", "$task-routing", "pre-edit repository investigation", "warning is owned by context construction", "Pre-Edit Repository Investigation Packet"),
    "cause_investigation_guard.py": RetiredHookRoute("dependency-analysis", "$dependency-analysis", "hypothesis-validation workflow", "cause evidence is implementation intake, not a hook stop", "cause investigation note"),
    "task_authority_schema_guard.py": RetiredHookRoute("task_authority.py", "python3 tools/agent_tools/task_authority.py", "implementation handoff", "authority schema is validated at the write route", "task authority packet"),
    "execution_resource_plan_projection_guard.py": RetiredHookRoute("hook_dispatcher.py", "python3 .codex/hooks/execution_resource_plan_projection_guard.py", "explicit projection validation", "standalone wrapper validates bytes; active dispatch calls it in-process", "validated execution-resource projection"),
    "role_write_policy_guard.py": RetiredHookRoute("agent_team.py", "python3 tools/agent_tools/agent_team.py", "write-capable handoff", "write scope is enforced at handoff and closeout", "write-scope manifest"),
    "oop_readability_guard.py": RetiredHookRoute("oop-readability-check", "python3 tools/oop/python/readability.py", "explicit OOP review", "review signal is non-blocking evidence", "OOP readability report"),
    "module_boundary_guard.py": RetiredHookRoute("import_responsibility.py", "python3 tools/agent_tools/import_responsibility.py", "dependency boundary review", "import ownership is checked by the owner tool", "import responsibility report"),
    "library_implementation_guard.py": RetiredHookRoute("dependency-module-change", "$dependency-module-change", "dependency source change", "library edits use the dependency source route", "dependency source packet"),
    "first_party_library_guard.py": RetiredHookRoute("task_authority.py", "python3 tools/agent_tools/task_authority.py", "first-party surface change", "public reusable surface authority is explicit", "authority evidence"),
    "helper_inventory_guard.py": RetiredHookRoute("helper inventory tool", "python3 tools/agent_tools/helper_function_inventory.py", "helper inventory review", "inventory findings are review evidence", "helper inventory report"),
    "helper_first_guard.py": RetiredHookRoute("owner-bounded-routing", "python3 tools/agent_tools/responsibility_scope.py --root .", "owner boundary selection", "helper placement follows responsibility evidence", "responsibility-scope evidence"),
    "style_checker_guard.py": RetiredHookRoute("md-style-check", "tools/bin/agent-canon docs check", "changed Markdown or docs", "style is a targeted validation result", "docs check result"),
    "log_surface_inventory_guard.py": RetiredHookRoute("log-surface inventory", "python3 tools/agent_tools/log_surface_inventory.py", "log field contract change", "telemetry fields are reviewed at the surface owner", "log-surface inventory"),
    "notebook_quality_guard.py": RetiredHookRoute("experiment-review", "python3 tools/validation/notebook_quality.py", "experiment notebook review", "notebook quality is explicit experiment evidence", "notebook quality report"),
    "completion_review_guard.py": RetiredHookRoute("change-review", "python3 tools/agent_tools/review_dispatch.py", "review gate", "review approval is a closeout gate, not an active hook", "change review packet"),
    "goal_completion_guard.py": RetiredHookRoute("codex-goals-workflow", "python3 tools/agent_tools/goal_loop.py status", "goal-driven task", "goal continuation is workflow state", "goal.md / goal-loop status"),
    "codex_runtime_summary_logger.py": RetiredHookRoute("runtime summary exporter", "python3 tools/agent_tools/export_codex_runtime_summary.py", "explicit runtime summary export", "summary is bounded derived evidence", "Codex runtime summary"),
    "runtime_log_auto_sync.py": RetiredHookRoute("runtime-log-archive owner", "python3 tools/agent_tools/runtime_log_archive_git.py sync", "explicit log archive checkpoint", "archive sync is administrative and fail-open outside hooks", "hook archive checkpoint"),
}

if set(RETIRED_HOOK_ROUTES) != FORMER_ACTIVE_HOOK_CHILDREN:
    raise RuntimeError("retired hook route table must cover each former child exactly once")
if set(RETIRED_HOOK_ROUTES).intersection(ACTIVE_HOOK_HANDLERS):
    raise RuntimeError("active and retired hook route sets must be disjoint")

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
    return Path(override).resolve() if override else Path.cwd().resolve()


def spool_event(event: str, raw_payload: bytes, status: str, **telemetry: str) -> None:
    """Write one bounded fingerprint-only event; telemetry never changes safety."""
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
    try:
        context.append(entry)
    except Exception:
        # Local spool transport is deliberately fail-open and cannot alter the decision.
        return


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
    spool_event(event, raw_payload, status, **telemetry)
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
        "retired_hook_routes": {
            name: asdict(route) for name, route in sorted(RETIRED_HOOK_ROUTES.items())
        },
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
