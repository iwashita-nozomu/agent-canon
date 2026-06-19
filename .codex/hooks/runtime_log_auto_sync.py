#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Runs best-effort unattended runtime log archive sync at Stop.
# upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py owns archive sync, report copy, commit, and push behavior
# upstream implementation ./hook_dispatcher.py invokes this hook from Stop
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and automation policy
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates quiet fail-open behavior
# @dependency-end
"""Best-effort runtime log archive sync hook."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DISABLE_ENV = "AGENT_CANON_DISABLE_RUNTIME_LOG_AUTO_SYNC"
NO_PUSH_ENV = "AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_NO_PUSH"
VERBOSE_ENV = "AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_VERBOSE"
TIMEOUT_ENV = "AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_TIMEOUT_SECONDS"
CANON_ROOT_ENV = "AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_CANON_ROOT"
DEFAULT_TIMEOUT_SECONDS = 55
GIT_REV_PARSE_TIMEOUT_SECONDS = 5


def consume_stdin() -> None:
    """Consume hook payload so the dispatcher pipe stays clean."""
    if not sys.stdin.isatty():
        sys.stdin.read()


def env_truthy(name: str) -> bool:
    """Return whether an environment flag is enabled."""
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "on"}


def timeout_seconds() -> int:
    """Return the bounded auto-sync subprocess timeout."""
    raw = os.environ.get(TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


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


def canon_root(source_root: Path) -> Path:
    """Return the AgentCanon root that owns the archive manager."""
    override = os.environ.get(CANON_ROOT_ENV, "").strip()
    if override:
        return Path(override).resolve()
    vendored = source_root / "vendor" / "agent-canon"
    if (vendored / "tools" / "agent_tools" / "runtime_log_archive_git.py").is_file():
        return vendored.resolve()
    return Path(__file__).resolve().parents[2]


def sync_command(source_root: Path, canon: Path) -> list[str]:
    """Return the unattended sync command."""
    command = [
        sys.executable,
        str(canon / "tools" / "agent_tools" / "runtime_log_archive_git.py"),
        "--source-root",
        str(source_root),
        "--canon-root",
        str(canon),
        "sync",
    ]
    if env_truthy(NO_PUSH_ENV):
        command.append("--no-push")
    return command


def visible_payload(message: str) -> dict[str, object]:
    """Return optional visible hook context for debug runs."""
    return {
        "decision": "approve",
        "reason": message,
        "next_action": "runtime_log_auto_sync_review_optional",
    }


def main() -> int:
    """Run unattended archive sync without blocking the Stop hook."""
    consume_stdin()
    if env_truthy(DISABLE_ENV):
        return 0
    source = repo_root()
    canon = canon_root(source)
    try:
        result = subprocess.run(
            sync_command(source, canon),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        if env_truthy(VERBOSE_ENV):
            json.dump(visible_payload(f"runtime log auto-sync skipped: {type(exc).__name__}: {exc}"), sys.stdout)
            sys.stdout.write("\n")
        return 0
    if result.returncode != 0 and env_truthy(VERBOSE_ENV):
        detail = (result.stderr.strip() or result.stdout.strip()).splitlines()[:8]
        json.dump(visible_payload("runtime log auto-sync failed:\n" + "\n".join(detail)), sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
