# @dependency-start
# contract test
# responsibility Tests native Lake delegation, probe safety, dry runs, and unchanged Lean failure statuses.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/lean_proof_env.rs owns the proof-environment CLI
# @dependency-end
"""Native CLI process-boundary regressions; real Lean checks run separately."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
TOOLCHAIN = "leanprover/lean4:v4.30.0"
MATHLIB_REVISION = "resolved-mathlib-revision"
SELECTOR = "lean-proof-env"


def install_fake_lake(tmp_path: Path) -> dict[str, str]:
    """Install an external Lake provider fixture and return its process environment."""
    bin_dir = tmp_path / "provider-bin"
    bin_dir.mkdir()
    call_log = tmp_path / "lake-calls.jsonl"
    executable = bin_dir / "lake"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import signal
import sys
from pathlib import Path

command = sys.argv[1:]
log_path = Path(os.environ["LAKE_CALL_LOG"])
with log_path.open("a+", encoding="utf-8") as stream:
    stream.seek(0)
    call_number = sum(1 for _ in stream) + 1
    stream.seek(0, 2)
    stream.write(json.dumps(command) + chr(10))
returncode = int(os.environ.get("LAKE_RETURN_CODE", "0"))
if int(os.environ.get("LAKE_FAIL_AT", "-1")) == call_number:
    returncode = 17

if returncode == 0 and len(command) >= 2 and command[1] == "init":
    root = Path.cwd()
    (root / "lakefile.toml").write_text("native Lake package" + chr(10), encoding="utf-8")
    (root / "lean-toolchain").write_text(command[0][1:] + chr(10), encoding="utf-8")
    (root / "lake-manifest.json").write_text(
        json.dumps({"packages": [{"name": "mathlib", "rev": os.environ["LAKE_MATHLIB_REVISION"]}]}) + chr(10),
        encoding="utf-8",
    )

if "LAKE_OUTPUT_OVERRIDE" in os.environ:
    stdout = os.environ["LAKE_OUTPUT_OVERRIDE"]
elif command[-3:] == ["env", "lean", "--version"]:
    stdout = "Lean " + command[0][1:] + chr(10)
elif command[-1:] == ["--version"]:
    stdout = "Lake " + command[0][1:] + chr(10)
else:
    stdout = "Found a counter-example!" + chr(10)
stderr = os.environ.get("LAKE_STDERR", "native diagnostic" + chr(10))
sys.stdout.write(stdout)
sys.stdout.flush()
sys.stderr.write(stderr)
sys.stderr.flush()
if returncode == -9:
    os.kill(os.getpid(), signal.SIGKILL)
sys.exit(returncode)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return {
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        "LAKE_CALL_LOG": str(call_log),
        "LAKE_MATHLIB_REVISION": MATHLIB_REVISION,
    }


def provider_calls(provider: dict[str, str]) -> list[tuple[str, ...]]:
    path = Path(provider["LAKE_CALL_LOG"])
    if not path.exists():
        return []
    return [tuple(json.loads(line)) for line in path.read_text().splitlines()]


def run_cli(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    if not AGENT_CANON_CLI:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    executable = Path(AGENT_CANON_CLI)
    if not executable.is_absolute() or not executable.is_file():
        raise RuntimeError("AGENT_CANON_CLI must name the selected native executable")
    return subprocess.run(
        [AGENT_CANON_CLI, SELECTOR, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
        env={**os.environ, **(env or {})},
    )


def arguments(
    root: Path,
    action: str = "all-smoke",
    *,
    execute: bool = True,
    toolchain: str | None = None,
) -> list[str]:
    argv = [action, "--env-dir", str(root), "--format", "json"]
    if toolchain:
        argv.extend(("--lean-toolchain", toolchain))
    if execute:
        argv.append("--execute")
    return argv


def result_payload(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.stdout, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    "action", ("init", "smoke", "agent-smoke", "counterexample-smoke", "all-smoke")
)
def test_dry_run_neither_initializes_nor_writes_probes(
    tmp_path: Path, action: str
) -> None:
    root = tmp_path / "absent"
    provider = install_fake_lake(tmp_path)
    completed = run_cli(
        *arguments(root, action, execute=False, toolchain=TOOLCHAIN), env=provider
    )
    result = result_payload(completed)
    assert completed.returncode == 0
    assert result["status"] == "dry_run"
    assert result["executed"] is False
    assert not root.exists()
    assert result["created_or_updated_files"] == []
    assert result["command_results"] == []
    assert not provider_calls(provider)
    assert result["lean_toolchain"] is None
    assert result["commands"][0] == (
        f"lake +{TOOLCHAIN} init agent_canon_lean_proof_env math"
    )


@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_empty_package_is_created_by_native_lake_only(tmp_path: Path) -> None:
    root = tmp_path / "new"
    provider = install_fake_lake(tmp_path)
    completed = run_cli(*arguments(root, toolchain=TOOLCHAIN), env=provider)
    result = result_payload(completed)
    calls = provider_calls(provider)
    assert completed.returncode == 0
    assert result["status"] == "checked"
    assert calls[0] == (
        f"+{TOOLCHAIN}",
        "init",
        "agent_canon_lean_proof_env",
        "math",
    )
    # Only the external Lake provider fixture creates the standard package files.
    assert (root / "lakefile.toml").read_text() == "native Lake package\n"
    assert (root / "lean-toolchain").read_text() == f"{TOOLCHAIN}\n"
    assert not (root / "AgentCanonLeanProofEnv.lean").exists()
    assert len(result["created_or_updated_files"]) == 3
    assert all(Path(path).is_file() for path in result["created_or_updated_files"])
    assert result["lean_toolchain"] == TOOLCHAIN
    assert result["lake_version"] == f"Lake {TOOLCHAIN}"
    assert result["lean_version"] == f"Lean {TOOLCHAIN}"
    assert result["lake_manifest"] == str(root / "lake-manifest.json")
    assert result["mathlib_revision"] == MATHLIB_REVISION
    assert set(result) == {
        "action",
        "status",
        "env_dir",
        "created_or_updated_files",
        "commands",
        "executed",
        "command_results",
        "lean_file",
        "lean_toolchain",
        "lake_version",
        "lean_version",
        "lake_manifest",
        "mathlib_revision",
    }
    text_result = run_cli("init", "--env-dir", str(root), "--lean-toolchain", TOOLCHAIN)
    assert text_result.returncode == 0
    assert f"LEAN_PROOF_ENV_TOOLCHAIN={TOOLCHAIN}" in text_result.stdout


@pytest.mark.parametrize("config_name", ("lakefile.lean", "lakefile.toml"))
@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_existing_package_configuration_is_not_rewritten(
    tmp_path: Path, config_name: str
) -> None:
    files = {
        config_name: b"project-owned dependency declaration\n",
        "lean-toolchain": b"project-selected-toolchain\n",
        "lake-manifest.json": (
            '{"packages":[{"name":"mathlib","rev":"' + MATHLIB_REVISION + '"}]}\n'
        ).encode(),
    }
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    provider = install_fake_lake(tmp_path)
    completed = run_cli(
        *arguments(tmp_path, "smoke"),
        env=provider,
    )
    result = result_payload(completed)
    calls = provider_calls(provider)
    assert completed.returncode == 0
    assert all("init" not in call and "update" not in call for call in calls)
    assert (
        "+project-selected-toolchain",
        "--keep-toolchain",
        "build",
    ) in calls
    assert {name: (tmp_path / name).read_bytes() for name in files} == files
    assert result["lean_toolchain"] == "project-selected-toolchain"
    assert result["lake_version"] == "Lake project-selected-toolchain"
    assert result["lean_version"] == "Lean project-selected-toolchain"
    assert result["lake_manifest"] == str(tmp_path / "lake-manifest.json")
    assert result["mathlib_revision"] == MATHLIB_REVISION


@pytest.mark.parametrize("fail_at", (1, 2, 3, 4, 5, 6, 7))
@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_native_failure_stops_subsequent_commands(tmp_path: Path, fail_at: int) -> None:
    root = tmp_path / "new"
    provider = install_fake_lake(tmp_path)
    provider["LAKE_FAIL_AT"] = str(fail_at)
    completed = run_cli(*arguments(root, toolchain=TOOLCHAIN), env=provider)
    result = result_payload(completed)
    calls = provider_calls(provider)
    assert completed.returncode == 17
    assert result["status"] == "failed"
    assert len(calls) == fail_at
    assert result["command_results"][-1]["returncode"] == 17
    assert result["command_results"][-1]["stderr"] == "native diagnostic\n"
    assert len(result["created_or_updated_files"]) == max(0, fail_at - 4)


@pytest.mark.parametrize(
    "returncode", (0, 1, 17, -9) if os.name == "posix" else (0, 1, 17)
)
@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_counterexample_text_cannot_change_native_status(
    tmp_path: Path, returncode: int
) -> None:
    root = tmp_path / "package"
    root.mkdir()
    (root / "lakefile.toml").write_text("project-owned\n", encoding="utf-8")
    (root / "lean-toolchain").write_text(
        "project-selected-toolchain\n", encoding="utf-8"
    )
    provider = install_fake_lake(tmp_path)
    provider["LAKE_RETURN_CODE"] = str(returncode)
    provider["LAKE_OUTPUT_OVERRIDE"] = "Found a counter-example!\n"
    provider["LAKE_STDERR"] = "unrelated type error\n"
    completed = run_cli(
        *arguments(root, "check-file", execute=True),
        "--lean-file",
        str(tmp_path / "probe.lean"),
        env=provider,
    )
    result = result_payload(completed)
    native_code = result["command_results"][0]["returncode"]
    assert native_code == returncode
    assert result["command_results"][0]["stderr"] == "unrelated type error\n"
    assert result["status"] == ("failed" if returncode else "checked")


@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_cli_propagates_native_nonzero(tmp_path: Path) -> None:
    root = tmp_path / "new"
    provider = install_fake_lake(tmp_path)
    provider["LAKE_FAIL_AT"] = "1"
    completed = run_cli(*arguments(root, "init", toolchain=TOOLCHAIN), env=provider)
    assert completed.returncode == 17


def test_native_execution_failure_is_not_success(tmp_path: Path) -> None:
    root = tmp_path / "new"
    empty_path = tmp_path / "empty-bin"
    empty_path.mkdir()
    completed = run_cli(
        *arguments(root, "init", toolchain=TOOLCHAIN),
        env={"PATH": str(empty_path)},
    )
    assert completed.returncode == 2
    assert "LEAN_PROOF_ENV_ERROR=" in completed.stderr
    assert "lake" in completed.stderr


def test_foreign_directory_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "env"
    root.mkdir()
    source = root / "user.lean"
    source.write_text("user-owned\n", encoding="utf-8")
    provider = install_fake_lake(tmp_path)
    completed = run_cli(*arguments(root), env=provider)
    assert completed.returncode == 2
    assert (
        "empty directory, a toolchain-only directory, or an existing Lake package"
        in completed.stderr
    )
    assert not provider_calls(provider)
    assert source.read_text(encoding="utf-8") == "user-owned\n"


@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_external_file_path_is_a_single_native_argument(tmp_path: Path) -> None:
    (tmp_path / "lakefile.toml").write_text("project-owned\n", encoding="utf-8")
    (tmp_path / "lean-toolchain").write_text(
        "project-selected-toolchain\n", encoding="utf-8"
    )
    target = tmp_path / "proof with spaces.lean"
    target.write_text("example : True := by trivial\n", encoding="utf-8")
    provider = install_fake_lake(tmp_path)
    completed = run_cli(
        *arguments(tmp_path, "check-file"),
        "--lean-toolchain",
        "project-selected-toolchain",
        "--lean-file",
        str(target),
        env=provider,
    )
    result = result_payload(completed)
    calls = provider_calls(provider)
    assert completed.returncode == 0
    assert calls[-1] == (
        "+project-selected-toolchain",
        "--keep-toolchain",
        "env",
        "lean",
        str(target.resolve()),
    )
    assert result["created_or_updated_files"] == []


def test_missing_check_file_argument_fails_before_writing(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    completed = run_cli(*arguments(root, "check-file"))
    assert completed.returncode == 2
    assert "--lean-file is required" in completed.stderr
    assert not root.exists()


def test_new_package_requires_an_explicit_selected_toolchain(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    provider = install_fake_lake(tmp_path)
    completed = run_cli(*arguments(root, "init", execute=False), env=provider)
    assert completed.returncode == 2
    assert "Select an exact Lean toolchain" in completed.stderr
    assert not root.exists()
    assert not provider_calls(provider)


@pytest.mark.skipif(
    os.name == "nt", reason="fake Lake provider uses a POSIX executable"
)
def test_toolchain_only_directory_uses_native_lake_init(tmp_path: Path) -> None:
    root = tmp_path / "env"
    root.mkdir()
    (root / "lean-toolchain").write_text(f"{TOOLCHAIN}\n", encoding="utf-8")
    provider = install_fake_lake(tmp_path)
    completed = run_cli(*arguments(root, "init"), env=provider)
    result = result_payload(completed)
    calls = provider_calls(provider)
    assert completed.returncode == 0
    assert calls[0] == (
        f"+{TOOLCHAIN}",
        "init",
        "agent_canon_lean_proof_env",
        "math",
    )
    assert (root / "lean-toolchain").read_text() == f"{TOOLCHAIN}\n"
    assert result["lean_toolchain"] == TOOLCHAIN
    assert result["mathlib_revision"] == MATHLIB_REVISION


def test_explicit_toolchain_cannot_replace_a_project_declaration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package"
    root.mkdir()
    toolchain = root / "lean-toolchain"
    toolchain.write_text("project-selected-toolchain\n", encoding="utf-8")
    provider = install_fake_lake(tmp_path)
    completed = run_cli(
        *arguments(root, "init", toolchain="different-toolchain"),
        env=provider,
    )
    assert completed.returncode == 2
    assert "does not match the project declaration" in completed.stderr
    assert not provider_calls(provider)
    assert toolchain.read_text() == "project-selected-toolchain\n"
