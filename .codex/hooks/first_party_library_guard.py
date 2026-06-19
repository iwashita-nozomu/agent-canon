#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks first-party library and public API edits without task authority.
# upstream implementation ../../tools/agent_tools/task_authority.py defines first-party library authority matching.
# upstream design ../../responsibility-scope.toml defines reusable first-party surfaces.
# downstream implementation ./hook_dispatcher.py invokes this hook for PostToolUse and Stop.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates first-party guard behavior.
# @dependency-end
"""Guard first-party reusable library/API surfaces from unauthorized edits."""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

from hook_event_log import HookLogContext, fingerprint_json, utc_now  # noqa: E402
from task_authority import first_party_library_authorized, load_task_authority  # noqa: E402
import tomllib

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
LOG_PATH_ENV = "AGENT_CANON_FIRST_PARTY_LIBRARY_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
MANIFEST_PATH = "responsibility-scope.toml"
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
GIT_TIMEOUT_SECONDS = 10
DEFAULT_FIRST_PARTY_PATTERNS = ("python/**", "src/**", "include/**", "lib/**")
TASK_LOCAL_ADAPTER_MARKERS = ("adapter", "adapters", "wrapper", "wrappers")
PUBLIC_SUFFIXES = (".py", ".pyi", ".h", ".hh", ".hpp", ".hxx", ".ixx")


@dataclass(frozen=True)
class ChangeRecord:
    """One changed repository path."""

    path: str
    status: str


@dataclass(frozen=True)
class FirstPartyFinding:
    """One first-party library/API authority finding."""

    path: str
    kind: str
    detail: str

    def render(self) -> str:
        """Render a stable finding line."""
        return f"FIRST_PARTY_LIBRARY_FINDING={self.path}:{self.kind}:{self.detail}"


@dataclass(frozen=True)
class PatternLoadResult:
    """First-party path patterns plus any manifest loading finding."""

    patterns: tuple[str, ...]
    finding: FirstPartyFinding | None = None


def load_payload() -> dict[str, object]:
    """Read one hook payload."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {PAYLOAD_STATUS_KEY: "empty"}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {PAYLOAD_STATUS_KEY: "invalid_json"}
    if isinstance(loaded, dict):
        loaded[PAYLOAD_STATUS_KEY] = "valid"
        return loaded
    return {PAYLOAD_STATUS_KEY: "invalid_json"}


def hook_event_name(payload: dict[str, object]) -> str:
    """Return hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) else ""


def tool_name(payload: dict[str, object]) -> str:
    """Return tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def should_check(payload: dict[str, object]) -> bool:
    """Return whether this hook should inspect first-party surfaces."""
    event = hook_event_name(payload)
    if event == "Stop":
        return True
    return event == "PostToolUse" and tool_name(payload) in EDIT_TOOL_NAMES


def repo_root() -> Path:
    """Return active repository root."""
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


def changed_records(root: Path) -> tuple[ChangeRecord, ...]:
    """Return changed path records."""
    records: list[ChangeRecord] = []
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-status", "--diff-filter=ACMRTD", "HEAD", "--"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2:
                records.append(ChangeRecord(path=fields[-1], status=fields[0][:1]))
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        records.extend(ChangeRecord(path=line.strip(), status="A") for line in result.stdout.splitlines() if line.strip())
    return tuple(record for record in records if visible_path(record.path))


def visible_path(path: str) -> bool:
    """Return whether one path should be inspected."""
    return not path.startswith(("reports/", ".agent-canon/log-archive/"))


def manifest_first_party_patterns(root: Path) -> PatternLoadResult:
    """Return first-party reusable patterns from responsibility-scope.toml."""
    manifest = root / MANIFEST_PATH
    if not manifest.is_file():
        return PatternLoadResult(patterns=DEFAULT_FIRST_PARTY_PATTERNS)
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return PatternLoadResult(
            patterns=DEFAULT_FIRST_PARTY_PATTERNS,
            finding=FirstPartyFinding(
                path=MANIFEST_PATH,
                kind="first-party-manifest-parse-error",
                detail=f"{type(exc).__name__}:{exc}",
            ),
        )
    scopes = data.get("scope")
    if not isinstance(scopes, list):
        return PatternLoadResult(patterns=DEFAULT_FIRST_PARTY_PATTERNS)
    patterns: list[str] = list(DEFAULT_FIRST_PARTY_PATTERNS)
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        owner = str(scope.get("owner") or "")
        scope_class = str(scope.get("class") or "")
        if owner == "external-vendor" or scope_class == "external_dependency":
            continue
        raw_paths = scope.get("paths")
        if isinstance(raw_paths, list):
            for path in raw_paths:
                if isinstance(path, str) and path.split("/", 1)[0] in {"python", "src", "include", "lib"}:
                    patterns.append(path)
    return PatternLoadResult(patterns=tuple(dict.fromkeys(patterns)))


def pattern_covers(pattern: str, path: str) -> bool:
    """Return whether one glob-like pattern covers one path."""
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern.removesuffix("/**").rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def task_local_adapter_addition(record: ChangeRecord) -> bool:
    """Return whether this addition looks like a task-local adapter/wrapper surface."""
    if record.status != "A":
        return False
    parts = {part.casefold() for part in Path(record.path).parts}
    name = Path(record.path).stem.casefold()
    return bool(parts & set(TASK_LOCAL_ADAPTER_MARKERS)) or any(marker in name for marker in TASK_LOCAL_ADAPTER_MARKERS)


def first_party_path(path: str, patterns: tuple[str, ...]) -> bool:
    """Return whether a path is a first-party library/API candidate."""
    if Path(path).suffix not in PUBLIC_SUFFIXES:
        return False
    return any(pattern_covers(pattern, path) for pattern in patterns)


def findings_for_records(
    authority_root: Path,
    records: tuple[ChangeRecord, ...],
    patterns: tuple[str, ...],
) -> tuple[FirstPartyFinding, ...]:
    """Return unauthorized first-party findings."""
    authority = load_task_authority(authority_root)
    findings: list[FirstPartyFinding] = []
    for record in records:
        if not first_party_path(record.path, patterns):
            continue
        if task_local_adapter_addition(record):
            continue
        allowed, detail = first_party_library_authorized(authority, record.path)
        if not allowed:
            findings.append(
                FirstPartyFinding(
                    path=record.path,
                    kind="first-party-library-change-without-authority",
                    detail=f"status:{record.status}:{detail}",
                )
            )
    return tuple(findings)


def block_payload(findings: tuple[FirstPartyFinding, ...]) -> dict[str, object]:
    """Return a blocking hook payload."""
    return {
        "decision": "block",
        "reason": "First-party reusable library/API surface changed without task authority.",
        "next_action": "add_first_party_library_authority_or_move_to_task_local_adapter",
        "remediation": [
            "Prefer a task-local adapter, caller-side configuration, or existing extension point.",
            "If the reusable surface must change, add first_party_library_change authority with reason, affected callers, and tests.",
            "Keep public API and reusable core changes separate from opportunistic feature/debug edits.",
        ],
        "findings": [finding.render() for finding in findings],
    }


def maybe_log(context: HookLogContext, entry: dict[str, object]) -> None:
    """Append hook log unless disabled."""
    if not os.environ.get(DISABLE_LOG_ENV, "").strip():
        context.append(entry)


def main() -> int:
    """Run the first-party library guard."""
    payload = load_payload()
    if not should_check(payload):
        return 0
    root = repo_root()
    records = changed_records(root)
    pattern_result = manifest_first_party_patterns(root)
    findings = tuple(
        finding
        for finding in (pattern_result.finding, *findings_for_records(root, records, pattern_result.patterns))
        if finding is not None
    )
    context = HookLogContext(
        active_root=root,
        hook_name="first_party_library_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    timestamp = utc_now()
    maybe_log(
        context,
        {
            "hook_run_id": context.run_id(timestamp, fingerprint_json(payload)),
            "timestamp": timestamp,
            "event": hook_event_name(payload),
            "tool_name": tool_name(payload),
            "checked_file_count": len(records),
            "patterns": list(pattern_result.patterns),
            "finding_count": len(findings),
            "findings": [asdict(finding) for finding in findings],
            "status": "fail" if findings else "pass",
        },
    )
    if findings:
        print(json.dumps(block_payload(findings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
