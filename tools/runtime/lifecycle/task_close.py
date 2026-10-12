#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides task close agent workflow automation.
# upstream implementation ../../repository/workspace/workspace_scope.py resolves report root defaults and write scope
# upstream implementation ../../agent/orchestration/tool_calls.py materializes close-agent ToolCalls
# upstream implementation ../values.py refines decoded runtime artifact containers
# upstream implementation ../artifacts/report_artifact_checks.py validates actual run artifacts
# upstream implementation ./update_lifecycle_contract.py owns gate, cleanup, handback, and terminal ToolCall identities.
# upstream implementation ../../agent/orchestration/packets.py owns owner-local receipt normalization and compatibility.
# upstream design ../../../templates/agents/closeout_gate.md defines closeout status contract
# upstream design ../../../templates/agents/agent_evaluation.md defines evaluation contract
# upstream design ../../../documents/design/request-intent-and-update-relation.md cleanup/readback receipt closeout projection
# downstream implementation ../../../tests/agent_tools/test_bootstrap_and_close.py tests closeout
# @dependency-end
"""Own the sole terminal predicate for user-facing run completion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runtime.values import (
    is_object_list,
    is_string_object_dict,
    is_string_object_mapping,
)
from tools.runtime.artifacts.runtime_artifacts import (
    RUNTIME_ROOT_ENV,
    RuntimeArtifactError,
    runtime_artifact_boundary,
)
from tools.repository.workspace.parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    attest_parent_root,
)


def _parent_validate(path: Path, purpose: str) -> None:
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if not configured:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            f"{purpose}: explicit parent root is required",
        )
    parent = Path(configured).resolve(strict=True)
    attestation = attest_parent_root(
        ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose=purpose)
    )
    if path.resolve() == parent:
        # The attestation itself pins the authenticated parent root; asking
        # the path capability to resolve the root as a child would be an
        # invalid target lookup rather than an additional safety check.
        return
    ParentRootSideEffectBoundary().resolve_parent_owned_path(
        attestation, path, purpose, create=False
    )


from tools.agent.orchestration.tool_calls import (
    CloseAgentLifecycleEvidence,
    materialize_close_agent_tool_call,
)

from tools.repository.workspace.workspace_scope import resolve_report_root
from tools.runtime.artifacts.report_artifact_checks import (
    check_final_review_artifact,
    check_work_log_artifact,
    report_artifact_placement_blockers,
    token_fields,
)
from tools.runtime.lifecycle.update_lifecycle_contract import (
    GATE_IDS,
    binding_identity,
    validate_cleanup_proof,
    validate_durable_handback,
    validate_gate_chain,
)
from tools.agent.orchestration.packets import (
    normalize_owner_guarantee_packet,
    owner_receipt_is_compatible,
    owner_receipt_key,
)

STATIC_ANALYSIS_COMPLETE_STATUSES = {"yes", "profile_selected"}
COMMIT_PUSH_COMPLETE_STATUSES = {"yes", "not_applicable"}
DOCUMENT_STRUCTURE_MISSING_VALUES = {"", "missing", "none", "not_applicable"}
DOCUMENT_SPLIT_DECISION_PREFIXES = (
    "keep:",
    "split:",
    "merge:",
    "inline:",
    "rename:",
)
DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX = "not_applicable:format-only:"
DOCUMENT_STRUCTURE_ACTIVATIONS = {"required", "not_required", "format_only"}
DOCUMENT_STRUCTURE_VALUE_MISSING = {"", "missing", "none", "not_applicable"}
VERIFIER_RECEIPT_SCHEMA = "agent-canon.verifier-receipt.v1"
PARENT_MUTATION_EVIDENCE_SCHEMA = "agent-canon.parent-mutation-evidence.v1"


def _validated_runtime_receipt(
    report_dir: Path,
    reference: str,
    schema: str,
) -> dict[str, object] | None:
    """Read one authenticated runtime receipt under the current run bundle."""
    path = Path(reference)
    if path.is_absolute() or ".." in path.parts:
        return None
    target = (report_dir / path).resolve()
    if report_dir.resolve() not in target.parents or not target.is_file():
        return None
    try:
        value: object = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not is_string_object_dict(value) or value.get("schema") != schema:
        return None
    receipt = value
    receipt_sha = receipt.get("receipt_sha256")
    if not isinstance(receipt_sha, str):
        return None
    unsigned: dict[str, object] = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if (
        hashlib.sha256(
            json.dumps(
                unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        ).hexdigest()
        != receipt_sha
    ):
        return None
    return receipt


def _child_closeout_evidence(
    report_dir: Path,
    closeout: dict[str, str],
) -> tuple[bool, tuple[str, ...]]:
    """Require verifier provenance and hook-backed parent nonmutation evidence."""
    required = (
        "verifier_role_id",
        "verifier_runtime_agent_id",
        "verifier_receipt_ref",
        "parent_mutation_status",
        "parent_mutation_evidence_ref",
    )
    missing = tuple(field for field in required if not closeout.get(field, "").strip())
    if missing:
        return False, tuple(
            f"runtime_child_closeout_missing:{field}" for field in missing
        )
    verifier = _validated_runtime_receipt(
        report_dir,
        closeout["verifier_receipt_ref"],
        VERIFIER_RECEIPT_SCHEMA,
    )
    parent_evidence = _validated_runtime_receipt(
        report_dir,
        closeout["parent_mutation_evidence_ref"],
        PARENT_MUTATION_EVIDENCE_SCHEMA,
    )
    blockers: list[str] = []
    if verifier is None:
        blockers.append("runtime_verifier_receipt_invalid")
    else:
        source_events = verifier.get("source_event_ids")
        if (
            verifier.get("role_id") != "verifier"
            or verifier.get("runtime_agent_id") != closeout["verifier_runtime_agent_id"]
            or verifier.get("status") != "pass"
            or not is_object_list(source_events)
            or not source_events
        ):
            blockers.append("runtime_verifier_provenance_mismatch")
    if parent_evidence is None:
        blockers.append("parent_mutation_evidence_invalid")
    else:
        mutation_events = parent_evidence.get("mutation_event_ids")
        source_events = parent_evidence.get("source_event_ids")
        if is_object_list(source_events):
            source_event_values: list[object] = source_events
        else:
            source_event_values = []
        ledger_ref = parent_evidence.get("event_ledger_ref")
        ledger_ids: set[str] = set()
        ledger_mutations: list[Mapping[str, object]] = []
        if isinstance(ledger_ref, str):
            ledger_path = Path(ledger_ref)
            if not ledger_path.is_absolute() and ".." not in ledger_path.parts:
                ledger_target = (report_dir / ledger_path).resolve()
                if (
                    report_dir.resolve() in ledger_target.parents
                    and ledger_target.is_file()
                ):
                    try:
                        for line in ledger_target.read_text(
                            encoding="utf-8"
                        ).splitlines():
                            item: object = json.loads(line)
                            if is_string_object_dict(item):
                                event = item
                                hook_run_id = event.get("hook_run_id")
                                if isinstance(hook_run_id, str):
                                    ledger_ids.add(hook_run_id)
                                    control = event.get("mutation_control")
                                    if is_string_object_mapping(control):
                                        mutation_control = control
                                        ledger_mutations.append(mutation_control)
                    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                        pass
        if (
            closeout["parent_mutation_status"] != "no_parent_mutation"
            or parent_evidence.get("status") != "no_parent_mutation"
            or not is_object_list(mutation_events)
            or mutation_events
            or not is_object_list(source_events)
            or not source_events
            or not isinstance(ledger_ref, str)
            or any(not isinstance(event_id, str) for event_id in source_event_values)
            or not set(source_event_values).issubset(ledger_ids)
            or any(control.get("status") == "allowed" for control in ledger_mutations)
        ):
            blockers.append("parent_mutation_provenance_mismatch")
    return not blockers, tuple(blockers)


OWNER_GUARANTEE_RECEIPTS_ARTIFACT_NAME = "owner_guarantee_receipts.json"


def owner_receipt_closeout_consumer(
    report_dir: Path,
    *,
    candidate_digest: str | None = None,
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> dict[str, object]:
    """Consume owner receipts without rerunning owner commands or checks."""
    artifact_path = report_dir / OWNER_GUARANTEE_RECEIPTS_ARTIFACT_NAME
    if not artifact_path.is_file():
        return {"ready": True, "applicable": False, "reason": "not_applicable"}
    try:
        raw: object = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ready": False, "applicable": True, "reason": f"unreadable:{exc}"}
    if is_string_object_dict(raw):
        artifact = raw
        receipts = artifact.get("owner_receipts")
        artifact_candidate = artifact.get("candidate_digest")
        artifact_edges = artifact.get("dependency_edges", ())
        artifact_required = artifact.get("required_owner_refs", ())
    else:
        receipts = raw
        artifact_candidate = None
        artifact_edges = ()
        artifact_required = ()
    if candidate_digest is None and isinstance(artifact_candidate, str):
        candidate_digest = artifact_candidate
    if not required_owner_refs and is_object_list(artifact_required):
        required_owner_refs = tuple(str(value) for value in artifact_required)
    if not dependency_edges and is_object_list(artifact_edges):
        dependency_edges = tuple(str(value) for value in artifact_edges)
    if not is_object_list(receipts):
        return {"ready": False, "applicable": True, "reason": "receipts_not_list"}
    keys: set[tuple[str, str, str, str, str]] = set()
    owner_refs: set[str] = set()
    receipt_refs: list[str] = []
    declared_edges: set[str] = set()
    failures: list[str] = []
    for index, receipt in enumerate(receipts):
        try:
            packet = normalize_owner_guarantee_packet(
                receipt, f"owner_receipts[{index}]"
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            failures.append(str(exc))
            continue
        key = owner_receipt_key(packet)
        if key in keys:
            continue
        keys.add(key)
        if (
            packet["correspondence_state"] != "verified"
            or packet["observation_outcome"] != "observed_pass"
        ):
            continue
        if not owner_receipt_is_compatible(packet, candidate_digest=candidate_digest):
            failures.append(f"incompatible:{packet['primary_observation_ref']}")
            continue
        owner_refs.add(packet["owner_ref"])
        receipt_refs.append(packet["primary_observation_ref"])
        declared_edges.update(packet["downstream_edges"])
    failures.extend(
        f"missing_owner:{owner}"
        for owner in required_owner_refs
        if owner not in owner_refs
    )
    failures.extend(
        f"missing_dependency_edge:{edge}"
        for edge in dependency_edges
        if edge not in declared_edges
    )
    return {
        "ready": not failures,
        "applicable": True,
        "reason": "pass" if not failures else ";".join(failures),
        "owner_receipt_refs": receipt_refs,
        "dependency_edges": list(dependency_edges),
    }


def _runtime_validate(
    path: Path,
    purpose: str,
    *,
    runtime_root: Path | str | None = None,
) -> None:
    """Validate one report path against the explicit external runtime root."""
    configured = runtime_root or os.environ.get(RUNTIME_ROOT_ENV, "").strip() or None
    if configured is None:
        raise ParentRootSideEffectError(
            ParentRootReject.RUNTIME_ROOT_REQUIRED,
            f"{purpose}: explicit runtime root is required",
        )
    source_root = Path(__file__).resolve().parents[3]
    try:
        runtime_artifact_boundary(source_root, configured).resolve(path)
    except RuntimeArtifactError as exc:
        raise ParentRootSideEffectError(
            ParentRootReject.RUNTIME_PATH_ESCAPE,
            f"{purpose}: {exc}",
        ) from exc


UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME = "update_lifecycle_closeout.json"
UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA = "agent-canon.update-lifecycle-closeout.v1"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Check verification.txt and closeout_gate.md and fail unless the run is ready "
            "for a user-facing completion report."
        )
    )
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument("--report-dir", help="Explicit run directory to inspect.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional external directory that contains per-run report folders. "
            "Defaults below --runtime-root."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        help=(
            "Explicit external runtime root for reports and active-run state. "
            f"Defaults to {RUNTIME_ROOT_ENV}."
        ),
    )
    return parser


def parse_kv_lines(path: Path) -> dict[str, str]:
    """Parse a simple key=value file."""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def parse_markdown_status(path: Path) -> dict[str, str]:
    """Parse '- key: value' status lines from one markdown artifact."""
    data: dict[str, str] = {}
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def parse_markdown_status_section(path: Path, heading: str) -> dict[str, str]:
    """Parse '- key: value' status lines under one level-2 markdown heading."""
    data: dict[str, str] = {}
    pattern = re.compile(r"^- ([a-zA-Z0-9_]+): (.+)$")
    in_section = False
    target = f"## {heading}"
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == target:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = pattern.match(stripped)
        if match:
            key = match.group(1)
            if key in data:
                raise SystemExit(f"Duplicate status key in {heading}: {key}")
            data[key] = match.group(2).strip()
    return data


def markdown_section_text(path: Path, heading: str) -> str:
    """Return one level-2 Markdown section."""
    lines = path.read_text(encoding="utf-8").splitlines()
    target = f"## {heading}"
    in_section = False
    selected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == target:
            in_section = True
            selected.append(line)
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            selected.append(line)
    return "\n".join(selected)


def workflow_tool_warning_problems(workflow_monitoring_path: Path) -> tuple[str, ...]:
    """Return unresolved workflow-monitoring tool warning problems."""
    if not workflow_monitoring_path.is_file():
        return ("workflow_monitoring.md missing",)
    status = (
        parse_markdown_status(workflow_monitoring_path)
        .get("tool_warnings_status", "")
        .strip()
        .lower()
    )
    problems: list[str] = []
    if status not in {"none", "resolved"}:
        problems.append("tool_warnings_status must be none or resolved")
    latest_by_id: dict[str, dict[str, str]] = {}
    for line in markdown_section_text(
        workflow_monitoring_path, "Tool Warnings"
    ).splitlines():
        if "tool_warning=recorded" not in line:
            continue
        fields = token_fields(line)
        warning_id = fields.get("warning_id", "")
        if not warning_id:
            problems.append("tool_warning entry missing warning_id")
            continue
        latest_by_id[warning_id] = fields
    for warning_id, fields in sorted(latest_by_id.items()):
        warning_status = fields.get("status", "").lower()
        severity = fields.get("severity", "").lower()
        if warning_status in {"", "open", "pending", "observed", "unresolved"}:
            problems.append(f"tool warning remains open: {warning_id}")
        if (
            severity in {"fix-now", "s0", "s1", "blocker"}
            and warning_status != "resolved"
        ):
            problems.append(f"fix-now tool warning must be resolved: {warning_id}")
    return tuple(problems)


def join_blockers(blockers: list[str]) -> str:
    """Render blocker list for terminal output."""
    return ",".join(blockers) if blockers else ""


def resolve_run_artifact(report_dir: Path, value: str) -> Path | None:
    """Resolve one run-local artifact path, rejecting paths outside the run bundle."""
    if not value:
        return None
    raw_path = Path(value)
    candidate = (
        raw_path.resolve()
        if raw_path.is_absolute()
        else (report_dir / raw_path).resolve()
    )
    try:
        candidate.relative_to(report_dir)
    except ValueError:
        return None
    return candidate


def current_git_head(workspace: Path) -> str:
    """Return the current git commit for the workspace."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def current_diff_ref(workspace: Path) -> str:
    """Return a ref for the exact tracked diff state under review."""
    head = current_git_head(workspace)
    if not head:
        raise SystemExit(f"Unable to resolve git HEAD from workspace: {workspace}")
    unstaged = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    diff_bytes = unstaged.stdout + staged.stdout
    if untracked.returncode == 0 and untracked.stdout:
        for raw_path in sorted(path for path in untracked.stdout.split(b"\0") if path):
            if raw_path.startswith(b"reports/agents/"):
                continue
            path = workspace / raw_path.decode("utf-8", errors="surrogateescape")
            diff_bytes += b"\0UNTRACKED\0" + raw_path + b"\0"
            if path.is_file():
                diff_bytes += path.read_bytes()
    if not diff_bytes:
        return head
    diff_hash = hashlib.sha256(diff_bytes).hexdigest()
    return f"{head}-dirty-{diff_hash}"


def changed_markdown_paths(workspace: Path) -> tuple[str, ...]:
    """Return source-tree Markdown paths changed in the current checkout."""
    return tuple(path for path in changed_file_paths(workspace) if path.endswith(".md"))


def changed_file_paths(workspace: Path) -> tuple[str, ...]:
    """Return tracked and untracked non-report file paths changed in the checkout."""
    commands = (
        ("git", "diff", "--name-only"),
        ("git", "diff", "--cached", "--name-only"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            list(command),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            path = line.strip()
            if not path:
                continue
            if path.startswith("reports/") or path.startswith(
                ".agent-canon/log-archive/"
            ):
                continue
            paths.add(path)
    return tuple(sorted(paths))


def agent_canon_parent_sync_gate_required(
    changed_paths: Sequence[str],
    *,
    workspace: Path | None = None,
) -> bool:
    """Return whether a parent projection gate is required.

    AgentCanon is no longer embedded in a parent checkout, so there is no
    parent projection or gitlink whose synchronization can block closeout.
    Parent-owned product paths remain governed by their own validation route.
    """
    return False


def parse_document_structure_paths(value: str) -> set[str]:
    """Parse a closeout document-structure path list."""
    if value in {"", "missing", "none"}:
        return set()
    return {
        Path(item.strip()).as_posix()
        for item in re.split(r"[,\s]+", value)
        if item.strip() and item.strip() not in {"missing", "none"}
    }


def document_split_decision_ready(status: str, decision: str) -> bool:
    """Return whether document split evidence matches the structure route."""
    normalized_decision = decision.strip()
    if normalized_decision in DOCUMENT_STRUCTURE_MISSING_VALUES:
        return False
    if status == "skipped":
        return normalized_decision.startswith(
            DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX
        )
    if status == "complete":
        return normalized_decision.startswith(DOCUMENT_SPLIT_DECISION_PREFIXES)
    return False


def document_structure_evidence_ready(
    changed_markdown: Sequence[str], evidence: dict[str, str]
) -> tuple[bool, bool, bool]:
    """Return path-record, split-decision, and route readiness.

    This consumer validates supplied graph evidence but cannot infer whether the
    owning skill selected graph analysis or assess its analysis results.
    """
    if not changed_markdown:
        return True, True, True
    recorded_paths = parse_document_structure_paths(
        evidence.get("document_structure_paths", "")
    )
    normalized_changed = {Path(path).as_posix() for path in changed_markdown}
    paths_recorded = normalized_changed.issubset(recorded_paths)
    status = evidence.get("document_structure_status", "")
    activation = evidence.get("structure_activation", "")
    structure_contract = evidence.get("structure_contract", "")
    split_decision_ready = document_split_decision_ready(
        status, evidence.get("document_split_decision", "")
    )
    graph_activation = evidence.get("prose_graph_activation", "")
    graph_status = evidence.get("prose_graph", "")
    optional_graph_evidence_ready = (
        (graph_activation == "selected" and graph_status == "complete")
        or (graph_activation == "not_selected" and graph_status == "not_selected")
        or (
            graph_activation in {"", "not_applicable"}
            and graph_status in {"", "not_applicable"}
        )
    )
    identity_ready = all(
        evidence.get(field, "") not in DOCUMENT_STRUCTURE_VALUE_MISSING
        for field in (
            "structure_owner",
            "structure_source",
            "structure_reader",
            "structure_layout",
            "structure_validation_topology",
        )
    )
    required_route = (
        activation == "required"
        and evidence.get("structure_planning") == "complete"
        and optional_graph_evidence_ready
        and structure_contract.startswith("required:")
        and identity_ready
    )
    existing_topology_route = (
        activation == "not_required"
        and evidence.get("structure_planning") == "not_required"
        and optional_graph_evidence_ready
        and structure_contract.startswith("not_required:existing-topology:")
        and identity_ready
    )
    complete_route = (
        status == "complete"
        and activation in {"required", "not_required"}
        and (required_route or existing_topology_route)
    )
    skipped_route = (
        status == "skipped"
        and activation == "format_only"
        and evidence.get("md_style_check") == "pass"
        and evidence.get("document_split_decision", "").startswith(
            DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX
        )
        and structure_contract.startswith("skipped:")
        and evidence.get("format_only_reason", "")
        not in DOCUMENT_STRUCTURE_VALUE_MISSING
    )
    return (
        paths_recorded,
        split_decision_ready,
        split_decision_ready and (complete_route or skipped_route),
    )


def active_run_name(report_dir: Path) -> str | None:
    """Return the active run marker for a report root, or None when absent."""
    active_run_path = report_dir.parent / ".active_run"
    if not active_run_path.is_file():
        return None
    return active_run_path.read_text(encoding="utf-8").strip()


def active_run_matches(active_run: str | None, report_dir: Path) -> bool:
    """Return whether one active-run marker points to this report directory."""
    return active_run in {report_dir.name, str(report_dir.resolve())}


def update_lifecycle_closeout_consumer(report_dir: Path) -> dict[str, object]:
    """Consume six gate IDs and terminal cleanup evidence without rerunning gates."""
    artifact_path = report_dir / UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME
    if not artifact_path.is_file():
        return {"ready": True, "applicable": False, "reason": "not_applicable"}
    try:
        parsed: object = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": f"close_agent:artifact_unreadable:{exc}",
        }
    if not is_string_object_dict(parsed):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:schema_invalid",
        }
    closeout = parsed
    if closeout.get("schema") != UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:schema_invalid",
        }
    required = {
        "schema",
        "gate_verdicts",
        "durable_handback",
        "descendants",
        "reservations",
        "descendants_closed_evidence_ref",
        "reservations_released_evidence_ref",
        "cleanup_proof",
        "close_agent_tool_call",
    }
    if set(closeout) != required:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:artifact_fields_invalid",
        }
    try:
        raw_gate_values = closeout["gate_verdicts"]
        if not is_object_list(raw_gate_values) or len(raw_gate_values) != len(GATE_IDS):
            raise ValueError("close_agent:all_six_gate_evidence_required")
        gate_values = raw_gate_values
        source_gates = list(
            validate_gate_chain(
                gate_values[:5],
                expected_gate_ids=GATE_IDS[:5],
                require_pass=True,
            )
        )
        identity = binding_identity(source_gates[0]["binding"])
        if any(
            binding_identity(gate["binding"]) != identity for gate in source_gates[1:]
        ):
            raise ValueError("close_agent:identity_mismatch")
        handback = validate_durable_handback(closeout["durable_handback"])
        cleanup = validate_cleanup_proof(closeout["cleanup_proof"])
        if binding_identity(handback["binding"]) != identity:
            raise ValueError("close_agent:identity_mismatch")
        if binding_identity(cleanup["binding"]) != identity:
            raise ValueError("close_agent:identity_mismatch")
    except (TypeError, ValueError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": str(exc),
        }
    raw_descendant_values = closeout["descendants"]
    if not is_object_list(raw_descendant_values):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:descendant_evidence_invalid",
        }
    descendant_values = raw_descendant_values
    for raw_item in descendant_values:
        if not is_string_object_dict(raw_item):
            continue
        if raw_item.get("state") == "completed":
            return {
                "ready": False,
                "applicable": True,
                "reason": "close_agent:completed_but_open",
            }
    raw_reservation_values = closeout["reservations"]
    if not is_object_list(raw_reservation_values):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:reservation_evidence_invalid",
        }
    reservation_values = raw_reservation_values
    supplied_token = closeout["close_agent_tool_call"]
    try:
        if not is_string_object_dict(supplied_token):
            raise ValueError("close_agent:token_invalid")
        raw_supplied_args = supplied_token.get("args")
        if not is_string_object_dict(raw_supplied_args):
            raise ValueError("close_agent:token_invalid")
        supplied_args = raw_supplied_args
        run_id = supplied_args.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("close_agent:token_invalid")
        materialized = materialize_close_agent_tool_call(
            run_id=run_id,
            agent_id=str(handback["agent_id"]),
            evidence=CloseAgentLifecycleEvidence(
                gate_verdicts=source_gates,
                cleanup_proof=cleanup,
                durable_handback=handback,
                descendant_close_receipts=descendant_values,
                reservation_release_receipts=reservation_values,
            ),
        )
    except (TypeError, ValueError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": str(exc),
        }
    raw_canonical_g6 = materialized["g6_gate"]
    raw_token = materialized["close_agent_tool_call"]
    if not is_string_object_dict(raw_canonical_g6):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:g6_not_owner_materialized",
        }
    canonical_g6 = raw_canonical_g6
    if not is_string_object_dict(raw_token):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:token_evidence_mismatch",
        }
    token = raw_token
    descendants_ref = materialized["descendants_closed_evidence_ref"]
    reservations_ref = materialized["reservations_released_evidence_ref"]
    if gate_values[5] != canonical_g6:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:g6_not_owner_materialized",
        }
    if (
        closeout["descendants_closed_evidence_ref"] != descendants_ref
        or closeout["reservations_released_evidence_ref"] != reservations_ref
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:lifecycle_evidence_mismatch",
        }
    if supplied_token != token:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:token_evidence_mismatch",
        }
    gates = [*source_gates, canonical_g6]
    gate_refs: list[str] = []
    for gate in gates:
        binding = gate.get("binding")
        if not is_string_object_dict(binding):
            return {
                "ready": False,
                "applicable": True,
                "reason": "close_agent:lifecycle_evidence_mismatch",
            }
        evidence_ref = binding.get("evidence_ref")
        if not isinstance(evidence_ref, str):
            return {
                "ready": False,
                "applicable": True,
                "reason": "close_agent:lifecycle_evidence_mismatch",
            }
        gate_refs.append(evidence_ref)
    token_id = token.get("token_id")
    if not isinstance(token_id, str):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:token_evidence_mismatch",
        }
    return {
        "ready": True,
        "applicable": True,
        "reason": "pass",
        "gate_evidence_refs": gate_refs,
        "close_agent_token_id": token_id,
    }


def main() -> int:
    """Run the closeout check."""
    args = build_parser().parse_args()
    if bool(args.run_id) == bool(args.report_dir):
        raise SystemExit("Provide exactly one of --run-id or --report-dir.")

    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    else:
        report_dir = (
            resolve_report_root(args.report_root, runtime_root=args.runtime_root)
            / str(args.run_id)
        ).resolve()
    workspace = Path.cwd().resolve()
    # The checkout remains parent-owned, while run artifacts live under the
    # separately authenticated external runtime capability.
    _parent_validate(workspace, "task-close-workspace")
    _runtime_validate(
        report_dir,
        "task-close-report",
        runtime_root=args.runtime_root,
    )
    active_run = active_run_name(report_dir)

    verification_path = report_dir / "verification.txt"
    closeout_path = report_dir / "closeout_gate.md"
    request_contract_path = report_dir / "user_request_contract.md"
    schedule_path = report_dir / "schedule.md"
    work_log_path = report_dir / "work_log.md"
    workflow_monitoring_path = report_dir / "workflow_monitoring.md"
    final_review_path = report_dir / "final_review.md"
    agent_evaluation_path = report_dir / "agent_evaluation.md"
    if not verification_path.is_file():
        raise SystemExit(f"verification.txt not found: {verification_path}")
    if not closeout_path.is_file():
        raise SystemExit(f"closeout_gate.md not found: {closeout_path}")
    if not request_contract_path.is_file():
        raise SystemExit(f"user_request_contract.md not found: {request_contract_path}")
    if not schedule_path.is_file():
        raise SystemExit(f"schedule.md not found: {schedule_path}")
    if not work_log_path.is_file():
        raise SystemExit(f"work_log.md not found: {work_log_path}")
    if not agent_evaluation_path.is_file():
        raise SystemExit(f"agent_evaluation.md not found: {agent_evaluation_path}")

    verification = parse_kv_lines(verification_path)
    closeout = parse_markdown_status_section(closeout_path, "Gate Status")
    tool_warning_evidence = parse_markdown_status_section(
        closeout_path, "Tool Warning Evidence"
    )
    document_structure = parse_markdown_status_section(
        closeout_path, "Document Structure Evidence"
    )
    subagent_lifecycle = parse_markdown_status_section(
        closeout_path, "Subagent Lifecycle Evidence"
    )
    agent_canon_latest = parse_markdown_status_section(
        closeout_path, "AgentCanon Latest Evidence"
    )
    canonical_evidence = parse_markdown_status_section(
        closeout_path, "Canonical Formatter And Static Evidence"
    )
    runtime_log_archive = parse_markdown_status_section(
        closeout_path, "Runtime Log Archive Evidence"
    )
    child_closeout_ready, child_closeout_blockers = _child_closeout_evidence(
        report_dir,
        closeout,
    )
    diff_check = parse_markdown_status_section(
        closeout_path, "Diff-Check Agent Evidence"
    )
    diff_check_artifact_path = resolve_run_artifact(
        report_dir, diff_check.get("diff_check_artifact", "")
    )
    diff_check_artifact = (
        parse_markdown_status_section(diff_check_artifact_path, "Diff-Check Review")
        if diff_check_artifact_path and diff_check_artifact_path.is_file()
        else {}
    )
    diff_check_not_applicable = (
        closeout.get("diff_check_agent_complete", "").strip() == "not_applicable"
    )
    active_diff_ref = current_diff_ref(workspace)
    changed_all = changed_file_paths(workspace)
    changed_markdown = tuple(path for path in changed_all if path.endswith(".md"))
    diff_check_route_unselected = (
        closeout.get("required_reviews_complete", "").strip() == "not_applicable"
        or diff_check.get("diff_check_agent_role", "").strip() == "not_applicable"
    ) and all(
        diff_check.get(field, "").strip() in {"", "not_applicable"}
        for field in (
            "diff_check_agent_role",
            "diff_check_agent_decision",
            "diff_check_latest_diff_ref",
            "diff_check_artifact",
        )
    )
    diff_check_not_applicable_valid = not diff_check_not_applicable or (
        diff_check_route_unselected
        and not changed_all
        and active_diff_ref == current_git_head(workspace)
    )
    requires_canon_parent_sync = agent_canon_parent_sync_gate_required(
        changed_all,
        workspace=workspace,
    )
    parent_gitlink_commit = None
    requires_parent_gitlink_integrity = False
    (
        document_structure_paths_ready,
        document_split_decision_route_ready,
        document_structure_route_ready,
    ) = document_structure_evidence_ready(changed_markdown, document_structure)
    agent_evaluation = parse_markdown_status(agent_evaluation_path)
    workflow_tool_warning_blockers = workflow_tool_warning_problems(
        workflow_monitoring_path
    )
    request_contract = parse_markdown_status(request_contract_path)
    work_log_blockers = check_work_log_artifact(
        work_log_path.read_text(encoding="utf-8")
    )
    final_review_blockers = (
        check_final_review_artifact(final_review_path.read_text(encoding="utf-8"))
        if final_review_path.is_file()
        else []
    )
    report_artifact_blockers = report_artifact_placement_blockers(workspace, report_dir)
    owner_receipt_decision = owner_receipt_closeout_consumer(report_dir)
    update_lifecycle_decision = update_lifecycle_closeout_consumer(report_dir)

    closeout_checks = {
        "verification_status": verification.get("status") == "pass",
        "closeout_verifier_status": closeout.get("verifier_status") == "pass",
        "closeout_auditor_status": closeout.get("auditor_status") == "resolved",
        "verifier_child_provenance": child_closeout_ready,
        "parent_nonmutation_evidence": child_closeout_ready,
        "required_reviews_complete": closeout.get("required_reviews_complete")
        in {"yes", "not_applicable"},
        "validation_complete": closeout.get("validation_complete") == "yes",
        "request_contract_complete": closeout.get("request_contract_complete") == "yes",
        "owner_receipts_consumer": owner_receipt_decision.get("ready") is True,
        "update_lifecycle_closeout_consumer": update_lifecycle_decision.get("ready")
        is True,
        "overall_delivery_complete": closeout.get("overall_delivery_complete") == "yes",
        "dependency_headers_complete": closeout.get("dependency_headers_complete")
        == "yes",
        "repo_wide_dependency_tools_complete": closeout.get(
            "repo_wide_dependency_tools_complete"
        )
        == "yes",
        "repo_wide_static_analysis_complete": closeout.get(
            "repo_wide_static_analysis_complete"
        )
        in STATIC_ANALYSIS_COMPLETE_STATUSES,
        "agent_canon_latest_complete": closeout.get("agent_canon_latest_complete")
        == "yes"
        if requires_canon_parent_sync
        else closeout.get("agent_canon_latest_complete") in {"yes", "not_applicable"},
        "agent_canon_latest_command": (
            agent_canon_latest.get("agent_canon_latest_command", "")
            not in {"", "missing", "none"}
            if requires_canon_parent_sync
            else True
        ),
        "agent_canon_latest_status": (
            agent_canon_latest.get("agent_canon_latest_status", "") == "pass"
            if requires_canon_parent_sync
            else True
        ),
        "agent_canon_submodule_status": agent_canon_latest.get(
            "agent_canon_submodule_status", ""
        )
        not in {"", "missing", "none"}
        if requires_canon_parent_sync
        else True,
        "agent_canon_source_head": agent_canon_latest.get("agent_canon_source_head", "")
        not in {"", "missing", "none"}
        if requires_canon_parent_sync
        else True,
        "agent_canon_parent_pin": agent_canon_latest.get("agent_canon_parent_pin", "")
        not in {"", "missing", "none"}
        if requires_canon_parent_sync
        else True,
        "agent_canon_parent_gitlink_commit": (
            parent_gitlink_commit is not None
            if requires_parent_gitlink_integrity
            else True
        ),
        "mapping_error_sets_empty": (
            closeout.get(
                "mapping_error_sets_empty",
                canonical_evidence.get("mapping_error_sets_empty", ""),
            )
            == "yes"
        ),
        "typed_owner_boundary_status": (
            closeout.get(
                "typed_owner_boundary_status",
                canonical_evidence.get("typed_owner_boundary_status", ""),
            )
            == "pass"
        ),
        "canonical_format_check_status": canonical_evidence.get(
            "canonical_format_check_status",
            closeout.get("canonical_format_check_status", ""),
        )
        == "pass",
        "canonical_dispatcher_schema_status": (
            closeout.get(
                "canonical_dispatcher_schema_status",
                canonical_evidence.get("canonical_dispatcher_schema_status", ""),
            )
            == "pass"
        ),
        "review_findings_integrated": closeout.get("review_findings_integrated")
        == "yes",
        "focused_recheck_complete": closeout.get("focused_recheck_complete")
        in {"yes", "not_applicable"},
        "tool_warnings_resolved": closeout.get("tool_warnings_resolved") == "yes",
        "tool_warning_monitoring_status": tool_warning_evidence.get(
            "tool_warning_monitoring_status", ""
        )
        in {"none", "resolved"},
        "tool_warning_open_items": tool_warning_evidence.get("tool_warning_open_items")
        == "none",
        "tool_warning_resolution_evidence": tool_warning_evidence.get(
            "tool_warning_resolution_evidence", ""
        )
        not in {"", "missing", "none"},
        "workflow_tool_warnings_closed": not workflow_tool_warning_blockers,
        "document_structure_paths_recorded": document_structure_paths_ready,
        "document_split_decision_evidence": document_split_decision_route_ready,
        "document_structure_evidence": document_structure_route_ready,
        "subagents_closed": closeout.get("subagents_closed") == "yes",
        "subagent_closeout_status": subagent_lifecycle.get("subagent_closeout_status")
        in {"closed", "not_applicable"},
        "open_subagent_instances": subagent_lifecycle.get("open_subagent_instances")
        == "none",
        "close_agent_evidence": subagent_lifecycle.get("close_agent_evidence", "")
        not in {"", "none", "missing"},
        "diff_check_not_applicable_route": diff_check_not_applicable_valid,
        "diff_check_agent_complete": diff_check_not_applicable
        or closeout.get("diff_check_agent_complete") == "yes",
        "diff_check_agent_role": diff_check_not_applicable
        or diff_check.get("diff_check_agent_role", "")
        not in {"", "parent", "self", "codex"},
        "diff_check_agent_decision": diff_check_not_applicable
        or diff_check.get("diff_check_agent_decision") == "approve",
        "diff_check_latest_diff_ref": diff_check_not_applicable
        or diff_check.get("diff_check_latest_diff_ref") == active_diff_ref,
        "diff_check_artifact_path": diff_check_not_applicable
        or diff_check_artifact_path is not None,
        "diff_check_artifact_exists": diff_check_not_applicable
        or bool(diff_check_artifact_path and diff_check_artifact_path.is_file()),
        "diff_check_artifact_role": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_agent_role")
        == diff_check.get("diff_check_agent_role"),
        "diff_check_artifact_decision": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_agent_decision") == "approve",
        "diff_check_artifact_latest_diff_ref": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_latest_diff_ref")
        == diff_check.get("diff_check_latest_diff_ref"),
        "diff_check_artifact_read_only": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_read_only") == "yes",
        "diff_check_artifact_independent": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_independent_agent") == "yes",
        "diff_check_artifact_findings_status": diff_check_not_applicable
        or diff_check_artifact.get("diff_check_findings_status")
        in {"none", "resolved"},
        "canonical_tree_head_complete": closeout.get("canonical_tree_head_complete")
        == "yes",
        "agent_evaluation_complete": closeout.get("agent_evaluation_complete") == "yes",
        "runtime_log_archive_synced": closeout.get("runtime_log_archive_synced")
        == "yes",
        "runtime_log_archive_sync_command": runtime_log_archive.get(
            "runtime_log_archive_sync_command", ""
        )
        not in {"", "missing", "none"},
        "runtime_log_archive_sync_status": runtime_log_archive.get(
            "runtime_log_archive_sync_status", ""
        )
        == "pass",
        "runtime_log_archive_check_clean_status": runtime_log_archive.get(
            "runtime_log_archive_check_clean_status", ""
        )
        == "pass",
        "runtime_log_archive_dirty": runtime_log_archive.get(
            "runtime_log_archive_dirty", ""
        )
        == "no",
        "runtime_log_archive_foreign_dirty": runtime_log_archive.get(
            "runtime_log_archive_foreign_dirty", ""
        )
        == "no",
        "runtime_log_archive_branch_match": runtime_log_archive.get(
            "runtime_log_archive_branch_match", ""
        )
        == "yes",
        "runtime_log_archive_commit_or_noop": runtime_log_archive.get(
            "runtime_log_archive_commit", ""
        )
        not in {"", "missing", "none"},
        "runtime_log_archive_push_or_noop": runtime_log_archive.get(
            "runtime_log_archive_push", ""
        )
        not in {"", "missing", "none"},
        "agent_evaluation_status": agent_evaluation.get("evaluation_status") == "pass",
        "agent_feedback_resolved": agent_evaluation.get("feedback_actions_resolved")
        == "yes",
        "agent_learning_capture_complete": agent_evaluation.get(
            "learning_capture_complete"
        )
        == "yes",
        "request_contract_resolved": request_contract.get("all_clauses_resolved")
        == "yes",
        "no_forbidden_drift": request_contract.get("forbidden_drift_detected") == "no",
        "work_log_complete": not work_log_blockers,
        "final_review_artifact_complete": not final_review_blockers,
        "report_active_run_match": active_run_matches(active_run, report_dir),
        "report_artifact_placement_clean": not report_artifact_blockers,
        "commit_created": closeout.get("commit_created")
        in COMMIT_PUSH_COMPLETE_STATUSES,
        "push_completed": closeout.get("push_completed")
        in COMMIT_PUSH_COMPLETE_STATUSES,
        "closeout_unlock": closeout.get("user_completion_report") == "unlocked",
    }
    ready = all(closeout_checks.values())

    print(f"REPORT_DIR={report_dir}")
    print(f"VERIFICATION_STATUS={verification.get('status', '')}")
    print(f"CLOSEOUT_VERIFIER_STATUS={closeout.get('verifier_status', '')}")
    print(f"CLOSEOUT_AUDITOR_STATUS={closeout.get('auditor_status', '')}")
    print(f"VERIFIER_CHILD_PROVENANCE={'pass' if child_closeout_ready else 'fail'}")
    print(f"PARENT_NONMUTATION_EVIDENCE={'pass' if child_closeout_ready else 'fail'}")
    print(f"CHILD_CLOSEOUT_BLOCKERS={join_blockers(list(child_closeout_blockers))}")
    print(f"REQUIRED_REVIEWS_COMPLETE={closeout.get('required_reviews_complete', '')}")
    print(f"VALIDATION_COMPLETE={closeout.get('validation_complete', '')}")
    print(f"REQUEST_CONTRACT_COMPLETE={closeout.get('request_contract_complete', '')}")
    print(f"OVERALL_DELIVERY_COMPLETE={closeout.get('overall_delivery_complete', '')}")
    print(
        "OWNER_RECEIPTS_CONSUMER="
        f"{'yes' if owner_receipt_decision.get('ready') else 'no'}"
    )
    print(f"OWNER_RECEIPTS_CONSUMER_REASON={owner_receipt_decision.get('reason', '')}")
    print(
        "UPDATE_LIFECYCLE_CLOSEOUT_APPLICABLE="
        f"{update_lifecycle_decision.get('applicable', False)}"
    )
    print(
        "UPDATE_LIFECYCLE_CLOSEOUT_READY="
        f"{update_lifecycle_decision.get('ready', False)}"
    )
    print(
        "UPDATE_LIFECYCLE_CLOSEOUT_REASON="
        f"{update_lifecycle_decision.get('reason', '')}"
    )
    print(
        "MAPPING_ERROR_SETS_EMPTY="
        f"{closeout.get('mapping_error_sets_empty', canonical_evidence.get('mapping_error_sets_empty', ''))}"
    )
    print(
        "TYPED_OWNER_BOUNDARY_STATUS="
        f"{closeout.get('typed_owner_boundary_status', canonical_evidence.get('typed_owner_boundary_status', ''))}"
    )
    print(
        "CANONICAL_FORMAT_CHECK_STATUS="
        f"{canonical_evidence.get('canonical_format_check_status', '')}"
    )
    print(
        "CANONICAL_DISPATCHER_SCHEMA_STATUS="
        f"{closeout.get('canonical_dispatcher_schema_status', canonical_evidence.get('canonical_dispatcher_schema_status', ''))}"
    )
    print(
        f"DEPENDENCY_HEADERS_COMPLETE={closeout.get('dependency_headers_complete', '')}"
    )
    print(
        "REPO_WIDE_DEPENDENCY_TOOLS_COMPLETE="
        f"{closeout.get('repo_wide_dependency_tools_complete', '')}"
    )
    print(
        "REPO_WIDE_STATIC_ANALYSIS_COMPLETE="
        f"{closeout.get('repo_wide_static_analysis_complete', '')}"
    )
    print(
        f"AGENT_CANON_LATEST_COMPLETE={closeout.get('agent_canon_latest_complete', '')}"
    )
    print(
        "AGENT_CANON_LATEST_COMMAND="
        f"{agent_canon_latest.get('agent_canon_latest_command', '')}"
    )
    print(
        "AGENT_CANON_LATEST_STATUS="
        f"{agent_canon_latest.get('agent_canon_latest_status', '')}"
    )
    print(
        "AGENT_CANON_SUBMODULE_STATUS="
        f"{agent_canon_latest.get('agent_canon_submodule_status', '')}"
    )
    print(
        "AGENT_CANON_SOURCE_HEAD="
        f"{agent_canon_latest.get('agent_canon_source_head', '')}"
    )
    print(
        f"AGENT_CANON_PARENT_PIN={agent_canon_latest.get('agent_canon_parent_pin', '')}"
    )
    print(
        f"REVIEW_FINDINGS_INTEGRATED={closeout.get('review_findings_integrated', '')}"
    )
    print(f"FOCUSED_RECHECK_COMPLETE={closeout.get('focused_recheck_complete', '')}")
    print(f"TOOL_WARNINGS_RESOLVED={closeout.get('tool_warnings_resolved', '')}")
    print(
        "TOOL_WARNING_MONITORING_STATUS="
        f"{tool_warning_evidence.get('tool_warning_monitoring_status', '')}"
    )
    print(
        "TOOL_WARNING_OPEN_ITEMS="
        f"{tool_warning_evidence.get('tool_warning_open_items', '')}"
    )
    print(
        "TOOL_WARNING_RESOLUTION_EVIDENCE="
        f"{tool_warning_evidence.get('tool_warning_resolution_evidence', '')}"
    )
    print(
        "WORKFLOW_TOOL_WARNING_BLOCKERS="
        f"{join_blockers(list(workflow_tool_warning_blockers))}"
    )
    print(f"DOCUMENT_STRUCTURE_REQUIRED={'yes' if changed_markdown else 'no'}")
    print(
        "DOCUMENT_STRUCTURE_CHANGED_MARKDOWN="
        f"{','.join(changed_markdown) if changed_markdown else 'none'}"
    )
    print(
        "DOCUMENT_STRUCTURE_STATUS="
        f"{document_structure.get('document_structure_status', '')}"
    )
    print(
        "DOCUMENT_STRUCTURE_PATHS="
        f"{document_structure.get('document_structure_paths', '')}"
    )
    print(
        "DOCUMENT_SPLIT_DECISION="
        f"{document_structure.get('document_split_decision', '')}"
    )
    print(
        "DOCUMENT_SPLIT_DECISION_EVIDENCE="
        f"{'yes' if document_split_decision_route_ready else 'no'}"
    )
    print(
        "DOCUMENT_STRUCTURE_EVIDENCE="
        f"{'yes' if document_structure_route_ready else 'no'}"
    )
    print(
        "SUBAGENT_CLOSEOUT_STATUS="
        f"{subagent_lifecycle.get('subagent_closeout_status', '')}"
    )
    print(
        "SUBAGENT_OPEN_INSTANCES="
        f"{subagent_lifecycle.get('open_subagent_instances', '')}"
    )
    print(f"DIFF_CHECK_AGENT_COMPLETE={closeout.get('diff_check_agent_complete', '')}")
    print(f"DIFF_CHECK_AGENT_ROLE={diff_check.get('diff_check_agent_role', '')}")
    print(
        f"DIFF_CHECK_AGENT_DECISION={diff_check.get('diff_check_agent_decision', '')}"
    )
    print(
        f"DIFF_CHECK_LATEST_DIFF_REF={diff_check.get('diff_check_latest_diff_ref', '')}"
    )
    print(f"DIFF_CHECK_CURRENT_DIFF_REF={active_diff_ref}")
    print(f"DIFF_CHECK_ARTIFACT={diff_check.get('diff_check_artifact', '')}")
    print(
        "DIFF_CHECK_ARTIFACT_EXISTS="
        f"{'yes' if diff_check_artifact_path and diff_check_artifact_path.is_file() else 'no'}"
    )
    print(
        "CANONICAL_TREE_HEAD_COMPLETE="
        f"{closeout.get('canonical_tree_head_complete', '')}"
    )
    print(f"AGENT_EVALUATION_COMPLETE={closeout.get('agent_evaluation_complete', '')}")
    print(
        f"RUNTIME_LOG_ARCHIVE_SYNCED={closeout.get('runtime_log_archive_synced', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_SYNC_COMMAND="
        f"{runtime_log_archive.get('runtime_log_archive_sync_command', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_SYNC_STATUS="
        f"{runtime_log_archive.get('runtime_log_archive_sync_status', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_CHECK_CLEAN_STATUS="
        f"{runtime_log_archive.get('runtime_log_archive_check_clean_status', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_DIRTY="
        f"{runtime_log_archive.get('runtime_log_archive_dirty', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY="
        f"{runtime_log_archive.get('runtime_log_archive_foreign_dirty', '')}"
    )
    print(
        "RUNTIME_LOG_ARCHIVE_BRANCH_MATCH="
        f"{runtime_log_archive.get('runtime_log_archive_branch_match', '')}"
    )
    print(f"AGENT_EVALUATION_STATUS={agent_evaluation.get('evaluation_status', '')}")
    print(
        f"AGENT_FEEDBACK_RESOLVED={agent_evaluation.get('feedback_actions_resolved', '')}"
    )
    print(
        "AGENT_LEARNING_CAPTURE_COMPLETE="
        f"{agent_evaluation.get('learning_capture_complete', '')}"
    )
    print(
        f"REQUEST_CONTRACT_RESOLVED={request_contract.get('all_clauses_resolved', '')}"
    )
    print(
        f"FORBIDDEN_DRIFT_DETECTED={request_contract.get('forbidden_drift_detected', '')}"
    )
    print(f"UNRESOLVED_CLAUSE_IDS={request_contract.get('unresolved_clause_ids', '')}")
    print(f"WORK_LOG_COMPLETE={'yes' if not work_log_blockers else 'no'}")
    print(f"WORK_LOG_BLOCKERS={join_blockers(work_log_blockers)}")
    print(
        f"FINAL_REVIEW_ARTIFACT_COMPLETE={'yes' if not final_review_blockers else 'no'}"
    )
    print(f"FINAL_REVIEW_ARTIFACT_BLOCKERS={join_blockers(final_review_blockers)}")
    print(f"REPORT_ACTIVE_RUN={active_run or ''}")
    print(
        f"REPORT_ACTIVE_RUN_MATCH={'yes' if active_run_matches(active_run, report_dir) else 'no'}"
    )
    print(
        "REPORT_ARTIFACT_PLACEMENT_CLEAN="
        f"{'yes' if not report_artifact_blockers else 'no'}"
    )
    print(
        f"REPORT_ARTIFACT_PLACEMENT_BLOCKERS={join_blockers(report_artifact_blockers)}"
    )
    print(f"COMMIT_CREATED={closeout.get('commit_created', '')}")
    print(f"PUSH_COMPLETED={closeout.get('push_completed', '')}")
    print(f"USER_COMPLETION_REPORT={closeout.get('user_completion_report', '')}")
    print(f"CLOSEOUT_READY={'yes' if ready else 'no'}")

    if not ready:
        missing = ",".join(key for key, passed in closeout_checks.items() if not passed)
        print(f"CLOSEOUT_BLOCKERS={missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
