#!/usr/bin/env python3
# @dependency-start
# responsibility Provides Canon-owned append-only hook event log paths and IDs.
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# downstream implementation ./oop_readability_guard.py records OOP hook outcomes
# downstream implementation ./skill_usage_logger.py records skill hook outcomes
# @dependency-end
"""Shared hook event log primitives."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HOOK_RESULTS_DIR_ENV = "AGENT_CANON_HOOK_RESULTS_DIR"
FINGERPRINT_HEX_LENGTH = 12
RUN_ID_DIGEST_LENGTH = 10
RUN_ID_NONCE_LENGTH = 10


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

    def results_dir(self) -> Path:
        """Return the hook-result directory."""
        override = os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip()
        if override:
            return Path(override)
        return self.canon_root() / "agents" / "evals" / "results" / "hook-runs"

    def result_path(self) -> Path:
        """Return this hook's JSONL log path."""
        if self.override_path:
            return Path(self.override_path)
        return self.results_dir() / f"{self.hook_name}.jsonl"

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
