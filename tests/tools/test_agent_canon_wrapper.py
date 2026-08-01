# @dependency-start
# contract test
# responsibility Tests stable AgentCanon shell wrapper runtime isolation.
# upstream design ../../documents/design/rust-agent-tool-migration.md Rust CLI runtime boundary.
# upstream implementation ../../tools/bin/agent-canon stable shell wrapper.
# @dependency-end

"""Tests for the stable AgentCanon shell wrapper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def _run_with_fake_cargo(
    tmp_path: Path, *, cargo_target_dir: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "cargo-target.txt"
    fake_cargo = fake_bin / "cargo"
    fake_cargo.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "${CARGO_TARGET_DIR-}" > "$WRAPPER_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_cargo.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["AGENT_CANON_TOOLS_HOME"] = str(tmp_path / "tools-home")
    env["WRAPPER_CAPTURE"] = str(capture)
    if cargo_target_dir is None:
        env.pop("CARGO_TARGET_DIR", None)
    else:
        env["CARGO_TARGET_DIR"] = str(cargo_target_dir)

    result = subprocess.run(
        [str(WRAPPER), "--version"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, capture


def test_wrapper_isolates_source_fallback_from_repository_target(
    tmp_path: Path,
) -> None:
    """The default source fallback should build in the user-owned tools cache."""
    result, capture = _run_with_fake_cargo(tmp_path)

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").strip() == str(
        tmp_path / "tools-home" / "agent-canon" / "cargo-target"
    )


def test_wrapper_preserves_explicit_cargo_target_dir(tmp_path: Path) -> None:
    """Callers should retain authority over an explicit Cargo target directory."""
    explicit_target = tmp_path / "explicit-target"
    result, capture = _run_with_fake_cargo(tmp_path, cargo_target_dir=explicit_target)

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").strip() == str(explicit_target)
