#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Inspects legacy worktree scope evidence for cleanup diagnostics.
# upstream design ../README.md shared automation index
# @dependency-end

"""Inspect legacy worktree scope evidence and summarize cleanup actions."""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from worktree_scope_lint import lint_scope


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the current checkout for legacy WORKTREE_SCOPE.md and worktree action-log "
            "state. This diagnostic does not create, resume, or switch worktrees."
        )
    )
    parser.add_argument(
        "branch",
        nargs="?",
        help="Legacy branch argument is unsupported; use --current to inspect the current workspace.",
    )
    parser.add_argument(
        "worktree_path",
        nargs="?",
        help="Legacy worktree path argument is unsupported; use --current for cleanup diagnostics.",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help=(
            "Inspect the current workspace root for legacy worktree scope evidence."
        ),
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not append a cleanup diagnostic entry to the legacy action log.",
    )
    return parser


def run_checked(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one command and require success."""
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def run_optional(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one command and capture output without raising."""
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def repo_root(start_dir: Path) -> Path:
    """Return the current git workspace root."""
    result = run_checked(["git", "rev-parse", "--show-toplevel"], cwd=start_dir)
    return Path(result.stdout.strip()).resolve()


def current_branch(workspace_root: Path) -> str:
    """Return the current branch or HEAD label."""
    result = run_optional(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=workspace_root)
    if result.returncode != 0:
        return "(unknown)"
    return result.stdout.strip() or "(unknown)"


def parse_worktree_list(repo_root: Path) -> list[dict[str, str]]:
    """Parse `git worktree list --porcelain` into dictionaries."""
    result = run_checked(["git", "worktree", "list", "--porcelain"], cwd=repo_root)
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree" and current:
            entries.append(current)
            current = {}
        current[key] = value
    if current:
        entries.append(current)
    return entries


def normalize_branch_name(branch_ref: str) -> str:
    """Convert `refs/heads/<branch>` to `<branch>`."""
    prefix = "refs/heads/"
    if branch_ref.startswith(prefix):
        return branch_ref[len(prefix) :]
    return branch_ref


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


def resolve_action_log_path(workspace_root: Path, scope_file: Path) -> Path | None:
    """Return the action log path from WORKTREE_SCOPE.md when available."""
    sections = parse_sections(scope_file)
    working_notes = sections.get("Working Notes During Execution", [])
    raw_value = extract_named_value(working_notes, "Action log path")
    if not raw_value or "<" in raw_value or "worktree_<topic>" in raw_value:
        return None
    token = raw_value.split("`")
    candidate = token[1] if len(token) >= 3 else raw_value
    path = Path(candidate)
    if path.is_absolute():
        return path

    repo_guess = run_optional(["git", "rev-parse", "--show-toplevel"], cwd=workspace_root)
    if repo_guess.returncode == 0:
        return (Path(repo_guess.stdout.strip()).resolve() / path).resolve()

    for ancestor in (workspace_root, *workspace_root.parents):
        if (ancestor / path.parent).exists() or (ancestor / "notes").is_dir():
            return (ancestor / path).resolve()
    return (workspace_root / path).resolve()


def resolve_user_request_contract_path(workspace_root: Path, scope_file: Path) -> Path | None:
    """Return the user request contract path from WORKTREE_SCOPE.md when available."""
    sections = parse_sections(scope_file)
    for section_name in ("Working Notes During Execution", "Kickoff Status"):
        raw_value = extract_named_value(
            sections.get(section_name, []),
            "User request contract path",
        )
        if not raw_value or "<" in raw_value or "<run-id>" in raw_value:
            continue
        token = raw_value.split("`")
        candidate = token[1] if len(token) >= 3 else raw_value
        path = Path(candidate)
        if path.is_absolute():
            return path
        repo_guess = run_optional(["git", "rev-parse", "--show-toplevel"], cwd=workspace_root)
        if repo_guess.returncode == 0:
            return (Path(repo_guess.stdout.strip()).resolve() / path).resolve()
        return (workspace_root / path).resolve()
    return None


def _log_action_entry(action_log_path: Path, entry: str) -> None:
    """Append one entry to the action log, creating a minimal file when missing."""
    action_log_path.parent.mkdir(parents=True, exist_ok=True)
    if not action_log_path.exists():
        action_log_path.write_text("# Worktree Log\n\n## Action Log\n\n", encoding="utf-8")
    with action_log_path.open("a", encoding="utf-8") as handle:
        if action_log_path.stat().st_size > 0:
            handle.write("\n")
        handle.write(f"- {entry}\n")


def append_action_log_entry(action_log_path: Path, entry: str) -> None:
    """Append one entry to the action log."""
    _log_action_entry(action_log_path, entry)


def summarize_scope_presence(repo_root: Path) -> list[str]:
    """Return scope presence for every live worktree."""
    lines: list[str] = []
    for entry in parse_worktree_list(repo_root):
        worktree = Path(entry["worktree"]).resolve()
        branch = normalize_branch_name(entry.get("branch", ""))
        status = "present" if (worktree / "WORKTREE_SCOPE.md").is_file() else "missing"
        label = branch or "(detached)"
        lines.append(f"{label}: {worktree} [{status}]")
    return lines


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    starting_root = repo_root(Path.cwd())

    if args.branch is not None or args.worktree_path is not None:
        raise SystemExit(
            "worktree_start.py is cleanup diagnostic only; branch/path worktree kickoff is unsupported."
        )

    workspace_root = starting_root
    status = "current-workspace"

    branch = current_branch(workspace_root)
    scope_file = workspace_root / "WORKTREE_SCOPE.md"
    findings = lint_scope(workspace_root)
    action_log_path = (
        resolve_action_log_path(workspace_root, scope_file) if scope_file.is_file() else None
    )

    if action_log_path is not None and not args.no_log:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M JST")
        entry = (
            f"`{timestamp} | {status} | branch={branch} "
            f"worktree={workspace_root} | next: inspect legacy scope and cleanup evidence`"
        )
        _log_action_entry(action_log_path, entry)

    print(f"WORKTREE_STATUS={status}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    print(f"BRANCH={branch}")
    print(f"SCOPE_FILE={scope_file}")
    print(f"ACTION_LOG={action_log_path if action_log_path is not None else '(not-resolved)'}")
    print("WORKTREE_SCOPE_PRESENCE:")
    for line in summarize_scope_presence(starting_root):
        print(f"  - {line}")
    if findings:
        print("LINT_STATUS=needs-refresh")
        for finding in findings:
            print(f"{finding.level.upper()}: {finding.message}")
        return 0

    print("LINT_STATUS=ok")
    print("NEXT_STEPS:")
    print("  1. Confirm legacy action log, branch summary, and carry-over targets are current.")
    print("  2. Run git status --short --branch and git worktree list --porcelain.")
    print(
        "  3. Use python3 tools/agent_tools/work_log.py --run-id <run-id> "
        "--kind <kind> --message '<what changed>' --next '<next>' "
        "after each meaningful step."
    )
    print("  4. Start editing only after the current checkout run-local handoff is updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
