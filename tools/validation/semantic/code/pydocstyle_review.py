#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs the explicit AgentCanon Docstring review against the canonical source-root config.
# upstream implementation ./agent_canon_source_root.py resolves standalone and derived source roots.
# upstream design ../../documents/conventions/DOCSTRING_GUIDE.md owns the D213 Docstring contract.
# downstream implementation ../../agents/skills/python-review.md documents the explicit review route.
# downstream implementation ../../tools/ci/PRE_REVIEW_GUIDE.md documents the explicit review route.
# @dependency-end
"""Run the explicit AgentCanon pydocstyle review with source-root authority."""

from __future__ import annotations

import argparse
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tools.runtime.source.agent_canon_source_root import (
    RootResolution,
    SourceRootFailure,
    resolve_agent_canon_source_root,
)

CANONICAL_CONFIG_RELATIVE_PATH = Path("tools/validation/ci/config/pydocstyle.toml")


def _is_within(path: Path, root: Path) -> bool:
    """Return whether a resolved path belongs to the resolved source root."""
    return path == root or root in path.parents


def _contains_symlink(path: Path, root: Path) -> bool:
    """Return whether a lexical target component is a symlink."""
    relative = path.relative_to(root)
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            return True
    return False


def resolve_canonical_config(
    raw_root: Path,
    *,
    resolver: Callable[[Path], RootResolution] = resolve_agent_canon_source_root,
) -> Path:
    """Resolve the unique canonical pydocstyle config under AgentCanon source root."""
    resolution = resolver(raw_root)
    source_root = resolution.source_root.resolve()
    config = (source_root / CANONICAL_CONFIG_RELATIVE_PATH).resolve()
    if not _is_within(config, source_root):
        raise SourceRootFailure(
            "agent_canon_pydocstyle_config_escape",
            f"Canonical config resolves outside source root: {config}",
        )
    if not config.is_file():
        raise SourceRootFailure(
            "agent_canon_pydocstyle_config_missing",
            f"Canonical config does not exist: {config}",
        )
    return config


def resolve_target(
    raw_root: Path,
    target: str,
    *,
    resolver: Callable[[Path], RootResolution] = resolve_agent_canon_source_root,
) -> Path:
    """Resolve one safe repository-relative regular Python target."""
    if not target or target.startswith("-"):
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_invalid",
            "Target must be one repository-relative Python path",
        )
    lexical_target = Path(target)
    if lexical_target.is_absolute() or ".." in lexical_target.parts:
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_escape",
            f"Target must remain repository-relative: {target}",
        )
    if lexical_target.suffix != ".py":
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_type",
            f"Target must have a .py suffix: {target}",
        )

    resolution = resolver(raw_root)
    repository_root = resolution.current_repository_root.resolve()
    candidate = repository_root / lexical_target
    if _contains_symlink(candidate, repository_root):
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_symlink",
            f"Target must not contain a symlink component: {target}",
        )
    try:
        normalized = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_missing",
            f"Target does not resolve to an existing file: {target}",
        ) from exc
    if not _is_within(normalized, repository_root):
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_escape",
            f"Target resolves outside repository root: {normalized}",
        )
    try:
        is_regular = stat.S_ISREG(normalized.stat().st_mode)
    except OSError as exc:
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_missing",
            f"Target cannot be inspected: {normalized}",
        ) from exc
    if not is_regular:
        raise SourceRootFailure(
            "agent_canon_pydocstyle_target_type",
            f"Target is not a regular file: {normalized}",
        )
    return normalized


class _SingleTargetAction(argparse.Action):
    """Reject repeated target options instead of silently replacing one."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        if not isinstance(values, str):
            parser.error("--target requires one path")
        if getattr(namespace, self.dest, None) is not None:
            parser.error("--target may be provided exactly once")
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    """Create the explicit Docstring review parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        required=True,
        action=_SingleTargetAction,
        help="One repository-relative existing Python file to review.",
    )
    return parser


def run(
    args: argparse.Namespace,
    *,
    raw_root: Path | None = None,
    resolver: Callable[[Path], RootResolution] = resolve_agent_canon_source_root,
) -> int:
    """Run pydocstyle with the canonical config and return its exit code."""
    root = raw_root or Path.cwd()
    config = resolve_canonical_config(root, resolver=resolver)
    target = resolve_target(root, args.target, resolver=resolver)
    command = (
        sys.executable,
        "-m",
        "pydocstyle",
        f"--config={config}",
        "--",
        str(target),
    )
    return subprocess.run(command, check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Resolve the source-root authority and execute the explicit review."""
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except SourceRootFailure as exc:
        print(f"pydocstyle_review: {exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
