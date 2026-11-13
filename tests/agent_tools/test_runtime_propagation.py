"""Focused tests for external eval runtime propagation and source immutability."""

# @dependency-start
# contract test
# responsibility Verifies eval child runtime propagation and source immutability.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/eval_accumulation.rs propagates typed runtime roots
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md external artifact boundary
# @dependency-end

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


def test_eval_producers_leave_source_status_and_bytes_unchanged(tmp_path: Path) -> None:
    """Real producer execution must leave AgentCanon source unchanged."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    before_status, before_files = _tracked_snapshot()
    environment = os.environ.copy()
    environment.pop("AGENT_CANON_HOOK_ARCHIVE_DIR", None)
    environment.pop("AGENT_CANON_LOG_ROOT", None)
    environment.pop("AGENT_CANON_RUNTIME_ROOT", None)
    result = subprocess.run(
        [
            str(ROOT / "tools/bin/agent-canon"),
            "run-accumulated-agent-evals",
            "--root",
            str(ROOT),
            "--run-id",
            "runtime-propagation-test",
            "--runtime-root",
            str(runtime),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
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
