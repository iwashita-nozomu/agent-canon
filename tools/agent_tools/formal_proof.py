#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Builds formal-proof planning scaffolds from natural-language mathematical claims.
# upstream design ../../agents/skills/formal-proof-workflow.md defines proof workflow boundaries.
# upstream design ../../references/agent-canon-technology-bibliography.md records proof sources.
# downstream design ../../documents/tools/formal_proof.md documents operator-facing usage.
# downstream implementation ../../tests/agent_tools/test_formal_proof.py tests scaffold output.
# @dependency-end
"""Create a formal-proof scaffold from a natural-language claim."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from textwrap import indent
from typing import TypeAlias

TARGET_EXTENSIONS = {
    "lean": "lean",
    "isabelle": "thy",
    "coq": "v",
    "smt": "smt2",
}
TARGET_LABELS = {
    "lean": "Lean 4",
    "isabelle": "Isabelle/HOL",
    "coq": "Coq/Rocq",
    "smt": "SMT-LIB",
}
SECTION_ALIASES = {
    "assumptions": "assumptions",
    "assumption": "assumptions",
    "given": "assumptions",
    "hypotheses": "assumptions",
    "definitions": "definitions",
    "definition": "definitions",
    "defs": "definitions",
    "claim": "target",
    "target": "target",
    "theorem": "target",
    "goal": "target",
    "proof": "proof_sketch",
    "proof sketch": "proof_sketch",
    "sketch": "proof_sketch",
}
SECTION_RE = re.compile(r"^\s*([A-Za-z][A-Za-z _-]{0,40})\s*:\s*(.*)$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")
MAX_QUERY_WORDS = 16
PythonAstSymbol: TypeAlias = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class FormalProofPlan:
    """Machine-readable formal-proof scaffold."""

    status: str
    target: str
    target_label: str
    claim_text: str
    source_kind: str
    source_path: str | None
    source_symbol: str | None
    source_summary: str | None
    assumptions: tuple[str, ...]
    definitions: tuple[str, ...]
    theorem_target: str
    proof_sketch: tuple[str, ...]
    proof_obligations: tuple[str, ...]
    existing_proof_queries: tuple[str, ...]
    literature_queries: tuple[str, ...]
    verification_commands: tuple[str, ...]
    theorem_stub_path: str | None
    theorem_stub_name: str | None
    library_trace_module_path: str | None
    library_trace_module_name: str | None
    origin_theorem_stub_path: str | None
    origin_library_trace_module_path: str | None
    trace_path_semantics: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PythonAstSource:
    """Proof-planning input extracted from a Python AST symbol."""

    path: str
    qualname: str
    node_kind: str
    signature: str
    docstring: str | None
    lineno: int
    end_lineno: int | None
    branch_count: int
    return_expressions: tuple[str, ...]
    proof_obligations: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--claim", help="Natural-language mathematical claim.")
    source.add_argument("--claim-file", help="Path to a natural-language claim file.")
    source.add_argument(
        "--python-symbol",
        help=(
            "Python AST source in path.py::qualname form. The file is parsed with ast.parse "
            "and is not imported or executed."
        ),
    )
    parser.add_argument("--target", choices=tuple(TARGET_EXTENSIONS), default="lean")
    parser.add_argument("--domain", action="append", default=[], help="Domain keyword. Repeatable.")
    parser.add_argument(
        "--name",
        default=None,
        help="Identifier for the theorem stub.",
    )
    parser.add_argument("--out-dir", help="Optional directory for scaffold artifacts.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    return parser


def read_claim(args: argparse.Namespace) -> str:
    """Read the claim text from CLI args."""
    if args.claim_file:
        return Path(args.claim_file).read_text(encoding="utf-8").strip()
    return str(args.claim).strip()


def parse_python_symbol_reference(reference: str) -> tuple[Path, str]:
    """Parse a path.py::qualname Python AST source reference."""
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


def find_python_ast_symbol(module: ast.Module, qualname: str) -> PythonAstSymbol:
    """Find a class/function symbol by dotted qualname without importing it."""
    parts = tuple(part for part in qualname.split(".") if part)
    if not parts:
        raise ValueError("--python-symbol qualname is empty")

    current_body: list[ast.stmt] = list(module.body)
    current: PythonAstSymbol | None = None
    for part in parts:
        current = None
        for node in current_body:
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                if node.name == part:
                    current = node
                    break
        if current is None:
            raise ValueError(f"Python AST symbol not found: {qualname}")
        current_body = list(getattr(current, "body", ()))

    if current is None:  # defensive; empty qualnames are rejected above.
        raise ValueError("--python-symbol qualname is empty")
    return current


def _unparse(node: ast.AST | None) -> str:
    """Return a bounded source expression for an AST node."""
    if node is None:
        return "None"
    try:
        return compact_space(ast.unparse(node))
    except Exception:  # pragma: no cover - defensive for unusual parser nodes.
        return node.__class__.__name__


def _python_ast_signature(node: PythonAstSymbol) -> str:
    """Return a source-like signature summary for a class or function node."""
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(_unparse(base) for base in node.bases)
        suffix = f"({bases})" if bases else ""
        return f"class {node.name}{suffix}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {_unparse(node.returns)}" if node.returns is not None else ""
    return f"{prefix} {node.name}({_unparse(node.args)}){returns}"


def _python_return_expressions(node: PythonAstSymbol) -> tuple[str, ...]:
    """Extract bounded return-expression summaries from a Python AST symbol."""
    expressions: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Return):
            expressions.append(_unparse(child.value))
    return tuple(expressions[:8])


def _python_ast_branch_count(node: PythonAstSymbol) -> int:
    """Count common branch nodes for proof-obligation planning."""
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.Match,
        ast.BoolOp,
        ast.IfExp,
    )
    return sum(1 for child in ast.walk(node) if isinstance(child, branch_nodes))


def extract_python_ast_source(reference: str, root: Path | None = None) -> PythonAstSource:
    """Extract proof-planning metadata from a Python AST symbol reference."""
    path, qualname = parse_python_symbol_reference(reference)
    source_text = path.read_text(encoding="utf-8")
    try:
        module = ast.parse(source_text, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Python AST parse failed for {path}: {exc.msg}") from exc

    node = find_python_ast_symbol(module, qualname)
    signature = _python_ast_signature(node)
    branch_count = _python_ast_branch_count(node)
    return_expressions = _python_return_expressions(node)
    relative_path = path_relative_to(path, root or Path.cwd())
    obligations = [
        f"Formalize Python AST source without importing or executing: {relative_path}::{qualname}",
        f"Formalize extracted signature: {signature}",
    ]
    if return_expressions:
        obligations.append(
            "Prove or encode extracted return expressions: " + "; ".join(return_expressions)
        )
    if branch_count:
        obligations.append(f"Split proof obligations across {branch_count} AST branch node(s).")
    return PythonAstSource(
        path=relative_path,
        qualname=qualname,
        node_kind=node.__class__.__name__,
        signature=signature,
        docstring=ast.get_docstring(node, clean=True),
        lineno=int(getattr(node, "lineno", 0)),
        end_lineno=getattr(node, "end_lineno", None),
        branch_count=branch_count,
        return_expressions=return_expressions,
        proof_obligations=tuple(obligations),
    )


def build_claim_from_python_ast(source: PythonAstSource) -> str:
    """Build structured claim text from Python AST metadata."""
    claim = (
        compact_space(source.docstring)
        if source.docstring
        else f"Formalize the extracted Python AST behavior of {source.qualname}."
    )
    return_lines = (
        "; ".join(source.return_expressions) if source.return_expressions else "<none>"
    )
    return "\n".join(
        [
            f"Definitions: Python AST source {source.path}::{source.qualname}",
            f"- Node kind: {source.node_kind}",
            f"- Signature: {source.signature}",
            f"- Lines: {source.lineno}-{source.end_lineno or source.lineno}",
            f"- Branch nodes: {source.branch_count}",
            f"- Return expressions: {return_lines}",
            f"Claim: {claim}",
            "Proof sketch: Translate the parsed AST into target-language semantics,",
            "then discharge the extracted branch and return-expression obligations.",
        ]
    )


def compact_space(text: str) -> str:
    """Collapse whitespace for query text."""
    return " ".join(text.split())


def normalize_identifier(raw: str) -> str:
    """Return an ASCII-ish theorem identifier."""
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").lower()
    if not cleaned:
        return "generated_claim"
    if cleaned[0].isdigit():
        cleaned = f"claim_{cleaned}"
    return cleaned


def append_section(sections: dict[str, list[str]], section: str, value: str) -> None:
    """Append a nonempty section line."""
    stripped = value.strip()
    if stripped:
        sections.setdefault(section, []).append(stripped)


def parse_sections(claim_text: str) -> dict[str, list[str]]:
    """Parse lightweight natural-language sections from claim text."""
    sections: dict[str, list[str]] = {
        "assumptions": [],
        "definitions": [],
        "target": [],
        "proof_sketch": [],
    }
    current = "target"
    saw_explicit_target = False
    for raw_line in claim_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = SECTION_RE.match(line)
        if match:
            label = match.group(1).strip().lower().replace("-", " ")
            section = SECTION_ALIASES.get(label)
            if section:
                current = section
                if section == "target":
                    saw_explicit_target = True
                append_section(sections, current, match.group(2))
                continue
        append_section(sections, current, line.lstrip("-*0123456789. "))

    if not saw_explicit_target and sections["target"]:
        first_line = sections["target"][0]
        rest = sections["target"][1:]
        sections["target"] = [first_line]
        sections["proof_sketch"].extend(rest)
    return sections


def query_terms(claim_text: str, domains: tuple[str, ...]) -> str:
    """Extract bounded query terms from claim and domain hints."""
    words: list[str] = []
    for source in (*domains, claim_text):
        for word in WORD_RE.findall(source):
            lowered = word.lower()
            if len(lowered) <= 2:
                continue
            if lowered in {"the", "and", "for", "with", "that", "then", "from", "there"}:
                continue
            words.append(word)
    deduped = list(dict.fromkeys(words))
    return " ".join(deduped[:MAX_QUERY_WORDS]) or compact_space(claim_text)[:120]


def build_existing_proof_queries(
    claim_text: str,
    domains: tuple[str, ...],
    target: str,
) -> tuple[str, ...]:
    """Build web and formal-library search queries for existing proofs."""
    terms = query_terms(claim_text, domains)
    natural = compact_space(claim_text)
    queries = [
        f'"{natural}" formal proof',
        f'"{natural}" theorem proof',
        f"{terms} Lean mathlib",
        f"{terms} site:leanprover-community.github.io/mathlib4_docs",
        f"{terms} LeanSearch mathlib",
        f"{terms} Loogle mathlib",
        f"{terms} Isabelle AFP",
        f"{terms} Coq Rocq theorem",
    ]
    if target == "isabelle":
        queries.insert(2, f"{terms} Isabelle Sledgehammer AFP")
    elif target == "coq":
        queries.insert(2, f"{terms} CoqHammer Coq Rocq")
    elif target == "smt":
        queries.insert(2, f"{terms} SMT-LIB Z3 cvc5")
    return tuple(dict.fromkeys(query for query in queries if query.strip()))


def build_literature_queries(claim_text: str, domains: tuple[str, ...]) -> tuple[str, ...]:
    """Build literature-survey queries for proof sources and prior art."""
    terms = query_terms(claim_text, domains)
    return (
        f"{terms} proof paper",
        f"{terms} theorem survey",
        f"{terms} formalization Lean Isabelle Coq",
        f"{terms} counterexample assumptions",
    )


def build_obligations(sections: dict[str, list[str]]) -> tuple[str, ...]:
    """Create initial proof obligations from parsed sections."""
    obligations: list[str] = []
    if not sections["definitions"]:
        obligations.append(
            "Define all mathematical objects and notation in the target proof assistant."
        )
    for assumption in sections["assumptions"]:
        obligations.append(f"Formalize assumption: {assumption}")
    target = " ".join(sections["target"]).strip()
    if target:
        obligations.append(f"Formalize theorem target: {target}")
    if sections["proof_sketch"]:
        obligations.append("Split the informal proof sketch into assistant-checkable lemmas.")
    obligations.append("Search existing formal libraries before proving new lemmas.")
    obligations.append("Run the target proof assistant and record the checker log.")
    obligations.append(
        "When a fragment is checked, register it in the package-retained proof "
        "trace and record remaining implementation-instantiation obligations "
        "as explicit proof boundaries."
    )
    return tuple(obligations)


def build_verification_commands(stub_path: str, target: str) -> tuple[str, ...]:
    """Return target-specific verification commands."""
    if target == "lean":
        return (
            "python3 tools/agent_tools/lean_proof_env.py check-file "
            "--env-dir reports/formal-proof/lean-proof-env "
            f"--lean-file {shlex.quote(stub_path)} --execute",
        )
    if target == "isabelle":
        return (f"isabelle process -T GeneratedClaim {stub_path}",)
    if target == "coq":
        return (f"coqc {stub_path}",)
    return (f"z3 -smt2 {stub_path}", f"cvc5 --lang smt2 {stub_path}")


def comment_block(prefix: str, text: str) -> str:
    """Prefix a text block as comments."""
    return "\n".join(f"{prefix} {line}" if line else prefix for line in text.splitlines())


def build_stub(target: str, name: str, plan: FormalProofPlan) -> str:
    """Build an intentionally unfinished target-language theorem stub."""
    claim_comment = comment_block(";", plan.claim_text)
    safe_name = normalize_identifier(name)
    if target == "lean":
        return "\n".join(
            [
                "import Mathlib",
                "import Aesop",
                "",
                "/-",
                "Formal proof scaffold generated by formal_proof.py.",
                "This file is not proof evidence until <FORMAL_TARGET> is replaced",
                "and the checker command succeeds without sorry/admit/placeholders.",
                "",
                "Natural-language claim:",
                indent(plan.claim_text, "  "),
                "-/",
                "",
                f"theorem {safe_name} : <FORMAL_TARGET> := by",
                "  -- TODO: replace this scaffold with a checked proof.",
                "  sorry",
                "",
            ]
        )
    if target == "isabelle":
        return "\n".join(
            [
                "theory GeneratedClaim",
                "  imports Main",
                "begin",
                "",
                "(* Formal proof scaffold generated by formal_proof.py.",
                "   This file is not proof evidence until <FORMAL_TARGET> is replaced",
                "   and Isabelle checks a proof without sorry/placeholders.",
                "",
                "   Natural-language claim:",
                *[f"   {line}" for line in plan.claim_text.splitlines()],
                "*)",
                "",
                f'theorem {safe_name}:',
                '  "<FORMAL_TARGET>"',
                "  sorry",
                "",
                "end",
                "",
            ]
        )
    if target == "coq":
        return "\n".join(
            [
                "(*",
                "Formal proof scaffold generated by formal_proof.py.",
                "This file is not proof evidence until <FORMAL_TARGET> is replaced",
                "and Coq/Rocq checks a proof without Admitted/placeholders.",
                "",
                "Natural-language claim:",
                *[line for line in plan.claim_text.splitlines()],
                "*)",
                "",
                f"Theorem {safe_name} : <FORMAL_TARGET>.",
                "Proof.",
                "  (* TODO: replace this scaffold with a checked proof. *)",
                "Admitted.",
                "",
            ]
        )
    return "\n".join(
        [
            "; Formal proof scaffold generated by formal_proof.py.",
            "; This file is not proof evidence until assertions are formalized",
            "; and an SMT solver returns unsat/sat as expected for the encoded obligation.",
            claim_comment,
            "",
            "(set-logic ALL)",
            "; TODO: declare symbols and assert the negated theorem.",
            "; (check-sat)",
            "",
        ]
    )


def build_plan(
    claim_text: str,
    target: str,
    domains: tuple[str, ...],
    name: str,
    stub_path: str | None,
    *,
    source_kind: str = "natural_language",
    source_path: str | None = None,
    source_symbol: str | None = None,
    source_summary: str | None = None,
    extra_obligations: tuple[str, ...] = (),
) -> FormalProofPlan:
    """Build the proof plan object."""
    sections = parse_sections(claim_text)
    theorem_target = " ".join(sections["target"]).strip() or compact_space(claim_text)
    verification_stub = (
        stub_path or f"<out-dir>/{normalize_identifier(name)}.{TARGET_EXTENSIONS[target]}"
    )
    proof_obligations = (*extra_obligations, *build_obligations(sections))
    return FormalProofPlan(
        status="scaffold_only_unverified",
        target=target,
        target_label=TARGET_LABELS[target],
        claim_text=claim_text,
        source_kind=source_kind,
        source_path=source_path,
        source_symbol=source_symbol,
        source_summary=source_summary,
        assumptions=tuple(sections["assumptions"]),
        definitions=tuple(sections["definitions"]),
        theorem_target=theorem_target,
        proof_sketch=tuple(sections["proof_sketch"]),
        proof_obligations=proof_obligations,
        existing_proof_queries=build_existing_proof_queries(claim_text, domains, target),
        literature_queries=build_literature_queries(claim_text, domains),
        verification_commands=build_verification_commands(verification_stub, target),
        theorem_stub_path=stub_path,
        theorem_stub_name=None,
        library_trace_module_path=None,
        library_trace_module_name=None,
        origin_theorem_stub_path=None,
        origin_library_trace_module_path=None,
        trace_path_semantics=(
            "No library trace module has been written. Paths are scaffold-generation context."
        ),
        notes=(
            "This scaffold is not proof evidence.",
            "Use $literature-survey before new formalization when the claim may already exist.",
            "Only a successful proof-assistant checker log can upgrade proof_status to verified.",
        ),
    )


def render_markdown(plan: FormalProofPlan) -> str:
    """Render a proof plan in Markdown."""
    lines = [
        "# Formal Proof Plan",
        "",
        f"- status: `{plan.status}`",
        f"- target: `{plan.target_label}`",
        f"- theorem_stub_path: `{plan.theorem_stub_path or '<not-written>'}`",
        f"- theorem_stub_name: `{plan.theorem_stub_name or '<not-written>'}`",
        f"- library_trace_module_path: `{plan.library_trace_module_path or '<not-written>'}`",
        f"- library_trace_module_name: `{plan.library_trace_module_name or '<not-written>'}`",
        f"- source_kind: `{plan.source_kind}`",
        f"- source_path: `{plan.source_path or '<none>'}`",
        f"- source_symbol: `{plan.source_symbol or '<none>'}`",
        f"- trace_path_semantics: `{plan.trace_path_semantics}`",
        "",
        "## Claim",
        "",
        plan.claim_text,
        "",
        "## Source Summary",
        "",
        plan.source_summary or "<none>",
        "",
        "## Assumptions",
        "",
    ]
    lines.extend(f"- {item}" for item in plan.assumptions or ("<none parsed>",))
    lines.extend(["", "## Definitions", ""])
    lines.extend(f"- {item}" for item in plan.definitions or ("<none parsed>",))
    lines.extend(["", "## Proof Obligations", ""])
    lines.extend(f"- {item}" for item in plan.proof_obligations)
    lines.extend(["", "## Existing Proof Queries", ""])
    lines.extend(f"- `{query}`" for query in plan.existing_proof_queries)
    lines.extend(["", "## Literature Queries", ""])
    lines.extend(f"- `{query}`" for query in plan.literature_queries)
    lines.extend(["", "## Verification Commands", ""])
    lines.extend(f"- `{command}`" for command in plan.verification_commands)
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in plan.notes)
    return "\n".join(lines) + "\n"


def render_text(plan: FormalProofPlan) -> str:
    """Render compact machine-readable text."""
    lines = [
        f"FORMAL_PROOF_STATUS={plan.status}",
        f"FORMAL_PROOF_TARGET={plan.target}",
        f"FORMAL_PROOF_STUB={plan.theorem_stub_path or '<not-written>'}",
        f"FORMAL_PROOF_LIBRARY_TRACE_MODULE={plan.library_trace_module_path or '<not-written>'}",
        "FORMAL_PROOF_LIBRARY_TRACE_MODULE_NAME="
        f"{plan.library_trace_module_name or '<not-written>'}",
        f"FORMAL_PROOF_SOURCE_KIND={plan.source_kind}",
    ]
    if plan.source_path:
        lines.append(f"FORMAL_PROOF_SOURCE_PATH={plan.source_path}")
    if plan.source_symbol:
        lines.append(f"FORMAL_PROOF_SOURCE_SYMBOL={plan.source_symbol}")
    for query in plan.existing_proof_queries:
        lines.append(f"FORMAL_PROOF_EXISTING_QUERY={query}")
    for query in plan.literature_queries:
        lines.append(f"FORMAL_PROOF_LITERATURE_QUERY={query}")
    for command in plan.verification_commands:
        lines.append(f"FORMAL_PROOF_VERIFY={command}")
    return "\n".join(lines) + "\n"


def build_library_trace_module(plan: FormalProofPlan) -> str:
    """Build an importable Python module containing the proof-planning trace."""
    trace_json = json.dumps(asdict(plan), indent=2, sort_keys=True)
    return "\n".join(
        [
            '"""Generated formal-proof trace for Python package distribution.',
            "",
            "This module is provenance and planning evidence only. It is not proof",
            "evidence until the checker command recorded in FORMAL_PROOF_TRACE succeeds",
            "on a completed artifact without placeholders or unchecked proof escapes.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "import json",
            "from pathlib import Path",
            "from typing import Any",
            "",
            f"FORMAL_PROOF_TRACE_JSON = {trace_json!r}",
            "FORMAL_PROOF_TRACE: dict[str, Any] = json.loads(FORMAL_PROOF_TRACE_JSON)",
            "_TRACE_MODULE_PATH = Path(__file__).resolve()",
            "_ORIGIN_LIBRARY_TRACE_MODULE_PATH = FORMAL_PROOF_TRACE.get(",
            "    \"library_trace_module_path\"",
            ")",
            "_ORIGIN_THEOREM_STUB_PATH = FORMAL_PROOF_TRACE.get(\"theorem_stub_path\")",
            "FORMAL_PROOF_TRACE[\"origin_library_trace_module_path\"] = (",
            "    _ORIGIN_LIBRARY_TRACE_MODULE_PATH",
            ")",
            "FORMAL_PROOF_TRACE[\"origin_theorem_stub_path\"] = _ORIGIN_THEOREM_STUB_PATH",
            "FORMAL_PROOF_TRACE[\"library_trace_module_path\"] = _TRACE_MODULE_PATH.as_posix()",
            "FORMAL_PROOF_TRACE[\"library_trace_module_name\"] = _TRACE_MODULE_PATH.name",
            "_THEOREM_STUB_NAME = FORMAL_PROOF_TRACE.get(\"theorem_stub_name\")",
            "if isinstance(_THEOREM_STUB_NAME, str):",
            "    FORMAL_PROOF_TRACE[\"runtime_theorem_stub_candidate_path\"] = (",
            "        _TRACE_MODULE_PATH.parent / _THEOREM_STUB_NAME",
            "    ).as_posix()",
            "FORMAL_PROOF_TRACE[\"trace_path_semantics\"] = (",
            "    \"library_trace_module_path is computed from this installed module's \"",
            "    \"__file__; origin_* fields preserve generation-context paths.\"",
            ")",
            "",
        ]
    )


def write_outputs(plan: FormalProofPlan, out_dir: Path, name: str) -> FormalProofPlan:
    """Write JSON, Markdown, query, and theorem-stub artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = normalize_identifier(name)
    stub_path = out_dir / f"{safe_name}.{TARGET_EXTENSIONS[plan.target]}"
    trace_module_path = out_dir / f"{safe_name}_proof_trace.py"
    stub_relpath = path_relative_to(stub_path, Path.cwd())
    trace_relpath = path_relative_to(trace_module_path, Path.cwd())
    written_plan = replace(
        plan,
        theorem_stub_path=stub_relpath,
        theorem_stub_name=stub_path.name,
        library_trace_module_path=trace_relpath,
        library_trace_module_name=trace_module_path.name,
        origin_theorem_stub_path=stub_relpath,
        origin_library_trace_module_path=trace_relpath,
        trace_path_semantics=(
            "library_trace_module_path is generation-context until the generated trace "
            "module is imported; the module rewrites that field from __file__ and keeps "
            "origin_* paths for generation provenance."
        ),
        verification_commands=build_verification_commands(
            stub_relpath,
            plan.target,
        ),
    )
    stub_path.write_text(build_stub(plan.target, name, written_plan), encoding="utf-8")
    trace_module_path.write_text(build_library_trace_module(written_plan), encoding="utf-8")
    (out_dir / "formal_proof_plan.json").write_text(
        json.dumps(asdict(written_plan), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "formal_proof_plan.md").write_text(render_markdown(written_plan), encoding="utf-8")
    (out_dir / "existing_proof_queries.txt").write_text(
        "\n".join(written_plan.existing_proof_queries) + "\n",
        encoding="utf-8",
    )
    (out_dir / "literature_queries.txt").write_text(
        "\n".join(written_plan.literature_queries) + "\n",
        encoding="utf-8",
    )
    return written_plan


def path_relative_to(path: Path, root: Path) -> str:
    """Return path relative to root when possible."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def main() -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    domains = tuple(compact_space(domain) for domain in args.domain if compact_space(domain))
    ast_source: PythonAstSource | None = None
    try:
        if args.python_symbol:
            ast_source = extract_python_ast_source(args.python_symbol)
            claim_text = build_claim_from_python_ast(ast_source)
            default_name = normalize_identifier(ast_source.qualname)
        else:
            claim_text = read_claim(args)
            default_name = "generated_claim"
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        parser.error(str(exc))

    name = args.name or default_name
    plan = build_plan(
        claim_text,
        args.target,
        domains,
        name,
        stub_path=None,
        source_kind="python_ast" if ast_source else "natural_language",
        source_path=ast_source.path if ast_source else None,
        source_symbol=ast_source.qualname if ast_source else None,
        source_summary=ast_source.signature if ast_source else None,
        extra_obligations=ast_source.proof_obligations if ast_source else (),
    )
    if args.out_dir:
        plan = write_outputs(plan, Path(args.out_dir), name)

    if args.format == "json":
        print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(plan), end="")
    else:
        print(render_text(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
