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
from tools.agent_tools.bootstrap_runtime import (
    PRIVATE_LOG_DESTINATION,
    BootstrapRuntime,
)
from tools.agent_tools.log_repository_identity import stable_log_branch

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def invoke(runtime: Path, *argv: str, log_root: Path | None = None) -> int:
    """Invoke the private feedback adapter against a test-owned runtime."""
    args = ["--runtime-root", str(runtime), "--source-root", str(SOURCE_ROOT)]
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
        "source=user target=agent-log action=knowledge_record runtime_feedback=observed",
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
    branch = stable_log_branch(SOURCE_ROOT)
    subprocess.run(["git", "-C", str(seed), "branch", branch], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "push", "origin", f"HEAD:refs/heads/{branch}"],
        check=True,
        capture_output=True,
    )
    return remote, seed


def test_no_annex_remote_keeps_raw_spool_pending(tmp_path: Path) -> None:
    """Raw content is not committed as an ordinary Git blob without annex."""
    remote, _seed = _local_remote(tmp_path)
    runtime = tmp_path / "runtime"
    raw = runtime / "spool/private-feedback/raw/topic/payload.bin"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"payload")
    assert invoke(runtime, "k", "sync", log_root=tmp_path / "log") == 0
    assert invoke(runtime, "--remote", f"file://{remote}", "host-sync", log_root=tmp_path / "log") == 1
    assert raw.is_file()
    assert not (tmp_path / "log/raw/topic/payload.bin").exists()


def test_sync_failure_retains_spool(tmp_path: Path) -> None:
    """Remote/network failure preserves private content for retry."""
    runtime = tmp_path / "runtime"
    invoke(runtime, "f", "add", "retry", "retain this", "--task", "t1")
    assert invoke(runtime, "f", "sync", log_root=tmp_path / "log") == 0
    with pytest.raises((private_feedback.PrivateFeedbackError, subprocess.CalledProcessError), match="git_failed|clone|does-not-exist"):
        invoke(runtime, "--remote", "file:///tmp/private-feedback-does-not-exist.git", "host-sync", log_root=tmp_path / "log")
    assert list((runtime / "spool/private-feedback/feedback").rglob("*.md"))


def test_operational_clone_migration_observes_old_archive_before_new_clone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A legacy runtime clone is observed, retained, and replaced by the stable checkout."""
    remote, _seed = _local_remote(tmp_path)
    legacy = tmp_path / "runtime/archive/agent-canon-log"
    subprocess.run(["git", "clone", str(remote), str(legacy)], check=True, capture_output=True)
    runtime = tmp_path / "runtime"
    invoke(runtime, "f", "add", "migration", "keep archive", "--task", "t1")
    assert invoke(runtime, "f", "sync", log_root=tmp_path / "log") == 0
    assert invoke(runtime, "--remote", f"file://{remote}", "host-sync", log_root=tmp_path / "log") == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["migration"] == "legacy-readback-observed"
    assert legacy.is_dir()
    assert (tmp_path / "log/.git").is_dir()


def test_sync_request_host_readback_and_private_log_mount_are_separate(tmp_path: Path) -> None:
    """The container request is consumed by host Git and its checkout is RO-mounted."""
    remote, _seed = _local_remote(tmp_path)
    control = tmp_path / "control"
    log_root = control / "agent-canon-log"
    runtime = control / "runtime"
    log_root.mkdir(parents=True)
    invoke(runtime, "k", "add", "boundary", "keep archive host-owned", "--task", "t1")
    assert invoke(runtime, "k", "sync", log_root=log_root) == 0
    request = runtime / "spool/private-feedback/sync-request.json"
    assert request.is_file()
    assert invoke(
        runtime,
        "--remote",
        f"file://{remote}",
        "host-sync",
        log_root=log_root,
    ) == 0
    assert not request.exists()
    remote_head = subprocess.run(
        ["git", "-C", str(log_root), "rev-parse", f"origin/{stable_log_branch(SOURCE_ROOT)}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    local_head = subprocess.run(
        ["git", "-C", str(log_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert local_head == remote_head
    manager = BootstrapRuntime(control, runtime, repository_root=Path(__file__).resolve().parents[2])
    manager._ensure_layout()
    mount = next(item for item in manager._mounts({}) if item["destination"] == PRIVATE_LOG_DESTINATION)
    assert mount["mode"] == "read-only"


def test_sync_request_is_reused_across_k_and_f_and_publishes_stable_branch(tmp_path: Path) -> None:
    """One valid request is shared by k/f and removed only after branch readback."""
    remote, _seed = _local_remote(tmp_path)
    runtime = tmp_path / "runtime"
    log_root = tmp_path / "log"
    invoke(runtime, "k", "add", "knowledge", "keep this knowledge", "--task", "t1")
    assert invoke(runtime, "k", "sync") == 0
    request = runtime / "spool/private-feedback/sync-request.json"
    first_request = request.read_bytes()
    invoke(runtime, "f", "add", "feedback", "keep this feedback", "--task", "t1")
    assert invoke(runtime, "f", "sync") == 0
    assert request.read_bytes() == first_request

    assert invoke(
        runtime,
        "--remote",
        f"file://{remote}",
        "host-sync",
        log_root=log_root,
    ) == 0
    branch = stable_log_branch(SOURCE_ROOT)
    remote_head = subprocess.run(
        ["git", "-C", str(log_root), "rev-parse", f"origin/{branch}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    local_head = subprocess.run(
        ["git", "-C", str(log_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert local_head == remote_head
    assert subprocess.run(
        ["git", "-C", str(log_root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == branch
    assert not request.exists()
    assert not list((runtime / "spool/private-feedback").rglob("*.md"))


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


def test_bootstrap_consumes_container_runtime_private_feedback_spool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bootstrap consumes the request from the host-side bind-mapped spool."""
    remote, _seed = _local_remote(tmp_path)
    control = tmp_path / "control"
    control.mkdir()
    runtime = control / "runtime"
    manager = BootstrapRuntime(
        control, runtime, repository_root=Path(__file__).resolve().parents[2]
    )
    monkeypatch.setattr(
        type(manager),
        "private_log_root",
        property(lambda _manager: control / "agent-canon-log"),
    )
    manager._ensure_layout()
    container_runtime = manager.paths.container_runtime
    assert (
        invoke(container_runtime, "k", "add", "mapped", "consume this", "--task", "t1")
        == 0
    )
    assert invoke(container_runtime, "k", "sync") == 0
    request = container_runtime / "spool/private-feedback/sync-request.json"
    assert request.is_file()
    assert not (runtime / "spool/private-feedback/sync-request.json").exists()

    monkeypatch.setenv("AGENT_CANON_LOG_REMOTE", f"file://{remote}")
    result = manager._host_private_feedback_sync()

    assert result is not None
    assert result["status"] == "synced"
    assert not request.exists()
    assert not list((container_runtime / "spool/private-feedback").rglob("*.md"))
    assert (control / "agent-canon-log/knowledge/topics/mapped/candidate.md").is_file()
