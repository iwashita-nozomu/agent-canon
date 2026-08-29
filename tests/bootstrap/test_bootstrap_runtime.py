"""Bootstrap tests use a stateful fake Docker executable, never Docker itself."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

import tools.runtime.container.bootstrap_runtime as bootstrap_runtime_module  # noqa: E402
from tools.runtime.container.bootstrap_runtime import (  # noqa: E402
    BootstrapError,
    BootstrapRuntime,
    DockerAdapter,
    _container_source_identity,
    _container_request_environment,
    build_parser,
    run,
    sha256_bytes,
    validate_roots,
)
from tools.runtime.archive.runtime_exchange_cleanup import clear_exchange  # noqa: E402


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
    from tools.runtime.archive.log_repository_identity import stable_source_repository_id

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
        "logs/github.com-iwashita-nozomu-agent-canon-"
        "9680c2230417944f4dd780e2"
    )


def test_source_identity_operation_has_no_runtime_side_effects(tmp_path: Path) -> None:
    """The internal identity operation needs neither state nor network access."""
    args = build_parser().parse_args(
        [
            "--container-control",
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
        "logs/github.com-iwashita-nozomu-agent-canon-"
        "9680c2230417944f4dd780e2"
    )


def test_source_identity_accepts_transport_variants_and_rejects_other_repo() -> None:
    """The host comparison can accept equivalent URLs without merging repositories."""
    equivalent = (
        "git@github.com:iwashita-nozomu/agent-canon.git",
        "ssh://git@github.com/iwashita-nozomu/agent-canon",
        "https://reader:credential@github.com:443/iwashita-nozomu/agent-canon.git",
    )
    identities = {_container_source_identity(remote)["repository_id"] for remote in equivalent}
    assert len(identities) == 1
    assert _container_source_identity(
        "https://github.com/iwashita-nozomu/agent-canon-log.git"
    )["repository_id"] not in identities


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


def test_default_source_runtime_rebuilds_without_copying_legacy_state(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Migrate the fixed legacy root and remove it only after new readback."""
    repository = tmp_path / "repo"
    (repository / "bootstrap").mkdir(parents=True)
    (repository / "bootstrap" / "host" / "manifest.toml").write_bytes(
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml").read_bytes()
    )
    scheduler_source = REPOSITORY_ROOT / "bootstrap" / "systemd" / "user"
    scheduler_target = repository / "bootstrap" / "systemd" / "user"
    scheduler_target.mkdir(parents=True)
    for template in scheduler_source.glob("*.in"):
        (scheduler_target / template.name).write_bytes(template.read_bytes())
    legacy = tmp_path / "workspace" / "agent-canon-runtime" / "host"
    (legacy / "unknown.sqlite").parent.mkdir(parents=True)
    (legacy / "unknown.sqlite").write_text("do not copy\n", encoding="utf-8")
    legacy_manager = BootstrapRuntime(
        tmp_path,
        legacy,
        repository_root=repository,
        docker=fake_docker,
    )
    with legacy_manager.locked():
        state = legacy_manager._new_state()
        state["state"] = "installed"
        state["resources"] = legacy_manager._resource_records()
        legacy_manager._write_state(state)

    manager = BootstrapRuntime(
        tmp_path,
        repository / ".runtime",
        repository_root=repository,
        docker=fake_docker,
    )
    with manager.locked():
        manager._prepare_legacy_runtime_reset()
        assert not (repository / ".runtime" / "unknown.sqlite").exists()
        assert legacy.is_dir()
        fresh = manager._new_state()
        fresh["state"] = "installed"
        fresh["resources"] = manager._resource_records()
        manager._write_mounts(fresh)
        manager._write_state(fresh)
        manager._finalize_legacy_runtime_reset()
    assert not legacy.exists()
    assert not legacy.parent.exists()


def test_explicit_roots_canonicalize_dot_segments_after_symlink_validation(
    tmp_path: Path,
) -> None:
    """Use one canonical host path for state, mount creation, and readback."""
    control = tmp_path / "control"
    nested = control / "nested"
    nested.mkdir(parents=True)

    observed_control, observed_runtime = validate_roots(
        nested / "..", nested / ".." / "runtime"
    )

    assert observed_control == control
    assert observed_runtime == control / "runtime"


def test_explicit_roots_reject_symlink_even_when_dot_segments_cancel_it(
    tmp_path: Path,
) -> None:
    """Do not let lexical normalization hide a traversed symlink component."""
    control = tmp_path / "control"
    outside = tmp_path / "outside"
    control.mkdir()
    outside.mkdir()
    (control / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BootstrapError, match="symlink_path_rejected"):
        validate_roots(control, control / "link" / ".." / "runtime")


def test_start_accepts_daemon_canonical_mount_readback(
    tmp_path: Path,
    fake_docker: DockerAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Match rootful Docker inspect output to the canonical admitted roots."""
    control = tmp_path / "control"
    nested = control / "nested"
    nested.mkdir(parents=True)
    monkeypatch.setenv("FAKE_DOCKER_CANONICALIZE_MOUNTS", "1")
    manager = BootstrapRuntime(
        nested / "..",
        nested / ".." / "runtime",
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )

    manager.install()

    assert manager.start()["after_state"] == "ready"


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
    install_commands = list(fake_docker.commands)
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
    build = next(command for command in install_commands if command[1] == "build")
    assert "--build-arg" not in build
    assert not any(command[1:3] == ["container", "ls"] for command in install_commands)
    create = next(command for command in fake_docker.commands if command[1] == "create")
    assert "--user" not in create
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


def test_preseeded_image_tag_is_adopted_without_overwrite_or_cleanup(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Protect an existing matching image tag from replacement and deletion."""
    manager = runtime(tmp_path, fake_docker)
    image_tag = manager._image_tag()
    state_path = Path(os.environ["FAKE_DOCKER_STATE"])
    state_path.write_text(
        json.dumps(
            {
                "images": {
                    image_tag: {
                        "Id": "sha256:preseeded-image",
                        "RepoTags": [image_tag],
                        "Config": {"Labels": manager._labels()},
                    }
                },
                "containers": {},
                "next": 1,
            }
        ),
        encoding="utf-8",
    )

    installed = manager.install()
    image = installed["resource_ids"]["image"]
    assert image["id"] == "sha256:preseeded-image"
    assert image["owned"] is False
    assert not any(command[1] == "build" for command in fake_docker.commands)

    manager.uninstall()
    assert manager.docker.inspect_image(image_tag) is not None
    assert not any(command[1:3] == ["image", "rm"] for command in fake_docker.commands)


def test_health_polling_waits_for_starting_container(
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Poll a starting health state instead of failing immediately."""
    monkeypatch.setenv("FAKE_DOCKER_HEALTH_POLLS", "2")
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.start()
    inspect_count_before_status = sum(
        command[1:3] == ["container", "inspect"] for command in fake_docker.commands
    )
    # name lookup + post-create readback + three health polls + one final
    # immutable readback; no immutable validation happens inside the polls.
    assert inspect_count_before_status == 6
    state = manager.status()["details"]["docker_container"]
    assert state["health"] == "healthy"


def test_health_final_readback_catches_security_drift_after_polling(
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch a resource drift once after health becomes healthy."""
    monkeypatch.setenv("FAKE_DOCKER_DRIFT_ON_HEALTH", "network")
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    with pytest.raises(BootstrapError, match="docker_readback_invalid"):
        manager.start()

    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    container = state["resources"]["container"]
    assert container["state"] == "quarantined"
    assert container["id"]
    assert manager.docker.inspect_container(container["id"]) is None


def test_health_timeout_quarantines_and_removes_container(
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop and quarantine a container that never reaches healthy."""
    monkeypatch.setenv("FAKE_DOCKER_HEALTH_POLLS", "1000")
    manifest = tmp_path / "manifest.toml"
    source = (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml").read_text(
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


def test_start_refuses_foreign_named_container_without_adopting_or_cleaning(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Keep a same-name container owned by another control root untouched."""
    first_control = tmp_path / "first-control"
    first_control.mkdir()
    first = BootstrapRuntime(
        first_control,
        first_control / "runtime",
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )
    first.install()
    first.start()

    second_control = tmp_path / "second-control"
    second_control.mkdir()
    second = BootstrapRuntime(
        second_control,
        second_control / "runtime",
        repository_root=REPOSITORY_ROOT,
        docker=fake_docker,
    )
    second.install()
    with pytest.raises(BootstrapError, match="shared_runtime_owned_elsewhere"):
        second.start()

    first.uninstall()


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


def test_target_add_prunes_missing_target_and_is_idempotent(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Target convergence removes one stale row while retaining a valid sibling."""
    manager = runtime(tmp_path, fake_docker)
    stale = tmp_path / "stale"
    valid = tmp_path / "valid"
    stale.mkdir()
    valid.mkdir()
    manager.install()
    manager.start()
    manager.target_add(stale)
    manager.target_add(valid)

    stale.rmdir()
    converged = manager.target_add(valid)
    assert converged["code"] == "generation_active"
    state = manager.status()["details"]["state"]
    valid_digest = sha256_bytes(str(valid.resolve()).encode("utf-8"))
    assert state["target_digests"] == [valid_digest]
    registry = manager.paths.mounts.read_text(encoding="utf-8")
    assert f"[targets.{valid_digest}]" in registry
    assert str(stale.resolve()) not in registry

    repeated = manager.target_add(valid)
    assert repeated["code"] == "target_unchanged"
    assert repeated["details"]["changed"] is False


def test_fresh_install_and_update_prune_retained_stale_targets(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Reinstalling an uninstalled runtime keeps valid targets only."""
    manager = runtime(tmp_path, fake_docker)
    stale = tmp_path / "stale"
    valid = tmp_path / "valid"
    stale.mkdir()
    valid.mkdir()
    manager.install()
    manager.start()
    manager.target_add(stale)
    manager.target_add(valid)
    manager.uninstall()
    stale.rmdir()

    manager.install()
    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    valid_digest = sha256_bytes(str(valid.resolve()).encode("utf-8"))
    assert list(state["targets"]) == [valid_digest]
    registry = manager.paths.mounts.read_text(encoding="utf-8")
    assert f"[targets.{valid_digest}]" in registry
    assert str(stale.resolve()) not in registry
    manager.uninstall()

    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    stale_digest = sha256_bytes(str(stale.resolve()).encode("utf-8"))
    state["targets"][stale_digest] = {
        "root": str(stale.resolve()),
        "mode": "read-only",
        "digest": stale_digest,
    }
    manager.paths.state.write_text(json.dumps(state), encoding="utf-8")
    manager._legacy_runtime_pending_cleanup = tmp_path / "legacy-runtime"
    manager._finalize_legacy_runtime_reset = lambda: None  # type: ignore[method-assign]
    assert manager.update()["code"] == "updated"
    state = json.loads(manager.paths.state.read_text(encoding="utf-8"))
    assert list(state["targets"]) == [valid_digest]
    registry = manager.paths.mounts.read_text(encoding="utf-8")
    assert f"[targets.{valid_digest}]" in registry
    assert str(stale.resolve()) not in registry


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
    routed_external = manager.tool_run("template-bundle", ["export", "--help"])
    assert routed_external["details"]["argv"][:3] == ["agent-canon-tool", "tool", "run"]
    docker_exec = next(
        command
        for command in reversed(fake_docker.commands)
        if command[1] == "exec" and "template-bundle" in command
    )
    output_env = next(
        docker_exec[index + 1]
        for index, value in enumerate(docker_exec)
        if value == "--env" and docker_exec[index + 1].startswith("AGENT_CANON_OUTPUT_ROOT=")
    )
    assert output_env == "AGENT_CANON_OUTPUT_ROOT=/var/lib/agent-canon/runtime/tool-output"
    assert "AGENT_CANON_HOOK_ARCHIVE_DIR=/var/lib/agent-canon/private-log" in docker_exec
    assert "AGENT_CANON_LOG_ROOT=/var/lib/agent-canon/private-log" in docker_exec


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
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
    monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)
    monkeypatch.setenv("AGENT_CANON_PRIVATE_LOG_ROOT", str(private_log))

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
            {"catalog_id": catalog_id, "argv": argv, "root": root, "environment": environment}
        )
        return {"code": "completed"}

    monkeypatch.setattr(BootstrapRuntime, "tool_run", fake_tool_run)
    args = build_parser().parse_args(
        [
            "--container-control",
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
    assert mapped["AGENT_CANON_SOURCE_ROOT"] == "/usr/local/share/agent-canon/runtime"
    assert mapped["AGENT_CANON_ROOT"] == "/usr/local/share/agent-canon/runtime"
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
    (control / "private-log").mkdir()
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
    state.update({"state": "ready", "targets": {digest: target_record}, "resources": manager._resource_records()})
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
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
            "--container-control",
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
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex receives a session root below the bootstrap-owned runtime."""
    manager = runtime(tmp_path, fake_docker)
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
    manager.install()

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

    with pytest.raises(BootstrapError, match="archive path does not match private log mount"):
        _container_request_environment(
            request,
            container_target=Path("/targets/target"),
            source_root=source,
            host_runtime=runtime_root,
            host_control=control,
            host_private_log=private_log,
        )


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
    assert "canary" not in failure.value.evidence["stderr_preview"]
    assert "<redacted>" in failure.value.evidence["stderr_preview"]
    assert "terminal-diagnostic" in failure.value.evidence["stderr_preview"]
    assert failure.value.evidence["stderr_truncated"] is True
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


def test_container_rollback_restores_previous_targets_and_generation_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resident rollback applies the host-provided previous target manifest."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    control.mkdir()
    (control / "private-log").mkdir()
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
    manager = BootstrapRuntime(
        control, runtime_root, repository_root=REPOSITORY_ROOT
    )
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
                "container": {"id": "container-current", "state": "running", "owned": True},
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
            "--container-control",
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
    assert f"{previous_digest}\t{previous_root}\t/targets/{previous_digest}\tread-only" in (
        runtime_root / "mounts.tsv"
    ).read_text(encoding="utf-8")


def test_container_restore_reads_mounted_target_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """State-only recovery reads the target backup through the runtime mount."""
    control = tmp_path / "control"
    runtime_root = control / "runtime"
    control.mkdir()
    (control / "private-log").mkdir()
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
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
                "container": {"id": "container-candidate", "state": "running", "owned": True},
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
    monkeypatch.setenv(
        "AGENT_CANON_CURRENT_IMAGE_ID", candidate_id
    )
    monkeypatch.setenv(
        "AGENT_CANON_RESTORE_TARGETS_FILE",
        str(backup),
    )
    args = build_parser().parse_args(
        [
            "--container-control",
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
    (control / "private-log").mkdir()
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
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
                "image": {"id": image_id, "tag": image_ref, "state": "present", "owned": True},
                "container": {"id": "container-shared", "state": "running", "owned": True},
            },
        }
    )
    manager._write_mounts(state)
    manager._write_mount_manifest(state)
    manager._write_state(state)
    target_a, target_b = tmp_path / "target-a", tmp_path / "target-b"
    target_a.mkdir()
    target_b.mkdir()

    def target_args(action: str, root: Path, digest: str) -> Any:
        monkeypatch.setenv("AGENT_CANON_TARGET_HOST_ROOT", str(root))
        monkeypatch.setenv("AGENT_CANON_TARGET_CONTAINER_ROOT", f"/targets/{digest}")
        monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)
        return build_parser().parse_args(
            [
                "--container-control",
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
    plan = runtime_root / "rollback-plan.tsv"
    assert plan.is_file()
    assert "target-a" in plan.read_text(encoding="utf-8")

    def rollback_args() -> Any:
        monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_ID", image_id)
        monkeypatch.setenv("AGENT_CANON_RESTORE_IMAGE_REF", image_ref)
        monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_ID", image_id)
        monkeypatch.setenv("AGENT_CANON_CURRENT_IMAGE_REF", image_ref)
        return build_parser().parse_args(
            [
                "--container-control",
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
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
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
            "--container-control",
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


def test_gc_enforces_archive_quota_only_without_unpublished_spool(
    tmp_path: Path, fake_docker: DockerAdapter
) -> None:
    """Prune a reproducible archive cache, but never while a spool is pending."""
    manifest = tmp_path / "manifest.toml"
    manifest.write_text(
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml")
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
    generated = manager.paths.container_runtime / "tmp" / "pytest-of-agentcanon"
    generated.mkdir(parents=True)
    (generated / "artifact").write_text("fixture", encoding="utf-8")
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
    cleanup_index = next(
        index
        for index, command in enumerate(fake_docker.commands)
        if command[-2:] == [
            "python3",
            "/usr/local/share/agent-canon/runtime/tools/agent_tools/"
            "runtime_exchange_cleanup.py",
        ]
    )
    stop_index = next(
        index
        for index, command in enumerate(fake_docker.commands)
        if len(command) > 1 and command[1] == "stop"
    )
    assert cleanup_index < stop_index


def test_exchange_cleanup_unlinks_symlink_without_touching_target(tmp_path: Path) -> None:
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
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml")
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
    updated = changed.update()
    rebound = json.loads(changed.paths.state.read_text(encoding="utf-8"))
    assert updated["code"] == "updated"
    assert rebound["manifest_digest"] == changed.manifest_digest


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
        build_parser().parse_args(base + ["sync", "--install-root", str(REPOSITORY_ROOT)])
    controller = (REPOSITORY_ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "SourceSync" not in controller
    assert "source_sync_image_required" not in controller
    assert not (REPOSITORY_ROOT / "tools/agent_tools/source_sync.py").exists()


def test_status_reads_host_owned_source_sync_record(tmp_path: Path) -> None:
    """Status reads the canonical host record rather than container state."""
    state_path = tmp_path / "runtime" / "source-sync.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema": "agent-canon.source-sync.v1",
                "status": "failed",
                "code": "source_sync_candidate_failed",
                "source_root": "/source",
                "source_head": "1" * 40,
                "source_tree": "2" * 40,
                "remote": "origin",
                "remote_url": "remote",
                "branch": "main",
                "updated_at": "2026-08-27T00:00:00Z",
                "failure": "source_sync_candidate_failed",
            }
        ),
        encoding="utf-8",
    )
    manager = BootstrapRuntime(
        tmp_path,
        state_path.parent,
        repository_root=REPOSITORY_ROOT,
        docker=DockerAdapter(str(REPOSITORY_ROOT / "tests/bootstrap/fake_docker.py")),
    )
    # Avoid a lifecycle install; status's state fallback is enough to exercise
    # the source-sync reader and its owner path.
    manager.paths.state.parent.mkdir(parents=True, exist_ok=True)
    manager.paths.state.write_text(json.dumps(manager._new_state()), encoding="utf-8")
    result = manager.status()
    assert result["details"]["source_sync"]["failure"] == "source_sync_candidate_failed"
    for invalid_state in (
        {
            "failure": "old",
            "schema": "agent-canon.source-sync.v1",
            "status": "failed",
            "updated_at": "2026-08-26T00:00:00Z",
        },
        {"schema": "agent-canon.source-sync.v1", "status": 7},
        {
            "schema": "agent-canon.source-sync.v1",
            "status": "success",
            "code": "up_to_date",
        },
    ):
        state_path.write_text(json.dumps(invalid_state), encoding="utf-8")
        assert manager.status()["details"]["source_sync"] is None


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
    tmp_path: Path, fake_docker: DockerAdapter, monkeypatch: pytest.MonkeyPatch
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
        (REPOSITORY_ROOT / "bootstrap" / "host" / "manifest.toml")
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
    eval_command = next(
        command
        for command in fake_docker.commands
        if "/usr/local/share/agent-canon/runtime/eval/producers/run_accumulated_agent_evals.py"
        in command
    )
    assert eval_command[eval_command.index("--root") + 1] == (
        "/usr/local/share/agent-canon/runtime"
    )
    observed_target = eval_command[eval_command.index("--target-root") + 1]
    assert observed_target.startswith("/targets/")
    assert eval_command[eval_command.index("--prompt-eval-manifest") + 1] == (
        "/usr/local/share/agent-canon/runtime/evidence/agent-evals/"
        "skill_workflow_prompt_eval.toml"
    )
    spool = manager.paths.runtime_root / "spool" / "eval-e2e"
    assert (spool / "collection.json").is_file()
    assert (source / "README.md").read_bytes() == before
    monkeypatch.delenv("AGENT_CANON_TARGET_DIGEST", raising=False)
    synced = manager.eval_sync("eval-e2e")
    assert synced["code"] == "host_archive_requested"
    assert synced["details"] == {
        "execution_plane": "host_archive_adapter",
        "run_id": "eval-e2e",
        "status": "requested",
    }
    request = spool / "sync-request.tsv"
    assert request.read_text(encoding="utf-8") == (
        "schema\tagent-canon.eval-sync-request.v1\n"
        "operation\tsync\n"
        "execution-plane\tagentcanon_tool_container\n"
        "run-id\teval-e2e\n"
        "target-digest\t\n"
        f"source-root\t{source}\n"
    )
    assert spool.is_dir()
    assert not (manager.paths.runtime_root / "archive" / "agent-canon-log").exists()


def test_eval_producer_failure_is_not_masked_by_missing_export(
    tmp_path: Path,
    fake_docker: DockerAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve producer failure evidence before attempting Host export."""
    source = tmp_path / "source-free-parent"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    (source / "README.md").write_text("source-free fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
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
        cwd=source,
        check=True,
    )
    manager = runtime(tmp_path, fake_docker)
    manager.install()
    manager.start()
    manager.target_add(source)
    monkeypatch.setenv("FAKE_EVAL_FAIL", "1")

    with pytest.raises(BootstrapError) as failure:
        manager.eval_collect(source, "producer-failure")

    assert failure.value.code == "eval_producer_failed"
    spool = manager.paths.runtime_root / "spool" / "producer-failure"
    collection = json.loads((spool / "collection.json").read_text(encoding="utf-8"))
    assert collection["status"] == "failed"
    assert collection["failure"] == "eval_producer_failed"
    assert len(collection["producer_matrix"]) == 4
    assert (spool / "producer-logs").is_dir()
