#!/usr/bin/env python3
"""Shared helpers for repo-defined container runtime scripts."""

from __future__ import annotations

import shutil
import shlex
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def detect_workspace_root() -> Path:
    """Return the outer repo root even when the script is reached through a symlink view."""
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
HOST_CODEX_HOME = Path.home() / ".codex"


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


@dataclass(frozen=True)
class ContainerPack:
    """Describe one reusable container runtime pack."""

    name: str
    dockerfile: str
    context: str
    target: str | None
    image_tag: str
    smoke: SmokeSpec
    runtime: RuntimeSpec


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
            raise RuntimeError(f"No usable container builder found. {'; '.join(unavailable_reasons)}")
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
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return f"{builder} info timed out"

    if result.returncode == 0:
        return None

    detail = command_error_detail(result.stdout, result.stderr)
    if builder == "docker" and "permission denied" in detail.lower():
        return (
            "docker is installed but the daemon socket is not accessible. "
            "Use a user with docker access, switch to --builder podman, or run with --print-only."
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
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{source}: [{section_name}].{key} must be a list of strings")
    return tuple(value)


def load_pack(path_like: str | Path) -> ContainerPack:
    """Load a runtime pack from TOML."""
    path = workspace_path(path_like)
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    pack_data = data.get("pack", {})
    smoke_data = data.get("smoke", {})
    runtime_data = data.get("runtime", {})
    if not isinstance(pack_data, dict) or not isinstance(smoke_data, dict) or not isinstance(runtime_data, dict):
        raise ValueError(f"{path}: pack, smoke, and runtime sections must be tables")

    name = require_string(pack_data, "name", path, "pack")
    dockerfile = require_string(pack_data, "dockerfile", path, "pack")
    context = require_string(pack_data, "context", path, "pack")
    image_tag = require_string(pack_data, "image_tag", path, "pack")

    target = pack_data.get("target")
    if target is not None and not isinstance(target, str):
        raise ValueError(f"{path}: [pack].target must be a string if present")

    smoke_shell = smoke_data.get("shell", "/bin/bash")
    if not isinstance(smoke_shell, str):
        raise ValueError(f"{path}: [smoke].shell must be a string")
    runtime_shell = runtime_data.get("shell", "/bin/bash")
    if not isinstance(runtime_shell, str):
        raise ValueError(f"{path}: [runtime].shell must be a string")
    workdir = runtime_data.get("workdir", "/workspace")
    if not isinstance(workdir, str):
        raise ValueError(f"{path}: [runtime].workdir must be a string")
    workspace_mount = runtime_data.get("workspace_mount", "/workspace")
    if not isinstance(workspace_mount, str):
        raise ValueError(f"{path}: [runtime].workspace_mount must be a string")
    gpus = runtime_data.get("gpus")
    if gpus is not None and not isinstance(gpus, str):
        raise ValueError(f"{path}: [runtime].gpus must be a string if present")

    return ContainerPack(
        name=name,
        dockerfile=dockerfile,
        context=context,
        target=target,
        image_tag=image_tag,
        smoke=SmokeSpec(
            shell=smoke_shell,
            commands=require_string_list(smoke_data, "commands", path, "smoke"),
        ),
        runtime=RuntimeSpec(
            shell=runtime_shell,
            workdir=workdir,
            workspace_mount=workspace_mount,
            env=require_string_list(runtime_data, "env", path, "runtime"),
            mounts=require_string_list(runtime_data, "mounts", path, "runtime"),
            gpus=gpus,
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
    gpus: str | None = None,
    user: str | None = None,
    tty: bool = False,
    auto_mount_host_codex_home: bool = True,
) -> list[str]:
    """Build one container run command."""
    resolved_workspace = workspace_root.resolve()
    resolved_mount = container_workspace or pack.runtime.workspace_mount
    resolved_workdir = workdir or pack.runtime.workdir
    resolved_shell = shell or pack.runtime.shell
    resolved_gpus = gpus if gpus is not None else pack.runtime.gpus
    combined_env = tuple(dict.fromkeys((*pack.runtime.env, *env)))
    combined_mounts = pack.runtime.mounts + mounts

    run_command = [builder, "run", "--rm"]
    if tty:
        run_command.extend(["-i", "-t"])
    if user is not None:
        run_command.extend(["--user", user])
    if resolved_gpus is not None:
        run_command.extend(["--gpus", resolved_gpus])

    run_command.extend(["-v", f"{resolved_workspace}:{resolved_mount}"])
    if auto_mount_host_codex_home and HOST_CODEX_HOME.is_dir() and not any(":/root/.codex" in mount for mount in combined_mounts):
        run_command.extend(["-v", f"{HOST_CODEX_HOME}:/root/.codex"])
    for mount in combined_mounts:
        run_command.extend(["-v", mount])
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


def load_toml(path_like: str | Path) -> dict[str, Any]:
    """Load one generic TOML file."""
    path = workspace_path(path_like)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: TOML root must be a table")
    return data
