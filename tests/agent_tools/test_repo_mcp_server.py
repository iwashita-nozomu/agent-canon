# @dependency-start
# responsibility Tests repo MCP server behavior.
# upstream implementation ../../mcp/repo_mcp_server.py exposes repo MCP tools
# upstream implementation ../../tools/agent_tools/goal_loop.py provides loop status
# @dependency-end
"""Tests for the repo-local MCP server."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER = PROJECT_ROOT / "mcp" / "repo_mcp_server.py"


def load_server() -> ModuleType:
    """Load the MCP server module from its file path."""
    spec = importlib.util.spec_from_file_location("repo_mcp_server_test", SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load repo_mcp_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepoMcpServerTest(unittest.TestCase):
    """Verify repo MCP tool behavior."""

    def test_goal_loop_status_tool_reports_next_action(self) -> None:
        """The MCP server should expose goal.md loop state for adaptive loops."""
        server = load_server()
        old_root = os.environ.get("CODEX_WORKSPACE_ROOT")
        os.environ["CODEX_WORKSPACE_ROOT"] = str(PROJECT_ROOT)
        try:
            result = server.call_tool("goal.loop_status", {"goal_file": "goal.md"})
        finally:
            if old_root is None:
                os.environ.pop("CODEX_WORKSPACE_ROOT", None)
            else:
                os.environ["CODEX_WORKSPACE_ROOT"] = old_root

        text = result["content"][0]["text"]
        self.assertIn("MCP_GOAL_LOOP_TOOL=goal.loop_status", text)
        self.assertIn("GOAL_LOOP_STATUS=", text)
        self.assertIn("NEXT_ACTION=", text)

    def test_goal_loop_status_rejects_paths_outside_repo(self) -> None:
        """The MCP goal tool must not inspect files outside the repository root."""
        server = load_server()

        with self.assertRaises(ValueError):
            server.call_tool("goal.loop_status", {"goal_file": "../goal.md"})


if __name__ == "__main__":
    unittest.main()
