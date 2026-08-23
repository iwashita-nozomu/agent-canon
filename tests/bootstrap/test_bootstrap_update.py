"""Focused simple update lifecycle tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.agent_tools.bootstrap_runtime import BootstrapError, BootstrapRuntime, DockerAdapter, _source_snapshot


ROOT = Path(__file__).resolve().parents[2]


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "bootstrap/container").mkdir(parents=True)
    (repo / "bootstrap/manifest.toml").write_text(
        (ROOT / "bootstrap/manifest.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (repo / "bootstrap/container/Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    return repo


def _runtime(tmp_path: Path, repo: Path | None = None) -> tuple[BootstrapRuntime, DockerAdapter]:
    state = tmp_path / "docker.json"
    os.environ["FAKE_DOCKER_STATE"] = str(state)
    docker = DockerAdapter(str(ROOT / "tests/bootstrap/fake_docker.py"))
    control = tmp_path / "control"
    control.mkdir()
    return BootstrapRuntime(control, control / "runtime", repository_root=repo or ROOT, docker=docker), docker


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


def test_update_noop_does_not_build_again(tmp_path: Path) -> None:
    manager, docker = _runtime(tmp_path)
    assert manager.install()["code"] == "installed"
    builds = sum(command[1] == "build" for command in docker.commands)
    assert manager.update()["code"] == "up_to_date"
    assert sum(command[1] == "build" for command in docker.commands) == builds


def test_worktree_content_change_builds_once_and_updates_identity(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    manager, docker = _runtime(tmp_path, repo)
    manager.install()
    before = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert manager.update()["code"] == "updated"
    after = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert after["tree_digest"] != before["tree_digest"]
    assert sum(command[1] == "build" for command in docker.commands) == 2


def test_image_input_change_builds_once(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    (repo / "tools").mkdir()
    manager, docker = _runtime(tmp_path, repo)
    manager.install()
    (repo / "tools/tool.py").write_text("changed\n", encoding="utf-8")
    assert manager.update()["code"] == "updated"
    assert sum(command[1] == "build" for command in docker.commands) == 2


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


def test_tree_digest_is_worktree_content_identity(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    before = _source_snapshot(repo)["tree_digest"]
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert _source_snapshot(repo)["tree_digest"] != before


def test_update_then_codex_prepare_reads_current_tracked_adapters(tmp_path: Path) -> None:
    manager, _docker = _runtime(tmp_path)
    manager.install()
    manager.update()
    result = manager.codex_prepare()
    manifest = json.loads((manager.paths.codex_home / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_root"] == str(ROOT)
    assert manifest["tree_digest"] == manager.source_identity["tree_digest"]
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
