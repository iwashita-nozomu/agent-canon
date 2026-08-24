"""Focused simple update lifecycle tests."""

from __future__ import annotations

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


def _seed_registry_image(
    state_path: Path,
    image_ref: str,
    source_head: str,
    image_id: str = "sha256:registry-image",
) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["images"][image_ref] = {
        "Id": image_id,
        "RepoTags": [image_ref],
        "RepoDigests": ["ghcr.io/example/agent-canon@sha256:registry-digest"],
        "Config": {
            "Labels": {"org.opencontainers.image.revision": source_head},
        },
        "Os": "linux",
        "Architecture": "amd64",
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")


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


@pytest.mark.parametrize("fail_candidate", [False, True])
def test_source_sync_reconciles_manifest_transition_and_preserves_old_state_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_candidate: bool,
) -> None:
    """Only the source-sync update route crosses a checkout manifest boundary."""
    state = tmp_path / "docker.json"
    os.environ["FAKE_DOCKER_STATE"] = str(state)
    docker = DockerAdapter(str(ROOT / "tests/bootstrap/fake_docker.py"))
    control = tmp_path / "control"
    control.mkdir()
    manager = BootstrapRuntime(
        control,
        control / "runtime",
        repository_root=ROOT,
        manifest_path=_local_manifest(tmp_path),
        docker=docker,
    )
    assert manager.install()["code"] == "installed"
    assert manager.start()["code"] == "ready"
    old = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    changed = BootstrapRuntime(
        manager.paths.control_parent_root,
        manager.paths.runtime_root,
        repository_root=ROOT,
        manifest_path=_local_manifest(tmp_path, fast=True),
        docker=docker,
    )
    source_head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    image_ref = f"ghcr.io/example/agent-canon:sha-{source_head}"
    candidate_id = "sha256:registry-image"
    _seed_registry_image(
        Path(os.environ["FAKE_DOCKER_STATE"]), image_ref, source_head, candidate_id
    )

    if fail_candidate:
        original_ensure = changed._ensure_container

        def fail_only_candidate(
            state: dict[str, Any], *, start: bool
        ) -> dict[str, Any]:
            image = state.get("resources", {}).get("image", {})
            if isinstance(image, dict) and image.get("id") == candidate_id:
                raise BootstrapError("candidate_generation_unhealthy", "candidate health failed")
            return original_ensure(state, start=start)

        monkeypatch.setattr(changed, "_ensure_container", fail_only_candidate)
        with pytest.raises(BootstrapError, match="candidate_generation_unhealthy"):
            changed.update(image_ref=image_ref, source_sync=True)
        after = json.loads(manager.paths.state.read_text(encoding="utf-8"))
        assert after["manifest_digest"] == old["manifest_digest"]
        assert after["resources"]["image"]["id"] == old["resources"]["image"]["id"]
        assert after["current_generation"] == old["current_generation"]
    else:
        result = changed.update(image_ref=image_ref, source_sync=True)
        assert result["code"] == "updated"
        after = json.loads(manager.paths.state.read_text(encoding="utf-8"))
        assert after["manifest_digest"] == changed.manifest_digest
        assert after["resources"]["image"]["id"] == candidate_id


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
    assert all("/.agents/skills/" in entry["source"] for entry in skill_links)
    assert all(Path(entry["target"]).is_symlink() for entry in skill_links)


def test_install_update_owns_control_root_agents_link_and_uninstall_removes_exact_link(
    tmp_path: Path,
) -> None:
    manager, _docker = _runtime(tmp_path)
    managed = manager.paths.control_parent_root / ".agents"
    assert manager.install()["code"] == "installed"
    assert managed.is_symlink()
    assert managed.resolve() == (ROOT / ".agents").resolve()
    assert manager.update()["code"] == "updated"
    assert manager.status()["details"]["managed_agents_link"]["exact"] is True
    manager.uninstall()
    assert not managed.exists() and not managed.is_symlink()


def test_control_root_agents_collision_is_typed_and_foreign_path_preserved(
    tmp_path: Path,
) -> None:
    manager, docker = _runtime(tmp_path)
    collision = manager.paths.control_parent_root / ".agents"
    collision.mkdir()
    with pytest.raises(BootstrapError, match="agents_link_collision"):
        manager.install()
    assert collision.is_dir()
    assert sum(command[1] == "build" for command in docker.commands) == 0
    collision.rmdir()
    foreign = tmp_path / "foreign-agents"
    foreign.mkdir()
    collision.symlink_to(foreign, target_is_directory=True)
    with pytest.raises(BootstrapError, match="agents_link_collision"):
        manager.install()
    assert collision.is_symlink() and collision.resolve() == foreign.resolve()


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
