#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Runs a non-blocking Codex runtime summary export at hook boundaries.
# upstream implementation ../../tools/agent_tools/export_codex_runtime_summary.py exports bounded runtime summaries
# upstream implementation ./hook_dispatcher.py invokes this hook from Stop
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and mount policy
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook wiring
# @dependency-end
"""Best-effort Codex runtime summary hook."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DISABLE_ENV = "AGENT_CANON_DISABLE_CODEX_RUNTIME_SUMMARY_LOG"
THREAD_ENV = "CODEX_THREAD_ID"
CANON_ROOT_ENV = "AGENT_CANON_CODEX_RUNTIME_CANON_ROOT"
HISTORY_ENV = "AGENT_CANON_CODEX_HISTORY_JSONL"
SQLITE_ENV = "AGENT_CANON_CODEX_SQLITE_LOG"
RECENT_DAYS_ENV = "AGENT_CANON_CODEX_RUNTIME_RECENT_DAYS"
HOOK_TIMEOUT_SECONDS = 8
GIT_REV_PARSE_TIMEOUT_SECONDS = 5


def consume_stdin() -> None:
    """Consume hook payload so parent pipes do not stall."""
    if not sys.stdin.isatty():
        sys.stdin.read()


def env_truthy(name: str) -> bool:
    """Return whether an environment flag is enabled."""
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes"}


def repo_root() -> Path:
    """Return the active source repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_REV_PARSE_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path.cwd().resolve()


def exporter_path() -> Path:
    """Return the AgentCanon exporter script path."""
    return Path(__file__).resolve().parents[2] / "tools" / "agent_tools" / "export_codex_runtime_summary.py"


def command(source_root: Path, thread_id: str) -> list[str]:
    """Return the exporter command."""
    cmd = [
        sys.executable,
        str(exporter_path()),
        "--source-root",
        str(source_root),
        "--thread-id",
        thread_id,
    ]
    canon_root = os.environ.get(CANON_ROOT_ENV, "").strip()
    if canon_root:
        cmd.extend(["--canon-root", canon_root])
    history = os.environ.get(HISTORY_ENV, "").strip()
    if history:
        cmd.extend(["--history-jsonl", history])
    sqlite_log = os.environ.get(SQLITE_ENV, "").strip()
    if sqlite_log:
        cmd.extend(["--sqlite-log", sqlite_log])
    recent_days = os.environ.get(RECENT_DAYS_ENV, "").strip()
    if recent_days:
        cmd.extend(["--recent-days", recent_days])
    return cmd


def main() -> int:
    """Run the non-blocking summary export."""
    consume_stdin()
    if env_truthy(DISABLE_ENV):
        return 0
    thread_id = os.environ.get(THREAD_ENV, "").strip()
    if not thread_id:
        return 0
    subprocess.run(
        command(repo_root(), thread_id),
        check=False,
        capture_output=True,
        timeout=HOOK_TIMEOUT_SECONDS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
