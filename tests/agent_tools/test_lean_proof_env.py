# @dependency-start
# contract test
# responsibility Tests native Lake delegation, probe safety, dry runs, and unchanged Lean failure statuses.
# upstream implementation ../../tools/analysis/proof/lean_proof_env.py owns the proof-environment CLI
# @dependency-end
"""Focused process-boundary regressions; native Lean checks are separate."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.analysis.proof import lean_proof_env as proof_env


def arguments(root: Path, action: str = "all-smoke", *, execute: bool = True):
    argv = [action, "--env-dir", str(root)]
    if execute:
        argv.append("--execute")
    return proof_env.build_parser().parse_args(argv)


def native_results(monkeypatch: pytest.MonkeyPatch, *, fail_at: int = -1):
    calls: list[tuple[str, ...]] = []

    def run(parts, **kwargs):
        calls.append(tuple(parts))
        return subprocess.CompletedProcess(
            parts, 17 if len(calls) == fail_at else 0,
            stdout="Found a counter-example!\n", stderr="native diagnostic\n",
        )

    monkeypatch.setattr(proof_env.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("action", ("init", "smoke", "agent-smoke", "counterexample-smoke", "all-smoke"))
def test_dry_run_neither_initializes_nor_writes_probes(tmp_path: Path, monkeypatch, action: str):
    root = tmp_path / "absent"
    calls = native_results(monkeypatch)
    result = proof_env.build_result(arguments(root, action, execute=False))
    assert result.status == "dry_run"
    assert not result.executed
    assert not root.exists()
    assert result.created_or_updated_files == ()
    assert result.command_results == ()
    assert not calls
    assert result.commands[0] == "lake init agent_canon_lean_proof_env math"


def test_empty_package_is_created_by_native_lake_only(tmp_path: Path, monkeypatch):
    root = tmp_path / "new"
    calls = native_results(monkeypatch)
    result = proof_env.build_result(arguments(root))
    assert result.status == "checked"
    assert calls[0] == ("lake", "init", "agent_canon_lean_proof_env", "math")
    # The process fake creates no package files: Python must not fabricate them.
    assert not (root / "lakefile.lean").exists()
    assert not (root / "lakefile.toml").exists()
    assert not (root / "lean-toolchain").exists()
    assert not (root / "AgentCanonLeanProofEnv.lean").exists()
    assert len(result.created_or_updated_files) == 3
    assert all(Path(path).is_file() for path in result.created_or_updated_files)
    assert result.lean_toolchain is None
    assert result.lake_manifest is None


@pytest.mark.parametrize("config_name", ("lakefile.lean", "lakefile.toml"))
def test_existing_package_configuration_is_not_rewritten(tmp_path: Path, monkeypatch, config_name: str):
    files = {
        config_name: b"project-owned dependency declaration\n",
        "lean-toolchain": b"project-selected-toolchain\n",
        "lake-manifest.json": b'{"packages": []}\n',
    }
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    calls = native_results(monkeypatch)
    result = proof_env.build_result(arguments(tmp_path, "smoke"))
    assert all("init" not in call and "update" not in call for call in calls)
    assert ("lake", "--keep-toolchain", "build") in calls
    assert {name: (tmp_path / name).read_bytes() for name in files} == files
    assert result.lean_toolchain == "project-selected-toolchain"
    assert result.lake_manifest == str(tmp_path / "lake-manifest.json")


@pytest.mark.parametrize("fail_at", (1, 2, 3, 4, 5, 6, 7))
def test_native_failure_stops_subsequent_commands(tmp_path: Path, monkeypatch, fail_at: int):
    calls = native_results(monkeypatch, fail_at=fail_at)
    result = proof_env.build_result(arguments(tmp_path))
    assert result.status == "failed"
    assert len(calls) == fail_at
    assert result.command_results[-1].returncode == 17
    assert result.command_results[-1].stderr == "native diagnostic\n"
    assert len(result.created_or_updated_files) == max(0, fail_at - 4)


@pytest.mark.parametrize("returncode", (0, 1, 17, -9))
def test_counterexample_text_cannot_change_native_status(tmp_path: Path, monkeypatch, returncode: int):
    def run(parts, **kwargs):
        return subprocess.CompletedProcess(
            parts, returncode,
            stdout="Found a counter-example!\n", stderr="unrelated type error\n",
        )

    monkeypatch.setattr(proof_env.subprocess, "run", run)
    result = proof_env.run_command(("lake", "env", "lean", "probe.lean"), tmp_path)
    assert result.returncode == returncode
    assert result.stderr == "unrelated type error\n"


def test_cli_propagates_native_nonzero(tmp_path: Path, monkeypatch):
    native_results(monkeypatch, fail_at=1)
    assert proof_env.main(["init", "--env-dir", str(tmp_path), "--execute"]) == 17


def test_native_execution_failure_is_not_success(tmp_path: Path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("lake is unavailable")

    monkeypatch.setattr(proof_env.subprocess, "run", missing)
    assert proof_env.main(["init", "--env-dir", str(tmp_path), "--execute"]) == 2


def test_foreign_directory_is_preserved(tmp_path: Path, monkeypatch):
    source = tmp_path / "user.lean"
    source.write_text("user-owned\n", encoding="utf-8")
    calls = native_results(monkeypatch)
    with pytest.raises(ValueError, match="empty directory or an existing Lake package"):
        proof_env.build_result(arguments(tmp_path))
    assert not calls
    assert source.read_text(encoding="utf-8") == "user-owned\n"


def test_different_probe_and_symlink_are_not_overwritten(tmp_path: Path):
    source = tmp_path / "probe.lean"
    source.write_text("user-owned\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-matching"):
        proof_env.write_generated(source, "replacement\n")
    link = tmp_path / "link.lean"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        proof_env.write_generated(link, "replacement\n")
    assert source.read_text(encoding="utf-8") == "user-owned\n"
    assert not proof_env.write_generated(source, "user-owned\n")


def test_expected_counterexample_is_checked_inside_lean():
    source = proof_env.counterexample_text()
    assert "/-- error: Found a counter-example! -/\n#guard_msgs in\n#eval" in source
    assert "forall (n : Nat), n < n" in source
    assert "quiet := true" in source
    assert "import Plausible" in source


def test_external_file_path_is_a_single_native_argument(tmp_path: Path, monkeypatch):
    (tmp_path / "lakefile.toml").write_text("project-owned\n", encoding="utf-8")
    target = tmp_path / "proof with spaces.lean"
    target.write_text("example : True := by trivial\n", encoding="utf-8")
    args = proof_env.build_parser().parse_args([
        "check-file", "--env-dir", str(tmp_path), "--lean-file", str(target), "--execute",
    ])
    calls = native_results(monkeypatch)
    result = proof_env.build_result(args)
    assert calls[-1] == ("lake", "--keep-toolchain", "env", "lean", str(target))
    assert result.created_or_updated_files == ()


def test_missing_check_file_argument_fails_before_writing(tmp_path: Path):
    root = tmp_path / "absent"
    with pytest.raises(ValueError, match="--lean-file is required"):
        proof_env.build_result(arguments(root, "check-file"))
    assert not root.exists()
