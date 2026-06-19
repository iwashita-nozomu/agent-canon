#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates notebooks as readable runnable demos instead of fine-grained tests.
# upstream design ../../tools/README.md shared validation tool family ownership
# upstream design ../../documents/tools/README.md root-facing tool entrypoint policy
# downstream implementation ../../.codex/hooks/notebook_quality_guard.py blocks changed notebook quality findings
# downstream implementation ../../tools/ci/run_all_checks.sh runs notebook quality validation in CI
# downstream implementation ../../tests/tools/test_notebook_quality.py tests notebook quality checks
# @dependency-end
"""Validate notebooks as practical, readable, visualization-oriented demos."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

NOTEBOOK_SUFFIX = ".ipynb"
DEFAULT_NOTEBOOK_DIRS = ("jupyter", "notebooks")
MAX_CODE_CELL_LINES = 80
MIN_MARKDOWN_CHARS = 120
GIT_TIMEOUT_SECONDS = 10
FORBIDDEN_CODE_PATTERNS = (
    (re.compile(r"(?m)^\s*assert\b"), "fine-grained-assertion", "move assertions to tests/"),
    (re.compile(r"\bpytest\b"), "pytest-in-notebook", "move pytest usage to tests/"),
    (re.compile(r"\bunittest\b"), "unittest-in-notebook", "move unittest usage to tests/"),
    (re.compile(r"(?m)^\s*def\s+test_[A-Za-z0-9_]*\s*\("), "test-function", "move test functions to tests/"),
    (re.compile(r"\braise\s+AssertionError\b"), "assertion-error", "move assertion failures to tests/"),
    (re.compile(r"\b(?:np|numpy)\.testing\b"), "testing-helper", "move testing helpers to tests/"),
)
VISUALIZATION_PATTERNS = (
    re.compile(r"\bplt\.(?:figure|subplots|plot|scatter|imshow|show)\b"),
    re.compile(r"\bdisplay\s*\("),
    re.compile(r"\b(?:altair|plotly|bokeh|seaborn)\b"),
    re.compile(r"\.(?:plot|hist|imshow)\s*\("),
)


@dataclass(frozen=True)
class Finding:
    """One notebook quality finding."""

    path: str
    cell: int
    line: int
    check: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return (
            "NOTEBOOK_QUALITY_FINDING="
            f"{self.path}:cell={self.cell}:line={self.line}:"
            f"{self.check}:{self.detail}"
        )


@dataclass(frozen=True)
class Warning:
    """One non-blocking notebook quality warning."""

    path: str
    cell: int
    line: int
    check: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable warning."""
        return (
            "NOTEBOOK_QUALITY_WARNING="
            f"{self.path}:cell={self.cell}:line={self.line}:"
            f"{self.check}:{self.detail}"
        )


@dataclass(frozen=True)
class NotebookMetrics:
    """Notebook quality metrics useful for logs and JSON output."""

    path: str
    markdown_cells: int
    code_cells: int
    visualization_cells: int
    error_outputs: int
    markdown_chars: int


@dataclass(frozen=True)
class NotebookReport:
    """Validation result for a notebook set."""

    findings: tuple[Finding, ...]
    warnings: tuple[Warning, ...]
    metrics: tuple[NotebookMetrics, ...]


@dataclass
class NotebookScanState:
    """Mutable counters collected while scanning one notebook."""

    path: str
    findings: list[Finding]
    warnings: list[Warning]
    markdown_cells: int = 0
    code_cells: int = 0
    visualization_cells: int = 0
    error_outputs: int = 0
    markdown_chars: int = 0
    previous_was_code: bool = False
    first_non_empty_type: str = ""

    def metrics(self) -> NotebookMetrics:
        """Return immutable metrics for the scanned notebook."""
        return NotebookMetrics(
            path=self.path,
            markdown_cells=self.markdown_cells,
            code_cells=self.code_cells,
            visualization_cells=self.visualization_cells,
            error_outputs=self.error_outputs,
            markdown_chars=self.markdown_chars,
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Notebook files or directories to check.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check changed notebooks relative to HEAD plus untracked notebooks.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check notebooks under the default notebook directories.",
    )
    parser.add_argument(
        "--max-code-cell-lines",
        type=int,
        default=MAX_CODE_CELL_LINES,
        help=f"Maximum source lines allowed in one code cell. Default: {MAX_CODE_CELL_LINES}.",
    )
    parser.add_argument(
        "--min-markdown-chars",
        type=int,
        default=MIN_MARKDOWN_CHARS,
        help=f"Minimum total Markdown characters required. Default: {MIN_MARKDOWN_CHARS}.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )
    return parser


def git_lines(root: Path, args: Sequence[str]) -> list[str]:
    """Return non-empty git output lines."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_notebook_paths(root: Path) -> list[Path]:
    """Return tracked and untracked changed notebook paths."""
    names: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMR", "--"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        names.update(git_lines(root, args))
    return sorted(
        root / name
        for name in names
        if name.endswith(NOTEBOOK_SUFFIX) and (root / name).is_file()
    )


def all_notebook_paths(root: Path) -> list[Path]:
    """Return notebooks in the default notebook directories."""
    paths: list[Path] = []
    for relative_dir in DEFAULT_NOTEBOOK_DIRS:
        directory = root / relative_dir
        if directory.is_dir():
            paths.extend(directory.rglob(f"*{NOTEBOOK_SUFFIX}"))
    return sorted(path for path in paths if path.is_file())


def explicit_notebook_paths(root: Path, raw_paths: Sequence[str]) -> list[Path]:
    """Resolve explicit notebook file or directory arguments."""
    paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        candidate = path if path.is_absolute() else root / path
        if candidate.is_dir():
            paths.extend(candidate.rglob(f"*{NOTEBOOK_SUFFIX}"))
        elif candidate.suffix == NOTEBOOK_SUFFIX and candidate.is_file():
            paths.append(candidate)
    return sorted(set(paths))


def notebook_paths(root: Path, raw_paths: Sequence[str], *, changed: bool, all_: bool) -> list[Path]:
    """Return the notebook paths requested by one invocation."""
    if raw_paths:
        return explicit_notebook_paths(root, raw_paths)
    if changed:
        return changed_notebook_paths(root)
    if all_:
        return all_notebook_paths(root)
    return changed_notebook_paths(root)


def relative_path(root: Path, path: Path) -> str:
    """Return a stable display path."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cell_source(cell: Mapping[str, object]) -> str:
    """Return one notebook cell source as text."""
    source = cell.get("source")
    if isinstance(source, str):
        return source
    if isinstance(source, Sequence):
        return "".join(item for item in source if isinstance(item, str))
    return ""


def cell_type(cell: Mapping[str, object]) -> str:
    """Return one notebook cell type."""
    value = cell.get("cell_type")
    return value if isinstance(value, str) else ""


def source_line_for_match(source: str, match: re.Match[str]) -> int:
    """Return a 1-based source line for a regex match."""
    return source[: match.start()].count("\n") + 1


def has_visualization_code(source: str) -> bool:
    """Return whether one code cell appears to produce a visualization."""
    return any(pattern.search(source) for pattern in VISUALIZATION_PATTERNS)


def output_has_error(cell: Mapping[str, object]) -> int:
    """Return how many error outputs one code cell stores."""
    outputs = cell.get("outputs")
    if not isinstance(outputs, Sequence) or isinstance(outputs, str):
        return 0
    count = 0
    for output in outputs:
        if isinstance(output, Mapping) and output.get("output_type") == "error":
            count += 1
    return count


def load_notebook_cells(path: Path, display_path: str) -> tuple[Sequence[object] | None, list[Finding]]:
    """Load one notebook and return its raw cells or findings."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [
            Finding(display_path, 0, 0, "invalid-json", type(exc).__name__),
        ]
    if not isinstance(raw, Mapping):
        return None, [
            Finding(
                display_path,
                0,
                0,
                "invalid-notebook",
                "top-level must be an object",
            )
        ]
    cells = raw.get("cells")
    if not isinstance(cells, Sequence) or isinstance(cells, str):
        return None, [
            Finding(display_path, 0, 0, "invalid-notebook", "cells must be a list")
        ]
    return cells, []


def record_markdown_cell(state: NotebookScanState, source: str) -> None:
    """Record one Markdown cell."""
    state.markdown_cells += 1
    state.markdown_chars += len(source.strip())
    state.previous_was_code = False


def code_cell_structure_findings(
    state: NotebookScanState,
    cell_index: int,
    source: str,
    max_code_cell_lines: int,
) -> list[Finding]:
    """Return structure findings for one code cell."""
    findings: list[Finding] = []
    if state.previous_was_code:
        findings.append(
            Finding(
                state.path,
                cell_index,
                1,
                "consecutive-code-cells",
                "add a Markdown explanation between runnable steps",
            )
        )
    source_lines = source.splitlines()
    if len(source_lines) > max_code_cell_lines:
        findings.append(
            Finding(
                state.path,
                cell_index,
                max_code_cell_lines + 1,
                "oversized-code-cell",
                f"{len(source_lines)} lines exceeds {max_code_cell_lines}",
            )
        )
    return findings


def code_cell_content_findings(
    display_path: str,
    cell_index: int,
    source: str,
    cell_errors: int,
) -> tuple[list[Finding], list[Warning]]:
    """Return content findings and warnings for one code cell."""
    findings: list[Finding] = []
    warnings: list[Warning] = []
    if cell_errors:
        warnings.append(
            Warning(
                display_path,
                cell_index,
                0,
                "error-output",
                f"{cell_errors} stored error output(s)",
            )
        )
    for pattern, check, detail in FORBIDDEN_CODE_PATTERNS:
        for match in pattern.finditer(source):
            findings.append(
                Finding(
                    display_path,
                    cell_index,
                    source_line_for_match(source, match),
                    check,
                    detail,
                )
            )
    return findings, warnings


def record_code_cell(
    state: NotebookScanState,
    cell_index: int,
    cell: Mapping[str, object],
    source: str,
    max_code_cell_lines: int,
) -> None:
    """Record one code cell and its findings."""
    state.code_cells += 1
    state.findings.extend(
        code_cell_structure_findings(state, cell_index, source, max_code_cell_lines)
    )
    state.previous_was_code = True
    if has_visualization_code(source):
        state.visualization_cells += 1
    cell_errors = output_has_error(cell)
    state.error_outputs += cell_errors
    content_findings, content_warnings = code_cell_content_findings(
        state.path, cell_index, source, cell_errors
    )
    state.findings.extend(content_findings)
    state.warnings.extend(content_warnings)


def record_cell(
    state: NotebookScanState,
    cell_index: int,
    cell_value: object,
    max_code_cell_lines: int,
) -> None:
    """Record one raw notebook cell."""
    if not isinstance(cell_value, Mapping):
        state.findings.append(
            Finding(state.path, cell_index, 0, "invalid-cell", "cell must be an object")
        )
        state.previous_was_code = False
        return
    kind = cell_type(cell_value)
    source = cell_source(cell_value)
    if source.strip() and not state.first_non_empty_type:
        state.first_non_empty_type = kind
    if kind == "markdown":
        record_markdown_cell(state, source)
    elif kind == "code":
        record_code_cell(state, cell_index, cell_value, source, max_code_cell_lines)
    else:
        state.previous_was_code = False


def final_notebook_findings(
    state: NotebookScanState,
    *,
    min_markdown_chars: int,
) -> list[Finding]:
    """Return notebook-level findings after all cells were scanned."""
    findings: list[Finding] = []
    if state.first_non_empty_type != "markdown":
        findings.append(
            Finding(
                state.path,
                1,
                1,
                "missing-title-markdown",
                "first non-empty cell should be Markdown",
            )
        )
    if state.markdown_cells == 0:
        findings.append(
            Finding(state.path, 0, 0, "missing-markdown", "notebooks need narrative cells")
        )
    if state.code_cells == 0:
        findings.append(
            Finding(state.path, 0, 0, "missing-code", "notebooks need runnable code cells")
        )
    if state.markdown_chars < min_markdown_chars:
        findings.append(
            Finding(
                state.path,
                0,
                0,
                "thin-narrative",
                f"{state.markdown_chars} Markdown chars is below {min_markdown_chars}",
            )
        )
    if state.visualization_cells == 0:
        findings.append(
            Finding(
                state.path,
                0,
                0,
                "missing-visualization",
                "include runnable visualization code such as matplotlib, display, "
                "plotly, or dataframe plotting",
            )
        )
    return findings


def build_notebook_validation(
    root: Path,
    path: Path,
    *,
    max_code_cell_lines: int,
    min_markdown_chars: int,
) -> tuple[list[Finding], NotebookMetrics | None]:
    """Validate one notebook file."""
    display_path = relative_path(root, path)
    cells, load_findings = load_notebook_cells(path, display_path)
    if cells is None:
        return load_findings, None
    state = NotebookScanState(path=display_path, findings=list(load_findings), warnings=[])
    for cell_index, cell_value in enumerate(cells, start=1):
        record_cell(state, cell_index, cell_value, max_code_cell_lines)
    state.findings.extend(
        final_notebook_findings(
            state,
            min_markdown_chars=min_markdown_chars,
        )
    )
    return state.findings, state.warnings, state.metrics()


def validate_paths(
    root: Path,
    paths: Iterable[Path],
    *,
    max_code_cell_lines: int,
    min_markdown_chars: int,
) -> NotebookReport:
    """Validate notebook paths and return one report."""
    findings: list[Finding] = []
    warnings: list[Warning] = []
    metrics: list[NotebookMetrics] = []
    for path in paths:
        notebook_findings, notebook_warnings, notebook_metrics = build_notebook_validation(
            root,
            path,
            max_code_cell_lines=max_code_cell_lines,
            min_markdown_chars=min_markdown_chars,
        )
        findings.extend(notebook_findings)
        warnings.extend(notebook_warnings)
        if notebook_metrics is not None:
            metrics.append(notebook_metrics)
    return NotebookReport(
        findings=tuple(findings),
        warnings=tuple(warnings),
        metrics=tuple(metrics),
    )


def render_text(report: NotebookReport) -> str:
    """Render one text report."""
    lines = [
        f"NOTEBOOK_QUALITY_FILES={len(report.metrics)}",
        f"NOTEBOOK_QUALITY_FINDINGS={len(report.findings)}",
        f"NOTEBOOK_QUALITY_WARNINGS={len(report.warnings)}",
    ]
    for metrics in report.metrics:
        lines.append(
            "NOTEBOOK_QUALITY_METRICS="
            f"{metrics.path}:markdown_cells={metrics.markdown_cells}:"
            f"code_cells={metrics.code_cells}:"
            f"visualization_cells={metrics.visualization_cells}:"
            f"error_outputs={metrics.error_outputs}:"
            f"markdown_chars={metrics.markdown_chars}"
        )
    lines.extend(finding.render() for finding in report.findings)
    lines.extend(warning.render() for warning in report.warnings)
    lines.append(f"NOTEBOOK_QUALITY={'fail' if report.findings else 'pass'}")
    return "\n".join(lines)


def render_json(report: NotebookReport) -> str:
    """Render one JSON report."""
    payload = {
        "status": "fail" if report.findings else "pass",
        "findings": [asdict(finding) for finding in report.findings],
        "warnings": [asdict(warning) for warning in report.warnings],
        "metrics": [asdict(metrics) for metrics in report.metrics],
    }
    return json.dumps(payload, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run notebook quality validation."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    paths = notebook_paths(root, args.paths, changed=args.changed, all_=args.all)
    report = validate_paths(
        root,
        paths,
        max_code_cell_lines=args.max_code_cell_lines,
        min_markdown_chars=args.min_markdown_chars,
    )
    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
