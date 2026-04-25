#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Lint WORKTREE_SCOPE.md for concrete, reusable kickoff quality."""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

CORE_REFS = (
    "documents/worktree-lifecycle.md",
    "documents/BRANCH_SCOPE.md",
    "notes/worktrees/README.md",
)
PLACEHOLDER_PATTERNS = (
    r"<[^>]+>",
    r"\bTODO\b",
    r"\.\.\.",
    r"path/to/",
    r"another/path",
    r"documents/<",
    r"notes/<",
    r"reports/agents/<",
    r"worktree_<topic>",
    r"<branch_topic>",
)


@dataclass(frozen=True)
class ScopeFinding:
    """One lint finding."""

    level: str
    message: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Lint one WORKTREE_SCOPE.md or every live worktree for missing or weak "
            "scope fields."
        )
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root whose WORKTREE_SCOPE.md should be linted.",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Alias for linting the current workspace root.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Lint every live worktree in the current repository.",
    )
    return parser


def parse_worktree_roots(repo_root: Path) -> list[Path]:
    """Return live worktree roots from git worktree list."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    roots: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line.split(" ", 1)[1]).resolve())
    return roots


def git_output(workspace_root: Path, args: list[str]) -> str | None:
    """Return stdout for one git command, or None if it cannot run."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def contains_placeholder(text: str) -> bool:
    """Return whether text still contains an unresolved placeholder."""
    stripped = text.strip()
    if not stripped:
        return True
    return any(re.search(pattern, stripped) for pattern in PLACEHOLDER_PATTERNS)


def strip_markdown_wrapping(text: str) -> str:
    """Extract a path-like token from markdown list content."""
    code_match = re.search(r"`([^`]+)`", text)
    if code_match is not None:
        return code_match.group(1)
    link_match = re.search(r"\[[^\]]+\]\(([^)]+)\)", text)
    if link_match is not None:
        return link_match.group(1)
    return text.strip()


def parse_sections(scope_file: Path) -> dict[str, list[str]]:
    """Parse markdown headings into bullet-line lists."""
    sections: dict[str, list[str]] = {}
    current_section: str | None = None
    for raw_line in scope_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            sections[current_section].append(stripped[2:].strip())
    return sections


def extract_named_value(entries: list[str], name: str) -> str:
    """Extract one `Field: value` bullet."""
    prefix = f"{name}:"
    for entry in entries:
        if entry.startswith(prefix):
            return entry[len(prefix) :].strip()
    return ""


def normalize_scope_value(value: str) -> str:
    """Normalize a scalar markdown scope field for comparison."""
    return strip_markdown_wrapping(value).strip().strip("`").strip()


def resolve_scope_path(workspace_root: Path, value: str) -> Path | None:
    """Resolve a path-like scope field against the current workspace."""
    normalized = normalize_scope_value(value)
    if contains_placeholder(normalized):
        return None
    if normalized == ".":
        return workspace_root.resolve()
    path = Path(normalized).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace_root / path).resolve()


def path_is_under(path: Path, parent: Path) -> bool:
    """Return whether path is equal to or nested under parent."""
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def changed_files(workspace_root: Path) -> list[Path]:
    """Return tracked and untracked changed files relative to the workspace."""
    commands = (
        ["diff", "--name-only", "--cached"],
        ["diff", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    paths: list[Path] = []
    seen: set[Path] = set()
    for command in commands:
        output = git_output(workspace_root, command)
        if output is None:
            continue
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            resolved = (workspace_root / line).resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return paths


def concrete_section_paths(workspace_root: Path, entries: list[str]) -> list[Path]:
    """Resolve concrete path entries from one WORKTREE_SCOPE.md section."""
    paths: list[Path] = []
    for entry in entries:
        if contains_placeholder(entry):
            continue
        path = resolve_scope_path(workspace_root, entry)
        if path is not None:
            paths.append(path)
    return paths


def lint_scope(workspace_root: Path) -> list[ScopeFinding]:
    """Return findings for one workspace scope."""
    scope_file = workspace_root / "WORKTREE_SCOPE.md"
    findings: list[ScopeFinding] = []
    if not scope_file.is_file():
        return [ScopeFinding("error", f"WORKTREE_SCOPE.md が見つかりません: {scope_file}")]

    sections = parse_sections(scope_file)
    summary = sections.get("Worktree Summary", [])
    kickoff = sections.get("Kickoff Status", [])
    editable = sections.get("Editable Directories", [])
    runtime_outputs = sections.get("Runtime Output Directories", [])
    readonly = sections.get("Read-Only Or Avoid Directories", [])
    required_refs = sections.get("Required References Before Editing", [])
    carry_over = sections.get("Main Carry-Over Targets", [])
    working_notes = sections.get("Working Notes During Execution", [])
    checks = sections.get("Required Checks Before Commit", [])

    for field in ("Branch", "Worktree path", "Purpose", "Owner or agent"):
        value = extract_named_value(summary, field)
        if contains_placeholder(value):
            findings.append(ScopeFinding("error", f"Worktree Summary の `{field}` が未確定です。"))

    declared_branch = normalize_scope_value(extract_named_value(summary, "Branch"))
    actual_branch = git_output(workspace_root, ["symbolic-ref", "--short", "HEAD"])
    if actual_branch is None:
        actual_branch = git_output(workspace_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if actual_branch is not None and not contains_placeholder(declared_branch):
        if declared_branch != actual_branch:
            findings.append(
                ScopeFinding(
                    "error",
                    "Worktree Summary の `Branch` が current branch と一致しません: "
                    f"{declared_branch} != {actual_branch}",
                )
            )

    declared_worktree_path = resolve_scope_path(
        workspace_root, extract_named_value(summary, "Worktree path")
    )
    actual_worktree_root_text = git_output(workspace_root, ["rev-parse", "--show-toplevel"])
    actual_worktree_root = (
        Path(actual_worktree_root_text).resolve()
        if actual_worktree_root_text is not None
        else workspace_root.resolve()
    )
    if declared_worktree_path is not None and declared_worktree_path != actual_worktree_root:
        findings.append(
            ScopeFinding(
                "error",
                "Worktree Summary の `Worktree path` が current worktree root と一致しません: "
                f"{declared_worktree_path} != {actual_worktree_root}",
            )
        )

    for field in ("Action log path", "Kickoff checks completed", "Next step after kickoff"):
        value = extract_named_value(kickoff, field)
        if contains_placeholder(value):
            findings.append(ScopeFinding("warning", f"Kickoff Status の `{field}` が未確定です。"))

    for section_name, entries in (
        ("Editable Directories", editable),
        ("Runtime Output Directories", runtime_outputs),
        ("Read-Only Or Avoid Directories", readonly),
        ("Main Carry-Over Targets", carry_over),
        ("Required Checks Before Commit", checks),
    ):
        if not entries:
            findings.append(ScopeFinding("error", f"{section_name} が空です。"))
            continue
        for entry in entries:
            if contains_placeholder(entry):
                findings.append(
                    ScopeFinding("error", f"{section_name} に placeholder が残っています: {entry}")
                )

    if not required_refs:
        findings.append(ScopeFinding("error", "Required References Before Editing が空です。"))
    else:
        normalized_refs = {strip_markdown_wrapping(entry).strip() for entry in required_refs}
        for entry in required_refs:
            if contains_placeholder(entry):
                findings.append(
                    ScopeFinding(
                        "error",
                        "Required References Before Editing に placeholder が残っています: "
                        f"{entry}",
                    )
                )
        for required_ref in CORE_REFS:
            if required_ref not in normalized_refs:
                findings.append(
                    ScopeFinding(
                        "warning",
                        "Required References Before Editing に core reference が不足しています: "
                        f"{required_ref}",
                    )
                )

    action_log = extract_named_value(working_notes, "Action log path")
    if contains_placeholder(action_log):
        findings.append(
            ScopeFinding(
                "error",
                "Working Notes During Execution の Action log path が未確定です。",
            )
        )
    else:
        action_log_raw = strip_markdown_wrapping(action_log)
        action_log_path = Path(action_log_raw)
        if not action_log_path.is_absolute():
            action_log_path = (actual_worktree_root / action_log_path).resolve()
        if not action_log_path.is_file():
            findings.append(
                ScopeFinding("error", f"Action log file が存在しません: {action_log_path}")
            )
        else:
            action_log_text = action_log_path.read_text(encoding="utf-8")
            if "## Action Log" not in action_log_text:
                findings.append(
                    ScopeFinding(
                        "warning",
                        f"Action log section が見つかりません: {action_log_path}",
                    )
                )
            if "kickoff" not in action_log_text and "resume" not in action_log_text:
                findings.append(
                    ScopeFinding(
                        "warning",
                        f"Kickoff or resume entry が不足しています: {action_log_path}",
                    )
                )

    editable_paths = concrete_section_paths(workspace_root, editable)
    readonly_paths = concrete_section_paths(workspace_root, readonly)
    for changed_path in changed_files(workspace_root):
        if editable_paths and not any(path_is_under(changed_path, path) for path in editable_paths):
            findings.append(
                ScopeFinding(
                    "error",
                    f"変更ファイルが Editable Directories 外です: {changed_path}",
                )
            )
        if any(path_is_under(changed_path, path) for path in readonly_paths):
            findings.append(
                ScopeFinding(
                    "error",
                    f"変更ファイルが Read-Only Or Avoid Directories 内です: {changed_path}",
                )
            )

    branch_summary = extract_named_value(working_notes, "Branch summary path")
    branch = extract_named_value(summary, "Branch")
    if branch and "/" in branch and contains_placeholder(branch_summary):
        findings.append(
            ScopeFinding(
                "warning",
                "複数 session を想定する branch なら Branch summary path も埋めてください。",
            )
        )
    elif branch_summary and not contains_placeholder(branch_summary):
        branch_summary_raw = strip_markdown_wrapping(branch_summary)
        branch_summary_path = Path(branch_summary_raw)
        if not branch_summary_path.is_absolute():
            branch_summary_path = (actual_worktree_root / branch_summary_path).resolve()
        if not branch_summary_path.is_file():
            findings.append(
                ScopeFinding(
                    "warning",
                    f"Branch summary file が存在しません: {branch_summary_path}",
                )
            )

    return findings


def print_findings(workspace_root: Path, findings: list[ScopeFinding]) -> int:
    """Print findings and return the exit code for one workspace."""
    label = workspace_root.resolve()
    if not findings:
        print(f"OK {label}")
        return 0

    print(f"WORKSPACE {label}")
    for finding in findings:
        print(f"  {finding.level.upper()}: {finding.message}")
    return 1 if any(finding.level == "error" for finding in findings) else 0


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    if args.current:
        workspace_root = Path.cwd().resolve()
    repo_root_text = git_output(workspace_root, ["rev-parse", "--show-toplevel"])
    if repo_root_text is None:
        if args.all:
            raise SystemExit("--all requires a git worktree.")
        repo_root = workspace_root
    else:
        repo_root = Path(repo_root_text).resolve()

    targets = parse_worktree_roots(repo_root) if args.all else [workspace_root]
    exit_code = 0
    for target in targets:
        findings = lint_scope(target)
        exit_code = max(exit_code, print_findings(target, findings))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
