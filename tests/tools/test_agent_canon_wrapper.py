"""Focused tests for the host-only AgentCanon CLI adapter."""

# @dependency-start
# contract test
# responsibility Verifies stable wrapper requests and bootstrap-owned runtime boundaries.
# upstream implementation ../../tools/bin/agent-canon stable wrapper
# upstream implementation ../../tools/agent_tools/tool_dispatch.py typed dispatcher
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


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a source/control/runtime fixture and a fake bootstrap boundary."""
    source = tmp_path / "agent-canon"
    source_tools = source / "tools" / "bin"
    source_tools.mkdir(parents=True)
    wrapper = source_tools / "agent-canon"
    wrapper.write_bytes(WRAPPER.read_bytes())
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    dispatcher = source / "tools" / "agent_tools"
    dispatcher.mkdir(parents=True)
    (dispatcher / "tool_dispatch.py").write_bytes(
        (PROJECT_ROOT / "tools/agent_tools/tool_dispatch.py").read_bytes()
    )
    control = tmp_path / "control"
    runtime = control / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "state.json").write_text(
        json.dumps({"targets": {"fixture": {"root": str(source)}}}),
        encoding="utf-8",
    )
    captured = tmp_path / "request.json"
    bootstrap = source / "bootstrap.sh"
    bootstrap.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(captured)!r}).write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    bootstrap.chmod(bootstrap.stat().st_mode | stat.S_IXUSR)
    return source, control, runtime, bootstrap


def _environment(control: Path, runtime: Path, bootstrap: Path) -> dict[str, str]:
    """Return the minimum runtime environment accepted by the wrapper."""
    environment = {
        "PATH": os.environ["PATH"],
        "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
        "AGENT_CANON_RUNTIME_ROOT": str(runtime),
        "AGENT_CANON_TARGET_ROOT": str(bootstrap.parent),
    }
    return environment


def test_wrapper_submits_rust_request_to_bootstrap(tmp_path: Path) -> None:
    """The stable Rust API is preserved behind a typed bootstrap request."""
    source, control, runtime, bootstrap = _fixture(tmp_path)
    result = subprocess.run(
        [str(source / "tools/bin/agent-canon"), "--version", "a value"],
        cwd=source,
        env=_environment(control, runtime, bootstrap),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    assert request[request.index("exec") :] == [
        "exec",
        "--root",
        str(source.resolve()),
        "--",
        "agent-canon",
        "--version",
        "a value",
    ]
    assert not (source / ".agent-canon").exists()


def test_wrapper_leaves_missing_runtime_to_bootstrap(tmp_path: Path) -> None:
    """Rust requests let bootstrap create or migrate the runtime root."""
    source, control, _runtime, bootstrap = _fixture(tmp_path)
    legacy_runtime = tmp_path / "home" / "workspace" / "agent-canon-runtime" / "host"
    result = subprocess.run(
        [str(source / "tools/bin/agent-canon"), "--version"],
        cwd=source,
        env={
            "PATH": os.environ["PATH"],
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
            "AGENT_CANON_RUNTIME_ROOT": str(legacy_runtime),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    assert request[request.index("--runtime-root") + 1] == str(legacy_runtime)
    assert request[-5:] == [
        "--root",
        str(source.resolve()),
        "--",
        "agent-canon",
        "--version",
    ]
    assert not (source / ".agent-canon").exists()


def test_symlinked_dotfiles_wrapper_uses_source_root_and_legacy_runtime(
    tmp_path: Path,
) -> None:
    """A dotfiles symlink submits the source-root request without host checks."""
    source, control, _runtime, _bootstrap = _fixture(tmp_path)
    home = tmp_path / "home"
    dotfiles = home / ".dotfiles"
    dotfiles.mkdir(parents=True)
    link = dotfiles / "agent-canon"
    link.symlink_to(source / "tools/bin/agent-canon")
    legacy_runtime = home / "workspace" / "agent-canon-runtime" / "host"
    result = subprocess.run(
        [str(link), "--version"],
        cwd=source,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(home),
            "AGENT_CANON_RUNTIME_ROOT": str(legacy_runtime),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    request = json.loads((tmp_path / "request.json").read_text(encoding="utf-8"))
    assert request[request.index("--repository-root") + 1] == str(source.resolve())
    assert request[request.index("--runtime-root") + 1] == str(legacy_runtime)
    assert request[-5:] == [
        "--root",
        str(source.resolve()),
        "--",
        "agent-canon",
        "--version",
    ]


def test_wrapper_has_no_host_build_or_source_cache_fallback() -> None:
    """The wrapper cannot silently rebuild or create source-owned state."""
    source = WRAPPER.read_text(encoding="utf-8")
    assert "cargo run" not in source
    assert "mkdir" not in source
    assert "AGENT_CANON_TOOLS_HOME" not in source
    assert "AGENT_CANON_*" not in source
