#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks forced Python module-internal rewrites without boundary or import evidence.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/agent_tools/import_responsibility.py validates import ownership.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates module boundary hook behavior.
# @dependency-end
"""Guard Python module boundaries after editing tool calls."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_MODULE_BOUNDARY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
MAX_CHANGED_LINES_ENV = "AGENT_CANON_MODULE_BOUNDARY_MAX_CHANGED_LINES"
MAX_CHANGED_RATIO_ENV = "AGENT_CANON_MODULE_BOUNDARY_MAX_CHANGED_RATIO"
DEFAULT_MAX_CHANGED_LINES = 80
DEFAULT_MAX_CHANGED_RATIO = 0.35
GIT_TIMEOUT_SECONDS = 10
CHECK_TIMEOUT_SECONDS = 60
MAX_OUTPUT_LINES = 12
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+.*--fix|git\s+mv|mv\s+|cp\s+|"
    r"touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
CHECKER_COMMAND_RE = re.compile(
    r"(?is)(module_boundary_guard\.py|import_responsibility\.py|"
    r"tool_rejection_preflight\.py|ruff\s+check|python3?\s+-m\s+ruff\s+check)"
)
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "reports",
    "target",
}
EVIDENCE_SUFFIXES = {".md", ".toml", ".yaml", ".yml"}


@dataclass(frozen=True)
class ModuleChange:
    """One changed Python module and its module-boundary facts."""

    path: str
    added: int
    deleted: int
    current_lines: int
    changed_ratio: float
    public_removed: tuple[str, ...]
    public_added: tuple[str, ...]


@dataclass(frozen=True)
class BoundaryFinding:
    """One module boundary hook finding."""

    path: str
    kind: str
    detail: str

    def render(self) -> str:
        """Render a stable hook finding."""
        return f"MODULE_BOUNDARY_FINDING={self.path}:{self.kind}:{self.detail}"


@dataclass(frozen=True)
class ImportCheckResult:
    """Result of import responsibility validation."""

    command: tuple[str, ...]
    returncode: int
    output: str

    def _log_entry(self) -> dict[str, object]:
        """Return a JSON-friendly log payload."""
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "output_snippet": "\n".join(self.output.splitlines()[:MAX_OUTPUT_LINES]),
        }


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
    """Return how the payload was parsed."""
    value = payload.get(PAYLOAD_STATUS_KEY)
    return value if isinstance(value, str) else PAYLOAD_STATUS_VALID


def tool_command(payload: dict[str, object]) -> str:
    """Return the command-like payload value."""
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


def has_tool_signal(payload: dict[str, object]) -> bool:
    """Return whether payload looks like a tool event."""
    return isinstance(payload.get("tool_name"), str) or bool(tool_command(payload))


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the declared hook event name."""
    value = payload.get("hookEventName")
    if isinstance(value, str):
        return value
    return ""


def tool_name(payload: dict[str, object]) -> str:
    """Return the tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this hook should inspect changed modules."""
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
    return tool_name(payload) in EDIT_TOOL_NAMES or bool(EDIT_COMMAND_PATTERN.search(command))


def repo_root() -> Path:
    """Return active Git repository root."""
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
    """Return roots whose changed files should be inspected."""
    roots = [active_root.resolve()]
    vendored = active_root / "vendor" / "agent-canon"
    if (vendored / "agents" / "evals").is_dir():
        roots.append(vendored.resolve())
    return tuple(dict.fromkeys(roots))


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
    """Return changed tracked and untracked paths."""
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        names.update(git_lines(root, args))
    return tuple(sorted(name for name in names if is_visible_file(root, name)))


def is_visible_file(root: Path, relative_path: str) -> bool:
    """Return whether one changed file is visible to this guard."""
    path = root / relative_path
    return path.is_file() and not any(part in EXCLUDED_PARTS for part in Path(relative_path).parts)


def changed_python_modules(root: Path) -> tuple[str, ...]:
    """Return changed non-test Python module paths."""
    return tuple(
        path
        for path in changed_files(root)
        if path.endswith(".py") and not is_test_path(path)
    )


def is_test_path(relative_path: str) -> bool:
    """Return whether a path is a test file or under a test directory."""
    parts = Path(relative_path).parts
    return "tests" in parts or Path(relative_path).name.startswith("test_")


def evidence_files_changed(root: Path) -> bool:
    """Return whether tests or boundary evidence files changed with modules."""
    for path in changed_files(root):
        suffix = Path(path).suffix
        if is_test_path(path):
            return True
        if suffix in EVIDENCE_SUFFIXES and (
            path.startswith(("documents/", "agents/", "issues/", "reports/"))
            or path in {"responsibility-scope.toml", "tools/catalog.yaml"}
        ):
            return True
    return False


def numstat(root: Path, path: str) -> tuple[int, int]:
    """Return added and deleted line counts for one path."""
    lines = git_lines(root, ("diff", "--numstat", "HEAD", "--", path))
    if not lines:
        return (0, 0)
    fields = lines[0].split("\t")
    if len(fields) < 2:
        return (0, 0)
    return (parse_count(fields[0]), parse_count(fields[1]))


def parse_count(value: str) -> int:
    """Parse one git numstat count."""
    try:
        return int(value)
    except ValueError:
        return 0


def current_line_count(root: Path, path: str) -> int:
    """Return the current line count for one file."""
    text = (root / path).read_text(encoding="utf-8")
    return max(1, len(text.splitlines()))


def public_symbols(text: str) -> set[str]:
    """Return top-level public functions and classes from Python source."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.add(node.name)
    return symbols


def add_head_text(snapshot: dict[str, str], root: Path, path: str) -> None:
    """Add file text at HEAD to snapshot, using empty text for new files."""
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{path}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    snapshot[path] = result.stdout if result.returncode == 0 else ""


def module_changes(root: Path, paths: tuple[str, ...]) -> tuple[ModuleChange, ...]:
    """Return module-boundary facts for changed Python modules."""
    changes: list[ModuleChange] = []
    head_snapshot: dict[str, str] = {}
    for path in paths:
        add_head_text(head_snapshot, root, path)
    for path in paths:
        added, deleted = numstat(root, path)
        lines = current_line_count(root, path)
        before = public_symbols(head_snapshot[path])
        after = public_symbols((root / path).read_text(encoding="utf-8"))
        changes.append(
            ModuleChange(
                path=path,
                added=added,
                deleted=deleted,
                current_lines=lines,
                changed_ratio=(added + deleted) / lines,
                public_removed=tuple(sorted(before - after)),
                public_added=tuple(sorted(after - before)),
            )
        )
    return tuple(changes)


def max_changed_lines() -> int:
    """Return the large-rewrite line threshold."""
    return int(os.environ.get(MAX_CHANGED_LINES_ENV, str(DEFAULT_MAX_CHANGED_LINES)))


def max_changed_ratio() -> float:
    """Return the large-rewrite ratio threshold."""
    return float(os.environ.get(MAX_CHANGED_RATIO_ENV, str(DEFAULT_MAX_CHANGED_RATIO)))


def boundary_findings(changes: tuple[ModuleChange, ...], *, evidence_present: bool) -> tuple[BoundaryFinding, ...]:
    """Return module-boundary findings for changed modules."""
    findings: list[BoundaryFinding] = []
    max_lines = max_changed_lines()
    max_ratio = max_changed_ratio()
    for change in changes:
        changed_lines = change.added + change.deleted
        if changed_lines > max_lines and change.changed_ratio > max_ratio and not evidence_present:
            findings.append(
                BoundaryFinding(
                    change.path,
                    "large-module-rewrite-without-evidence",
                    f"changed_lines:{changed_lines}:ratio:{change.changed_ratio:.2f}:threshold:{max_lines}/{max_ratio}",
                )
            )
        if (change.public_added or change.public_removed) and not evidence_present:
            findings.append(
                BoundaryFinding(
                    change.path,
                    "public-surface-change-without-evidence",
                    f"added:{','.join(change.public_added) or '-'}:removed:{','.join(change.public_removed) or '-'}",
                )
            )
    return tuple(findings)


def run_import_check(root: Path, paths: tuple[str, ...]) -> tuple[ImportCheckResult, ...]:
    """Run import responsibility checker for changed module paths."""
    checker = root / "tools" / "agent_tools" / "import_responsibility.py"
    if not checker.is_file() or not paths:
        return ()
    command = ("python3", str(checker), "--root", str(root), *paths)
    result = subprocess.run(
        list(command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    return (
        ImportCheckResult(
            command=command,
            returncode=result.returncode,
            output=result.stdout + result.stderr,
        ),
    )


def block_payload(
    findings: tuple[BoundaryFinding, ...],
    import_failure_lines: tuple[str, ...],
) -> dict[str, object]:
    """Return a Codex hook block payload."""
    details = [finding.render() for finding in findings]
    details.extend(import_failure_lines)
    return {
        "decision": "block",
        "reason": (
            "Module boundary hook blocked Python module edits. Run import "
            "responsibility checks, add tests or boundary evidence, or reduce "
            "the edit to the owning scope before continuing."
        ),
        "next_action": "run_import_responsibility_and_add_boundary_evidence",
        "remediation": [
            "Run `python3 tools/agent_tools/import_responsibility.py --root . <changed-python-files>`.",
            "Move the change to the owning module or reduce it to the current module boundary.",
            "Add tests or boundary evidence before retrying broad module edits.",
        ],
        "findings": details,
    }


def _log_entry(
    context: HookLogContext,
    payload: dict[str, object],
    changes: tuple[ModuleChange, ...],
    findings: tuple[BoundaryFinding, ...],
    import_results: tuple[ImportCheckResult, ...],
    *,
    checked: bool,
) -> dict[str, object]:
    """Build a hook JSONL entry."""
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    failed = bool(findings) or any(result.returncode != 0 for result in import_results)
    return {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "timestamp": timestamp,
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fingerprint": payload_fingerprint,
        "checked": checked,
        "changed_module_count": len(changes),
        "changed_modules": [asdict(change) for change in changes],
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "import_checks": [result._log_entry() for result in import_results],
        "status": "fail" if failed else "pass",
    }


def maybe_log(entry: dict[str, object], context: HookLogContext) -> None:
    """Append hook log unless disabled."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    context.append(entry)


def main() -> int:
    """Run the module boundary hook."""
    payload = load_payload()
    root = repo_root()
    context = HookLogContext(
        active_root=root,
        hook_name="module_boundary_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    if not should_check(payload):
        return 0

    all_changes: list[ModuleChange] = []
    all_findings: list[BoundaryFinding] = []
    import_results: list[ImportCheckResult] = []
    for current_root in candidate_roots(root):
        paths = changed_python_modules(current_root)
        changes = module_changes(current_root, paths)
        all_changes.extend(changes)
        all_findings.extend(
            boundary_findings(changes, evidence_present=evidence_files_changed(current_root))
        )
        import_results.extend(run_import_check(current_root, paths))

    failed_import = next((result for result in import_results if result.returncode != 0), None)
    import_failure_lines = (
        tuple(failed_import.output.splitlines()[:MAX_OUTPUT_LINES])
        if failed_import is not None
        else ()
    )
    entry = _log_entry(
        context,
        payload,
        tuple(all_changes),
        tuple(all_findings),
        tuple(import_results),
        checked=True,
    )
    maybe_log(entry, context)

    if all_findings or failed_import is not None:
        print(
            json.dumps(
                block_payload(tuple(all_findings), import_failure_lines),
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
