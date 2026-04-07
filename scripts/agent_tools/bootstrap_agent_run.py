#!/usr/bin/env python3
"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent_team import (
    DEFAULT_REPORT_ROOT,
    create_run_bundle,
    load_team_config,
    make_run_id,
    select_roles,
    specialist_role_ids,
)


def build_parser(specialist_choices: tuple[str, ...]) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Create a standard reports/agents/<run-id>/ bundle for one agent-team run."
    )
    parser.add_argument("--task", required=True, help="Short task description for the run.")
    parser.add_argument("--owner", required=True, help="Human or agent responsible for the run.")
    parser.add_argument("--run-id", help="Optional explicit run id. Defaults to a timestamped slug.")
    parser.add_argument(
        "--enable",
        action="append",
        choices=specialist_choices,
        default=[],
        help="Enable a specialist role. Repeat the flag to enable multiple roles.",
    )
    parser.add_argument(
        "--full-team",
        action="store_true",
        help="Enable every specialist role for this run.",
    )
    parser.add_argument(
        "--report-root",
        default=str(DEFAULT_REPORT_ROOT),
        help="Directory that will contain per-run report folders.",
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
    args = build_parser(specialist_role_ids(config)).parse_args()
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    report_root = Path(args.report_root).resolve()
    workspace_root = Path(args.workspace_root).resolve()
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    roles = select_roles(config, args.enable, args.full_team)
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
    if args.dry_run:
        print("DRY_RUN=1")
    else:
        print(f"ACTIVE_ROLES={','.join(role.id for role in roles)}")
        print(f"CREATED_FILES={','.join(created_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
