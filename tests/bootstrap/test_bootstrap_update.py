"""Focused simple update lifecycle tests."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.agent_tools.bootstrap_runtime import (
    BootstrapError,
    BootstrapRuntime,
    DockerAdapter,
    _runtime_from_args,
    build_parser,
)


ROOT = Path(__file__).resolve().parents[2]


def _runtime(tmp_path: Path) -> tuple[BootstrapRuntime, DockerAdapter]:
    state = tmp_path / "docker.json"
    os.environ["FAKE_DOCKER_STATE"] = str(state)
    docker = DockerAdapter(str(ROOT / "tests/bootstrap/fake_docker.py"))
    control = tmp_path / "control"
    control.mkdir()
    return BootstrapRuntime(control, control / "runtime", repository_root=ROOT, docker=docker), docker


def _fast_manifest(tmp_path: Path) -> Path:
    text = (ROOT / "bootstrap/manifest.toml").read_text(encoding="utf-8")
    for old, new in (
        ("idle_stop_seconds = 3600", "idle_stop_seconds = 1800"),
        ("health_start_period_seconds = 10", "health_start_period_seconds = 0.01"),
        ("health_timeout_seconds = 5", "health_timeout_seconds = 0.01"),
        ("health_poll_interval_seconds = 0.2", "health_poll_interval_seconds = 0.005"),
    ):
        text = text.replace(old, new)
    path = tmp_path / "manifest.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _local_manifest(tmp_path: Path, *, fast: bool = False) -> Path:
    text = (ROOT / "bootstrap/manifest.toml").read_text(encoding="utf-8")
    if fast:
        for old, new in (
            ("idle_stop_seconds = 3600", "idle_stop_seconds = 1800"),
            ("health_start_period_seconds = 10", "health_start_period_seconds = 0.01"),
            ("health_timeout_seconds = 5", "health_timeout_seconds = 0.01"),
            ("health_poll_interval_seconds = 0.2", "health_poll_interval_seconds = 0.005"),
        ):
            text = text.replace(old, new)
    text = text.replace(
        '\n[registry]\nimage = "ghcr.io/iwashita-nozomu/agent-canon"\nsource_branch = "main"\n',
        "\n",
    )
    path = tmp_path / ("local-fast-manifest.toml" if fast else "local-manifest.toml")
    path.write_text(text, encoding="utf-8")
    return path


def test_bootstrap_defaults_runtime_to_repository_dot_runtime(tmp_path: Path) -> None:
    """The persistent default follows the install checkout."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    (repository / "bootstrap").mkdir(parents=True)
    (repository / "bootstrap" / "manifest.toml").write_bytes(
        (ROOT / "bootstrap" / "manifest.toml").read_bytes()
    )
    control.mkdir()
    args = build_parser().parse_args(
        [
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "status",
        ]
    )
    runtime = _runtime_from_args(args)
    assert runtime.paths.runtime_root == repository / ".runtime"


def test_lifecycle_lock_cannot_be_bypassed_by_environment_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old child-process marker never suppresses lock acquisition."""
    manager, _docker = _runtime(tmp_path)
    flock_calls: list[int] = []
    monkeypatch.setenv("AGENT_CANON_LOCK_HELD", "1")
    monkeypatch.setattr(fcntl, "flock", lambda _fd, operation: flock_calls.append(operation))

    with manager.locked():
        pass

    assert flock_calls == [fcntl.LOCK_EX, fcntl.LOCK_UN]


def test_scheduler_generation_uses_test_owned_xdg_and_fake_systemctl(
    tmp_path: Path,
) -> None:
    """Scheduler rendering never needs the developer's user systemd manager."""
    manager, _docker = _runtime(tmp_path)

    result = manager.scheduler_enable()

    service_path, timer_path = manager._scheduler_paths()
    assert result["code"] == "scheduler_enabled"
    assert service_path.parent == Path(os.environ["XDG_CONFIG_HOME"]) / "systemd" / "user"
    assert service_path.is_file()
    assert timer_path.is_file()
    assert "ExecStart=" in service_path.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=" in timer_path.read_text(encoding="utf-8")
    systemctl_log = Path(os.environ["AGENT_CANON_TEST_SYSTEMCTL_LOG"])
    assert systemctl_log.is_relative_to(tmp_path)

    manager.scheduler_uninstall()
    assert not service_path.exists()
    assert not timer_path.exists()
    operations = [
        value
        for key, value in (
            line.split("\t", 1)
            for line in systemctl_log.read_text(encoding="utf-8").splitlines()
        )
        if key == "argv"
    ]
    assert operations == [
        "--user show-environment",
        "--user daemon-reload",
        "--user enable --now agent-canon-sync.timer",
        "--user disable --now agent-canon-sync.timer",
        "--user daemon-reload",
    ]


def test_bootstrap_maps_only_the_exact_legacy_runtime_default(tmp_path: Path) -> None:
    """Migrate the removed default without rewriting an explicit runtime root."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    (repository / "bootstrap").mkdir(parents=True)
    (repository / "bootstrap" / "manifest.toml").write_bytes(
        (ROOT / "bootstrap" / "manifest.toml").read_bytes()
    )
    control.mkdir()

    def parse(runtime_root: Path):
        return _runtime_from_args(
            build_parser().parse_args(
                [
                    "--repository-root",
                    str(repository),
                    "--control-parent-root",
                    str(control),
                    "--runtime-root",
                    str(runtime_root),
                    "status",
                ]
            )
        )

    assert parse(control / "workspace/agent-canon-runtime/host").paths.runtime_root == (
        repository / ".runtime"
    )
    explicit = control / "workspace/agent-canon-runtime/custom"
    assert parse(explicit).paths.runtime_root == explicit


def test_update_adopts_fresh_source_runtime_after_legacy_default_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An old default path is rebuilt and scheduled at the source-owned root."""
    # This test observes the production scheduler call through a stub.  The
    # shared bootstrap fixture still provides a test-owned XDG directory, so
    # no real user unit can be reached when the scheduler boundary is opened.
    monkeypatch.delenv("AGENT_CANON_CONTAINER_CONTROL", raising=False)
    state_path = tmp_path / "docker.json"
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state_path))
    docker = DockerAdapter(str(ROOT / "tests/bootstrap/fake_docker.py"))
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    (repository / "bootstrap").mkdir(parents=True)
    (repository / "bootstrap" / "manifest.toml").write_bytes(
        (ROOT / "bootstrap" / "manifest.toml").read_bytes()
    )
    control.mkdir()
    legacy = control / "workspace/agent-canon-runtime/host"
    old = BootstrapRuntime(
        control,
        legacy,
        repository_root=repository,
        manifest_path=repository / "bootstrap/manifest.toml",
        docker=docker,
    )
    with old.locked():
        old_state = old._new_state()
        old_state["state"] = "installed"
        old_state["resources"] = old._resource_records()
        old._write_state(old_state)

    runtime = BootstrapRuntime(
        control,
        repository / ".runtime",
        repository_root=repository,
        manifest_path=repository / "bootstrap/manifest.toml",
        docker=docker,
    )
    monkeypatch.setattr(runtime, "codex_prepare", lambda: {"code": "prepared"})
    scheduler_calls: list[str] = []
    monkeypatch.setattr(
        runtime,
        "scheduler_enable",
        lambda: scheduler_calls.append(str(runtime.paths.runtime_root)) or {"code": "enabled"},
    )

    image_id = "sha256:fresh-source-image"

    def fake_image(state: dict[str, Any], *, force_build: bool = False) -> dict[str, Any]:
        assert force_build is True
        state["resources"]["image"] = {
            "id": image_id,
            "tag": "agent-canon-tools:test",
            "owned": True,
            "state": "present",
        }
        return {"Id": image_id}

    monkeypatch.setattr(runtime, "_image", fake_image)
    result = runtime.update()

    assert result["code"] == "updated"
    assert runtime.paths.runtime_root == repository / ".runtime"
    assert runtime.paths.state.is_file()
    assert not legacy.exists()
    assert scheduler_calls == [str(repository / ".runtime")]


def test_update_runs_one_normal_build(tmp_path: Path) -> None:
    manager, docker = _runtime(tmp_path)
    assert manager.install()["code"] == "installed"
    builds = sum(command[1] == "build" for command in docker.commands)
    assert manager.update()["code"] == "updated"
    assert sum(command[1] == "build" for command in docker.commands) == builds + 1


def test_health_failure_restores_old_runtime_and_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, docker = _runtime(tmp_path)
    manager.install()
    manager.start()
    old = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    changed = BootstrapRuntime(
        manager.paths.control_parent_root,
        manager.paths.runtime_root,
        repository_root=ROOT,
        manifest_path=_fast_manifest(tmp_path),
        docker=docker,
    )
    monkeypatch.setenv("FAKE_DOCKER_HEALTH_POLLS", "1000")
    with pytest.raises(BootstrapError):
        changed.update()
    after = json.loads(changed.paths.state.read_text(encoding="utf-8"))
    assert after["current_generation"] == old["current_generation"]
    assert after["resources"]["image"]["id"] == old["resources"]["image"]["id"]
    assert after["resources"]["container"]["id"]


def test_active_task_rejected_before_build(tmp_path: Path) -> None:
    manager, docker = _runtime(tmp_path)
    manager.install()
    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    state["active_task_count"] = 1
    manager.paths.state.write_text(json.dumps(state), encoding="utf-8")
    builds = sum(command[1] == "build" for command in docker.commands)
    with pytest.raises(BootstrapError, match="mount_update_blocked"):
        manager.update()
    assert sum(command[1] == "build" for command in docker.commands) == builds


def test_owned_image_filter_argv_and_failure_are_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, docker = _runtime(tmp_path)
    manager.install()
    manager.gc(dry_run=True)
    command = next(item for item in docker.commands if item[1:3] == ["image", "ls"])
    assert command.count("--filter") == 2
    assert all(command[index + 1] != "--filter" for index, value in enumerate(command[:-1]) if value == "--filter")
    monkeypatch.setenv("FAKE_DOCKER_FAIL_IMAGE_LS", "1")
    with pytest.raises(BootstrapError, match="docker_command_failed"):
        manager.gc(dry_run=True)


def test_update_then_codex_prepare_reads_current_tracked_adapters(tmp_path: Path) -> None:
    manager, _docker = _runtime(tmp_path)
    manager.install()
    manager.update()
    result = manager.codex_prepare()
    manifest = json.loads((manager.paths.codex_home / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_root"] == str(ROOT)
    assert manifest["manifest_digest"] == manager.manifest_digest
    assert {entry["surface"] for entry in manifest["links"]} == {
        "skills", "agents", "hooks", "config"
    }
    for entry in manifest["links"]:
        assert Path(entry["target"]).is_symlink()
        assert Path(entry["target"]).resolve() == Path(entry["source"]).resolve()
    skill_links = [entry for entry in result["details"]["links"] if entry["surface"] == "skills"]
    assert skill_links
    assert all("/.codex/personal/skills/" in entry["source"] for entry in skill_links)
    assert all(Path(entry["target"]).is_symlink() for entry in skill_links)


def test_codex_prepare_places_config_at_code_home_root(tmp_path: Path) -> None:
    """Codex reads the managed config at CODEX_HOME/config.toml."""
    manager, _docker = _runtime(tmp_path)
    manager.install()
    manager.codex_prepare()
    config_link = manager.paths.codex_home / "config.toml"
    assert config_link.is_symlink()
    assert config_link.resolve() == (ROOT / ".codex" / "config.toml").resolve()
    assert not (manager.paths.codex_home / "config" / "config.toml").exists()


def test_container_codex_links_project_to_host_live_install_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resident validation sources stay in-image while links target host live files."""
    control = tmp_path / "control"
    control.mkdir()
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
    monkeypatch.setenv("AGENT_CANON_HOST_INSTALL_ROOT", str(ROOT))
    manager = BootstrapRuntime(control, control / "runtime", repository_root=ROOT)
    links = manager._managed_links()
    assert links
    for entry in links:
        source = Path(entry["source"])
        assert source.exists()
        assert str(source).startswith(str(ROOT) + "/")
        validation_source = Path(entry.get("validation_source", entry["source"]))
        assert validation_source.exists()
        assert str(validation_source).startswith(str(ROOT) + "/")
    assert any(entry["surface"] == "skills" for entry in links)
    assert any(entry["surface"] == "config" for entry in links)


def test_non_owned_image_update_materializes_absent_personal_skill_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-build update path materializes the skill view before linking it."""
    manager, _docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    manager.install()
    skill_path = ROOT / ".codex" / "personal" / "skills" / "agent-orchestration" / "SKILL.md"
    original = skill_path.read_bytes()
    skill_path.unlink()
    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    state["resources"]["image"]["owned"] = False
    manager.paths.state.write_text(json.dumps(state), encoding="utf-8")
    try:
        result = manager.update()
        assert result["code"] == "up_to_date"
        assert skill_path.read_bytes() == original
    finally:
        skill_path.write_bytes(original)


def test_install_update_owns_control_root_agents_link_and_uninstall_removes_exact_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    managed = manager.paths.control_parent_root / ".agents"
    assert manager.install()["code"] == "installed"
    assert managed.is_dir() and not managed.is_symlink()
    assert (managed / "skills" / "agent-orchestration").is_symlink()
    assert (managed / "skills" / "agent-orchestration").resolve() == (
        ROOT / ".codex" / "personal" / "skills" / "agent-orchestration"
    ).resolve()
    assert manager.update()["code"] == "updated"
    assert manager.status()["details"]["managed_agents_link"]["split"] is True
    assert manager.status()["details"]["managed_global_links"]["all_exact"] is True
    manager.uninstall()
    assert not managed.exists() and not managed.is_symlink()


def test_control_root_agents_collision_is_typed_and_foreign_path_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    collision = manager.paths.control_parent_root / ".agents"
    collision.mkdir()
    foreign_skill = collision / "skills" / "personal"
    foreign_skill.mkdir(parents=True)
    (foreign_skill / "SKILL.md").write_text("personal\n", encoding="utf-8")
    assert manager.install()["code"] == "installed"
    assert foreign_skill.is_dir()
    manager.uninstall()
    assert foreign_skill.is_dir()
    assert sum(command[1] == "build" for command in docker.commands) == 1

    (foreign_skill / "SKILL.md").unlink()
    foreign_skill.rmdir()
    (collision / "skills").rmdir()
    collision.rmdir()
    foreign = tmp_path / "foreign-agents"
    foreign.mkdir()
    collision.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(BootstrapError, match="agents_link_collision"):
        manager.install()
    assert collision.is_symlink() and collision.resolve() == foreign.resolve()


def test_legacy_root_agents_symlink_is_migrated_to_split_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, _docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    legacy = manager.paths.control_parent_root / ".agents"
    legacy.symlink_to(ROOT / ".agents", target_is_directory=True)

    assert manager.install()["code"] == "installed"
    assert legacy.is_dir() and not legacy.is_symlink()
    assert (legacy / "skills" / "agent-orchestration").is_symlink()
    assert (legacy / "skills" / "agent-orchestration").resolve() == (
        ROOT / ".codex" / "personal" / "skills" / "agent-orchestration"
    ).resolve()

    manager.uninstall()
    assert not legacy.exists() and not legacy.is_symlink()


def test_arbitrary_control_root_does_not_receive_global_codex_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actual_home = tmp_path / "actual-home"
    actual_home.mkdir()
    monkeypatch.setenv("HOME", str(actual_home))
    manager, _docker = _runtime(tmp_path)

    assert manager.install()["code"] == "installed"
    assert not (manager.paths.control_parent_root / ".agents").exists()
    assert not (manager.paths.control_parent_root / ".codex").exists()
    details = manager.status()["details"]
    assert details["managed_agents_link"]["state"] == "home_scope_disabled"
    assert details["managed_global_links"]["home_scope"] is False


def test_image_failure_does_not_leave_global_projection_orphaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, _docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))

    def fail_image(_state: dict[str, Any], *, force_build: bool = False) -> None:
        raise BootstrapError("candidate_image_failed", "image build failed")

    monkeypatch.setattr(manager, "_image", fail_image)
    with pytest.raises(BootstrapError, match="candidate_image_failed"):
        manager.install()
    assert not (manager.paths.control_parent_root / ".agents").exists()
    assert not (manager.paths.control_parent_root / ".codex").exists()


def test_global_collision_preflight_preserves_existing_home_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    manager.personal_codex_config.unlink(missing_ok=True)
    legacy = manager.paths.control_parent_root / ".agents"
    legacy.symlink_to(ROOT / ".agents", target_is_directory=True)
    codex = manager.paths.control_parent_root / ".codex"
    config = codex / "config.toml"
    config.parent.mkdir()
    payload = b"model = \"personal\"\n"
    config.write_bytes(payload)
    foreign_agent = codex / "agents" / "worker.toml"
    foreign_agent.parent.mkdir()
    foreign_agent.write_text("foreign\n", encoding="utf-8")

    with pytest.raises(BootstrapError, match="agents_link_collision"):
        manager.install()
    assert legacy.is_symlink() and legacy.resolve() == (ROOT / ".agents").resolve()
    assert config.is_file() and not config.is_symlink() and config.read_bytes() == payload
    assert not manager.personal_codex_config.exists()
    assert sum(command[1] == "build" for command in docker.commands) == 1


def test_global_codex_config_is_migrated_losslessly_and_restored_on_uninstall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _docker = _runtime(tmp_path)
    monkeypatch.setenv("HOME", str(manager.paths.control_parent_root))
    manager.personal_codex_config.unlink(missing_ok=True)
    codex = manager.paths.control_parent_root / ".codex"
    codex.mkdir()
    config = codex / "config.toml"
    payload = b"model = \"personal-model\"\n\n[profiles.personal]\nvalue = true\n"
    config.write_bytes(payload)
    config.chmod(0o640)
    foreign_agent = codex / "agents" / "personal.toml"
    foreign_agent.parent.mkdir()
    foreign_agent.write_text("name = \"personal\"\n", encoding="utf-8")

    assert manager.install()["code"] == "installed"
    source = manager.personal_codex_config
    assert config.is_symlink() and config.resolve() == source.resolve()
    assert source.read_bytes() == payload
    assert source.stat().st_mode & 0o777 == 0o640
    assert foreign_agent.read_text(encoding="utf-8") == "name = \"personal\"\n"
    assert (codex / "agents" / "worker.toml").is_symlink()
    assert (codex / "agents" / "worker.toml").resolve() == (
        ROOT / ".codex" / "agents" / "worker.toml"
    ).resolve()
    assert manager.update()["code"] == "updated"
    assert source.read_bytes() == payload

    manager.uninstall()
    assert config.is_file() and not config.is_symlink()
    assert config.read_bytes() == payload
    assert config.stat().st_mode & 0o777 == 0o640
    assert source.read_bytes() == payload
    assert foreign_agent.read_text(encoding="utf-8") == "name = \"personal\"\n"


def test_codex_prepare_removes_only_exact_stale_managed_links(tmp_path: Path) -> None:
    manager, _docker = _runtime(tmp_path)
    manager.install()
    stale_source = tmp_path / "stale-source"
    stale_source.write_text("stale\n", encoding="utf-8")
    stale_target = manager.paths.codex_home / "skills/stale/SKILL.md"
    stale_target.parent.mkdir(parents=True, exist_ok=True)
    stale_target.symlink_to(stale_source)
    foreign = manager.paths.codex_home / "agents/foreign.toml"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("foreign\n", encoding="utf-8")
    manifest = manager.paths.codex_home / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["links"].extend(
        [
            {"target": str(stale_target), "source": str(stale_source), "managed": True},
            {"target": str(foreign), "source": str(tmp_path / "other"), "managed": True},
        ]
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    manager.codex_prepare()
    assert not stale_target.exists() and not stale_target.is_symlink()
    assert foreign.read_text(encoding="utf-8") == "foreign\n"


def test_template_logical_command_routes_to_container_receipt(tmp_path: Path) -> None:
    manager, docker = _runtime(tmp_path)
    manager.install()
    manager.target_add(ROOT)
    result = manager.template_export(ROOT, "agent-artifacts", "bundle")
    assert result["details"]["execution_plane"] == "agentcanon_tool_container"
    command = next(command for command in docker.commands if command[1] == "exec")
    assert "python3" not in command
    assert "PYTHONPATH" not in command
    parsed = build_parser().parse_args(
        [
            "--repository-root", str(ROOT),
            "--control-parent-root", str(tmp_path / "control"),
            "--runtime-root", str(tmp_path / "control/runtime"),
            "template", "export", "--root", str(ROOT),
            "--profile", "agent-artifacts", "--output", "bundle",
        ]
    )
    assert not hasattr(parsed, "execution_plane")
