#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks algorithm InitializeConfig/SolveConfig ownership partition.
# upstream design ../../documents/design/jax_util/algorithm_module_contract.md config contract
# upstream design ../../documents/algorithm-implementation-boundary.md algorithm boundary policy
# downstream implementation ../../tests/agent_tools/test_check_algorithm_config_partition.py tests
# @dependency-end
"""Check algorithm config ownership and hidden runtime defaults."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_EXCLUDES = (
    ".git",
    ".ruff_cache",
    "__pycache__",
    "build",
    "reports",
    "vendor",
    "python/jax_util.egg-info",
)
INITIALIZE_ONLY_FIELD_NAMES = frozenset(
    {
        "run_log",
        "output_path",
        "run_label",
        "log_iterates",
        "log_intermediates",
        "log_operator_stats",
    }
)
RUNTIME_ONLY_FIELD_NAMES = frozenset(
    {
        "atol",
        "maxiter",
        "rtol",
        "runtime_atol",
        "runtime_rtol",
        "stopping",
    }
)
PROTOCOL_MODULE = "jax_util.base.algorithm_module_protocol"
CONFIG_BASE_KINDS = {
    "InitializeConfig": "InitializeConfig",
    "SolveConfig": "SolveConfig",
}


@dataclass(frozen=True)
class Finding:
    """One config partition finding."""

    path: str
    line: int
    class_name: str
    field: str
    annotation: str
    expected_owner: str
    reason: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "ALGORITHM_CONFIG_PARTITION_FINDING="
            f"{self.path}:{self.line}:{self.class_name}.{self.field}:"
            f"expected={self.expected_owner}:reason={self.reason}"
        )


@dataclass(frozen=True)
class DefaultFinding:
    """One hidden default-value finding."""

    path: str
    line: int
    scope: str
    kind: str
    name: str
    owner: str
    severity: str
    reason: str
    guidance: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "ALGORITHM_CONFIG_DEFAULT_FINDING="
            f"{self.path}:{self.line}:{self.scope}:{self.kind}:{self.name}:"
            f"owner={self.owner}:severity={self.severity}:reason={self.reason}"
        )


@dataclass(frozen=True)
class ConfigField:
    """One annotated field declared on an algorithm config class."""

    path: str
    line: int
    class_name: str
    field: str
    annotation: str
    annotation_config_kinds: tuple[str, ...]


@dataclass(frozen=True)
class ImportContext:
    """Import aliases needed to resolve config classes from AST."""

    module_aliases: dict[str, str]
    class_aliases: dict[str, str]


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Check that initialization-only fields are not in SolveConfig, "
            "runtime-only fields are not in InitializeConfig, and defaults are "
            "owned by explicit config surfaces instead of hidden runtime defaults."
        )
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
    parser.add_argument("--fail-on-finding", action="store_true")
    parser.add_argument(
        "--fail-on-default",
        action="store_true",
        help="Return non-zero when hidden runtime default findings are present.",
    )
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


def relative_path(root: Path, path: Path) -> str:
    """Return root-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def base_name(node: ast.AST) -> str:
    """Return a dotted-ish name for an AST expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = base_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Subscript):
        return base_name(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return "|".join(part for part in (base_name(node.left), base_name(node.right)) if part)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def annotation_text(node: ast.AST) -> str:
    """Return compact source text for an annotation."""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - best-effort only.
        return base_name(node)


def base_names(node: ast.AST) -> tuple[str, ...]:
    """Return comparable base names for a class base expression."""
    name = base_name(node)
    if not name:
        return ()
    return (name, name.split(".")[-1])


def algorithm_protocol_import_aliases(
    tree: ast.Module,
) -> tuple[set[str], dict[str, str]]:
    """Return AST-proven aliases for algorithm module protocol config bases."""
    module_aliases: set[str] = set()
    class_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PROTOCOL_MODULE or alias.name.endswith(
                    ".algorithm_module_protocol"
                ):
                    module_aliases.add(alias.asname or alias.name)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        module_name = node.module or ""
        imports_protocol_module = (
            module_name == PROTOCOL_MODULE
            or module_name.endswith(".algorithm_module_protocol")
        )
        for alias in node.names:
            alias_name = alias.asname or alias.name
            if imports_protocol_module and alias.name in CONFIG_BASE_KINDS:
                class_aliases[alias_name] = CONFIG_BASE_KINDS[alias.name]
            if alias.name == "algorithm_module_protocol":
                module_aliases.add(alias_name)
    return module_aliases, class_aliases


def direct_config_class_kind(
    node: ast.ClassDef,
    *,
    protocol_module_aliases: set[str],
    protocol_class_aliases: dict[str, str],
) -> str | None:
    """Return the direct amp config kind for one class base list."""
    bases = {name for base in node.bases for name in base_names(base)}
    for base in bases:
        direct_alias = protocol_class_aliases.get(base)
        if direct_alias is not None:
            return direct_alias
        parts = base.split(".")
        if len(parts) < 2:
            continue
        owner = ".".join(parts[:-1])
        kind = CONFIG_BASE_KINDS.get(parts[-1])
        if kind is not None and owner in protocol_module_aliases:
            return kind
    return None


def class_base_names(node: ast.ClassDef) -> tuple[str, ...]:
    """Return comparable names for all direct bases."""
    return tuple(name for base in node.bases for name in base_names(base))


def config_class_kinds(tree: ast.Module) -> dict[str, str]:
    """Resolve config class ownership from AST inheritance only."""
    protocol_module_aliases, protocol_class_aliases = algorithm_protocol_import_aliases(tree)
    by_name: dict[str, ast.ClassDef] = {}

    def collect_classes(body: list[ast.stmt], prefix: tuple[str, ...] = ()) -> None:
        for item in body:
            if not isinstance(item, ast.ClassDef):
                continue
            dotted = ".".join((*prefix, item.name))
            by_name[dotted] = item
            if not prefix:
                by_name[item.name] = item
            collect_classes(item.body, (*prefix, item.name))

    collect_classes(tree.body)
    resolved: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for name, node in by_name.items():
            if name in resolved:
                continue
            direct = direct_config_class_kind(
                node,
                protocol_module_aliases=protocol_module_aliases,
                protocol_class_aliases=protocol_class_aliases,
            )
            if direct is not None:
                resolved[name] = direct
                changed = True
                continue
            for base in class_base_names(node):
                base_tail = base.split(".")[-1]
                if base in resolved:
                    resolved[name] = resolved[base]
                    changed = True
                    break
                if "." not in base and base_tail in resolved:
                    resolved[name] = resolved[base_tail]
                    changed = True
                    break
    return resolved


def module_names_for_path(root: Path, path: Path) -> tuple[str, ...]:
    """Return likely importable module names for one Python file."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path.resolve()
    if relative.suffix != ".py":
        return ()
    parts = list(relative.with_suffix("").parts)
    candidates: list[str] = []
    for start in (0, 1 if parts[:1] == ["python"] else -1):
        if start < 0:
            continue
        module_parts = parts[start:]
        if module_parts[-1:] == ["__init__"]:
            module_parts = module_parts[:-1]
        if module_parts:
            candidates.append(".".join(module_parts))
    return tuple(dict.fromkeys(candidates))


def primary_module_name(root: Path, path: Path) -> str:
    """Return the best module name for relative import resolution."""
    names = module_names_for_path(root, path)
    return names[0] if names else ""


def resolve_import_from_module(current_module: str, level: int, module: str | None) -> str:
    """Resolve an ImportFrom module string relative to the current file module."""
    if level <= 0:
        return module or ""
    parts = current_module.split(".")[:-1]
    for _ in range(level - 1):
        if parts:
            parts.pop()
    if module:
        parts.extend(part for part in module.split(".") if part)
    return ".".join(parts)


def build_module_config_index(
    root: Path,
    files: list[Path],
) -> dict[str, dict[str, str]]:
    """Map importable module names to amp-derived config classes."""
    module_index: dict[str, dict[str, str]] = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        kinds = config_class_kinds(tree)
        if not kinds:
            continue
        for module_name in module_names_for_path(root, path):
            module_index[module_name] = kinds
    return module_index


def import_context(
    tree: ast.Module,
    *,
    current_module: str,
    module_index: dict[str, dict[str, str]],
) -> ImportContext:
    """Build AST import aliases for config class resolution."""
    module_aliases: dict[str, str] = {}
    class_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[0]
                if alias.name in module_index:
                    module_aliases[alias_name] = alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        module_name = resolve_import_from_module(
            current_module,
            node.level,
            node.module,
        )
        for alias in node.names:
            if alias.name == "*":
                continue
            alias_name = alias.asname or alias.name
            imported_module = f"{module_name}.{alias.name}" if module_name else alias.name
            if imported_module in module_index:
                module_aliases[alias_name] = imported_module
                continue
            config_kind = module_index.get(module_name, {}).get(alias.name)
            if config_kind is not None:
                class_aliases[alias_name] = config_kind
    return ImportContext(module_aliases=module_aliases, class_aliases=class_aliases)


def config_kind_for_expr(
    node: ast.AST,
    *,
    local_config_kinds: dict[str, str],
    imports: ImportContext,
    module_index: dict[str, dict[str, str]],
) -> str | None:
    """Return config kind for an expression resolved through AST imports."""
    if isinstance(node, ast.Name):
        return local_config_kinds.get(node.id) or imports.class_aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        expression_name = dotted_name(node)
        local_kind = local_config_kinds.get(expression_name)
        if local_kind is not None:
            return local_kind
        parts = expression_name.split(".")
        if len(parts) >= 2:
            first = parts[0]
            if first in imports.module_aliases:
                module_name = ".".join([imports.module_aliases[first], *parts[1:-1]])
                config_kind = module_index.get(module_name, {}).get(parts[-1])
                if config_kind is not None:
                    return config_kind
            module_name = ".".join(parts[:-1])
            config_kind = module_index.get(module_name, {}).get(parts[-1])
            if config_kind is not None:
                return config_kind
    if isinstance(node, ast.Subscript):
        return config_kind_for_expr(
            node.value,
            local_config_kinds=local_config_kinds,
            imports=imports,
            module_index=module_index,
        )
    return None


def config_kinds_in_expr(
    node: ast.AST,
    *,
    local_config_kinds: dict[str, str],
    imports: ImportContext,
    module_index: dict[str, dict[str, str]],
) -> tuple[str, ...]:
    """Return every amp config kind referenced by an annotation expression."""
    kinds: set[str] = set()
    direct = config_kind_for_expr(
        node,
        local_config_kinds=local_config_kinds,
        imports=imports,
        module_index=module_index,
    )
    if direct is not None:
        kinds.add(direct)
    for child in ast.iter_child_nodes(node):
        kinds.update(
            config_kinds_in_expr(
                child,
                local_config_kinds=local_config_kinds,
                imports=imports,
                module_index=module_index,
            )
        )
    return tuple(sorted(kinds))


def attach_parents(tree: ast.AST) -> None:
    """Attach parent pointers for local AST context checks."""
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            setattr(child, "_parent", node)


def parent(node: ast.AST) -> ast.AST | None:
    """Return the parent pointer when present."""
    candidate = getattr(node, "_parent", None)
    return candidate if isinstance(candidate, ast.AST) else None


def enclosing_scope(node: ast.AST) -> str:
    """Return the nearest class/function scope name."""
    names: list[str] = []
    current = parent(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(current.name)
        current = parent(current)
    return ".".join(reversed(names)) if names else "<module>"


def enclosing_config_owner(node: ast.AST, config_kinds: dict[str, str]) -> str:
    """Return the enclosing config owner or an empty string."""
    current = parent(node)
    while current is not None:
        if isinstance(current, ast.ClassDef):
            kind = config_kinds.get(current.name)
            if kind is not None:
                return kind
        current = parent(current)
    return ""


def dotted_name(node: ast.AST) -> str:
    """Return a dotted call or attribute name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    return ""


def is_literalish_default(
    node: ast.AST | None,
    *,
    local_config_kinds: dict[str, str] | None = None,
    imports: ImportContext | None = None,
    module_index: dict[str, dict[str, str]] | None = None,
) -> bool:
    """Return true for expressions that encode a concrete default value."""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return node.value is not Ellipsis
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return is_literalish_default(
            node.operand,
            local_config_kinds=local_config_kinds,
            imports=imports,
            module_index=module_index,
        )
    if isinstance(node, ast.Call):
        name = dotted_name(node.func)
        if name in {"dict", "list", "set", "tuple"}:
            return True
        if (
            local_config_kinds is None
            or imports is None
            or module_index is None
        ):
            return False
        return (
            config_kind_for_expr(
                node.func,
                local_config_kinds=local_config_kinds,
                imports=imports,
                module_index=module_index,
            )
            is not None
        )
    return False


def field_default_kind(
    node: ast.AST,
    *,
    local_config_kinds: dict[str, str],
    imports: ImportContext,
    module_index: dict[str, dict[str, str]],
) -> tuple[str, ast.AST] | None:
    """Return default kind and value node for an assignment expression."""
    value: ast.AST | None = None
    if isinstance(node, ast.AnnAssign):
        value = node.value
    elif isinstance(node, ast.Assign):
        value = node.value
    if value is None:
        return None
    if isinstance(value, ast.Call) and dotted_name(value.func).endswith("field"):
        for keyword in value.keywords:
            if keyword.arg in {"default", "default_factory"}:
                return f"field-{keyword.arg}", keyword.value
        return None
    if is_literalish_default(
        value,
        local_config_kinds=local_config_kinds,
        imports=imports,
        module_index=module_index,
    ):
        return "assigned-default", value
    return None


def target_name(node: ast.AST) -> str:
    """Return a stable target name for assignments."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.Assign):
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        return ",".join(names) if names else "<assignment>"
    return "<assignment>"


def is_module_constant_assignment(node: ast.AST) -> bool:
    """Return true for module-level named constants, not hidden defaults."""
    if not isinstance(parent(node), ast.Module):
        return False
    names: list[str] = []
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    if isinstance(node, ast.Assign):
        names.extend(target.id for target in node.targets if isinstance(target, ast.Name))
    return bool(names) and all(name.isupper() or name.startswith("__") for name in names)


def function_default_findings(
    root: Path,
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    config_kinds: dict[str, str],
) -> list[DefaultFinding]:
    """Return findings for callable parameter defaults."""
    findings: list[DefaultFinding] = []
    relative = relative_path(root, path)
    scope = enclosing_scope(node)
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaulted_positional = positional[len(positional) - len(node.args.defaults) :]
    for arg, default in zip(defaulted_positional, node.args.defaults, strict=False):
        findings.append(
            DefaultFinding(
                path=relative,
                line=getattr(default, "lineno", node.lineno),
                scope=scope,
                kind="parameter-default",
                name=arg.arg,
                owner=enclosing_config_owner(node, config_kinds) or "runtime",
                severity="error",
                reason="callable parameter supplies a code default outside config ownership",
                guidance=(
                    "move the value into InitializeConfig/SolveConfig "
                    "or require the caller to pass it explicitly"
                ),
            )
        )
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False):
        if default is None:
            continue
        findings.append(
            DefaultFinding(
                path=relative,
                line=getattr(default, "lineno", node.lineno),
                scope=scope,
                kind="keyword-parameter-default",
                name=arg.arg,
                owner=enclosing_config_owner(node, config_kinds) or "runtime",
                severity="error",
                reason="keyword-only parameter supplies a code default outside config ownership",
                guidance=(
                    "move the value into InitializeConfig/SolveConfig "
                    "or require the caller to pass it explicitly"
                ),
            )
        )
    return findings


class ConfigDefaultVisitor(ast.NodeVisitor):
    """Collect hidden runtime defaults."""

    def __init__(
        self,
        *,
        root: Path,
        path: Path,
        config_kinds: dict[str, str],
        imports: ImportContext,
        module_index: dict[str, dict[str, str]],
    ) -> None:
        """Store file-local AST resolution context for default detection."""
        self.root = root
        self.path = path
        self.relative = relative_path(root, path)
        self.config_kinds = config_kinds
        self.imports = imports
        self.module_index = module_index
        self.findings: list[DefaultFinding] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Check function parameter defaults."""
        self.findings.extend(
            function_default_findings(self.root, self.path, node, self.config_kinds)
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Check async function parameter defaults."""
        self.findings.extend(
            function_default_findings(self.root, self.path, node, self.config_kinds)
        )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """Check annotated field defaults."""
        self._record_assignment_default(node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Check assigned field defaults."""
        self._record_assignment_default(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Check implicit-default call idioms."""
        name = dotted_name(node.func)
        default_arg: ast.AST | None = None
        kind = ""
        reason = ""
        if name.endswith(".get") and len(node.args) >= 2:
            default_arg = node.args[1]
            kind = "mapping-get-default"
            reason = "mapping get supplies an implicit value outside config ownership"
        elif name == "getattr" and len(node.args) >= 3:
            default_arg = node.args[2]
            kind = "getattr-default"
            reason = "getattr supplies an implicit value outside config ownership"
        elif name.endswith(".setdefault") and len(node.args) >= 2:
            default_arg = node.args[1]
            kind = "setdefault-default"
            reason = "setdefault creates an implicit value outside config ownership"
        elif (
            config_kind_for_expr(
                node.func,
                local_config_kinds=self.config_kinds,
                imports=self.imports,
                module_index=self.module_index,
            )
            is not None
            and not node.args
            and not node.keywords
        ):
            default_arg = node
            kind = "empty-config-constructor"
            reason = "config constructor is called without explicit fields"
        if default_arg is not None:
            self.findings.append(
                DefaultFinding(
                    path=self.relative,
                    line=getattr(default_arg, "lineno", node.lineno),
                    scope=enclosing_scope(node),
                    kind=kind,
                    name=name,
                    owner=enclosing_config_owner(node, self.config_kinds) or "runtime",
                    severity="error",
                    reason=reason,
                    guidance=(
                        "thread the value through InitializeConfig/SolveConfig "
                        "or fail when absent"
                    ),
                )
            )
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        """Check ``x or default`` style implicit runtime defaults."""
        if isinstance(node.op, ast.Or) and len(node.values) >= 2:
            implicit_default = node.values[-1]
            if is_literalish_default(
                implicit_default,
                local_config_kinds=self.config_kinds,
                imports=self.imports,
                module_index=self.module_index,
            ):
                self.findings.append(
                    DefaultFinding(
                        path=self.relative,
                        line=getattr(implicit_default, "lineno", node.lineno),
                        scope=enclosing_scope(node),
                        kind="or-implicit-default",
                        name="<or>",
                        owner=enclosing_config_owner(node, self.config_kinds) or "runtime",
                        severity="error",
                        reason="boolean or supplies an implicit value outside config ownership",
                        guidance=(
                            "thread the value through InitializeConfig/SolveConfig "
                            "or fail when absent"
                        ),
                    )
                )
        self.generic_visit(node)

    def _record_assignment_default(self, node: ast.AST) -> None:
        if not isinstance(parent(node), ast.ClassDef):
            return
        owner = enclosing_config_owner(node, self.config_kinds)
        if not owner:
            return
        default = field_default_kind(
            node,
            local_config_kinds=self.config_kinds,
            imports=self.imports,
            module_index=self.module_index,
        )
        if default is None or is_module_constant_assignment(node):
            return
        kind, value = default
        self.findings.append(
            DefaultFinding(
                path=self.relative,
                line=getattr(value, "lineno", getattr(node, "lineno", 1)),
                scope=enclosing_scope(node),
                kind=kind,
                name=target_name(node),
                owner=owner,
                severity="warn",
                reason="config class owns this default value",
                guidance=(
                    "make this field required if caller-specific configuration must be explicit"
                ),
            )
        )


def class_fields(
    root: Path,
    path: Path,
    tree: ast.Module,
    config_kinds: dict[str, str],
    imports: ImportContext,
    module_index: dict[str, dict[str, str]],
) -> list[ConfigField]:
    """Return annotated fields from algorithm config classes."""
    fields: list[ConfigField] = []
    relative = relative_path(root, path)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        kind = config_kinds.get(node.name)
        if kind is None:
            continue
        for item in node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            fields.append(
                ConfigField(
                    path=relative,
                    line=item.lineno,
                    class_name=kind,
                    field=item.target.id,
                    annotation=annotation_text(item.annotation),
                    annotation_config_kinds=config_kinds_in_expr(
                        item.annotation,
                        local_config_kinds=config_kinds,
                        imports=imports,
                        module_index=module_index,
                    ),
                )
            )
    return fields


def field_findings(field: ConfigField) -> list[Finding]:
    """Return config partition findings for one field."""
    if field.class_name == "SolveConfig":
        if field.field in INITIALIZE_ONLY_FIELD_NAMES:
            return [
                Finding(
                    path=field.path,
                    line=field.line,
                    class_name=field.class_name,
                    field=field.field,
                    annotation=field.annotation,
                    expected_owner="InitializeConfig",
                    reason="initialization-only field name in SolveConfig",
                )
            ]
        if "InitializeConfig" in field.annotation_config_kinds:
            return [
                Finding(
                    path=field.path,
                    line=field.line,
                    class_name=field.class_name,
                    field=field.field,
                    annotation=field.annotation,
                    expected_owner="InitializeConfig",
                    reason="initialization-only config type in SolveConfig",
                )
            ]
    if field.class_name == "InitializeConfig":
        if field.field in RUNTIME_ONLY_FIELD_NAMES:
            return [
                Finding(
                    path=field.path,
                    line=field.line,
                    class_name=field.class_name,
                    field=field.field,
                    annotation=field.annotation,
                    expected_owner="SolveConfig",
                    reason="runtime-only field name in InitializeConfig",
                )
            ]
        if "SolveConfig" in field.annotation_config_kinds:
            return [
                Finding(
                    path=field.path,
                    line=field.line,
                    class_name=field.class_name,
                    field=field.field,
                    annotation=field.annotation,
                    expected_owner="SolveConfig",
                    reason="runtime-only config type in InitializeConfig",
                )
            ]
    return []


def scan_file(
    root: Path,
    path: Path,
    module_index: dict[str, dict[str, str]],
) -> tuple[list[ConfigField], list[Finding], list[DefaultFinding]]:
    """Scan one Python file for config partition findings."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        finding = Finding(
            path=relative_path(root, path),
            line=exc.lineno or 1,
            class_name="<syntax-error>",
            field="<syntax-error>",
            annotation="",
            expected_owner="fix-syntax",
            reason="syntax error prevents config partition analysis",
        )
        return [], [finding], []
    attach_parents(tree)
    config_kinds = config_class_kinds(tree)
    imports = import_context(
        tree,
        current_module=primary_module_name(root, path),
        module_index=module_index,
    )
    fields = class_fields(root, path, tree, config_kinds, imports, module_index)
    findings = [finding for field in fields for finding in field_findings(field)]
    visitor = ConfigDefaultVisitor(
        root=root,
        path=path,
        config_kinds=config_kinds,
        imports=imports,
        module_index=module_index,
    )
    visitor.visit(tree)
    return fields, findings, visitor.findings


def main() -> int:
    """Run the checker."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    files = iter_python_files(root, args.paths, args.exclude)
    module_index = build_module_config_index(root, files)
    all_fields: list[ConfigField] = []
    all_findings: list[Finding] = []
    all_default_findings: list[DefaultFinding] = []
    for path in files:
        fields, findings, default_findings = scan_file(root, path, module_index)
        all_fields.extend(fields)
        all_findings.extend(findings)
        all_default_findings.extend(default_findings)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "summary": {
                        "fields": len(all_fields),
                        "findings": len(all_findings),
                        "default_findings": len(all_default_findings),
                        "runtime_default_errors": sum(
                            1
                            for finding in all_default_findings
                            if finding.severity == "error"
                        ),
                        "config_default_warnings": sum(
                            1
                            for finding in all_default_findings
                            if finding.severity == "warn"
                        ),
                    },
                    "fields": [asdict(field) for field in all_fields],
                    "findings": [asdict(finding) for finding in all_findings],
                    "default_findings": [
                        asdict(finding) for finding in all_default_findings
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in all_findings:
            print(finding.render())
        for finding in all_default_findings:
            print(finding.render())
        print(f"ALGORITHM_CONFIG_PARTITION_FIELDS={len(all_fields)}")
        print(f"ALGORITHM_CONFIG_PARTITION_FINDINGS={len(all_findings)}")
        print(f"ALGORITHM_CONFIG_DEFAULT_FINDINGS={len(all_default_findings)}")
        runtime_default_errors = sum(
            1 for finding in all_default_findings if finding.severity == "error"
        )
        print(f"ALGORITHM_CONFIG_RUNTIME_DEFAULT_ERRORS={runtime_default_errors}")
        status = "fail" if all_findings or runtime_default_errors else "pass"
        print(f"ALGORITHM_CONFIG_PARTITION={status}")
    default_errors = [
        finding for finding in all_default_findings if finding.severity == "error"
    ]
    if args.fail_on_finding and all_findings:
        return 1
    if args.fail_on_default and default_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
