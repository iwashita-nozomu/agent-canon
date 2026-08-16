#!/usr/bin/env python3
"""Apply the one-time Issue #706 repository-identity product correction."""

from __future__ import annotations

from pathlib import Path

PATH = Path("tools/agent_tools/check_agent_runtime_alignment.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace one exact source fragment or fail without partial output."""
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    """Make repository identity an explicit alignment-workspace component."""
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''@dataclass(frozen=True)
class AlignmentWorkspace:
    """Temporary workspace used for runtime bundle smoke checks."""

    workspace_root: Path
    report_root: Path
    repository_roots: RepositoryRoots
''',
        '''@dataclass(frozen=True)
class AlignmentWorkspace:
    """Repository identity, writable workspace, report root, and tool roots."""

    repository_root: Path
    workspace_root: Path
    report_root: Path
    repository_roots: RepositoryRoots
''',
        "AlignmentWorkspace product",
    )
    text = replace_once(
        text,
        '''def alignment_workspace(
    tmp_root: Path,
    source_resolution: RootResolution,
) -> AlignmentWorkspace:
    """Return the temporary workspace layout for bundle smoke checks."""
    workspace_root = tmp_root / "workspace"
    report_root = tmp_root / "reports"
    repository_roots = resolve_repository_roots(
        workspace_root,
        report_root,
        source_root=source_resolution.source_root,
        canon_root=source_resolution.canon_root,
    )
    return AlignmentWorkspace(
        workspace_root=workspace_root,
        report_root=report_root,
        repository_roots=repository_roots,
    )
''',
        '''def alignment_workspace(
    tmp_root: Path,
    source_resolution: RootResolution,
) -> AlignmentWorkspace:
    """Return the typed repository/workspace/tool product for bundle checks."""
    workspace_root = tmp_root / "workspace"
    report_root = tmp_root / "reports"
    identity_resolution = resolve_agent_canon_source_root(
        workspace_root,
        source_root=source_resolution.source_root,
        canon_root=source_resolution.canon_root,
    )
    repository_roots = resolve_repository_roots(
        workspace_root,
        report_root,
        source_root=source_resolution.source_root,
        canon_root=source_resolution.canon_root,
    )
    if identity_resolution.public_tool_root is None:
        raise RuntimeError("runtime alignment identity has no public tool root")
    if repository_roots.public_tool_root is None:
        raise RuntimeError("runtime alignment roots have no public tool root")
    if (
        identity_resolution.public_tool_root.absolute()
        != repository_roots.public_tool_root.absolute()
    ):
        raise RuntimeError(
            "runtime alignment root projections disagree on the public tool view"
        )
    return AlignmentWorkspace(
        repository_root=identity_resolution.current_repository_root.resolve(),
        workspace_root=workspace_root,
        report_root=report_root,
        repository_roots=repository_roots,
    )
''',
        "alignment_workspace product construction",
    )
    text = replace_once(
        text,
        '''def _materialize_alignment_public_tool_view(workspace: AlignmentWorkspace) -> None:
    """Project source-owned tooling into the synthetic repository view.

    The workspace owns only the lexical public path.  Executable bytes remain
    in ``agentcanon_source_root`` and are neither copied nor installed into the
    fixture.  This keeps repository identity, writable state, and tool product
    identity distinct while exercising the same ``tools/agent-canon`` public
    command surface used by a derived checkout.
    """
    roots = workspace.repository_roots
    public_tool_root = roots.public_tool_root
    if public_tool_root is None:
        raise RuntimeError("runtime alignment public tool root is missing")
    expected_public_root = workspace.workspace_root / "tools" / "agent-canon"
    if public_tool_root.absolute() != expected_public_root.absolute():
        raise RuntimeError(
            "runtime alignment public tool root is not workspace-owned: "
            f"{public_tool_root}"
        )

    source_root = roots.agentcanon_source_root.resolve()
    source_tools = (source_root / "tools").resolve()
    try:
        source_tools.relative_to(source_root)
    except ValueError as error:
        raise RuntimeError(
            "runtime alignment source tools escape the canonical source root"
        ) from error
    if not source_tools.is_dir():
        raise RuntimeError(
            f"runtime alignment source tools are missing: {source_tools}"
        )

    public_tool_root.parent.mkdir(parents=True, exist_ok=False)
    public_tool_root.symlink_to(source_tools, target_is_directory=True)
    if public_tool_root.resolve() != source_tools:
        raise RuntimeError(
            "runtime alignment public tool projection does not resolve to source tooling"
        )
''',
        '''def _materialize_alignment_public_tool_view(workspace: AlignmentWorkspace) -> None:
    """Project source-owned tooling into the synthetic repository view.

    The synthetic repository owns only the lexical public path.  Executable
    bytes remain in ``agentcanon_source_root`` and are neither copied nor
    installed into the fixture.  The writable task workspace must remain a
    descendant of that independent repository identity.
    """
    roots = workspace.repository_roots
    public_tool_root = roots.public_tool_root
    if public_tool_root is None:
        raise RuntimeError("runtime alignment public tool root is missing")

    repository_root = workspace.repository_root.resolve(strict=True)
    expected_public_root = repository_root / "tools" / "agent-canon"
    if public_tool_root.absolute() != expected_public_root.absolute():
        raise RuntimeError(
            "runtime alignment public tool root is not repository-owned: "
            f"{public_tool_root}"
        )
    try:
        workspace.workspace_root.resolve().relative_to(repository_root)
    except ValueError as error:
        raise RuntimeError(
            "runtime alignment workspace escapes repository identity: "
            f"{workspace.workspace_root}"
        ) from error

    source_root = roots.agentcanon_source_root.resolve()
    source_tools = (source_root / "tools").resolve()
    try:
        source_tools.relative_to(source_root)
    except ValueError as error:
        raise RuntimeError(
            "runtime alignment source tools escape the canonical source root"
        ) from error
    if not source_tools.is_dir():
        raise RuntimeError(
            f"runtime alignment source tools are missing: {source_tools}"
        )

    public_tool_root.parent.mkdir(parents=True, exist_ok=False)
    public_tool_root.symlink_to(source_tools, target_is_directory=True)
    if public_tool_root.resolve() != source_tools:
        raise RuntimeError(
            "runtime alignment public tool projection does not resolve to source tooling"
        )
''',
        "repository-owned public tool projection",
    )
    PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
