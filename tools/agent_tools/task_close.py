#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides task close agent workflow automation.
# upstream implementation ./agent_team.py resolves report root defaults
# upstream implementation ./report_artifact_checks.py validates schedule and work log artifacts
# upstream implementation ./update_lifecycle_contract.py owns gate, cleanup, handback, and terminal ToolCall identities.
# upstream design ../../agents/templates/closeout_gate.md defines closeout status contract
# upstream design ../../agents/templates/agent_evaluation.md defines evaluation contract
# downstream implementation ../../tests/agent_tools/test_task_start_and_close.py tests closeout
# @dependency-end
"""Evaluate whether one run bundle is ready for a user-facing completion report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from agent_team import resolve_report_root
from artifact_identity import canonical_json_bytes
from report_artifact_checks import (
    COMPLETION_COVERAGE_SCHEMA,
    COMPLETION_COVERAGE_TAXONOMY_REFS,
    check_final_review_artifact,
    check_schedule_artifact,
    check_work_log_artifact,
    consume_checked_completion_coverage,
    generated_completion_coverage_errors,
    report_artifact_placement_blockers,
    token_fields,
    wave_reconciliation_blockers,
)
from update_lifecycle_contract import (
    GATE_IDS,
    binding_identity,
    validate_cleanup_proof,
    validate_close_agent_tool_call,
    validate_descendant_close_receipt,
    validate_durable_handback,
    validate_gate_chain,
    validate_reservation_release_receipt,
)

STATIC_ANALYSIS_COMPLETE_STATUSES = {"yes", "profile_selected"}
MECHANICAL_STATIC_ANALYSIS_READY_STATUSES = {"pass", "targeted", "not_applicable"}
DOCUMENT_STRUCTURE_MISSING_VALUES = {"", "missing", "none", "not_applicable"}
DOCUMENT_SPLIT_DECISION_PREFIXES = (
    "keep:",
    "split:",
    "merge:",
    "inline:",
    "rename:",
)
DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX = "not_applicable:format-only:"
COMPLETION_COVERAGE_ARTIFACT_NAME = "completion_coverage.json"
UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME = "update_lifecycle_closeout.json"
UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA = "agent-canon.update-lifecycle-closeout.v1"
EVIDENCE_REF_PATTERN = re.compile(r"^evidence:[0-9a-f]{64}$")


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
            "Optional directory that contains per-run report folders. Defaults to "
            "./reports/agents relative to the current workspace."
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
    status = parse_markdown_status(workflow_monitoring_path).get(
        "tool_warnings_status", ""
    ).strip().lower()
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
        if severity in {"fix-now", "s0", "s1", "blocker"} and warning_status != "resolved":
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
    candidate = raw_path.resolve() if raw_path.is_absolute() else (report_dir / raw_path).resolve()
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
            if not path.endswith(".md"):
                continue
            if path.startswith(("reports/", ".agent-canon/log-archive/")):
                continue
            paths.add(path)
    return tuple(sorted(paths))


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
        return normalized_decision.startswith(DOCUMENT_SPLIT_DECISION_FORMAT_ONLY_PREFIX)
    if status == "complete":
        return normalized_decision.startswith(DOCUMENT_SPLIT_DECISION_PREFIXES)
    return False


def document_structure_evidence_ready(
    changed_markdown: Sequence[str], evidence: dict[str, str]
) -> tuple[bool, bool, bool]:
    """Return path-record, split-decision, and route readiness."""
    if not changed_markdown:
        return True, True, True
    recorded_paths = parse_document_structure_paths(
        evidence.get("document_structure_paths", "")
    )
    normalized_changed = {Path(path).as_posix() for path in changed_markdown}
    paths_recorded = normalized_changed.issubset(recorded_paths)
    status = evidence.get("document_structure_status", "")
    structure_contract = evidence.get("structure_contract", "")
    split_decision_ready = document_split_decision_ready(
        status, evidence.get("document_split_decision", "")
    )
    complete_route = (
        status == "complete"
        and evidence.get("structure_planning") == "complete"
        and evidence.get("prose_graph") == "complete"
        and structure_contract
        not in {"", "missing", "none", "not_applicable"}
        and "skipped" not in structure_contract
    )
    skipped_route = (
        status == "skipped"
        and evidence.get("md_style_check") == "pass"
        and "skipped" in evidence.get("structure_contract", "")
        and evidence.get("format_only_reason", "") not in {"", "missing", "none"}
    )
    return paths_recorded, split_decision_ready, split_decision_ready and (
        complete_route or skipped_route
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


def completion_coverage_consumer(report_dir: Path) -> dict[str, object]:
    """Consume the generated v1 projection without rebuilding its ledger state."""
    artifact_path = report_dir / COMPLETION_COVERAGE_ARTIFACT_NAME
    if not artifact_path.is_file():
        return {"ready": False, "reason": f"missing:{artifact_path}"}
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ready": False, "reason": f"unreadable:{exc}"}
    if not isinstance(artifact, dict):
        return {"ready": False, "reason": "artifact_is_not_object"}
    generated_errors = generated_completion_coverage_errors(report_dir, artifact)
    if generated_errors:
        return {
            "ready": False,
            "reason": "hand_written_or_stale_artifact:" + ",".join(generated_errors),
        }
    if artifact.get("schema") != COMPLETION_COVERAGE_SCHEMA:
        return {"ready": False, "reason": "schema_mismatch"}
    source_binding = artifact.get("source_binding")
    required_binding_fields = {
        "run_id",
        "context_id",
        "organizer_context_id",
        "parent",
        "component_manager",
        "assigned_unit",
        "source_binding",
        "source_refs",
    }
    if not isinstance(source_binding, dict) or not required_binding_fields.issubset(
        source_binding
    ):
        return {"ready": False, "reason": "source_binding_incomplete"}
    if source_binding.get("run_id") != report_dir.name:
        return {"ready": False, "reason": "source_binding_run_id_mismatch"}
    if not isinstance(source_binding.get("context_id"), str) or not source_binding.get(
        "context_id"
    ).strip():
        return {"ready": False, "reason": "source_binding_context_id_missing"}
    nested_binding = source_binding.get("source_binding")
    if not isinstance(nested_binding, dict) or not nested_binding:
        return {"ready": False, "reason": "source_binding_reference_incomplete"}
    if nested_binding.get("run_id") != source_binding.get("run_id"):
        return {"ready": False, "reason": "nested_source_binding_run_id_mismatch"}
    if nested_binding.get("context_id") != source_binding.get("context_id"):
        return {"ready": False, "reason": "nested_source_binding_context_id_mismatch"}
    if not isinstance(source_binding.get("source_refs"), list) or not source_binding.get(
        "source_refs"
    ):
        return {"ready": False, "reason": "source_refs_incomplete"}
    if any(
        not isinstance(source_ref, str) or not source_ref.strip()
        for source_ref in source_binding["source_refs"]
    ):
        return {"ready": False, "reason": "source_refs_item_invalid"}
    if any(
        not isinstance(nested_binding.get(field), str)
        or not nested_binding.get(field).strip()
        for field in ("run_id", "context_id")
    ):
        return {"ready": False, "reason": "nested_source_binding_incomplete"}
    owner_evidence = artifact.get("owner_boundary_evidence")
    if not isinstance(owner_evidence, list) or not owner_evidence or any(
        not isinstance(item, dict)
        or any(
            not isinstance(item.get(field), str) or not item.get(field).strip()
            for field in (
                "owner",
                "state_owner",
                "api_owner",
                "dependency_owner",
            )
        )
        or not isinstance(item.get("evidence_refs"), list)
        or not item.get("evidence_refs")
        or any(
            not isinstance(ref, str) or not ref.strip()
            for ref in item.get("evidence_refs", [])
        )
        for item in owner_evidence
    ):
        return {"ready": False, "reason": "typed_owner_boundary_incomplete"}
    projection_metadata = artifact.get("projection_metadata")
    if not isinstance(projection_metadata, dict):
        return {"ready": False, "reason": "projection_metadata_missing"}
    if projection_metadata.get("generated_artifact_identity") != (
        f"{source_binding['run_id']}:{source_binding['context_id']}"
    ):
        return {"ready": False, "reason": "generated_artifact_identity_mismatch"}
    if not isinstance(projection_metadata.get("ledger_snapshot_identity"), str) or not projection_metadata.get(
        "ledger_snapshot_identity"
    ).strip():
        return {"ready": False, "reason": "ledger_snapshot_identity_missing"}
    if projection_metadata.get("source_refs") != source_binding.get("source_refs"):
        return {"ready": False, "reason": "projection_source_refs_mismatch"}
    coverage_check = artifact.get("coverage_check")
    completion_boundary = artifact.get("completion_boundary")
    if not isinstance(coverage_check, dict) or not isinstance(completion_boundary, dict):
        return {"ready": False, "reason": "checked_projection_fields_missing"}
    if coverage_check.get("schema") != "agent-canon.completion-coverage-check.v1":
        return {"ready": False, "reason": "coverage_check_schema_mismatch"}
    error_sets = coverage_check.get("error_sets")
    required_error_sets = {
        "uncovered",
        "multiply_mapped",
        "orphan",
        "redundant",
        "empty",
    }
    if not isinstance(error_sets, dict) or set(error_sets) != required_error_sets:
        return {"ready": False, "reason": "coverage_error_sets_incomplete"}
    if any(value != [] for value in error_sets.values()):
        return {"ready": False, "reason": "coverage_error_sets_nonempty"}
    gate_results = coverage_check.get("gate_results")
    required_gate_results = {
        "G1_CLAUSE_COVERAGE",
        "G2_OWNER_BOUNDARY",
        "G3_STAGE_EVIDENCE",
        "G4_VALIDATION_RESPONSE",
        "G5_DELIVERY_BOUNDARY",
    }
    if not isinstance(gate_results, dict) or set(gate_results) != required_gate_results:
        return {"ready": False, "reason": "coverage_gate_results_incomplete"}
    if any(gate_results.get(gate) is not True for gate in required_gate_results):
        return {"ready": False, "reason": "coverage_gate_results_not_ready"}
    if coverage_check.get("ok") is not True:
        return {"ready": False, "reason": "coverage_check_not_ok"}
    if coverage_check.get("source_binding") != source_binding:
        return {"ready": False, "reason": "coverage_source_binding_mismatch"}
    if tuple(coverage_check.get("taxonomy_refs", ())) != COMPLETION_COVERAGE_TAXONOMY_REFS:
        return {"ready": False, "reason": "coverage_taxonomy_refs_mismatch"}
    if completion_boundary.get("schema") != "agent-canon.completion-boundary.v1":
        return {"ready": False, "reason": "completion_boundary_schema_mismatch"}
    if not all(
        isinstance(completion_boundary.get(field), bool)
        for field in ("all_planned_chunks_complete", "overall_delivery_complete")
    ):
        return {"ready": False, "reason": "completion_boundary_flags_invalid"}
    if gate_results.get("G5_DELIVERY_BOUNDARY") is not completion_boundary.get(
        "overall_delivery_complete"
    ):
        return {"ready": False, "reason": "coverage_delivery_gate_mismatch"}
    if completion_boundary.get("topology_errors") != []:
        return {"ready": False, "reason": "completion_boundary_topology_invalid"}
    if not isinstance(completion_boundary.get("control_topology_observation_ref"), str) or not completion_boundary.get(
        "control_topology_observation_ref"
    ):
        return {"ready": False, "reason": "completion_boundary_topology_ref_missing"}
    for field in ("open_repairs", "open_crossing_edges"):
        values = completion_boundary.get(field)
        if not isinstance(values, list):
            return {"ready": False, "reason": f"{field}_schema_invalid"}
        for value in values:
            if isinstance(value, str) and value.strip():
                continue
            if isinstance(value, dict) and any(
                isinstance(value.get(key), str) and value.get(key).strip()
                for key in ("id", "ref", "identity")
            ):
                continue
            return {"ready": False, "reason": f"{field}_item_schema_invalid"}
        if values:
            return {"ready": False, "reason": f"{field}_nonempty"}
    semantic_events = artifact.get("semantic_events")
    if not isinstance(semantic_events, list) or not semantic_events:
        return {"ready": False, "reason": "semantic_events_missing"}
    events_by_id: dict[str, dict[str, object]] = {}
    for event in semantic_events:
        if not isinstance(event, dict):
            return {"ready": False, "reason": "semantic_event_invalid"}
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in events_by_id:
            return {"ready": False, "reason": "semantic_event_identity_invalid"}
        if event.get("run_id") != source_binding.get("run_id"):
            return {"ready": False, "reason": "semantic_event_run_id_mismatch"}
        if event.get("context_id") != source_binding.get("context_id"):
            return {"ready": False, "reason": "semantic_event_context_id_mismatch"}
        if event.get("source_binding") != nested_binding:
            return {"ready": False, "reason": "semantic_event_source_binding_mismatch"}
        events_by_id[event_id] = event
    coverage_map = artifact.get("coverage_map")
    if not isinstance(coverage_map, list):
        return {"ready": False, "reason": "coverage_map_missing"}
    source_event_refs: set[str] = set()
    for mapping in coverage_map:
        if not isinstance(mapping, dict):
            return {"ready": False, "reason": "coverage_mapping_invalid"}
        source_event_ref = mapping.get("source_event_ref")
        if not isinstance(source_event_ref, str) or source_event_ref in source_event_refs:
            return {"ready": False, "reason": "coverage_source_event_identity_invalid"}
        if source_event_ref not in events_by_id:
            return {"ready": False, "reason": "coverage_source_event_missing"}
        source_event_refs.add(source_event_ref)
    monitor_evidence = artifact.get("monitor_evidence")
    if not isinstance(monitor_evidence, list):
        return {"ready": False, "reason": "monitor_evidence_invalid"}
    for evidence in monitor_evidence:
        if not isinstance(evidence, dict):
            return {"ready": False, "reason": "monitor_evidence_item_invalid"}
        if evidence.get("run_id") != source_binding.get("run_id") or evidence.get(
            "context_id"
        ) != source_binding.get("context_id"):
            return {"ready": False, "reason": "monitor_evidence_binding_invalid"}
        source_event_ref = evidence.get("source_event_ref")
        if source_event_ref is not None and source_event_ref not in events_by_id:
            return {"ready": False, "reason": "monitor_evidence_source_event_missing"}
    gate_evidence = artifact.get("gate_evidence")
    if not isinstance(gate_evidence, list) or not gate_evidence:
        return {"ready": False, "reason": "gate_evidence_missing"}
    gate_ids: set[str] = set()
    for evidence in gate_evidence:
        if not isinstance(evidence, dict):
            return {"ready": False, "reason": "gate_evidence_invalid"}
        gate_id = evidence.get("gate_id")
        refs = evidence.get("source_event_refs")
        if not isinstance(gate_id, str) or not gate_id.strip() or gate_id in gate_ids:
            return {"ready": False, "reason": "gate_evidence_identity_invalid"}
        if not isinstance(refs, list) or not refs or any(
            not isinstance(ref, str) or ref not in events_by_id for ref in refs
        ):
            return {"ready": False, "reason": "gate_evidence_source_invalid"}
        gate_ids.add(gate_id)
    if not {"oop_readability_guard", "solid_evidence_gate"}.issubset(gate_ids):
        return {"ready": False, "reason": "oop_review_signal_missing"}
    resource_certificates = artifact.get("resource_certificates")
    if not isinstance(resource_certificates, list):
        return {"ready": False, "reason": "resource_certificates_invalid"}
    resource_certificate_refs: set[str] = set()
    for certificate in resource_certificates:
        if not isinstance(certificate, dict):
            return {"ready": False, "reason": "resource_certificate_invalid"}
        source_event_ref = certificate.get("source_event_ref")
        if not isinstance(source_event_ref, str) or source_event_ref in resource_certificate_refs:
            return {"ready": False, "reason": "resource_certificate_source_invalid"}
        if source_event_ref not in events_by_id:
            return {"ready": False, "reason": "resource_certificate_source_missing"}
        if certificate.get("run_id") != source_binding.get("run_id") or certificate.get(
            "context_id"
        ) != source_binding.get("context_id"):
            return {"ready": False, "reason": "resource_certificate_binding_mismatch"}
        resource_certificate_refs.add(source_event_ref)
    failure_event_refs = artifact.get("failure_event_refs")
    failure_responses = artifact.get("failure_responses")
    if not isinstance(failure_event_refs, list) or not isinstance(failure_responses, list):
        return {"ready": False, "reason": "failure_response_projection_invalid"}
    expected_failure_refs = {
        event_id
        for event_id, event in events_by_id.items()
        if event.get("semantic_kind") == "failure"
    }
    if set(failure_event_refs) != expected_failure_refs or any(
        not isinstance(ref, str) for ref in failure_event_refs
    ):
        return {"ready": False, "reason": "failure_event_source_binding_invalid"}
    response_refs: list[str] = []
    for response in failure_responses:
        if not isinstance(response, dict):
            return {"ready": False, "reason": "failure_response_invalid"}
        response_ref = response.get("source_event_ref")
        if not isinstance(response_ref, str) or response_ref in response_refs:
            return {"ready": False, "reason": "failure_response_identity_invalid"}
        if response_ref not in expected_failure_refs:
            return {"ready": False, "reason": "failure_response_source_invalid"}
        response_refs.append(response_ref)
    if set(response_refs) != expected_failure_refs:
        return {"ready": False, "reason": "failure_response_exact_once_invalid"}
    try:
        return consume_checked_completion_coverage(
            artifact,
            coverage_check,
            completion_boundary,
        )
    except ValueError as exc:
        return {"ready": False, "reason": str(exc)}


def update_lifecycle_closeout_consumer(report_dir: Path) -> dict[str, object]:
    """Consume six gate IDs and terminal cleanup evidence without rerunning gates."""
    artifact_path = report_dir / UPDATE_LIFECYCLE_CLOSEOUT_ARTIFACT_NAME
    if not artifact_path.is_file():
        return {"ready": True, "applicable": False, "reason": "not_applicable"}
    try:
        raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": f"close_agent:artifact_unreadable:{exc}",
        }
    if not isinstance(raw, dict) or raw.get("schema") != UPDATE_LIFECYCLE_CLOSEOUT_SCHEMA:
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
    if set(raw) != required:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:artifact_fields_invalid",
        }
    try:
        gate_values = raw["gate_verdicts"]
        if not isinstance(gate_values, list) or len(gate_values) != len(GATE_IDS):
            raise ValueError("close_agent:all_six_gate_evidence_required")
        gates = list(
            validate_gate_chain(
                gate_values,
                expected_gate_ids=GATE_IDS,
                require_pass=True,
            )
        )
        identity = binding_identity(gates[0]["binding"])
        if any(binding_identity(gate["binding"]) != identity for gate in gates[1:]):
            raise ValueError("close_agent:identity_mismatch")
        handback = validate_durable_handback(raw["durable_handback"])
        cleanup = validate_cleanup_proof(raw["cleanup_proof"])
        token = validate_close_agent_tool_call(raw["close_agent_tool_call"])
        if binding_identity(handback["binding"]) != identity:
            raise ValueError("close_agent:identity_mismatch")
        if binding_identity(cleanup["binding"]) != identity:
            raise ValueError("close_agent:identity_mismatch")
        if binding_identity(token["binding"]) != identity:
            raise ValueError("close_agent:identity_mismatch")
    except (TypeError, ValueError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": str(exc),
        }
    descendant_values = raw["descendants"]
    if not isinstance(descendant_values, list):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:descendant_evidence_invalid",
        }
    if any(
        isinstance(item, dict) and item.get("state") == "completed"
        for item in descendant_values
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:completed_but_open",
        }
    try:
        descendants = [
            validate_descendant_close_receipt(item) for item in descendant_values
        ]
    except (TypeError, ValueError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": str(exc),
        }
    declared_descendants = set(handback["descendant_ids"])
    observed_descendants = {str(item["agent_id"]) for item in descendants}
    if observed_descendants != declared_descendants:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:unknown_descendant",
        }
    if any(
        binding_identity(item["binding"]) != identity
        or item["durable_handback_evidence_ref"] != handback["evidence_ref"]
        for item in descendants
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:descendant_identity_mismatch",
        }
    reservation_values = raw["reservations"]
    if not isinstance(reservation_values, list):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:reservation_evidence_invalid",
        }
    try:
        reservations = [
            validate_reservation_release_receipt(item)
            for item in reservation_values
        ]
    except (TypeError, ValueError) as exc:
        return {
            "ready": False,
            "applicable": True,
            "reason": str(exc),
        }
    declared_reservations = set(handback["reservation_ids"])
    observed_reservations = {str(item["reservation_id"]) for item in reservations}
    if observed_reservations != declared_reservations or any(
        binding_identity(item["binding"]) != identity
        or item["durable_handback_evidence_ref"] != handback["evidence_ref"]
        for item in reservations
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:reservation_leak",
        }
    descendants_ref = raw["descendants_closed_evidence_ref"]
    reservations_ref = raw["reservations_released_evidence_ref"]
    if (
        EVIDENCE_REF_PATTERN.fullmatch(str(descendants_ref)) is None
        or EVIDENCE_REF_PATTERN.fullmatch(str(reservations_ref)) is None
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:lifecycle_evidence_invalid",
        }
    expected_descendants_ref = "evidence:" + hashlib.sha256(
        canonical_json_bytes(descendants)
    ).hexdigest()
    expected_reservations_ref = "evidence:" + hashlib.sha256(
        canonical_json_bytes(reservations)
    ).hexdigest()
    if (
        descendants_ref != expected_descendants_ref
        or reservations_ref != expected_reservations_ref
    ):
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:lifecycle_evidence_mismatch",
        }
    gate_refs = [gate["binding"]["evidence_ref"] for gate in gates]
    if cleanup["remote_readback_evidence_ref"] != gate_refs[4]:
        return {
            "ready": False,
            "applicable": True,
            "reason": "close_agent:cleanup_before_remote_readback",
        }
    args = token["args"]
    if (
        args["gate_verdict_evidence_refs"] != gate_refs
        or args["cleanup_proof_evidence_ref"] != cleanup["evidence_ref"]
        or args["durable_handback_evidence_ref"] != handback["evidence_ref"]
        or args["descendants_closed_evidence_ref"] != descendants_ref
        or args["reservations_released_evidence_ref"] != reservations_ref
        or token["agent_id"] != handback["agent_id"]
    ):
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
        "close_agent_token_id": token["token_id"],
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
            resolve_report_root(args.report_root, Path.cwd()) / str(args.run_id)
        ).resolve()
    workspace = Path.cwd().resolve()
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
    mechanical_loop = parse_markdown_status_section(
        closeout_path, "Mechanical Completion Loop Evidence"
    )
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
    completion_coverage_evidence = parse_markdown_status_section(
        closeout_path, "CompletionCoverage And Failure Response Evidence"
    )
    runtime_log_archive = parse_markdown_status_section(
        closeout_path, "Runtime Log Archive Evidence"
    )
    diff_check = parse_markdown_status_section(closeout_path, "Diff-Check Agent Evidence")
    diff_check_artifact_path = resolve_run_artifact(
        report_dir, diff_check.get("diff_check_artifact", "")
    )
    diff_check_artifact = (
        parse_markdown_status_section(diff_check_artifact_path, "Diff-Check Review")
        if diff_check_artifact_path and diff_check_artifact_path.is_file()
        else {}
    )
    active_diff_ref = current_diff_ref(workspace)
    changed_markdown = changed_markdown_paths(workspace)
    (
        document_structure_paths_ready,
        document_split_decision_route_ready,
        document_structure_route_ready,
    ) = (
        document_structure_evidence_ready(changed_markdown, document_structure)
    )
    agent_evaluation = parse_markdown_status(agent_evaluation_path)
    workflow_tool_warning_blockers = workflow_tool_warning_problems(
        workflow_monitoring_path
    )
    request_contract = parse_markdown_status(request_contract_path)
    schedule_text = schedule_path.read_text(encoding="utf-8")
    workflow_monitoring_text = (
        workflow_monitoring_path.read_text(encoding="utf-8")
        if workflow_monitoring_path.is_file()
        else ""
    )
    schedule_blockers = check_schedule_artifact(schedule_text)
    work_log_blockers = check_work_log_artifact(work_log_path.read_text(encoding="utf-8"))
    final_review_blockers = (
        check_final_review_artifact(final_review_path.read_text(encoding="utf-8"))
        if final_review_path.is_file()
        else ["final_review.md:missing"]
    )
    report_artifact_blockers = report_artifact_placement_blockers(workspace, report_dir)
    completion_decision = completion_coverage_consumer(report_dir)
    update_lifecycle_decision = update_lifecycle_closeout_consumer(report_dir)
    wave_reconciliation = wave_reconciliation_blockers(
        schedule_text,
        workflow_monitoring_text,
        subagent_lifecycle,
        report_dir,
        workspace,
    )

    checks = {
        "verification_status": verification.get("status") == "pass",
        "verification_unlock": verification.get("user_completion_report") == "unlocked",
        "closeout_verifier_status": closeout.get("verifier_status") == "pass",
        "closeout_auditor_status": closeout.get("auditor_status") == "resolved",
        "required_reviews_complete": closeout.get("required_reviews_complete") == "yes",
        "validation_complete": closeout.get("validation_complete") == "yes",
        "request_contract_complete": closeout.get("request_contract_complete") == "yes",
        "completion_coverage_consumer": completion_decision.get("ready") is True,
        "update_lifecycle_closeout_consumer": update_lifecycle_decision.get("ready")
        is True,
        "all_planned_chunks_complete": (
            completion_decision.get("all_planned_chunks_complete") is True
            and closeout.get("all_planned_chunks_complete") == "yes"
        ),
        "overall_delivery_complete": (
            completion_decision.get("overall_delivery_complete") is True
            and closeout.get("overall_delivery_complete") == "yes"
        ),
        "unfinished_tasks_absent": closeout.get("unfinished_tasks_absent") == "yes",
        "dependency_headers_complete": closeout.get("dependency_headers_complete") == "yes",
        "repo_wide_dependency_tools_complete": closeout.get("repo_wide_dependency_tools_complete")
        == "yes",
        "repo_wide_static_analysis_complete": closeout.get(
            "repo_wide_static_analysis_complete"
        )
        in STATIC_ANALYSIS_COMPLETE_STATUSES,
        "agent_canon_latest_complete": closeout.get("agent_canon_latest_complete") == "yes",
        "agent_canon_latest_command": agent_canon_latest.get(
            "agent_canon_latest_command", ""
        )
        not in {"", "missing", "none"},
        "agent_canon_latest_status": agent_canon_latest.get("agent_canon_latest_status", "")
        == "pass",
        "agent_canon_submodule_status": agent_canon_latest.get(
            "agent_canon_submodule_status", ""
        )
        not in {"", "missing", "none"},
        "agent_canon_source_head": agent_canon_latest.get("agent_canon_source_head", "")
        not in {"", "missing", "none"},
        "agent_canon_parent_pin": agent_canon_latest.get("agent_canon_parent_pin", "")
        not in {"", "missing", "none"},
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
            "canonical_format_check_status", closeout.get("canonical_format_check_status", "")
        )
        == "pass",
        "canonical_dispatcher_schema_status": (
            closeout.get(
                "canonical_dispatcher_schema_status",
                canonical_evidence.get("canonical_dispatcher_schema_status", ""),
            )
            == "pass"
        ),
        "validation_failure_response_status": completion_coverage_evidence.get(
            "validation_failure_response_status",
            closeout.get("validation_failure_response_status", ""),
        )
        == "pass",
        "review_findings_integrated": closeout.get("review_findings_integrated") == "yes",
        "post_fix_full_review_complete": closeout.get("post_fix_full_review_complete") == "yes",
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
        "mechanical_completion_loop_complete": closeout.get(
            "mechanical_completion_loop_complete"
        )
        == "yes",
        "subagents_closed": closeout.get("subagents_closed") == "yes",
        "mechanical_loop_iterations": mechanical_loop.get("mechanical_loop_iterations", "")
        not in {"", "0", "none"},
        "mechanical_loop_open_items": mechanical_loop.get("mechanical_loop_open_items")
        == "none",
        "mechanical_loop_stop_reason": mechanical_loop.get("mechanical_loop_stop_reason", "")
        != "",
        "mechanical_loop_planned_work_status": mechanical_loop.get(
            "mechanical_loop_planned_work_status"
        )
        == "complete",
        "mechanical_loop_review_findings_status": mechanical_loop.get(
            "mechanical_loop_review_findings_status"
        )
        in {"none", "resolved"},
        "mechanical_loop_validation_status": mechanical_loop.get(
            "mechanical_loop_validation_status"
        )
        == "pass",
        "mechanical_loop_dependency_review_status": mechanical_loop.get(
            "mechanical_loop_dependency_review_status"
        )
        == "pass",
        "mechanical_loop_static_analysis_status": mechanical_loop.get(
            "mechanical_loop_static_analysis_status"
        )
        in MECHANICAL_STATIC_ANALYSIS_READY_STATUSES,
        "mechanical_loop_commit_push_status": mechanical_loop.get(
            "mechanical_loop_commit_push_status"
        )
        == "complete",
        "mechanical_loop_canon_sync_status": mechanical_loop.get(
            "mechanical_loop_canon_sync_status"
        )
        in {"complete", "not_applicable"},
        "mechanical_loop_follow_up_status": mechanical_loop.get(
            "mechanical_loop_follow_up_status"
        )
        in {"none", "resolved"},
        "fresh_subagents_required": subagent_lifecycle.get("fresh_subagents_required")
        == "yes",
        "reuse_for_new_task": subagent_lifecycle.get("reuse_for_new_task")
        == "forbidden",
        "previous_task_subagent_reuse": subagent_lifecycle.get(
            "previous_task_subagent_reuse"
        )
        == "none",
        "agent_wave_ledger_status": subagent_lifecycle.get("agent_wave_ledger_status")
        in {"complete", "not_applicable"},
        "planned_vs_actual_wave_status": subagent_lifecycle.get(
            "planned_vs_actual_wave_status"
        )
        in {"reconciled", "not_applicable"},
        "subagent_wave_reconciliation_clean": not wave_reconciliation,
        "dynamic_spawn_policy_status": subagent_lifecycle.get("dynamic_spawn_policy_status")
        in {"applied", "not_applicable"},
        "subagent_closeout_status": subagent_lifecycle.get("subagent_closeout_status")
        == "closed",
        "open_subagent_instances": subagent_lifecycle.get("open_subagent_instances")
        == "none",
        "close_agent_evidence": subagent_lifecycle.get("close_agent_evidence", "")
        not in {"", "none", "missing"},
        "diff_check_agent_complete": closeout.get("diff_check_agent_complete") == "yes",
        "diff_check_agent_role": diff_check.get("diff_check_agent_role", "")
        not in {"", "parent", "self", "codex"},
        "diff_check_agent_decision": diff_check.get("diff_check_agent_decision") == "approve",
        "diff_check_latest_diff_ref": diff_check.get("diff_check_latest_diff_ref")
        == active_diff_ref,
        "diff_check_artifact_path": diff_check_artifact_path is not None,
        "diff_check_artifact_exists": bool(
            diff_check_artifact_path and diff_check_artifact_path.is_file()
        ),
        "diff_check_artifact_role": diff_check_artifact.get("diff_check_agent_role")
        == diff_check.get("diff_check_agent_role"),
        "diff_check_artifact_decision": diff_check_artifact.get("diff_check_agent_decision")
        == "approve",
        "diff_check_artifact_latest_diff_ref": diff_check_artifact.get(
            "diff_check_latest_diff_ref"
        )
        == diff_check.get("diff_check_latest_diff_ref"),
        "diff_check_artifact_read_only": diff_check_artifact.get("diff_check_read_only")
        == "yes",
        "diff_check_artifact_independent": diff_check_artifact.get(
            "diff_check_independent_agent"
        )
        == "yes",
        "diff_check_artifact_findings_status": diff_check_artifact.get(
            "diff_check_findings_status"
        )
        in {"none", "resolved"},
        "canonical_tree_head_complete": closeout.get("canonical_tree_head_complete") == "yes",
        "agent_evaluation_complete": closeout.get("agent_evaluation_complete") == "yes",
        "runtime_log_archive_synced": closeout.get("runtime_log_archive_synced") == "yes",
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
        "agent_feedback_resolved": agent_evaluation.get("feedback_actions_resolved") == "yes",
        "agent_learning_capture_complete": agent_evaluation.get("learning_capture_complete")
        == "yes",
        "request_contract_resolved": request_contract.get("all_clauses_resolved") == "yes",
        "no_forbidden_drift": request_contract.get("forbidden_drift_detected") == "no",
        "todo_artifact_complete": not schedule_blockers,
        "work_log_complete": not work_log_blockers,
        "final_review_artifact_complete": not final_review_blockers,
        "report_active_run_match": active_run_matches(active_run, report_dir),
        "report_artifact_placement_clean": not report_artifact_blockers,
        "commit_created": closeout.get("commit_created") == "yes",
        "push_completed": closeout.get("push_completed") == "yes",
        "closeout_unlock": closeout.get("user_completion_report") == "unlocked",
    }
    ready = all(checks.values())

    print(f"REPORT_DIR={report_dir}")
    print(f"VERIFICATION_STATUS={verification.get('status', '')}")
    print(f"VERIFICATION_UNLOCK={verification.get('user_completion_report', '')}")
    print(f"CLOSEOUT_VERIFIER_STATUS={closeout.get('verifier_status', '')}")
    print(f"CLOSEOUT_AUDITOR_STATUS={closeout.get('auditor_status', '')}")
    print(f"REQUIRED_REVIEWS_COMPLETE={closeout.get('required_reviews_complete', '')}")
    print(f"VALIDATION_COMPLETE={closeout.get('validation_complete', '')}")
    print(f"REQUEST_CONTRACT_COMPLETE={closeout.get('request_contract_complete', '')}")
    print(f"ALL_PLANNED_CHUNKS_COMPLETE={closeout.get('all_planned_chunks_complete', '')}")
    print(f"OVERALL_DELIVERY_COMPLETE={closeout.get('overall_delivery_complete', '')}")
    print(f"COMPLETION_COVERAGE_ARTIFACT={report_dir / COMPLETION_COVERAGE_ARTIFACT_NAME}")
    print(f"COMPLETION_COVERAGE_CONSUMER_READY={completion_decision.get('ready', False)}")
    print(f"COMPLETION_COVERAGE_CONSUMER_REASON={completion_decision.get('reason', '')}")
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
        "VALIDATION_FAILURE_RESPONSE_STATUS="
        f"{completion_coverage_evidence.get('validation_failure_response_status', '')}"
    )
    print(f"UNFINISHED_TASKS_ABSENT={closeout.get('unfinished_tasks_absent', '')}")
    print(f"DEPENDENCY_HEADERS_COMPLETE={closeout.get('dependency_headers_complete', '')}")
    print(
        "REPO_WIDE_DEPENDENCY_TOOLS_COMPLETE="
        f"{closeout.get('repo_wide_dependency_tools_complete', '')}"
    )
    print(
        "REPO_WIDE_STATIC_ANALYSIS_COMPLETE="
        f"{closeout.get('repo_wide_static_analysis_complete', '')}"
    )
    print(
        "MAKE_CI_STATUS="
        f"{mechanical_loop.get('mechanical_loop_static_analysis_status', '')}"
    )
    print(
        "AGENT_CANON_LATEST_COMPLETE="
        f"{closeout.get('agent_canon_latest_complete', '')}"
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
        "AGENT_CANON_PARENT_PIN="
        f"{agent_canon_latest.get('agent_canon_parent_pin', '')}"
    )
    print(f"REVIEW_FINDINGS_INTEGRATED={closeout.get('review_findings_integrated', '')}")
    print(
        "POST_FIX_FULL_REVIEW_COMPLETE="
        f"{closeout.get('post_fix_full_review_complete', '')}"
    )
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
    print(
        "DOCUMENT_STRUCTURE_REQUIRED="
        f"{'yes' if changed_markdown else 'no'}"
    )
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
        "MECHANICAL_COMPLETION_LOOP_COMPLETE="
        f"{closeout.get('mechanical_completion_loop_complete', '')}"
    )
    print(f"SUBAGENTS_CLOSED={closeout.get('subagents_closed', '')}")
    print(f"MECHANICAL_LOOP_ITERATIONS={mechanical_loop.get('mechanical_loop_iterations', '')}")
    print(f"MECHANICAL_LOOP_OPEN_ITEMS={mechanical_loop.get('mechanical_loop_open_items', '')}")
    print(
        "MECHANICAL_LOOP_VALIDATION_STATUS="
        f"{mechanical_loop.get('mechanical_loop_validation_status', '')}"
    )
    print(
        "MECHANICAL_LOOP_DEPENDENCY_REVIEW_STATUS="
        f"{mechanical_loop.get('mechanical_loop_dependency_review_status', '')}"
    )
    print(
        "MECHANICAL_LOOP_STATIC_ANALYSIS_STATUS="
        f"{mechanical_loop.get('mechanical_loop_static_analysis_status', '')}"
    )
    print(
        "SUBAGENT_FRESH_REQUIRED="
        f"{subagent_lifecycle.get('fresh_subagents_required', '')}"
    )
    print(
        "SUBAGENT_REUSE_FOR_NEW_TASK="
        f"{subagent_lifecycle.get('reuse_for_new_task', '')}"
    )
    print(
        "SUBAGENT_PREVIOUS_TASK_REUSE="
        f"{subagent_lifecycle.get('previous_task_subagent_reuse', '')}"
    )
    print(
        "SUBAGENT_CLOSEOUT_STATUS="
        f"{subagent_lifecycle.get('subagent_closeout_status', '')}"
    )
    print(
        "SUBAGENT_WAVE_RECONCILIATION_BLOCKERS="
        f"{join_blockers(wave_reconciliation)}"
    )
    print(
        "SUBAGENT_OPEN_INSTANCES="
        f"{subagent_lifecycle.get('open_subagent_instances', '')}"
    )
    print(f"DIFF_CHECK_AGENT_COMPLETE={closeout.get('diff_check_agent_complete', '')}")
    print(f"DIFF_CHECK_AGENT_ROLE={diff_check.get('diff_check_agent_role', '')}")
    print(f"DIFF_CHECK_AGENT_DECISION={diff_check.get('diff_check_agent_decision', '')}")
    print(f"DIFF_CHECK_LATEST_DIFF_REF={diff_check.get('diff_check_latest_diff_ref', '')}")
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
    print(f"RUNTIME_LOG_ARCHIVE_SYNCED={closeout.get('runtime_log_archive_synced', '')}")
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
    print(f"AGENT_FEEDBACK_RESOLVED={agent_evaluation.get('feedback_actions_resolved', '')}")
    print(
        "AGENT_LEARNING_CAPTURE_COMPLETE="
        f"{agent_evaluation.get('learning_capture_complete', '')}"
    )
    print(f"REQUEST_CONTRACT_RESOLVED={request_contract.get('all_clauses_resolved', '')}")
    print(f"FORBIDDEN_DRIFT_DETECTED={request_contract.get('forbidden_drift_detected', '')}")
    print(f"UNRESOLVED_CLAUSE_IDS={request_contract.get('unresolved_clause_ids', '')}")
    print(f"TODO_ARTIFACT_COMPLETE={'yes' if not schedule_blockers else 'no'}")
    print(f"TODO_ARTIFACT_BLOCKERS={join_blockers(schedule_blockers)}")
    print(f"WORK_LOG_COMPLETE={'yes' if not work_log_blockers else 'no'}")
    print(f"WORK_LOG_BLOCKERS={join_blockers(work_log_blockers)}")
    print(f"FINAL_REVIEW_ARTIFACT_COMPLETE={'yes' if not final_review_blockers else 'no'}")
    print(f"FINAL_REVIEW_ARTIFACT_BLOCKERS={join_blockers(final_review_blockers)}")
    print(f"REPORT_ACTIVE_RUN={active_run or ''}")
    print(f"REPORT_ACTIVE_RUN_MATCH={'yes' if active_run_matches(active_run, report_dir) else 'no'}")
    print(
        "REPORT_ARTIFACT_PLACEMENT_CLEAN="
        f"{'yes' if not report_artifact_blockers else 'no'}"
    )
    print(f"REPORT_ARTIFACT_PLACEMENT_BLOCKERS={join_blockers(report_artifact_blockers)}")
    print(f"COMMIT_CREATED={closeout.get('commit_created', '')}")
    print(f"PUSH_COMPLETED={closeout.get('push_completed', '')}")
    print(f"USER_COMPLETION_REPORT={closeout.get('user_completion_report', '')}")
    print(f"CLOSEOUT_READY={'yes' if ready else 'no'}")

    if not ready:
        missing = ",".join(key for key, passed in checks.items() if not passed)
        print(f"CLOSEOUT_BLOCKERS={missing}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
