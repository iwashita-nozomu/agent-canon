#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates and forwards the exact R5 PostToolUse projection only.
# upstream design ../../documents/gpu-admission-r5-source-packet.md U-14/U-15 projection consumer contract and composition graph
# downstream implementation hook_dispatcher.py PostToolUse child registration and selective forwarding
# @dependency-end

"""Validate one canonical PostToolUse projection without becoming an authority."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any

OFFICIAL_HOOK_SCHEMA = "agent-canon.posttooluse-stop.v1"
PROJECTION_KEYS = {
    "admission",
    "completion_coverage_path",
    "error",
    "exit_code",
    "plan_fingerprint",
    "plan_path",
    "projection",
    "run_id",
    "schema_version",
}
NORMALIZED_INPUT_KEYS = {
    "hook_event_name",
    "schema_version",
    "tool_input_fingerprint",
    "tool_name",
    "tool_input",
    "tool_response",
}
NORMALIZED_INPUT_SCHEMA = "agent-canon-post-tool-use-input/v1"
ADMISSION_KEYS = {
    "admission_fingerprint",
    "guarantee",
    "namespace_id",
    "provision_receipt_fingerprint",
    "selected_uuids",
}
ERROR_KEYS = {"kind", "message", "operation"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
UUID_RE = re.compile(r"^(?:GPU|MIG)-[A-Za-z0-9-]+$")


class ProjectionError(ValueError):
    """Raised when raw Hook input or projection bytes violate the contract."""


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ProjectionError(f"non-finite JSON constant: {value}")


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def require_sha256(value: object, field: str) -> None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ProjectionError(f"{field} is not a lowercase SHA-256 fingerprint")


def validate_normalized_input(payload: dict[str, Any]) -> None:
    """Validate the exact dispatcher-owned six-field PostToolUse input."""
    if set(payload) != NORMALIZED_INPUT_KEYS:
        raise ProjectionError("normalized PostToolUse fields are not exact")
    if payload["hook_event_name"] != "PostToolUse":
        raise ProjectionError("normalized Hook event is not PostToolUse")
    if payload["schema_version"] != NORMALIZED_INPUT_SCHEMA:
        raise ProjectionError("normalized Hook schema_version is not exact")
    if not isinstance(payload["tool_name"], str):
        raise ProjectionError("normalized tool_name is not a string")
    tool_input = payload["tool_input"]
    if not isinstance(tool_input, dict):
        raise ProjectionError("normalized tool_input is not an object")
    require_sha256(payload["tool_input_fingerprint"], "tool_input_fingerprint")
    expected_fingerprint = hashlib.sha256(
        canonical_bytes(tool_input)
    ).hexdigest()
    if payload["tool_input_fingerprint"] != expected_fingerprint:
        raise ProjectionError("tool_input_fingerprint does not match tool_input")
    tool_response = payload["tool_response"]
    if not isinstance(tool_response, dict) or set(tool_response) != {
        "exit_code",
        "stderr",
        "stdout",
    }:
        raise ProjectionError("normalized tool_response fields are not exact")
    if (
        isinstance(tool_response["exit_code"], bool)
        or not isinstance(tool_response["exit_code"], int)
        or not isinstance(tool_response["stderr"], str)
        or not isinstance(tool_response["stdout"], str)
    ):
        raise ProjectionError("normalized tool_response field types are invalid")


def validate_admission(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != ADMISSION_KEYS:
        raise ProjectionError("admission fields are not exact")
    require_sha256(value["admission_fingerprint"], "admission_fingerprint")
    require_sha256(value["provision_receipt_fingerprint"], "provision_receipt_fingerprint")
    if not isinstance(value["guarantee"], str) or not value["guarantee"]:
        raise ProjectionError("admission guarantee is not a non-empty string")
    if not isinstance(value["namespace_id"], str) or not value["namespace_id"]:
        raise ProjectionError("admission namespace_id is not a non-empty string")
    selected = value["selected_uuids"]
    if not isinstance(selected, list) or any(
        not isinstance(item, str) or UUID_RE.fullmatch(item) is None for item in selected
    ):
        raise ProjectionError("admission selected_uuids are not opaque UUIDs")


def validate_error(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != ERROR_KEYS:
        raise ProjectionError("error fields are not exact")
    if any(not isinstance(value[field], str) for field in ERROR_KEYS):
        raise ProjectionError("error fields must be strings")


def validate_projection_bytes(stdout: str) -> dict[str, Any]:
    if not stdout.endswith("\n") or stdout.count("\n") != 1 or "\r" in stdout:
        raise ProjectionError("projection must be exactly one LF-terminated line")
    line = stdout[:-1]
    if not line:
        raise ProjectionError("projection line is empty")
    projection = json.loads(
        line,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(projection, dict) or set(projection) != PROJECTION_KEYS:
        raise ProjectionError("projection fields are not the exact nine-key set")
    if projection["schema_version"] != "execution-resource-plan/v1":
        raise ProjectionError("projection schema_version is not execution-resource-plan/v1")
    if projection["projection"] != "post_tool_use":
        raise ProjectionError("projection kind is not post_tool_use")
    run_id = projection["run_id"]
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        raise ProjectionError("projection run_id is not safe")
    expected_runtime = f"reports/agents/{run_id}/runtime"
    if projection["plan_path"] != f"{expected_runtime}/execution_resource_plan.json":
        raise ProjectionError("projection plan_path is not canonical")
    if projection["completion_coverage_path"] != f"{expected_runtime}/completion_coverage.json":
        raise ProjectionError("projection completion_coverage_path is not canonical")
    if type(projection["exit_code"]) is not int:
        raise ProjectionError("projection exit_code is not an integer")
    require_sha256(projection["plan_fingerprint"], "plan_fingerprint")
    validate_admission(projection["admission"])
    validate_error(projection["error"])
    canonical = canonical_bytes(projection) + b"\n"
    if canonical != stdout.encode("utf-8"):
        raise ProjectionError("projection bytes are not canonical")
    return projection


def reject(reason: str) -> int:
    print(f"execution_resource_plan_projection_guard: {reason}", file=sys.stderr)
    return 0


def main() -> int:
    try:
        raw = sys.stdin.buffer.read()
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
        if not isinstance(payload, dict):
            raise ProjectionError("Hook input is not an object")
        validate_normalized_input(payload)
        event = payload["hook_event_name"]
        if event != "PostToolUse":
            return reject("unrelated event")
        if payload["tool_name"] != "Bash":
            return reject("unrelated tool")
        tool_response = payload["tool_response"]
        assert isinstance(tool_response, dict)
        if type(tool_response.get("exit_code")) is not int or tool_response["exit_code"] != 0:
            return reject("tool response is not successful")
        stdout = tool_response.get("stdout")
        if not isinstance(stdout, str):
            raise ProjectionError("tool_response.stdout is not a string")
        validate_projection_bytes(stdout)
    except (ProjectionError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        return reject(str(exc))
    wrapper = {
        "schema": OFFICIAL_HOOK_SCHEMA,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": stdout,
        },
    }
    json.dump(wrapper, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
