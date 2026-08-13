#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolve AgentCanon runtime source root for command execution and route entry.
# upstream implementation ../../tools/agent_tools/route.py consumes deterministic source root for route-root selection
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py consumes deterministic command execution roots
# @dependency-end
"""Resolve the AgentCanon source root used by runtime entrypoints."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

try:
    from . import parent_root_side_effects as _parent_boundary
except ImportError:  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import parent_root_side_effects as _parent_boundary  # type: ignore[no-redef]

LAYOUT_STANDALONE = "standalone"
LAYOUT_VENDORED = "vendored"
LAYOUT_OVERRIDE = "override"
SOURCE_ROOT_OVERRIDE_ENV = "AGENT_CANON_SOURCE_ROOT"
CANON_ROOT_OVERRIDE_ENV = "AGENT_CANON_ROOT"
SOURCE_PREFIX_ENV = "AGENT_CANON_PREFIX"

VENDOR_OUTSIDE_REPOSITORY = "agent_canon_source_root_vendor_outside_repository"
ROOT_VIEW_OUTSIDE_REPOSITORY = "agent_canon_source_root_root_view_outside_repository"


@dataclass(frozen=True)
class SourceRootFailure(ValueError):
    """Typed failure raised when source-root resolution is not deterministic."""

    code: str
    detail: str


@dataclass(frozen=True)
class RootResolution:
    """Canonical root resolution used by all AgentCanon entrypoints."""

    current_repository_root: Path
    source_root: Path
    layout: str
    canon_root: Path
    parent_attestation: object | None = None


def _default_pythonpath(*, root: Path) -> str:
    """Build a deterministic pythonpath for delegated owner-owned command execution."""
    tools_path = str(root / "tools")
    repository_tools_path = str(root.resolve() / "tools")
    extra = os.environ.get("PYTHONPATH", "").strip()
    if extra:
        return ":".join((tools_path, repository_tools_path, extra))
    return ":".join((tools_path, repository_tools_path))


def _resolve_executable(root_resolution: RootResolution, command: str) -> Path:
    """Resolve a command path under the resolved source root."""
    resolved = Path(command)
    if not resolved.is_absolute():
        resolved = root_resolution.source_root / resolved
    resolved = resolved.resolve()
    if not _is_within(resolved, root_resolution.source_root):
        raise SourceRootFailure(
            "agent_canon_source_root_command_escape",
            f"Command resolves outside source root: {resolved}",
        )
    if not resolved.is_file():
        raise SourceRootFailure(
            "agent_canon_source_root_command_missing",
            f"Command path does not exist: {resolved}",
        )
    return resolved


def _run_subcommand(resolution: RootResolution, command: Sequence[str]) -> int:
    """Execute a delegated command inside the resolved AgentCanon owner root."""
    if not command:
        raise SourceRootFailure("agent_canon_source_root_command_missing", "No command provided")
    executable = _resolve_executable(resolution, command[0])
    try:
        attestation = resolution.parent_attestation
        if attestation is None:
            attestation = _parent_boundary.attest_parent_root(
                _parent_boundary.ParentRootAttestationRequest(
                    cwd=resolution.current_repository_root,
                    explicit_root=resolution.current_repository_root,
                    source_root=resolution.source_root,
                    purpose="agent-canon-source-root",
                )
            )
        env = _parent_boundary.child_environment(cast(Any, attestation), os.environ)
    except Exception as exc:
        if isinstance(exc, _parent_boundary.ParentRootSideEffectError):
            raise SourceRootFailure(
                f"agent_canon_parent_root_{exc.reject.value}", exc.detail
            ) from exc
        raise
    env["PYTHONPATH"] = _default_pythonpath(root=resolution.source_root)
    env[SOURCE_PREFIX_ENV] = _source_prefix(resolution)
    process = subprocess.run(
        (str(executable), *command[1:]),
        cwd=resolution.source_root.as_posix(),
        env=env,
        check=False,
    )
    return process.returncode


def _source_prefix(resolution: RootResolution) -> str:
    """Return the source path expected by delegated root-aware commands."""
    command_root = _find_current_repository_root(resolution.source_root)
    if not _is_within(resolution.source_root, command_root):
        raise SourceRootFailure(
            "agent_canon_source_root_prefix_outside_repository",
            f"Source root is outside delegated repository root: {resolution.source_root}",
        )
    relative = resolution.source_root.relative_to(command_root).as_posix()
    return relative or "."


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode")
    parser_exec = subparsers.add_parser("exec")
    parser_exec.add_argument("command")
    parser_exec.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def run(
    parser: argparse.Namespace,
    resolver: Callable[[Path], RootResolution] | None = None,
) -> int:
    """Run the owner-bound command delegation."""
    if resolver is None:
        resolver = resolve_agent_canon_source_root
    if parser.mode != "exec":
        raise SystemExit("agent_canon_source_root requires the `exec` subcommand")
    resolution = resolver(Path.cwd())
    return _run_subcommand(resolution, (parser.command, *tuple(parser.args)))


def _find_current_repository_root(raw_root: Path) -> Path:
    """Find the active parent root, including calls from its AgentCanon submodule."""
    start = raw_root if raw_root.is_absolute() else raw_root.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            repository_root = candidate.resolve()
            if (
                repository_root.name == "agent-canon"
                and repository_root.parent.name == "vendor"
            ):
                parent_root = repository_root.parents[1]
                expected_source = parent_root / "vendor" / "agent-canon"
                try:
                    is_parent_layout = (
                        (parent_root / ".git").exists()
                        and expected_source.resolve() == repository_root
                    )
                except (OSError, RuntimeError):
                    is_parent_layout = False
                if is_parent_layout:
                    return parent_root.resolve()
            return repository_root
    return start.resolve()


def _has_catalog(root: Path) -> bool:
    return (root / "agents" / "skills" / "catalog.yaml").is_file()


def _is_within(path: Path, root: Path) -> bool:
    """Return whether a canonical path remains within a repository root."""
    return path == root or root in path.parents


def _resolve_path(path: Path, *, failure_code: str, root: Path) -> Path:
    """Resolve one path and reject symlink targets outside the repository."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise SourceRootFailure(failure_code, f"Unable to resolve {path}: {exc}") from exc
    if not _is_within(resolved, root):
        raise SourceRootFailure(
            failure_code,
            f"{path} resolves outside current_repository_root={root}: {resolved}",
        )
    return resolved


def _same_canonical_entity(left: Path, right: Path) -> bool:
    """Return whether two existing paths identify the same filesystem entity."""
    try:
        return left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()


def _explicit_resolution(raw_root: Path, source: Path, canon: Path) -> RootResolution:
    """Resolve explicit source and canon roots without collapsing their identities."""
    if not _has_catalog(source):
        raise SourceRootFailure(
            "agent_canon_source_root_override_missing",
            f"Override source root has no AgentCanon catalog: {source}",
        )
    if not _has_catalog(canon):
        raise SourceRootFailure(
            "agent_canon_canon_root_override_missing",
            f"Override canon root has no AgentCanon catalog: {canon}",
        )
    return RootResolution(
        current_repository_root=_find_current_repository_root(raw_root),
        source_root=source,
        layout=LAYOUT_OVERRIDE,
        canon_root=canon,
    )


def _explicit_override(raw_root: Path) -> RootResolution | None:
    source_override = os.environ.get(SOURCE_ROOT_OVERRIDE_ENV, "").strip()
    canon_override = os.environ.get(CANON_ROOT_OVERRIDE_ENV, "").strip()
    if not source_override and not canon_override:
        return None
    if not source_override or not canon_override:
        raise SourceRootFailure(
            "agent_canon_source_root_override_incomplete",
            "AGENT_CANON_SOURCE_ROOT and AGENT_CANON_ROOT must be supplied together",
        )
    source_root = Path(source_override).expanduser().resolve()
    canon_root = Path(canon_override).expanduser().resolve()
    return _explicit_resolution(raw_root, source_root, canon_root)


def resolve_agent_canon_source_root(
    raw_root: Path,
    *,
    source_root: Path | None = None,
    canon_root: Path | None = None,
) -> RootResolution:
    """Resolve a deterministic AgentCanon source root from an entry directory."""
    if source_root is not None or canon_root is not None:
        if source_root is None or canon_root is None:
            raise SourceRootFailure(
                "agent_canon_source_root_override_incomplete",
                "source_root and canon_root must be supplied together",
            )
        source = source_root.expanduser().resolve()
        canon = canon_root.expanduser().resolve()
        return _explicit_resolution(raw_root, source, canon)

    explicit = _explicit_override(raw_root)
    if explicit is not None:
        return explicit

    current_repository_root = _find_current_repository_root(raw_root)
    vendor_root = current_repository_root / "vendor" / "agent-canon"
    vendor_source_root = _resolve_path(
        vendor_root,
        failure_code=VENDOR_OUTSIDE_REPOSITORY,
        root=current_repository_root,
    )
    root_view = current_repository_root / "agents"
    _resolve_path(
        root_view,
        failure_code=ROOT_VIEW_OUTSIDE_REPOSITORY,
        root=current_repository_root,
    )

    standalone_catalog = current_repository_root / "agents" / "skills" / "catalog.yaml"
    vendor_catalog = vendor_source_root / "agents" / "skills" / "catalog.yaml"
    has_standalone = _has_catalog(current_repository_root)
    has_vendor = _has_catalog(vendor_source_root)

    if not has_standalone and not has_vendor:
        raise SourceRootFailure(
            "agent_canon_source_root_missing",
            (
                f"No AgentCanon catalog found from current_repository_root={current_repository_root}"
                f" (standalone: {current_repository_root}, vendored: {vendor_source_root})"
            ),
        )

    if has_standalone and has_vendor:
        if _same_canonical_entity(standalone_catalog, vendor_catalog):
            return RootResolution(
                current_repository_root=current_repository_root,
                source_root=vendor_source_root,
                layout=LAYOUT_VENDORED,
                canon_root=vendor_source_root,
            )
        candidate_labels = (
            f"{LAYOUT_STANDALONE}:{current_repository_root}",
            f"{LAYOUT_VENDORED}:{vendor_source_root}",
        )
        raise SourceRootFailure(
            "agent_canon_source_root_ambiguous",
            " | ".join(candidate_labels),
        )

    layout = LAYOUT_STANDALONE if has_standalone else LAYOUT_VENDORED
    source_root = current_repository_root if has_standalone else vendor_source_root
    return RootResolution(
        current_repository_root=current_repository_root,
        source_root=source_root,
        layout=layout,
        canon_root=source_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SourceRootFailure as exc:
        print(f"agent_canon_source_root: {exc.code}: {exc.detail}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
