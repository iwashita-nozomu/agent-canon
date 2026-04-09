#!/usr/bin/env python3
"""Append one timestamped action-log entry for the current worktree."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from worktree_start import append_action_log_entry, resolve_action_log_path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one action-log entry.")
    parser.add_argument("--workspace-root", default=".", help="Workspace root that owns WORKTREE_SCOPE.md.")
    parser.add_argument("--kind", default="work", help="Short event kind, for example kickoff/test/edit/review.")
    parser.add_argument("--message", required=True, help="What happened in this step.")
    parser.add_argument("--next", default="", help="Explicit next step.")
    parser.add_argument(
        "--request-clause-id",
        action="append",
        default=[],
        help="User request clause id covered by this log entry. Repeat to add multiple ids.",
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        help="Optional path or artifact reference. Repeat to add multiple refs.",
    )
    return parser


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    scope_path = workspace_root / "WORKTREE_SCOPE.md"
    if not scope_path.is_file():
        raise SystemExit(f"WORKTREE_SCOPE.md not found: {scope_path}")

    action_log_path = resolve_action_log_path(workspace_root, scope_path)
    if action_log_path is None:
        raise SystemExit("Action log path is unresolved in WORKTREE_SCOPE.md")
    if not args.request_clause_id:
        raise SystemExit("At least one --request-clause-id is required.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    clause_suffix = " | request_clause_ids: " + ",".join(args.request_clause_id)
    ref_suffix = ""
    if args.ref:
        ref_suffix = " | refs: " + ", ".join(args.ref)
    next_suffix = ""
    if args.next:
        next_suffix = f" | next: {args.next}"
    entry = f"`{timestamp} | {args.kind} | {args.message}{clause_suffix}{ref_suffix}{next_suffix}`"
    append_action_log_entry(action_log_path, entry)
    print(f"ACTION_LOG={action_log_path}")
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
