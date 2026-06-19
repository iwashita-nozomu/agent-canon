#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Warns when the AgentCanon log archive mount is absent without blocking hook execution.
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and mount policy
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves archive mount paths
# upstream implementation ../hooks.json invokes this hook at prompt and pre-tool boundaries
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates non-blocking warning behavior
# @dependency-end

"""Warn when the shared AgentCanon log archive is not mounted."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "agent_tools"
if TOOLS_DIR.is_dir():
    sys.path.insert(0, str(TOOLS_DIR))

from runtime_log_paths import (  # noqa: E402
    HOOK_ARCHIVE_DIR_ENV,
    mounted_log_archive_root,
)

CANON_ROOT_ENV = "AGENT_CANON_LOG_ARCHIVE_WARNING_CANON_ROOT"
DISABLE_ENV = "AGENT_CANON_DISABLE_LOG_ARCHIVE_MOUNT_WARNING"
GIT_ROOT_TIMEOUT_SECONDS = 5


def consume_stdin() -> None:
    """Consume the hook payload so the dispatcher pipe stays clean."""
    if not sys.stdin.isatty():
        sys.stdin.read()


def env_truthy(name: str) -> bool:
    """Return whether an environment flag is enabled."""
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes"}


def repo_root() -> Path:
    """Return the active repository root when Git can resolve it."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return Path.cwd().resolve()


def canon_root() -> Path:
    """Return the AgentCanon checkout whose archive mount should exist."""
    override = os.environ.get(CANON_ROOT_ENV, "").strip()
    if override:
        return Path(override).resolve()
    root = repo_root()
    vendored = root / "vendor" / "agent-canon"
    if (vendored / "tools" / "agent_tools" / "runtime_log_archive_git.py").is_file():
        return vendored.resolve()
    return Path(__file__).resolve().parents[2]


def archive_status(root: Path) -> tuple[str, Path]:
    """Return mount status and the path the agent should repair."""
    override = os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip()
    if override:
        archive = Path(override).expanduser().resolve()
        if archive.is_dir() and (archive / ".git").exists():
            return "mounted", archive
        return "override-missing", archive
    archive = mounted_log_archive_root(root).resolve()
    if not archive.exists():
        return "missing", archive
    if not archive.is_dir():
        return "not-directory", archive
    if not (archive / ".git").exists():
        return "not-git-clone", archive
    return "mounted", archive


def warning_payload(status: str, archive: Path, root: Path) -> dict[str, object]:
    """Return a non-blocking Codex hook warning."""
    return {
        "decision": "approve",
        "reason": (
            "AgentCanon log archive mount is not ready "
            f"(LOG_ARCHIVE_MOUNT_STATUS={status}, path={archive}). "
            "Before accumulating hook/eval/report logs, mount or ensure the shared log archive."
        ),
        "next_action": "ensure_agent_canon_log_archive_mount_before_accumulating_logs",
        "remediation": [
            f"From AgentCanon root `{root}` run: `python3 tools/agent_tools/runtime_log_archive_git.py ensure`.",
            (
                "From a parent repo run: "
                "`python3 vendor/agent-canon/tools/agent_tools/runtime_log_archive_git.py "
                "--canon-root vendor/agent-canon ensure`."
            ),
            "This warning is non-blocking; do not disable hooks to continue read-only or validation work.",
        ],
    }


def main() -> int:
    """Run the non-blocking mount warning hook."""
    consume_stdin()
    if env_truthy(DISABLE_ENV):
        return 0
    root = canon_root()
    status, archive = archive_status(root)
    if status == "mounted":
        return 0
    json.dump(warning_payload(status, archive, root), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
