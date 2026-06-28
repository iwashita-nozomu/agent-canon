#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Provides Canon-owned append-only hook event log paths and IDs.
# upstream design ../../documents/runtime-log-archive.md runtime log archive contract
# upstream design ../../documents/runtime-log-archive.md hook result accumulation contract
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves archive paths
# upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py selects and preserves archive branches
# downstream implementation ./oop_readability_guard.py records OOP hook outcomes
# downstream implementation ./module_boundary_guard.py records module boundary outcomes
# downstream implementation ./library_implementation_guard.py records protected library rewrite outcomes
# downstream implementation ./helper_first_guard.py records helper-first implementation outcomes
# downstream implementation ./cause_investigation_guard.py records cause investigation outcomes
# downstream implementation ./notebook_quality_guard.py records notebook hook outcomes
# downstream implementation ./style_checker_guard.py records changed-file style outcomes
# downstream implementation ./skill_usage_logger.py records skill hook outcomes
# @dependency-end
"""Shared hook event log primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "agent_tools"
if TOOLS_DIR.is_dir():
    sys.path.insert(0, str(TOOLS_DIR))

from runtime_log_paths import (  # noqa: E402
    HOOK_ARCHIVE_DIR_ENV,
    agent_canon_root,
    codex_trace_key,
    hook_log_file_name,
    hook_results_dir,
    mounted_log_archive_root,
    repo_log_key,
    source_git_head,
)

HOOK_RESULTS_DIR_ENV = "AGENT_CANON_HOOK_RESULTS_DIR"
HOOK_RUN_NAMESPACE_ENV = "AGENT_CANON_HOOK_RUN_NAMESPACE"
HOOK_SOURCE_ROOT_ENV = "AGENT_CANON_HOOK_SOURCE_ROOT"
FINGERPRINT_HEX_LENGTH = 12
RUN_ID_DIGEST_LENGTH = 10
RUN_ID_NONCE_LENGTH = 10
NAMESPACE_HASH_LENGTH = 8
MAX_NAMESPACE_LENGTH = 80
ARCHIVE_ENSURE_TIMEOUT_SECONDS = 20


def safe_slug(value: str) -> str:
    """Return a filesystem-safe runtime namespace segment."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-").casefold()
    return slug[:MAX_NAMESPACE_LENGTH].strip("._-") or "unknown-runtime"


def utc_now() -> str:
    """Return one UTC timestamp for hook log entries."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def compact_timestamp(timestamp: str) -> str:
    """Return a filename-safe timestamp segment."""
    return (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace("+00:00", "Z")
        .replace(".", "")
    )


def fingerprint_json(value: object) -> str:
    """Return a stable short hash for JSON-compatible hook data."""
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_LENGTH]


def short_hash(value: str) -> str:
    """Return a stable short hash for runtime namespace disambiguation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:NAMESPACE_HASH_LENGTH]


@dataclass(frozen=True)
class HookLogContext:
    """Resolve one hook's Canon-owned append-only log destination."""

    active_root: Path
    hook_name: str
    override_path: str = ""

    def source_root(self) -> Path:
        """Return the repository whose hook evidence should be keyed."""
        override = os.environ.get(HOOK_SOURCE_ROOT_ENV, "").strip()
        if override:
            return Path(override).resolve()
        return self.active_root.resolve()

    def canon_root(self) -> Path:
        """Return the AgentCanon checkout that owns durable hook evidence."""
        return agent_canon_root(self.source_root())

    def durable_results_dir(self) -> Path:
        """Return the durable hook-result archive directory."""
        return hook_results_dir(self.source_root(), self.canon_root())

    def archive_root(self) -> Path:
        """Return the archive root used for durable hook logs."""
        override = os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip()
        if override:
            return Path(override).resolve()
        return mounted_log_archive_root(self.canon_root())

    def explicit_log_sink(self) -> bool:
        """Return whether this hook writes to a caller-owned log path."""
        return bool(self.override_path or os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip())

    def ensure_archive_branch(self) -> None:
        """Ensure durable hook writes happen on the expected archive branch."""
        if self.explicit_log_sink():
            return
        archive_root = self.archive_root()
        if os.environ.get(HOOK_ARCHIVE_DIR_ENV, "").strip() and not (archive_root / ".git").exists():
            return
        script = TOOLS_DIR / "runtime_log_archive_git.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--source-root",
                str(self.source_root()),
                "--canon-root",
                str(self.canon_root()),
                "--archive-root",
                str(archive_root),
                "ensure",
                "--no-fetch",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=ARCHIVE_ENSURE_TIMEOUT_SECONDS,
        )

    def results_dir(self) -> Path:
        """Return the hook-result directory."""
        override = os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip()
        if override:
            return Path(override)
        return self.durable_results_dir()

    def result_path(self) -> Path:
        """Return this hook's JSONL log path."""
        if self.override_path:
            return Path(self.override_path)
        return self.results_dir() / self.runtime_namespace() / hook_log_file_name(
            self.hook_name,
            self.canon_root(),
        )

    def runtime_namespace(self) -> str:
        """Return the runtime shard name for append-only hook logs."""
        explicit = os.environ.get(HOOK_RUN_NAMESPACE_ENV, "").strip()
        if explicit:
            return safe_slug(explicit)
        for env_name in ("DEVCONTAINER_PROJECT_NAME", "COMPOSE_PROJECT_NAME"):
            value = os.environ.get(env_name, "").strip()
            if value:
                return safe_slug(value)
        compose_name = self.compose_project_name()
        if compose_name:
            return safe_slug(compose_name)
        if self.override_path:
            return "direct-log-override"
        raise RuntimeError(
            "hook runtime namespace is required; set "
            f"{HOOK_RUN_NAMESPACE_ENV}, DEVCONTAINER_PROJECT_NAME, or COMPOSE_PROJECT_NAME"
        )

    def compose_project_name(self) -> str:
        """Return the generated devcontainer Compose project name when available."""
        compose = self.source_root() / ".devcontainer" / "docker-compose.generated.yml"
        if not compose.is_file():
            return ""
        try:
            for line in compose.read_text(encoding="utf-8").splitlines():
                match = re.match(r"^\s*name:\s*[\"']?([^\"'\s#]+)", line)
                if match:
                    return match.group(1)
        except OSError:
            return ""
        return ""

    def run_id(self, timestamp: str, payload_fingerprint: str) -> str:
        """Return a unique hook run id."""
        digest = fingerprint_json(
            {
                "hook_name": self.hook_name,
                "payload_fingerprint": payload_fingerprint,
                "timestamp": timestamp,
            }
        )[:RUN_ID_DIGEST_LENGTH]
        nonce = uuid.uuid4().hex[:RUN_ID_NONCE_LENGTH]
        return f"hook-{compact_timestamp(timestamp)}-{digest}-{nonce}"

    def append(self, entry: dict[str, object]) -> None:
        """Append one JSONL entry."""
        try:
            self.ensure_archive_branch()
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return
        path = self.result_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        source_root = self.source_root()
        entry.setdefault("source_repo_key", repo_log_key(source_root))
        trace_key = codex_trace_key()
        if trace_key:
            entry.setdefault("codex_trace_key", trace_key)
            entry.setdefault("codex_thread_id", trace_key)
        canon_head = source_git_head(self.canon_root())
        if canon_head:
            entry.setdefault("agent_canon_git_head", canon_head)
        git_head = source_git_head(source_root)
        if git_head:
            entry.setdefault("source_git_head", git_head)
        with path.open("a", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True, default=str)
            stream.write("\n")
