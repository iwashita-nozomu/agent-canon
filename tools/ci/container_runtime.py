#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides container runtime CI automation.
# upstream design ../README.md shared automation index
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md exact runtime receipt names
# @dependency-end

"""Shared helpers for repo-defined container runtime scripts."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]


def detect_workspace_root() -> Path:
    """Return the repo root even when reached through a symlink view."""
    markers = ("docker/packs/default.toml", "README.md")
    search_roots = [Path.cwd().resolve(), Path(__file__).absolute().parent]
    for search_root in search_roots:
        for candidate in (search_root, *search_root.parents):
            if all((candidate / marker).exists() for marker in markers):
                return candidate
    return Path(__file__).absolute().parents[2]


# Preserve the template or derived checkout root when this module is imported
# through a symlinked runtime surface from vendor/agent-canon.
WORKSPACE_ROOT = detect_workspace_root()
HOST_GH_CONFIG = Path.home() / ".config" / "gh"
HOST_SSH_DIR = Path.home() / ".ssh"
BUILDER_INFO_TIMEOUT_SECONDS = 15
HOST_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
CONTAINER_RUNTIME_ROOT = "/var/lib/agent-canon/runtime"
DOCKER_HOST_SOCKET = Path("/var/run/docker.sock")
RUNTIME_GROUP_NAME = "agent-canon-runtime"
PROCESS_UMASK = 0o0007
DIRECTORY_MODE = 0o2770
FILE_MODE = 0o0660
LOCAL_FLOCK_FILESYSTEMS = ("btrfs", "ext4", "xfs")
PROVISION_RECEIPT_NAME = "shared-runtime-provision.json"
READBACK_RECEIPT_NAME = "shared-runtime-readback.json"
RUNTIME_ROUTE = "MANAGED_CONTAINER"
DEPENDENCY_PROFILE_ENV = "AGENT_CANON_DEPENDENCY_PROFILE"
DEFAULT_DEPENDENCY_PROFILE = "full"
DEPENDENCY_PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
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
    dependency_profile: str = DEFAULT_DEPENDENCY_PROFILE
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


def default_pack_path() -> Path:
    """Return the default runtime pack path."""
    return workspace_path("docker/packs/default.toml")


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
    dependency_profile = runtime_section.get(
        "dependency_profile", DEFAULT_DEPENDENCY_PROFILE
    )
    if (
        not isinstance(dependency_profile, str)
        or DEPENDENCY_PROFILE_RE.fullmatch(dependency_profile) is None
    ):
        raise ValueError(
            f"{path}: [runtime].dependency_profile must be a non-empty profile name"
        )
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
            dependency_profile=dependency_profile,
            optional_mount_profiles=optional_mount_profiles,
            linked_data_roots=linked_data_roots,
            linked_data_roots_declared=linked_data_roots_declared,
        ),
    )


def load_or_default_pack(path_like: str | None) -> ContainerPack:
    """Load the requested pack or the default pack."""
    if path_like is None:
        return load_pack(default_pack_path())
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
    dependency_profile_env = (
        f"{DEPENDENCY_PROFILE_ENV}={pack.runtime.dependency_profile}"
    )
    combined_env = tuple(
        dict.fromkeys((*pack.runtime.env, *env, dependency_profile_env))
    )
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


def build_workspace_setup_command(
    command: list[str],
    *,
    shell: str,
    container_workspace: str,
    dependency_profile: str,
    skip_setup: bool = False,
) -> list[str]:
    """Run the repo installer for the pack profile before one command."""
    if skip_setup:
        return command

    installer = (
        f"{container_workspace.rstrip('/')}/docker/install_python_dependencies.sh"
    )
    lines = [
        "set -euo pipefail",
        (
            f"if [ -f {shlex.quote(installer)} ]; then "
            f"bash {shlex.quote(installer)} {shlex.quote(container_workspace)} "
            f"--profile {shlex.quote(dependency_profile)}; "
            "fi"
        ),
        f"exec {shlex.join(command)}",
    ]
    return build_shell_invocation(shell, join_shell_lines(lines))


def join_shell_lines(lines: list[str]) -> str:
    """Join multi-line shell script fragments."""
    return "\n".join(line for line in lines if line.strip())


def run_or_print(command: list[str], *, print_only: bool) -> int:
    """Run one command or print it."""
    print(shlex.join(command))
    if print_only:
        return 0
    return subprocess.run(command, cwd=WORKSPACE_ROOT, check=False).returncode


def print_label_and_command(label: str, command: list[str]) -> None:
    """Print one labeled command."""
    print(f"{label}:")
    print(shlex.join(command))


def load_toml(path_like: str | Path) -> dict[str, object]:
    """Load one generic TOML file."""
    path = workspace_path(path_like)
    with path.open("rb") as handle:
        return tomllib.load(handle)
