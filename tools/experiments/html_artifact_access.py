#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Builds local-browser access commands for remote HTML artifacts.
# upstream design ../../documents/result-log-retention-and-visualization.md defines visual artifact retention.
# upstream design ../../documents/experiment-report-style.md defines experiment report artifact layout.
# downstream design ../../documents/tools/html_artifact_access.md documents command usage.
# downstream implementation ../../tests/tools/test_html_artifact_access.py covers command rendering.
# downstream design ../catalog.yaml catalogs this experiment helper.
# @dependency-end
"""Print SSH tunnel and static-server commands for remote HTML artifacts."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_HTTP_PORT = 8765
DEFAULT_BIND_ADDRESS = "127.0.0.1"
CONTAINER_BIND_ADDRESS = "0.0.0.0"
SOCKET_ADDRESS_INDEX = 4
SSH_CONNECTION_SERVER_HOST_INDEX = 2
SSH_HOST_ENV_VAR = "AGENT_CANON_SSH_HOST"
SSH_CONNECTION_ENV_VAR = "SSH_CONNECTION"
USER_ENV_VAR = "USER"
SSH_HOST_PLACEHOLDER = "<ssh-host>"


@dataclass(frozen=True)
class AccessPlan:
    """Browser access commands for one HTML artifact."""

    mode: str
    report_path: str
    server_directory: str
    ssh_host: str
    tunnel_target: str
    local_url: str
    server_command: str
    tunnel_command: str
    local_open_macos: str
    local_open_linux: str
    local_open_windows: str
    note: str


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build commands to open a remote HTML artifact in a local browser."
    )
    parser.add_argument("report_path", help="HTML file path on the current runtime or container.")
    parser.add_argument(
        "--ssh-host",
        default="",
        help=(
            "SSH target for the HPC host. Optional; derives from "
            f"${SSH_HOST_ENV_VAR}, SSH_CONNECTION, or {SSH_HOST_PLACEHOLDER}."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Local and remote HTTP port.",
    )
    parser.add_argument(
        "--bind",
        default="",
        help="HTTP server bind address. Defaults to 127.0.0.1, or 0.0.0.0 with --use-container-ip.",
    )
    parser.add_argument(
        "--tunnel-target",
        default="",
        help="Host/IP the SSH server should forward to. Use the container IP for direct container serving.",
    )
    parser.add_argument(
        "--use-container-ip",
        action="store_true",
        help="Use this runtime's non-loopback IPv4 address as the tunnel target and bind to 0.0.0.0.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def local_url(port: int, filename: str) -> str:
    """Return the local browser URL for one forwarded artifact."""
    return f"http://127.0.0.1:{port}/{filename}"


def tunnel_command(ssh_host: str, port: int, target: str) -> str:
    """Return the local-PC SSH tunnel command."""
    return shlex.join(
        [
            "ssh",
            "-N",
            "-L",
            f"{port}:{target}:{port}",
            ssh_host,
        ]
    )


def open_commands(url: str) -> tuple[str, str, str]:
    """Return platform-specific local browser commands."""
    return (
        shlex.join(["open", url]),
        shlex.join(["xdg-open", url]),
        f"start {url}",
    )


def resolved_report_path(report_path: str) -> Path:
    """Return a stable current-runtime path for one report."""
    return Path(report_path).expanduser().resolve()


def ssh_host_from_connection() -> str:
    """Infer a local-PC SSH target from SSH_CONNECTION when available."""
    fields = os.environ.get(SSH_CONNECTION_ENV_VAR, "").split()
    if len(fields) <= SSH_CONNECTION_SERVER_HOST_INDEX:
        return ""
    user = os.environ.get(USER_ENV_VAR, "")
    if user:
        return f"{user}@{fields[SSH_CONNECTION_SERVER_HOST_INDEX]}"
    return fields[SSH_CONNECTION_SERVER_HOST_INDEX]


def current_runtime_ip() -> str:
    """Return a non-loopback IPv4 address for the current runtime."""
    hostname = socket.gethostname()
    addresses = [
        entry[SOCKET_ADDRESS_INDEX][0]
        for entry in socket.getaddrinfo(hostname, None, family=socket.AF_INET)
    ]
    for address in addresses:
        if not address.startswith("127."):
            return address
    if addresses:
        return addresses[0]
    return hostname


def effective_bind(args: argparse.Namespace) -> str:
    """Return the HTTP bind address for the requested mode."""
    if args.bind:
        return str(args.bind)
    if args.use_container_ip:
        return CONTAINER_BIND_ADDRESS
    return DEFAULT_BIND_ADDRESS


def effective_tunnel_target(args: argparse.Namespace) -> str:
    """Return the SSH tunnel target visible from the SSH host."""
    if args.tunnel_target:
        return str(args.tunnel_target)
    if args.use_container_ip:
        return current_runtime_ip()
    return DEFAULT_BIND_ADDRESS


def effective_ssh_host(args: argparse.Namespace) -> str:
    """Return the SSH host target for the local-PC tunnel command."""
    if args.ssh_host:
        return str(args.ssh_host)
    configured_host = os.environ.get(SSH_HOST_ENV_VAR, "")
    if configured_host:
        return configured_host
    inferred_host = ssh_host_from_connection()
    if inferred_host:
        return inferred_host
    return SSH_HOST_PLACEHOLDER


def build_http_server_plan(
    report_path: str,
    ssh_host: str,
    port: int,
    bind: str,
    tunnel_target: str,
) -> AccessPlan:
    """Build direct Python http.server access commands."""
    path = resolved_report_path(report_path)
    url = local_url(port, path.name)
    macos, linux, windows = open_commands(url)
    return AccessPlan(
        mode="python-http-server",
        report_path=str(path),
        server_directory=str(path.parent),
        ssh_host=ssh_host,
        tunnel_target=tunnel_target,
        local_url=url,
        server_command=shlex.join(
            [
                "python3",
                "-m",
                "http.server",
                str(port),
                "--bind",
                bind,
                "--directory",
                str(path.parent),
            ]
        ),
        tunnel_command=tunnel_command(ssh_host, port, tunnel_target),
        local_open_macos=macos,
        local_open_linux=linux,
        local_open_windows=windows,
        note="Run the server command where the HTML file exists, then run the tunnel on the local PC.",
    )


def build_plan(args: argparse.Namespace) -> AccessPlan:
    """Build the requested access plan."""
    return build_http_server_plan(
        report_path=str(args.report_path),
        ssh_host=effective_ssh_host(args),
        port=int(args.port),
        bind=effective_bind(args),
        tunnel_target=effective_tunnel_target(args),
    )


def render_text(plan: AccessPlan) -> str:
    """Render one access plan as machine-readable lines."""
    lines = [
        f"HTML_ARTIFACT_MODE={plan.mode}",
        f"HTML_ARTIFACT_REPORT_PATH={plan.report_path}",
        f"HTML_ARTIFACT_SERVER_DIRECTORY={plan.server_directory}",
        f"HTML_ARTIFACT_SSH_HOST={plan.ssh_host}",
        f"HTML_ARTIFACT_TUNNEL_TARGET={plan.tunnel_target}",
    ]
    lines.extend(
        [
            f"HTML_ARTIFACT_SERVER_COMMAND={plan.server_command}",
            f"HTML_ARTIFACT_TUNNEL_COMMAND={plan.tunnel_command}",
            f"HTML_ARTIFACT_LOCAL_URL={plan.local_url}",
            f"HTML_ARTIFACT_OPEN_MACOS={plan.local_open_macos}",
            f"HTML_ARTIFACT_OPEN_LINUX={plan.local_open_linux}",
            f"HTML_ARTIFACT_OPEN_WINDOWS={plan.local_open_windows}",
            f"HTML_ARTIFACT_NOTE={plan.note}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Print one local-browser access plan."""
    args = parse_args()
    plan = build_plan(args)
    if args.format == "json":
        print(json.dumps(asdict(plan), indent=2, ensure_ascii=True))
    else:
        print(render_text(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
