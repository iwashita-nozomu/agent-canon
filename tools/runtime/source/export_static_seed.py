#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Exports the canonical static AgentCanon seed from one committed allowlist without consumer runtime or network behavior.
# upstream design ../../documents/contracts/static-seed-export.md static seed ownership and exclusion contract
# upstream design ../../documents/contracts/static-seed-allowlist.toml canonical exact-path allowlist
# downstream design ../../documents/tools/export_static_seed.md command and failure semantics
# downstream implementation ../../tests/agent_tools/test_export_static_seed.py verifies deterministic, forbidden-surface, and source-hidden behavior
# @dependency-end
"""Export the canonical static AgentCanon seed from a committed source snapshot."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

ALLOWLIST_PATH = "documents/contracts/static-seed-allowlist.toml"
PROVENANCE_PATH = "agent-canon-static-seed.json"
CANONICAL_SOURCE_REPOSITORY = "iwashita-nozomu/agent-canon"
ALLOWLIST_KEYS = frozenset({"version", "source_repository", "files"})
REGULAR_NONEXECUTABLE_MODE = "100644"
OBJECT_ID_RE = re.compile(r"^[0-9a-f]{40,64}$")

FORBIDDEN_PATH_PREFIXES = (
    ".agent-canon",
    ".agents",
    ".codex/hooks",
    ".devcontainer",
    ".github",
    ".vscode",
    "agents",
    "evidence",
    "issues",
    "knowledge",
    "notes",
    "reports",
    "rust",
    "tests",
    "tools",
    "vendor",
)
FORBIDDEN_EXACT_PATHS = frozenset(
    {
        ".git",
        ".gitmodules",
        "AGENTS.md",
        "ROOT_AGENTS.md",
        "sources.json",
        "sources.toml",
        "sources.yaml",
        "sources.yml",
        "sync-state.json",
        "update-state.toml",
        PROVENANCE_PATH,
    }
)
FORBIDDEN_SECRET_SUFFIXES = (".key", ".p12", ".pem")
FORBIDDEN_SECRET_COMPONENTS = frozenset(
    {".env", "credentials", "credential", "private_key", "secret", "secrets", "token"}
)
FORBIDDEN_CONTENT_MARKERS = (
    b"agent_canon_repo_ssh_key",
    b"agent_canon_repo_token",
    b"agent_canon_source_root",
    b"agent-canon-latest-check",
    b"agent-canon-update",
    b"begin private key",
    b"check_agent_canon_latest",
    b"checkout_agent_canon_submodule",
    b"curl ",
    b"from agent_tools",
    b"ghp_",
    b"git clone",
    b"git submodule",
    b"git@",
    b"github_pat_",
    b"http://",
    b"https://",
    b"import agent_tools",
    b"ssh://",
    b"sync-state.json",
    b"tools/agent-canon",
    b"update-state.toml",
    b"vendor/agent-canon",
    b"wget ",
)
# Exact producer-path prefixes rejected after case normalization.  This gate
# runs for every allowlisted blob while the immutable plan is built, before a
# destination directory can be created.
FORBIDDEN_CONTENT_PREFIXES = (
    b"agents/skills/",
    b"agents/model_profiles.toml",
    b"tools/agent_tools/",
    b"../../agents/",
    b"../../tools/",
)
FORBIDDEN_TOML_KEYS = frozenset(
    {
        "command",
        "credentials",
        "credential",
        "env",
        "environment",
        "hooks",
        "http_url",
        "mcp_servers",
        "network_access",
        "remote",
        "secret",
        "secrets",
        "socket",
        "token",
        "update_state",
        "url",
    }
)


class StaticSeedError(RuntimeError):
    """Raised when the committed seed contract cannot be exported safely."""


@dataclass(frozen=True)
class GitTreeEntry:
    """One exact entry from a committed Git tree."""

    mode: str
    object_type: str
    object_id: str
    path: str


@dataclass(frozen=True)
class StaticSeedFile:
    """One validated regular tracked file ready for export."""

    path: str
    content: bytes


@dataclass(frozen=True)
class StaticSeedPlan:
    """All source-independent bytes needed to materialize one seed."""

    source_commit: str
    source_repository: str
    files: tuple[StaticSeedFile, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the deterministic export command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        default=".",
        help="AgentCanon Git worktree containing the committed source snapshot.",
    )
    parser.add_argument(
        "--source-ref",
        default="HEAD",
        help="Git commit-ish to export. A full commit ID is recommended.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Destination directory. It must not already exist.",
    )
    return parser


def _run_git(source_root: Path, *args: str) -> bytes:
    """Run one read-only Git command with locale-stable diagnostics."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ("git", "-C", str(source_root), *args),
        check=False,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise StaticSeedError(f"git {' '.join(args)} failed: {detail or 'unknown error'}")
    return result.stdout


def _resolve_commit(source_root: Path, source_ref: str) -> str:
    """Resolve one commit without fetching or consulting a remote."""
    commit = _run_git(source_root, "rev-parse", "--verify", f"{source_ref}^{{commit}}")
    value = commit.decode("ascii", errors="strict").strip()
    if not OBJECT_ID_RE.fullmatch(value):
        raise StaticSeedError(f"resolved source commit has an invalid object ID: {value!r}")
    return value


def _load_tree(source_root: Path, commit: str) -> dict[str, GitTreeEntry]:
    """Load the complete committed tree without reading worktree files."""
    raw = _run_git(source_root, "ls-tree", "-r", "-z", "--full-tree", commit)
    entries: dict[str, GitTreeEntry] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", maxsplit=1)
            mode_bytes, type_bytes, object_id_bytes = metadata.split(b" ", maxsplit=2)
            path = path_bytes.decode("utf-8", errors="strict")
            entry = GitTreeEntry(
                mode=mode_bytes.decode("ascii", errors="strict"),
                object_type=type_bytes.decode("ascii", errors="strict"),
                object_id=object_id_bytes.decode("ascii", errors="strict"),
                path=path,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise StaticSeedError("committed tree contains an unsupported path record") from exc
        if path in entries:
            raise StaticSeedError(f"committed tree contains duplicate path: {path}")
        entries[path] = entry
    return entries


def _read_blob(source_root: Path, object_id: str) -> bytes:
    """Read exact blob bytes from the local object database."""
    if not OBJECT_ID_RE.fullmatch(object_id):
        raise StaticSeedError(f"invalid blob object ID: {object_id!r}")
    return _run_git(source_root, "cat-file", "blob", object_id)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    """Return a string-keyed mapping or reject the manifest value."""
    if not isinstance(value, Mapping):
        raise StaticSeedError(f"{label} must be a TOML table")
    raw = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise StaticSeedError(f"{label} contains a non-string key")
    return cast(Mapping[str, object], raw)


def _string_sequence(value: object, *, label: str) -> tuple[str, ...]:
    """Return an immutable string sequence or reject the manifest value."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise StaticSeedError(f"{label} must be an array of strings")
    raw = cast(Sequence[object], value)
    if not all(isinstance(item, str) for item in raw):
        raise StaticSeedError(f"{label} must contain only strings")
    return tuple(cast(str, item) for item in raw)


def _validate_relative_path(raw_path: str) -> str:
    """Require one canonical repository-relative POSIX path."""
    if not raw_path or "\x00" in raw_path or "\\" in raw_path:
        raise StaticSeedError(f"invalid allowlisted path: {raw_path!r}")
    path = PurePosixPath(raw_path)
    normalized = path.as_posix()
    if path.is_absolute() or normalized != raw_path:
        raise StaticSeedError(f"allowlisted path is not canonical and relative: {raw_path!r}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise StaticSeedError(f"allowlisted path escapes or aliases the seed root: {raw_path!r}")
    return normalized


def _matches_prefix(path: str, prefix: str) -> bool:
    """Return whether path equals or descends from one forbidden prefix."""
    return path == prefix or path.startswith(prefix + "/")


def _validate_path_surface(path: str) -> None:
    """Reject source/runtime/state/secret surfaces before blob materialization."""
    if path in FORBIDDEN_EXACT_PATHS:
        raise StaticSeedError(f"allowlisted path is a forbidden surface: {path}")
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if _matches_prefix(path, prefix):
            raise StaticSeedError(f"allowlisted path is a forbidden surface: {path}")
    for component in PurePosixPath(path).parts:
        lowered = component.lower()
        if lowered in FORBIDDEN_SECRET_COMPONENTS or lowered.endswith(FORBIDDEN_SECRET_SUFFIXES):
            raise StaticSeedError(f"allowlisted path may contain secret material: {path}")


def _validate_content(path: str, content: bytes) -> None:
    """Reject runtime imports, updater state, secrets, and network behavior."""
    lowered = content.lower()
    for prefix in FORBIDDEN_CONTENT_PREFIXES:
        if prefix in lowered:
            label = prefix.decode("ascii", errors="replace")
            raise StaticSeedError(
                f"allowlisted file contains forbidden producer prefix {label!r}: {path}"
            )
    for marker in FORBIDDEN_CONTENT_MARKERS:
        if marker in lowered:
            label = marker.decode("ascii", errors="replace")
            raise StaticSeedError(f"allowlisted file contains forbidden marker {label!r}: {path}")
    try:
        parsed = tomllib.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise StaticSeedError(f"allowlisted file is not valid UTF-8 TOML: {path}") from exc
    _validate_toml_keys(path, parsed)


def _validate_toml_keys(path: str, value: object, *, prefix: str = "") -> None:
    """Reject executable, network, state, and secret-bearing TOML keys recursively."""
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        for raw_key, child in mapping.items():
            if not isinstance(raw_key, str):
                raise StaticSeedError(f"TOML key is not a string in {path}")
            key = raw_key.lower()
            qualified = f"{prefix}.{raw_key}" if prefix else raw_key
            if key in FORBIDDEN_TOML_KEYS:
                raise StaticSeedError(f"allowlisted TOML contains forbidden key {qualified!r}: {path}")
            _validate_toml_keys(path, child, prefix=qualified)
    elif isinstance(value, list):
        for index, child in enumerate(cast(list[object], value)):
            _validate_toml_keys(path, child, prefix=f"{prefix}[{index}]")


def _parse_allowlist(content: bytes) -> tuple[str, tuple[str, ...]]:
    """Parse the sole committed allowlist and reject undeclared control fields."""
    try:
        raw = tomllib.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise StaticSeedError(f"{ALLOWLIST_PATH} is not valid UTF-8 TOML") from exc
    manifest = _mapping(raw, label=ALLOWLIST_PATH)
    unknown = set(manifest) - ALLOWLIST_KEYS
    missing = ALLOWLIST_KEYS - set(manifest)
    if unknown:
        raise StaticSeedError(f"{ALLOWLIST_PATH} has unsupported keys: {sorted(unknown)}")
    if missing:
        raise StaticSeedError(f"{ALLOWLIST_PATH} is missing keys: {sorted(missing)}")
    if manifest["version"] != 1:
        raise StaticSeedError(f"{ALLOWLIST_PATH} has unsupported version")
    source_repository = manifest["source_repository"]
    if source_repository != CANONICAL_SOURCE_REPOSITORY:
        raise StaticSeedError(
            f"{ALLOWLIST_PATH} source_repository must be "
            f"{CANONICAL_SOURCE_REPOSITORY!r}"
        )
    files = _string_sequence(manifest["files"], label=f"{ALLOWLIST_PATH} files")
    if not files:
        raise StaticSeedError(f"{ALLOWLIST_PATH} files must not be empty")
    normalized = tuple(_validate_relative_path(path) for path in files)
    if normalized != tuple(sorted(normalized)):
        raise StaticSeedError(f"{ALLOWLIST_PATH} files must be lexicographically sorted")
    if len(set(normalized)) != len(normalized):
        raise StaticSeedError(f"{ALLOWLIST_PATH} files contain duplicates")
    return source_repository, normalized


def _validate_codex_config(files: tuple[StaticSeedFile, ...]) -> None:
    """Require every registered Codex role to resolve inside the exported seed."""
    by_path = {item.path: item.content for item in files}
    config_path = ".codex/config.toml"
    config_bytes = by_path.get(config_path)
    if config_bytes is None:
        raise StaticSeedError(f"canonical seed must include {config_path}")
    config = _mapping(
        tomllib.loads(config_bytes.decode("utf-8", errors="strict")),
        label=config_path,
    )
    agents_value = config.get("agents")
    agents = _mapping(agents_value, label=f"{config_path} agents")
    referenced: set[str] = set()
    for role, raw_role in agents.items():
        if not isinstance(raw_role, Mapping):
            continue
        role_table = _mapping(raw_role, label=f"{config_path} agents.{role}")
        config_file = role_table.get("config_file")
        if not isinstance(config_file, str):
            continue
        relative = _validate_relative_path(config_file)
        resolved = PurePosixPath(".codex", relative).as_posix()
        expected = PurePosixPath(".codex", "agents", f"{role}.toml").as_posix()
        if resolved != expected:
            raise StaticSeedError(
                f"Codex role {role!r} must resolve to its same-named seed file: {resolved}"
            )
        if resolved not in by_path:
            raise StaticSeedError(f"Codex role {role!r} references an unexported file: {resolved}")
        referenced.add(resolved)
    exported_roles = {path for path in by_path if path.startswith(".codex/agents/")}
    if referenced != exported_roles:
        missing = sorted(exported_roles - referenced)
        raise StaticSeedError(f"unreferenced Codex role files in seed: {missing}")


def load_export_plan(source_root: Path, source_ref: str) -> StaticSeedPlan:
    """Load and validate all bytes before any destination write occurs."""
    root = source_root.resolve()
    commit = _resolve_commit(root, source_ref)
    tree = _load_tree(root, commit)
    allowlist_entry = tree.get(ALLOWLIST_PATH)
    if allowlist_entry is None:
        raise StaticSeedError(f"committed source does not contain {ALLOWLIST_PATH}")
    if (
        allowlist_entry.mode != REGULAR_NONEXECUTABLE_MODE
        or allowlist_entry.object_type != "blob"
    ):
        raise StaticSeedError(f"{ALLOWLIST_PATH} must be a regular non-executable tracked file")
    source_repository, paths = _parse_allowlist(
        _read_blob(root, allowlist_entry.object_id)
    )

    files: list[StaticSeedFile] = []
    for path in paths:
        _validate_path_surface(path)
        entry = tree.get(path)
        if entry is None:
            raise StaticSeedError(f"allowlisted path is not tracked in source commit: {path}")
        if entry.mode != REGULAR_NONEXECUTABLE_MODE or entry.object_type != "blob":
            raise StaticSeedError(
                f"allowlisted path must be a regular non-executable tracked file: {path} "
                f"(mode={entry.mode}, type={entry.object_type})"
            )
        content = _read_blob(root, entry.object_id)
        _validate_content(path, content)
        files.append(StaticSeedFile(path=path, content=content))
    plan = StaticSeedPlan(
        source_commit=commit,
        source_repository=source_repository,
        files=tuple(files),
    )
    _validate_codex_config(plan.files)
    return plan


def _provenance_bytes(plan: StaticSeedPlan) -> bytes:
    """Render minimal deterministic provenance without time or sync state."""
    payload = {
        "schema_version": 1,
        "source_commit": plan.source_commit,
        "source_repository": plan.source_repository,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_export(plan: StaticSeedPlan, output: Path) -> None:
    """Materialize a validated plan as regular files in one fresh directory."""
    destination = output.resolve()
    if destination.exists() or destination.is_symlink():
        raise StaticSeedError(f"output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        temporary.chmod(0o755)
        for item in plan.files:
            target = temporary / PurePosixPath(item.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(item.content)
            target.chmod(0o644)
        provenance = temporary / PROVENANCE_PATH
        with provenance.open("xb") as handle:
            handle.write(_provenance_bytes(plan))
        provenance.chmod(0o644)
        directories = sorted(
            (path for path in temporary.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            directory.chmod(0o755)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    """Export one committed static seed and print a stable result line."""
    args = build_parser().parse_args(argv)
    try:
        plan = load_export_plan(Path(args.source_root), args.source_ref)
        write_export(plan, Path(args.output))
    except StaticSeedError as exc:
        print(f"AGENT_CANON_STATIC_SEED=fail detail={exc}", file=sys.stderr)
        return 1
    print(
        "AGENT_CANON_STATIC_SEED=exported "
        f"source_commit={plan.source_commit} files={len(plan.files)} "
        f"provenance={PROVENANCE_PATH} output={Path(args.output).resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
