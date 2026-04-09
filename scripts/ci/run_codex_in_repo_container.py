#!/usr/bin/env python3
"""Run Codex inside the repo-defined Docker runtime."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from container_runtime import (
    apply_pack_overrides,
    build_build_command,
    build_run_command,
    build_shell_invocation,
    join_shell_lines,
    load_or_default_pack,
    load_toml,
    print_label_and_command,
    resolve_builder,
    workspace_path,
)


@dataclass(frozen=True)
class ProfileDefaults:
    """Shared defaults for nested Codex profiles."""

    container_home_root: str
    use_host_user: bool
    tty: bool
    share_host_codex_home: bool
    seed_host_codex: bool
    mount_host_gitconfig: bool
    mount_host_git_credentials: bool
    mount_host_ssh_dir: bool
    forward_ssh_auth_sock: bool
    forward_env: tuple[str, ...]


@dataclass(frozen=True)
class CodexProfile:
    """One runtime profile for nested Codex."""

    name: str
    pack: str
    description: str


def parse_bool(data: dict[str, object], key: str, default: bool) -> bool:
    """Extract a boolean option with a default."""
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"docker/codex-container-profiles.toml: {key} must be a boolean")
    return value


def parse_string(data: dict[str, object], key: str, default: str) -> str:
    """Extract a string option with a default."""
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"docker/codex-container-profiles.toml: {key} must be a string")
    return value


def parse_string_list(data: dict[str, object], key: str) -> tuple[str, ...]:
    """Extract a list of strings."""
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"docker/codex-container-profiles.toml: {key} must be a list of strings")
    return tuple(value)


def load_profiles(path_like: str) -> tuple[ProfileDefaults, list[CodexProfile]]:
    """Load nested Codex profile definitions."""
    data = load_toml(path_like)
    defaults_data = data.get("defaults", {})
    if not isinstance(defaults_data, dict):
        raise ValueError("docker/codex-container-profiles.toml: [defaults] must be a table")

    defaults = ProfileDefaults(
        container_home_root=parse_string(defaults_data, "container_home_root", "/workspace/.state/nested-codex"),
        use_host_user=parse_bool(defaults_data, "use_host_user", True),
        tty=parse_bool(defaults_data, "tty", True),
        share_host_codex_home=parse_bool(defaults_data, "share_host_codex_home", False),
        seed_host_codex=parse_bool(defaults_data, "seed_host_codex", True),
        mount_host_gitconfig=parse_bool(defaults_data, "mount_host_gitconfig", True),
        mount_host_git_credentials=parse_bool(defaults_data, "mount_host_git_credentials", True),
        mount_host_ssh_dir=parse_bool(defaults_data, "mount_host_ssh_dir", False),
        forward_ssh_auth_sock=parse_bool(defaults_data, "forward_ssh_auth_sock", True),
        forward_env=parse_string_list(defaults_data, "forward_env"),
    )

    raw_profiles = data.get("profile", [])
    if not isinstance(raw_profiles, list):
        raise ValueError("docker/codex-container-profiles.toml: [[profile]] must be a list")

    profiles: list[CodexProfile] = []
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            raise ValueError("docker/codex-container-profiles.toml: each profile must be a table")
        name = raw_profile.get("name")
        pack = raw_profile.get("pack")
        description = raw_profile.get("description", "")
        if not isinstance(name, str) or not isinstance(pack, str) or not isinstance(description, str):
            raise ValueError("docker/codex-container-profiles.toml: invalid profile entry")
        profiles.append(CodexProfile(name=name, pack=pack, description=description))
    return defaults, profiles


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Run Codex inside the repo-defined container runtime.")
    parser.add_argument(
        "--profiles",
        default="docker/codex-container-profiles.toml",
        help="Profile TOML file. Default: docker/codex-container-profiles.toml",
    )
    parser.add_argument("--profile", default="default", help="Profile name. Default: default")
    parser.add_argument("--list-profiles", action="store_true", help="List available profiles and exit.")
    parser.add_argument(
        "--builder",
        default="auto",
        choices=("auto", "docker", "podman"),
        help="Container builder to use. Default: auto",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip the build step.")
    parser.add_argument("--keep-image", action="store_true", help="Keep the built image.")
    parser.add_argument("--print-only", action="store_true", help="Print commands without executing.")
    parser.add_argument(
        "--share-host-codex-home",
        action="store_true",
        help="Bind mount host ~/.codex directly into the container HOME.",
    )
    parser.add_argument(
        "--no-seed-host-codex",
        action="store_true",
        help="Do not seed auth/config from host ~/.codex.",
    )
    parser.add_argument(
        "--mount-host-ssh-dir",
        action="store_true",
        help="Bind mount host ~/.ssh read-only into the container.",
    )
    parser.add_argument(
        "--no-forward-ssh-auth-sock",
        action="store_true",
        help="Do not forward SSH_AUTH_SOCK even when available.",
    )
    parser.add_argument(
        "--forward-env",
        action="append",
        default=[],
        metavar="NAME",
        help="Additional host environment variable to forward. Repeatable.",
    )
    parser.add_argument("--workspace-root", default=".", help="Workspace root to mount. Default: repo root")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run inside the nested Codex container. Defaults to `codex`.",
    )
    return parser


def cleanup_image(builder: str, image_tag: str) -> None:
    """Remove one image quietly."""
    subprocess.run([builder, "image", "rm", "-f", image_tag], check=False, capture_output=True)


def find_profile(profiles: list[CodexProfile], name: str) -> CodexProfile:
    """Return a profile by name."""
    for profile in profiles:
        if profile.name == name:
            return profile
    known = ", ".join(sorted(profile.name for profile in profiles))
    raise SystemExit(f"Unknown profile `{name}`. Known profiles: {known}")


def host_to_container_home(defaults: ProfileDefaults, profile: CodexProfile, workspace_root: Path) -> tuple[Path, str]:
    """Return the host path and container path for nested Codex HOME."""
    container_home = f"{defaults.container_home_root.rstrip('/')}/{profile.name}"
    container_workspace = "/workspace"
    if not container_home.startswith(container_workspace.rstrip("/") + "/"):
        raise SystemExit("container_home_root must live under /workspace for this template")
    relative_home = container_home.removeprefix(container_workspace).lstrip("/")
    host_home = (workspace_root / relative_home).resolve()
    host_home.mkdir(parents=True, exist_ok=True)
    return host_home, container_home


def normalize_command(command: list[str]) -> list[str]:
    """Normalize the trailing user command."""
    normalized = list(command)
    if normalized and normalized[0] == "--":
        normalized = normalized[1:]
    if normalized:
        return normalized
    return ["codex"]


def build_nested_codex_script(command: list[str], *, seed_host_codex: bool, mount_host_ssh_dir: bool) -> str:
    """Return the shell prelude that seeds HOME before starting Codex."""
    quoted_command = shlex.join(command)
    lines = [
        "set -euo pipefail",
        'mkdir -p "$HOME"',
        'mkdir -p "$HOME/.codex"',
    ]
    if seed_host_codex:
        lines.extend(
            [
                'if [ -d /tmp/host-codex-home ]; then',
                '  for name in auth.json config.toml; do',
                '    if [ -f "/tmp/host-codex-home/$name" ] && [ ! -e "$HOME/.codex/$name" ]; then',
                '      cp "/tmp/host-codex-home/$name" "$HOME/.codex/$name"',
                "    fi",
                "  done",
                "fi",
            ]
        )
    lines.extend(
        [
            'if [ -f /tmp/host-gitconfig ] && [ ! -e "$HOME/.gitconfig" ]; then cp /tmp/host-gitconfig "$HOME/.gitconfig"; fi',
            'if [ -f /tmp/host-git-credentials ] && [ ! -e "$HOME/.git-credentials" ]; then cp /tmp/host-git-credentials "$HOME/.git-credentials"; fi',
        ]
    )
    if mount_host_ssh_dir:
        lines.append('if [ -d /tmp/host-ssh-dir ] && [ ! -e "$HOME/.ssh" ]; then ln -s /tmp/host-ssh-dir "$HOME/.ssh"; fi')
    lines.append(f"exec {quoted_command}")
    return join_shell_lines(lines)


def main() -> int:
    """Run the CLI."""
    try:
        args = build_parser().parse_args()
        defaults, profiles = load_profiles(args.profiles)
        if args.list_profiles:
            for profile in profiles:
                print(f"{profile.name}: {profile.description}")
            return 0

        profile = find_profile(profiles, args.profile)
        workspace_root = workspace_path(args.workspace_root)
        _, container_home = host_to_container_home(defaults, profile, workspace_root)
        pack = apply_pack_overrides(load_or_default_pack(profile.pack))
        builder = resolve_builder(args.builder, print_only=args.print_only)

        share_host_codex_home = defaults.share_host_codex_home or args.share_host_codex_home
        seed_host_codex = defaults.seed_host_codex and not args.no_seed_host_codex and not share_host_codex_home
        mount_host_ssh_dir = defaults.mount_host_ssh_dir or args.mount_host_ssh_dir
        forward_ssh_auth_sock = defaults.forward_ssh_auth_sock and not args.no_forward_ssh_auth_sock
        forward_env = tuple(dict.fromkeys((*defaults.forward_env, *args.forward_env)))
        use_host_user = defaults.use_host_user
        tty = defaults.tty

        mounts: list[str] = []
        envs: list[str] = [f"HOME={container_home}"]

        host_codex_home = Path.home() / ".codex"
        if share_host_codex_home and host_codex_home.is_dir():
            mounts.append(f"{host_codex_home}:{container_home}/.codex:ro")
        elif seed_host_codex and host_codex_home.is_dir():
            mounts.append(f"{host_codex_home}:/tmp/host-codex-home:ro")

        host_gitconfig = Path.home() / ".gitconfig"
        if defaults.mount_host_gitconfig and host_gitconfig.is_file():
            mounts.append(f"{host_gitconfig}:/tmp/host-gitconfig:ro")

        host_git_credentials = Path.home() / ".git-credentials"
        if defaults.mount_host_git_credentials and host_git_credentials.is_file():
            mounts.append(f"{host_git_credentials}:/tmp/host-git-credentials:ro")

        host_ssh_dir = Path.home() / ".ssh"
        if mount_host_ssh_dir and host_ssh_dir.is_dir():
            mounts.append(f"{host_ssh_dir}:/tmp/host-ssh-dir:ro")

        host_ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK", "")
        if forward_ssh_auth_sock and host_ssh_auth_sock:
            mounts.append(f"{host_ssh_auth_sock}:/tmp/host-ssh-agent.sock")
            envs.append("SSH_AUTH_SOCK=/tmp/host-ssh-agent.sock")

        for env_name in forward_env:
            value = os.environ.get(env_name)
            if value:
                envs.append(f"{env_name}={value}")

        user = None
        if use_host_user:
            user = f"{os.getuid()}:{os.getgid()}"

        shell_script = build_nested_codex_script(
            normalize_command(args.command),
            seed_host_codex=seed_host_codex,
            mount_host_ssh_dir=mount_host_ssh_dir,
        )
        build_command = build_build_command(builder, pack)
        run_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=build_shell_invocation(pack.runtime.shell, shell_script),
            env=tuple(envs),
            mounts=tuple(mounts),
            user=user,
            tty=tty,
            auto_mount_host_codex_home=False,
        )

        print_label_and_command("build", build_command)
        print_label_and_command("run", run_command)

        if args.print_only:
            return 0

        image_built_here = False
        if not args.skip_build:
            build_result = subprocess.run(build_command, check=False)
            if build_result.returncode != 0:
                return build_result.returncode
            image_built_here = True

        try:
            run_result = subprocess.run(run_command, check=False)
            return run_result.returncode
        finally:
            if image_built_here and not args.keep_image:
                cleanup_image(builder, pack.image_tag)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
