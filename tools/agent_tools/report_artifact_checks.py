#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../documents/design/request-intent-and-update-relation.md run-bundle temporary-state and retention readback projection
# upstream implementation ./work_log.py reconstructs the canonical logical ledger
# upstream implementation ./mid_task_user_input_policy.py defines mid-task user input evidence policy
# downstream implementation ./task_close.py consumes checked CompletionCoverage at closeout
# downstream implementation ./agent_canon_preflight.py blocks task-entry updates on eval transient captures
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
from typing import cast

try:
    from .parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )
except ImportError:
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )

from artifact_identity import canonical_body_sha256, canonical_json_bytes, git_blob_oid
from mid_task_user_input_policy import (
    MID_TASK_CLASSIFICATION_ACTIONS,
    MID_TASK_CLASSIFICATION_SCOPE_STATUS,
    MID_TASK_EVIDENCE_FIELDS,
    MID_TASK_REQUIRED_WAVE_FIELDS,
    MID_TASK_REUSE_MARKERS,
    MID_TASK_SPAWN_AUTHORITY,
    MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS,
    MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS,
    has_reuse_marker,
    is_empty_policy_value,
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
REQUIRED_ACTUAL_WAVE_FIELDS = (
    "wave_event",
    "wave_id",
    "event_kind",
    "spawn_authority",
    "trigger",
    "budget_before",
    "budget_after",
    "runtime_max_threads",
    "runtime_max_depth",
    "spawned_roles",
    "role_instances",
    "skipped_roles",
    "allowed_paths",
    "do_not_read",
    "write_scope",
    "validation_route",
    "review_gate",
    "handoff_artifacts",
    "status",
)
WAVE_COMPARISON_FIELDS = (
    ("Spawn Authority", "spawn_authority"),
    ("Trigger", "trigger"),
    ("Budget Before", "budget_before"),
    ("Budget After", "budget_after"),
    ("Runtime Max Threads", "runtime_max_threads"),
    ("Runtime Max Depth", "runtime_max_depth"),
    ("Role Instances", "role_instances"),
    ("Allowed Paths", "allowed_paths"),
    ("Do Not Read", "do_not_read"),
    ("Write Scope", "write_scope"),
    ("Validation Route", "validation_route"),
    ("Review Gate", "review_gate"),
    ("Handoff Artifacts", "handoff_artifacts"),
    ("Status", "status"),
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

# W2 completion coverage is a read model over the existing run ledger.  Keep
# these contracts here, beside the artifact checker, so task_close remains a
# consumer and no second persistence or closeout authority is introduced.
COMPLETION_COVERAGE_SCHEMA = "agent-canon.completion-coverage.v1"
VALIDATION_RESULT_SCHEMA = "agent-canon.validation-result-projection.v1"
VALIDATION_ROUTE_ID = "python.ruff.full"
VALIDATION_OWNER_PATHS = (
    "tools/agent_tools/review_dispatch.py",
    "tools/agent_tools/artifact_identity.py",
    "tools/agent_tools/external_artifact_binding.py",
    "tools/agent_tools/publication_integrator.py",
    "tools/agent_tools/report_artifact_checks.py",
    "tools/agent_tools/review_dispatch.py",
    "tools/agent_tools/work_log.py",
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
COMPLETION_COVERAGE_TAXONOMY_REFS = (
    "documents/runtime/runtime-profiles-and-check-matrix.json",
    "documents/runtime/runtime-profiles-and-check-matrix.md",
)
RUNTIME_PROFILE_TAXONOMY_PATH = (
    Path(__file__).resolve().parents[2]
    / "documents"
    / "runtime-profiles-and-check-matrix.json"
)
COMPLETION_SEMANTIC_KINDS = (
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
LEDGER_EVENT_REQUIRED_FIELDS = (
    "run_id",
    "context_id",
    "event_id",
    "semantic_kind",
    "owner",
    "state_owner",
    "api_owner",
    "dependency_owner",
    "responsibility_unit",
    "outcome",
    "intent_id",
    "evidence_refs",
    "artifact_refs",
)
GPU_CERTIFICATE_SEQUENCE = (
    "caller_candidate_uuid_set_A",
    "process_held_O_t_pid_start_identities",
    "active_reservations_R_t",
    "selected_uuids",
    "atomic_lock_lease_and_post_lock_readback",
    "effective_environment",
    "actual_terminal_gpu_process_identities",
    "release_or_retained_for_descendant_disposition",
    "typed_insufficient_eligible_or_mismatch_failure",
)
W1_CERTIFICATE_REQUIRED_FIELDS = (
    "run_id",
    "context_id",
    "producer_owner",
    "certificate_id",
    "sequence",
    "source_refs",
    "artifact_refs",
    "terminal_outcome",
)
SOURCE_BINDING_REQUIRED_FIELDS = (
    "run_id",
    "context_id",
    "organizer_context_id",
    "parent",
    "component_manager",
    "assigned_unit",
    "source_binding",
    "source_refs",
)
TOPOLOGY_BOOLEAN_FIELDS = (
    "writer_release_order_complete",
    "final_review_approved",
    "closeout_unlocked",
)
TOPOLOGY_REQUIRED_FIELDS = (
    "branch_creation_reason",
    "source_freeze_before_review",
    "formatter_static_events",
    "writer_cardinality",
    "writer_collision_state",
    "descendant_disposition",
    "topology_schema",
    "topology_order",
)
OOP_REVIEW_SIGNAL_GATE_IDS = frozenset({"oop_readability_guard", "solid_evidence_gate"})
BRANCH_CREATION_REASON = "convergence_w2_writer_owned_after_git_index_blocker"
TOPOLOGY_SCHEMA = "agent-canon.control-topology.v1"


@dataclass(frozen=True)
class TypedOwnerBoundaryEvidence:
    """Typed ownership evidence replacing scalar OOP heuristics."""

    owner: str
    state_owner: str
    api_owner: str
    dependency_owner: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ValidationFailureResponse:
    """Canonical pointer-only validation failure response."""

    failing_contract: str
    observation_level: str
    cause_classification: str
    intent_preservation: str
    evidence: tuple[str, ...]
    taxonomy_refs: tuple[str, ...]
    same_intent_repair_or_escalation: str
    repair_or_escalation_owner: str
    repair_or_escalation_result: str
    result_artifact_refs: tuple[str, ...]


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
    if not baseline_bytes.endswith(b"\n") or len(baseline_bytes) != 65:
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
    from work_log import read_ledger_snapshot

    snapshot = read_ledger_snapshot(
        report_dir,
        f"validation-materializer-ledger:{report_dir.name}",
    )
    events = snapshot.get("events")
    if not isinstance(events, list):
        raise ValidationMaterializerError("validation_result:ledger_mismatch")
    return [event for event in events if isinstance(event, dict)]


def _current_validation_candidate(
    events: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return the highest immutable candidate already present in canonical L."""
    candidates: list[dict[str, object]] = []
    for event in events:
        payload = event.get("automatic_review")
        if isinstance(payload, Mapping) and payload.get("record_kind") == "candidate":
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
            isinstance(payload, Mapping)
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
            isinstance(payload, Mapping)
            and payload.get("record_kind") == "resume_event"
            and payload.get("candidate_id") == candidate_id
            and payload.get("review_frame_id") == frame.get("review_frame_id")
        ):
            observed = payload.get("observed_result")
            if isinstance(observed, Mapping):
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
            ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose="validation-artifact")
        )
        boundary = ParentRootSideEffectBoundary()
        receipt = boundary.resolve_parent_owned_path(attestation, path, "validation-artifact", create=False)
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
    if not isinstance(artifact, Mapping):
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
    if not isinstance(streams, Mapping):
        raise ValidationMaterializerError("validation_result:stream_mismatch")
    termination = manifest.get("termination")
    if not isinstance(termination, Mapping):
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
        if not isinstance(group_streams, Mapping):
            raise ValidationMaterializerError("validation_result:stream_mismatch")
        for stream_name, leaf_name in names.items():
            stream = group_streams.get(stream_name)
            if not isinstance(stream, Mapping):
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
            if not isinstance(artifact, Mapping) or artifact.get("path") != leaf_name:
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
        if not isinstance(artifact, Mapping):
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
        if not isinstance(manifest, Mapping):
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
            "state_owner": "tools/agent_tools/work_log.py",
            "api_owner": "tools/agent_tools/report_artifact_checks.py",
            "dependency_owner": "agents/COMMUNICATION_PROTOCOL.md",
            "responsibility_unit": "existing materializer-backed validation route",
            "intent_id": "W2-v16-runtime-recovery",
            "outcome": "pending",
            "evidence_refs": ["tools/agent_tools/report_artifact_checks.py"],
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
        from work_log import append_ledger_event

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
    if not isinstance(route_command, Mapping):
        raise ValidationMaterializerError("validation_route:schema_mismatch")
    argv = route_command.get("argv")
    if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
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
    from work_log import append_ledger_event

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
        writer.get("runtime_agent_id") if isinstance(writer, Mapping) else None
    )
    failure_value = manifest.get("failure_codes", [])
    failure_codes = (
        [item for item in failure_value if isinstance(item, str)]
        if isinstance(failure_value, list)
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


def _nonempty_text(value: object) -> str:
    """Return one required text field or raise a contract error."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("completion coverage required text is empty")
    return value.strip()


def _mapping_has_nonempty_text(mapping: Mapping[str, object], field: str) -> bool:
    """Return whether one mapping field contains non-empty text."""
    value = mapping.get(field)
    return isinstance(value, str) and bool(value.strip())


def _text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Return a deterministic tuple of non-empty string references."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of strings")
    result = tuple(_nonempty_text(item) for item in value)
    if not result:
        raise ValueError(f"{field_name} must not be empty")
    return result


def _source_binding_errors(binding: object) -> list[str]:
    """Return fail-closed errors for one artifact source binding."""
    errors: list[str] = []
    if not isinstance(binding, Mapping):
        return ["object"]
    for field in SOURCE_BINDING_REQUIRED_FIELDS:
        if field == "source_refs":
            value = binding.get(field)
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(ref, str) or not ref.strip() for ref in value)
            ):
                errors.append(field)
            continue
        if field == "source_binding":
            nested = binding.get(field)
            if not isinstance(nested, Mapping) or not nested:
                errors.append(field)
            continue
        value = binding.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(field)
    nested = binding.get("source_binding")
    if isinstance(nested, Mapping):
        for field in ("run_id", "context_id"):
            value = nested.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"nested:{field}")
        if nested.get("run_id") != binding.get("run_id"):
            errors.append("nested:run_id_binding")
        if nested.get("context_id") != binding.get("context_id"):
            errors.append("nested:context_id_binding")
    return sorted(set(errors))


def _mapping_text_list(value: object) -> bool:
    """Return whether a value is a non-empty list of non-empty text."""
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _typed_count_mapping(value: object) -> bool:
    """Return whether a typed OOP count projection has string keys and int values."""
    return isinstance(value, Mapping) and all(
        isinstance(key, str)
        and key.strip()
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        for key, count in value.items()
    )


def _oop_solid_gate_errors(evidence: Mapping[str, object]) -> list[str]:
    """Validate changed-path OOP and SOLID evidence at the gate boundary."""
    gate_id = evidence.get("gate_id")
    errors: list[str] = []
    if gate_id == "oop_readability_guard":
        if not _mapping_text_list(evidence.get("scanned_paths")):
            errors.append("scanned_paths")
        for field in ("signal_counts", "typed_boundary_counts", "solid_counts"):
            if not _typed_count_mapping(evidence.get(field)):
                errors.append(field)
        if evidence.get("typed_evidence_owner") != "oop-readability-checker":
            errors.append("typed_evidence_owner")
    elif gate_id == "solid_evidence_gate":
        if not _mapping_text_list(evidence.get("scanned_paths")):
            errors.append("scanned_paths")
        if not _mapping_text_list(evidence.get("covered_paths")):
            errors.append("covered_paths")
        if not _typed_count_mapping(evidence.get("solid_counts")):
            errors.append("solid_counts")
    return errors


def _topology_errors(snapshot: object) -> list[str]:
    """Return typed topology errors used by the delivery boundary."""
    if not isinstance(snapshot, Mapping):
        return ["object"]
    errors: list[str] = []
    for field in (
        "run_id",
        "context_id",
        "observation_ref",
        "global_publication_state",
        "routing_gate",
    ):
        value = snapshot.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(field)
    for field in TOPOLOGY_BOOLEAN_FIELDS:
        if not isinstance(snapshot.get(field), bool):
            errors.append(field)
    for field in TOPOLOGY_REQUIRED_FIELDS:
        value = snapshot.get(field)
        if field in {"source_freeze_before_review"}:
            if not isinstance(value, bool):
                errors.append(field)
        elif field in {"writer_cardinality"}:
            if value != 1:
                errors.append(field)
        elif field in {"formatter_static_events", "topology_order"}:
            if not _mapping_text_list(value):
                errors.append(field)
        elif field == "descendant_disposition":
            if (
                not isinstance(value, Mapping)
                or not value
                or not any(
                    _mapping_has_nonempty_text(value, key)
                    for key in ("status", "release", "retained")
                )
            ):
                errors.append(field)
        elif field == "writer_collision_state":
            if value != "collision_preserved":
                errors.append(field)
        elif field == "topology_schema":
            if value != TOPOLOGY_SCHEMA:
                errors.append(field)
        elif field == "branch_creation_reason":
            if value != BRANCH_CREATION_REASON:
                errors.append(field)
        elif not isinstance(value, str) or not value.strip():
            errors.append(field)
    order = snapshot.get("topology_order")
    if isinstance(order, list) and _mapping_text_list(order):
        if len(order) != len(set(order)):
            errors.append("topology_order:duplicate")
        try:
            if order.index("source_frozen") > order.index("change_review_approved"):
                errors.append("topology_order:freeze_after_review")
        except ValueError:
            errors.append("topology_order:freeze_or_review_missing")
    return sorted(set(errors))


def _open_state_errors(value: object, field: str) -> list[str]:
    """Return schema errors for one non-routing open-state list."""
    if not isinstance(value, list):
        return [f"{field}:list"]
    errors: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str) and item.strip():
            continue
        if isinstance(item, Mapping) and any(
            _mapping_has_nonempty_text(item, key) for key in ("id", "ref", "identity")
        ):
            continue
        errors.append(f"{field}:item:{index}")
    return errors


def _taxonomy_values(field: str) -> frozenset[str]:
    """Read one canonical validation taxonomy set without copying its values."""
    raw = json.loads(RUNTIME_PROFILE_TAXONOMY_PATH.read_text(encoding="utf-8"))
    policy = raw.get("validation_failure_response") if isinstance(raw, dict) else None
    values = policy.get(field) if isinstance(policy, Mapping) else None
    if not isinstance(values, list) or not values:
        raise ValueError(f"validation taxonomy missing {field}")
    return frozenset(_nonempty_text(value) for value in values)


def _validate_failure_taxonomy_values(
    cause_classification: str,
    intent_preservation: str,
) -> None:
    """Validate failure slugs against the JSON-owned taxonomy."""
    if cause_classification not in _taxonomy_values("cause_classes"):
        raise ValueError(f"unsupported cause_classification: {cause_classification}")
    if intent_preservation not in _taxonomy_values("intent_preservation"):
        raise ValueError(f"unsupported intent_preservation: {intent_preservation}")


def _event_records(ledger_snapshot: object) -> tuple[dict[str, object], ...]:
    """Read the existing logical ledger snapshot without creating a store."""
    raw_events: object = ledger_snapshot
    if isinstance(ledger_snapshot, Mapping):
        raw_events = ledger_snapshot.get("events")
    if not isinstance(raw_events, (list, tuple)):
        raise ValueError("ledger_snapshot.events must be a list")
    events: list[dict[str, object]] = []
    identities: set[str] = set()
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, Mapping):
            raise ValueError(f"ledger event {index} must be an object")
        event = dict(raw_event)
        identity = _nonempty_text(event.get("event_id", event.get("sequence", "")))
        if identity in identities:
            raise ValueError(f"duplicate ledger event identity: {identity}")
        identities.add(identity)
        semantic_kind = _nonempty_text(event.get("semantic_kind"))
        if semantic_kind not in COMPLETION_SEMANTIC_KINDS:
            raise ValueError(f"unsupported semantic_kind: {semantic_kind}")
        for field in LEDGER_EVENT_REQUIRED_FIELDS:
            if field in {"event_id", "semantic_kind"}:
                continue
            if field.endswith("_refs"):
                _text_tuple(event.get(field), field)
            else:
                _nonempty_text(event.get(field))
        if event.get("clause_id") is not None:
            _nonempty_text(event.get("clause_id"))
        events.append(event)
    return tuple(
        sorted(
            events,
            key=lambda event: (
                str(event.get("sequence", "")),
                str(event.get("event_id", "")),
            ),
        )
    )


def _owner_evidence(event: Mapping[str, object]) -> dict[str, object]:
    """Project typed owner/state/API/dependency evidence from one event."""
    evidence = TypedOwnerBoundaryEvidence(
        owner=_nonempty_text(event.get("owner")),
        state_owner=_nonempty_text(event.get("state_owner")),
        api_owner=_nonempty_text(event.get("api_owner")),
        dependency_owner=_nonempty_text(event.get("dependency_owner")),
        evidence_refs=_text_tuple(event.get("evidence_refs"), "evidence_refs"),
    )
    return {
        "owner": evidence.owner,
        "state_owner": evidence.state_owner,
        "api_owner": evidence.api_owner,
        "dependency_owner": evidence.dependency_owner,
        "evidence_refs": list(evidence.evidence_refs),
    }


def _mapping_from_event(event: Mapping[str, object]) -> dict[str, object] | None:
    """Return one direct/group clause mapping when the event carries a clause."""
    clause_id = event.get("clause_id")
    if clause_id is None:
        return None
    mapping_mode = _nonempty_text(event.get("mapping_mode", "direct"))
    member_clause_ids = event.get("member_clause_ids", [clause_id])
    members = _text_tuple(member_clause_ids, "member_clause_ids")
    semantic_kind = _nonempty_text(event.get("semantic_kind"))
    if mapping_mode == "group" and semantic_kind in NON_GROUPABLE_SEMANTIC_KINDS:
        raise ValueError(f"{semantic_kind} mappings cannot be grouped")
    if mapping_mode not in {"direct", "group"}:
        raise ValueError(f"unsupported mapping_mode: {mapping_mode}")
    if mapping_mode == "direct" and members != (_nonempty_text(clause_id),):
        raise ValueError("direct mappings must contain exactly their clause_id")
    if mapping_mode == "group" and len(set(members)) < 2:
        raise ValueError("group mappings require at least two distinct member clauses")
    source_event_ref = _nonempty_text(event.get("event_id", event.get("sequence", "")))
    group_identity = _nonempty_text(
        event.get("group_identity", event.get("group_id", source_event_ref))
    )
    return {
        "clause_id": _nonempty_text(clause_id),
        "mapping_mode": mapping_mode,
        "group_identity": group_identity,
        "owner": _nonempty_text(event.get("owner")),
        "state_owner": _nonempty_text(event.get("state_owner")),
        "api_owner": _nonempty_text(event.get("api_owner")),
        "dependency_owner": _nonempty_text(event.get("dependency_owner")),
        "responsibility_unit": _nonempty_text(event.get("responsibility_unit")),
        "outcome": _nonempty_text(event.get("outcome")),
        "member_clause_ids": list(members),
        "semantic_kind": semantic_kind,
        "evidence_refs": list(_text_tuple(event.get("evidence_refs"), "evidence_refs")),
        "source_event_ref": source_event_ref,
    }


def _resource_certificate_errors(
    certificate: Mapping[str, object],
    source_binding: Mapping[str, object],
) -> list[str]:
    """Validate W1 certificate shape without recomputing resource semantics."""
    errors: list[str] = []
    for field in W1_CERTIFICATE_REQUIRED_FIELDS:
        value = certificate.get(field)
        if not value:
            errors.append(f"missing:{field}")
        if field == "sequence" and not (
            (isinstance(value, str) and bool(value.strip()))
            or _mapping_text_list(value)
        ):
            errors.append("typed:sequence")
    for field in (
        "run_id",
        "context_id",
        "producer_owner",
        "certificate_id",
        "terminal_outcome",
    ):
        value = certificate.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"typed:{field}")
    if certificate.get("producer_owner") != "W1":
        errors.append("producer_owner")
    for field in ("source_refs", "artifact_refs"):
        if not _mapping_text_list(certificate.get(field)):
            errors.append(f"typed:{field}")
    for field in ("run_id", "context_id"):
        if certificate.get(field) != source_binding.get(
            "run_id" if field == "run_id" else "context_id"
        ):
            errors.append(f"binding:{field}")
    sections = (
        "applicability",
        "plan",
        "actual",
        "readback",
        "environment",
        "terminal",
        "cleanup",
        "failure",
    )
    for field in sections:
        section = certificate.get(field)
        if not isinstance(section, Mapping):
            errors.append(f"missing:{field}")
            continue
        evidence_refs = section.get("evidence_refs")
        if not _mapping_text_list(evidence_refs):
            errors.append(f"typed_evidence:{field}:evidence_refs")
        if field == "applicability" and section.get("applicable") is not True:
            errors.append("applicability:not_applicable")
    gpu_items = certificate.get("gpu_semantics")
    if gpu_items is not None:
        if not isinstance(gpu_items, list):
            errors.append("gpu_semantics")
        else:
            if any(not isinstance(item, Mapping) for item in gpu_items):
                errors.append("gpu_semantics:item_shape")
            observed = [
                item.get("item") for item in gpu_items if isinstance(item, Mapping)
            ]
            if observed != list(GPU_CERTIFICATE_SEQUENCE) or len(gpu_items) != len(
                GPU_CERTIFICATE_SEQUENCE
            ):
                errors.append("gpu_semantics:ordered_nine_items")
            for item in gpu_items:
                if not isinstance(item, Mapping) or any(
                    not item.get(field)
                    for field in (
                        "item",
                        "semantic_identity",
                        "consumer_rule",
                        "evidence_refs",
                    )
                ):
                    errors.append("gpu_semantics:item_evidence")
                elif (
                    not isinstance(item.get("evidence_refs"), list)
                    or any(
                        not isinstance(ref, str) or not ref.strip()
                        for ref in item.get("evidence_refs", [])
                    )
                    or not item.get("evidence_refs")
                ):
                    errors.append("gpu_semantics:item_evidence_refs")
    return sorted(set(errors))


def materialize_completion_coverage_from_work_log(
    report_dir: Path,
    snapshot_identity: str,
    source_binding: Mapping[str, object],
    active_clause_ids: Sequence[str],
    owner_contract: Mapping[str, object],
    schedule_state_non_routing: Mapping[str, object],
    open_work_state_non_routing: Mapping[str, object],
    repair_state_non_routing: Mapping[str, object],
    crossing_edge_state_non_routing: Mapping[str, object],
    control_topology_ledger_snapshot: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
    monitor_evidence: Sequence[Mapping[str, object]] = (),
) -> Path:
    """Read the canonical work ledger and materialize one checked read model."""
    from work_log import read_ledger_snapshot

    ledger_snapshot = read_ledger_snapshot(report_dir, snapshot_identity)
    return write_completion_coverage_artifact(
        report_dir,
        ledger_snapshot,
        source_binding,
        active_clause_ids,
        owner_contract,
        schedule_state_non_routing,
        open_work_state_non_routing,
        repair_state_non_routing,
        crossing_edge_state_non_routing,
        control_topology_ledger_snapshot,
        taxonomy_refs,
        monitor_evidence,
    )


def generated_completion_coverage_errors(
    report_dir: Path, artifact: Mapping[str, object]
) -> list[str]:
    """Reject a hand-written artifact by comparing it with the canonical ledger projection."""
    metadata = artifact.get("projection_metadata")
    source_binding = artifact.get("source_binding")
    if not isinstance(metadata, Mapping) or not isinstance(source_binding, Mapping):
        return ["generated_projection_metadata_missing"]
    snapshot_identity = metadata.get("ledger_snapshot_identity")
    if not isinstance(snapshot_identity, str) or not snapshot_identity.strip():
        return ["ledger_snapshot_identity_missing"]
    try:
        from work_log import ledger_snapshot_digest, read_ledger_snapshot

        snapshot = read_ledger_snapshot(report_dir, snapshot_identity)
        expected = project_completion_coverage(snapshot, source_binding)
        expected_digest = ledger_snapshot_digest(snapshot)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"ledger_projection_error:{exc}"]
    errors: list[str] = []
    if metadata.get("ledger_snapshot_digest") != expected_digest:
        errors.append("ledger_snapshot_digest_mismatch")
    for field in (
        "schema",
        "source_binding",
        "projection_metadata",
        "semantic_events",
        "coverage_map",
        "owner_boundary_evidence",
        "gate_evidence",
        "monitor_evidence",
        "failure_event_refs",
        "failure_responses",
        "resource_certificates",
        "resource_certificate_errors",
    ):
        if artifact.get(field) != expected.get(field):
            errors.append(f"generated_projection_mismatch:{field}")
    return sorted(set(errors))


def project_completion_coverage(
    ledger_snapshot: object,
    source_binding: Mapping[str, object],
    schema_version: str = COMPLETION_COVERAGE_SCHEMA,
    monitor_evidence: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Generate the deterministic v1 reader model from one ledger snapshot."""
    if schema_version != COMPLETION_COVERAGE_SCHEMA:
        raise ValueError(f"unsupported completion coverage schema: {schema_version}")
    binding = {key: value for key, value in source_binding.items()}
    for field in (
        "run_id",
        "context_id",
        "organizer_context_id",
        "parent",
        "component_manager",
        "assigned_unit",
        "source_binding",
        "source_refs",
    ):
        if field == "source_refs":
            binding[field] = list(_text_tuple(binding.get(field), field))
        elif field == "source_binding":
            if not isinstance(binding.get(field), Mapping) or not binding[field]:
                raise ValueError("source_binding must be a non-empty object")
        else:
            binding[field] = _nonempty_text(binding.get(field))
    nested_binding = cast(Mapping[str, object], binding["source_binding"])
    binding["source_binding"] = dict(nested_binding)
    if nested_binding.get("run_id") != binding["run_id"]:
        raise ValueError("source_binding.run_id does not match run_id")
    if nested_binding.get("context_id") != binding["context_id"]:
        raise ValueError("source_binding.context_id does not match context_id")
    binding_errors = _source_binding_errors(binding)
    if binding_errors:
        raise ValueError("source_binding contract errors: " + ",".join(binding_errors))
    events = _event_records(ledger_snapshot)
    for event in events:
        if event.get("run_id") != binding["run_id"]:
            raise ValueError("ledger event run_id does not match source binding")
        if event.get("context_id") != binding["context_id"]:
            raise ValueError("ledger event context_id does not match source binding")
        event_binding = event.get("source_binding")
        if event_binding is not None and event_binding != binding["source_binding"]:
            raise ValueError(
                "ledger event source_binding does not match source binding"
            )
    mappings = [mapping for event in events if (mapping := _mapping_from_event(event))]
    resource_certificates = []
    for event in events:
        certificate = event.get("resource_certificate")
        if not isinstance(certificate, Mapping):
            continue
        certificate_record = dict(certificate)
        certificate_record["source_event_ref"] = _nonempty_text(
            event.get("event_id", event.get("sequence", ""))
        )
        certificate_record["source_clause_id"] = event.get("clause_id")
        resource_certificates.append(certificate_record)
    semantic_events: list[dict[str, object]] = []
    gate_evidence: list[dict[str, object]] = []
    projected_monitor_evidence: list[dict[str, object]] = []
    for event in events:
        event_id = _nonempty_text(event.get("event_id", event.get("sequence", "")))
        semantic_event: dict[str, object] = {
            "run_id": _nonempty_text(event.get("run_id")),
            "context_id": _nonempty_text(event.get("context_id")),
            "event_id": event_id,
            "sequence": str(event.get("sequence", "")),
            "semantic_kind": _nonempty_text(event.get("semantic_kind")),
            "owner_evidence": _owner_evidence(event),
            "responsibility_unit": _nonempty_text(event.get("responsibility_unit")),
            "intent_id": _nonempty_text(event.get("intent_id")),
            "outcome": _nonempty_text(event.get("outcome")),
            "evidence_refs": list(
                _text_tuple(event.get("evidence_refs"), "evidence_refs")
            ),
            "artifact_refs": list(
                _text_tuple(event.get("artifact_refs"), "artifact_refs")
            ),
            "source_binding": dict(binding["source_binding"]),
        }
        if event.get("clause_id") is not None:
            semantic_event["clause_id"] = _nonempty_text(event.get("clause_id"))
            semantic_event["mapping_mode"] = _nonempty_text(
                event.get("mapping_mode", "direct")
            )
            semantic_event["member_clause_ids"] = list(
                _text_tuple(
                    event.get("member_clause_ids", [event.get("clause_id")]),
                    "member_clause_ids",
                )
            )
            semantic_event["group_identity"] = _nonempty_text(
                event.get("group_identity", event.get("group_id", event_id))
            )
        for optional_field in (
            "gate_evidence",
            "failure_response",
            "resource_certificate",
            "monitor_evidence",
            "monitoring_evidence",
        ):
            optional_value = event.get(optional_field)
            if optional_value is not None:
                semantic_event[optional_field] = optional_value
        semantic_events.append(semantic_event)

        raw_gate_evidence = event.get("gate_evidence")
        gate_records = (
            [raw_gate_evidence]
            if isinstance(raw_gate_evidence, Mapping)
            else raw_gate_evidence
            if isinstance(raw_gate_evidence, list)
            else []
        )
        if raw_gate_evidence is not None and not gate_records:
            raise ValueError("ledger gate_evidence must be an object or list")
        for raw_gate in gate_records:
            if not isinstance(raw_gate, Mapping):
                raise ValueError("ledger gate_evidence entries must be objects")
            gate = dict(raw_gate)
            gate["source_event_refs"] = list(
                _text_tuple(
                    gate.get("source_event_refs", [event_id]), "source_event_refs"
                )
            )
            gate_evidence.append(gate)

        for monitor_field in ("monitor_evidence", "monitoring_evidence"):
            raw_monitor = event.get(monitor_field)
            monitor_records = (
                [raw_monitor]
                if isinstance(raw_monitor, Mapping)
                else raw_monitor
                if isinstance(raw_monitor, list)
                else []
            )
            if raw_monitor is not None and not monitor_records:
                raise ValueError(f"ledger {monitor_field} must be an object or list")
            for raw_record in monitor_records:
                if not isinstance(raw_record, Mapping):
                    raise ValueError(f"ledger {monitor_field} entries must be objects")
                record = dict(raw_record)
                record["run_id"] = _nonempty_text(
                    record.get("run_id", binding["run_id"])
                )
                record["context_id"] = _nonempty_text(
                    record.get("context_id", binding["context_id"])
                )
                if (
                    record["run_id"] != binding["run_id"]
                    or record["context_id"] != binding["context_id"]
                ):
                    raise ValueError("ledger monitor evidence binding mismatch")
                record["source_event_ref"] = event_id
                projected_monitor_evidence.append(record)
    for index, raw_monitor in enumerate(monitor_evidence):
        if not isinstance(raw_monitor, Mapping):
            raise ValueError(f"monitor_evidence[{index}] must be an object")
        record = dict(raw_monitor)
        record["run_id"] = _nonempty_text(record.get("run_id", binding["run_id"]))
        record["context_id"] = _nonempty_text(
            record.get("context_id", binding["context_id"])
        )
        if (
            record["run_id"] != binding["run_id"]
            or record["context_id"] != binding["context_id"]
        ):
            raise ValueError("monitor evidence binding mismatch")
        projected_monitor_evidence.append(record)
    snapshot_digest = (
        str(ledger_snapshot.get("snapshot_digest", ""))
        if isinstance(ledger_snapshot, Mapping)
        else ""
    )
    if not snapshot_digest:
        events_payload = json.dumps(events, sort_keys=True, separators=(",", ":"))
        snapshot_digest = hashlib.sha256(events_payload.encode("utf-8")).hexdigest()
    return {
        "schema": COMPLETION_COVERAGE_SCHEMA,
        "source_binding": binding,
        "projection_metadata": {
            "deterministic_order": "sequence,event_id",
            "ledger_snapshot_identity": _nonempty_text(
                ledger_snapshot.get("snapshot_identity")
                if isinstance(ledger_snapshot, Mapping)
                else "in_memory_snapshot"
            ),
            "ledger_snapshot_digest": snapshot_digest,
            "generated_artifact_identity": f"{binding['run_id']}:{binding['context_id']}",
            "semantic_kinds": list(COMPLETION_SEMANTIC_KINDS),
            "source_refs": list(cast(list[str], binding["source_refs"])),
        },
        "semantic_events": semantic_events,
        "coverage_map": mappings,
        "owner_boundary_evidence": [
            event["owner_evidence"] for event in semantic_events
        ],
        "gate_evidence": gate_evidence,
        "monitor_evidence": projected_monitor_evidence,
        "failure_event_refs": [
            _nonempty_text(event.get("event_id", event.get("sequence", "")))
            for event in events
            if event.get("semantic_kind") == "failure"
        ],
        "failure_responses": [
            {
                **dict(cast(Mapping[str, object], event["failure_response"])),
                "source_event_ref": _nonempty_text(
                    event.get("event_id", event.get("sequence", ""))
                ),
            }
            for event in events
            if isinstance(event.get("failure_response"), Mapping)
        ],
        "resource_certificates": resource_certificates,
        "resource_certificate_errors": [
            {
                "certificate_id": certificate.get("certificate_id", ""),
                "source_event_ref": certificate.get("source_event_ref", ""),
                "errors": _resource_certificate_errors(certificate, binding),
            }
            for certificate in resource_certificates
        ],
    }


def _empty_error_sets() -> dict[str, list[str]]:
    """Return the five explicit mapping error sets."""
    return {
        "uncovered": [],
        "multiply_mapped": [],
        "orphan": [],
        "redundant": [],
        "empty": [],
    }


def check_completion_coverage(
    completion_coverage: Mapping[str, object],
    active_clause_ids: Sequence[str],
    owner_contract: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
) -> dict[str, object]:
    """Check exact mappings and typed gate evidence without scalar heuristics."""
    errors = _empty_error_sets()
    owner_contract_for_check: Mapping[str, object] = (
        owner_contract if isinstance(owner_contract, Mapping) else {}
    )
    if not isinstance(owner_contract, Mapping):
        errors["empty"].append("owner_contract")
    if completion_coverage.get("schema") != COMPLETION_COVERAGE_SCHEMA:
        errors["empty"].append("schema")
    source_binding = completion_coverage.get("source_binding")
    if not isinstance(source_binding, Mapping):
        errors["empty"].append("source_binding")
    else:
        errors["empty"].extend(
            f"source_binding:{item}" for item in _source_binding_errors(source_binding)
        )
    binding_for_comparison: Mapping[str, object] = (
        source_binding if isinstance(source_binding, Mapping) else {}
    )
    expected = tuple(_nonempty_text(clause_id) for clause_id in active_clause_ids)
    expected_set = set(expected)
    if len(expected) != len(expected_set):
        errors["redundant"].append("duplicate_expected_clause_id")
    raw_mappings = completion_coverage.get("coverage_map", [])
    if not isinstance(raw_mappings, list):
        errors["empty"].append("coverage_map")
        raw_mappings = []
    by_clause: dict[str, list[Mapping[str, object]]] = {}
    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, Mapping):
            errors["empty"].append("mapping")
            continue
        clause_id = str(raw_mapping.get("clause_id", ""))
        members = raw_mapping.get("member_clause_ids")
        mode = raw_mapping.get("mapping_mode")
        group_identity = raw_mapping.get("group_identity")
        if (
            not isinstance(members, list)
            or not members
            or any(
                not isinstance(member, str) or not member.strip() for member in members
            )
        ):
            errors["empty"].append(clause_id or "mapping")
            members = []
        member_ids = [str(member) for member in members]
        if len(set(member_ids)) != len(member_ids):
            errors["redundant"].append(clause_id or "mapping")
        if mode == "direct":
            if member_ids != [clause_id]:
                errors["redundant"].append(clause_id or "mapping")
        elif mode == "group":
            if len(member_ids) < 2:
                errors["redundant"].append(clause_id or "mapping")
            if raw_mapping.get("semantic_kind") in NON_GROUPABLE_SEMANTIC_KINDS:
                errors["empty"].append(f"group:{clause_id or 'mapping'}")
            if clause_id not in member_ids:
                errors["redundant"].append(clause_id or "mapping")
            if not isinstance(group_identity, str) or not group_identity.strip():
                errors["empty"].append(f"group_identity:{clause_id or 'mapping'}")
        else:
            errors["empty"].append(clause_id or "mapping")
        required = (
            "owner",
            "state_owner",
            "api_owner",
            "dependency_owner",
            "responsibility_unit",
            "outcome",
            "semantic_kind",
            "source_event_ref",
            "group_identity",
        )
        if any(
            not isinstance(raw_mapping.get(field), str)
            or not str(raw_mapping.get(field)).strip()
            for field in required
        ) or not _mapping_text_list(raw_mapping.get("evidence_refs")):
            errors["empty"].append(clause_id or "mapping")
        for member_id in member_ids:
            by_clause.setdefault(member_id, []).append(raw_mapping)
            if member_id not in expected_set:
                errors["orphan"].append(member_id)
        if clause_id and clause_id not in expected_set:
            errors["orphan"].append(clause_id)
    for clause_id in expected:
        matches = by_clause.get(clause_id, [])
        if not matches:
            errors["uncovered"].append(clause_id)
        elif len(matches) != 1:
            errors["multiply_mapped"].append(clause_id)
    owner_fields = ("owner", "state_owner", "api_owner", "dependency_owner")
    if not all(
        _mapping_has_nonempty_text(owner_contract_for_check, field)
        for field in owner_fields
    ):
        errors["empty"].append("owner_contract")
    owner_evidence = completion_coverage.get("owner_boundary_evidence", [])
    owner_evidence_items = (
        cast(list[object], owner_evidence) if isinstance(owner_evidence, list) else []
    )
    if not isinstance(owner_evidence, list) or not owner_evidence:
        errors["empty"].append("owner_boundary_evidence")
    for evidence in owner_evidence_items:
        if (
            not isinstance(evidence, Mapping)
            or any(
                not _mapping_has_nonempty_text(evidence, field)
                for field in ("owner", "state_owner", "api_owner", "dependency_owner")
            )
            or not _mapping_text_list(evidence.get("evidence_refs"))
        ):
            errors["empty"].append("owner_boundary_evidence")
    if (
        isinstance(owner_evidence, list)
        and all(
            _mapping_has_nonempty_text(owner_contract_for_check, field)
            for field in ("owner", "state_owner", "api_owner", "dependency_owner")
        )
        and not any(
            isinstance(evidence, Mapping)
            and all(
                evidence.get(field) == owner_contract_for_check.get(field)
                for field in owner_fields
            )
            for evidence in owner_evidence_items
        )
    ):
        errors["empty"].append("owner_contract:correspondence")
    gate_evidence = completion_coverage.get("gate_evidence", [])
    gate_evidence_items = (
        cast(list[object], gate_evidence) if isinstance(gate_evidence, list) else []
    )
    if not isinstance(gate_evidence, list) or not gate_evidence:
        errors["empty"].append("gate_evidence")
    gate_ids: set[str] = set()
    for evidence in gate_evidence_items:
        if (
            not isinstance(evidence, Mapping)
            or any(
                not _mapping_has_nonempty_text(evidence, field)
                for field in ("gate_id", "stage", "owner", "outcome")
            )
            or not _mapping_text_list(evidence.get("artifact_refs"))
            or not _mapping_text_list(evidence.get("source_event_refs"))
        ):
            errors["empty"].append("gate_evidence")
            continue
        gate_id = str(evidence["gate_id"])
        if gate_id in gate_ids:
            errors["redundant"].append(f"gate_evidence:{gate_id}")
        gate_ids.add(gate_id)
        errors["empty"].extend(
            f"{gate_id}:{field}" for field in _oop_solid_gate_errors(evidence)
        )
    if tuple(taxonomy_refs) != COMPLETION_COVERAGE_TAXONOMY_REFS:
        errors["empty"].append("taxonomy_refs")
    certificate_results = completion_coverage.get("resource_certificate_errors", [])
    if not isinstance(certificate_results, list):
        errors["empty"].append("resource_certificate_errors")
        certificate_results = []
    certificate_ids: set[str] = set()
    for certificate_result in certificate_results:
        if not isinstance(certificate_result, Mapping):
            errors["empty"].append("resource_certificate")
            continue
        certificate_id = str(certificate_result.get("certificate_id", ""))
        if certificate_id in certificate_ids:
            errors["redundant"].append(f"resource_certificate:{certificate_id}")
        certificate_ids.add(certificate_id)
    for certificate_result in certificate_results:
        if isinstance(certificate_result, Mapping) and certificate_result.get("errors"):
            errors["empty"].append(
                f"resource_certificate:{certificate_result.get('certificate_id', '')}"
            )
    mappings_by_clause = {
        str(mapping.get("clause_id")): mapping
        for mapping in raw_mappings
        if isinstance(mapping, Mapping)
    }
    semantic_events = completion_coverage.get("semantic_events", [])
    semantic_event_items = (
        cast(list[object], semantic_events) if isinstance(semantic_events, list) else []
    )
    if not isinstance(semantic_events, list) or not semantic_events:
        errors["empty"].append("semantic_events")
    events_by_id = {
        str(event.get("event_id")): event
        for event in semantic_event_items
        if isinstance(event, Mapping) and event.get("event_id")
    }
    if isinstance(semantic_events, list):
        if len(events_by_id) != len(semantic_events):
            errors["redundant"].append("semantic_event_identity")
        for event in semantic_event_items:
            if not isinstance(event, Mapping):
                errors["empty"].append("semantic_event")
                continue
            if event.get("run_id") != binding_for_comparison.get("run_id"):
                errors["empty"].append("semantic_event:run_id_binding")
            if event.get("context_id") != binding_for_comparison.get("context_id"):
                errors["empty"].append("semantic_event:context_id_binding")
            if event.get("source_binding") != binding_for_comparison.get(
                "source_binding"
            ):
                errors["empty"].append("semantic_event:source_binding")
    for evidence in gate_evidence_items:
        if not isinstance(evidence, Mapping):
            continue
        refs = evidence.get("source_event_refs")
        if not _mapping_text_list(refs):
            continue
        refs_text = cast(list[str], refs)
        if len(set(refs_text)) != len(refs_text):
            errors["redundant"].append(f"gate_evidence:{evidence.get('gate_id', '')}")
        for event_ref in refs_text:
            if event_ref not in events_by_id:
                errors["empty"].append(f"gate_evidence:source_event:{event_ref}")
    projected_monitor_evidence = completion_coverage.get("monitor_evidence", [])
    if not isinstance(projected_monitor_evidence, list):
        errors["empty"].append("monitor_evidence")
        projected_monitor_evidence = []
    for evidence in projected_monitor_evidence:
        if not isinstance(evidence, Mapping):
            errors["empty"].append("monitor_evidence:item")
            continue
        source_event_ref = evidence.get("source_event_ref")
        if source_event_ref is not None and source_event_ref not in events_by_id:
            errors["empty"].append(f"monitor_evidence:source_event:{source_event_ref}")
    oop_signals = [
        evidence
        for evidence in gate_evidence_items
        if isinstance(evidence, Mapping)
        and evidence.get("gate_id") in OOP_REVIEW_SIGNAL_GATE_IDS
    ]
    if not oop_signals:
        errors["empty"].append("oop_review_signal")
    source_event_owners: dict[str, str] = {}
    group_facts: dict[str, tuple[object, ...]] = {}
    group_members: dict[str, set[str]] = {}
    for raw_mapping in raw_mappings:
        if not isinstance(raw_mapping, Mapping):
            continue
        source_event_ref = str(raw_mapping.get("source_event_ref", ""))
        clause_id = str(raw_mapping.get("clause_id", ""))
        if source_event_ref in source_event_owners:
            errors["redundant"].append(f"source_event:{source_event_ref}")
        source_event_owners[source_event_ref] = clause_id
        if raw_mapping.get("mapping_mode") == "group":
            group_identity = str(raw_mapping.get("group_identity", ""))
            facts = tuple(
                raw_mapping.get(field)
                for field in (
                    "owner",
                    "state_owner",
                    "api_owner",
                    "dependency_owner",
                    "responsibility_unit",
                    "outcome",
                )
            )
            prior_facts = group_facts.get(group_identity)
            if prior_facts is not None and prior_facts != facts:
                errors["empty"].append(f"group_identity:{group_identity}:member_facts")
            group_facts.setdefault(group_identity, facts)
            member_set = group_members.setdefault(group_identity, set())
            raw_members = raw_mapping.get("member_clause_ids")
            if isinstance(raw_members, list):
                if member_set.intersection(raw_members):
                    errors["redundant"].append(
                        f"group_identity:{group_identity}:members"
                    )
                member_set.update(str(member) for member in raw_members)
        source_event = events_by_id.get(source_event_ref)
        if source_event is None:
            errors["empty"].append(f"source_event:{source_event_ref or 'missing'}")
            continue
        owner_evidence = source_event.get("owner_evidence")
        if not isinstance(owner_evidence, Mapping):
            errors["empty"].append(f"source_event:{source_event_ref}:owner_evidence")
            continue
        correspondence = (
            ("owner", owner_evidence.get("owner")),
            ("state_owner", owner_evidence.get("state_owner")),
            ("api_owner", owner_evidence.get("api_owner")),
            ("dependency_owner", owner_evidence.get("dependency_owner")),
            ("responsibility_unit", source_event.get("responsibility_unit")),
            ("outcome", source_event.get("outcome")),
            ("semantic_kind", source_event.get("semantic_kind")),
            ("group_identity", source_event.get("group_identity", source_event_ref)),
            ("mapping_mode", source_event.get("mapping_mode", "direct")),
            ("evidence_refs", source_event.get("evidence_refs")),
            ("member_clause_ids", source_event.get("member_clause_ids")),
        )
        for field, expected_value in correspondence:
            actual_value = raw_mapping.get(field)
            if field in {"evidence_refs", "member_clause_ids"}:
                if actual_value != expected_value:
                    errors["empty"].append(
                        f"source_event:{source_event_ref}:{field}:correspondence"
                    )
            elif actual_value != expected_value:
                errors["empty"].append(
                    f"source_event:{source_event_ref}:{field}:correspondence"
                )
    certificates_by_event = {
        str(result.get("source_event_ref")): result
        for result in certificate_results
        if isinstance(result, Mapping)
    }
    certificate_source_refs = [
        str(result.get("source_event_ref"))
        for result in certificate_results
        if isinstance(result, Mapping) and result.get("source_event_ref")
    ]
    if len(certificate_source_refs) != len(set(certificate_source_refs)):
        errors["redundant"].append("resource_certificate:source_event_ref")
    resource_certificates_value = completion_coverage.get("resource_certificates", [])
    resource_certificate_items = (
        cast(list[object], resource_certificates_value)
        if isinstance(resource_certificates_value, list)
        else []
    )
    for certificate in resource_certificate_items:
        if not isinstance(certificate, Mapping):
            continue
        source_event_ref = str(certificate.get("source_event_ref", ""))
        source_event = events_by_id.get(source_event_ref)
        if source_event is None:
            errors["empty"].append(
                f"resource_certificate:source_event:{source_event_ref or 'missing'}"
            )
            continue
        if certificate.get("run_id") != binding_for_comparison.get("run_id"):
            errors["empty"].append(f"resource_certificate:{source_event_ref}:run_id")
        if certificate.get("context_id") != binding_for_comparison.get("context_id"):
            errors["empty"].append(
                f"resource_certificate:{source_event_ref}:context_id"
            )
        if certificate.get("source_clause_id") != source_event.get("clause_id"):
            errors["empty"].append(
                f"resource_certificate:{source_event_ref}:source_clause"
            )
    resource_mapping_event_refs: dict[str, str] = {}
    for clause_id in ("W2-12", "W2-19"):
        if clause_id not in expected_set:
            continue
        mapping = mappings_by_clause.get(clause_id)
        if not isinstance(mapping, Mapping) or mapping.get("mapping_mode") != "direct":
            errors["empty"].append(f"resource_mapping:{clause_id}")
            continue
        source_event_ref = str(mapping.get("source_event_ref", ""))
        resource_mapping_event_refs[clause_id] = source_event_ref
        if source_event_ref not in certificates_by_event:
            errors["empty"].append(f"resource_mapping:{clause_id}")
        certificate = next(
            (
                item
                for item in resource_certificate_items
                if isinstance(item, Mapping)
                and item.get("source_event_ref") == source_event_ref
            ),
            None,
        )
        if (
            not isinstance(certificate, Mapping)
            or certificate.get("source_clause_id") != clause_id
        ):
            errors["empty"].append(f"resource_mapping:{clause_id}:source_clause")
        if clause_id == "W2-19":
            if not isinstance(certificate, Mapping) or not isinstance(
                certificate.get("gpu_semantics"), list
            ):
                errors["empty"].append("resource_mapping:W2-19:gpu_semantics")
            elif [
                item.get("item")
                for item in certificate.get("gpu_semantics", [])
                if isinstance(item, Mapping)
            ] != list(GPU_CERTIFICATE_SEQUENCE):
                errors["empty"].append("resource_mapping:W2-19:ordered_gpu_semantics")
    if (
        len(resource_mapping_event_refs) == 2
        and len(set(resource_mapping_event_refs.values())) != 2
    ):
        errors["empty"].append("resource_mapping:distinct_source_events")
    responses = completion_coverage.get("failure_responses", [])
    if not isinstance(responses, list):
        errors["empty"].append("failure_responses")
        responses = []
    for response in responses:
        if not isinstance(response, Mapping):
            errors["empty"].append("failure_response")
            continue
        if (
            tuple(response.get("taxonomy_refs", ()))
            != COMPLETION_COVERAGE_TAXONOMY_REFS
        ):
            errors["empty"].append("failure_response:taxonomy_refs")
        try:
            _validate_failure_taxonomy_values(
                str(response.get("cause_classification", "")),
                str(response.get("intent_preservation", "")),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            errors["empty"].append("failure_response:taxonomy_values")
        if any(
            not response.get(field)
            for field in (
                "failing_contract",
                "observation_level",
                "cause_classification",
                "intent_preservation",
                "evidence",
                "same_intent_repair_or_escalation",
                "repair_or_escalation_owner",
                "repair_or_escalation_result",
                "result_artifact_refs",
                "source_event_ref",
            )
        ):
            errors["empty"].append("failure_response")
        if not _mapping_text_list(response.get("evidence")) or not _mapping_text_list(
            response.get("result_artifact_refs")
        ):
            errors["empty"].append("failure_response:typed_refs")
    response_refs = {
        str(response.get("source_event_ref"))
        for response in responses
        if isinstance(response, Mapping) and response.get("source_event_ref")
    }
    response_ref_list = [
        str(response.get("source_event_ref"))
        for response in responses
        if isinstance(response, Mapping) and response.get("source_event_ref")
    ]
    if len(response_ref_list) != len(set(response_ref_list)):
        errors["redundant"].append("failure_response:source_event_ref")
    failure_event_refs = completion_coverage.get("failure_event_refs", [])
    if not isinstance(failure_event_refs, list):
        errors["empty"].append("failure_event_refs")
        failure_event_refs = []
    if any(
        not isinstance(event_ref, str) or not event_ref.strip()
        for event_ref in failure_event_refs
    ):
        errors["empty"].append("failure_event_refs:item")
    if len(failure_event_refs) != len(set(failure_event_refs)):
        errors["redundant"].append("failure_event_refs")
    expected_failure_refs = {
        str(event.get("event_id"))
        for event in semantic_event_items
        if isinstance(event, Mapping) and event.get("semantic_kind") == "failure"
    }
    if set(failure_event_refs) != expected_failure_refs:
        errors["empty"].append("failure_event_refs:source_ownership")
    for event_ref in failure_event_refs:
        if not isinstance(event_ref, str) or event_ref not in response_refs:
            errors["empty"].append(f"failure_response:{event_ref}")
    for response_ref in response_refs:
        event = events_by_id.get(response_ref)
        if event is None or event.get("semantic_kind") != "failure":
            errors["empty"].append(f"failure_response:source_event:{response_ref}")
    errors = {key: sorted(set(value)) for key, value in errors.items()}
    failure_response_errors = tuple(
        item
        for item in errors["empty"]
        if item == "failure_response"
        or item.startswith("failure_response:")
        or item.startswith("failure_event_refs")
    )
    owner_boundary_error = any(
        item in {"owner_contract", "owner_boundary_evidence"}
        or item.startswith("owner_contract:")
        or item.startswith("owner_boundary_evidence:")
        or item.startswith("source_binding:")
        for item in errors["empty"]
    )
    gate_results = {
        "G1_CLAUSE_COVERAGE": not any(errors.values()),
        "G2_OWNER_BOUNDARY": not owner_boundary_error,
        "G3_STAGE_EVIDENCE": bool(gate_evidence_items)
        and not any(
            item == "gate_evidence"
            or item.startswith("gate_evidence:")
            or item == "oop_review_signal"
            or item.startswith("oop_readability_guard:")
            or item.startswith("solid_evidence_gate:")
            for item in errors["empty"]
        ),
        "G4_VALIDATION_RESPONSE": not failure_response_errors
        and all(
            all(
                response.get(field)
                for field in (
                    "failing_contract",
                    "observation_level",
                    "cause_classification",
                    "intent_preservation",
                    "evidence",
                    "taxonomy_refs",
                    "same_intent_repair_or_escalation",
                    "repair_or_escalation_owner",
                    "repair_or_escalation_result",
                    "result_artifact_refs",
                    "source_event_ref",
                )
            )
            for response in responses
            if isinstance(response, Mapping)
        ),
        "G5_DELIVERY_BOUNDARY": False,
    }
    gate_ids = {
        str(evidence.get("gate_id"))
        for evidence in gate_evidence_items
        if isinstance(evidence, Mapping)
    }
    if not OOP_REVIEW_SIGNAL_GATE_IDS.issubset(gate_ids):
        errors["empty"].append("oop_solid_evidence_contract")
        gate_results["G3_STAGE_EVIDENCE"] = False
    if not any("format" in gate_id or "static" in gate_id for gate_id in gate_ids):
        errors["empty"].append("formatter_static_events")
        gate_results["G3_STAGE_EVIDENCE"] = False
    errors = {key: sorted(set(value)) for key, value in errors.items()}
    gate_results["G1_CLAUSE_COVERAGE"] = not any(errors.values())
    gate_results["G2_OWNER_BOUNDARY"] = not any(
        item in {"owner_contract", "owner_boundary_evidence"}
        or item.startswith("owner_contract:")
        or item.startswith("owner_boundary_evidence:")
        or item.startswith("source_binding:")
        for item in errors["empty"]
    )
    gate_results["G4_VALIDATION_RESPONSE"] = not failure_response_errors and all(
        all(
            response.get(field)
            for field in (
                "failing_contract",
                "observation_level",
                "cause_classification",
                "intent_preservation",
                "evidence",
                "taxonomy_refs",
                "same_intent_repair_or_escalation",
                "repair_or_escalation_owner",
                "repair_or_escalation_result",
                "result_artifact_refs",
                "source_event_ref",
            )
        )
        for response in responses
        if isinstance(response, Mapping)
    )
    return {
        "schema": "agent-canon.completion-coverage-check.v1",
        "source_binding": dict(
            cast(Mapping[str, object], completion_coverage.get("source_binding", {}))
        ),
        "ok": not any(errors.values()) and all(gate_results.values()),
        "error_sets": errors,
        "gate_results": gate_results,
        "taxonomy_refs": list(COMPLETION_COVERAGE_TAXONOMY_REFS),
        "owner_contract": dict(owner_contract_for_check),
    }


def write_completion_coverage_artifact(
    report_dir: Path,
    ledger_snapshot: object,
    source_binding: Mapping[str, object],
    active_clause_ids: Sequence[str],
    owner_contract: Mapping[str, object],
    schedule_state_non_routing: Mapping[str, object],
    open_work_state_non_routing: Mapping[str, object],
    repair_state_non_routing: Mapping[str, object],
    crossing_edge_state_non_routing: Mapping[str, object],
    control_topology_ledger_snapshot: Mapping[str, object],
    taxonomy_refs: Sequence[str] = COMPLETION_COVERAGE_TAXONOMY_REFS,
    monitor_evidence: Sequence[Mapping[str, object]] = (),
) -> Path:
    """Materialize one deterministic checked projection from one ledger snapshot."""
    coverage = project_completion_coverage(
        ledger_snapshot,
        source_binding,
        monitor_evidence=monitor_evidence,
    )
    coverage_check = check_completion_coverage(
        coverage,
        active_clause_ids,
        owner_contract,
        taxonomy_refs,
    )
    completion_boundary = evaluate_completion_boundary(
        coverage_check,
        schedule_state_non_routing,
        open_work_state_non_routing,
        repair_state_non_routing,
        crossing_edge_state_non_routing,
        control_topology_ledger_snapshot,
    )
    gate_results = coverage_check.get("gate_results")
    if isinstance(gate_results, dict):
        gate_results["G5_DELIVERY_BOUNDARY"] = bool(
            completion_boundary.get("overall_delivery_complete")
        )
        error_sets = cast(Mapping[str, object], coverage_check.get("error_sets", {}))
        coverage_check["ok"] = not any(error_sets.values()) and all(
            bool(value) for value in gate_results.values()
        )
    artifact = {
        **coverage,
        "coverage_check": coverage_check,
        "completion_boundary": completion_boundary,
    }
    serialized = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    artifact_path = report_dir / "completion_coverage.json"
    if artifact_path.exists():
        existing = artifact_path.read_text(encoding="utf-8")
        if existing != serialized:
            raise ValueError(f"completion coverage artifact conflict: {artifact_path}")
        return artifact_path
    _write_validation_leaf(artifact_path, serialized.encode("utf-8"))
    return artifact_path


def record_validation_failure_response(
    failing_contract: str,
    observation_level: str,
    cause_classification: str,
    intent_preservation: str,
    evidence: Sequence[str],
    same_intent_repair_or_escalation: str,
    repair_or_escalation_owner: str = "",
    repair_or_escalation_result: str = "",
    result_artifact_refs: Sequence[str] = (),
) -> dict[str, object]:
    """Create the canonical pointer-only validation failure record."""
    _validate_failure_taxonomy_values(cause_classification, intent_preservation)
    response = ValidationFailureResponse(
        failing_contract=_nonempty_text(failing_contract),
        observation_level=_nonempty_text(observation_level),
        cause_classification=_nonempty_text(cause_classification),
        intent_preservation=_nonempty_text(intent_preservation),
        evidence=_text_tuple(evidence, "evidence"),
        taxonomy_refs=COMPLETION_COVERAGE_TAXONOMY_REFS,
        same_intent_repair_or_escalation=_nonempty_text(
            same_intent_repair_or_escalation
        ),
        repair_or_escalation_owner=_nonempty_text(repair_or_escalation_owner),
        repair_or_escalation_result=_nonempty_text(repair_or_escalation_result),
        result_artifact_refs=_text_tuple(result_artifact_refs, "result_artifact_refs"),
    )
    return {
        "schema": "agent-canon.validation-failure-response.v1",
        "failing_contract": response.failing_contract,
        "observation_level": response.observation_level,
        "cause_classification": response.cause_classification,
        "intent_preservation": response.intent_preservation,
        "evidence": list(response.evidence),
        "taxonomy_refs": list(response.taxonomy_refs),
        "same_intent_repair_or_escalation": response.same_intent_repair_or_escalation,
        "repair_or_escalation_owner": response.repair_or_escalation_owner,
        "repair_or_escalation_result": response.repair_or_escalation_result,
        "result_artifact_refs": list(response.result_artifact_refs),
    }


def evaluate_completion_boundary(
    coverage_check: Mapping[str, object],
    schedule_state_non_routing: Mapping[str, object],
    open_work_state_non_routing: Mapping[str, object],
    repair_state_non_routing: Mapping[str, object],
    crossing_edge_state_non_routing: Mapping[str, object],
    control_topology_ledger_snapshot: Mapping[str, object],
) -> dict[str, object]:
    """Derive planned-work and delivery predicates from one topology snapshot."""
    raw_repairs = (
        repair_state_non_routing.get("open_repairs")
        if isinstance(repair_state_non_routing, Mapping)
        else None
    )
    raw_edges = (
        crossing_edge_state_non_routing.get("open_crossing_edges")
        if isinstance(crossing_edge_state_non_routing, Mapping)
        else None
    )
    open_state_errors = _open_state_errors(
        raw_repairs, "open_repairs"
    ) + _open_state_errors(raw_edges, "open_crossing_edges")
    open_repairs = list(raw_repairs) if isinstance(raw_repairs, list) else []
    open_edges = list(raw_edges) if isinstance(raw_edges, list) else []
    topology_errors = _topology_errors(control_topology_ledger_snapshot)
    topology = (
        control_topology_ledger_snapshot
        if isinstance(control_topology_ledger_snapshot, Mapping)
        else {}
    )
    coverage_binding = (
        coverage_check.get("source_binding")
        if isinstance(coverage_check, Mapping)
        else None
    )
    if not isinstance(coverage_binding, Mapping):
        topology_errors.append("coverage_source_binding")
    elif isinstance(control_topology_ledger_snapshot, Mapping):
        for field in ("run_id", "context_id"):
            if control_topology_ledger_snapshot.get(field) != coverage_binding.get(
                field
            ):
                topology_errors.append(f"binding:{field}")
    topology_valid = not topology_errors
    typed_schedule = all(
        isinstance(schedule_state_non_routing.get(field), bool)
        if isinstance(schedule_state_non_routing, Mapping)
        else False
        for field in (
            "w2_implementation_complete",
            "w2_review_complete",
            "source_freeze_review_complete",
            "formatter_and_static_checks_pass",
        )
    )
    typed_open_work = (
        isinstance(open_work_state_non_routing.get("planned_work_complete"), bool)
        if isinstance(open_work_state_non_routing, Mapping)
        else False
    )
    typed_coverage = isinstance(coverage_check, Mapping)
    coverage_gate_results = (
        coverage_check.get("gate_results")
        if isinstance(coverage_check, Mapping)
        else None
    )
    coverage_ready_before_delivery = (
        typed_coverage
        and isinstance(coverage_gate_results, Mapping)
        and all(
            coverage_gate_results.get(gate) is True
            for gate in (
                "G1_CLAUSE_COVERAGE",
                "G2_OWNER_BOUNDARY",
                "G3_STAGE_EVIDENCE",
                "G4_VALIDATION_RESPONSE",
            )
        )
    )
    planned = bool(
        topology_valid
        and not open_state_errors
        and typed_schedule
        and typed_open_work
        and schedule_state_non_routing.get("w2_implementation_complete")
        and schedule_state_non_routing.get("w2_review_complete")
        and schedule_state_non_routing.get("source_freeze_review_complete")
        and open_work_state_non_routing.get("planned_work_complete")
        and not open_repairs
        and not open_edges
        and topology.get("writer_release_order_complete")
    )
    delivery = bool(
        topology_valid
        and not open_state_errors
        and typed_schedule
        and typed_open_work
        and coverage_ready_before_delivery
        and topology.get("global_publication_state") == "publication_ready"
        and topology.get("final_review_approved")
        and topology.get("closeout_unlocked")
        and topology.get("routing_gate") == "verified"
        and schedule_state_non_routing.get("formatter_and_static_checks_pass")
        and not open_repairs
        and not open_edges
    )
    return {
        "schema": "agent-canon.completion-boundary.v1",
        "all_planned_chunks_complete": planned,
        "overall_delivery_complete": delivery,
        "open_repairs": open_repairs,
        "open_crossing_edges": open_edges,
        "topology_errors": sorted(set(topology_errors + open_state_errors)),
        "gate_results": {
            "G5_DELIVERY_BOUNDARY": delivery,
        },
        "control_topology_observation_ref": _nonempty_text(
            topology.get("observation_ref")
        )
        if "observation_ref" not in topology_errors
        else "",
    }


def consume_checked_completion_coverage(
    completion_coverage_v1: Mapping[str, object],
    coverage_check: Mapping[str, object],
    completion_boundary: Mapping[str, object],
) -> dict[str, object]:
    """Consume the checked projection without rebuilding coverage or state."""
    if completion_coverage_v1.get("schema") != COMPLETION_COVERAGE_SCHEMA:
        raise ValueError("closeout requires agent-canon.completion-coverage.v1")
    if not isinstance(coverage_check, Mapping) or not isinstance(
        completion_boundary, Mapping
    ):
        return {"ready": False, "reason": "checked_projection_types_invalid"}
    if not coverage_check.get("ok"):
        return {"ready": False, "reason": "coverage_check_failed"}
    gate_results = coverage_check.get("gate_results")
    required_gate_results = {
        "G1_CLAUSE_COVERAGE",
        "G2_OWNER_BOUNDARY",
        "G3_STAGE_EVIDENCE",
        "G4_VALIDATION_RESPONSE",
        "G5_DELIVERY_BOUNDARY",
    }
    if (
        not isinstance(gate_results, Mapping)
        or set(gate_results) != required_gate_results
    ):
        return {"ready": False, "reason": "coverage_gate_results_incomplete"}
    if any(gate_results.get(gate) is not True for gate in required_gate_results):
        return {"ready": False, "reason": "coverage_gate_results_not_ready"}
    if completion_boundary.get("topology_errors") != []:
        return {"ready": False, "reason": "completion_boundary_topology_invalid"}
    if gate_results.get("G5_DELIVERY_BOUNDARY") is not completion_boundary.get(
        "overall_delivery_complete"
    ):
        return {"ready": False, "reason": "coverage_delivery_gate_mismatch"}
    return {
        "ready": bool(completion_boundary.get("overall_delivery_complete")),
        "all_planned_chunks_complete": bool(
            completion_boundary.get("all_planned_chunks_complete")
        ),
        "overall_delivery_complete": bool(
            completion_boundary.get("overall_delivery_complete")
        ),
        "coverage_check": dict(coverage_check),
        "completion_boundary": dict(completion_boundary),
    }


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
            re.sub(r"[^a-z0-9]+", "_", cell.lower()).strip("_")
            for cell in cells
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


def table_body_rows(text: str, heading: str) -> list[str]:
    """Return non-header table rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if any(
            cell
            in {"Clause ID", "Source Bucket", "Stage", "Unit ID", "Wave ID", "Time"}
            for cell in cells
        ):
            continue
        rows.append(stripped)
    return rows


def markdown_table_dict_rows(text: str, heading: str) -> list[dict[str, str]]:
    """Return markdown table rows as dictionaries under one level-2 heading."""
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            headers = None
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if headers is None:
            headers = cells
            continue
        padded = cells + [""] * max(0, len(headers) - len(cells))
        rows.append({header: padded[index] for index, header in enumerate(headers)})
    return rows


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

    Tracked durable reports are allowed. Tracked generated report roots and tracked
    agent run bundles outside the current run are blockers. Untracked generated
    report files are allowed only under the current run directory because runtime
    archive tooling collects one active run bundle at closeout. Ignored non-
    generated report paths are local cache and do not block closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths = {}
    for path in _git_report_paths(workspace, ()):
        normalized = _normalized_git_path(path)
        if normalized.startswith(
            "reports/agents/"
        ) or is_mechanically_regenerated_report_path(path):
            report_paths[path] = "tracked"
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


def actual_wave_event_fields(workflow_monitoring_text: str) -> list[dict[str, str]]:
    """Return structured Actual Wave Events rows from workflow_monitoring.md."""
    rows: list[dict[str, str]] = []
    in_section = False
    for line in workflow_monitoring_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == "## Actual Wave Events"
            continue
        if not in_section or not stripped.startswith("- wave_event="):
            continue
        rows.append(token_fields(stripped))
    return rows


def _split_csv_field(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip() and item.strip().lower() != "none"
    )


def _candidate_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> tuple[Path, ...]:
    """Return policy-allowed filesystem paths for one evidence token."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    raw_candidates: list[Path] = []
    if path.is_absolute():
        raw_candidates.append(path)
    else:
        if workspace is not None:
            raw_candidates.append(workspace / path)
        if report_dir is not None:
            raw_candidates.append(report_dir / path)
            raw_candidates.append(report_dir.parent / path)
            if len(path.parts) == 1:
                raw_candidates.append(report_dir.parent / path.name)
    if report_dir is None:
        return ()
    current_run_root = report_dir.resolve()
    report_root = report_dir.parent.resolve()
    candidates: list[Path] = []
    for candidate in raw_candidates:
        resolved = candidate.resolve()
        if evidence_field == "fresh_wave_evidence":
            if resolved.is_relative_to(current_run_root):
                candidates.append(candidate)
        elif (
            evidence_field == "fresh_run_bundle"
            and resolved.parent == report_root
            and resolved != current_run_root
        ):
            candidates.append(candidate)
    return tuple(dict.fromkeys(candidates))


def _raw_evidence_paths(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
) -> tuple[Path, ...]:
    """Return unfiltered path interpretations for diagnostics."""
    if is_empty_policy_value(value):
        return ()
    path = Path(value)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        if workspace is not None:
            candidates.append(workspace / path)
        if report_dir is not None:
            candidates.append(report_dir / path)
            candidates.append(report_dir.parent / path)
    if report_dir is not None:
        if len(path.parts) == 1:
            candidates.append(report_dir.parent / path.name)
    return tuple(dict.fromkeys(candidates))


def _evidence_path_exists(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    *,
    require_dir: bool = False,
    evidence_field: str,
) -> bool:
    """Return whether one evidence token points at an existing artifact."""
    candidates = _candidate_evidence_paths(value, report_dir, workspace, evidence_field)
    if not candidates:
        return False
    if require_dir:
        return any(candidate.is_dir() for candidate in candidates)
    return any(candidate.exists() for candidate in candidates)


def _evidence_path_outside_scope(
    value: str,
    report_dir: Path | None,
    workspace: Path | None,
    evidence_field: str,
) -> bool:
    """Return whether evidence exists but outside the allowed run-artifact scope."""
    raw_existing = any(
        candidate.exists()
        for candidate in _raw_evidence_paths(value, report_dir, workspace)
    )
    if not raw_existing:
        return False
    return not _candidate_evidence_paths(value, report_dir, workspace, evidence_field)


def _actual_waves_by_id(
    actual_rows: list[dict[str, str]],
) -> tuple[dict[str, dict[str, str]], list[str]]:
    actual_by_id: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    for row in actual_rows:
        wave_id = row.get("wave_id", "").strip()
        if not wave_id:
            blockers.append("workflow_monitoring.md:actual_wave_missing:wave_id")
            continue
        if wave_id in actual_by_id:
            blockers.append(f"workflow_monitoring.md:actual_wave_duplicate:{wave_id}")
            continue
        actual_by_id[wave_id] = row
    return actual_by_id, blockers


def _actual_wave_field_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    blockers = [
        f"workflow_monitoring.md:actual_wave_field_missing:{wave_id}:{field}"
        for field in REQUIRED_ACTUAL_WAVE_FIELDS
        if actual.get(field, "").strip() in {"", "missing"}
    ]
    if actual.get("event_kind") == "mid_task_user_input":
        blockers.extend(
            _mid_task_user_input_blockers(wave_id, actual, report_dir, workspace)
        )
    return blockers


def _mid_task_user_input_blockers(
    wave_id: str,
    actual: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    """Return blockers for mid-task user input wave checkpoints."""
    blockers = [
        f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:{field}"
        for field in MID_TASK_REQUIRED_WAVE_FIELDS
        if actual.get(field, "").strip().lower() in {"", "missing"}
    ]
    if is_empty_policy_value(actual.get("updated_packet", "")):
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:updated_packet"
        )
    classification = actual.get("input_classification", "").strip()
    if not classification:
        return blockers
    if classification not in MID_TASK_CLASSIFICATION_ACTIONS:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_classification:"
            f"{wave_id}:{classification}"
        )
        return blockers
    expected_spawn_authority = MID_TASK_SPAWN_AUTHORITY[classification]
    if actual.get("spawn_authority", "").strip() != expected_spawn_authority:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_spawn_authority:"
            f"{wave_id}:expected={expected_spawn_authority}"
        )
    expected_action = MID_TASK_CLASSIFICATION_ACTIONS[classification]
    if actual.get("redispatch_action", "").strip() != expected_action:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_redispatch_action:"
            f"{wave_id}:expected={expected_action}"
        )
    expected_scope = MID_TASK_CLASSIFICATION_SCOPE_STATUS[classification]
    if actual.get("scope_status", "").strip() != expected_scope:
        blockers.append(
            "workflow_monitoring.md:mid_task_user_input_invalid_scope_status:"
            f"{wave_id}:expected={expected_scope}"
        )
    target_agents = actual.get("target_agents", "").strip()
    if (
        classification in MID_TASK_TARGET_REQUIRED_CLASSIFICATIONS
        and is_empty_policy_value(target_agents)
    ):
        blockers.append(
            f"workflow_monitoring.md:mid_task_user_input_field_missing:{wave_id}:target_agents"
        )
    spawned_roles = actual.get("spawned_roles", "").strip()
    if classification in MID_TASK_SPAWNED_ROLES_REQUIRED_CLASSIFICATIONS:
        if is_empty_policy_value(spawned_roles):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:spawned_roles"
            )
    if classification in MID_TASK_EVIDENCE_FIELDS:
        skipped_roles = actual.get("skipped_roles", "")
        if has_reuse_marker(skipped_roles):
            markers = ",".join(MID_TASK_REUSE_MARKERS)
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_reused_agent_forbidden:"
                f"{wave_id}:{markers}"
            )
    evidence_field = MID_TASK_EVIDENCE_FIELDS.get(classification)
    if evidence_field:
        evidence_value = actual.get(evidence_field, "").strip()
        if is_empty_policy_value(evidence_value):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                f"{wave_id}:{evidence_field}"
            )
        elif _evidence_path_outside_scope(
            evidence_value,
            report_dir,
            workspace,
            evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_outside_scope:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
            )
        elif not _evidence_path_exists(
            evidence_value,
            report_dir,
            workspace,
            require_dir=evidence_field == "fresh_run_bundle",
            evidence_field=evidence_field,
        ):
            blockers.append(
                "workflow_monitoring.md:mid_task_user_input_evidence_missing:"
                f"{wave_id}:{evidence_field}:{evidence_value}"
            )
    return blockers


def _actual_wave_mismatch_blockers(
    wave_id: str,
    planned: dict[str, str],
    actual: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    for schedule_field, event_field in WAVE_COMPARISON_FIELDS:
        planned_value = planned.get(schedule_field, "").strip()
        if planned_value and planned_value != actual.get(event_field, "").strip():
            blockers.append(
                f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:{event_field}"
            )
    if _split_csv_field(planned.get("Spawned Roles", "")) != _split_csv_field(
        actual.get("spawned_roles", "")
    ):
        blockers.append(
            f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:spawned_roles"
        )
    if _split_csv_field(planned.get("Role Instances", "")) != _split_csv_field(
        actual.get("role_instances", "")
    ):
        blockers.append(
            f"workflow_monitoring.md:actual_wave_mismatch:{wave_id}:role_instances"
        )
    return blockers


class MissingActualWaveClassification(str, Enum):
    """Exact classifications for planned waves with no actual event."""

    OVERPLANNING = "overplanning"
    LOGGING_GAP = "logging_gap"
    UNRESOLVED = "unresolved"


def _missing_actual_wave_classification(planned: dict[str, str]) -> str:
    """Return one exact missing-wave enum value; invalid values are unresolved."""
    candidates: list[MissingActualWaveClassification] = []
    for field in ("Status", "Skipped Roles / Rationale"):
        raw_value = planned.get(field, "").strip().lower()
        try:
            candidates.append(MissingActualWaveClassification(raw_value))
        except ValueError:
            continue
    if not candidates or len(set(candidates)) != 1:
        return MissingActualWaveClassification.UNRESOLVED.value
    return candidates[0].value


def wave_reconciliation_blockers(
    schedule_text: str,
    workflow_monitoring_text: str,
    lifecycle_status: dict[str, str],
    report_dir: Path | None = None,
    workspace: Path | None = None,
) -> list[str]:
    """Return blockers when planned subagent waves do not match observed events."""
    planned_rows = markdown_table_dict_rows(schedule_text, "## Agent Wave Ledger")
    planned_by_id = {
        row.get("Wave ID", "").strip(): row
        for row in planned_rows
        if row.get("Wave ID", "").strip()
    }
    blockers: list[str] = []

    if lifecycle_status.get("agent_wave_ledger_status") == "not_applicable":
        actual_rows = actual_wave_event_fields(workflow_monitoring_text)
        if planned_by_id or actual_rows:
            blockers.append(
                "subagent_lifecycle:not_applicable_but_wave_evidence_present"
            )
        return blockers

    actual_by_id, actual_id_blockers = _actual_waves_by_id(
        actual_wave_event_fields(workflow_monitoring_text)
    )
    blockers.extend(actual_id_blockers)

    for wave_id, planned in planned_by_id.items():
        actual = actual_by_id.get(wave_id)
        if actual is None:
            classification = _missing_actual_wave_classification(planned)
            if classification in {"overplanning", "unresolved"}:
                continue
            if classification == "logging_gap":
                blockers.append(
                    f"workflow_monitoring.md:actual_wave_missing:{wave_id}:logging_gap"
                )
                continue
            blockers.append(f"workflow_monitoring.md:actual_wave_missing:{wave_id}")
            continue
        blockers.extend(
            _actual_wave_field_blockers(wave_id, actual, report_dir, workspace)
        )
        blockers.extend(_actual_wave_mismatch_blockers(wave_id, planned, actual))
    for wave_id in sorted(set(actual_by_id) - set(planned_by_id)):
        blockers.append(f"workflow_monitoring.md:actual_wave_without_plan:{wave_id}")
    return blockers


def check_schedule_artifact(text: str) -> list[str]:
    """Return blockers for schedule.md."""
    blockers: list[str] = []
    required_tables = (
        ("## Stage Plan", "stage_plan_empty"),
        ("## Clause Coverage", "clause_coverage_empty"),
        ("## Planned Work Units", "planned_work_units_empty"),
        ("## Agent Wave Ledger", "agent_wave_ledger_empty"),
    )
    for heading, slug in required_tables:
        if not table_body_rows(text, heading):
            blockers.append(f"schedule.md:{slug}")
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
