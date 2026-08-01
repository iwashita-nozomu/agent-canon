# @dependency-start
# contract tool
# responsibility AgentTeam facade owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./team_config.py provides the approved config APIs.
# upstream implementation ./packets.py provides the approved packet APIs.
# upstream implementation ./tool_calls.py provides the approved ToolCall APIs.
# upstream implementation ./implementation_dispatch.py provides the approved dispatch APIs.
# upstream implementation ./manifest_rendering.py provides the approved rendering APIs.
# upstream implementation ./workspace_scope.py provides the approved scope APIs.
# downstream implementation ./bootstrap_agent_run.py consumes the facade allowlist.
# downstream implementation ./task_start.py consumes the facade allowlist.
# downstream implementation ./task_close.py consumes the facade allowlist.
# @dependency-end
"""Public facade for the AgentTeam owner modules."""

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
        write_initial_wave_execution_gate as _write_initial_wave_execution_gate,
    )
else:
    from manifest_rendering import build_manifest as _build_manifest
    from manifest_rendering import has_template as _has_template
    from manifest_rendering import render_template as _render_template
    from manifest_rendering import (
        write_initial_wave_execution_gate as _write_initial_wave_execution_gate,
    )

if __package__:
    from .packets import iter_artifacts as _iter_artifacts
else:
    from packets import iter_artifacts as _iter_artifacts

import json as _json
from collections.abc import Mapping as _Mapping

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
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        unique_codex_agents_for_roles,
        validate_agent_type_selections,
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
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        unique_codex_agents_for_roles,
        validate_agent_type_selections,
        workflow_spawn_budget,
        workflow_topology_policy_violations,
    )

if __package__:
    from .manifest_rendering import (
        contract_complete_implementation_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        repo_tool_routing_policy_output_lines,
        required_output_templates_missing,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
    )
else:
    from manifest_rendering import (
        contract_complete_implementation_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        repo_tool_routing_policy_output_lines,
        required_output_templates_missing,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
    )

if __package__:
    from .tool_calls import (
        CloseAgentLifecycleEvidence,
        materialize_close_agent_tool_call,
        materialize_skill_tool_call_token,
    )
else:
    from tool_calls import (
        CloseAgentLifecycleEvidence,
        materialize_close_agent_tool_call,
        materialize_skill_tool_call_token,
    )

del annotations


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


def create_run_bundle(spec: RunBundleSpec) -> tuple[str, ...]:
    """Create the standard files for a run."""
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    capacity_runtime = capacity_runtime_for_spec(spec)
    spec.report_dir.mkdir(parents=True, exist_ok=True)
    active_design_packet = run_active_design_packet(spec)
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
    for artifact in created_files:
        template_name = selected_templates.get(artifact, artifact)
        if _has_template(template_name):
            output_path = resolve_report_bundle_artifact_path(spec.report_dir, artifact)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                _render_template(template_name, replacements),
                encoding="utf-8",
            )
    (spec.report_dir / spec.config.artifacts["team_manifest"]).write_text(
        _build_manifest(spec, capacity_runtime),
        encoding="utf-8",
    )
    (spec.report_dir / "closeout_packet.json").write_text(
        _json.dumps(
            {
                "capacity_request": __capacity_projection(capacity_runtime, spec),
                "closeout_packet": __closeout_projection(capacity_runtime, spec),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    created_files.append("closeout_packet.json")
    (spec.report_dir / spec.config.artifacts["verification"]).write_text(
        "\n".join(
            [
                f"run_id={spec.run_id}",
                f"task={spec.task}",
                f"owner={spec.owner}",
                f"created_at_utc={spec.created_at_iso}",
                "status=pending",
                "user_completion_report=locked",
                "closeout_gate_status=pending",
                "",
            ]
        ),
        encoding="utf-8",
    )
    authority_roles = {
        role.id: role.write_policy.mode not in {"read_only", "artifacts_only"}
        for role in spec.roles
    }
    (spec.report_dir / _AUTHORITY_FILE_NAME).write_text(
        _build_default_task_authority(
            run_id=spec.run_id,
            task=spec.task,
            roles=authority_roles,
        ),
        encoding="utf-8",
    )
    created_files.append(_AUTHORITY_FILE_NAME)
    _write_initial_wave_execution_gate(spec)
    unique_created_files: list[str] = []
    for artifact in created_files:
        if artifact not in unique_created_files:
            unique_created_files.append(artifact)
    return tuple(unique_created_files)


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
    "recommended_initial_subagent_wave",
    "recommended_dynamic_expansion_waves",
    "recommended_dynamic_expansion_wave_slots",
    "unique_codex_agents_for_roles",
    "default_quality_check_agent_types",
    "parse_agent_type_selections",
    "format_agent_type_selections",
    "validate_agent_type_selections",
    "agent_type_selection_map",
    "capacity_start_output_lines",
    "materialize_skill_tool_call_token",
    "materialize_close_agent_tool_call",
    "CloseAgentLifecycleEvidence",
    "create_run_bundle",
    "run_active_design_packet",
    "run_workflow_family",
    "format_subagent_wave",
    "format_subagent_wave_chunks",
    "format_subagent_role_instance_wave_chunks",
    "suggested_public_skills",
    "default_review_pack_ids_for_task",
    "default_quality_check_policy_output_lines",
    "contract_complete_implementation_policy_output_lines",
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
