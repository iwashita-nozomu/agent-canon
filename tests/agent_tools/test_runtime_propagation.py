"""Focused tests for external eval runtime propagation and source immutability."""

# @dependency-start
# contract test
# responsibility Verifies eval child runtime propagation and source immutability.
# upstream implementation ../../eval/producers/run_accumulated_agent_evals.py propagates typed runtime roots
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md external artifact boundary
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from eval.producers.run_accumulated_agent_evals import (  # noqa: E402
    EvalProducer,
    run_producers,
)


def _tracked_snapshot() -> tuple[str, dict[str, str]]:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paths = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    digests: dict[str, str] = {}
    for raw in paths:
        if not raw:
            continue
        relative = raw.decode()
        path = ROOT / relative
        if not os.path.lexists(path):
            digests[relative] = "deleted"
            continue
        payload = (
            b"symlink:\0" + os.readlink(path).encode()
            if path.is_symlink()
            else path.read_bytes()
        )
        digests[relative] = hashlib.sha256(payload).hexdigest()
    return status, digests


def test_producer_child_receives_typed_runtime_and_root_capabilities(tmp_path: Path) -> None:
    """Keep producer-definition and observed-target capabilities distinct."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    runtime = tmp_path / "runtime"
    source.mkdir()
    target.mkdir()
    runtime.mkdir()
    observed: dict[str, str] = {}

    def fake_runner(command, cwd, env):  # type: ignore[no-untyped-def]
        observed.update(env)
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    run_producers(
        root=source,
        producers=(EvalProducer("fixture", ("fixture",)),),
        log_dir=runtime / "logs",
        target_root=target,
        runtime_root=runtime,
        runner=fake_runner,
    )

    assert observed["AGENT_CANON_RUNTIME_ROOT"] == str(runtime.resolve())
    assert observed["AGENT_CANON_PARENT_ROOT"] == str(source.resolve())
    assert observed["AGENT_CANON_TARGET_ROOT"] == str(target.resolve())
    assert json.loads(observed["AGENT_CANON_PARENT_ROOT_CAPABILITY"])["kind"] == "parent-root"
    assert json.loads(observed["AGENT_CANON_TARGET_ROOT_CAPABILITY"])["kind"] == "target-root"


def test_eval_producers_leave_source_status_and_bytes_unchanged(tmp_path: Path) -> None:
    """Real producer execution must leave AgentCanon source unchanged."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    before_status, before_files = _tracked_snapshot()
    commands = (
        (
            "evaluate_report_quality.py",
            "--accumulate",
            "--runtime-root",
            str(runtime),
        ),
        (
            "evaluate_workflow_selection.py",
            "--accumulate",
            "--runtime-root",
            str(runtime),
        ),
        (
            "evaluate_skill_workflow_prompts.py",
            "--accumulate",
            "--runtime-root",
            str(runtime),
        ),
        (
            "evaluate_codex_agent_roles.py",
            "--accumulate",
            "--runtime-root",
            str(runtime),
        ),
    )
    for command in commands:
        result = subprocess.run(
            [sys.executable, str(ROOT / "eval" / "producers" / command[0]), *command[1:]],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        # A semantic eval may legitimately report status=fail while this test
        # verifies the execution plane and source immutability. Exit 2+ is an
        # infrastructure/usage failure and remains blocking here.
        assert result.returncode in {0, 1}, result.stdout + result.stderr
        assert "Traceback" not in result.stderr
    after_status, after_files = _tracked_snapshot()
    assert after_status == before_status
    assert after_files == before_files
    assert tuple(runtime.rglob("*.md"))
