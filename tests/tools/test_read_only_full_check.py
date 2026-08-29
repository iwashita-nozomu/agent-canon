"""Focused contract tests for the read-only full-check execution route."""

# @dependency-start
# contract test
# responsibility Verifies full checks are admitted only after a read-only target mount proof and reuse the existing full-check body without checkout mutation.
# upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh owns target admission and full-check dispatch
# upstream implementation ../../tools/validation/ci/runners/run_all_checks.sh owns the existing full-confidence check body
# @dependency-end

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "validation" / "ci" / "runners" / "run_standalone_static_gate_unit.sh"


def runner_text() -> str:
    """Read the canonical shared-runtime unit runner."""
    return RUNNER.read_text(encoding="utf-8")


def test_full_unit_is_guarded_by_read_only_mount_proof() -> None:
    """The full body cannot run before the deepest source mount proves `ro`."""
    text = runner_text()
    guard = text.split("assert_read_only_target() {", 1)[1].split(
        "\n}\n\nassert_read_only_target", 1
    )[0]

    assert "/proc/self/mountinfo" in guard
    assert 'if "ro" not in options' in guard
    assert "target_mount_not_read_only" in guard
    assert "\nassert_read_only_target\n" in text
    assert text.index("\nassert_read_only_target\n") < text.index("run_full()")


def test_full_unit_reuses_existing_body_and_forwards_options() -> None:
    """The adapter adds only an effect boundary; it does not duplicate checks."""
    text = runner_text()
    body = text.split("run_full() {", 1)[1].split("\n}\n\nrun_rust()", 1)[0]

    assert 'bash "${ROOT}/tools/validation/ci/runners/run_all_checks.sh" "${UNIT_ARGS[@]}"' in body
    assert (
        'AGENT_CANON_CONTROL_PARENT_ROOT="${control_parent_root}"' in body
    )
    assert "AGENT_CANON_CONTROL_PARENT_ROOT:?AGENT_CANON_CONTROL_PARENT_ROOT is required" in body
    assert 'AGENT_CANON_CHILD_PURPOSE="standalone-static-gate-unit"' in body
    assert 'AGENT_CANON_CLI_CMD="/usr/local/bin/agent-canon"' in body
    assert 'CARGO_HOME="${CARGO_HOME}"' in body
    assert 'RUSTUP_HOME="${RUSTUP_HOME}"' in body
    assert 'AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"' in body
    assert "full) run_full" in text
    assert '"${UNIT}" != "full"' in text
    assert 'cd "${AGENT_CANON_STATIC_RUNTIME_ROOT}/.."' not in body


@pytest.mark.parametrize("body_status", (0, 17))
def test_full_unit_preserves_body_status_without_target_mutation(
    tmp_path: Path,
    body_status: int,
) -> None:
    """The adapter forwards capabilities and preserves the body result."""
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    tracked = target / "tracked.txt"
    tracked.write_text("unchanged\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(target), "add", "tracked.txt"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.email=agent-canon@example.invalid",
            "-c",
            "user.name=AgentCanon",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
    )

    runner_parent = target / "tools" / "validation" / "ci" / "runners"
    runner_parent.mkdir(parents=True)
    runner = runner_parent / RUNNER.name
    runner_text = RUNNER.read_text(encoding="utf-8").replace(
        "/usr/local/share/agent-canon/.agent-canon-tool-container",
        str(tmp_path / "tool-container-marker"),
    )
    runner.write_text(runner_text, encoding="utf-8")
    runner.chmod(0o755)
    (tmp_path / "tool-container-marker").touch()

    capture = tmp_path / "capture.txt"
    fake_checks = target / "tools" / "validation" / "ci" / "runners" / "run_all_checks.sh"
    fake_checks.parent.mkdir(parents=True, exist_ok=True)
    fake_checks.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        ": > \"${FAKE_CAPTURE}\"\n"
        "printf 'control=%s\\n' \"${AGENT_CANON_CONTROL_PARENT_ROOT}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'runtime=%s\\n' \"${AGENT_CANON_RUNTIME_ROOT}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'purpose=%s\\n' \"${AGENT_CANON_CHILD_PURPOSE}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'handoff=%s\\n' \"${AGENT_CANON_CHILD_HANDOFF}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'cli=%s\\n' \"${AGENT_CANON_CLI_CMD}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'cargo=%s\\n' \"${CARGO_HOME}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'rustup=%s\\n' \"${RUSTUP_HOME}\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'args=%s\\n' \"$*\" >> \"${FAKE_CAPTURE}\"\n"
        "printf 'RUN_ALL_CHECKS_BODY=completed\\n'\n"
        "exit \"${FAKE_BODY_STATUS}\"\n",
        encoding="utf-8",
    )
    fake_checks.chmod(0o755)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "payload=$(cat)\n"
        "if [[ \"${payload}\" == *'runtime_artifact_boundary'* ]]; then\n"
        "  if [[ \"$#\" -ge 4 ]]; then printf '%s\\n' \"${4}\"; else printf '%s\\n' \"${3}\"; fi\n"
        "else\n"
        "  exit 0\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    control = tmp_path / "home"
    runtime = control / "workspace" / "full-check"
    before_tree = subprocess.run(
        ["git", "-C", str(target), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    before_index = (target / ".git" / "index").read_bytes()
    result = subprocess.run(
        ["bash", str(runner), "full", "--quick", "--skip-docs"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "AGENT_CANON_TARGET_ROOT": str(target),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
            "AGENT_CANON_RUNTIME_ROOT": str(runtime),
            "AGENT_CANON_CHILD_HANDOFF": "authenticated-handoff",
            "AGENT_CANON_HANDOFF_AUDIENCE": "standalone-static-gate-unit",
            "FAKE_CAPTURE": str(capture),
            "FAKE_BODY_STATUS": str(body_status),
        },
    )
    assert result.returncode == body_status, result.stderr
    assert "RUN_ALL_CHECKS_BODY=completed" in result.stdout
    observed = dict(
        line.split("=", 1)
        for line in capture.read_text(encoding="utf-8").splitlines()
    )
    assert observed == {
        "control": str(control),
        "runtime": str(runtime),
        "purpose": "standalone-static-gate-unit",
        "handoff": "authenticated-handoff",
        "cli": "/usr/local/bin/agent-canon",
        "cargo": str(runtime / "cargo-home"),
        "rustup": str(runtime / "rustup-home"),
        "args": "--quick --skip-docs",
    }
    after_tree = subprocess.run(
        ["git", "-C", str(target), "write-tree"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert after_tree == before_tree
    assert (target / ".git" / "index").read_bytes() == before_index
    assert hashlib.sha256(tracked.read_bytes()).hexdigest() == hashlib.sha256(
        b"unchanged\n"
    ).hexdigest()


def test_read_only_route_never_repairs_the_caller_checkout() -> None:
    """Isolation must not be replaced by destructive Git rollback."""
    text = runner_text()
    for command in ("git restore", "git reset", "git clean", "git stash"):
        assert command not in text


def test_host_execution_fails_before_any_check_body() -> None:
    """The unit runner is not a writable-Host fallback."""
    marker = Path("/usr/local/share/agent-canon/.agent-canon-tool-container")
    if marker.is_file():
        return
    result = subprocess.run(
        ["bash", str(RUNNER), "full", "--quick"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "shared_tool_runtime_required" in result.stderr


def test_shell_syntax() -> None:
    """The read-only runner remains valid Bash."""
    result = subprocess.run(
        ["bash", "-n", str(RUNNER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
