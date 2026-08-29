#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run-local work log automation.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md runtime preflight logging rules
# upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md run bundle artifact placement contract
# downstream implementation ./workflow_monitor.py projects semantic events into monitoring output
# downstream implementation ./workflow_monitor.py projects semantic monitoring events here
# downstream implementation ./report_artifact_checks.py materializes the checked completion read model from this ledger
# downstream implementation ../../tests/agent_tools/test_work_log.py verifies work log behavior
# @dependency-end
"""Append one timestamped run-local work-log entry."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal

if __package__:
    from .workspace_scope import resolve_report_root, resolve_runtime_artifact_path
else:
    from workspace_scope import (  # type: ignore[no-redef]
        resolve_report_root,
        resolve_runtime_artifact_path,
    )
LEDGER_SEMANTIC_KINDS = (
    "request_clause",
    "responsibility_unit",
    "decision",
    "change",
    "review_finding",
    "validation",
    "failure",
    "publication_state",
    "deferral",
)
NON_GROUPABLE_SEMANTIC_KINDS = frozenset(
    {"responsibility_unit", "decision", "failure", "deferral", "publication_state"}
)
MONITOR_PASSTHROUGH_FIELDS = frozenset(
    {
        "gate_evidence",
        "failure_response",
        "resource_certificate",
        "source_binding",
        "monitor_evidence",
        "monitoring_evidence",
    }
)

NO_REPLACE_PUBLICATION_PRIMITIVE = "renameat2_RENAME_NOREPLACE"
NO_REPLACE_TARGET_BASENAME = "creation_owner.json"
NO_REPLACE_OUTCOMES = frozenset({"published", "target_exists", "io_failed"})
RACED_OWNER_STATES = frozenset(
    {"complete_regular", "complete_non_regular", "unstable_or_unreadable"}
)
RACED_OWNER_FAILURES = frozenset(
    {
        "vanished",
        "lstat_failed",
        "open_failed",
        "fstat_changed",
        "read_failed",
        "short_read",
    }
)


class MaterializerError(ValueError):
    """Typed canonical materializer failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable materializer error."""
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _runtime_path(path: Path, runtime_root: Path | str | None = None) -> Path:
    """Resolve one work-log artifact below the external runtime boundary."""
    return resolve_runtime_artifact_path(path, runtime_root=runtime_root)


def _parent_path(
    path: Path,
    purpose: str,
    *,
    create: bool = False,
    runtime_root: Path | str | None = None,
) -> Path:
    del purpose
    target = _runtime_path(path, runtime_root)
    if create:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _parent_write(
    path: Path,
    data: bytes,
    purpose: str,
    runtime_root: Path | str | None = None,
) -> None:
    del purpose
    target = _runtime_path(path, runtime_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    temporary: Path | None = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _git_blob_oid(data: bytes) -> str:
    """Return the Git SHA-1 blob identity for exact bytes."""
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def _json_sha256(value: object) -> str:
    """Hash one canonical JSON value in the repository's integer/string domain."""
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _node_kind(mode: int) -> str:
    """Map one lstat mode to the closed raced-owner node union."""
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISBLK(mode):
        return "block_device"
    if stat.S_ISCHR(mode):
        return "character_device"
    return "unknown"


def _read_raced_owner(directory_fd: int, basename: str) -> dict[str, object]:
    """Read the raced owner entry without authorizing any namespace mutation."""
    common: dict[str, object] = {
        "schema": "agent-canon.raced-owner-readback.v1",
        "path_basename": basename,
        "node_kind": None,
        "device": None,
        "inode": None,
        "mode": None,
        "size_bytes": None,
        "content_sha256": None,
        "content_git_blob": None,
        "readback_failure": None,
    }
    try:
        before = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        common["state"] = "unstable_or_unreadable"
        common["readback_failure"] = "vanished"
        return common
    except OSError:
        common["state"] = "unstable_or_unreadable"
        common["readback_failure"] = "lstat_failed"
        return common
    common.update(
        {
            "node_kind": _node_kind(before.st_mode),
            "device": before.st_dev,
            "inode": before.st_ino,
            "mode": before.st_mode,
            "size_bytes": before.st_size,
        }
    )
    if not stat.S_ISREG(before.st_mode):
        common["state"] = "complete_non_regular"
        return common
    descriptor = -1
    try:
        descriptor = os.open(
            basename,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        common["state"] = "unstable_or_unreadable"
        common["readback_failure"] = "vanished"
        return common
    except OSError:
        common["state"] = "unstable_or_unreadable"
        common["readback_failure"] = "open_failed"
        return common
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_mode, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_size,
        ):
            common["state"] = "unstable_or_unreadable"
            common["readback_failure"] = "fstat_changed"
            return common
        chunks: list[bytes] = []
        while True:
            try:
                chunk = os.read(descriptor, 1024 * 1024)
            except OSError:
                common["state"] = "unstable_or_unreadable"
                common["readback_failure"] = "read_failed"
                return common
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
        ):
            common["state"] = "unstable_or_unreadable"
            common["readback_failure"] = "fstat_changed"
            return common
        content = b"".join(chunks)
        if len(content) != after.st_size:
            common["state"] = "unstable_or_unreadable"
            common["readback_failure"] = "short_read"
            return common
        common["state"] = "complete_regular"
        common["content_sha256"] = hashlib.sha256(content).hexdigest()
        common["content_git_blob"] = _git_blob_oid(content)
        return common
    finally:
        os.close(descriptor)


def _temp_identity(directory_fd: int, basename: str) -> dict[str, object]:
    """Read one deterministic temp identity with complete regular-file bytes."""
    absent: dict[str, object] = {
        "state": "absent",
        "classification": "no_candidate",
        "basename": None,
        "node_kind": None,
        "device": None,
        "inode": None,
        "link_count": None,
        "uid": None,
        "mode": None,
        "size_bytes": None,
        "sha256": None,
        "blob": None,
    }
    try:
        observed = os.stat(basename, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return {**absent, "identity_sha256": _json_sha256(absent)}
    except OSError as exc:
        raise MaterializerError(
            "validation_creation_owner_recovery:temp_identity_read_failed",
            str(exc),
        ) from exc
    if not stat.S_ISREG(observed.st_mode):
        raise MaterializerError("validation_creation_owner_recovery:temp_not_regular")
    descriptor = os.open(
        basename,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )
    try:
        opened = os.fstat(descriptor)
        data = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            data.extend(chunk)
        closed = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_size) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
    ) or (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size) != (
        closed.st_dev,
        closed.st_ino,
        closed.st_mode,
        closed.st_size,
    ):
        raise MaterializerError(
            "validation_creation_owner_recovery:temp_identity_changed"
        )
    content = bytes(data)
    if len(content) != closed.st_size:
        raise MaterializerError(
            "validation_creation_owner_recovery:temp_readback_failed"
        )
    identity: dict[str, object] = {
        "state": "present",
        "classification": "exact_complete_reusable",
        "basename": basename,
        "node_kind": "regular",
        "device": closed.st_dev,
        "inode": closed.st_ino,
        "link_count": closed.st_nlink,
        "uid": closed.st_uid,
        "mode": closed.st_mode,
        "size_bytes": closed.st_size,
        "sha256": hashlib.sha256(content).hexdigest(),
        "blob": _git_blob_oid(content),
    }
    return {**identity, "identity_sha256": _json_sha256(identity)}


def _renameat2_no_replace(
    directory_fd: int,
    source_basename: str,
    target_basename: str,
) -> tuple[Literal["published", "target_exists", "io_failed"], str | None]:
    """Perform one Linux atomic renameat2(RENAME_NOREPLACE) operation."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        return "io_failed", "renameat2_unavailable"
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        source_basename.encode("utf-8"),
        directory_fd,
        target_basename.encode("utf-8"),
        1,
    )
    if result == 0:
        return "published", None
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        return "target_exists", None
    return "io_failed", os.strerror(error_number)


def _owner_target_conflict_result(
    context: Mapping[str, object],
    temp_before_publish: Mapping[str, object],
    temp_after_conflict: Mapping[str, object],
    raced_owner_readback: Mapping[str, object],
) -> dict[str, object]:
    """Construct the closed v16 target-exists result without writing state."""
    side_effects = {
        "no_replace_attempted": True,
        "no_replace_succeeded": False,
        "temp_unlinked": False,
        "temp_replaced": False,
        "temp_rewritten_after_readback": False,
        "owner_unlinked": False,
        "owner_overwritten": False,
        "owner_adopted": False,
        "cleanup_attempted": False,
        "artifact_directory_fsync_attempted": False,
        "terminal_event_written": False,
        "settlement_written": False,
        "successor_aggregate_written": False,
        "current_pointer_updated": False,
    }
    result: dict[str, object] = {
        "schema": "agent-canon.validation-creation-owner-recovery-io-result.v1",
        "kind": "owner_target_conflict",
        "code": "validation_creation_owner_recovery_io:owner_target_conflict",
        "run_id": context["run_id"],
        "logical_key": context["logical_key"],
        "attempt": context["attempt"],
        "aggregate_id": context["aggregate_id"],
        "aggregate_revision": context["aggregate_revision"],
        "current_intent_revision_id": context["current_intent_revision_id"],
        "pending_event_id": context["pending_event_id"],
        "lock_id": context["lock_id"],
        "permit_sha256": context["permit_sha256"],
        "q3_sha256": context["q3_sha256"],
        "source_basename": temp_before_publish["basename"],
        "target_basename": NO_REPLACE_TARGET_BASENAME,
        "publication_primitive": NO_REPLACE_PUBLICATION_PRIMITIVE,
        "publication_outcome": "target_exists",
        "temp_before_publish": dict(temp_before_publish),
        "temp_after_conflict": dict(temp_after_conflict),
        "raced_owner_readback": dict(raced_owner_readback),
        "side_effects": side_effects,
        "body_sha256": "",
    }
    result["body_sha256"] = _json_sha256(
        {key: value for key, value in result.items() if key != "body_sha256"}
    )
    return result


def _publish_creation_owner_no_replace(
    directory_fd: int,
    source_basename: str,
    temp_before_publish: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, object]:
    """Publish the owner leaf exactly once using the v16 no-replace primitive."""
    outcome, detail = _renameat2_no_replace(
        directory_fd,
        source_basename,
        NO_REPLACE_TARGET_BASENAME,
    )
    if outcome == "target_exists":
        temp_after = _temp_identity(directory_fd, source_basename)
        if temp_after != temp_before_publish:
            raise MaterializerError(
                "validation_creation_owner_recovery_io:temp_readback_failed"
            )
        raced_owner = _read_raced_owner(directory_fd, NO_REPLACE_TARGET_BASENAME)
        raced_owner_after = _read_raced_owner(
            directory_fd,
            NO_REPLACE_TARGET_BASENAME,
        )
        if raced_owner_after != raced_owner:
            raise MaterializerError(
                "validation_creation_owner_recovery_io:owner_readback_failed"
            )
        return _owner_target_conflict_result(
            context,
            temp_before_publish,
            temp_after,
            raced_owner,
        )
    if outcome == "io_failed":
        raise MaterializerError(
            "validation_creation_owner_recovery_io:rename_failed",
            detail or "renameat2_RENAME_NOREPLACE_failed",
        )
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise MaterializerError(
            "validation_creation_owner_recovery_io:directory_fsync_failed",
            str(exc),
        ) from exc
    owner_readback = _read_raced_owner(directory_fd, NO_REPLACE_TARGET_BASENAME)
    if owner_readback.get("state") != "complete_regular":
        raise MaterializerError(
            "validation_creation_owner_recovery_io:owner_readback_failed"
        )
    return {
        "publication_primitive": NO_REPLACE_PUBLICATION_PRIMITIVE,
        "publication_outcome": "published",
        "source_basename": source_basename,
        "target_basename": NO_REPLACE_TARGET_BASENAME,
        "owner_readback": owner_readback,
        "side_effects": {
            "no_replace_attempted": True,
            "no_replace_succeeded": True,
            "temp_unlinked": False,
            "temp_replaced": False,
            "temp_rewritten_after_readback": False,
            "owner_unlinked": False,
            "owner_overwritten": False,
            "owner_adopted": False,
            "cleanup_attempted": False,
            "artifact_directory_fsync_attempted": True,
            "terminal_event_written": False,
            "settlement_written": False,
            "successor_aggregate_written": False,
            "current_pointer_updated": False,
        },
    }


def _required_ledger_text(event: Mapping[str, object], field: str) -> str:
    """Return one required ledger text field."""
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ledger event requires {field}")
    return value.strip()


def _required_ledger_refs(event: Mapping[str, object], field: str) -> tuple[str, ...]:
    """Return non-empty evidence or artifact references."""
    value = event.get(field)
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"ledger event requires non-empty {field}")
    refs = tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )
    if len(refs) != len(value):
        raise ValueError(f"ledger event {field} must contain only non-empty strings")
    return refs


def _validate_ledger_event(event: Mapping[str, object], report_dir: Path) -> str:
    """Validate one append-only event and return its stable identity."""
    if not isinstance(event, Mapping):
        raise ValueError("ledger event must be an object")
    run_id = _required_ledger_text(event, "run_id")
    if run_id != report_dir.name:
        raise ValueError("ledger event run_id does not match report directory")
    _required_ledger_text(event, "context_id")
    identity = event.get("event_id", event.get("sequence"))
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("ledger event requires event_id or sequence")
    semantic_kind = _required_ledger_text(event, "semantic_kind")
    if semantic_kind not in LEDGER_SEMANTIC_KINDS:
        raise ValueError(f"unsupported semantic_kind: {semantic_kind}")
    for field in (
        "owner",
        "state_owner",
        "api_owner",
        "dependency_owner",
        "responsibility_unit",
        "intent_id",
        "outcome",
    ):
        _required_ledger_text(event, field)
    for field in ("evidence_refs", "artifact_refs"):
        _required_ledger_refs(event, field)
    clause_id = event.get("clause_id")
    if clause_id is not None and (
        not isinstance(clause_id, str) or not clause_id.strip()
    ):
        raise ValueError("ledger event clause_id must be null or non-empty text")
    mapping_mode = event.get("mapping_mode", "direct")
    if not isinstance(mapping_mode, str) or not mapping_mode.strip():
        raise ValueError("ledger event mapping_mode must be non-empty text")
    mapping_mode = mapping_mode.strip()
    if mapping_mode not in {"direct", "group"}:
        raise ValueError("ledger event mapping_mode must be direct or group")
    if mapping_mode == "group" and semantic_kind in NON_GROUPABLE_SEMANTIC_KINDS:
        raise ValueError(f"{semantic_kind} ledger events cannot be grouped")
    if mapping_mode == "group":
        group_identity = event.get("group_identity", event.get("group_id"))
        if not isinstance(group_identity, str) or not group_identity.strip():
            raise ValueError("group ledger events require group_identity")
        members = event.get("member_clause_ids")
        if not isinstance(members, (list, tuple)) or len(members) < 2:
            raise ValueError("group ledger events require member_clause_ids")
        if any(not isinstance(member, str) or not member.strip() for member in members):
            raise ValueError("group member_clause_ids must be non-empty text")
        if len(set(member.strip() for member in members)) != len(members):
            raise ValueError("group member_clause_ids must be unique")
    source_binding = event.get("source_binding")
    if source_binding is not None:
        if not isinstance(source_binding, Mapping):
            raise ValueError("ledger event source_binding must be an object")
        binding_run_id = source_binding.get("run_id")
        binding_context_id = source_binding.get("context_id")
        if not isinstance(binding_run_id, str) or not binding_run_id.strip():
            raise ValueError("ledger event source_binding requires run_id")
        if not isinstance(binding_context_id, str) or not binding_context_id.strip():
            raise ValueError("ledger event source_binding requires context_id")
        if binding_run_id.strip() != run_id:
            raise ValueError("ledger event source_binding.run_id does not match run_id")
        if binding_context_id.strip() != _required_ledger_text(event, "context_id"):
            raise ValueError(
                "ledger event source_binding.context_id does not match context_id"
            )
    for field in MONITOR_PASSTHROUGH_FIELDS - {"source_binding"}:
        value = event.get(field)
        if value is None:
            continue
        if not isinstance(value, (Mapping, list, tuple)):
            raise ValueError(f"ledger event {field} must remain structured evidence")
    return str(identity).strip()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one run-local work-log entry.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used for explicit runtime selection; state is external.",
    )
    parser.add_argument("--report-dir", help="Explicit run bundle directory to update.")
    parser.add_argument("--run-id", help="Run id under the external reports/agents root.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional external directory that contains per-run report folders. "
            "Defaults below --runtime-root."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        help="Explicit external runtime root; defaults to AGENT_CANON_RUNTIME_ROOT.",
    )
    parser.add_argument(
        "--kind",
        default="work",
        help="Short event kind, for example kickoff/test/edit/review.",
    )
    parser.add_argument("--message", required=True, help="What happened in this step.")
    parser.add_argument("--next", default="", help="Explicit next step.")
    parser.add_argument(
        "--request-clause-id",
        action="append",
        default=[],
        help="User request clause id covered by this log entry. Repeat to add multiple ids.",
    )
    parser.add_argument(
        "--design-ref",
        action="append",
        default=[],
        help="Approved design section or artifact clause used by this entry.",
    )
    parser.add_argument(
        "--allow-missing-request-clause-id",
        action="store_true",
        help=(
            "Allow a run-bundle-only pre-contract/runtime note without a clause id. "
            "Use only before a clause can reasonably exist."
        ),
    )
    parser.add_argument(
        "--missing-request-clause-reason",
        default="",
        help="Required reason when --allow-missing-request-clause-id is used.",
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        help="Optional path or artifact reference. Repeat to add multiple refs.",
    )
    return parser


def append_ledger_event(
    report_dir: Path,
    event: dict[str, object],
    *,
    runtime_root: Path | str | None = None,
) -> Path:
    """Append one semantic event to the existing run-local work ledger."""
    event_identity = _validate_ledger_event(event, report_dir)
    work_log_path = _parent_path(
        report_dir / "work_log.md",
        "work-log",
        create=True,
        runtime_root=runtime_root,
    )
    if not work_log_path.exists():
        _log_run_work_entry(report_dir, "ledger-bootstrap")
    lines = work_log_path.read_text(encoding="utf-8").splitlines()
    heading = "## Ledger Events"
    if heading not in lines:
        lines.extend(["", heading, ""])
    payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
    line = f"- ledger_event={payload}"
    for existing_line in lines:
        if not existing_line.startswith("- ledger_event="):
            continue
        try:
            existing = json.loads(existing_line.removeprefix("- ledger_event="))
        except json.JSONDecodeError:
            continue
        if not isinstance(existing, dict):
            continue
        existing_identity = existing.get("event_id", existing.get("sequence"))
        if existing_identity == event_identity:
            if existing != event:
                raise ValueError(
                    f"ledger event conflict for event identity={event_identity}"
                )
            return work_log_path
    if line not in lines:
        lines.append(line)
        _parent_write(
            work_log_path,
            ("\n".join(lines) + "\n").encode("utf-8"),
            "work-log",
            runtime_root,
        )
    return work_log_path


def read_ledger_snapshot(
    report_dir: Path,
    snapshot_identity: str,
    *,
    runtime_root: Path | str | None = None,
) -> dict[str, object]:
    """Reconstruct one immutable logical-ledger snapshot from the run log."""
    if not snapshot_identity.strip():
        raise ValueError("snapshot_identity must not be empty")
    work_log_path = _runtime_path(report_dir / "work_log.md", runtime_root)
    if not work_log_path.is_file():
        raise ValueError(f"missing work log: {work_log_path}")
    events: list[dict[str, object]] = []
    identities: set[str] = set()
    for line in work_log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ledger_event="):
            continue
        try:
            event = json.loads(line.removeprefix("- ledger_event="))
        except json.JSONDecodeError as exc:
            raise ValueError("malformed ledger event") from exc
        if not isinstance(event, dict):
            raise ValueError("ledger event must be an object")
        identity = _validate_ledger_event(event, report_dir)
        if identity in identities:
            raise ValueError(f"duplicate ledger event identity: {identity}")
        identities.add(identity)
        events.append(event)
    events.sort(
        key=lambda event: (
            str(event.get("sequence", "")),
            str(event.get("event_id", event.get("sequence", ""))),
        )
    )
    snapshot = {
        "snapshot_identity": snapshot_identity.strip(),
        "events": events,
        "event_identities": sorted(identities),
    }
    snapshot["snapshot_digest"] = ledger_snapshot_digest(snapshot)
    return snapshot


def ledger_snapshot_digest(snapshot: Mapping[str, object]) -> str:
    """Return the stable digest for the canonical ledger event projection."""
    events = snapshot.get("events")
    if not isinstance(events, list):
        raise ValueError("ledger snapshot events must be a list")
    payload = json.dumps(events, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_active_report_dir(
    workspace_root: Path,
    report_root: Path,
    runtime_root: Path | str | None = None,
) -> Path | None:
    """Resolve the current run bundle from the external runtime pointer."""
    del workspace_root
    pointer = _runtime_path(report_root / ".active_run", runtime_root)
    if not pointer.is_file():
        return None
    active = pointer.read_text(encoding="utf-8").strip()
    if not active:
        return None
    active_path = Path(active)
    if active_path.is_absolute():
        return active_path
    return _runtime_path(
        active_path if active_path.is_absolute() else report_root / active_path,
        runtime_root,
    )


def _log_run_work_entry(report_dir: Path, entry: str) -> Path:
    """Append one entry to the run-bundle work log."""
    _parent_path(report_dir / "work_log.md", "work-log", create=True)
    work_log_path = report_dir / "work_log.md"
    if not work_log_path.exists():
        _parent_write(
            work_log_path,
            "\n".join(
                [
                    "# Work Log",
                    "",
                    f"- Run ID: {report_dir.name}",
                    "- Task:",
                    "- Owner:",
                    "",
                    "## Purpose",
                    "",
                    "- Chronological run-local work log.",
                    "",
                    "## Entries",
                    "",
                ]
            ).encode("utf-8"),
            "work-log",
        )
    existing = work_log_path.read_bytes()
    separator = b"\n" if existing else b""
    _parent_write(
        work_log_path,
        existing + separator + f"- {entry}\n".encode("utf-8"),
        "work-log",
    )
    return work_log_path


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    if args.report_dir and args.run_id:
        raise SystemExit("Provide at most one of --report-dir or --run-id.")
    if args.report_dir:
        report_dir = _runtime_path(Path(args.report_dir).resolve(), args.runtime_root)
        report_root = report_dir.parent
    else:
        if (
            args.report_root is None
            and args.runtime_root is None
            and args.run_id is None
            and not os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
        ):
            source = Path(__file__).resolve().parents[3]
            candidate = workspace_root / "reports" / "agents"
            if workspace_root != source and source not in workspace_root.parents:
                report_root = candidate
            else:
                report_root = resolve_report_root(
                    args.report_root,
                    workspace_root,
                    runtime_root=args.runtime_root,
                )
        else:
            report_root = resolve_report_root(
                args.report_root,
                workspace_root,
                runtime_root=args.runtime_root,
            )
    if not args.report_dir and args.run_id:
        report_dir = report_root / str(args.run_id)
    elif not args.report_dir:
        report_dir = _resolve_active_report_dir(
            workspace_root,
            report_root,
            args.runtime_root,
        )

    if not args.request_clause_id:
        if not args.allow_missing_request_clause_id:
            raise SystemExit(
                "At least one --request-clause-id is required unless "
                "--allow-missing-request-clause-id is set."
            )
        if not args.missing_request_clause_reason.strip():
            raise SystemExit(
                "--missing-request-clause-reason is required when clause ids are omitted."
            )
        if report_dir is None:
            raise SystemExit(
                "Missing clause ids are only allowed when --report-dir or --run-id "
                "or the external .active_run pointer resolves a run bundle."
            )

    if report_dir is None:
        raise SystemExit(
            "No run bundle resolved. Provide --report-dir / --run-id or configure an external .active_run pointer."
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    if args.request_clause_id:
        clause_suffix = " | request_clause_ids: " + ",".join(args.request_clause_id)
    else:
        clause_suffix = (
            " | request_clause_ids: unassigned"
            f" | missing_request_clause_reason: {args.missing_request_clause_reason.strip()}"
        )
    ref_suffix = ""
    if args.ref:
        ref_suffix = " | refs: " + ", ".join(args.ref)
    design_suffix = ""
    if args.design_ref:
        design_suffix = " | design_refs: " + ", ".join(args.design_ref)
    next_suffix = ""
    if args.next:
        next_suffix = f" | next: {args.next}"
    entry = (
        f"`{timestamp} | {args.kind} | {args.message}"
        f"{clause_suffix}{design_suffix}{ref_suffix}{next_suffix}`"
    )
    work_log_path = _log_run_work_entry(report_dir, entry)
    print(f"WORK_LOG={work_log_path}")
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
