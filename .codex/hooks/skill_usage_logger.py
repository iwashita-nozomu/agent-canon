#!/usr/bin/env python3
# @dependency-start
# responsibility Logs Codex skill usage signals from hook payloads.
# upstream implementation ../hooks.json invokes this hook at prompt and stop boundaries.
# upstream design ../../agents/evals/README.md requires skill-use eval evidence.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook logging.
# @dependency-end

"""Append local JSONL records for skill usage observed by Codex hooks."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from hook_event_log import HookLogContext, fingerprint_json, utc_now

LOG_PATH_ENV = "AGENT_CANON_SKILL_LOG_PATH"
WORKFLOW_MONITOR_REPORT_DIR_ENV = "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
SKILL_TOKEN_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9_-]*)")
SKILLS_FIELD_RE = re.compile(r"(?:^|\s)(?:skills|skill_invocation)=([^\s]+)")
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
GIT_ROOT_TIMEOUT_SECONDS = 5


def load_payload() -> dict[str, object]:
    """Read one JSON hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def repo_root() -> Path:
    """Resolve the active repository root for hook logs."""
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
    return value if isinstance(value, str) and value else "UnknownHookEvent"


def text_values(value: object) -> list[str]:
    """Return text leaves from nested hook payload data."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for child in value.values():
            values.extend(text_values(child))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for child in value:
            values.extend(text_values(child))
        return values
    return []


def extract_skill_ids(text: str) -> set[str]:
    """Extract normalized skill ids from one text payload."""
    skills = {match.group(1).strip("-_") for match in SKILL_TOKEN_RE.finditer(text)}
    for match in SKILLS_FIELD_RE.finditer(text):
        raw_values = match.group(1).split(",")
        for raw_value in raw_values:
            value = raw_value.strip().strip("`'\"[](){}")
            value = value.removeprefix("$").strip("-_")
            if value and value != "-":
                skills.add(value)
    return {skill for skill in skills if SKILL_ID_RE.fullmatch(skill)}


def observed_text(payload: dict[str, object]) -> list[str]:
    """Return hook payload text fields relevant for skill-use discovery."""
    texts: list[str] = []
    for key in ("prompt", "last_assistant_message", "message", "tool_input"):
        if key in payload:
            texts.extend(text_values(payload[key]))
    return texts


def observed_skills(payload: dict[str, object]) -> list[str]:
    """Return sorted unique skill ids observed in a hook payload."""
    skills: set[str] = set()
    for text in observed_text(payload):
        skills.update(extract_skill_ids(text))
    return sorted(skills)


def default_log_path(root: Path) -> Path:
    """Return the skill usage log path."""
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return HookLogContext(root, "skill_usage", override).result_path()


def _log_append_log(root: Path, entry: dict[str, object]) -> None:
    """Append one skill usage JSONL entry without blocking runtime progress."""
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


def workflow_monitor_path(root: Path) -> Path:
    """Return the canonical workflow monitor tool path."""
    return root / "tools" / "agent_tools" / "workflow_monitor.py"


def workflow_monitor_report_dir() -> str:
    """Return the optional run-bundle report dir for behavior evidence."""
    return os.environ.get(WORKFLOW_MONITOR_REPORT_DIR_ENV, "").strip()


def append_workflow_monitor_events(root: Path, skills: list[str]) -> int:
    """Append skill invocation behavior events when a run bundle is active."""
    report_dir = workflow_monitor_report_dir()
    monitor = workflow_monitor_path(root)
    if not report_dir or not monitor.is_file() or not skills:
        return 0
    event_count = 0
    for skill in skills:
        result = subprocess.run(
            [
                sys.executable,
                str(monitor),
                "--report-dir",
                report_dir,
                "--behavior-event",
                f"skill_invocation=${skill} status=observed source=codex_hook",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_ROOT_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            event_count += 1
    return event_count


def main() -> int:
    """Append one skill usage hook log entry."""
    payload = load_payload()
    root = repo_root()
    skills = observed_skills(payload)
    if not skills:
        return 0
    workflow_event_count = append_workflow_monitor_events(root, skills)
    timestamp = utc_now()
    payload_fingerprint = fingerprint_json(payload)
    context = HookLogContext(root, "skill_usage", os.environ.get(LOG_PATH_ENV, "").strip())
    _log_append_log(
        root,
        {
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "timestamp": timestamp,
            "event": hook_event_name(payload),
            "skills": skills,
            "skill_count": len(skills),
            "payload_fingerprint": payload_fingerprint,
            "status": "pass",
            "workflow_monitor_event_count": workflow_event_count,
            "workflow_monitor_report_dir": workflow_monitor_report_dir(),
            "root": str(root),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
