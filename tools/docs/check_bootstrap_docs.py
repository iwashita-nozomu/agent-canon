#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates bootstrap-facing docs and source-free static-seed consumer structure.
# upstream design ../../documents/contracts/template-bootstrap.md default static-seed bootstrap contract
# upstream design ../../documents/contracts/static-seed-export.md static seed ownership and exclusion contract
# downstream implementation ../../tests/tools/test_check_bootstrap_docs.py exercises bootstrap and source-hidden consumer validation
# @dependency-end

"""Validate bootstrap docs and the source-free static-seed consumer boundary."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


BOOTSTRAP_DOCS = (
    Path("README.md"),
    Path("QUICK_START.md"),
    Path("docker/README.md"),
    Path("scripts/README.md"),
    Path("documents/contracts/template-bootstrap.md"),
    Path("documents/contracts/linux-wsl-host-requirements.md"),
)
DEFAULT_CONSUMER_CONTRACT_DOCS = frozenset(
    {
        Path("documents/contracts/template-bootstrap.md"),
        Path("agents/skills/start-repository.md"),
        Path("templates/README.md"),
    }
)
DEFAULT_CONSUMER_FORBIDDEN_MARKERS = (
    "vendor/agent-canon",
    "tools/agent-canon",
    "agent_canon_source_root",
    "agent-canon-update",
    "agent-canon-latest-check",
    "sync_agent_canon",
    "update_agent_canon",
    "make agent-canon-ensure-latest",
    "git submodule",
    ".gitmodules",
)
DEFAULT_BOOTSTRAP_REQUIRED_MARKERS = (
    "static seed",
    "agent-canon-static-seed.json",
    "regular file",
    "one-way",
)
ABSOLUTE_WORKSPACE_LINK = re.compile(r"\]\(/mnt/l/workspace/[^)]+\)")
DERIVED_REPO_STALE_STRINGS = (
    "Project Template",
    "project-template",
    "/mnt/l/workspace/project_template/",
)
OBJECT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")
PROVENANCE_PATH = Path("agent-canon-static-seed.json")
CANONICAL_SOURCE_REPOSITORY = "iwashita-nozomu/agent-canon"
STATIC_SEED_FORBIDDEN_PATHS = (
    Path(".agent-canon"),
    Path(".gitmodules"),
    Path("documents/runtime/shared-runtime-surfaces.toml"),
    Path("tools/agent-canon"),
    Path("vendor/agent-canon"),
)
STATIC_SEED_FORBIDDEN_CONTENT = tuple(
    marker.encode("utf-8")
    for marker in (
        "agent_canon_source_root",
        "agent-canon-latest-check",
        "agent-canon-update",
        "check_agent_canon_latest",
        "checkout_agent_canon_submodule",
        "from agent_tools",
        "git submodule",
        "http://",
        "https://",
        "import agent_tools",
        "sync_agent_canon",
        "tools/agent-canon",
        "update_agent_canon",
        "vendor/agent-canon",
    )
)
STATIC_SEED_FORBIDDEN_PREFIXES = (
    b"agents/skills/",
    b"agents/model_profiles.toml",
    b"tools/agent_tools/",
    b"../../agents/",
    b"../../tools/",
)


def build_parser() -> argparse.ArgumentParser:
    """Create the bootstrap and static-consumer validation parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository or exported seed root.")
    parser.add_argument(
        "--static-seed-consumer",
        action="store_true",
        help="Validate only the source-free static-seed consumer surface at --root.",
    )
    return parser


def current_project_name(root: Path) -> str | None:
    """Return the configured project name from ``pyproject.toml`` when available."""
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def iter_bootstrap_doc_findings(root: Path) -> list[str]:
    """Collect portability and default-consumer contract findings."""
    findings: list[str] = []
    project_name = current_project_name(root)
    check_derived_stale_strings = project_name not in (None, "project-template")

    scanned_default_docs: dict[Path, str] = {}
    scan_paths = tuple(
        dict.fromkeys((*BOOTSTRAP_DOCS, *sorted(DEFAULT_CONSUMER_CONTRACT_DOCS)))
    )
    for relative_path in scan_paths:
        path = root / relative_path
        if not path.exists() and not path.is_symlink():
            continue
        if relative_path in DEFAULT_CONSUMER_CONTRACT_DOCS and path.is_symlink():
            findings.append(
                f"{relative_path}: default consumer contract must be a regular file, not a symlink"
            )
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if relative_path in DEFAULT_CONSUMER_CONTRACT_DOCS:
            scanned_default_docs[relative_path] = text
        for line_no, line in enumerate(text.splitlines(), start=1):
            if ABSOLUTE_WORKSPACE_LINK.search(line):
                findings.append(
                    f"{relative_path}:{line_no}: replace workspace-absolute markdown links with relative links"
                )
            if check_derived_stale_strings:
                for stale_string in DERIVED_REPO_STALE_STRINGS:
                    if stale_string in line:
                        findings.append(
                            f"{relative_path}:{line_no}: stale template bootstrap text remains: {stale_string}"
                        )
            if relative_path in DEFAULT_CONSUMER_CONTRACT_DOCS:
                lowered = line.lower()
                for marker in DEFAULT_CONSUMER_FORBIDDEN_MARKERS:
                    if marker in lowered:
                        findings.append(
                            f"{relative_path}:{line_no}: default consumer contract references live runtime marker: {marker}"
                        )

    bootstrap_text = scanned_default_docs.get(Path("documents/contracts/template-bootstrap.md"))
    if bootstrap_text is not None:
        lowered = bootstrap_text.lower()
        for marker in DEFAULT_BOOTSTRAP_REQUIRED_MARKERS:
            if marker not in lowered:
                findings.append(
                    "documents/contracts/template-bootstrap.md: "
                    f"missing static consumer marker: {marker}"
                )
    return findings


def _is_regular_file(path: Path) -> bool:
    """Return whether a path is an existing non-symlink regular file."""
    return path.is_file() and not path.is_symlink()


def _load_mapping(path: Path, findings: list[str], label: str) -> Mapping[str, object] | None:
    """Load one TOML mapping and record parse/type failures."""
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        findings.append(f"{label}: invalid UTF-8 TOML: {exc}")
        return None
    if not isinstance(value, Mapping):
        findings.append(f"{label}: TOML root must be a table")
        return None
    return cast(Mapping[str, object], value)


def _canonical_role_path(role: str, raw_path: str) -> str | None:
    """Resolve a Codex role reference only when it is canonical and role-local."""
    candidate = PurePosixPath(raw_path)
    if (
        not raw_path
        or candidate.is_absolute()
        or candidate.as_posix() != raw_path
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    resolved = PurePosixPath(".codex", candidate).as_posix()
    expected = PurePosixPath(".codex", "agents", f"{role}.toml").as_posix()
    return resolved if resolved == expected else None


def iter_static_seed_consumer_findings(root: Path) -> list[str]:
    """Validate an exported seed without resolving or importing AgentCanon source."""
    findings: list[str] = []
    for relative_path in STATIC_SEED_FORBIDDEN_PATHS:
        path = root / relative_path
        if path.exists() or path.is_symlink():
            findings.append(f"{relative_path}: live AgentCanon consumer surface is forbidden")

    provenance_path = root / PROVENANCE_PATH
    if not _is_regular_file(provenance_path):
        findings.append(f"{PROVENANCE_PATH}: expected a regular provenance file")
        provenance: Mapping[str, object] | None = None
    else:
        try:
            raw_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            findings.append(f"{PROVENANCE_PATH}: invalid JSON: {exc}")
            provenance = None
        else:
            provenance = (
                cast(Mapping[str, object], raw_provenance)
                if isinstance(raw_provenance, Mapping)
                else None
            )
            if provenance is None:
                findings.append(f"{PROVENANCE_PATH}: JSON root must be an object")
    if provenance is not None:
        expected_keys = {"schema_version", "source_commit", "source_repository"}
        if set(provenance) != expected_keys:
            findings.append(
                f"{PROVENANCE_PATH}: keys must be exactly {sorted(expected_keys)}"
            )
        if provenance.get("schema_version") != 1:
            findings.append(f"{PROVENANCE_PATH}: schema_version must be 1")
        if provenance.get("source_repository") != CANONICAL_SOURCE_REPOSITORY:
            findings.append(
                f"{PROVENANCE_PATH}: source_repository must be {CANONICAL_SOURCE_REPOSITORY}"
            )
        source_commit = provenance.get("source_commit")
        if not isinstance(source_commit, str) or not OBJECT_ID_RE.fullmatch(source_commit):
            findings.append(f"{PROVENANCE_PATH}: source_commit must be a lowercase Git object ID")

    codex_root = root / ".codex"
    agents_root = codex_root / "agents"
    for relative_path, path in ((Path(".codex"), codex_root), (Path(".codex/agents"), agents_root)):
        if not path.is_dir() or path.is_symlink():
            findings.append(f"{relative_path}: expected a regular directory")

    config_path = codex_root / "config.toml"
    config: Mapping[str, object] | None = None
    if not _is_regular_file(config_path):
        findings.append(".codex/config.toml: expected a regular file")
    else:
        config = _load_mapping(config_path, findings, ".codex/config.toml")

    referenced_roles: set[str] = set()
    if config is not None:
        raw_agents = config.get("agents")
        if not isinstance(raw_agents, Mapping):
            findings.append(".codex/config.toml: [agents] table is required")
        else:
            for raw_role, raw_value in cast(Mapping[object, object], raw_agents).items():
                if not isinstance(raw_role, str) or not isinstance(raw_value, Mapping):
                    continue
                role_table = cast(Mapping[object, object], raw_value)
                config_file = role_table.get("config_file")
                if not isinstance(config_file, str):
                    findings.append(
                        f".codex/config.toml: agents.{raw_role}.config_file must be a string"
                    )
                    continue
                resolved = _canonical_role_path(raw_role, config_file)
                if resolved is None:
                    findings.append(
                        f".codex/config.toml: agents.{raw_role}.config_file must be agents/{raw_role}.toml"
                    )
                    continue
                referenced_roles.add(resolved)
                role_path = root / PurePosixPath(resolved)
                if not _is_regular_file(role_path):
                    findings.append(f"{resolved}: expected a regular referenced role file")

    actual_roles: set[str] = set()
    if agents_root.is_dir() and not agents_root.is_symlink():
        for path in agents_root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                findings.append(f"{relative}: static seed must not contain symlinks")
                continue
            if path.is_file():
                actual_roles.add(relative)
    if actual_roles != referenced_roles:
        missing = sorted(referenced_roles - actual_roles)
        extra = sorted(actual_roles - referenced_roles)
        if missing:
            findings.append(f".codex/agents: missing referenced role files: {missing}")
        if extra:
            findings.append(f".codex/agents: unreferenced role files: {extra}")

    # Scan every config/role payload, including an unreferenced role that will
    # also be reported by the exact-closure gate.
    controlled_files = {
        PROVENANCE_PATH.as_posix(),
        ".codex/config.toml",
        *referenced_roles,
        *actual_roles,
    }
    for relative in sorted(controlled_files):
        path = root / PurePosixPath(relative)
        if not _is_regular_file(path):
            continue
        lowered = path.read_bytes().lower()
        for marker in (*STATIC_SEED_FORBIDDEN_CONTENT, *STATIC_SEED_FORBIDDEN_PREFIXES):
            if marker in lowered:
                findings.append(
                    f"{relative}: static seed contains forbidden runtime marker: "
                    f"{marker.decode('utf-8', errors='replace')}"
                )
    return findings


def _print_findings(title: str, findings: Sequence[str]) -> int:
    """Print stable checker output."""
    if not findings:
        print(f"{title} passed")
        return 0
    print(f"{title} failed:")
    for finding in findings:
        print(f"- {finding}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run bootstrap-doc or source-free static-seed validation."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.static_seed_consumer:
        return _print_findings(
            "Static seed consumer check",
            iter_static_seed_consumer_findings(root),
        )
    return _print_findings("Bootstrap docs check", iter_bootstrap_doc_findings(root))


if __name__ == "__main__":
    raise SystemExit(main())
