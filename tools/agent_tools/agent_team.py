# @dependency-start
# contract tool
# responsibility AgentTeam facade owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./team_config.py provides the approved config APIs.
# upstream implementation ./packets.py provides the approved packet APIs.
# upstream implementation ./tool_calls.py provides the approved ToolCall APIs.
# upstream implementation ./issue_worker_dispatch.py provides the IssueWorker publisher route.
# upstream implementation ./implementation_dispatch.py provides the approved dispatch APIs.
# upstream implementation ./manifest_rendering.py provides the approved rendering APIs.
# upstream implementation ./workspace_scope.py provides the approved scope APIs.
# downstream implementation ./bootstrap_agent_run.py consumes the facade allowlist.
# downstream implementation ./task_close.py consumes the facade allowlist.
# @dependency-end
"""Public facade for the AgentTeam owner modules."""

# Research-backed skill-call order remains part of the public facade contract:
# research_driven_change selects $literature-survey before $research-workflow.
# The owner implementation performs the selected.append operations.

from __future__ import annotations

if __package__:
    from .implementation_dispatch import _capacity_projection as __capacity_projection
    from .implementation_dispatch import _closeout_projection as __closeout_projection
else:
    from implementation_dispatch import _capacity_projection as __capacity_projection
    from implementation_dispatch import _closeout_projection as __closeout_projection

if __package__:
    from .manifest_rendering import build_manifest as _build_manifest
    from .manifest_rendering import has_template as _has_template
    from .manifest_rendering import render_template as _render_template
    from .manifest_rendering import (
        initial_wave_execution_gate_lines as _initial_wave_execution_gate_lines,
    )
else:
    from manifest_rendering import build_manifest as _build_manifest
    from manifest_rendering import has_template as _has_template
    from manifest_rendering import render_template as _render_template
    from manifest_rendering import (
        initial_wave_execution_gate_lines as _initial_wave_execution_gate_lines,
    )

if __package__:
    from .skill_tool_commands import (
        validate_command_plan_executables as _validate_command_plan_executables,
    )
    from .agent_canon_source_root import resolve_agent_canon_source_root as _resolve_source_root
else:
    from skill_tool_commands import (  # type: ignore[no-redef]
        validate_command_plan_executables as _validate_command_plan_executables,
    )
    from agent_canon_source_root import resolve_agent_canon_source_root as _resolve_source_root

if __package__:
    from .packets import (
        MATHEMATICAL_INTENT_PACKET_SCHEMA,
        MATHEMATICAL_INTENT_ROUTE_ID,
        MathematicalIntentPacket,
        iter_artifacts as _iter_artifacts,
        mathematical_intent_packet_mapping,
        mathematical_intent_route_config,
        mathematical_intent_route_for_task,
        math_intent_route_id_from_context,
        math_intent_route_id_for_spec,
        normalize_mathematical_intent_packet,
        resolve_math_intent_packet_for_spec,
        validate_mathematical_intent_route,
    )
else:
    from packets import (  # type: ignore[no-redef]
        MATHEMATICAL_INTENT_PACKET_SCHEMA,
        MATHEMATICAL_INTENT_ROUTE_ID,
        MathematicalIntentPacket,
        iter_artifacts as _iter_artifacts,
        mathematical_intent_packet_mapping,
        mathematical_intent_route_config,
        mathematical_intent_route_for_task,
        math_intent_route_id_from_context,
        math_intent_route_id_for_spec,
        normalize_mathematical_intent_packet,
        resolve_math_intent_packet_for_spec,
        validate_mathematical_intent_route,
    )

import json as _json
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path

from task_authority import AUTHORITY_FILE_NAME as _AUTHORITY_FILE_NAME
from task_authority import build_default_task_authority as _build_default_task_authority

if __package__:
    from .team_config import (
        AgentTypeSelection,
        Role,
        RunBundleSpec,
        TaskCatalog,
        TeamConfig,
        codex_agent_model_matrix_for_roles,
        current_stage_skills,
        default_review_pack_ids_for_task,
        default_specialists_for_task,
        deferred_stage_skills,
        enable_choices,
        expand_enabled_specialists,
        load_task_catalog,
        load_team_config,
        resolve_role,
        resolve_task_spec,
        resolve_workflow_family,
        select_roles,
        specialist_role_ids,
        task_ids,
    )
else:
    from team_config import (
        AgentTypeSelection,
        Role,
        RunBundleSpec,
        TaskCatalog,
        TeamConfig,
        codex_agent_model_matrix_for_roles,
        current_stage_skills,
        default_review_pack_ids_for_task,
        default_specialists_for_task,
        deferred_stage_skills,
        enable_choices,
        expand_enabled_specialists,
        load_task_catalog,
        load_team_config,
        resolve_role,
        resolve_task_spec,
        resolve_workflow_family,
        select_roles,
        specialist_role_ids,
        task_ids,
    )

if __package__:
    from .writer_target import validate_mathematical_writer_target
else:
    from writer_target import validate_mathematical_writer_target  # type: ignore[no-redef]

if __package__:
    from .workspace_scope import (
        ReportBundleArtifactPathError,
        load_directory_snapshot,
        make_run_id,
        resolve_report_bundle_artifact_path,
        resolve_report_root,
        resolve_role_write_scope,
        schedule_wave_row,
        validate_role_write_scope,
        write_directory_snapshot,
        write_workspace_change_snapshot,
    )
else:
    from workspace_scope import (
        ReportBundleArtifactPathError,
        load_directory_snapshot,
        make_run_id,
        resolve_report_bundle_artifact_path,
        resolve_report_root,
        resolve_role_write_scope,
        schedule_wave_row,
        validate_role_write_scope,
        write_directory_snapshot,
        write_workspace_change_snapshot,
    )

if __package__:
    from .packets import (
        ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS,
        ACTIVE_DESIGN_PACKET_FIELDS,
        ACTIVE_DESIGN_PACKET_SCHEMA,
        ActiveDesignPacketConfig,
        active_design_packet_mapping,
        active_design_packet_reference_projection,
        normalize_active_design_packet_config,
        parse_active_design_packet_input,
        resolve_active_design_packet_config,
        resolve_cross_cutting_document_packet,
        resolve_role_document_packet,
    )
else:
    from packets import (
        ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS,
        ACTIVE_DESIGN_PACKET_FIELDS,
        ACTIVE_DESIGN_PACKET_SCHEMA,
        ActiveDesignPacketConfig,
        active_design_packet_mapping,
        active_design_packet_reference_projection,
        normalize_active_design_packet_config,
        parse_active_design_packet_input,
        resolve_active_design_packet_config,
        resolve_cross_cutting_document_packet,
        resolve_role_document_packet,
    )

if __package__:
    from .implementation_dispatch import (
        agent_type_selection_map,
        capacity_runtime_for_spec,
        capacity_start_output_lines,
        codex_runtime_max_depth,
        codex_runtime_max_threads,
        declared_team_capacity_derivation,
        default_quality_check_agent_types,
        dispatch_fixed_implementation,
        dispatch_subagent_wave,
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        recommended_initial_subagent_wave_slots,
        unique_codex_agents_for_roles,
        validate_agent_type_selections,
        validate_writer_handoff_waves,
        workflow_spawn_budget,
        workflow_topology_policy_violations,
    )
else:
    from implementation_dispatch import (
        agent_type_selection_map,
        capacity_runtime_for_spec,
        capacity_start_output_lines,
        codex_runtime_max_depth,
        codex_runtime_max_threads,
        declared_team_capacity_derivation,
        default_quality_check_agent_types,
        dispatch_fixed_implementation,
        dispatch_subagent_wave,
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        recommended_initial_subagent_wave_slots,
        unique_codex_agents_for_roles,
        validate_agent_type_selections,
        validate_writer_handoff_waves,
        workflow_spawn_budget,
        workflow_topology_policy_violations,
    )

if __package__:
    from .manifest_rendering import (
        checkout_identity_policy_output_lines,
        contract_complete_implementation_policy_output_lines,
        coordination_capability_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        repo_tool_routing_policy_output_lines,
        required_output_templates_missing,
        selected_skill_command_packets,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
        writer_target_policy_output_lines,
    )
else:
    from manifest_rendering import (
        checkout_identity_policy_output_lines,
        contract_complete_implementation_policy_output_lines,
        coordination_capability_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        repo_tool_routing_policy_output_lines,
        required_output_templates_missing,
        selected_skill_command_packets,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
        writer_target_policy_output_lines,
    )

if __package__:
    from .tool_calls import (
        CloseAgentLifecycleEvidence,
        materialize_close_agent_tool_call,
        materialize_issue_worker_tool_call,
        materialize_subagent_spawn_tool_call,
        materialize_skill_tool_call_token,
    )
else:
    from tool_calls import (
        CloseAgentLifecycleEvidence,
        materialize_close_agent_tool_call,
        materialize_issue_worker_tool_call,
        materialize_subagent_spawn_tool_call,
        materialize_skill_tool_call_token,
    )


def dispatch_issue_worker(*args: object, **kwargs: object) -> object:
    """Expose the logical IssueWorker route through the AgentTeam facade."""
    if __package__:
        from .issue_worker_dispatch import dispatch_issue_worker as dispatch
    else:
        from issue_worker_dispatch import dispatch_issue_worker as dispatch  # type: ignore[no-redef]
    return dispatch(*args, **kwargs)  # type: ignore[arg-type]

del annotations


@_dataclass(frozen=True)
class PreparedRunBundle:
    """Read-only rendered run bytes ready for staged parent publication."""

    files: tuple[tuple[str, bytes], ...]
    created_files: tuple[str, ...]
    active_design_packet: ActiveDesignPacketConfig


def _append_section_line(text: str, heading: str, line: str) -> str:
    """Apply one manifest section line to a rendered buffer."""
    if line in text:
        return text
    lines = text.splitlines()
    in_section = False
    insert_at = len(lines)
    for index, existing in enumerate(lines):
        stripped = existing.strip()
        if not stripped.startswith("## "):
            continue
        if in_section:
            insert_at = index
            break
        in_section = stripped == heading
    if not in_section:
        lines.extend(("", heading, "", line))
    else:
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, line)
    return "\n".join(lines) + "\n"


def run_workflow_family(spec: RunBundleSpec) -> dict[str, object] | None:
    """Resolve the selected workflow family for one run specification."""
    if not spec.workflow_family_id:
        return None
    if spec.task_catalog is None:
        raise RuntimeError("task catalog is required for workflow manifest rendering")
    return resolve_workflow_family(spec.task_catalog, spec.workflow_family_id)


def run_active_design_packet(
    spec: RunBundleSpec,
    workflow_family: _Mapping[str, object] | None = None,
) -> ActiveDesignPacketConfig:
    """Resolve explicit run, workflow, or registry packet precedence."""
    if spec.active_design_packet is not None:
        return spec.active_design_packet
    selected_workflow = (
        workflow_family if workflow_family is not None else run_workflow_family(spec)
    )
    return resolve_active_design_packet_config(
        spec.config,
        workflow_family=selected_workflow,
    )


def _required_source_root(spec: RunBundleSpec) -> _Path:
    """Return the immutable source root carried by a run specification."""
    source_root = spec.agentcanon_source_root
    if source_root is None and spec.repository_roots is not None:
        source_root = spec.repository_roots.agentcanon_source_root
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    return source_root.resolve()


def _required_report_root(spec: RunBundleSpec) -> _Path:
    """Return the explicit report root carried by a run specification."""
    report_root = spec.report_root
    if report_root is None and spec.repository_roots is not None:
        report_root = spec.repository_roots.report_root
    if report_root is None:
        raise RuntimeError("runtime_roots_invalid:report_root_missing")
    return report_root.resolve()


def _validate_report_destination(spec: RunBundleSpec, report_root: _Path) -> None:
    """Require the public destination to be exactly ``report_root/run_id``."""
    expected = (report_root / spec.run_id).resolve()
    declared = spec.report_dir.resolve()
    if declared != expected:
        raise RuntimeError("runtime_roots_invalid:report_dir_mismatch")


def prepare_run_bundle(spec: RunBundleSpec) -> PreparedRunBundle:
    """Render and validate all initial run bytes without filesystem writes."""
    math_packet = resolve_math_intent_packet_for_spec(spec)
    if math_packet is not None:
        for target in spec.writer_targets.values():
            validate_mathematical_writer_target(target, math_packet)
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    source_root = _required_source_root(spec)
    report_root = _required_report_root(spec)
    _validate_report_destination(spec, report_root)
    capacity_runtime = capacity_runtime_for_spec(spec)
    active_design_packet = run_active_design_packet(spec)
    missing_templates = required_output_templates_missing(
        spec.config,
        spec.roles,
        allowed_missing=(
            spec.config.artifacts["team_manifest"],
            spec.config.artifacts["verification"],
        ),
        source_root=source_root,
    )
    if missing_templates:
        raise RuntimeError(
            "preflight_output_templates_missing:" + ",".join(missing_templates)
        )
    if spec.selected_skills:
        source_resolution = _resolve_source_root(source_root)
        for packet in selected_skill_command_packets(
            spec.selected_skills,
            source_root,
        ):
            _validate_command_plan_executables(source_resolution, packet)
    created_files = list(_iter_artifacts(spec.config, spec.roles, active_design_packet))
    selected_templates = {
        active_design_packet.design_artifact: spec.config.artifacts["design_brief"],
        active_design_packet.design_review_artifact: spec.config.artifacts[
            "design_review"
        ],
        active_design_packet.document_flow_review_artifact: spec.config.artifacts[
            "document_flow_review"
        ],
    }
    rendered: dict[str, str] = {}
    for artifact in created_files:
        template_name = selected_templates.get(artifact, artifact)
        if _has_template(template_name, source_root=source_root):
            rendered[artifact] = _render_template(
                template_name, replacements, source_root=source_root
            )
    rendered[spec.config.artifacts["team_manifest"]] = _build_manifest(
        spec, capacity_runtime
    )
    rendered["closeout_packet.json"] = _json.dumps(
        {
            "capacity_request": __capacity_projection(capacity_runtime, spec),
            "closeout_packet": __closeout_projection(capacity_runtime, spec),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    created_files.append("closeout_packet.json")
    rendered[spec.config.artifacts["verification"]] = "\n".join(
        (
            f"run_id={spec.run_id}",
            f"task={spec.task}",
            f"owner={spec.owner}",
            f"created_at_utc={spec.created_at_iso}",
            "status=pending",
            "user_completion_report=locked",
            "closeout_gate_status=pending",
            "",
        )
    )
    authority_roles = {
        role.id: role.write_policy.mode not in {"read_only", "artifacts_only"}
        for role in spec.roles
    }
    rendered[_AUTHORITY_FILE_NAME] = _build_default_task_authority(
        run_id=spec.run_id,
        task=spec.task,
        roles=authority_roles,
    )
    created_files.append(_AUTHORITY_FILE_NAME)
    for relative, heading, line in _initial_wave_execution_gate_lines(spec):
        rendered[relative] = _append_section_line(
            rendered.get(relative, ""), heading, line
        )
        if relative not in created_files:
            created_files.append(relative)
    unique_created_files = tuple(dict.fromkeys(created_files))
    return PreparedRunBundle(
        files=tuple(
            (path, rendered[path].encode("utf-8")) for path in rendered
        ),
        created_files=unique_created_files,
        active_design_packet=active_design_packet,
    )


def create_run_bundle(spec: RunBundleSpec) -> tuple[str, ...]:
    """Publish one prepared run through the shared atomic transaction."""
    prepared = prepare_run_bundle(spec)
    report_root = _required_report_root(spec)
    # Keep the compatibility facade on the exact publisher used by bootstrap.
    # The import is deliberately lazy because bootstrap imports this facade to
    # prepare its bundle before invoking the publisher with monitoring.
    if __package__:
        from .bootstrap_agent_run import publish_prepared_run
    else:
        from bootstrap_agent_run import publish_prepared_run  # type: ignore[no-redef]
    return publish_prepared_run(spec, prepared, report_root)


__all__ = (
    "Role",
    "RunBundleSpec",
    "TaskCatalog",
    "TeamConfig",
    "AgentTypeSelection",
    "ReportBundleArtifactPathError",
    "ACTIVE_DESIGN_PACKET_SCHEMA",
    "ACTIVE_DESIGN_PACKET_FIELDS",
    "ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS",
    "load_team_config",
    "load_task_catalog",
    "specialist_role_ids",
    "resolve_role",
    "resolve_task_spec",
    "resolve_workflow_family",
    "select_roles",
    "task_ids",
    "enable_choices",
    "expand_enabled_specialists",
    "default_specialists_for_task",
    "current_stage_skills",
    "deferred_stage_skills",
    "workflow_spawn_budget",
    "workflow_topology_policy_violations",
    "writer_target_policy_output_lines",
    "required_output_templates_missing",
    "codex_runtime_max_threads",
    "codex_runtime_max_depth",
    "codex_agent_model_matrix_for_roles",
    "ActiveDesignPacketConfig",
    "normalize_active_design_packet_config",
    "parse_active_design_packet_input",
    "active_design_packet_mapping",
    "active_design_packet_reference_projection",
    "resolve_active_design_packet_config",
    "resolve_cross_cutting_document_packet",
    "resolve_role_document_packet",
    "declared_team_capacity_derivation",
    "capacity_runtime_for_spec",
    "dispatch_fixed_implementation",
    "dispatch_subagent_wave",
    "recommended_initial_subagent_wave",
    "recommended_initial_subagent_wave_slots",
    "recommended_dynamic_expansion_waves",
    "recommended_dynamic_expansion_wave_slots",
    "recommended_initial_subagent_wave_slots",
    "unique_codex_agents_for_roles",
    "default_quality_check_agent_types",
    "parse_agent_type_selections",
    "format_agent_type_selections",
    "validate_agent_type_selections",
    "validate_writer_handoff_waves",
    "agent_type_selection_map",
    "capacity_start_output_lines",
    "materialize_skill_tool_call_token",
    "materialize_close_agent_tool_call",
    "materialize_issue_worker_tool_call",
    "materialize_subagent_spawn_tool_call",
    "dispatch_issue_worker",
    "CloseAgentLifecycleEvidence",
    "create_run_bundle",
    "prepare_run_bundle",
    "PreparedRunBundle",
    "MathematicalIntentPacket",
    "MATHEMATICAL_INTENT_PACKET_SCHEMA",
    "MATHEMATICAL_INTENT_ROUTE_ID",
    "normalize_mathematical_intent_packet",
    "mathematical_intent_packet_mapping",
    "mathematical_intent_route_for_task",
    "mathematical_intent_route_config",
    "math_intent_route_id_from_context",
    "math_intent_route_id_for_spec",
    "validate_mathematical_intent_route",
    "resolve_math_intent_packet_for_spec",
    "run_active_design_packet",
    "run_workflow_family",
    "format_subagent_wave",
    "format_subagent_wave_chunks",
    "format_subagent_role_instance_wave_chunks",
    "suggested_public_skills",
    "default_review_pack_ids_for_task",
    "default_quality_check_policy_output_lines",
    "checkout_identity_policy_output_lines",
    "contract_complete_implementation_policy_output_lines",
    "coordination_capability_policy_output_lines",
    "pre_handoff_gate_status_output_lines",
    "pre_handoff_scope_policy_output_lines",
    "repo_tool_routing_policy_output_lines",
    "same_role_subagent_policy_output_lines",
    "standard_agent_wave_sequence_output_lines",
    "user_facing_language_policy_output_lines",
    "language_review_candidates",
    "subagent_wave_record_command",
    "resolve_report_root",
    "resolve_report_bundle_artifact_path",
    "resolve_role_write_scope",
    "validate_role_write_scope",
    "load_directory_snapshot",
    "write_directory_snapshot",
    "write_workspace_change_snapshot",
    "schedule_wave_row",
    "make_run_id",
)
