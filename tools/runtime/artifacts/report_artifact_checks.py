#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../../../README.md shared automation index
# upstream design ../../../documents/design/request-intent-and-update-relation.md run-bundle temporary-state and retention readback projection
# upstream implementation ../manifest/manifest_rendering.py renders optional run-bundle artifacts
# @dependency-end

"""Shared checks for run-bundle artifact completeness."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import TypeGuard

try:
    from tools.repository.workspace.parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )
except ImportError:
    from tools.repository.workspace.parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )

from tools.runtime.archive.work_log import MIN_GROUP_MEMBER_COUNT
from tools.runtime.artifacts.artifact_identity import (
    canonical_body_sha256,
    canonical_json_bytes,
    git_blob_oid,
)
from tools.runtime.values import (
    is_object_list,
    is_string_object_mapping,
)

PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
REVIEW_ADJUDICATION_PLACEHOLDERS = frozenset(
    {"", "-", "—", "none", "null", "n/a", "na", "missing", "unknown", "todo", "tbd"}
)
APPROVE_DECISION_PATTERN = re.compile(
    r"^(?:[-*]\s*)?(?:decision\s*:\s*)?approve\s*$",
    re.IGNORECASE,
)
REVIEW_TARGET_SHA_PATTERN = re.compile(
    r"\breview_target_sha256\s*=\s*`?([0-9a-f]{64})`?",
    re.IGNORECASE,
)
DESIGN_ARTIFACT_PATH_PATTERN = re.compile(
    r"^\s*-\s*Design artifact path:\s*`?([^`\r\n]+?)`?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
MECHANICALLY_REGENERATED_REPORT_ROOTS = (
    PurePosixPath("reports/agent-eval-runs"),
    PurePosixPath("reports/agent-improvement-guide"),
    PurePosixPath("reports/agent-runtime-dashboard"),
    PurePosixPath("reports/dependency-review"),
    PurePosixPath("reports/hooks"),
    PurePosixPath("reports/.cache"),
)
MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS = (
    re.compile(r"^reports/[^/]+\.(?:json|patch|txt)$"),
)
EVAL_TRANSIENT_CAPTURE_PATTERN = re.compile(
    r"^reports/agent-eval-runs/[^/]+/[^/]+\.(?:stdout|stderr)\.txt$"
)

SHA256_HEX_DIGEST_BYTE_LENGTH = hashlib.sha256().digest_size * 2
VALIDATION_RESULT_SCHEMA = "agent-canon.validation-result-projection.v1"
VALIDATION_ROUTE_ID = "python.ruff.full"
VALIDATION_OWNER_PATHS = (
    "tools/agent/orchestration/review_dispatch.py",
    "tools/runtime/artifacts/artifact_identity.py",
    "tools/runtime/artifacts/external_artifact_binding.py",
    "tools/repository/github/publication_integrator.py",
    "tools/runtime/artifacts/report_artifact_checks.py",
    "tools/agent/orchestration/review_dispatch.py",
    "tools/runtime/archive/work_log.py",
    "tests/agent_tools/test_artifact_identity.py",
    "tests/agent_tools/test_codex_hooks.py",
    "tests/agent_tools/test_external_artifact_binding.py",
    "tests/agent_tools/test_publication_integrator.py",
    "tests/agent_tools/test_review_dispatch.py",
    "tests/agent_tools/test_work_log.py",
)
VALIDATION_LEAVES = (
    "result_manifest.json",
    "validation.stderr",
    "validation.stdout",
    "version.stderr",
    "version.stdout",
)
VALIDATION_ROUTE_ARGV_PREFIX = (
    "-m",
    "ruff",
    "check",
)
VALIDATION_ROUTE_ARGV_SUFFIX = (
    "--select",
    "D,E,F,I,UP",
    "--ignore",
    "E501",
)


class ValidationMaterializerError(ValueError):
    """Typed failure from the canonical validation materializer."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable materializer failure."""
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def _validation_stable_bytes(path: Path) -> bytes:
    """Read one no-follow regular file and prove its identity stayed stable."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValidationMaterializerError(
            "canonical_run_locator:missing",
            str(path),
        ) from exc
    if not stat.S_ISREG(before.st_mode):
        raise ValidationMaterializerError("canonical_run_locator:non_regular")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise ValidationMaterializerError(
            "canonical_run_locator:readback_failed",
            str(path),
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    before_identity = (before.st_dev, before.st_ino, before.st_mode, before.st_size)
    opened_identity = (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size)
    after_identity = (after.st_dev, after.st_ino, after.st_mode, after.st_size)
    data = b"".join(chunks)
    if before_identity != opened_identity or opened_identity != after_identity:
        raise ValidationMaterializerError(
            "canonical_run_locator:moved_during_operation"
        )
    if len(data) != after.st_size:
        raise ValidationMaterializerError("canonical_run_locator:short_read")
    return data


def _validation_locator(workspace: Path) -> dict[str, object]:
    """Construct the workspace-only canonical run locator."""
    root = workspace.resolve()
    report_root = (root / "reports" / "agents").resolve()
    pointer_path = report_root / ".active_run"
    baseline_path = report_root / ".active_run.sha256"
    pointer_bytes = _validation_stable_bytes(pointer_path)
    baseline_bytes = _validation_stable_bytes(baseline_path)
    try:
        pointer_text = pointer_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationMaterializerError(
            "canonical_run_locator:pointer_encoding"
        ) from exc
    if not pointer_text.endswith("\n") or "\n" in pointer_text[:-1]:
        raise ValidationMaterializerError("canonical_run_locator:pointer_framing")
    pointer_value = pointer_text[:-1]
    if not pointer_value or not os.path.isabs(pointer_value):
        raise ValidationMaterializerError("canonical_run_locator:pointer_not_absolute")
    normalized = os.path.normpath(pointer_value)
    if normalized != pointer_value:
        raise ValidationMaterializerError(
            "canonical_run_locator:pointer_not_normalized"
        )
    report_dir = Path(pointer_value)
    if report_dir.parent != report_root or report_dir.name in {"", ".", ".."}:
        raise ValidationMaterializerError("canonical_run_locator:report_dir_invalid")
    try:
        report_stat = report_dir.lstat()
    except OSError as exc:
        raise ValidationMaterializerError(
            "canonical_run_locator:report_dir_missing"
        ) from exc
    if not stat.S_ISDIR(report_stat.st_mode):
        raise ValidationMaterializerError("canonical_run_locator:report_dir_invalid")
    if not baseline_bytes.endswith(b"\n") or len(baseline_bytes) != (
        SHA256_HEX_DIGEST_BYTE_LENGTH + len(b"\n")
    ):
        raise ValidationMaterializerError("canonical_run_locator:baseline_invalid")
    baseline = baseline_bytes[:-1].decode("ascii", errors="replace")
    if not re.fullmatch(r"[0-9a-f]{64}", baseline):
        raise ValidationMaterializerError("canonical_run_locator:baseline_invalid")
    if hashlib.sha256(pointer_bytes).hexdigest() != baseline:
        raise ValidationMaterializerError("canonical_run_locator:baseline_mismatch")
    for leaf in (report_dir / "task_authority.yaml", report_dir / "work_log.md"):
        _validation_stable_bytes(leaf)
    core: dict[str, object] = {
        "schema": "agent-canon.canonical-run-locator.v1",
        "schema_version": 1,
        "workspace_repository_id": root.name,
        "report_root_repo_relative": "reports/agents",
        "report_dir_repo_relative": report_dir.relative_to(root).as_posix(),
        "run_id": report_dir.name,
        "pointer_path": "reports/agents/.active_run",
        "pointer_sha256": hashlib.sha256(pointer_bytes).hexdigest(),
        "baseline_path": "reports/agents/.active_run.sha256",
    }
    locator_id = "run-locator:" + hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    locator = {
        **core,
        "run_locator_id": locator_id,
        "run_locator_body_sha256": "",
    }
    locator["run_locator_body_sha256"] = canonical_body_sha256(
        locator,
        "run_locator_body_sha256",
    )
    return {**locator, "report_dir": report_dir}


def _validation_ledger_events(report_dir: Path) -> list[dict[str, object]]:
    """Read the current logical ledger through its canonical work-log owner."""
    from tools.runtime.archive.work_log import read_ledger_snapshot

    snapshot = read_ledger_snapshot(
        report_dir,
        f"validation-materializer-ledger:{report_dir.name}",
    )
    return snapshot["events"]


def _current_validation_candidate(
    events: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return the highest immutable candidate already present in canonical L."""
    candidates: list[dict[str, object]] = []
    for event in events:
        payload = event.get("automatic_review")
        if (
            is_string_object_mapping(payload)
            and payload.get("record_kind") == "candidate"
        ):
            candidates.append(dict(payload))
    if not candidates:
        raise ValidationMaterializerError("validation_result:candidate_missing")
    candidates_with_revision: list[tuple[int, dict[str, object]]] = []
    for candidate in candidates:
        revision = candidate.get("candidate_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValidationMaterializerError("validation_result:candidate_mismatch")
        candidates_with_revision.append((revision, candidate))
    candidates_with_revision.sort(key=lambda item: item[0])
    candidate = candidates_with_revision[-1][1]
    if not isinstance(candidate.get("candidate_revision"), int):
        raise ValidationMaterializerError("validation_result:candidate_mismatch")
    if candidate.get("candidate_body_sha256") != canonical_body_sha256(
        candidate,
        "candidate_body_sha256",
    ):
        raise ValidationMaterializerError(
            "validation_result:candidate_body_hash_mismatch"
        )
    return candidate


def _validation_producer_evidence(
    events: Sequence[Mapping[str, object]],
    candidate_id: str,
) -> tuple[str | None, str | None]:
    """Read producer identity evidence without evaluating reviewer eligibility."""
    frame: Mapping[str, object] | None = None
    for event in events:
        payload = event.get("automatic_review")
        if (
            is_string_object_mapping(payload)
            and payload.get("record_kind") == "frame"
            and payload.get("candidate_id") == candidate_id
            and payload.get("review_role_id") == "change_reviewer"
        ):
            frame = payload
    if frame is None:
        return None, None
    runtime_id = frame.get("assigned_runtime_agent_id")
    for event in events:
        payload = event.get("automatic_review")
        if (
            is_string_object_mapping(payload)
            and payload.get("record_kind") == "resume_event"
            and payload.get("candidate_id") == candidate_id
            and payload.get("review_frame_id") == frame.get("review_frame_id")
        ):
            observed = payload.get("observed_result")
            if is_string_object_mapping(observed):
                runtime_id = observed.get("nested_runtime_agent_id")
    return (
        "change_reviewer" if isinstance(runtime_id, str) and runtime_id else None,
        runtime_id if isinstance(runtime_id, str) and runtime_id else None,
    )


def _validation_owner_paths(workspace: Path) -> tuple[str, ...]:
    """Return existing W2 AgentCanon Python owner paths in canonical order."""
    roots = tuple(
        path for path in VALIDATION_OWNER_PATHS if (workspace / path).is_file()
    )
    if roots != VALIDATION_OWNER_PATHS:
        raise ValidationMaterializerError("validation_route:owner_paths_missing")
    return roots


def _validation_route_record(
    workspace: Path,
    locator: Mapping[str, object],
    candidate: Mapping[str, object],
    logical_key_sha256: str,
    attempt_ordinal: int,
) -> dict[str, object]:
    """Derive the closed registered Python Ruff route without caller input."""
    executable = str(Path(sys.executable).resolve())
    owner_paths = _validation_owner_paths(workspace)
    argv = [
        executable,
        *VALIDATION_ROUTE_ARGV_PREFIX,
        *owner_paths,
        *VALIDATION_ROUTE_ARGV_SUFFIX,
    ]
    core: dict[str, object] = {
        "schema": "agent-canon.registered-validation-route.v2",
        "schema_version": 2,
        "route_id": VALIDATION_ROUTE_ID,
        "requirement_id": VALIDATION_ROUTE_ID,
        "run_locator_ref": {
            "run_locator_id": locator["run_locator_id"],
            "run_locator_body_sha256": locator["run_locator_body_sha256"],
        },
        "candidate": {
            "candidate_id": candidate.get("candidate_id"),
            "candidate_revision": candidate.get("candidate_revision"),
            "candidate_body_sha256": candidate.get("candidate_body_sha256"),
            "commit": candidate.get("candidate_commit"),
            "tree": candidate.get("candidate_tree"),
        },
        "logical_key_sha256": logical_key_sha256,
        "attempt_ordinal": attempt_ordinal,
        "command": {
            "argv": argv,
            "argv_sha256": hashlib.sha256(canonical_json_bytes(argv)).hexdigest(),
            "cwd_repository_id": workspace.name,
            "cwd_repo_relative": ".",
            "cwd_absolute": str(workspace),
            "cwd_absolute_sha256": hashlib.sha256(str(workspace).encode()).hexdigest(),
            "environment_profile": {},
            "execution_identity_contract": {
                "launcher": executable,
                "module": "ruff",
            },
        },
        "artifact_derivation": {
            "root_parent_run_relative": "results/validation",
            "artifact_id_prefix": "validation-result:",
            "attempt_encoding": "16-lowercase-hex",
            "pending_event_binding": "id-and-canonical-sha256",
            "leaf_set": list(VALIDATION_LEAVES),
        },
        "version_policy": {"required": True},
        "success_rule": {
            "termination_kind": "exited",
            "exit_code": 0,
            "signal": None,
            "spawn_error": None,
            "stdout_complete": True,
            "stderr_complete": True,
        },
    }
    route_id = (
        "validation-route:" + hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    )
    route = {**core, "route_record_id": route_id, "route_record_body_sha256": ""}
    route["route_record_body_sha256"] = canonical_body_sha256(
        route,
        "route_record_body_sha256",
    )
    return route


def _validation_stream(
    data: bytes,
    returncode: int | None,
    state: str,
    stream_name: str,
    artifact_path: str,
) -> dict[str, object]:
    """Materialize one complete stream observation."""
    return {
        "stream": stream_name,
        "state": state,
        "pipe_created": state != "not_created",
        "eof_observed": state == "eof_complete",
        "complete": state == "eof_complete",
        "capture_error": None if state == "eof_complete" else "process_not_spawned",
        "artifact": {
            "path": artifact_path,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "blob": git_blob_oid(data),
        },
        "returncode": returncode,
    }


def _write_validation_leaf(path: Path, data: bytes) -> None:
    """Create one deterministic leaf once, or accept exact replay bytes."""
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if configured:
        parent = Path(configured).resolve(strict=True)
        attestation = attest_parent_root(
            ParentRootAttestationRequest(
                cwd=parent, explicit_root=parent, purpose="validation-artifact"
            )
        )
        boundary = ParentRootSideEffectBoundary()
        receipt = boundary.resolve_parent_owned_path(
            attestation, path, "validation-artifact", create=False
        )
        try:
            existing = boundary.read_parent_owned_file(receipt)
        except ParentRootSideEffectError as exc:
            if exc.reject is not ParentRootReject.ROOT_MISSING:
                raise
            existing = None
        if existing is not None:
            if existing != data:
                raise ValidationMaterializerError("validation_artifact:byte_mismatch")
            return
        boundary.write_parent_owned_file(attestation, path, data, "validation-artifact")
        return
    raise ParentRootSideEffectError(
        ParentRootReject.HANDOFF_INVALID,
        "validation-artifact: explicit parent root is required",
    )


def _validation_event_hash(event: Mapping[str, object]) -> str:
    """Hash one canonical logical-ledger event without inventing a receipt."""
    return hashlib.sha256(canonical_json_bytes(event)).hexdigest()


def _verify_validation_replay(
    report_dir: Path,
    locator: Mapping[str, object],
    candidate: Mapping[str, object],
    terminal_event: Mapping[str, object],
    manifest_path: Path,
    manifest: Mapping[str, object],
) -> None:
    """Verify every stored identity before accepting a pass replay."""
    artifact = terminal_event.get("artifact")
    if not is_string_object_mapping(artifact):
        raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
    try:
        manifest_relative = manifest_path.relative_to(report_dir).as_posix()
    except ValueError as exc:
        raise ValidationMaterializerError("validation_artifact:root_mismatch") from exc
    if artifact.get("manifest_path") != manifest_relative:
        raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
    manifest_bytes = _validation_stable_bytes(manifest_path)
    if artifact.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
    if artifact.get("manifest_blob") != git_blob_oid(manifest_bytes):
        raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str) or manifest.get("artifact_id") != artifact_id:
        raise ValidationMaterializerError("validation_artifact:id_mismatch")
    if manifest.get("leaves") != list(VALIDATION_LEAVES):
        raise ValidationMaterializerError("validation_artifact:leaf_set_mismatch")
    run_locator_ref = manifest.get("run_locator_ref")
    expected_locator_ref = {
        "run_locator_id": locator["run_locator_id"],
        "run_locator_body_sha256": locator["run_locator_body_sha256"],
    }
    if run_locator_ref != expected_locator_ref:
        raise ValidationMaterializerError("validation_result:locator_mismatch")
    manifest_candidate = manifest.get("candidate")
    expected_candidate = {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_revision": candidate.get("candidate_revision"),
        "candidate_body_sha256": candidate.get("candidate_body_sha256"),
        "commit": candidate.get("candidate_commit"),
        "tree": candidate.get("candidate_tree"),
    }
    if manifest_candidate != expected_candidate:
        raise ValidationMaterializerError("validation_result:candidate_mismatch")
    manifest_route_ref = manifest.get("route_record_ref")
    expected_route_ref = {
        "route_record_id": terminal_event.get("route_record_id"),
        "route_record_body_sha256": terminal_event.get("route_record_body_sha256"),
    }
    if manifest_route_ref != expected_route_ref:
        raise ValidationMaterializerError("validation_result:route_mismatch")
    manifest_attempt = manifest.get("attempt")
    expected_attempt = {
        "logical_key_sha256": terminal_event.get("logical_key_sha256"),
        "attempt_ordinal": terminal_event.get("attempt_ordinal"),
        "pending_event_id": terminal_event.get("pending_event_id"),
        "pending_event_sha256": terminal_event.get("pending_event_sha256"),
    }
    if manifest_attempt != expected_attempt:
        raise ValidationMaterializerError("validation_result:attempt_mismatch")
    try:
        children = list(manifest_path.parent.iterdir())
    except OSError as exc:
        raise ValidationMaterializerError("validation_artifact:root_mismatch") from exc
    child_names = sorted(
        (child.name for child in children), key=lambda item: item.encode()
    )
    if child_names != list(VALIDATION_LEAVES):
        raise ValidationMaterializerError("validation_artifact:leaf_set_mismatch")
    streams = manifest.get("streams")
    if not is_string_object_mapping(streams):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    termination = manifest.get("termination")
    if not is_string_object_mapping(termination):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    version_returncode = termination.get("version_returncode")
    validation_returncode = termination.get("validation_returncode")
    if not isinstance(version_returncode, int) or isinstance(version_returncode, bool):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    if validation_returncode is not None and (
        not isinstance(validation_returncode, int)
        or isinstance(validation_returncode, bool)
    ):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    if terminal_event.get("outcome") == "pass" and (
        version_returncode != 0 or validation_returncode != 0
    ):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    stream_paths = {
        "version": {"stdout": "version.stdout", "stderr": "version.stderr"},
        "validation": {
            "stdout": "validation.stdout",
            "stderr": "validation.stderr",
        },
    }
    for group, names in stream_paths.items():
        group_streams = streams.get(group)
        if not is_string_object_mapping(group_streams):
            raise ValidationMaterializerError("validation_result:stream_mismatch")
        for stream_name, leaf_name in names.items():
            stream = group_streams.get(stream_name)
            if not is_string_object_mapping(stream):
                raise ValidationMaterializerError("validation_result:stream_mismatch")
            expected_returncode = (
                version_returncode if group == "version" else validation_returncode
            )
            expected_state = (
                "eof_complete" if expected_returncode is not None else "not_created"
            )
            expected_capture_error = (
                None if expected_state == "eof_complete" else "process_not_spawned"
            )
            if (
                stream.get("stream") != stream_name
                or stream.get("state") != expected_state
                or stream.get("pipe_created") != (expected_state != "not_created")
                or stream.get("eof_observed") != (expected_state == "eof_complete")
                or stream.get("complete") != (expected_state == "eof_complete")
                or stream.get("capture_error") != expected_capture_error
                or stream.get("returncode") != expected_returncode
            ):
                raise ValidationMaterializerError("validation_result:stream_mismatch")
            artifact = stream.get("artifact")
            if (
                not is_string_object_mapping(artifact)
                or artifact.get("path") != leaf_name
            ):
                raise ValidationMaterializerError("validation_result:stream_mismatch")
            leaf_bytes = _validation_stable_bytes(manifest_path.parent / leaf_name)
            if artifact.get("size_bytes") != len(leaf_bytes):
                raise ValidationMaterializerError(
                    "validation_result:output_hash_mismatch"
                )
            if artifact.get("sha256") != hashlib.sha256(leaf_bytes).hexdigest():
                raise ValidationMaterializerError(
                    "validation_result:output_hash_mismatch"
                )
            if artifact.get("blob") != git_blob_oid(leaf_bytes):
                raise ValidationMaterializerError(
                    "validation_result:output_hash_mismatch"
                )


def materialize_required_validation(workspace: Path) -> dict[str, object]:
    """Materialize or replay the sole active-profile validation result."""
    locator = _validation_locator(workspace)
    report_dir = locator["report_dir"]
    if not isinstance(report_dir, Path):
        raise ValidationMaterializerError("canonical_run_locator:report_dir_invalid")
    events = _validation_ledger_events(report_dir)
    candidate = _current_validation_candidate(events)
    candidate_id = candidate.get("candidate_id")
    candidate_revision = candidate.get("candidate_revision")
    if not isinstance(candidate_id, str) or not isinstance(candidate_revision, int):
        raise ValidationMaterializerError("validation_result:candidate_mismatch")
    producer_role_id, producer_runtime_agent_id = _validation_producer_evidence(
        events,
        candidate_id,
    )
    logical_key_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {"candidate_id": candidate_id, "route_id": VALIDATION_ROUTE_ID}
        )
    ).hexdigest()
    prior = [
        event
        for event in events
        if event.get("semantic_kind") == "validation"
        and event.get("subject_id") == VALIDATION_ROUTE_ID
        and event.get("logical_key_sha256") == logical_key_sha256
    ]
    terminal = [event for event in prior if event.get("outcome") in {"pass", "fail"}]
    latest_terminal = terminal[-1] if terminal else None
    replay_producer_matches = latest_terminal is not None and (
        latest_terminal.get("producer_role_id") == producer_role_id
        and latest_terminal.get("producer_runtime_agent_id")
        == producer_runtime_agent_id
    )
    if (
        latest_terminal is not None
        and latest_terminal.get("outcome") == "pass"
        and replay_producer_matches
    ):
        artifact = latest_terminal.get("artifact")
        if not is_string_object_mapping(artifact):
            raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
        manifest_reference = artifact.get("manifest_path")
        if not isinstance(manifest_reference, str) or not manifest_reference:
            raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
        manifest_path = report_dir / manifest_reference
        manifest_bytes = _validation_stable_bytes(manifest_path)
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationMaterializerError(
                "validation_artifact:manifest_mismatch"
            ) from exc
        if not is_string_object_mapping(manifest):
            raise ValidationMaterializerError("validation_artifact:manifest_mismatch")
        _verify_validation_replay(
            report_dir,
            locator,
            candidate,
            latest_terminal,
            manifest_path,
            manifest,
        )
        return _validation_projection(
            locator,
            candidate,
            latest_terminal,
            manifest_path,
            manifest,
        )
    attempts: list[int] = []
    for event in prior:
        attempt_value = event.get("attempt_ordinal")
        if isinstance(attempt_value, int) and not isinstance(attempt_value, bool):
            attempts.append(attempt_value)
    attempt_ordinal = max(attempts, default=0) + 1
    route = _validation_route_record(
        workspace.resolve(),
        locator,
        candidate,
        logical_key_sha256,
        attempt_ordinal,
    )
    route_id = str(route["route_record_id"])
    pending = next(
        (
            event
            for event in prior
            if event.get("outcome") == "pending"
            and event.get("attempt_ordinal") == attempt_ordinal
        ),
        None,
    )
    if pending is None:
        pending_id = f"validation-pending:{logical_key_sha256}:{attempt_ordinal:016x}"
        pending = {
            "run_id": report_dir.name,
            "context_id": report_dir.name,
            "event_id": pending_id,
            "semantic_kind": "validation",
            "event_kind": "validation",
            "subject_id": VALIDATION_ROUTE_ID,
            "owner": "completion_authority",
            "state_owner": "tools/runtime/archive/work_log.py",
            "api_owner": "tools/runtime/artifacts/report_artifact_checks.py",
            "dependency_owner": "agents/COMMUNICATION_PROTOCOL.md",
            "responsibility_unit": "existing materializer-backed validation route",
            "intent_id": "W2-v16-runtime-recovery",
            "outcome": "pending",
            "evidence_refs": ["tools/runtime/artifacts/report_artifact_checks.py"],
            "artifact_refs": ["work_log.md"],
            "source_binding": {
                "run_id": report_dir.name,
                "context_id": report_dir.name,
            },
            "logical_key_sha256": logical_key_sha256,
            "attempt_ordinal": attempt_ordinal,
            "route_record_id": route_id,
            "route_record_body_sha256": route["route_record_body_sha256"],
            "producer_role_id": producer_role_id,
            "producer_runtime_agent_id": producer_runtime_agent_id,
        }
        from tools.runtime.archive.work_log import append_ledger_event

        append_ledger_event(report_dir, pending)
    pending_event_sha256 = _validation_event_hash(pending)
    seed = (
        "agent-canon.validation-result-artifact.v1\0"
        f"logical-key-sha256={logical_key_sha256}\0"
        f"attempt-ordinal={attempt_ordinal:016x}\0"
        f"pending-event-id-size={len(str(pending['event_id']).encode('utf-8')):016x}\0"
        f"pending-event-id={pending['event_id']}\0"
        f"pending-event-sha256={pending_event_sha256}\0"
        "end\0"
    ).encode()
    artifact_digest = hashlib.sha256(seed).hexdigest()
    artifact_id = f"validation-result:{artifact_digest}"
    artifact_root = report_dir / "results" / "validation" / artifact_digest
    route_command = route["command"]
    if not is_string_object_mapping(route_command):
        raise ValidationMaterializerError("validation_route:schema_mismatch")
    argv = route_command.get("argv")
    if not is_object_list(argv) or any(not isinstance(item, str) for item in argv):
        raise ValidationMaterializerError("validation_route:argv_mismatch")
    version = subprocess.run(
        [str(item) for item in argv[:1]] + ["--version"],
        cwd=workspace.resolve(),
        check=False,
        capture_output=True,
    )
    version_stdout = bytes(version.stdout)
    version_stderr = bytes(version.stderr)
    if version.returncode == 0:
        validation = subprocess.run(
            [str(item) for item in argv],
            cwd=workspace.resolve(),
            check=False,
            capture_output=True,
        )
        validation_stdout = bytes(validation.stdout)
        validation_stderr = bytes(validation.stderr)
        validation_state = "eof_complete"
        validation_returncode: int | None = validation.returncode
    else:
        validation_stdout = b""
        validation_stderr = b""
        validation_state = "not_created"
        validation_returncode = None
    version_state = "eof_complete"
    streams = {
        "version": {
            "stdout": _validation_stream(
                version_stdout,
                version.returncode,
                version_state,
                "stdout",
                "version.stdout",
            ),
            "stderr": _validation_stream(
                version_stderr,
                version.returncode,
                version_state,
                "stderr",
                "version.stderr",
            ),
        },
        "validation": {
            "stdout": _validation_stream(
                validation_stdout,
                validation_returncode,
                validation_state,
                "stdout",
                "validation.stdout",
            ),
            "stderr": _validation_stream(
                validation_stderr,
                validation_returncode,
                validation_state,
                "stderr",
                "validation.stderr",
            ),
        },
    }
    outcome = (
        "pass" if version.returncode == 0 and validation_returncode == 0 else "fail"
    )
    failure_codes = [] if outcome == "pass" else ["validation_route:command_failed"]
    manifest: dict[str, object] = {
        "schema": "agent-canon.validation-result-manifest.v1",
        "schema_version": 1,
        "artifact_id": artifact_id,
        "artifact_root_run_relative": f"results/validation/{artifact_digest}",
        "artifact_root_repo_relative": (
            f"reports/agents/{report_dir.name}/results/validation/{artifact_digest}"
        ),
        "leaves": list(VALIDATION_LEAVES),
        "run_locator_ref": {
            "run_locator_id": locator["run_locator_id"],
            "run_locator_body_sha256": locator["run_locator_body_sha256"],
        },
        "candidate": {
            "candidate_id": candidate_id,
            "candidate_revision": candidate_revision,
            "candidate_body_sha256": candidate["candidate_body_sha256"],
            "commit": candidate["candidate_commit"],
            "tree": candidate["candidate_tree"],
        },
        "route_record_ref": {
            "route_record_id": route_id,
            "route_record_body_sha256": route["route_record_body_sha256"],
        },
        "attempt": {
            "logical_key_sha256": logical_key_sha256,
            "attempt_ordinal": attempt_ordinal,
            "pending_event_id": pending["event_id"],
            "pending_event_sha256": pending_event_sha256,
        },
        "streams": streams,
        "observations": [
            "before_version_spawn",
            "after_version_capture_before_validation",
            "after_validation_capture",
        ],
        "termination": {
            "version_returncode": version.returncode,
            "validation_returncode": validation_returncode,
        },
        "failure_codes": failure_codes,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    for name, data in (
        ("version.stdout", version_stdout),
        ("version.stderr", version_stderr),
        ("validation.stdout", validation_stdout),
        ("validation.stderr", validation_stderr),
    ):
        _write_validation_leaf(artifact_root / name, data)
    _write_validation_leaf(artifact_root / "result_manifest.json", manifest_bytes)
    terminal_id = f"validation-terminal:{artifact_id}:{outcome}"
    terminal_event = {
        **pending,
        "event_id": terminal_id,
        "outcome": outcome,
        "pending_event_id": pending["event_id"],
        "pending_event_sha256": pending_event_sha256,
        "current_event_id": terminal_id,
        "producer_role_id": producer_role_id,
        "producer_runtime_agent_id": producer_runtime_agent_id,
        "artifact": {
            "artifact_id": artifact_id,
            "manifest_path": f"results/validation/{artifact_digest}/result_manifest.json",
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "manifest_blob": git_blob_oid(manifest_bytes),
        },
        "evidence_refs": [
            f"results/validation/{artifact_digest}/{name}" for name in VALIDATION_LEAVES
        ],
        "completed_at_utc": "materialized",
    }
    from tools.runtime.archive.work_log import append_ledger_event

    append_ledger_event(report_dir, terminal_event)
    return _validation_projection(
        locator,
        candidate,
        terminal_event,
        artifact_root / "result_manifest.json",
        manifest,
    )


def _validation_projection(
    locator: Mapping[str, object],
    candidate: Mapping[str, object],
    terminal_event: Mapping[str, object],
    manifest_path: Path,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    """Project one materializer-owned terminal event into ValidationResult v1."""
    artifact_id = manifest.get("artifact_id")
    manifest_bytes = _validation_stable_bytes(manifest_path)
    outcome = terminal_event.get("outcome")
    if outcome not in {"pass", "fail"} or not isinstance(artifact_id, str):
        raise ValidationMaterializerError("validation_result:stored_outcome_mismatch")
    artifact_digest = artifact_id.removeprefix("validation-result:")
    artifact = {
        "artifact_id": artifact_id,
        "root_repo_relative": (
            f"reports/agents/{manifest_path.parents[3].name}/results/validation/{artifact_digest}"
        ),
        "manifest_path": (f"results/validation/{artifact_digest}/result_manifest.json"),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "manifest_blob": git_blob_oid(manifest_bytes),
    }
    attempt = {
        "logical_key_sha256": terminal_event.get("logical_key_sha256"),
        "attempt_ordinal": terminal_event.get("attempt_ordinal"),
        "pending_event_id": terminal_event.get("pending_event_id"),
        "pending_event_sha256": terminal_event.get("pending_event_sha256"),
        "current_event_id": terminal_event.get(
            "current_event_id", terminal_event.get("event_id")
        ),
        "current_event_sha256": _validation_event_hash(terminal_event),
    }
    writer = candidate.get("writer")
    writer_runtime_agent_id = (
        writer.get("runtime_agent_id") if is_string_object_mapping(writer) else None
    )
    failure_value = manifest.get("failure_codes", [])
    failure_codes = (
        [item for item in failure_value if isinstance(item, str)]
        if is_object_list(failure_value)
        else []
    )
    producer = {
        "producer_role_id": terminal_event.get("producer_role_id"),
        "producer_runtime_agent_id": terminal_event.get("producer_runtime_agent_id"),
        "writer_runtime_agent_id": writer_runtime_agent_id,
    }
    core: dict[str, object] = {
        "schema": VALIDATION_RESULT_SCHEMA,
        "schema_version": 1,
        "run_locator_ref": {
            "run_locator_id": locator["run_locator_id"],
            "run_locator_body_sha256": locator["run_locator_body_sha256"],
        },
        "aggregate_identity": locator["run_id"],
        "candidate": {
            "candidate_id": candidate.get("candidate_id"),
            "candidate_revision": candidate.get("candidate_revision"),
            "candidate_body_sha256": candidate.get("candidate_body_sha256"),
            "commit": candidate.get("candidate_commit"),
            "tree": candidate.get("candidate_tree"),
        },
        "route_record_ref": {
            "route_record_id": terminal_event.get("route_record_id"),
            "route_record_body_sha256": terminal_event.get("route_record_body_sha256"),
        },
        "attempt": attempt,
        "artifact": artifact,
        "producer_evidence": producer,
        "outcome": outcome,
        "failure_codes": sorted(failure_codes, key=lambda item: item.encode("utf-8")),
        "validation_result_body_sha256": "",
    }
    core["validation_result_id"] = (
        "validation-result-projection:"
        + hashlib.sha256(
            canonical_json_bytes(
                {
                    "run_locator_id": locator["run_locator_id"],
                    "logical_key_sha256": attempt["logical_key_sha256"],
                    "attempt_ordinal": attempt["attempt_ordinal"],
                    "current_event_id": attempt["current_event_id"],
                    "outcome": outcome,
                    "failure_codes": core["failure_codes"],
                }
            )
        ).hexdigest()
    )
    core["validation_result_body_sha256"] = canonical_body_sha256(
        core,
        "validation_result_body_sha256",
    )
    return core


def resolve_validation_result(workspace: Path) -> dict[str, object]:
    """Regenerate the materializer-only validation projection from canonical L."""
    return materialize_required_validation(workspace)


def is_placeholder_only_section(text: str) -> bool:
    """Return whether the artifact still looks like an untouched template."""
    stripped = PLACEHOLDER_PATTERN.sub("", text).strip()
    stripped = "\n".join(
        line
        for line in stripped.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("- Run ID:")
        and not line.strip().startswith("- Task:")
        and not line.strip().startswith("- Owner:")
        and not line.strip().startswith("- Created At")
        and not line.strip().startswith("|")
    ).strip()
    return not stripped


def markdown_without_adjudicated_rejected_hypotheses(text: str) -> str:
    """Exclude only structurally valid rejected hypothesis table rows."""
    lines = text.splitlines()
    table_indexes: tuple[int, int, int] | None = None
    output: list[str] = []
    for line in lines:
        cells = tuple(cell.strip() for cell in line.split("|")[1:-1])
        normalized = tuple(
            re.sub(r"[^a-z0-9]+", "_", cell.lower()).strip("_") for cell in cells
        )
        if {
            "adjudication",
            "reason_code",
            "evidence_ref",
        }.issubset(normalized):
            table_indexes = (
                normalized.index("adjudication"),
                normalized.index("reason_code"),
                normalized.index("evidence_ref"),
            )
            output.append(line)
            continue
        if not cells or not line.lstrip().startswith("|"):
            table_indexes = None
            output.append(line)
            continue
        if table_indexes is not None:
            adjudication_index, reason_index, evidence_index = table_indexes
            indexes = (adjudication_index, reason_index, evidence_index)
            if max(indexes) < len(cells):
                adjudication = cells[adjudication_index].lower()
                reason_code = cells[reason_index].lower()
                evidence_ref = cells[evidence_index].lower()
                if (
                    adjudication == "rejected"
                    and reason_code not in REVIEW_ADJUDICATION_PLACEHOLDERS
                    and evidence_ref not in REVIEW_ADJUDICATION_PLACEHOLDERS
                ):
                    continue
        output.append(line)
    return "\n".join(output)


def section_has_content(text: str, heading: str) -> bool:
    """Return whether a markdown section exists and has non-placeholder content."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    if not in_section:
        return False
    body_text = PLACEHOLDER_PATTERN.sub("", "\n".join(body))
    body_text = "\n".join(
        line for line in body_text.splitlines() if line.strip()
    ).strip()
    return bool(body_text)


def bullet_rows(text: str, heading: str) -> list[str]:
    """Return bullet rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            rows.append(stripped)
    return rows


def token_fields(line: str) -> dict[str, str]:
    """Parse whitespace-separated key=value fields from one evidence line."""
    data: dict[str, str] = {}
    for token in line.strip().strip("-").strip("`").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip("`'\"")
    return data


def _git_report_paths(workspace: Path, args: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, "-z", "--", "reports"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _normalized_git_path(path: str) -> str:
    """Return a POSIX-style Git path for classification."""
    return path.replace("\\", "/").strip("/")


def _is_relative_to(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return whether a POSIX path is equal to or nested under root."""
    return path == root or path.is_relative_to(root)


def is_mechanically_regenerated_report_path(path: str) -> bool:
    """Return whether one report path is a known mechanically regenerated output."""
    normalized = _normalized_git_path(path)
    candidate = PurePosixPath(normalized)
    if any(
        _is_relative_to(candidate, root)
        for root in MECHANICALLY_REGENERATED_REPORT_ROOTS
    ):
        return True
    return any(
        pattern.match(normalized)
        for pattern in MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS
    )


def generated_report_artifact_blockers(workspace: Path) -> list[str]:
    """Return regenerated report outputs that should not remain in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if is_mechanically_regenerated_report_path(path)
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if is_mechanically_regenerated_report_path(path):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def generated_eval_transient_blockers(workspace: Path) -> list[str]:
    """Return exact two-level eval producer stdout/stderr captures in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path))
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def join_artifact_blockers(blockers: Sequence[str]) -> str:
    """Render blockers for compact shell output."""
    return "|".join(blockers) if blockers else "none"


def report_artifact_placement_blockers(workspace: Path, report_dir: Path) -> list[str]:
    """Return generated report artifacts outside the active run bundle.

    Tracked report history is baseline repository state and is not a placement
    error.  Untracked generated report files are allowed only under the current
    run directory because runtime archive tooling collects one active run bundle
    at closeout. Ignored non-generated report paths are local cache and do not
    block closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths: dict[str, str] = {}
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "ignored")

    blockers: list[str] = []
    report_root_metadata = {
        (report_dir.parent / ".active_run").resolve(),
        (report_dir.parent / ".active_run.sha256").resolve(),
        (report_dir.parent / ".run_bundle_materialization.lock").resolve(),
    }
    for path, state in sorted(report_paths.items()):
        candidate = workspace / path
        if candidate.resolve() in report_root_metadata:
            continue
        if candidate.resolve().is_relative_to(report_dir.resolve()):
            continue
        if state == "ignored" and not is_mechanically_regenerated_report_path(path):
            continue
        blockers.append(f"report_artifact_{state}_outside_current_run:{path}")
    return blockers


def check_work_log_artifact(text: str) -> list[str]:
    """Return blockers for work_log.md."""
    blockers: list[str] = []
    if not section_has_content(text, "## Entries"):
        blockers.append("work_log.md:section_empty_or_missing:entries")
        return blockers
    if not bullet_rows(text, "## Entries"):
        blockers.append("work_log.md:entries_empty")
    return blockers


def final_review_decision_lines(text: str) -> list[str]:
    """Return normalized non-placeholder lines from a final-review Decision section."""
    lines: list[str] = []
    in_decision = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_decision:
                break
            in_decision = stripped == "## Decision"
            continue
        if in_decision:
            normalized = PLACEHOLDER_PATTERN.sub("", line).strip()
            if normalized:
                lines.append(normalized)
    return lines


def has_approve_decision(text: str) -> bool:
    """Return whether a final-review Decision section contains an exact approve decision."""
    return any(
        APPROVE_DECISION_PATTERN.fullmatch(line)
        for line in final_review_decision_lines(text)
    )


@dataclass(frozen=True)
class ReviewIdentityResult:
    """Authoritative design-path, target-digest, and decision projection."""

    design_artifact_path: str | None
    review_target_sha256: str | None
    decision_approved: bool


def parse_review_identity(text: str) -> ReviewIdentityResult:
    """Parse one review identity through the shared structural decision owner."""
    path_matches = DESIGN_ARTIFACT_PATH_PATTERN.findall(text)
    sha_matches = REVIEW_TARGET_SHA_PATTERN.findall(text)
    return ReviewIdentityResult(
        design_artifact_path=(
            path_matches[-1].strip().strip("'\"") if path_matches else None
        ),
        review_target_sha256=(sha_matches[-1].lower() if sha_matches else None),
        decision_approved=has_approve_decision(text),
    )


def check_final_review_artifact(text: str) -> list[str]:
    """Return blockers for final_review.md."""
    blockers: list[str] = []
    if is_placeholder_only_section(text):
        blockers.append("final_review.md:placeholder_only")
    if not section_has_content(text, "## Decision"):
        blockers.append("final_review.md:section_empty_or_missing:decision")
        return blockers
    if not has_approve_decision(text):
        blockers.append("final_review.md:decision_not_approve")
    return blockers
