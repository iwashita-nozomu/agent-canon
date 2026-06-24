#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks Python imports for unused aliases and responsibility-scope boundary violations.
# upstream design ../../responsibility-scope.toml declares scope ownership and import rules
# upstream design ../../documents/responsibility-scope-management.md explains scope ownership policy
# upstream design ../../documents/coding-conventions-python.md defines Python import boundary policy
# upstream design ../../tools/catalog.yaml registers this tool
# upstream design ../../tools/README.md documents shared tool entrypoints
# upstream design ../../documents/tools/README.md documents user-facing tool usage
# upstream implementation ./responsibility_scope.py validates responsibility scope metadata
# downstream implementation ../../tools/ci/run_all_checks.sh runs import responsibility checks
# downstream implementation ../../tests/agent_tools/test_import_responsibility.py validates import findings
# @dependency-end
"""Check Python imports against responsibility scopes."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import subprocess
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

MANIFEST_PATH = "responsibility-scope.toml"
PYTHON_SUFFIX = ".py"
IGNORED_DIRS = {
    ".agent-canon",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "reports",
    "target",
}


@dataclass(frozen=True)
class Scope:
    """One responsibility scope and its path patterns."""

    scope_id: str
    paths: tuple[str, ...]
    exclude_paths: tuple[str, ...]


@dataclass(frozen=True)
class ImportRule:
    """Allowed target scopes for one source scope."""

    source: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class ImportRecord:
    """One Python import edge extracted from AST."""

    path: str
    line: int
    module: str
    imported_name: str
    local_name: str
    level: int
    kind: str


@dataclass(frozen=True)
class Finding:
    """One import responsibility finding."""

    check: str
    path: str
    line: int
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "IMPORT_RESPONSIBILITY_FINDING="
            f"{self.check}:{self.path}:{self.line}:{self.detail}"
        )


@dataclass(frozen=True)
class Report:
    """Import responsibility check result."""

    files: int
    imports: int
    findings: tuple[Finding, ...]


class ScopeIndex:
    """Resolve repository paths to responsibility scope IDs."""

    def __init__(self, scopes: Sequence[Scope], root: Path) -> None:
        """Store scopes for path lookup."""
        self.scopes = tuple(scopes)
        self.root = root.resolve()

    def scope_for(self, path: str) -> str | None:
        """Return the most specific scope covering a path."""
        scope_path = self.scope_path(path)
        matches: list[tuple[int, str]] = []
        for scope in self.scopes:
            if any(pattern_covers(pattern, scope_path) for pattern in scope.exclude_paths):
                continue
            for pattern in scope.paths:
                if pattern_covers(pattern, scope_path):
                    matches.append((len(pattern), scope.scope_id))
        if not matches:
            return None
        return sorted(matches)[-1][1]

    def scope_path(self, path: str) -> str:
        """Return the canonical path used for scope lookup."""
        candidate = self.root / path
        try:
            resolved = candidate.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path
        return resolved if resolved != path else path


class ImportCollector(ast.NodeVisitor):
    """Collect import statements and loaded names from one Python file."""

    def __init__(self, path: str) -> None:
        """Initialize collector state for one relative path."""
        self.path = path
        self.imports: list[ImportRecord] = []
        self.used_names: set[str] = set()
        self.exported_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Collect ``import module`` aliases."""
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self.imports.append(
                ImportRecord(
                    path=self.path,
                    line=node.lineno,
                    module=alias.name,
                    imported_name=alias.name,
                    local_name=local_name,
                    level=0,
                    kind="import",
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Collect ``from module import name`` aliases."""
        module = node.module or ""
        for alias in node.names:
            local_name = alias.asname or alias.name
            self.imports.append(
                ImportRecord(
                    path=self.path,
                    line=node.lineno,
                    module=module,
                    imported_name=alias.name,
                    local_name=local_name,
                    level=node.level,
                    kind="from",
                )
            )

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Collect names used in load context."""
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Collect string names assigned to ``__all__``."""
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                self.exported_names.update(string_sequence_values(node.value))
        self.generic_visit(node)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Python files to check.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--changed", action="store_true", help="Check changed Python files.")
    parser.add_argument(
        "--baseline-ref",
        default="HEAD",
        help="Git ref used by --changed. Defaults to HEAD.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a TOML value."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in cast(list[object], value) if isinstance(item, str))


def mapping_list(value: object) -> tuple[Mapping[str, object], ...]:
    """Return mapping rows from a TOML array."""
    if not isinstance(value, list):
        return ()
    return tuple(
        cast(Mapping[str, object], item)
        for item in cast(list[object], value)
        if isinstance(item, Mapping)
    )


def load_scope_index(root: Path, path: Path) -> tuple[ScopeIndex, dict[str, ImportRule]]:
    """Load scopes and import rules from a responsibility manifest."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    scopes = tuple(
        Scope(
            scope_id=str(item.get("id") or ""),
            paths=string_tuple(item.get("paths")),
            exclude_paths=string_tuple(item.get("exclude_paths")),
        )
        for item in mapping_list(data.get("scope"))
    )
    rules = {
        str(item.get("source") or ""): ImportRule(
            source=str(item.get("source") or ""),
            targets=string_tuple(item.get("targets")),
        )
        for item in mapping_list(data.get("import_rule"))
    }
    return ScopeIndex(scopes, root), rules


def resolve_manifest_path(root: Path, manifest: str) -> Path:
    """Return the active responsibility manifest path.

    Parent repositories may omit a root-local override and rely on the vendored
    AgentCanon default manifest. A root-local manifest wins when present.
    """
    requested = Path(manifest)
    if requested.is_absolute():
        return requested
    root_manifest = root / requested
    if root_manifest.is_file():
        return root_manifest
    vendored_manifest = root / "vendor" / "agent-canon" / requested
    if vendored_manifest.is_file():
        return vendored_manifest
    return root_manifest


def pattern_covers(pattern: str, path: str) -> bool:
    """Return whether one scope pattern covers a repository path."""
    if pattern == path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern.removesuffix("/**").rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def string_sequence_values(value: ast.AST) -> set[str]:
    """Return string constants from a simple sequence AST node."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return set()
    names: set[str] = set()
    for element in value.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            names.add(element.value)
    return names


def changed_python_paths(root: Path, baseline_ref: str) -> tuple[str, ...]:
    """Return changed Python paths from git."""
    commands = (
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            baseline_ref,
            "--",
        ],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        add_changed_python_paths(paths, command)
    return tuple(sorted(paths))


def add_changed_python_paths(paths: set[str], command: list[str]) -> None:
    """Add changed Python paths from one git command into paths."""
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        paths.update(
            line
            for line in result.stdout.splitlines()
            if line.endswith(PYTHON_SUFFIX) and not should_skip(line)
        )


def existing_python_path(root: Path, relative_path: str) -> bool:
    """Return whether a git-visible Python path exists as a file."""
    return (root / relative_path).is_file()


def git_visible_python_paths(root: Path) -> tuple[str, ...] | None:
    """Return Python paths visible to git, respecting standard ignore rules."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return tuple(
        sorted(
            path
            for path in result.stdout.split("\0")
            if path.endswith(PYTHON_SUFFIX)
            and not should_skip(path)
            and existing_python_path(root, path)
        )
    )


def checked_python_paths(
    root: Path,
    raw_paths: Sequence[str],
    *,
    changed: bool,
    baseline_ref: str,
) -> tuple[str, ...]:
    """Return normalized Python paths to inspect."""
    if raw_paths:
        return tuple(
            dict.fromkeys(
                normalize_path(root, raw_path)
                for raw_path in raw_paths
                if raw_path.endswith(PYTHON_SUFFIX)
            )
        )
    if changed:
        return changed_python_paths(root, baseline_ref)
    git_paths = git_visible_python_paths(root)
    if git_paths is not None:
        return git_paths
    paths: list[str] = []
    for path in sorted(root.rglob(f"*{PYTHON_SUFFIX}")):
        relative = path.relative_to(root).as_posix()
        if should_skip(relative):
            continue
        paths.append(relative)
    return tuple(paths)


def normalize_path(root: Path, raw_path: str) -> str:
    """Return a root-relative path when possible."""
    candidate = (root / raw_path).resolve()
    try:
        return candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return raw_path


def should_skip(relative: str) -> bool:
    """Return whether a path should be skipped by repository-wide scans."""
    parts = set(Path(relative).parts)
    return bool(parts & IGNORED_DIRS)


def parse_imports(root: Path, relative_path: str) -> tuple[ImportCollector | None, list[Finding]]:
    """Parse imports from one Python file."""
    path = root / relative_path
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=relative_path)
    except SyntaxError as exc:
        return None, [Finding("parse-error", relative_path, exc.lineno or 0, exc.msg)]
    collector = ImportCollector(relative_path)
    collector.visit(tree)
    return collector, wildcard_findings(collector)


def wildcard_findings(collector: ImportCollector) -> list[Finding]:
    """Return wildcard import findings."""
    findings: list[Finding] = []
    for record in collector.imports:
        if record.imported_name == "*":
            findings.append(
                Finding(
                    "wildcard-import",
                    record.path,
                    record.line,
                    f"module:{record.module or '<relative>'}",
                )
            )
    return findings


def unused_import_findings(collector: ImportCollector, lines: Sequence[str]) -> list[Finding]:
    """Return unused import findings from AST usage."""
    findings: list[Finding] = []
    used = collector.used_names | collector.exported_names
    for record in collector.imports:
        if record.imported_name == "*" or record.module == "__future__":
            continue
        if has_noqa_f401(lines, record.line):
            continue
        if record.local_name not in used:
            findings.append(
                Finding(
                    "unused-import",
                    record.path,
                    record.line,
                    f"name:{record.local_name}:module:{record.module or record.imported_name}",
                )
            )
    return findings


def has_noqa_f401(lines: Sequence[str], line_number: int) -> bool:
    """Return whether a line carries a no-F401 marker."""
    if line_number <= 0 or line_number > len(lines):
        return False
    line = lines[line_number - 1]
    return "# noqa" in line and ("F401" in line or line.rstrip().endswith("# noqa"))


def resolve_import_target(root: Path, record: ImportRecord) -> str | None:
    """Resolve a local import target to a repository path when possible."""
    source_path = root / record.path
    if record.kind == "from":
        candidates = module_candidates(root, source_path, record.module, record.level)
        if record.imported_name != "*":
            candidates += module_candidates(
                root,
                source_path,
                dotted_join(record.module, record.imported_name),
                record.level,
            )
    else:
        candidates = module_candidates(root, source_path, record.module, 0)

    for candidate in candidates:
        target = existing_module_path(candidate)
        if target is not None:
            try:
                return target.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                return None
    return None


def dotted_join(prefix: str, suffix: str) -> str:
    """Join module components with a dot."""
    if not prefix:
        return suffix
    return f"{prefix}.{suffix}"


def module_candidates(root: Path, source_path: Path, module: str, level: int) -> list[Path]:
    """Return possible filesystem stems for an import module."""
    module_path = Path(*module.split(".")) if module else Path()
    if level > 0:
        base = source_path.parent
        for _ in range(max(level - 1, 0)):
            base = base.parent
        return [base / module_path]
    return [source_path.parent / module_path, root / module_path]


def existing_module_path(stem: Path) -> Path | None:
    """Return the concrete Python file for a module stem."""
    if stem.suffix == PYTHON_SUFFIX and stem.is_file():
        return stem
    module_file = stem.with_suffix(PYTHON_SUFFIX)
    if module_file.is_file():
        return module_file
    init_file = stem / "__init__.py"
    if init_file.is_file():
        return init_file
    return None


def scope_import_findings(
    root: Path,
    collector: ImportCollector,
    scope_index: ScopeIndex,
    rules: Mapping[str, ImportRule],
) -> list[Finding]:
    """Return local import findings for disallowed scope crossings."""
    findings: list[Finding] = []
    source_scope = scope_index.scope_for(collector.path)
    for record in collector.imports:
        target_path = resolve_import_target(root, record)
        if target_path is None or target_path == record.path:
            continue
        target_scope = scope_index.scope_for(target_path)
        if source_scope is None or target_scope is None:
            findings.append(
                Finding(
                    "unscoped-local-import",
                    record.path,
                    record.line,
                    f"{source_scope or '<unscoped>'}->{target_scope or '<unscoped>'}:target:{target_path}",
                )
            )
            continue
        rule = rules.get(source_scope)
        allowed_targets = set(rule.targets if rule is not None else (source_scope,))
        if target_scope not in allowed_targets:
            findings.append(
                Finding(
                    "scope-import",
                    record.path,
                    record.line,
                    f"{source_scope}->{target_scope}:module:{record.module or record.imported_name}:target:{target_path}",
                )
            )
    return findings


def check_imports(
    root: Path,
    manifest: str,
    paths: Sequence[str],
    *,
    changed: bool,
    baseline_ref: str,
) -> Report:
    """Check import usage and responsibility boundaries."""
    scope_index, rules = load_scope_index(root, resolve_manifest_path(root, manifest))
    findings: list[Finding] = []
    import_count = 0
    checked_paths = checked_python_paths(
        root,
        paths,
        changed=changed,
        baseline_ref=baseline_ref,
    )
    for relative_path in checked_paths:
        collector, parse_findings = parse_imports(root, relative_path)
        findings.extend(parse_findings)
        if collector is None:
            continue
        import_count += len(collector.imports)
        lines = (root / relative_path).read_text(encoding="utf-8").splitlines()
        findings.extend(unused_import_findings(collector, lines))
        findings.extend(scope_import_findings(root, collector, scope_index, rules))
    return Report(
        files=len(checked_paths),
        imports=import_count,
        findings=tuple(
            sorted(
                dict.fromkeys(findings),
                key=lambda item: (item.path, item.line, item.check, item.detail),
            )
        ),
    )


def render_text(report: Report) -> str:
    """Render stable text output."""
    lines = [finding.render() for finding in report.findings]
    lines.extend(
        [
            f"IMPORT_RESPONSIBILITY_FILES={report.files}",
            f"IMPORT_RESPONSIBILITY_IMPORTS={report.imports}",
            f"IMPORT_RESPONSIBILITY_FINDINGS={len(report.findings)}",
            f"IMPORT_RESPONSIBILITY={'pass' if not report.findings else 'fail'}",
        ]
    )
    return "\n".join(lines)


def render_json(report: Report) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "files": report.files,
            "imports": report.imports,
            "findings": [asdict(finding) for finding in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the import responsibility checker."""
    args = build_parser().parse_args(argv)
    report = check_imports(
        Path(args.root).resolve(),
        args.manifest,
        args.paths,
        changed=args.changed,
        baseline_ref=args.baseline_ref,
    )
    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
