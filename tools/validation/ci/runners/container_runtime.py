#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides container runtime CI automation.
# upstream design ../README.md shared automation index
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md exact runtime receipt names
# @dependency-end

"""Shared helpers for repo-defined container runtime scripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

try:
    from tools.runtime.artifacts.runtime_artifacts import (
        RuntimeArtifactBoundary,
        RuntimeArtifactError,
    )
except ImportError:  # pragma: no cover - direct script loading.
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from tools.runtime.artifacts.runtime_artifacts import (  # type: ignore[no-redef]
        RuntimeArtifactBoundary,
        RuntimeArtifactError,
    )


def detect_workspace_root() -> Path:
    """Return the repo root even when reached through a symlink view."""
    markers = (".git", "README.md")
    search_roots = [Path.cwd().resolve(), Path(__file__).absolute().parent]
    for search_root in search_roots:
        for candidate in (search_root, *search_root.parents):
            if all((candidate / marker).exists() for marker in markers):
                return candidate
    return Path(__file__).absolute().parents[2]


# Resolve the standalone AgentCanon source checkout for runtime helpers.
WORKSPACE_ROOT = detect_workspace_root()
HOST_GH_CONFIG = Path.home() / ".config" / "gh"
HOST_SSH_DIR = Path.home() / ".ssh"
BUILDER_INFO_TIMEOUT_SECONDS = 15
HOST_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
CONTAINER_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
DOCKER_HOST_SOCKET = Path("/var/run/docker.sock")
PROCESS_UMASK = 0o0007
DIRECTORY_MODE = 0o2770
FILE_MODE = 0o0660
LOCAL_FLOCK_FILESYSTEMS = ("btrfs", "ext4", "xfs")
PROVISION_RECEIPT_NAME = "shared-runtime-provision.json"
READBACK_RECEIPT_NAME = "shared-runtime-readback.json"
RUNTIME_ROUTE = "MANAGED_CONTAINER"
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
OPTIONAL_MOUNT_PROFILES = frozenset(
    {
        "host-zshrc",
        "host-git",
        "host-secrets",
        "host-credentials",
        "ssh-agent",
        "docker-host",
        "linked-data-roots",
    }
)
LINKED_DATA_TARGET_RE = re.compile(r"/mnt/[a-z]/[^/].*\Z")


@dataclass(frozen=True)
class SmokeSpec:
    """Describe how to smoke-test a built image."""

    shell: str = "/bin/bash"
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeSpec:
    """Describe runtime mounts and env for one pack run."""

    shell: str = "/bin/bash"
    workdir: str = "/workspace"
    workspace_mount: str = "/workspace"
    env: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    gpus: str | None = None
    optional_mount_profiles: tuple[str, ...] = ()
    linked_data_roots: tuple[LinkedDataRoot, ...] = ()
    linked_data_roots_declared: bool = False


@dataclass(frozen=True)
class LinkedDataRoot:
    """Describe one repository symlink and its exact declared data target."""

    link: str
    target: str


@dataclass(frozen=True)
class ContainerPack:
    """Describe one reusable container runtime pack."""

    name: str
    dockerfile: str
    context: str
    target: str | None
    image_tag: str
    platform: str | None
    smoke: SmokeSpec
    runtime: RuntimeSpec


@dataclass(frozen=True)
class HostRuntimeFeatures:
    """Describe host-dependent runtime features shared across container entrypoints."""

    has_gpu: bool
    has_host_gh_config: bool
    has_host_ssh_dir: bool
    ssh_auth_sock: str | None


LIFECYCLE_SCHEMA = "agent-canon.container-lifecycle.v1"
TASK_LABEL = "com.agent-canon.task-id"
REPOSITORY_LABEL = "com.agent-canon.repository"
TASK_REPOSITORY_LABEL = "com.agent-canon.task-repository"
LIFECYCLE_LABEL = "com.agent-canon.lifecycle-id"
LIFECYCLE_KINDS = ("container", "network", "volume", "image")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class LifecycleContext:
    """Immutable task/repository identity used to scope daemon resources."""

    task_id: str
    repo_identity: str
    builder: str = "docker"
    task_repo_label: str | None = None
    operation: str = "run"
    lifecycle_id: str = field(default_factory=lambda: secrets.token_hex(16))
    expected_image_tags: tuple[str, ...] = ()

    def labels(self) -> dict[str, str]:
        """Return stable labels required on task-created resources."""
        return {
            TASK_LABEL: self.task_id,
            REPOSITORY_LABEL: self.repo_identity,
            TASK_REPOSITORY_LABEL: self.task_repo_label
            or f"{self.task_id}:{self.repo_identity}",
            LIFECYCLE_LABEL: self.lifecycle_id,
        }

    def bind_image_tag(self, image_tag: str) -> LifecycleContext:
        """Return this invocation context bound to one exact image tag."""
        if not image_tag or CONTROL_RE.search(image_tag):
            raise ValueError("expected image tag must be non-empty and label-safe")
        return replace(
            self,
            expected_image_tags=tuple(
                dict.fromkeys((*self.expected_image_tags, image_tag))
            ),
        )


def lifecycle_context(
    workspace_root: Path, builder: str, operation: str
) -> LifecycleContext:
    """Derive stable task/repository labels without host-global state."""
    task_id = os.environ.get("AGENT_CANON_TASK_ID") or (
        f"{operation}-{workspace_root.name}-{os.getpid()}-{time.time_ns()}"
    )
    repo_identity = os.environ.get("AGENT_CANON_REPOSITORY_ID") or str(
        workspace_root.resolve()
    )
    task_repo_label = os.environ.get("AGENT_CANON_TASK_REPOSITORY")
    lifecycle_id = os.environ.get("AGENT_CANON_LIFECYCLE_ID") or secrets.token_hex(16)
    expected_tags_raw = os.environ.get("AGENT_CANON_EXPECTED_IMAGE_TAG", "")
    expected_image_tags = tuple(
        dict.fromkeys(tag for tag in expected_tags_raw.split(",") if tag)
    )
    for name, value in (
        ("AGENT_CANON_TASK_ID", task_id),
        ("AGENT_CANON_REPOSITORY_ID", repo_identity),
        ("AGENT_CANON_TASK_REPOSITORY", task_repo_label),
        ("AGENT_CANON_LIFECYCLE_ID", lifecycle_id),
    ):
        if value is not None and (not value or CONTROL_RE.search(value)):
            raise ValueError(f"{name} must be a non-empty label-safe value")
    if task_repo_label is not None and task_repo_label != f"{task_id}:{repo_identity}":
        raise ValueError(
            "AGENT_CANON_TASK_REPOSITORY must match task and repository identity"
        )
    return LifecycleContext(
        task_id=task_id,
        repo_identity=repo_identity,
        builder=builder,
        task_repo_label=task_repo_label,
        operation=operation,
        lifecycle_id=lifecycle_id,
        expected_image_tags=expected_image_tags,
    )


@dataclass(frozen=True)
class DaemonResource:
    """Daemon object carrying an immutable cleanup identity."""

    kind: str
    immutable_id: str
    digest: str | None = None
    name: str | None = None
    tags: tuple[str, ...] = ()
    labels: tuple[tuple[str, str], ...] = ()
    project: str | None = None
    state: str | None = None
    image_id: str | None = None

    def __post_init__(self) -> None:
        """Validate the immutable resource kind and identifier."""
        if self.kind not in LIFECYCLE_KINDS:
            raise ValueError(f"unsupported daemon resource kind: {self.kind}")
        if not self.immutable_id or self.immutable_id.startswith("-"):
            raise ValueError("daemon resource immutable_id must be non-empty")

    @property
    def label_map(self) -> dict[str, str]:
        """Return normalized labels as a mapping."""
        return dict(self.labels)

    def as_json(self) -> dict[str, object]:
        """Serialize this immutable resource for a lifecycle receipt."""
        return {
            "kind": self.kind,
            "immutable_id": self.immutable_id,
            "digest": self.digest,
            "name": self.name,
            "tags": list(self.tags),
            "labels": dict(self.labels),
            "project": self.project,
            "state": self.state,
            "image_id": self.image_id,
        }


@dataclass(frozen=True)
class DaemonSnapshot:
    """Immutable pre/post daemon inventory."""

    builder: str
    daemon: Mapping[str, object]
    query_status: str
    resources: tuple[DaemonResource, ...] = ()
    captured_at: float = 0.0

    def by_kind(self, kind: str) -> tuple[DaemonResource, ...]:
        """Return resources of one exact daemon kind."""
        return tuple(item for item in self.resources if item.kind == kind)

    def as_json(self) -> dict[str, object]:
        """Serialize this daemon snapshot for a lifecycle receipt."""
        return {
            "builder": self.builder,
            "daemon": dict(self.daemon),
            "query_status": self.query_status,
            "resources": [item.as_json() for item in self.resources],
            "captured_at": self.captured_at,
        }


_STABLE_VALUE_MISSING = object()


def _mapping_value(
    mapping: Mapping[str, object], names: tuple[str, ...]
) -> object:
    """Return one field using case-insensitive aliases from daemon JSON."""
    for name in names:
        if name in mapping:
            return mapping[name]
    folded = {
        key.casefold(): value
        for key, value in mapping.items()
    }
    for name in names:
        value = folded.get(name.casefold(), _STABLE_VALUE_MISSING)
        if value is not _STABLE_VALUE_MISSING:
            return value
    return _STABLE_VALUE_MISSING


def _stable_json_value(value: object) -> object:
    """Copy JSON-compatible values while rejecting opaque daemon objects."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        typed_value = cast(Mapping[object, object], value)
        copied: dict[str, object] = {}
        for key, item in typed_value.items():
            if not isinstance(key, str):
                continue
            stable_item = _stable_json_value(item)
            if stable_item is not _STABLE_VALUE_MISSING:
                copied[key] = stable_item
        return copied
    if isinstance(value, (list, tuple)):
        typed_value = cast(list[object] | tuple[object, ...], value)
        copied_items: list[object] = []
        for item in typed_value:
            stable_item = _stable_json_value(item)
            if stable_item is not _STABLE_VALUE_MISSING:
                copied_items.append(stable_item)
        return copied_items
    return _STABLE_VALUE_MISSING


def _stable_scalar(value: object) -> object:
    """Keep only stable daemon scalar fields (strings and booleans)."""
    if isinstance(value, (str, bool)):
        return value
    return _STABLE_VALUE_MISSING


def _project_stable_scalars(
    mapping: Mapping[str, object],
    fields: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, object]:
    """Project named daemon fields without importing telemetry or counters."""
    projected: dict[str, object] = {}
    for output_name, names in fields:
        value = _mapping_value(mapping, names)
        stable_value = _stable_scalar(value)
        if stable_value is not _STABLE_VALUE_MISSING:
            projected[output_name] = stable_value
    return projected


def _project_podman_id_mappings(value: object) -> object:
    """Keep only stable UID/GID mapping rows from Podman's host payload."""
    if not isinstance(value, Mapping):
        return _STABLE_VALUE_MISSING
    typed_value = cast(Mapping[str, object], value)
    projected: dict[str, object] = {}
    for output_name, names in (("uidmap", ("uidmap",)), ("gidmap", ("gidmap",))):
        item = _mapping_value(typed_value, names)
        stable_item = _stable_json_value(item)
        if stable_item is not _STABLE_VALUE_MISSING:
            projected[output_name] = stable_item
    return projected


def _stable_podman_identity(payload: Mapping[str, object]) -> dict[str, object]:
    """Project Podman info onto the daemon identity fields that can be stable."""
    version_value = _mapping_value(payload, ("version", "Version"))
    host_value = _mapping_value(payload, ("host", "Host"))
    store_value = _mapping_value(payload, ("store", "Store"))
    version = (
        _project_stable_scalars(
            cast(Mapping[str, object], version_value),
            (
                ("Version", ("Version",)),
                ("APIVersion", ("APIVersion", "ApiVersion")),
                ("GitCommit", ("GitCommit",)),
                ("GoVersion", ("GoVersion",)),
                ("OsArch", ("OsArch", "OSArch")),
            ),
        )
        if isinstance(version_value, Mapping)
        else {}
    )
    host: dict[str, object] = {}
    if isinstance(host_value, Mapping):
        typed_host = cast(Mapping[str, object], host_value)
        host.update(
            _project_stable_scalars(
                typed_host,
                (
                    ("arch", ("arch",)),
                    ("os", ("os",)),
                    ("kernel", ("kernel",)),
                    ("hostname", ("hostname",)),
                    ("serviceIsRemote", ("serviceIsRemote",)),
                    ("cgroupManager", ("cgroupManager",)),
                    ("cgroupVersion", ("cgroupVersion",)),
                    ("databaseBackend", ("databaseBackend",)),
                    ("networkBackend", ("networkBackend",)),
                ),
            )
        )
        platform_value = _mapping_value(typed_host, ("platform", "Platform"))
        if isinstance(platform_value, Mapping):
            platform = _project_stable_scalars(
                cast(Mapping[str, object], platform_value),
                (
                    ("name", ("name", "Name")),
                    ("os", ("os", "Os", "OS")),
                    ("arch", ("arch", "Arch")),
                ),
            )
            if platform:
                host["platform"] = platform
        remote_socket_value = _mapping_value(
            typed_host, ("remoteSocket", "remote_socket")
        )
        if isinstance(remote_socket_value, Mapping):
            remote_socket = cast(Mapping[str, object], remote_socket_value)
            remote_path = _stable_scalar(
                _mapping_value(remote_socket, ("path",))
            )
        else:
            remote_path = _stable_scalar(remote_socket_value)
        if remote_path is not _STABLE_VALUE_MISSING:
            host["remoteSocket"] = {"path": remote_path}
        oci_runtime = _mapping_value(typed_host, ("ociRuntime", "oci_runtime"))
        if isinstance(oci_runtime, Mapping):
            typed_oci_runtime = cast(Mapping[str, object], oci_runtime)
            oci = _project_stable_scalars(
                typed_oci_runtime,
                (("name", ("name",)), ("path", ("path",))),
            )
            if oci:
                host["ociRuntime"] = oci
        id_mappings = _project_podman_id_mappings(
            _mapping_value(typed_host, ("idMappings", "id_mappings"))
        )
        if id_mappings is not _STABLE_VALUE_MISSING:
            host["idMappings"] = id_mappings
    store: dict[str, object] = {}
    if isinstance(store_value, Mapping):
        store.update(
            _project_stable_scalars(
                cast(Mapping[str, object], store_value),
                (
                    ("configFile", ("configFile",)),
                    ("graphDriverName", ("graphDriverName",)),
                    ("graphRoot", ("graphRoot",)),
                    ("runRoot", ("runRoot",)),
                    ("volumePath", ("volumePath",)),
                    ("transientStore", ("transientStore",)),
                ),
            )
        )
    if "Version" not in version and "APIVersion" not in version:
        raise ValueError("podman daemon identity is missing version metadata")
    service_is_remote = host.get("serviceIsRemote")
    remote_socket_value = host.get("remoteSocket")
    remote_socket: Mapping[str, object] = (
        cast(Mapping[str, object], remote_socket_value)
        if isinstance(remote_socket_value, Mapping)
        else {}
    )
    remote_path: object = remote_socket.get("path")
    hostname = host.get("hostname")
    if not isinstance(service_is_remote, bool):
        raise ValueError("podman daemon identity is missing serviceIsRemote")
    if not (
        isinstance(remote_path, str)
        and bool(remote_path)
        or isinstance(hostname, str)
        and bool(hostname)
    ):
        raise ValueError(
            "podman daemon identity is missing remote endpoint or hostname"
        )
    platform_value = host.get("platform")
    platform_mapping: Mapping[str, object] = (
        cast(Mapping[str, object], platform_value)
        if isinstance(platform_value, Mapping)
        else {}
    )
    platform_os: object = host.get("os")
    platform_arch: object = host.get("arch")
    if not isinstance(platform_os, str) or not platform_os:
        platform_os = platform_mapping.get("os") or platform_mapping.get("Os")
    if not isinstance(platform_arch, str) or not platform_arch:
        platform_arch = platform_mapping.get("arch") or platform_mapping.get("Arch")
    if not (
        isinstance(platform_os, str)
        and bool(platform_os)
        and isinstance(platform_arch, str)
        and bool(platform_arch)
    ):
        raise ValueError("podman daemon identity is missing platform os/arch")
    required_store_fields = ("graphRoot", "runRoot", "graphDriverName")
    if not all(
        isinstance(store.get(field), str) and bool(store[field])
        for field in required_store_fields
    ):
        raise ValueError("podman daemon identity is missing storage metadata")
    return {"builder": "podman", "version": version, "host": host, "store": store}


def _stable_docker_identity(payload: Mapping[str, object]) -> dict[str, object]:
    """Project Docker's server metadata while preserving fake scalar fixtures."""
    server_value = _mapping_value(payload, ("Server", "server"))
    if not isinstance(server_value, Mapping):
        raise ValueError("docker daemon identity is missing Server metadata")
    typed_server = cast(Mapping[str, object], server_value)
    server = _project_stable_scalars(
        typed_server,
        (
            ("Version", ("Version",)),
            ("ApiVersion", ("ApiVersion", "APIVersion")),
            ("MinAPIVersion", ("MinAPIVersion",)),
            ("GitCommit", ("GitCommit",)),
            ("GoVersion", ("GoVersion",)),
            ("Os", ("Os",)),
            ("Arch", ("Arch",)),
            ("KernelVersion", ("KernelVersion",)),
            ("OperatingSystem", ("OperatingSystem",)),
            ("OSType", ("OSType",)),
            ("Architecture", ("Architecture",)),
            ("Name", ("Name",)),
            ("DockerRootDir", ("DockerRootDir",)),
            ("Driver", ("Driver",)),
        ),
    )
    platform_value = _mapping_value(typed_server, ("Platform", "platform"))
    if isinstance(platform_value, Mapping):
        platform = _project_stable_scalars(
            cast(Mapping[str, object], platform_value),
            (("Name", ("Name", "name")),),
        )
        if platform:
            server["Platform"] = platform
    components_value = _mapping_value(typed_server, ("Components", "components"))
    if isinstance(components_value, (list, tuple)):
        typed_components = cast(list[object] | tuple[object, ...], components_value)
        components: list[dict[str, object]] = []
        for item in typed_components:
            if not isinstance(item, Mapping):
                continue
            component = _project_stable_scalars(
                cast(Mapping[str, object], item),
                (("Name", ("Name",)), ("Version", ("Version",))),
            )
            if component:
                components.append(component)
        if components:
            server["Components"] = components
    if not isinstance(server.get("Version"), str) or not server["Version"]:
        raise ValueError("docker daemon identity is missing Server version")
    return {"builder": "docker", "server": server}


def _stable_daemon_identity(builder: str, payload: object) -> dict[str, object]:
    """Return the auditable, closed daemon identity projection."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{builder} daemon identity is not an object")
    typed_payload = cast(Mapping[str, object], payload)
    if builder == "podman":
        return _stable_podman_identity(typed_payload)
    if builder == "docker":
        return _stable_docker_identity(typed_payload)
    raise ValueError(f"unsupported daemon builder: {builder}")


def daemon_identity_fingerprint(snapshot: DaemonSnapshot) -> str:
    """Hash the stable daemon identity payload for pre/post binding."""
    stable_identity = _stable_daemon_identity(snapshot.builder, snapshot.daemon)
    canonical = json.dumps(
        stable_identity,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class LifecycleResourceReceipt:
    """Ownership and cleanup readback for one resource ID."""

    resource: DaemonResource
    preexisting: bool
    created_or_pulled_by_task: bool
    preservation_policy: str = "pre-snapshot-preserve"
    exclusion_authority: str = "exact-id-and-task-label"
    operation: str = ""
    cleanup_operation: str = ""
    cleanup_exit: int | None = None
    post_inspect: str = "not-run"
    absence: str = "not-checked"
    restore_tags: tuple[tuple[str, str], ...] = ()
    alias_tags: tuple[str, ...] = ()

    @property
    def preservation_policy_owner(self) -> str:
        """Compatibility name used by the durable lifecycle contract."""
        return self.preservation_policy

    @property
    def exclusion_authority_owner(self) -> str:
        """Compatibility name used by the durable lifecycle contract."""
        return self.exclusion_authority

    def as_json(self) -> dict[str, object]:
        """Serialize cleanup ownership and readback for one resource."""
        return {
            **self.resource.as_json(),
            "preexisting": self.preexisting,
            "created_or_pulled_by_task": self.created_or_pulled_by_task,
            "preservation_policy": self.preservation_policy,
            "exclusion_authority": self.exclusion_authority,
            "preservation_policy_owner": self.preservation_policy_owner,
            "exclusion_authority_owner": self.exclusion_authority_owner,
            "operation": self.operation,
            "cleanup_operation": self.cleanup_operation,
            "cleanup_exit": self.cleanup_exit,
            "post_inspect": self.post_inspect,
            "absence": self.absence,
            "restore_tags": [
                {"tag": tag, "immutable_id": immutable_id}
                for tag, immutable_id in self.restore_tags
            ],
            "alias_tags": list(self.alias_tags),
        }


def _empty_resource_receipts() -> list[LifecycleResourceReceipt]:
    """Provide a typed dataclass factory for lifecycle resource rows."""
    return []


@dataclass
class ContainerLifecycleReceipt:
    """Durable lifecycle state for one build/run operation."""

    context: LifecycleContext
    before: DaemonSnapshot
    after: DaemonSnapshot | None = None
    resources: list[LifecycleResourceReceipt] = field(
        default_factory=_empty_resource_receipts
    )
    state: str = "snapshot"
    failure: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def as_json(self) -> dict[str, object]:
        """Serialize the complete lifecycle receipt."""
        return {
            "schema": LIFECYCLE_SCHEMA,
            "task_id": self.context.task_id,
            "repo_identity": self.context.repo_identity,
            "operation": self.context.operation,
            "task_repo_label": self.context.task_repo_label
            or f"{self.context.task_id}:{self.context.repo_identity}",
            "lifecycle_id": self.context.lifecycle_id,
            "expected_image_tags": list(self.context.expected_image_tags),
            "builder": self.context.builder,
            "daemon": dict((self.after or self.before).daemon),
            "before": self.before.as_json(),
            "after": self.after.as_json() if self.after else None,
            "resources": [item.as_json() for item in self.resources],
            "state": self.state,
            "failure": self.failure,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass(frozen=True)
class CleanupResult:
    """Cleanup outcome with the receipt retained for blocked states."""

    state: str
    receipt: ContainerLifecycleReceipt
    removed_ids: tuple[str, ...] = ()
    failure: str | None = None


@dataclass
class ContainerLifecycleRun:
    """Build/run lifecycle aggregate used by one repository-local runner."""

    boundary: ContainerLifecycleBoundary
    receipt: ContainerLifecycleReceipt
    workspace_root: Path

    @property
    def context(self) -> LifecycleContext:
        """Return the immutable invocation context."""
        return self.boundary.context

    def finish(self, *, cleanup: bool) -> CleanupResult:
        """Capture post-state, optionally clean exact IDs, and write a receipt."""
        after = self.boundary.snapshot()
        self.receipt = self.boundary.record_create_or_pull(
            self.receipt, after, self.context.operation
        )
        if cleanup:
            result = self.boundary.cleanup(self.receipt)
        else:
            result = CleanupResult(self.receipt.state, self.receipt)
        write_lifecycle_receipt(self.workspace_root, self.receipt)
        return result


def emit_not_created_lifecycle_receipt(
    workspace_root: Path, context: LifecycleContext
) -> ContainerLifecycleReceipt:
    """Publish a typed no-daemon receipt for a print-only invocation."""
    now = time.time()
    receipt = ContainerLifecycleReceipt(
        context,
        DaemonSnapshot(
            context.builder,
            {"source": "print-only", "daemon_call": False},
            "not-created",
            (),
            now,
        ),
        state="not-created",
        started_at=now,
        finished_at=now,
    )
    write_lifecycle_receipt(workspace_root, receipt)
    return receipt


def start_container_lifecycle(
    workspace_root: Path,
    builder: str,
    operation: str,
    *,
    context: LifecycleContext | None = None,
) -> ContainerLifecycleRun:
    """Take the mandatory pre-operation snapshot for one runner."""
    context = context or lifecycle_context(workspace_root, builder, operation)
    boundary = ContainerLifecycleBoundary(
        context, CommandDaemonClient(builder, cwd=workspace_root)
    )
    return ContainerLifecycleRun(boundary, boundary.begin(), workspace_root)


def task_scoped_image_tag(image_tag: str, context: LifecycleContext) -> str:
    """Return a unique build tag without retargeting a shared mutable tag."""
    digest = hashlib.sha256(
        f"{context.task_id}\0{context.lifecycle_id}".encode()
    ).hexdigest()[:16]
    suffix = f"ac-{digest}"
    repository, separator, tag = image_tag.rpartition(":")
    if not separator or "/" in tag:
        repository, tag = image_tag, "task"
    if not tag or len(tag) + len(suffix) + 1 > 128:
        raise ValueError(
            "image tag component is too long for the lifecycle suffix: "
            f"{len(tag)} + {len(suffix)} + 1 > 128"
        )
    return f"{repository}:{tag}-{suffix}"


def scope_pack_image_tag(pack: ContainerPack, context: LifecycleContext) -> ContainerPack:
    """Bind one pack's mutable tag to this lifecycle's task identity."""
    scoped = task_scoped_image_tag(pack.image_tag, context)
    return replace(pack, image_tag=scoped)


def lifecycle_receipt_path(
    workspace_root: Path, receipt: ContainerLifecycleReceipt
) -> Path:
    """Resolve a lifecycle receipt strictly below the external runtime root."""
    root = workspace_root.resolve(strict=True)
    control_configured = os.environ.get("AGENT_CANON_CONTROL_PARENT_ROOT", "").strip()
    if not control_configured:
        raise RuntimeArtifactError(
            "explicit AGENT_CANON_CONTROL_PARENT_ROOT is required for lifecycle receipts"
        )
    control_root = Path(control_configured).expanduser().resolve(strict=True)
    try:
        root.relative_to(control_root)
    except ValueError as exc:
        raise RuntimeArtifactError(
            "workspace root must be below AGENT_CANON_CONTROL_PARENT_ROOT"
        ) from exc
    boundary = RuntimeArtifactBoundary.for_source(root, create=True)
    configured = os.environ.get("AGENT_CANON_CONTAINER_LIFECYCLE_RECEIPT")
    if configured:
        candidate = configured
    else:
        task = re.sub(r"[^A-Za-z0-9._-]+", "_", receipt.context.task_id).strip("._")
        operation = re.sub(
            r"[^A-Za-z0-9._-]+", "_", receipt.context.operation
        ).strip("._")
        lifecycle = re.sub(
            r"[^A-Za-z0-9._-]+", "_", receipt.context.lifecycle_id
        ).strip("._")
        candidate = Path("container-lifecycle") / (
            f"{operation or 'run'}-{task or 'task'}-{lifecycle or 'lifecycle'}.json"
        )
    return boundary.resolve(candidate)


def write_lifecycle_receipt(
    workspace_root: Path, receipt: ContainerLifecycleReceipt
) -> Path:
    """Atomically publish one receipt through the external runtime boundary."""
    target = lifecycle_receipt_path(workspace_root, receipt)
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"lifecycle receipt collision at {target}") from exc
        if not isinstance(existing, Mapping):
            raise ValueError(f"lifecycle receipt collision at {target}")
        existing_mapping = cast(Mapping[str, object], existing)
        if existing_mapping.get("lifecycle_id") != receipt.context.lifecycle_id:
            raise ValueError(f"lifecycle receipt collision at {target}")
    payload = (json.dumps(receipt.as_json(), sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    boundary = RuntimeArtifactBoundary.for_source(
        workspace_root.resolve(strict=True),
        os.environ.get("AGENT_CANON_RUNTIME_ROOT"),
        create=True,
    )
    return boundary.atomic_write_bytes(target, payload)


class ContainerLifecycleBoundary:
    """Own exact-ID daemon snapshots and reverse cleanup.

    ``client`` is a deliberately small adapter exposing ``snapshot``,
    ``remove(kind, immutable_id)``, and ``inspect_absence(kind, id)``.  Tests
    use a fake client; production adapters can wrap Docker or Podman without
    changing the ownership policy.
    """

    def __init__(self, context: LifecycleContext, client: object) -> None:
        """Bind one invocation context to its daemon adapter."""
        self.context = context
        self.client = client

    @staticmethod
    def resource_from_value(value: object) -> DaemonResource:
        """Normalize one daemon JSON row into an immutable resource record."""
        if isinstance(value, DaemonResource):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("daemon resource must be a mapping")
        typed_value = cast(Mapping[str, object], value)
        labels: object = typed_value.get("labels", {})
        tags: object = typed_value.get("tags", ())
        if labels is None:
            labels = {}
        if tags is None:
            tags = ()
        if isinstance(labels, str):
            parsed_labels: dict[str, str] = {}
            for item in labels.split(","):
                key, separator, label_value = item.partition("=")
                if separator and key:
                    parsed_labels[key] = label_value
            labels = parsed_labels
        if not isinstance(labels, Mapping) or not isinstance(tags, (list, tuple)):
            raise ValueError("daemon resource labels/tags are malformed")
        typed_tags = cast(list[object] | tuple[object, ...], tags)
        typed_labels = cast(Mapping[object, object], labels)
        immutable_id = typed_value.get(
            "immutable_id", typed_value.get("id")
        )
        immutable_id = _strict_json_string(
            immutable_id, "daemon resource immutable_id"
        )
        kind = _strict_json_string(typed_value.get("kind"), "daemon resource kind")
        tags_value = tuple(
            _strict_json_string(item, "daemon resource tag") for item in typed_tags
        )
        labels_value = tuple(
            sorted(
                (
                    _strict_json_string(key, "daemon resource label key"),
                    _strict_json_string(item, "daemon resource label value", allow_empty=True),
                )
                for key, item in typed_labels.items()
            )
        )
        return DaemonResource(
            kind=kind,
            immutable_id=immutable_id,
            digest=_optional_json_string(typed_value.get("digest"), "daemon resource digest"),
            name=_optional_json_string(typed_value.get("name"), "daemon resource name"),
            tags=tags_value,
            labels=labels_value,
            project=_optional_json_string(typed_value.get("project"), "daemon resource project"),
            state=_optional_json_string(typed_value.get("state"), "daemon resource state"),
            image_id=_optional_json_string(typed_value.get("image_id"), "daemon resource image_id"),
        )

    def snapshot(self, _context: LifecycleContext | None = None) -> DaemonSnapshot:
        """Capture one immutable inventory, reporting daemon outages typed."""
        try:
            raw = getattr(self.client, "snapshot")()
        except Exception as exc:
            return DaemonSnapshot(
                self.context.builder,
                {"error": str(exc)},
                "daemon-unavailable",
                (),
                time.time(),
            )
        if isinstance(raw, DaemonSnapshot):
            return replace(raw, resources=self.dedupe_resources(raw.resources))
        if not isinstance(raw, Mapping):
            raise ValueError("daemon snapshot must be a mapping")
        typed_raw = cast(Mapping[str, object], raw)
        raw_resources = typed_raw.get("resources", ())
        if not isinstance(raw_resources, (list, tuple)):
            raise ValueError("daemon snapshot resources must be a list")
        typed_raw_resources = cast(list[object] | tuple[object, ...], raw_resources)
        daemon_value = typed_raw.get("daemon", {})
        daemon: Mapping[str, object] = (
            cast(Mapping[str, object], daemon_value)
            if isinstance(daemon_value, Mapping)
            else cast(Mapping[str, object], {})
        )
        return DaemonSnapshot(
            str(typed_raw.get("builder", self.context.builder)),
            dict(daemon),
            str(typed_raw.get("query_status", "ok")),
            self.dedupe_resources(
                tuple(
                    self.resource_from_value(item) for item in typed_raw_resources
                )
            ),
            time.time(),
        )

    @staticmethod
    def dedupe_resources(
        resources: tuple[DaemonResource, ...] | list[DaemonResource],
    ) -> tuple[DaemonResource, ...]:
        """Merge repeated daemon rows by immutable identity and union tags."""
        merged: dict[tuple[str, str], DaemonResource] = {}
        for resource in resources:
            resource = replace(
                resource,
                tags=tuple(dict.fromkeys(resource.tags)),
                labels=tuple(sorted(dict(resource.labels).items())),
            )
            key = (resource.kind, resource.immutable_id)
            prior = merged.get(key)
            if prior is None:
                merged[key] = resource
                continue
            labels = dict(prior.labels)
            labels.update(dict(resource.labels))
            merged[key] = replace(
                prior,
                digest=prior.digest or resource.digest,
                name=prior.name or resource.name,
                tags=tuple(dict.fromkeys((*prior.tags, *resource.tags))),
                labels=tuple(sorted(labels.items())),
                project=prior.project or resource.project,
                state=prior.state or resource.state,
                image_id=prior.image_id or resource.image_id,
            )
        return tuple(merged.values())

    def begin(self) -> ContainerLifecycleReceipt:
        """Start a receipt from the pre-operation snapshot."""
        before = self.snapshot()
        state = "snapshot" if before.query_status == "ok" else before.query_status
        return ContainerLifecycleReceipt(self.context, before, state=state)

    def record_create_or_pull(
        self,
        before: DaemonSnapshot | ContainerLifecycleReceipt,
        after: DaemonSnapshot,
        operation: str = "run",
    ) -> ContainerLifecycleReceipt:
        """Diff snapshots and authorize only new resources with exact labels."""
        receipt = (
            before
            if isinstance(before, ContainerLifecycleReceipt)
            else ContainerLifecycleReceipt(self.context, before)
        )
        receipt.before = replace(
            receipt.before,
            resources=self.dedupe_resources(receipt.before.resources),
        )
        after = replace(after, resources=self.dedupe_resources(after.resources))
        receipt.after = after
        partial_reasons: list[str] = [
            f"{source}:{resource.kind}:{resource.immutable_id}:{resource.state}"
            for source, snapshot in (("before", receipt.before), ("after", after))
            for resource in snapshot.resources
            if resource.state in {"partial", "nonterminal", "unknown"}
        ]
        partial_reasons.extend(
            f"{source}:query-status:{snapshot.query_status}"
            for source, snapshot in (("before", receipt.before), ("after", after))
            if snapshot.query_status in {"partial", "nonterminal", "unknown"}
        )
        if (
            receipt.before.query_status != "ok"
            or after.query_status != "ok"
            or partial_reasons
        ):
            partial = any(
                status in {"partial", "nonterminal", "unknown"}
                for status in (receipt.before.query_status, after.query_status)
            ) or bool(partial_reasons)
            receipt.state = "partial-failure" if partial else "daemon-unavailable"
            receipt.failure = (
                ";".join(("daemon snapshot is partial", *partial_reasons))
                if partial
                else ";".join(("daemon snapshot unavailable", *partial_reasons))
            )
            receipt.finished_at = time.time()
            return receipt
        before_identity = daemon_identity_fingerprint(receipt.before)
        after_identity = daemon_identity_fingerprint(after)
        if receipt.before.builder != after.builder or before_identity != after_identity:
            receipt.state = "cleanup-blocked"
            receipt.failure = (
                "daemon identity mismatch: "
                f"before={receipt.before.builder}/{before_identity} "
                f"after={after.builder}/{after_identity}"
            )
            receipt.finished_at = time.time()
            return receipt
        previous = {(item.kind, item.immutable_id) for item in receipt.before.resources}
        previous_images_by_tag: dict[str, str] = {}
        for item in receipt.before.resources:
            if item.kind == "image":
                for tag in item.tags:
                    previous_images_by_tag[tag] = item.immutable_id
        expected = self.context.labels()
        expected_image_tags = set(self.context.expected_image_tags)
        blocked_reasons: list[str] = []
        # A receipt may be re-bound to a fresh post-operation snapshot during
        # finish/cleanup. Rebuild its resource rows from the immutable
        # pre-snapshot instead of appending a second observation of each ID.
        receipt.resources = []
        for resource in after.resources:
            preexisting = (resource.kind, resource.immutable_id) in previous
            labels = resource.label_map
            labelled_owner = all(
                labels.get(key) == value for key, value in expected.items()
            )
            expected_tag_owner = resource.kind == "image" and bool(
                expected_image_tags.intersection(resource.tags)
            )
            owned = (not preexisting) and (labelled_owner or expected_tag_owner)
            restore_tags: list[tuple[str, str]] = []
            alias_tags: list[str] = []
            if resource.kind == "image":
                prior_resource = next(
                    (
                        item
                        for item in receipt.before.resources
                        if item.kind == "image"
                        and item.immutable_id == resource.immutable_id
                    ),
                    None,
                )
                prior_tags = set(prior_resource.tags if prior_resource else ())
                alias_tags.extend(
                    tag
                    for tag in resource.tags
                    if tag not in prior_tags and tag in expected_image_tags
                )
                if preexisting and alias_tags:
                    blocked_reasons.extend(
                        "pre-existing image alias lacks task provenance: "
                        f"{resource.immutable_id}:{tag}"
                        for tag in alias_tags
                    )
                    # The immutable image existed before this invocation, so
                    # an added expected tag cannot be attributed to this task
                    # without an explicit daemon create receipt.
                    alias_tags.clear()
                for tag in resource.tags:
                    previous_id = previous_images_by_tag.get(tag)
                    if previous_id is not None and previous_id != resource.immutable_id:
                        if owned and tag in expected_image_tags:
                            restore_tags.append((tag, previous_id))
                        else:
                            # A shared image retarget observed without our labels is
                            # preserved as unrelated daemon activity.
                            if tag in alias_tags:
                                alias_tags.remove(tag)
            receipt.resources.append(
                LifecycleResourceReceipt(
                    resource=resource,
                    preexisting=preexisting,
                    created_or_pulled_by_task=owned,
                    operation=operation if owned else "unowned-observation",
                    preservation_policy=(
                        "pre-snapshot-preserve"
                        if preexisting or not owned
                        else "task-created-exact-id"
                    ),
                    restore_tags=tuple(restore_tags),
                    alias_tags=tuple(alias_tags) if preexisting else (),
                )
            )
        if partial_reasons:
            receipt.state = "partial-failure"
            receipt.failure = ";".join(partial_reasons)
        elif blocked_reasons:
            receipt.state = "cleanup-blocked"
            receipt.failure = ";".join(blocked_reasons)
        else:
            receipt.state = (
                "created"
                if any(item.created_or_pulled_by_task for item in receipt.resources)
                else "not-created"
            )
        receipt.finished_at = time.time()
        return receipt

    # Older handoff packets called this operation ``record``.
    record = record_create_or_pull

    def cleanup(self, receipt: ContainerLifecycleReceipt) -> CleanupResult:
        """Remove only task IDs in reverse dependency order and inspect absence."""
        has_alias_cleanup = any(item.alias_tags for item in receipt.resources)
        if receipt.state in {"daemon-unavailable", "cleanup-blocked"}:
            return CleanupResult(receipt.state, receipt)
        if receipt.state == "not-created" and not has_alias_cleanup:
            return CleanupResult(receipt.state, receipt)
        if receipt.state == "partial-failure":
            receipt.state = "cleanup-blocked"
            receipt.failure = receipt.failure or "partial lifecycle observation"
            receipt.finished_at = time.time()
            return CleanupResult(
                receipt.state, receipt, failure=receipt.failure
            )
        receipt.state = "cleaning"
        # Cleanup follows daemon dependency order: a container may hold open
        # network/volume references, and those resources must be gone before
        # the task-created image is considered removable.  ``LIFECYCLE_KINDS``
        # is inventory order, not cleanup order, so keep this mapping explicit.
        rank = {"container": 0, "network": 1, "volume": 2, "image": 3}
        candidates = [
            item
            for item in receipt.resources
            if item.created_or_pulled_by_task and not item.preexisting
        ]
        candidates.sort(key=lambda item: rank[item.resource.kind])
        removed: list[str] = []
        retargeted = any(item.restore_tags for item in candidates)
        for item in candidates:
            resource = item.resource
            try:
                if resource.kind == "image":
                    for tag, previous_id in item.restore_tags:
                        if getattr(self.client, "inspect_image_tag")(tag) != resource.immutable_id:
                            raise RuntimeError(f"tag retarget readback mismatch: {tag}")
                        restore = getattr(self.client, "restore_image_tag")(
                            previous_id, tag
                        )
                        restore_code = (
                            restore
                            if isinstance(restore, int)
                            else getattr(restore, "returncode", 0)
                        )
                        if int(restore_code) != 0:
                            raise RuntimeError(f"tag restore returned {restore_code}")
                        if getattr(self.client, "inspect_image_tag")(
                            tag
                        ) != previous_id:
                            raise RuntimeError(f"tag restore readback mismatch: {tag}")
                outcome = getattr(self.client, "remove")(
                    resource.kind, resource.immutable_id
                )
                code = outcome if isinstance(outcome, int) else getattr(outcome, "returncode", 0)
                if int(code) != 0:
                    raise RuntimeError(f"remove returned {code}")
                if getattr(self.client, "inspect_absence")(
                    resource.kind, resource.immutable_id
                ) is not True:
                    raise RuntimeError("immutable ID remains present or absence is unknown")
            except Exception as exc:
                receipt.state = "cleanup-blocked"
                receipt.failure = f"{resource.kind}:{resource.immutable_id}:{exc}"
                receipt.finished_at = time.time()
                return CleanupResult(receipt.state, receipt, tuple(removed), receipt.failure)
            index = receipt.resources.index(item)
            receipt.resources[index] = replace(
                item,
                cleanup_operation=f"{self.context.builder} {resource.kind} rm {resource.immutable_id}",
                cleanup_exit=0,
                post_inspect="absent",
                absence="absent",
            )
            removed.append(resource.immutable_id)
        for item in receipt.resources:
            if not item.alias_tags:
                continue
            for tag in item.alias_tags:
                try:
                    outcome = getattr(self.client, "remove_image_alias")(
                        item.resource.immutable_id, tag
                    )
                    code = outcome if isinstance(outcome, int) else getattr(outcome, "returncode", 0)
                    if int(code) != 0:
                        raise RuntimeError(f"alias removal returned {code}")
                    if getattr(self.client, "inspect_image_alias_absence")(
                        item.resource.immutable_id, tag
                    ) is not True:
                        raise RuntimeError("image alias remains present or is unknown")
                except Exception as exc:
                    receipt.state = "cleanup-blocked"
                    receipt.failure = f"image-alias:{item.resource.immutable_id}:{tag}:{exc}"
                    receipt.finished_at = time.time()
                    return CleanupResult(receipt.state, receipt, tuple(removed), receipt.failure)
                removed.append(f"alias:{tag}")
        receipt.state = "cleanup-blocked" if retargeted else "cleaned"
        if retargeted:
            receipt.failure = (
                "pre-existing image tag retargeted and restored; "
                "lifecycle is non-success"
            )
        receipt.finished_at = time.time()
        return CleanupResult(receipt.state, receipt, tuple(removed))


def _object_mapping(value: object, description: str) -> dict[str, object]:
    """Validate and normalize one JSON object without untyped escape hatches."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{description} must be an object")
    typed_value = cast(Mapping[str, object], value)
    normalized: dict[str, object] = {}
    for key, item in typed_value.items():
        normalized[key] = item
    return normalized


_STRICT_MISSING = object()


def _strict_json_string(
    value: object,
    description: str,
    *,
    default: object = _STRICT_MISSING,
    allow_empty: bool = False,
) -> str:
    """Read one receipt string without Python truthiness/coercion."""
    if value is _STRICT_MISSING:
        if default is _STRICT_MISSING:
            raise ValueError(f"{description} is required")
        value = default
    if not isinstance(value, str):
        raise ValueError(f"{description} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{description} must be non-empty")
    if CONTROL_RE.search(value):
        raise ValueError(f"{description} contains control characters")
    return value


def _optional_json_string(value: object, description: str) -> str | None:
    """Read one nullable receipt string with strict type and control checks."""
    if value is None:
        return None
    return _strict_json_string(value, description)


def _strict_json_bool(value: object, description: str, *, default: bool) -> bool:
    """Read one JSON boolean; strings such as ``"false"`` are rejected."""
    if value is _STRICT_MISSING:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{description} must be a boolean")
    return value


def _object_sequence(value: object, description: str) -> list[object]:
    """Validate and normalize one JSON array without untyped escape hatches."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{description} must be an array")
    typed_value = cast(list[object] | tuple[object, ...], value)
    normalized: list[object] = []
    for item in typed_value:
        normalized.append(item)
    return normalized


def _string_sequence(value: object, description: str) -> tuple[str, ...]:
    """Validate one JSON string array."""
    strings: list[str] = []
    for item in _object_sequence(value, description):
        strings.append(_strict_json_string(item, f"{description} item"))
    return tuple(strings)


def _optional_int(value: object, description: str) -> int | None:
    """Validate one optional JSON integer."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{description} must be an integer or null")
    return value


def _required_float(value: object, description: str, default: float) -> float:
    """Validate one JSON number with an explicit default."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{description} must be a number or null")
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{description} must be a number or null")


def lifecycle_receipt_from_json(payload: Mapping[str, object]) -> ContainerLifecycleReceipt:
    """Restore a boundary receipt for a later post-state or cleanup phase."""
    payload = _object_mapping(payload, "lifecycle receipt")
    schema = _strict_json_string(
        payload.get("schema", _STRICT_MISSING), "lifecycle receipt schema"
    )
    if schema != LIFECYCLE_SCHEMA:
        raise ValueError("lifecycle receipt schema does not match the supported schema")
    before_payload = _object_mapping(
        payload.get("before"), "lifecycle receipt before snapshot"
    )
    task_id = _strict_json_string(payload.get("task_id"), "lifecycle receipt task_id")
    repo_identity = _strict_json_string(
        payload.get("repo_identity"), "lifecycle receipt repo_identity"
    )
    task_repo_label = _optional_json_string(
        payload.get("task_repo_label"), "lifecycle receipt task_repo_label"
    )
    if task_repo_label is not None and task_repo_label != f"{task_id}:{repo_identity}":
        raise ValueError("lifecycle receipt task/repository identity contradicts its label")
    context = LifecycleContext(
        task_id=task_id,
        repo_identity=repo_identity,
        builder=_strict_json_string(
            payload.get("builder", "docker"), "lifecycle receipt builder"
        ),
        task_repo_label=task_repo_label,
        operation=_strict_json_string(
            payload.get("operation", "gpu-admission"), "lifecycle receipt operation"
        ),
        lifecycle_id=_strict_json_string(
            payload.get("lifecycle_id"), "lifecycle receipt lifecycle_id"
        ),
        expected_image_tags=_string_sequence(
            payload.get("expected_image_tags", ()),
            "lifecycle receipt expected_image_tags",
        ),
    )

    def snapshot_from(value: Mapping[str, object]) -> DaemonSnapshot:
        raw_resources = _object_sequence(
            value.get("resources", ()), "lifecycle receipt resources"
        )
        daemon = _object_mapping(
            value.get("daemon", {}), "lifecycle receipt daemon identity"
        )
        return DaemonSnapshot(
            _strict_json_string(
                value.get("builder", context.builder),
                "lifecycle receipt snapshot builder",
            ),
            daemon,
            _strict_json_string(
                value.get("query_status", "ok"),
                "lifecycle receipt snapshot query_status",
            ),
            ContainerLifecycleBoundary.dedupe_resources(
                tuple(
                    ContainerLifecycleBoundary.resource_from_value(
                        _object_mapping(item, "daemon resource")
                    )
                    for item in raw_resources
                )
            ),
            _required_float(value.get("captured_at", 0.0), "captured_at", 0.0),
        )

    resources_payload = _object_sequence(
        payload.get("resources", ()), "lifecycle receipt resources"
    )
    resources: list[LifecycleResourceReceipt] = []
    for raw_item in resources_payload:
        item = _object_mapping(raw_item, "lifecycle receipt resource row")
        resource = ContainerLifecycleBoundary.resource_from_value(item)
        restore_tags: list[tuple[str, str]] = []
        for raw_row in _object_sequence(
            item.get("restore_tags", ()), "lifecycle receipt restore_tags"
        ):
            row = _object_mapping(raw_row, "lifecycle receipt restore tag")
            if "tag" not in row or "immutable_id" not in row:
                raise ValueError("lifecycle receipt restore tag requires tag and immutable_id")
            restore_tags.append(
                (
                    _strict_json_string(row["tag"], "lifecycle receipt restore tag tag"),
                    _strict_json_string(
                        row["immutable_id"],
                        "lifecycle receipt restore tag immutable_id",
                    ),
                )
            )
        preexisting = _strict_json_bool(
            item.get("preexisting", _STRICT_MISSING),
            "lifecycle receipt preexisting",
            default=False,
        )
        created = _strict_json_bool(
            item.get("created_or_pulled_by_task", _STRICT_MISSING),
            "lifecycle receipt created_or_pulled_by_task",
            default=False,
        )
        preservation_policy = _strict_json_string(
            item.get("preservation_policy", "pre-snapshot-preserve"),
            "lifecycle receipt preservation_policy",
        )
        exclusion_authority = _strict_json_string(
            item.get("exclusion_authority", "exact-id-and-task-label"),
            "lifecycle receipt exclusion_authority",
        )
        policy_owner = item.get("preservation_policy_owner")
        if policy_owner is not None and _strict_json_string(
            policy_owner, "lifecycle receipt preservation_policy_owner"
        ) != preservation_policy:
            raise ValueError("lifecycle receipt preservation policy owner mismatch")
        authority_owner = item.get("exclusion_authority_owner")
        if authority_owner is not None and _strict_json_string(
            authority_owner, "lifecycle receipt exclusion_authority_owner"
        ) != exclusion_authority:
            raise ValueError("lifecycle receipt exclusion authority owner mismatch")
        resources.append(
            LifecycleResourceReceipt(
                resource,
                preexisting,
                created,
                restore_tags=tuple(restore_tags),
                alias_tags=_string_sequence(
                    item.get("alias_tags", ()), "lifecycle receipt alias_tags"
                ),
                preservation_policy=preservation_policy,
                exclusion_authority=exclusion_authority,
                operation=_strict_json_string(
                    item.get("operation", ""),
                    "lifecycle receipt operation",
                    allow_empty=True,
                ),
                cleanup_operation=_strict_json_string(
                    item.get("cleanup_operation", ""),
                    "lifecycle receipt cleanup_operation",
                    allow_empty=True,
                ),
                cleanup_exit=_optional_int(
                    item.get("cleanup_exit"), "lifecycle receipt cleanup_exit"
                ),
                post_inspect=_strict_json_string(
                    item.get("post_inspect", "not-run"),
                    "lifecycle receipt post_inspect",
                ),
                absence=_strict_json_string(
                    item.get("absence", "not-checked"),
                    "lifecycle receipt absence",
                ),
            )
        )
    after_payload = payload.get("after")
    after = (
        snapshot_from(_object_mapping(after_payload, "lifecycle receipt after snapshot"))
        if after_payload is not None
        else None
    )
    return ContainerLifecycleReceipt(
        context,
        snapshot_from(before_payload),
        after=after,
        resources=resources,
        state=_strict_json_string(
            payload.get("state", "snapshot"), "lifecycle receipt state"
        ),
        failure=_optional_json_string(
            payload.get("failure"), "lifecycle receipt failure"
        ),
        started_at=_required_float(
            payload.get("started_at", time.time()), "started_at", time.time()
        ),
        finished_at=(
            _required_float(payload.get("finished_at"), "finished_at", time.time())
            if payload.get("finished_at") is not None
            else None
        ),
    )


class CommandDaemonClient:
    """Strict Docker/Podman JSON-lines adapter used by authorized runners."""

    def __init__(self, builder: str, *, cwd: Path | None = None) -> None:
        """Configure a strict Docker or Podman JSON adapter."""
        if builder not in {"docker", "podman"}:
            raise ValueError(f"unsupported daemon builder: {builder}")
        self.builder = builder
        self.cwd = cwd or WORKSPACE_ROOT

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.builder, *argv],
            cwd=self.cwd,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _json_lines(result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
        if result.returncode != 0:
            raise RuntimeError(command_error_detail(result.stdout, result.stderr))
        text = result.stdout.strip()
        if text:
            try:
                payload: object = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                typed_payload = cast(list[object], payload)
                if not all(isinstance(item, dict) for item in typed_payload):
                    raise ValueError("daemon JSON array rows must be objects")
                return [cast(dict[str, object], item) for item in typed_payload]
            if isinstance(payload, dict):
                return [cast(dict[str, object], payload)]
        values: list[dict[str, object]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            value: object = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("daemon listing row must be an object")
            values.append(cast(dict[str, object], value))
        return values

    @staticmethod
    def _labels(row: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
        """Normalize Docker/Podman label projections without broad selectors."""
        labels: object = row.get("Labels", row.get("labels", {}))
        if isinstance(labels, Mapping):
            typed_labels = cast(Mapping[object, object], labels)
            return tuple(
                sorted(
                    (str(key), str(value)) for key, value in typed_labels.items()
                )
            )
        if isinstance(labels, str):
            parsed: dict[str, str] = {}
            for item in labels.split(","):
                key, separator, value = item.partition("=")
                if separator and key:
                    parsed[key] = value
            return tuple(sorted(parsed.items()))
        return ()

    def _image_labels(self, immutable_id: str) -> tuple[tuple[str, str], ...]:
        """Read image config labels when an image-list projection omits them."""
        result = self._run(
            ["image", "inspect", "--format", "{{json .Config.Labels}}", immutable_id]
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ()
        try:
            payload: object = json.loads(result.stdout)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, Mapping):
            return ()
        typed_payload = cast(Mapping[object, object], payload)
        return tuple(
            sorted((str(key), str(value)) for key, value in typed_payload.items())
        )

    def snapshot(self) -> DaemonSnapshot:
        """Capture daemon identity and all resource inventories."""
        if self.builder == "docker":
            version = self._run(["version", "--format", "{{json .}}"])
            if version.returncode != 0:
                raise RuntimeError(
                    "docker daemon identity unavailable: "
                    + command_error_detail(version.stdout, version.stderr)
                )
            image_rows = self._json_lines(self._run(["image", "ls", "--no-trunc", "--format", "{{json .}}"]))
            container_rows = self._json_lines(self._run(["ps", "-a", "--no-trunc", "--format", "{{json .}}"]))
            network_rows = self._json_lines(self._run(["network", "ls", "--no-trunc", "--format", "{{json .}}"]))
            volume_rows = self._json_lines(self._run(["volume", "ls", "--format", "{{json .}}"]))
        else:
            version = self._run(["info", "--format", "json"])
            if version.returncode != 0:
                raise RuntimeError(
                    "podman daemon identity unavailable: "
                    + command_error_detail(version.stdout, version.stderr)
                )
            image_rows = self._json_lines(self._run(["images", "--no-trunc", "--format", "json"]))
            container_rows = self._json_lines(self._run(["ps", "-a", "--format", "json"]))
            network_rows = self._json_lines(self._run(["network", "ls", "--format", "json"]))
            volume_rows = self._json_lines(self._run(["volume", "ls", "--format", "json"]))
        daemon_payload: Mapping[str, object]
        try:
            payload: object = json.loads(version.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{self.builder} daemon identity is not valid JSON"
            ) from exc
        if not isinstance(payload, Mapping) or not payload:
            raise ValueError(f"{self.builder} daemon identity is empty or malformed")
        typed_payload = cast(Mapping[str, object], payload)
        daemon_payload = _stable_daemon_identity(self.builder, typed_payload)
        resources: list[DaemonResource] = []
        for row in image_rows:
            image_id = str(row.get("ID", row.get("Id", "")))
            row_tags = row.get(
                "RepoTags", row.get("repoTags", row.get("Names", ()))
            )
            if isinstance(row_tags, str):
                tags = [row_tags]
            elif isinstance(row_tags, (list, tuple)):
                typed_row_tags = cast(list[object] | tuple[object, ...], row_tags)
                tags = [str(item) for item in typed_row_tags]
            else:
                tags = []
            if row.get("Tag"):
                tags.append(str(row["Tag"]))
            labels = self._labels(row) or self._image_labels(image_id)
            resources.append(DaemonResource("image", image_id, digest=str(row.get("Digest")) if row.get("Digest") else None, name=str(row.get("Repository")) if row.get("Repository") else None, tags=tuple(dict.fromkeys(tags)), labels=labels))
        for row in container_rows:
            resources.append(DaemonResource("container", str(row.get("ID", row.get("Id", ""))), name=str(row.get("Names")) if row.get("Names") else None, labels=self._labels(row), image_id=str(row.get("ImageID", row.get("Image", ""))) or None, state=str(row.get("State")) if row.get("State") else None))
        for row in network_rows:
            resources.append(DaemonResource("network", str(row.get("ID", row.get("Id", ""))), name=str(row.get("Name")) if row.get("Name") else None, labels=self._labels(row)))
        for row in volume_rows:
            resources.append(DaemonResource("volume", str(row.get("Name", row.get("name", ""))), name=str(row.get("Name", row.get("name", ""))), labels=self._labels(row)))
        return DaemonSnapshot(
            self.builder,
            daemon_payload,
            "ok",
            ContainerLifecycleBoundary.dedupe_resources(resources),
            time.time(),
        )

    def remove(self, kind: str, immutable_id: str) -> int:
        """Remove one exact immutable resource ID."""
        command = {
            "container": ["rm", immutable_id],
            "network": ["network", "rm", immutable_id],
            "volume": ["volume", "rm", immutable_id],
            "image": ["image", "rm", immutable_id],
        }.get(kind)
        if command is None:
            raise ValueError(f"unsupported cleanup kind: {kind}")
        return self._run(command).returncode

    def restore_image_tag(self, immutable_id: str, tag: str) -> int:
        """Restore a pre-snapshot alias from an immutable image ID."""
        return self._run(["image", "tag", immutable_id, tag]).returncode

    def inspect_image_tag(self, tag: str) -> str | None:
        """Read the immutable ID currently bound to one exact tag."""
        result = self._run(["image", "inspect", "--format", "{{.Id}}", tag])
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
        return None

    def remove_image_alias(self, immutable_id: str, tag: str) -> int:
        """Remove one prevalidated exact alias without accepting a broad selector."""
        if self.inspect_image_tag(tag) != immutable_id:
            raise RuntimeError(f"image alias does not resolve to expected ID: {tag}")
        return self._run(["image", "rm", tag]).returncode

    def inspect_image_alias_absence(self, immutable_id: str, tag: str) -> bool:
        """Prove that the exact alias is absent or now points elsewhere."""
        resolved = self.inspect_image_tag(tag)
        return resolved is None or resolved != immutable_id

    def inspect_absence(self, kind: str, immutable_id: str) -> bool:
        """Prove that one exact immutable resource ID is absent."""
        command = {
            "container": ["inspect", immutable_id],
            "network": ["network", "inspect", immutable_id],
            "volume": ["volume", "inspect", immutable_id],
            "image": ["image", "inspect", immutable_id],
        }.get(kind)
        if command is None:
            raise ValueError(f"unsupported cleanup kind: {kind}")
        result = self._run(command)
        if result.returncode == 1:
            detail = f"{result.stdout}\n{result.stderr}".lower()
            not_found_tokens = (
                "no such object",
                "no such container",
                "no such image",
                "no such network",
                "no such volume",
                "not found",
                "does not exist",
                "cannot find",
            )
            if any(token in detail for token in not_found_tokens):
                return True
            raise RuntimeError(command_error_detail(result.stdout, result.stderr))
        if result.returncode == 0:
            return False
        raise RuntimeError(command_error_detail(result.stdout, result.stderr))


def detect_host_runtime_features() -> HostRuntimeFeatures:
    """Detect host-dependent runtime features once."""
    has_gpu = Path("/dev/nvidiactl").exists() or shutil.which("nvidia-smi") is not None
    has_host_gh_config = HOST_GH_CONFIG.is_dir()
    has_host_ssh_dir = HOST_SSH_DIR.is_dir()
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if ssh_auth_sock is not None and not Path(ssh_auth_sock).exists():
        ssh_auth_sock = None
    return HostRuntimeFeatures(
        has_gpu=has_gpu,
        has_host_gh_config=has_host_gh_config,
        has_host_ssh_dir=has_host_ssh_dir,
        ssh_auth_sock=ssh_auth_sock,
    )


def default_host_mounts(
    *,
    auto_mount_host_gh_config: bool = False,
    auto_mount_host_ssh_dir: bool = False,
    auto_forward_ssh_auth_sock: bool = False,
) -> tuple[str, ...]:
    """Return host mounts that should appear in canonical container entrypoints."""
    mounts: list[str] = []
    features = detect_host_runtime_features()
    if auto_mount_host_gh_config and features.has_host_gh_config:
        mounts.append(f"{HOST_GH_CONFIG}:/root/.config/gh")
    if auto_mount_host_ssh_dir and features.has_host_ssh_dir:
        mounts.append(f"{HOST_SSH_DIR}:/root/.ssh:ro")
    if auto_forward_ssh_auth_sock and features.ssh_auth_sock is not None:
        mounts.append(f"{features.ssh_auth_sock}:/ssh-agent")
    return tuple(mounts)


def workspace_path(path_like: str | Path) -> Path:
    """Resolve a workspace-relative path."""
    candidate = Path(path_like)
    if candidate.is_absolute():
        return candidate
    return (WORKSPACE_ROOT / candidate).resolve()


def default_container_pack() -> ContainerPack:
    """Return direct Dockerfile defaults when no project pack is selected."""
    repository_name = re.sub(r"[^a-z0-9._-]+", "-", WORKSPACE_ROOT.name.lower())
    repository_name = repository_name.strip("-.") or "repository"
    return ContainerPack(
        name="default",
        dockerfile="docker/Dockerfile",
        context=".",
        target=None,
        image_tag=f"{repository_name}:agent-canon",
        platform=None,
        smoke=SmokeSpec(),
        runtime=RuntimeSpec(),
    )


def resolve_builder(builder: str, print_only: bool) -> str:
    """Resolve the builder, relaxing checks for print-only previews."""
    if not print_only:
        return detect_builder(builder)

    if builder != "auto":
        return builder
    for candidate in ("docker", "podman"):
        if shutil.which(candidate) is not None:
            return candidate
    return "docker"


def detect_builder(builder: str) -> str:
    """Return the resolved container builder."""
    if builder == "auto":
        unavailable_reasons: list[str] = []
        for candidate in ("docker", "podman"):
            if shutil.which(candidate) is None:
                continue
            readiness_error = builder_readiness_error(candidate)
            if readiness_error is None:
                return candidate
            unavailable_reasons.append(f"{candidate}: {readiness_error}")
        if unavailable_reasons:
            details = "; ".join(unavailable_reasons)
            raise RuntimeError(f"No usable container builder found. {details}")
        raise RuntimeError("Neither docker nor podman is available.")

    if shutil.which(builder) is None:
        raise RuntimeError(f"Requested builder is not available: {builder}")

    readiness_error = builder_readiness_error(builder)
    if readiness_error is not None:
        raise RuntimeError(readiness_error)
    return builder


def builder_readiness_error(builder: str) -> str | None:
    """Return an actionable readiness error for a builder, if any."""
    try:
        result = subprocess.run(
            [builder, "info"],
            cwd=WORKSPACE_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=BUILDER_INFO_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"{builder} info timed out"

    if result.returncode == 0:
        return None

    detail = command_error_detail(result.stdout, result.stderr)
    if builder == "docker" and "permission denied" in detail.lower():
        return (
            "docker is installed but the daemon socket is not accessible. "
            "Use a user with docker access, switch to --builder podman, or run "
            "with --print-only."
        )
    return f"{builder} is installed but not ready: {detail}"


def command_error_detail(stdout: str, stderr: str) -> str:
    """Return the first useful error line from a failed subprocess."""
    combined = "\n".join(part.strip() for part in (stderr, stdout) if part.strip())
    if not combined:
        return "no additional details"
    return combined.splitlines()[0].strip()


def require_string(
    section: dict[str, object],
    key: str,
    source: Path,
    section_name: str,
) -> str:
    """Require a non-empty string from a TOML section."""
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{source}: [{section_name}].{key} must be a non-empty string")
    return value


def require_string_list(
    section: dict[str, object],
    key: str,
    source: Path,
    section_name: str,
) -> tuple[str, ...]:
    """Require a list of strings from a TOML section."""
    value = section.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{source}: [{section_name}].{key} must be a list of strings")
    value_items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in value_items):
        raise ValueError(f"{source}: [{section_name}].{key} must be a list of strings")
    return tuple(cast("list[str]", value_items))


def _is_normalized_link(value: str) -> bool:
    """Return whether a pack link is normalized and repository-relative."""
    path = Path(value)
    return (
        bool(value)
        and not any(ord(char) < 32 for char in value)
        and not path.is_absolute()
        and value != "."
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _is_linked_target(value: str) -> bool:
    """Return whether a linked data target is a narrow /mnt mount path."""
    path = Path(value)
    return bool(
        LINKED_DATA_TARGET_RE.fullmatch(value)
        and not any(ord(char) < 32 for char in value)
        and ":" not in value
        and "," not in value
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and value not in {"/mnt", "/mnt/l"}
    )


def _parse_optional_mount_profiles(
    runtime_section: dict[str, object], source: Path
) -> tuple[str, ...]:
    """Parse and validate the pack-declared optional profile order."""
    value = runtime_section.get("optional_mount_profiles", [])
    if not isinstance(value, list):
        raise ValueError(f"{source}: [runtime].optional_mount_profiles must be a string array")
    profile_values = cast(list[object], value)
    if not all(isinstance(item, str) for item in profile_values):
        raise ValueError(f"{source}: [runtime].optional_mount_profiles must be a string array")
    profiles = tuple(cast(list[str], profile_values))
    seen: set[str] = set()
    for profile in profiles:
        if not profile or profile != profile.strip():
            raise ValueError(
                f"{source}: [runtime].optional_mount_profiles cannot contain empty or whitespace entries"
            )
        if profile not in OPTIONAL_MOUNT_PROFILES:
            raise ValueError(
                f"{source}: [runtime].optional_mount_profiles contains unknown profile: {profile}"
            )
        if profile in seen:
            raise ValueError(
                f"{source}: [runtime].optional_mount_profiles contains duplicate profile: {profile}"
            )
        seen.add(profile)
    return profiles


def _parse_linked_data_roots(
    runtime_section: dict[str, object], source: Path
) -> tuple[tuple[LinkedDataRoot, ...], bool]:
    """Parse typed linked roots without probing their runtime targets."""
    declared = "linked_data_roots" in runtime_section
    value = runtime_section.get("linked_data_roots", [])
    if not declared:
        return (), False
    if not isinstance(value, list):
        raise ValueError(
            f"{source}: [runtime].linked_data_roots must be an inline table array"
        )
    if not value:
        raise ValueError(
            f"{source}: [runtime].linked_data_roots must be non-empty when selected"
        )
    # A pack is stored at ``<repo>/docker/packs/<name>.toml``.  Resolve links
    # against the repository root rather than the intermediate ``docker``
    # directory; parent/derived checkouts use the same layout.
    pack_root = source.parent.parent.parent
    roots: list[LinkedDataRoot] = []
    seen_links: set[str] = set()
    seen_targets: set[str] = set()
    items = cast(list[object], value)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(
                f"{source}: linked_data_roots entry {index} must contain only link and target"
            )
        item_map = cast(dict[str, object], item)
        if set(item_map) != {"link", "target"}:
            raise ValueError(
                f"{source}: linked_data_roots entry {index} must contain only link and target"
            )
        link = item_map.get("link")
        target = item_map.get("target")
        if not isinstance(link, str) or not isinstance(target, str):
            raise ValueError(
                f"{source}: linked_data_roots entry {index} requires string link and target"
            )
        if not _is_normalized_link(link):
            raise ValueError(f"{source}: linked_data_roots link is invalid: {link}")
        if not (pack_root / link).is_symlink():
            raise ValueError(f"{source}: linked_data_roots link must be a symlink: {link}")
        if not _is_linked_target(target):
            raise ValueError(f"{source}: linked_data_roots target is invalid: {target}")
        if link in seen_links or target in seen_targets:
            raise ValueError(f"{source}: linked_data_roots links and targets must be unique")
        seen_links.add(link)
        seen_targets.add(target)
        roots.append(LinkedDataRoot(link=link, target=target))
    return tuple(roots), True


def _canonical_optional_mount_profiles(pack: ContainerPack) -> tuple[str, ...]:
    """Return pack-first optional profiles plus strict environment-only additions."""
    env_name = "AGENT_CANON_OPTIONAL_MOUNTS"
    env_profiles: tuple[str, ...] = ()
    if env_name in os.environ:
        raw = os.environ[env_name]
        if not raw:
            raise ValueError("AGENT_CANON_OPTIONAL_MOUNTS cannot be empty")
        values = raw.split(",")
        if any(not value or value != value.strip() or any(char.isspace() for char in value) for value in values):
            raise ValueError("AGENT_CANON_OPTIONAL_MOUNTS cannot contain empty or whitespace entries")
        seen: set[str] = set()
        for profile in values:
            if profile not in OPTIONAL_MOUNT_PROFILES:
                raise ValueError(f"AGENT_CANON_OPTIONAL_MOUNTS contains unknown profile: {profile}")
            if profile in seen:
                raise ValueError(f"AGENT_CANON_OPTIONAL_MOUNTS contains duplicate profile: {profile}")
            seen.add(profile)
        env_profiles = tuple(values)
    profiles = list(pack.runtime.optional_mount_profiles)
    profiles.extend(profile for profile in env_profiles if profile not in profiles)
    return tuple(profiles)


def resolve_linked_data_mounts(
    pack: ContainerPack,
    workspace_root: Path,
    *,
    resolve_path: Callable[[Path], Path] | None = None,
) -> tuple[str, ...]:
    """Resolve selected linked roots to exact read-write Docker bind strings."""
    profiles = _canonical_optional_mount_profiles(pack)
    selected = "linked-data-roots" in profiles
    if selected != pack.runtime.linked_data_roots_declared:
        raise ValueError("linked-data-roots profile and linked_data_roots list must match")
    if not selected:
        return ()
    if not pack.runtime.linked_data_roots:
        raise ValueError("linked-data-roots profile requires a non-empty linked_data_roots list")
    resolver: Callable[[Path], Path] = resolve_path or (
        lambda path: path.resolve(strict=True)
    )
    mounts: list[str] = []
    seen_sources: set[str] = set()
    seen_targets: set[str] = set()
    for linked_root in pack.runtime.linked_data_roots:
        source_path = workspace_root / linked_root.link
        try:
            resolved = resolver(source_path)
        except FileNotFoundError as exc:
            raise ValueError(
                f"linked_data_roots source does not resolve: {linked_root.link}"
            ) from exc
        if not resolved.is_dir():
            raise ValueError(
                f"linked_data_roots source must resolve to an existing directory: {linked_root.link}"
            )
        resolved_text = str(resolved)
        if resolved_text != linked_root.target:
            raise ValueError(
                f"linked_data_roots target does not match resolved source: {linked_root.link}"
            )
        if resolved_text in seen_sources or linked_root.target in seen_targets:
            raise ValueError("linked_data_roots sources and targets must be unique")
        seen_sources.add(resolved_text)
        seen_targets.add(linked_root.target)
        mounts.append(f"{resolved_text}:{linked_root.target}")
    return tuple(mounts)


def resolve_docker_host_mounts(
    *, socket_path: Path = DOCKER_HOST_SOCKET
) -> tuple[str, ...]:
    """Resolve the explicit docker-host profile to one read-write socket bind."""
    if not socket_path.exists() or not socket_path.is_socket():
        raise ValueError(
            f"docker-host profile requires an existing Unix socket: {socket_path}"
        )
    return (f"{socket_path}:/var/run/docker.sock",)


def _mount_destination(mount: str) -> str | None:
    """Extract a Docker bind destination from short or ``--mount`` syntax."""
    long_keys = {"type", "source", "src", "target", "dst", "destination"}
    fields = mount.split(",")
    first_key = fields[0].partition("=")[0]
    long_form = first_key in long_keys or any(
        field.partition("=")[0] in long_keys for field in fields[1:]
    )
    if long_form:
        for field in fields:
            key, separator, value = field.partition("=")
            if separator and key in {"target", "dst", "destination"}:
                return value
        raise ValueError(
            "unsupported long Docker mount syntax; target, dst, or destination is required"
        )
    parts = mount.split(":")
    if len(parts) >= 2:
        return parts[1]
    return None


def _normalized_mount_destination(mount: str) -> Path | None:
    """Return an absolute, lexical destination for overlap checks."""
    destination = _mount_destination(mount)
    if destination is None:
        return None
    path = Path(destination)
    if not path.is_absolute():
        return None
    return path.resolve(strict=False)


def load_pack(path_like: str | Path) -> ContainerPack:
    """Load a runtime pack from TOML."""
    path = workspace_path(path_like)
    with path.open("rb") as handle:
        data = cast("dict[str, object]", tomllib.load(handle))

    pack_data = data.get("pack", {})
    smoke_data = data.get("smoke", {})
    runtime_data = data.get("runtime", {})
    if (
        not isinstance(pack_data, dict)
        or not isinstance(smoke_data, dict)
        or not isinstance(runtime_data, dict)
    ):
        raise ValueError(f"{path}: pack, smoke, and runtime sections must be tables")
    pack_section = cast("dict[str, object]", pack_data)
    smoke_section = cast("dict[str, object]", smoke_data)
    runtime_section = cast("dict[str, object]", runtime_data)

    name = require_string(pack_section, "name", path, "pack")
    dockerfile = require_string(pack_section, "dockerfile", path, "pack")
    context = require_string(pack_section, "context", path, "pack")
    image_tag = require_string(pack_section, "image_tag", path, "pack")

    target = pack_section.get("target")
    if target is not None and not isinstance(target, str):
        raise ValueError(f"{path}: [pack].target must be a string if present")
    platform = pack_section.get("platform")
    if platform is not None and not isinstance(platform, str):
        raise ValueError(f"{path}: [pack].platform must be a string if present")

    smoke_shell = smoke_section.get("shell", "/bin/bash")
    if not isinstance(smoke_shell, str):
        raise ValueError(f"{path}: [smoke].shell must be a string")
    runtime_shell = runtime_section.get("shell", "/bin/bash")
    if not isinstance(runtime_shell, str):
        raise ValueError(f"{path}: [runtime].shell must be a string")
    workdir = runtime_section.get("workdir", "/workspace")
    if not isinstance(workdir, str):
        raise ValueError(f"{path}: [runtime].workdir must be a string")
    workspace_mount = runtime_section.get("workspace_mount", "/workspace")
    if not isinstance(workspace_mount, str):
        raise ValueError(f"{path}: [runtime].workspace_mount must be a string")
    gpus = runtime_section.get("gpus")
    if gpus is not None and not isinstance(gpus, str):
        raise ValueError(f"{path}: [runtime].gpus must be a string if present")
    optional_mount_profiles = _parse_optional_mount_profiles(runtime_section, path)
    linked_data_roots, linked_data_roots_declared = _parse_linked_data_roots(
        runtime_section, path
    )
    if ("linked-data-roots" in optional_mount_profiles) != linked_data_roots_declared:
        raise ValueError(
            f"{path}: linked-data-roots profile and linked_data_roots list must both be present or absent"
        )
    raw_runtime_mounts = require_string_list(runtime_section, "mounts", path, "runtime")
    if raw_runtime_mounts:
        raise ValueError(
            f"{path}: [runtime].mounts is not supported; use an explicit optional mount profile"
        )
    return ContainerPack(
        name=name,
        dockerfile=dockerfile,
        context=context,
        target=target,
        image_tag=image_tag,
        platform=platform,
        smoke=SmokeSpec(
            shell=smoke_shell,
            commands=require_string_list(smoke_section, "commands", path, "smoke"),
        ),
        runtime=RuntimeSpec(
            shell=runtime_shell,
            workdir=workdir,
            workspace_mount=workspace_mount,
            env=require_string_list(runtime_section, "env", path, "runtime"),
            mounts=(),
            gpus=gpus,
            optional_mount_profiles=optional_mount_profiles,
            linked_data_roots=linked_data_roots,
            linked_data_roots_declared=linked_data_roots_declared,
        ),
    )


def load_or_default_pack(path_like: str | None) -> ContainerPack:
    """Load an explicit project pack or use direct Dockerfile defaults."""
    if path_like is None:
        return default_container_pack()
    return load_pack(path_like)


def apply_pack_overrides(
    pack: ContainerPack,
    *,
    dockerfile: str | None = None,
    context: str | None = None,
    target: str | None = None,
    tag: str | None = None,
) -> ContainerPack:
    """Apply CLI overrides on top of a resolved pack."""
    return replace(
        pack,
        dockerfile=dockerfile if dockerfile is not None else pack.dockerfile,
        context=context if context is not None else pack.context,
        target=target if target is not None else pack.target,
        image_tag=tag if tag is not None else pack.image_tag,
    )


def build_build_command(
    builder: str,
    pack: ContainerPack,
    *,
    pull: bool = False,
    no_cache: bool = False,
    labels: Mapping[str, str] | None = None,
) -> list[str]:
    """Build the container build command for one pack."""
    command = [
        builder,
        "build",
        "-f",
        str(workspace_path(pack.dockerfile)),
        "-t",
        pack.image_tag,
    ]
    if pull:
        command.append("--pull")
    if no_cache:
        command.append("--no-cache")
    for key, value in sorted((labels or {}).items()):
        command.extend(["--label", f"{key}={value}"])
    if pack.target:
        command.extend(["--target", pack.target])
    if pack.platform:
        command.extend(["--platform", pack.platform])
    command.append(str(workspace_path(pack.context)))
    return command


def build_run_command(
    builder: str,
    pack: ContainerPack,
    *,
    workspace_root: Path,
    command: list[str],
    shell: str | None = None,
    workdir: str | None = None,
    container_workspace: str | None = None,
    env: tuple[str, ...] = (),
    mounts: tuple[str, ...] = (),
    ports: tuple[str, ...] = (),
    gpus: str | None = None,
    user: str | None = None,
    tty: bool = False,
    labels: Mapping[str, str] | None = None,
) -> list[str]:
    """Build one container run command."""
    resolved_workspace = workspace_root.resolve()
    resolved_mount = container_workspace or pack.runtime.workspace_mount
    resolved_workdir = workdir or pack.runtime.workdir
    resolved_shell = shell or pack.runtime.shell
    resolved_gpus = gpus if gpus is not None else pack.runtime.gpus
    if pack.runtime.mounts:
        raise ValueError(
            "raw runtime.mounts are not supported; use an explicit optional mount profile"
        )
    combined = dict(
        item.split("=", 1)
        for item in (*pack.runtime.env, *env)
        if "=" in item
    )
    combined_env = tuple(f"{name}={value}" for name, value in combined.items())
    optional_profiles = _canonical_optional_mount_profiles(pack)
    linked_data_mounts = resolve_linked_data_mounts(pack, resolved_workspace)
    profile_mounts = (
        resolve_docker_host_mounts()
        if "docker-host" in optional_profiles
        else ()
    )
    linked_targets = tuple(
        Path(linked_root.target).resolve(strict=False)
        for linked_root in pack.runtime.linked_data_roots
    )
    for mount in mounts:
        destination = _normalized_mount_destination(mount)
        if destination is not None and any(
            destination == linked_target
            or destination.is_relative_to(linked_target)
            or linked_target.is_relative_to(destination)
            for linked_target in linked_targets
        ):
            raise ValueError(
                "CLI mount destination collides with a linked-data-roots target"
            )
        if (
            "docker-host" in optional_profiles
            and destination == Path("/var/run/docker.sock").resolve(strict=False)
        ):
            raise ValueError("CLI mount destination collides with docker-host socket target")
    combined_mounts = linked_data_mounts + profile_mounts + mounts

    run_command = [builder, "run", "--rm"]
    if tty:
        run_command.extend(["-i", "-t"])
    if user is not None:
        run_command.extend(["--user", user])
    if resolved_gpus is not None:
        run_command.extend(["--gpus", resolved_gpus])
    for key, value in sorted((labels or {}).items()):
        run_command.extend(["--label", f"{key}={value}"])

    run_command.extend(["-v", f"{resolved_workspace}:{resolved_mount}"])
    auto_mounts = default_host_mounts()
    for mount in (*auto_mounts, *combined_mounts):
        run_command.extend(["-v", mount])
    for port in ports:
        run_command.extend(["-p", port])
    for env_item in combined_env:
        run_command.extend(["-e", env_item])
    run_command.extend(["-w", resolved_workdir, pack.image_tag])

    if not command:
        return run_command + [resolved_shell]
    return run_command + command


def build_shell_invocation(shell: str, script: str) -> list[str]:
    """Return a shell invocation for a multi-line script."""
    return [shell, "-lc", script]


def join_shell_lines(lines: list[str]) -> str:
    """Join multi-line shell script fragments."""
    return "\n".join(line for line in lines if line.strip())


def print_label_and_command(label: str, command: list[str]) -> None:
    """Print one labeled command."""
    print(f"{label}:")
    print(shlex.join(command))


def load_toml(path_like: str | Path) -> dict[str, object]:
    """Load one generic TOML file."""
    path = workspace_path(path_like)
    with path.open("rb") as handle:
        return tomllib.load(handle)
