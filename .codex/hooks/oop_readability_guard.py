#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Runs OOP readability hook checks after source-editing tool calls.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/oop/python/readability.py checks Python OOP readability.
# upstream implementation ../../tools/oop/cpp/readability.py checks C++ OOP readability.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates guard output.
# @dependency-end

"""Warn when changed source files fail OOP readability checks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
EXCLUDED_PARTS = {".git", "__pycache__", "reports", "tests", ".pytest_cache", ".ruff_cache"}
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+-m\s+ruff\s+.*--fix|ruff\s+.*--fix|"
    r"python3?\s+(?:-c\b|-(?:\s|$)|<<)|"
    r"git\s+mv|mv\s+|cp\s+|touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_OOP_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
MODE_ENV = "AGENT_CANON_OOP_HOOK_MODE"
BASELINE_REF_ENV = "AGENT_CANON_OOP_HOOK_BASELINE_REF"
MODE_FULL = "full"
MODE_DIFF = "diff"
DEFAULT_DIFF_BASELINE_REF = "HEAD"
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


FindingKey = tuple[str, str, str, str, str, str, str]


@dataclass(frozen=True)
class HeadSource:
    """One source file as it existed at HEAD."""

    relative_path: str
    text: str
    exists: bool


@dataclass(frozen=True)
class CheckMode:
    """Describe how the hook should evaluate changed-source findings."""

    mode: str
    baseline_ref: str | None


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
    """Return whether one payload carries tool identity or command fields."""
    return isinstance(payload.get("tool_name"), str) or bool(tool_command(payload))


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
    """Return the declared hook event name."""
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    return "UnknownHookEvent"


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name from one hook payload."""
    value = payload.get("tool_name")
    if isinstance(value, str):
        return value
    return "unknown"


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


def check_mode_from_environment() -> CheckMode:
    """Return the OOP hook mode, defaulting to changed-finding checks."""
    mode = os.environ.get(MODE_ENV, MODE_DIFF).strip().casefold() or MODE_DIFF
    if mode in {"baseline", "changed", "changed-only", "diff-only"}:
        mode = MODE_DIFF
    if mode == MODE_FULL:
        return CheckMode(mode=MODE_FULL, baseline_ref=None)
    baseline_ref = os.environ.get(BASELINE_REF_ENV, DEFAULT_DIFF_BASELINE_REF).strip()
    return CheckMode(mode=MODE_DIFF, baseline_ref=baseline_ref or DEFAULT_DIFF_BASELINE_REF)


def run_analyzer(
    root: Path,
    analyzer: Path,
    paths: list[Path],
    check_mode: CheckMode,
) -> AnalyzerResult | None:
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
    if check_mode.mode == MODE_DIFF and check_mode.baseline_ref is not None:
        command_parts.extend(("--baseline-ref", check_mode.baseline_ref))
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
    result_record = AnalyzerResult(
        command=command,
        returncode=result.returncode,
        output=(result.stdout + result.stderr).strip(),
        min_score=min_score,
    )
    if result_record.returncode == 0:
        return result_record
    if check_mode.mode == MODE_DIFF and check_mode.baseline_ref is not None:
        return run_preexisting_finding_filter(
            root,
            analyzer,
            paths,
            result_record,
            baseline_ref=check_mode.baseline_ref,
        )
    return result_record


def build_finding_key(finding: dict[str, object]) -> FindingKey:
    """Return a line-stable identity for one OOP finding."""
    return (
        str(finding.get("path", "")),
        str(finding.get("language", "")),
        str(finding.get("severity", "")),
        str(finding.get("kind", "")),
        str(finding.get("symbol", "")),
        str(finding.get("actual", "")),
        str(finding.get("limit", "")),
    )


def parse_finding_keys(output: str) -> tuple[set[FindingKey], bool]:
    """Return finding identities from analyzer JSON output."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return set(), False
    findings = payload.get("findings") if isinstance(payload, dict) else None
    if not isinstance(findings, list):
        return set(), False
    return (
        {
            build_finding_key(finding)
            for finding in findings
            if isinstance(finding, dict)
        },
        True,
    )


def run_analyzer_finding_keys(
    root: Path,
    analyzer: Path,
    paths: list[Path],
) -> tuple[set[FindingKey], bool]:
    """Run one analyzer in JSON mode and return stable finding identities."""
    if not paths:
        return set(), True
    relative_paths = [path.relative_to(root).as_posix() for path in paths]
    result = subprocess.run(
        [
            "python3",
            str(analyzer),
            "--root",
            str(root),
            "--format",
            "json",
            "--min-score",
            "0",
            *relative_paths,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=ANALYZER_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return set(), False
    return parse_finding_keys(result.stdout)


def read_baseline_source(root: Path, baseline_ref: str, relative_path: str) -> HeadSource:
    """Return one changed file's baseline content when it exists."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{baseline_ref}:{relative_path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
    )
    return HeadSource(
        relative_path=relative_path,
        text=result.stdout,
        exists=result.returncode == 0,
    )


def run_baseline_finding_keys(
    root: Path,
    analyzer: Path,
    paths: list[Path],
    *,
    baseline_ref: str,
) -> tuple[set[FindingKey], bool]:
    """Run one analyzer against baseline copies of changed files."""
    sources = [
        read_baseline_source(root, baseline_ref, path.relative_to(root).as_posix())
        for path in paths
    ]
    existing_sources = [source for source in sources if source.exists]
    if not existing_sources:
        return set(), True
    with tempfile.TemporaryDirectory() as temp_dir:
        baseline_root = Path(temp_dir)
        baseline_paths: list[Path] = []
        for source in existing_sources:
            target = baseline_root / source.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.text, encoding="utf-8")
            baseline_paths.append(target)
        return run_analyzer_finding_keys(baseline_root, analyzer, baseline_paths)


def run_preexisting_finding_filter(
    root: Path,
    analyzer: Path,
    paths: list[Path],
    result: AnalyzerResult,
    *,
    baseline_ref: str,
) -> AnalyzerResult:
    """Allow an analyzer failure only when every finding already existed in baseline."""
    current_keys, current_ok = run_analyzer_finding_keys(root, analyzer, paths)
    baseline_keys, baseline_ok = run_baseline_finding_keys(
        root,
        analyzer,
        paths,
        baseline_ref=baseline_ref,
    )
    if not current_ok or not baseline_ok:
        return result
    new_or_worse_keys = current_keys - baseline_keys
    if new_or_worse_keys:
        return result
    return AnalyzerResult(
        command=result.command,
        returncode=0,
        output=f"{result.output}\nOOP_READABILITY_BASELINE=preexisting-only",
        min_score=result.min_score,
    )


def candidate_roots(root: Path) -> list[Path]:
    """Return root and AgentCanon submodule roots to inspect."""
    roots = [root]
    submodule = root / "vendor" / "agent-canon"
    if (submodule / ".git").exists():
        roots.append(submodule)
    return roots


def run_oop_checks(root: Path, check_mode: CheckMode) -> list[AnalyzerResult]:
    """Run applicable OOP checks for changed Python and C++ files."""
    results: list[AnalyzerResult] = []
    for candidate in candidate_roots(root):
        python_result = run_analyzer(
            candidate,
            candidate / "tools" / "oop" / "python" / "readability.py",
            source_paths(candidate, PYTHON_SUFFIXES),
            check_mode,
        )
        cpp_result = run_analyzer(
            candidate,
            candidate / "tools" / "oop" / "cpp" / "readability.py",
            source_paths(candidate, CPP_SUFFIXES),
            check_mode,
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


def emit_warning(results: list[AnalyzerResult]) -> None:
    """Emit a non-blocking hook result with OOP remediation details."""
    failed = [result for result in results if result.returncode != 0]
    snippets = []
    for result in failed[:MAX_BLOCKED_ANALYZER_SNIPPETS]:
        first_lines = "\n".join(result.output.splitlines()[:MAX_ANALYZER_OUTPUT_LINES])
        snippets.append(f"$ {' '.join(result.command)}\n{first_lines}")
    json.dump(
        {
            "decision": "approve",
            "reason": (
                "OOP readability hook found new or changed-source review findings. "
                "This warning is a non-blocking boundary review signal; do not split code only "
                "to satisfy the score. Run the listed checker(s) before closeout and "
                "either fix a true design risk or record why the current boundary is intended.\n\n"
                + "\n\n".join(snippets)
            ),
            "next_action": "review_oop_boundary_signal",
            "remediation": [
                "Classify each finding as true boundary risk, accepted boundary, or checker false positive.",
                "Refactor only when caller contracts or source ownership show a real boundary change.",
                "Record the boundary decision when findings are accepted for the current edit.",
            ],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def default_log_path(root: Path) -> Path:
    """Return the OOP hook log path."""
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return HookLogContext(root, "oop_readability_guard", override).result_path()


def analyzer_snippet(result: AnalyzerResult) -> str:
    """Return a short analyzer output snippet for durable hook logs."""
    return "\n".join(result.output.splitlines()[:MAX_ANALYZER_OUTPUT_LINES])


def skip_reason(payload: dict[str, object]) -> str:
    """Return why this hook invocation did not run analyzers."""
    event = hook_event_name(payload)
    if event == "UnknownHookEvent":
        return "unsupported_payload_without_event_or_tool_signal"
    if event not in {"PostToolUse", "Stop"}:
        return f"event_not_checked:{event}"
    command = tool_command(payload)
    name = tool_name(payload)
    if event == "PostToolUse" and name not in EDIT_TOOL_NAMES and not EDIT_COMMAND_PATTERN.search(command):
        return "post_tool_without_source_edit_signal"
    return ""


def logged_checked(checked: bool, results: list[AnalyzerResult]) -> bool:
    """Return whether analyzers actually ran for log semantics."""
    return checked and bool(results)


def _log_skip_reason(
    payload: dict[str, object],
    checked: bool,
    results: list[AnalyzerResult],
) -> str:
    """Return the durable skip reason for one hook invocation."""
    if checked and not results:
        return "no_changed_source_files"
    if not checked:
        return skip_reason(payload)
    return ""


def hook_log_status(
    checked: bool,
    results: list[AnalyzerResult],
    failed: list[AnalyzerResult],
) -> str:
    """Return the status value for one OOP hook log entry."""
    if not logged_checked(checked, results):
        return "skipped"
    return "warn" if failed else "pass"


def analyzer_log_payload(
    payload: dict[str, object],
    root: Path,
    *,
    checked: bool,
    results: list[AnalyzerResult],
    check_mode: CheckMode,
) -> dict[str, object]:
    """Build one OOP hook invocation log payload."""
    failed = [result for result in results if result.returncode != 0]
    min_score = next((result.min_score for result in results if result.min_score is not None), None)
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    failure_fingerprint = fingerprint_json(
        [
            {
                "command": list(result.command),
                "output": analyzer_snippet(result),
                "returncode": result.returncode,
            }
            for result in failed
        ]
    )
    context = HookLogContext(root, "oop_readability_guard", os.environ.get(LOG_PATH_ENV, "").strip())
    return {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "hook_log_namespace": context.runtime_namespace(),
        "timestamp": timestamp,
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fingerprint": payload_fingerprint,
        "payload_empty": payload_status(payload) == PAYLOAD_STATUS_EMPTY,
        "event_declared": isinstance(payload.get("hookEventName"), str),
        "check_requested": checked,
        "checked": logged_checked(checked, results),
        "skip_reason": _log_skip_reason(payload, checked, results),
        "mode": check_mode.mode,
        "baseline_ref": check_mode.baseline_ref or "",
        "min_score": min_score,
        "result_count": len(results),
        "failed_count": len(failed),
        "failure_fingerprint": failure_fingerprint if failed else "",
        "status": hook_log_status(checked, results, failed),
        "root": str(root),
        "commands": [
            {
                "command": list(result.command),
                "returncode": result.returncode,
                "output_snippet": analyzer_snippet(result),
            }
            for result in results
        ],
    }


def _log_append_hook_log(root: Path, entry: dict[str, object]) -> None:
    """Append one JSONL hook log entry without blocking the hook on logging errors."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    try:
        HookLogContext(root, "oop_readability_guard", os.environ.get(LOG_PATH_ENV, "").strip()).append(
            entry
        )
    except OSError:
        return


def main() -> int:
    """Warn on changed-source OOP findings without blocking tool execution."""
    payload = load_payload()
    root = repo_root()
    if payload_status(payload) == PAYLOAD_STATUS_EMPTY:
        return 0
    checked = should_check(payload)
    check_mode = check_mode_from_environment()
    if not checked:
        _log_append_hook_log(
            root,
            analyzer_log_payload(
                payload,
                root,
                checked=False,
                results=[],
                check_mode=check_mode,
            ),
        )
        return 0
    results = run_oop_checks(root, check_mode)
    _log_append_hook_log(
        root,
        analyzer_log_payload(
            payload,
            root,
            checked=True,
            results=results,
            check_mode=check_mode,
        ),
    )
    if any(result.returncode != 0 for result in results):
        emit_warning(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
