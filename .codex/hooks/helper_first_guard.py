#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks helper-function-first edits before ownership or boundary evidence exists.
# upstream implementation ../hooks.json invokes this hook for PostToolUse and Stop.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# upstream implementation ../../tools/agent_tools/helper_function_inventory.py classifies helper symbols.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates helper-first hook behavior.
# @dependency-end
"""Guard against helper-function-first implementation drift."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "agent_tools"))

from hook_event_log import HookLogContext, fingerprint_json, utc_now  # noqa: E402
from task_authority import (  # noqa: E402
    TaskAuthority,
    helper_authority_matches,
    load_task_authority,
)

PAYLOAD_STATUS_KEY = "_agent_canon_payload_status"
PAYLOAD_STATUS_VALID = "valid"
PAYLOAD_STATUS_EMPTY = "empty"
PAYLOAD_STATUS_INVALID_JSON = "invalid_json"
LOG_PATH_ENV = "AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
GIT_TIMEOUT_SECONDS = 10
CHECK_TIMEOUT_SECONDS = 30
MAX_OUTPUT_LINES = 12
MAX_RECORDED_HELPERS = 20
EDIT_TOOL_NAMES = {"apply_patch", "python", "python3", "Bash", "bash"}
EDIT_COMMAND_PATTERN = re.compile(
    r"(?is)(apply_patch|python3?\s+|ruff\s+.*--fix|git\s+mv|mv\s+|cp\s+|"
    r"touch\s+|rm\s+|sed\s+-i|perl\s+-pi)"
)
CHECKER_COMMAND_RE = re.compile(
    r"(?is)(helper_first_guard\.py|helper_function_inventory\.py|"
    r"tool_rejection_preflight\.py)"
)
EVIDENCE_SUFFIXES = {".md", ".toml", ".yaml", ".yml"}
EVIDENCE_PATHS = {"responsibility-scope.toml", "tools/catalog.yaml"}
EVIDENCE_PREFIXES = ("documents/", "agents/", "issues/", "tests/")
IGNORED_PARTS = {".git", "__pycache__", ".pytest_cache", "reports", "target", "vendor"}


@dataclass(frozen=True)
class HelperFirstFinding:
    """One helper-first hook finding."""

    path: str
    line: int
    qualname: str
    verdict: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "HELPER_FIRST_FINDING="
            f"{self.path}:{self.line}:{self.qualname}:{self.verdict}:{self.detail}"
        )


@dataclass(frozen=True)
class HelperAuthorityCheck:
    """One helper-authority comparison result."""

    path: str
    qualname: str
    matched: bool
    detail: str


@dataclass(frozen=True)
class InventoryRun:
    """Helper inventory execution result for one hook pass."""

    command: tuple[str, ...]
    returncode: int
    output: str
    records: tuple[dict[str, object], ...]
    findings: tuple[HelperFirstFinding, ...]


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
    """Return whether this hook should inspect helper-first edits."""
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
    """Return changed tracked and untracked paths."""
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        names.update(git_lines(root, args))
    return tuple(sorted(path for path in names if visible_path(path)))


def visible_path(path: str) -> bool:
    """Return whether one changed path is visible to this guard."""
    return not (set(Path(path).parts) & IGNORED_PARTS)


def python_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return visible changed Python paths."""
    return tuple(path for path in paths if path.endswith(".py"))


def evidence_changed(paths: tuple[str, ...]) -> bool:
    """Return whether helper edits carry boundary or ownership evidence."""
    for path in paths:
        if path in EVIDENCE_PATHS:
            return True
        if path.startswith(EVIDENCE_PREFIXES) and Path(path).suffix in EVIDENCE_SUFFIXES:
            return True
    return False


def inventory_command(root: Path) -> tuple[str, ...]:
    """Return the helper inventory command."""
    return (
        "python3",
        str(root / "tools" / "agent_tools" / "helper_function_inventory.py"),
        "--root",
        str(root),
        "--changed",
        "--baseline-ref",
        "HEAD",
        "--format",
        "json",
    )


def run_inventory(root: Path) -> tuple[tuple[str, ...], int, str]:
    """Run helper inventory and return command, status, and output."""
    command = inventory_command(root)
    if not Path(command[1]).is_file():
        return command, 0, json.dumps({"records": [], "tool_status": "missing"})
    result = subprocess.run(
        list(command),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    return command, result.returncode, result.stdout + result.stderr


def inventory_records(output: str) -> tuple[dict[str, object], ...]:
    """Return record dicts from helper inventory JSON."""
    try:
        payload = json.loads(output or "{}")
    except json.JSONDecodeError:
        return ()
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return ()
    return tuple(record for record in records if isinstance(record, dict))


def record_verdict(record: dict[str, object]) -> str:
    """Return helper inventory verdict from one JSON record."""
    if bool(record.get("redundant_helper")):
        return "redundant_helper"
    if bool(record.get("helper_candidate")):
        return "auto_helper"
    if bool(record.get("needs_user_judgment")):
        return "needs_user_judgment"
    return str(record.get("verdict") or "not_helper")


def implementation_order_findings(
    records: tuple[dict[str, object], ...],
    *,
    boundary_evidence: bool,
    authority: TaskAuthority | None,
) -> tuple[HelperFirstFinding, ...]:
    """Return helper-first findings from helper inventory records."""
    findings: list[HelperFirstFinding] = []
    for candidate in implementation_order_candidates(records):
        matched, detail = helper_authority_matches(
            authority,
            path=candidate.path,
            qualname=candidate.qualname,
        )
        if matched:
            continue
        findings.append(
            HelperFirstFinding(
                path=candidate.path,
                line=candidate.line,
                qualname=candidate.qualname,
                verdict=candidate.verdict,
                detail=f"{candidate.detail}:boundary_evidence:{str(boundary_evidence).lower()}:{detail}",
            )
        )
    return tuple(findings)


def helper_authority_checks(
    records: tuple[dict[str, object], ...],
    authority: TaskAuthority | None,
) -> tuple[HelperAuthorityCheck, ...]:
    """Return helper authority comparison rows for hook logs."""
    checks: list[HelperAuthorityCheck] = []
    for candidate in implementation_order_candidates(records):
        matched, detail = helper_authority_matches(
            authority,
            path=candidate.path,
            qualname=candidate.qualname,
        )
        checks.append(
            HelperAuthorityCheck(
                path=candidate.path,
                qualname=candidate.qualname,
                matched=matched,
                detail=detail,
            )
        )
    return tuple(checks)


def implementation_order_candidates(
    records: tuple[dict[str, object], ...],
) -> tuple[HelperFirstFinding, ...]:
    """Return detected helper-like implementation-order candidate records."""
    findings: list[HelperFirstFinding] = []
    for record in records:
        verdict = record_verdict(record)
        if verdict not in {"auto_helper", "needs_user_judgment", "redundant_helper"}:
            continue
        if str(record.get("kind") or "function") != "function":
            continue
        if str(record.get("domain") or "") == "test":
            continue
        findings.append(
            HelperFirstFinding(
                path=str(record.get("path") or ""),
                line=int(record.get("line") or 0),
                qualname=str(record.get("qualname") or record.get("name") or ""),
                verdict=verdict,
                detail=implementation_order_detail(record),
            )
        )
    return tuple(findings)


def implementation_order_detail(record: dict[str, object]) -> str:
    """Return compact prompt-improvement detail for one helper-first record."""
    parts = [
        f"domain:{record.get('domain') or 'unknown'}",
        f"role:{record.get('role') or 'unknown'}",
        f"candidate:{record.get('candidate_rule') or 'none'}",
        f"judgment:{record.get('judgment_rule') or 'none'}",
        f"redundancy:{record.get('redundancy_rule') or 'none'}",
        f"incoming:{record.get('incoming_count') or 0}",
        f"specialization:{record.get('specialization') or 'unknown'}",
    ]
    return ":".join(parts)


def _log_entry(
    context: HookLogContext,
    payload: dict[str, object],
    changed_paths: tuple[str, ...],
    changed_python_paths: tuple[str, ...],
    inventory_run: InventoryRun,
    *,
    checked: bool,
    authority: TaskAuthority | None,
) -> dict[str, object]:
    """Build one helper-first hook JSONL entry."""
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    candidates = implementation_order_candidates(inventory_run.records)
    authority_checks = helper_authority_checks(inventory_run.records, authority)
    return {
        "hook_run_id": context.run_id(timestamp, payload_fingerprint),
        "hook_log_namespace": context.runtime_namespace(),
        "timestamp": timestamp,
        "event": hook_event_name(payload),
        "tool_name": tool_name(payload),
        "payload_status": payload_status(payload),
        "payload_fingerprint": payload_fingerprint,
        "checked": checked,
        "changed_file_count": len(changed_paths),
        "changed_python_count": len(changed_python_paths),
        "boundary_evidence_changed": evidence_changed(changed_paths),
        "task_authority_path": str(authority.path) if authority is not None else "",
        "inventory_command": list(inventory_run.command),
        "inventory_returncode": inventory_run.returncode,
        "inventory_output_snippet": "\n".join(inventory_run.output.splitlines()[:MAX_OUTPUT_LINES]),
        "helper_record_count": len(inventory_run.records),
        "helper_candidate_record_count": len(candidates),
        "helper_candidate_records": [
            candidate.__dict__ for candidate in candidates[:MAX_RECORDED_HELPERS]
        ],
        "helper_authority_checks": [
            check.__dict__ for check in authority_checks[:MAX_RECORDED_HELPERS]
        ],
        "helper_first_candidate_count": len(inventory_run.findings),
        "helper_first_records": [
            finding.__dict__ for finding in inventory_run.findings[:MAX_RECORDED_HELPERS]
        ],
        "status": "fail" if inventory_run.returncode != 0 or inventory_run.findings else "pass",
    }


def maybe_log(entry: dict[str, object], context: HookLogContext) -> None:
    """Append hook log unless disabled."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip():
        return
    context.append(entry)


def block_payload(findings: tuple[HelperFirstFinding, ...]) -> dict[str, object]:
    """Return a Codex hook block payload."""
    return {
        "decision": "block",
        "reason": (
            "Helper-first guard blocked helper-like function additions before "
            "ownership, module boundary, issue, docs, or test evidence was present. "
            "Define the owning object/module contract first, reuse existing helpers, "
            "or add boundary evidence before continuing."
        ),
        "next_action": "add_boundary_or_reuse_evidence_then_retry",
        "remediation": [
            "Identify the owning module or object before adding helper-like functions.",
            "Search for existing helpers and extend them when possible.",
            "Add helper_change authority tied to helper path, qualname, owner, caller, existing-helper gap, and tests.",
        ],
        "findings": [finding.render() for finding in findings],
    }


def main() -> int:
    """Run the helper-first hook."""
    payload = load_payload()
    root = repo_root()
    context = HookLogContext(
        active_root=root,
        hook_name="helper_first_guard",
        override_path=os.environ.get(LOG_PATH_ENV, ""),
    )
    if not should_check(payload):
        return 0
    paths = changed_files(root)
    python_path_list = python_paths(paths)
    checked = bool(python_path_list)
    inventory_run = InventoryRun(command=(), returncode=0, output="", records=(), findings=())
    if checked:
        authority = load_task_authority(root)
        command, returncode, output = run_inventory(root)
        records = inventory_records(output)
        findings = implementation_order_findings(
            records,
            boundary_evidence=evidence_changed(paths),
            authority=authority,
        )
        inventory_run = InventoryRun(
            command=command,
            returncode=returncode,
            output=output,
            records=records,
            findings=findings,
        )
    maybe_log(
        _log_entry(
            context,
            payload,
            paths,
            python_path_list,
            inventory_run,
            checked=checked,
            authority=load_task_authority(root),
        ),
        context,
    )
    if inventory_run.returncode != 0:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": inventory_run.output,
                    "next_action": "fix_helper_inventory_command_then_retry",
                    "remediation": [
                        "Run `python3 tools/agent_tools/helper_function_inventory.py --root . --changed --baseline-ref HEAD`.",
                        "Fix the inventory command failure before continuing the edit.",
                    ],
                }
            )
        )
    elif inventory_run.findings:
        print(json.dumps(block_payload(inventory_run.findings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
