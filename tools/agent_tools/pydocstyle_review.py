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
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.agent_tools.agent_canon_source_root import (
    RootResolution,
    SourceRootFailure,
    resolve_agent_canon_source_root,
)

CANONICAL_CONFIG_RELATIVE_PATH = Path("tools/ci/pydocstyle.toml")


def _is_within(path: Path, root: Path) -> bool:
    """Return whether a resolved path belongs to the resolved source root."""
    return path == root or root in path.parents


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


def build_parser() -> argparse.ArgumentParser:
    """Create the explicit Docstring review parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets", nargs="+", help="Python files or directories to review."
    )
    return parser


def run(
    args: argparse.Namespace,
    *,
    raw_root: Path | None = None,
    resolver: Callable[[Path], RootResolution] = resolve_agent_canon_source_root,
) -> int:
    """Run pydocstyle with the canonical config and return its exit code."""
    config = resolve_canonical_config(raw_root or Path.cwd(), resolver=resolver)
    command = (
        sys.executable,
        "-m",
        "pydocstyle",
        f"--config={config}",
        *args.targets,
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
