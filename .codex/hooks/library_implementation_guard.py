#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks direct rewrites of vendored or installed library implementations.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream design ../../responsibility-scope.toml marks external dependency scopes.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates library implementation guard behavior.
# @dependency-end
"""Guard external library implementation files from direct rewrites."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now
import tomllib

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_LIBRARY_IMPLEMENTATION_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
MANIFEST_PATH = "responsibility-scope.toml"
GIT_TIMEOUT_SECONDS = 10
MAX_OUTPUT_LINES = 12
RENAME_STATUS_FIELD_COUNT = 3
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+.*--fix|git\s+mv|mv\s+|cp\s+|"
    r"touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
CHECKER_COMMAND_RE = re.compile(
    r"(?is)(library_implementation_guard\.py|tool_rejection_preflight\.py)"
)
COMMON_PROTECTED_PATTERNS = (
    "vendor/**",
    "third_party/**",
    "third-party/**",
    "external/**",
    "node_modules/**",
    ".venv/**",
    "venv/**",
    "env/**",
    ".tox/**",
)
PROTECTED_PARTS = {"site-packages", "dist-packages", "node_modules"}
PROTECTED_SCOPE_OWNERS = {"external-vendor"}
PROTECTED_SCOPE_CLASSES = {"external_dependency"}
AGENT_CANON_SUBMODULE_PREFIX = "vendor/agent-canon"
ALLOWED_METADATA_EXACT_PATHS = {
    "vendor/README.md",
    "vendor/skills/README.md",
    "vendor/skills/manifest.toml",
}
ALLOWED_METADATA_NAMES = {
    "AUTHORS",
    "AUTHORS.md",
    "COPYING",
    "COPYING.md",
    "LICENSE",
    "LICENSE.md",
    "NOTICE",
    "NOTICE.md",
    "README",
    "README.md",
    "manifest.toml",
}
IMPORT_EVIDENCE_PATHS = {
    "vendor/skills/manifest.toml",
    "vendor/README.md",
    "vendor/skills/README.md",
}
IMPORT_EVIDENCE_PREFIXES = ("issues/", "references/")


@dataclass(frozen=True)
class ChangeRecord:
    """One changed repository path from Git status."""

    path: str
    status: str
    previous_path: str


@dataclass(frozen=True)
class LibraryFinding:
    """One protected library implementation finding."""

    path: str
    kind: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"LIBRARY_IMPLEMENTATION_FINDING={self.path}:{self.kind}:{self.detail}"


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
    """Return whether this hook should inspect changed library paths."""
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
    """Return roots whose library edits should be inspected."""
    roots = [active_root.resolve()]
    vendored = active_root / "vendor" / "agent-canon"
    if (vendored / "agents" / "evals").is_dir():
        roots.append(vendored.resolve())
    return tuple(dict.fromkeys(roots))


def git_lines(root: Path, args: tuple[str, ...]) -> tuple[str, ...]:
    """Return non-empty Git output lines."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return ()
    return tuple(line.rstrip("\n") for line in result.stdout.splitlines() if line.strip())


def changed_records(root: Path) -> tuple[ChangeRecord, ...]:
    """Return changed tracked and untracked path records."""
    records: list[ChangeRecord] = []
    for line in git_lines(root, ("diff", "--name-status", "--diff-filter=ACMRTD", "HEAD", "--")):
        add_name_status_record(records, line)
    for path in git_lines(root, ("ls-files", "--others", "--exclude-standard")):
        records.append(ChangeRecord(path=path, status="A", previous_path=""))
    return tuple(record for record in records if is_visible_path(record.path))


def add_name_status_record(records: list[ChangeRecord], line: str) -> None:
    """Parse one git name-status line into records."""
    fields = line.split("\t")
    if len(fields) < 2:
        return
    status = fields[0]
    if status.startswith("R") and len(fields) >= RENAME_STATUS_FIELD_COUNT:
        records.append(ChangeRecord(path=fields[2], status="R", previous_path=fields[1]))
        return
    records.append(ChangeRecord(path=fields[1], status=status[:1], previous_path=""))


def is_visible_path(relative_path: str) -> bool:
    """Return whether one changed path is visible to this guard."""
    parts = Path(relative_path).parts
    return not any(part in {".git", "__pycache__", ".pytest_cache", "reports", "target"} for part in parts)


def protected_patterns(root: Path) -> tuple[str, ...]:
    """Return protected library implementation patterns."""
    patterns = list(COMMON_PROTECTED_PATTERNS)
    manifest = root / MANIFEST_PATH
    if manifest.is_file():
        patterns.extend(manifest_external_dependency_patterns(manifest))
    return tuple(dict.fromkeys(patterns))


def manifest_external_dependency_patterns(path: Path) -> tuple[str, ...]:
    """Return paths from external dependency scopes in the manifest."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    scopes = data.get("scope")
    if not isinstance(scopes, list):
        return ()
    patterns: list[str] = []
    for item in scopes:
        if not isinstance(item, dict):
            continue
        owner = str(item.get("owner") or "")
        scope_class = str(item.get("class") or "")
        if owner not in PROTECTED_SCOPE_OWNERS and scope_class not in PROTECTED_SCOPE_CLASSES:
            continue
        raw_paths = item.get("paths")
        if isinstance(raw_paths, list):
            patterns.extend(path_item for path_item in raw_paths if isinstance(path_item, str))
    return tuple(patterns)


def pattern_covers(pattern: str, path: str) -> bool:
    """Return whether one scope pattern covers a repository path."""
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern.removesuffix("/**").rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def allowed_library_metadata_path(path: str) -> bool:
    """Return whether a protected path is metadata, not implementation."""
    if path in ALLOWED_METADATA_EXACT_PATHS:
        return True
    name = Path(path).name
    return name in ALLOWED_METADATA_NAMES


def agent_canon_submodule_path(path: str) -> bool:
    """Return whether a parent repo path is the AgentCanon submodule pointer."""
    return path == AGENT_CANON_SUBMODULE_PREFIX or path.startswith(
        AGENT_CANON_SUBMODULE_PREFIX + "/"
    )


def protected_library_path(path: str, patterns: tuple[str, ...]) -> bool:
    """Return whether a path is protected library implementation."""
    if agent_canon_submodule_path(path) or allowed_library_metadata_path(path):
        return False
    parts = set(Path(path).parts)
    if parts & PROTECTED_PARTS:
        return True
    return any(pattern_covers(pattern, path) for pattern in patterns)


def import_evidence_changed(records: tuple[ChangeRecord, ...]) -> bool:
    """Return whether a vendor import/update carries provenance evidence."""
    for record in records:
        if record.path in IMPORT_EVIDENCE_PATHS:
            return True
        if record.path.startswith(IMPORT_EVIDENCE_PREFIXES):
            return True
    return False


def rewrite_status(record: ChangeRecord) -> bool:
    """Return whether a Git status rewrites an existing implementation."""
    return record.status[:1] in {"M", "D", "R", "C", "T"}


def library_findings(
    records: tuple[ChangeRecord, ...],
    patterns: tuple[str, ...],
) -> tuple[LibraryFinding, ...]:
    """Return protected library implementation findings."""
    findings: list[LibraryFinding] = []
    has_import_evidence = import_evidence_changed(records)
    for record in records:
        if not protected_library_path(record.path, patterns):
            continue
        if rewrite_status(record):
            findings.append(
                LibraryFinding(
                    path=record.path,
                    kind="library-implementation-rewrite",
                    detail=f"status:{record.status}:use-wrapper-fork-or-upstream-patch",
                )
            )
        elif record.status == "A" and not has_import_evidence:
            findings.append(
                LibraryFinding(
                    path=record.path,
                    kind="library-implementation-addition-without-import-evidence",
                    detail="status:A:add-vendor-manifest-reference-or-issue-evidence",
                )
            )
    return tuple(findings)


def _log_entry(
    context: HookLogContext,
    payload: dict[str, object],
    records: tuple[ChangeRecord, ...],
    findings: tuple[LibraryFinding, ...],
    *,
    checked: bool,
) -> dict[str, object]:
    """Build one hook JSONL entry."""
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    library_records = tuple(
        record
        for record in records
        if protected_library_path(record.path, protected_patterns(context.active_root))
    )
    return {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "timestamp": timestamp,
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fingerprint": payload_fingerprint,
        "checked": checked,
        "changed_library_file_count": len(library_records),
        "changed_library_files": [asdict(record) for record in library_records],
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
        "status": "fail" if findings else "pass",
    }


def maybe_log(entry: dict[str, object], context: HookLogContext) -> None:
    """Append hook log unless disabled."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    context.append(entry)


def block_payload(findings: tuple[LibraryFinding, ...]) -> dict[str, object]:
    """Return a Codex hook block payload."""
    return {
        "decision": "block",
        "reason": (
            "Library implementation guard blocked direct edits under vendored or "
            "installed dependency paths. Use a wrapper/adapter, fork/upstream patch, "
            "or a manifest-backed vendor import instead of rewriting library internals."
        ),
        "next_action": "move_change_to_wrapper_fork_or_owned_vendor_surface",
        "remediation": [
            "Do not edit installed dependency or vendored third-party internals in place.",
            "Use an adapter/wrapper, an upstream patch branch, or a manifest-backed vendor import.",
            "If the path is misclassified, update the protected-path policy with evidence before retrying.",
        ],
        "findings": [finding.render() for finding in findings],
    }


def main() -> int:
    """Run the library implementation guard."""
    payload = load_payload()
    root = repo_root()
    context = HookLogContext(
        active_root=root,
        hook_name="library_implementation_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    if not should_check(payload):
        return 0

    all_records: list[ChangeRecord] = []
    all_findings: list[LibraryFinding] = []
    for current_root in candidate_roots(root):
        records = changed_records(current_root)
        all_records.extend(records)
        all_findings.extend(library_findings(records, protected_patterns(current_root)))

    findings = tuple(all_findings)
    maybe_log(
        _log_entry(context, payload, tuple(all_records), findings, checked=True),
        context,
    )
    if findings:
        print(json.dumps(block_payload(findings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
