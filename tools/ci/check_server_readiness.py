#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Inspect host-side readiness for using this machine as the main server."""

from __future__ import annotations

import argparse
import grp
import os
import platform
import pwd
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class Finding:
    """One readiness finding."""

    level: str
    message: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Inspect whether the current host is ready to act as the main repo server."
    )
    parser.add_argument(
        "--layout",
        help="Optional TOML file describing expected paths, mounts, and builder assumptions.",
    )
    return parser


def run_optional(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one command without raising."""
    return subprocess.run(command, check=False, capture_output=True, text=True)


def parse_mounts() -> dict[str, tuple[str, str]]:
    """Return a mapping of mountpoint -> (source, fstype)."""
    mounts: dict[str, tuple[str, str]] = {}
    with Path("/proc/mounts").open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if len(parts) < 3:
                continue
            source, mountpoint, fstype = parts[:3]
            mounts[mountpoint] = (source, fstype)
    return mounts


def mount_for_path(path: Path, mounts: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """Return the closest mount entry for one path."""
    resolved = path.resolve()
    candidates = sorted(mounts, key=len, reverse=True)
    for mountpoint in candidates:
        mount_path = Path(mountpoint)
        if resolved == mount_path or mount_path in resolved.parents:
            return mounts[mountpoint]
    return None


def load_layout(path_like: str) -> dict[str, object]:
    """Load one TOML layout file."""
    path = Path(path_like)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: TOML root must be a table")
    return data


def detect_host_kind() -> str:
    """Return a coarse host kind."""
    kernel = platform.release().lower()
    if "microsoft" in kernel or "wsl" in kernel:
        return "wsl2"
    return "linux"


def command_exists(name: str) -> bool:
    """Return whether one command exists."""
    return shutil.which(name) is not None


def format_command_result(result: subprocess.CompletedProcess[str]) -> str:
    """Return the first useful line from command output."""
    combined = "\n".join(part.strip() for part in (result.stderr, result.stdout) if part.strip())
    if not combined:
        return "(no output)"
    return combined.splitlines()[0]


def collect_findings(layout: dict[str, object] | None) -> tuple[list[Finding], list[str]]:
    """Collect findings and summary lines."""
    findings: list[Finding] = []
    summary: list[str] = []
    mounts = parse_mounts()

    host_kind = detect_host_kind()
    summary.append(f"host_kind={host_kind}")
    summary.append(f"kernel={platform.platform()}")
    username = os.environ.get("USER") or pwd.getpwuid(os.getuid()).pw_name
    summary.append(f"user={username}")

    active_group_ids = set(os.getgroups())
    active_group_names = sorted(
        grp.getgrgid(group_id).gr_name for group_id in active_group_ids if group_id >= 0
    )
    summary.append(f"active_groups={','.join(active_group_names)}")

    for command_name in ("git", "python3", "codex"):
        if command_exists(command_name):
            findings.append(Finding("ok", f"{command_name} is available"))
        else:
            findings.append(Finding("error", f"{command_name} is not available"))

    docker_exists = command_exists("docker")
    podman_exists = command_exists("podman")
    if docker_exists:
        findings.append(Finding("ok", "docker CLI is available"))
    elif podman_exists:
        findings.append(Finding("warning", "docker CLI is absent but podman is available"))
    else:
        findings.append(Finding("error", "Neither docker nor podman is available"))

    docker_group = grp.getgrnam("docker") if "docker" in {group.gr_name for group in grp.getgrall()} else None
    docker_socket = Path("/var/run/docker.sock")
    if docker_socket.exists():
        source_mount = mount_for_path(docker_socket, mounts)
        if source_mount is not None:
            _, socket_fs = source_mount
            summary.append(f"docker_socket_fs={socket_fs}")
        if os.access(docker_socket, os.R_OK | os.W_OK):
            findings.append(Finding("ok", "docker socket is accessible from the current shell"))
        else:
            findings.append(
                Finding(
                    "error",
                    "docker socket exists but is not accessible from the current shell; reopen the login shell or verify with `sg docker -c 'docker version'`",
                )
            )
        if docker_group is not None:
            listed_in_group = username in docker_group.gr_mem
            active_in_group = docker_group.gr_gid in active_group_ids
            if listed_in_group and not active_in_group:
                findings.append(
                    Finding(
                        "warning",
                        "user is listed in docker group but the current shell does not have that group yet; reopen the login shell before Docker checks",
                    )
                )
    else:
        findings.append(Finding("warning", "/var/run/docker.sock is absent"))

    docker_version = run_optional(["docker", "version"]) if docker_exists else None
    if docker_version is not None:
        if docker_version.returncode == 0:
            findings.append(Finding("ok", "docker version succeeded"))
        else:
            findings.append(Finding("warning", f"docker version failed: {format_command_result(docker_version)}"))

    default_paths = {
        "bare_repo_root": Path("/mnt/git"),
        "workspace_root": Path("/mnt/l/workspace"),
        "docker_state_root": Path("/var/lib/docker"),
    }
    for label, path in default_paths.items():
        if path.exists():
            mount_info = mount_for_path(path, mounts)
            mount_label = f"{mount_info[1]} from {mount_info[0]}" if mount_info is not None else "unknown"
            findings.append(Finding("ok", f"{label} exists ({mount_label})"))
        else:
            findings.append(Finding("warning", f"{label} does not exist: {path}"))

    if layout is not None:
        server_data = layout.get("server", {})
        paths_data = layout.get("paths", {})
        mounts_data = layout.get("mounts", {})
        if isinstance(server_data, dict):
            expected_host_kind = server_data.get("host_kind")
            if isinstance(expected_host_kind, str) and expected_host_kind != host_kind:
                findings.append(
                    Finding(
                        "warning",
                        f"layout host_kind={expected_host_kind} but detected host_kind={host_kind}",
                    )
                )
            expected_builder = server_data.get("container_builder")
            if isinstance(expected_builder, str):
                if not command_exists(expected_builder):
                    findings.append(Finding("error", f"expected builder is unavailable: {expected_builder}"))
                else:
                    findings.append(Finding("ok", f"expected builder is present: {expected_builder}"))
        if isinstance(paths_data, dict):
            for key, raw_path in paths_data.items():
                if not isinstance(raw_path, str):
                    continue
                path = Path(raw_path)
                if path.exists():
                    findings.append(Finding("ok", f"layout path exists: {key} -> {path}"))
                else:
                    findings.append(Finding("warning", f"layout path is missing: {key} -> {path}"))
                if isinstance(mounts_data, dict):
                    mount_spec = mounts_data.get(key)
                    if isinstance(mount_spec, dict):
                        expected_type = mount_spec.get("type")
                        required = mount_spec.get("required", False)
                        mount_info = mount_for_path(path, mounts)
                        if mount_info is None:
                            if required:
                                findings.append(Finding("error", f"no mount information found for required path: {path}"))
                            continue
                        _, actual_type = mount_info
                        if isinstance(expected_type, str) and actual_type != expected_type:
                            level = "error" if required else "warning"
                            findings.append(
                                Finding(level, f"{key} mount type mismatch: expected {expected_type}, got {actual_type}")
                            )
                        else:
                            findings.append(Finding("ok", f"{key} mount type matches: {actual_type}"))

    return findings, summary


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    try:
        layout = load_layout(args.layout) if args.layout else None
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    findings, summary = collect_findings(layout)
    for line in summary:
        print(line)
    for finding in findings:
        print(f"{finding.level.upper()}: {finding.message}")

    if any(finding.level == "error" for finding in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
