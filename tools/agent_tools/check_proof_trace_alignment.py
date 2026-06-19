#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks package-retained formal-proof trace claims against code-path anchors.
# upstream design ../../agents/skills/formal-proof-workflow.md defines alignment policy.
# downstream design ../../documents/tools/check_proof_trace_alignment.md documents CLI usage.
# downstream implementation ../../tests/agent_tools/test_check_proof_trace_alignment.py tests it.
# @dependency-end
"""Check that formal-proof trace contracts align with implementation anchors."""

from __future__ import annotations

import argparse
import ast
import json
import runpy
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

JsonMapping = Mapping[str, object]
JsonObject = dict[str, object]


@dataclass(frozen=True)
class Finding:
    """One proof-trace alignment finding."""

    contract: str
    anchor: str
    kind: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding line."""
        return (
            "PROOF_TRACE_ALIGNMENT_FINDING="
            f"{self.contract}:{self.anchor}:{self.kind}:{self.detail}"
        )


@dataclass(frozen=True)
class AnchorCheck:
    """One normalized source anchor to check."""

    contract_key: str
    anchor_id: str
    source_path: str | None
    qualname: str | None
    required_source_tokens: tuple[str, ...]
    forbidden_source_tokens: tuple[str, ...]
    required_ast_patterns: tuple[str, ...]
    min_return_count: int | None
    min_branch_count: int | None
    max_branch_count: int | None


@dataclass(frozen=True)
class AlignmentReport:
    """Proof trace alignment report."""

    status: str
    trace_path: str
    checked_contract_count: int
    checked_anchor_count: int
    findings: tuple[Finding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root used to resolve source_path entries.",
    )
    parser.add_argument(
        "--trace-module",
        required=True,
        help="Python proof trace module path containing FORMAL_PROOF_TRACE.",
    )
    parser.add_argument(
        "--trace-symbol",
        default="FORMAL_PROOF_TRACE",
        help="Global variable name that stores the trace mapping.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def as_mapping(value: object) -> JsonMapping | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(JsonMapping, mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return a sequence value, excluding strings and bytes."""
    if isinstance(value, str | bytes):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a trace value."""
    if isinstance(value, str):
        return (value,)
    sequence = as_sequence(value)
    if sequence is None:
        return ()
    return tuple(item for item in sequence if isinstance(item, str))


def int_or_none(value: object) -> int | None:
    """Return an integer value or None."""
    return value if isinstance(value, int) else None


def load_trace(path: Path, trace_symbol: str) -> JsonMapping:
    """Load a Python proof trace without importing it as a package module."""
    namespace = runpy.run_path(path.as_posix())
    value = namespace.get(trace_symbol)
    trace = as_mapping(value)
    if trace is None:
        raise ValueError(f"{path} does not define mapping {trace_symbol}")
    return trace


def checked_fragment_names(trace: JsonMapping) -> set[str]:
    """Return checked fragment names retained by the trace."""
    names: set[str] = set()
    for fragment in as_sequence(trace.get("checked_proof_fragments")) or ():
        mapping = as_mapping(fragment)
        if mapping is None:
            continue
        name = mapping.get("name")
        if isinstance(name, str):
            names.add(name)
    return names


def is_contract_entry(value: JsonMapping) -> bool:
    """Return whether a mapping looks like a proof contract entry."""
    return any(
        key in value
        for key in (
            "checked_fragment",
            "implementation_anchor",
            "implementation_anchors",
            "source_shape_anchor",
            "source_path",
            "source_symbol",
            "source_symbols",
        )
    )


def proof_contract_entries(trace: JsonMapping) -> list[tuple[str, JsonMapping]]:
    """Return top-level proof contract entries from a trace."""
    entries: list[tuple[str, JsonMapping]] = []
    for key, value in trace.items():
        mapping = as_mapping(value)
        if mapping is None or not is_contract_entry(mapping):
            continue
        entries.append((str(key), mapping))
    return entries


def inherited_anchor_mapping(
    contract: JsonMapping,
    raw_anchor: JsonMapping,
) -> JsonObject:
    """Return one anchor mapping with contract-level source defaults."""
    anchor = dict(raw_anchor)
    if "source_path" not in anchor and isinstance(contract.get("source_path"), str):
        anchor["source_path"] = contract["source_path"]
    if "source_symbol" not in anchor and isinstance(contract.get("source_symbol"), str):
        anchor["source_symbol"] = contract["source_symbol"]
    return anchor


def contract_anchor_mappings(contract: JsonMapping) -> list[JsonObject]:
    """Extract implementation anchor mappings from one contract."""
    anchors: list[JsonObject] = []
    for key in ("implementation_anchor", "source_shape_anchor"):
        mapping = as_mapping(contract.get(key))
        if mapping is not None:
            anchors.append(inherited_anchor_mapping(contract, mapping))
    sequence = as_sequence(contract.get("implementation_anchors")) or ()
    for item in sequence:
        mapping = as_mapping(item)
        if mapping is not None:
            anchors.append(inherited_anchor_mapping(contract, mapping))

    if isinstance(contract.get("source_path"), str):
        source_symbols = string_tuple(contract.get("source_symbols"))
        if isinstance(contract.get("source_symbol"), str):
            source_symbols = (*source_symbols, str(contract["source_symbol"]))
        if not anchors and not source_symbols:
            anchors.append({"source_path": contract["source_path"]})
        for symbol in source_symbols:
            anchors.append(
                {
                    "source_path": contract["source_path"],
                    "source_symbol": symbol,
                }
            )
    return anchors


def normalize_anchor(
    contract_key: str,
    index: int,
    anchor: JsonMapping,
) -> AnchorCheck:
    """Normalize a raw trace anchor into a check record."""
    qualname = anchor.get("qualname", anchor.get("source_symbol"))
    source_path = anchor.get("source_path")
    anchor_id = (
        str(anchor.get("id"))
        if isinstance(anchor.get("id"), str)
        else f"anchor-{index}"
    )
    return AnchorCheck(
        contract_key=contract_key,
        anchor_id=anchor_id,
        source_path=source_path if isinstance(source_path, str) else None,
        qualname=qualname if isinstance(qualname, str) else None,
        required_source_tokens=string_tuple(anchor.get("required_source_tokens")),
        forbidden_source_tokens=string_tuple(anchor.get("forbidden_source_tokens")),
        required_ast_patterns=string_tuple(anchor.get("required_ast_patterns")),
        min_return_count=int_or_none(anchor.get("min_return_count")),
        min_branch_count=int_or_none(anchor.get("min_branch_count")),
        max_branch_count=int_or_none(anchor.get("max_branch_count")),
    )


def contract_anchors(contract_key: str, contract: JsonMapping) -> list[AnchorCheck]:
    """Return normalized anchors for one contract."""
    return [
        normalize_anchor(contract_key, index, anchor)
        for index, anchor in enumerate(contract_anchor_mappings(contract), start=1)
    ]


def resolve_source_path(root: Path, source_path: str) -> Path:
    """Resolve a trace source path through root or vendored AgentCanon."""
    direct = root / source_path
    if direct.exists():
        return direct
    vendored = root / "vendor" / "agent-canon" / source_path
    if vendored.exists():
        return vendored
    return direct


PythonSymbol = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def find_ast_symbol(module: ast.Module, qualname: str) -> PythonSymbol:
    """Find a class/function by dotted qualname."""
    current_body: list[ast.stmt] = list(module.body)
    current: PythonSymbol | None = None
    for part in tuple(part for part in qualname.split(".") if part):
        current = None
        for node in current_body:
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name == part:
                    current = node
                    current_body = list(node.body)
                    break
        if current is None:
            raise ValueError(f"AST symbol not found: {qualname}")
    if current is None:
        raise ValueError("empty AST qualname")
    return current


def ast_shape_counts(node: ast.AST) -> tuple[int, int]:
    """Count return and branch nodes in an AST subtree."""
    return_count = sum(isinstance(inner, ast.Return) for inner in ast.walk(node))
    branch_count = sum(isinstance(inner, ast.If | ast.Match) for inner in ast.walk(node))
    return return_count, branch_count


def compact_space(value: str) -> str:
    """Normalize whitespace in a source expression."""
    return " ".join(value.split())


def ast_operation_candidates(node: ast.AST) -> tuple[str, ...]:
    """Return source-like expression candidates for one AST node."""
    try:
        if isinstance(node, ast.Call):
            return (
                compact_space(ast.unparse(node.func)),
                compact_space(ast.unparse(node)),
            )
        if isinstance(node, ast.expr) and not isinstance(node, ast.Constant | ast.Name):
            return (compact_space(ast.unparse(node)),)
    except Exception:  # pragma: no cover - defensive for unusual parser nodes.
        return ()
    return ()


def ast_operation_snippets(node: ast.AST) -> set[str]:
    """Return normalized source-like expressions in an AST subtree."""
    snippets: set[str] = set()
    for inner in ast.walk(node):
        snippets.update(ast_operation_candidates(inner))
    return snippets


def check_anchor(root: Path, anchor: AnchorCheck) -> list[Finding]:
    """Check one normalized source anchor."""
    findings: list[Finding] = []
    if anchor.source_path is None:
        findings.append(
            Finding(anchor.contract_key, anchor.anchor_id, "missing-source-path", "-")
        )
        return findings

    source_file = resolve_source_path(root, anchor.source_path)
    if not source_file.is_file():
        findings.append(
            Finding(
                anchor.contract_key,
                anchor.anchor_id,
                "missing-source-file",
                anchor.source_path,
            )
        )
        return findings

    source_text = source_file.read_text(encoding="utf-8")
    source_segment = source_text
    node: ast.AST | None = None
    if anchor.qualname is not None:
        try:
            module = ast.parse(source_text, filename=source_file.as_posix())
            node = find_ast_symbol(module, anchor.qualname)
        except (SyntaxError, ValueError) as exc:
            findings.append(
                Finding(
                    anchor.contract_key,
                    anchor.anchor_id,
                    "missing-ast-symbol",
                    f"{anchor.source_path}::{anchor.qualname}:{exc}",
                )
            )
            return findings
        source_segment = ast.get_source_segment(source_text, node) or source_text

    snippets = ast_operation_snippets(node) if node is not None else set[str]()
    for token in anchor.required_source_tokens:
        if token not in source_segment and compact_space(token) not in snippets:
            findings.append(
                Finding(
                    anchor.contract_key,
                    anchor.anchor_id,
                    "missing-required-source-token",
                    token,
                )
            )
    for token in anchor.forbidden_source_tokens:
        if token in source_segment:
            findings.append(
                Finding(
                    anchor.contract_key,
                    anchor.anchor_id,
                    "forbidden-source-token-present",
                    token,
                )
            )

    if node is None:
        if (
            anchor.required_ast_patterns
            or anchor.min_return_count is not None
            or anchor.min_branch_count is not None
            or anchor.max_branch_count is not None
        ):
            findings.append(
                Finding(
                    anchor.contract_key,
                    anchor.anchor_id,
                    "missing-ast-symbol-for-ast-check",
                    anchor.source_path,
                )
            )
        return findings

    for pattern in anchor.required_ast_patterns:
        if compact_space(pattern) not in snippets:
            findings.append(
                Finding(
                    anchor.contract_key,
                    anchor.anchor_id,
                    "missing-required-ast-pattern",
                    pattern,
                )
            )
    return_count, branch_count = ast_shape_counts(node)
    if anchor.min_return_count is not None and return_count < anchor.min_return_count:
        findings.append(
            Finding(
                anchor.contract_key,
                anchor.anchor_id,
                "return-count-below-minimum",
                f"{return_count}<{anchor.min_return_count}",
            )
        )
    if anchor.min_branch_count is not None and branch_count < anchor.min_branch_count:
        findings.append(
            Finding(
                anchor.contract_key,
                anchor.anchor_id,
                "branch-count-below-minimum",
                f"{branch_count}<{anchor.min_branch_count}",
            )
        )
    if anchor.max_branch_count is not None and branch_count > anchor.max_branch_count:
        findings.append(
            Finding(
                anchor.contract_key,
                anchor.anchor_id,
                "branch-count-above-maximum",
                f"{branch_count}>{anchor.max_branch_count}",
            )
        )
    return findings


def check_contract(
    contract_key: str,
    contract: JsonMapping,
    known_fragments: set[str],
) -> list[Finding]:
    """Check proposition-level fields for one contract."""
    findings: list[Finding] = []
    checked_fragment = contract.get("checked_fragment")
    if isinstance(checked_fragment, str) and checked_fragment not in known_fragments:
        findings.append(
            Finding(
                contract_key,
                "contract",
                "checked-fragment-not-retained",
                checked_fragment,
            )
        )
    anchors = contract_anchor_mappings(contract)
    has_proposition = any(
        isinstance(contract.get(key), str) and str(contract[key]).strip()
        for key in ("claim", "checked_conclusion", "proof_boundary")
    )
    if anchors and not has_proposition:
        findings.append(
            Finding(contract_key, "contract", "missing-proposition-text", "-")
        )
    return findings


def check_trace_alignment(root: Path, trace_path: Path, trace_symbol: str) -> AlignmentReport:
    """Check one package-retained proof trace."""
    trace = load_trace(trace_path, trace_symbol)
    known_fragments = checked_fragment_names(trace)
    entries = proof_contract_entries(trace)
    findings: list[Finding] = []
    checked_anchor_count = 0
    for contract_key, contract in entries:
        findings.extend(check_contract(contract_key, contract, known_fragments))
        for anchor in contract_anchors(contract_key, contract):
            checked_anchor_count += 1
            findings.extend(check_anchor(root, anchor))
    findings = sorted(
        findings,
        key=lambda finding: (
            finding.contract,
            finding.anchor,
            finding.kind,
            finding.detail,
        ),
    )
    return AlignmentReport(
        status="pass" if not findings else "fail",
        trace_path=trace_path.as_posix(),
        checked_contract_count=len(entries),
        checked_anchor_count=checked_anchor_count,
        findings=tuple(findings),
    )


def render_text(report: AlignmentReport) -> str:
    """Render text output."""
    lines = [
        f"PROOF_TRACE_ALIGNMENT={report.status}",
        f"PROOF_TRACE_ALIGNMENT_CONTRACTS={report.checked_contract_count}",
        f"PROOF_TRACE_ALIGNMENT_ANCHORS={report.checked_anchor_count}",
        f"PROOF_TRACE_ALIGNMENT_FINDINGS={len(report.findings)}",
    ]
    lines.extend(finding.render() for finding in report.findings)
    return "\n".join(lines)


def render_json(report: AlignmentReport) -> str:
    """Render JSON output."""
    return json.dumps(asdict(report), indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run proof trace alignment checker."""
    args = build_parser().parse_args(argv)
    report = check_trace_alignment(
        Path(args.root).resolve(),
        Path(args.trace_module).resolve(),
        str(args.trace_symbol),
    )
    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report))
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
