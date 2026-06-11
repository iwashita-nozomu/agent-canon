#!/usr/bin/env python3
# @dependency-start
# responsibility Builds Algorithm Expansion IR from Python AST without importing target modules.
# upstream design ../../agents/skills/formal-proof-workflow.md defines Algorithm Expansion IR.
# downstream design ../../documents/tools/algorithm_expansion_ir.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_algorithm_expansion_ir.py tests it.
# @dependency-end
"""Build an Algorithm Expansion IR from Python AST source."""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

PythonSymbol = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
BUILTIN_BOOKKEEPING_CALLS = frozenset(
    {
        "abs",
        "bool",
        "dict",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "range",
        "set",
        "str",
        "tuple",
    }
)
STATIC_INSTANCE_EDGE_KINDS = frozenset(
    {
        "instance_constructs",
        "instance_method_call",
        "callable_argument",
        "callable_variant",
    }
)
STATIC_EDGE_STATUSES = frozenset(
    {
        "statically_checked",
        "static_checker_required",
        "static_resolution_gap",
    }
)


@dataclass(frozen=True)
class IRNode:
    """One algorithm IR node."""

    node_id: str
    source_path: str
    source_symbol: str
    source_span: str
    node_kind: str
    lineno: int
    end_lineno: int | None
    math_role: str
    runtime_object: str
    residual_unit: str
    precision_model: str
    iteration_scope: str
    equation_tags: tuple[str, ...]
    proof_relevance: str
    selected_obligation_id: str | None
    assumption_id: str | None
    status: str


@dataclass(frozen=True)
class IREdge:
    """One algorithm IR edge."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_kind: str
    source_symbol: str
    target_symbol: str
    call_text: str
    line: int
    assigned_to: tuple[str, ...]
    receiver_name: str | None
    receiver_type: str | None
    child_config_field: str | None
    child_initialize: str | None
    proof_scope: str | None
    selection_rule: str
    role: str
    quantity_flow: str | None
    unit_conversion: str | None
    resolved: bool
    status: str


@dataclass(frozen=True)
class IRObligation:
    """One theorem-directed local proof obligation."""

    obligation_id: str
    statement: str
    grain: str
    consumes_nodes: tuple[str, ...]
    consumes_edges: tuple[str, ...]
    existing_proof_search: tuple[str, ...]
    checker_route: str
    remaining_gap: str
    status: str


@dataclass(frozen=True)
class IRStaticCheck:
    """One static check discharged before mathematical proof selection."""

    check_id: str
    edge_id: str
    check_kind: str
    source_symbol: str
    target_symbol: str
    evidence: str
    status: str
    proof_effect: str


@dataclass(frozen=True)
class IRBackendAssumption:
    """One proof-only backend arithmetic assumption overlay."""

    assumption_id: str
    statement: str
    profile_variable: str
    profile_library_path: str
    profile_ids: tuple[str, ...]
    profile_details: dict[str, dict[str, object]]
    owning_surface: str
    scope: str
    applies_to_nodes: tuple[str, ...]
    required_witnesses: tuple[str, ...]
    checker_route: str
    status: str


@dataclass(frozen=True)
class IRCodeFact:
    """One AST-derived equation, default, or constant fact."""

    fact_id: str
    source_path: str
    source_symbol: str
    source_node_id: str | None
    source_span: str
    fact_kind: str
    target: str
    expression: str
    expression_ast: dict[str, Any]
    statement: str
    equation_tags: tuple[str, ...]
    target_profiles: tuple[str, ...]


@dataclass(frozen=True)
class IRControlFact:
    """One AST-derived branch or loop control fact."""

    fact_id: str
    source_path: str
    source_symbol: str
    source_node_id: str | None
    source_span: str
    control_kind: str
    condition: str | None
    condition_ast: dict[str, Any] | None
    target: str | None
    target_ast: dict[str, Any] | None
    iterator: str | None
    iterator_ast: dict[str, Any] | None
    body_targets: tuple[str, ...]
    orelse_targets: tuple[str, ...]
    statement: str


@dataclass(frozen=True)
class ImportBinding:
    """One import alias visible in a parsed module."""

    alias: str
    module: str
    imported_name: str | None
    module_path: Path | None
    import_kind: str


@dataclass(frozen=True)
class AlgorithmIRReport:
    """Machine-readable Algorithm Expansion IR report."""

    status: str
    root_path: str
    root_symbol: str
    target_theorem: str
    backend_profile_library: str
    nodes: tuple[IRNode, ...]
    edges: tuple[IREdge, ...]
    code_facts: tuple[IRCodeFact, ...]
    control_facts: tuple[IRControlFact, ...]
    static_checks: tuple[IRStaticCheck, ...]
    backend_assumptions: tuple[IRBackendAssumption, ...]
    obligations: tuple[IRObligation, ...]
    goal_directed_slice: tuple[str, ...]
    selected_local_obligations: tuple[str, ...]


@dataclass(frozen=True)
class ModuleIndex:
    """AST symbol index for one Python module."""

    path: Path
    relative_path: str
    tree: ast.Module
    symbols: dict[str, PythonSymbol]
    class_methods: dict[str, dict[str, PythonSymbol]]
    class_attribute_types: dict[str, dict[str, str]]
    import_aliases: frozenset[str]
    import_bindings: dict[str, ImportBinding]


@dataclass(frozen=True)
class CallSite:
    """One call expression with assignment context."""

    call: ast.Call
    assigned_to: tuple[str, ...]


@dataclass(frozen=True)
class CallableReferenceSite:
    """One callable expression passed as a value to another call."""

    expression: ast.Attribute
    parent_call: ast.Call


@dataclass(frozen=True)
class ResolvedCall:
    """Resolved call target, possibly from another parsed module."""

    symbol: str
    resolved: bool
    receiver_name: str | None
    receiver_type: str | None
    index: ModuleIndex | None


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root used to relativize paths.",
    )
    parser.add_argument(
        "--python-symbol",
        required=True,
        help="Root algorithm symbol in path.py::qualname form.",
    )
    parser.add_argument(
        "--import-root",
        action="append",
        default=[],
        help=(
            "Additional source root used for AST-only import resolution. "
            "May be passed multiple times."
        ),
    )
    parser.add_argument(
        "--target-theorem",
        default="final_target_theorem",
        help=(
            "Name or short statement of the final theorem used to label "
            "goal-directed local obligations."
        ),
    )
    parser.add_argument(
        "--backend-profile-library",
        default="lean/lib/backend_profiles.json",
        help=(
            "Proof-only backend profile library read by the IR builder. "
            "This is not production optimizer configuration."
        ),
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
    )
    parser.add_argument(
        "--out",
        help="Optional output path. When omitted, print to stdout.",
    )
    return parser


def parse_python_symbol_reference(reference: str) -> tuple[Path, str]:
    """Parse a ``path.py::qualname`` reference."""
    if "::" not in reference:
        raise ValueError("--python-symbol must use path.py::qualname syntax")
    raw_path, raw_qualname = reference.split("::", 1)
    path = Path(raw_path.strip())
    qualname = raw_qualname.strip()
    if not str(path):
        raise ValueError("--python-symbol path is empty")
    if not qualname:
        raise ValueError("--python-symbol qualname is empty")
    return path, qualname


def load_backend_profile_library(path: Path | None) -> dict[str, object]:
    """Load a proof-only backend profile library if one is available."""
    if path is None or not str(path):
        return {}
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("backend profile library must be a JSON object")
    profiles = payload.get("profiles")
    if profiles is not None and not isinstance(profiles, dict):
        raise ValueError("backend profile library `profiles` must be a JSON object")
    return payload


def backend_profile_ids(profile_library: dict[str, object]) -> tuple[str, ...]:
    """Return profile ids from a proof-only profile library."""
    profiles = profile_library.get("profiles")
    if not isinstance(profiles, dict):
        return ()
    return tuple(str(key) for key in sorted(profiles))


def backend_profile_details(profile_library: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return stable profile detail payloads from a proof-only profile library."""
    profiles = profile_library.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    details: dict[str, dict[str, object]] = {}
    for profile_id, raw_profile in sorted(profiles.items()):
        if isinstance(raw_profile, dict):
            details[str(profile_id)] = {
                str(key): value for key, value in sorted(raw_profile.items())
            }
    return details


def backend_required_witnesses(profile_library: dict[str, object]) -> tuple[str, ...]:
    """Return the union of required witnesses from the backend profile library."""
    default_witnesses = (
        "dtype",
        "unit_roundoff",
        "numeric_precision_reduction",
        "fast_math_or_contraction_semantics",
        "reassociation_semantics",
        "denormal_mode",
        "minmax_nan_signed_zero_semantics",
        "lowered_ir_or_backend_flag_evidence",
    )
    profiles = profile_library.get("profiles")
    if not isinstance(profiles, dict):
        return default_witnesses
    witnesses: set[str] = set()
    for raw_profile in profiles.values():
        if not isinstance(raw_profile, dict):
            continue
        raw_witnesses = raw_profile.get("required_witnesses")
        if isinstance(raw_witnesses, list | tuple):
            witnesses.update(str(item) for item in raw_witnesses)
    if not witnesses:
        return default_witnesses
    return tuple(sorted(witnesses))


def relative_path(path: Path, root: Path) -> str:
    """Return root-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _unparse(node: ast.AST | None) -> str:
    """Return compact source text for one AST node."""
    if node is None:
        return "None"
    try:
        return " ".join(ast.unparse(node).split())
    except Exception:  # pragma: no cover - defensive for unusual parser nodes.
        return node.__class__.__name__


def _jsonable_value(value: object) -> object:
    """Return a JSON-stable representation for AST scalar values."""
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def ast_to_json(node: object) -> Any:
    """Convert Python AST nodes into a stable JSON tree for Rust lowering."""
    if isinstance(node, ast.AST):
        payload: dict[str, Any] = {"node": type(node).__name__}
        for field in getattr(node, "_fields", ()):
            payload[field] = ast_to_json(getattr(node, field))
        return payload
    if isinstance(node, list | tuple):
        return [ast_to_json(item) for item in node]
    return _jsonable_value(node)


def candidate_source_roots(root: Path, import_roots: tuple[Path, ...] = ()) -> tuple[Path, ...]:
    """Return likely Python source roots for import resolution."""
    candidates = [root]
    for name in ("python", "src"):
        path = root / name
        if path.exists():
            candidates.append(path)
    candidates.extend(import_roots)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(candidate)
    return tuple(deduped)


def source_root_for_path(path: Path, root: Path, import_roots: tuple[Path, ...]) -> Path:
    """Return the deepest known source root containing a module path."""
    resolved = path.resolve()
    matches: list[Path] = []
    for candidate in candidate_source_roots(root, import_roots):
        try:
            resolved.relative_to(candidate.resolve())
        except ValueError:
            continue
        matches.append(candidate)
    return max(matches, key=lambda item: len(item.resolve().parts), default=root)


def module_path_for_name(
    root: Path,
    import_roots: tuple[Path, ...],
    module_name: str,
) -> Path | None:
    """Resolve a dotted module name to an AST-readable Python path."""
    if not module_name:
        return None
    module_parts = module_name.split(".")
    for source_root in candidate_source_roots(root, import_roots):
        module_base = source_root.joinpath(*module_parts)
        for candidate in (module_base.with_suffix(".py"), module_base / "__init__.py"):
            if candidate.exists():
                return candidate
    return None


def package_parts_for_path(
    path: Path,
    root: Path,
    import_roots: tuple[Path, ...],
) -> tuple[str, ...]:
    """Return package parts for a module path under a source root."""
    source_root = source_root_for_path(path, root, import_roots)
    try:
        relative = path.resolve().relative_to(source_root.resolve())
    except ValueError:
        relative = path
    if relative.name == "__init__.py":
        return tuple(relative.parent.parts)
    return tuple(relative.with_suffix("").parent.parts)


def resolve_import_from_module(
    current_path: Path,
    root: Path,
    import_roots: tuple[Path, ...],
    module: str | None,
    level: int,
) -> str:
    """Resolve an ImportFrom module name, including relative import levels."""
    module_parts = tuple(part for part in (module or "").split(".") if part)
    if level <= 0:
        return ".".join(module_parts)
    package_parts = package_parts_for_path(current_path, root, import_roots)
    keep_count = max(len(package_parts) - (level - 1), 0)
    return ".".join((*package_parts[:keep_count], *module_parts))


def load_module_index(path: Path, root: Path, import_roots: tuple[Path, ...] = ()) -> ModuleIndex:
    """Parse one Python module and index classes/functions by qualname."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Python AST parse failed for {path}: {exc.msg}") from exc

    symbols: dict[str, PythonSymbol] = {}
    class_methods: dict[str, dict[str, PythonSymbol]] = {}
    class_attribute_types: dict[str, dict[str, str]] = {}
    import_aliases: set[str] = set()
    import_bindings: dict[str, ImportBinding] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                alias_name = alias.asname or alias.name.split(".", 1)[0]
                import_aliases.add(alias_name)
                import_bindings[alias_name] = ImportBinding(
                    alias=alias_name,
                    module=alias.name,
                    imported_name=None,
                    module_path=module_path_for_name(root, import_roots, alias.name),
                    import_kind="import",
                )
        elif isinstance(stmt, ast.ImportFrom):
            module_name = resolve_import_from_module(
                current_path=path,
                root=root,
                import_roots=import_roots,
                module=stmt.module,
                level=stmt.level,
            )
            for alias in stmt.names:
                if alias.name == "*":
                    continue
                alias_name = alias.asname or alias.name
                submodule_name = ".".join(part for part in (module_name, alias.name) if part)
                submodule_path = module_path_for_name(root, import_roots, submodule_name)
                module_path = submodule_path or module_path_for_name(
                    root,
                    import_roots,
                    module_name,
                )
                import_aliases.add(alias_name)
                import_bindings[alias_name] = ImportBinding(
                    alias=alias_name,
                    module=submodule_name if submodule_path else module_name,
                    imported_name=None if submodule_path else alias.name,
                    module_path=module_path,
                    import_kind="from_import",
                )

    def visit_body(body: Iterable[ast.stmt], prefix: tuple[str, ...]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                qualname = ".".join((*prefix, stmt.name))
                symbols[qualname] = stmt
                methods: dict[str, PythonSymbol] = {}
                attributes: dict[str, str] = {}
                for child in stmt.body:
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                        child_qualname = f"{qualname}.{child.name}"
                        symbols[child_qualname] = child
                        methods[child.name] = child
                    elif isinstance(child, ast.AnnAssign) and isinstance(
                        child.target,
                        ast.Name,
                    ):
                        attributes[child.target.id] = _unparse(child.annotation)
                class_methods[qualname] = methods
                class_attribute_types[qualname] = attributes
                visit_body(stmt.body, (*prefix, stmt.name))
            elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                qualname = ".".join((*prefix, stmt.name))
                symbols[qualname] = stmt
                visit_body(stmt.body, (*prefix, stmt.name))

    visit_body(tree.body, ())
    return ModuleIndex(
        path=path,
        relative_path=relative_path(path, root),
        tree=tree,
        symbols=symbols,
        class_methods=class_methods,
        class_attribute_types=class_attribute_types,
        import_aliases=frozenset(import_aliases),
        import_bindings=import_bindings,
    )


def find_symbol(index: ModuleIndex, qualname: str) -> PythonSymbol:
    """Find a symbol in one module index."""
    symbol = index.symbols.get(qualname)
    if symbol is None:
        raise ValueError(f"Python AST symbol not found: {qualname}")
    return symbol


def node_id_for(qualname: str) -> str:
    """Return a stable node id."""
    qualname = qualname.replace(".", "__").replace("<", "").replace(">", "")
    return "".join(char if char.isalnum() or char == "_" else "_" for char in qualname)


def id_fragment(value: str) -> str:
    """Return a stable lower-case id fragment."""
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "value"


def node_id_for_ref(index: ModuleIndex, qualname: str) -> str:
    """Return a stable node id for one source path and qualname."""
    return node_id_for(f"{index.relative_path}::{qualname}")


def external_node_id(call_text: str) -> str:
    """Return a stable external node id."""
    normalized = (
        call_text.replace(".", "__")
        .replace("(", "_")
        .replace(")", "_")
        .replace("[", "_")
        .replace("]", "_")
        .replace(" ", "_")
    )
    return f"external__{normalized}"


def type_name_from_annotation(node: ast.AST | None) -> str | None:
    """Return a simple type name from an annotation expression."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return None if node.id in {"Any", "None"} else node.id
    if isinstance(node, ast.Attribute):
        return _unparse(node)
    if isinstance(node, ast.Subscript):
        return type_name_from_annotation(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = type_name_from_annotation(node.left)
        return left or type_name_from_annotation(node.right)
    return None


def simple_name_from_call(func: ast.AST) -> str:
    """Return the leaf name for a call target."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return _unparse(func)


def dotted_name(node: ast.AST) -> str:
    """Return a source-like dotted name for an expression."""
    return _unparse(node)


def receiver_name(func: ast.AST) -> str | None:
    """Return the receiver name for an attribute call."""
    if isinstance(func, ast.Attribute):
        value = func.value
        if isinstance(value, ast.Name):
            return value.id
    return None


def assigned_names(target: ast.AST) -> tuple[str, ...]:
    """Return assigned variable names from one assignment target."""
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, ast.Tuple | ast.List):
        names: list[str] = []
        for element in target.elts:
            names.extend(assigned_names(element))
        return tuple(names)
    if isinstance(target, ast.Attribute):
        return (_unparse(target),)
    return ()


def collect_call_sites(node: PythonSymbol) -> tuple[CallSite, ...]:
    """Collect call expressions with shallow assignment context."""
    sites: list[CallSite] = []

    class Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            names: list[str] = []
            for target in node.targets:
                names.extend(assigned_names(target))
            for child in ast.walk(node.value):
                if isinstance(child, ast.Call):
                    sites.append(CallSite(child, tuple(names)))
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            names = assigned_names(node.target)
            if node.value is not None:
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Call):
                        sites.append(CallSite(child, names))
            self.generic_visit(node)

        def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
            if node.value is not None:
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Call):
                        sites.append(CallSite(child, ()))
            self.generic_visit(node)

        def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
            for child in ast.walk(node.value):
                if isinstance(child, ast.Call):
                    sites.append(CallSite(child, ()))
            self.generic_visit(node)

    Visitor().visit(node)
    deduped: list[CallSite] = []
    seen: set[tuple[int, int, str, tuple[str, ...]]] = set()
    for site in sites:
        key = (
            int(getattr(site.call, "lineno", 0)),
            int(getattr(site.call, "col_offset", 0)),
            _unparse(site.call),
            site.assigned_to,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(site)
    return tuple(deduped)


def collect_callable_reference_sites(node: PythonSymbol) -> tuple[CallableReferenceSite, ...]:
    """Collect attribute references passed as callable values."""
    sites: list[CallableReferenceSite] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        for arg in (*child.args, *(keyword.value for keyword in child.keywords)):
            if isinstance(arg, ast.Attribute):
                sites.append(CallableReferenceSite(arg, child))
    deduped: list[CallableReferenceSite] = []
    seen: set[tuple[int, int, str]] = set()
    for site in sites:
        key = (
            int(getattr(site.expression, "lineno", 0)),
            int(getattr(site.expression, "col_offset", 0)),
            _unparse(site.expression),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(site)
    return tuple(deduped)


def target_texts(target: ast.AST) -> tuple[str, ...]:
    """Return source-like targets for an assignment fact."""
    if isinstance(target, ast.Name | ast.Attribute | ast.Subscript):
        return (_unparse(target),)
    if isinstance(target, ast.Tuple | ast.List):
        names: list[str] = []
        for element in target.elts:
            names.extend(target_texts(element))
        return tuple(names)
    return ()


def equation_tags_for_fact(
    source_symbol: str,
    fact_kind: str,
    target: str,
    expression: str,
) -> tuple[str, ...]:
    """Return equation tags for one AST-derived fact."""
    text = f"{source_symbol} {fact_kind} {target} {expression}"
    return equation_tags_for_symbol(text, fact_kind)


def make_code_fact(
    index: ModuleIndex,
    *,
    source_symbol: str,
    source_node_id: str | None,
    fact_kind: str,
    target: str,
    expression_node: ast.AST,
    line: int,
) -> IRCodeFact:
    """Create one stable code fact from AST source text."""
    expression = _unparse(expression_node)
    tags = equation_tags_for_fact(source_symbol, fact_kind, target, expression)
    fact_id = (
        f"fact__{node_id_for_ref(index, source_symbol)}__{id_fragment(fact_kind)}__"
        f"line_{line}__{id_fragment(target)[:48]}"
    )
    return IRCodeFact(
        fact_id=fact_id,
        source_path=index.relative_path,
        source_symbol=source_symbol,
        source_node_id=source_node_id,
        source_span=f"{line}:None",
        fact_kind=fact_kind,
        target=target,
        expression=expression,
        expression_ast=ast_to_json(expression_node),
        statement=f"`{source_symbol}` {fact_kind} `{target}` as `{expression}`.",
        equation_tags=tags,
        target_profiles=target_profiles_for_equation_tags(tags),
    )


def collect_symbol_code_facts(
    index: ModuleIndex,
    qualname: str,
    symbol: PythonSymbol,
) -> tuple[IRCodeFact, ...]:
    """Collect local assignment and return equations from one expanded symbol."""
    if not isinstance(symbol, ast.FunctionDef | ast.AsyncFunctionDef):
        return ()
    facts: list[IRCodeFact] = []
    source_node_id = node_id_for_ref(index, qualname)

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node is not symbol:
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            if node is not symbol:
                return
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            for target in node.targets:
                for target_text in target_texts(target):
                    facts.append(
                        make_code_fact(
                            index,
                            source_symbol=qualname,
                            source_node_id=source_node_id,
                            fact_kind="assignment_equation",
                            target=target_text,
                            expression_node=node.value,
                            line=int(getattr(node, "lineno", 0)),
                        )
                    )
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            if node.value is None:
                return
            for target_text in target_texts(node.target):
                facts.append(
                    make_code_fact(
                        index,
                        source_symbol=qualname,
                        source_node_id=source_node_id,
                        fact_kind="assignment_equation",
                        target=target_text,
                        expression_node=node.value,
                        line=int(getattr(node, "lineno", 0)),
                    )
                )
            self.generic_visit(node)

        def visit_Return(self, node: ast.Return) -> None:  # noqa: N802
            if node.value is None:
                return
            facts.append(
                make_code_fact(
                    index,
                    source_symbol=qualname,
                source_node_id=source_node_id,
                fact_kind="return_equation",
                target="return",
                expression_node=node.value,
                line=int(getattr(node, "lineno", 0)),
            )
            )
            self.generic_visit(node)

    Visitor().visit(symbol)
    return tuple(facts)


def assignment_targets_in(statements: Iterable[ast.stmt]) -> tuple[str, ...]:
    """Return assignment targets appearing directly in a control body."""
    targets: list[str] = []
    for stmt in statements:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                targets.extend(target_texts(target))
        elif isinstance(stmt, ast.AnnAssign):
            targets.extend(target_texts(stmt.target))
        elif isinstance(stmt, ast.AugAssign):
            targets.extend(target_texts(stmt.target))
    return tuple(targets)


def make_control_fact(
    index: ModuleIndex,
    *,
    source_symbol: str,
    source_node_id: str | None,
    control_kind: str,
    node: ast.If | ast.While | ast.For,
    ordinal: int,
) -> IRControlFact:
    """Create one branch/loop fact from Python AST."""
    line = int(getattr(node, "lineno", 0))
    fact_id = (
        f"control__{node_id_for_ref(index, source_symbol)}__"
        f"{id_fragment(control_kind)}__line_{line}__{ordinal}"
    )
    condition_node: ast.AST | None = None
    target_node: ast.AST | None = None
    iterator_node: ast.AST | None = None
    target_text: str | None = None
    iterator_text: str | None = None
    if isinstance(node, ast.If | ast.While):
        condition_node = node.test
    elif isinstance(node, ast.For):
        target_node = node.target
        iterator_node = node.iter
        target_text = _unparse(node.target)
        iterator_text = _unparse(node.iter)
    subject = _unparse(condition_node) if condition_node is not None else iterator_text
    return IRControlFact(
        fact_id=fact_id,
        source_path=index.relative_path,
        source_symbol=source_symbol,
        source_node_id=source_node_id,
        source_span=f"{line}:None",
        control_kind=control_kind,
        condition=_unparse(condition_node) if condition_node is not None else None,
        condition_ast=ast_to_json(condition_node) if condition_node is not None else None,
        target=target_text,
        target_ast=ast_to_json(target_node) if target_node is not None else None,
        iterator=iterator_text,
        iterator_ast=ast_to_json(iterator_node) if iterator_node is not None else None,
        body_targets=assignment_targets_in(node.body),
        orelse_targets=assignment_targets_in(node.orelse),
        statement=(
            f"`{source_symbol}` {control_kind} at line {line}"
            + (f" over `{subject}`." if subject else ".")
        ),
    )


def collect_symbol_control_facts(
    index: ModuleIndex,
    qualname: str,
    symbol: PythonSymbol,
) -> tuple[IRControlFact, ...]:
    """Collect branch and loop facts from one expanded symbol."""
    if not isinstance(symbol, ast.FunctionDef | ast.AsyncFunctionDef):
        return ()
    facts: list[IRControlFact] = []
    source_node_id = node_id_for_ref(index, qualname)

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node is not symbol:
                return
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            if node is not symbol:
                return
            self.generic_visit(node)

        def visit_If(self, node: ast.If) -> None:  # noqa: N802
            facts.append(
                make_control_fact(
                    index,
                    source_symbol=qualname,
                    source_node_id=source_node_id,
                    control_kind="if",
                    node=node,
                    ordinal=len(facts) + 1,
                )
            )
            self.generic_visit(node)

        def visit_While(self, node: ast.While) -> None:  # noqa: N802
            facts.append(
                make_control_fact(
                    index,
                    source_symbol=qualname,
                    source_node_id=source_node_id,
                    control_kind="while",
                    node=node,
                    ordinal=len(facts) + 1,
                )
            )
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> None:  # noqa: N802
            facts.append(
                make_control_fact(
                    index,
                    source_symbol=qualname,
                    source_node_id=source_node_id,
                    control_kind="for",
                    node=node,
                    ordinal=len(facts) + 1,
                )
            )
            self.generic_visit(node)

    Visitor().visit(symbol)
    return tuple(facts)


def collect_module_static_code_facts(index: ModuleIndex) -> tuple[IRCodeFact, ...]:
    """Collect module constants and class defaults used as proof parameters."""
    facts: list[IRCodeFact] = []
    for stmt in index.tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                for target_text in target_texts(target):
                    if not target_text.startswith("_") and not target_text.isupper():
                        continue
                    facts.append(
                        make_code_fact(
                            index,
                            source_symbol="<module>",
                            source_node_id=None,
                            fact_kind="module_constant",
                            target=target_text,
                            expression_node=stmt.value,
                            line=int(getattr(stmt, "lineno", 0)),
                        )
                    )
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            for target_text in target_texts(stmt.target):
                if not target_text.startswith("_") and not target_text.isupper():
                    continue
                facts.append(
                    make_code_fact(
                        index,
                        source_symbol="<module>",
                        source_node_id=None,
                        fact_kind="module_constant",
                        target=target_text,
                        expression_node=stmt.value,
                        line=int(getattr(stmt, "lineno", 0)),
                    )
                )
        elif isinstance(stmt, ast.ClassDef):
            for child in stmt.body:
                expression_node: ast.AST | None = None
                targets: tuple[str, ...] = ()
                if isinstance(child, ast.Assign):
                    expression_node = child.value
                    targets = tuple(
                        target_text
                        for target in child.targets
                        for target_text in target_texts(target)
                    )
                elif isinstance(child, ast.AnnAssign) and child.value is not None:
                    expression_node = child.value
                    targets = target_texts(child.target)
                if expression_node is None:
                    continue
                class_symbol = stmt.name
                source_node_id = (
                    node_id_for_ref(index, class_symbol)
                    if class_symbol in index.symbols
                    else None
                )
                for target_text in targets:
                    facts.append(
                        make_code_fact(
                            index,
                            source_symbol=class_symbol,
                            source_node_id=source_node_id,
                            fact_kind="class_default",
                            target=target_text,
                            expression_node=expression_node,
                            line=int(getattr(child, "lineno", 0)),
                        )
                    )
    return tuple(facts)


def initial_instance_types(node: PythonSymbol, current_class: str | None) -> dict[str, str]:
    """Infer instance names from simple argument annotations."""
    types: dict[str, str] = {}
    if current_class is not None and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        args = list(node.args.args)
        if args and args[0].arg == "self":
            types["self"] = current_class
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            annotation_name = type_name_from_annotation(arg.annotation)
            if annotation_name:
                types[arg.arg] = annotation_name
    return types


def update_instance_types(
    instance_types: dict[str, str],
    call_target: str,
    assigned_to: tuple[str, ...],
    resolved_symbol: str | None,
    source_index: ModuleIndex,
    target_index: ModuleIndex | None = None,
) -> None:
    """Update instance type facts from constructor calls and annotated returns."""
    if not assigned_to:
        return
    type_index = target_index or source_index
    constructor = resolved_symbol if resolved_symbol in type_index.class_methods else None
    if constructor is None and call_target in type_index.class_methods:
        constructor = call_target
    if constructor is not None:
        for name in assigned_to:
            if "." not in name:
                instance_types[name] = constructor
        return

    if resolved_symbol is None or target_index is None:
        return
    symbol = target_index.symbols.get(resolved_symbol)
    if not isinstance(symbol, ast.FunctionDef | ast.AsyncFunctionDef):
        return
    return_types = return_type_names(symbol)
    if not return_types:
        return
    call_head = call_target.split(".", 1)[0]
    binding = source_index.import_bindings.get(call_head)
    for name, type_name in zip(assigned_to, return_types, strict=False):
        if "." in name:
            continue
        qualified = (
            f"{binding.alias}.{type_name}"
            if binding is not None and type_name in target_index.class_methods
            else type_name
        )
        instance_types[name] = qualified


def return_type_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """Return tuple element type names from a function return annotation."""
    annotation = node.returns
    if annotation is None:
        return ()
    if isinstance(annotation, ast.Subscript):
        base = type_name_from_annotation(annotation.value) or ""
        if base.split(".")[-1] in {"tuple", "Tuple"}:
            slice_node = annotation.slice
            if isinstance(slice_node, ast.Tuple):
                return tuple(
                    name
                    for item in slice_node.elts
                    if (name := type_name_from_annotation(item))
                )
            item_name = type_name_from_annotation(slice_node)
            return (item_name,) if item_name else ()
    name = type_name_from_annotation(annotation)
    return (name,) if name else ()


def current_class_for(qualname: str, index: ModuleIndex) -> str | None:
    """Return the containing class qualname for a method symbol."""
    parts = qualname.split(".")
    if len(parts) < 2:
        return None
    candidate = ".".join(parts[:-1])
    return candidate if candidate in index.class_methods else None


def index_cache_key(path: Path) -> Path:
    """Return a stable cache key for one module path."""
    return path.resolve()


def load_index_for_path(
    path: Path,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ModuleIndex:
    """Load or reuse one AST module index."""
    key = index_cache_key(path)
    cached = module_indexes.get(key)
    if cached is not None:
        return cached
    loaded = load_module_index(path, root, import_roots)
    module_indexes[key] = loaded
    return loaded


def resolve_imported_name_call(
    binding: ImportBinding,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall:
    """Resolve ``from module import name`` call targets when source is available."""
    target_symbol = binding.imported_name or binding.alias
    if binding.module_path is None:
        external_symbol = ".".join(
            part for part in (binding.module, binding.imported_name or binding.alias) if part
        )
        return ResolvedCall(external_symbol, False, None, None, None)
    target_index = load_index_for_path(binding.module_path, root, import_roots, module_indexes)
    if target_symbol in target_index.symbols:
        return ResolvedCall(target_symbol, True, None, None, target_index)
    return ResolvedCall(
        ".".join(part for part in (binding.module, target_symbol) if part),
        False,
        None,
        None,
        None,
    )


def resolve_imported_attribute_call(
    binding: ImportBinding,
    attr: str,
    recv: str | None,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall:
    """Resolve calls through imported module aliases such as ``kkt.initialize``."""
    if binding.module_path is None:
        return ResolvedCall(f"{binding.module}.{attr}", False, recv, None, None)
    target_index = load_index_for_path(binding.module_path, root, import_roots, module_indexes)
    candidate_symbols = (
        (f"{binding.imported_name}.{attr}", attr)
        if binding.imported_name is not None
        else (attr,)
    )
    for candidate in candidate_symbols:
        if candidate in target_index.symbols:
            return ResolvedCall(candidate, True, recv, None, target_index)
    return ResolvedCall(f"{binding.module}.{attr}", False, recv, None, None)


def resolve_type_reference(
    type_reference: str,
    index: ModuleIndex,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> tuple[ModuleIndex, str] | None:
    """Resolve a type annotation string to a parsed class symbol."""
    if type_reference in index.symbols:
        return index, type_reference
    head, separator, tail = type_reference.partition(".")
    if not separator:
        binding = index.import_bindings.get(head)
        if binding is None:
            return None
        return resolve_import_binding_to_symbol(
            binding,
            binding.imported_name or binding.alias,
            root,
            import_roots,
            module_indexes,
        )
    binding = index.import_bindings.get(head)
    if binding is None or binding.module_path is None:
        return None
    target_index = load_index_for_path(binding.module_path, root, import_roots, module_indexes)
    if tail in target_index.symbols:
        return target_index, tail
    return None


def resolve_import_binding_to_symbol(
    binding: ImportBinding,
    symbol: str,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> tuple[ModuleIndex, str] | None:
    """Resolve one imported symbol into its module index and qualname."""
    if binding.module_path is None:
        return None
    target_index = load_index_for_path(binding.module_path, root, import_roots, module_indexes)
    if symbol in target_index.symbols:
        return target_index, symbol
    return None


def resolve_self_callable_attribute(
    index: ModuleIndex,
    current_qualname: str,
    attr: str,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall | None:
    """Resolve ``self.field(...)`` through class field annotations."""
    current_class = current_class_for(current_qualname, index)
    if current_class is None:
        return None
    type_reference = index.class_attribute_types.get(current_class, {}).get(attr)
    if type_reference is None:
        return None
    resolved_type = resolve_type_reference(
        type_reference,
        index,
        root,
        import_roots,
        module_indexes,
    )
    if resolved_type is None:
        return None
    target_index, class_symbol = resolved_type
    call_symbol = f"{class_symbol}.__call__"
    if call_symbol in target_index.symbols:
        return ResolvedCall(call_symbol, True, f"self.{attr}", type_reference, target_index)
    return ResolvedCall(class_symbol, True, f"self.{attr}", type_reference, target_index)


def resolve_typed_callable_attribute(
    index: ModuleIndex,
    receiver_type: str,
    receiver_label: str,
    attr: str,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall | None:
    """Resolve ``receiver.field(...)`` through the receiver type annotation."""
    type_reference = index.class_attribute_types.get(receiver_type, {}).get(attr)
    if type_reference is None:
        return None
    resolved_type = resolve_type_reference(
        type_reference,
        index,
        root,
        import_roots,
        module_indexes,
    )
    if resolved_type is None:
        return None
    target_index, class_symbol = resolved_type
    call_symbol = f"{class_symbol}.__call__"
    receiver = f"{receiver_label}.{attr}"
    if call_symbol in target_index.symbols:
        return ResolvedCall(call_symbol, True, receiver, type_reference, target_index)
    return ResolvedCall(class_symbol, True, receiver, type_reference, target_index)


def resolve_typed_callable_value(
    index: ModuleIndex,
    type_reference: str,
    receiver_label: str,
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall | None:
    """Resolve a variable call through its annotated callable type."""
    resolved_type = resolve_type_reference(
        type_reference,
        index,
        root,
        import_roots,
        module_indexes,
    )
    if resolved_type is None:
        return None
    target_index, class_symbol = resolved_type
    call_symbol = f"{class_symbol}.__call__"
    if call_symbol in target_index.symbols:
        return ResolvedCall(call_symbol, True, receiver_label, type_reference, target_index)
    return ResolvedCall(class_symbol, True, receiver_label, type_reference, target_index)


def callable_field_variant_targets(
    index: ModuleIndex,
    current_qualname: str,
    call: ast.Call,
) -> tuple[str, ...]:
    """Return same-module function-pointer variants for ``self.field(...)``."""
    if not isinstance(call.func, ast.Attribute):
        return ()
    recv = receiver_name(call.func)
    if recv != "self":
        return ()
    current_class = current_class_for(current_qualname, index)
    if current_class is None:
        return ()
    field_name = call.func.attr
    type_reference = index.class_attribute_types.get(current_class, {}).get(field_name, "")
    if "Callable" not in type_reference and not type_reference.lower().endswith("update"):
        return ()
    suffix = f"_{field_name}"
    candidates = tuple(
        symbol
        for symbol, node in index.symbols.items()
        if "." not in symbol
        and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and symbol.endswith(suffix)
    )
    return candidates


def resolve_call_symbol(
    index: ModuleIndex,
    current_qualname: str,
    call: ast.Call,
    instance_types: dict[str, str],
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall:
    """Resolve a call target within parsed AST modules when possible."""
    call_text = dotted_name(call.func)
    recv = receiver_name(call.func)
    recv_type = instance_types.get(recv) if recv is not None else None
    current_class = current_class_for(current_qualname, index)

    if isinstance(call.func, ast.Name):
        name = call.func.id
        if name in index.symbols:
            return ResolvedCall(name, True, None, None, index)
        type_reference = instance_types.get(name)
        if type_reference is not None:
            resolved_callable = resolve_typed_callable_value(
                index,
                type_reference,
                name,
                root,
                import_roots,
                module_indexes,
            )
            if resolved_callable is not None:
                return resolved_callable
        binding = index.import_bindings.get(name)
        if binding is not None:
            return resolve_imported_name_call(binding, root, import_roots, module_indexes)
        return ResolvedCall(call_text, False, None, None, None)

    if isinstance(call.func, ast.Attribute):
        attr = call.func.attr
        if recv is not None:
            binding = index.import_bindings.get(recv)
            if binding is not None:
                return resolve_imported_attribute_call(
                    binding,
                    attr,
                    recv,
                    root,
                    import_roots,
                    module_indexes,
                )
        if recv == "self":
            resolved_self_field = resolve_self_callable_attribute(
                index,
                current_qualname,
                attr,
                root,
                import_roots,
                module_indexes,
            )
            if resolved_self_field is not None:
                return resolved_self_field
        if recv_type is not None:
            method_symbol = f"{recv_type}.{attr}"
            if method_symbol in index.symbols:
                return ResolvedCall(method_symbol, True, recv, recv_type, index)
            resolved_typed_field = resolve_typed_callable_attribute(
                index,
                recv_type,
                recv or "receiver",
                attr,
                root,
                import_roots,
                module_indexes,
            )
            if resolved_typed_field is not None:
                return resolved_typed_field
            return ResolvedCall(method_symbol, False, recv, recv_type, None)
        if recv == "self" and current_class is not None:
            method_symbol = f"{current_class}.{attr}"
            if method_symbol in index.symbols:
                return ResolvedCall(method_symbol, True, recv, current_class, index)
        if call_text in index.symbols:
            return ResolvedCall(call_text, True, recv, recv_type, index)
    return ResolvedCall(call_text, False, recv, recv_type, None)


def resolve_callable_reference(
    index: ModuleIndex,
    current_qualname: str,
    expression: ast.Attribute,
    instance_types: dict[str, str],
    root: Path,
    import_roots: tuple[Path, ...],
    module_indexes: dict[Path, ModuleIndex],
) -> ResolvedCall:
    """Resolve a callable attribute reference passed as a value."""
    reference_text = dotted_name(expression)
    recv = receiver_name(expression)
    recv_type = instance_types.get(recv) if recv is not None else None
    attr = expression.attr
    if recv_type is not None:
        method_symbol = f"{recv_type}.{attr}"
        if method_symbol in index.symbols:
            return ResolvedCall(method_symbol, True, recv, recv_type, index)
        return ResolvedCall(method_symbol, False, recv, recv_type, None)
    if recv == "self":
        resolved_self_field = resolve_self_callable_attribute(
            index,
            current_qualname,
            attr,
            root,
            import_roots,
            module_indexes,
        )
        if resolved_self_field is not None:
            return resolved_self_field
    return ResolvedCall(reference_text, False, recv, recv_type, None)


def classify_math_role(symbol: str, node_kind: str, source_text: str = "") -> str:
    """Classify an IR node by its likely mathematical role."""
    leaf = symbol.rsplit(".", 1)[-1]
    lowered_leaf = leaf.lower()
    lowered_text = source_text.lower()
    if (
        leaf in BUILTIN_BOOKKEEPING_CALLS
        or "run_log" in symbol
        or "runlog" in symbol.lower()
        or "log." in symbol
    ):
        return "implementation_bookkeeping"
    if node_kind == "ClassDef":
        if leaf.endswith("Info"):
            return "certificate"
        if "Stepper" in leaf or "Iterator" in leaf:
            return "mathematical_state_transition"
        return "implementation_bookkeeping"
    if "certificate" in lowered_leaf or "stopping" in lowered_leaf:
        return "certificate"
    if "diagnostic" in lowered_leaf or "residual" in lowered_leaf or lowered_leaf.endswith("info"):
        return "diagnostic"
    if (
        lowered_leaf in {"solve", "_solve"}
        or lowered_leaf.endswith("_solve")
        or "solve_direction" in lowered_leaf
        or "kkt" in lowered_leaf
        or "minres" in lowered_leaf
        or "linear solve" in lowered_text
    ):
        return "linear_or_nonlinear_solve"
    if "step" in lowered_leaf or "update" in lowered_leaf or "candidate" in lowered_leaf:
        return "mathematical_state_transition"
    if "initialize" in lowered_leaf or "config" in lowered_leaf or leaf.endswith("Algorithm"):
        return "implementation_bookkeeping"
    return "implementation_bookkeeping"


def equation_tags_for_symbol(symbol: str, node_kind: str, source_text: str = "") -> tuple[str, ...]:
    """Return proof-topic equation tags visible from one symbol name."""
    lowered = f"{symbol} {node_kind} {source_text}".lower()
    tags: set[str] = set()
    if any(token in lowered for token in ("reduced_kkt", "rhs_top", "solve_direction")):
        tags.add("reduced_kkt")
    if any(token in lowered for token in ("step_update", "apply_primal_dual_step")):
        tags.add("step_update")
    if any(
        token in lowered
        for token in ("fraction_to_boundary", "safe_interior", "positivity_floor")
    ):
        tags.add("floor_preserving_step")
    if any(
        token in lowered
        for token in (
            "minres",
            "runtime_rtol",
            "runtime_atol",
            "dtype_rtol_floor",
            "resolve_tolerance",
        )
    ):
        tags.add("minres_defaults")
    if any(token in lowered for token in ("initial_values", "cold_start", "reset")):
        tags.add("pdipm_initialization_path")
    return tuple(sorted(tags))


def target_profiles_for_equation_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    """Map equation tags to lemma-graph target profiles."""
    profiles: set[str] = {"all"}
    if "reduced_kkt" in tags:
        profiles.update(("local_convergence", "solver_chain", "reduced_kkt"))
    if "step_update" in tags:
        profiles.update(("local_convergence", "step_update"))
    if "floor_preserving_step" in tags:
        profiles.update(("local_convergence", "fp32_floor", "floor_preserving_step"))
    if "minres_defaults" in tags:
        profiles.update(("solver_chain", "minres_defaults"))
    if "pdipm_initialization_path" in tags:
        profiles.update(("local_convergence", "pdipm_initialization_path"))
    order = (
        "all",
        "certificate_soundness",
        "local_convergence",
        "fp32_floor",
        "solver_chain",
        "reduced_kkt",
        "step_update",
        "floor_preserving_step",
        "minres_defaults",
        "pdipm_initialization_path",
    )
    return tuple(profile for profile in order if profile in profiles)


def runtime_object_for(symbol: str) -> str:
    """Return a coarse runtime object label for one symbol."""
    leaf = symbol.rsplit(".", 1)[-1]
    for token in (
        "InitializeConfig",
        "SolveConfig",
        "Problem",
        "State",
        "Info",
        "Algorithm",
        "Answer",
    ):
        if token in leaf:
            return token
    lowered = leaf.lower()
    if "residual" in lowered:
        return "residual"
    if "direction" in lowered or "solve" in lowered:
        return "direction_or_solve"
    if "certificate" in lowered or "stopping" in lowered:
        return "certificate"
    return "unknown"


def residual_unit_for(symbol: str, math_role: str) -> str:
    """Return a coarse residual or certificate unit label."""
    lowered = symbol.lower()
    if "kkt" in lowered:
        return "kkt_residual_unit"
    if "ipm" in lowered or "pdipm" in lowered:
        return "outer_ipm_residual_unit"
    if "residual" in lowered:
        return "residual_unit"
    if math_role == "certificate":
        return "certificate_unit"
    return "none"


def precision_model_for(symbol: str) -> str:
    """Return whether a symbol appears to carry precision/floor concerns."""
    leaf = symbol.rsplit(".", 1)[-1]
    if (
        leaf in BUILTIN_BOOKKEEPING_CALLS
        or "run_log" in symbol
        or "runlog" in symbol.lower()
        or "log." in symbol
    ):
        return "none"
    lowered = symbol.lower()
    if any(
        token in lowered
        for token in ("dtype", "finfo", "fp32", "float", "floor", "epsilon")
    ):
        return "dtype_or_backend_floor"
    return "none"


def iteration_scope_for(symbol: str, math_role: str) -> str:
    """Return the iteration scope visible from a symbol name."""
    lowered = symbol.lower()
    if any(token in lowered for token in ("step", "candidate", "_solve", "iterate")):
        return "per_iteration"
    if math_role in {"linear_or_nonlinear_solve", "mathematical_state_transition"}:
        return "per_iteration"
    return "global_or_initialization"


def proof_relevance_for(math_role: str, precision_model: str) -> str:
    """Return proof relevance for a node."""
    if precision_model != "none":
        return "required"
    if math_role in {
        "mathematical_state_transition",
        "linear_or_nonlinear_solve",
        "certificate",
        "diagnostic",
    }:
        return "required"
    return "excluded"


def obligation_id_for(symbol: str) -> str:
    """Return a stable obligation id for one source symbol."""
    return f"obl__{node_id_for(symbol)}"


def assumption_id_for(symbol: str, precision_model: str, resolved: bool = True) -> str | None:
    """Return an assumption id when proof evidence must come from outside the AST."""
    if precision_model != "none":
        return f"asm__precision__{node_id_for(symbol)}"
    if not resolved:
        return f"asm__external__{external_node_id(symbol)}"
    return None


def child_config_field_for(call: ast.Call) -> str | None:
    """Infer an InitializeConfig child field from initialize call arguments."""
    for arg in call.args:
        if isinstance(arg, ast.Attribute):
            return _unparse(arg)
    for keyword in call.keywords:
        if isinstance(keyword.value, ast.Attribute):
            return _unparse(keyword.value)
        if keyword.arg:
            return keyword.arg
    return None


def quantity_flow_for(call_text: str, assigned_to: tuple[str, ...]) -> str | None:
    """Return a compact quantity-flow label for one edge."""
    if assigned_to:
        return f"{call_text} -> {', '.join(assigned_to)}"
    quantity_tokens = ("res", "tol", "cert", "info")
    if any(token in call_text.lower() for token in quantity_tokens):
        return call_text
    return None


def unit_conversion_for(call_text: str) -> str | None:
    """Infer whether a call likely converts between residual units."""
    lowered = call_text.lower()
    if "precondition" in lowered:
        return "preconditioned_to_physical_residual"
    if "kkt" in lowered and "ipm" in lowered:
        return "kkt_to_outer_ipm_residual"
    if "certificate" in lowered or "stopping" in lowered:
        return "residual_to_certificate"
    return None


def edge_role_for(edge_kind: str, target_symbol: str) -> str:
    """Return proof-planning role for one edge."""
    if edge_kind == "initializes":
        return "initialize_dispatch"
    if edge_kind in {"requests_certificate", "projects_status"}:
        return "correctness_certificate"
    if edge_kind == "instance_method_call":
        return "instance_interaction"
    if edge_kind == "callable_argument":
        return "callback_dispatch"
    if edge_kind == "callable_variant":
        return "variant_dispatch"
    if "precondition" in target_symbol.lower():
        return "reachability_or_performance_helper"
    return "runtime_dependency"


def classify_edge_kind(
    call_text: str,
    resolved_symbol: str,
    assigned_to: tuple[str, ...],
    index: ModuleIndex,
    receiver: str | None,
) -> str:
    """Classify a call edge."""
    lowered = call_text.lower()
    if call_text.isidentifier():
        parsed_stmt = cast(ast.Expr, ast.parse(f"{call_text}()").body[0])
        parsed_call = cast(ast.Call, parsed_stmt.value)
        leaf = simple_name_from_call(parsed_call.func)
    else:
        leaf = call_text.rsplit(".", 1)[-1]
    if resolved_symbol in index.class_methods or leaf.endswith(
        ("Config", "State", "Info", "Problem", "Algorithm", "Answer")
    ):
        return "instance_constructs"
    if leaf == "initialize" or lowered.endswith(".initialize"):
        return "initializes"
    if "certificate" in lowered or "stopping" in lowered or leaf == "Info":
        return "requests_certificate"
    if receiver is not None and ("run_log" in receiver or "log" in receiver.lower()):
        return "calls"
    if receiver in index.import_aliases:
        return "calls"
    if receiver is not None:
        return "instance_method_call"
    if assigned_to and any("state" in name.lower() for name in assigned_to):
        return "updates_state"
    return "calls"


def make_node(index: ModuleIndex, qualname: str, symbol: PythonSymbol) -> IRNode:
    """Create an IR node from one AST symbol."""
    source_text = ast.get_docstring(symbol, clean=True) or ""
    math_role = classify_math_role(qualname, symbol.__class__.__name__, source_text)
    precision_model = precision_model_for(qualname)
    proof_relevance = proof_relevance_for(math_role, precision_model)
    equation_tags = equation_tags_for_symbol(
        qualname,
        symbol.__class__.__name__,
        source_text,
    )
    return IRNode(
        node_id=node_id_for_ref(index, qualname),
        source_path=index.relative_path,
        source_symbol=qualname,
        source_span=f"{getattr(symbol, 'lineno', 0)}:{getattr(symbol, 'end_lineno', None)}",
        node_kind=symbol.__class__.__name__,
        lineno=int(getattr(symbol, "lineno", 0)),
        end_lineno=getattr(symbol, "end_lineno", None),
        math_role=math_role,
        runtime_object=runtime_object_for(qualname),
        residual_unit=residual_unit_for(qualname, math_role),
        precision_model=precision_model,
        iteration_scope=iteration_scope_for(qualname, math_role),
        equation_tags=equation_tags,
        proof_relevance=proof_relevance,
        selected_obligation_id=(
            obligation_id_for(qualname) if proof_relevance == "required" else None
        ),
        assumption_id=assumption_id_for(qualname, precision_model),
        status="unverified" if proof_relevance == "required" else "excluded",
    )


def make_external_node(index: ModuleIndex, call_text: str) -> IRNode:
    """Create an unresolved external node."""
    math_role = classify_math_role(call_text, "ExternalCall")
    precision_model = precision_model_for(call_text)
    proof_relevance = proof_relevance_for(math_role, precision_model)
    equation_tags = equation_tags_for_symbol(call_text, "ExternalCall")
    return IRNode(
        node_id=external_node_id(call_text),
        source_path=index.relative_path,
        source_symbol=call_text,
        source_span="external",
        node_kind="ExternalCall",
        lineno=0,
        end_lineno=None,
        math_role=math_role,
        runtime_object=runtime_object_for(call_text),
        residual_unit=residual_unit_for(call_text, math_role),
        precision_model=precision_model,
        iteration_scope=iteration_scope_for(call_text, math_role),
        equation_tags=equation_tags,
        proof_relevance=proof_relevance,
        selected_obligation_id=(
            obligation_id_for(call_text) if proof_relevance == "required" else None
        ),
        assumption_id=assumption_id_for(call_text, precision_model, resolved=False),
        status="unverified" if proof_relevance == "required" else "excluded",
    )


def make_static_instance_gap_node(index: ModuleIndex, call_text: str) -> IRNode:
    """Create an excluded node for an instance call that must be resolved statically."""
    return IRNode(
        node_id=external_node_id(call_text),
        source_path=index.relative_path,
        source_symbol=call_text,
        source_span="static-instance-resolution",
        node_kind="StaticInstanceResolution",
        lineno=0,
        end_lineno=None,
        math_role="implementation_bookkeeping",
        runtime_object="instance_interaction",
        residual_unit="none",
        precision_model="none",
        iteration_scope="global_or_initialization",
        equation_tags=(),
        proof_relevance="excluded",
        selected_obligation_id=None,
        assumption_id=None,
        status="static_resolution_gap",
    )


def obligation_grain_for(node: IRNode) -> str:
    """Return the obligation grain for one node."""
    if node.proof_relevance != "required":
        return "excluded"
    if node.assumption_id is not None:
        return "assumption"
    if node.math_role in {"certificate", "diagnostic"}:
        return "known_lemma"
    return "local_obligation"


def obligation_search_queries(node: IRNode, target_theorem: str) -> tuple[str, ...]:
    """Return existing-proof search queries for one selected obligation."""
    terms = [target_theorem, node.math_role, node.runtime_object]
    if node.residual_unit != "none":
        terms.append(node.residual_unit)
    if node.precision_model != "none":
        terms.append(node.precision_model)
    terms.extend(node.equation_tags)
    return (" ".join(term for term in terms if term and term != "unknown"),)


def obligation_checker_route(node: IRNode) -> str:
    """Return the checker route for one obligation."""
    if node.assumption_id is not None:
        return "record_as_problem_class_or_backend_assumption"
    return "formal_proof_assistant_or_solver"


def make_obligation(
    node: IRNode,
    edges: list[IREdge],
    target_theorem: str,
) -> IRObligation:
    """Create one first-class local proof obligation from a required node."""
    consumed_edges = tuple(
        edge.edge_id
        for edge in edges
        if (edge.source_node_id == node.node_id or edge.target_node_id == node.node_id)
        and edge.status not in STATIC_EDGE_STATUSES
    )
    grain = obligation_grain_for(node)
    statement = (
        f"For `{target_theorem}`, discharge `{node.source_symbol}` as "
        f"{grain} with role `{node.math_role}` and unit `{node.residual_unit}`."
    )
    return IRObligation(
        obligation_id=node.selected_obligation_id or obligation_id_for(node.source_symbol),
        statement=statement,
        grain=grain,
        consumes_nodes=(node.node_id,),
        consumes_edges=consumed_edges,
        existing_proof_search=obligation_search_queries(node, target_theorem),
        checker_route=obligation_checker_route(node),
        remaining_gap=(
            "instantiate external/problem/backend assumption"
            if grain == "assumption"
            else "formal theorem or checked lemma required"
        ),
        status="unverified" if grain != "excluded" else "excluded",
    )


def backend_assumptions_for(
    nodes: Iterable[IRNode],
    target_theorem: str,
    *,
    profile_library_path: str,
    profile_library: dict[str, object],
) -> tuple[IRBackendAssumption, ...]:
    """Return proof-only backend assumptions selected by the theorem target."""
    node_tuple = tuple(nodes)
    precision_node_ids = tuple(
        node.node_id for node in node_tuple if node.precision_model != "none"
    )
    theorem_lower = target_theorem.lower()
    needs_backend_overlay = bool(precision_node_ids) or any(
        token in theorem_lower
        for token in (
            "backend",
            "finite precision",
            "float",
            "fp32",
            "iree",
            "roundoff",
        )
    )
    if not needs_backend_overlay:
        return ()
    return (
        IRBackendAssumption(
            assumption_id="asm__backend_profile__target",
            statement=(
                "Backend floating-point semantics are proof IR overlay variables "
                "read from the backend profile library by the IR builder; they "
                "are not production InitializeConfig fields."
            ),
            profile_variable="backend_profile",
            profile_library_path=profile_library_path,
            profile_ids=backend_profile_ids(profile_library),
            profile_details=backend_profile_details(profile_library),
            owning_surface="algorithm_expansion_ir",
            scope="proof_only_overlay",
            applies_to_nodes=precision_node_ids,
            required_witnesses=backend_required_witnesses(profile_library),
            checker_route=(
                "record_as_backend_assumption_or_lowered_ir_evidence_before_"
                "using_fp32_error_bounds"
            ),
            status="unverified",
        ),
    )


def instance_edge_status(
    edge_kind: str,
    resolved: bool,
    recv: str | None,
    recv_type: str | None,
) -> str:
    """Return the static-check status for an instance edge."""
    if edge_kind == "instance_constructs":
        return "statically_checked" if resolved else "static_checker_required"
    if edge_kind == "callable_argument":
        return "statically_checked" if resolved else "static_resolution_gap"
    if edge_kind == "callable_variant":
        return "statically_checked" if resolved else "static_resolution_gap"
    if edge_kind != "instance_method_call":
        return "retained"
    if resolved:
        return "statically_checked"
    if recv is not None and recv_type is not None:
        return "static_checker_required"
    return "static_resolution_gap"


def static_check_for_edge(edge: IREdge) -> IRStaticCheck | None:
    """Create a pre-proof static check for instance dispatch edges."""
    if edge.edge_kind not in STATIC_INSTANCE_EDGE_KINDS:
        return None
    check_kind = (
        "constructor_resolution"
        if edge.edge_kind == "instance_constructs"
        else (
            "callable_argument_resolution"
            if edge.edge_kind == "callable_argument"
            else (
                "callable_variant_resolution"
                if edge.edge_kind == "callable_variant"
                else "instance_method_resolution"
            )
        )
    )
    if edge.status == "statically_checked":
        evidence = (
            f"`{edge.call_text}` resolves to `{edge.target_symbol}` in AST"
            if edge.receiver_name is None
            else (
                f"receiver `{edge.receiver_name}` inferred as `{edge.receiver_type}`; "
                f"`{edge.call_text}` resolves to `{edge.target_symbol}`"
            )
        )
    elif edge.status == "static_checker_required":
        evidence = (
            f"receiver `{edge.receiver_name}` inferred as `{edge.receiver_type}`; "
            "target method body is outside this AST root and must be discharged by "
            "the static checker or a child expansion root"
        )
    else:
        evidence = (
            f"receiver `{edge.receiver_name or 'unknown'}` has no statically inferred "
            "type in this AST slice"
        )
    return IRStaticCheck(
        check_id=f"static-{edge.edge_id}",
        edge_id=edge.edge_id,
        check_kind=check_kind,
        source_symbol=edge.source_symbol,
        target_symbol=edge.target_symbol,
        evidence=evidence,
        status=edge.status,
        proof_effect="drop_instance_dispatch_edge_before_obligation_selection",
    )


def build_algorithm_ir(
    root_symbol: str,
    index: ModuleIndex,
    target_theorem: str,
    root: Path,
    import_roots: tuple[Path, ...] = (),
    backend_profile_library_path: str = "",
    backend_profile_library: dict[str, object] | None = None,
) -> AlgorithmIRReport:
    """Build an Algorithm Expansion IR from a root AST symbol."""
    nodes: dict[str, IRNode] = {}
    edges: list[IREdge] = []
    code_facts: dict[str, IRCodeFact] = {}
    control_facts: dict[str, IRControlFact] = {}
    expanded: set[str] = set()
    module_indexes: dict[Path, ModuleIndex] = {index_cache_key(index.path): index}

    def add_node(node: IRNode) -> None:
        nodes.setdefault(node.node_id, node)

    def add_code_facts(items: Iterable[IRCodeFact]) -> None:
        for fact in items:
            code_facts.setdefault(fact.fact_id, fact)

    def add_control_facts(items: Iterable[IRControlFact]) -> None:
        for fact in items:
            control_facts.setdefault(fact.fact_id, fact)

    def make_edge(
        site: CallSite,
        call_text: str,
        source_index: ModuleIndex,
        qualname: str,
        target_node_id: str,
        target_symbol: str,
        edge_kind: str,
        recv: str | None,
        recv_type: str | None,
        resolved: bool,
    ) -> IREdge:
        edge_id = f"edge-{len(edges) + 1}"
        child_initialize = target_symbol if edge_kind == "initializes" else None
        child_config_field = (
            child_config_field_for(site.call) if edge_kind == "initializes" else None
        )
        if edge_kind in STATIC_INSTANCE_EDGE_KINDS:
            status = instance_edge_status(edge_kind, resolved, recv, recv_type)
        elif edge_kind in {"initializes", "requests_certificate"}:
            status = "unverified"
        else:
            status = "retained"
        return IREdge(
            edge_id=edge_id,
            source_node_id=node_id_for_ref(source_index, qualname),
            target_node_id=target_node_id,
            edge_kind=edge_kind,
            source_symbol=qualname,
            target_symbol=target_symbol,
            call_text=_unparse(site.call),
            line=int(getattr(site.call, "lineno", 0)),
            assigned_to=site.assigned_to,
            receiver_name=recv,
            receiver_type=recv_type,
            child_config_field=child_config_field,
            child_initialize=child_initialize,
            proof_scope=f"{target_symbol}::proof_scope" if child_initialize else None,
            selection_rule=(
                "initialize-call"
                if child_initialize
                else (
                    "static-instance-resolution"
                    if edge_kind in STATIC_INSTANCE_EDGE_KINDS
                    else "ast-call-target"
                )
            ),
            role=edge_role_for(edge_kind, target_symbol),
            quantity_flow=quantity_flow_for(call_text, site.assigned_to),
            unit_conversion=unit_conversion_for(call_text),
            resolved=resolved,
            status=status,
        )

    def make_callable_reference_edge(
        site: CallableReferenceSite,
        source_index: ModuleIndex,
        qualname: str,
        target_node_id: str,
        target_symbol: str,
        resolved_call: ResolvedCall,
    ) -> IREdge:
        edge_id = f"edge-{len(edges) + 1}"
        return IREdge(
            edge_id=edge_id,
            source_node_id=node_id_for_ref(source_index, qualname),
            target_node_id=target_node_id,
            edge_kind="callable_argument",
            source_symbol=qualname,
            target_symbol=target_symbol,
            call_text=_unparse(site.expression),
            line=int(getattr(site.expression, "lineno", 0)),
            assigned_to=(),
            receiver_name=resolved_call.receiver_name,
            receiver_type=resolved_call.receiver_type,
            child_config_field=None,
            child_initialize=None,
            proof_scope=None,
            selection_rule="static-callable-reference",
            role=edge_role_for("callable_argument", target_symbol),
            quantity_flow=None,
            unit_conversion=None,
            resolved=resolved_call.resolved,
            status=instance_edge_status(
                "callable_argument",
                resolved_call.resolved,
                resolved_call.receiver_name,
                resolved_call.receiver_type,
            ),
        )

    def make_callable_variant_edge(
        site: CallSite,
        source_index: ModuleIndex,
        qualname: str,
        target_node_id: str,
        target_symbol: str,
    ) -> IREdge:
        edge_id = f"edge-{len(edges) + 1}"
        return IREdge(
            edge_id=edge_id,
            source_node_id=node_id_for_ref(source_index, qualname),
            target_node_id=target_node_id,
            edge_kind="callable_variant",
            source_symbol=qualname,
            target_symbol=target_symbol,
            call_text=_unparse(site.call.func),
            line=int(getattr(site.call, "lineno", 0)),
            assigned_to=site.assigned_to,
            receiver_name="self",
            receiver_type=current_class_for(qualname, source_index),
            child_config_field=None,
            child_initialize=None,
            proof_scope=None,
            selection_rule="static-callable-variant",
            role=edge_role_for("callable_variant", target_symbol),
            quantity_flow=quantity_flow_for(target_symbol, site.assigned_to),
            unit_conversion=unit_conversion_for(target_symbol),
            resolved=True,
            status=instance_edge_status("callable_variant", True, "self", None),
        )

    def expand_with_edges(source_index: ModuleIndex, qualname: str) -> None:
        expansion_key = f"{source_index.relative_path}::{qualname}"
        if expansion_key in expanded:
            return
        symbol = find_symbol(source_index, qualname)
        expanded.add(expansion_key)
        add_node(make_node(source_index, qualname, symbol))
        add_code_facts(collect_symbol_code_facts(source_index, qualname, symbol))
        add_control_facts(collect_symbol_control_facts(source_index, qualname, symbol))
        instance_types = initial_instance_types(symbol, current_class_for(qualname, source_index))
        for site in collect_call_sites(symbol):
            call_text = dotted_name(site.call.func)
            variant_targets = callable_field_variant_targets(source_index, qualname, site.call)
            if variant_targets:
                for target_symbol in variant_targets:
                    target_node_id = node_id_for_ref(source_index, target_symbol)
                    add_node(
                        make_node(
                            source_index,
                            target_symbol,
                            find_symbol(source_index, target_symbol),
                        )
                    )
                    edges.append(
                        make_callable_variant_edge(
                            site,
                            source_index,
                            qualname,
                            target_node_id,
                            target_symbol,
                        )
                    )
                    expand_with_edges(source_index, target_symbol)
                continue
            resolved_call = resolve_call_symbol(
                source_index,
                qualname,
                site.call,
                instance_types,
                root,
                import_roots,
                module_indexes,
            )
            target_index = resolved_call.index
            resolved_symbol = resolved_call.symbol
            edge_kind = classify_edge_kind(
                call_text,
                resolved_symbol,
                site.assigned_to,
                source_index,
                resolved_call.receiver_name,
            )
            if resolved_call.resolved and target_index is not None:
                target_symbol = resolved_symbol
                target_node_id = node_id_for_ref(target_index, resolved_symbol)
                add_node(
                    make_node(
                        target_index,
                        resolved_symbol,
                        find_symbol(target_index, resolved_symbol),
                    )
                )
            elif edge_kind == "instance_method_call" and resolved_call.receiver_type is None:
                target_symbol = resolved_symbol
                target_node_id = external_node_id(call_text)
                add_node(make_static_instance_gap_node(source_index, call_text))
            else:
                target_symbol = resolved_symbol
                target_node_id = external_node_id(call_text)
                add_node(make_external_node(source_index, target_symbol))
            edges.append(
                make_edge(
                    site,
                    call_text,
                    source_index,
                    qualname,
                    target_node_id,
                    target_symbol,
                    edge_kind,
                    resolved_call.receiver_name,
                    resolved_call.receiver_type,
                    resolved_call.resolved,
                )
            )
            update_instance_types(
                instance_types,
                site.call.func.id if isinstance(site.call.func, ast.Name) else dotted_name(site.call.func),
                site.assigned_to,
                target_symbol if resolved_call.resolved else None,
                source_index,
                target_index if resolved_call.resolved else None,
            )
            if (
                resolved_call.resolved
                and target_index is not None
                and target_symbol not in target_index.class_methods
            ):
                expand_with_edges(target_index, target_symbol)
        for site in collect_callable_reference_sites(symbol):
            resolved_call = resolve_callable_reference(
                source_index,
                qualname,
                site.expression,
                instance_types,
                root,
                import_roots,
                module_indexes,
            )
            target_index = resolved_call.index
            target_symbol = resolved_call.symbol
            if resolved_call.resolved and target_index is not None:
                target_node_id = node_id_for_ref(target_index, target_symbol)
                add_node(
                    make_node(
                        target_index,
                        target_symbol,
                        find_symbol(target_index, target_symbol),
                    )
                )
            else:
                continue
            edges.append(
                make_callable_reference_edge(
                    site,
                    source_index,
                    qualname,
                    target_node_id,
                    target_symbol,
                    resolved_call,
                )
            )
            if resolved_call.resolved and target_symbol not in target_index.class_methods:
                expand_with_edges(target_index, target_symbol)

    expand_with_edges(index, root_symbol)
    for loaded_index in tuple(module_indexes.values()):
        add_code_facts(collect_module_static_code_facts(loaded_index))
    static_checks = tuple(
        check
        for edge in edges
        for check in (static_check_for_edge(edge),)
        if check is not None
    )
    obligations = tuple(
        make_obligation(node, edges, target_theorem)
        for node in sorted(nodes.values(), key=lambda item: item.node_id)
        if node.proof_relevance == "required" and node.selected_obligation_id is not None
    )
    backend_assumptions = backend_assumptions_for(
        sorted(nodes.values(), key=lambda item: item.node_id),
        target_theorem,
        profile_library_path=backend_profile_library_path,
        profile_library=backend_profile_library or {},
    )
    selected_local_obligations = tuple(
        obligation.statement for obligation in obligations if obligation.grain != "excluded"
    )
    goal_directed_slice = tuple(
        node.node_id
        for node in sorted(nodes.values(), key=lambda item: item.node_id)
        if node.proof_relevance == "required"
    )
    return AlgorithmIRReport(
        status="algorithm_ir_built",
        root_path=index.relative_path,
        root_symbol=root_symbol,
        target_theorem=target_theorem,
        backend_profile_library=backend_profile_library_path,
        nodes=tuple(sorted(nodes.values(), key=lambda item: item.node_id)),
        edges=tuple(edges),
        code_facts=tuple(sorted(code_facts.values(), key=lambda item: item.fact_id)),
        control_facts=tuple(sorted(control_facts.values(), key=lambda item: item.fact_id)),
        static_checks=static_checks,
        backend_assumptions=backend_assumptions,
        obligations=obligations,
        goal_directed_slice=goal_directed_slice,
        selected_local_obligations=selected_local_obligations,
    )


def render_text(report: AlgorithmIRReport) -> str:
    """Render stable text output."""
    lines = [
        "ALGORITHM_EXPANSION_IR=pass",
        f"ALGORITHM_EXPANSION_IR_ROOT={report.root_path}::{report.root_symbol}",
        f"ALGORITHM_EXPANSION_IR_TARGET_THEOREM={report.target_theorem}",
        f"ALGORITHM_EXPANSION_IR_BACKEND_PROFILE_LIBRARY={report.backend_profile_library}",
        f"ALGORITHM_EXPANSION_IR_NODES={len(report.nodes)}",
        f"ALGORITHM_EXPANSION_IR_EDGES={len(report.edges)}",
        f"ALGORITHM_EXPANSION_IR_CODE_FACTS={len(report.code_facts)}",
        f"ALGORITHM_EXPANSION_IR_CONTROL_FACTS={len(report.control_facts)}",
        f"ALGORITHM_EXPANSION_IR_STATIC_CHECKS={len(report.static_checks)}",
        f"ALGORITHM_EXPANSION_IR_OBLIGATIONS={len(report.obligations)}",
        f"ALGORITHM_EXPANSION_IR_SELECTED_OBLIGATIONS={len(report.selected_local_obligations)}",
    ]
    for node in report.nodes:
        lines.append(
            "ALGORITHM_EXPANSION_IR_NODE="
            f"{node.node_id}:{node.source_symbol}:{node.math_role}:{node.proof_relevance}"
        )
    for edge in report.edges:
        lines.append(
            "ALGORITHM_EXPANSION_IR_EDGE="
            f"{edge.edge_id}:{edge.source_symbol}->{edge.target_symbol}:{edge.edge_kind}:"
            f"line={edge.line}:resolved={str(edge.resolved).lower()}"
        )
    for fact in report.code_facts:
        lines.append(
            "ALGORITHM_EXPANSION_IR_CODE_FACT="
            f"{fact.fact_id}:{fact.fact_kind}:{fact.source_symbol}:"
            f"target={fact.target}:tags={','.join(fact.equation_tags) or 'none'}"
        )
    for fact in report.control_facts:
        lines.append(
            "ALGORITHM_EXPANSION_IR_CONTROL_FACT="
            f"{fact.fact_id}:{fact.control_kind}:{fact.source_symbol}:"
            f"condition={fact.condition or fact.iterator or 'none'}"
        )
    for check in report.static_checks:
        lines.append(
            "ALGORITHM_EXPANSION_IR_STATIC_CHECK="
            f"{check.check_id}:{check.check_kind}:{check.status}:edge={check.edge_id}"
        )
    for assumption in report.backend_assumptions:
        lines.append(
            "ALGORITHM_EXPANSION_IR_BACKEND_ASSUMPTION="
            f"{assumption.assumption_id}:{assumption.profile_variable}:"
            f"{assumption.scope}:profiles={','.join(assumption.profile_ids) or 'unbound'}:"
            f"{assumption.status}"
        )
    for obligation in report.obligations:
        lines.append(
            "ALGORITHM_EXPANSION_IR_OBLIGATION="
            f"{obligation.obligation_id}:{obligation.grain}:{obligation.status}"
        )
    return "\n".join(lines) + "\n"


def markdown_cell(value: object) -> str:
    """Escape a value for a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: AlgorithmIRReport) -> str:
    """Render Markdown output."""
    lines = [
        "# Algorithm Expansion IR",
        "",
        f"- root: `{report.root_path}::{report.root_symbol}`",
        f"- target theorem: `{report.target_theorem}`",
        f"- status: `{report.status}`",
        f"- backend profile library: `{report.backend_profile_library or 'none'}`",
        f"- nodes: `{len(report.nodes)}`",
        f"- edges: `{len(report.edges)}`",
        f"- code facts: `{len(report.code_facts)}`",
        f"- control facts: `{len(report.control_facts)}`",
        f"- static checks: `{len(report.static_checks)}`",
        f"- obligations: `{len(report.obligations)}`",
        "",
        "## Nodes",
        "",
        "| Node | Source Symbol | Role | Unit | Runtime Object | Precision | Iteration | "
        "Equation Tags | Relevance | Obligation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for node in report.nodes:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    node.node_id,
                    f"`{node.source_symbol}`",
                    node.math_role,
                    node.residual_unit,
                    node.runtime_object,
                    node.precision_model,
                    node.iteration_scope,
                    ", ".join(node.equation_tags) or "none",
                    node.proof_relevance,
                    node.selected_obligation_id or "none",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Code Facts",
            "",
            "| Fact | Kind | Source | Target | Expression | Equation Tags | Profiles |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.code_facts:
        for fact in report.code_facts:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        fact.fact_id,
                        fact.fact_kind,
                        f"`{fact.source_symbol}`",
                        f"`{fact.target}`",
                        f"`{fact.expression}`",
                        ", ".join(fact.equation_tags) or "none",
                        ", ".join(fact.target_profiles),
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Control Facts",
            "",
            "| Fact | Kind | Source | Condition | Target | Iterator | Body Targets | Orelse Targets |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.control_facts:
        for fact in report.control_facts:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        fact.fact_id,
                        fact.control_kind,
                        f"`{fact.source_symbol}`",
                        f"`{fact.condition}`" if fact.condition is not None else "none",
                        f"`{fact.target}`" if fact.target is not None else "none",
                        f"`{fact.iterator}`" if fact.iterator is not None else "none",
                        ", ".join(f"`{target}`" for target in fact.body_targets) or "none",
                        ", ".join(f"`{target}`" for target in fact.orelse_targets) or "none",
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Static Checks",
            "",
            "| Check | Edge | Kind | Status | Proof Effect | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.static_checks:
        for check in report.static_checks:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        check.check_id,
                        check.edge_id,
                        check.check_kind,
                        check.status,
                        check.proof_effect,
                        check.evidence,
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Edges",
            "",
            "| Edge | Source | Target | Kind | Role | Quantity Flow | Unit Conversion | "
            "Receiver | Resolved |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for edge in report.edges:
        lines.append(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in (
                    edge.edge_id,
                    f"`{edge.source_symbol}`",
                    f"`{edge.target_symbol}`",
                    edge.edge_kind,
                    edge.role,
                    edge.quantity_flow or "none",
                    edge.unit_conversion or "none",
                    edge.receiver_name or "none",
                    edge.resolved,
                )
            )
            + " |"
    )
    lines.extend(
        [
            "",
            "## Backend Assumptions",
            "",
            "| Assumption | Profile Variable | Scope | Nodes | Witnesses | Checker Route | "
            "Profiles | Library | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.backend_assumptions:
        for assumption in report.backend_assumptions:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        assumption.assumption_id,
                        assumption.profile_variable,
                        assumption.scope,
                        ", ".join(assumption.applies_to_nodes) or "target-level",
                        ", ".join(assumption.required_witnesses),
                        assumption.checker_route,
                        ", ".join(assumption.profile_ids) or "unbound",
                        assumption.profile_library_path or "none",
                        assumption.status,
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none | none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Obligations",
            "",
            "| Obligation | Grain | Status | Nodes | Edges | Remaining Gap |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if report.obligations:
        for obligation in report.obligations:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in (
                        obligation.obligation_id,
                        obligation.grain,
                        obligation.status,
                        ", ".join(obligation.consumes_nodes),
                        ", ".join(obligation.consumes_edges) or "none",
                        obligation.remaining_gap,
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | none | none | none | none |")
    lines.extend(["", "## Selected Local Obligations", ""])
    if report.selected_local_obligations:
        lines.extend(f"- {obligation}" for obligation in report.selected_local_obligations)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def render_json(report: AlgorithmIRReport) -> str:
    """Render JSON output."""
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_report(report: AlgorithmIRReport, output_format: str) -> str:
    """Render a report in the selected format."""
    if output_format == "json":
        return render_json(report)
    if output_format == "markdown":
        return render_markdown(report)
    return render_text(report)


def main() -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    root = Path(args.root)
    path, qualname = parse_python_symbol_reference(str(args.python_symbol))
    if not path.is_absolute():
        path = root / path
    import_roots = tuple(
        candidate if candidate.is_absolute() else root / candidate
        for candidate in (Path(raw_path) for raw_path in args.import_root)
    )
    raw_profile_library = Path(str(args.backend_profile_library))
    profile_library_path = (
        raw_profile_library if raw_profile_library.is_absolute() else root / raw_profile_library
    )
    profile_library = load_backend_profile_library(profile_library_path)
    index = load_module_index(path, root, import_roots)
    report = build_algorithm_ir(
        qualname,
        index,
        str(args.target_theorem),
        root,
        import_roots,
        backend_profile_library_path=relative_path(profile_library_path, root),
        backend_profile_library=profile_library,
    )
    rendered = render_report(report, str(args.format))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
