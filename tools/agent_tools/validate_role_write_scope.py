#!/usr/bin/env python3
"""Validate changed files against one agent role's write scope."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_team import (
    load_directory_snapshot,
    load_team_config,
    validate_role_write_scope,
    write_directory_snapshot,
    write_workspace_change_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Validate that changed files match the write policy for one agent role."
    )
    parser.add_argument("--role", help="Role id to validate.")
    parser.add_argument(
        "--report-dir",
        required=True,
        help="Run report directory such as reports/agents/<run-id>.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root whose git changes should be inspected.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Optional file path to validate. Repeat to pass explicit files instead of git state.",
    )
    parser.add_argument(
        "--report-snapshot-in",
        help="Json snapshot of the report dir captured before the current role ran.",
    )
    parser.add_argument(
        "--report-snapshot-out",
        help="Write the current report-dir snapshot to this json file. When used alone, exits after writing.",
    )
    parser.add_argument(
        "--workspace-snapshot-in",
        help="Json snapshot of workspace git-visible changes captured before the current role ran.",
    )
    parser.add_argument(
        "--workspace-snapshot-out",
        help="Write the current workspace git-visible change snapshot to this json file.",
    )
    return parser


def main() -> int:
    """Run the validation command."""
    args = build_parser().parse_args()
    report_dir = Path(args.report_dir).resolve()
    workspace_root = Path(args.workspace_root).resolve()
    if args.report_snapshot_out is not None:
        snapshot_path = Path(args.report_snapshot_out).resolve()
        write_directory_snapshot(report_dir, snapshot_path)
        print(f"REPORT_SNAPSHOT={snapshot_path}")
    if args.workspace_snapshot_out is not None:
        snapshot_path = Path(args.workspace_snapshot_out).resolve()
        ignored_snapshot_paths = (snapshot_path,)
        if args.report_snapshot_out is not None:
            ignored_snapshot_paths += (Path(args.report_snapshot_out).resolve(),)
        write_workspace_change_snapshot(
            workspace_root,
            snapshot_path,
            ignored_roots=(report_dir,),
            ignored_paths=ignored_snapshot_paths,
        )
        print(f"WORKSPACE_SNAPSHOT={snapshot_path}")
    if (
        args.role is None
        and not args.file
        and args.report_snapshot_in is None
        and args.workspace_snapshot_in is None
    ):
        return 0

    if args.role is None:
        raise SystemExit("--role is required unless the command is only capturing snapshot files.")

    config = load_team_config()
    explicit_files = tuple((workspace_root / path).resolve() for path in args.file)
    report_snapshot = None
    workspace_snapshot = None
    ignored_paths: tuple[Path, ...] = ()
    if args.report_snapshot_in is not None:
        snapshot_path = Path(args.report_snapshot_in).resolve()
        report_snapshot = load_directory_snapshot(snapshot_path)
        ignored_paths += (snapshot_path,)
    if args.workspace_snapshot_in is not None:
        snapshot_path = Path(args.workspace_snapshot_in).resolve()
        workspace_snapshot = load_directory_snapshot(snapshot_path)
        ignored_paths += (snapshot_path,)
    scope, violations = validate_role_write_scope(
        config=config,
        role_name=args.role,
        report_dir=report_dir,
        workspace_root=workspace_root,
        files=explicit_files or None,
        report_dir_snapshot=report_snapshot,
        workspace_snapshot=workspace_snapshot,
        ignored_paths=ignored_paths,
    )

    print(f"ROLE={scope.role_id}")
    print(f"MODE={scope.mode}")
    if scope.worktree_scope_file is not None:
        print(f"WORKTREE_SCOPE_FILE={scope.worktree_scope_file}")
    if scope.unresolved_reason is not None:
        print(f"UNRESOLVED_REASON={scope.unresolved_reason}")
    for path in scope.allowed_files:
        print(f"ALLOWED_FILE={path}")
    for path in scope.allowed_directories:
        print(f"ALLOWED_DIRECTORY={path}")
    if not violations:
        print("WRITE_SCOPE=pass")
        return 0
    for path in violations:
        print(f"VIOLATION={path}")
    print("WRITE_SCOPE=fail")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
