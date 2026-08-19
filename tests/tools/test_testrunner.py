# @dependency-start
# contract test
# responsibility Tests source-owned test selection and responsibility-aware execution receipts.
# upstream implementation ../../test/testrunner.sh public shell entrypoint
# upstream implementation ../../test/testrunner.py typed test executor
# upstream implementation ../../test/testlist.toml canonical command list
# @dependency-end

"""Tests for the public repository test runner."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "test" / "testrunner.sh"


def run_list(
    tmp_path: Path, text: str, *, route: str = "docker"
) -> subprocess.CompletedProcess[str]:
    """Run one temporary list through the checked-in shell entrypoint."""
    test_list = tmp_path / "testlist.toml"
    test_list.write_text(text, encoding="utf-8")
    environment = {
        **os.environ,
        "AGENT_CANON_TESTLIST": str(test_list),
        "AGENT_CANON_ACTIVE_ROUTE": route,
    }
    return subprocess.run(
        ["bash", str(RUNNER)],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def records(result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
    """Decode runner-owned JSONL without mixing child command output."""
    return [json.loads(line) for line in result.stdout.splitlines()]


def record(record_id: str, command: list[str], *, requirement: str = "docker") -> str:
    """Render one complete TOML record."""
    return "\n".join(
        (
            "[[tests]]",
            f"id = {json.dumps(record_id)}",
            'environment = "tooling"',
            f"require = {json.dumps(requirement)}",
            'code_owner = "test/testrunner.py"',
            'responsibility_scope = "repository-test-runner"',
            f"command = {json.dumps(command)}",
            "",
        )
    )


def test_selected_records_continue_after_failure_and_retain_ownership(
    tmp_path: Path,
) -> None:
    """Every selected command emits start/terminal metadata even after a failure."""
    result = run_list(
        tmp_path,
        record("pass", ["python3", "-c", "print('pass-output')"])
        + record("fail", ["python3", "-c", "import sys; sys.exit(7)"]),
    )

    assert result.returncode == 1
    assert "pass-output" in result.stderr
    emitted = records(result)
    assert [(item["id"], item["status"]) for item in emitted] == [
        ("pass", "start"),
        ("pass", "pass"),
        ("fail", "start"),
        ("fail", "fail"),
    ]
    failure = emitted[-1]
    assert failure["exit_code"] == 7
    assert failure["environment"] == "tooling"
    assert failure["code_owner"] == "test/testrunner.py"
    assert failure["responsibility_scope"] == "repository-test-runner"
    assert failure["argv"] == ["python3", "-c", "import sys; sys.exit(7)"]


def test_requirement_selection_emits_not_selected_receipt(tmp_path: Path) -> None:
    """Docker and devcontainer records share one list without cross-execution."""
    result = run_list(
        tmp_path,
        record("docker-only", ["python3", "-c", "raise SystemExit(9)"])
        + record(
            "devcontainer-only",
            ["python3", "-c", "raise SystemExit(0)"],
            requirement="devcontainer",
        ),
        route="devcontainer",
    )

    assert result.returncode == 0
    emitted = records(result)
    assert [(item["id"], item["status"]) for item in emitted] == [
        ("docker-only", "not_selected"),
        ("devcontainer-only", "start"),
        ("devcontainer-only", "pass"),
    ]


def test_missing_executable_is_a_typed_command_failure(tmp_path: Path) -> None:
    """Command-start errors retain the declared code and responsibility owners."""
    result = run_list(tmp_path, record("missing", ["missing-agent-canon-command"]))

    assert result.returncode == 1
    terminal = records(result)[-1]
    assert terminal["status"] == "fail"
    assert terminal["exit_code"] == 127
    assert terminal["environment"] == "tooling"
    assert "command start failed for missing" in result.stderr


def test_checked_in_list_declares_only_public_requirements() -> None:
    """The canonical source list records the Docker/devcontainer requirement field."""
    text = (PROJECT_ROOT / "test" / "testlist.toml").read_text(encoding="utf-8")
    assert 'require = "docker"' in text
    assert "tests/agent_tools" in text
    assert "tests/tools" in text
    assert "rust/agent-canon/Cargo.toml" in text
