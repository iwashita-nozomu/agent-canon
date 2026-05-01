#!/usr/bin/env python3
# @dependency-start
# responsibility Implements the repository MCP server.
# upstream design README.md MCP runtime surface contract
# upstream implementation ./repo_mcp_server.sh launches this server
# upstream implementation ../tools/agent_tools/goal_loop.py provides adaptive loop state
# downstream implementation ../tools/agent_tools/check_mcp_inventory.py validates launcher
# @dependency-end
"""Small repo-local MCP stdio server for Agent Canon repositories."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SERVER_INFO = {"name": "repo_mcp_server", "version": "0.1.0"}
USE_CONTENT_LENGTH = False


def repo_root() -> Path:
    """Return the repository root this server should describe."""
    configured = os.environ.get("CODEX_WORKSPACE_ROOT")
    if configured:
        return Path(configured).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    return Path.cwd().resolve()


def send(message: Mapping[str, Any]) -> None:
    """Write one JSON-RPC message to stdout."""
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if USE_CONTENT_LENGTH:
        sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return
    sys.stdout.buffer.write(payload + b"\n")
    sys.stdout.buffer.flush()


def tool_schema() -> dict[str, Any]:
    """Return the available MCP tools."""
    return {
        "tools": [
            {
                "name": "repo.root",
                "description": "Return the repository root used by this MCP server.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "repo.status",
                "description": (
                    "Return `git status --short --branch --untracked-files=all` "
                    "for the repository."
                ),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "goal.loop_status",
                "description": (
                    "Return machine-readable goal.md loop status and NEXT_ACTION. "
                    "Use this for adaptive-improvement-loop iteration decisions."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "goal_file": {
                            "type": "string",
                            "description": (
                                "Goal file path relative to repo root. "
                                "Defaults to goal.md."
                            ),
                        }
                    },
                    "additionalProperties": False,
                },
            },
        ]
    }


def text_result(text: str) -> dict[str, Any]:
    """Build a text content result."""
    return {"content": [{"type": "text", "text": text}]}


def resolve_repo_relative_path(root: Path, raw_path: str) -> Path:
    """Resolve a repo-relative tool path without escaping the repository."""
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {raw_path}") from exc
    return candidate


def goal_loop_status(root: Path, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Return goal.md loop status through the canonical goal loop tool."""
    raw_goal_file = arguments.get("goal_file", "goal.md")
    if not isinstance(raw_goal_file, str) or not raw_goal_file.strip():
        raise ValueError("goal_file must be a non-empty string")
    goal_file = resolve_repo_relative_path(root, raw_goal_file)
    script = root / "tools" / "agent_tools" / "goal_loop.py"
    result = subprocess.run(
        [sys.executable, str(script), "status", "--goal-file", str(goal_file)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip()
    if result.stderr.strip():
        output = f"{output}\n{result.stderr.strip()}".strip()
    prefix = "MCP_GOAL_LOOP_TOOL=goal.loop_status"
    status_line = f"MCP_GOAL_LOOP_EXIT={result.returncode}"
    return text_result("\n".join(line for line in (prefix, status_line, output) if line))


def call_tool(name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Execute a supported tool."""
    root = repo_root()
    tool_arguments = arguments or {}
    if name == "repo.root":
        return text_result(str(root))
    if name == "repo.status":
        result = subprocess.run(
            ["git", "status", "--short", "--branch", "--untracked-files=all"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        return text_result(output)
    if name == "goal.loop_status":
        return goal_loop_status(root, tool_arguments)
    raise KeyError(name)


def handle_request(message: Mapping[str, Any]) -> None:
    """Handle one JSON-RPC request or notification."""
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return

    if method == "initialize":
        params = message.get("params")
        protocol_version = "2024-11-05"
        if isinstance(params, dict) and isinstance(params.get("protocolVersion"), str):
            protocol_version = params["protocolVersion"]
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                },
            }
        )
        return

    if method == "ping":
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
        return

    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": request_id, "result": tool_schema()})
        return

    if method == "tools/call":
        params = message.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        arguments = params.get("arguments", {}) if isinstance(params, dict) else {}
        if not isinstance(name, str):
            send_error(request_id, -32602, "tools/call requires params.name")
            return
        if not isinstance(arguments, dict):
            send_error(request_id, -32602, "tools/call params.arguments must be an object")
            return
        try:
            result = call_tool(name, arguments)
        except KeyError:
            send_error(request_id, -32602, f"unknown tool: {name}")
            return
        except ValueError as exc:
            send_error(request_id, -32602, str(exc))
            return
        send({"jsonrpc": "2.0", "id": request_id, "result": result})
        return

    if method in {"resources/list", "prompts/list"}:
        key = "resources" if method == "resources/list" else "prompts"
        send({"jsonrpc": "2.0", "id": request_id, "result": {key: []}})
        return

    send_error(request_id, -32601, f"method not found: {method}")


def send_error(request_id: Any, code: int, message: str) -> None:
    """Write one JSON-RPC error."""
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def main() -> int:
    """Run the stdio JSON-RPC loop."""
    global USE_CONTENT_LENGTH
    reader = sys.stdin.buffer
    while True:
        line = reader.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(b"content-length:"):
            USE_CONTENT_LENGTH = True
            try:
                length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                continue
            while True:
                header_line = reader.readline()
                if not header_line or header_line in {b"\n", b"\r\n"}:
                    break
            raw_message = reader.read(length)
            if not raw_message:
                break
            text = raw_message.decode("utf-8")
        else:
            text = stripped.decode("utf-8")
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            handle_request(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
