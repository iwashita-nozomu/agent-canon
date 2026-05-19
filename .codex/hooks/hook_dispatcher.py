#!/usr/bin/env python3
# @dependency-start
# responsibility Dispatches Codex lifecycle hook events to the configured guard scripts.
# upstream implementation ../hooks.json invokes this dispatcher once per active hook event.
# upstream design ../README.md documents dispatcher-based hook wiring.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates dispatch order and hook count.
# @dependency-end

"""Run the configured child hooks for one Codex lifecycle event."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DISPATCHER_DIR_ENV = "AGENT_CANON_HOOK_DISPATCHER_DIR"
GIT_ROOT_TIMEOUT_SECONDS = 5
MAX_REASON_LINES = 20


@dataclass(frozen=True)
class HookCommandSpec:
    """One child hook command and its legacy timeout."""

    script: str
    timeout: int


@dataclass(frozen=True)
class HookResult:
    """Captured result from one child hook command."""

    spec: HookCommandSpec
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def json_stdout(self) -> dict[str, object] | None:
        """Return parsed JSON stdout when the child emitted a hook payload."""
        text = self.stdout.strip()
        if not text:
            return None
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def blocks(self) -> bool:
        """Return whether this result is a Codex blocking hook payload."""
        payload = self.json_stdout()
        return payload is not None and payload.get("decision") == "block"

    def visible(self) -> bool:
        """Return whether this child emitted output Codex should see."""
        return bool(self.stdout.strip())

    def failed(self) -> bool:
        """Return whether the child command failed outside normal hook output."""
        return self.returncode != 0 or self.timed_out


EVENT_COMMANDS: dict[str, tuple[HookCommandSpec, ...]] = {
    "UserPromptSubmit": (
        HookCommandSpec("prompt_secret_guard.py", 10),
        HookCommandSpec("skill_usage_logger.py", 10),
        HookCommandSpec("reference_capture_guard.py", 10),
    ),
    "PreToolUse": (
        HookCommandSpec("cause_investigation_guard.py", 30),
    ),
    "PostToolUse": (
        HookCommandSpec("skill_usage_logger.py", 10),
        HookCommandSpec("reference_capture_guard.py", 15),
        HookCommandSpec("oop_readability_guard.py", 60),
        HookCommandSpec("module_boundary_guard.py", 60),
        HookCommandSpec("library_implementation_guard.py", 60),
        HookCommandSpec("helper_inventory_guard.py", 60),
        HookCommandSpec("helper_first_guard.py", 60),
        HookCommandSpec("style_checker_guard.py", 90),
        HookCommandSpec("log_surface_inventory_guard.py", 60),
        HookCommandSpec("notebook_quality_guard.py", 60),
    ),
    "Stop": (
        HookCommandSpec("goal_completion_guard.py", 15),
        HookCommandSpec("oop_readability_guard.py", 60),
        HookCommandSpec("module_boundary_guard.py", 60),
        HookCommandSpec("library_implementation_guard.py", 60),
        HookCommandSpec("helper_inventory_guard.py", 60),
        HookCommandSpec("helper_first_guard.py", 60),
        HookCommandSpec("style_checker_guard.py", 90),
        HookCommandSpec("log_surface_inventory_guard.py", 60),
        HookCommandSpec("notebook_quality_guard.py", 60),
        HookCommandSpec("reference_capture_guard.py", 15),
        HookCommandSpec("skill_usage_logger.py", 10),
    ),
}

EVENT_ALIASES = {
    event.casefold(): event
    for event in EVENT_COMMANDS
} | {
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
}


def load_raw_payload() -> bytes:
    """Read the hook payload once so every child receives identical stdin."""
    return sys.stdin.buffer.read()


def repo_root() -> Path:
    """Return the active repository root for child hook execution."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_directory() -> Path:
    """Return the directory containing child hook scripts."""
    override = os.environ.get(DISPATCHER_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent


def normalize_event(raw_event: str) -> str:
    """Return the canonical lifecycle event name."""
    event = EVENT_ALIASES.get(raw_event.casefold())
    if event:
        return event
    choices = ", ".join(EVENT_COMMANDS)
    raise SystemExit(f"unknown hook event {raw_event!r}; expected one of: {choices}")


def run_hook_command(
    spec: HookCommandSpec,
    *,
    raw_payload: bytes,
    root: Path,
    hooks_dir: Path,
) -> HookResult:
    """Run one child hook script with the original payload."""
    script = hooks_dir / spec.script
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            input=raw_payload,
            cwd=root,
            check=False,
            capture_output=True,
            timeout=spec.timeout,
        )
    except OSError as exc:
        return HookResult(
            spec=spec,
            returncode=127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = bytes(exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = bytes(exc.stderr or b"").decode("utf-8", errors="replace")
        timeout_message = f"{spec.script} timed out after {spec.timeout} seconds"
        return HookResult(
            spec=spec,
            returncode=124,
            stdout=stdout,
            stderr="\n".join(part for part in (stderr, timeout_message) if part),
            timed_out=True,
        )
    return HookResult(
        spec=spec,
        returncode=result.returncode,
        stdout=result.stdout.decode("utf-8", errors="replace"),
        stderr=result.stderr.decode("utf-8", errors="replace"),
    )


def failure_payload(result: HookResult) -> dict[str, object]:
    """Return a blocking payload for child process failures."""
    detail_lines = [
        line
        for text in (result.stderr, result.stdout)
        for line in text.splitlines()
        if line.strip()
    ][:MAX_REASON_LINES]
    detail = "\n".join(detail_lines)
    return {
        "decision": "block",
        "reason": (
            "Hook dispatcher child command failed. Fix the child hook or rerun "
            f"the original hook directly.\n{result.spec.script}\n{detail}"
        ).strip(),
        "next_action": "fix_child_hook_failure_then_retry",
        "remediation": [
            f"Run `.codex/hooks/{result.spec.script}` directly with the same payload.",
            "Fix the child hook failure before continuing the tool action.",
        ],
    }


def non_block_payload(result: HookResult) -> dict[str, object] | None:
    """Return a non-blocking JSON payload emitted by a child hook."""
    payload = result.json_stdout()
    if payload is None or payload.get("decision") == "block":
        return None
    return payload


def visible_output_payload(results: list[HookResult]) -> dict[str, object] | None:
    """Combine non-blocking child outputs into one visible approve payload."""
    visible_results = [result for result in results if result.visible()]
    if not visible_results:
        return None
    payloads = [
        payload
        for result in visible_results
        if (payload := non_block_payload(result)) is not None
    ]
    text_outputs = [
        result.stdout.strip()
        for result in visible_results
        if non_block_payload(result) is None and result.stdout.strip()
    ]
    if len(visible_results) == 1 and not text_outputs:
        return payloads[0] if payloads else None

    reason_parts: list[str] = []
    remediation: list[str] = []
    for payload in payloads:
        reason = payload.get("reason")
        if isinstance(reason, str) and reason.strip():
            reason_parts.append(reason.strip())
        raw_remediation = payload.get("remediation")
        if isinstance(raw_remediation, list):
            remediation.extend(str(item) for item in raw_remediation)
    reason_parts.extend(text_outputs)
    combined: dict[str, object] = {
        "decision": "approve",
        "reason": "\n\n".join(reason_parts),
        "child_output_count": len(visible_results),
        "child_outputs": [
            {
                "script": result.spec.script,
                "stdout": result.stdout.strip(),
            }
            for result in visible_results
        ],
    }
    next_action = next(
        (
            payload.get("next_action")
            for payload in payloads
            if isinstance(payload.get("next_action"), str)
        ),
        None,
    )
    if next_action is not None:
        combined["next_action"] = next_action
    if remediation:
        combined["remediation"] = remediation
    return combined


def emit_json_payload(payload: dict[str, object]) -> None:
    """Write one JSON hook payload."""
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def dispatch_event(event: str, raw_payload: bytes) -> int:
    """Run every child hook for one event and emit the highest-priority output."""
    root = repo_root()
    hooks_dir = hook_directory()
    results = [
        run_hook_command(spec, raw_payload=raw_payload, root=root, hooks_dir=hooks_dir)
        for spec in EVENT_COMMANDS[event]
    ]
    blocking = next((result for result in results if result.blocks()), None)
    failure = next((result for result in results if result.failed()), None)
    visible_payload = visible_output_payload(results)

    if blocking is not None:
        sys.stdout.write(blocking.stdout)
        if not blocking.stdout.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    if failure is not None:
        emit_json_payload(failure_payload(failure))
        return 0
    if visible_payload is not None:
        emit_json_payload(visible_payload)
    return 0


def command_list_payload(event: str | None) -> dict[str, object]:
    """Return a JSON-visible dispatch matrix for tests and reviews."""
    events = [event] if event is not None else list(EVENT_COMMANDS)
    return {
        "events": {
            name: [
                {"script": spec.script, "timeout": spec.timeout}
                for spec in EVENT_COMMANDS[name]
            ]
            for name in events
        },
        "event_count": len(events),
        "command_count": sum(len(EVENT_COMMANDS[name]) for name in events),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse dispatcher command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", nargs="?", help="Codex hook event to dispatch")
    parser.add_argument("--group", dest="group", help="Alias for the event argument")
    parser.add_argument("--list", action="store_true", help="Print the child hook matrix")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    raw_event = args.group or args.event
    if args.list:
        event = normalize_event(raw_event) if raw_event else None
        json.dump(command_list_payload(event), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    if not raw_event:
        raise SystemExit("hook event is required")
    event = normalize_event(raw_event)
    return dispatch_event(event, load_raw_payload())


if __name__ == "__main__":
    raise SystemExit(main())
