"""Focused tests for the container pack runtime helpers."""

# @dependency-start
# contract test
# responsibility Verifies container pack runtime mount resolution and direct-runner command construction.
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent default/opt-in runtime boundary
# upstream implementation ../../tools/ci/container_runtime.py shared container pack runtime helpers under test
# upstream implementation ../../tools/ci/run_container_pack.py direct pack runner exercised by the regression suite
# @dependency-end

from __future__ import annotations

import copy
import hashlib
import importlib.util
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from tools.ci import container_runtime as runtime_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_container_pack.py"
REPO_PROGRAM_SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_repo_program.py"


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


def test_workspace_discovery_uses_repo_markers_without_runtime_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Workspace discovery is independent of optional project pack files."""
    repo = tmp_path / "parent"
    nested = repo / "scripts" / "nested"
    (repo / ".git").mkdir(parents=True)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert runtime_module.detect_workspace_root() == repo


def test_repo_program_defaults_without_pack_or_python_rules(tmp_path: Path) -> None:
    """Direct execution uses Dockerfile defaults when optional TOML is absent."""
    repo = tmp_path / "parent"
    (repo / ".git").mkdir(parents=True)
    (repo / "docker").mkdir()
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    (repo / "docker" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "sample.py").write_text("print('fixture')\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_PROGRAM_SCRIPT),
            "--print-only",
            "--skip-env-check",
            "sample.py",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "docker/python-execution-rules.toml" not in result.stderr
    assert "docker/packs/default.toml" not in result.stderr
    assert "python3 /workspace/sample.py" in result.stdout
    assert "parent:agent-canon" in result.stdout


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


def test_docker_host_profile_requires_socket_and_projects_rw_bind() -> None:
    """Explicit docker-host selection requires and projects an existing socket."""
    runtime = load_runtime_module()
    socket_path = PROJECT_ROOT / "s"
    if socket_path.exists():
        pytest.skip("short parent-local socket path is already occupied")
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
    socket_path.write_text("not a socket\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="existing Unix socket"):
            runtime.resolve_docker_host_mounts(socket_path=socket_path)
    finally:
        socket_path.unlink(missing_ok=True)


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
    monkeypatch.setattr(runtime, "write_lifecycle_receipt", lambda *_args: None)
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


class FakeLifecycleDaemon:
    """In-memory daemon used to exercise exact-ID lifecycle cleanup."""

    def __init__(self, before: dict[str, object], after: dict[str, object], *, unknown_absence: bool = False) -> None:
        """Store deterministic pre/post inventories and optional readback failure."""
        self.snapshots = [before, after]
        self.removed: list[tuple[str, str]] = []
        self.restored_tags: list[tuple[str, str]] = []
        self.trace: list[tuple[str, str]] = []
        self.tag_targets: dict[str, str] = {}
        for resource in after.get("resources", []):
            if resource.get("kind") == "image":
                for tag in resource.get("tags", []):
                    self.tag_targets[str(tag)] = str(resource["immutable_id"])
        self.unknown_absence = unknown_absence

    def snapshot(self) -> dict[str, object]:
        """Return the next inventory snapshot."""
        return self.snapshots.pop(0)

    def remove(self, kind: str, immutable_id: str) -> int:
        """Record one exact-ID removal."""
        self.trace.append(("remove", immutable_id))
        self.removed.append((kind, immutable_id))
        return 0

    def inspect_absence(self, _kind: str, immutable_id: str) -> bool | None:
        """Return whether an exact ID has been removed or make it unknown."""
        if self.unknown_absence:
            return None
        return immutable_id in {item[1] for item in self.removed}

    def restore_image_tag(self, immutable_id: str, tag: str) -> int:
        """Retarget one image alias to the requested immutable ID."""
        self.trace.append(("restore", tag))
        self.restored_tags.append((immutable_id, tag))
        self.tag_targets[tag] = immutable_id
        return 0

    def inspect_image_tag(self, tag: str) -> str | None:
        """Read one exact fake image alias."""
        self.trace.append(("inspect-tag", tag))
        return self.tag_targets.get(tag)

    def remove_image_alias(self, immutable_id: str, tag: str) -> int:
        """Remove one exact fake image alias."""
        self.trace.append(("remove-alias", tag))
        self.removed.append(("image-alias", f"{immutable_id}:{tag}"))
        self.tag_targets.pop(tag, None)
        return 0

    def inspect_image_alias_absence(self, _immutable_id: str, _tag: str) -> bool:
        """Confirm fake alias absence."""
        return True


def lifecycle_snapshot(
    resources: list[dict[str, object]], daemon: dict[str, object] | None = None
) -> dict[str, object]:
    """Build one fake daemon snapshot with stable builder metadata."""
    return {
        "builder": "docker",
        "daemon": daemon or {"server": {"Version": "fake"}},
        "resources": resources,
    }


def lifecycle_labels(runtime: Any, context: Any) -> dict[str, str]:
    """Return the complete label set emitted for one fake invocation."""
    return context.labels()


def test_container_lifecycle_boundary_cleans_owned_ids_in_dependency_order() -> None:
    """Only new labelled resources are removed, container through image."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-1", "repo-1")
    labels = lifecycle_labels(runtime, context)
    preexisting = {
        "kind": "image",
        "immutable_id": "sha256:shared",
        "tags": ["shared:latest"],
        "labels": {},
    }
    created = [
        {"kind": "image", "immutable_id": "sha256:new", "digest": "sha256:new", "labels": labels},
        {"kind": "volume", "immutable_id": "vol-new", "labels": labels},
        {"kind": "network", "immutable_id": "net-new", "labels": labels},
        {"kind": "container", "immutable_id": "ctr-new", "labels": labels},
    ]
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([preexisting]),
        lifecycle_snapshot([preexisting, *created]),
    )
    boundary = runtime.ContainerLifecycleBoundary(
        context, daemon
    )

    receipt = boundary.record_create_or_pull(boundary.begin(), boundary.snapshot(), "run")
    result = boundary.cleanup(receipt)

    assert result.state == "cleaned"
    assert daemon.removed == [
        ("container", "ctr-new"),
        ("network", "net-new"),
        ("volume", "vol-new"),
        ("image", "sha256:new"),
    ]
    assert all(item.resource.immutable_id != "sha256:shared" or item.preexisting for item in receipt.resources)
    assert all(item.absence == "absent" for item in receipt.resources if item.created_or_pulled_by_task)
    payload = receipt.as_json()
    assert payload["schema"] == runtime.LIFECYCLE_SCHEMA
    assert payload["task_id"] == "task-1"
    assert payload["repo_identity"] == "repo-1"
    restored = runtime.lifecycle_receipt_from_json(payload)
    assert restored.context.lifecycle_id == context.lifecycle_id
    assert [item.resource.immutable_id for item in restored.resources] == [
        item.resource.immutable_id for item in receipt.resources
    ]
    assert all(item.absence == "absent" for item in restored.resources if item.created_or_pulled_by_task)


def test_container_lifecycle_boundary_blocks_unknown_absence_readback() -> None:
    """Cleanup remains blocked when immutable-ID absence cannot be proven."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-2", "repo-2")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot([{"kind": "container", "immutable_id": "ctr-2", "labels": labels}]),
        unknown_absence=True,
    )
    boundary = runtime.ContainerLifecycleBoundary(
        context, daemon
    )

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert result.state == "cleanup-blocked"
    assert result.removed_ids == ()
    assert receipt.failure is not None
    assert daemon.removed == [("container", "ctr-2")]


def test_lifecycle_receipt_rejects_string_bool_before_cleanup() -> None:
    """Malformed receipt booleans cannot be coerced into a cleanup authorization."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-bool", "repo-bool")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [{"kind": "container", "immutable_id": "ctr-bool", "labels": labels}]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)
    receipt = boundary.record_create_or_pull(boundary.begin(), boundary.snapshot())
    payload = receipt.as_json()
    rows = payload["resources"]
    assert isinstance(rows, list)
    rows[0]["created_or_pulled_by_task"] = "false"

    with pytest.raises(ValueError, match="created_or_pulled_by_task must be a boolean"):
        runtime.lifecycle_receipt_from_json(payload)
    assert daemon.removed == []


def test_lifecycle_receipt_rejects_nonstring_identity_before_cleanup() -> None:
    """Receipt identity fields reject numeric coercion."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-string", "repo-string")
    payload = runtime.ContainerLifecycleReceipt(
        context,
        runtime.DaemonSnapshot("docker", {"server": {"Version": "fake"}}, "ok"),
    ).as_json()
    payload["task_id"] = 42

    with pytest.raises(ValueError, match="task_id must be a string"):
        runtime.lifecycle_receipt_from_json(payload)


@pytest.mark.parametrize(
    ("schema_state", "schema_value"),
    (("missing", None), ("wrong", "other-schema"), ("nonstring", False)),
)
def test_lifecycle_receipt_rejects_missing_or_invalid_schema_before_cleanup(
    schema_state: str, schema_value: object
) -> None:
    """Malformed receipt schemas cannot reach lifecycle cleanup."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-schema", "repo-schema")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [{"kind": "container", "immutable_id": "ctr-schema", "labels": labels}]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)
    receipt = boundary.record_create_or_pull(boundary.begin(), boundary.snapshot())
    payload = receipt.as_json()
    if schema_state == "missing":
        payload.pop("schema")
    else:
        payload["schema"] = schema_value

    with pytest.raises(ValueError, match="lifecycle receipt schema"):
        runtime.lifecycle_receipt_from_json(payload)
    assert daemon.removed == []


@pytest.mark.parametrize("resource_state", ("partial", "nonterminal", "unknown"))
def test_container_lifecycle_blocks_partial_resource_observation(
    resource_state: str,
) -> None:
    """An incomplete daemon row cannot become a cleanup candidate."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-2b", "repo-2b")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [
                {
                    "kind": "container",
                    "immutable_id": "ctr-partial",
                    "labels": labels,
                    "state": resource_state,
                }
            ]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert receipt.state == "cleanup-blocked"
    assert result.state == "cleanup-blocked"
    assert receipt.failure is not None
    assert resource_state in receipt.failure
    assert daemon.removed == []


def test_container_lifecycle_blocks_unknown_snapshot_status() -> None:
    """An unknown inventory status is retained as a partial lifecycle outcome."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-2c", "repo-2c")
    labels = lifecycle_labels(runtime, context)
    before = lifecycle_snapshot([])
    after = lifecycle_snapshot(
        [{"kind": "container", "immutable_id": "ctr-unknown", "labels": labels}]
    )
    after["query_status"] = "unknown"
    daemon = FakeLifecycleDaemon(before, after)
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert result.state == "cleanup-blocked"
    assert receipt.failure is not None
    assert "after:query-status:unknown" in receipt.failure
    assert daemon.removed == []


def test_container_lifecycle_boundary_restores_tag_retarget() -> None:
    """A task-owned retarget is cleaned and the pre-existing tag is restored."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-3", "repo-3").bind_image_tag(
        "task:latest"
    )
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([
            {"kind": "image", "immutable_id": "sha256:old", "tags": ["task:latest"]}
        ]),
        lifecycle_snapshot([
            {
                "kind": "image",
                "immutable_id": "sha256:new",
                "tags": ["task:latest"],
                "labels": labels,
            }
        ]),
    )
    boundary = runtime.ContainerLifecycleBoundary(
        context, daemon
    )

    receipt = boundary.record(boundary.begin(), boundary.snapshot(), "build")

    assert receipt.state == "created"
    result = boundary.cleanup(receipt)
    assert result.state == "cleanup-blocked"
    assert daemon.removed == [("image", "sha256:new")]
    assert daemon.restored_tags == [("sha256:old", "task:latest")]
    assert daemon.trace.index(("restore", "task:latest")) < daemon.trace.index(("remove", "sha256:new"))


def test_container_lifecycle_boundary_blocks_concurrent_retarget() -> None:
    """A concurrent tag change blocks cleanup before deleting the new image."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-3b", "repo-3b").bind_image_tag(
        "task:latest"
    )
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([
            {"kind": "image", "immutable_id": "sha256:old", "tags": ["task:latest"]}
        ]),
        lifecycle_snapshot([
            {
                "kind": "image",
                "immutable_id": "sha256:new",
                "tags": ["task:latest"],
                "labels": labels,
            }
        ]),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)
    receipt = boundary.record(boundary.begin(), boundary.snapshot(), "build")
    daemon.tag_targets["task:latest"] = "sha256:concurrent"

    result = boundary.cleanup(receipt)

    assert result.state == "cleanup-blocked"
    assert result.removed_ids == ()
    assert daemon.removed == []
    assert receipt.failure is not None
    assert "tag retarget readback mismatch" in receipt.failure


def test_container_lifecycle_ignores_unrelated_new_resources() -> None:
    """Concurrent unrelated daemon activity is preserved, not a partial failure."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-4", "repo-4")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [
                {"kind": "network", "immutable_id": "shared-network"},
                {"kind": "container", "immutable_id": "owned", "labels": labels},
            ]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(
        context, daemon
    )

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert result.state == "cleaned"
    assert daemon.removed == [("container", "owned")]
    unrelated = next(item for item in receipt.resources if item.resource.immutable_id == "shared-network")
    assert unrelated.created_or_pulled_by_task is False
    assert unrelated.preservation_policy == "pre-snapshot-preserve"


def test_container_lifecycle_blocks_daemon_identity_change() -> None:
    """A daemon identity or builder change blocks resource attribution."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-4b", "repo-4b")
    labels = lifecycle_labels(runtime, context)
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([], daemon={"server": {"Version": "before"}}),
        lifecycle_snapshot(
            [{"kind": "container", "immutable_id": "ctr-new", "labels": labels}],
            daemon={"server": {"Version": "after"}},
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert receipt.state == "cleanup-blocked"
    assert result.state == "cleanup-blocked"
    assert receipt.failure is not None
    assert "daemon identity mismatch" in receipt.failure
    assert daemon.removed == []


def test_container_lifecycle_deduplicates_image_rows_and_unions_tags() -> None:
    """Docker's one-row-per-tag inventory becomes one immutable resource."""
    runtime = load_runtime_module()
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot(
            [
                {"kind": "image", "immutable_id": "sha256:one", "tags": ["one:a"]},
                {"kind": "image", "immutable_id": "sha256:one", "tags": ["one:b"]},
            ]
        ),
        lifecycle_snapshot([]),
    )
    boundary = runtime.ContainerLifecycleBoundary(
        runtime.LifecycleContext("task-5", "repo-5"), daemon
    )

    snapshot = boundary.begin().before

    assert [item.immutable_id for item in snapshot.resources] == ["sha256:one"]
    assert snapshot.resources[0].tags == ("one:a", "one:b")


def test_container_lifecycle_blocks_unproven_alias_on_preexisting_image() -> None:
    """An expected alias on a shared image is preserved without provenance."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-6", "repo-6").bind_image_tag(
        "task:temporary"
    )
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot(
            [{"kind": "image", "immutable_id": "sha256:shared", "tags": ["shared:stable"]}]
        ),
        lifecycle_snapshot(
            [
                {
                    "kind": "image",
                    "immutable_id": "sha256:shared",
                    "tags": [
                        "shared:stable",
                        "task:temporary",
                        "concurrent:unrelated",
                    ],
                }
            ]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(
        context, daemon
    )

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert result.state == "cleanup-blocked"
    assert receipt.failure is not None
    assert "lacks task provenance" in receipt.failure
    assert daemon.removed == []


def test_container_lifecycle_claims_new_expected_image_tag_without_labels() -> None:
    """A newly observed exact runner tag authorizes an otherwise unlabeled image."""
    runtime = load_runtime_module()
    context = runtime.LifecycleContext("task-6b", "repo-6b").bind_image_tag(
        "task:expected"
    )
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [{"kind": "image", "immutable_id": "sha256:task", "tags": ["task:expected"]}]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(context, daemon)

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert receipt.resources[0].created_or_pulled_by_task is True
    assert result.state == "cleaned"
    assert daemon.removed == [("image", "sha256:task")]


def test_lifecycle_context_default_identity_is_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Default task labels cannot collide for same-name concurrent invocations."""
    runtime = load_runtime_module()
    monkeypatch.delenv("AGENT_CANON_TASK_ID", raising=False)

    first = runtime.lifecycle_context(tmp_path, "docker", "run")
    second = runtime.lifecycle_context(tmp_path, "docker", "run")

    assert first.task_id != second.task_id
    assert first.lifecycle_id != second.lifecycle_id


def test_lifecycle_context_rejects_contradictory_task_repository_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ambient task/repository label cannot override its component identities."""
    runtime = load_runtime_module()
    monkeypatch.setenv("AGENT_CANON_TASK_ID", "task-identity")
    monkeypatch.setenv("AGENT_CANON_REPOSITORY_ID", "repo-identity")
    monkeypatch.setenv("AGENT_CANON_TASK_REPOSITORY", "other-task:other-repo")

    with pytest.raises(ValueError, match="match task and repository identity"):
        runtime.lifecycle_context(tmp_path, "docker", "run")


def test_lifecycle_nonce_prevents_same_task_concurrent_claim() -> None:
    """Identical task/repository labels do not authorize another nonce."""
    runtime = load_runtime_module()
    first = runtime.LifecycleContext("same-task", "same-repo")
    second = runtime.LifecycleContext("same-task", "same-repo")
    daemon = FakeLifecycleDaemon(
        lifecycle_snapshot([]),
        lifecycle_snapshot(
            [
                {
                    "kind": "container",
                    "immutable_id": "owned-by-first",
                    "labels": first.labels(),
                }
            ]
        ),
    )
    boundary = runtime.ContainerLifecycleBoundary(second, daemon)

    receipt = boundary.record(boundary.begin(), boundary.snapshot())
    result = boundary.cleanup(receipt)

    assert result.state == "not-created"
    assert daemon.removed == []


def test_task_scoped_image_tag_reserves_full_nonce_suffix() -> None:
    """Concurrent tags keep their complete nonce suffix within Docker's limit."""
    runtime = load_runtime_module()
    first = runtime.LifecycleContext("same-task", "same-repo", lifecycle_id="a" * 32)
    second = runtime.LifecycleContext("same-task", "same-repo", lifecycle_id="b" * 32)

    first_tag = runtime.task_scoped_image_tag("repo:" + "x" * 108, first)
    second_tag = runtime.task_scoped_image_tag("repo:" + "x" * 108, second)

    assert first_tag != second_tag
    assert len(first_tag.rsplit(":", 1)[1]) == 128
    assert first_tag.rsplit(":", 1)[1].endswith(
        "-ac-" + hashlib.sha256(
            f"{first.task_id}\0{first.lifecycle_id}".encode()
        ).hexdigest()[:16]
    )
    with pytest.raises(ValueError, match="too long"):
        runtime.task_scoped_image_tag("repo:" + "x" * 109, first)


def test_command_client_rc_one_permission_failure_is_unknown() -> None:
    """Only explicit not-found text proves absence; permission errors remain blocked."""
    runtime = load_runtime_module()
    client = runtime.CommandDaemonClient("docker")
    client._run = lambda _argv: subprocess.CompletedProcess(
        _argv, 1, stdout="", stderr="permission denied"
    )

    with pytest.raises(RuntimeError, match="permission denied"):
        client.inspect_absence("image", "sha256:blocked")


def test_command_client_accepts_podman_json_arrays() -> None:
    """Podman's array-form JSON inventory is normalized like Docker JSON lines."""
    runtime = load_runtime_module()
    result = subprocess.CompletedProcess(
        ["podman", "images"], 0, stdout='[{"Id":"sha256:podman"}]', stderr=""
    )

    assert runtime.CommandDaemonClient._json_lines(result) == [{"Id": "sha256:podman"}]


def test_command_client_snapshot_rejects_failed_or_invalid_daemon_identity() -> None:
    """A failed/invalid daemon identity cannot become a healthy snapshot."""
    runtime = load_runtime_module()
    client = runtime.CommandDaemonClient("docker")
    client._run = lambda _argv: subprocess.CompletedProcess(
        _argv, 1, stdout="{}", stderr="daemon unavailable"
    )
    with pytest.raises(RuntimeError, match="identity unavailable"):
        client.snapshot()

    client._run = lambda _argv: subprocess.CompletedProcess(
        _argv, 0, stdout="{}", stderr=""
    )
    with pytest.raises(ValueError, match="empty or malformed|missing server metadata"):
        client.snapshot()

    with pytest.raises(ValueError, match="missing version metadata"):
        runtime._stable_daemon_identity(
            "podman",
            {"host": {"cpuUtilization": {"idle": 99.0}}},
        )
    with pytest.raises(ValueError, match="missing Server version"):
        runtime._stable_daemon_identity("docker", {"Server": {"NCPU": 8}})


def test_stable_daemon_identity_ignores_podman_telemetry() -> None:
    """Telemetry changes do not block an otherwise identical Podman lifecycle."""
    runtime = load_runtime_module()
    payload: dict[str, object] = {
        "version": {
            "APIVersion": "4.9.0",
            "Version": "5.4.1",
            "BuiltTime": "2026-08-10T00:00:00Z",
        },
        "host": {
            "os": "linux",
            "arch": "amd64",
            "serviceIsRemote": False,
            "remoteSocket": {"path": "/run/podman/podman.sock", "exists": True},
            "idMappings": {"uidMap": [{"container_id": 0, "host_id": 1000}]},
            "cpuUtilization": {"idle": 91.0},
            "memFree": 123456,
        },
        "store": {
            "configFile": "/etc/containers/storage.conf",
            "graphRoot": "/var/lib/containers/storage",
            "runRoot": "/run/containers/storage",
            "graphDriverName": "overlay",
            "graphStatus": {"Backing Filesystem": "xfs"},
        },
    }
    telemetry = copy.deepcopy(payload)
    version = telemetry["version"]
    host = telemetry["host"]
    store = telemetry["store"]
    assert isinstance(version, dict)
    assert isinstance(host, dict)
    assert isinstance(store, dict)
    version["BuiltTime"] = "2026-08-11T00:00:00Z"
    host["cpuUtilization"] = {"idle": 42.0}
    host["memFree"] = 654321
    store["graphStatus"] = {"Backing Filesystem": "ext4"}

    before_identity = runtime._stable_daemon_identity("podman", payload)
    after_identity = runtime._stable_daemon_identity("podman", telemetry)
    assert before_identity == after_identity
    assert runtime.daemon_identity_fingerprint(
        runtime.DaemonSnapshot("podman", payload, "ok")
    ) == runtime.daemon_identity_fingerprint(
        runtime.DaemonSnapshot("podman", telemetry, "ok")
    )

    context = runtime.LifecycleContext("task", "repo", builder="podman")
    boundary = runtime.ContainerLifecycleBoundary(
        context,
        FakeLifecycleDaemon(
            {"builder": "podman", "daemon": before_identity, "resources": []},
            {"builder": "podman", "daemon": after_identity, "resources": []},
        ),
    )
    receipt = boundary.record_create_or_pull(boundary.begin(), boundary.snapshot())
    assert receipt.state == "not-created"


@pytest.mark.parametrize(
    ("section", "key", "replacement"),
    (
        ("version", "Version", "5.4.2"),
        ("store", "graphRoot", "/var/lib/containers/other-storage"),
        ("host", "remoteSocket", {"path": "/run/podman/other.sock"}),
    ),
)
def test_stable_podman_identity_mutation_blocks_cleanup(
    section: str, key: str, replacement: object
) -> None:
    """Stable Podman version/store/endpoint changes block attribution."""
    runtime = load_runtime_module()
    payload: dict[str, object] = {
        "version": {"APIVersion": "4.9.0", "Version": "5.4.1"},
        "host": {
            "os": "linux",
            "arch": "amd64",
            "serviceIsRemote": False,
            "remoteSocket": {"path": "/run/podman/podman.sock"},
            "idMappings": {"uidMap": [{"container_id": 0, "host_id": 1000}]},
        },
        "store": {
            "configFile": "/etc/containers/storage.conf",
            "graphRoot": "/var/lib/containers/storage",
            "runRoot": "/run/containers/storage",
            "graphDriverName": "overlay",
        },
    }
    changed = copy.deepcopy(payload)
    selected = changed[section]
    assert isinstance(selected, dict)
    selected[key] = replacement
    before_identity = runtime._stable_daemon_identity("podman", payload)
    after_identity = runtime._stable_daemon_identity("podman", changed)
    assert before_identity != after_identity

    context = runtime.LifecycleContext("task", "repo", builder="podman")
    boundary = runtime.ContainerLifecycleBoundary(
        context,
        FakeLifecycleDaemon(
            {"builder": "podman", "daemon": before_identity, "resources": []},
            {"builder": "podman", "daemon": after_identity, "resources": []},
        ),
    )
    receipt = boundary.record_create_or_pull(boundary.begin(), boundary.snapshot())
    assert receipt.state == "cleanup-blocked"
    assert receipt.failure and "daemon identity mismatch" in receipt.failure


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload["host"].update(serviceIsRemote="false"),
        lambda payload: payload["host"].update(remoteSocket={"path": ""}),
        lambda payload: payload["host"].pop("arch"),
        lambda payload: payload["store"].update(graphRoot=""),
        lambda payload: payload["store"].update(runRoot=0),
        lambda payload: payload["store"].update(graphDriverName=None),
    ),
)
def test_stable_podman_identity_rejects_missing_or_malformed_required_fields(
    mutation: Any,
) -> None:
    """Podman identity requires typed endpoint, platform, and storage fields."""
    runtime = load_runtime_module()
    payload: dict[str, object] = {
        "version": {"Version": "5.4.1", "APIVersion": "4.9.0"},
        "host": {
            "os": "linux",
            "arch": "amd64",
            "serviceIsRemote": False,
            "remoteSocket": {"path": "/run/podman/podman.sock"},
        },
        "store": {
            "graphRoot": "/var/lib/containers/storage",
            "runRoot": "/run/containers/storage",
            "graphDriverName": "overlay",
        },
    }
    mutation(payload)

    with pytest.raises(ValueError, match="podman daemon identity is missing"):
        runtime._stable_daemon_identity("podman", payload)


def test_lifecycle_receipt_path_rejects_symlink_escape(tmp_path: Path) -> None:
    """Receipt publication cannot resolve through a workspace symlink escape."""
    runtime = load_runtime_module()
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / ".agent-canon").symlink_to(outside, target_is_directory=True)
    receipt = runtime.ContainerLifecycleReceipt(
        runtime.LifecycleContext("task-7", str(root), operation="receipt"),
        runtime.DaemonSnapshot("docker", {}, "ok"),
    )

    with pytest.raises(ValueError, match="remain below workspace root"):
        runtime.lifecycle_receipt_path(root, receipt)


def test_lifecycle_receipt_identity_is_unique_and_collision_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent same-task lifecycles receive distinct paths and reject takeover."""
    runtime = load_runtime_module()
    first = runtime.ContainerLifecycleReceipt(
        runtime.LifecycleContext("same-task", "same-repo", operation="run"),
        runtime.DaemonSnapshot("docker", {}, "not-created"),
    )
    second = runtime.ContainerLifecycleReceipt(
        runtime.LifecycleContext("same-task", "same-repo", operation="run"),
        runtime.DaemonSnapshot("docker", {}, "not-created"),
    )

    assert runtime.lifecycle_receipt_path(tmp_path, first) != runtime.lifecycle_receipt_path(
        tmp_path, second
    )

    collision = tmp_path / "collision.json"
    collision.write_text('{"lifecycle_id":"another-invocation"}\n', encoding="utf-8")
    monkeypatch.setenv("AGENT_CANON_CONTAINER_LIFECYCLE_RECEIPT", str(collision))
    with pytest.raises(ValueError, match="receipt collision"):
        runtime.write_lifecycle_receipt(tmp_path, first)
