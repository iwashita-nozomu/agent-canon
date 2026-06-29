#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks nested algorithm ownership fields for algorithm modules.
# upstream design ../../documents/design/jax_util/algorithm_module_contract.md algorithm boundary policy
# upstream implementation ./check_algorithm_module_public_surface.py discovers algorithm modules
# downstream implementation ../../tests/agent_tools/test_check_algorithm_module_nested_contract.py tests  # noqa: E501
# @dependency-end
"""Check nested algorithm ownership in modules using ``algorithm_module_protocol``.

When algorithm module ``B`` imports and uses algorithm module ``A``, ``B`` must
surface the nested ownership explicitly:

* ``B.InitializeConfig`` holds ``A.InitializeConfig``.
* ``B.SolveConfig`` holds ``A.SolveConfig``.
* ``B.Algorithm`` holds ``A.Algorithm``.

``Info`` is intentionally not required to hold every child ``Info``. Parent
algorithms may return a summary ``Info`` while child details are emitted through
the shared run-log file.

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
_PROBLEM_ATTRIBUTE = "Problem"
_ALGORITHM_ATTRIBUTE = "Algorithm"
_INITIALIZE_CONFIG_ATTRIBUTE = "InitializeConfig"


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


def contract_annotation_dependencies(
    classes: dict[str, ast.ClassDef],
    aliases: dict[str, str],
    dependency_aliases: set[str],
) -> dict[str, set[str]]:
    """Return dependency classes explicitly owned by public contract annotations."""
    dependencies: dict[str, set[str]] = {}
    for contract_class, class_node in classes.items():
        if contract_class not in EXPECTED_PUBLIC_NAME_SET:
            continue
        for annotation in class_annotation_texts(class_node, aliases):
            for dependency_alias in dependency_aliases:
                prefix = f"{dependency_alias}."
                if prefix not in annotation:
                    continue
                dependency_class = annotation.split(prefix, maxsplit=1)[1].split(
                    "[", maxsplit=1
                )[0].split(")", maxsplit=1)[0].split(",", maxsplit=1)[0]
                if dependency_class and dependency_class != _PROBLEM_ATTRIBUTE:
                    dependencies.setdefault(dependency_alias, set()).add(dependency_class)
    return dependencies


def initialize_call_requirements(
    tree: ast.Module,
    dependency_aliases: set[str],
) -> dict[str, set[str]]:
    """Return ownership requirements implied by nested ``initialize`` calls.

    A child algorithm callable owned by the parent must be visible in the parent
    ``Algorithm``. A child ``InitializeConfig`` is required only when the call
    consumes a parent ``config.<field>``; fixed or parent-derived child config
    construction stays an implementation detail.
    """
    requirements: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "initialize"
            and isinstance(func.value, ast.Name)
            and func.value.id in dependency_aliases
        ):
            continue
        dependency_alias = func.value.id
        requirements.setdefault(dependency_alias, set()).add(_ALGORITHM_ATTRIBUTE)
        if (
            node.args
            and uses_parent_config_field(node.args[0])
            and not is_dependency_initialize_config_construction(
                node.args[0],
                dependency_alias,
            )
        ):
            requirements[dependency_alias].add(_INITIALIZE_CONFIG_ATTRIBUTE)
    return requirements


def is_dependency_initialize_config_construction(
    node: ast.AST,
    dependency_alias: str,
) -> bool:
    """Return true for ``dependency.InitializeConfig(...)`` construction."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == _INITIALIZE_CONFIG_ATTRIBUTE
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == dependency_alias
    )


def uses_parent_config_field(node: ast.AST) -> bool:
    """Return true when an expression reads ``config.<field>``."""
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "config"
        ):
            return True
    return False


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
    aliases = top_level_type_aliases(tree)
    classes = class_definitions(tree)
    dependency_aliases = set(imported)
    owned_dependencies = contract_annotation_dependencies(
        classes,
        aliases,
        dependency_aliases,
    )
    requirements = initialize_call_requirements(tree, dependency_aliases)
    findings: list[Finding] = []
    dependencies: set[str] = set(owned_dependencies) | set(requirements)

    for dependency_alias in sorted(dependencies):
        required = requirements.get(dependency_alias, set())
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
        ModuleReport(path=relative, dependencies=tuple(sorted(dependencies))),
        findings,
    )


def summarize(
    modules: list[ModuleReport],
    findings: list[Finding],
    files: list[Path],
) -> dict[str, int | str]:
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
