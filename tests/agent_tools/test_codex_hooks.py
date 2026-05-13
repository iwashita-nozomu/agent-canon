"""Tests for Codex project-local hook wiring."""

# @dependency-start
# responsibility Tests test codex hooks behavior.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares MCP context hooks
# upstream implementation ../../.codex/hooks/mcp_session_context.sh emits hook JSON
# upstream implementation ../../.codex/hooks/oop_readability_guard.py logs and blocks OOP findings
# upstream implementation ../../.codex/hooks/skill_usage_logger.py logs observed skill usage
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / ".codex" / "config.toml"
HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"
HOOK_SCRIPT = PROJECT_ROOT / ".codex" / "hooks" / "mcp_session_context.sh"
PRE_TOOL_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "pre_tool_guard.py"
PROMPT_SECRET_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "prompt_secret_guard.py"
GOAL_COMPLETION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "goal_completion_guard.py"
AGENT_CANON_READ_WARNING = PROJECT_ROOT / ".codex" / "hooks" / "agent_canon_read_warning.py"
OOP_READABILITY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "oop_readability_guard.py"
SKILL_USAGE_LOGGER = PROJECT_ROOT / ".codex" / "hooks" / "skill_usage_logger.py"


class CodexHooksTest(unittest.TestCase):
    """Validate the repo-local Codex hooks surface."""

    def _run_oop_guard_with_changed_python(
        self,
        hook_input: str,
        *,
        analyzer_text: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Run the OOP guard against one changed Python file in a temp repo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=temp_root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=temp_root,
                check=True,
                capture_output=True,
            )
            analyzer = temp_root / "tools" / "oop" / "python" / "readability.py"
            analyzer.parent.mkdir(parents=True)
            analyzer.write_text(
                analyzer_text
                or "#!/usr/bin/env python3\n"
                "print('OOP_READABILITY=fail')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )
            source = temp_root / "bad.py"
            source.write_text("def helper_value(value):\n    return value\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            source.write_text("def helper_value(value):\n    return value + 1\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "oop.jsonl"

            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input=hook_input,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path)},
            )

            log_entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            payload = json.loads(result.stdout)
        return payload, log_entry

    def test_config_enables_hooks_and_hooks_file_exists(self) -> None:
        """Codex hooks must be enabled from the project config layer."""
        config_text = CONFIG.read_text(encoding="utf-8")

        self.assertIn("[features]", config_text)
        self.assertIn("hooks = true", config_text)
        self.assertNotIn("codex_hooks", config_text)
        self.assertTrue(HOOKS_JSON.exists())
        self.assertTrue(HOOK_SCRIPT.exists())

    def test_hooks_json_wires_mcp_context_hook(self) -> None:
        """Session and prompt hooks should point at the repo-local MCP context script."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

        session_start = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        prompt_hooks = hooks["hooks"]["UserPromptSubmit"][0]["hooks"]
        prompt_commands = [hook["command"] for hook in prompt_hooks]
        pre_tool = hooks["hooks"]["PreToolUse"][0]
        pre_tool_commands = [hook["command"] for hook in pre_tool["hooks"]]
        post_tool = hooks["hooks"]["PostToolUse"][0]
        post_tool_commands = [hook["command"] for hook in post_tool["hooks"]]
        stop_hooks = hooks["hooks"]["Stop"][0]["hooks"]
        stop_commands = [hook["command"] for hook in stop_hooks]

        self.assertIn("mcp_session_context.sh", session_start["command"])
        self.assertTrue(any("mcp_session_context.sh" in command for command in prompt_commands))
        self.assertTrue(any("prompt_secret_guard.py" in command for command in prompt_commands))
        self.assertTrue(any("skill_usage_logger.py" in command for command in prompt_commands))
        self.assertEqual(pre_tool["matcher"], "Bash")
        self.assertTrue(any("pre_tool_guard.py" in command for command in pre_tool_commands))
        self.assertTrue(any("agent_canon_read_warning.py" in command for command in pre_tool_commands))
        self.assertIn("apply_patch", post_tool["matcher"])
        self.assertTrue(any("oop_readability_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("goal_completion_guard.py" in command for command in stop_commands))
        self.assertTrue(any("oop_readability_guard.py" in command for command in stop_commands))
        self.assertTrue(any("skill_usage_logger.py" in command for command in stop_commands))
        self.assertIn("SessionStart", session_start["command"])
        self.assertTrue(any("UserPromptSubmit" in command for command in prompt_commands))

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
        self.assertIn("goal.loop_status", hook_output["additionalContext"])
        self.assertIn("NEXT_ACTION=run_next_iteration", hook_output["additionalContext"])
        self.assertIn("context/loop-status only", hook_output["additionalContext"])
        self.assertIn("do not repeat that limitation", hook_output["additionalContext"])

    def test_pre_tool_guard_blocks_destructive_git_reset(self) -> None:
        """The pre-tool guard should deny clearly destructive Bash commands."""
        result = subprocess.run(
            [sys.executable, str(PRE_TOOL_GUARD)],
            cwd=PROJECT_ROOT,
            input=json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git reset --hard HEAD"},
                }
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        hook_output = payload["hookSpecificOutput"]

        self.assertEqual(hook_output["hookEventName"], "PreToolUse")
        self.assertEqual(hook_output["permissionDecision"], "deny")
        self.assertIn("git reset --hard", hook_output["permissionDecisionReason"])

    def test_agent_canon_read_warning_warns_without_blocking(self) -> None:
        """The read-warning hook should warn when reading shared AgentCanon paths."""
        result = subprocess.run(
            [sys.executable, str(AGENT_CANON_READ_WARNING)],
            cwd=PROJECT_ROOT,
            input=json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "sed -n '1,40p' vendor/agent-canon/codex-cli-guide/README.md"},
                }
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertIn("systemMessage", payload)
        self.assertIn("shared canon", payload["systemMessage"])
        self.assertIn("do not make Docker/devcontainer build logic depend", payload["systemMessage"])

    def test_prompt_secret_guard_blocks_obvious_api_key(self) -> None:
        """The prompt guard should block high-confidence secret patterns."""
        result = subprocess.run(
            [sys.executable, str(PROMPT_SECRET_GUARD)],
            cwd=PROJECT_ROOT,
            input=json.dumps(
                {
                    "hookEventName": "UserPromptSubmit",
                    "prompt": "please use sk-abcdefghijklmnopqrstuvwxyz1234567890",
                }
            ),
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["decision"], "block")
        self.assertIn("API key", payload["reason"])

    def test_goal_completion_guard_blocks_active_goal_completion(self) -> None:
        """Stop hook should continue when a completion-like answer races active goal state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            goal_loop = temp_root / "tools" / "agent_tools" / "goal_loop.py"
            goal_loop.parent.mkdir(parents=True)
            (temp_root / "goal.md").write_text("# Goal\n", encoding="utf-8")
            goal_loop.write_text(
                "print('NEXT_ACTION=run_next_iteration')\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(GOAL_COMPLETION_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "修正しました。完了です。",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
            )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["decision"], "block")
        self.assertIn("NEXT_ACTION=run_next_iteration", payload["reason"])

    def test_oop_readability_guard_blocks_changed_python_findings(self) -> None:
        """OOP guard should block after source edits when changed Python fails."""
        payload, log_entry = self._run_oop_guard_with_changed_python(
            json.dumps(
                {
                    "hookEventName": "PostToolUse",
                    "tool_name": "apply_patch",
                }
            ),
            analyzer_text=(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "if sys.argv[sys.argv.index('--min-score') + 1] != '95':\n"
                "    raise SystemExit(0)\n"
                "print('OOP_READABILITY=fail')\n"
                "raise SystemExit(1)\n"
            ),
        )
        self.assertEqual(payload["decision"], "block")
        reason = payload["reason"]
        if not isinstance(reason, str):
            self.fail("OOP guard reason must be a string")
        self.assertIn("OOP readability hook", reason)
        self.assertIn("--min-score 95", reason)
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["min_score"], 95)
        self.assertEqual(log_entry["failed_count"], 1)

    def test_oop_readability_guard_checks_payloadless_invocations(self) -> None:
        """OOP guard should still run when a runtime calls the hook without stdin."""
        payload, log_entry = self._run_oop_guard_with_changed_python("")
        self.assertEqual(payload["decision"], "block")
        reason = payload["reason"]
        if not isinstance(reason, str):
            self.fail("OOP guard reason must be a string")
        self.assertIn("OOP readability hook", reason)
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertEqual(log_entry["tool_name"], "Bash")
        self.assertEqual(log_entry["payload_status"], "empty")
        self.assertTrue(log_entry["payload_fallback"])
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["failed_count"], 1)

    def test_oop_readability_guard_infers_post_tool_event_when_event_missing(self) -> None:
        """OOP guard should run when tool payloads omit hookEventName."""
        payload, log_entry = self._run_oop_guard_with_changed_python(
            json.dumps({"tool_name": "apply_patch"})
        )
        self.assertEqual(payload["decision"], "block")
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertEqual(log_entry["tool_name"], "apply_patch")
        self.assertEqual(log_entry["payload_status"], "valid")
        self.assertTrue(log_entry["event_fallback"])
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["failed_count"], 1)

    def test_skill_usage_logger_writes_prompt_and_stop_logs(self) -> None:
        """Skill usage hook should append local JSONL records when skills are observed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            env = {**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)}

            prompt = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $agent-orchestration and skills=$python-review,$dependency-analysis",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            stop = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "workflow=Scoped Change skills=$change-review",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            shell_text = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Check $PATH but use $skill-creator only if needed.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            entries = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(prompt.stdout, "")
        self.assertEqual(stop.stdout, "")
        self.assertEqual(shell_text.stdout, "")
        self.assertEqual(entries[0]["event"], "UserPromptSubmit")
        self.assertEqual(
            entries[0]["skills"],
            ["agent-orchestration", "dependency-analysis", "python-review"],
        )
        self.assertEqual(entries[1]["event"], "Stop")
        self.assertEqual(entries[1]["skills"], ["change-review"])
        self.assertEqual(entries[2]["skills"], ["skill-creator"])

    def test_skill_usage_logger_records_workflow_monitor_events_when_report_dir_is_set(self) -> None:
        """Skill usage hook should reuse workflow_monitor.py for run-bundle evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports" / "agents" / "run-1"
            log_path = root / "reports" / "hooks" / "skills.jsonl"
            env = {
                **os.environ,
                "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(report_dir),
            }

            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $agent-orchestration.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["workflow_monitor_event_count"], 1)
        self.assertIn(
            "skill_invocation=$agent-orchestration status=observed source=codex_hook",
            monitoring,
        )
