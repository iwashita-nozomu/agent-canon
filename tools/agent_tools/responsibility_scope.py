#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates AgentCanon responsibility scopes and their protecting tools.
# upstream design ../../responsibility-scope.toml machine-readable repo-local scope manifest
# upstream design ../../documents/templates/responsibility-scope.template.toml starter manifest for template-derived repositories
# upstream design ../../documents/responsibility-scope-management.md scope ownership policy
# upstream design ../../tools/catalog.yaml structured tool ownership
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tools/ci/run_all_checks.sh runs responsibility scope checks
# downstream implementation ../../tests/agent_tools/test_responsibility_scope.py tests scope validation
# @dependency-end
"""Validate AgentCanon responsibility scopes."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast
import tomllib

import yaml

MANIFEST_PATH = "responsibility-scope.toml"
CATALOG_PATH = "tools/catalog.yaml"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Finding:
    """One responsibility scope validation finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"RESPONSIBILITY_SCOPE_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class Scope:
    """One responsibility scope row."""

    scope_id: str
    owner: str
    scope_class: str
    description: str
    paths: tuple[str, ...]
    exclude_paths: tuple[str, ...]
    protecting_tools: tuple[str, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class ImportRule:
    """One allowed responsibility-scope import boundary."""

    source: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class ScopeReport:
    """Responsibility scope validation report."""

    scopes: tuple[Scope, ...]
    import_rules: tuple[ImportRule, ...]
    findings: tuple[Finding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a TOML value."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def mapping_list(value: object) -> tuple[Mapping[str, object], ...]:
    """Return a list of string-keyed mappings from a TOML value."""
    if not isinstance(value, list):
        return ()
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        if isinstance(item, Mapping) and all(isinstance(key, str) for key in item):
            result.append(cast(Mapping[str, object], item))
    return tuple(result)


def load_manifest(path: Path) -> tuple[Mapping[str, object] | None, list[Finding]]:
    """Load the responsibility scope manifest."""
    if not path.is_file():
        return None, [Finding("manifest", path.as_posix(), "missing-file")]
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if data.get("catalog_kind") != "agent_canon_responsibility_scope":
        return None, [Finding("manifest", path.as_posix(), "invalid-catalog-kind")]
    return data, []


def load_catalog_paths(root: Path) -> tuple[set[str], list[Finding]]:
    """Return paths listed in the structured tool catalog."""
    path = root / CATALOG_PATH
    if not path.is_file():
        return set(), [Finding("catalog", CATALOG_PATH, "missing-file")]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        return set(), [Finding("catalog", CATALOG_PATH, "not-mapping")]
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return set(), [Finding("catalog", CATALOG_PATH, "missing-entries")]
    paths = {
        entry.get("path")
        for entry in cast(list[object], entries)
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }
    return {cast(str, path) for path in paths}, []


def scope_from_mapping(raw_scope: Mapping[str, object]) -> Scope:
    """Convert one raw TOML scope mapping to a Scope."""
    return Scope(
        scope_id=str(raw_scope.get("id") or ""),
        owner=str(raw_scope.get("owner") or ""),
        scope_class=str(raw_scope.get("class") or ""),
        description=str(raw_scope.get("description") or ""),
        paths=string_tuple(raw_scope.get("paths")),
        exclude_paths=string_tuple(raw_scope.get("exclude_paths")),
        protecting_tools=string_tuple(raw_scope.get("protecting_tools")),
        issues=string_tuple(raw_scope.get("issues")),
    )


def import_rule_from_mapping(raw_rule: Mapping[str, object]) -> ImportRule:
    """Convert one raw TOML import-rule mapping to an ImportRule."""
    return ImportRule(
        source=str(raw_rule.get("source") or ""),
        targets=string_tuple(raw_rule.get("targets")),
    )


def has_glob(pattern: str) -> bool:
    """Return whether one path pattern contains glob syntax."""
    return any(token in pattern for token in ("*", "?", "["))


def pattern_matches(root: Path, pattern: str) -> bool:
    """Return whether one scope path pattern matches current tree content."""
    if has_glob(pattern):
        return any(root.glob(pattern))
    return (root / pattern).exists()


def pattern_covers(pattern: str, required_path: str) -> bool:
    """Return whether a scope pattern covers a required path."""
    if pattern == required_path:
        return True
    if pattern.endswith("/**"):
        prefix = pattern.removesuffix("/**").rstrip("/")
        return required_path == prefix or required_path.startswith(prefix + "/")
    return fnmatch.fnmatch(required_path, pattern)


def scope_covers(scope: Scope, path: str) -> bool:
    """Return whether one scope covers a path after exclusions."""
    if any(pattern_covers(pattern, path) for pattern in scope.exclude_paths):
        return False
    return any(pattern_covers(pattern, path) for pattern in scope.paths)


def validate_scope_shape(
    scope: Scope,
    owners: set[str],
    classes: set[str],
) -> list[Finding]:
    """Validate one scope's scalar fields."""
    findings: list[Finding] = []
    label = scope.scope_id or "<missing-id>"
    if not ID_RE.fullmatch(scope.scope_id):
        findings.append(Finding("scope", label, "invalid-id"))
    if scope.owner not in owners:
        findings.append(Finding("scope", label, "invalid-owner"))
    if scope.scope_class not in classes:
        findings.append(Finding("scope", label, "invalid-class"))
    if not scope.description.strip():
        findings.append(Finding("scope", label, "missing-description"))
    if not scope.paths:
        findings.append(Finding("scope", label, "missing-paths"))
    if not scope.protecting_tools:
        findings.append(Finding("scope", label, "missing-protecting-tools"))
    return findings


def validate_scope_paths(root: Path, scope: Scope) -> list[Finding]:
    """Validate one scope's path and issue references."""
    findings: list[Finding] = []
    for pattern in scope.paths:
        if not pattern_matches(root, pattern):
            findings.append(Finding("scope_path", scope.scope_id, f"no-match:{pattern}"))
    for pattern in scope.exclude_paths:
        if not pattern_matches(root, pattern):
            findings.append(Finding("scope_exclude_path", scope.scope_id, f"no-match:{pattern}"))
    for issue in scope.issues:
        if not (root / issue).is_file():
            findings.append(Finding("scope_issue", scope.scope_id, f"missing:{issue}"))
    return findings


def validate_protecting_tools(
    root: Path,
    scope: Scope,
    catalog_paths: set[str],
) -> list[Finding]:
    """Validate that scope protecting tools exist and are cataloged."""
    findings: list[Finding] = []
    for tool in scope.protecting_tools:
        if not (root / tool).exists():
            findings.append(Finding("scope_tool", scope.scope_id, f"missing:{tool}"))
        if tool not in catalog_paths:
            findings.append(Finding("scope_tool", scope.scope_id, f"uncataloged:{tool}"))
    return findings


def coverage_findings(required: Sequence[str], scopes: Sequence[Scope]) -> list[Finding]:
    """Return findings for required paths not covered by any scope."""
    findings: list[Finding] = []
    for required_path in required:
        if not any(scope_covers(scope, required_path) for scope in scopes):
            findings.append(Finding("coverage", required_path, "uncovered-required-path"))
    return findings


def tracked_paths(root: Path) -> tuple[str, ...]:
    """Return tracked paths when git is available, otherwise repository files."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return tuple(path for path in result.stdout.splitlines() if path)
    ignored = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "reports", "target"}
    paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if set(Path(relative).parts) & ignored:
            continue
        paths.append(relative)
    return tuple(sorted(paths))


def overlap_findings(root: Path, scopes: Sequence[Scope]) -> list[Finding]:
    """Return findings for files claimed by more than one scope."""
    findings: list[Finding] = []
    for path in tracked_paths(root):
        scope_ids = tuple(scope.scope_id for scope in scopes if scope_covers(scope, path))
        if len(scope_ids) > 1:
            findings.append(Finding("scope_overlap", path, "scopes:" + ",".join(scope_ids)))
    return findings


def validate_import_rules(
    scopes: Sequence[Scope],
    import_rules: Sequence[ImportRule],
) -> list[Finding]:
    """Validate scope import rules."""
    findings: list[Finding] = []
    scope_ids = {scope.scope_id for scope in scopes}
    seen: set[str] = set()
    for rule in import_rules:
        label = rule.source or "<missing-source>"
        if rule.source in seen:
            findings.append(Finding("import_rule", label, "duplicate-source"))
        seen.add(rule.source)
        if rule.source not in scope_ids:
            findings.append(Finding("import_rule", label, "unknown-source-scope"))
        if not rule.targets:
            findings.append(Finding("import_rule", label, "missing-targets"))
        for target in rule.targets:
            if target not in scope_ids:
                findings.append(Finding("import_rule", label, f"unknown-target-scope:{target}"))
    return findings


def validate(root: Path, manifest: str) -> ScopeReport:
    """Validate responsibility scopes under one root."""
    scope_root = root.resolve()
    data, findings = load_manifest(scope_root / manifest)
    catalog_paths, catalog_findings = load_catalog_paths(scope_root)
    findings.extend(catalog_findings)
    if data is None:
        return ScopeReport((), (), tuple(findings))

    owners = set(string_tuple(data.get("owner_values")))
    classes = set(string_tuple(data.get("class_values")))
    scopes = tuple(scope_from_mapping(item) for item in mapping_list(data.get("scope")))
    import_rules = tuple(
        import_rule_from_mapping(item) for item in mapping_list(data.get("import_rule"))
    )
    if data.get("version") != 1:
        findings.append(Finding("manifest", manifest, "unsupported-version"))
    if not scopes:
        findings.append(Finding("manifest", manifest, "missing-scopes"))

    seen: set[str] = set()
    for scope in scopes:
        if scope.scope_id in seen:
            findings.append(Finding("scope", scope.scope_id, "duplicate-id"))
        seen.add(scope.scope_id)
        findings.extend(validate_scope_shape(scope, owners, classes))
        findings.extend(validate_scope_paths(scope_root, scope))
        findings.extend(validate_protecting_tools(scope_root, scope, catalog_paths))
    findings.extend(coverage_findings(string_tuple(data.get("required_coverage")), scopes))
    findings.extend(overlap_findings(scope_root, scopes))
    findings.extend(validate_import_rules(scopes, import_rules))
    return ScopeReport(
        scopes,
        import_rules,
        tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: ScopeReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "findings": [asdict(item) for item in report.findings],
            "scopes": [asdict(item) for item in report.scopes],
            "import_rules": [asdict(item) for item in report.import_rules],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the responsibility scope checker."""
    args = build_parser().parse_args(argv)
    report = validate(args.root, args.manifest)
    if args.format == "json":
        print(render_json(report))
    else:
        for finding in report.findings:
            print(finding.render())
        print(f"RESPONSIBILITY_SCOPE_SCOPES={len(report.scopes)}")
        print(f"RESPONSIBILITY_SCOPE_IMPORT_RULES={len(report.import_rules)}")
        print(f"RESPONSIBILITY_SCOPE_FINDINGS={len(report.findings)}")
        print(f"RESPONSIBILITY_SCOPE={'pass' if not report.findings else 'fail'}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
