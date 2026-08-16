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
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ALIGNMENT = (
    ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
)


def _runtime_alignment_source() -> str:
    """Return the canonical source text used by script and package entrypoints."""
    return RUNTIME_ALIGNMENT.read_text(encoding="utf-8")


def _function_node(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Return one top-level function node from the canonical runtime owner."""
    tree = ast.parse(_runtime_alignment_source())
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _function_source(name: str) -> str:
    """Return one top-level function source from the canonical runtime owner."""
    segment = ast.get_source_segment(
        _runtime_alignment_source(),
        _function_node(name),
    )
    assert segment is not None
    return segment


def _load_function(name: str, namespace: dict[str, Any]) -> Any:
    """Compile one focused owner function without importing the full CLI."""
    function = _function_node(name)
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(RUNTIME_ALIGNMENT), "exec"), namespace)
    return namespace[name]


def _load_environment_projection() -> Any:
    """Compile only the pure environment boundary without importing the CLI."""
    return _load_function(
        "_project_process_environment",
        {
            "contextmanager": contextmanager,
            "Iterator": Iterator,
            "Mapping": Mapping,
            "os": os,
        },
    )


def _load_public_tool_projection() -> Any:
    """Compile only the source-to-public-view projection boundary."""
    return _load_function(
        "_materialize_alignment_public_tool_view",
        {
            "AlignmentWorkspace": object,
            "Path": Path,
        },
    )


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


def test_alignment_workspace_keeps_repository_identity_as_a_product_component() -> None:
    """Repository, workspace, report, and tool roots cannot collapse to one path."""
    product = _function_source("alignment_workspace")

    assert "identity_resolution = resolve_agent_canon_source_root" in product
    assert "repository_roots = resolve_repository_roots" in product
    assert (
        "repository_root=identity_resolution.current_repository_root.resolve()"
        in product
    )
    assert "workspace_root=workspace_root" in product
    assert "report_root=report_root" in product
    assert "repository_roots=repository_roots" in product
    assert "root projections disagree on the public tool view" in product


def test_runtime_alignment_public_tool_view_is_source_backed_not_copied() -> None:
    """The repository owns the public name while source owns executable bytes."""
    materialize = _load_public_tool_projection()

    with tempfile.TemporaryDirectory(prefix="agent-canon-runtime-tool-view-") as directory:
        root = Path(directory)
        source_root = root / "source"
        source_tools = source_root / "tools"
        source_tools.mkdir(parents=True)
        marker = source_tools / "owner-marker.txt"
        marker.write_text("source-owned\n", encoding="utf-8")

        repository_root = root / "fixture-repository"
        workspace_root = repository_root / "scratch" / "workspace"
        workspace_root.mkdir(parents=True)
        public_tool_root = repository_root / "tools" / "agent-canon"
        workspace = SimpleNamespace(
            repository_root=repository_root,
            workspace_root=workspace_root,
            repository_roots=SimpleNamespace(
                public_tool_root=public_tool_root,
                agentcanon_source_root=source_root,
            ),
        )

        materialize(workspace)

        assert public_tool_root.is_symlink()
        assert public_tool_root.resolve() == source_tools.resolve()
        assert Path(os.readlink(public_tool_root)) == source_tools.resolve()
        assert (public_tool_root / marker.name).read_text(encoding="utf-8") == (
            "source-owned\n"
        )


def test_runtime_alignment_public_tool_view_rejects_workspace_escape() -> None:
    """A repository-owned public path cannot authorize an external workspace."""
    materialize = _load_public_tool_projection()

    with tempfile.TemporaryDirectory(prefix="agent-canon-runtime-escape-") as directory:
        root = Path(directory)
        source_root = root / "source"
        (source_root / "tools").mkdir(parents=True)
        repository_root = root / "fixture-repository"
        repository_root.mkdir()
        external_workspace = root / "external-workspace"
        external_workspace.mkdir()
        workspace = SimpleNamespace(
            repository_root=repository_root,
            workspace_root=external_workspace,
            repository_roots=SimpleNamespace(
                public_tool_root=repository_root / "tools" / "agent-canon",
                agentcanon_source_root=source_root,
            ),
        )

        try:
            materialize(workspace)
        except RuntimeError as error:
            assert "workspace escapes repository identity" in str(error)
        else:
            raise AssertionError("external workspace was accepted")


def test_runtime_alignment_public_tool_projection_has_no_copy_or_install_lane() -> None:
    """Public-view construction cannot become a second tool-product owner."""
    function = _function_source("_materialize_alignment_public_tool_view")
    initializer = _function_source("initialize_alignment_workspace")

    assert 'workspace.repository_root.resolve(strict=True)' in function
    assert 'repository_root / "tools" / "agent-canon"' in function
    assert '(source_root / "tools").resolve()' in function
    assert "symlink_to(source_tools, target_is_directory=True)" in function
    assert "_materialize_alignment_public_tool_view(workspace)" in initializer
    for forbidden in (
        "copytree",
        "copy2",
        "pip install",
        "cargo install",
        "npm install",
        "apt-get",
    ):
        assert forbidden not in function


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
