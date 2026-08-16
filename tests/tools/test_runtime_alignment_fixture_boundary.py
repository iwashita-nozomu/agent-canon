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
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ALIGNMENT = (
    ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
)


def _runtime_alignment_source() -> str:
    """Return the canonical source text used by script and package entrypoints."""
    return RUNTIME_ALIGNMENT.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    """Return one top-level function from the canonical runtime owner."""
    source = _runtime_alignment_source()
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    segment = ast.get_source_segment(source, function)
    assert segment is not None
    return segment


def _load_environment_projection() -> Any:
    """Compile only the pure environment boundary without importing the CLI."""
    source = _runtime_alignment_source()
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_project_process_environment"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {
        "contextmanager": contextmanager,
        "Iterator": Iterator,
        "Mapping": Mapping,
        "os": os,
    }
    exec(compile(module, str(RUNTIME_ALIGNMENT), "exec"), namespace)
    return namespace["_project_process_environment"]


def test_runtime_alignment_projects_source_root_before_fixture_imports() -> None:
    """Direct script execution resolves the repository-owned central adapter."""
    source = _runtime_alignment_source()
    projection = "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))"

    assert source.count(projection) == 1
    assert source.index(projection) < source.index("from .fixture_spawn import")
    assert source.index(projection) < source.index("from fixture_spawn import")


def test_runtime_alignment_environment_projection_is_exact_and_reversible() -> None:
    """Fixture state is a temporary value, not a mutation of caller identity."""
    project_environment = _load_environment_projection()
    previous = os.environ.copy()
    projected = {"AGENT_CANON_RUNTIME_ALIGNMENT_FIXTURE": "fixture-owned"}

    with project_environment(projected):
        assert dict(os.environ) == projected

    assert dict(os.environ) == previous


def test_runtime_alignment_environment_restores_after_body_failure() -> None:
    """A failed bundle probe cannot leak fixture identity to later checks."""
    project_environment = _load_environment_projection()
    previous = os.environ.copy()

    try:
        with project_environment({"AGENT_CANON_RUNTIME_ALIGNMENT_FIXTURE": "failure"}):
            raise RuntimeError("probe failure")
    except RuntimeError as error:
        assert str(error) == "probe failure"
    else:
        raise AssertionError("probe failure was not propagated")

    assert dict(os.environ) == previous


def test_runtime_alignment_uses_central_synthetic_fixture_projection() -> None:
    """The source record may authorize a fixture but cannot become its identity."""
    function = _function_source("runtime_alignment_parent")

    assert "record_capability_from_environment" in function
    assert "RecordCapability.from_record" in function
    assert "create_parent_owned_temp_directory" in function
    assert "bootstrap_fixture_public_environment" in function
    assert 'mode="synthetic_tool"' in function
    assert "fixture.session.attestation" in function
    assert "_project_process_environment(fixture.environment)" in function
    assert "_temporary_environment" not in function
    assert "remove_parent_owned_tree" in function


def test_runtime_alignment_does_not_create_or_authorize_a_sibling_repository() -> None:
    """Synthetic identity stays nested under the authenticated source capability."""
    function = _function_source("runtime_alignment_parent")

    assert "source_root.parent" not in function
    assert "outer.attestation" not in function
    assert "dir=source_root.parent" not in function
    assert "fixture_receipt.physical_path" in function


def test_runtime_alignment_keeps_managed_parent_projection_unchanged() -> None:
    """A caller-provided derived parent remains the direct writable owner."""
    function = _function_source("runtime_alignment_parent")

    assert "if parent != source_root:" in function
    assert 'purpose="runtime-alignment"' in function
    assert 'parent / ".agent-canon" / "tmp" / "runtime-alignment"' in function
