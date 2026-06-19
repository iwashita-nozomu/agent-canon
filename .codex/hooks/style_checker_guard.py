#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Runs changed-file style checks after editing tool calls and logs unchecked edits.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/ci/run_all_checks.sh runs Python ruff style checks.
# upstream implementation ../../rust/agent-canon/src/docs.rs checks Markdown style and math notation.
# upstream implementation ../../codex-cli-guide/tools/validate_split.py checks generated Codex guide split coherence.
# upstream implementation ../../tools/oop/cpp/readability.py checks C++ readability style.
# upstream implementation ../../tools/validation/notebook_quality.py checks notebook quality.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates style hook behavior.
# @dependency-end
"""Run automatic style checks for changed files and log uncovered edits."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+-m\s+ruff\s+.*--fix|ruff\s+.*--fix|"
    r"python3?\s+(?:-c\b|-(?:\s|$)|<<)|jupyter\s+nbconvert|"
    r"papermill|git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
CHECKER_COMMAND_RE = re.compile(
    r"(?is)(style_checker_guard\.py|agent-canon docs check|"
    r"tools/validation/notebook_quality\.py|notebook_quality(?:_guard)?\.py|"
    r"tools/oop/python/readability\.py|tools/oop/cpp/readability\.py|"
    r"python3?\s+-m\s+ruff\s+(?:check|format)|ruff\s+(?:check|format))"
)
GIT_TIMEOUT_SECONDS = 10
CHECK_TIMEOUT_SECONDS = 90
MAX_OUTPUT_LINES = 10
PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
NOTEBOOK_SUFFIXES = {".ipynb"}
MARKDOWN_SUFFIXES = {".md"}
EXCLUDED_PARTS = {".git", "__pycache__", "reports", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".jsonl"}
EXCLUDED_PREFIXES = (
    ("agents", "evals", "results"),
)
CODEX_CLI_GUIDE_GENERATED_PREFIXES = (
    ("codex-cli-guide", "sections"),
    ("codex-cli-guide", "source"),
)


@dataclass(frozen=True)
class StyleCommand:
    """One style checker command selected for changed files."""

    checker: str
    family: str
    command: tuple[str, ...]
    paths: tuple[str, ...]


@dataclass(frozen=True)
class StyleResult:
    """One executed style checker result."""

    checker: str
    family: str
    command: tuple[str, ...]
    paths: tuple[str, ...]
    returncode: int
    output: str

    def as_log_entry(self) -> dict[str, object]:
        """Return a JSON-friendly result payload."""
        return {
            "checker": self.checker,
            "family": self.family,
            "command": list(self.command),
            "paths": list(self.paths),
            "returncode": self.returncode,
            "output_snippet": "\n".join(self.output.splitlines()[:MAX_OUTPUT_LINES]),
        }


@dataclass(frozen=True)
class RootStylePlan:
    """Changed-file style check plan for one Git root."""

    root: Path
    changed_files: tuple[str, ...]
    commands: tuple[StyleCommand, ...]
    unchecked_files: tuple[str, ...]

    def checked_files(self) -> tuple[str, ...]:
        """Return paths covered by at least one selected checker."""
        covered: set[str] = set()
        for command in self.commands:
            covered.update(command.paths)
        return tuple(sorted(covered))


def load_payload() -> dict[str, object]:
    """Read one Codex hook payload from stdin."""
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
    """Return how the hook payload was read."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


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


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the declared hook event name."""
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    return ""


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name from one hook payload."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this invocation should inspect changed-file style."""
    if payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return False
    command = tool_command(payload)
    if CHECKER_COMMAND_RE.search(command):
        return False
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    if event != "PostToolUse":
        return False
    return tool_name(payload) in EDIT_TOOL_NAMES or bool(
        EDIT_COMMAND_PATTERN.search(command)
    )


def repo_root() -> Path:
    """Return the active Git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def candidate_roots(active_root: Path) -> tuple[Path, ...]:
    """Return Git roots that can contain changed files for this hook."""
    roots = [active_root]
    vendored = active_root / "vendor" / "agent-canon"
    if (vendored / ".git").exists() or (vendored / "agents" / "evals").is_dir():
        roots.append(vendored)
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def git_lines(root: Path, args: tuple[str, ...]) -> tuple[str, ...]:
    """Return non-empty git output lines."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return ()
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def changed_files(root: Path) -> tuple[str, ...]:
    """Return tracked and untracked changed files relative to one root."""
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        names.update(git_lines(root, args))
    return tuple(sorted(name for name in names if is_visible_changed_file(root, name)))


def is_visible_changed_file(root: Path, relative_path: str) -> bool:
    """Return whether one changed path belongs in style-check coverage logs."""
    path = root / relative_path
    if not path.is_file():
        return False
    relative_parts = Path(relative_path).parts
    if any(part in EXCLUDED_PARTS for part in relative_parts):
        return False
    if Path(relative_path).suffix in EXCLUDED_SUFFIXES:
        return False
    return not any(relative_parts[: len(prefix)] == prefix for prefix in EXCLUDED_PREFIXES)


def files_with_suffixes(paths: tuple[str, ...], suffixes: set[str]) -> tuple[str, ...]:
    """Return changed files with any selected suffix."""
    return tuple(path for path in paths if Path(path).suffix in suffixes)


def markdown_commands(root: Path, paths: tuple[str, ...]) -> tuple[StyleCommand, ...]:
    """Return Markdown style commands."""
    generated_guide_paths = codex_cli_guide_generated_paths(paths)
    standard_paths = tuple(path for path in paths if path not in generated_guide_paths)
    commands: list[StyleCommand] = []
    if standard_paths:
        commands.append(
            StyleCommand(
                checker="agent_canon_docs_check",
                family="markdown",
                command=(
                    str(root / "tools" / "bin" / "agent-canon"),
                    "docs",
                    "check",
                    "--root",
                    str(root),
                    *standard_paths,
                ),
                paths=standard_paths,
            )
        )
    if generated_guide_paths:
        commands.append(
            StyleCommand(
                checker="codex_cli_guide_split",
                family="markdown",
                command=(
                    "python3",
                    str(root / "codex-cli-guide" / "tools" / "validate_split.py"),
                ),
                paths=generated_guide_paths,
            )
        )
    return tuple(commands)


def codex_cli_guide_generated_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return generated Codex guide source/section Markdown paths."""
    selected: list[str] = []
    for path in paths:
        parts = Path(path).parts
        if any(parts[: len(prefix)] == prefix for prefix in CODEX_CLI_GUIDE_GENERATED_PREFIXES):
            selected.append(path)
    return tuple(selected)


def build_style_plan(root: Path) -> RootStylePlan:
    """Return the style check plan for one Git root."""
    paths = changed_files(root)
    python_paths = files_with_suffixes(paths, PYTHON_SUFFIXES)
    cpp_paths = files_with_suffixes(paths, CPP_SUFFIXES)
    notebook_paths = files_with_suffixes(paths, NOTEBOOK_SUFFIXES)
    markdown_paths = files_with_suffixes(paths, MARKDOWN_SUFFIXES)
    commands = [
        *python_style_commands(python_paths),
        *cpp_style_commands(root, cpp_paths),
        *notebook_style_commands(root, notebook_paths),
        *markdown_commands(root, markdown_paths),
    ]
    covered: set[str] = set()
    for command in commands:
        covered.update(command.paths)
    unchecked = tuple(path for path in paths if path not in covered)
    return RootStylePlan(
        root=root,
        changed_files=paths,
        commands=tuple(commands),
        unchecked_files=unchecked,
    )


def python_style_commands(paths: tuple[str, ...]) -> tuple[StyleCommand, ...]:
    """Return Python style commands."""
    if not paths:
        return ()
    return (
        StyleCommand(
            checker="ruff",
            family="python",
            command=(
                "python3",
                "-m",
                "ruff",
                "check",
                *paths,
                "--select",
                "D,E,F,I,UP",
                "--ignore",
                "E501",
            ),
            paths=paths,
        ),
    )


def cpp_style_commands(root: Path, paths: tuple[str, ...]) -> tuple[StyleCommand, ...]:
    """Return C and C++ style commands."""
    if not paths:
        return ()
    return (
        StyleCommand(
            checker="cpp_readability",
            family="cpp",
            command=(
                "python3",
                str(root / "tools" / "oop" / "cpp" / "readability.py"),
                "--root",
                str(root),
                *paths,
            ),
            paths=paths,
        ),
    )


def notebook_style_commands(root: Path, paths: tuple[str, ...]) -> tuple[StyleCommand, ...]:
    """Return notebook quality commands."""
    if not paths:
        return ()
    return (
        StyleCommand(
            checker="notebook_quality",
            family="notebook",
            command=(
                "python3",
                str(root / "tools" / "validation" / "notebook_quality.py"),
                "--root",
                str(root),
                *paths,
            ),
            paths=paths,
        ),
    )


def run_style_command(root: Path, command: StyleCommand) -> StyleResult:
    """Run one selected style checker command."""
    result = subprocess.run(
        list(command.command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part.strip())
    return StyleResult(
        checker=command.checker,
        family=command.family,
        command=command.command,
        paths=command.paths,
        returncode=result.returncode,
        output=output,
    )


def append_style_log(
    active_root: Path,
    payload: dict[str, object],
    plans: tuple[RootStylePlan, ...],
    results: tuple[StyleResult, ...],
) -> None:
    """Append one style-check hook log record."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    context = HookLogContext(
        active_root=active_root,
        hook_name="style_checker_guard",
        override_path=os.environ.get(LOG_PATH_ENV, "").strip(),
    )
    failed_results = tuple(result for result in results if result.returncode != 0)
    context.append(
        {
            "timestamp": timestamp,
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "hook_log_namespace": context.runtime_namespace(),
            "payload_fingerprint": payload_fingerprint,
            "payload_status": payload_status(payload),
            "event": hook_event_name(payload),
            "event_declared": isinstance(payload.get("hookEventName"), str),
            "tool_name": tool_name(payload),
            "root": str(active_root),
            "candidate_roots": [str(plan.root) for plan in plans],
            "checked": bool(results),
            "check_requested": True,
            "selected_checkers": sorted({result.checker for result in results}),
            "changed_files": changed_file_log(plans),
            "checked_files": checked_file_log(plans),
            "unchecked_files": unchecked_file_log(plans),
            "unchecked_count": sum(len(plan.unchecked_files) for plan in plans),
            "result_count": len(results),
            "failed_count": len(failed_results),
            "status": "fail" if failed_results else "pass",
            "commands": [result.as_log_entry() for result in results],
            "failure_fingerprint": ""
            if not failed_results
            else fingerprint_json([result.as_log_entry() for result in failed_results]),
        }
    )


def changed_file_log(plans: tuple[RootStylePlan, ...]) -> list[dict[str, object]]:
    """Return changed-file log rows grouped by root."""
    return [
        {"root": str(plan.root), "paths": list(plan.changed_files)}
        for plan in plans
        if plan.changed_files
    ]


def checked_file_log(plans: tuple[RootStylePlan, ...]) -> list[dict[str, object]]:
    """Return checked-file log rows grouped by root."""
    return [
        {"root": str(plan.root), "paths": list(plan.checked_files())}
        for plan in plans
        if plan.checked_files()
    ]


def unchecked_file_log(plans: tuple[RootStylePlan, ...]) -> list[dict[str, object]]:
    """Return unchecked-file log rows grouped by root."""
    return [
        {"root": str(plan.root), "paths": list(plan.unchecked_files)}
        for plan in plans
        if plan.unchecked_files
    ]


def block_payload(results: tuple[StyleResult, ...]) -> dict[str, object]:
    """Return a Codex block payload for failed style checks."""
    failed = [result for result in results if result.returncode != 0]
    lines = [
        f"{result.family}:{result.checker}: {' '.join(result.paths)}"
        for result in failed[:MAX_OUTPUT_LINES]
    ]
    detail = "\n".join(lines)
    return {
        "decision": "block",
        "reason": (
            "Style checker hook blocked changed files. Fix the selected style "
            f"checker findings before continuing.\n{detail}"
        ).strip(),
        "next_action": "run_selected_style_checkers_and_fix_findings",
        "remediation": [
            "Run the checker family shown in the reason for each changed file group.",
            "Fix the formatting or style findings before retrying the tool action.",
            "If a changed file type is unsupported, add checker coverage or record explicit unchecked-file evidence.",
        ],
    }


def main() -> int:
    """Run the changed-file style checker hook."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    active_root = repo_root()
    plans = tuple(build_style_plan(root) for root in candidate_roots(active_root))
    if not any(plan.changed_files for plan in plans):
        return 0
    results = tuple(
        run_style_command(plan.root, command)
        for plan in plans
        for command in plan.commands
    )
    append_style_log(active_root, payload, plans, results)
    if any(result.returncode != 0 for result in results):
        json.dump(block_payload(results), sys.stdout)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
