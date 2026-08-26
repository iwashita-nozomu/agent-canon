#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Bootstraps agent run artifacts for agent workflows.
# upstream design ../README.md shared automation index
# @dependency-end

"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

try:
    from .runtime_artifacts import runtime_artifact_boundary
except ImportError:  # direct script/module execution
    from runtime_artifacts import (  # type: ignore[no-redef]
        runtime_artifact_boundary,
    )

if __package__:
    from .agent_canon_source_root import resolve_agent_canon_source_root
else:
    from agent_canon_source_root import resolve_agent_canon_source_root

from agent_canon_preflight import AgentCanonPreflightResult, run_agent_canon_preflight

if __package__:
    from .packets import (
        ACTIVE_DESIGN_PACKET_SCHEMA,
        ActiveDesignPacketConfig,
        parse_active_design_packet_input,
        resolve_cross_cutting_document_packet,
        resolve_role_document_packet,
    )
else:
    from packets import (
        ACTIVE_DESIGN_PACKET_SCHEMA,
        ActiveDesignPacketConfig,
        parse_active_design_packet_input,
        resolve_cross_cutting_document_packet,
        resolve_role_document_packet,
    )

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
        resolve_task_spec,
        resolve_workflow_family,
        select_roles,
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
        resolve_task_spec,
        resolve_workflow_family,
        select_roles,
        task_ids,
    )

if __package__:
    from .manifest_rendering import (
        contract_complete_implementation_policy_output_lines,
        checkout_identity_policy_output_lines,
        coordination_capability_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        public_command_for_layout,
        repo_tool_routing_policy_output_lines,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
        implementation_handoff_required,
    )
else:
    from manifest_rendering import (
        contract_complete_implementation_policy_output_lines,
        checkout_identity_policy_output_lines,
        coordination_capability_policy_output_lines,
        default_quality_check_policy_output_lines,
        format_subagent_role_instance_wave_chunks,
        format_subagent_wave,
        format_subagent_wave_chunks,
        language_review_candidates,
        pre_handoff_gate_status_output_lines,
        pre_handoff_scope_policy_output_lines,
        public_command_for_layout,
        repo_tool_routing_policy_output_lines,
        same_role_subagent_policy_output_lines,
        standard_agent_wave_sequence_output_lines,
        subagent_wave_record_command,
        suggested_public_skills,
        user_facing_language_policy_output_lines,
        implementation_handoff_required,
    )

if __package__:
    from .implementation_dispatch import (
        capacity_start_output_lines,
        codex_runtime_max_depth,
        codex_runtime_max_threads,
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        validate_agent_type_selections,
        workflow_spawn_budget,
    )
else:
    from implementation_dispatch import (
        capacity_start_output_lines,
        codex_runtime_max_depth,
        codex_runtime_max_threads,
        format_agent_type_selections,
        parse_agent_type_selections,
        recommended_dynamic_expansion_wave_slots,
        recommended_dynamic_expansion_waves,
        recommended_initial_subagent_wave,
        validate_agent_type_selections,
        workflow_spawn_budget,
    )

if __package__:
    from .agent_team import (
        PreparedRunBundle,
        prepare_run_bundle,
    )
else:
    from agent_team import (  # type: ignore[no-redef]
        PreparedRunBundle,
        prepare_run_bundle,
    )

if __package__:
    from .workspace_scope import (
        make_run_id,
        resolve_report_root,
        resolve_repository_roots,
    )
else:
    from workspace_scope import (  # type: ignore[no-redef]
        make_run_id,
        resolve_report_root,
        resolve_repository_roots,
    )
from task_authority import (
    AUTHORITY_FILE_NAME,
    hash_baseline_bytes,
)
from workflow_monitor import append_monitoring


@dataclass(frozen=True)
class BootstrapRunContext:
    """Resolved run metadata for bootstrap output and bundle creation."""

    created_at_iso: str
    report_root: Path
    run_id: str
    report_dir: Path
    manual_specialists: tuple[str, ...]
    enabled_specialists: tuple[str, ...]
    task_default_specialists: tuple[str, ...]
    language_review_candidates: tuple[str, ...]
    default_review_pack_ids: tuple[str, ...]
    workflow_family_id: str | None
    workflow_family_name: str | None
    workflow_active_spawn_budget: int | None
    workflow_max_write_subagents: int | None
    issue_worker_candidate: Mapping[str, object] | None = None
    repository_roots: object | None = None


@dataclass(frozen=True)
class BootstrapRuntime:
    """Runtime objects created by bootstrap before output."""

    roles: tuple[Role, ...]
    created_files: tuple[str, ...]
    active_pointer: Path
    agent_type_selections: tuple[AgentTypeSelection, ...]
    active_design_packet: ActiveDesignPacketConfig


def suggested_skills(
    task_id: str | None,
    workflow_family_id: str | None,
    task_text: str = "",
    *,
    source_root: Path | None = None,
) -> tuple[str, ...]:
    """Return the public skills that should be read before work starts."""
    return suggested_public_skills(
        task_id,
        workflow_family_id,
        task_text,
        source_root=source_root,
    )


def codex_agents_for_role(config: TeamConfig, role_id: str) -> tuple[str, ...]:
    """Return Codex subagent candidates for one permanent role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role.id == role_id:
            return role.codex_agents
    return ()


def document_packet_output(
    config: TeamConfig,
    role_id: str,
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render one role's explicit document packet as a CSV-like path list."""
    role = next(
        role
        for role in config.always_on_roles + config.specialist_roles
        if role.id == role_id
    )
    packet = resolve_role_document_packet(
        config,
        role,
        report_dir,
        workspace_root,
        active_design_packet,
        agentcanon_source_root,
    )
    return ",".join(str(entry.path) for entry in packet.read_before_work)


def cross_cutting_document_packet_output(
    workspace_root: Path,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render the common cross-cutting document packet."""
    return ",".join(
        str(entry.path)
        for entry in resolve_cross_cutting_document_packet(
            workspace_root,
            agentcanon_source_root,
        )
    )


def build_parser(
    enable_names: tuple[str, ...], task_choices: tuple[str, ...]
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard external-runtime reports/agents/<run-id> bundle "
            "for one agent-team run."
        )
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Short task description for the run.",
    )
    parser.add_argument(
        "--owner",
        required=True,
        help="Human or agent responsible for the run.",
    )
    parser.add_argument(
        "--task-id",
        choices=task_choices,
        help=(
            "Optional task catalog id. Expands default specialists and review packs "
            "for that task."
        ),
    )
    parser.add_argument(
        "--issue-worker-candidate",
        metavar="JSON",
        help=(
            "Explicit JSON IssueWorker candidate that activates the T15 publisher "
            "initial wave. Other workflows ignore this input."
        ),
    )
    parser.add_argument(
        "--run-id",
        help="Optional explicit run id. Defaults to a timestamped slug.",
    )
    parser.add_argument(
        "--active-design-packet",
        metavar="JSON",
        help=(
            f"Atomic {ACTIVE_DESIGN_PACKET_SCHEMA} JSON object. All schema, path, "
            "document_flow_required, clause_registry, and graph-entry fields are required."
        ),
    )
    parser.add_argument(
        "--enable",
        action="append",
        choices=enable_names,
        default=[],
        help="Enable a specialist role or review pack. Repeat the flag to enable multiple entries.",
    )
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help=(
            "Optional changed path hint. Repeat to populate explicit language-review "
            "candidates."
        ),
    )
    parser.add_argument(
        "--select-agent-type",
        action="append",
        default=[],
        metavar="ROLE_ID=AGENT_TYPE:EVIDENCE",
        help=(
            "Explicit parent-packet role-to-agent selection with evidence. "
            "Required for non-default codex_agents candidates."
        ),
    )
    parser.add_argument(
        "--no-language-review-candidates",
        action="store_true",
        help=(
            "Disable language-review candidate discovery from changed paths or git status."
        ),
    )
    parser.add_argument(
        "--full-team",
        action="store_true",
        help="Enable every specialist role for this run.",
    )
    parser.add_argument(
        "--no-default-review-packs",
        action="store_true",
        help=(
            "When --task-id is set, skip review packs whose default_for_tasks "
            "contains that task."
        ),
    )
    parser.add_argument(
        "--report-root",
        help=(
            "Optional external directory that will contain per-run report folders. "
            "Defaults below --runtime-root."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        help=(
            "Explicit external runtime root for reports, active-run state, "
            "ledgers, and receipts. Defaults to AGENT_CANON_RUNTIME_ROOT."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve run-local reports and current-checkout path authority.",
    )
    parser.add_argument(
        "--skip-agent-canon-preflight",
        action="store_true",
        help="Skip the automatic read-only AgentCanon update-plan preflight.",
    )
    return parser


def parse_issue_worker_candidate(value: str | None) -> Mapping[str, object] | None:
    """Parse one explicit IssueWorker candidate without inferring candidates."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("issue_worker_candidate:invalid_json") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError("issue_worker_candidate:must_be_nonempty_object")
    return parsed


def resolve_bootstrap_context(
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    workspace_root: Path,
    repository_roots: object | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> BootstrapRunContext:
    """Resolve workflow family, specialists, and report paths for one run."""
    if implementation_handoff_required(args.task):
        implementer_roles = [
            role
            for role in (*config.always_on_roles, *config.specialist_roles)
            if role.id == "implementer" and role.codex_agents
        ]
        if not implementer_roles:
            raise RuntimeError(
                "WRITE_SUBAGENT_AUTHORIZATION=required;"
                "PARENT_BLOCKED_ROUTE=typed_blocked_retry_or_user_report"
            )
    created_at = datetime.now(UTC).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    # The parent capability authorizes the eventual write; it does not replace
    # the caller's logical workspace/report-root selection.
    report_root = (
        repository_roots.report_root
        if repository_roots is not None
        else resolve_report_root(
            args.report_root,
            workspace_root,
            runtime_root=args.runtime_root,
        )
    )
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    manual_specialists = expand_enabled_specialists(config, catalog, tuple(args.enable))
    enabled_specialists = list(manual_specialists)
    task_default_specialists: tuple[str, ...] = ()
    default_review_pack_ids: tuple[str, ...] = ()
    workflow_family_id: str | None = None
    workflow_family_name: str | None = None
    workflow_active_spawn_budget: int | None = None
    workflow_max_write_subagents: int | None = None
    if args.task_id is not None:
        task_spec = resolve_task_spec(catalog, args.task_id)
        workflow_family_id = str(task_spec["family"])
        workflow_family = resolve_workflow_family(catalog, workflow_family_id)
        workflow_family_name = str(workflow_family["name"])
        workflow_active_spawn_budget, workflow_max_write_subagents = (
            workflow_spawn_budget(
                catalog,
                workflow_family_id,
            )
        )
        task_default_specialists = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=args.task_id,
            include_default_review_packs=not args.no_default_review_packs,
        )
        if not args.no_default_review_packs:
            default_review_pack_ids = default_review_pack_ids_for_task(
                catalog,
                args.task_id,
            )
        # Task-catalog specialists and default review packs remain candidates;
        # explicit enablement or an owner-critical route activates them.
    language_candidates: tuple[str, ...] = ()
    if not args.no_language_review_candidates:
        language_candidates = language_review_candidates(
            workspace_root=workspace_root,
            changed_paths=tuple(args.changed_path),
        )
    return BootstrapRunContext(
        created_at_iso=created_at_iso,
        report_root=report_root,
        run_id=run_id,
        report_dir=report_dir,
        manual_specialists=tuple(manual_specialists),
        enabled_specialists=tuple(enabled_specialists),
        task_default_specialists=task_default_specialists,
        language_review_candidates=language_candidates,
        default_review_pack_ids=default_review_pack_ids,
        workflow_family_id=workflow_family_id,
        workflow_family_name=workflow_family_name,
        workflow_active_spawn_budget=workflow_active_spawn_budget,
        workflow_max_write_subagents=workflow_max_write_subagents,
        issue_worker_candidate=issue_worker_candidate,
        repository_roots=repository_roots,
    )


def selected_review_roles(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return role ids that should appear in the review declaration."""
    fixed_review_roles = {
        "reviewer",
        "verifier",
        "auditor",
        "docs_workflow_steward",
    }
    return tuple(
        role.id
        for role in roles
        if role.id.endswith("_reviewer") or role.id in fixed_review_roles
    )


def emit_bootstrap_output(
    *,
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    context: BootstrapRunContext,
    workspace_root: Path,
    preflight: AgentCanonPreflightResult,
    runtime: BootstrapRuntime,
) -> None:
    """Print the machine-readable bootstrap summary."""
    repository_roots = context.repository_roots
    if repository_roots is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    source_root = getattr(repository_roots, "agentcanon_source_root", None)
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
        source_root=source_root,
    )
    active_skills = current_stage_skills(
        selected_skills, args.task, source_root=source_root
    )
    deferred_skills = deferred_stage_skills(
        selected_skills, args.task, source_root=source_root
    )
    review_roles = selected_review_roles(runtime.roles)
    public_layout = getattr(repository_roots, "layout", None)
    if public_layout is None:
        raise RuntimeError("runtime_roots_invalid:layout_missing")
    print("AGENT_CANON_PREFLIGHT_COMMAND=bash bootstrap.sh --help")
    print(f"AGENT_CANON_PREFLIGHT_STATUS={preflight.status}")
    print(f"AGENT_CANON_PREFLIGHT_REASON={preflight.reason}")
    print(f"AGENT_CANON_PREFLIGHT_NEXT={preflight.next_step}")
    print(f"AGENT_CANON_PREFLIGHT_CHECKLIST={preflight.checklist_path}")
    print(f"AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS={preflight.checklist_status}")
    print(f"RUN_ID={context.run_id}")
    print(f"REPORT_DIR={context.report_dir}")
    print(f"TASK_AUTHORITY={context.report_dir / 'task_authority.yaml'}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    for line in capacity_start_output_lines(catalog, workspace_root, context.run_id):
        print(line)
    print(f"REQUEST_CONTRACT={context.report_dir / 'user_request_contract.md'}")
    print("REQUEST_CONTRACT_REQUIRED=yes")
    print(f"RUNTIME_MAX_THREADS={codex_runtime_max_threads(workspace_root)}")
    print(f"RUNTIME_MAX_DEPTH={codex_runtime_max_depth(workspace_root)}")
    print(f"SUGGESTED_SKILLS={','.join(selected_skills)}")
    print(f"ACTIVE_SKILLS={','.join(active_skills)}")
    print(f"DEFERRED_SKILLS={','.join(deferred_skills) or '-'}")
    print(
        "START_DECLARATION="
        f"workflow={context.workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(active_skills) or '-'}, "
        f"review={','.join(review_roles) or '-'}"
    )
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
        print("TASK_ID_ROUTE_STATUS=explicit")
        print(f"WORKFLOW_FAMILY={context.workflow_family_id}")
        print(f"WORKFLOW_FAMILY_NAME={context.workflow_family_name}")
        print(
            "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet"
        )
        print(f"WORKFLOW_ACTIVE_SPAWN_BUDGET={context.workflow_active_spawn_budget}")
        print(f"WORKFLOW_MAX_WRITE_SUBAGENTS={context.workflow_max_write_subagents}")
        print("INITIAL_THREE_AGENT_INTAKE_IS_TOTAL_CAP=no")
        print("DYNAMIC_SUBAGENT_EXPANSION=allowed")
        print("DYNAMIC_SUBAGENT_EXPANSION_LEDGER=schedule.md#Agent Wave Ledger")
        print(
            "DYNAMIC_SUBAGENT_EXPANSION_MONITOR=workflow_monitoring.md#Behavior Events"
        )
        if context.workflow_family_id == "issue_worker_publication":
            print(
                "ISSUE_WORKER_CANDIDATE_STATUS="
                + ("explicit" if context.issue_worker_candidate else "absent")
            )
            print(
                "ISSUE_WORKER_DISPATCH_ROUTE="
                "tools/agent_tools/agent_team.py#dispatch_issue_worker"
            )
            print("ISSUE_WORKER_EXECUTION_ROLE=publisher")
            print(
                "ISSUE_WORKER_TOOL_CALL_ROUTE="
                "tools/agent_tools/tool_calls.py#materialize_issue_worker_tool_call"
            )
            print("ISSUE_WORKER_READBACK=URL,number,body,state")
        print(
            f"SUBAGENT_WAVE_RECORD_COMMAND={subagent_wave_record_command(context.report_dir, layout=public_layout)}"
        )
        active_budget = context.workflow_active_spawn_budget or 0
        initial_wave = recommended_initial_subagent_wave(
            runtime.roles,
            active_budget,
            catalog,
            runtime.agent_type_selections,
            source_root / ".codex" / "agents",
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=context.issue_worker_candidate,
        )
        if initial_wave:
            print("PARENT_WAVE_EXECUTION_GATE=required_before_implementation")
            print("PARENT_WAVE_EXECUTION_GATE_STATUS=blocked_authority_required")
            print(
                "PARENT_WAVE_EXECUTION_GATE_ARTIFACTS="
                "schedule.md#Agent Wave Ledger,workflow_monitoring.md#Actual Wave Events"
            )
        else:
            print("PARENT_WAVE_EXECUTION_GATE=not_applicable")
            print("PARENT_WAVE_EXECUTION_GATE_STATUS=no_initial_wave")
        expansion_waves = recommended_dynamic_expansion_waves(
            runtime.roles,
            active_budget,
            initial_wave,
            catalog,
            runtime.agent_type_selections,
            source_root / ".codex" / "agents",
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=context.issue_worker_candidate,
        )
        expansion_wave_slots = recommended_dynamic_expansion_wave_slots(
            runtime.roles,
            active_budget,
            initial_wave,
            catalog,
            runtime.agent_type_selections,
            source_root / ".codex" / "agents",
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=context.issue_worker_candidate,
        )
        print(
            "SUBAGENT_AGENT_TYPE_SELECTIONS="
            f"{format_agent_type_selections(runtime.agent_type_selections)}"
        )
        print(f"RECOMMENDED_INITIAL_SUBAGENT_WAVE={format_subagent_wave(initial_wave)}")
        print(
            f"RECOMMENDED_DYNAMIC_EXPANSION_WAVES={format_subagent_wave_chunks(expansion_waves)}"
        )
        print(
            "RECOMMENDED_DYNAMIC_EXPANSION_ROLE_INSTANCES="
            f"{format_subagent_role_instance_wave_chunks(expansion_wave_slots)}"
        )
        for line in standard_agent_wave_sequence_output_lines():
            print(line)
        for line in same_role_subagent_policy_output_lines():
            print(line)
        print(f"TASK_DEFAULT_SPECIALISTS={','.join(context.task_default_specialists)}")
        print(f"PLANNED_ACTIVE_ROLE_COUNT={len(runtime.roles)}")
        print(
            "SUBAGENT_FANOUT_EXPECTATION=record_skipped_roles_when_below_family_default"
        )
    else:
        print("TASK_ID_ROUTE_STATUS=missing")
        print("TASK_ID_ROUTE_REQUIRED_FOR_MULTI_AGENT=yes")
        print("TASK_ID_ROUTE_RECOMMENDED_TASK_IDS=T11,T12")
        print("SUBAGENT_FANOUT_EXPECTATION=blocked_until_task_id_or_explicit_family")
    for line in pre_handoff_scope_policy_output_lines():
        print(line)
    for line in checkout_identity_policy_output_lines():
        print(line)
    for line in coordination_capability_policy_output_lines():
        print(line)
    for line in pre_handoff_gate_status_output_lines():
        print(line)
    for line in user_facing_language_policy_output_lines():
        print(line)
    for line in contract_complete_implementation_policy_output_lines(args.task):
        print(line)
    for line in repo_tool_routing_policy_output_lines(
        selected_skills,
        source_root=source_root,
    ):
        print(line)
    for line in default_quality_check_policy_output_lines(
        runtime.roles,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        language_review_candidates=context.language_review_candidates,
        default_review_packs_enabled=False,
        default_review_pack_ids=context.default_review_pack_ids,
        layout=public_layout,
    ):
        print(line)
    if not args.no_language_review_candidates:
        print(
            "LANGUAGE_REVIEW_CANDIDATES="
            f"{','.join(context.language_review_candidates)}"
        )
    print(
        "IMPLEMENTATION_CODEX_AGENTS="
        f"{','.join(codex_agents_for_role(config, 'implementer'))}"
    )
    print(
        f"ROLE_MODEL_MATRIX={';'.join(codex_agent_model_matrix_for_roles(runtime.roles))}"
    )
    print("IMPLEMENTATION_SURFACE_ROUTE_STATUS=pending")
    print(
        "IMPLEMENTATION_SURFACE_ROUTE_COMMAND="
        +
        public_command_for_layout(
            "python3 tools/agent_tools/search.py "
            "--query-file <request-or-design-question.txt> "
            "--providers text,semantic,vector,tool,header-deps,code-deps "
            "--format json",
            public_layout,
        )
    )
    print("TOOL_REUSE_LEDGER_STATUS=required_before_custom_implementation")
    print("PRE_EDIT_REJECTION_PREDICTION_STATUS=pending")
    print(
        "PRE_EDIT_REJECTION_COMMAND="
        +
        public_command_for_layout(
            "python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>",
            public_layout,
        )
    )
    print("AGENT_REPORT_COLLECTION_STATUS=available")
    print(
        "AGENT_REPORT_COLLECTION_STATUS_COMMAND="
        + public_command_for_layout(
            "python3 tools/agent_tools/runtime_log_archive_git.py status",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_ARCHIVE_RUN_COMMAND="
        +
        public_command_for_layout(
            f"python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir {context.report_dir}",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_COLLECTION_SYNC_COMMAND="
        + public_command_for_layout(
            "python3 tools/agent_tools/runtime_log_archive_git.py sync",
            public_layout,
        )
    )
    print(
        "CROSS_CUTTING_DOCUMENT_PACKET="
        f"{cross_cutting_document_packet_output(workspace_root, source_root)}"
    )
    print(
        "DESIGN_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'designer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(
        "IMPLEMENTATION_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'implementer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(f"ACTIVE_ROLES={','.join(role.id for role in runtime.roles)}")
    print(f"CREATED_FILES={','.join(runtime.created_files)}")
    print(f"AGENT_CANON_ACTIVE_RUN_POINTER={runtime.active_pointer}")


def record_bootstrap_monitoring(
    context: BootstrapRunContext,
    roles: tuple[Role, ...],
    selected_skills: tuple[str, ...],
    review_roles: tuple[str, ...],
    task_text: str,
    preflight_status: str,
    source_root: Path | None = None,
) -> None:
    """Record bootstrap monitoring evidence."""
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    selected_source_root = source_root
    append_monitoring(
        context.report_dir,
        signals=[
            (
                f"workflow={context.workflow_family_name or 'Unspecified'}, "
                f"skills={','.join(current_stage_skills(selected_skills, task_text, source_root=selected_source_root)) or '-'}, "
                f"review={','.join(review_roles) or '-'}"
            ),
            f"stage owner routing active_roles={','.join(role.id for role in roles)}",
            f"agent_canon_preflight={preflight_status}",
            "web_research_not_required: bootstrap does not decide external research",
        ],
        interventions=[
            f"created run bundle and workflow_monitoring.md at {context.report_dir}"
        ],
        behavior_events=["token_efficiency_not_required reason=bootstrap_default"],
    )


def _read_optional_bytes(path: Path) -> bytes | None:
    """Read one prior file exactly, preserving absent state as ``None``."""
    return path.read_bytes() if path.is_file() else None


def _restore_runtime_file(
    boundary: object,
    path: Path,
    prior: bytes | None,
    purpose: str,
) -> None:
    """Restore one captured runtime file without touching source state."""
    del purpose
    if prior is not None:
        boundary.atomic_write_bytes(path, prior)  # type: ignore[attr-defined]
        return
    if not path.exists():
        return
    path.unlink()


def publish_prepared_run(
    spec: RunBundleSpec,
    prepared: PreparedRunBundle,
    report_root: Path,
    post_move: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    """Stage one prepared byte map, move it once, publish sidecars, and rollback."""
    report_root = report_root.resolve(strict=False)
    configured_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip() or None
    runtime_base = configured_runtime or report_root.parent
    boundary = runtime_artifact_boundary(
        spec.agentcanon_source_root,
        runtime_base,
        create=True,
    )
    report_root = boundary.resolve(report_root)
    boundary.ensure_directory(report_root.relative_to(boundary.root))
    final_run = spec.report_dir.resolve()
    expected_final_run = (report_root / spec.run_id).resolve()
    if final_run != expected_final_run:
        raise RuntimeError("runtime_roots_invalid:report_dir_mismatch")
    if final_run.exists():
        raise RuntimeError(f"bootstrap_run_id_collision:{spec.run_id}")
    pointer = report_root / ".active_run"
    pointer_baseline = report_root / ".active_run.sha256"
    authority_baseline = final_run / f"{AUTHORITY_FILE_NAME}.sha256"
    prior_files = {
        pointer: _read_optional_bytes(pointer),
        pointer_baseline: _read_optional_bytes(pointer_baseline),
        authority_baseline: _read_optional_bytes(authority_baseline),
    }
    prior_children = {child.name for child in report_root.iterdir()} if report_root.is_dir() else set()
    stage_dir: Path | None = None
    moved = False
    try:
        stage_dir = Path(tempfile.mkdtemp(prefix=".stage-run-", dir=str(report_root)))
        for relative, payload in prepared.files:
            relative_path = Path(relative)
            if (
                relative_path.is_absolute()
                or not relative
                or any(part in {"", ".", ".."} for part in relative_path.parts)
            ):
                raise RuntimeError(f"runtime_artifact_path_invalid:stage:{relative}")
            target = stage_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if target.read_bytes() != payload:
                raise RuntimeError(f"bootstrap_stage_readback_failed:{relative}")
        os.replace(stage_dir, final_run)
        stage_dir = None
        moved = True
        pointer_bytes = (str(final_run.resolve()) + "\n").encode("utf-8")
        boundary.atomic_write_bytes(pointer, pointer_bytes)
        boundary.atomic_write_bytes(pointer_baseline, hash_baseline_bytes(pointer_bytes))
        authority_path = final_run / AUTHORITY_FILE_NAME
        if authority_path.is_file():
            boundary.atomic_write_bytes(
                authority_baseline,
                hash_baseline_bytes(authority_path.read_bytes()),
            )
        if post_move is not None:
            post_move()
        for relative, payload in prepared.files:
            if relative == "workflow_monitoring.md":
                continue
            if (final_run / relative).read_bytes() != payload:
                raise RuntimeError(f"bootstrap_final_readback_failed:{relative}")
        monitoring_path = final_run / "workflow_monitoring.md"
        if not monitoring_path.is_file() or not monitoring_path.read_bytes().startswith(
            dict(prepared.files).get("workflow_monitoring.md", b"")
        ):
            raise RuntimeError("bootstrap_monitoring_readback_failed")
        if pointer.read_bytes() != pointer_bytes:
            raise RuntimeError("bootstrap_pointer_readback_failed")
        if pointer_baseline.read_bytes() != hash_baseline_bytes(pointer_bytes):
            raise RuntimeError("bootstrap_pointer_baseline_readback_failed")
        if authority_path.is_file() and authority_baseline.read_bytes() != hash_baseline_bytes(
            authority_path.read_bytes()
        ):
            raise RuntimeError("bootstrap_authority_baseline_readback_failed")
        return prepared.created_files
    except Exception as primary_error:
        rollback_errors: list[str] = []
        try:
            if stage_dir is not None and stage_dir.exists():
                shutil.rmtree(stage_dir)
            if moved and final_run.exists():
                shutil.rmtree(final_run)
            for path, prior in prior_files.items():
                _restore_runtime_file(
                    boundary,
                    path,
                    prior,
                    "bootstrap-publish-rollback",
                )
            observed_children = {child.name for child in report_root.iterdir()} if report_root.is_dir() else set()
            if observed_children != prior_children:
                raise RuntimeError(
                    f"child_delta:{sorted(observed_children ^ prior_children)}"
                )
            for path, prior in prior_files.items():
                if _read_optional_bytes(path) != prior:
                    raise RuntimeError(f"prior_bytes:{path}")
        except Exception as rollback_error:
            rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(
                "bootstrap_publish_rollback_failed:"
                f"{primary_error}:{';'.join(rollback_errors)}"
            ) from primary_error
        raise


def main() -> int:
    """Run the bootstrap command."""
    # Source resolution itself uses the external runtime boundary.  Parse only
    # that capability before loading source-owned config so an unrelated
    # caller TMPDIR cannot be mistaken for this run's artifact root.
    runtime_parser = argparse.ArgumentParser(add_help=False)
    runtime_parser.add_argument("--runtime-root")
    runtime_args, _ = runtime_parser.parse_known_args()
    selected_runtime = (
        runtime_args.runtime_root
        or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    )
    if selected_runtime:
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = selected_runtime
        for name in (
            "TMPDIR",
            "TEMP",
            "TMP",
            "XDG_CACHE_HOME",
            "PYTHONPYCACHEPREFIX",
            "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "AGENT_CANON_CLI_TARGET_DIR",
            "RUSTUP_HOME",
            "ELAN_HOME",
        ):
            os.environ.pop(name, None)
    try:
        source_resolution = resolve_agent_canon_source_root(Path(__file__).resolve())
        source_root = source_resolution.source_root
        config = load_team_config(source_root / "agents" / "agents_config.json")
        catalog = load_task_catalog(config, root=source_root)
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    args = build_parser(enable_choices(config, catalog), task_ids(catalog)).parse_args()
    try:
        issue_worker_candidate = parse_issue_worker_candidate(
            args.issue_worker_candidate
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    try:
        explicit_active_design_packet = parse_active_design_packet_input(
            args.active_design_packet
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    workspace_root = Path(args.workspace_root).resolve()
    try:
        repository_roots = resolve_repository_roots(
            workspace_root,
            args.report_root,
            source_root=source_root,
            canon_root=source_resolution.canon_root,
            runtime_root=args.runtime_root,
        )
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    try:
        preflight = run_agent_canon_preflight(
            workspace_root,
            skip=args.skip_agent_canon_preflight,
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 1
    context = resolve_bootstrap_context(
        args,
        config,
        catalog,
        workspace_root,
        repository_roots,
        issue_worker_candidate,
    )
    roles = select_roles(
        config,
        list(context.enabled_specialists),
        args.full_team,
        catalog=catalog,
        workflow_family_id=context.workflow_family_id,
        issue_worker_candidate=context.issue_worker_candidate,
    )
    try:
        agent_type_selections = validate_agent_type_selections(
            config,
            roles,
            parse_agent_type_selections(tuple(args.select_agent_type)),
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 1
    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
        source_root=repository_roots.agentcanon_source_root,
    )
    run_spec = RunBundleSpec(
            config=config,
            report_dir=context.report_dir,
            run_id=context.run_id,
            task=args.task,
            owner=args.owner,
            created_at_iso=context.created_at_iso,
            roles=roles,
            workspace_root=workspace_root,
            agentcanon_source_root=repository_roots.agentcanon_source_root,
            report_root=repository_roots.report_root,
            repository_roots=repository_roots,
            active_design_packet=explicit_active_design_packet,
            workflow_family_id=context.workflow_family_id or "",
            issue_worker_candidate=context.issue_worker_candidate,
            manual_specialists=context.manual_specialists,
            task_default_specialists=context.task_default_specialists,
            language_review_candidates=context.language_review_candidates,
            default_review_packs_enabled=False,
            default_review_pack_ids=context.default_review_pack_ids,
            selected_skills=selected_skills,
            task_catalog=catalog,
            agent_type_selections=agent_type_selections,
        )
    try:
        prepared = prepare_run_bundle(run_spec)
        active_design_packet = prepared.active_design_packet
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    active_pointer = context.report_root / ".active_run"
    review_roles = selected_review_roles(roles)
    runtime = BootstrapRuntime(
        roles=roles,
        created_files=prepared.created_files,
        active_pointer=active_pointer,
        agent_type_selections=agent_type_selections,
        active_design_packet=active_design_packet,
    )
    try:
        publish_prepared_run(
            run_spec,
            prepared,
            context.report_root,
            post_move=lambda: record_bootstrap_monitoring(
                context,
                roles,
                selected_skills,
                review_roles,
                args.task,
                preflight.status,
                repository_roots.agentcanon_source_root,
            ),
        )
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    emit_bootstrap_output(
        args=args,
        config=config,
        catalog=catalog,
        context=context,
        workspace_root=workspace_root,
        preflight=preflight,
        runtime=runtime,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
