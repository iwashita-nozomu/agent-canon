"""Bootstrap tests use a stateful fake Docker executable, never Docker itself."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.agent_tools.bootstrap_runtime import (  # noqa: E402
    BootstrapError,
    BootstrapRuntime,
    DockerAdapter,
    sha256_bytes,
    validate_roots,
)


@pytest.fixture()
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DockerAdapter:
    """Return a Docker argv adapter backed by the fake daemon executable."""
    state = tmp_path / "docker-state.json"
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    return DockerAdapter(str(Path(__file__).with_name("fake_docker.py")))


def runtime(
    tmp_path: Path, fake_docker: DockerAdapter, name: str = "runtime"
) -> BootstrapRuntime:
    """Construct a runtime rooted inside the test-owned temporary directory."""
    control = tmp_path / "control"
    control.mkdir()
    return BootstrapRuntime(
        control, control / name, repository_root=REPOSITORY_ROOT, docker=fake_docker
    )


def test_explicit_roots_reject_escape_and_symlink_without_rootless_policy(
    tmp_path: Path,
) -> None:
    """Reject escape and symlink paths while allowing a root host UID."""
    control, outside = tmp_path / "control", tmp_path / "outside"
    control.mkdir()
    outside.mkdir()
    with pytest.raises(BootstrapError, match="runtime_root_escape"):
        validate_roots(control, outside / "runtime")
    link = control / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(BootstrapError, match="symlink_path_rejected"):
        validate_roots(control, link / "runtime")


def test_effective_root_is_allowed_but_manifest_container_uid_is_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Keep host UID policy separate from the non-root container policy."""
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    manager = runtime(tmp_path, fake_docker)
    assert manager.uid == 0
    assert manager.container_uid > 0 and manager.container_gid > 0


def test_install_tightens_preexisting_runtime_control_directories(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Receipts and task state never remain readable through a 0755 fixture."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    (runtime_root / "receipts").mkdir(parents=True)
    runtime_root.chmod(0o755)
    (runtime_root / "receipts").chmod(0o755)
    manager = BootstrapRuntime(
        control,
        runtime_root,
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )
    manager.install()
    assert runtime_root.stat().st_mode & 0o777 == 0o700
    assert (runtime_root / "receipts").stat().st_mode & 0o777 == 0o700


def test_install_start_status_readback_and_single_container(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Verify Docker argv and structural inspect readback for one container."""
    manager = runtime(tmp_path, fake_docker)
    installed = manager.install()
    assert installed["code"] == "installed"
    started = manager.start()
    assert started["after_state"] == "ready"
    status = manager.status()["details"]
    assert status["state"]["resources"]["container"]["state"] == "running"
    assert status["docker_container"]["health"] == "healthy"
    assert "Env" not in json.dumps(status)
    assert len(json.dumps(status)) < 5000
    install_receipt = json.loads(
        Path(installed["receipt_path"]).read_text(encoding="utf-8")
    )
    assert install_receipt["resource_ids"]["image"]["id"] is not None
    create = next(command for command in fake_docker.commands if command[1] == "create")
    assert (
        create.count("--user") == 1
        and create[create.index("--user") + 1].split(":")[0] != "0"
    )
    assert (
        sum(
            command[1:3] == ["container", "inspect"] for command in fake_docker.commands
        )
        >= 2
    )
    assert manager.paths.container_runtime.stat().st_mode & 0o7777 == 0o1777
    mount_specs = [
        create[index + 1] for index, item in enumerate(create) if item == "--mount"
    ]
    exchange = next(
        spec for spec in mount_specs if "dst=/var/lib/agent-canon/runtime" in spec
    )
    registry = next(
        spec
        for spec in mount_specs
        if "dst=/var/lib/agent-canon/mount-registry.toml" in spec
    )
    assert ",readonly" not in exchange
    assert registry.endswith(",readonly")
    assert str(manager.paths.state) not in exchange


def test_health_polling_waits_for_starting_container(
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Poll a starting health state instead of failing immediately."""
    monkeypatch.setenv("FAKE_DOCKER_HEALTH_POLLS", "2")
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.start()
    state = manager.status()["details"]["docker_container"]
    assert state["health"] == "healthy"
    assert (
        sum(
            command[1:3] == ["container", "inspect"] for command in fake_docker.commands
        )
        >= 4
    )


def test_health_timeout_quarantines_and_removes_container(
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop and quarantine a container that never reaches healthy."""
    monkeypatch.setenv("FAKE_DOCKER_HEALTH_POLLS", "1000")
    manifest = tmp_path / "manifest.toml"
    source = (REPOSITORY_ROOT / "bootstrap" / "manifest.toml").read_text(
        encoding="utf-8"
    )
    source = source.replace(
        "health_start_period_seconds = 10", "health_start_period_seconds = 0.03"
    )
    source = source.replace(
        "health_timeout_seconds = 5", "health_timeout_seconds = 0.03"
    )
    source = source.replace(
        "health_poll_interval_seconds = 0.2", "health_poll_interval_seconds = 0.01"
    )
    manifest.write_text(source, encoding="utf-8")
    control = tmp_path / "control"
    control.mkdir()
    manager = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=REPOSITORY_ROOT,
        manifest_path=manifest,
        docker=fake_docker,
    )
    manager.install()
    with pytest.raises(BootstrapError, match="container_health_timeout"):
        manager.start()
    state = manager.status()["details"]["state"]
    assert state["resources"]["container"]["state"] == "quarantined"
    assert fake_docker.inspect_container(state["resources"]["container"]["id"]) is None


def test_second_control_root_cannot_adopt_existing_runtime(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Refuse a state record owned by another explicit control root."""
    control = tmp_path / "control"
    control.mkdir()
    first = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )
    first.install()
    second = BootstrapRuntime(
        tmp_path,
        control / "runtime",
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )
    with pytest.raises(BootstrapError, match="shared_runtime_owned_elsewhere"):
        second.status()


def test_multi_target_registry_and_admission_race_guard(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Preserve multiple targets and close admission during updates."""
    manager = runtime(tmp_path, fake_docker)
    target_a = tmp_path / "a"
    target_b = tmp_path / "b"
    target_a.mkdir()
    target_b.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target_a)
    manager.target_add(target_b)
    state = manager.status()["details"]["state"]
    assert len(state["target_digests"]) == 2
    manager.admit_task("task-a", target_root=target_a)
    with pytest.raises(BootstrapError, match="mount_update_blocked"):
        manager.target_add(target_a)
    manager.release_task("task-a")


def test_candidate_registry_is_snapshotted_before_create_and_restored_on_failure(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Model file-bind inode capture for candidate and rollback containers."""
    manager = runtime(tmp_path, fake_docker)
    target_a, target_b = tmp_path / "a", tmp_path / "b"
    target_a.mkdir()
    target_b.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target_a)
    manager.target_add(target_b)
    old_registry = manager.paths.mounts.read_bytes()
    state_path = Path(os.environ["FAKE_DOCKER_STATE"])
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    container = next(iter(docker_state["containers"].values()))
    assert container["MountSnapshots"][
        "/var/lib/agent-canon/mount-registry.toml"
    ] == manager.paths.mounts.read_text(encoding="utf-8")
    with pytest.raises(BootstrapError, match="candidate_generation_unhealthy"):
        manager.target_add(target_a, health_ok=False)
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    container = next(iter(docker_state["containers"].values()))
    assert (
        container["MountSnapshots"]["/var/lib/agent-canon/mount-registry.toml"].encode()
        == old_registry
    )


def test_exec_and_tool_run_return_bounded_io_evidence_and_external_logs(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Preserve command output through redacted external logs and digests."""
    manager = runtime(tmp_path, fake_docker)
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
    manager.install()
    manager.start()
    manager.target_add(target)
    result = manager.exec(target, ["agent-canon", "--version"])
    details = result["details"]
    assert details["stdout_preview"] == "agent-canon 0.1.0\n"
    assert details["stdout_bytes"] == len(Path(details["stdout_log"]).read_bytes())
    assert details["stdout_digest"] == sha256_bytes(
        Path(details["stdout_log"]).read_bytes()
    )
    assert details["stderr_bytes"] == 0
    routed = manager.tool_run("route", ["--list"])
    assert "route output" in routed["details"]["stdout_preview"]
    assert routed["details"]["argv"][:3] == ["agent-canon-tool", "tool", "run"]


def test_exec_preserves_nonzero_command_exit_and_redacts_output(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Keep command exit status while storing only redacted stream evidence."""
    manager = runtime(tmp_path, fake_docker)
    target = tmp_path / "target"
    target.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target)
    with pytest.raises(BootstrapError) as failure:
        manager.exec(target, ["agent-canon", "fail"])
    assert failure.value.code == "tool_failed"
    assert failure.value.evidence["exit"] == 7
    receipt = json.loads(
        Path(failure.value.evidence["receipt_path"]).read_text(encoding="utf-8")
    )
    assert "canary" not in receipt["details"]["stderr_preview"]
    assert "<redacted>" in receipt["details"]["stderr_preview"]


def test_exec_rejects_project_commands_before_container_admission(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """The shared tool plane cannot become a project test environment."""
    manager = runtime(tmp_path, fake_docker)
    target = tmp_path / "project"
    target.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target)
    exec_count = sum(command[1] == "exec" for command in fake_docker.commands)
    with pytest.raises(BootstrapError) as failure:
        manager.exec(target, ["python3", "-m", "pytest"])
    assert failure.value.code == "tool_plane_command_rejected"
    assert sum(command[1] == "exec" for command in fake_docker.commands) == exec_count


def test_failed_candidate_is_quarantined_and_previous_generation_restored(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Quarantine an unhealthy candidate and keep the previous pointer."""
    manager = runtime(tmp_path, fake_docker)
    target_a = tmp_path / "a"
    target_b = tmp_path / "b"
    target_a.mkdir()
    target_b.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target_a)
    before = manager.status()["details"]["state"]["current_generation"]
    with pytest.raises(BootstrapError, match="candidate_generation_unhealthy"):
        manager.target_add(target_b, health_ok=False)
    state = manager.status()["details"]["state"]
    assert state["current_generation"] == before
    assert any(item["state"] == "quarantined" for item in state["generations"].values())


def test_rollback_restarts_previous_verified_mount_generation(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Switch back to a verified generation with a fresh container."""
    manager = runtime(tmp_path, fake_docker)
    target_a, target_b = tmp_path / "a", tmp_path / "b"
    target_a.mkdir()
    target_b.mkdir()
    manager.install()
    manager.start()
    manager.target_add(target_a)
    manager.target_add(target_b)
    current = manager.status()["details"]["state"]["current_generation"]
    manager.rollback()
    state = manager.status()["details"]["state"]
    assert state["current_generation"] != current
    assert state["generations"][state["current_generation"]]["state"] == "current"


def test_symlink_state_write_fails_closed(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Refuse replacing a state symlink and preserve its outside target."""
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.paths.state.unlink()
    outside = tmp_path / "outside"
    outside.write_text("keep", encoding="utf-8")
    manager.paths.state.symlink_to(outside)
    with pytest.raises(BootstrapError, match="symlink_path_rejected"):
        manager.start()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_gc_high_water_keeps_current_rollback_and_unpublished_spool(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Expose LRU candidates without deleting protected unpublished state."""
    manager = runtime(tmp_path, fake_docker)
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
    manager.install()
    manager.start()
    manager.target_add(target)
    manager.admit_task("task-a")
    manager.release_task("task-a")
    (manager.paths.runtime_root / "spool" / "pending").mkdir()
    # A dry run exposes LRU candidates but never removes a pinned/current/spool item.
    preview = manager.gc(dry_run=True)["details"]
    assert preview["preserved"]["unpublished_spool"] is True
    assert "task:task-a" in preview["candidates"]


def test_gc_enforces_archive_quota_only_without_unpublished_spool(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Prune a reproducible archive cache, but never while a spool is pending."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "manifest.toml")
        .read_text(encoding="utf-8")
        .replace("archive_lease_quota_bytes = 2147483648", "archive_lease_quota_bytes = 1"),
        encoding="utf-8",
    )
    control = tmp_path / "control"
    control.mkdir()
    manager = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=REPOSITORY_ROOT,
        manifest_path=manifest,
        docker=fake_docker,
    )
    manager.install()
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


def test_uninstall_removes_only_owned_container_and_image(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Read back exact owned image removal during uninstall."""
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.start()
    manager.codex_prepare()
    manager.uninstall()
    state_file = manager.paths.state.read_text(encoding="utf-8")
    assert json.loads(state_file)["state"] == "uninstalled"
    assert any(
        command[1:3] == ["image", "rm"]
        for command in fake_docker.commands
        if len(command) >= 3
    )
    # The fake image is removed by its digest; absence is read back by Docker.
    assert manager.docker.inspect_image(manager._image_tag()) is None
    assert not manager.paths.container_runtime.exists()


def test_changed_inputs_preserve_status_and_exact_cleanup_then_allow_reinstall(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Source updates must not strand resources created by the prior generation."""
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.start()
    old_state = json.loads(manager.paths.state.read_text(encoding="utf-8"))

    changed_manifest = tmp_path / "changed-manifest.toml"
    changed_manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "manifest.toml")
        .read_text(encoding="utf-8")
        .replace("idle_stop_seconds = 3600", "idle_stop_seconds = 1800"),
        encoding="utf-8",
    )
    changed = BootstrapRuntime(
        manager.paths.control_parent_root,
        manager.paths.runtime_root,
        repository_root=REPOSITORY_ROOT,
        manifest_path=changed_manifest,
        docker=fake_docker,
    )

    status = changed.status()
    assert status["details"]["manifest_drift"] is True
    assert status["resource_ids"]["container"]["id"] == old_state["resources"]["container"]["id"]
    with pytest.raises(BootstrapError, match="manifest_mismatch"):
        changed.install()

    changed.stop()
    changed.uninstall()
    uninstalled = json.loads(changed.paths.state.read_text(encoding="utf-8"))
    assert uninstalled["state"] == "uninstalled"
    assert uninstalled["manifest_digest"] == old_state["manifest_digest"]

    reinstalled = changed.install()
    rebound = json.loads(changed.paths.state.read_text(encoding="utf-8"))
    assert reinstalled["code"] == "installed"
    assert rebound["manifest_digest"] == changed.manifest_digest
    assert rebound["manifest_digest"] != old_state["manifest_digest"]


def test_parser_has_typed_exec_tool_codex_and_eval_routes() -> None:
    """Keep all documented typed parser routes available."""
    from tools.agent_tools.bootstrap_runtime import build_parser

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


def test_eval_precondition_failure_creates_no_spool_or_exchange(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """An unregistered eval target can be retried after registration."""
    manager = runtime(tmp_path, fake_docker)
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
    manager.install()
    manager.start()
    with pytest.raises(BootstrapError) as failure:
        manager.eval_collect(target, "precondition")
    assert failure.value.code == "target_not_registered"
    assert not (manager.paths.runtime_root / "spool" / "precondition").exists()
    assert not (
        manager.paths.container_runtime / "tasks" / "eval-precondition"
    ).exists()


def test_top_level_entrypoint_reports_typed_docker_failure_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Return runtime_unavailable instead of a host-tool fallback."""
    control = tmp_path / "control"
    control.mkdir()
    monkeypatch.setenv("AGENT_CANON_DOCKER", str(tmp_path / "missing-docker"))
    completed = subprocess.run(
        [
            str(REPOSITORY_ROOT / "bootstrap.sh"),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(control / "runtime"),
            "install",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert json.loads(completed.stderr)["code"] == "runtime_unavailable"


def test_eval_collect_runs_image_producers_and_syncs_local_bare_archive(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Collect a real producer matrix, prove source stability, and read back Git blobs."""
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (source / "README.md").write_text("source fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "remote", "add", "origin", "https://github.com/example/source.git"],
        check=True,
    )

    seed = tmp_path / "archive-seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    (seed / "README.md").write_text("archive\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-qm", "seed"], check=True)
    remote = tmp_path / "agent-canon-log.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(remote)], check=True)
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "manifest.toml")
        .read_text(encoding="utf-8")
        .replace(
            'remote = "git@github.com:iwashita-nozomu/agent-canon-log.git"',
            f'remote = "{remote}"',
        ),
        encoding="utf-8",
    )

    (tmp_path / "control").mkdir()
    manager = BootstrapRuntime(
        tmp_path / "control",
        tmp_path / "control" / "runtime",
        repository_root=REPOSITORY_ROOT,
        manifest_path=manifest,
        docker=fake_docker,
    )
    manager.install()
    manager.start()
    manager.target_add(source)
    before = (source / "README.md").read_bytes()
    collected = manager.eval_collect(source, "eval-e2e")
    collection = collected["details"]["collection"]
    assert collection["status"] == "collected"
    assert collection["source_tree_unchanged"] is True
    assert len(collection["producer_matrix"]) == 4
    assert collection["tool_image_digest"] == "sha256:fake-image-1"
    spool = manager.paths.runtime_root / "spool" / "eval-e2e"
    assert (spool / "collection.json").is_file()
    assert (source / "README.md").read_bytes() == before
    synced = manager.eval_sync("eval-e2e")
    assert synced["code"] == "archive_published"
    assert not spool.exists()
    clone = tmp_path / "archive-clone"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    from tools.agent_tools.log_repository_identity import stable_source_id

    branch = f"logs/{stable_source_id(source)}"
    branch_result = subprocess.run(
        ["git", "-C", str(clone), "ls-tree", "-r", "--name-only", f"origin/{branch}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "eval-results/skill-workflow-prompt/skill-eval-20260101T000000000000Z-0123456789-pass-bootstrap.md" in branch_result.stdout
