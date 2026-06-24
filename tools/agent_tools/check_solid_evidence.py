#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks SOLID-sensitive Python changes have path-covered OOP readability evidence.
# upstream design ../../documents/coding-conventions-python.md SOLID evidence route policy
# upstream design ../../agents/skills/oop-readability-check.md SOLID route owner skill
# upstream implementation ../oop/python/readability.py emits OOP readability evidence reports
# upstream implementation ../oop/shared/readability_core.py emits scanned_paths and SOLID counts
# downstream implementation ../../tests/agent_tools/test_check_solid_evidence.py tests evidence gate behavior
# @dependency-end
"""Require OOP readability evidence for SOLID-sensitive Python edits."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

DEFAULT_EXCLUDES = (".git", ".ruff_cache", "__pycache__", "build", "reports", "vendor")
REQUIRED_JSON_SUMMARY_KEYS = {
    "dimension_counts",
    "findings",
    "kind_counts",
    "scanned_paths",
    "solid_counts",
    "status",
}
MARKDOWN_REQUIRED_MARKERS = (
    "## SOLID Principle Signals",
    "## Dimensions",
    "## Finding Kinds",
)


@dataclass(frozen=True, order=True)
class SensitiveChange:
    """One changed Python surface that needs OOP readability evidence."""

    path: str
    line: int
    kind: str
    symbol: str

    def render(self) -> str:
        """Render a stable machine-readable record."""
        return f"{self.path}:{self.line}:{self.kind}:{self.symbol}"


@dataclass(frozen=True, order=True)
class LineSelection:
    """Changed-line selection for one file."""

    full_file: bool
    lines: frozenset[int]


FULL_FILE_SELECTION = LineSelection(full_file=True, lines=frozenset())


@dataclass(frozen=True, order=True)
class Finding:
    """One SOLID evidence gate finding."""

    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"SOLID_EVIDENCE_FINDING={self.path}:{self.detail}"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Check that SOLID-sensitive Python paths are covered by an OOP "
            "readability report."
        )
    )
    parser.add_argument("paths", nargs="*", help="Python files or directories to inspect.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Use git changed paths and changed line ranges when no paths are supplied.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD",
        help="Git base ref for --changed line detection. Defaults to HEAD.",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="OOP readability JSON or Markdown report path. Repeatable.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=list(DEFAULT_EXCLUDES),
        help="Path prefix or part to skip. Repeatable.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print sensitive-change rows even when the gate passes.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def git_lines(root: Path, args: Sequence[str]) -> tuple[str, ...]:
    """Return stdout lines for one git command."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def git_changed_paths(root: Path, base_ref: str) -> tuple[str, ...]:
    """Return tracked and untracked changed paths."""
    paths = set(
        git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRT", base_ref, "--"])
    )
    paths.update(git_lines(root, ["ls-files", "--others", "--exclude-standard"]))
    return tuple(sorted(paths))


def git_diff_text(root: Path, base_ref: str, relative_path: str) -> str:
    """Return git diff text for one path."""
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--unified=0", base_ref, "--", relative_path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    return result.stdout


def line_selection_from_diff(diff_text: str) -> LineSelection:
    """Return changed new-file line numbers from unified diff text."""
    if not diff_text.strip():
        return FULL_FILE_SELECTION
    lines: set[int] = set()
    for line in diff_text.splitlines():
        match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if match is None:
            continue
        start = int(match.group(1))
        length = int(match.group(2) or "1")
        lines.update(range(start, start + length))
    return LineSelection(full_file=False, lines=frozenset(lines))


def path_is_excluded(relative: Path, exclude_patterns: Sequence[str]) -> bool:
    """Return true when a relative path belongs to an excluded surface."""
    parts = set(relative.parts)
    relative_posix = relative.as_posix()
    for raw_pattern in exclude_patterns:
        pattern = raw_pattern.strip().strip("/")
        if (
            pattern
            and (relative_posix == pattern or relative_posix.startswith(f"{pattern}/") or pattern in parts)
        ):
            return True
    return False


def selected_python_paths(
    root: Path,
    raw_paths: Sequence[str],
    *,
    changed: bool,
    base_ref: str,
    exclude_patterns: Sequence[str],
) -> dict[Path, LineSelection]:
    """Return Python files and optional changed-line filters."""
    path_lines: dict[Path, LineSelection] = {}
    source_paths = list(raw_paths)
    from_changed = changed and not source_paths
    if from_changed:
        source_paths = list(git_changed_paths(root, base_ref))
    for raw_path in source_paths:
        candidate = (root / raw_path).resolve()
        if not candidate.exists():
            continue
        files = [candidate] if candidate.is_file() else sorted(candidate.rglob("*.py"))
        for path in files:
            if path.suffix != ".py":
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if path_is_excluded(relative, exclude_patterns):
                continue
            line_selection = (
                line_selection_from_diff(git_diff_text(root, base_ref, relative.as_posix()))
                if from_changed
                else FULL_FILE_SELECTION
            )
            path_lines[path] = line_selection
    return path_lines


def selected_lines_intersect(start: int, end: int, selection: LineSelection) -> bool:
    """Return whether a node span touches selected lines."""
    if selection.full_file:
        return True
    return any(start <= line <= end for line in selection.lines)


def node_end(node: ast.AST) -> int:
    """Return a best-effort ending line number for an AST node."""
    return int(getattr(node, "end_lineno", getattr(node, "lineno", 1)))


def expr_name(expr: ast.AST) -> str:
    """Return a compact expression name for bases and decorators."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return f"{expr_name(expr.value)}.{expr.attr}"
    if isinstance(expr, ast.Call):
        return expr_name(expr.func)
    return type(expr).__name__


def public_symbol(name: str) -> bool:
    """Return whether a symbol is a public boundary."""
    return not name.startswith("_")


def sensitive_changes_for_file(
    root: Path,
    path: Path,
    selected_lines: LineSelection,
) -> tuple[SensitiveChange, ...]:
    """Return SOLID-sensitive changes for one Python file."""
    relative = path.relative_to(root).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    except SyntaxError as exc:
        return (
            SensitiveChange(relative, exc.lineno or 1, "parse_boundary", "python-syntax"),
        )
    changes: set[SensitiveChange] = set()
    for node in tree.body:
        changes.update(sensitive_changes_for_node(relative, node, selected_lines))
    return tuple(sorted(changes))


def sensitive_changes_for_node(
    relative: str,
    node: ast.stmt,
    selected_lines: LineSelection,
) -> tuple[SensitiveChange, ...]:
    """Return sensitive changes for one module-level AST node."""
    if isinstance(node, ast.ClassDef):
        return class_sensitive_changes(relative, node, selected_lines)
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return public_function_sensitive_change(relative, node, selected_lines)
    if isinstance(node, ast.Import | ast.ImportFrom):
        return import_sensitive_change(relative, node, selected_lines)
    return ()


def class_sensitive_changes(
    relative: str,
    node: ast.ClassDef,
    selected_lines: LineSelection,
) -> tuple[SensitiveChange, ...]:
    """Return sensitive records for one class definition."""
    changes: set[SensitiveChange] = set()
    if selected_lines_intersect(node.lineno, node_end(node), selected_lines):
        changes.add(SensitiveChange(relative, node.lineno, "class_boundary", node.name))
    if node.bases and selected_lines_intersect(node.lineno, node.lineno, selected_lines):
        bases = ",".join(expr_name(base) for base in node.bases)
        changes.add(SensitiveChange(relative, node.lineno, "inheritance_boundary", bases))
    decorators = {expr_name(item) for item in node.decorator_list}
    if decorators & {"dataclass", "dataclasses.dataclass"} and selected_lines_intersect(
        node.lineno, node.lineno, selected_lines
    ):
        changes.add(SensitiveChange(relative, node.lineno, "dataclass_boundary", node.name))
    if any(base.endswith("Protocol") for base in (expr_name(base) for base in node.bases)):
        changes.add(SensitiveChange(relative, node.lineno, "protocol_boundary", node.name))
    return tuple(sorted(changes))


def public_function_sensitive_change(
    relative: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    selected_lines: LineSelection,
) -> tuple[SensitiveChange, ...]:
    """Return a sensitive record for one public module function."""
    if public_symbol(node.name) and selected_lines_intersect(node.lineno, node.lineno, selected_lines):
        return (SensitiveChange(relative, node.lineno, "public_api", node.name),)
    return ()


def import_sensitive_change(
    relative: str,
    node: ast.Import | ast.ImportFrom,
    selected_lines: LineSelection,
) -> tuple[SensitiveChange, ...]:
    """Return a sensitive record for one module import."""
    if selected_lines_intersect(node.lineno, node_end(node), selected_lines):
        return (SensitiveChange(relative, node.lineno, "dependency_direction", "import"),)
    return ()


def collect_sensitive_changes(
    root: Path,
    path_lines: dict[Path, LineSelection],
) -> tuple[SensitiveChange, ...]:
    """Collect SOLID-sensitive changes for selected Python files."""
    changes: list[SensitiveChange] = []
    for path, selected_lines in sorted(path_lines.items()):
        changes.extend(sensitive_changes_for_file(root, path, selected_lines))
    return tuple(sorted(set(changes)))


def parse_markdown_scanned_paths(text: str) -> set[str]:
    """Return scanned_paths from a Markdown OOP report."""
    match = re.search(r"(?m)^- scanned_paths: `([^`]*)`$", text)
    if match is None:
        return set()
    value = match.group(1).strip()
    if not value or value == "none":
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def evidence_covered_paths(root: Path, evidence_paths: Sequence[str]) -> tuple[set[str], list[Finding]]:
    """Return covered paths and evidence-structure findings."""
    covered: set[str] = set()
    findings: list[Finding] = []
    for raw_path in evidence_paths:
        path, relative = resolve_evidence_path(root, raw_path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            findings.append(Finding(relative, "missing-evidence-file"))
            continue
        scanned_paths, finding = scanned_paths_from_evidence_text(relative, text)
        if finding is not None:
            findings.append(finding)
            continue
        covered.update(scanned_paths)
    return covered, findings


def resolve_evidence_path(root: Path, raw_path: str) -> tuple[Path, str]:
    """Return resolved evidence path and root-relative display path."""
    path = (root / raw_path).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = raw_path
    return path, relative


def scanned_paths_from_evidence_text(
    relative: str,
    text: str,
) -> tuple[set[str], Finding | None]:
    """Return scanned paths from one OOP evidence text."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return scanned_paths_from_markdown(relative, text)
    return scanned_paths_from_json(relative, payload)


def scanned_paths_from_markdown(relative: str, text: str) -> tuple[set[str], Finding | None]:
    """Return scanned paths from one Markdown OOP report."""
    missing_markers = [marker for marker in MARKDOWN_REQUIRED_MARKERS if marker not in text]
    if missing_markers:
        return set(), Finding(relative, f"invalid-markdown-evidence:{missing_markers[0]}")
    scanned_paths = parse_markdown_scanned_paths(text)
    if not scanned_paths:
        return set(), Finding(relative, "missing-scanned_paths")
    return scanned_paths, None


def scanned_paths_from_json(relative: str, payload: object) -> tuple[set[str], Finding | None]:
    """Return scanned paths from one JSON OOP report."""
    if not isinstance(payload, dict):
        return set(), Finding(relative, "invalid-json-evidence")
    payload_mapping = cast(dict[str, object], payload)
    summary_obj = payload_mapping.get("summary")
    if not isinstance(summary_obj, dict):
        return set(), Finding(relative, "missing-json-summary")
    summary = cast(dict[str, object], summary_obj)
    summary_keys = set(summary)
    missing = sorted(REQUIRED_JSON_SUMMARY_KEYS - summary_keys)
    if missing:
        return set(), Finding(relative, f"missing-json-key:{missing[0]}")
    scanned_paths_obj = summary.get("scanned_paths")
    if not isinstance(scanned_paths_obj, list):
        return set(), Finding(relative, "invalid-scanned_paths")
    scanned_paths = cast(list[object], scanned_paths_obj)
    if not all(isinstance(item, str) for item in scanned_paths):
        return set(), Finding(relative, "invalid-scanned_paths")
    return set(cast(list[str], scanned_paths)), None


def check_evidence(
    root: Path,
    sensitive_changes: Sequence[SensitiveChange],
    evidence_paths: Sequence[str],
) -> tuple[list[Finding], set[str]]:
    """Check evidence coverage for sensitive paths."""
    required_paths = {change.path for change in sensitive_changes}
    if not required_paths:
        return [], set()
    if not evidence_paths:
        return [Finding("<evidence>", "missing-oop-readability-evidence")], set()
    covered_paths, findings = evidence_covered_paths(root, evidence_paths)
    for path in sorted(required_paths - covered_paths):
        findings.append(Finding(path, "missing-path-coverage"))
    return findings, covered_paths


def text_output(
    sensitive_changes: Sequence[SensitiveChange],
    findings: Sequence[Finding],
    covered_paths: Iterable[str],
    *,
    verbose: bool,
) -> str:
    """Render stable text output."""
    lines = [
        f"SOLID_EVIDENCE={'fail' if findings else 'pass'}",
        f"SOLID_EVIDENCE_SENSITIVE_CHANGES={len(sensitive_changes)}",
        f"SOLID_EVIDENCE_COVERED_PATHS={len(set(covered_paths))}",
    ]
    if verbose or findings:
        for change in sensitive_changes:
            lines.append(f"SOLID_EVIDENCE_SENSITIVE_CHANGE={change.render()}")
    for finding in findings:
        lines.append(finding.render())
    return "\n".join(lines)


def json_output(
    sensitive_changes: Sequence[SensitiveChange],
    findings: Sequence[Finding],
    covered_paths: Iterable[str],
) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "fail" if findings else "pass",
            "sensitive_changes": [asdict(change) for change in sensitive_changes],
            "covered_paths": sorted(set(covered_paths)),
            "findings": [asdict(finding) for finding in findings],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SOLID evidence checker."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    path_lines = selected_python_paths(
        root,
        args.paths,
        changed=args.changed,
        base_ref=args.base_ref,
        exclude_patterns=args.exclude,
    )
    sensitive_changes = collect_sensitive_changes(root, path_lines)
    findings, covered_paths = check_evidence(root, sensitive_changes, args.evidence)
    output = (
        json_output(sensitive_changes, findings, covered_paths)
        if args.format == "json"
        else text_output(sensitive_changes, findings, covered_paths, verbose=args.verbose)
    )
    print(output)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
