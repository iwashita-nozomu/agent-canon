#!/usr/bin/env python3
"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent_team import (
    auto_language_specialists,
    create_run_bundle,
    default_specialists_for_task,
    load_team_config,
    load_task_catalog,
    make_run_id,
    select_roles,
    specialist_role_ids,
    task_ids,
    TeamConfig,
    resolve_report_root,
)


def codex_agents_for_role(config: TeamConfig, role_id: str) -> tuple[str, ...]:
    """Return Codex subagent candidates for one permanent role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role.id == role_id:
            return role.codex_agents
    return ()


def build_parser(
    specialist_choices: tuple[str, ...],
    task_choices: tuple[str, ...],
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard <workspace-root>/reports/agents/<run-id>/ bundle for one "
            "agent-team run."
        )
    )
    parser.add_argument("--task", required=True, help="Short task description for the run.")
    parser.add_argument("--owner", required=True, help="Human or agent responsible for the run.")
    parser.add_argument(
        "--task-id",
        choices=task_choices,
        help="Optional task catalog id. Expands default specialists and review packs for that task.",
    )
    parser.add_argument("--run-id", help="Optional explicit run id. Defaults to a timestamped slug.")
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
        help="Optional changed path hint. Repeat to drive automatic language-specific reviewer selection.",
    )
    parser.add_argument(
        "--no-auto-language-reviewers",
        action="store_true",
        help="Disable automatic language-specific reviewer selection from changed paths or git status.",
    )
    parser.add_argument(
        "--full-team",
        action="store_true",
        help="Enable every specialist role for this run.",
    )
    parser.add_argument(
        "--no-default-review-packs",
        action="store_true",
        help="When --task-id is set, skip review packs whose default_for_tasks contains that task.",
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
    return parser


def main() -> int:
    """Run the bootstrap command."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    args = build_parser(specialist_role_ids(config), task_ids(catalog)).parse_args()
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    workspace_root = Path(args.workspace_root).resolve()
    report_root = resolve_report_root(args.report_root, workspace_root)
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    enabled_specialists = list(args.enable)
    task_default_specialists: tuple[str, ...] = ()
    auto_specialists: tuple[str, ...] = ()
    if args.task_id is not None:
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
        )

    print(f"RUN_ID={run_id}")
    print(f"REPORT_DIR={report_dir}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
        print(f"TASK_DEFAULT_SPECIALISTS={','.join(task_default_specialists)}")
    if not args.no_auto_language_reviewers:
        print(f"AUTO_SPECIALISTS={','.join(auto_specialists)}")
    print(f"IMPLEMENTATION_CODEX_AGENTS={','.join(codex_agents_for_role(config, 'implementer'))}")
    if args.dry_run:
        print("DRY_RUN=1")
    else:
        print(f"ACTIVE_ROLES={','.join(role.id for role in roles)}")
        print(f"CREATED_FILES={','.join(created_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
