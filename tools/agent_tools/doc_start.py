#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Start one document-writing run with machine-generated writing workflow and review hints."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent_team import (
    create_run_bundle,
    load_team_config,
    make_run_id,
    resolve_report_root,
    select_roles,
    specialist_role_ids,
)


DOC_KIND_MAP = {
    "long-form": {
        "workflow_family_id": "scoped_change",
        "workflow_family": "Scoped Change",
        "skills": (
            "$agent-orchestration",
            "$codex-task-workflow",
            "$subagent-bootstrap",
            "$long-form-writing",
        ),
        "enable": (),
    },
    "academic": {
        "workflow_family_id": "research_driven_change",
        "workflow_family": "Research-Driven Change",
        "skills": (
            "$agent-orchestration",
            "$codex-task-workflow",
            "$subagent-bootstrap",
            "$academic-writing",
        ),
        "enable": (
            "notation_definition_reviewer",
            "logic_gap_reviewer",
        ),
    },
    "paper": {
        "workflow_family_id": "research_driven_change",
        "workflow_family": "Research-Driven Change",
        "skills": (
            "$agent-orchestration",
            "$codex-task-workflow",
            "$subagent-bootstrap",
            "$paper-writing",
        ),
        "enable": (
            "citation_evidence_reviewer",
            "notation_definition_reviewer",
            "logic_gap_reviewer",
            "report_reviewer",
        ),
    },
}


def build_parser(specialist_choices: tuple[str, ...]) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard run bundle for long-form, academic, or paper writing and emit "
            "machine-generated workflow/skill/review declarations."
        )
    )
    parser.add_argument("--task", required=True, help="Short writing task description for the run.")
    parser.add_argument("--owner", required=True, help="Human or agent responsible for the run.")
    parser.add_argument(
        "--kind",
        required=True,
        choices=tuple(DOC_KIND_MAP),
        help="Document kind to bootstrap.",
    )
    parser.add_argument("--run-id", help="Optional explicit run id. Defaults to a timestamped slug.")
    parser.add_argument(
        "--enable",
        action="append",
        choices=specialist_choices,
        default=[],
        help="Enable an extra specialist role. Repeat the flag to enable multiple roles.",
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
    """Run the doc-start command."""
    config = load_team_config()
    args = build_parser(specialist_role_ids(config)).parse_args()
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    workspace_root = Path(args.workspace_root).resolve()
    report_root = resolve_report_root(args.report_root, workspace_root)
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id

    kind_spec = DOC_KIND_MAP[args.kind]
    enabled_specialists = list(kind_spec["enable"])
    for role_id in args.enable:
        if role_id not in enabled_specialists:
            enabled_specialists.append(role_id)

    roles = select_roles(config, enabled_specialists, full_team=False)
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
            workflow_family_id=str(kind_spec["workflow_family_id"]),
        )

    review_roles = tuple(
        role.id
        for role in roles
        if role.id.endswith("_reviewer")
        or role.id in {"reviewer", "verifier", "auditor", "docs_workflow_steward"}
    )
    start_declaration = (
        f"workflow={kind_spec['workflow_family']}, "
        f"skills={','.join(kind_spec['skills'])}, "
        f"review={','.join(review_roles) or '-'}"
    )

    print(f"RUN_ID={run_id}")
    print(f"REPORT_DIR={report_dir}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    print(f"DOC_KIND={args.kind}")
    print(f"WORKFLOW_FAMILY_NAME={kind_spec['workflow_family']}")
    print("WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet")
    print(f"RECOMMENDED_SPECIALISTS={','.join(kind_spec['enable'])}")
    print(f"SUGGESTED_SKILLS={','.join(kind_spec['skills'])}")
    print(f"START_DECLARATION={start_declaration}")
    if args.dry_run:
        print("DRY_RUN=1")
    else:
        print(f"ACTIVE_ROLES={','.join(role.id for role in roles)}")
        print(f"CREATED_FILES={','.join(created_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
