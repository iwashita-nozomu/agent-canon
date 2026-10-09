#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Verifies the private feedback/knowledge adapter's owner-local observations.
# upstream implementation ../../tools/runtime/archive/private_feedback.py private feedback adapter behavior
# upstream design ../../documents/runtime/private-feedback-knowledge.md private feedback command and storage contract
# @dependency-end
"""Focused tests for private feedback storage and promotion."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.runtime.archive import private_feedback


def invoke(runtime: Path, *argv: str, log_root: Path | None = None) -> int:
    """Invoke the private feedback adapter against a test-owned runtime."""
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
    request = runtime / "spool/private-feedback/sync-request.json"
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["schema"] == private_feedback.SYNC_REQUEST_SCHEMA
    assert set(payload) == {
        "execution_plane",
        "operation",
        "requested_at",
        "schema",
        "source_commit",
    }
    assert "direct prose" not in request.read_text(encoding="utf-8")
    assert "stdin prose" not in request.read_text(encoding="utf-8")


def test_k_and_f_sync_reuse_the_body_free_publication_request(tmp_path: Path) -> None:
    """The existing aliases keep one stable request while adding spool items."""
    runtime = tmp_path / "runtime"
    assert invoke(runtime, "k", "add", "knowledge", "private knowledge", "--task", "t1") == 0
    assert invoke(runtime, "k", "sync") == 0
    request = runtime / "spool/private-feedback/sync-request.json"
    first_request = request.read_bytes()
    assert invoke(runtime, "f", "add", "feedback", "private feedback", "--task", "t1") == 0
    assert invoke(runtime, "f", "sync") == 0
    assert request.read_bytes() == first_request
    payload = json.loads(first_request)
    assert payload["schema"] == private_feedback.SYNC_REQUEST_SCHEMA
    assert payload["operation"] == "sync"
    assert payload["execution_plane"] == "agentcanon_tool_container"
    assert "private knowledge" not in first_request.decode("utf-8")
    assert "private feedback" not in first_request.decode("utf-8")
    assert (runtime / "spool/private-feedback/knowledge/topics/knowledge/candidate.md").is_file()
    assert (runtime / "spool/private-feedback/feedback/feedback").is_dir()


def test_body_redaction_receipt_rejects_secret_and_never_prints_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Credential-shaped payloads are refused before private persistence."""
    with pytest.raises(private_feedback.PrivateFeedbackError, match="private_data_rejected"):
        invoke(tmp_path / "runtime", "f", "add", "secret-topic", "token=do-not-store")
    assert "do-not-store" not in capsys.readouterr().err


def test_structured_runtime_feedback_auto_capture(tmp_path: Path) -> None:
    """The existing structured feedback route can write an external spool record."""
    meta = private_feedback.capture_runtime_feedback(
        "source=user target=agent-log action=knowledge_record runtime_feedback=observed",
        runtime_root=tmp_path / "runtime",
        run="run-1",
        task="task-1",
    )
    assert meta["input_mode"] == "structured-log"
    assert meta["sync_request"] == "created"
    assert (tmp_path / "runtime/spool/private-feedback/feedback/runtime-feedback").is_dir()
    request = tmp_path / "runtime/spool/private-feedback/sync-request.json"
    assert request.is_file()
    assert "runtime_feedback=observed" not in request.read_text(encoding="utf-8")


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


def test_invalid_sync_request_is_a_preserved_typed_blocker(tmp_path: Path) -> None:
    """A conflicting request is never replaced or discarded by a retry."""
    runtime = tmp_path / "runtime"
    request = runtime / "spool/private-feedback/sync-request.json"
    request.parent.mkdir(parents=True)
    request.write_text('{"schema":"wrong"}\n', encoding="utf-8")
    before = request.read_bytes()
    with pytest.raises(private_feedback.PrivateFeedbackError, match="sync_request_invalid"):
        invoke(runtime, "k", "sync")
    assert request.read_bytes() == before


def test_spool_writer_waits_for_host_snapshot_cleanup_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A producer cannot change feedback while the host compares and clears it."""
    runtime = tmp_path / "runtime"
    spool = private_feedback._spool_root(runtime)
    started = threading.Event()
    attempting_lock = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    original_flock = private_feedback.fcntl.flock

    def observe_flock(descriptor: int, operation: int) -> None:
        if threading.current_thread().name == "feedback-writer" and operation == private_feedback.fcntl.LOCK_EX:
            attempting_lock.set()
        original_flock(descriptor, operation)

    monkeypatch.setattr(private_feedback.fcntl, "flock", observe_flock)

    def write_feedback() -> None:
        started.set()
        try:
            invoke(runtime, "f", "add", "concurrent", "new bytes", "--task", "t1")
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    with private_feedback._private_feedback_spool_lock(spool):
        writer = threading.Thread(target=write_feedback, name="feedback-writer")
        writer.start()
        assert started.wait(1)
        assert attempting_lock.wait(1)
        assert not finished.wait(0.05)
        assert not (spool / "feedback/concurrent").exists()
    writer.join(1)

    assert not writer.is_alive()
    assert not errors
    assert finished.is_set()
    assert (spool / "feedback/concurrent").is_dir()
    assert (spool / "sync-request.json").is_file()
