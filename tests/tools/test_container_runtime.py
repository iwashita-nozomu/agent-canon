"""Focused tests for the container pack runtime helpers."""

from __future__ import annotations

import importlib.util
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from tools.ci import container_runtime as runtime_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_container_pack.py"


def load_runtime_module() -> Any:
    """Load the runtime helper under the import name used by its runners."""
    sys.modules["container_runtime"] = runtime_module
    return runtime_module


def load_runner_module() -> Any:
    """Load the direct pack runner after its runtime dependency."""
    load_runtime_module()
    spec = importlib.util.spec_from_file_location(
        "agent_canon_run_container_pack", RUNNER_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_parent_pack(tmp_path: Path, *, linked: bool = True) -> tuple[Path, Path, Path]:
    """Write a parent-shaped pack and repository symlink without host paths."""
    repo = tmp_path / "workspace" / "topic" / "parent"
    pack_path = repo / "docker" / "packs" / "default.toml"
    pack_path.parent.mkdir(parents=True)
    target = tmp_path / "canonical-data"
    target.mkdir()
    link = repo / "link" / "msm_data_root"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    linked_profile = 'optional_mount_profiles = ["linked-data-roots"]\n'
    linked_roots = (
        'linked_data_roots = [{link = "link/msm_data_root", target = "/mnt/l/msm_data_root"}]\n'
        if linked
        else ""
    )
    pack_path.write_text(
        "\n".join(
            [
                "[pack]",
                'name = "parent"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "parent:fixture"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                linked_profile if linked else "",
                linked_roots,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo, pack_path, target


class FakeResolvedPath:
    """Minimal resolved-path contract used for host-independent unit tests."""

    def __init__(self, value: str) -> None:
        """Store the canonical path text returned by the fake resolver."""
        self.value = value

    def is_dir(self) -> bool:
        """Report the fake target as an existing directory."""
        return True

    def __str__(self) -> str:
        """Return the canonical path text."""
        return self.value


def fake_resolver(_path: Path) -> Path:
    """Return a host-independent canonical linked-data directory."""
    return cast(Path, FakeResolvedPath("/mnt/l/msm_data_root"))


def fixed_linked_mounts(_pack: Any, _workspace: Path) -> tuple[str, ...]:
    """Return the selected bind without touching a host mount path."""
    return ("/mnt/l/msm_data_root:/mnt/l/msm_data_root",)


def test_parent_pack_link_is_resolved_against_repo_root(tmp_path: Path) -> None:
    """Pack parsing uses the parent repo root, not the intermediate docker dir."""
    runtime = load_runtime_module()
    repo, pack_path, _ = write_parent_pack(tmp_path)

    pack = runtime.load_pack(pack_path)

    assert pack.runtime.linked_data_roots[0].link == "link/msm_data_root"
    resolver: Callable[[Path], Path] = fake_resolver
    mounts = runtime.resolve_linked_data_mounts(pack, repo, resolve_path=resolver)
    assert mounts == ("/mnt/l/msm_data_root:/mnt/l/msm_data_root",)


def test_parent_pack_link_mount_reaches_run_command(tmp_path: Path) -> None:
    """Direct runner command construction carries the selected linked bind."""
    runtime = load_runtime_module()
    repo, pack_path, _ = write_parent_pack(tmp_path)
    pack = runtime.load_pack(pack_path)
    original = runtime.resolve_linked_data_mounts

    def forward_linked_mounts(loaded: Any, workspace: Path) -> tuple[str, ...]:
        """Apply the fake canonical resolver to the production helper."""
        return original(loaded, workspace, resolve_path=fake_resolver)

    runtime.resolve_linked_data_mounts = forward_linked_mounts
    try:
        command = runtime.build_run_command(
            "docker", pack, workspace_root=repo, command=["true"]
        )
    finally:
        runtime.resolve_linked_data_mounts = original

    assert "-v" in command
    assert "/mnt/l/msm_data_root:/mnt/l/msm_data_root" in command


def test_raw_runtime_mounts_are_rejected() -> None:
    """Runtime packs cannot bypass named optional mount profiles."""
    runtime = load_runtime_module()
    pack = runtime.ContainerPack(
        name="raw",
        dockerfile="docker/Dockerfile",
        context=".",
        target=None,
        image_tag="raw:fixture",
        platform=None,
        smoke=runtime.SmokeSpec(),
        runtime=runtime.RuntimeSpec(mounts=("/host:/container",)),
    )
    with pytest.raises(ValueError, match="raw runtime.mounts"):
        runtime.build_run_command(
            "docker", pack, workspace_root=Path("/tmp"), command=["true"]
        )


def test_empty_optional_mount_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicitly empty optional-profile environment is not an omission."""
    runtime = load_runtime_module()
    monkeypatch.setenv("AGENT_CANON_OPTIONAL_MOUNTS", "")
    pack = runtime.ContainerPack(
        name="plain",
        dockerfile="docker/Dockerfile",
        context=".",
        target=None,
        image_tag="plain:fixture",
        platform=None,
        smoke=runtime.SmokeSpec(),
        runtime=runtime.RuntimeSpec(),
    )
    with pytest.raises(ValueError, match="cannot be empty"):
        runtime.resolve_linked_data_mounts(pack, Path("/tmp"))


def test_cli_mount_cannot_override_linked_target(tmp_path: Path) -> None:
    """CLI mounts cannot replace a declared linked-data-roots destination."""
    runtime = load_runtime_module()
    repo, pack_path, _ = write_parent_pack(tmp_path)
    pack = runtime.load_pack(pack_path)
    original = runtime.resolve_linked_data_mounts
    runtime.resolve_linked_data_mounts = fixed_linked_mounts
    try:
        for mount in (
            "/other:/mnt/l/msm_data_root",
            "/other:/mnt/l/msm_data_root/subdir",
            "/other:/mnt/l",
            "type=bind,source=/other,dst=/mnt/l/msm_data_root",
            "type=bind,source=/other,destination=/mnt/l/msm_data_root",
            "dst=/mnt/l/msm_data_root,source=/other,type=bind",
            "destination=/mnt/l/msm_data_root,source=/other,type=bind",
            "target=/mnt/l/msm_data_root,source=/other,type=bind",
        ):
            with pytest.raises(ValueError, match="collides"):
                runtime.build_run_command(
                    "docker",
                    pack,
                    workspace_root=repo,
                    command=["true"],
                    mounts=(mount,),
                )
    finally:
        runtime.resolve_linked_data_mounts = original


def test_docker_host_profile_requires_socket_and_projects_rw_bind(tmp_path: Path) -> None:
    """Explicit docker-host selection requires and projects an existing socket."""
    runtime = load_runtime_module()
    socket_path = tmp_path / "docker.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(socket_path))
    try:
        assert runtime.resolve_docker_host_mounts(socket_path=socket_path) == (
            f"{socket_path}:/var/run/docker.sock",
        )
    finally:
        sock.close()
        socket_path.unlink()
    with pytest.raises(ValueError, match="existing Unix socket"):
        runtime.resolve_docker_host_mounts(socket_path=socket_path)


def test_docker_host_profile_reaches_direct_run_command(tmp_path: Path) -> None:
    """Direct runner applies the docker-host bind only when profile-selected."""
    runtime = load_runtime_module()
    pack = runtime.ContainerPack(
        name="docker-host",
        dockerfile="docker/Dockerfile",
        context=".",
        target=None,
        image_tag="docker-host:fixture",
        platform=None,
        smoke=runtime.SmokeSpec(),
        runtime=runtime.RuntimeSpec(optional_mount_profiles=("docker-host",)),
    )
    original = runtime.resolve_docker_host_mounts
    runtime.resolve_docker_host_mounts = lambda: (
        "/var/run/docker.sock:/var/run/docker.sock",
    )
    try:
        command = runtime.build_run_command(
            "docker", pack, workspace_root=tmp_path, command=["true"]
        )
    finally:
        runtime.resolve_docker_host_mounts = original
    assert "/var/run/docker.sock:/var/run/docker.sock" in command


def test_docker_host_cli_mount_collision_is_rejected(tmp_path: Path) -> None:
    """CLI mounts cannot override the docker-host socket destination."""
    runtime = load_runtime_module()
    pack = runtime.ContainerPack(
        name="docker-host",
        dockerfile="docker/Dockerfile",
        context=".",
        target=None,
        image_tag="docker-host:fixture",
        platform=None,
        smoke=runtime.SmokeSpec(),
        runtime=runtime.RuntimeSpec(optional_mount_profiles=("docker-host",)),
    )
    original = runtime.resolve_docker_host_mounts

    def fake_docker_mount() -> tuple[str, ...]:
        """Return a deterministic selected docker-host bind."""
        return ("/var/run/docker.sock:/var/run/docker.sock",)

    runtime.resolve_docker_host_mounts = fake_docker_mount
    try:
        for mount in (
            "/other:/var/run/docker.sock",
            "type=bind,source=/other,dst=/var/run/docker.sock",
            "type=bind,source=/other,destination=/var/run/docker.sock",
            "dst=/var/run/docker.sock,source=/other,type=bind",
            "destination=/var/run/docker.sock,source=/other,type=bind",
            "target=/var/run/docker.sock,source=/other,type=bind",
        ):
            with pytest.raises(ValueError, match="docker-host socket"):
                runtime.build_run_command(
                    "docker",
                    pack,
                    workspace_root=tmp_path,
                    command=["true"],
                    mounts=(mount,),
                )
    finally:
        runtime.resolve_docker_host_mounts = original


def test_print_only_runner_projects_linked_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Print-only direct runner output includes the selected linked bind."""
    runner = load_runner_module()
    runtime: Any = runtime_module
    repo, pack_path, _ = write_parent_pack(tmp_path)
    original = runtime.resolve_linked_data_mounts
    runtime.resolve_linked_data_mounts = fixed_linked_mounts
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(RUNNER_SCRIPT),
            "--pack",
            str(pack_path),
            "--builder",
            "docker",
            "--workspace-root",
            str(repo),
            "--print-only",
        ],
    )
    try:
        assert runner.main() == 0
    finally:
        runtime.resolve_linked_data_mounts = original

    assert "/mnt/l/msm_data_root:/mnt/l/msm_data_root" in capsys.readouterr().out
