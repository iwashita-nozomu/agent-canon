#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides the shared external-output and explicit source-mutation boundary for documentation tools.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md runtime artifact and target mutation boundary
# upstream implementation ../agent_tools/runtime_artifacts.py validates external runtime paths
# downstream implementation ./audit_and_fix_links.py consumes explicit mutation capability
# downstream implementation ./find_redundant_designs.py consumes explicit mutation capability
# downstream implementation ./find_similar_designs.py consumes external report output
# downstream implementation ./organize_designs.py consumes explicit mutation capability
# @dependency-end
"""Shared capability handling for documentation maintenance tools.

Documentation analyzers read source trees, but their reports and drafts are
runtime artifacts.  This module deliberately has no source-tree fallback.  A
caller must provide ``--runtime-root`` or the equivalent explicit runtime
environment capability.  Source mutation is a separate capability and can
never be inferred from an output path or a command such as ``--apply``.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from tools.runtime.artifacts.runtime_artifacts import (
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
    runtime_artifact_boundary,
)


class MutationCapabilityError(RuntimeArtifactError):
    """Raised when source mutation lacks a typed, bounded capability."""


@dataclass(frozen=True)
class MutationCapability:
    """A source mutation grant bound to one checkout and exact relative paths."""

    source_root: Path
    allowed_paths: tuple[PurePosixPath, ...]
    purpose: str
    authority: str

    @classmethod
    def from_json(cls, source_root: Path, raw: str | None) -> "MutationCapability":
        """Parse and validate the exact bootstrap mutation-capability shape."""
        if not raw:
            raise MutationCapabilityError(
                "explicit mutation capability required; pass --mutation-capability-json"
            )
        try:
            value: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MutationCapabilityError("mutation capability is not valid JSON") from exc
        if not isinstance(value, Mapping):
            raise MutationCapabilityError("mutation capability must be a JSON object")
        if set(value) != {"allowed_paths", "purpose", "authority"}:
            raise MutationCapabilityError(
                "mutation capability fields must be allowed_paths, purpose, authority"
            )
        allowed = value.get("allowed_paths")
        if not isinstance(allowed, list) or not allowed:
            raise MutationCapabilityError("mutation capability allowed_paths is required")
        source = source_root.expanduser().resolve(strict=True)
        normalized: list[PurePosixPath] = []
        for item in allowed:
            if not isinstance(item, str) or not item.strip():
                raise MutationCapabilityError("mutation capability path must be text")
            pure = PurePosixPath(item)
            if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                raise MutationCapabilityError(f"unsafe mutation capability path: {item}")
            # A capability must identify a source path without allowing a
            # symlink to redirect the mutation outside the checkout.  Missing
            # files are permitted for conservative organization proposals, but
            # existing components are checked here and again immediately
            # before mutation by ``assert_allowed``.
            lexical = source.joinpath(*pure.parts)
            try:
                resolved = lexical.resolve(strict=False)
            except OSError as exc:
                raise MutationCapabilityError(f"cannot resolve mutation path: {item}") from exc
            if not _under(source, resolved):
                raise MutationCapabilityError(f"mutation capability escapes source: {item}")
            normalized.append(pure)
        for field in ("purpose", "authority"):
            field_value = value.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise MutationCapabilityError(f"mutation capability {field} is required")
        return cls(
            source_root=source,
            allowed_paths=tuple(sorted(set(normalized), key=lambda item: item.as_posix())),
            purpose=value["purpose"],
            authority=value["authority"],
        )

    def assert_allowed(self, path: Path) -> Path:
        """Validate one source mutation target and return its resolved path."""
        candidate = path if path.is_absolute() else self.source_root / path
        try:
            resolved = candidate.resolve(strict=False)
            relative = resolved.relative_to(self.source_root)
        except (OSError, ValueError) as exc:
            raise MutationCapabilityError(f"mutation target is outside source: {path}") from exc
        relative_posix = PurePosixPath(relative.as_posix())
        if not any(
            relative_posix == allowed or allowed in relative_posix.parents
            for allowed in self.allowed_paths
        ):
            raise MutationCapabilityError(
                f"mutation target is outside allowed_paths: {relative_posix.as_posix()}"
            )
        # Existing symlink components are never a valid write target.  This
        # check intentionally covers the final path as well as its parents.
        current = self.source_root
        for part in relative.parts:
            current /= part
            try:
                if current.is_symlink():
                    raise MutationCapabilityError(
                        f"mutation target contains symlink component: {current}"
                    )
            except OSError as exc:
                raise MutationCapabilityError(
                    f"cannot inspect mutation target: {current}"
                ) from exc
        return resolved


def _under(parent: Path, child: Path) -> bool:
    """Return whether ``child`` is equal to or below ``parent``."""
    return child == parent or parent in child.parents


def external_output(
    source_root: Path,
    runtime_root: str | None,
    *,
    category: str,
    filename: str,
    output: str | None = None,
) -> tuple[RuntimeArtifactBoundary, Path]:
    """Resolve one report path beneath an explicitly external runtime root."""
    boundary = runtime_artifact_boundary(source_root, runtime_root, create=True)
    if output:
        target = boundary.resolve(Path(output))
        if target.name in {"", "."}:
            raise RuntimeArtifactError("output must name a file")
        boundary.ensure_directory(target.parent.relative_to(boundary.root))
        return boundary, target
    parent = boundary.ensure_directory(Path("tasks") / category)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=str(parent)))
    return boundary, run_dir / filename


def output_value(target: Path, boundary: RuntimeArtifactBoundary) -> str:
    """Render an output path in a stable, runtime-relative form."""
    return target.relative_to(boundary.root).as_posix()


def add_runtime_output_arguments(parser: Any, *, output_help: str = "External report path") -> None:
    """Add the common explicit runtime/output options to an argparse parser."""
    parser.add_argument(
        "--runtime-root",
        default=os.environ.get("AGENT_CANON_RUNTIME_ROOT") or None,
        help="External runtime root (or AGENT_CANON_RUNTIME_ROOT); never source-local.",
    )
    parser.add_argument(
        "--output",
        help=f"{output_help}; when omitted, a run-scoped file is created under the runtime root.",
    )
