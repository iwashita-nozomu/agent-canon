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
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
EXCLUDED_PARTS = {".git", "__pycache__", "reports", ".pytest_cache", ".ruff_cache"}
EDIT_TOOL_NAMES = {"apply_patch", "Bash", "bash", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+--fix|python3?\s+-m\s+ruff\s+.*--fix|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)


@dataclass(frozen=True)
class AnalyzerResult:
    """One analyzer run result."""

    command: tuple[str, ...]
    returncode: int
    output: str


def load_payload() -> dict[str, object]:
    """Read the Codex hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def repo_root() -> Path:
    """Resolve the active repository root for hook checks."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) else ""


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name from one hook payload."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


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
        timeout=10,
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


def run_analyzer(root: Path, analyzer: Path, paths: list[Path]) -> AnalyzerResult | None:
    """Run one OOP analyzer for changed files."""
    if not analyzer.is_file() or not paths:
        return None
    relative_paths = [path.relative_to(root).as_posix() for path in paths]
    command = (
        "python3",
        str(analyzer),
        "--root",
        str(root),
        "--min-score",
        "85",
        *relative_paths,
    )
    result = subprocess.run(
        list(command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return AnalyzerResult(
        command=command,
        returncode=result.returncode,
        output=(result.stdout + result.stderr).strip(),
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
    for result in failed[:3]:
        first_lines = "\n".join(result.output.splitlines()[:12])
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


def main() -> int:
    """Block source-editing continuations when changed source files fail OOP checks."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    results = run_oop_checks(repo_root())
    if any(result.returncode != 0 for result in results):
        emit_block(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
