#!/usr/bin/env python3
"""Sync branch/worktree metadata into the experiment registry."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from registry_lib import find_topic
from registry_lib import load_registry
from registry_lib import write_registry


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Sync active_branch / active_worktree / scope_file into experiments/registry.toml."
    )
    parser.add_argument("--topic", required=True, help="Experiment topic to update.")
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--registry",
        help="Optional registry path. Defaults to <repo-root>/experiments/registry.toml.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root for active_worktree and default scope file resolution.",
    )
    parser.add_argument(
        "--branch",
        help="Explicit branch name. Defaults to the current branch for the workspace root.",
    )
    parser.add_argument(
        "--scope-file",
        help="Optional scope file path. Defaults to <workspace-root>/WORKTREE_SCOPE.md when present.",
    )
    parser.add_argument(
        "--branch-note",
        help="Optional branch note path to record.",
    )
    parser.add_argument(
        "--primary-note",
        help="Optional primary note path to record.",
    )
    parser.add_argument(
        "--clear-context",
        action="store_true",
        help="Remove active_branch, active_worktree, scope_file, and branch_note for this topic.",
    )
    return parser


def current_branch(workspace_root: Path) -> str:
    """Return the current branch for one workspace."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "rev-parse", "--abbrev-ref", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"failed to resolve current branch for {workspace_root}")
    branch = result.stdout.strip()
    if not branch:
        raise ValueError(f"failed to resolve current branch for {workspace_root}")
    return branch


def relpath_or_none(repo_root: Path, path: Path | None) -> str | None:
    """Return one path relative to the repo root when possible."""
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(repo_root))
    except ValueError:
        return str(path.resolve())


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else repo_root / "experiments" / "registry.toml"
    workspace_root = Path(args.workspace_root).resolve()
    registry = load_registry(registry_path)
    topic_entry = find_topic(registry, args.topic)
    if topic_entry is None:
        raise SystemExit(f"topic {args.topic!r} is missing from {registry_path}")

    if args.clear_context:
        for key in ("active_branch", "active_worktree", "scope_file", "branch_note"):
            topic_entry.pop(key, None)
    else:
        branch = args.branch or current_branch(workspace_root)
        topic_entry["active_branch"] = branch
        topic_entry["active_worktree"] = relpath_or_none(repo_root, workspace_root)
        scope_file = Path(args.scope_file).resolve() if args.scope_file else workspace_root / "WORKTREE_SCOPE.md"
        if scope_file.exists():
            topic_entry["scope_file"] = relpath_or_none(repo_root, scope_file)
        else:
            topic_entry.pop("scope_file", None)
        if args.branch_note:
            topic_entry["branch_note"] = args.branch_note
    if args.primary_note:
        topic_entry["primary_note"] = args.primary_note

    write_registry(registry_path, registry)
    print(f"registry_path={registry_path}")
    print(f"topic_name={args.topic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
