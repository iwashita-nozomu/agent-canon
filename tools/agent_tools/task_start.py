#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides task start agent workflow automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Start one agent-task run with machine-generated workflow and review hints."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_canon_preflight import AgentCanonPreflightResult, run_agent_canon_preflight
from agent_team import (
    Role,
    RunBundleSpec,
    TaskCatalog,
    TeamConfig,
    auto_language_specialists,
    codex_agent_model_matrix_for_roles,
    codex_runtime_max_depth,
    codex_runtime_max_threads,
    contract_complete_implementation_policy_output_lines,
    create_run_bundle,
    current_stage_skills,
    default_quality_check_policy_output_lines,
    default_review_pack_ids_for_task,
    default_specialists_for_task,
    deferred_stage_skills,
    enable_choices,
    expand_enabled_specialists,
    format_subagent_role_instance_wave_chunks,
    format_subagent_wave,
    format_subagent_wave_chunks,
    load_task_catalog,
    load_team_config,
    make_run_id,
    pre_handoff_gate_status_output_lines,
    pre_handoff_scope_policy_output_lines,
    recommended_dynamic_expansion_wave_slots,
    recommended_dynamic_expansion_waves,
    recommended_initial_subagent_wave,
    repo_tool_routing_policy_output_lines,
    resolve_cross_cutting_document_packet,
    resolve_report_root,
    resolve_role_document_packet,
    resolve_task_spec,
    resolve_workflow_family,
    same_role_subagent_policy_output_lines,
    select_roles,
    standard_agent_wave_sequence_output_lines,
    subagent_wave_record_command,
    suggested_public_skills,
    task_ids,
    user_facing_language_policy_output_lines,
    workflow_spawn_budget,
)
from task_authority import write_task_authority_baselines
from workflow_monitor import append_monitoring


@dataclass(frozen=True)
class TaskStartContext:
    """Resolved run metadata for task-start output and bundle creation."""

    created_at_iso: str
    report_root: Path
    run_id: str
    report_dir: Path
    manual_specialists: tuple[str, ...]
    enabled_specialists: tuple[str, ...]
    task_default_specialists: tuple[str, ...]
    auto_specialists: tuple[str, ...]
    default_review_pack_ids: tuple[str, ...]
    workflow_family_id: str | None
    workflow_family_name: str | None
    workflow_active_spawn_budget: int | None
    workflow_max_write_subagents: int | None


@dataclass(frozen=True)
class TaskStartRuntime:
    """Runtime objects created by task-start before output."""

    roles: tuple[Role, ...]
    created_files: tuple[str, ...]
    active_pointer: Path


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
) -> str:
    """Render one role's explicit document packet as a CSV-like path list."""
    role = next(
        role
        for role in config.always_on_roles + config.specialist_roles
        if role.id == role_id
    )
    packet = resolve_role_document_packet(config, role, report_dir, workspace_root)
    return ",".join(str(entry.path) for entry in packet.read_before_work)


def cross_cutting_document_packet_output(workspace_root: Path) -> str:
    """Render the common cross-cutting document packet."""
    return ",".join(
        str(entry.path)
        for entry in resolve_cross_cutting_document_packet(workspace_root)
    )


def build_parser(
    enable_names: tuple[str, ...], task_choices: tuple[str, ...]
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard run bundle and emit machine-generated "
            "workflow/skill/review declarations for the first task update."
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
        "--run-id",
        help="Optional explicit run id. Defaults to a timestamped slug.",
    )
    parser.add_argument(
        "--enable",
        action="append",
        choices=enable_names,
        default=[],
        help="Enable a specialist role or review pack. Repeat the flag to enable multiple entries.",
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
        "--changed-path",
        action="append",
        default=[],
        help=(
            "Optional changed path hint. Repeat to drive automatic language-specific "
            "reviewer selection."
        ),
    )
    parser.add_argument(
        "--no-auto-language-reviewers",
        action="store_true",
        help=(
            "Disable automatic language-specific reviewer selection from changed paths "
            "or git status."
        ),
    )
    parser.add_argument(
        "--report-root",
        help=(
            "Optional directory that will contain per-run report folders. Defaults to "
            "<workspace-root>/reports/agents."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve run-bundle paths and write permissions.",
    )
    parser.add_argument(
        "--skip-agent-canon-preflight",
        action="store_true",
        help="Skip the automatic make agent-canon-ensure-latest preflight.",
    )
    return parser


def suggested_skills(
    task_id: str | None,
    workflow_family_id: str | None,
    task_text: str = "",
) -> tuple[str, ...]:
    """Return the public skill set required by the selected route."""
    return suggested_public_skills(task_id, workflow_family_id, task_text)


def resolve_task_start_context(
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    workspace_root: Path,
) -> TaskStartContext:
    """Resolve workflow family, specialists, and report paths for one task start."""
    created_at = datetime.now(UTC).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    report_root = resolve_report_root(args.report_root, workspace_root)
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
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
    manual_specialists = expand_enabled_specialists(config, catalog, tuple(args.enable))
    enabled_specialists = list(manual_specialists)
    for role_id in task_default_specialists:
        if role_id not in enabled_specialists:
            enabled_specialists.append(role_id)
    auto_specialists: tuple[str, ...] = ()
    if not args.no_auto_language_reviewers:
        auto_specialists = auto_language_specialists(
            workspace_root=workspace_root,
            changed_paths=tuple(args.changed_path),
        )
        for role_id in auto_specialists:
            if role_id not in enabled_specialists:
                enabled_specialists.append(role_id)
    return TaskStartContext(
        created_at_iso=created_at_iso,
        report_root=report_root,
        run_id=run_id,
        report_dir=report_dir,
        manual_specialists=tuple(manual_specialists),
        enabled_specialists=tuple(enabled_specialists),
        task_default_specialists=task_default_specialists,
        auto_specialists=auto_specialists,
        default_review_pack_ids=default_review_pack_ids,
        workflow_family_id=workflow_family_id,
        workflow_family_name=workflow_family_name,
        workflow_active_spawn_budget=workflow_active_spawn_budget,
        workflow_max_write_subagents=workflow_max_write_subagents,
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


def emit_task_start_output(
    *,
    args: argparse.Namespace,
    config: TeamConfig,
    context: TaskStartContext,
    workspace_root: Path,
    preflight: AgentCanonPreflightResult,
    runtime: TaskStartRuntime,
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Print the machine-readable task-start summary."""
    review_roles = selected_review_roles(runtime.roles)
    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
    )
    active_skills = current_stage_skills(selected_skills, args.task)
    deferred_skills = deferred_stage_skills(selected_skills, args.task)
    start_declaration = (
        f"workflow={context.workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(active_skills) or '-'}, "
        f"review={','.join(review_roles) or '-'}"
    )
    request_contract_path = context.report_dir / "user_request_contract.md"
    print("AGENT_CANON_PREFLIGHT_COMMAND=make agent-canon-ensure-latest")
    print(f"AGENT_CANON_PREFLIGHT_STATUS={preflight.status}")
    print(f"AGENT_CANON_PREFLIGHT_REASON={preflight.reason}")
    print(f"AGENT_CANON_PREFLIGHT_NEXT={preflight.next_step}")
    print(f"AGENT_CANON_PREFLIGHT_CHECKLIST={preflight.checklist_path}")
    print(f"AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS={preflight.checklist_status}")
    print(f"RUN_ID={context.run_id}")
    print(f"REPORT_DIR={context.report_dir}")
    print(f"TASK_AUTHORITY={context.report_dir / 'task_authority.yaml'}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    print(f"REQUEST_CONTRACT={request_contract_path}")
    print("REQUEST_CONTRACT_REQUIRED=yes")
    print(f"RUNTIME_MAX_THREADS={codex_runtime_max_threads()}")
    print(f"RUNTIME_MAX_DEPTH={codex_runtime_max_depth()}")
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
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
        print(
            f"SUBAGENT_WAVE_RECORD_COMMAND={subagent_wave_record_command(context.report_dir)}"
        )
        active_budget = context.workflow_active_spawn_budget or 0
        initial_wave = recommended_initial_subagent_wave(runtime.roles, active_budget)
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
        )
        expansion_wave_slots = recommended_dynamic_expansion_wave_slots(
            runtime.roles,
            active_budget,
            initial_wave,
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
    for line in pre_handoff_scope_policy_output_lines():
        print(line)
    for line in pre_handoff_gate_status_output_lines():
        print(line)
    for line in user_facing_language_policy_output_lines():
        print(line)
    for line in contract_complete_implementation_policy_output_lines(args.task):
        print(line)
    for line in repo_tool_routing_policy_output_lines(selected_skills):
        print(line)
    for line in default_quality_check_policy_output_lines(
        runtime.roles,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        auto_specialists=context.auto_specialists,
        default_review_packs_enabled=bool(
            args.task_id is not None and not args.no_default_review_packs
        ),
        default_review_pack_ids=context.default_review_pack_ids,
    ):
        print(line)
    if not args.no_auto_language_reviewers:
        print(f"AUTO_SPECIALISTS={','.join(context.auto_specialists)}")
    print(f"SUGGESTED_SKILLS={','.join(selected_skills)}")
    print(f"ACTIVE_SKILLS={','.join(active_skills)}")
    print(f"DEFERRED_SKILLS={','.join(deferred_skills) or '-'}")
    print(f"START_DECLARATION={start_declaration}")
    print(
        "IMPLEMENTATION_CODEX_AGENTS="
        f"{','.join(codex_agents_for_role(config, 'implementer'))}"
    )
    print(
        f"ROLE_MODEL_MATRIX={';'.join(codex_agent_model_matrix_for_roles(runtime.roles))}"
    )
    print(
        "CROSS_CUTTING_DOCUMENT_PACKET="
        f"{cross_cutting_document_packet_output(workspace_root)}"
    )
    print(
        "DESIGN_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'designer', context.report_dir, workspace_root)}"
    )
    print(
        "IMPLEMENTATION_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'implementer', context.report_dir, workspace_root)}"
    )
    print(f"ACTIVE_ROLES={','.join(role.id for role in runtime.roles)}")
    print(f"CREATED_FILES={','.join(runtime.created_files)}")
    print(f"AGENT_CANON_ACTIVE_RUN_POINTER={runtime.active_pointer}")
    return selected_skills, review_roles, start_declaration


def record_task_start_monitoring(
    context: TaskStartContext,
    roles: tuple[Role, ...],
    start_declaration: str,
    preflight_status: str,
) -> None:
    """Record task-start monitoring evidence."""
    append_monitoring(
        context.report_dir,
        signals=[
            start_declaration,
            f"stage owner routing active_roles={','.join(role.id for role in roles)}",
            f"agent_canon_preflight={preflight_status}",
            "web_research_not_required: task_start does not decide external research",
        ],
        interventions=[
            f"created run bundle and workflow_monitoring.md at {context.report_dir}"
        ],
        behavior_events=["token_efficiency_not_required reason=task_start_default"],
    )


def main() -> int:
    """Run the task-start command."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    args = build_parser(enable_choices(config, catalog), task_ids(catalog)).parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    try:
        preflight = run_agent_canon_preflight(
            workspace_root,
            skip=args.skip_agent_canon_preflight,
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 1
    context = resolve_task_start_context(args, config, catalog, workspace_root)
    roles = select_roles(
        config,
        list(context.enabled_specialists),
        args.full_team,
        catalog=catalog,
        workflow_family_id=context.workflow_family_id,
    )
    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
    )
    created_files = create_run_bundle(
        RunBundleSpec(
            config=config,
            report_dir=context.report_dir,
            run_id=context.run_id,
            task=args.task,
            owner=args.owner,
            created_at_iso=context.created_at_iso,
            roles=roles,
            workspace_root=workspace_root,
            workflow_family_id=context.workflow_family_id or "",
            manual_specialists=context.manual_specialists,
            task_default_specialists=context.task_default_specialists,
            auto_specialists=context.auto_specialists,
            default_review_packs_enabled=bool(
                args.task_id is not None and not args.no_default_review_packs
            ),
            default_review_pack_ids=context.default_review_pack_ids,
            selected_skills=selected_skills,
        )
    )
    active_pointer = context.report_root / ".active_run"
    active_pointer.write_text(
        str(context.report_dir.resolve()) + "\n", encoding="utf-8"
    )
    write_task_authority_baselines(context.report_dir, context.report_root)
    runtime = TaskStartRuntime(
        roles=roles, created_files=created_files, active_pointer=active_pointer
    )
    _, _, start_declaration = emit_task_start_output(
        args=args,
        config=config,
        context=context,
        workspace_root=workspace_root,
        preflight=preflight,
        runtime=runtime,
    )
    record_task_start_monitoring(context, roles, start_declaration, preflight.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
