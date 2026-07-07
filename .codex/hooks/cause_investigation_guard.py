#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks code edits before cause investigation evidence exists.
# upstream implementation ../hooks.json invokes this hook for PreToolUse.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream design ../../agents/workflows/hypothesis-validation-workflow.md defines analysis-first evidence fields.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates cause investigation hook behavior.
# @dependency-end
"""Guard code edits until cause investigation evidence is present."""

from __future__ import annotations

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
LOG_PATH_ENV = "AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH"
CONFIRMED_ENV = "AGENT_CANON_CAUSE_INVESTIGATION_CONFIRMED"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
ACTIVE_REPORT_DIR_ENVS = (
    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR",
    "AGENT_RUN_REPORT_DIR",
    "AGENT_REPORT_DIR",
)
GIT_TIMEOUT_SECONDS = 10
MAX_TEXT_BYTES = 160_000
MAX_RECORDED_PATHS = 20
MAX_EVIDENCE_FILES = 40
DEFAULT_EVIDENCE_CANDIDATE_PRIORITY_RANK = 3
CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
EDIT_TOOL_NAMES = {"apply_patch", "Bash", "bash", "python", "python3"}
PATCH_PATH_RE = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (?P<path>.+)$|"
    r"^\*\*\* Move to: (?P<move>.+)$",
    re.MULTILINE,
)
CODE_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.@+-]+/)*[A-Za-z0-9_.@+-]+\."
    r"(?:c|cc|cpp|cxx|go|h|hpp|java|js|jsx|kt|py|rs|sh|swift|ts|tsx))"
)
EDIT_COMMAND_RE = re.compile(
    r"(?is)(apply_patch|sed\s+-i|perl\s+-pi|git\s+mv|"
    r"\b(?:mv|cp|rm|touch)\s+|write_text\s*\(|open\s*\([^)]*[\"']w)"
)
CAUSE_EVIDENCE_SUFFIXES = {".md", ".txt"}
CAUSE_EVIDENCE_PREFIXES = (
    "documents/",
    "issues/open/",
    "issues/closed/",
    "notes/",
    "reports/agents/",
)
CAUSE_EVIDENCE_GLOBS = (
    "reports/agents/**/cause_investigation.md",
    "reports/agents/**/*hypothesis*.md",
)
RUN_LOCAL_EVIDENCE_NAMES = (
    "cause_investigation.md",
    "workflow_monitoring.md",
    "work_log.md",
)
REQUIRED_TOKEN_GROUPS = (
    ("Observation:",),
    ("Hypothesis:", "Root Cause:", "Cause:"),
    ("Expected Fix Surface:", "Selected Surface:", "Fix Surface Justification:"),
    ("Validation Before Edit:", "Support Evidence:"),
)
VALIDATION_FAILURE_CAUSE_TOKENS = (
    "failing_contract",
    "observation_level",
    "cause_classification",
    "intent_preservation",
    "evidence",
)


@dataclass(frozen=True)
class EditIntent:
    """One PreToolUse code-edit intent."""

    detected: bool
    tool_name: str
    command_digest: str
    code_paths: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceFile:
    """One cause investigation evidence candidate."""

    path: str
    valid: bool
    missing_groups: tuple[str, ...]
    mentions_target: bool


@dataclass(frozen=True)
class EvidenceDecision:
    """Cause evidence decision for one edit attempt."""

    status: str
    source: str
    files: tuple[EvidenceFile, ...]


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


def hook_event_name(payload: dict[str, object]) -> str:
    """Return hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) else ""


def tool_name(payload: dict[str, object]) -> str:
    """Return tool name."""
    value = payload.get("tool_name")
    return value if isinstance(value, str) else ""


def command_text(payload: dict[str, object]) -> str:
    """Return command-like payload text."""
    parts: list[str] = []
    collect_strings(payload, parts)
    return "\n".join(parts)


def collect_strings(value: object, parts: list[str]) -> None:
    """Collect bounded strings from nested hook payload values."""
    if isinstance(value, str):
        parts.append(value[:MAX_TEXT_BYTES])
        return
    if isinstance(value, dict):
        for nested in value.values():
            collect_strings(nested, parts)
        return
    if isinstance(value, list):
        for nested in value:
            collect_strings(nested, parts)


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
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def changed_files(root: Path) -> tuple[str, ...]:
    """Return changed tracked and untracked non-ignored paths."""
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(git_lines(root, args))
    return tuple(sorted(paths))


def code_path(path: str) -> bool:
    """Return whether a path is code-like."""
    return Path(path).suffix in CODE_SUFFIXES


def patch_paths(text: str) -> tuple[str, ...]:
    """Return file paths declared by an apply_patch payload."""
    paths: list[str] = []
    for match in PATCH_PATH_RE.finditer(text):
        raw = match.group("path") or match.group("move") or ""
        paths.append(raw.strip())
    return tuple(dict.fromkeys(paths))


def command_code_paths(text: str) -> tuple[str, ...]:
    """Return code-like path mentions from command text."""
    return tuple(dict.fromkeys(match.group("path") for match in CODE_PATH_RE.finditer(text)))


def edit_intent(payload: dict[str, object]) -> EditIntent:
    """Return whether this hook payload is about editing code."""
    name = tool_name(payload)
    text = command_text(payload)
    paths = patch_paths(text) if name == "apply_patch" else ()
    if not paths and (name in {"Bash", "bash", "python", "python3"} or EDIT_COMMAND_RE.search(text)):
        paths = command_code_paths(text)
    code_paths = tuple(path for path in paths if code_path(path))
    detected = bool(code_paths) and name in EDIT_TOOL_NAMES and (
        name == "apply_patch" or bool(EDIT_COMMAND_RE.search(text))
    )
    return EditIntent(
        detected=detected,
        tool_name=name,
        command_digest=fingerprint_json({"tool_name": name, "command": text}),
        code_paths=code_paths,
    )


def evidence_path(path: str) -> bool:
    """Return whether a path can carry cause investigation evidence."""
    if Path(path).suffix not in CAUSE_EVIDENCE_SUFFIXES:
        return False
    return path.startswith(CAUSE_EVIDENCE_PREFIXES)


def evidence_candidate_paths(root: Path) -> tuple[str, ...]:
    """Return changed or task-local cause evidence candidate paths."""
    paths = {path for path in changed_files(root) if evidence_path(path)}
    for report_dir in active_report_dirs(root):
        for name in RUN_LOCAL_EVIDENCE_NAMES:
            candidate = report_dir / name
            if candidate.is_file():
                paths.add(candidate.relative_to(root).as_posix())
    for pattern in CAUSE_EVIDENCE_GLOBS:
        for candidate in root.glob(pattern):
            if candidate.is_file():
                paths.add(candidate.relative_to(root).as_posix())
    return tuple(sorted(paths, key=lambda path: evidence_candidate_priority(root, path))[:MAX_EVIDENCE_FILES])


def active_report_dirs(root: Path) -> tuple[Path, ...]:
    """Return explicit current run directories under the repository root."""
    dirs: list[Path] = []
    root_resolved = root.resolve()
    for env_name in ACTIVE_REPORT_DIR_ENVS:
        raw_path = os.environ.get(env_name, "").strip()
        if not raw_path:
            continue
        report_dir = Path(raw_path)
        if not report_dir.is_absolute():
            report_dir = root / report_dir
        try:
            resolved = report_dir.resolve()
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        if resolved.is_dir() and resolved not in dirs:
            dirs.append(resolved)
    return tuple(dirs)


def evidence_candidate_priority(root: Path, path: str) -> tuple[int, int, str]:
    """Return priority for bounded evidence scanning."""
    name = Path(path).name
    if name == "cause_investigation.md":
        rank = 0
    elif "hypothesis" in name:
        rank = 1
    elif name == "workflow_monitoring.md":
        rank = 2
    else:
        rank = DEFAULT_EVIDENCE_CANDIDATE_PRIORITY_RANK
    try:
        mtime = (root / path).stat().st_mtime_ns
    except OSError:
        mtime = 0
    return (rank, -mtime, path)


def read_evidence_text(path: Path) -> str:
    """Read bounded text from one evidence path."""
    try:
        return path.read_text(encoding="utf-8")[:MAX_TEXT_BYTES]
    except OSError:
        return ""


def missing_token_groups(text: str) -> tuple[str, ...]:
    """Return missing cause investigation token groups."""
    missing: list[str] = []
    for group in REQUIRED_TOKEN_GROUPS:
        if not any(token in text for token in group):
            missing.append("|".join(group))
    return tuple(missing)


def mentions_target(text: str, paths: tuple[str, ...]) -> bool:
    """Return whether evidence mentions at least one target code path."""
    if not paths:
        return True
    for path in paths:
        name = Path(path).name
        if path in text or name in text:
            return True
    return False


def evidence_files(root: Path, intent: EditIntent) -> tuple[EvidenceFile, ...]:
    """Return evaluated cause evidence files."""
    files: list[EvidenceFile] = []
    for relative_path in evidence_candidate_paths(root):
        text = read_evidence_text(root / relative_path)
        missing = missing_token_groups(text)
        target_mentioned = mentions_target(text, intent.code_paths)
        files.append(
            EvidenceFile(
                path=relative_path,
                valid=not missing and target_mentioned,
                missing_groups=missing,
                mentions_target=target_mentioned,
            )
        )
    return tuple(files)


def cause_evidence_decision(root: Path, intent: EditIntent) -> EvidenceDecision:
    """Return cause evidence decision."""
    if os.environ.get(CONFIRMED_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return EvidenceDecision(status="pass", source="env_override", files=())
    files = evidence_files(root, intent)
    if any(file.valid for file in files):
        return EvidenceDecision(status="pass", source="artifact", files=files)
    return EvidenceDecision(status="fail", source="missing_or_incomplete", files=files)


def _log_entry(
    context: HookLogContext,
    payload: dict[str, object],
    intent: EditIntent,
    decision: EvidenceDecision,
) -> dict[str, object]:
    """Build one cause investigation hook JSONL entry."""
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    return {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "hook_log_namespace": context.runtime_namespace(),
        "timestamp": timestamp,
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fingerprint": payload_fingerprint,
        "checked": intent.detected,
        "code_edit_detected": intent.detected,
        "code_path_count": len(intent.code_paths),
        "code_paths": list(intent.code_paths[:MAX_RECORDED_PATHS]),
        "command_digest": intent.command_digest,
        "cause_evidence_status": decision.status,
        "cause_evidence_source": decision.source,
        "cause_evidence_files": [asdict(file) for file in decision.files[:MAX_RECORDED_PATHS]],
        "status": "fail" if intent.detected and decision.status != "pass" else "pass",
    }


def maybe_log(entry: dict[str, object], context: HookLogContext) -> None:
    """Append hook log unless disabled."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    context.append(entry)


def block_payload(intent: EditIntent, decision: EvidenceDecision) -> dict[str, object]:
    """Return a Codex hook block payload."""
    validation_tokens = ",".join(VALIDATION_FAILURE_CAUSE_TOKENS)
    return {
        "decision": "block",
        "reason": (
            "Cause investigation guard blocked a code edit before root-cause or "
            "hypothesis evidence was recorded. Create or update "
            "`reports/agents/<run-id>/cause_investigation.md`, an issue, or a "
            "design note with Observation, Hypothesis/Root Cause, Expected Fix "
            "Surface/Selected Surface, and Validation Before Edit/Support Evidence. "
            "For validation failures, classify the failing contract before repair "
            "and preserve intent instead of deleting tests or weakening oracles."
        ),
        "next_action": "write_cause_investigation_evidence_then_retry_edit",
        "remediation": [
            "Record Observation, Hypothesis or Root Cause, Expected Fix Surface or Selected Surface, and Validation Before Edit.",
            (
                "For failed validation/tests, also record failing_contract, "
                "observation_level, cause_classification, intent_preservation, "
                "and evidence for same-intent repair or escalation."
            ),
            "Use `reports/agents/<run-id>/cause_investigation.md`, an issue, or a design note as the durable evidence path.",
            "Retry the edit only after the evidence exists in the worktree.",
        ],
        "findings": [
            "CAUSE_INVESTIGATION_FINDING="
            f"missing_or_incomplete:{','.join(intent.code_paths[:MAX_RECORDED_PATHS])}:"
            f"evidence_source:{decision.source}",
            "VALIDATION_FAILURE_CAUSE_CLASSIFICATION_REQUIRED="
            f"{validation_tokens}",
        ],
    }


def main() -> int:
    """Run the cause investigation hook."""
    payload = load_payload()
    root = repo_root()
    context = HookLogContext(
        active_root=root,
        hook_name="cause_investigation_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    intent = edit_intent(payload)
    if not intent.detected:
        return 0
    decision = cause_evidence_decision(root, intent)
    maybe_log(_log_entry(context, payload, intent, decision), context)
    if decision.status != "pass":
        print(json.dumps(block_payload(intent, decision), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
