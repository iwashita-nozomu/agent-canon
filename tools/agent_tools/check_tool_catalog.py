#!/usr/bin/env python3
# @dependency-start
# responsibility Validates the structured AgentCanon tool catalog.
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# upstream design ../../tools/README.md shared tool family ownership
# upstream design ../../tools/legacy/jax_solver_util/README.md legacy provenance policy
# upstream design ../../documents/tools/README.md root-facing tool entrypoint policy
# upstream design ../../documents/repo-local-tool-imports.md legacy tool disposition policy
# downstream implementation ../../tools/ci/run_all_checks.sh runs catalog validation
# downstream implementation ../../tests/agent_tools/test_check_tool_catalog.py tests validator
# @dependency-end
"""Validate the structured AgentCanon tool catalog."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

CATALOG_PATH = "tools/catalog.yaml"
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


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
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


def has_dependency_manifest(path: Path) -> bool:
    """Return whether one file has a dependency manifest near the top."""
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    return any("@dependency-start" in line for line in lines) and any(
        "@dependency-end" in line for line in lines
    )


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


def check_entry(
    root: Path,
    entry: Mapping[str, object],
    families: set[str],
    statuses: set[str],
    roles: set[str],
) -> list[Finding]:
    """Validate one catalog entry."""
    findings: list[Finding] = []
    path = entry_path(entry)
    entry_id = entry.get("id")
    family = entry.get("family")
    status = entry.get("status")
    role = entry.get("role")
    target = root / path

    if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
        findings.append(Finding("entry", path, "invalid-id"))
    if not isinstance(family, str) or family not in families:
        findings.append(Finding("entry", path, "invalid-family"))
    if not isinstance(status, str) or status not in statuses:
        findings.append(Finding("entry", path, "invalid-status"))
    if not isinstance(role, str) or role not in roles:
        findings.append(Finding("entry", path, "invalid-role"))
    if not target.exists():
        findings.append(Finding("entry", path, "missing-path"))

    if path.startswith("tools/legacy/") and status != "legacy_provenance":
        findings.append(Finding("legacy", path, "legacy-path-must-be-provenance"))
    if status == "legacy_provenance":
        if family != "legacy":
            findings.append(Finding("legacy", path, "legacy-entry-must-use-legacy-family"))
        if entry.get("callable_by_default") is not False:
            findings.append(Finding("legacy", path, "callable-by-default-must-be-false"))
        wiring = as_mapping(entry.get("default_wiring")) or {}
        if bool_from_mapping(wiring, "ci") or bool_from_mapping(wiring, "pr_check"):
            findings.append(Finding("legacy", path, "legacy-entry-must-not-be-default-wired"))
        legacy = as_mapping(entry.get("legacy"))
        if legacy is None:
            findings.append(Finding("legacy", path, "missing-legacy-provenance"))
        else:
            for key in ("source_repo", "source_path", "promotion_status"):
                if not isinstance(legacy.get(key), str) or not str(legacy.get(key)).strip():
                    findings.append(Finding("legacy", path, f"missing-{key}"))
    elif path.startswith("tools/legacy/"):
        findings.append(Finding("legacy", path, "canonical-entry-under-legacy"))

    docs = string_list(entry.get("docs"))
    if not docs:
        findings.append(Finding("entry", path, "missing-docs"))
    for doc in docs:
        if not (root / doc).is_file():
            findings.append(Finding("entry", path, f"missing-doc:{doc}"))
        elif not has_dependency_manifest(root / doc):
            findings.append(Finding("entry", path, f"doc-missing-dependency-header:{doc}"))

    tests = string_list(entry.get("tests"))
    exempt_reason = entry.get("test_exempt_reason")
    if status in {"canonical", "compatibility_wrapper"} and not tests:
        if not isinstance(exempt_reason, str) or not exempt_reason.strip():
            findings.append(Finding("entry", path, "missing-tests-or-exemption"))
    for test in tests:
        if not (root / test).is_file():
            findings.append(Finding("entry", path, f"missing-test:{test}"))
        elif not has_dependency_manifest(root / test):
            findings.append(Finding("entry", path, f"test-missing-dependency-header:{test}"))

    return findings


def read_existing_text(root: Path, paths: Iterable[str]) -> str:
    """Read and concatenate existing text files."""
    chunks: list[str] = []
    for path in paths:
        target = root / path
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
        if path not in catalog_paths and not path.startswith("tools/legacy/"):
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
    required = ("tools/catalog.yaml", "check_tool_catalog.py")
    for path in CATALOG_DOCS:
        target = root / path
        if not target.is_file():
            findings.append(Finding("catalog_docs", path, "missing-file"))
            continue
        text = target.read_text(encoding="utf-8")
        for snippet in required:
            if snippet not in text:
                findings.append(Finding("catalog_docs", path, f"missing:{snippet}"))
    return findings


def check_catalog(root: Path) -> list[Finding]:
    """Run catalog validation."""
    root = root.resolve()
    data, findings = load_catalog(root / CATALOG_PATH)
    if data is None:
        return findings

    families_map = as_mapping(data.get("families")) or {}
    families = set(families_map)
    statuses = allowed_values(data, "status_values")
    roles = allowed_values(data, "role_values")
    entries_raw = as_sequence(data.get("entries"))
    if data.get("version") != 1:
        findings.append(Finding("catalog", CATALOG_PATH, "unsupported-version"))
    if not families:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-families"))
    if not statuses:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-status-values"))
    if not roles:
        findings.append(Finding("catalog", CATALOG_PATH, "missing-role-values"))
    if entries_raw is None:
        findings.append(Finding("catalog", CATALOG_PATH, "entries-must-be-list"))
        return findings

    entries: list[Mapping[str, object]] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for index, raw_entry in enumerate(entries_raw, start=1):
        entry = as_mapping(raw_entry)
        if entry is None:
            findings.append(Finding("entry", CATALOG_PATH, f"entry-{index}-not-mapping"))
            continue
        entries.append(entry)
        entry_id = entry.get("id")
        path = entry_path(entry)
        if isinstance(entry_id, str):
            if entry_id in ids:
                findings.append(Finding("entry", path, f"duplicate-id:{entry_id}"))
            ids.add(entry_id)
        if path in paths:
            findings.append(Finding("entry", path, "duplicate-path"))
        paths.add(path)
        findings.extend(check_entry(root, entry, families, statuses, roles))

    findings.extend(check_default_wiring(root, entries))
    findings.extend(check_catalog_docs(root))
    return sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )


def render_json(findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    payload = {
        "status": "pass" if not findings else "fail",
        "findings": [asdict(finding) for finding in findings],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the catalog validator."""
    args = build_parser().parse_args(argv)
    findings = check_catalog(Path(args.root))
    if args.format == "json":
        print(render_json(findings))
    else:
        for finding in findings:
            print(finding.render())
        print(f"TOOL_CATALOG_FINDINGS={len(findings)}")
        print(f"TOOL_CATALOG={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
