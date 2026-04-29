#!/usr/bin/env python3
# @dependency-start
# responsibility Checks mcp inventory agent workflow state.
# upstream implementation ../../.codex/config.toml declares repo_mcp_server launcher
# upstream design ../../.codex/README.md documents MCP inventory preflight
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md requires MCP preflight
# downstream implementation ../../tests/agent_tools/test_check_mcp_inventory.py tests inventory checks
# @dependency-end
"""Check that required Codex MCP servers are visible in the configured inventory."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class McpServer:
    """One configured MCP server entry."""

    name: str
    status: str
    command: str
    args: tuple[str, ...]


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
        inventory_data = cast(object, json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"`{codex_bin} mcp list --json` returned invalid JSON") from exc
    if not isinstance(inventory_data, list):
        raise RuntimeError("Codex MCP inventory JSON must be a list")
    raw_servers = cast(list[object], inventory_data)

    servers: list[McpServer] = []
    for raw_server in raw_servers:
        if not isinstance(raw_server, dict):
            continue
        server_data = cast(dict[str, Any], raw_server)
        name = server_data.get("name")
        if not isinstance(name, str) or not name:
            continue
        enabled = server_data.get("enabled")
        status = server_data.get("status")
        if not isinstance(status, str):
            status = "enabled" if enabled is True else "disabled" if enabled is False else ""
        command = server_data.get("command")
        raw_args = server_data.get("args")
        transport = server_data.get("transport")
        if isinstance(transport, dict):
            transport_data = cast(dict[str, Any], transport)
            if not isinstance(command, str):
                transport_command = transport_data.get("command")
                if isinstance(transport_command, str):
                    command = transport_command
            if not isinstance(raw_args, list):
                raw_args = transport_data.get("args")
        parsed_args = (
            tuple(item for item in cast(list[object], raw_args) if isinstance(item, str))
            if isinstance(raw_args, list)
            else ()
        )
        servers.append(
            McpServer(
                name=name,
                status=status,
                command=command if isinstance(command, str) else "",
                args=parsed_args,
            )
        )
    return servers


def load_project_config_server_names(root: Path) -> set[str]:
    """Return MCP server names declared by the repo-local Codex config."""
    config_path = root / ".codex" / "config.toml"
    if not config_path.is_file():
        return set()
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    names: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("[mcp_servers.") or not stripped.endswith("]"):
            continue
        server_name = stripped.removeprefix("[mcp_servers.").removesuffix("]").strip()
        if server_name and not any(char.isspace() for char in server_name):
            names.add(server_name.strip('"').strip("'"))
    return names


def launcher_errors(server: McpServer, root: Path) -> list[str]:
    """Return launcher availability errors for one server."""
    errors: list[str] = []
    if not server.command:
        return [f"{server.name}: missing launcher command"]
    if "/" in server.command:
        command_path = (root / server.command).resolve() if not Path(server.command).is_absolute() else Path(server.command)
        if not command_path.exists():
            errors.append(f"{server.name}: launcher command path not found: {server.command}")
    elif shutil.which(server.command) is None:
        errors.append(f"{server.name}: launcher command not found on PATH: {server.command}")

    for arg in server.args:
        if arg.startswith("-") or "/" not in arg:
            continue
        arg_path = (root / arg).resolve() if not Path(arg).is_absolute() else Path(arg)
        if not arg_path.exists():
            errors.append(f"{server.name}: launcher argument path not found: {arg}")
    return errors


def render_servers(servers: Sequence[McpServer]) -> None:
    """Print configured servers in a stable grep-friendly form."""
    for server in servers:
        print(
            "MCP_SERVER="
            f"{server.name}\tstatus={server.status or '(unknown)'}"
            f"\tcommand={server.command or '(unknown)'}"
            f"\targs={' '.join(server.args) if server.args else '(none)'}"
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
        project_config_names = load_project_config_server_names(Path.cwd())
        ignored_required = sorted(set(missing) & project_config_names)
        print("MCP_INVENTORY=fail")
        print(f"MISSING_MCP_SERVERS={','.join(missing)}")
        if ignored_required:
            print("PROJECT_CODEX_CONFIG_DECLARES_MISSING_MCP=yes")
            print(f"PROJECT_CONFIG_MCP_SERVERS={','.join(sorted(project_config_names))}")
            print("LIKELY_CAUSE=project_config_not_loaded_or_project_not_trusted")
            print("NEXT_ACTION=trust_project_or_fix_codex_config_loading_before_work")
            return 1
        print("NEXT_ACTION=configure_required_mcp_servers_before_work")
        return 1
    required_servers = [server for server in servers if server.name in set(args.require)]
    launcher_issues = [
        issue
        for server in required_servers
        for issue in launcher_errors(server, Path.cwd())
    ]
    if launcher_issues:
        print("MCP_INVENTORY=fail")
        for issue in launcher_issues:
            print(f"MCP_LAUNCHER_ERROR={issue}")
        print("NEXT_ACTION=fix_required_mcp_launcher_before_work")
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
