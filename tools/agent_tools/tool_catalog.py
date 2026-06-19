#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates the structured AgentCanon tool catalog.
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# upstream design ../../tools/README.md shared tool family ownership
# upstream design ../../documents/tools/README.md root-facing tool entrypoint policy
# upstream design ../../documents/tools/tool-docs.toml one-to-one tool documentation map
# upstream design ../../documents/repo-local-tool-imports.md legacy tool disposition policy
# upstream implementation ./tool_path_policy.py defines retired legacy path policy
# downstream implementation ../../tools/ci/run_all_checks.sh runs catalog validation
# downstream implementation ../../tests/agent_tools/test_tool_catalog.py tests validator
# @dependency-end
"""Validate the structured AgentCanon tool catalog."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml
from tool_path_policy import is_retired_legacy_tool_path

CATALOG_PATH = "tools/catalog.yaml"
TOOL_DOCS_PATH = "documents/tools/tool-docs.toml"
HEADER_SCAN_LINES = 80
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOOL_REFERENCE_RE = re.compile(r"\btools/[A-Za-z0-9_./-]+\.(?:py|sh)\b")
DEFAULT_COMMAND_SOURCES = (
    "tools/ci/run_all_checks.sh",
    "tools/ci/check_agent_canon_pr.sh",
)
ENTRY_WIRING_SOURCES = (
    *DEFAULT_COMMAND_SOURCES,
    "agents/workflows/agent-canon-pr-workflow.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
)
CATALOG_DOCS = (
    "tools/README.md",
    "documents/tools/README.md",
    TOOL_DOCS_PATH,
    "documents/repo-local-tool-imports.md",
)


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


def has_dependency_manifest(path: Path) -> bool:
    """Return whether one file has a dependency manifest near the top."""
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    return any("@dependency-start" in line for line in lines) and any(
        "@dependency-end" in line for line in lines
    )


def resolve_repo_path(root: Path, relative_path: str) -> Path:
    """Resolve a path through the root view or vendored AgentCanon source."""
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
    if not has_dependency_manifest(path):
        return None, [Finding("catalog", CATALOG_PATH, "missing-dependency-header")]
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
        elif not has_dependency_manifest(doc_path):
            findings.append(Finding("entry", path, f"doc-missing-dependency-header:{doc}"))

    tests = string_list(entry.get("tests"))
    exempt_reason = entry.get("test_exempt_reason")
    if status in {"canonical", "compatibility_wrapper"} and not tests:
        if not isinstance(exempt_reason, str) or not exempt_reason.strip():
            findings.append(Finding("entry", path, "missing-tests-or-exemption"))
    for test in tests:
        test_path = resolve_repo_path(root, test)
        if not test_path.is_file():
            findings.append(Finding("entry", path, f"missing-test:{test}"))
        elif not has_dependency_manifest(test_path):
            findings.append(Finding("entry", path, f"test-missing-dependency-header:{test}"))

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
    if not has_dependency_manifest(path):
        return [], [Finding("tool_docs", TOOL_DOCS_PATH, "missing-dependency-header")]
    raw = cast(Mapping[str, object], tomllib.loads(path.read_text(encoding="utf-8")))
    if raw.get("catalog_kind") != "agent_canon_tool_docs":
        return [], [Finding("tool_docs", TOOL_DOCS_PATH, "invalid-catalog-kind")]
    entries_raw = raw.get("tool")
    if not isinstance(entries_raw, list):
        return [], [Finding("tool_docs", TOOL_DOCS_PATH, "missing-tool-list")]
    entries = cast(list[object], entries_raw)
    result: list[Mapping[str, object]] = []
    for entry in entries:
        mapping = as_mapping(entry)
        if mapping is None:
            return [], [Finding("tool_docs", TOOL_DOCS_PATH, "tool-entry-not-mapping")]
        result.append(mapping)
    return result, []


def check_tool_docs_manifest(
    root: Path,
    catalog_entries: Sequence[Mapping[str, object]],
) -> list[Finding]:
    """Validate same-named one-to-one tool documentation entries."""
    doc_entries, findings = load_tool_docs(root)
    catalog_by_id = {
        entry.get("id"): entry
        for entry in catalog_entries
        if isinstance(entry.get("id"), str)
    }
    seen_tools: set[str] = set()
    seen_docs: set[str] = set()
    for doc_entry in doc_entries:
        entry_id = doc_entry.get("id")
        tool = doc_entry.get("tool")
        doc = doc_entry.get("doc")
        if not isinstance(entry_id, str) or not isinstance(tool, str) or not isinstance(doc, str):
            findings.append(Finding("tool_docs", TOOL_DOCS_PATH, "missing-id-tool-or-doc"))
            continue
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
        elif not has_dependency_manifest(doc_path):
            findings.append(Finding("tool_docs", doc, "doc-missing-dependency-header"))
        if Path(tool).stem != Path(doc).stem:
            findings.append(Finding("tool_docs", doc, "tool-doc-name-mismatch"))
        docs = string_list(catalog_entry.get("docs"))
        if doc not in docs:
            findings.append(Finding("tool_docs", tool, f"catalog-doc-missing:{doc}"))
    return findings


def validate_catalog(root: Path) -> CatalogReport:
    """Run catalog validation."""
    root = root.resolve()
    data, findings = load_catalog(root / CATALOG_PATH)
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
    sorted_findings = sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )
    return CatalogReport(tuple(sorted_findings), tuple(rows))


def check_catalog(root: Path) -> list[Finding]:
    """Run catalog validation and return only findings."""
    return list(validate_catalog(root).findings)


def render_json(report: CatalogReport) -> str:
    """Render JSON output."""
    payload = {
        "status": "pass" if not report.findings else "fail",
        "findings": [asdict(finding) for finding in report.findings],
        "entries": [asdict(entry) for entry in report.entries],
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
    report = validate_catalog(Path(args.root))
    if args.format == "json":
        print(render_json(report))
    elif args.format == "markdown":
        print(render_markdown(report))
    else:
        for finding in report.findings:
            print(finding.render())
        print(f"TOOL_CATALOG_FINDINGS={len(report.findings)}")
        print(f"TOOL_CATALOG={'pass' if not report.findings else 'fail'}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
