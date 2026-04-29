#!/usr/bin/env python3
# @dependency-start
# responsibility Bootstraps worktree notes artifacts for agent workflows.
# upstream design ../README.md shared automation index
# @dependency-end

"""Create concrete worktree log paths and fill WORKTREE_SCOPE.md placeholders."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap worktree notes and fill concrete action-log and branch-summary paths "
            "into WORKTREE_SCOPE.md."
        )
    )
    parser.add_argument("--repo-root", required=True, help="Repository root.")
    parser.add_argument("--workspace-root", required=True, help="Target worktree root.")
    parser.add_argument("--branch", required=True, help="Branch name for the worktree.")
    parser.add_argument(
        "--purpose",
        default="TODO: refine purpose",
        help="Initial purpose line for WORKTREE_SCOPE.md and the worktree log.",
    )
    parser.add_argument(
        "--owner",
        default="codex-or-human",
        help="Initial owner line for WORKTREE_SCOPE.md.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite concrete scope fields as well as placeholders.",
    )
    return parser


def topic_slug(branch: str) -> str:
    """Return a stable topic slug from one branch name."""
    slug = branch.strip().replace("/", "-")
    slug = re.sub(r"-(20\d{2}[01]\d[0-3]\d)$", "", slug)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "work"


def replace_scope_line(
    lines: list[str],
    prefix: str,
    replacement: str,
    *,
    force: bool,
) -> list[str]:
    """Replace one bullet line when empty, placeholder, or forced."""
    updated: list[str] = []
    for line in lines:
        if not line.startswith(prefix):
            updated.append(line)
            continue
        current_value = line[len(prefix) :].strip()
        if force or not current_value or "<" in current_value or "TODO" in current_value:
            updated.append(f"{prefix} {replacement}")
        else:
            updated.append(line)
    return updated


def fill_scope_file(
    scope_path: Path,
    *,
    branch: str,
    workspace_root: Path,
    action_log_rel: str,
    branch_summary_rel: str,
    purpose: str,
    owner: str,
    force: bool,
) -> None:
    """Fill core scope placeholders with concrete values."""
    if not scope_path.is_file():
        return

    today = datetime.now().strftime("%Y-%m-%d")
    worktree_rel = workspace_root.as_posix()
    lines = scope_path.read_text(encoding="utf-8").splitlines()
    replacements = (
        ("- Branch:", f"`{branch}`"),
        ("- Worktree path:", f"`{worktree_rel}`"),
        ("- Purpose:", purpose),
        ("- Owner or agent:", owner),
        ("- Scope refreshed at:", today),
        ("- Action log path:", f"`{action_log_rel}`"),
        ("- Branch summary path:", f"`{branch_summary_rel}`"),
        ("- Kickoff checks completed:", "`pending`"),
        ("- Next step after kickoff:", "refresh references and append the first execution log entry"),
        ("- `notes/worktrees/worktree_<topic>_YYYY-MM-DD.md`", f"`{action_log_rel}`"),
        ("- `notes/branches/<branch_topic>.md`", f"`{branch_summary_rel}`"),
    )
    for prefix, replacement in replacements:
        lines = replace_scope_line(lines, prefix, replacement, force=force)
    scope_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_worktree_log(path: Path, *, branch: str, workspace_root: Path, purpose: str) -> None:
    """Create the worktree log from the template when missing."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    title = topic_slug(branch).replace("-", " ").strip().title() or "Worktree Note"
    today = datetime.now().strftime("%Y-%m-%d")
    template = "\n".join(
        [
            f"# {title}",
            "",
            "## Summary",
            "",
            f"- Branch: `{branch}`",
            f"- Worktree path: `{workspace_root}`",
            f"- Purpose: {purpose}",
            "- Current state: kickoff",
            "- Scope file: `WORKTREE_SCOPE.md`",
            f"- Branch summary path: `notes/branches/{topic_slug(branch)}.md`",
            f"- Main carry-over targets: `notes/worktrees/worktree_{topic_slug(branch)}_{today}.md`",
            "",
            "## Kickoff Record",
            "",
            f"- Scope refreshed at: {today}",
            "- Relevant references confirmed:",
            "- Initial checks:",
            "- Next step:",
            "",
            "## Action Log",
            "",
            "- `YYYY-MM-DD HH:MM JST | kickoff | branch/path/scope を確認。next: ...`",
            "",
            "## Risks Or Drift",
            "",
            "- Unexpected dirty files:",
            "- Conflict risk:",
            "- Scope drift concern:",
            "",
            "## Observations",
            "",
            "- ",
            "",
            "## Carry-Over Targets",
            "",
            "- ",
            "",
            "## Quick References",
            "",
            "- `documents/...`",
            "- `notes/...`",
            "- `reports/...`",
        ]
    )
    path.write_text(template + "\n", encoding="utf-8")


def ensure_branch_summary(path: Path, *, branch: str, action_log_rel: str, purpose: str) -> None:
    """Create a minimal branch summary when missing."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    title = topic_slug(branch).replace("-", " ").strip().title() or "Branch Note"
    contents = "\n".join(
        [
            f"# {title}",
            "",
            "## Summary",
            "",
            f"- Branch: `{branch}`",
            f"- Purpose: {purpose}",
            "- Status: active",
            "- Retention: keep-while-active",
            f"- Action log: `{action_log_rel}`",
            "",
            "## Read First",
            "",
            f"- `{action_log_rel}`",
            "",
            "## Main Carry-Over Targets",
            "",
            "- `notes/...`",
            "- `documents/...`",
            "- `reports/...`",
        ]
    )
    path.write_text(contents + "\n", encoding="utf-8")


def main() -> int:
    """Run the bootstrap helper."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    workspace_root = Path(args.workspace_root).resolve()
    branch = args.branch.strip()
    slug = topic_slug(branch)
    today = datetime.now().strftime("%Y-%m-%d")

    action_log_rel = f"notes/worktrees/worktree_{slug}_{today}.md"
    branch_summary_rel = f"notes/branches/{slug}.md"
    action_log_path = repo_root / action_log_rel
    branch_summary_path = repo_root / branch_summary_rel
    scope_path = workspace_root / "WORKTREE_SCOPE.md"

    fill_scope_file(
        scope_path,
        branch=branch,
        workspace_root=workspace_root,
        action_log_rel=action_log_rel,
        branch_summary_rel=branch_summary_rel,
        purpose=args.purpose,
        owner=args.owner,
        force=args.force,
    )
    ensure_worktree_log(action_log_path, branch=branch, workspace_root=workspace_root, purpose=args.purpose)
    ensure_branch_summary(branch_summary_path, branch=branch, action_log_rel=action_log_rel, purpose=args.purpose)

    print(f"ACTION_LOG={action_log_rel}")
    print(f"BRANCH_SUMMARY={branch_summary_rel}")
    print(f"SCOPE_FILE={scope_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
