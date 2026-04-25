#!/usr/bin/env python3
# @dependency-start
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md runtime preflight logging rules
# upstream design ../../agents/skills/worktree-start.md worktree action log usage
# upstream design ../../documents/WORKTREE_SCOPE_TEMPLATE.md worktree log contract
# downstream implementation ../../tests/agent_tools/test_work_log.py verifies work log behavior
# @dependency-end
"""Append one timestamped action-log entry for the current worktree."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from agent_team import resolve_report_root
from worktree_start import (
    append_action_log_entry,
    resolve_action_log_path,
    resolve_user_request_contract_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one action-log entry.")
    parser.add_argument("--workspace-root", default=".", help="Workspace root that owns WORKTREE_SCOPE.md.")
    parser.add_argument("--report-dir", help="Explicit run bundle directory to update.")
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional directory that contains per-run report folders. Defaults to "
            "<workspace-root>/reports/agents."
        ),
    )
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
        "--allow-missing-request-clause-id",
        action="store_true",
        help=(
            "Allow a run-bundle-only pre-contract/runtime note without a clause id. "
            "Use only before a clause can reasonably exist."
        ),
    )
    parser.add_argument(
        "--missing-request-clause-reason",
        default="",
        help="Required reason when --allow-missing-request-clause-id is used.",
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        help="Optional path or artifact reference. Repeat to add multiple refs.",
    )
    return parser


def append_run_work_log_entry(report_dir: Path, entry: str) -> Path:
    """Append one entry to the run-bundle work log."""
    report_dir.mkdir(parents=True, exist_ok=True)
    work_log_path = report_dir / "work_log.md"
    if not work_log_path.exists():
        work_log_path.write_text(
            "\n".join(
                [
                    "# Work Log",
                    "",
                    f"- Run ID: {report_dir.name}",
                    "- Task:",
                    "- Owner:",
                    "",
                    "## Purpose",
                    "",
                    "- Chronological run-local work log.",
                    "",
                    "## Entries",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    with work_log_path.open("a", encoding="utf-8") as handle:
        if work_log_path.stat().st_size > 0:
            handle.write("\n")
        handle.write(f"- {entry}\n")
    return work_log_path


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    scope_path = workspace_root / "WORKTREE_SCOPE.md"
    action_log_path: Path | None = None
    inferred_report_dir: Path | None = None
    if scope_path.is_file():
        action_log_path = resolve_action_log_path(workspace_root, scope_path)
        request_contract_path = resolve_user_request_contract_path(workspace_root, scope_path)
        if request_contract_path is not None:
            inferred_report_dir = request_contract_path.parent

    if args.report_dir and args.run_id:
        raise SystemExit("Provide at most one of --report-dir or --run-id.")
    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    elif args.run_id:
        report_dir = resolve_report_root(args.report_root, workspace_root) / str(args.run_id)
    else:
        report_dir = inferred_report_dir

    if not args.request_clause_id:
        if not args.allow_missing_request_clause_id:
            raise SystemExit(
                "At least one --request-clause-id is required unless "
                "--allow-missing-request-clause-id is set."
            )
        if not args.missing_request_clause_reason.strip():
            raise SystemExit(
                "--missing-request-clause-reason is required when clause ids are omitted."
            )
        if action_log_path is not None:
            raise SystemExit(
                "Missing clause ids are only allowed for run-bundle-only logging; "
                "provide --request-clause-id when WORKTREE_SCOPE.md resolves an action log."
            )
        if report_dir is None:
            raise SystemExit(
                "Missing clause ids are only allowed when --report-dir or --run-id resolves a run bundle."
            )

    if action_log_path is None and report_dir is None:
        raise SystemExit(
            "No action log or run bundle resolved. Provide WORKTREE_SCOPE.md with concrete paths, "
            "or pass --report-dir / --run-id."
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    if args.request_clause_id:
        clause_suffix = " | request_clause_ids: " + ",".join(args.request_clause_id)
    else:
        clause_suffix = (
            " | request_clause_ids: unassigned"
            f" | missing_request_clause_reason: {args.missing_request_clause_reason.strip()}"
        )
    ref_suffix = ""
    if args.ref:
        ref_suffix = " | refs: " + ", ".join(args.ref)
    next_suffix = ""
    if args.next:
        next_suffix = f" | next: {args.next}"
    entry = f"`{timestamp} | {args.kind} | {args.message}{clause_suffix}{ref_suffix}{next_suffix}`"
    if action_log_path is not None:
        append_action_log_entry(action_log_path, entry)
    work_log_path: Path | None = None
    if report_dir is not None:
        work_log_path = append_run_work_log_entry(report_dir, entry)
    print(f"ACTION_LOG={action_log_path if action_log_path is not None else '(not-written)'}")
    print(f"WORK_LOG={work_log_path if work_log_path is not None else '(not-written)'}")
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
