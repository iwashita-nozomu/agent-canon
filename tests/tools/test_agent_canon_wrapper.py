# @dependency-start
# contract test
# responsibility Tests stable AgentCanon shell wrapper runtime isolation.
# upstream design ../../documents/design/rust-agent-tool-migration.md Rust CLI runtime boundary.
# upstream implementation ../../tools/bin/agent-canon stable shell wrapper.
# @dependency-end

"""Tests for the stable AgentCanon shell wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def _prepare_canon_layout(tmp_path: Path) -> tuple[Path, Path]:
    canon_root = tmp_path / "canon"
    wrapper = canon_root / "tools" / "bin" / "agent-canon"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(WRAPPER, wrapper)

    rust_root = canon_root / "rust" / "agent-canon"
    source = rust_root / "src" / "main.rs"
    source.parent.mkdir(parents=True)
    manifest = rust_root / "Cargo.toml"
    manifest.write_text(
        '[package]\nname = "agent-canon-wrapper-fixture"\nversion = "0.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    source.write_text("fn main() {}\n", encoding="utf-8")

    tools_home = tmp_path / "tools-home"
    installed_binary = tools_home / "agent-canon" / "bin" / "agent-canon"
    installed_binary.parent.mkdir(parents=True)
    # A stale installed candidate shadows any host /opt binary and must be bypassed.
    installed_binary.write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
    installed_binary.chmod(0o755)

    stale_mtime_ns = 1_000_000_000
    source_mtime_ns = stale_mtime_ns + 1_000_000_000
    os.utime(installed_binary, ns=(stale_mtime_ns, stale_mtime_ns))
    for source_path in (manifest, source):
        os.utime(source_path, ns=(source_mtime_ns, source_mtime_ns))

    return wrapper, tools_home


def _run_with_fake_cargo(
    tmp_path: Path, *, cargo_target_dir: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    wrapper, tools_home = _prepare_canon_layout(tmp_path)
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
    env["AGENT_CANON_TOOLS_HOME"] = str(tools_home)
    env["WRAPPER_CAPTURE"] = str(capture)
    if cargo_target_dir is None:
        env.pop("CARGO_TARGET_DIR", None)
    else:
        env["CARGO_TARGET_DIR"] = str(cargo_target_dir)

    result = subprocess.run(
        [str(wrapper), "--version"],
        cwd=wrapper.parents[2],
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
