# @dependency-start
# contract test
# responsibility Verifies dependency graph scratch and publication stay in the selected parent.
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh owns graph scratch and TSV publication.
# @dependency-end

"""Focused parent-boundary tests for the dependency graph shell entrypoint."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.agent_tools.fixture_spawn import record_session_from_environment
from tools.agent_tools.parent_root_side_effects import ParentRootSideEffectBoundary

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_graph.sh"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


def _parent_fixture(tmp_path: Path) -> tuple[Path, Path]:
    parent = tmp_path / "parent"
    parent.mkdir()
    _git("init", "-q", "-b", "main", cwd=parent)
    (parent / ".gitignore").write_text(".agent-canon/\n", encoding="utf-8")
    _git("add", ".", cwd=parent)
    _git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "fixture",
        cwd=parent,
    )
    graph_cli = parent / "tools" / "bin" / "agent-canon"
    graph_cli.parent.mkdir(parents=True)
    graph_cli.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\" graph status \"*) printf '%s\\n' '{\"status\":\"fresh\"}' ;;\n"
        "  *\" graph query \"*) printf '%s\\n' "
        "'{\"status\":\"fresh\",\"nodes\":[],\"facts\":[]}' ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    graph_cli.chmod(0o755)
    source = tmp_path / "read-only-source"
    source.mkdir()
    return parent, source


def test_graph_uses_selected_parent_for_temp_and_output(tmp_path: Path) -> None:
    parent, source = _parent_fixture(tmp_path)
    output = parent / "reports" / "dependency.tsv"
    with record_session_from_environment() as session:
        environment = ParentRootSideEffectBoundary().session_environment(
            session, os.environ
        )
        result = subprocess.run(
            ("bash", str(SCRIPT), "--root", str(source), "--graph-tsv", str(output)),
            cwd=parent,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_text(encoding="utf-8") == "direction\tkind\tsource\ttarget\n"
    assert not (source / ".agent-canon").exists()
    temp_root = parent / ".agent-canon" / "tmp"
    assert not temp_root.exists() or not any(temp_root.iterdir())


def test_graph_rejects_output_outside_selected_parent(tmp_path: Path) -> None:
    parent, source = _parent_fixture(tmp_path)
    output = source / "dependency.tsv"
    with record_session_from_environment() as session:
        environment = ParentRootSideEffectBoundary().session_environment(
            session, os.environ
        )
        result = subprocess.run(
            ("bash", str(SCRIPT), "--root", str(source), "--graph-tsv", str(output)),
            cwd=parent,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "PARENT_ROOT_SIDE_EFFECT_ERROR" in result.stderr
    assert not output.exists()
    temp_root = parent / ".agent-canon" / "tmp"
    assert not temp_root.exists() or not any(temp_root.iterdir())
