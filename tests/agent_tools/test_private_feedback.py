#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Verifies the private feedback/knowledge adapter's owner-local observations.
# upstream implementation ../../tools/agent_tools/private_feedback.py
# upstream external-schema git@github.com:iwashita-nozomu/agent-canon-log.git@db3722b817be8574c682949db733df0fb5c2674a
# downstream documentation ../../documents/runtime/private-feedback-knowledge.md
# @dependency-end
"""Focused tests for private feedback storage and promotion."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.agent_tools import private_feedback


def invoke(runtime: Path, *argv: str, log_root: Path | None = None) -> int:
    args = ["--runtime-root", str(runtime)]
    if log_root is not None:
        args.extend(["--log-root", str(log_root)])
    args.extend(argv)
    return private_feedback.main(args)


def test_direct_text_and_stdin_write_metadata_only(capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct prose and stdin both land in the external spool."""
    runtime = tmp_path / "runtime"
    assert invoke(runtime, "k", "add", "topic", "direct prose", "--run", "r1", "--task", "t1") == 0
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("stdin prose"))
    assert invoke(runtime, "k", "add", "stdin-topic", "--stdin", "--run", "r2", "--task", "t2") == 0
    output = capsys.readouterr().out
    assert "direct prose" not in output
    assert "stdin prose" not in output
    assert (runtime / "spool/private-feedback/knowledge/topics/topic/candidate.md").is_file()
    assert (runtime / "spool/private-feedback/knowledge/topics/stdin-topic/candidate.md").is_file()


def test_body_redaction_receipt_rejects_secret_and_never_prints_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Credential-shaped payloads are refused before private persistence."""
    with pytest.raises(private_feedback.PrivateFeedbackError, match="private_data_rejected"):
        invoke(tmp_path / "runtime", "f", "add", "secret-topic", "token=do-not-store")
    assert "do-not-store" not in capsys.readouterr().err


def test_structured_runtime_feedback_auto_capture(tmp_path: Path) -> None:
    """The existing structured feedback route can write an external spool record."""
    meta = private_feedback.capture_runtime_feedback(
        "source=user target=agent-log action=memory_record runtime_feedback=observed",
        runtime_root=tmp_path / "runtime",
        run="run-1",
        task="task-1",
    )
    assert meta["input_mode"] == "structured-log"
    assert (tmp_path / "runtime/spool/private-feedback/feedback/runtime-feedback").is_dir()


def test_two_distinct_tasks_promote_to_private_skill_and_same_task_dedupes(tmp_path: Path) -> None:
    """Promotion needs two task scopes; repeat reads in one task count once."""
    runtime = tmp_path / "runtime"
    log_root = tmp_path / "missing-log"
    invoke(runtime, "k", "add", "promotion", "Keep the owner boundary", "--run", "r1", "--task", "t1")
    assert invoke(runtime, "k", "read", "promotion", "--run", "r1", "--task", "t1", log_root=log_root) == 0
    assert invoke(runtime, "k", "read", "promotion", "--run", "r1b", "--task", "t1", log_root=log_root) == 0
    assert not (runtime / "private-skills/promotion/SKILL.md").exists()
    assert invoke(runtime, "k", "read", "promotion", "--run", "r2", "--task", "t2", log_root=log_root) == 0
    skill = runtime / "private-skills/promotion/SKILL.md"
    assert skill.is_file()
    assert "Keep the owner boundary" in skill.read_text(encoding="utf-8")
    assert "not public AgentCanon policy" in skill.read_text(encoding="utf-8")


def _local_remote(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "private-feedback-test"], check=True)
    (seed / "README.md").write_text("private archive\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-m", "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "push", "origin", "HEAD:main"], check=True, capture_output=True)
    return remote, seed


def test_no_annex_remote_keeps_raw_spool_pending(tmp_path: Path) -> None:
    """Raw content is not committed as an ordinary Git blob without annex."""
    remote, _seed = _local_remote(tmp_path)
    runtime = tmp_path / "runtime"
    raw = runtime / "spool/private-feedback/raw/topic/payload.bin"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"payload")
    assert invoke(runtime, "--remote", f"file://{remote}", "k", "sync", log_root=tmp_path / "log") == 1
    assert raw.is_file()
    assert not (tmp_path / "log/raw/topic/payload.bin").exists()


def test_sync_failure_retains_spool(tmp_path: Path) -> None:
    """Remote/network failure preserves private content for retry."""
    runtime = tmp_path / "runtime"
    invoke(runtime, "f", "add", "retry", "retain this", "--task", "t1")
    with pytest.raises((private_feedback.PrivateFeedbackError, subprocess.CalledProcessError), match="git_failed|clone|does-not-exist"):
        invoke(runtime, "--remote", "file:///tmp/private-feedback-does-not-exist.git", "f", "sync", log_root=tmp_path / "log")
    assert list((runtime / "spool/private-feedback/feedback").rglob("*.md"))


def test_operational_clone_migration_observes_old_archive_before_new_clone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A legacy runtime clone is observed, retained, and replaced by main checkout."""
    remote, _seed = _local_remote(tmp_path)
    legacy = tmp_path / "runtime/archive/agent-canon-log"
    subprocess.run(["git", "clone", str(remote), str(legacy)], check=True, capture_output=True)
    runtime = tmp_path / "runtime"
    invoke(runtime, "f", "add", "migration", "keep archive", "--task", "t1")
    assert invoke(runtime, "--remote", f"file://{remote}", "f", "sync", log_root=tmp_path / "log") == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["migration"] == "legacy-readback-observed"
    assert legacy.is_dir()
    assert (tmp_path / "log/.git").is_dir()


def test_memory_migration_is_non_destructive(tmp_path: Path) -> None:
    """The one-cycle memory migration never deletes source records."""
    source = tmp_path / "source"
    record = source / "memory/records/runtime--boundary.md"
    record.parent.mkdir(parents=True)
    record.write_text("# Boundary\n\nKeep runtime data external.\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    assert invoke(runtime, "k", "migrate-memory", "--root", str(source)) == 0
    assert record.is_file()
    assert list((runtime / "spool/private-feedback/knowledge/topics").rglob("candidate.md"))
