# @dependency-start
# contract test
# responsibility Tests stable AgentCanon shell wrapper runtime isolation.
# upstream design ../../documents/design/rust-agent-tool-migration.md Rust CLI runtime boundary.
# upstream implementation ../../tools/bin/agent-canon stable shell wrapper.
# @dependency-end

"""Tests for the stable AgentCanon shell wrapper."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from tools.agent_tools.fixture_spawn import bootstrap_fixture_public_environment
from tools.agent_tools.parent_root_side_effects import (
    ParentRootSideEffectError,
    current_supervisor_issuer,
    public_session,
    resolve_parent_side_effect_session_v2,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def _build_clean_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("CARGO_TARGET_DIR", None)
    if overrides:
        env.update(overrides)
    return env


@contextmanager
def _authenticated_parent_env(
    parent_root: Path,
    base_env: dict[str, str],
) -> Iterator[dict[str, str]]:
    """Run a wrapper synthetic tool through the canonical fixture facade."""
    wrapper = parent_root / "tools" / "bin" / "agent-canon"
    if not wrapper.is_file():
        wrapper = parent_root / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon"
    saved_environment = os.environ.copy()
    previous_cwd = Path.cwd()
    try:
        os.environ.clear()
        os.environ.update(base_env)
        if base_env.get(SIDE_EFFECT_HANDOFF_ENV) and base_env.get(SIDE_EFFECT_PARENT_ROOT_ENV):
            with bootstrap_fixture_public_environment(
                mode="synthetic_tool",
                fixture_cwd=parent_root,
                base_env=base_env,
                invocation_script=wrapper,
            ) as fixture:
                yield fixture.environment
            return

        os.chdir(parent_root)
        with public_session(
            invocation_script=wrapper,
            purpose="wrapper-test-supervisor",
            independent=True,
            cleanup_state=True,
        ):
            issuer = current_supervisor_issuer()
            assert issuer is not None
            child = issuer.issue_child(
                role="record",
                record_id=f"wrapper-record-{time.monotonic_ns()}",
                physical_root=parent_root,
                now_mono_ns=time.monotonic_ns(),
            )
            child_environment = {
                SIDE_EFFECT_PARENT_ROOT_ENV: child.record.parent_root_realpath,
                SIDE_EFFECT_HANDOFF_ENV: child.handoff,
                SIDE_EFFECT_REQUIRED_ENV: "1",
            }
            record = resolve_parent_side_effect_session_v2(
                env=child_environment,
                observed_cwd=parent_root,
            )
            try:
                with bootstrap_fixture_public_environment(
                    mode="synthetic_tool",
                    fixture_cwd=parent_root,
                    record=record,
                    base_env=base_env,
                    invocation_script=wrapper,
                ) as fixture:
                    yield fixture.environment
            finally:
                record.close()
                issuer.revoke_drain_child(
                    child=child.child,
                    reason="normal_exit",
                    now_mono_ns=time.monotonic_ns(),
                )
    finally:
        os.environ.clear()
        os.environ.update(saved_environment)
        os.chdir(previous_cwd)


def _pending_handoff_nonces(root: Path) -> dict[str, object]:
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _prepare_canon_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    canon_root = tmp_path / "canon"
    wrapper = canon_root / "tools" / "bin" / "agent-canon"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(WRAPPER, wrapper)

    tools_home = canon_root / ".agent-canon" / "tools"

    rust_root = canon_root / "rust" / "agent-canon"
    source = rust_root / "src" / "main.rs"
    source.parent.mkdir(parents=True)
    manifest = rust_root / "Cargo.toml"
    manifest.write_text(
        '[package]\nname = "agent-canon-wrapper-fixture"\nversion = "0.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    source.write_text("fn main() {}\n", encoding="utf-8")

    installed_binary = tools_home / "agent-canon" / "bin" / "agent-canon"
    installed_binary.parent.mkdir(parents=True)
    # A stale installed candidate shadows any host /opt binary and must be bypassed.
    installed_binary.write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
    installed_binary.chmod(0o755)

    # Keep the copied wrapper functional by mirroring the parent boundary
    # shim into the synthetic repository root.
    boundary_source = WRAPPER.parents[2] / "tools" / "agent_tools" / "parent_root_side_effects.py"
    boundary_target = canon_root / "tools" / "agent_tools"
    boundary_target.mkdir(parents=True)
    shutil.copy2(boundary_source, boundary_target / "parent_root_side_effects.py")
    shutil.copy2(
        WRAPPER.parents[2] / "tools" / "agent_tools" / "agent_canon_source_root.py",
        boundary_target / "agent_canon_source_root.py",
    )
    catalog = canon_root / "agents" / "skills" / "catalog.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("skills: []\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(canon_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(canon_root),
            "remote",
            "add",
            "origin",
            "https://example.invalid/agent-canon.git",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(canon_root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )

    stale_mtime_ns = 1_000_000_000
    source_mtime_ns = stale_mtime_ns + 1_000_000_000
    os.utime(installed_binary, ns=(stale_mtime_ns, stale_mtime_ns))
    for source_path in (manifest, source):
        os.utime(source_path, ns=(source_mtime_ns, source_mtime_ns))

    return wrapper, tools_home, canon_root


def _prepare_nested_vendor_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Prepare vendor layout and return wrapper, tools home, and outer root."""
    outer_root = tmp_path / "outer"
    wrapper = outer_root / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(WRAPPER, wrapper)

    canon_root = outer_root / "vendor" / "agent-canon"
    tools_home = outer_root / ".agent-canon" / "tools"

    rust_root = canon_root / "rust" / "agent-canon"
    source = rust_root / "src" / "main.rs"
    source.parent.mkdir(parents=True)
    manifest = rust_root / "Cargo.toml"
    manifest.write_text(
        '[package]\nname = "agent-canon-wrapper-fixture"\nversion = "0.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    source.write_text("fn main() {}\n", encoding="utf-8")

    installed_binary = tools_home / "agent-canon" / "bin" / "agent-canon"
    installed_binary.parent.mkdir(parents=True)
    installed_binary.write_text("#!/bin/sh\nexit 86\n", encoding="utf-8")
    installed_binary.chmod(0o755)

    boundary_source = WRAPPER.parents[2] / "tools" / "agent_tools" / "parent_root_side_effects.py"
    boundary_target = canon_root / "tools" / "agent_tools"
    boundary_target.mkdir(parents=True)
    shutil.copy2(boundary_source, boundary_target / "parent_root_side_effects.py")
    shutil.copy2(
        WRAPPER.parents[2] / "tools" / "agent_tools" / "agent_canon_source_root.py",
        boundary_target / "agent_canon_source_root.py",
    )
    catalog = canon_root / "agents" / "skills" / "catalog.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("skills: []\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(outer_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(canon_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(canon_root),
            "add",
            ".",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(canon_root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "source fixture",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(canon_root),
            "remote",
            "add",
            "origin",
            "https://example.invalid/agent-canon.git",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(outer_root),
            "remote",
            "add",
            "origin",
            "https://example.invalid/outer-agent-canon.git",
        ],
        check=True,
    )
    (outer_root / ".gitmodules").write_text(
        """[submodule "vendor/agent-canon"]
  path = vendor/agent-canon
  url = https://example.invalid/agent-canon.git
""",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(outer_root),
            "add",
            ".gitmodules",
            "vendor/agent-canon",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(outer_root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )

    stale_mtime_ns = 1_000_000_000
    source_mtime_ns = stale_mtime_ns + 1_000_000_000
    os.utime(installed_binary, ns=(stale_mtime_ns, stale_mtime_ns))
    for source_path in (manifest, source):
        os.utime(source_path, ns=(source_mtime_ns, source_mtime_ns))

    return wrapper, tools_home, outer_root


def _run_with_fake_cargo(
    tmp_path: Path, *, cargo_target_dir: Path | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    wrapper, _tools_home, canon_root = _prepare_canon_layout(tmp_path)
    capture = canon_root / "cargo-target.txt"
    for source_path in ((wrapper.parents[2] / "rust" / "agent-canon" / "Cargo.toml"), (wrapper.parents[2] / "rust" / "agent-canon" / "src" / "main.rs")):
        os.utime(source_path, ns=(1_000_000_000, 1_000_000_000))

    base_env = _build_clean_env(
        {
            "WRAPPER_CAPTURE": str(capture),
        }
    )
    if cargo_target_dir is None:
        base_env.pop("CARGO_TARGET_DIR", None)
    else:
        base_env["CARGO_TARGET_DIR"] = str(cargo_target_dir)

    with _authenticated_parent_env(canon_root, base_env) as env:
        installed_binary = Path(env["AGENT_CANON_TOOLS_HOME"]) / "agent-canon" / "bin" / "agent-canon"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text(
            '#!/bin/sh\n'
            'printf \'%s\\n\' "${CARGO_TARGET_DIR-}" > "$WRAPPER_CAPTURE"\n',
            encoding="utf-8",
        )
        installed_binary.chmod(0o755)
        os.utime(installed_binary, ns=(3_000_000_000, 3_000_000_000))
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=wrapper.parents[2],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    return result, capture


def _run_with_fake_installed(
    tmp_path: Path,
    *,
    preserve_home: Path | None = None,
    exit_code: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    wrapper, _tools_home, canon_root = _prepare_canon_layout(tmp_path)
    capture = canon_root / "installed-target.txt"
    # Make installed binary preferred over cargo by being fresh and source older.
    mtime = 2_000_000_000
    source_mtime_ns = mtime - 1_000
    source = wrapper.parents[2] / "rust" / "agent-canon" / "src" / "main.rs"
    os.utime(source, ns=(source_mtime_ns, source_mtime_ns))
    manifest = wrapper.parents[2] / "rust" / "agent-canon" / "Cargo.toml"
    os.utime(manifest, ns=(source_mtime_ns, source_mtime_ns))

    env = _build_clean_env(
        {
            "WRAPPER_CAPTURE": str(capture),
        }
    )
    if preserve_home is not None:
        env["HOME"] = str(preserve_home)

    with _authenticated_parent_env(canon_root, env) as env:
        installed_binary = Path(env["AGENT_CANON_TOOLS_HOME"]) / "agent-canon" / "bin" / "agent-canon"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text(
            '#!/bin/sh\n'
            f'printf \'home=%s\\n\' "$HOME" >> "{capture}"\n'
            f'printf \'tmpdir=%s\\n\' "$TMPDIR" >> "{capture}"\n'
            f'printf \'target=%s\\n\' "${{CARGO_TARGET_DIR-}}" >> "{capture}"\n'
            f'printf \'cli=%s\\n\' "${{AGENT_CANON_CLI_TARGET_DIR-}}" >> "{capture}"\n'
            f'printf \'handoff=%s\\n\' "${{AGENT_CANON_CHILD_HANDOFF-}}" >> "{capture}"\n'
            f'printf \'purpose=%s\\n\' "${{AGENT_CANON_CHILD_PURPOSE-}}" >> "{capture}"\n'
            f'exit {exit_code}\n',
            encoding="utf-8",
        )
        installed_binary.chmod(0o755)
        os.utime(installed_binary, ns=(mtime, mtime))
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=wrapper.parents[2],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    return result, capture


def test_wrapper_uses_active_repository_root_for_parent_bound_paths(
    tmp_path: Path,
) -> None:
    """Parent-bound paths must follow the active repository root in vendor layout."""
    wrapper, _tools_home, outer_root = _prepare_nested_vendor_layout(tmp_path)
    capture = outer_root / "nested-installed-target.txt"

    mtime = 2_000_000_000
    source_root = wrapper.parents[2] / "rust" / "agent-canon" / "src" / "main.rs"
    manifest = wrapper.parents[2] / "rust" / "agent-canon" / "Cargo.toml"
    source_time = mtime - 1_000
    os.utime(source_root, ns=(source_time, source_time))
    os.utime(manifest, ns=(source_time, source_time))

    with _authenticated_parent_env(
        outer_root,
        _build_clean_env({"WRAPPER_CAPTURE": str(capture)}),
    ) as env:
        installed_binary = Path(env["AGENT_CANON_TOOLS_HOME"]) / "agent-canon" / "bin" / "agent-canon"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text(
            '#!/bin/sh\n'
            f'printf \'tmpdir=%s\\n\' "$TMPDIR" >> "{capture}"\n'
            f'printf \'target=%s\\n\' "${{CARGO_TARGET_DIR-}}" >> "{capture}"\n'
            f'printf \'cli=%s\\n\' "${{AGENT_CANON_CLI_TARGET_DIR-}}" >> "{capture}"\n',
            encoding="utf-8",
        )
        installed_binary.chmod(0o755)
        os.utime(installed_binary, ns=(mtime, mtime))
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=outer_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    lines = dict(line.split("=", 1) for line in capture.read_text(encoding="utf-8").splitlines())
    assert Path(lines["tmpdir"]).resolve().is_relative_to((outer_root / ".agent-canon").resolve())
    assert Path(lines["target"]).resolve().is_relative_to((outer_root / ".agent-canon").resolve())
    assert lines["target"] == lines["cli"]


def test_wrapper_nested_scrubbed_env_selects_prebuilt_without_cargo(
    tmp_path: Path,
) -> None:
    """Nested source resolution selects the parent binary without Cargo fallback."""
    wrapper, _tools_home, outer_root = _prepare_nested_vendor_layout(tmp_path)
    canon_root = wrapper.parents[2]
    capture = tmp_path / "nested-prebuilt.txt"
    cargo_capture = tmp_path / "cargo-must-not-run.txt"
    binary_time = 3_000_000_000
    source_time = binary_time - 1_000
    for source_path in (
        canon_root / "rust" / "agent-canon" / "Cargo.toml",
        canon_root / "rust" / "agent-canon" / "src" / "main.rs",
    ):
        os.utime(source_path, ns=(source_time, source_time))
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_cargo = fake_bin / "cargo"
    fake_cargo.write_text(
        f'#!/bin/sh\nprintf reached > "{cargo_capture}"\nexit 41\n',
        encoding="utf-8",
    )
    fake_cargo.chmod(0o755)
    with _authenticated_parent_env(
        outer_root,
        _build_clean_env(
            {
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            }
        ),
    ) as env:
        installed_binary = Path(env["AGENT_CANON_TOOLS_HOME"]) / "agent-canon" / "bin" / "agent-canon"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text(
            f'#!/bin/sh\nprintf reached > "{capture}"\nexit 37\n',
            encoding="utf-8",
        )
        installed_binary.chmod(0o755)
        os.utime(installed_binary, ns=(binary_time, binary_time))
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=canon_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 37, result.stderr
    assert capture.is_file()
    assert not cargo_capture.exists()
    assert "AGENT_CANON_PARENT_ROOT" not in env
    assert outer_root.joinpath(".agent-canon").is_dir()


def test_wrapper_isolates_source_fallback_from_repository_target(
    tmp_path: Path,
) -> None:
    """The default source fallback should build in the parent-owned tools cache."""
    result, capture = _run_with_fake_cargo(tmp_path)

    assert result.returncode == 0, result.stderr
    target = Path(capture.read_text(encoding="utf-8").strip())
    assert target.is_relative_to((tmp_path / "canon").resolve())
    assert target.name == "cargo-target"


def test_wrapper_preserves_explicit_cargo_target_dir(tmp_path: Path) -> None:
    """Callers should retain authority over an explicit Cargo target directory."""
    explicit_target = tmp_path / "canon" / "explicit-target"
    result, capture = _run_with_fake_cargo(tmp_path, cargo_target_dir=explicit_target)

    assert result.returncode == 0, result.stderr
    assert capture.read_text(encoding="utf-8").strip() == str(explicit_target)


def test_wrapper_rejects_explicit_external_cargo_target_before_side_effects(tmp_path: Path) -> None:
    """The wrapper rejects a physically external Cargo target before writes."""
    wrapper, _tools_home, canon_root = _prepare_canon_layout(tmp_path)
    capture = canon_root / "cargo-target.txt"
    external_target = tmp_path.parent / "external-cargo-target"
    env = _build_clean_env({"WRAPPER_CAPTURE": str(capture)})
    with _authenticated_parent_env(canon_root, env) as child_environment:
        child_environment = dict(child_environment)
        fake_cargo = Path(child_environment["AGENT_CANON_TOOLS_HOME"]) / "cargo"
        fake_cargo.write_text(
            f'#!/bin/sh\nprintf reached > "{capture}"\nexit 0\n',
            encoding="utf-8",
        )
        fake_cargo.chmod(0o755)
        child_environment["CARGO_TARGET_DIR"] = str(external_target)
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=canon_root,
            env=child_environment,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode != 0
    assert "outside parent root" in result.stderr
    assert not capture.exists()
    assert not external_target.exists()


def test_wrapper_installed_binary_receives_parent_local_paths_and_keeps_home(
    tmp_path: Path,
) -> None:
    out_home = tmp_path / "outside-home"
    out_home.mkdir()
    result, capture = _run_with_fake_installed(tmp_path, preserve_home=out_home)

    assert result.returncode == 0, result.stderr
    lines = dict(line.split("=", 1) for line in capture.read_text(encoding="utf-8").splitlines())
    assert lines["home"] != str(out_home)
    assert Path(lines["home"]).resolve().is_relative_to((tmp_path / "canon").resolve())
    assert Path(lines["tmpdir"]).resolve().is_relative_to((tmp_path / "canon").resolve())
    assert Path(lines["target"]).resolve().is_relative_to((tmp_path / "canon").resolve())
    assert lines["cli"] == lines["target"]
    assert lines["handoff"] == ""
    assert lines["purpose"] == ""
    assert _pending_handoff_nonces(tmp_path / "canon") == {}


def test_wrapper_preserves_selected_installed_binary_exit_code(tmp_path: Path) -> None:
    """A selected installed runtime failure is not converted into fallback success."""
    result, capture = _run_with_fake_installed(tmp_path, exit_code=37)

    assert result.returncode == 37
    assert capture.is_file()


def test_wrapper_preserves_selected_cargo_exit_code_without_installed_fallback(
    tmp_path: Path,
) -> None:
    """A selected Cargo runtime failure does not fall through to an installed binary."""
    wrapper, _tools_home, canon_root = _prepare_canon_layout(tmp_path)
    # Keep the installed candidate stale so Cargo is the selected runtime.
    source_time = 3_000_000_000
    os.utime(
        canon_root / "rust" / "agent-canon" / "Cargo.toml",
        ns=(source_time, source_time),
    )
    os.utime(
        canon_root / "rust" / "agent-canon" / "src" / "main.rs",
        ns=(source_time, source_time),
    )
    env = _build_clean_env(
        {
            "WRAPPER_CAPTURE": str(tmp_path / "cargo-failure.txt"),
        }
    )
    installed_capture = tmp_path / "installed-fallback.txt"

    with _authenticated_parent_env(canon_root, env) as env:
        fixture_tools = Path(env["AGENT_CANON_TOOLS_HOME"])
        fake_cargo = fixture_tools / "cargo"
        fake_cargo.write_text("#!/bin/sh\nexit 41\n", encoding="utf-8")
        fake_cargo.chmod(0o755)
        installed_binary = fixture_tools / "agent-canon" / "bin" / "agent-canon"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text(
            f'#!/bin/sh\nprintf reached > "{installed_capture}"\n',
            encoding="utf-8",
        )
        installed_binary.chmod(0o755)
        os.utime(installed_binary, ns=(1_000_000_000, 1_000_000_000))
        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=canon_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 41
    assert not installed_capture.exists()
