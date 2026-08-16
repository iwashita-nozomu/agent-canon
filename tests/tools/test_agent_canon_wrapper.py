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
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pytest
from tools.agent_tools.fixture_spawn import (
    bootstrap_fixture_public_environment,
    record_capability_from_environment,
    record_environment,
)
from tools.agent_tools.parent_root_side_effects import (
    ParentRootReject,
    ParentRootSideEffectError,
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
    *,
    explicit_path_entries: Sequence[str] = (),
    explicit_target_dir: Path | None = None,
) -> Iterator[dict[str, str]]:
    """Run a wrapper synthetic tool through one consumed runner capability."""
    wrapper = parent_root / "tools" / "bin" / "agent-canon"
    if not wrapper.is_file():
        wrapper = parent_root / "vendor" / "agent-canon" / "tools" / "bin" / "agent-canon"
    capability = record_capability_from_environment(
        observed_cwd=Path.cwd().resolve()
    )
    with bootstrap_fixture_public_environment(
        mode="synthetic_tool",
        fixture_cwd=parent_root,
        record_capability=capability,
        base_env=base_env,
        invocation_script=wrapper,
        explicit_path_entries=explicit_path_entries,
        explicit_target_dir=explicit_target_dir,
    ) as fixture:
        yield fixture.environment


def _pending_handoff_nonces(root: Path) -> dict[str, object]:
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_record_environment_uses_preissued_public_record() -> None:
    """The ordinary adapter consumes private transport and projects public setup."""
    if not (
        os.environ.get("AGENT_CANON_SIDE_EFFECT_PARENT_ROOT")
        and os.environ.get("AGENT_CANON_SIDE_EFFECT_HANDOFF")
        and os.environ.get("AGENT_CANON_PRIVATE_RECORD_REQUIRED") == "1"
    ):
        pytest.skip("requires a producer-preissued public/private record pair")
    from tools.agent_tools.parent_root_side_effects import (
        resolve_parent_side_effect_session_v2,
    )

    capability = record_capability_from_environment(observed_cwd=Path.cwd().resolve())
    public = resolve_parent_side_effect_session_v2(
        env=os.environ,
        observed_cwd=Path.cwd().resolve(),
    )
    try:
        with record_environment(cwd=Path.cwd()) as child:
            assert child.receipt.capability_record_id == capability.record_id
            assert child.receipt.capability_consumed_once
            assert child.receipt.capability_consumption_count == 1
            assert child.receipt.public_projection_record_id == public.record.record_id
            assert child.receipt.public_projection_record_id != capability.record_id
            assert child.receipt.private_transport_absent_in_child
            assert child["AGENT_CANON_SIDE_EFFECT_HANDOFF"] == public.handoff
            assert all(
                name not in child
                for name in (
                    "AGENT_CANON_PRIVATE_RECORD_PARENT_ROOT",
                    "AGENT_CANON_PRIVATE_RECORD_HANDOFF",
                    "AGENT_CANON_PRIVATE_RECORD_REQUIRED",
                )
            )
    finally:
        public.close()


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
    base_env.pop("CARGO_TARGET_DIR", None)

    with _authenticated_parent_env(
        canon_root, base_env, explicit_target_dir=cargo_target_dir
    ) as env:
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
    fake_bin = outer_root / "fake-bin"
    fake_bin.mkdir()
    fake_cargo = fake_bin / "cargo"
    fake_cargo.write_text(
        f'#!/bin/sh\nprintf reached > "{cargo_capture}"\nexit 41\n',
        encoding="utf-8",
    )
    fake_cargo.chmod(0o755)
    with _authenticated_parent_env(
        outer_root,
        _build_clean_env(),
        explicit_path_entries=(str(fake_bin),),
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
    _wrapper, _tools_home, canon_root = _prepare_canon_layout(tmp_path)
    capture = canon_root / "cargo-target.txt"
    external_target = tmp_path.parent / "external-cargo-target"
    env = _build_clean_env({"WRAPPER_CAPTURE": str(capture)})
    env.pop("CARGO_TARGET_DIR", None)
    with pytest.raises(ParentRootSideEffectError) as raised:
        with _authenticated_parent_env(
            canon_root, env, explicit_target_dir=external_target
        ):
            raise AssertionError("external target was admitted by fixture facade")

    assert raised.value.reject is ParentRootReject.ROOT_MISMATCH
    assert "TARGET_OUTSIDE_FIXTURE" in str(raised.value)
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
