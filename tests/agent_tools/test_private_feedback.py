"""Public native private feedback contracts; Python is only the test oracle."""

# @dependency-start
# contract test
# responsibility Verifies native private storage, body-free output and OS lock interoperability.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/private_feedback.rs native behavior
# upstream design ../../documents/runtime/private-feedback-knowledge.md storage contract
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

SCHEMA = "agent-canon.private-feedback-sync-request.v1"


@pytest.fixture(scope="session")
def native() -> str:
    """Use the selected built executable; never build or substitute the old adapter."""
    executable = os.environ.get("AGENT_CANON_NATIVE_BIN") or shutil.which("agent-canon")
    if not executable:
        raise RuntimeError("Set AGENT_CANON_NATIVE_BIN to the candidate native executable")
    return executable


def invoke(
    native: str,
    runtime: Path,
    *argv: str,
    log_root: Path | None = None,
    body: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [native, *argv, "--runtime-root", str(runtime)]
    if log_root is not None:
        args.extend(["--log-root", str(log_root)])
    return subprocess.run(
        args,
        input=body,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "AGENT_CANON_SOURCE_COMMIT": "a" * 40,
            "AGENT_CANON_PYTHON": str(runtime / "must-not-run-python"),
            **(extra_env or {}),
        },
    )


def metadata(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return json.loads(result.stdout.splitlines()[0])


def test_direct_text_and_stdin_write_metadata_only(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    direct = invoke(native, runtime, "k", "add", "topic", "direct prose", "--run", "r1", "--task", "t1")
    via_stdin = invoke(native, runtime, "k", "add", "stdin-topic", "--stdin", "--run", "r2", "--task", "t2", body="stdin prose")
    assert metadata(direct)["input_mode"] == "text"
    assert metadata(via_stdin)["input_mode"] == "stdin"
    assert "direct prose" not in direct.stdout + direct.stderr
    assert "stdin prose" not in via_stdin.stdout + via_stdin.stderr
    candidate = runtime / "spool/private-feedback/knowledge/topics/topic/candidate.md"
    assert candidate.read_text(encoding="utf-8").endswith("\n\ndirect prose\n")
    assert (runtime / "spool/private-feedback/knowledge/topics/stdin-topic/candidate.md").is_file()
    request = runtime / "spool/private-feedback/sync-request.json"
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert set(payload) == {"execution_plane", "operation", "requested_at", "schema", "source_commit"}
    assert payload["schema"] == SCHEMA
    assert payload["source_commit"] == "a" * 40
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", payload["requested_at"])
    assert request.read_text(encoding="utf-8") == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert "direct prose" not in request.read_text(encoding="utf-8")


def test_k_and_f_sync_reuse_body_free_request(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    metadata(invoke(native, runtime, "k", "add", "knowledge", "private knowledge", "--task", "t1"))
    request = runtime / "spool/private-feedback/sync-request.json"
    before = request.read_bytes()
    assert metadata(invoke(native, runtime, "k", "sync"))["request_reused"] == "yes"
    metadata(invoke(native, runtime, "f", "add", "feedback", "private feedback", "--task", "t1"))
    assert metadata(invoke(native, runtime, "f", "sync"))["request_reused"] == "yes"
    assert request.read_bytes() == before
    assert b"private knowledge" not in before
    assert b"private feedback" not in before


@pytest.mark.parametrize("body", [
    "token=do-not-store", "Bearer do-not-store", "APİ_KEY=do-not-store",
    "-----BEGIN OPENSSH KEY-----",
])
def test_redaction_precedes_persistence(native: str, tmp_path: Path, body: str) -> None:
    runtime = tmp_path / "runtime"
    result = invoke(native, runtime, "f", "add", "secret-topic", "--stdin", body=body)
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "private_data_rejected"
    assert body not in result.stdout + result.stderr
    assert "do-not-store" not in result.stdout + result.stderr
    assert not runtime.exists()


@pytest.mark.parametrize("family", ["k", "knowledge", "f", "feedback"])
def test_capture_has_runtime_topic(native: str, tmp_path: Path, family: str) -> None:
    runtime = tmp_path / "runtime"
    result = invoke(native, runtime, family, "capture", "--stdin", body="source=user target=skill action=repair")
    meta = metadata(result)
    assert meta["topic"] == "runtime-feedback"
    assert meta["kind"] == "feedback"
    assert meta["status"] == "spooled"
    assert (runtime / "spool/private-feedback" / meta["locator"]).is_file()


def test_structured_capture_preserves_monitor_metadata(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    body = "  source=user target=agent-log action=knowledge_record runtime_feedback=observed  "
    result = invoke(
        native, runtime, "f", "capture", "--structured-log", "--stdin", "--run", "run-1",
        body=body, extra_env={"AGENT_CANON_TASK_ID": "unrelated-task"},
    )
    meta = metadata(result)
    assert meta["input_mode"] == "structured-log"
    assert meta["status"] == "observed"
    assert meta["run"] == "run-1"
    assert meta["task"] == ""
    assert meta["content_digest"] == "sha256:" + hashlib.sha256((body.strip() + "\n").encode()).hexdigest()
    assert meta["sync_request"] == "created"
    stored = (runtime / "spool/private-feedback" / meta["locator"]).read_text(encoding="utf-8")
    assert "input_mode: structured-log" in stored
    assert stored.endswith(body.strip() + "\n")
    assert body.strip() not in result.stdout + result.stderr
    assert "runtime_feedback=observed" not in (runtime / "spool/private-feedback/sync-request.json").read_text()


def test_capture_limit_is_utf8_bytes(native: str, tmp_path: Path) -> None:
    result = invoke(native, tmp_path / "runtime", "f", "capture", "--structured-log", "--stdin", body="あ" * 6000)
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "private_data_rejected"
    assert not (tmp_path / "runtime").exists()


def test_two_tasks_promote_and_same_task_dedupes(native: str, tmp_path: Path) -> None:
    runtime, log_root = tmp_path / "runtime", tmp_path / "missing-log"
    metadata(invoke(native, runtime, "k", "add", "promotion", "Keep the owner boundary", "--run", "r1", "--task", "t1"))
    first = metadata(invoke(native, runtime, "k", "read", "promotion", "--run", "r1", "--task", "t1", log_root=log_root))
    duplicate = metadata(invoke(native, runtime, "k", "read", "promotion", "--run", "r1b", "--task", "t1", log_root=log_root))
    assert first["status"] == "read"
    assert duplicate["status"] == "duplicate"
    assert not (runtime / "private-skills/promotion/SKILL.md").exists()
    second = metadata(invoke(native, runtime, "k", "read", "promotion", "--run", "r2", "--task", "t2", log_root=log_root))
    assert second["promotion"] == "private-skill-candidate"
    skill = (runtime / "private-skills/promotion/SKILL.md").read_text(encoding="utf-8")
    assert "Keep the owner boundary" in skill
    assert "not public AgentCanon policy" in skill
    assert "- task:t1" in skill and "- task:t2" in skill
    assert (runtime / "spool/private-feedback/runtime/skills/promotion/SKILL.md").read_text(encoding="utf-8") == skill


def test_read_show_is_opt_in_and_search_hashes_file(native: str, tmp_path: Path) -> None:
    runtime, log_root = tmp_path / "runtime", tmp_path / "private-log"
    metadata(invoke(native, runtime, "k", "add", "topic", "local body"))
    archived = log_root / "knowledge/topics/topic/candidate.md"
    archived.parent.mkdir(parents=True)
    archived.write_text("archived body\n", encoding="utf-8")
    read = invoke(native, runtime, "k", "read", "topic", "--task", "t1", log_root=log_root)
    assert metadata(read)["status"] == "read"
    assert "archived body" not in read.stdout
    shown = invoke(native, runtime, "k", "read", "topic", "--task", "t1", "--show", log_root=log_root)
    assert shown.stdout.splitlines()[1:] == ["archived body"]
    result = invoke(native, runtime, "k", "search", "--query", "topic", log_root=log_root)
    assert result.returncode == 0, result.stderr
    records = json.loads(result.stdout)["results"]
    assert any(record["content_digest"] == "sha256:" + hashlib.sha256(archived.read_bytes()).hexdigest() for record in records)
    assert "archived body" not in result.stdout


def test_invalid_request_and_existing_content_are_preserved(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    request = runtime / "spool/private-feedback/sync-request.json"
    request.parent.mkdir(parents=True)
    request.write_bytes(b'{"schema":"wrong"}\n')
    result = invoke(native, runtime, "k", "sync")
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "sync_request_invalid"
    assert request.read_bytes() == b'{"schema":"wrong"}\n'
    request.unlink()  # The test owns this invalid fixture, not the product.
    metadata(invoke(native, runtime, "k", "add", "topic", "first"))
    candidate = runtime / "spool/private-feedback/knowledge/topics/topic/candidate.md"
    before = candidate.read_bytes()
    result = invoke(native, runtime, "k", "add", "topic", "different")
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "content_conflict"
    assert candidate.read_bytes() == before


@contextmanager
def independent_lock(runtime: Path) -> Iterator[Path]:
    """Hold the host protocol lock without importing product implementation."""
    path = runtime / "spool/.private-feedback.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_native_writer_waits_for_independent_host_lock(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    record_root = runtime / "spool/private-feedback"
    writer = None
    try:
        with independent_lock(runtime) as lock_path:
            writer = subprocess.Popen(
                [native, "f", "add", "concurrent", "new bytes", "--runtime-root", str(runtime)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            deadline = time.monotonic() + 5
            while not record_root.is_dir() and writer.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert record_root.is_dir(), "writer did not reach the spool boundary"
            with pytest.raises(subprocess.TimeoutExpired):
                writer.wait(timeout=0.2)
            assert not (record_root / "feedback/concurrent").exists()
        stdout, stderr = writer.communicate(timeout=5)
        assert writer.returncode == 0, stderr
        assert "new bytes" not in stdout + stderr
        assert (record_root / "feedback/concurrent").is_dir()
        assert (record_root / "sync-request.json").is_file()
        assert lock_path.read_bytes() == b"\0"
    finally:
        if writer is not None and writer.poll() is None:
            writer.kill()
            writer.communicate()


def test_concurrent_records_share_one_valid_request(native: str, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    writers = [
        subprocess.Popen(
            [native, "f", "add", f"topic-{index}", f"record-{index}", "--runtime-root", str(runtime)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for index in range(4)
    ]
    try:
        for writer in writers:
            stdout, stderr = writer.communicate(timeout=10)
            assert writer.returncode == 0, stderr
            assert "record-" not in stdout + stderr
        records = list((runtime / "spool/private-feedback/feedback").rglob("*.md"))
        assert len(records) == 4
        request = json.loads((runtime / "spool/private-feedback/sync-request.json").read_text())
        assert request["schema"] == SCHEMA
        assert request["operation"] == "sync"
    finally:
        for writer in writers:
            if writer.poll() is None:
                writer.kill()
                writer.communicate()
