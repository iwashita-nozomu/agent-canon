#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Provides Canon-owned append-only hook event log paths and IDs.
# upstream design ../../documents/runtime/runtime-log-archive.md runtime log archive contract
# upstream design ../../documents/runtime/runtime-log-archive.md hook result accumulation contract
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves archive paths
# downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py checkpoints immutable per-event spool files
# downstream implementation ./hook_dispatcher.py creates one bounded context per active event
# downstream implementation ../../tools/agent_tools/hook_safety.py keeps prompt/command values out of spool telemetry
# downstream design ../../documents/runtime/runtime-log-archive.md assigns archive work to explicit checkpoints
# @dependency-end

# PostToolUse must append to the repo-owned spool without invoking Git,
# runtime_log_archive_git.py, or archive ensure/status on the hook hot path.
"""Shared hook event log primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools" / "agent_tools"
if TOOLS_DIR.is_dir():
    sys.path.insert(0, str(TOOLS_DIR))

from parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    attest_parent_root,
)
from runtime_log_paths import (  # noqa: E402
    codex_trace_key,
    hook_event_spool_root,
    repo_log_key,
)

HOOK_RESULTS_DIR_ENV = "AGENT_CANON_HOOK_RESULTS_DIR"
HOOK_RUN_NAMESPACE_ENV = "AGENT_CANON_HOOK_RUN_NAMESPACE"
HOOK_SOURCE_ROOT_ENV = "AGENT_CANON_HOOK_SOURCE_ROOT"
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
class HookAppendResult:
    """Describe the local no-replace result for one hook event."""

    status: str
    hook_run_id: str
    spool_path: Path
    event_sha256: str
    error_code: str = ""


def _required_event_string(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key)
    return value


def canonical_hook_event_bytes(entry: dict[str, object]) -> bytes:
    """Serialize one hook event with the canonical LF-terminated JSON form."""
    if not isinstance(entry, dict):
        raise ValueError("event_schema_invalid")
    for key in (
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
        "status",
        "source_repo_key",
        "hook_log_namespace",
    ):
        _required_event_string(entry, key)
    try:
        encoded = json.dumps(
            entry,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("event_schema_invalid") from exc
    return encoded + b"\n"


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("hook event write made no progress")
        offset += written


def _publish_parent_owned(path: Path, bytes_: bytes) -> tuple[str, str]:
    """Publish a hook event through the authenticated parent capability."""
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if not configured:
        return "failed", "parent_unattested"
    try:
        parent = Path(configured)
        attestation = attest_parent_root(
            ParentRootAttestationRequest(
                cwd=parent, explicit_root=parent, purpose="hook-event-spool"
            )
        )
        boundary = ParentRootSideEffectBoundary()
        receipt = boundary.resolve_parent_owned_path(
            attestation, path, "hook-event-spool", create=False
        )
        if receipt.target_dev is not None:
            identical = boundary.read_parent_owned_file(receipt) == bytes_
            return ("duplicate", "") if identical else ("failed", "spool_conflict")
        return boundary.publish_parent_owned_file_noreplace(
            attestation, path, bytes_, "hook-event-spool"
        )
    except ParentRootSideEffectError:
        return "failed", "parent_unattested"
    except OSError:
        return "failed", "spool_io_failure"


def publish_hook_event_noreplace(path: Path, bytes_: bytes) -> tuple[str, str]:
    """Publish one event without replacing an existing event identity."""
    return _publish_parent_owned(path, bytes_)


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

    def explicit_log_sink(self) -> bool:
        """Return whether this hook writes to a caller-owned log path."""
        return bool(self.override_path or os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip())

    def spool_root(self) -> Path:
        """Return the local O(1) spool root without inspecting repositories."""
        if self.override_path:
            override = Path(self.override_path)
            if override.suffix.casefold() == ".jsonl":
                return Path(f"{override}.events")
            return override
        legacy_results_dir = os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip()
        if legacy_results_dir:
            return Path(legacy_results_dir) / ".event-spool"
        return hook_event_spool_root(self.source_root())

    def event_path(self, hook_run_id: str) -> Path:
        """Return the exact per-event spool path."""
        if (
            not hook_run_id
            or hook_run_id in {".", ".."}
            or Path(hook_run_id).name != hook_run_id
        ):
            raise ValueError("event_schema_invalid")
        return (
            self.spool_root()
            / self.runtime_namespace()
            / safe_slug(self.hook_name)
            / f"{hook_run_id}.json"
        )

    def results_dir(self) -> Path:
        """Return the local hook-result directory for legacy readers."""
        override = os.environ.get(HOOK_RESULTS_DIR_ENV, "").strip()
        if override:
            return Path(override)
        return self.spool_root()

    def result_path(self) -> Path:
        """Return a compatibility path for callers that display a result path."""
        if self.override_path:
            return Path(self.override_path)
        return self.spool_root() / self.runtime_namespace() / safe_slug(self.hook_name)

    def runtime_namespace(self) -> str:
        """Return the runtime shard name for append-only hook logs."""
        explicit = os.environ.get(HOOK_RUN_NAMESPACE_ENV, "").strip()
        if explicit:
            return safe_slug(explicit)
        for env_name in ("DEVCONTAINER_PROJECT_NAME", "COMPOSE_PROJECT_NAME"):
            value = os.environ.get(env_name, "").strip()
            if value:
                return safe_slug(value)
        if self.override_path:
            return "direct-log-override"
        return "unknown-runtime"

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

    def append(self, entry: dict[str, object]) -> HookAppendResult:
        """Append one canonical event to the local spool without archive I/O."""
        raw_hook_run_id = entry.get("hook_run_id")
        if not isinstance(raw_hook_run_id, str) or not raw_hook_run_id.strip():
            return HookAppendResult("failed", "", Path(), "", "event_identity_missing")
        hook_run_id = raw_hook_run_id.strip()
        if hook_run_id != raw_hook_run_id:
            return HookAppendResult(
                "failed",
                hook_run_id,
                Path(),
                "",
                "event_schema_invalid",
            )
        try:
            event = dict(entry)
            event["source_repo_key"] = repo_log_key(self.source_root())
            trace_key = codex_trace_key()
            if trace_key:
                event.setdefault("codex_trace_key", trace_key)
                event.setdefault("codex_thread_id", trace_key)
            event["hook_log_namespace"] = self.runtime_namespace()
            payload = canonical_hook_event_bytes(event)
            event_sha256 = hashlib.sha256(payload).hexdigest()
            path = self.event_path(hook_run_id)
            status, error_code = publish_hook_event_noreplace(path, payload)
            return HookAppendResult(status, hook_run_id, path, event_sha256, error_code)
        except ValueError:
            return HookAppendResult("failed", hook_run_id, Path(), "", "event_schema_invalid")
        except OSError:
            return HookAppendResult("failed", hook_run_id, Path(), "", "spool_unavailable")
