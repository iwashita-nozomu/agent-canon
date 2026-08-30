#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates the structured AgentCanon tool catalog.
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# upstream design ../../tools/README.md shared tool family ownership
# upstream design ../../documents/tools/README.md root-facing tool entrypoint policy
# upstream design ../../documents/tools/tool-docs.toml one-to-one tool documentation map
# upstream implementation ./visualization_contract.py canonical typed visualization contract/checker
# upstream design ../../documents/tools/repo-local-tool-imports.md legacy tool disposition policy
# upstream implementation ./tool_path_policy.py defines retired legacy path policy
# downstream implementation ../../tools/validation/ci/runners/run_all_checks.sh runs catalog validation
# downstream implementation ../../tests/agent_tools/test_tool_catalog.py tests validator
# @dependency-end
"""Validate the structured AgentCanon tool catalog."""

from __future__ import annotations

import argparse
import json
import re

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

if __package__ in (None, ""):
    # Direct execution must resolve the canonical package from the repository
    # root rather than treating this relocated manifest directory as a module.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from tools.runtime.authority.tool_path_policy import is_retired_legacy_tool_path
else:
    from ..authority.tool_path_policy import is_retired_legacy_tool_path

CATALOG_PATH = "tools/catalog.yaml"
TOOL_DOCS_PATH = "documents/tools/tool-docs.toml"
PUBLIC_SURFACE_PRODUCER_VERSION = "public-surface.v1"
TOOL_CLASSIFICATIONS = frozenset({"public", "internal", "compat", "retired", "example"})
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOOL_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])tools/[A-Za-z0-9_./-]+\.(?:py|sh)\b"
)
DEFAULT_COMMAND_SOURCES = (
    "tools/validation/ci/runners/run_all_checks.sh",
    "tools/validation/ci/checks/check_agent_canon_pr.sh",
)
ENTRY_WIRING_SOURCES = (
    *DEFAULT_COMMAND_SOURCES,
    "eval/producers/run_accumulated_agent_evals.py",
    "agents/workflows/agent-canon-pr-workflow.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
)
CATALOG_DOCS = (
    "tools/README.md",
    "documents/tools/README.md",
    TOOL_DOCS_PATH,
    "documents/tools/repo-local-tool-imports.md",
)
VISUALIZATION_CONTRACT_ID = "visualization-contract"
VISUALIZATION_CONTRACT_PATH = "tools/validation/semantic/tools/visualization_contract.py"
VISUALIZATION_CONTRACT_DOC = "documents/tools/visualization_contract.md"


@dataclass(frozen=True)
class Finding:
    """One catalog validation finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"TOOL_CATALOG_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class CatalogRow:
    """One catalog row ready for reports."""

    tool_id: str
    path: str
    summary: str
    family: str
    role: str
    status: str
    audience: str
    placement: str
    command: str | None
    writes: bool
    ci: bool
    pr_check: bool
    docs: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True)
class CatalogReport:
    """Catalog validation result plus the tool crosswalk."""

    findings: tuple[Finding, ...]
    entries: tuple[CatalogRow, ...]


@dataclass(frozen=True)
class PublicSourceSpan:
    """One exact public-surface source span."""

    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class PublicSurfaceRow:
    """One canonical public CLI, tool, or skill surface."""

    surface_id: str
    kind: str
    path: str
    selector: str
    source_span: PublicSourceSpan
    secondary_spans: tuple[PublicSourceSpan, ...]
    authority: str = "public-surface"


@dataclass(frozen=True)
class PublicSurfaceReport:
    """Token-parsed public surface plus producer diagnostics."""

    producer_version: str
    rows: tuple[PublicSurfaceRow, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class RustToken:
    """One bounded Rust token with a one-based source span."""

    value: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    return parser


def as_mapping(value: object) -> Mapping[str, object] | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return value as a sequence, excluding strings."""
    if isinstance(value, str):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def string_list(value: object) -> list[str]:
    """Return a list of strings from one YAML value."""
    sequence = as_sequence(value)
    if sequence is None:
        return []
    return [item for item in sequence if isinstance(item, str)]


def bool_from_mapping(mapping: Mapping[str, object], key: str) -> bool:
    """Return a boolean mapping value when it is explicitly true."""
    return mapping.get(key) is True


def inherited_string(
    entry: Mapping[str, object],
    family_defaults: Mapping[str, object],
    key: str,
) -> str | None:
    """Return an entry value, falling back to its family default."""
    if key in entry:
        value = entry[key]
        return value if isinstance(value, str) else None
    default = family_defaults.get(key)
    return default if isinstance(default, str) else None


def has_non_string_key(mapping: Mapping[str, object], key: str) -> bool:
    """Return whether a present key has a non-string value."""
    return key in mapping and not isinstance(mapping[key], str)


def resolve_repo_path(
    root: Path,
    relative_path: str,
    *,
    source_root: Path | None = None,
) -> Path:
    """Resolve a catalog path below an explicit source root when supplied."""
    if source_root is not None:
        return source_root.resolve() / relative_path
    root_path = root / relative_path
    if root_path.exists():
        return root_path
    vendor_path = root / "vendor" / "agent-canon" / relative_path
    if vendor_path.exists():
        return vendor_path
    return root_path


def load_catalog(path: Path) -> tuple[Mapping[str, object] | None, list[Finding]]:
    """Load the catalog YAML."""
    if not path.is_file():
        return None, [Finding("catalog", CATALOG_PATH, "missing-file")]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    data = as_mapping(raw)
    if data is None:
        return None, [Finding("catalog", CATALOG_PATH, "must-parse-as-mapping")]
    return data, []


def allowed_values(data: Mapping[str, object], key: str) -> set[str]:
    """Return allowed enum values from the catalog."""
    return set(string_list(data.get(key)))


def entry_path(entry: Mapping[str, object]) -> str:
    """Return one catalog entry path."""
    value = entry.get("path")
    return value if isinstance(value, str) else "<missing-path>"


def entry_summary(entry: Mapping[str, object]) -> str:
    """Return one catalog entry summary."""
    value = entry.get("summary")
    return value.strip() if isinstance(value, str) else ""


def catalog_row(entry: Mapping[str, object], family_defaults: Mapping[str, object]) -> CatalogRow:
    """Convert one entry mapping into a report row."""
    wiring = as_mapping(entry.get("default_wiring")) or {}
    entry_id = entry.get("id")
    family = entry.get("family")
    role = entry.get("role")
    status = entry.get("status")
    command = entry.get("command")
    return CatalogRow(
        tool_id=entry_id if isinstance(entry_id, str) else "<missing-id>",
        path=entry_path(entry),
        summary=entry_summary(entry),
        family=family if isinstance(family, str) else "<missing>",
        role=role if isinstance(role, str) else "<missing>",
        status=status if isinstance(status, str) else "<missing>",
        audience=inherited_string(entry, family_defaults, "audience") or "<missing>",
        placement=inherited_string(entry, family_defaults, "placement") or "<missing>",
        command=command if isinstance(command, str) else None,
        writes=entry.get("writes") is True,
        ci=bool_from_mapping(wiring, "ci"),
        pr_check=bool_from_mapping(wiring, "pr_check"),
        docs=tuple(string_list(entry.get("docs"))),
        tests=tuple(string_list(entry.get("tests"))),
    )


def check_entry(
    root: Path,
    entry: Mapping[str, object],
    families: set[str],
    statuses: set[str],
    roles: set[str],
    audiences: set[str],
    placements: set[str],
    family_defaults: Mapping[str, object],
) -> list[Finding]:
    """Validate one catalog entry."""
    findings: list[Finding] = []
    path = entry_path(entry)
    entry_id = entry.get("id")
    family = entry.get("family")
    status = entry.get("status")
    role = entry.get("role")
    audience = inherited_string(entry, family_defaults, "audience")
    placement = inherited_string(entry, family_defaults, "placement")
    target = resolve_repo_path(root, path)

    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        findings.append(Finding("entry", path, "invalid-id"))
    if "public" in entry and not isinstance(entry["public"], bool):
        findings.append(Finding("entry", path, "invalid-public"))
    if not isinstance(family, str) or family not in families:
        findings.append(Finding("entry", path, "invalid-family"))
    if not isinstance(status, str) or status not in statuses:
        findings.append(Finding("entry", path, "invalid-status"))
    if not isinstance(role, str) or role not in roles:
        findings.append(Finding("entry", path, "invalid-role"))
    if has_non_string_key(entry, "audience"):
        findings.append(Finding("entry", path, "invalid-audience"))
    elif audience is None:
        findings.append(Finding("entry", path, "missing-audience"))
    elif audience not in audiences:
        findings.append(Finding("entry", path, "invalid-audience"))
    if has_non_string_key(entry, "placement"):
        findings.append(Finding("entry", path, "invalid-placement"))
    elif placement is None:
        findings.append(Finding("entry", path, "missing-placement"))
    elif placement not in placements:
        findings.append(Finding("entry", path, "invalid-placement"))
    if status == "compatibility_wrapper" and placement != "compatibility_wrapper":
        findings.append(Finding("entry", path, "compatibility-wrapper-placement-required"))
    if not entry_summary(entry):
        findings.append(Finding("entry", path, "missing-summary"))
    if not target.exists():
        findings.append(Finding("entry", path, "missing-path"))

    if is_retired_legacy_tool_path(path) or status == "legacy_provenance":
        findings.append(Finding("legacy", path, "legacy-tools-are-retired"))

    docs = string_list(entry.get("docs"))
    if not docs:
        findings.append(Finding("entry", path, "missing-docs"))
    for doc in docs:
        doc_path = resolve_repo_path(root, doc)
        if not doc_path.is_file():
            findings.append(Finding("entry", path, f"missing-doc:{doc}"))

    tests = string_list(entry.get("tests"))
    exempt_reason = entry.get("test_exempt_reason")
    if status in {"canonical", "compatibility_wrapper"} and not tests:
        if not isinstance(exempt_reason, str) or not exempt_reason.strip():
            findings.append(Finding("entry", path, "missing-tests-or-exemption"))
    for test in tests:
        test_path = resolve_repo_path(root, test)
        if not test_path.is_file():
            findings.append(Finding("entry", path, f"missing-test:{test}"))

    return findings


def read_existing_text(root: Path, paths: Iterable[str]) -> str:
    """Read and concatenate existing text files."""
    chunks: list[str] = []
    for path in paths:
        target = resolve_repo_path(root, path)
        if target.is_file():
            chunks.append(target.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def referenced_tool_paths(root: Path) -> set[str]:
    """Return tool paths referenced by default wiring surfaces."""
    text = read_existing_text(root, DEFAULT_COMMAND_SOURCES)
    return set(TOOL_REFERENCE_RE.findall(text))


def check_default_wiring(
    root: Path,
    entries: Sequence[Mapping[str, object]],
) -> list[Finding]:
    """Validate catalog/default wiring consistency."""
    findings: list[Finding] = []
    catalog_paths = {entry_path(entry) for entry in entries}
    default_text = read_existing_text(root, ENTRY_WIRING_SOURCES)
    for path in sorted(referenced_tool_paths(root)):
        if path not in catalog_paths:
            findings.append(Finding("default_wiring", path, "uncataloged-tool-reference"))
    for entry in entries:
        path = entry_path(entry)
        wiring = as_mapping(entry.get("default_wiring")) or {}
        if not (bool_from_mapping(wiring, "ci") or bool_from_mapping(wiring, "pr_check")):
            continue
        if path not in default_text and Path(path).name not in default_text:
            findings.append(Finding("default_wiring", path, "wired-entry-not-referenced"))
    return findings


def check_catalog_docs(root: Path) -> list[Finding]:
    """Validate that reader-facing docs point at the structured catalog."""
    findings: list[Finding] = []
    required = ("tools/catalog.yaml", "tool_catalog.py")
    for path in CATALOG_DOCS:
        target = resolve_repo_path(root, path)
        if not target.is_file():
            findings.append(Finding("catalog_docs", path, "missing-file"))
            continue
        text = target.read_text(encoding="utf-8")
        for snippet in required:
            if snippet not in text:
                findings.append(Finding("catalog_docs", path, f"missing:{snippet}"))
    return findings


def load_tool_docs(root: Path) -> tuple[list[Mapping[str, object]], list[Finding]]:
    """Load one-to-one tool documentation manifest."""
    path = resolve_repo_path(root, TOOL_DOCS_PATH)
    if not path.is_file():
        return [], [Finding("tool_docs", TOOL_DOCS_PATH, "missing-file")]
    raw = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    findings: list[Finding] = []
    if raw.get("catalog_kind") != "agent_canon_tool_docs":
        return [], [Finding("tool_docs", TOOL_DOCS_PATH, "invalid-catalog-kind")]
    classifications = raw.get("classification_values")
    if set(string_list(classifications)) != TOOL_CLASSIFICATIONS:
        findings.append(Finding("tool_docs", TOOL_DOCS_PATH, "invalid-classification-values"))
    entries_raw = raw.get("tool")
    if not isinstance(entries_raw, list):
        findings.append(Finding("tool_docs", TOOL_DOCS_PATH, "missing-tool-list"))
        return [], findings
    entries = cast(list[object], entries_raw)
    result: list[Mapping[str, object]] = []
    for entry in entries:
        mapping = as_mapping(entry)
        if mapping is None:
            findings.append(Finding("tool_docs", TOOL_DOCS_PATH, "tool-entry-not-mapping"))
            continue
        result.append(mapping)
    return result, findings


def check_tool_docs_manifest(
    root: Path,
    catalog_entries: Sequence[Mapping[str, object]],
) -> list[Finding]:
    """Validate same-named one-to-one tool documentation entries."""
    doc_entries, findings = load_tool_docs(root)
    catalog_by_id: dict[str, Mapping[str, object]] = {}
    for entry in catalog_entries:
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            catalog_by_id[entry_id] = entry
    seen_tools: set[str] = set()
    seen_docs: set[str] = set()
    documented_public_ids: set[str] = set()
    documented_public_tools: dict[str, str] = {}
    for doc_entry in doc_entries:
        entry_id = doc_entry.get("id")
        tool = doc_entry.get("tool")
        doc = doc_entry.get("doc")
        classification = doc_entry.get("classification")
        if not isinstance(entry_id, str) or not isinstance(tool, str) or not isinstance(doc, str):
            findings.append(Finding("tool_docs", TOOL_DOCS_PATH, "missing-id-tool-or-doc"))
            continue
        if not isinstance(classification, str) or classification not in TOOL_CLASSIFICATIONS:
            findings.append(Finding("tool_docs", tool, "invalid-classification"))
        elif classification == "public":
            documented_public_ids.add(entry_id)
            documented_public_tools[entry_id] = tool
        if tool in seen_tools:
            findings.append(Finding("tool_docs", tool, "duplicate-tool"))
        if doc in seen_docs:
            findings.append(Finding("tool_docs", doc, "duplicate-doc"))
        seen_tools.add(tool)
        seen_docs.add(doc)
        catalog_entry = catalog_by_id.get(entry_id)
        if catalog_entry is None:
            findings.append(Finding("tool_docs", tool, f"missing-catalog-id:{entry_id}"))
            continue
        if catalog_entry.get("path") != tool:
            findings.append(Finding("tool_docs", tool, "catalog-path-mismatch"))
        tool_path = resolve_repo_path(root, tool)
        doc_path = resolve_repo_path(root, doc)
        if not tool_path.is_file():
            findings.append(Finding("tool_docs", tool, "missing-tool"))
        if not doc_path.is_file():
            findings.append(Finding("tool_docs", doc, "missing-doc"))
        if not tool_doc_name_matches(tool, doc):
            findings.append(Finding("tool_docs", doc, "tool-doc-name-mismatch"))
        docs = string_list(catalog_entry.get("docs"))
        if doc not in docs:
            findings.append(Finding("tool_docs", tool, f"catalog-doc-missing:{doc}"))

    catalog_public_ids: set[str] = {
        entry_id
        for entry_id, entry in catalog_by_id.items()
        if entry.get("public") is True
    }
    catalog_ids: set[str] = set(catalog_by_id)
    for entry_id in sorted(documented_public_ids - catalog_public_ids):
        detail = (
            f"missing-catalog-entry:{entry_id}:{documented_public_tools[entry_id]}"
            if entry_id not in catalog_ids
            else f"missing-public-mark:{entry_id}:{documented_public_tools[entry_id]}"
        )
        findings.append(Finding("public_tools", TOOL_DOCS_PATH, detail))
    documented_ids: set[str] = set()
    for entry in doc_entries:
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            documented_ids.add(entry_id)
    for entry_id in sorted(catalog_public_ids - documented_public_ids):
        detail = (
            f"missing-public-documentation:{entry_id}:{entry_path(catalog_by_id[entry_id])}"
            if entry_id not in documented_ids
            else f"non-public-documentation:{entry_id}:{entry_path(catalog_by_id[entry_id])}"
        )
        findings.append(Finding("public_tools", CATALOG_PATH, detail))
    return findings


def tool_doc_name_matches(tool: str, doc: str) -> bool:
    """Return whether a tool path and reader doc share their canonical identity."""
    tool_path = Path(tool)
    doc_stem = Path(doc).stem
    if tool_path.name == "mod.rs":
        owner_stem = tool_path.parent.name
        return doc_stem in {owner_stem, owner_stem.replace("_", "-")}
    return tool_path.stem == doc_stem


def check_visualization_contract_entry(
    root: Path,
    entries: Sequence[Mapping[str, object]],
    family_defaults: Mapping[str, Mapping[str, object]],
) -> list[Finding]:
    """Require exactly one canonical skill-facing visualization contract tool."""
    findings: list[Finding] = []
    candidates = [
        entry
        for entry in entries
        if entry.get("id") == VISUALIZATION_CONTRACT_ID
        or entry.get("path") == VISUALIZATION_CONTRACT_PATH
    ]
    if not candidates and not resolve_repo_path(root, VISUALIZATION_CONTRACT_PATH).exists():
        return findings
    if len(candidates) != 1:
        return [
            Finding(
                "visualization_contract",
                CATALOG_PATH,
                f"expected-one-canonical-entry:found-{len(candidates)}",
            )
        ]
    entry = candidates[0]
    family = entry.get("family")
    defaults = family_defaults.get(family, {}) if isinstance(family, str) else {}
    if entry.get("id") != VISUALIZATION_CONTRACT_ID:
        findings.append(
            Finding("visualization_contract", VISUALIZATION_CONTRACT_PATH, "invalid-id")
        )
    if entry.get("path") != VISUALIZATION_CONTRACT_PATH:
        findings.append(
            Finding("visualization_contract", VISUALIZATION_CONTRACT_PATH, "invalid-path")
        )
    if entry.get("status") != "canonical":
        findings.append(
            Finding("visualization_contract", VISUALIZATION_CONTRACT_PATH, "must-be-canonical")
        )
    if inherited_string(entry, defaults, "audience") != "skill":
        findings.append(
            Finding("visualization_contract", VISUALIZATION_CONTRACT_PATH, "audience-must-be-skill")
        )
    if inherited_string(entry, defaults, "placement") not in {
        "support_library",
        "validation_checker",
    }:
        findings.append(
            Finding(
                "visualization_contract",
                VISUALIZATION_CONTRACT_PATH,
                "invalid-placement",
            )
        )
    if VISUALIZATION_CONTRACT_DOC not in string_list(entry.get("docs")):
        findings.append(
            Finding(
                "visualization_contract",
                VISUALIZATION_CONTRACT_PATH,
                "missing-canonical-doc",
            )
        )
    return findings


def validate_catalog(root: Path) -> CatalogReport:
    """Run catalog validation."""
    root = root.resolve()
    data, findings = load_catalog(resolve_repo_path(root, CATALOG_PATH))
    if data is None:
        return CatalogReport(tuple(findings), ())

    families_map = as_mapping(data.get("families")) or {}
    family_defaults = {
        name: as_mapping(raw_family) or {}
        for name, raw_family in families_map.items()
    }
    families = set(families_map)
    statuses = allowed_values(data, "status_values")
    roles = allowed_values(data, "role_values")
    audiences = allowed_values(data, "audience_values")
    placements = allowed_values(data, "placement_values")
    entries_raw = as_sequence(data.get("entries"))
    if data.get("version") != 1:
        findings.append(Finding("catalog", CATALOG_PATH, "unsupported-version"))
    if not families:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-families"))
    if not statuses:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-status-values"))
    if not roles:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-role-values"))
    if not audiences:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-audience-values"))
    if not placements:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-placement-values"))
    for family_name, family_info in family_defaults.items():
        audience = inherited_string(family_info, {}, "audience")
        placement = inherited_string(family_info, {}, "placement")
        if has_non_string_key(family_info, "audience"):
            findings.append(Finding("family", family_name, "invalid-audience"))
        elif audience is None:
            findings.append(Finding("family", family_name, "missing-audience"))
        elif audience not in audiences:
            findings.append(Finding("family", family_name, "invalid-audience"))
        if has_non_string_key(family_info, "placement"):
            findings.append(Finding("family", family_name, "invalid-placement"))
        elif placement is None:
            findings.append(Finding("family", family_name, "missing-placement"))
        elif placement not in placements:
            findings.append(Finding("family", family_name, "invalid-placement"))
    if entries_raw is None:
        findings.append(Finding("catalog", CATALOG_PATH, "entries-must-be-list"))
        return CatalogReport(tuple(findings), ())

    entries: list[Mapping[str, object]] = []
    rows: list[CatalogRow] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for index, raw_entry in enumerate(entries_raw, start=1):
        entry = as_mapping(raw_entry)
        if entry is None:
            findings.append(Finding("entry", CATALOG_PATH, f"entry-{index}-not-mapping"))
            continue
        entries.append(entry)
        family = entry.get("family")
        defaults = family_defaults.get(family, {}) if isinstance(family, str) else {}
        rows.append(catalog_row(entry, defaults))
        entry_id = entry.get("id")
        path = entry_path(entry)
        if isinstance(entry_id, str):
            if entry_id in ids:
                findings.append(Finding("entry", path, f"duplicate-id:{entry_id}"))
            ids.add(entry_id)
        if path in paths:
            findings.append(Finding("entry", path, "duplicate-path"))
        paths.add(path)
        findings.extend(
            check_entry(root, entry, families, statuses, roles, audiences, placements, defaults)
        )

    findings.extend(check_default_wiring(root, entries))
    findings.extend(check_catalog_docs(root))
    findings.extend(check_tool_docs_manifest(root, entries))
    findings.extend(check_visualization_contract_entry(root, entries, family_defaults))
    sorted_findings = sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )
    return CatalogReport(tuple(sorted_findings), tuple(rows))


def check_catalog(root: Path) -> list[Finding]:
    """Run catalog validation and return only findings."""
    return list(validate_catalog(root).findings)


def rust_tokens(text: str) -> tuple[RustToken, ...]:
    """Lex the bounded Rust token subset used by manual CLI dispatch."""
    tokens: list[RustToken] = []
    index = 0
    line = 1
    column = 1

    def advance(value: str) -> None:
        nonlocal line, column
        for character in value:
            if character == "\n":
                line += 1
                column = 1
            else:
                column += 1

    while index < len(text):
        character = text[index]
        if character.isspace():
            advance(character)
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            advance(text[index:end])
            index = end
            continue
        if text.startswith("/*", index):
            depth = 1
            end = index + 2
            while end < len(text) and depth:
                if text.startswith("/*", end):
                    depth += 1
                    end += 2
                elif text.startswith("*/", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            if depth:
                raise ValueError("unterminated block comment")
            advance(text[index:end])
            index = end
            continue
        start_line, start_column = line, column
        if character == '"':
            end = index + 1
            escaped = False
            while end < len(text):
                current = text[end]
                if current == '"' and not escaped:
                    end += 1
                    break
                escaped = current == "\\" and not escaped
                if current != "\\":
                    escaped = False
                end += 1
            else:
                raise ValueError("unterminated string literal")
            value = text[index:end]
        elif character.isalpha() or character == "_":
            end = index + 1
            while end < len(text) and (text[end].isalnum() or text[end] == "_"):
                end += 1
            value = text[index:end]
        elif character.isdigit():
            end = index + 1
            while end < len(text) and text[end].isdigit():
                end += 1
            value = text[index:end]
        else:
            compound = next(
                (
                    item
                    for item in ("::", "..", ">=", "&&", "||", "==", "=>")
                    if text.startswith(item, index)
                ),
                None,
            )
            value = compound or character
            end = index + len(value)
        advance(text[index:end])
        tokens.append(
            RustToken(
                value=value,
                start_line=start_line,
                start_column=start_column,
                end_line=line,
                end_column=column,
            )
        )
        index = end
    return tuple(tokens)


def token_sequence_matches(tokens: tuple[RustToken, ...], values: tuple[str, ...]) -> tuple[int, ...]:
    """Return every exact token-sequence start."""
    return tuple(
        index
        for index in range(0, len(tokens) - len(values) + 1)
        if tuple(token.value for token in tokens[index : index + len(values)]) == values
    )


def token_span(path: str, tokens: tuple[RustToken, ...], start: int, length: int) -> PublicSourceSpan:
    """Return the span covering one exact token sequence."""
    first = tokens[start]
    last = tokens[start + length - 1]
    return PublicSourceSpan(
        path=path,
        start_line=first.start_line,
        start_column=first.start_column,
        end_line=last.end_line,
        end_column=last.end_column,
    )


def text_phrase_span(path: str, text: str, phrase: str) -> PublicSourceSpan | None:
    """Return the unique line span for one corroborating phrase."""
    matches: list[PublicSourceSpan] = []
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        start = source_line.find(phrase)
        if start >= 0:
            matches.append(
                PublicSourceSpan(
                    path=path,
                    start_line=line_number,
                    start_column=start + 1,
                    end_line=line_number,
                    end_column=start + len(phrase) + 1,
                )
            )
    return matches[0] if len(matches) == 1 else None


def yaml_id_spans(path: str, text: str) -> dict[str, PublicSourceSpan]:
    """Index YAML id declarations from the parser's source marks."""
    spans: dict[str, PublicSourceSpan] = {}

    def visit(node: yaml.Node) -> None:
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if (
                    isinstance(key, yaml.ScalarNode)
                    and key.value == "id"
                    and isinstance(value, yaml.ScalarNode)
                    and value.value not in spans
                ):
                    spans[value.value] = PublicSourceSpan(
                        path=path,
                        start_line=value.start_mark.line + 1,
                        start_column=value.start_mark.column + 1,
                        end_line=value.end_mark.line + 1,
                        end_column=value.end_mark.column + 1,
                    )
                visit(key)
                visit(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)

    document = yaml.compose(text)
    if document is not None:
        visit(document)
    return spans


def extract_public_surface(root: Path) -> PublicSurfaceReport:
    """Extract the fixed public CLI/tool/skill surfaces from canonical inputs."""
    root = root.resolve()
    main_path = "tools/runtime/dispatch/agent-canon/src/main.rs"
    graph_path = "tools/runtime/dispatch/agent-canon/src/graph.rs"
    cli_path = "agents/canonical/CLI_ENTRYPOINTS.md"
    tool_path = CATALOG_PATH
    skill_path = "agents/skills/catalog.yaml"
    findings: list[Finding] = []
    required_paths = (main_path, graph_path, cli_path, tool_path, skill_path)
    texts: dict[str, str] = {}
    for relative_path in required_paths:
        resolved = resolve_repo_path(root, relative_path)
        if not resolved.is_file():
            findings.append(Finding("public_surface", relative_path, "missing-input"))
            continue
        texts[relative_path] = resolved.read_text(encoding="utf-8")
    if main_path not in texts or graph_path not in texts or cli_path not in texts:
        return PublicSurfaceReport(PUBLIC_SURFACE_PRODUCER_VERSION, (), tuple(findings))
    try:
        main_tokens = rust_tokens(texts[main_path])
        graph_tokens = rust_tokens(texts[graph_path])
    except ValueError as error:
        findings.append(Finding("public_surface", "rust-dispatch", f"rust_dispatch_invalid:{error}"))
        return PublicSurfaceReport(PUBLIC_SURFACE_PRODUCER_VERSION, (), tuple(findings))

    mod_sequence = ("mod", "graph", ";")
    main_sequence = (
        "if", "args", ".", "len", "(", ")", ">=", "2", "&&", "args", "[", "1", "]",
        "==", '"graph"', "{", "std", "::", "process", "::", "exit", "(", "graph", "::", "run",
        "(", "&", "args", "[", "2", "..", "]", ")", ")", ";", "}",
    )
    mod_matches = token_sequence_matches(main_tokens, mod_sequence)
    main_matches = token_sequence_matches(main_tokens, main_sequence)
    if len(mod_matches) != 1 or len(main_matches) != 1:
        detail = "rust_dispatch_ambiguous" if len(mod_matches) > 1 or len(main_matches) > 1 else "rust_dispatch_invalid"
        findings.append(Finding("public_surface", main_path, detail))
        return PublicSurfaceReport(PUBLIC_SURFACE_PRODUCER_VERSION, (), tuple(findings))
    main_span = token_span(main_path, main_tokens, main_matches[0], len(main_sequence))
    rows: list[PublicSurfaceRow] = []
    operation_handlers = {
        "build": "build_graph_with_failure",
        "status": "read_graph_status",
        "query": "query_graph",
        "context": "context_graph",
    }
    for operation, handler in operation_handlers.items():
        sequence = (
            f'"{operation}"',
            "=>",
            handler,
            "(",
            "&",
            "parsed",
            ")",
        )
        matches = token_sequence_matches(graph_tokens, sequence)
        doc_span = text_phrase_span(cli_path, texts[cli_path], f"graph {operation}")
        if len(matches) != 1 or doc_span is None:
            detail = "rust_dispatch_ambiguous" if len(matches) > 1 else "rust_dispatch_invalid"
            findings.append(Finding("public_surface", graph_path, f"{detail}:{operation}"))
            continue
        rows.append(
            PublicSurfaceRow(
                surface_id=f"cli:graph {operation}",
                kind="cli",
                path=graph_path,
                selector=f"graph {operation}",
                source_span=token_span(graph_path, graph_tokens, matches[0], len(sequence)),
                secondary_spans=tuple(sorted((main_span, doc_span), key=lambda item: (item.path, item.start_line, item.start_column))),
            )
        )

    if tool_path in texts:
        raw_tools = yaml.safe_load(texts[tool_path])
        tool_mapping = as_mapping(raw_tools) or {}
        tool_entries = as_sequence(tool_mapping.get("entries")) or ()
        tool_spans = yaml_id_spans(tool_path, texts[tool_path])
        for raw_entry in tool_entries:
            entry = as_mapping(raw_entry)
            if (
                entry is None
                or entry.get("public") is not True
                or not isinstance(entry.get("id"), str)
            ):
                continue
            identifier = cast(str, entry["id"])
            span = tool_spans.get(identifier)
            if span is None:
                findings.append(Finding("public_surface", tool_path, f"span-missing:{identifier}"))
                continue
            command = entry.get("command")
            selector = command if isinstance(command, str) else identifier
            rows.append(PublicSurfaceRow(f"tool:{identifier}", "tool", span.path, selector, span, ()))
    if skill_path in texts:
        raw_skills = yaml.safe_load(texts[skill_path])
        skill_mapping = as_mapping(raw_skills) or {}
        skill_entries = as_sequence(skill_mapping.get("skill_families")) or ()
        skill_spans = yaml_id_spans(skill_path, texts[skill_path])
        for raw_entry in skill_entries:
            entry = as_mapping(raw_entry)
            if entry is None or not isinstance(entry.get("id"), str):
                continue
            identifier = cast(str, entry["id"])
            span = skill_spans.get(identifier)
            if span is None:
                findings.append(Finding("public_surface", skill_path, f"span-missing:{identifier}"))
                continue
            rows.append(PublicSurfaceRow(f"skill:{identifier}", "skill", span.path, identifier, span, ()))
    rows.sort(key=lambda row: (row.kind, row.surface_id, row.source_span.path, row.source_span.start_line))
    seen: set[str] = set()
    for row in rows:
        if row.surface_id in seen:
            findings.append(Finding("public_surface", row.source_span.path, f"surface-id-duplicate:{row.surface_id}"))
        seen.add(row.surface_id)
    return PublicSurfaceReport(
        PUBLIC_SURFACE_PRODUCER_VERSION,
        tuple(rows) if not findings else (),
        tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: CatalogReport, public: PublicSurfaceReport | None = None) -> str:
    """Render JSON output."""
    catalog = {
        "status": "pass" if not report.findings else "fail",
        "findings": [asdict(finding) for finding in report.findings],
        "entries": [asdict(entry) for entry in report.entries],
    }
    payload: dict[str, object] = {
        "schema": "agent_canon.catalog_bundle.v1",
        "catalog": catalog,
    }
    if public is not None:
        payload["public"] = {
            "producer_version": public.producer_version,
            "status": "pass" if not public.findings else "fail",
            "findings": [asdict(finding) for finding in public.findings],
            "rows": [asdict(row) for row in public.rows],
        }
    return json.dumps(payload, indent=2, sort_keys=True)


def markdown_cell(value: object) -> str:
    """Render one safe Markdown table cell."""
    return str(value).replace("|", "\\|")


def render_markdown(report: CatalogReport) -> str:
    """Render a Markdown validation report and tool crosswalk."""
    status = "pass" if not report.findings else "fail"
    lines = [
        "# AgentCanon Tool Catalog",
        "",
        f"- Status: `{status}`",
        f"- Findings: `{len(report.findings)}`",
        f"- Entries: `{len(report.entries)}`",
        "",
    ]
    if report.findings:
        lines.extend(
            [
                "## Findings",
                "",
                "| Check | Path | Detail |",
                "| ----- | ---- | ------ |",
            ]
        )
        for finding in report.findings:
            lines.append(
                "| "
                f"{markdown_cell(finding.check)} | "
                f"`{markdown_cell(finding.path)}` | "
                f"{markdown_cell(finding.detail)} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Tool Crosswalk",
            "",
            "| ID | Family | Audience | Placement | Status | Default | Path | Summary |",
            "| -- | ------ | -------- | --------- | ------ | ------- | ---- | ------- |",
        ]
    )
    for entry in report.entries:
        default = ",".join(
            label
            for label, enabled in (("ci", entry.ci), ("pr", entry.pr_check))
            if enabled
        ) or "-"
        lines.append(
            "| "
            f"`{markdown_cell(entry.tool_id)}` | "
            f"{markdown_cell(entry.family)} | "
            f"{markdown_cell(entry.audience)} | "
            f"{markdown_cell(entry.placement)} | "
            f"{markdown_cell(entry.status)} | "
            f"{markdown_cell(default)} | "
            f"`{markdown_cell(entry.path)}` | "
            f"{markdown_cell(entry.summary)} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the catalog validator."""
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    report = validate_catalog(root)
    public = extract_public_surface(root)
    if args.format == "json":
        print(render_json(report, public))
    elif args.format == "markdown":
        print(render_markdown(report))
        # Markdown is the catalog crosswalk projection.  The public-surface
        # extractor is intentionally reported by the JSON/text projections;
        # minimal catalog fixtures need not materialize Rust/CLI inputs merely
        # to render this catalog-owned view.
        return 1 if report.findings else 0
    else:
        for finding in report.findings:
            print(finding.render())
        for finding in public.findings:
            print(finding.render())
        total_findings = len(report.findings) + len(public.findings)
        print(f"TOOL_CATALOG_FINDINGS={total_findings}")
        print(f"TOOL_CATALOG={'pass' if total_findings == 0 else 'fail'}")
    return 1 if report.findings or public.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
