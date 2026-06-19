#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks Python run-log ownership and Info summary emission contracts.
# upstream design ../../documents/coding-conventions-logging.md logging convention overview
# upstream design ../../documents/conventions/common/01_principles.md canonical simplicity principle
# downstream implementation ../../tests/agent_tools/test_check_run_log_contract.py tests checker behavior
# @dependency-end
"""Check that run-log summaries are resolved from ``amp.Info`` objects."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PATHS = ("python/jax_util",)
DEFAULT_EXCLUDES = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "python/tests",
    "reports",
    "tests",
    "vendor",
)
RUN_LOG_INTERNAL_MODULES = frozenset({"python/jax_util/base/_run_log.py"})
DIRECT_RUN_LOG_NAMES = frozenset(
    {
        "RunLogWriter",
        "InfoRunLogEmitter",
        "begin_run_log",
        "child_run_log_context",
        "write_device_run_log_event",
        "write_host_run_log_event",
        "write_info_run_log_event",
    }
)
SUMMARY_FIELD_LIST_SUFFIXES = (
    "_INFO_FIELD_NAMES",
    "_SUMMARY_FIELD_NAMES",
    "_RUN_LOG_FIELD_NAMES",
)


@dataclass(frozen=True)
class Finding:
    """One run-log contract violation."""

    path: str
    line: int
    code: str
    symbol: str
    reason: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "RUN_LOG_CONTRACT_FINDING="
            f"{self.path}:{self.line}:{self.code}:{self.symbol}:{self.reason}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Check run-log conventions: Info summaries should auto-resolve from "
            "amp.Info, product code should not call low-level run-log writers, "
            "and summary field-name constants should not duplicate Info fields."
        )
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to scan.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=list(DEFAULT_EXCLUDES),
        help="Path, path prefix, path part, or glob to exclude. Repeatable.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on-finding", action="store_true")
    return parser


def path_is_excluded(relative: Path, exclude_patterns: list[str]) -> bool:
    """Return true when a root-relative path matches an exclude pattern."""
    relative_posix = relative.as_posix()
    for raw_pattern in exclude_patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue
        if any(char in pattern for char in "*?[]"):
            if fnmatch.fnmatch(relative_posix, pattern):
                return True
            continue
        if (
            relative_posix == pattern
            or relative_posix.startswith(f"{pattern}/")
            or pattern in relative.parts
        ):
            return True
    return False


def is_hidden(path: Path) -> bool:
    """Return true when any path part is hidden."""
    return any(part.startswith(".") for part in path.parts)


def iter_python_files(
    root: Path,
    raw_paths: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Expand explicit files and directories into Python source files."""
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [
        root / raw_path for raw_path in DEFAULT_PATHS
    ]
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            files.append(target.resolve())
            continue
        if target.is_dir():
            for path in sorted(target.rglob("*.py")):
                relative = relative_path(root, path)
                relative_path_obj = Path(relative)
                if is_hidden(relative_path_obj):
                    continue
                if path_is_excluded(relative_path_obj, exclude_patterns):
                    continue
                files.append(path.resolve())
    return sorted(set(files))


def relative_path(root: Path, path: Path) -> str:
    """Return root-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def base_name(node: ast.AST) -> str:
    """Return a dotted name for a Python expression when possible."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = base_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return base_name(node.func)
    return ""


def has_keyword(call: ast.Call, keyword_name: str) -> bool:
    """Return true when one call has the named keyword argument."""
    return any(keyword.arg == keyword_name for keyword in call.keywords)


def keyword_string_value(call: ast.Call, keyword_name: str) -> str | None:
    """Return one string keyword value when it is a literal."""
    for keyword in call.keywords:
        if keyword.arg != keyword_name:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def target_names(node: ast.AST) -> tuple[str, ...]:
    """Return assignment target names."""
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in node.elts:
            names.extend(target_names(item))
        return tuple(names)
    return ()


def assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    """Return top-level assignment target names."""
    if isinstance(node, ast.AnnAssign):
        return target_names(node.target)
    names: list[str] = []
    for target in node.targets:
        names.extend(target_names(target))
    return tuple(names)


def calls_name(node: ast.AST | None, names: frozenset[str]) -> str | None:
    """Return the matched callee suffix if an expression calls one name."""
    if not isinstance(node, ast.Call):
        return None
    callee = base_name(node.func).split(".")[-1]
    return callee if callee in names else None


def analyze_file(root: Path, path: Path) -> list[Finding]:
    """Return run-log contract findings for one file."""
    relative = relative_path(root, path)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative)
    if relative in RUN_LOG_INTERNAL_MODULES:
        return []
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in DIRECT_RUN_LOG_NAMES:
                    findings.append(
                        Finding(
                            path=relative,
                            line=node.lineno,
                            code="direct-run-log-writer-import",
                            symbol=alias.name,
                            reason=(
                                "use RunLog.submit/submit_device/submit_info; "
                                "low-level writers are implementation details"
                            ),
                        )
                    )
        elif isinstance(node, ast.Call):
            called_name = base_name(node.func).split(".")[-1]
            if called_name in DIRECT_RUN_LOG_NAMES:
                findings.append(
                    Finding(
                        path=relative,
                        line=node.lineno,
                        code="direct-run-log-writer-call",
                        symbol=called_name,
                        reason=(
                            "use RunLog.submit/submit_device/submit_info; "
                            "low-level writers are implementation details"
                        ),
                    )
                )
            if called_name == "submit_info" and has_keyword(node, "field_names"):
                findings.append(
                    Finding(
                        path=relative,
                        line=node.lineno,
                        code="manual-info-field-list",
                        symbol="submit_info.field_names",
                        reason=(
                            "Info summary logs should auto-resolve public amp.Info "
                            "fields; pass field_names only in explicit alias tests"
                        ),
                    )
                )
            if called_name in {"submit", "submit_device"} and keyword_string_value(
                node,
                "event",
            ) == "iter":
                findings.append(
                    Finding(
                        path=relative,
                        line=node.lineno,
                        code="iteration-log-without-info",
                        symbol=f"{called_name}(event='iter')",
                        reason=(
                            "iteration diagnostics must use the module Info type via "
                            "RunLog.submit_info(..., event='iter')"
                        ),
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            matched_callee = calls_name(getattr(node, "value", None), DIRECT_RUN_LOG_NAMES)
            for name in assigned_names(node):
                if name.endswith(SUMMARY_FIELD_LIST_SUFFIXES):
                    findings.append(
                        Finding(
                            path=relative,
                            line=node.lineno,
                            code="summary-field-list-constant",
                            symbol=name,
                            reason=(
                                "summary log field lists duplicate amp.Info annotations; "
                                "let RunLog.submit_info resolve fields"
                            ),
                        )
                    )
                if matched_callee is not None:
                    findings.append(
                        Finding(
                            path=relative,
                            line=node.lineno,
                            code="direct-run-log-writer-object",
                            symbol=f"{name}={matched_callee}",
                            reason=(
                                "do not create dedicated summary/log writer objects; "
                                "use the algorithm RunLog"
                            ),
                        )
                    )
    return findings


def collect_findings(root: Path, files: list[Path]) -> list[Finding]:
    """Collect findings across files."""
    findings: list[Finding] = []
    for path in files:
        findings.extend(analyze_file(root, path))
    return sorted(findings, key=lambda item: (item.path, item.line, item.code, item.symbol))


def write_json(files: list[Path], findings: list[Finding]) -> None:
    """Write JSON output."""
    print(
        json.dumps(
            {
                "summary": {
                    "files": len(files),
                    "findings": len(findings),
                },
                "findings": [asdict(finding) for finding in findings],
            },
            indent=2,
            sort_keys=True,
        )
    )


def write_text(files: list[Path], findings: list[Finding]) -> None:
    """Write text output."""
    print(f"RUN_LOG_CONTRACT_FILES={len(files)}")
    print(f"RUN_LOG_CONTRACT_FINDINGS={len(findings)}")
    for finding in findings:
        print(finding.render())
    print(f"RUN_LOG_CONTRACT={'fail' if findings else 'pass'}")


def main() -> int:
    """Run the checker."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    files = iter_python_files(root, args.paths, args.exclude)
    findings = collect_findings(root, files)
    if args.format == "json":
        write_json(files, findings)
    else:
        write_text(files, findings)
    return 1 if findings and args.fail_on_finding else 0


if __name__ == "__main__":
    raise SystemExit(main())
