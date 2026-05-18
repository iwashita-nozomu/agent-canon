#!/usr/bin/env python3
# @dependency-start
# responsibility Provides Canon-owned append-only hook event log paths and IDs.
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HOOK_RESULTS_DIR_ENV = "AGENT_CANON_HOOK_RESULTS_DIR"
HOOK_RUN_NAMESPACE_ENV = "AGENT_CANON_HOOK_RUN_NAMESPACE"
FINGERPRINT_HEX_LENGTH = 12
RUN_ID_DIGEST_LENGTH = 10
RUN_ID_NONCE_LENGTH = 10
NAMESPACE_HASH_LENGTH = 8
MAX_NAMESPACE_LENGTH = 80


def safe_slug(value: str) -> str:
    """Return a filesystem-safe runtime namespace segment."""
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-").casefold()
    return slug[:MAX_NAMESPACE_LENGTH].strip("._-") or "unknown-runtime"


def utc_now() -> str:
    """Return one UTC timestamp for hook log entries."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

    def canon_root(self) -> Path:
        """Return the AgentCanon checkout that owns durable hook evidence."""
        root = self.active_root.resolve()
        vendored = root / "vendor" / "agent-canon"
        if (vendored / "agents" / "evals" / "results").is_dir():
            return vendored
        return root

    def durable_results_dir(self) -> Path:
        """Return the AgentCanon-owned durable hook-result directory."""
        return self.canon_root() / "agents" / "evals" / "results" / "hook-runs"

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
        return self.results_dir() / self.runtime_namespace() / f"{self.hook_name}.jsonl"

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
        return self.fallback_namespace()

    def compose_project_name(self) -> str:
        """Return the generated devcontainer Compose project name when available."""
        compose = self.active_root.resolve() / ".devcontainer" / "docker-compose.generated.yml"
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

    def fallback_namespace(self) -> str:
        """Return a stable namespace when the runtime did not provide one."""
        root = self.active_root.resolve()
        hostname = os.environ.get("HOSTNAME", "").strip() or "host"
        return safe_slug(f"{root.name}-{hostname}-{short_hash(str(root))}")

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
        path = self.result_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            json.dump(entry, stream, sort_keys=True, default=str)
            stream.write("\n")
