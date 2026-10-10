"""Resident controller state, task, tool, and eval contracts."""

from __future__ import annotations

import json
import fcntl
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from conftest import materialize_source_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

import tools.runtime.container.bootstrap_runtime as bootstrap_runtime_module  # noqa: E402
from tools.runtime.container.bootstrap_runtime import (  # noqa: E402
    BootstrapError,
    BootstrapRuntime,
    RuntimePaths,
    _container_source_identity,
    _container_request_environment,
    build_parser,
    run,
)
from tools.runtime.archive.runtime_exchange_cleanup import clear_exchange  # noqa: E402


@pytest.fixture(autouse=True)
def resident_private_log_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give controller operations their explicitly mounted private-log surface."""
    private_log = tmp_path / "private-log"
    private_log.mkdir()
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )


@pytest.mark.parametrize(
    ("remote", "normalized"),
    (
        (
            "git@github.com:iwashita-nozomu/agent-canon.git",
            "github.com/iwashita-nozomu/agent-canon",
        ),
        (
            "ssh://git@github.com/iwashita-nozomu/agent-canon.git",
            "github.com/iwashita-nozomu/agent-canon",
        ),
        (
            "https://reader:credential@example.com:8443/owner/repo.git",
            "example.com/owner/repo",
        ),
        (
            "https://github.com/iwashita-nozomu/agent-canon.GIT",
            "github.com/iwashita-nozomu/agent-canon",
        ),
    ),
)
def test_container_source_identity_matches_canonical_remote_normalization(
    remote: str, normalized: str
) -> None:
    """The resident identity operation delegates to the canonical resolver."""
    from tools.runtime.archive.log_repository_identity import (
        stable_source_repository_id,
    )

    result = _container_source_identity(remote)
    repository_id = stable_source_repository_id(remote)
    assert result == {
        "schema": "agent-canon.source-identity.v1",
        "normalized_remote": normalized,
        "repository_id": repository_id,
        "stable_branch": f"logs/{repository_id}",
    }


def test_container_source_identity_preserves_live_agent_canon_branch() -> None:
    """The current AgentCanon source identity remains on its existing branch."""
    result = _container_source_identity(
        "git@github.com:iwashita-nozomu/agent-canon.git"
    )
    assert result["stable_branch"] == (
        "logs/github.com-iwashita-nozomu-agent-canon-9680c2230417944f4dd780e2"
    )


def test_source_identity_operation_has_no_runtime_side_effects(tmp_path: Path) -> None:
    """The internal identity operation needs neither state nor network access."""
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(tmp_path),
            "source-identity",
            "--remote",
            "git@github.com:iwashita-nozomu/agent-canon.git",
        ]
    )
    assert run(args)["stable_branch"] == (
        "logs/github.com-iwashita-nozomu-agent-canon-9680c2230417944f4dd780e2"
    )


def test_direct_container_links_read_tracked_skills_without_pythonpath(
    tmp_path: Path,
) -> None:
    """Direct controller imports can resolve the tracked public skill directory."""
    control = tmp_path / "control"
    runtime = control / "runtime"
    control.mkdir()
    probe = """
import importlib.util
import json
import sys
from pathlib import Path

controller_path, repository_root, control_root, runtime_root = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("agent_canon_bootstrap_runtime", controller_path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
manager = module.BootstrapRuntime(
    control_root,
    runtime_root,
    repository_root=repository_root,
)
links = manager._managed_links()
public = [entry for entry in links if entry["surface"] == "skills"]
print(json.dumps({"sources": [entry["source"] for entry in public]}))
"""
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
            str(REPOSITORY_ROOT / "tools/runtime/container/bootstrap_runtime.py"),
            str(REPOSITORY_ROOT),
            str(control),
            str(runtime),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "sources": [str(REPOSITORY_ROOT / ".codex/personal/skills")]
    }
    assert not (runtime / "container-runtime" / "skill-projection").exists()


def test_source_identity_accepts_transport_variants_and_rejects_other_repo() -> None:
    """The host comparison can accept equivalent URLs without merging repositories."""
    equivalent = (
        "git@github.com:iwashita-nozomu/agent-canon.git",
        "ssh://git@github.com/iwashita-nozomu/agent-canon",
        "https://reader:credential@github.com:443/iwashita-nozomu/agent-canon.git",
    )
    identities = {
        _container_source_identity(remote)["repository_id"] for remote in equivalent
    }
    assert len(identities) == 1
    assert (
        _container_source_identity(
            "https://github.com/iwashita-nozomu/agent-canon-log.git"
        )["repository_id"]
        not in identities
    )


def test_remote_identity_mode_never_accepts_source_override() -> None:
    """Generic log remotes return only normalized identity and no branch override."""
    remote = "https://reader:credential@github.com:443/iwashita-nozomu/agent-canon.git"
    identity = _container_source_identity(remote, mode="remote")
    assert identity == {
        "schema": "agent-canon.remote-identity.v1",
        "normalized_remote": "github.com/iwashita-nozomu/agent-canon",
    }
    with pytest.raises(BootstrapError, match="source_repository_id_invalid"):
        _container_source_identity(remote, "unexpected", mode="remote")


def test_source_identity_override_is_validated_only_for_source_mode() -> None:
    """A valid source override is accepted, while a mismatch rejects the branch."""
    remote = "git@github.com:iwashita-nozomu/agent-canon.git"
    repository_id = _container_source_identity(remote)["repository_id"]
    assert _container_source_identity(remote, repository_id)["stable_branch"].endswith(
        repository_id
    )
    with pytest.raises(BootstrapError, match="source_repository_id_mismatch"):
        _container_source_identity(remote, "wrong-source-id")


def test_source_override_does_not_constrain_distinct_log_repository() -> None:
    """Source branch identity and the separate private log remote stay independent."""
    source = "git@github.com:iwashita-nozomu/agent-canon.git"
    source_id = _container_source_identity(source)["repository_id"]
    log = _container_source_identity(
        "https://reader:credential@github.com:443/iwashita-nozomu/agent-canon-log.git",
        mode="remote",
    )
    source_result = _container_source_identity(source, source_id, mode="source")
    assert source_result["stable_branch"].endswith(source_id)
    assert log["normalized_remote"] == "github.com/iwashita-nozomu/agent-canon-log"
    assert log["normalized_remote"] != source_result["normalized_remote"]


def runtime(
    tmp_path: Path,
    name: str = "runtime",
    *,
    repository_root: Path | None = None,
) -> BootstrapRuntime:
    """Keep control state temporary while selecting the source tree explicitly."""
    control = tmp_path / "control"
    control.mkdir()
    source = repository_root or materialize_source_fixture(tmp_path)
    return BootstrapRuntime(control, control / name, repository_root=source)


def test_global_skill_projection_is_a_directory_link() -> None:
    """The host adapter owns one complete skills directory link."""
    adapter = (REPOSITORY_ROOT / "bootstrap/host/lifecycle/entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert 'ln -s -- "$skill_source_root" "$skills_link"' in adapter
    assert 'for source in "$skill_source_root"/*' not in adapter
    assert "_migrate_legacy_prompt_skill" not in adapter


def test_resident_state_lock_cannot_be_bypassed_by_environment_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The controller always acquires its state lock before mutation."""
    manager = runtime(tmp_path)
    flock_calls: list[int] = []
    monkeypatch.setenv("AGENT_CANON_LOCK_HELD", "1")
    monkeypatch.setattr(
        bootstrap_runtime_module.fcntl,
        "flock",
        lambda _fd, operation: flock_calls.append(operation),
    )

    with manager.locked():
        pass

    assert flock_calls == [fcntl.LOCK_EX, fcntl.LOCK_UN]




def test_runtime_paths_preserve_host_roots_and_fixed_container_destinations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve the resident paths from its mounted runtime surfaces."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    paths = RuntimePaths(control, runtime_root)

    assert paths.codex_home == runtime_root / "codex-home"
    assert paths.spool == runtime_root / "spool"
    assert paths.archive == runtime_root / "archive"
    assert paths.cache == runtime_root / "cache"
    assert paths.container_runtime == runtime_root / "container-runtime"

    exchange = tmp_path / "exchange"
    host_surfaces = {
        "CODEX_HOME": tmp_path / "codex-home",
        "SPOOL": tmp_path / "spool",
        "ARCHIVE": tmp_path / "archive",
        "CACHE": tmp_path / "cache",
    }
    monkeypatch.setenv("AGENT_CANON_EXCHANGE_ROOT", str(exchange))
    for name, path in host_surfaces.items():
        monkeypatch.setenv(f"AGENT_CANON_HOST_{name}_ROOT", str(path))

    assert paths.codex_home == host_surfaces["CODEX_HOME"]
    assert paths.spool == host_surfaces["SPOOL"]
    assert paths.archive == host_surfaces["ARCHIVE"]
    assert paths.cache == host_surfaces["CACHE"]
    assert paths.container_runtime == exchange


























def _admit_process_owned_task(
    manager: BootstrapRuntime, task_id: str, target: Path
) -> tuple[dict[str, Any], int]:
    """Admit one runtime-owned worker and retain its process lease descriptor."""
    with manager.locked():
        state = manager._read_state()
        record, lease_fd = manager._admit_task_locked(
            state, task_id, target_root=target, process_owned=True
        )
    assert lease_fd is not None
    return record, lease_fd


def _run_process_owned_worker_controller(
    manager: BootstrapRuntime,
    task_id: str,
    target: Path,
    ready_file: Path,
) -> None:
    """Spawn one resident worker that keeps its admitted process lease."""
    _, lease_fd = _admit_process_owned_task(manager, task_id, target)
    try:
        bootstrap_runtime_module._run_resident_command(
            [
                "/bin/sh",
                "-c",
                'printf "%s\\n" "$$" > "$READY_FILE"; exec /bin/sleep 30',
            ],
            cwd=str(target),
            environment={"READY_FILE": str(ready_file)},
            timeout=60,
            pass_fds=(lease_fd,),
        )
    finally:
        os.close(lease_fd)


def _ready_runtime_with_target(
    tmp_path: Path, *, repository_root: Path | None = None
) -> tuple[BootstrapRuntime, Path]:
    """Build the minimum resident state for task lease tests."""
    manager = runtime(tmp_path, repository_root=repository_root)
    target = tmp_path / "target"
    target.mkdir()
    manager._ensure_layout()
    state = manager._new_state()
    state.update(state="ready", generation_counter=1, current_generation="generation-0001")
    target_record = manager._target_record(target, "read-only")
    state["targets"] = {target_record["digest"]: target_record}
    resources = manager._resource_records()
    resources["image"].update(
        {"id": "sha256:" + "a" * 64, "state": "present"}
    )
    resources["container"].update({"id": "resident", "state": "running"})
    state["resources"] = resources
    state["generations"]["generation-0001"] = {
        "image_id": resources["image"]["id"],
        "image_ref": resources["image"]["tag"],
        "targets": dict(state["targets"]),
        "state": "current",
    }
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    return manager, target


def test_resident_exec_passes_process_lease_to_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local resident worker receives the FD that protects its task lease."""
    lease_path = tmp_path / "process-lease.lock"
    lease_fd = os.open(lease_path, os.O_CREAT | os.O_RDWR, 0o600)
    observed: dict[str, tuple[int, ...]] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["pass_fds"] = tuple(kwargs["pass_fds"])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(bootstrap_runtime_module.subprocess, "run", fake_run)
    try:
        result = bootstrap_runtime_module._run_resident_command(
            ["worker"],
            cwd="/",
            timeout=5,
            pass_fds=(lease_fd,),
        )
    finally:
        os.close(lease_fd)

    assert result.returncode == 0
    assert observed["pass_fds"] == (lease_fd,)


def test_process_lease_survives_controller_death_until_worker_exits(
    tmp_path: Path
) -> None:
    """A live child keeps its lease after controller death until admission recovers."""
    manager, target = _ready_runtime_with_target(tmp_path)
    task_id = "exec-controller-death"
    ready_file = tmp_path / "worker.pid"
    controller = multiprocessing.get_context("fork").Process(
        target=_run_process_owned_worker_controller,
        args=(manager, task_id, target, ready_file),
    )
    worker_pid: int | None = None
    worker_stop_sent = False
    next_task_admitted = False

    def ready_worker_pid() -> int | None:
        try:
            value = ready_file.read_text(encoding="ascii").strip()
        except OSError:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    controller.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            worker_pid = ready_worker_pid()
            if worker_pid is not None:
                break
            if not controller.is_alive():
                break
            time.sleep(0.01)
        assert worker_pid is not None, "resident worker did not publish its PID"

        controller_pid = controller.pid
        assert controller_pid is not None
        os.kill(controller_pid, signal.SIGKILL)
        controller.join(timeout=5)
        assert not controller.is_alive(), "controller did not exit after SIGKILL"
        assert controller.exitcode == -signal.SIGKILL
        os.kill(worker_pid, 0)

        with pytest.raises(BootstrapError) as live_worker:
            manager.admit_task("exec-next", target_root=target)
        assert live_worker.value.code == "target_busy"
        state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
        assert state["tasks"][task_id]["state"] == "active"
        assert state["tasks"][task_id]["pinned"] is True

        try:
            os.kill(worker_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        worker_stop_sent = True
        deadline = time.monotonic() + 5
        while True:
            try:
                result = manager.admit_task("exec-next", target_root=target)
            except BootstrapError as exc:
                if exc.code != "target_busy" or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
            else:
                next_task_admitted = True
                break

        assert result["code"] == "task_reserved"
        state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
        assert state["tasks"][task_id]["state"] == "cancelled"
        assert state["tasks"][task_id]["outcome"] == "terminated"
        assert state["tasks"][task_id]["pinned"] is False
        assert state["tasks"]["exec-next"]["state"] == "active"
    finally:
        if worker_pid is None and controller.is_alive():
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                worker_pid = ready_worker_pid()
                if worker_pid is not None or not controller.is_alive():
                    break
                time.sleep(0.01)
        if controller.is_alive():
            controller_pid = controller.pid
            if controller_pid is not None:
                os.kill(controller_pid, signal.SIGKILL)
            controller.join(timeout=5)
        if worker_pid is not None and not worker_stop_sent:
            try:
                os.kill(worker_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            worker_stop_sent = True
        if worker_pid is not None:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                lease_fd = manager._open_task_process_lease(task_id)
                if lease_fd is not None:
                    os.close(lease_fd)
                    break
                time.sleep(0.01)
        if next_task_admitted:
            manager.release_task("exec-next")


def test_dead_process_task_lease_is_reconciled_before_next_admission(
    tmp_path: Path
) -> None:
    """An unlocked exec lease is released before it can keep its target busy."""
    manager, target = _ready_runtime_with_target(tmp_path)
    record, lease_fd = _admit_process_owned_task(manager, "exec-old", target)
    os.close(lease_fd)

    result = manager.admit_task("exec-next", target_root=target)

    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert record["lease_kind"] == "process"
    assert result["code"] == "task_reserved"
    assert state["tasks"]["exec-old"]["state"] == "cancelled"
    assert state["tasks"]["exec-old"]["outcome"] == "terminated"
    assert state["tasks"]["exec-old"]["pinned"] is False
    assert state["tasks"]["exec-next"]["state"] == "active"
    manager.release_task("exec-next")


def test_live_process_task_lease_and_manual_release_stay_protected(
    tmp_path: Path
) -> None:
    """A held worker lock blocks both admission and explicit task release."""
    manager, target = _ready_runtime_with_target(tmp_path)
    record, lease_fd = _admit_process_owned_task(manager, "exec-live", target)
    try:
        with pytest.raises(BootstrapError, match="target_busy"):
            manager.admit_task("exec-next", target_root=target)
        with pytest.raises(BootstrapError, match="task_process_active"):
            manager.release_task("exec-live", outcome="terminated")

        state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
        assert state["tasks"][record["id"]]["state"] == "active"
        assert state["tasks"][record["id"]]["pinned"] is True
    finally:
        os.close(lease_fd)


def test_manual_task_lease_remains_persistent_without_process_marker(
    tmp_path: Path
) -> None:
    """Caller-owned reservations remain pinned until their explicit release."""
    manager, target = _ready_runtime_with_target(tmp_path)
    receipt = manager.admit_task("caller-lease", target_root=target)

    with pytest.raises(BootstrapError, match="target_busy"):
        manager.admit_task("exec-next", target_root=target)

    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert "lease_kind" not in receipt["details"]["task"]
    assert state["tasks"]["caller-lease"]["state"] == "active"
    assert state["tasks"]["caller-lease"]["pinned"] is True
    manager.release_task("caller-lease")


def test_closed_admission_does_not_reconcile_process_task_lease(
    tmp_path: Path
) -> None:
    """Closed lifecycle states reject before reconciliation mutates task state."""
    manager, target = _ready_runtime_with_target(tmp_path)
    record, lease_fd = _admit_process_owned_task(manager, "exec-old", target)
    os.close(lease_fd)
    with manager.locked():
        state = manager._read_state()
        state["state"] = "stopped"
        manager._write_state(state)

    with pytest.raises(BootstrapError, match="task_admission_closed"):
        manager.admit_task("exec-next", target_root=target)

    after = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert after["tasks"][record["id"]]["state"] == "active"
    assert after["tasks"][record["id"]]["pinned"] is True










def test_container_control_maps_structured_tool_request_to_registered_mounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forward only mapped tool environment and the registered target path."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    target = tmp_path / "target"
    private_log = tmp_path / "agent-canon-log"
    control.mkdir()
    target.mkdir()
    private_log.mkdir()
    exchange = runtime_root / "exchange"
    codex_home = runtime_root / "codex-home"
    spool = runtime_root / "spool"
    archive = runtime_root / "archive"
    cache = runtime_root / "cache"
    for path in (exchange, codex_home, spool, archive, cache):
        path.mkdir(parents=True)
        path.chmod(0o700)
    monkeypatch.setenv("AGENT_CANON_EXCHANGE_ROOT", str(exchange))
    monkeypatch.setenv("AGENT_CANON_HOST_CODEX_HOME_ROOT", str(codex_home))
    monkeypatch.setenv("AGENT_CANON_HOST_SPOOL_ROOT", str(spool))
    monkeypatch.setenv("AGENT_CANON_HOST_ARCHIVE_ROOT", str(archive))
    monkeypatch.setenv("AGENT_CANON_HOST_CACHE_ROOT", str(cache))
    monkeypatch.setenv("AGENT_CANON_PRIVATE_LOG_ROOT", str(private_log))
    monkeypatch.setenv("AGENT_CANON_HOST_PRIVATE_LOG", str(private_log))
    # The autouse fixture redirects filesystem checks; this oracle separately
    # verifies the fixed path passed to a resident worker.
    monkeypatch.setattr(
        bootstrap_runtime_module,
        "PRIVATE_LOG_DESTINATION",
        "/var/lib/agent-canon/private-log",
    )
    monkeypatch.setattr(
        BootstrapRuntime,
        "private_log_root",
        property(lambda _manager: private_log),
    )
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    manager._ensure_layout()
    digest = "target-structured"
    target_record = {
        "digest": digest,
        "host_root": str(target),
        "root": f"/targets/{digest}",
        "mode": "read-only",
    }
    state = manager._new_state()
    state.update(
        {
            "state": "ready",
            "targets": {digest: target_record},
            "resources": manager._resource_records(),
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)

    output_root = runtime_root / "reports"
    environment = {
        "PATH": "/usr/bin:/bin",
        "AGENT_CANON_SOURCE_ROOT": str(REPOSITORY_ROOT),
        "AGENT_CANON_ROOT": str(REPOSITORY_ROOT),
        "AGENT_CANON_DISPATCH_ENTRY_ID": "generate-agent-runtime-dashboard",
        "AGENT_CANON_DISPATCH_RUNTIME": "python",
        "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
        "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
        "AGENT_CANON_TARGET_ROOT": str(target),
        "AGENT_CANON_TASK_ROOT": str(target),
        "AGENT_CANON_OUTPUT_ROOT": str(output_root),
        "AGENT_CANON_HOOK_ARCHIVE_DIR": str(private_log),
    }
    request = {
        "schema": "agent-canon.tool-exec-request.v1",
        "tool_id": "generate-agent-runtime-dashboard",
        "argv": ["python3", "eval/producers/generate_agent_runtime_dashboard.py"],
        "child_args": ["--root", ".", "--api-out", "reports/api.json"],
        "source_root": str(REPOSITORY_ROOT),
        "cwd": str(target),
        "cwd_policy": "target-root",
        "target_root": str(target),
        "environment": environment,
        "stdin": "inherited",
        "stdout": "inherited",
        "stderr": "inherited",
        "exit": "propagate",
        "signal": "propagate",
        "side_effect": "external-artifact",
        "output_root": str(output_root),
        "written_paths": [],
    }
    captured: dict[str, Any] = {}

    def fake_tool_run(
        self: BootstrapRuntime,
        catalog_id: str,
        argv: list[str],
        *,
        root: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        captured.update(
            {
                "catalog_id": catalog_id,
                "argv": argv,
                "root": root,
                "environment": environment,
            }
        )
        return {"code": "completed"}

    monkeypatch.setattr(BootstrapRuntime, "tool_run", fake_tool_run)
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime_root),
            "exec",
            "--target-digest",
            digest,
            "--request-json",
            json.dumps(request),
        ]
    )

    result = run(args)

    assert result == {"code": "completed"}
    assert captured["catalog_id"] == "generate-agent-runtime-dashboard"
    assert captured["root"] == Path(f"/targets/{digest}")
    mapped = captured["environment"]
    assert mapped["AGENT_CANON_SOURCE_ROOT"] == "/opt/agent-canon/source"
    assert mapped["AGENT_CANON_ROOT"] == "/opt/agent-canon/source"
    assert mapped["AGENT_CANON_RUNTIME_ROOT"] == "/var/lib/agent-canon/runtime"
    assert mapped["AGENT_CANON_CONTROL_PARENT_ROOT"] == "/var/lib/agent-canon"
    assert mapped["AGENT_CANON_TARGET_ROOT"] == f"/targets/{digest}"
    assert mapped["AGENT_CANON_TASK_ROOT"] == f"/targets/{digest}"
    assert mapped["AGENT_CANON_OUTPUT_ROOT"] == "/var/lib/agent-canon/runtime/reports"
    assert mapped["AGENT_CANON_HOOK_ARCHIVE_DIR"] == "/var/lib/agent-canon/private-log"
    assert "AWS_SECRET_ACCESS_KEY" not in mapped


def test_container_control_rejects_unallowlisted_structured_tool_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Credentials cannot cross the structured request boundary."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    target = tmp_path / "target"
    control.mkdir()
    target.mkdir()
    private_log = control / "private-log"
    private_log.mkdir()
    # Preserve the resident mount precondition while testing the request filter.
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    manager._ensure_layout()
    digest = "target-secret"
    target_record = {
        "digest": digest,
        "host_root": str(target),
        "root": f"/targets/{digest}",
        "mode": "read-only",
    }
    state = manager._new_state()
    state.update(
        {
            "state": "ready",
            "targets": {digest: target_record},
            "resources": manager._resource_records(),
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)
    request = {
        "schema": "agent-canon.tool-exec-request.v1",
        "tool_id": "route",
        "argv": ["python3", "tools/agent/orchestration/route.py"],
        "child_args": ["--help"],
        "source_root": str(REPOSITORY_ROOT),
        "cwd": str(target),
        "cwd_policy": "target-root",
        "target_root": str(target),
        "environment": {
            "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
            "AWS_SECRET_ACCESS_KEY": "must-not-cross-boundary",
        },
        "stdin": "inherited",
        "stdout": "inherited",
        "stderr": "inherited",
        "exit": "propagate",
        "signal": "propagate",
        "side_effect": "read-only",
        "output_root": None,
        "written_paths": [],
    }
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime_root),
            "exec",
            "--target-digest",
            digest,
            "--request-json",
            json.dumps(request),
        ]
    )

    with pytest.raises(BootstrapError, match="invalid_exec_request"):
        run(args)


def test_codex_launch_binds_session_root_to_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex receives a session root below the bootstrap-owned runtime."""
    manager = runtime(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    capture = tmp_path / "codex-env.json"
    executable = tmp_path / "fake-codex.py"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "Path(os.environ['CAPTURE']).write_text(json.dumps({\n"
        "  'session_root': os.environ.get('AGENT_CANON_CODEX_SESSION_ROOT'),\n"
        "  'runtime_root': os.environ.get('AGENT_CANON_RUNTIME_ROOT'),\n"
        "}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("AGENT_CANON_CODEX", str(executable))
    monkeypatch.setenv("CAPTURE", str(capture))
    manager.codex_launch(project)

    payload = json.loads(capture.read_text(encoding="utf-8"))
    assert payload == {
        "session_root": str(manager.paths.codex_home / "sessions"),
        "runtime_root": str(manager.paths.runtime_root),
    }
    assert (manager.paths.codex_home / "sessions").is_dir()


def test_structured_tool_environment_rejects_private_log_self_claim(
    tmp_path: Path,
) -> None:
    """A request cannot replace the host-owned private-log source identity."""
    source = tmp_path / "agent-canon"
    target = tmp_path / "target"
    runtime_root = tmp_path / "runtime"
    control = tmp_path / "control"
    private_log = tmp_path / "agent-canon-log"
    wrong_log = tmp_path / "other-log"
    for path in (source, target, runtime_root, control, private_log, wrong_log):
        path.mkdir()
    request = {
        "target_root": str(target),
        "environment": {
            "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
            "AGENT_CANON_HOOK_ARCHIVE_DIR": str(wrong_log),
        },
        "output_root": None,
    }

    with pytest.raises(
        BootstrapError, match="archive path does not match private log mount"
    ):
        _container_request_environment(
            request,
            container_target=Path("/targets/target"),
            source_root=source,
            host_runtime=runtime_root,
            host_control=control,
            host_private_log=private_log,
        )


def test_exec_preserves_nonzero_command_exit_and_redacts_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep command exit status while storing only redacted stream evidence."""
    manager, target = _ready_runtime_with_target(tmp_path)
    stderr = "terminal-diagnostic api_key=canary " + "x" * 700
    monkeypatch.setenv("AGENT_CANON_CONTAINER_ID", "resident")
    monkeypatch.setattr(
        bootstrap_runtime_module.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 7, stdout="", stderr=stderr
        ),
    )
    with pytest.raises(BootstrapError) as failure:
        manager.exec(target, ["agent-canon", "fail"])
    assert failure.value.code == "tool_failed"
    assert failure.value.evidence["exit"] == 7
    assert "canary" not in failure.value.evidence["stderr_preview"]
    assert "<redacted>" in failure.value.evidence["stderr_preview"]
    assert "terminal-diagnostic" in failure.value.evidence["stderr_preview"]
    assert failure.value.evidence["stderr_truncated"] is True
    receipt = json.loads(
        Path(failure.value.evidence["receipt_path"]).read_text(encoding="utf-8")
    )
    assert "canary" not in receipt["details"]["stderr_preview"]
    assert "<redacted>" in receipt["details"]["stderr_preview"]


@pytest.mark.parametrize("argv", [["python3", "-m", "pytest"], ["ruff", "format"]])
def test_exec_accepts_native_commands_for_standalone_source(argv: list[str]) -> None:
    """A source topic checkout uses the resident despite a different install path."""
    bootstrap_runtime_module._validate_tool_plane_argv(
        REPOSITORY_ROOT, REPOSITORY_ROOT.parent / "installed-source", argv
    )


def test_exec_rejects_project_commands_before_container_admission(
    tmp_path: Path,
) -> None:
    """The shared tool plane cannot become a project test environment."""
    manager = runtime(tmp_path)
    target = tmp_path / "project"
    target.mkdir()
    with pytest.raises(BootstrapError) as failure:
        manager.exec(target, ["python3", "-m", "pytest"])
    assert failure.value.code == "tool_plane_command_rejected"
    assert not manager.paths.state.exists()
    assert not manager.paths.tasks.exists()






def test_container_rollback_restores_previous_targets_and_generation_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resident rollback applies the host-provided previous target manifest."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    control.mkdir()
    private_log = control / "private-log"
    private_log.mkdir()
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    manager._ensure_layout()
    current_root, previous_root = tmp_path / "current", tmp_path / "previous"
    current_root.mkdir()
    previous_root.mkdir()
    current_id = "sha256:candidate-image-1234567890"
    previous_id = "sha256:previous-image-0987654321"
    current_digest = "current-target"
    previous_digest = "previous-target"
    current_target = {
        "digest": current_digest,
        "host_root": str(current_root),
        "root": f"/targets/{current_digest}",
        "mode": "read-only",
    }
    previous_target = {
        "digest": previous_digest,
        "host_root": str(previous_root),
        "root": f"/targets/{previous_digest}",
        "mode": "read-only",
    }
    state = manager._new_state()
    state.update(
        {
            "state": "ready",
            "targets": {current_digest: current_target},
            "current_generation": "generation-current",
            "rollback_generation": "generation-previous",
            "generations": {
                "generation-current": {
                    "image_id": current_id,
                    "targets": {current_digest: current_target},
                    "state": "current",
                },
                "generation-previous": {
                    "image_id": previous_id,
                    "targets": {previous_digest: previous_target},
                    "state": "rollback",
                },
            },
            "resources": {
                "image": {"id": current_id, "state": "present", "owned": True},
                "container": {
                    "id": "container-current",
                    "state": "running",
                    "owned": True,
                },
            },
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    (runtime_root / "rollback-mounts.tsv").write_text(
        f"target\t{previous_digest}\t{previous_root}\t/targets/{previous_digest}\tread-only\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_ID", current_id)
    monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_ID", previous_id)
    monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_REF", previous_id)
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime_root),
            "rollback",
        ]
    )
    result = run(args)
    assert result["code"] == "previous_generation_restored"
    restored = json.loads((runtime_root / "state.json").read_text(encoding="utf-8"))
    assert restored["targets"] == {previous_digest: previous_target}
    active = restored["generations"][restored["current_generation"]]
    rollback = restored["generations"][restored["rollback_generation"]]
    assert active["targets"] == {previous_digest: previous_target}
    assert rollback["targets"] == {current_digest: current_target}
    assert (
        f"{previous_digest}\t{previous_root}\t/targets/{previous_digest}\tread-only"
        in (manager.paths.container_runtime / "mounts.tsv").read_text(encoding="utf-8")
    )


def test_container_restore_reads_mounted_target_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """State-only recovery reads the target backup through the runtime mount."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    control.mkdir()
    private_log = control / "private-log"
    private_log.mkdir()
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    manager._ensure_layout()
    candidate_root, restored_root = tmp_path / "candidate", tmp_path / "restored"
    candidate_root.mkdir()
    restored_root.mkdir()
    candidate_id = "sha256:candidate-image-1234567890"
    restored_id = "sha256:restored-image-0987654321"
    candidate_digest = "candidate-target"
    restored_digest = "restored-target"
    candidate_target = {
        "digest": candidate_digest,
        "host_root": str(candidate_root),
        "root": f"/targets/{candidate_digest}",
        "mode": "read-only",
    }
    restored_target = {
        "digest": restored_digest,
        "host_root": str(restored_root),
        "root": f"/targets/{restored_digest}",
        "mode": "read-only",
    }
    state = manager._new_state()
    state.update(
        {
            "state": "ready",
            "targets": {candidate_digest: candidate_target},
            "current_generation": "generation-candidate",
            "rollback_generation": "generation-restored",
            "generations": {
                "generation-candidate": {
                    "image_id": candidate_id,
                    "targets": {candidate_digest: candidate_target},
                    "state": "current",
                }
            },
            "resources": {
                "image": {"id": candidate_id, "state": "present", "owned": True},
                "container": {
                    "id": "container-candidate",
                    "state": "running",
                    "owned": True,
                },
            },
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    backup = runtime_root / "restore-targets.tsv"
    backup.write_text(
        f"target\t{restored_digest}\t{restored_root}\t/targets/{restored_digest}\tread-only\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_ID", restored_id)
    monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_ID", candidate_id)
    monkeypatch.setenv(
        "AGENT_CANON_RESTORE_TARGETS_FILE",
        str(backup),
    )
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime_root),
            "restore",
        ]
    )
    result = run(args)
    assert result["code"] == "previous_generation_restored"
    restored = json.loads((runtime_root / "state.json").read_text(encoding="utf-8"))
    assert restored["targets"] == {restored_digest: restored_target}
    assert restored["generations"][restored["current_generation"]]["targets"] == {
        restored_digest: restored_target
    }
    assert restored["generations"][restored["rollback_generation"]]["targets"] == {
        candidate_digest: candidate_target
    }


def test_container_target_only_rollback_toggles_generations_without_image_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Target generation rollback uses one plan and preserves the image."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    control.mkdir()
    private_log = control / "private-log"
    private_log.mkdir()
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )
    image_id = "sha256:shared-image-1234567890"
    image_ref = "agent-canon-tools:shared"
    monkeypatch.setenv("AGENT_CANON_IMAGE_ID", image_id)
    monkeypatch.setenv("AGENT_CANON_IMAGE_REF", image_ref)
    monkeypatch.setenv("AGENT_CANON_CONTAINER_ID", "container-shared")
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    manager._ensure_layout()
    state = manager._new_state()
    state.update(
        {
            "state": "ready",
            "resources": {
                "image": {
                    "id": image_id,
                    "tag": image_ref,
                    "state": "present",
                    "owned": True,
                },
                "container": {
                    "id": "container-shared",
                    "state": "running",
                    "owned": True,
                },
            },
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    target_a, target_b = tmp_path / "target-a", tmp_path / "target-b"
    target_a.mkdir()
    target_b.mkdir()

    existing_no_symlink = bootstrap_runtime_module._existing_no_symlink

    def mounted_target(path: Path, *, field: str) -> Path:
        if path.parts[:2] == ("/", "targets"):
            return path
        return existing_no_symlink(path, field=field)

    monkeypatch.setattr(
        bootstrap_runtime_module, "_existing_no_symlink", mounted_target
    )
    monkeypatch.setattr(
        bootstrap_runtime_module.BootstrapRuntime,
        "_prune_stale_targets",
        lambda _self, _state: [],
    )

    def target_args(action: str, root: Path, digest: str) -> Any:
        monkeypatch.setenv("AGENT_CANON_TARGET_HOST_ROOT", str(root))
        monkeypatch.setenv("AGENT_CANON_TARGET_CONTAINER_ROOT", f"/targets/{digest}")
        monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)
        return build_parser().parse_args(
            [
                "--repository-root",
                str(REPOSITORY_ROOT),
                "--control-parent-root",
                str(control),
                "--runtime-root",
                str(runtime_root),
                "target",
                action,
                "--root",
                str(root),
                "--mode",
                "read-only",
            ]
        )

    run(target_args("add", target_a, "target-a"))
    run(target_args("add", target_b, "target-b"))
    plan = manager.paths.container_runtime / "rollback-plan.tsv"
    assert plan.is_file()
    assert "target-a" in plan.read_text(encoding="utf-8")

    def rollback_args() -> Any:
        monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_ID", image_id)
        monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_REF", image_ref)
        monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_ID", image_id)
        monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_REF", image_ref)
        return build_parser().parse_args(
            [
                "--repository-root",
                str(REPOSITORY_ROOT),
                "--control-parent-root",
                str(control),
                "--runtime-root",
                str(runtime_root),
                "rollback",
            ]
        )

    def mount_backup(digest: str, root: Path) -> None:
        (runtime_root / "rollback-mounts.tsv").write_text(
            f"target\t{digest}\t{root}\t/targets/{digest}\tread-only\n",
            encoding="utf-8",
        )

    mount_backup("target-a", target_a)
    first = run(rollback_args())
    first_state = json.loads((runtime_root / "state.json").read_text(encoding="utf-8"))
    assert first["code"] == "previous_generation_restored"
    assert set(first_state["targets"]) == {"target-a"}
    assert first_state["resources"]["image"]["id"] == image_id
    assert first_state["current_generation"] != first_state["rollback_generation"]
    assert "target-b" in plan.read_text(encoding="utf-8")

    mount_backup("target-b", target_b)
    second = run(rollback_args())
    second_state = json.loads((runtime_root / "state.json").read_text(encoding="utf-8"))
    assert second["code"] == "previous_generation_restored"
    assert set(second_state["targets"]) == {"target-b"}
    assert second_state["resources"]["image"]["id"] == image_id
    assert second_state["current_generation"] != first_state["current_generation"]


def test_container_target_record_keeps_host_validation_outside_resident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container target record checks only the mounted namespace."""
    control = tmp_path / "control"
    control.mkdir()
    manager = BootstrapRuntime(
        control, control / "runtime", repository_root=REPOSITORY_ROOT
    )
    host_root = tmp_path / "host-source"
    calls: list[tuple[Path, str]] = []

    def record_mount(path: Path, *, field: str) -> Path:
        calls.append((path, field))
        return path

    monkeypatch.setattr(bootstrap_runtime_module, "_existing_no_symlink", record_mount)
    target = manager._target_record(
        Path("/targets/target-digest"),
        "read-only",
        host_root=str(host_root),
        host_digest="target-digest",
    )

    assert target == {
        "root": "/targets/target-digest",
        "host_root": str(host_root),
        "mode": "read-only",
        "digest": "target-digest",
    }
    assert calls == [(Path("/targets/target-digest"), "mounted target root")]


def test_symlink_state_write_fails_closed(tmp_path: Path) -> None:
    """Refuse replacing a state symlink and preserve its outside target."""
    manager = runtime(tmp_path)
    manager._ensure_layout()
    state = manager._new_state()
    manager._write_state(state)
    manager.paths.state.unlink()
    outside = tmp_path / "outside"
    outside.write_text("keep", encoding="utf-8")
    manager.paths.state.symlink_to(outside)
    with pytest.raises(BootstrapError, match="symlink_path_rejected"):
        manager._write_state(state)
    assert outside.read_text(encoding="utf-8") == "keep"


def test_gc_high_water_keeps_current_rollback_and_unpublished_spool(
    tmp_path: Path
) -> None:
    """Expose LRU candidates without deleting protected unpublished state."""
    manager = runtime(tmp_path)
    manager._ensure_layout()
    state = manager._new_state()
    state["state"] = "ready"
    manager._write_state(state)
    manager.admit_task("task-a")
    manager.release_task("task-a")
    (manager.paths.runtime_root / "spool" / "pending").mkdir()
    # A dry run exposes LRU candidates but never removes a pinned/current/spool item.
    preview = manager.gc(dry_run=True)["details"]
    assert preview["preserved"]["unpublished_spool"] is True
    assert "task:task-a" in preview["candidates"]


def test_container_control_gc_delegates_to_runtime_gc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Container control returns the real runtime GC result."""
    calls: list[bool] = []
    expected = {"operation": "gc", "code": "runtime-gc-result"}

    def fake_gc(self: BootstrapRuntime, *, dry_run: bool = False) -> dict[str, Any]:
        calls.append(dry_run)
        return expected

    monkeypatch.setattr(BootstrapRuntime, "gc", fake_gc)
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(tmp_path),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "gc",
            "--dry-run",
        ]
    )
    assert run(args) is expected
    assert calls == [True]


def test_resident_gc_cleans_local_cache_without_host_resource_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resident GC cleans the mounted cache without reporting Host resources."""
    control = tmp_path / "control"
    control.mkdir()
    cache = tmp_path / "host-cache"
    private_log = tmp_path / "private-log"
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml")
        .read_text(encoding="utf-8")
        .replace("cache_quota_bytes = 4294967296", "cache_quota_bytes = 1"),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CANON_EXCHANGE_ROOT", str(tmp_path / "exchange"))
    monkeypatch.setenv("AGENT_CANON_HOST_CACHE_ROOT", str(cache))
    monkeypatch.setattr(
        bootstrap_runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log)
    )
    manager = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=REPOSITORY_ROOT,
        manifest_path=manifest,
    )
    state = manager._new_state()
    state["state"] = "ready"
    state["resources"] = {
        "image": {"id": "sha256:stale-image", "owned": True},
        "container": {"id": "container-live", "state": "running", "owned": True},
    }
    manager.paths.state.parent.mkdir(parents=True)
    manager.paths.state.write_text(json.dumps(state), encoding="utf-8")
    cache.mkdir()
    cached = cache / "stale"
    cached.write_text("remove me", encoding="utf-8")

    preview = manager.gc(dry_run=True)
    assert preview["code"] == "gc_plan"
    assert "idle_stop" not in preview["details"]
    assert "stale_images" not in preview["details"]
    assert cached.is_file()

    completed = manager.gc()
    assert completed["code"] == "gc_complete"
    assert "cache:stale" in completed["details"]["deleted"]
    assert not cached.exists()




def test_gc_enforces_archive_quota_only_without_unpublished_spool(
    tmp_path: Path
) -> None:
    """Prune a reproducible archive cache, but never while a spool is pending."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml")
        .read_text(encoding="utf-8")
        .replace(
            "archive_lease_quota_bytes = 2147483648", "archive_lease_quota_bytes = 1"
        ),
        encoding="utf-8",
    )
    control = tmp_path / "control"
    control.mkdir()
    fixture_source = materialize_source_fixture(tmp_path)
    manager = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=fixture_source,
        manifest_path=manifest,
    )
    manager._ensure_layout()
    archive_cache = manager.paths.runtime_root / "archive" / "agent-canon-log"
    archive_cache.mkdir()
    (archive_cache / "cache").write_text("published", encoding="utf-8")
    pending = manager.paths.runtime_root / "spool" / "pending"
    pending.mkdir()

    blocked = manager.gc()["details"]
    assert blocked["archive_high_water"] is True
    assert blocked["archive_cleanup_blocked_by_spool"] is True
    assert archive_cache.exists()

    pending.rmdir()
    cleaned = manager.gc()["details"]
    assert cleaned["archive_cleanup_blocked_by_spool"] is False
    assert "archive:agent-canon-log" in cleaned["deleted"]
    assert not archive_cache.exists()




def test_exchange_cleanup_unlinks_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    """The in-container cleanup cannot follow an exchange child symlink."""
    exchange = tmp_path / "exchange"
    outside = tmp_path / "outside"
    exchange.mkdir()
    outside.mkdir()
    protected = outside / "protected"
    protected.write_text("keep", encoding="utf-8")
    (exchange / "linked").symlink_to(outside, target_is_directory=True)

    assert clear_exchange(exchange) == (1, 0)
    assert protected.read_text(encoding="utf-8") == "keep"
    assert not (exchange / "linked").exists()


def test_exchange_cleanup_preserves_host_owned_entries_for_host_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A root-Host entry may remain until the following Host cleanup phase."""
    exchange = tmp_path / "exchange"
    host_owned = exchange / "host-owned"
    host_file = host_owned / "receipt"
    host_owned.mkdir(parents=True)
    host_file.write_text("host", encoding="utf-8")
    original_unlink = Path.unlink

    def deny_container_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == host_file:
            raise PermissionError("simulated root-Host ownership")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_container_unlink)

    assert clear_exchange(exchange) == (0, 1)
    assert host_file.read_text(encoding="utf-8") == "host"
    original_unlink(host_file)
    host_owned.rmdir()
    exchange.rmdir()
    assert not exchange.exists()




def test_parser_has_typed_exec_tool_codex_and_eval_routes() -> None:
    """Keep all documented typed parser routes available."""
    from tools.runtime.container.bootstrap_runtime import build_parser

    base = [
        "--repository-root",
        str(REPOSITORY_ROOT),
        "--control-parent-root",
        "/tmp",
        "--runtime-root",
        "/tmp/runtime",
    ]
    assert (
        build_parser()
        .parse_args(base + ["exec", "--root", "/tmp", "--", "true"])
        .operation
        == "exec"
    )
    assert (
        build_parser()
        .parse_args(base + ["tool", "run", "catalog.id", "--", "--help"])
        .tool_operation
        == "run"
    )
    assert (
        build_parser().parse_args(base + ["codex", "prepare"]).codex_operation
        == "prepare"
    )
    assert (
        build_parser()
        .parse_args(base + ["eval", "collect", "--root", "/tmp", "--run-id", "r1"])
        .eval_operation
        == "collect"
    )


def test_public_python_source_sync_route_is_removed() -> None:
    """Only the host shell owns source-sync; dead Python fallback is absent."""
    base = [
        "--repository-root",
        str(REPOSITORY_ROOT),
        "--control-parent-root",
        "/tmp",
        "--runtime-root",
        "/tmp/runtime",
    ]
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            base + ["sync", "--install-root", str(REPOSITORY_ROOT)]
        )
    controller = (
        REPOSITORY_ROOT / "tools/runtime/container/bootstrap_runtime.py"
    ).read_text(encoding="utf-8")
    assert "SourceSync" not in controller
    assert "source_sync_image_required" not in controller
    assert not (REPOSITORY_ROOT / "tools/agent_tools/source_sync.py").exists()


def test_source_sync_reader_uses_nested_directory_path() -> None:
    """The resident reads the host-mounted directory's nested state file."""
    source = (
        REPOSITORY_ROOT / "tools/runtime/container/bootstrap_runtime.py"
    ).read_text(encoding="utf-8")
    assert 'SOURCE_SYNC_DESTINATION = "/var/lib/agent-canon/source-sync"' in source
    assert 'return Path(SOURCE_SYNC_DESTINATION) / "source-sync.json"' in source
    assert 'return self.runtime_root / "source-sync" / "source-sync.json"' not in source


def test_container_control_uses_host_passed_state_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Container control writes state below the mounted host runtime only."""
    repository = tmp_path / "image-source"
    (repository / "bootstrap" / "host").mkdir(parents=True)
    (repository / "bootstrap" / "host" / "manifest.toml").write_bytes(
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml").read_bytes()
    )
    control = tmp_path / "state-volume"
    control.mkdir()
    mounted_runtime = control / "runtime"
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(mounted_runtime),
            "status",
        ]
    )
    manager = bootstrap_runtime_module._runtime_from_args(args)
    assert manager.paths.runtime_root == mounted_runtime
    assert manager.paths.state == mounted_runtime / "state.json"
    assert not (repository / ".runtime").exists()


def test_reconciliation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A source-only refresh keeps active work; image replacement clears it."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    exchange = control / "exchange"
    private_log = control / "private-log"
    control.mkdir()
    exchange.mkdir()
    exchange.chmod(0o700)
    private_log.mkdir()
    monkeypatch.setenv("AGENT_CANON_EXCHANGE_ROOT", str(exchange))
    monkeypatch.setenv("AGENT_CANON_CONTAINER_NAME", "agent-canon-test")
    monkeypatch.setenv("AGENT_CANON_IMAGE_ID", "sha256:" + "a" * 64)
    monkeypatch.setenv("AGENT_CANON_CONTAINER_ID", "container-test")
    monkeypatch.setattr(
        BootstrapRuntime,
        "private_log_root",
        property(lambda _manager: private_log),
    )
    monkeypatch.setattr(
        BootstrapRuntime, "_prune_stale_targets", lambda _manager, _state: []
    )
    monkeypatch.setattr(BootstrapRuntime, "_write_mounts", lambda *_args: None)
    monkeypatch.setattr(BootstrapRuntime, "_write_mount_manifest", lambda *_args: None)
    manager = BootstrapRuntime(control, runtime_root, repository_root=REPOSITORY_ROOT)
    state = manager._new_state()
    state.update(
        state="ready",
        active_task_count=1,
        tasks={"active": {"state": "active"}},
        targets={
            "target-a": {
                "host_root": str(tmp_path / "target-a"),
                "root": "/targets/target-a",
                "mode": "read-only",
            }
        },
        resources=manager._resource_records(),
    )
    manager._ensure_layout()
    manager._write_state(state)
    plan = exchange / "rollback-plan.tsv"
    plan.write_text("stale rollback plan\n", encoding="utf-8")
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(REPOSITORY_ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime_root),
            "update",
        ]
    )

    run(args)
    after_refresh = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert after_refresh["active_task_count"] == 1
    assert after_refresh["tasks"] == {"active": {"state": "active"}}
    assert not plan.exists()

    monkeypatch.setenv("AGENT_CANON_PREVIOUS_IMAGE_ID", "sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_CANON_PREVIOUS_IMAGE_REF", "agent-canon-tools:previous")
    run(args)
    after_replacement = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert after_replacement["active_task_count"] == 0
    assert after_replacement["tasks"] == {}
    assert plan.is_file()
    plan_text = plan.read_text(encoding="utf-8")
    assert "image-id\tsha256:" + "b" * 64 in plan_text
    assert "image-ref\tagent-canon-tools:previous" in plan_text
    assert (
        "mount\tmount\t" + str(tmp_path / "target-a") + "\t/targets/target-a\ttrue"
        in plan_text
    )

    legacy_state = json.loads(json.dumps(after_replacement))
    legacy_state["generations"][legacy_state["rollback_generation"]].pop("targets")
    bootstrap_runtime_module._container_materialize_rollback_plan(manager, legacy_state)
    assert "mount\tmount\t" + str(
        tmp_path / "target-a"
    ) + "\t/targets/target-a\ttrue" in plan.read_text(encoding="utf-8")


def test_eval_precondition_failure_creates_no_spool_or_exchange(
    tmp_path: Path
) -> None:
    """An unregistered eval target can be retried after registration."""
    manager = runtime(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
    (target / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=target, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Eval Fixture",
            "-c",
            "user.email=eval@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=target,
        check=True,
    )
    with pytest.raises(BootstrapError) as failure:
        manager.eval_collect(target, "precondition")
    assert failure.value.code == "target_not_registered"
    assert not (manager.paths.runtime_root / "spool" / "precondition").exists()
    assert not (
        manager.paths.container_runtime / "tasks" / "eval-precondition"
    ).exists()


def test_eval_collect_runs_existing_producers_and_prepares_sync_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resident executes both real producers and releases their task lease."""
    container_runtime_root = tmp_path / "container-runtime"
    exchange = container_runtime_root / "exchange"
    monkeypatch.setattr(
        bootstrap_runtime_module, "TOOL_SOURCE_DESTINATION", str(REPOSITORY_ROOT)
    )
    monkeypatch.setattr(
        bootstrap_runtime_module,
        "CONTAINER_RUNTIME_DESTINATION",
        str(container_runtime_root),
    )
    monkeypatch.setenv("AGENT_CANON_EXCHANGE_ROOT", str(exchange))
    monkeypatch.setenv("AGENT_CANON_CONTAINER_ID", "resident-test")

    manager, target = _ready_runtime_with_target(
        tmp_path, repository_root=REPOSITORY_ROOT
    )
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
    (target / "README.md").write_text("eval fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=target, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Eval Fixture",
            "-c",
            "user.email=eval@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=target,
        check=True,
    )
    state = manager._read_state()
    target_digest = next(iter(state["targets"]))
    container_target = f"/targets/{target_digest}"
    monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", target_digest)

    resident_command = bootstrap_runtime_module._run_resident_command

    def run_mounted_command(
        argv: list[str],
        *,
        cwd: str,
        environment: dict[str, str] | None = None,
        timeout: int,
        pass_fds: tuple[int, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        """Map only the resident's fixed target mount into this temp fixture."""
        mapped_argv = [
            str(target) if value == container_target else value for value in argv
        ]
        mapped_environment = dict(environment or {})
        for key in (
            "AGENT_CANON_TARGET_ROOT",
            "AGENT_CANON_TASK_ROOT",
            "GIT_CONFIG_VALUE_0",
        ):
            if mapped_environment.get(key) == container_target:
                mapped_environment[key] = str(target)
        return resident_command(
            mapped_argv,
            cwd=cwd,
            environment=mapped_environment,
            timeout=timeout,
            pass_fds=pass_fds,
        )

    monkeypatch.setattr(
        bootstrap_runtime_module, "_run_resident_command", run_mounted_command
    )
    run_id = "resident-eval-success"
    result = manager.eval_collect(target, run_id)

    assert result["code"] == "eval_spooled"
    collection = result["details"]["collection"]
    assert collection["status"] == "collected"
    assert collection["source_tree_unchanged"] is True
    assert {
        producer["name"]: producer["status"]
        for producer in collection["producer_matrix"]
    } == {
        "codex-agent-role": "pass",
        "workflow-selection": "pass",
    }
    spool = manager.paths.spool / run_id
    assert (spool / "eval-results").is_dir()
    assert (spool / "producer-logs").is_dir()
    assert collection["exported_files"]["eval_results"] > 0
    assert collection["exported_files"]["producer_logs"] > 0
    after_collection = manager._read_state()
    task = after_collection["tasks"][f"eval-{run_id}"]
    assert task["state"] == "completed"
    assert task["outcome"] == "completed"
    assert task["pinned"] is False
    assert after_collection["active_task_count"] == 0

    sync = manager.eval_sync_prepare(run_id)
    assert sync["code"] == "host_archive_requested"
    assert (spool / "sync-request.tsv").read_text(encoding="utf-8") == (
        "schema\tagent-canon.eval-sync-request.v1\n"
        "operation\tsync\n"
        "execution-plane\tagentcanon_tool_container\n"
        f"run-id\t{run_id}\n"
        f"target-digest\t{target_digest}\n"
        f"source-root\t{target}\n"
    )
