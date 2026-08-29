# @dependency-start
# contract test fixture
# responsibility Builds and exposes the Rust CLI for formatter tests without invoking the bootstrap wrapper.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs owns the standalone formatter CLI
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md assigns bootstrap routing to user tools
# downstream implementation ../tools/test_check_markdown_math.py uses the fixture for math checks
# downstream implementation ../tools/test_fix_markdown_math.py uses the fixture for math fixes
# downstream implementation ../tools/test_fix_mermaid.py uses the fixture for Mermaid fixes
# @dependency-end
"""Provide an external-target standalone AgentCanon binary for Rust CLI tests.

``tools/bin/agent-canon`` is intentionally a bootstrap control-plane adapter;
it cannot execute without an installed runtime and registered target.  These
formatter tests exercise the Rust implementation contract itself, so they use
the standalone binary built into a task-owned external target directory.  The
source checkout remains read-only apart from the test inputs created by each
test.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def standalone_agent_canon() -> Path:
    """Build the Rust CLI once under an external, automatically cleaned target."""
    workspace = PROJECT_ROOT / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(prefix="rust-cli-tests-", dir=workspace))
    atexit.register(shutil.rmtree, build_root, ignore_errors=True)

    target_dir = build_root / "cargo-target"
    environment = os.environ.copy()
    environment["CARGO_TARGET_DIR"] = str(target_dir)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # Cargo's registry is an input cache.  Keep it shared so a formatter-only
    # test run does not copy or rehydrate a second dependency cache.
    result = subprocess.run(
        [
            "cargo",
            "build",
            "--locked",
            "--manifest-path",
            str(PROJECT_ROOT / "tools/runtime/dispatch/agent-canon/Cargo.toml"),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "standalone AgentCanon build failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    binary = target_dir / "debug" / "agent-canon"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"standalone AgentCanon binary missing: {binary}")
    return binary
