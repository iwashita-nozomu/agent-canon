#!/usr/bin/env python3
# @dependency-start
# responsibility Checks merge structure CI readiness.
# upstream design ../README.md shared automation index
# @dependency-end

"""Check that branch-side structural path changes survived integration."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


STRUCTURAL_PREFIXES = ("A", "D", "R", "T")


@dataclass(frozen=True)
class PathState:
    """One git tree state for a path."""

    kind: str
    oid: str | None = None


def run_git(repo_root: Path, *args: str) -> str:
    """Run one git command and return stripped stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Confirm that structural changes from a source branch "
            "(add/delete/rename/type change) are preserved in an integration commit."
        )
    )
    parser.add_argument("--source", required=True, help="Source branch or commit being integrated.")
    parser.add_argument("--target", default="main", help="Target branch used to compute merge-base.")
    parser.add_argument(
        "--compare-commit",
        default="HEAD",
        help="Integration commit to inspect. Defaults to HEAD.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    return parser.parse_args()


def structural_paths(repo_root: Path, merge_base: str, source: str) -> set[str]:
    """Return all paths involved in structural changes on the source branch."""
    output = run_git(repo_root, "diff", "--name-status", "--find-renames", merge_base, source)
    paths: set[str] = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if not status or status[0] not in STRUCTURAL_PREFIXES:
            continue
        if status[0] == "R":
            if len(parts) >= 3:
                paths.add(parts[1])
                paths.add(parts[2])
            continue
        if len(parts) >= 2:
            paths.add(parts[1])
    return paths


def path_state(repo_root: Path, rev: str, path: str) -> PathState:
    """Return git tree state for one path at one revision."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", rev, "--", path],
        check=True,
        capture_output=True,
        text=True,
    )
    line = result.stdout.strip()
    if not line:
        return PathState("absent")

    before_path, _, _ = line.partition("\t")
    mode, obj_type, oid = before_path.split(" ", 2)
    if mode == "120000":
        return PathState("symlink", oid)
    return PathState(obj_type, oid)


def main() -> int:
    """Run the checker."""
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    merge_base = run_git(repo_root, "merge-base", args.target, args.source)
    paths = sorted(structural_paths(repo_root, merge_base, args.source))

    print(f"REPO_ROOT={repo_root}")
    print(f"TARGET={args.target}")
    print(f"SOURCE={args.source}")
    print(f"COMPARE_COMMIT={args.compare_commit}")
    print(f"MERGE_BASE={merge_base}")

    if not paths:
        print("STRUCTURAL_PATH_COUNT=0")
        print("MERGE_STRUCTURE_CHECK=pass (no structural changes on source branch)")
        return 0

    mismatches: list[str] = []
    print(f"STRUCTURAL_PATH_COUNT={len(paths)}")
    for path in paths:
        source_state = path_state(repo_root, args.source, path)
        compare_state = path_state(repo_root, args.compare_commit, path)
        if source_state != compare_state:
            mismatches.append(
                f"{path}: source={source_state.kind}:{source_state.oid} "
                f"compare={compare_state.kind}:{compare_state.oid}"
            )

    if mismatches:
        print("MERGE_STRUCTURE_CHECK=fail")
        print("MISMATCHES:")
        for line in mismatches:
            print(f"- {line}")
        return 1

    print("MERGE_STRUCTURE_CHECK=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
