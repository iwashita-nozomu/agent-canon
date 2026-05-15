"""Tests for Codex project-local hook wiring."""

# @dependency-start
# responsibility Tests test codex hooks behavior.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares MCP context hooks
# upstream implementation ../../.codex/hooks/mcp_session_context.sh emits hook JSON
# upstream implementation ../../.codex/hooks/helper_inventory_guard.py blocks helper inventory findings
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
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = PROJECT_ROOT / ".codex" / "config.toml"
HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"
HOOK_SCRIPT = PROJECT_ROOT / ".codex" / "hooks" / "mcp_session_context.sh"
PROMPT_SECRET_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "prompt_secret_guard.py"
GOAL_COMPLETION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "goal_completion_guard.py"
OOP_READABILITY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "oop_readability_guard.py"
HELPER_INVENTORY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "helper_inventory_guard.py"
SKILL_USAGE_LOGGER = PROJECT_ROOT / ".codex" / "hooks" / "skill_usage_logger.py"


class CodexHooksTest(unittest.TestCase):
    """Validate the repo-local Codex hooks surface."""

    def _run_oop_guard_with_changed_python(
        self,
        hook_input: str,
        *,
        analyzer_text: str | None = None,
        extra_env: dict[str, str] | None = None,
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
                env={
                    **os.environ,
                    "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path),
                    **(extra_env or {}),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
        return payload, log_entry

    def _run_oop_guard_with_preexisting_finding(
        self,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Run the OOP guard against a file whose finding already exists at HEAD."""
        analyzer_text = (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            "finding = {\n"
            "    'path': 'bad.py',\n"
            "    'language': 'python',\n"
            "    'severity': 'warn',\n"
            "    'kind': 'optional_boundary',\n"
            "    'symbol': 'helper_value',\n"
            "    'actual': 1,\n"
            "    'limit': 0,\n"
            "}\n"
            "if '--format' in sys.argv:\n"
            "    print(json.dumps({'findings': [finding]}))\n"
            "    raise SystemExit(0)\n"
            "print('OOP_READABILITY_FINDING=bad.py:1:python:warn:optional_boundary:helper_value:1>0:x')\n"
            "print('OOP_READABILITY=fail')\n"
            "raise SystemExit(1)\n"
        )
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
            analyzer.write_text(analyzer_text, encoding="utf-8")
            source = temp_root / "bad.py"
            source.write_text("def helper_value(value):\n    return value\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            source.write_text("def helper_value(value):\n    return value + 1\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "oop.jsonl"

            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "apply_patch",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path),
                    **(extra_env or {}),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            payload = (
                cast("dict[str, object]", json.loads(result.stdout))
                if result.stdout.strip()
                else {}
            )
        return payload, log_entry

    def _run_helper_guard_with_changed_python(
        self,
        hook_input: str,
        *,
        inventory_text: str,
        policy_payload: dict[str, object] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Run the helper inventory guard against one changed Python file."""
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
            inventory = temp_root / "tools" / "agent_tools" / "helper_function_inventory.py"
            inventory.parent.mkdir(parents=True)
            inventory.write_text(inventory_text, encoding="utf-8")
            if policy_payload is None:
                policy_payload = {
                    "enabled": True,
                    "baseline_ref": "HEAD",
                    "domain_limits": {
                        "main": {
                            "max_needs_user_judgment": 0,
                            "max_tool_rule_gap": 0,
                        },
                        "*": {
                            "max_needs_user_judgment": 0,
                            "max_tool_rule_gap": 0,
                        },
                    },
                }
            if policy_payload:
                policy = temp_root / "helper_inventory_guard_policy.json"
                policy.write_text(json.dumps(policy_payload), encoding="utf-8")
            source = temp_root / "changed.py"
            source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            source.write_text("def value() -> int:\n    return 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "helper.jsonl"

            result = subprocess.run(
                [sys.executable, str(HELPER_INVENTORY_GUARD)],
                cwd=temp_root,
                input=hook_input,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HELPER_INVENTORY_HOOK_LOG_PATH": str(log_path),
                    **(extra_env or {}),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            payload = (
                cast("dict[str, object]", json.loads(result.stdout))
                if result.stdout.strip()
                else {}
            )
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
        post_tool = hooks["hooks"]["PostToolUse"][0]
        post_tool_commands = [hook["command"] for hook in post_tool["hooks"]]
        stop_hooks = hooks["hooks"]["Stop"][0]["hooks"]
        stop_commands = [hook["command"] for hook in stop_hooks]

        self.assertIn("mcp_session_context.sh", session_start["command"])
        self.assertTrue(any("mcp_session_context.sh" in command for command in prompt_commands))
        self.assertTrue(any("prompt_secret_guard.py" in command for command in prompt_commands))
        self.assertTrue(any("skill_usage_logger.py" in command for command in prompt_commands))
        self.assertNotIn("PreToolUse", hooks["hooks"])
        self.assertIn("apply_patch", post_tool["matcher"])
        self.assertTrue(any("oop_readability_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("goal_completion_guard.py" in command for command in stop_commands))
        self.assertTrue(any("oop_readability_guard.py" in command for command in stop_commands))
        self.assertTrue(any("helper_inventory_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("helper_inventory_guard.py" in command for command in stop_commands))
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
        self.assertNotIn("--baseline-ref HEAD", reason)
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["mode"], "full")
        self.assertEqual(log_entry["baseline_ref"], "")
        self.assertEqual(log_entry["min_score"], 95)
        self.assertEqual(log_entry["failed_count"], 1)

    def test_oop_readability_guard_defaults_to_agentcanon_hook_result(self) -> None:
        """OOP guard should append to the AgentCanon hook result surface by default."""
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
                "#!/usr/bin/env python3\n"
                "print('OOP_READABILITY=fail')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )
            source = temp_root / "bad.py"
            source.write_text("def helper_value(value):\n    return value\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=temp_root,
                check=True,
                capture_output=True,
            )
            source.write_text("def helper_value(value):\n    return value + 1\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "apply_patch",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container"},
            )
            durable_log = (
                temp_root
                / "agents"
                / "evals"
                / "results"
                / "hook-runs"
                / "test-container"
                / "oop_readability_guard.jsonl"
            )
            durable_log_exists = durable_log.exists()
            log_entry = json.loads(durable_log.read_text(encoding="utf-8").splitlines()[0])

        self.assertIn("decision", json.loads(result.stdout))
        self.assertTrue(durable_log_exists)
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["mode"], "full")
        self.assertEqual(log_entry["hook_log_namespace"], "test-container")

    def test_oop_readability_guard_skips_payloadless_invocations(self) -> None:
        """OOP guard should not infer PostToolUse from empty stdin."""
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
                "#!/usr/bin/env python3\n"
                "print('OOP_READABILITY=fail')\n"
                "raise SystemExit(1)\n",
                encoding="utf-8",
            )
            source = temp_root / "bad.py"
            source.write_text("def helper_value(value):\n    return value\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=temp_root,
                check=True,
                capture_output=True,
            )
            source.write_text("def helper_value(value):\n    return value + 1\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "oop.jsonl"

            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input="",
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path)},
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_oop_readability_guard_ignores_payloadless_no_source_skip(self) -> None:
        """Payloadless OOP invocations with no source changes must not dirty logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "oop.jsonl"
            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input="",
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path)},
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

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
        self.assertIn("hook_run_id", log_entry)
        self.assertIn("payload_fingerprint", log_entry)
        self.assertIn("failure_fingerprint", log_entry)

    def test_oop_readability_guard_blocks_preexisting_findings_by_default(self) -> None:
        """OOP guard should block current changed-source findings by default."""
        payload, log_entry = self._run_oop_guard_with_preexisting_finding()

        self.assertEqual(payload["decision"], "block")
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["mode"], "full")
        self.assertEqual(log_entry["baseline_ref"], "")
        self.assertEqual(log_entry["failed_count"], 1)
        commands = cast(list[dict[str, object]], log_entry["commands"])
        command = commands[0]
        self.assertNotIn(
            "OOP_READABILITY_BASELINE=preexisting-only",
            str(command["output_snippet"]),
        )

    def test_oop_readability_guard_allows_preexisting_findings_in_diff_mode(self) -> None:
        """OOP guard should use baseline filtering only when explicitly requested."""
        payload, log_entry = self._run_oop_guard_with_preexisting_finding(
            extra_env={"AGENT_CANON_OOP_HOOK_MODE": "diff"}
        )

        self.assertEqual(payload, {})
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["mode"], "diff")
        self.assertEqual(log_entry["baseline_ref"], "HEAD")
        self.assertEqual(log_entry["failed_count"], 0)
        commands = cast(list[dict[str, object]], log_entry["commands"])
        command = commands[0]
        command_parts = cast(list[str], command["command"])
        self.assertIn("--baseline-ref", command_parts)
        self.assertIn("HEAD", command_parts)
        self.assertIn(
            "OOP_READABILITY_BASELINE=preexisting-only",
            str(command["output_snippet"]),
        )

    def test_oop_readability_guard_skips_read_only_bash_payloads(self) -> None:
        """Bash tool names alone should not re-run OOP checks for read-only commands."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "oop.jsonl"
            result = subprocess.run(
                [sys.executable, str(OOP_READABILITY_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "sed -n '1,20p' README.md"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path)},
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_oop_readability_guard_skips_bash_checker_invocations(self) -> None:
        """Bash commands that only run checkers should not recursively trigger OOP."""
        commands = (
            (
                "python3 /workspace/tools/oop/python/readability.py "
                "--root /workspace --min-score 95 python/pkg/module.py"
            ),
            "python3 -m pytest tests/agent_tools/test_codex_hooks.py -q",
            "python3 -m ruff check .codex/hooks/oop_readability_guard.py",
        )
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
                log_path = temp_root / "reports" / "hooks" / "oop.jsonl"
                result = subprocess.run(
                    [sys.executable, str(OOP_READABILITY_GUARD)],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path)},
                )

            self.assertEqual(result.stdout, "")
            self.assertFalse(log_path.exists())

    def test_helper_inventory_guard_blocks_repo_policy_findings(self) -> None:
        """Helper inventory guard should use repo-owned policy thresholds."""
        payload, log_entry = self._run_helper_guard_with_changed_python(
            json.dumps(
                {
                    "hookEventName": "PostToolUse",
                    "tool_name": "apply_patch",
                }
            ),
            inventory_text=(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'records': [{"
                "'path': 'changed.py', 'line': 1, 'domain': 'main', "
                "'qualname': 'value', 'needs_user_judgment': True, "
                "'judgment_rule': 'main:new-helper'}]}))\n"
            ),
        )

        self.assertEqual(payload["decision"], "block")
        reason = payload["reason"]
        if not isinstance(reason, str):
            self.fail("helper inventory guard reason must be a string")
        self.assertIn("Helper inventory hook", reason)
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["records"], 1)
        self.assertEqual(log_entry["violations"], 1)

    def test_helper_inventory_guard_uses_agentcanon_default_policy(self) -> None:
        """Missing repo-local policy should fall back to the AgentCanon default policy."""
        payload, log_entry = self._run_helper_guard_with_changed_python(
            json.dumps(
                {
                    "hookEventName": "PostToolUse",
                    "tool_name": "apply_patch",
                }
            ),
            policy_payload={},
            inventory_text=(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'records': [{"
                "'path': 'changed.py', 'line': 1, 'domain': 'main', "
                "'qualname': 'value', 'needs_user_judgment': True, "
                "'judgment_rule': 'main:new-helper'}]}))\n"
            ),
        )

        self.assertEqual(payload["decision"], "block")
        self.assertEqual(log_entry["policy_status"], "agentcanon-default")
        self.assertTrue(str(log_entry["policy_path"]).endswith("helper_inventory_guard_policy.json"))
        self.assertEqual(log_entry["mode"], "policy")
        self.assertEqual(log_entry["violations"], 1)

    def test_helper_inventory_guard_repo_policy_can_select_report_mode(self) -> None:
        """Repo-local policy may loosen the default blocking behavior explicitly."""
        payload, log_entry = self._run_helper_guard_with_changed_python(
            json.dumps(
                {
                    "hookEventName": "PostToolUse",
                    "tool_name": "apply_patch",
                }
            ),
            policy_payload={
                "enabled": True,
                "mode": "report",
            },
            inventory_text=(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'records': [{"
                "'path': 'changed.py', 'line': 1, 'domain': 'main', "
                "'qualname': 'value', 'needs_user_judgment': True, "
                "'judgment_rule': 'main:new-helper'}]}))\n"
            ),
        )

        self.assertEqual(payload, {})
        self.assertEqual(log_entry["policy_status"], "repo-local")
        self.assertEqual(log_entry["mode"], "report")
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["records"], 1)
        self.assertEqual(log_entry["violations"], 0)

    def test_helper_inventory_guard_skips_payloadless_invocations(self) -> None:
        """Helper guard should not infer PostToolUse from empty stdin."""
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
            policy = temp_root / "helper_inventory_guard_policy.json"
            policy.write_text(json.dumps({"enabled": True}), encoding="utf-8")
            source = temp_root / "changed.py"
            source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=temp_root,
                check=True,
                capture_output=True,
            )
            source.write_text("def value() -> int:\n    return 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "helper.jsonl"

            result = subprocess.run(
                [sys.executable, str(HELPER_INVENTORY_GUARD)],
                cwd=temp_root,
                input="",
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HELPER_INVENTORY_HOOK_LOG_PATH": str(log_path),
                },
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

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
        self.assertTrue(all(entry["hook_run_id"].startswith("hook-") for entry in entries))
        self.assertTrue(all(entry["payload_fingerprint"] for entry in entries))

    def test_skill_usage_logger_defaults_to_agentcanon_hook_result(self) -> None:
        """Default skill hook output should live under AgentCanon hook results."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $agent-orchestration.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container"},
            )
            log_path = (
                temp_root
                / "agents"
                / "evals"
                / "results"
                / "hook-runs"
                / "test-container"
                / "skill_usage.jsonl"
            )
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result.stdout, "")
        self.assertEqual(entries[0]["skills"], ["agent-orchestration"])
        self.assertTrue(entries[0]["hook_run_id"].startswith("hook-"))
        self.assertEqual(entries[0]["hook_log_namespace"], "test-container")

    def test_skill_usage_logger_skips_no_skill_payloads(self) -> None:
        """No-skill hook payloads should not dirty durable AgentCanon logs."""
        payloads: tuple[dict[str, object], ...] = (
            {},
            {
                "hookEventName": "UserPromptSubmit",
                "prompt": "plain text without a skill token",
            },
            {
                "hookEventName": "Stop",
                "last_assistant_message": "finished without skill declaration",
            },
        )
        for payload in payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
                log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
                result = subprocess.run(
                    [sys.executable, str(SKILL_USAGE_LOGGER)],
                    cwd=temp_root,
                    input=json.dumps(payload),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
                )

                self.assertEqual(result.stdout, "")
                self.assertFalse(log_path.exists())

    def test_skill_usage_logger_honors_results_dir_override(self) -> None:
        """Explicit overrides can route hook logs to a temporary local path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_dir = temp_root / "reports" / "hooks"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $agent-orchestration.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_RESULTS_DIR": str(log_dir),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                },
            )
            log_path = log_dir / "test-container" / "skill_usage.jsonl"
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result.stdout, "")
        self.assertEqual(entries[0]["skills"], ["agent-orchestration"])
        self.assertTrue(entries[0]["hook_run_id"].startswith("hook-"))

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
