#!/usr/bin/env python3
# @dependency-start
# upstream implementation ../../.codex/config.toml declares repo_mcp_server launcher
# upstream design ../../.codex/README.md documents MCP inventory preflight
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md requires MCP preflight
# downstream implementation ../../tests/agent_tools/test_check_mcp_inventory.py tests inventory checks
# @dependency-end
"""Check that required Codex MCP servers are visible in the configured inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class McpServer:
    """One configured MCP server entry."""

    name: str
    status: str
    command: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Fail closed when required Codex MCP servers are absent from inventory."
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="MCP server name that must appear in `codex mcp list --json`.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Pass when no --require entries are provided and the inventory is empty.",
    )
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex CLI binary to execute.",
    )
    return parser


def load_inventory(codex_bin: str) -> list[McpServer]:
    """Load configured MCP servers from Codex."""
    result = subprocess.run(
        [codex_bin, "mcp", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "no output"
        raise RuntimeError(f"`{codex_bin} mcp list --json` failed: {details}")
    try:
        raw_servers = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"`{codex_bin} mcp list --json` returned invalid JSON") from exc
    if not isinstance(raw_servers, list):
        raise RuntimeError("Codex MCP inventory JSON must be a list")

    servers: list[McpServer] = []
    for raw_server in raw_servers:
        if not isinstance(raw_server, dict):
            continue
        name = raw_server.get("name")
        if not isinstance(name, str) or not name:
            continue
        enabled = raw_server.get("enabled")
        status = raw_server.get("status")
        if not isinstance(status, str):
            status = "enabled" if enabled is True else "disabled" if enabled is False else ""
        command = raw_server.get("command")
        transport = raw_server.get("transport")
        if not isinstance(command, str) and isinstance(transport, dict):
            transport_command = transport.get("command")
            if isinstance(transport_command, str):
                command = transport_command
        servers.append(
            McpServer(
                name=name,
                status=status,
                command=command if isinstance(command, str) else "",
            )
        )
    return servers


def render_servers(servers: Sequence[McpServer]) -> None:
    """Print configured servers in a stable grep-friendly form."""
    for server in servers:
        print(
            "MCP_SERVER="
            f"{server.name}\tstatus={server.status or '(unknown)'}"
            f"\tcommand={server.command or '(unknown)'}"
        )


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    try:
        servers = load_inventory(args.codex_bin)
    except RuntimeError as exc:
        print("MCP_INVENTORY=fail")
        print(f"MCP_INVENTORY_ERROR={exc}")
        return 1

    render_servers(servers)
    configured_names = {server.name for server in servers}
    missing = sorted(set(args.require) - configured_names)
    if missing:
        print("MCP_INVENTORY=fail")
        print(f"MISSING_MCP_SERVERS={','.join(missing)}")
        print("NEXT_ACTION=configure_required_mcp_servers_before_work")
        return 1
    if not servers and not args.allow_empty and not args.require:
        print("MCP_INVENTORY=fail")
        print("MCP_INVENTORY_EMPTY=yes")
        print("NEXT_ACTION=pass_--allow-empty_or_--require_expected_servers")
        return 1
    print("MCP_INVENTORY=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
