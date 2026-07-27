#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks changed-file dependency headers and registered contract kind metadata.
# upstream design ../../agents/templates/closeout_gate.md closeout requires dependency evidence
# upstream design ../../documents/design/dependency-manifest-design.md dependency manifest DSL design
# upstream design ../../documents/design/dependency-contract-kinds.toml registered dependency header contract kinds
# downstream implementation ./check_dependency_header_format.sh validates manifest syntax
# downstream implementation ../../tests/agent_tools/test_check_dependency_headers.py verifies changed-file checker
# @dependency-end
"""Check that changed human-authored text files declare dependency manifests."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

try:
    from .graph_client import GraphClient, GraphClientError
except ImportError:  # pragma: no cover - direct CLI execution
    from graph_client import GraphClient, GraphClientError

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
RAW_NVIDIA_FIXTURE_PREFIX = "tests/fixtures/nvidia/"
HEADER_SCAN_LINES = 80
BINARY_SNIFF_BYTES = 4096
CONTRACT_REGISTRY = Path("documents/design/dependency-contract-kinds.toml")
CONTRACT_LINE_RE = re.compile(r"^contract\s+(?P<kind>[a-z0-9][a-z0-9-]*)$")
TOML_STRING_RE = re.compile(r'"(?P<value>[a-z0-9][a-z0-9-]*)"')


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


def path_is_repository_scoped(root: Path, path: Path) -> bool:
    """Return whether graph facts can canonically identify this source path."""
    if not (
        (root / ".git").exists()
        or (root / "vendor" / "agent-canon" / ".git").exists()
    ):
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_binary(path: Path) -> bool:
    """Return whether a file appears to be binary."""
    try:
        return b"\0" in path.read_bytes()[:BINARY_SNIFF_BYTES]
    except OSError:
        return True


def should_check(root: Path, path: Path) -> bool:
    """Return whether one file is in scope for dependency header validation."""
    if not path.is_file() or path.is_symlink() or is_binary(path):
        return False
    relative = repo_relative(root, path)
    if any(relative.startswith(prefix) for prefix in SKIP_PREFIXES):
        return False
    if relative.startswith(RAW_NVIDIA_FIXTURE_PREFIX) and path.suffix.lower() == ".txt":
        # These files are exact fd-bound NVIDIA byte evidence; their dependency
        # owner is tests/fixtures/nvidia/README.md and manifest.json. Injecting
        # a header would change the parser oracle bytes and manifest SHA.
        return False
    return path.suffix.lower() in CHECKABLE_SUFFIXES


def has_dependency_manifest(path: Path) -> bool:
    """Return whether a file declares the new dependency manifest markers."""
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    return any("@dependency-start" in line for line in lines) and any(
        "@dependency-end" in line for line in lines
    )


def has_dependency_header(path: Path) -> bool:
    """Return whether a file declares the dependency manifest format."""
    return has_dependency_manifest(path)


def strip_manifest_line(line: str) -> str:
    """Return a dependency manifest line without common comment wrappers."""
    stripped = line.rstrip("\r").strip()
    for prefix in ("# ", "#", "// ", "//", "* ", "*"):
        if stripped.startswith(prefix):
            stripped = stripped.removeprefix(prefix).strip()
            break
    if stripped.endswith(","):
        stripped = stripped[:-1].strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        stripped = stripped[1:-1].strip()
    return stripped


def manifest_lines(path: Path) -> list[str]:
    """Return normalized manifest lines from the first dependency block."""
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    inside = False
    manifest: list[str] = []
    for line in lines:
        stripped = strip_manifest_line(line)
        if stripped == "@dependency-start":
            inside = True
            continue
        if stripped == "@dependency-end":
            break
        if inside:
            manifest.append(stripped)
    return manifest


def registry_candidates(root: Path) -> tuple[Path, ...]:
    """Return registry candidates for standalone and vendored AgentCanon roots."""
    script_root = Path(__file__).resolve().parents[2]
    return (
        root / CONTRACT_REGISTRY,
        root / "vendor" / "agent-canon" / CONTRACT_REGISTRY,
        script_root / CONTRACT_REGISTRY,
    )


def contract_registry_path(root: Path) -> Path:
    """Return the dependency contract kind registry path."""
    for candidate in registry_candidates(root):
        if candidate.is_file():
            return candidate
    return root / CONTRACT_REGISTRY


def allowed_contract_kinds(root: Path) -> set[str]:
    """Return registered dependency header contract kinds."""
    registry = contract_registry_path(root)
    try:
        text = registry.read_text(encoding="utf-8")
    except OSError:
        return set()
    kinds: set[str] = set()
    in_allowed = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("allowed_kinds"):
            in_allowed = True
            continue
        if not in_allowed:
            continue
        if line.startswith("]"):
            break
        kinds.update(match.group("value") for match in TOML_STRING_RE.finditer(line))
    return kinds


def contract_kind_findings(root: Path, path: Path, allowed_kinds: set[str]) -> list[str]:
    """Return contract-kind findings for one manifest-bearing file."""
    relative = repo_relative(root, path)
    contract_lines = [
        line for line in manifest_lines(path) if line.startswith("contract ")
    ]
    if len(contract_lines) != 1:
        return [
            f"{relative}: dependency manifest must contain exactly one contract line; "
            f"fix: add 'contract <registered-kind>' after @dependency-start and choose the kind "
            f"from {contract_registry_path(root).as_posix()}"
        ]
    match = CONTRACT_LINE_RE.fullmatch(contract_lines[0])
    if match is None:
        return [
            f"{relative}: contract line must be: contract <registered-kind>; "
            f"fix: use lowercase kebab-case from {contract_registry_path(root).as_posix()}"
        ]
    contract_kind = match.group("kind")
    if contract_kind not in allowed_kinds:
        return [
            f"{relative}: unregistered dependency contract kind '{contract_kind}'; "
            f"fix: use an existing allowed_kinds entry from {contract_registry_path(root).as_posix()} "
            "or update the registry with review"
        ]
    return []


def graph_manifest_facts(root: Path) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Read manifest facts from one fresh graph snapshot."""
    try:
        client = GraphClient(root)
        response = client.query(relation="all", direction="both", all_nodes=True)
        if response.status != "fresh" or response.exit_code != 0:
            return {}, [
                "graph snapshot is not fresh; run the canonical graph build before "
                "consuming dependency-header facts"
            ]
        nodes = response.payload.get("nodes")
        if not isinstance(nodes, list):
            return {}, ["graph query omitted its canonical node snapshot"]
        facts: dict[str, dict[str, object]] = {}
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                return {}, ["graph query returned a malformed node"]
            path = raw_node.get("path")
            payload = raw_node.get("payload")
            if not isinstance(path, str) or not isinstance(payload, dict):
                return {}, ["graph query returned an incomplete source node"]
            facts[path] = payload
        return facts, []
    except GraphClientError as error:
        return {}, [f"graph snapshot unavailable: {error}"]


def graph_contract_kind_findings(
    root: Path,
    path: Path,
    allowed_kinds: set[str],
    facts: dict[str, dict[str, object]],
) -> list[str]:
    """Validate a graph-owned manifest fact without reparsing the source file."""
    relative = repo_relative(root, path)
    payload = facts.get(relative)
    if payload is None or payload.get("manifest_present") is not True:
        return [f"{relative}: missing top dependency manifest block"]
    contract_kind = payload.get("contract_kind")
    if not isinstance(contract_kind, str) or not contract_kind:
        return [f"{relative}: dependency manifest contract kind is absent from graph snapshot"]
    if contract_kind not in allowed_kinds:
        return [
            f"{relative}: unregistered dependency contract kind '{contract_kind}'; "
            f"fix: use an existing allowed_kinds entry from {contract_registry_path(root).as_posix()} "
            "or update the registry with review"
        ]
    return []


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
    allowed_kinds = allowed_contract_kinds(root)
    if not allowed_kinds:
        print("DEPENDENCY_HEADERS=fail")
        print(
            f"- missing dependency contract kind registry: "
            f"{contract_registry_path(root).as_posix()}; "
            "fix: restore documents/design/dependency-contract-kinds.toml"
        )
        return 1

    repository_paths: list[Path] = []
    for path in paths:
        resolved = path if path.is_absolute() else root / path
        if not should_check(root, resolved):
            continue
        if path_is_repository_scoped(root, resolved):
            repository_paths.append(resolved)
            continue
        if not has_dependency_manifest(resolved):
            findings.append(f"{repo_relative(root, resolved)}: missing top dependency manifest block")
            continue
        findings.extend(contract_kind_findings(root, resolved, allowed_kinds))

    if repository_paths:
        graph_facts, graph_findings = graph_manifest_facts(root)
        findings.extend(graph_findings)
        if not graph_findings:
            for resolved in repository_paths:
                findings.extend(
                    graph_contract_kind_findings(root, resolved, allowed_kinds, graph_facts)
                )

    if findings:
        print("DEPENDENCY_HEADERS=fail")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("DEPENDENCY_HEADERS=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
