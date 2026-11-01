"""Focused tests for the host-only AgentCanon CLI adapter."""

# @dependency-start
# contract test
# responsibility Verifies stable wrapper requests and bootstrap-owned runtime boundaries.
# upstream implementation ../../tools/bin/agent-canon stable wrapper
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/tool_dispatch.rs typed dispatcher
# downstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared runtime design
# @dependency-end

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    """Create source/control/runtime roots and a recording native executable."""
    source = tmp_path / "agent-canon"
    source_tools = source / "tools" / "bin"
    source_tools.mkdir(parents=True)
    wrapper = source_tools / "agent-canon"
    wrapper.write_bytes(WRAPPER.read_bytes())
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    control = tmp_path / "control"
    runtime = control / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "state.json").write_text(
        json.dumps({"targets": {"fixture": {"root": str(source)}}}),
        encoding="utf-8",
    )
    captured = tmp_path / "native-call.json"
    native = tmp_path / "native-agent-canon"
    native.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        f"pathlib.Path({str(captured)!r}).write_text(json.dumps({{'argv': sys.argv[1:], 'environment': {{key: os.environ.get(key) for key in ('AGENT_CANON_SOURCE_ROOT', 'AGENT_CANON_CONTROL_PARENT_ROOT', 'AGENT_CANON_RUNTIME_ROOT')}}}}))\n",
        encoding="utf-8",
    )
    native.chmod(native.stat().st_mode | stat.S_IXUSR)
    return source, control, runtime, native, captured


def _environment(control: Path, runtime: Path, native: Path) -> dict[str, str]:
    """Return the minimum environment used by the wrapper."""
    return {
        "PATH": os.environ["PATH"],
        "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
        "AGENT_CANON_RUNTIME_ROOT": str(runtime),
        "AGENT_CANON_NATIVE_BIN": str(native),
    }


def test_wrapper_uses_the_configured_native_cli(tmp_path: Path) -> None:
    source, control, runtime, native, captured = _fixture(tmp_path)
    result = subprocess.run(
        [str(source / "tools/bin/agent-canon"), "--version", "a value"],
        cwd=source,
        env=_environment(control, runtime, native),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    call = json.loads(captured.read_text(encoding="utf-8"))
    assert call["argv"] == ["--version", "a value"]
    assert call["environment"] == {
        "AGENT_CANON_SOURCE_ROOT": str(source.resolve()),
        "AGENT_CANON_CONTROL_PARENT_ROOT": None,
        "AGENT_CANON_RUNTIME_ROOT": None,
    }
    assert not (source / ".agent-canon").exists()


def test_wrapper_forwards_typed_tool_arguments_to_native_dispatch(
    tmp_path: Path,
) -> None:
    source, control, runtime, native, captured = _fixture(tmp_path)
    result = subprocess.run(
        [
            str(source / "tools/bin/agent-canon"),
            "tool",
            "run",
            "quarto",
            "--",
            "pandoc",
            "two words",
        ],
        cwd=source,
        env=_environment(control, runtime, native),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    call = json.loads(captured.read_text(encoding="utf-8"))
    assert call["argv"] == [
        "tool",
        "run",
        "--root",
        str(source.resolve()),
        "quarto",
        "--",
        "pandoc",
        "two words",
    ]
    assert call["environment"] == {
        "AGENT_CANON_SOURCE_ROOT": str(source.resolve()),
        "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
        "AGENT_CANON_RUNTIME_ROOT": str(runtime),
    }


def test_symlinked_dotfiles_wrapper_uses_the_source_root(
    tmp_path: Path,
) -> None:
    source, control, runtime, native, captured = _fixture(tmp_path)
    home = tmp_path / "home"
    dotfiles = home / ".dotfiles"
    dotfiles.mkdir(parents=True)
    link = dotfiles / "agent-canon"
    link.symlink_to(source / "tools/bin/agent-canon")
    environment = _environment(control, runtime, native)
    environment["HOME"] = str(home)
    result = subprocess.run(
        [str(link), "--version"],
        cwd=source,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    call = json.loads(captured.read_text(encoding="utf-8"))
    assert call["argv"] == ["--version"]
    assert call["environment"]["AGENT_CANON_SOURCE_ROOT"] == str(source.resolve())


def test_wrapper_has_no_host_build_or_source_cache_fallback() -> None:
    source = WRAPPER.read_text(encoding="utf-8")
    assert "cargo run" not in source
    assert "mkdir" not in source
    assert "AGENT_CANON_TOOLS_HOME" not in source
    assert "PYTHONDONTWRITEBYTECODE=1" in source
