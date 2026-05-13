#!/usr/bin/env python3
# @dependency-start
# responsibility Runs OOP readability hook checks after source-editing tool calls.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ../../tools/oop/python/readability.py checks Python OOP readability.
# upstream implementation ../../tools/oop/cpp/readability.py checks C++ OOP readability.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard output.
# @dependency-end

"""Block progression when changed source files still fail OOP readability checks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
EXCLUDED_PARTS = {".git", "__pycache__", "reports", ".pytest_cache", ".ruff_cache"}
EDIT_TOOL_NAMES = {"apply_patch", "Bash", "bash", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+--fix|python3?\s+-m\s+ruff\s+.*--fix|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
PAYLOADLESS_FALLBACK_EVENT = "PostToolUse"
PAYLOADLESS_FALLBACK_TOOL = "Bash"
LOG_PATH_ENV = "AGENT_CANON_OOP_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
GIT_ROOT_TIMEOUT_SECONDS = 5
GIT_CHANGED_PATHS_TIMEOUT_SECONDS = 10
ANALYZER_TIMEOUT_SECONDS = 30
MAX_BLOCKED_ANALYZER_SNIPPETS = 3
MAX_ANALYZER_OUTPUT_LINES = 12


@dataclass(frozen=True)
class AnalyzerResult:
    """One analyzer run result."""

    command: tuple[str, ...]
    returncode: int
    output: str
    min_score: int | None


def load_payload() -> dict[str, object]:
    """Read the Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_EMPTY}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}
    if isinstance(loaded, dict):
        loaded[PAYLOAD_STATUS_KEY] = PAYLOAD_STATUS_VALID
        return loaded
    return {PAYLOAD_STATUS_KEY: PAYLOAD_STATUS_INVALID_JSON}


def payload_status(payload: dict[str, object]) -> str:
    """Return how the hook payload was obtained."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def has_tool_signal(payload: dict[str, object]) -> bool:
    """Return whether one payload looks like a tool hook without an event name."""
    return isinstance(payload.get("tool_name"), str) or bool(tool_command(payload))


def uses_event_fallback(payload: dict[str, object]) -> bool:
    """Return whether the hook should infer a post-tool event name."""
    if isinstance(payload.get("hookEventName"), str):
        return False
    status = payload_status(payload)
    return status == PAYLOAD_STATUS_EMPTY or (
        status == PAYLOAD_STATUS_VALID and has_tool_signal(payload)
    )


def repo_root() -> Path:
    """Resolve the active repository root for hook checks."""
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


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the hook event name."""
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    if uses_event_fallback(payload):
        return PAYLOADLESS_FALLBACK_EVENT
    return ""


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name from one hook payload."""
    value = payload.get("tool_name")
    if isinstance(value, str):
        return value
    if payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return PAYLOADLESS_FALLBACK_TOOL
    return ""


def tool_command(payload: dict[str, object]) -> str:
    """Return a command-like string from one hook payload."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str):
            return command
    for key in ("command", "cmd"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def git_lines(root: Path, args: list[str]) -> list[str]:
    """Return non-empty git output lines for one repo."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_paths(root: Path) -> list[Path]:
    """Return tracked and untracked changed paths for one git repository."""
    names: set[str] = set()
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        names.update(git_lines(root, args))
    return sorted(root / name for name in names)


def is_source_path(path: Path, suffixes: set[str]) -> bool:
    """Return whether one path should be analyzed."""
    if path.suffix not in suffixes:
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    return path.is_file()


def source_paths(root: Path, suffixes: set[str]) -> list[Path]:
    """Return changed source files for one repository."""
    return [path for path in changed_paths(root) if is_source_path(path, suffixes)]


def default_oop_min_score(root: Path) -> int | None:
    """Return the analyzer-owned default min score."""
    candidate_roots = (Path(__file__).resolve().parents[2], root)
    for candidate in candidate_roots:
        sys.path.insert(0, str(candidate))
        try:
            from tools.oop.shared.readability_core import DEFAULT_MIN_SCORE

            return int(DEFAULT_MIN_SCORE)
        except (ImportError, ValueError, TypeError):
            continue
        finally:
            try:
                sys.path.remove(str(candidate))
            except ValueError:
                pass
    return None


def run_analyzer(root: Path, analyzer: Path, paths: list[Path]) -> AnalyzerResult | None:
    """Run one OOP analyzer for changed files."""
    if not analyzer.is_file() or not paths:
        return None
    relative_paths = [path.relative_to(root).as_posix() for path in paths]
    min_score = default_oop_min_score(root)
    command_parts = [
        "python3",
        str(analyzer),
        "--root",
        str(root),
    ]
    if min_score is not None:
        command_parts.extend(("--min-score", str(min_score)))
    command_parts.extend(relative_paths)
    command = tuple(command_parts)
    result = subprocess.run(
        list(command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=ANALYZER_TIMEOUT_SECONDS,
    )
    return AnalyzerResult(
        command=command,
        returncode=result.returncode,
        output=(result.stdout + result.stderr).strip(),
        min_score=min_score,
    )


def candidate_roots(root: Path) -> list[Path]:
    """Return root and AgentCanon submodule roots to inspect."""
    roots = [root]
    submodule = root / "vendor" / "agent-canon"
    if (submodule / ".git").exists():
        roots.append(submodule)
    return roots


def run_oop_checks(root: Path) -> list[AnalyzerResult]:
    """Run applicable OOP checks for changed Python and C++ files."""
    results: list[AnalyzerResult] = []
    for candidate in candidate_roots(root):
        python_result = run_analyzer(
            candidate,
            candidate / "tools" / "oop" / "python" / "readability.py",
            source_paths(candidate, PYTHON_SUFFIXES),
        )
        cpp_result = run_analyzer(
            candidate,
            candidate / "tools" / "oop" / "cpp" / "readability.py",
            source_paths(candidate, CPP_SUFFIXES),
        )
        for result in (python_result, cpp_result):
            if result is not None:
                results.append(result)
    return results


def should_check(payload: dict[str, object]) -> bool:
    """Return whether the hook payload should trigger OOP checks."""
    if uses_event_fallback(payload) and not has_tool_signal(payload):
        return True
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    name = tool_name(payload)
    command = tool_command(payload)
    return name in EDIT_TOOL_NAMES or bool(EDIT_COMMAND_PATTERN.search(command))


def emit_block(results: list[AnalyzerResult]) -> None:
    """Emit a blocking hook result with OOP remediation details."""
    failed = [result for result in results if result.returncode != 0]
    snippets = []
    for result in failed[:MAX_BLOCKED_ANALYZER_SNIPPETS]:
        first_lines = "\n".join(result.output.splitlines()[:MAX_ANALYZER_OUTPUT_LINES])
        snippets.append(f"$ {' '.join(result.command)}\n{first_lines}")
    json.dump(
        {
            "decision": "block",
            "reason": (
                "OOP readability hook found changed source files that need immediate repair. "
                "Run the listed checker(s), fix the implementation or adjust the approved "
                "OOP boundary before continuing.\n\n"
                + "\n\n".join(snippets)
            )
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def utc_now() -> str:
    """Return a compact UTC timestamp for hook logs."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_log_path(root: Path) -> Path:
    """Return the default local hook log path."""
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return root / "reports" / "hooks" / "oop_readability_guard.jsonl"


def analyzer_log_payload(
    payload: dict[str, object],
    root: Path,
    *,
    checked: bool,
    results: list[AnalyzerResult],
) -> dict[str, object]:
    """Build one OOP hook invocation log payload."""
    failed = [result for result in results if result.returncode != 0]
    min_score = next((result.min_score for result in results if result.min_score is not None), None)
    return {
        "timestamp": utc_now(),
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fallback": payload_status(payload) == PAYLOAD_STATUS_EMPTY,
        "event_fallback": uses_event_fallback(payload),
        "checked": checked,
        "min_score": min_score,
        "result_count": len(results),
        "failed_count": len(failed),
        "status": "fail" if failed else "pass",
        "root": str(root),
        "commands": [
            {
                "command": list(result.command),
                "returncode": result.returncode,
            }
            for result in results
        ],
    }


def _log_append_hook_log(root: Path, entry: dict[str, object]) -> None:
    """Append one JSONL hook log entry without blocking the hook on logging errors."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    try:
        path = default_log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True)
            stream.write("\n")
    except OSError:
        return


def main() -> int:
    """Block source-editing continuations when changed source files fail OOP checks."""
    payload = load_payload()
    root = repo_root()
    checked = should_check(payload)
    if not checked:
        _log_append_hook_log(
            root,
            analyzer_log_payload(payload, root, checked=False, results=[]),
        )
        return 0
    results = run_oop_checks(root)
    _log_append_hook_log(
        root,
        analyzer_log_payload(payload, root, checked=True, results=results),
    )
    if any(result.returncode != 0 for result in results):
        emit_block(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
