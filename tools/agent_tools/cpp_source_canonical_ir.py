#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Extracts source-canonical C++ records into the shared thin operational IR.
# upstream design ../../documents/tools/cpp_source_canonical_ir.md defines the wrapper contract.
# upstream implementation jit_canonical_ir.py defines the shared thin operational IR schema shape.
# downstream implementation ../../tests/agent_tools/test_cpp_source_canonical_ir.py tests it.
# @dependency-end
"""Extract source-canonical C++ records into the shared thin operational IR."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import cast

CXX_KEYWORDS = frozenset(
    {
        "alignas",
        "alignof",
        "and",
        "asm",
        "auto",
        "bool",
        "break",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "constexpr",
        "continue",
        "decltype",
        "default",
        "delete",
        "do",
        "double",
        "else",
        "enum",
        "explicit",
        "extern",
        "false",
        "float",
        "for",
        "friend",
        "goto",
        "if",
        "inline",
        "int",
        "long",
        "namespace",
        "new",
        "noexcept",
        "nullptr",
        "operator",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "signed",
        "sizeof",
        "static",
        "struct",
        "switch",
        "template",
        "this",
        "throw",
        "true",
        "try",
        "typedef",
        "typename",
        "using",
        "virtual",
        "void",
        "volatile",
        "while",
    }
)
TYPE_QUALIFIERS = frozenset(
    {
        "auto",
        "const",
        "constexpr",
        "inline",
        "mutable",
        "noexcept",
        "static",
        "virtual",
        "volatile",
    }
)
BUILTIN_TYPES = frozenset(
    {
        "bool",
        "char",
        "double",
        "float",
        "int",
        "long",
        "short",
        "size_t",
        "std.size_t",
        "std::size_t",
        "void",
    }
)
CONTROL_CALLS = frozenset({"if", "for", "while", "switch", "catch", "return", "sizeof"})
ALLOWED_OPERATION_KINDS = [
    "Function",
    "Let",
    "Call",
    "If",
    "While",
    "Case",
    "Tuple",
    "Projection",
    "Primitive",
    "Return",
]

FUNCTION_HEADER_RE = re.compile(
    r"(?P<prefix>(?:[A-Za-z_][\w:<>~*&,\s]+\s+)?)"
    r"(?P<name>[A-Za-z_~][\w:]*)\s*"
    r"\((?P<params>(?:[^;{}()]|\{\})*)\)\s*"
    r"(?P<suffix>[^{};]*)\{",
    re.MULTILINE,
)
RECORD_RE = re.compile(r"\b(?P<kind>class|struct)\s+(?P<name>[A-Za-z_]\w*)[^;{}]*\{")
NAMESPACE_RE = re.compile(r"\bnamespace\s+(?P<name>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\{")
METHOD_CALL_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_]\w*)\s*(?P<op>\.|->)\s*(?P<method>[A-Za-z_]\w*)\s*\("
)
DIRECT_CALL_RE = re.compile(r"(?<![\w:>.])(?P<name>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\(")
BRACE_CONSTRUCT_RE = re.compile(r"\b(?P<type>[A-Z][A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\{")
ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>(?:^|[;\n{])\s*)"
    r"(?P<decl>(?:[A-Za-z_][\w:<>]*\s+)*(?:[*&]\s*)?)?"
    r"(?P<target>[A-Za-z_]\w*)\s*=\s*(?P<expr>[^;]+);",
    re.MULTILINE,
)
BRACE_INITIALIZER_RE = re.compile(
    r"(?P<type>[A-Za-z_][\w:<>]*)\s+(?P<target>[A-Za-z_]\w*)\s*\{(?P<expr>[^;{}]*)\};",
    re.MULTILINE,
)
RETURN_RE = re.compile(r"\breturn\s+(?P<expr>[^;]+);")
IF_RE = re.compile(r"\bif\s*\(")
WHILE_RE = re.compile(r"\bwhile\s*\(")
FOR_RE = re.compile(r"\bfor\s*\(")
SWITCH_RE = re.compile(r"\bswitch\s*\(")
CASE_LABEL_RE = re.compile(r"\bcase\s+(?P<label>[^:]+):|\bdefault\s*:")


@dataclass(frozen=True)
class CxxSymbol:
    """One parsed C++ record, function, or method."""

    path: Path
    relative_path: str
    qualname: str
    node_kind: str
    lineno: int
    end_lineno: int | None
    header_text: str
    body_text: str
    params: str
    return_type: str | None
    record_name: str | None


@dataclass(frozen=True)
class CxxIndex:
    """C++ symbol index for one source file."""

    path: Path
    relative_path: str
    source_text: str
    source_sha256: str
    symbols: Mapping[str, CxxSymbol]
    records: frozenset[str]
    methods: Mapping[str, frozenset[str]]
    parse_warnings: tuple[str, ...]


@dataclass(frozen=True)
class CxxParseContext:
    """Shared context for converting function header matches into symbols."""

    path: Path
    relative: str
    source: str
    spans: Sequence[tuple[str, str, int, int]]
    namespaces: Sequence[tuple[str, int, int]]
    records: frozenset[str]


@dataclass(frozen=True)
class CxxCallSite:
    """One C++ call expression with shallow assignment context."""

    call_text: str
    line: int
    assigned_to: tuple[str, ...]
    receiver_name: str | None
    receiver_type: str | None
    target_symbol: str
    edge_kind: str
    resolved: bool


@dataclass(frozen=True)
class CxxControlSite:
    """One C++ control-flow site with static path alternatives."""

    keyword: str
    kind: str
    opcode: str
    line: int
    offset: int
    condition: str
    alternatives: tuple[str, ...]


@dataclass(frozen=True)
class CxxSourceFact:
    """One shallow source equation extracted from a C++ function body."""

    fact_id: str
    source_path: str
    source_symbol: str
    source_span: str
    fact_kind: str
    target: str
    expression: str
    statement: str
    text_sha256: str


@dataclass
class OperationalTables:
    """Mutable tables used while assembling the thin operational IR."""

    ops: list[dict[str, object]]
    functions: list[dict[str, object]]
    regions: list[dict[str, object]]
    expansion_edges: list[dict[str, object]]
    code_paths: list[dict[str, object]]
    function_signatures: list[str]
    region_by_function: dict[str, dict[str, object]]


@dataclass(frozen=True)
class OpSpec:
    """Specification for one operational IR operation row."""

    op_id: str
    kind: str
    opcode: str
    line: int
    text: str
    function: str
    parent_op_id: str
    call_target: str
    extra: Mapping[str, object]


def sha256_text(text: str) -> str:
    """Return a stable SHA-256 digest for text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_qualname(value: str) -> str:
    """Normalize common C++ ``::`` separators to dotted symbols."""
    normalized = value.strip().replace("::", ".")
    while ".." in normalized:
        normalized = normalized.replace("..", ".")
    return normalized.strip(".")


def normalize_space(value: str) -> str:
    """Return compact single-line source text."""
    return " ".join(value.strip().split())


def int_value(value: object, default: int = 0) -> int:
    """Return an integer JSON-ish value."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default


def mapping_value(value: object) -> Mapping[str, object]:
    """Return a JSON object mapping or an empty mapping."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def relative_path(path: Path, root: Path) -> str:
    """Return a stable POSIX relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def blank_comment_match(match: re.Match[str]) -> str:
    """Return spaces for a comment while preserving line breaks."""
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def line_for_offset(source: str, offset: int) -> int:
    """Return a 1-based line number for one source offset."""
    return source.count("\n", 0, offset) + 1


def find_matching_brace(source: str, open_offset: int) -> int:
    """Return the matching close-brace offset."""
    depth = 0
    for offset in range(open_offset, len(source)):
        char = source[offset]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return offset
    raise ValueError(f"unclosed brace at offset {open_offset}")


def find_matching_delimiter(
    source: str,
    open_offset: int,
    *,
    open_char: str,
    close_char: str,
) -> int:
    """Return the matching close delimiter offset."""
    depth = 0
    for offset in range(open_offset, len(source)):
        char = source[offset]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return offset
    raise ValueError(f"unclosed delimiter at offset {open_offset}")


def split_top_level_csv(text: str) -> tuple[str, ...]:
    """Split a comma-separated list without template or brace-depth confusion."""
    parts: list[str] = []
    depth = 0
    start = 0
    pairs = {"<": ">", "(": ")", "[": "]", "{": "}"}
    closing = set(pairs.values())
    for index, char in enumerate(text):
        if char in pairs:
            depth += 1
        elif char in closing and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                parts.append(item)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def clean_type_name(type_text: str) -> str | None:
    """Return a simple type name from a C++ declaration fragment."""
    cleaned = type_text.strip()
    cleaned = re.sub(r"=.*$", "", cleaned).strip()
    cleaned = re.sub(r"\b(const|constexpr|volatile|static|mutable|inline)\b", " ", cleaned)
    cleaned = cleaned.replace("&", " ").replace("*", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    token = normalize_qualname(cleaned.split()[-1])
    if token in BUILTIN_TYPES or token in TYPE_QUALIFIERS:
        return None
    return token


def parameter_records(params: str) -> tuple[dict[str, object], ...]:
    """Return source-level public parameter records."""
    records: list[dict[str, object]] = []
    for index, param in enumerate(split_top_level_csv(params)):
        normalized = re.sub(r"=.*$", "", param).strip()
        match = re.search(r"(?P<name>[A-Za-z_]\w*)\s*(?:\[[^\]]*\])?$", normalized)
        if match is None:
            records.append(
                {
                    "index": index,
                    "name": f"arg{index}",
                    "declaration": normalize_space(param),
                    "type": "",
                }
            )
            continue
        name = match.group("name")
        type_text = normalize_space(normalized[: match.start("name")])
        records.append(
            {
                "index": index,
                "name": name,
                "declaration": normalize_space(param),
                "type": type_text,
                "record_type": clean_type_name(type_text) or "",
            }
        )
    return tuple(records)


def parameter_types(params: str) -> dict[str, str]:
    """Infer parameter variable types from simple declarations."""
    return {
        str(record["name"]): str(record["record_type"])
        for record in parameter_records(params)
        if record.get("record_type")
    }


def declaration_type(declaration: str) -> str | None:
    """Infer a declared type from a C++ assignment prefix."""
    return clean_type_name(declaration.strip())


def constructor_type_from_expression(expression: str, records: frozenset[str]) -> str | None:
    """Infer a record type from a simple constructor expression."""
    expression = expression.strip()
    match = re.match(r"(?P<name>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*(?:\(|\{)", expression)
    if match is None:
        return None
    name = normalize_qualname(match.group("name")).rsplit(".", 1)[-1]
    return name if name in records else None


def collect_assignment_targets(body: str) -> dict[str, tuple[str, ...]]:
    """Map expression prefixes to assignment target names."""
    targets: dict[str, tuple[str, ...]] = {}
    for match in ASSIGNMENT_RE.finditer(body):
        expr = normalize_space(match.group("expr"))
        target = match.group("target")
        targets[expr] = (target,)
        call_prefix = normalize_qualname(expr.split("(", 1)[0].strip())
        if call_prefix:
            targets.setdefault(call_prefix, (target,))
    for match in BRACE_INITIALIZER_RE.finditer(body):
        type_name = match.group("type")
        target = match.group("target")
        expr = f"{type_name}{{{normalize_space(match.group('expr'))}}}"
        targets[expr] = (target,)
        targets.setdefault(normalize_qualname(type_name), (target,))
    return targets


def update_local_types_from_assignments(
    body: str,
    instance_types: dict[str, str],
    records: frozenset[str],
) -> None:
    """Infer local variable types from simple assignment and initializer statements."""
    for match in ASSIGNMENT_RE.finditer(body):
        target = match.group("target")
        declared_type = declaration_type(match.group("decl") or "")
        expression_type = constructor_type_from_expression(match.group("expr"), records)
        inferred = expression_type or declared_type
        if inferred is not None and inferred != "auto":
            instance_types[target] = inferred
    for match in BRACE_INITIALIZER_RE.finditer(body):
        type_name = clean_type_name(match.group("type"))
        if type_name is not None:
            instance_types[match.group("target")] = type_name


def parse_cpp_symbol_reference(reference: str) -> tuple[Path, str]:
    """Parse a ``path.cpp::qualname`` reference."""
    if "::" not in reference:
        raise ValueError("--cpp-symbol must use path.cpp::qualname syntax")
    raw_path, raw_qualname = reference.split("::", 1)
    path = Path(raw_path.strip())
    qualname = normalize_qualname(raw_qualname.strip())
    if not str(path):
        raise ValueError("--cpp-symbol path is empty")
    if not qualname:
        raise ValueError("--cpp-symbol qualname is empty")
    return path, qualname


def record_spans(source: str) -> tuple[tuple[str, str, int, int], ...]:
    """Return record body spans as ``(kind, name, open, close)`` tuples."""
    spans: list[tuple[str, str, int, int]] = []
    for match in RECORD_RE.finditer(source):
        close = find_matching_brace(source, match.end() - 1)
        spans.append((match.group("kind"), match.group("name"), match.end() - 1, close))
    return tuple(spans)


def namespace_spans(source: str) -> tuple[tuple[str, int, int], ...]:
    """Return namespace body spans as ``(name, open, close)`` tuples."""
    spans: list[tuple[str, int, int]] = []
    for match in NAMESPACE_RE.finditer(source):
        close = find_matching_brace(source, match.end() - 1)
        spans.append((normalize_qualname(match.group("name")), match.end() - 1, close))
    return tuple(spans)


def containing_record(
    spans: Sequence[tuple[str, str, int, int]],
    header_start: int,
) -> tuple[str, str] | None:
    """Return the innermost record containing one function header."""
    containing = [
        (kind, name, start, close)
        for kind, name, start, close in spans
        if start < header_start < close
    ]
    if not containing:
        return None
    kind, name, _, _ = max(containing, key=lambda item: item[2])
    return kind, name


def containing_namespace(spans: Sequence[tuple[str, int, int]], header_start: int) -> str:
    """Return the innermost namespace that should be part of a function symbol."""
    containing = [
        (name, start, close) for name, start, close in spans if start < header_start < close
    ]
    if not containing:
        return ""
    name, _, _ = max(containing, key=lambda item: item[1])
    return name


def return_type_from_header(prefix: str, name: str, record_name: str) -> str | None:
    """Infer a return type from a simple C++ function header."""
    prefix = normalize_space(prefix)
    if not prefix:
        return None
    leaf_name = name.rsplit("::", 1)[-1]
    if record_name and leaf_name in {record_name, f"~{record_name}"}:
        return None
    tokens = [token for token in prefix.split() if token not in TYPE_QUALIFIERS]
    return " ".join(tokens) if tokens else None


def record_symbols(
    path: Path,
    relative: str,
    source: str,
    spans: Sequence[tuple[str, str, int, int]],
) -> dict[str, CxxSymbol]:
    """Build record declaration symbols."""
    symbols: dict[str, CxxSymbol] = {}
    for kind, name, open_offset, close_offset in spans:
        lineno = line_for_offset(source, source.rfind(kind, 0, open_offset))
        end_lineno = line_for_offset(source, close_offset)
        symbols[name] = CxxSymbol(
            path=path,
            relative_path=relative,
            qualname=name,
            node_kind=f"Cxx{kind.title()}Decl",
            lineno=lineno,
            end_lineno=end_lineno,
            header_text=f"{kind} {name}",
            body_text=source[open_offset + 1 : close_offset],
            params="",
            return_type=None,
            record_name=None,
        )
    return symbols


def function_record_name(
    raw_name: str,
    header_start: int,
    spans: Sequence[tuple[str, str, int, int]],
    records: frozenset[str],
) -> str:
    """Infer the owning record name for a function-like header."""
    record = containing_record(spans, header_start)
    if record is not None:
        return record[1]
    parts = normalize_qualname(raw_name).split(".")
    if len(parts) >= 2 and parts[-2] in records:
        return parts[-2]
    return ""


def function_qualname(
    raw_name: str,
    record_name: str,
    namespace_name: str,
    records: frozenset[str],
) -> str:
    """Return the source symbol name for a C++ function-like header."""
    qualname = normalize_qualname(raw_name)
    if record_name and "." not in qualname:
        return f"{record_name}.{qualname}"
    parts = qualname.split(".")
    if len(parts) >= 2 and parts[-2] in records:
        return f"{parts[-2]}.{parts[-1]}"
    if namespace_name and "." not in qualname:
        return f"{namespace_name}.{qualname}"
    return qualname


def function_symbol_from_match(
    context: CxxParseContext,
    match: re.Match[str],
) -> CxxSymbol | None:
    """Build a function or method symbol from one regex match."""
    raw_name = match.group("name")
    if raw_name in CONTROL_CALLS or raw_name in CXX_KEYWORDS:
        return None
    open_offset = match.end() - 1
    close_offset = find_matching_brace(context.source, open_offset)
    record_name = function_record_name(
        raw_name,
        match.start(),
        context.spans,
        context.records,
    )
    namespace_name = containing_namespace(context.namespaces, match.start())
    qualname = function_qualname(raw_name, record_name, namespace_name, context.records)
    leaf = qualname.rsplit(".", 1)[-1]
    if leaf in CXX_KEYWORDS:
        return None
    node_kind = "CxxMethodDecl" if record_name else "CxxFunctionDecl"
    return CxxSymbol(
        path=context.path,
        relative_path=context.relative,
        qualname=qualname,
        node_kind=node_kind,
        lineno=line_for_offset(context.source, match.start()),
        end_lineno=line_for_offset(context.source, close_offset),
        header_text=normalize_space(context.source[match.start() : open_offset]),
        body_text=context.source[open_offset + 1 : close_offset],
        params=match.group("params"),
        return_type=return_type_from_header(match.group("prefix") or "", raw_name, record_name),
        record_name=record_name or None,
    )


def load_cxx_index(path: Path, root: Path) -> CxxIndex:
    """Parse one C++ file and index records/functions with lightweight source scanning."""
    if not path.is_file():
        raise ValueError(f"C++ source path does not exist: {path}")
    raw_source = path.read_text(encoding="utf-8")
    source = re.sub(r"//[^\n]*|/\*.*?\*/", blank_comment_match, raw_source, flags=re.DOTALL)
    relative = relative_path(path, root)
    warnings: list[str] = []
    try:
        spans = record_spans(source)
        namespaces = namespace_spans(source)
    except ValueError as exc:
        raise ValueError(f"C++ parse error: {exc}") from exc
    records = frozenset(name for _, name, _, _ in spans)
    symbols = record_symbols(path, relative, source, spans)
    methods: dict[str, set[str]] = {name: set() for name in records}
    context = CxxParseContext(
        path=path,
        relative=relative,
        source=source,
        spans=spans,
        namespaces=namespaces,
        records=records,
    )
    for match in FUNCTION_HEADER_RE.finditer(source):
        try:
            symbol = function_symbol_from_match(context, match)
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        if symbol is None:
            continue
        symbols[symbol.qualname] = symbol
        if symbol.record_name is not None:
            leaf = symbol.qualname.rsplit(".", 1)[-1]
            methods.setdefault(symbol.record_name, set()).add(leaf)
    return CxxIndex(
        path=path,
        relative_path=relative,
        source_text=source,
        source_sha256=sha256_text(source),
        symbols=symbols,
        records=records,
        methods={key: frozenset(value) for key, value in methods.items()},
        parse_warnings=tuple(warnings),
    )


def find_symbol(index: CxxIndex, qualname: str) -> CxxSymbol:
    """Find a symbol in one C++ index."""
    symbol = index.symbols.get(qualname)
    if symbol is None:
        raise ValueError(f"C++ source symbol not found: {qualname}")
    return symbol


def resolve_direct_call(name: str, index: CxxIndex, current_symbol: CxxSymbol) -> tuple[str, bool]:
    """Resolve a direct C++ call target inside one parsed source file."""
    normalized = normalize_qualname(name)
    leaf = normalized.rsplit(".", 1)[-1]
    if normalized in index.symbols:
        return normalized, True
    if leaf in index.symbols:
        return leaf, True
    if current_symbol.record_name is not None:
        method_symbol = f"{current_symbol.record_name}.{leaf}"
        if method_symbol in index.symbols:
            return method_symbol, True
    if "." in current_symbol.qualname:
        scoped_symbol = f"{current_symbol.qualname.rsplit('.', 1)[0]}.{leaf}"
        if scoped_symbol in index.symbols:
            return scoped_symbol, True
    if leaf in index.records:
        return leaf, True
    return normalized, False


def classify_call_edge_kind(
    call_text: str,
    target_symbol: str,
    assigned_to: tuple[str, ...],
    has_receiver: bool,
    index: CxxIndex,
) -> str:
    """Classify a C++ source call site."""
    lowered = call_text.lower()
    leaf = target_symbol.rsplit(".", 1)[-1]
    if target_symbol in index.records or leaf in index.records:
        return "constructs"
    if leaf == "initialize" or lowered.endswith(".initialize"):
        return "initializes"
    if "certificate" in lowered or "stopping" in lowered or leaf.endswith("Info"):
        return "requests_certificate"
    if has_receiver:
        return "method_call"
    if assigned_to and any("state" in target.lower() for target in assigned_to):
        return "updates_state"
    return "calls"


def initial_instance_types(index: CxxIndex, symbol: CxxSymbol) -> dict[str, str]:
    """Infer local instance types visible at the start of a symbol body."""
    instance_types = parameter_types(symbol.params)
    if symbol.record_name is not None:
        instance_types["this"] = symbol.record_name
    update_local_types_from_assignments(symbol.body_text, instance_types, index.records)
    return instance_types


def source_line_for_body_match(symbol: CxxSymbol, match: re.Match[str]) -> int:
    """Return a source line for one body-local regex match."""
    return symbol.lineno + line_for_offset(symbol.body_text, match.start()) - 1


def control_condition(body: str, match: re.Match[str]) -> str:
    """Return a normalized parenthesized control condition."""
    open_offset = match.end() - 1
    try:
        close_offset = find_matching_delimiter(
            body,
            open_offset,
            open_char="(",
            close_char=")",
        )
    except ValueError:
        return ""
    return normalize_space(body[open_offset + 1 : close_offset])


def switch_alternatives(body: str, match: re.Match[str]) -> tuple[str, ...]:
    """Return static switch path alternatives from shallow case labels."""
    try:
        condition_close = find_matching_delimiter(
            body,
            match.end() - 1,
            open_char="(",
            close_char=")",
        )
    except ValueError:
        return ("case_or_default",)
    open_brace = body.find("{", condition_close)
    if open_brace == -1:
        return ("case_or_default",)
    try:
        close_brace = find_matching_brace(body, open_brace)
    except ValueError:
        return ("case_or_default",)
    labels: list[str] = []
    for label_match in CASE_LABEL_RE.finditer(body[open_brace + 1 : close_brace]):
        label = label_match.group("label")
        labels.append(f"case:{normalize_space(label)}" if label is not None else "default")
    return tuple(labels or ("case_or_default",))


def collect_control_sites(symbol: CxxSymbol) -> tuple[CxxControlSite, ...]:
    """Collect C++ control-flow sites with static path alternatives."""
    if not symbol.body_text:
        return ()
    sites: list[CxxControlSite] = []
    for match in IF_RE.finditer(symbol.body_text):
        sites.append(
            CxxControlSite(
                keyword="if",
                kind="If",
                opcode="cxx.if",
                line=source_line_for_body_match(symbol, match),
                offset=match.start(),
                condition=control_condition(symbol.body_text, match),
                alternatives=("then", "else"),
            )
        )
    for match in WHILE_RE.finditer(symbol.body_text):
        sites.append(
            CxxControlSite(
                keyword="while",
                kind="While",
                opcode="cxx.while",
                line=source_line_for_body_match(symbol, match),
                offset=match.start(),
                condition=control_condition(symbol.body_text, match),
                alternatives=("skip", "enter"),
            )
        )
    for match in FOR_RE.finditer(symbol.body_text):
        sites.append(
            CxxControlSite(
                keyword="for",
                kind="While",
                opcode="cxx.for",
                line=source_line_for_body_match(symbol, match),
                offset=match.start(),
                condition=control_condition(symbol.body_text, match),
                alternatives=("skip", "enter"),
            )
        )
    for match in SWITCH_RE.finditer(symbol.body_text):
        sites.append(
            CxxControlSite(
                keyword="switch",
                kind="Case",
                opcode="cxx.switch",
                line=source_line_for_body_match(symbol, match),
                offset=match.start(),
                condition=control_condition(symbol.body_text, match),
                alternatives=switch_alternatives(symbol.body_text, match),
            )
        )
    return tuple(sorted(sites, key=lambda site: (site.offset, site.keyword)))


def method_call_sites(
    index: CxxIndex,
    symbol: CxxSymbol,
    assignment_targets: Mapping[str, tuple[str, ...]],
    instance_types: Mapping[str, str],
) -> tuple[CxxCallSite, ...]:
    """Collect object method call sites."""
    sites: list[CxxCallSite] = []
    for match in METHOD_CALL_RE.finditer(symbol.body_text):
        receiver = match.group("receiver")
        method = match.group("method")
        receiver_type = instance_types.get(receiver)
        call_text = f"{receiver}{match.group('op')}{method}"
        target_symbol = (
            f"{receiver_type}.{method}" if receiver_type else call_text.replace("->", ".")
        )
        sites.append(
            CxxCallSite(
                call_text=call_text,
                line=source_line_for_body_match(symbol, match),
                assigned_to=assignment_targets.get(call_text, ()),
                receiver_name=receiver,
                receiver_type=receiver_type,
                target_symbol=target_symbol,
                edge_kind="method_call",
                resolved=bool(receiver_type and target_symbol in index.symbols),
            )
        )
    return tuple(sites)


def direct_call_candidate(index: CxxIndex, body: str, match: re.Match[str]) -> bool:
    """Return whether a direct-call regex match is a candidate call edge."""
    name = match.group("name")
    if name in CXX_KEYWORDS or name in CONTROL_CALLS:
        return False
    leaf = normalize_qualname(name).rsplit(".", 1)[-1]
    if leaf in index.records:
        tail = body[match.end() : match.end() + 80]
        if re.match(r"\s*[^;{}()]*[;{]", tail):
            return False
    return not (match.start() > 0 and body[match.start() - 1] in ".>")


def direct_call_sites(
    index: CxxIndex,
    symbol: CxxSymbol,
    assignment_targets: Mapping[str, tuple[str, ...]],
) -> tuple[CxxCallSite, ...]:
    """Collect direct function or constructor call sites."""
    sites: list[CxxCallSite] = []
    for match in DIRECT_CALL_RE.finditer(symbol.body_text):
        if not direct_call_candidate(index, symbol.body_text, match):
            continue
        name = match.group("name")
        target_symbol, resolved = resolve_direct_call(name, index, symbol)
        call_text = normalize_qualname(name)
        assigned_to = assignment_targets.get(call_text, ())
        sites.append(
            CxxCallSite(
                call_text=call_text,
                line=source_line_for_body_match(symbol, match),
                assigned_to=assigned_to,
                receiver_name=None,
                receiver_type=None,
                target_symbol=target_symbol,
                edge_kind=classify_call_edge_kind(
                    call_text,
                    target_symbol,
                    assigned_to,
                    False,
                    index,
                ),
                resolved=resolved,
            )
        )
    return tuple(sites)


def brace_construct_call_sites(
    index: CxxIndex,
    symbol: CxxSymbol,
    assignment_targets: Mapping[str, tuple[str, ...]],
) -> tuple[CxxCallSite, ...]:
    """Collect record construction sites in brace-call form."""
    sites: list[CxxCallSite] = []
    for match in BRACE_CONSTRUCT_RE.finditer(symbol.body_text):
        type_name = normalize_qualname(match.group("type")).rsplit(".", 1)[-1]
        if type_name not in index.records:
            continue
        sites.append(
            CxxCallSite(
                call_text=type_name,
                line=source_line_for_body_match(symbol, match),
                assigned_to=assignment_targets.get(type_name, ()),
                receiver_name=None,
                receiver_type=None,
                target_symbol=type_name,
                edge_kind="constructs",
                resolved=True,
            )
        )
    return tuple(sites)


def brace_initializer_call_sites(index: CxxIndex, symbol: CxxSymbol) -> tuple[CxxCallSite, ...]:
    """Collect ``Type value{...}`` record construction sites."""
    sites: list[CxxCallSite] = []
    for match in BRACE_INITIALIZER_RE.finditer(symbol.body_text):
        type_name = normalize_qualname(match.group("type")).rsplit(".", 1)[-1]
        if type_name not in index.records:
            continue
        sites.append(
            CxxCallSite(
                call_text=type_name,
                line=source_line_for_body_match(symbol, match),
                assigned_to=(match.group("target"),),
                receiver_name=None,
                receiver_type=None,
                target_symbol=type_name,
                edge_kind="constructs",
                resolved=True,
            )
        )
    return tuple(sites)


def dedupe_call_sites(sites: Iterable[CxxCallSite]) -> tuple[CxxCallSite, ...]:
    """Return call sites with stable duplicate suppression."""
    deduped: list[CxxCallSite] = []
    seen: set[tuple[str, int, tuple[str, ...], str]] = set()
    for site in sites:
        key = (site.call_text, site.line, site.assigned_to, site.target_symbol)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(site)
    return tuple(deduped)


def collect_call_sites(index: CxxIndex, symbol: CxxSymbol) -> tuple[CxxCallSite, ...]:
    """Collect C++ call sites with shallow local type inference."""
    if not symbol.body_text:
        return ()
    assignment_targets = collect_assignment_targets(symbol.body_text)
    instance_types = initial_instance_types(index, symbol)
    return dedupe_call_sites(
        (
            *method_call_sites(index, symbol, assignment_targets, instance_types),
            *direct_call_sites(index, symbol, assignment_targets),
            *brace_construct_call_sites(index, symbol, assignment_targets),
            *brace_initializer_call_sites(index, symbol),
        )
    )


def make_source_fact(
    index: CxxIndex,
    symbol: CxxSymbol,
    *,
    fact_kind: str,
    target: str,
    expression: str,
    line: int,
) -> CxxSourceFact:
    """Create one stable source fact from C++ source text."""
    text = normalize_space(expression)
    fact_id = (
        f"fact:{index.relative_path}:{symbol.qualname}:{fact_kind}:"
        f"{line}:{target}"
    )
    return CxxSourceFact(
        fact_id=fact_id,
        source_path=index.relative_path,
        source_symbol=symbol.qualname,
        source_span=f"{line}:None",
        fact_kind=fact_kind,
        target=target,
        expression=text,
        statement=f"`{symbol.qualname}` {fact_kind} `{target}` as `{text}`.",
        text_sha256=sha256_text(text),
    )


def collect_source_facts(index: CxxIndex, symbol: CxxSymbol) -> tuple[CxxSourceFact, ...]:
    """Collect local assignment and return equations from one C++ symbol."""
    if not symbol.body_text:
        return ()
    facts: list[CxxSourceFact] = []
    for match in ASSIGNMENT_RE.finditer(symbol.body_text):
        facts.append(
            make_source_fact(
                index,
                symbol,
                fact_kind="assignment_equation",
                target=match.group("target"),
                expression=match.group("expr"),
                line=source_line_for_body_match(symbol, match),
            )
        )
    for match in BRACE_INITIALIZER_RE.finditer(symbol.body_text):
        facts.append(
            make_source_fact(
                index,
                symbol,
                fact_kind="assignment_equation",
                target=match.group("target"),
                expression=f"{match.group('type')}{{{normalize_space(match.group('expr'))}}}",
                line=source_line_for_body_match(symbol, match),
            )
        )
    for match in RETURN_RE.finditer(symbol.body_text):
        facts.append(
            make_source_fact(
                index,
                symbol,
                fact_kind="return_equation",
                target="return",
                expression=match.group("expr"),
                line=source_line_for_body_match(symbol, match),
            )
        )
    deduped: dict[str, CxxSourceFact] = {}
    for fact in facts:
        deduped.setdefault(fact.fact_id, fact)
    return tuple(deduped.values())


def has_expandable_body(symbol: CxxSymbol) -> bool:
    """Return whether a parsed symbol should be included as a function body."""
    return symbol.node_kind in {"CxxFunctionDecl", "CxxMethodDecl"} and bool(symbol.body_text)


def add_symbol_facts(
    facts: dict[str, CxxSourceFact],
    index: CxxIndex,
    symbol: CxxSymbol,
) -> None:
    """Add source facts for one symbol to a stable fact mapping."""
    for fact in collect_source_facts(index, symbol):
        facts.setdefault(fact.fact_id, fact)


def resolved_reachable_targets(index: CxxIndex, symbol: CxxSymbol) -> tuple[str, ...]:
    """Return parsed, expandable target symbols reached by one source symbol."""
    targets: list[str] = []
    for site in collect_call_sites(index, symbol):
        if not site.resolved or site.target_symbol not in index.symbols:
            continue
        target = index.symbols[site.target_symbol]
        if has_expandable_body(target):
            targets.append(site.target_symbol)
    return tuple(targets)


def expand_reachable_symbols(
    index: CxxIndex,
    root_symbol: str,
) -> tuple[list[str], dict[str, CxxSourceFact]]:
    """Return parsed function symbols reachable from one root."""
    expanded: set[str] = set()
    function_symbols: list[str] = []
    facts: dict[str, CxxSourceFact] = {}
    pending = [root_symbol]
    while pending:
        symbol_name = pending.pop()
        if symbol_name in expanded or symbol_name not in index.symbols:
            continue
        symbol = index.symbols[symbol_name]
        expanded.add(symbol_name)
        if has_expandable_body(symbol):
            function_symbols.append(symbol_name)
        add_symbol_facts(facts, index, symbol)
        pending.extend(resolved_reachable_targets(index, symbol))
    return function_symbols, facts


def next_op_id(tables: OperationalTables) -> str:
    """Return the next operation id for the current table state."""
    return f"op_{len(tables.ops):05d}"


def append_op(tables: OperationalTables, region: dict[str, object], spec: OpSpec) -> None:
    """Append one operation row and assign it to a region."""
    record: dict[str, object] = {
        "op_id": spec.op_id,
        "kind": spec.kind,
        "opcode": spec.opcode,
        "line": spec.line,
        "text": normalize_space(spec.text),
        "text_sha256": sha256_text(normalize_space(spec.text)),
        "tensor_types": [],
        "dtypes": [],
        "function": spec.function,
        "region_id": region["region_id"],
        "region_path": [region["region_id"]],
        "parent_op_id": spec.parent_op_id,
        "call_target": spec.call_target,
    }
    record.update(spec.extra)
    tables.ops.append(record)
    op_ids = region.get("op_ids")
    if isinstance(op_ids, list):
        cast(list[object], op_ids).append(spec.op_id)
    else:
        region["op_ids"] = [spec.op_id]


def collect_control_ops(
    symbol: CxxSymbol,
    tables: OperationalTables,
    region: dict[str, object],
) -> None:
    """Collect shallow C++ control-operation markers."""
    for site in collect_control_sites(symbol):
        append_op(
            tables,
            region,
            OpSpec(
                op_id=next_op_id(tables),
                kind=site.kind,
                opcode=site.opcode,
                line=site.line,
                text=f"{site.keyword} ({site.condition})",
                function=symbol.qualname,
                parent_op_id="",
                call_target="",
                extra={
                    "condition": site.condition,
                    "path_alternatives": list(site.alternatives),
                },
            ),
        )


def new_operational_tables(index: CxxIndex, root_symbol: str) -> OperationalTables:
    """Create operational IR tables with the module root region."""
    module_region: dict[str, object] = {
        "region_id": "region_00000",
        "kind": "module",
        "parent_function": "",
        "parent_op_id": "",
        "depth": 0,
        "line_start": 1,
        "line_end": len(index.source_text.splitlines()),
        "op_ids": list[str](),
    }
    return OperationalTables(
        ops=[],
        functions=[],
        regions=[module_region],
        expansion_edges=[
            {
                "edge_id": "edge_00000",
                "kind": "program_root",
                "from": "program",
                "to": f"function:{root_symbol}",
            }
        ],
        code_paths=[],
        function_signatures=[],
        region_by_function={},
    )


def append_function_rows(
    tables: OperationalTables,
    index: CxxIndex,
    reachable_symbols: Sequence[str],
) -> None:
    """Append function and body-region records for reachable C++ symbols."""
    module_region = tables.regions[0]
    for symbol_name in reachable_symbols:
        symbol = index.symbols[symbol_name]
        function_op_id = next_op_id(tables)
        tables.function_signatures.append(symbol.header_text)
        append_op(
            tables,
            module_region,
            OpSpec(
                op_id=function_op_id,
                kind="Function",
                opcode="cxx.function",
                line=symbol.lineno,
                text=symbol.header_text,
                function=symbol.qualname,
                parent_op_id="",
                call_target="",
                extra={"source_symbol": symbol.qualname},
            ),
        )
        body_region: dict[str, object] = {
            "region_id": f"region_{len(tables.regions):05d}",
            "kind": "function_body",
            "parent_function": symbol.qualname,
            "parent_op_id": function_op_id,
            "depth": 1,
            "line_start": symbol.lineno,
            "line_end": symbol.end_lineno or symbol.lineno,
            "op_ids": list[str](),
        }
        tables.regions.append(body_region)
        tables.region_by_function[symbol.qualname] = body_region
        tables.expansion_edges.append(
            {
                "edge_id": f"edge_{len(tables.expansion_edges):05d}",
                "kind": "function_body",
                "from": f"function:{symbol.qualname}",
                "to": body_region["region_id"],
            }
        )
        tables.functions.append(
            {
                "function_id": f"function:{symbol.qualname}",
                "name": symbol.qualname,
                "signature": symbol.header_text,
                "line_start": symbol.lineno,
                "line_end": symbol.end_lineno or symbol.lineno,
                "body_region_id": body_region["region_id"],
            }
        )


def append_fact_ops(
    tables: OperationalTables,
    index: CxxIndex,
    symbol: CxxSymbol,
    region: dict[str, object],
) -> None:
    """Append assignment and return operations for one reachable C++ symbol."""
    for fact in collect_source_facts(index, symbol):
        is_return = fact.fact_kind == "return_equation"
        append_op(
            tables,
            region,
            OpSpec(
                op_id=next_op_id(tables),
                kind="Return" if is_return else "Let",
                opcode="cxx.return" if is_return else "cxx.assign",
                line=int(fact.source_span.split(":", maxsplit=1)[0]),
                text=fact.expression,
                function=symbol.qualname,
                parent_op_id="",
                call_target="",
                extra={"source_fact_id": fact.fact_id, "target": fact.target},
            ),
        )


def append_call_ops(
    tables: OperationalTables,
    index: CxxIndex,
    symbol: CxxSymbol,
    region: dict[str, object],
) -> None:
    """Append call operations and call-target expansion edges for one symbol."""
    for site in collect_call_sites(index, symbol):
        call_target = (
            site.target_symbol
            if site.resolved
            and site.target_symbol in index.symbols
            and has_expandable_body(index.symbols[site.target_symbol])
            else ""
        )
        op_id = next_op_id(tables)
        append_op(
            tables,
            region,
            OpSpec(
                op_id=op_id,
                kind="Call" if call_target else "Primitive",
                opcode="cxx.call",
                line=site.line,
                text=site.call_text,
                function=symbol.qualname,
                parent_op_id="",
                call_target=call_target,
                extra={
                    "edge_kind": site.edge_kind,
                    "assigned_to": list(site.assigned_to),
                    "receiver_name": site.receiver_name or "",
                    "receiver_type": site.receiver_type or "",
                    "resolved": site.resolved,
                    "target_symbol": site.target_symbol,
                },
            ),
        )
        if call_target:
            append_call_target_edge(tables, op_id, call_target)


def append_call_target_edge(
    tables: OperationalTables,
    op_id: str,
    call_target: str,
) -> None:
    """Append one callee expansion edge unless the target is already expanded."""
    edge_target = f"function:{call_target}"
    if any(
        edge["kind"] == "call_target" and edge["to"] == edge_target
        for edge in tables.expansion_edges
    ):
        return
    tables.expansion_edges.append(
        {
            "edge_id": f"edge_{len(tables.expansion_edges):05d}",
            "kind": "call_target",
            "from": op_id,
            "to": edge_target,
        }
    )


def append_body_ops(
    tables: OperationalTables,
    index: CxxIndex,
    reachable_symbols: Sequence[str],
) -> None:
    """Append control, source fact, and call operations for function bodies."""
    for symbol_name in reachable_symbols:
        symbol = index.symbols[symbol_name]
        region = tables.region_by_function[symbol.qualname]
        collect_control_ops(symbol, tables, region)
        append_fact_ops(tables, index, symbol, region)
        append_call_ops(tables, index, symbol, region)


def control_op_key(symbol: CxxSymbol, site: CxxControlSite) -> tuple[str, str, int, str]:
    """Return the stable key used to bind a control site to an op row."""
    return (symbol.qualname, site.opcode, site.line, site.condition)


def control_op_bindings(tables: OperationalTables) -> dict[tuple[str, str, int, str], str]:
    """Return control op ids keyed by function/opcode/line/condition."""
    bindings: dict[tuple[str, str, int, str], str] = {}
    for op in tables.ops:
        if str(op.get("opcode")) not in {"cxx.if", "cxx.while", "cxx.for", "cxx.switch"}:
            continue
        key = (
            str(op.get("function", "")),
            str(op.get("opcode", "")),
            int_value(op.get("line", 0)),
            str(op.get("condition", "")),
        )
        bindings[key] = str(op["op_id"])
    return bindings


def code_path_decision(
    symbol: CxxSymbol,
    site: CxxControlSite,
    choice: str,
    bindings: Mapping[tuple[str, str, int, str], str],
) -> dict[str, object]:
    """Build one code-path decision row."""
    return {
        "op_id": bindings.get(control_op_key(symbol, site), ""),
        "kind": site.keyword,
        "choice": choice,
        "condition": site.condition,
        "line": site.line,
    }


def code_path_rows_for_symbol(
    tables: OperationalTables,
    symbol: CxxSymbol,
    bindings: Mapping[tuple[str, str, int, str], str],
) -> tuple[dict[str, object], ...]:
    """Enumerate static control-flow path alternatives for one function."""
    region = tables.region_by_function[symbol.qualname]
    raw_op_ids = region.get("op_ids", [])
    op_ids = (
        [str(op_id) for op_id in cast(list[object], raw_op_ids)]
        if isinstance(raw_op_ids, list)
        else []
    )
    sites = collect_control_sites(symbol)
    if not sites:
        return (
            {
                "path_id": f"path:{symbol.qualname}:00000",
                "function": symbol.qualname,
                "region_id": region["region_id"],
                "op_ids": op_ids,
                "decisions": [],
                "decision_count": 0,
                "summary": "straight_line",
            },
        )
    paths: list[dict[str, object]] = []
    for path_index, choices in enumerate(product(*(site.alternatives for site in sites))):
        decisions = [
            code_path_decision(symbol, site, choice, bindings)
            for site, choice in zip(sites, choices, strict=True)
        ]
        summary = " -> ".join(
            f"{decision['kind']}@{decision['line']}:{decision['choice']}"
            for decision in decisions
        )
        paths.append(
            {
                "path_id": f"path:{symbol.qualname}:{path_index:05d}",
                "function": symbol.qualname,
                "region_id": region["region_id"],
                "op_ids": op_ids,
                "decisions": decisions,
                "decision_count": len(decisions),
                "summary": summary,
            }
        )
    return tuple(paths)


def append_code_paths(
    tables: OperationalTables,
    index: CxxIndex,
    reachable_symbols: Sequence[str],
) -> None:
    """Append static code-path rows for every reachable function."""
    bindings = control_op_bindings(tables)
    for symbol_name in reachable_symbols:
        symbol = index.symbols[symbol_name]
        tables.code_paths.extend(code_path_rows_for_symbol(tables, symbol, bindings))


def operational_coverage(tables: OperationalTables) -> dict[str, object]:
    """Build coverage counters for the assembled operational IR."""
    known_region_ids = {region["region_id"] for region in tables.regions}
    unassigned_ops = [
        op["op_id"] for op in tables.ops if op["region_id"] not in known_region_ids
    ]
    unresolved_call_targets = sorted(
        {
            str(op.get("target_symbol", op.get("call_target", "")))
            for op in tables.ops
            if op["opcode"] == "cxx.call"
            and not op.get("call_target")
            and not bool(op.get("resolved"))
            and str(op.get("target_symbol", ""))
        }
    )
    assigned_region_ids = {op["region_id"] for op in tables.ops}
    code_path_functions = {str(path["function"]) for path in tables.code_paths}
    function_names = {str(function["name"]) for function in tables.functions}
    unmapped_code_path_functions = sorted(function_names - code_path_functions)
    code_path_decision_count = sum(
        int_value(path.get("decision_count", 0)) for path in tables.code_paths
    )
    return {
        "function_count": len(tables.functions),
        "region_count": len(tables.regions),
        "expansion_edge_count": len(tables.expansion_edges),
        "op_count": len(tables.ops),
        "assigned_region_count": len(assigned_region_ids),
        "unassigned_op_count": len(unassigned_ops),
        "unassigned_op_ids": unassigned_ops,
        "unresolved_call_targets": unresolved_call_targets,
        "max_region_depth": max(
            (int_value(region.get("depth", 0)) for region in tables.regions),
            default=0,
        ),
        "while_count": sum(1 for op in tables.ops if op["kind"] == "While"),
        "case_count": sum(1 for op in tables.ops if op["kind"] == "Case"),
        "if_count": sum(1 for op in tables.ops if op["kind"] == "If"),
        "call_count": sum(1 for op in tables.ops if op["kind"] == "Call"),
        "code_path_count": len(tables.code_paths),
        "code_path_decision_count": code_path_decision_count,
        "max_code_path_decisions": max(
            (int_value(path.get("decision_count", 0)) for path in tables.code_paths),
            default=0,
        ),
        "unmapped_code_path_functions": unmapped_code_path_functions,
    }


def build_thin_operational_ir(index: CxxIndex, root_symbol: str) -> dict[str, object]:
    """Build the shared thin operational IR from parsed C++ source."""
    reachable_symbols, _facts = expand_reachable_symbols(index, root_symbol)
    tables = new_operational_tables(index, root_symbol)
    append_function_rows(tables, index, reachable_symbols)
    append_body_ops(tables, index, reachable_symbols)
    append_code_paths(tables, index, reachable_symbols)
    return {
        "schema": "agent-canon.thin-operational-ir.v2",
        "allowed_kinds": ALLOWED_OPERATION_KINDS,
        "function_signatures": tables.function_signatures,
        "functions": tables.functions,
        "regions": tables.regions,
        "expansion_edges": tables.expansion_edges,
        "code_paths": tables.code_paths,
        "ops": tables.ops,
        "coverage": operational_coverage(tables),
    }


def build_source_root(index: CxxIndex, cpp_symbol: str, symbol: CxxSymbol) -> dict[str, object]:
    """Build source-root metadata for the requested C++ symbol."""
    segment = symbol.header_text + "\n" + symbol.body_text
    return {
        "schema": "agent-canon.cpp-source-root.v1",
        "status": "ok",
        "cpp_symbol": cpp_symbol,
        "path": str(symbol.path),
        "relative_path": index.relative_path,
        "qualname": symbol.qualname,
        "name": symbol.qualname.rsplit(".", 1)[-1],
        "node_kind": symbol.node_kind,
        "parameters": [str(record["name"]) for record in parameter_records(symbol.params)],
        "return_type": symbol.return_type or "",
        "source_sha256": sha256_text(segment),
        "file_sha256": index.source_sha256,
        "source_span": f"{symbol.lineno}:{symbol.end_lineno}",
        "parse_warnings": list(index.parse_warnings),
    }


def build_public_interface(cpp_symbol: str, symbol: CxxSymbol) -> dict[str, object]:
    """Build a source public-interface record for the requested C++ symbol."""
    parameters = [dict(record) for record in parameter_records(symbol.params)]
    return {
        "schema": "agent-canon.cpp-public-interface.v1",
        "status": "ok",
        "cpp_symbol": cpp_symbol,
        "qualname": symbol.qualname,
        "name": symbol.qualname.rsplit(".", 1)[-1],
        "parameters": parameters,
        "return_type": symbol.return_type or "",
        "coverage": {
            "parameter_count": len(parameters),
            "has_return_type": bool(symbol.return_type),
            "stablehlo_specific_fields": 0,
        },
    }


def build_source_facts(index: CxxIndex, root_symbol: str) -> dict[str, object]:
    """Build source facts for the reachable C++ slice."""
    _reachable, facts = expand_reachable_symbols(index, root_symbol)
    rows = [asdict(fact) for fact in sorted(facts.values(), key=lambda item: item.fact_id)]
    return {
        "schema": "agent-canon.cpp-source-facts.v1",
        "facts": rows,
        "coverage": {
            "fact_count": len(rows),
            "assignment_equation_count": sum(
                1 for fact in rows if fact["fact_kind"] == "assignment_equation"
            ),
            "return_equation_count": sum(
                1 for fact in rows if fact["fact_kind"] == "return_equation"
            ),
        },
    }


def build_cpp_source_canonical_ir(cpp_symbol: str, *, root: Path) -> dict[str, object]:
    """Build the C++ source-canonical IR wrapper."""
    path, qualname = parse_cpp_symbol_reference(cpp_symbol)
    if not path.is_absolute():
        path = root / path
    index = load_cxx_index(path.resolve(), root.resolve())
    symbol = find_symbol(index, qualname)
    operational_ir = build_thin_operational_ir(index, qualname)
    operational_coverage_record = mapping_value(operational_ir.get("coverage"))
    return {
        "schema": "agent-canon.cpp-source-canonical-ir.v1",
        "root": {
            "schema": "agent-canon.cpp-source-root-ref.v1",
            "cpp_symbol": cpp_symbol,
            "repo_root": str(root.resolve()),
            "source_kind": "cxx_source",
            "source_path": index.relative_path,
            "qualname": qualname,
        },
        "source_root": build_source_root(index, cpp_symbol, symbol),
        "public_interface": build_public_interface(cpp_symbol, symbol),
        "source_facts": build_source_facts(index, qualname),
        "operational_ir": operational_ir,
        "coverage": {
            "record_count": len(index.records),
            "indexed_symbol_count": len(index.symbols),
            "reachable_function_count": int_value(
                operational_coverage_record.get("function_count", 0)
            ),
            "parse_warning_count": len(index.parse_warnings),
            "source_only": True,
        },
    }


def render_markdown(record: Mapping[str, object]) -> str:
    """Render a compact Markdown report."""
    root = mapping_value(record.get("root"))
    source_root = mapping_value(record.get("source_root"))
    operational_ir = mapping_value(record.get("operational_ir"))
    public_interface = mapping_value(record.get("public_interface"))
    source_facts = mapping_value(record.get("source_facts"))
    coverage = mapping_value(operational_ir.get("coverage"))
    public_interface_coverage = mapping_value(public_interface.get("coverage"))
    source_facts_coverage = mapping_value(source_facts.get("coverage"))
    lines = [
        "# C++ Source Canonical IR",
        "",
        f"- schema: `{record['schema']}`",
        f"- cpp_symbol: `{root.get('cpp_symbol', '')}`",
        f"- source_path: `{root.get('source_path', '')}`",
        f"- root_function: `{source_root.get('qualname', '')}`",
        "",
        "## Public Interface",
        "",
        f"- return_type: `{public_interface.get('return_type', '')}`",
        f"- parameter_count: `{public_interface_coverage.get('parameter_count', 0)}`",
        "",
        "## Operational IR Coverage",
        "",
        f"- functions: `{coverage.get('function_count', 0)}`",
        f"- ops: `{coverage.get('op_count', 0)}`",
        f"- calls: `{coverage.get('call_count', 0)}`",
        f"- code_paths: `{coverage.get('code_path_count', 0)}`",
        f"- unmapped_code_path_functions: `{coverage.get('unmapped_code_path_functions', [])}`",
        f"- unresolved_call_targets: `{coverage.get('unresolved_call_targets', [])}`",
        "",
        "## Source Facts",
        "",
        f"- fact_count: `{source_facts_coverage.get('fact_count', 0)}`",
    ]
    return "\n".join(lines) + "\n"


def render_text(record: Mapping[str, object]) -> str:
    """Render a compact text report."""
    root = mapping_value(record.get("root"))
    operational_ir = mapping_value(record.get("operational_ir"))
    coverage = mapping_value(operational_ir.get("coverage"))
    return "\n".join(
        [
            f"schema={record['schema']}",
            f"cpp_symbol={root.get('cpp_symbol', '')}",
            f"source_path={root.get('source_path', '')}",
            f"function_count={coverage.get('function_count', 0)}",
            f"op_count={coverage.get('op_count', 0)}",
            f"call_count={coverage.get('call_count', 0)}",
            f"code_path_count={coverage.get('code_path_count', 0)}",
            "unmapped_code_path_functions="
            f"{coverage.get('unmapped_code_path_functions', [])}",
            f"unresolved_call_targets={coverage.get('unresolved_call_targets', [])}",
        ]
    ) + "\n"


def render_record(record: Mapping[str, object], output_format: str) -> str:
    """Render one record in the requested CLI format."""
    if output_format == "json":
        return json.dumps(record, indent=2, sort_keys=True) + "\n"
    if output_format == "markdown":
        return render_markdown(record)
    return render_text(record)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root used to relativize paths.")
    parser.add_argument(
        "--cpp-symbol",
        required=True,
        help="Root C++ symbol in path.{cc,cpp,h,hpp}::qualname form.",
    )
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("--out", help="Optional output path. When omitted, print to stdout.")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the C++ source-canonical IR extractor."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root)
    try:
        record = build_cpp_source_canonical_ir(args.cpp_symbol, root=root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    rendered = render_record(record, str(args.format))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
