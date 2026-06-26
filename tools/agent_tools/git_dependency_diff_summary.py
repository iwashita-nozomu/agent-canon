#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Summarizes Git diffs together with existing dependency expansion tools.
# upstream design ../../documents/dependency-manifest-design.md defines dependency graph and code dependency separation.
# upstream implementation ./scan_code_dependencies.sh extracts code dependency edges.
# upstream implementation ./run_repo_dependency_review.sh expands dependency-header graph evidence.
# downstream implementation ../../tests/agent_tools/test_git_dependency_diff_summary.py tests summary behavior.
# downstream design ../../documents/tools/git_dependency_diff_summary.md documents command usage.
# @dependency-end
"""Summarize a Git diff and dependency expansion artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeAlias, cast

SCHEMA = "agent_canon.git_dependency_diff_summary.v1"
TOOL_DIR = Path(__file__).resolve().parent
GIT_RENAME_OR_COPY_FIELD_COUNT = 3
GIT_NUMSTAT_FIELD_COUNT = 3
JsonObject: TypeAlias = dict[str, object]
Summary: TypeAlias = dict[str, object]
CommandMap: TypeAlias = dict[str, object]
CODE_SUFFIXES = {
    ".bash",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".py",
    ".sh",
    ".zsh",
}


@dataclass(frozen=True)
class CommandRecord:
    """Captured command result for summary artifacts."""

    command: list[str]
    returncode: int
    stdout_path: str | None = None
    stderr_path: str | None = None


@dataclass(frozen=True)
class ChangedPath:
    """One path-level Git diff row."""

    status: str
    path: str
    old_path: str | None = None
    additions: int | None = None
    deletions: int | None = None
    binary: bool = False
    exists_in_worktree: bool = False


@dataclass(frozen=True)
class DiffSpec:
    """Git diff selection."""

    base: str
    head: str
    paths: tuple[str, ...]

    @property
    def compares_worktree(self) -> bool:
        """Return whether the diff compares base to the current worktree."""
        return not self.head


@dataclass(frozen=True)
class DiffArtifacts:
    """Git diff artifacts written before dependency expansion."""

    rows: list[ChangedPath]
    changed_files_path: Path
    git_stat_path: Path


@dataclass(frozen=True)
class DependencyArtifacts:
    """Dependency artifacts written by existing dependency tools."""

    code_dependencies_path: Path
    dependency_dir: Path
    commands: CommandMap
    status_code: int


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--base",
        default="HEAD",
        help="Base ref for the diff. Defaults to HEAD.",
    )
    parser.add_argument(
        "--head",
        default="",
        help="Optional head ref. When omitted, compare base to the worktree.",
    )
    parser.add_argument(
        "--report-dir",
        default="",
        help="Directory for generated artifacts. Defaults to a temp directory.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Stdout format. Artifact files are always written.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for the selected stdout-format payload.",
    )
    parser.add_argument(
        "--skip-code-dependencies",
        action="store_true",
        help="Skip scan_code_dependencies.sh.",
    )
    parser.add_argument(
        "--skip-dependency-review",
        action="store_true",
        help="Skip run_repo_dependency_review.sh.",
    )
    parser.add_argument(
        "--strict-dependency-review",
        action="store_true",
        help="Pass --fail-missing to run_repo_dependency_review.sh.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional pathspecs passed to git diff and dependency tools.",
    )
    return parser


def git_stdout(root: Path, args: Sequence[str]) -> str:
    """Return stdout for a Git command, raising on failure."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def git_stdout_bytes(root: Path, args: Sequence[str]) -> bytes:
    """Return stdout bytes for a Git command, raising on failure."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def git_diff_args(diff: DiffSpec) -> list[str]:
    """Build the common git diff argument suffix."""
    args = [diff.base]
    if diff.head:
        args.append(diff.head)
    args.append("--")
    args.extend(diff.paths)
    return args


def parse_name_status(output: str) -> list[ChangedPath]:
    """Parse git diff --name-status --find-renames output."""
    rows: list[ChangedPath] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", GIT_NUMSTAT_FIELD_COUNT - 1)
        status = parts[0]
        if (
            status.startswith(("R", "C"))
            and len(parts) >= GIT_RENAME_OR_COPY_FIELD_COUNT
        ):
            rows.append(ChangedPath(status=status, old_path=parts[1], path=parts[2]))
        elif len(parts) >= 2:
            rows.append(ChangedPath(status=status, path=parts[1]))
    return rows


def parse_name_status_z(output: bytes) -> list[ChangedPath]:
    """Parse git diff --name-status -z --find-renames output."""
    rows: list[ChangedPath] = []
    parts = output.split(b"\0")
    index = 0
    while index < len(parts):
        raw_status = parts[index]
        index += 1
        if not raw_status:
            continue
        status = raw_status.decode("utf-8", errors="surrogateescape")
        if index >= len(parts):
            break
        first_path = parts[index].decode("utf-8", errors="surrogateescape")
        index += 1
        if status.startswith(("R", "C")):
            if index >= len(parts):
                break
            path = parts[index].decode("utf-8", errors="surrogateescape")
            index += 1
            rows.append(ChangedPath(status=status, old_path=first_path, path=path))
        else:
            rows.append(ChangedPath(status=status, path=first_path))
    return rows


def parse_numstat(output: str) -> dict[str, tuple[int | None, int | None, bool]]:
    """Parse git diff --numstat output by current path."""
    stats: dict[str, tuple[int | None, int | None, bool]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < GIT_NUMSTAT_FIELD_COUNT:
            continue
        raw_additions, raw_deletions = parts[0], parts[1]
        path = current_numstat_path(parts[-1])
        binary = raw_additions == "-" or raw_deletions == "-"
        additions = None if binary else int(raw_additions)
        deletions = None if binary else int(raw_deletions)
        stats[path] = (additions, deletions, binary)
    return stats


def current_numstat_path(path: str) -> str:
    """Return the current path from Git's text numstat path field."""
    marker = " => "
    if marker not in path:
        return path
    if "{" in path and "}" in path:
        prefix, rest = path.split("{", 1)
        body, suffix = rest.split("}", 1)
        if marker in body:
            return prefix + body.split(marker, 1)[1] + suffix
    return path.split(marker, 1)[1]


def parse_numstat_z(output: bytes) -> dict[str, tuple[int | None, int | None, bool]]:
    """Parse git diff --numstat -z output by current path."""
    stats: dict[str, tuple[int | None, int | None, bool]] = {}
    parts = output.split(b"\0")
    index = 0
    while index < len(parts):
        header = parts[index]
        index += 1
        if not header:
            continue
        fields = header.decode("utf-8", errors="surrogateescape").split(
            "\t", GIT_NUMSTAT_FIELD_COUNT - 1
        )
        if len(fields) < GIT_NUMSTAT_FIELD_COUNT:
            continue
        raw_additions, raw_deletions, path = fields[0], fields[1], fields[2]
        if not path:
            if index + 1 >= len(parts):
                continue
            index += 1
            path = parts[index].decode("utf-8", errors="surrogateescape")
            index += 1
        binary = raw_additions == "-" or raw_deletions == "-"
        additions = None if binary else int(raw_additions)
        deletions = None if binary else int(raw_deletions)
        stats[path] = (additions, deletions, binary)
    return stats


def untracked_paths(root: Path, paths: Sequence[str]) -> list[str]:
    """Return untracked files under the optional pathspec."""
    args = ["ls-files", "--others", "--exclude-standard", "--"]
    args.extend(paths)
    return [line for line in git_stdout(root, args).splitlines() if line.strip()]


def collect_changed_paths(
    root: Path,
    *,
    diff: DiffSpec,
) -> list[ChangedPath]:
    """Collect Git diff rows plus untracked files for worktree diffs."""
    suffix = git_diff_args(diff)
    rows = parse_name_status_z(
        git_stdout_bytes(
            root, ["diff", "--name-status", "-z", "--find-renames", *suffix]
        )
    )
    numstat = parse_numstat_z(
        git_stdout_bytes(root, ["diff", "--numstat", "-z", *suffix])
    )

    merged: list[ChangedPath] = []
    seen: set[str] = set()
    for row in rows:
        additions, deletions, binary = numstat.get(row.path, (None, None, False))
        merged.append(
            ChangedPath(
                status=row.status,
                old_path=row.old_path,
                path=row.path,
                additions=additions,
                deletions=deletions,
                binary=binary,
                exists_in_worktree=(root / row.path).is_file(),
            )
        )
        seen.add(row.path)

    if diff.compares_worktree:
        for path in untracked_paths(root, diff.paths):
            if path in seen:
                continue
            merged.append(
                ChangedPath(
                    status="??",
                    path=path,
                    exists_in_worktree=(root / path).is_file(),
                )
            )
    return sorted(merged, key=lambda item: (item.path, item.status))


def changed_file_list(rows: Sequence[ChangedPath]) -> list[str]:
    """Return paths that can seed dependency expansion."""
    paths = {row.path for row in rows}
    paths.update(row.old_path for row in rows if row.old_path)
    return sorted(paths)


def code_scan_paths(root: Path, rows: Sequence[ChangedPath]) -> list[str]:
    """Return existing source-like files suitable for code dependency scanning."""
    candidates: list[str] = []
    for row in rows:
        path = root / row.path
        if row.status.startswith("D") or not path.is_file():
            continue
        if path.suffix in CODE_SUFFIXES:
            candidates.append(row.path)
    return sorted(set(candidates))


def write_text(path: Path, text: str) -> Path:
    """Write UTF-8 text and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_capture(
    *,
    root: Path,
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
) -> CommandRecord:
    """Run one command and capture stdout/stderr artifacts."""
    result = subprocess.run(
        command, cwd=root, check=False, capture_output=True, text=True
    )
    write_text(stdout_path, result.stdout)
    write_text(stderr_path, result.stderr)
    return CommandRecord(
        command=command,
        returncode=result.returncode,
        stdout_path=stdout_path.as_posix(),
        stderr_path=stderr_path.as_posix(),
    )


def count_prefixed_lines(path: Path, prefix: str) -> int:
    """Count artifact lines that start with a prefix."""
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )


def nonempty_line_count(path: Path) -> int:
    """Count non-empty lines in an artifact when it exists."""
    if not path.exists():
        return 0
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def render_markdown(summary: Summary) -> str:
    """Render a reader-facing Markdown summary."""
    rows = cast(list[JsonObject], summary["changed_files"])
    totals = cast(dict[str, int], summary["totals"])
    lines = [
        "# Git Dependency Diff Summary",
        "",
        f"- Schema: `{summary['schema']}`",
        f"- Status: `{summary['status']}`",
        f"- Root: `{summary['root']}`",
        f"- Diff: `{summary['base']}` -> `{summary['head'] or 'worktree'}`",
        f"- Changed files: {totals['changed_files']}",
        f"- Added lines: {totals['additions']}",
        f"- Deleted lines: {totals['deletions']}",
        f"- Code dependency edges: {totals['code_dependency_edges']}",
        f"- Dependency edit-scope lines: {totals['dependency_edit_scope_lines']}",
        "",
        "## Changed Files",
        "",
        "| Status | Path | Lines | Previous path |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        additions = cast(int | None, row["additions"])
        deletions = cast(int | None, row["deletions"])
        binary = cast(bool, row["binary"])
        old_path = cast(str | None, row["old_path"]) or ""
        line_text = "binary" if binary else f"+{additions or 0} / -{deletions or 0}"
        lines.append(
            f"| `{row['status']}` | `{row['path']}` | {line_text} | `{old_path}` |"
        )

    artifacts = cast(dict[str, str], summary["artifacts"])
    lines.extend(
        [
            "",
            "## Dependency Artifacts",
            "",
            f"- Changed file list: `{artifacts['changed_files']}`",
            f"- Git stat: `{artifacts['git_stat']}`",
            f"- Code dependency TSV: `{artifacts['code_dependencies']}`",
            f"- Dependency review directory: `{artifacts['dependency_review_dir']}`",
            f"- Dependency graph TSV: `{artifacts['dependency_graph']}`",
            f"- Dependency edit scope: `{artifacts['dependency_edit_scope']}`",
        ]
    )
    commands = cast(CommandMap, summary["commands"])
    dependency_review = commands.get("dependency_review")
    if isinstance(dependency_review, dict):
        dependency_review_map = cast(CommandMap, dependency_review)
        lines.extend(
            [
                "",
                "## Command Status",
                "",
                f"- Dependency review exit code: {dependency_review_map['returncode']}",
            ]
        )
    return "\n".join(lines) + "\n"


def diff_spec_from_args(args: argparse.Namespace) -> DiffSpec:
    """Build the typed Git diff selection from CLI arguments."""
    return DiffSpec(base=args.base, head=args.head, paths=tuple(args.paths))


def write_diff_artifacts(root: Path, report_dir: Path, diff: DiffSpec) -> DiffArtifacts:
    """Write Git diff artifacts before dependency expansion."""
    rows = collect_changed_paths(root, diff=diff)
    changed_paths = changed_file_list(rows)
    changed_files_path = write_text(
        report_dir / "changed_files.txt", "\n".join(changed_paths) + "\n"
    )
    git_stat_path = write_text(
        report_dir / "git_stat.txt",
        git_stdout(root, ["diff", "--stat", *git_diff_args(diff)]),
    )
    return DiffArtifacts(
        rows=rows,
        changed_files_path=changed_files_path,
        git_stat_path=git_stat_path,
    )


def run_code_dependency_scan(
    *,
    root: Path,
    report_dir: Path,
    rows: Sequence[ChangedPath],
    skip: bool,
) -> tuple[Path, CommandMap, int]:
    """Run the existing code dependency scanner when source files changed."""
    code_dependencies_path = report_dir / "code_dependencies.tsv"
    commands: CommandMap = {}
    status_code = 0
    if skip:
        write_text(code_dependencies_path, "")
    else:
        scan_paths = code_scan_paths(root, rows)
        if scan_paths:
            record = run_capture(
                root=root,
                command=[
                    "bash",
                    str(TOOL_DIR / "scan_code_dependencies.sh"),
                    "--root",
                    str(root),
                    *scan_paths,
                ],
                stdout_path=code_dependencies_path,
                stderr_path=report_dir / "code_dependencies.stderr.txt",
            )
            commands["code_dependencies"] = asdict(record)
            status_code = max(status_code, record.returncode)
        else:
            write_text(code_dependencies_path, "")
    return code_dependencies_path, commands, status_code


def run_dependency_review(
    *,
    root: Path,
    report_dir: Path,
    dependency_dir: Path,
    changed_files_path: Path,
    skip: bool,
    strict: bool,
) -> tuple[CommandMap, int]:
    """Run the existing dependency-header review wrapper."""
    commands: CommandMap = {}
    status_code = 0
    if skip:
        dependency_dir.mkdir(parents=True, exist_ok=True)
        write_text(dependency_dir / "dependency_graph.tsv", "")
        write_text(dependency_dir / "dependency_edit_scope.txt", "")
    else:
        command = [
            "bash",
            str(TOOL_DIR / "run_repo_dependency_review.sh"),
            "--root",
            str(root),
            "--report-dir",
            str(dependency_dir),
            "--search-hits-file",
            str(changed_files_path),
        ]
        if strict:
            command.append("--fail-missing")
        record = run_capture(
            root=root,
            command=command,
            stdout_path=report_dir / "dependency_review.stdout.txt",
            stderr_path=report_dir / "dependency_review.stderr.txt",
        )
        commands["dependency_review"] = asdict(record)
        status_code = max(status_code, record.returncode)
    return commands, status_code


def build_summary(
    *,
    root: Path,
    report_dir: Path,
    diff: DiffSpec,
    diff_artifacts: DiffArtifacts,
    dependency_artifacts: DependencyArtifacts,
) -> Summary:
    """Build the JSON-serializable summary payload."""
    rows = diff_artifacts.rows
    dependency_dir = dependency_artifacts.dependency_dir
    totals = {
        "changed_files": len(rows),
        "additions": sum(row.additions or 0 for row in rows),
        "deletions": sum(row.deletions or 0 for row in rows),
        "code_dependency_edges": count_prefixed_lines(
            dependency_artifacts.code_dependencies_path, "CODE_DEPENDENCY\t"
        ),
        "dependency_edit_scope_lines": nonempty_line_count(
            dependency_dir / "dependency_edit_scope.txt"
        ),
    }
    summary: Summary = {
        "schema": SCHEMA,
        "status": "pass" if dependency_artifacts.status_code == 0 else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "root": root.as_posix(),
        "base": diff.base,
        "head": diff.head or None,
        "paths": list(diff.paths),
        "changed_files": [asdict(row) for row in rows],
        "totals": totals,
        "artifacts": {
            "report_dir": report_dir.as_posix(),
            "changed_files": diff_artifacts.changed_files_path.as_posix(),
            "git_stat": diff_artifacts.git_stat_path.as_posix(),
            "code_dependencies": dependency_artifacts.code_dependencies_path.as_posix(),
            "dependency_review_dir": dependency_dir.as_posix(),
            "dependency_graph": (dependency_dir / "dependency_graph.tsv").as_posix(),
            "dependency_edit_scope": (
                dependency_dir / "dependency_edit_scope.txt"
            ).as_posix(),
        },
        "commands": dependency_artifacts.commands,
    }
    summary_json = write_text(
        report_dir / "summary.json", json.dumps(summary, indent=2) + "\n"
    )
    summary_markdown = write_text(report_dir / "summary.md", render_markdown(summary))
    summary["artifacts"]["summary_json"] = summary_json.as_posix()
    summary["artifacts"]["summary_markdown"] = summary_markdown.as_posix()
    write_text(summary_json, json.dumps(summary, indent=2) + "\n")
    write_text(summary_markdown, render_markdown(summary))
    return summary


def emit(summary: Summary, output_format: str) -> str:
    """Return the requested stdout payload."""
    if output_format == "json":
        return json.dumps(summary, indent=2) + "\n"
    if output_format == "markdown":
        return render_markdown(summary)
    artifacts = cast(dict[str, str], summary["artifacts"])
    totals = cast(dict[str, int], summary["totals"])
    lines = [
        f"GIT_DEPENDENCY_DIFF_SUMMARY={summary['status']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_SCHEMA={summary['schema']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_CHANGED_FILES={totals['changed_files']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_CODE_EDGES={totals['code_dependency_edges']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_EDIT_SCOPE_LINES={totals['dependency_edit_scope_lines']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_JSON={artifacts['summary_json']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_MARKDOWN={artifacts['summary_markdown']}",
        f"GIT_DEPENDENCY_DIFF_SUMMARY_REPORT_DIR={artifacts['report_dir']}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    try:
        root = Path(str(args.root)).resolve()
        report_dir = (
            Path(args.report_dir)
            if args.report_dir
            else Path(tempfile.mkdtemp(prefix="agent-canon-git-dependency-diff-"))
        )
        report_dir.mkdir(parents=True, exist_ok=True)
        dependency_dir = report_dir / "dependency-review"
        diff = diff_spec_from_args(args)
        diff_artifacts = write_diff_artifacts(root, report_dir, diff)
        code_path, code_commands, code_status = run_code_dependency_scan(
            root=root,
            report_dir=report_dir,
            rows=diff_artifacts.rows,
            skip=args.skip_code_dependencies,
        )
        dependency_commands, dependency_status = run_dependency_review(
            root=root,
            report_dir=report_dir,
            dependency_dir=dependency_dir,
            changed_files_path=diff_artifacts.changed_files_path,
            skip=args.skip_dependency_review,
            strict=args.strict_dependency_review,
        )
        status = max(code_status, dependency_status)
        dependency_artifacts = DependencyArtifacts(
            code_dependencies_path=code_path,
            dependency_dir=dependency_dir,
            commands={**code_commands, **dependency_commands},
            status_code=status,
        )
        summary = build_summary(
            root=root,
            report_dir=report_dir,
            diff=diff,
            diff_artifacts=diff_artifacts,
            dependency_artifacts=dependency_artifacts,
        )
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(
            f"GIT_DEPENDENCY_DIFF_SUMMARY=fail\nGIT_DEPENDENCY_DIFF_SUMMARY_ERROR={exc}",
            file=sys.stderr,
        )
        return 1
    payload = emit(summary, args.format)
    if args.output:
        write_text(args.output, payload)
    print(payload, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
