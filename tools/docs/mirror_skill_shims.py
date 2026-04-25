#!/usr/bin/env python3
# @dependency-start
# @dependency-end

# Dependency Files:
# - vendor/agent-canon/agents/skills/catalog.yaml
# - vendor/agent-canon/.agents/skills/agent-orchestration/SKILL.md
"""
Mirror skill shim directories from one discovery path to another.

The default use case is syncing `.agents/skills/` into `.claude/skills/`
after shared skill shims change.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

FRONTMATTER_SCAN_LINES = 12


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Mirror skill shim directories between runtime discovery paths."
    )
    parser.add_argument(
        "--source",
        default=".agents/skills",
        help="source skill directory (default: .agents/skills)",
    )
    parser.add_argument(
        "--target",
        default=".claude/skills",
        help="target skill directory (default: .claude/skills)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report pending changes and exit non-zero if the target is stale",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="remove target skill directories and files that are absent in the source",
    )
    return parser.parse_args()


def iter_skill_dirs(root: Path) -> list[Path]:
    """Return skill directories below one root."""
    return sorted(
        path for path in root.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
    )


def validate_skill_frontmatter(root: Path) -> list[str]:
    """Return findings for skill shims without valid YAML frontmatter."""
    findings: list[str] = []
    for skill_dir in iter_skill_dirs(root):
        skill_path = skill_dir / "SKILL.md"
        lines = skill_path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            findings.append(f"{skill_path}: missing YAML frontmatter delimited by ---")
            continue
        closing_index = None
        for index, line in enumerate(lines[1:FRONTMATTER_SCAN_LINES], start=1):
            if line.strip() == "---":
                closing_index = index
                break
        if closing_index is None:
            findings.append(f"{skill_path}: missing YAML frontmatter delimited by ---")
            continue
        frontmatter = "\n".join(lines[1:closing_index])
        if "name:" not in frontmatter or "description:" not in frontmatter:
            findings.append(f"{skill_path}: frontmatter must include name and description")
    return findings


def iter_files(root: Path) -> list[Path]:
    """Return all files below one root."""
    return sorted(path for path in root.rglob("*") if path.is_file())


def files_match(source: Path, target: Path) -> bool:
    """Return whether source and target file contents match."""
    return target.is_file() and source.read_bytes() == target.read_bytes()


def plan_sync(source_root: Path, target_root: Path, prune: bool) -> list[str]:
    """Return sync actions needed to make target match source."""
    actions: list[str] = []
    source_skills = {path.name: path for path in iter_skill_dirs(source_root)}
    target_skills = (
        {path.name: path for path in iter_skill_dirs(target_root)}
        if target_root.exists()
        else {}
    )

    for skill_name, source_skill in source_skills.items():
        target_skill = target_root / skill_name
        for source_file in iter_files(source_skill):
            relative = source_file.relative_to(source_skill)
            target_file = target_skill / relative
            if not target_file.exists():
                actions.append(f"create {target_file}")
                continue
            if not files_match(source_file, target_file):
                actions.append(f"update {target_file}")

        if prune and target_skill.exists():
            source_relatives = {
                source_file.relative_to(source_skill) for source_file in iter_files(source_skill)
            }
            for target_file in iter_files(target_skill):
                relative = target_file.relative_to(target_skill)
                if relative not in source_relatives:
                    actions.append(f"remove {target_file}")

    if prune:
        for skill_name, target_skill in target_skills.items():
            if skill_name not in source_skills:
                actions.append(f"remove {target_skill}")

    return actions


def sync_skill(source_skill: Path, target_skill: Path, prune: bool) -> None:
    """Copy one source skill into one target directory."""
    source_files = iter_files(source_skill)
    source_relatives = set()

    for source_file in source_files:
        relative = source_file.relative_to(source_skill)
        source_relatives.add(relative)
        target_file = target_skill / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        if not files_match(source_file, target_file):
            shutil.copy2(source_file, target_file)

    if not prune or not target_skill.exists():
        return

    stale_files = [
        target_file
        for target_file in iter_files(target_skill)
        if target_file.relative_to(target_skill) not in source_relatives
    ]
    for stale_file in stale_files:
        stale_file.unlink()

    empty_dirs = sorted(
        (path for path in target_skill.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for empty_dir in empty_dirs:
        if not any(empty_dir.iterdir()):
            empty_dir.rmdir()


def apply_sync(source_root: Path, target_root: Path, prune: bool) -> None:
    """Apply the planned skill mirror synchronization."""
    target_root.mkdir(parents=True, exist_ok=True)
    source_skills = {path.name: path for path in iter_skill_dirs(source_root)}
    target_skills = {path.name: path for path in iter_skill_dirs(target_root)}

    for skill_name, source_skill in source_skills.items():
        sync_skill(source_skill, target_root / skill_name, prune=prune)

    if not prune:
        return

    for skill_name, target_skill in target_skills.items():
        if skill_name not in source_skills:
            shutil.rmtree(target_skill)


def main() -> int:
    """Run the skill mirror command."""
    args = parse_args()
    source_root = Path(args.source)
    target_root = Path(args.target)

    if not source_root.is_dir():
        print(f"source directory not found: {source_root}", file=sys.stderr)
        return 2
    if source_root.resolve() == target_root.resolve():
        print("source and target must be different directories", file=sys.stderr)
        return 2

    frontmatter_findings = validate_skill_frontmatter(source_root)
    if target_root.exists():
        frontmatter_findings.extend(validate_skill_frontmatter(target_root))
    actions = plan_sync(source_root, target_root, prune=args.prune)

    if args.check:
        if frontmatter_findings:
            for finding in frontmatter_findings:
                print(finding)
            return 1
        if actions:
            for action in actions:
                print(action)
            return 1
        print("skill mirrors are in sync")
        return 0

    apply_sync(source_root, target_root, prune=args.prune)

    if actions:
        for action in actions:
            print(action)
    else:
        print("skill mirrors are already in sync")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
