#!/usr/bin/env python3
# @dependency-start
# responsibility Checks nested algorithm ownership fields for algorithm modules.
# upstream design ../../documents/algorithm-implementation-boundary.md algorithm boundary policy
# upstream implementation ./check_algorithm_module_public_surface.py discovers algorithm modules
# downstream implementation ../../tests/agent_tools/test_check_algorithm_module_nested_contract.py
# @dependency-end
"""Check nested algorithm ownership in modules using ``algorithm_module_protocol``.

When algorithm module ``B`` imports and uses algorithm module ``A``, ``B`` must
surface the nested ownership explicitly:

* ``B.InitializeConfig`` holds ``A.InitializeConfig``.
* ``B.SolveConfig`` holds ``A.SolveConfig``.
* ``B.Info`` holds ``A.Info``.
* ``B.Algorithm`` holds ``A.Algorithm``.

``Problem`` is intentionally exempt because parent algorithms often assemble
child problems internally at solve time.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EXPECTED_PUBLIC_NAME_SET = frozenset(
    {
        "InitializeConfig",
        "SolveConfig",
        "Problem",
        "State",
        "Answer",
        "Info",
        "Algorithm",
        "initialize",
    }
)
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
_CONTRACT_CLASSES = (
    "InitializeConfig",
    "SolveConfig",
    "Info",
    "Algorithm",
)
_CONTRACT_ATTRIBUTE_TO_CLASS = {
    "InitializeConfig": "InitializeConfig",
    "SolveConfig": "SolveConfig",
    "Info": "Info",
    "Algorithm": "Algorithm",
}
_CALL_ATTRIBUTES = frozenset({"initialize"})
_PROBLEM_ATTRIBUTE = "Problem"


@dataclass(frozen=True)
class Finding:
    """One nested-contract finding."""

    path: str
    line: int
    kind: str
    dependency: str
    contract_class: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "ALGORITHM_NESTED_CONTRACT_FINDING="
            f"{self.path}:{self.line}:{self.kind}:"
            f"{self.dependency}:{self.contract_class}:{self.detail}"
        )


@dataclass(frozen=True)
class ModuleReport:
    """Nested-contract report for one algorithm module."""

    path: str
    dependencies: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Check nested algorithm ownership fields in algorithm modules."
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


def is_allowed_non_algorithm_import(relative: str) -> bool:
    """Return true for protocol imports that are not algorithm modules."""
    return any(
        relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in NON_ALGORITHM_IMPORT_ALLOWLIST
    )


def relative_path(root: Path, path: Path) -> str:
    """Return root-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def imported_aliases(tree: ast.Module) -> dict[str, str]:
    """Return import aliases that can name algorithm modules."""
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("algorithm_module_protocol"):
                    continue
                alias_name = alias.asname or alias.name.rsplit(".", maxsplit=1)[-1]
                aliases[alias_name] = alias.name
            continue
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("algorithm_module_protocol"):
                continue
            for alias in node.names:
                if alias.name == "algorithm_module_protocol":
                    continue
                alias_name = alias.asname or alias.name
                if node.level:
                    imported = "." * node.level + module
                    imported = f"{imported}.{alias.name}" if module else imported
                else:
                    imported = f"{module}.{alias.name}" if module else alias.name
                aliases[alias_name] = imported
    return aliases


def alias_attribute_usage(tree: ast.Module, aliases: dict[str, str]) -> dict[str, set[str]]:
    """Return attribute names used on each imported alias."""
    usage: dict[str, set[str]] = {alias: set() for alias in aliases}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id in aliases:
            usage[node.value.id].add(node.attr)
    return {alias: attrs for alias, attrs in usage.items() if attrs}


def required_contract_classes(attributes: set[str]) -> set[str]:
    """Return parent contract classes required by one child usage set."""
    required = {
        _CONTRACT_ATTRIBUTE_TO_CLASS[attribute]
        for attribute in attributes
        if attribute in _CONTRACT_ATTRIBUTE_TO_CLASS
    }
    if attributes & _CALL_ATTRIBUTES:
        required.update(_CONTRACT_CLASSES)
    if required == set() and attributes == {_PROBLEM_ATTRIBUTE}:
        return set()
    return required


def top_level_type_aliases(tree: ast.Module) -> dict[str, str]:
    """Return top-level private/public type alias expansions."""
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = node.value
            if value is not None:
                aliases[node.target.id] = ast.unparse(value)
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                aliases[target.id] = ast.unparse(node.value)
    return aliases


def class_definitions(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """Return top-level class definitions by name."""
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def class_field_annotations(class_node: ast.ClassDef) -> tuple[str, ...]:
    """Return top-level annotated field strings for one class."""
    annotations: list[str] = []
    for node in class_node.body:
        if isinstance(node, ast.AnnAssign):
            annotations.append(ast.unparse(node.annotation))
    return tuple(annotations)


def expand_annotation(
    annotation: str,
    aliases: dict[str, str],
    *,
    seen: frozenset[str] = frozenset(),
) -> str:
    """Expand simple annotation aliases inside one annotation string."""
    if annotation in seen:
        return annotation
    if annotation not in aliases:
        return annotation
    expanded = aliases[annotation]
    return expand_annotation(
        expanded,
        aliases,
        seen=seen | frozenset({annotation}),
    )


def class_annotation_texts(
    class_node: ast.ClassDef,
    aliases: dict[str, str],
) -> tuple[str, ...]:
    """Return raw and alias-expanded annotation text for one class."""
    texts: list[str] = []
    for annotation in class_field_annotations(class_node):
        texts.append(annotation)
        expanded = expand_annotation(annotation, aliases)
        if expanded != annotation:
            texts.append(expanded)
    return tuple(texts)


def annotation_contains_dependency(
    annotations: tuple[str, ...],
    dependency_alias: str,
    dependency_class: str,
) -> bool:
    """Return whether annotations contain ``dependency_alias.dependency_class``."""
    required = f"{dependency_alias}.{dependency_class}"
    return any(required in annotation for annotation in annotations)


def module_is_algorithm(tree: ast.Module, relative: str) -> bool:
    """Return true when a file is a production algorithm module."""
    if not imports_algorithm_module_protocol(tree):
        return False
    definitions = public_definition_names(tree)
    if set(definitions) & EXPECTED_PUBLIC_NAME_SET:
        return True
    return not is_allowed_non_algorithm_import(relative)


def analyze_file(root: Path, path: Path) -> tuple[ModuleReport | None, list[Finding]]:
    """Analyze one Python file for nested algorithm ownership."""
    relative = relative_path(root, path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return None, [
            Finding(
                path=relative,
                line=exc.lineno or 1,
                kind="syntax_error",
                dependency=path.name,
                contract_class="module",
                detail="parseable",
            )
        ]
    if not module_is_algorithm(tree, relative):
        return None, []

    imported = imported_aliases(tree)
    usage = alias_attribute_usage(tree, imported)
    aliases = top_level_type_aliases(tree)
    classes = class_definitions(tree)
    findings: list[Finding] = []
    dependencies: list[str] = []

    for dependency_alias in sorted(usage):
        required = required_contract_classes(usage[dependency_alias])
        if not required:
            continue
        dependencies.append(dependency_alias)
        for contract_class in sorted(required):
            class_node = classes.get(contract_class)
            if class_node is None:
                findings.append(
                    Finding(
                        path=relative,
                        line=1,
                        kind="missing_contract_class",
                        dependency=dependency_alias,
                        contract_class=contract_class,
                        detail=f"define-{contract_class}",
                    )
                )
                continue
            annotations = class_annotation_texts(class_node, aliases)
            if annotation_contains_dependency(
                annotations,
                dependency_alias,
                contract_class,
            ):
                continue
            findings.append(
                Finding(
                    path=relative,
                    line=class_node.lineno,
                    kind="missing_nested_field",
                    dependency=dependency_alias,
                    contract_class=contract_class,
                    detail=f"add-field-annotated-{dependency_alias}.{contract_class}",
                )
            )

    return (
        ModuleReport(path=relative, dependencies=tuple(sorted(set(dependencies)))),
        findings,
    )


def summarize(
    modules: list[ModuleReport],
    findings: list[Finding],
    files: list[Path],
) -> dict[str, Any]:
    """Build deterministic summary output."""
    return {
        "files": len(files),
        "algorithm_modules": len(modules),
        "dependencies": sum(len(module.dependencies) for module in modules),
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
        print(f"ALGORITHM_NESTED_CONTRACT_FILES={summary['files']}")
        print(f"ALGORITHM_NESTED_CONTRACT_MODULES={summary['algorithm_modules']}")
        print(f"ALGORITHM_NESTED_CONTRACT_DEPENDENCIES={summary['dependencies']}")
        print(f"ALGORITHM_NESTED_CONTRACT_FINDINGS={summary['findings']}")
        print(f"ALGORITHM_NESTED_CONTRACT={summary['status']}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
