#!/usr/bin/env python3
# @dependency-start
# responsibility Bootstraps agent run artifacts for agent workflows.
# upstream design ../README.md shared automation index
# @dependency-end

"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent_canon_preflight import project_root_from_script, run_agent_canon_preflight
from agent_team import (
    TeamConfig,
    auto_language_specialists,
    codex_runtime_max_threads,
    create_run_bundle,
    default_specialists_for_task,
    load_task_catalog,
    load_team_config,
    make_run_id,
    resolve_cross_cutting_document_packet,
    resolve_report_root,
    resolve_role_document_packet,
    resolve_task_spec,
    resolve_workflow_family,
    select_roles,
    specialist_role_ids,
    task_ids,
    workflow_spawn_budget,
)
from workflow_monitor import append_monitoring


def suggested_skills(
    task_id: str | None,
    workflow_family_id: str | None,
) -> tuple[str, ...]:
    """Return the public skills that should be read before work starts."""
    selected = ["$agent-orchestration", "$codex-task-workflow", "$subagent-bootstrap"]
    if workflow_family_id == "research_driven_change":
        selected.append("$research-workflow")
    elif workflow_family_id == "platform_and_environment":
        selected.append("$environment-maintenance")
    elif workflow_family_id == "comprehensive_development":
        selected.append("$comprehensive-development")
    elif workflow_family_id == "adaptive_improvement_loop":
        selected.append("$adaptive-improvement-loop")
    if task_id == "T6":
        selected.append("$behavior-preserving-refactor")
    if task_id == "T10":
        selected.append("$paper-writing")
    return tuple(dict.fromkeys(selected))


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
    specialist_choices: tuple[str, ...],
    task_choices: tuple[str, ...],
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard <workspace-root>/reports/agents/<run-id>/ "
            "bundle for one agent-team run."
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
        choices=specialist_choices,
        default=[],
        help="Enable a specialist role. Repeat the flag to enable multiple roles.",
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
            "Optional directory that will contain per-run report folders. Defaults to "
            "<workspace-root>/reports/agents."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve WORKTREE_SCOPE.md and write permissions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the run id and paths without writing files.",
    )
    parser.add_argument(
        "--skip-agent-canon-preflight",
        action="store_true",
        help="Skip the automatic make agent-canon-ensure-latest preflight.",
    )
    return parser


def main() -> int:
    """Run the bootstrap command."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    args = build_parser(specialist_role_ids(config), task_ids(catalog)).parse_args()
    project_root = project_root_from_script(Path(__file__))
    try:
        preflight = run_agent_canon_preflight(
            project_root,
            skip=args.skip_agent_canon_preflight,
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 1
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    workspace_root = Path(args.workspace_root).resolve()
    report_root = resolve_report_root(args.report_root, workspace_root)
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    enabled_specialists = list(args.enable)
    task_default_specialists: tuple[str, ...] = ()
    auto_specialists: tuple[str, ...] = ()
    workflow_family_id: str | None = None
    workflow_family_name: str | None = None
    workflow_active_spawn_budget: int | None = None
    workflow_max_write_subagents: int | None = None
    if args.task_id is not None:
        task_spec = resolve_task_spec(catalog, args.task_id)
        workflow_family_id = str(task_spec["family"])
        workflow_family = resolve_workflow_family(catalog, workflow_family_id)
        workflow_family_name = str(workflow_family["name"])
        (
            workflow_active_spawn_budget,
            workflow_max_write_subagents,
        ) = workflow_spawn_budget(
            catalog,
            workflow_family_id,
        )
        task_default_specialists = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=args.task_id,
            include_default_review_packs=not args.no_default_review_packs,
        )
        for role_id in task_default_specialists:
            if role_id not in enabled_specialists:
                enabled_specialists.append(role_id)
    if not args.no_auto_language_reviewers:
        auto_specialists = auto_language_specialists(
            workspace_root=workspace_root,
            changed_paths=tuple(args.changed_path),
        )
        for role_id in auto_specialists:
            if role_id not in enabled_specialists:
                enabled_specialists.append(role_id)
    roles = select_roles(config, enabled_specialists, args.full_team)
    created_files: tuple[str, ...] = ()

    if not args.dry_run:
        created_files = create_run_bundle(
            config=config,
            report_dir=report_dir,
            run_id=run_id,
            task=args.task,
            owner=args.owner,
            created_at_iso=created_at_iso,
            roles=roles,
            workspace_root=workspace_root,
            workflow_family_id=workflow_family_id,
        )

    print("AGENT_CANON_PREFLIGHT_COMMAND=make agent-canon-ensure-latest")
    print(f"AGENT_CANON_PREFLIGHT_STATUS={preflight.status}")
    print(f"AGENT_CANON_PREFLIGHT_REASON={preflight.reason}")
    print(f"AGENT_CANON_PREFLIGHT_NEXT={preflight.next_step}")
    print(f"RUN_ID={run_id}")
    print(f"REPORT_DIR={report_dir}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    print(f"RUNTIME_MAX_THREADS={codex_runtime_max_threads()}")
    selected_skills = suggested_skills(args.task_id, workflow_family_id)
    review_roles = tuple(
        role.id
        for role in roles
        if role.id.endswith("_reviewer")
        or role.id
        in {
            "reviewer",
            "verifier",
            "auditor",
            "docs_workflow_steward",
            "critical_guardian",
        }
    )
    print(f"SUGGESTED_SKILLS={','.join(selected_skills)}")
    print(
        "START_DECLARATION="
        f"workflow={workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(selected_skills)}, "
        f"review={','.join(review_roles) or '-'}"
    )
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
        print("WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet")
        print(f"WORKFLOW_ACTIVE_SPAWN_BUDGET={workflow_active_spawn_budget}")
        print(f"WORKFLOW_MAX_WRITE_SUBAGENTS={workflow_max_write_subagents}")
        print(f"TASK_DEFAULT_SPECIALISTS={','.join(task_default_specialists)}")
    if not args.no_auto_language_reviewers:
        print(f"AUTO_SPECIALISTS={','.join(auto_specialists)}")
    print(
        "IMPLEMENTATION_CODEX_AGENTS="
        f"{','.join(codex_agents_for_role(config, 'implementer'))}"
    )
    print(
        "CROSS_CUTTING_DOCUMENT_PACKET="
        f"{cross_cutting_document_packet_output(workspace_root)}"
    )
    print(
        "DESIGN_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'designer', report_dir, workspace_root)}"
    )
    print(
        "IMPLEMENTATION_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'implementer', report_dir, workspace_root)}"
    )
    if args.dry_run:
        print("DRY_RUN=1")
    else:
        append_monitoring(
            report_dir,
            signals=[
                (
                    f"workflow={workflow_family_name or 'Unspecified'}, "
                    f"skills={','.join(selected_skills)}, "
                    f"review={','.join(review_roles) or '-'}"
                ),
                (
                    "stage owner routing active_roles="
                    f"{','.join(role.id for role in roles)}"
                ),
                f"agent_canon_preflight={preflight.status}",
                (
                    "web_research_not_required: bootstrap does not decide "
                    "external research"
                ),
            ],
            interventions=[
                f"created run bundle and workflow_monitoring.md at {report_dir}",
            ],
        )
        print(f"ACTIVE_ROLES={','.join(role.id for role in roles)}")
        print(f"CREATED_FILES={','.join(created_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
