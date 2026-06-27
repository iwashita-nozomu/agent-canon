#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks algorithm module public surface against the standard solver contract.
# upstream design ../../documents/tools/README.md algorithm module surface checker
# downstream implementation ../../tests/agent_tools/test_check_algorithm_module_public_surface.py tests checker  # noqa: E501
# @dependency-end
"""Check algorithm modules that import ``algorithm_module_protocol``.

Production files that import ``algorithm_module_protocol`` are expected to be
algorithm modules unless they are package exports, canon registries, or tests.
Algorithm modules must expose the standard public names. Result-status constants
are allowed under the ``STATUS_`` prefix because they are the stable vocabulary
for ``Answer.status``; other top-level public definitions are rejected.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path

EXPECTED_PUBLIC_NAMES = (
    "InitializeConfig",
    "SolveConfig",
    "Problem",
    "State",
    "Answer",
    "Info",
    "Algorithm",
    "initialize",
)
EXPECTED_PUBLIC_NAME_SET = frozenset(EXPECTED_PUBLIC_NAMES)
EXPECTED_PUBLIC_NAMES_AS_SET: set[str] = set(EXPECTED_PUBLIC_NAMES)
ALLOWED_EXTRA_PUBLIC_PREFIXES = ("STATUS_",)
DEFAULT_EXCLUDES = (
    ".git",
    ".ruff_cache",
    "__pycache__",
    "build",
    "reports",
    "vendor",
    "python/jax_util.egg-info",
)
NON_ALGORITHM_IMPORT_ALLOWLIST = (
    "python/jax_util/base",
    "python/jax_util/canon",
    "python/tests",
    "tests",
)


@dataclass(frozen=True)
class Finding:
    """One public-surface finding."""

    path: str
    line: int
    kind: str
    name: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            f"ALGORITHM_PUBLIC_SURFACE_FINDING="
            f"{self.path}:{self.line}:{self.kind}:{self.name}:{self.detail}"
        )


@dataclass(frozen=True)
class ModuleReport:
    """Public-surface report for one algorithm module."""

    path: str
    public_names: tuple[str, ...]
    all_names: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Check algorithm modules expose only the standard public names."
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to analyze.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=list(DEFAULT_EXCLUDES),
        help="Path, path prefix, path part, or glob to exclude. Repeatable.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def path_is_excluded(relative: Path, exclude_patterns: list[str]) -> bool:
    """Return true when a root-relative path matches one exclude pattern."""
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
    """Expand files and directories into Python files."""
    targets = [root / raw_path for raw_path in raw_paths] if raw_paths else [root]
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            files.append(target.resolve())
            continue
        if target.is_dir():
            for path in sorted(target.rglob("*.py")):
                try:
                    relative = path.relative_to(root)
                except ValueError:
                    relative = path
                if is_hidden(relative):
                    continue
                if path_is_excluded(relative, exclude_patterns):
                    continue
                files.append(path.resolve())
    return sorted(set(files))


def imports_algorithm_module_protocol(tree: ast.Module) -> bool:
    """Return true when the module imports the algorithm module protocol."""
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.endswith("algorithm_module_protocol"):
                return True
            if any(alias.name == "algorithm_module_protocol" for alias in node.names):
                return True
        if isinstance(node, ast.Import):
            if any(alias.name.endswith("algorithm_module_protocol") for alias in node.names):
                return True
    return False


def public_definition_names(tree: ast.Module) -> dict[str, int]:
    """Return top-level public definitions and first line numbers."""
    names: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.setdefault(node.name, node.lineno)
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and is_public_assignment(target.id):
                    names.setdefault(target.id, node.lineno)
            continue
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and is_public_assignment(target.id):
                names.setdefault(target.id, node.lineno)
    return names


def is_public_assignment(name: str) -> bool:
    """Return true for top-level assignment names that create public surface."""
    return not name.startswith("_") and name != "__all__"


def is_allowed_extra_public_name(name: str) -> bool:
    """Return true for bounded public constants outside the standard surface."""
    return any(name.startswith(prefix) for prefix in ALLOWED_EXTRA_PUBLIC_PREFIXES)


def is_allowed_non_algorithm_import(relative: str) -> bool:
    """Return true for protocol imports that are not algorithm modules."""
    return any(
        relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in NON_ALGORITHM_IMPORT_ALLOWLIST
    )


def parse_all_names(tree: ast.Module) -> tuple[tuple[str, ...] | None, int, bool]:
    """Return static ``__all__`` names, line number, and dynamic flag."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in node.targets
            ):
                return literal_string_sequence(node.value), node.lineno, False
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "__all__":
                if node.value is None:
                    return None, node.lineno, True
                return literal_string_sequence(node.value), node.lineno, False
    return None, 1, False


def literal_string_sequence(value: ast.AST) -> tuple[str, ...] | None:
    """Return a literal sequence of strings or ``None`` for dynamic values."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return None
    names: list[str] = []
    for element in value.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        names.append(element.value)
    return tuple(names)


def relative_path(root: Path, path: Path) -> str:
    """Return root-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def analyze_file(root: Path, path: Path) -> tuple[ModuleReport | None, list[Finding]]:
    """Analyze one Python file."""
    relative = relative_path(root, path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return None, [
            Finding(
                path=relative,
                line=exc.lineno or 1,
                kind="syntax_error",
                name=path.name,
                detail="parseable",
            )
        ]
    imports_protocol = imports_algorithm_module_protocol(tree)
    definitions = public_definition_names(tree)
    if not imports_protocol:
        return None, []
    if not set(definitions) & EXPECTED_PUBLIC_NAME_SET:
        if is_allowed_non_algorithm_import(relative):
            return None, []
        return None, [
            Finding(
                path=relative,
                line=1,
                kind="non_algorithm_protocol_import",
                name="algorithm_module_protocol",
                detail="define-standard-public-surface-or-remove-import",
            )
        ]

    findings: list[Finding] = []
    all_names, all_line, all_dynamic = parse_all_names(tree)
    if all_names is None:
        findings.append(
            Finding(
                path=relative,
                line=all_line,
                kind="dynamic_all" if all_dynamic else "missing_all",
                name="__all__",
                detail="literal-standard-public-names-required",
            )
        )
        all_names = ()

    all_name_set = set(all_names)
    for name in sorted(all_name_set - EXPECTED_PUBLIC_NAME_SET):
        if is_allowed_extra_public_name(name):
            continue
        findings.append(
            Finding(
                path=relative,
                line=all_line,
                kind="extra_all",
                name=name,
                detail="remove-from-__all__",
            )
        )
    for name in sorted(EXPECTED_PUBLIC_NAMES_AS_SET - all_name_set):
        findings.append(
            Finding(
                path=relative,
                line=all_line,
                kind="missing_all_name",
                name=name,
                detail="add-to-__all__",
            )
        )
    for name, line in sorted(definitions.items()):
        if name not in EXPECTED_PUBLIC_NAME_SET:
            if is_allowed_extra_public_name(name):
                continue
            findings.append(
                Finding(
                    path=relative,
                    line=line,
                    kind="extra_public_definition",
                    name=name,
                    detail="make-private-or-remove",
                )
            )
    for name in sorted(EXPECTED_PUBLIC_NAMES_AS_SET - set(definitions)):
        findings.append(
            Finding(
                path=relative,
                line=all_line,
                kind="missing_public_definition",
                name=name,
                detail="define-standard-public-name",
            )
        )

    report = ModuleReport(
        path=relative,
        public_names=tuple(sorted(definitions)),
        all_names=tuple(all_names),
    )
    return report, findings


def summarize(
    modules: list[ModuleReport],
    findings: list[Finding],
    files: list[Path],
) -> dict[str, object]:
    """Build deterministic summary output."""
    return {
        "files": len(files),
        "algorithm_modules": len(modules),
        "findings": len(findings),
        "status": "pass" if not findings else "fail",
    }


def main() -> int:
    """Run the checker."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    files = iter_python_files(root, args.paths, args.exclude)
    modules: list[ModuleReport] = []
    findings: list[Finding] = []
    for path in files:
        report, file_findings = analyze_file(root, path)
        if report is not None:
            modules.append(report)
        findings.extend(file_findings)

    summary = summarize(modules, findings, files)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "summary": summary,
                    "modules": [asdict(module) for module in modules],
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in findings:
            print(finding.render())
        print(f"ALGORITHM_PUBLIC_SURFACE_FILES={summary['files']}")
        print(f"ALGORITHM_PUBLIC_SURFACE_MODULES={summary['algorithm_modules']}")
        print(f"ALGORITHM_PUBLIC_SURFACE_FINDINGS={summary['findings']}")
        print(f"ALGORITHM_PUBLIC_SURFACE={summary['status']}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
