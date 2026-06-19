#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run-local work log automation.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md runtime preflight logging rules
# upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md run bundle artifact placement contract
# downstream implementation ../../tests/agent_tools/test_work_log.py verifies work log behavior
# @dependency-end
"""Append one timestamped run-local work-log entry."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from agent_team import resolve_report_root
from task_authority import ACTIVE_RUN_POINTER


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one run-local work-log entry.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root containing reports/agents/.active_run.",
    )
    parser.add_argument("--report-dir", help="Explicit run bundle directory to update.")
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional directory that contains per-run report folders. Defaults to "
            "<workspace-root>/reports/agents."
        ),
    )
    parser.add_argument(
        "--kind",
        default="work",
        help="Short event kind, for example kickoff/test/edit/review.",
    )
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


def _resolve_active_report_dir(workspace_root: Path, report_root: Path) -> Path | None:
    """Resolve the current run bundle from reports/agents/.active_run."""
    pointer = workspace_root / ACTIVE_RUN_POINTER
    if not pointer.is_file():
        return None
    active = pointer.read_text(encoding="utf-8").strip()
    if not active:
        return None
    active_path = Path(active)
    if active_path.is_absolute():
        return active_path
    if active_path.as_posix().startswith("reports/agents/"):
        return workspace_root / active_path
    return report_root / active_path


def _log_run_work_entry(report_dir: Path, entry: str) -> Path:
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
    report_root = resolve_report_root(args.report_root, workspace_root)

    if args.report_dir and args.run_id:
        raise SystemExit("Provide at most one of --report-dir or --run-id.")
    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    elif args.run_id:
        report_dir = report_root / str(args.run_id)
    else:
        report_dir = _resolve_active_report_dir(workspace_root, report_root)

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
        if report_dir is None:
            raise SystemExit(
                "Missing clause ids are only allowed when --report-dir or --run-id "
                "or reports/agents/.active_run resolves a run bundle."
            )

    if report_dir is None:
        raise SystemExit(
            "No run bundle resolved. Provide --report-dir / --run-id or create reports/agents/.active_run."
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
    work_log_path = _log_run_work_entry(report_dir, entry)
    print(f"WORK_LOG={work_log_path}")
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
