"""Runtime-alignment fixture ownership regression tests."""

# @dependency-start
# contract test
# responsibility Verifies that runtime alignment separates source tooling, synthetic repository identity, and fixture-local writable state.
# upstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py runtime-alignment owner
# upstream implementation ../../tools/agent_tools/fixture_spawn.py central synthetic fixture projection
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py signed source and fixture capabilities
# @dependency-end

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ALIGNMENT = (
    ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
)


def _runtime_alignment_parent_source() -> str:
    """Return only the owner context-manager source from the canonical module."""
    source = RUNTIME_ALIGNMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "runtime_alignment_parent"
    )
    segment = ast.get_source_segment(source, function)
    assert segment is not None
    return segment


def test_runtime_alignment_uses_central_synthetic_fixture_projection() -> None:
    """The source record may authorize a fixture but cannot become its identity."""
    function = _runtime_alignment_parent_source()

    assert "record_capability_from_environment" in function
    assert "RecordCapability.from_record" in function
    assert "create_parent_owned_temp_directory" in function
    assert "bootstrap_fixture_public_environment" in function
    assert 'mode="synthetic_tool"' in function
    assert "fixture.session.attestation" in function
    assert "_temporary_environment(fixture.environment)" in function
    assert "remove_parent_owned_tree" in function


def test_runtime_alignment_does_not_create_or_authorize_a_sibling_repository() -> None:
    """Synthetic identity stays nested under the authenticated source capability."""
    function = _runtime_alignment_parent_source()

    assert "source_root.parent" not in function
    assert "outer.attestation" not in function
    assert "dir=source_root.parent" not in function
    assert "fixture_receipt.physical_path" in function


def test_runtime_alignment_keeps_managed_parent_projection_unchanged() -> None:
    """A caller-provided derived parent remains the direct writable owner."""
    function = _runtime_alignment_parent_source()

    assert "if parent != source_root:" in function
    assert 'purpose="runtime-alignment"' in function
    assert 'parent / ".agent-canon" / "tmp" / "runtime-alignment"' in function
