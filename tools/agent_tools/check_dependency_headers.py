#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks changed-file dependency headers and registered contract kind metadata.
# upstream design ../../agents/templates/closeout_gate.md closeout requires dependency evidence
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream design ../../documents/dependency-contract-kinds.toml registered dependency header contract kinds
# downstream implementation ./check_dependency_header_format.sh validates manifest syntax
# downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py verifies changed-file checker
# @dependency-end
"""Check that changed human-authored text files declare dependency manifests."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import cast

from graph_client import (
    CANONICAL_GRAPH_EXECUTABLE,
    GraphClient,
    GraphClientError,
    GraphResponse,
)

CHECKABLE_SUFFIXES = {
    ".bash",
    ".cfg",
    ".css",
    ".html",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".zsh",
}
SKIP_PREFIXES = (
    ".git/",
    ".pytest_cache/",
    ".ruff_cache/",
    "reports/",
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Require a top-of-file @dependency-start block in changed human-authored text files."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Specific files to check. When omitted, use --changed.",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Check files changed relative to HEAD plus untracked files.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--allow-frontmatter",
        action="store_true",
        help=(
            "Accepted for policy-explicit callers. YAML frontmatter and Markdown H1 "
            "titles are allowed before the manifest by default."
        ),
    )
    return parser


def git_lines(root: Path, args: list[str]) -> list[str]:
    """Return stdout lines from one git command."""
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def changed_paths(root: Path) -> list[Path]:
    """Return changed and untracked paths relative to one repository root."""
    changed = git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRT", "HEAD", "--"])
    untracked = git_lines(root, ["ls-files", "--others", "--exclude-standard"])
    return [root / path for path in [*changed, *untracked]]


def repo_relative(root: Path, path: Path) -> str:
    """Return a stable repository-relative path for diagnostics."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def should_check(root: Path, path: Path) -> bool:
    """Return whether one file is in scope for dependency header validation."""
    if path.is_symlink():
        return False
    relative = repo_relative(root, path)
    if any(relative.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    return path.suffix.lower() in CHECKABLE_SUFFIXES


def graph_state_finding(response: GraphResponse) -> str | None:
    """Return a finding when status lacks the verified default/parent integration."""
    if response.status != "fresh" or response.exit_code != 0:
        return (
            "canonical graph is not fresh: "
            f"status={response.status};reason={response.payload.get('reason')}"
        )
    raw_integration = response.payload.get("integration_record")
    if not isinstance(raw_integration, dict):
        return "canonical graph lacks integration_record"
    integration = cast(dict[str, object], raw_integration)
    expected = {
        "schema": "agent-canon.graph.integration.v1",
        "profile": "default",
        "source_snapshot_profile": "parent",
        "verified": True,
    }
    observed = {field: integration.get(field) for field in expected}
    if observed != expected:
        return f"canonical graph integration mismatch: {observed}"
    return None


def context_manifest_findings(relative: str, response: GraphResponse) -> list[str]:
    """Map one graph context response to dependency-manifest findings."""
    if response.status != "fresh" or response.exit_code != 0:
        return [
            f"{relative}: canonical graph context unavailable: "
            f"status={response.status};reason={response.payload.get('reason')}"
        ]
    if response.payload.get("claim_path") != relative:
        return [f"{relative}: graph context claim_path mismatch"]
    raw_items_value = response.payload.get("items")
    if not isinstance(raw_items_value, list):
        return [f"{relative}: graph context items must be an array"]
    raw_items = cast(list[object], raw_items_value)
    manifest_values: dict[str, list[str]] = {
        "manifest.present": [],
        "manifest.contract": [],
        "manifest.responsibility": [],
    }
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            return [f"{relative}: graph context item must be an object"]
        item = cast(dict[str, object], raw_item)
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in manifest_values:
            continue
        value = item.get("value")
        if (
            not isinstance(value, str)
            or item.get("source_store") != "manifest"
            or item.get("producer") != "source-snapshot"
            or item.get("authority") != "ManifestParser"
        ):
            return [f"{relative}: malformed canonical manifest context item {kind}"]
        manifest_values[kind].append(value)
    present = manifest_values["manifest.present"]
    if present == ["false"]:
        return [f"{relative}: missing top dependency manifest block"]
    if present != ["true"]:
        return [f"{relative}: canonical manifest presence cardinality is invalid"]
    findings: list[str] = []
    contracts = manifest_values["manifest.contract"]
    responsibilities = manifest_values["manifest.responsibility"]
    if len(contracts) != 1 or not contracts[0]:
        findings.append(
            f"{relative}: dependency manifest must contain exactly one registered contract"
        )
    if len(responsibilities) != 1 or not responsibilities[0]:
        findings.append(
            f"{relative}: dependency manifest must contain exactly one responsibility"
        )
    return findings


def main() -> int:
    """Run dependency header validation."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    paths = (
        changed_paths(root)
        if args.changed or not args.paths
        else [Path(path) for path in args.paths]
    )
    findings: list[str] = []
    graph_client = GraphClient(root, CANONICAL_GRAPH_EXECUTABLE)
    try:
        status = graph_client.status()
    except GraphClientError as error:
        print("DEPENDENCY_HEADERS=fail")
        print(f"- canonical graph unavailable: {error}")
        return 1
    if state_finding := graph_state_finding(status):
        print("DEPENDENCY_HEADERS=fail")
        print(f"- {state_finding}")
        return 1

    checkable_paths: list[tuple[str, Path]] = []
    for path in paths:
        resolved = path if path.is_absolute() else root / path
        if not should_check(root, resolved):
            continue
        relative = repo_relative(root, resolved)
        checkable_paths.append((relative, resolved))
    for relative, _resolved in sorted(checkable_paths):
        try:
            context = graph_client.context(relative)
        except GraphClientError as error:
            findings.append(f"{relative}: canonical graph unavailable: {error}")
            continue
        findings.extend(context_manifest_findings(relative, context))

    if findings:
        print("DEPENDENCY_HEADERS=fail")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("DEPENDENCY_HEADERS=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
