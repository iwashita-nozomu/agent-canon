#!/usr/bin/env python3
# @dependency-start
# responsibility Provides render devcontainer compose CI automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Render the devcontainer Docker Compose file from the canonical runtime pack."""

from __future__ import annotations

import argparse
from pathlib import Path

from container_runtime import (
    HOST_GH_CONFIG,
    HOST_SSH_DIR,
    detect_host_runtime_features,
    load_or_default_pack,
    workspace_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Render the devcontainer Docker Compose file from the canonical runtime pack."
    )
    parser.add_argument(
        "--pack",
        default="docker/packs/default.toml",
        help="Runtime pack path. Default: docker/packs/default.toml",
    )
    parser.add_argument(
        "--output",
        default=".devcontainer/docker-compose.generated.yml",
        help="Compose output path. Default: .devcontainer/docker-compose.generated.yml",
    )
    return parser


def main() -> int:
    """Render the compose file."""
    args = build_parser().parse_args()
    pack = load_or_default_pack(args.pack)
    output_path = workspace_path(args.output)
    features = detect_host_runtime_features()

    volume_lines = [f"      - ..:{pack.runtime.workspace_mount}:cached"]
    if features.has_mnt_git:
        volume_lines.append("      - /mnt/git:/mnt/git")
    if features.has_host_codex_home:
        volume_lines.append(f"      - {Path.home() / '.codex'}:/root/.codex")
    if features.has_host_gh_config:
        volume_lines.append(f"      - {HOST_GH_CONFIG}:/root/.config/gh")
    if features.has_host_ssh_dir:
        volume_lines.append(f"      - {HOST_SSH_DIR}:/root/.ssh:ro")
    if features.ssh_auth_sock is not None:
        volume_lines.append(f"      - {features.ssh_auth_sock}:/ssh-agent")

    environment_lines = ['      DEVCONTAINER_RUNTIME_MODE: "generated"']
    if features.ssh_auth_sock is not None:
        environment_lines.append('      SSH_AUTH_SOCK: "/ssh-agent"')
    if features.has_gpu:
        environment_lines.extend(
            [
                '      DEVCONTAINER_GPU_MODE: "enabled"',
                "      NVIDIA_VISIBLE_DEVICES: all",
                '      NVIDIA_DRIVER_CAPABILITIES: "compute,utility"',
            ]
        )
    else:
        environment_lines.append('      DEVCONTAINER_GPU_MODE: "disabled"')

    lines = [
        "services:",
        "  workspace:",
        "    build:",
        "      context: ..",
        f"      dockerfile: {pack.dockerfile}",
        f"    working_dir: {pack.runtime.workdir}",
        "    volumes:",
        *volume_lines,
        '    command: /bin/bash -lc "sleep infinity"',
        "    tty: true",
        "    init: true",
    ]
    if features.has_gpu:
        lines.append("    gpus: all")
    lines.extend(
        [
            "    environment:",
            *environment_lines,
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        "devcontainer runtime generated:"
        f" gpu={int(features.has_gpu)}"
        f" mount_mnt_git={int(features.has_mnt_git)}"
        f" mount_host_codex={int(features.has_host_codex_home)}"
        f" mount_host_gh={int(features.has_host_gh_config)}"
        f" mount_host_ssh={int(features.has_host_ssh_dir)}"
        f" forward_ssh_agent={int(features.ssh_auth_sock is not None)}"
        f" pack={args.pack}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
