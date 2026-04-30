"""Tests for Codex project-local hook wiring."""

# @dependency-start
# responsibility Tests test codex hooks behavior.
# upstream implementation ../../.codex/config.toml enables codex_hooks
# upstream implementation ../../.codex/hooks.json declares MCP context hooks
# upstream implementation ../../.codex/hooks/mcp_session_context.sh emits hook JSON
# @dependency-end

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / ".codex" / "config.toml"
HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"
HOOK_SCRIPT = PROJECT_ROOT / ".codex" / "hooks" / "mcp_session_context.sh"


class CodexHooksTest(unittest.TestCase):
    """Validate the repo-local Codex hooks surface."""

    def test_config_enables_hooks_and_hooks_file_exists(self) -> None:
        """Codex hooks must be enabled from the project config layer."""
        config_text = CONFIG.read_text(encoding="utf-8")

        self.assertIn("[features]", config_text)
        self.assertIn("codex_hooks = true", config_text)
        self.assertTrue(HOOKS_JSON.exists())
        self.assertTrue(HOOK_SCRIPT.exists())

    def test_hooks_json_wires_mcp_context_hook(self) -> None:
        """Session and prompt hooks should point at the repo-local MCP context script."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

        session_start = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        prompt_submit = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]

        self.assertIn("mcp_session_context.sh", session_start["command"])
        self.assertIn("mcp_session_context.sh", prompt_submit["command"])
        self.assertIn("SessionStart", session_start["command"])
        self.assertIn("UserPromptSubmit", prompt_submit["command"])

    def test_mcp_context_hook_outputs_valid_additional_context(self) -> None:
        """The hook script should emit JSON Codex can add to model context."""
        result = subprocess.run(
            ["bash", str(HOOK_SCRIPT), "SessionStart"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        hook_output = payload["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "SessionStart")
        self.assertIn("repo_mcp_server", hook_output["additionalContext"])
        self.assertIn("check_mcp_inventory.py", hook_output["additionalContext"])
        self.assertIn("even when the user did not mention MCP", hook_output["additionalContext"])
        self.assertIn("prefer repo MCP tools", hook_output["additionalContext"])
        self.assertIn("status/context only", hook_output["additionalContext"])
        self.assertIn("do not repeat that limitation", hook_output["additionalContext"])
