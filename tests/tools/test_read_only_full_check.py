"""Focused contract tests for the read-only full-check execution route."""

# @dependency-start
# contract test
# responsibility Verifies full checks are admitted only after a read-only target mount proof and reuse the existing full-check body without checkout mutation.
# upstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh owns target admission and full-check dispatch
# upstream implementation ../../tools/ci/run_all_checks.sh owns the existing full-confidence check body
# @dependency-end

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "ci" / "run_standalone_static_gate_unit.sh"


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

    assert 'bash "${ROOT}/tools/ci/run_all_checks.sh" "${UNIT_ARGS[@]}"' in body
    assert 'AGENT_CANON_CONTROL_PARENT_ROOT="${control_parent_root}"' in body
    assert 'AGENT_CANON_RUNTIME_ROOT="${AGENT_CANON_STATIC_RUNTIME_ROOT}"' in body
    assert "full) run_full" in text
    assert '"${UNIT}" != "full"' in text


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
