#!/usr/bin/env python3
"""Apply the one-time Issue #706 runtime public-tool projection correction."""

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
    """Materialize a source-backed public view inside the synthetic workspace."""
    text = PATH.read_text(encoding="utf-8")
    helper = '''

def _materialize_alignment_public_tool_view(workspace: AlignmentWorkspace) -> None:
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
'''
    anchor = "\n\ndef initialize_alignment_workspace(workspace: AlignmentWorkspace) -> None:\n"
    text = replace_once(
        text,
        anchor,
        helper + anchor,
        "alignment public tool view helper anchor",
    )
    text = replace_once(
        text,
        '''    workspace.workspace_root.mkdir(parents=True, exist_ok=True)
    workspace.report_root.mkdir(parents=True, exist_ok=True)
    (workspace.workspace_root / "python").mkdir()
''',
        '''    workspace.workspace_root.mkdir(parents=True, exist_ok=True)
    workspace.report_root.mkdir(parents=True, exist_ok=True)
    _materialize_alignment_public_tool_view(workspace)
    (workspace.workspace_root / "python").mkdir()
''',
        "alignment workspace initialization",
    )
    PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
