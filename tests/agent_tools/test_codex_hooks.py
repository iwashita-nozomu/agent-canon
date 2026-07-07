"""Tests for Codex project-local hook wiring."""

# @dependency-start
# contract test
# responsibility Tests test codex hooks behavior.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares active guardrail hooks
# upstream implementation ../../.codex/hooks/helper_inventory_guard.py blocks helper inventory findings
# upstream implementation ../../.codex/hooks/module_boundary_guard.py blocks forced module rewrites
# upstream implementation ../../.codex/hooks/library_implementation_guard.py blocks library implementation rewrites
# upstream implementation ../../.codex/hooks/first_party_library_guard.py blocks first-party API rewrites
# upstream implementation ../../.codex/hooks/task_authority_schema_guard.py validates task authority
# upstream implementation ../../.codex/hooks/role_write_policy_guard.py enforces role write policy
# upstream implementation ../../.codex/hooks/helper_first_guard.py blocks helper-first implementation drift
# upstream implementation ../../.codex/hooks/cause_investigation_guard.py blocks code edits without cause evidence
# upstream implementation ../../.codex/hooks/notebook_quality_guard.py blocks notebook quality findings
# upstream implementation ../../.codex/hooks/oop_readability_guard.py logs and warns on OOP findings
# upstream implementation ../../.codex/hooks/log_surface_inventory_guard.py blocks log surface drift
# upstream implementation ../../.codex/hooks/style_checker_guard.py logs style checker coverage
# upstream implementation ../../.codex/hooks/skill_usage_logger.py logs observed skill usage
# upstream implementation ../../.codex/hooks/codex_runtime_summary_logger.py exports bounded Codex runtime summaries
# upstream implementation ../../.codex/hooks/runtime_log_auto_sync.py runs unattended runtime log archive sync
# upstream implementation ../../.codex/hooks/log_archive_mount_warning.py warns when log archive is not mounted
# upstream implementation ../../.codex/hooks/branch_worktree_guard.py blocks unconfirmed branch/worktree creation
# upstream implementation ../../.codex/hooks/direct_rg_context_guard.py warns on context-polluting direct rg usage
# upstream implementation ../../.codex/hooks/reference_capture_guard.py logs reference capture coverage
# upstream implementation ../../.codex/hooks/hook_dispatcher.py dispatches hook events and skips read-only GitStatus checks
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

from tools.agent_tools.runtime_log_paths import (
    CODEX_TRACE_ENV_NAMES,
    mounted_log_archive_root,
    repo_log_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG = PROJECT_ROOT / ".codex" / "config.toml"
HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"
HOOK_DISPATCHER = PROJECT_ROOT / ".codex" / "hooks" / "hook_dispatcher.py"
PROMPT_SECRET_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "prompt_secret_guard.py"
GOAL_COMPLETION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "goal_completion_guard.py"
OOP_READABILITY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "oop_readability_guard.py"
HELPER_INVENTORY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "helper_inventory_guard.py"
MODULE_BOUNDARY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "module_boundary_guard.py"
LIBRARY_IMPLEMENTATION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "library_implementation_guard.py"
FIRST_PARTY_LIBRARY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "first_party_library_guard.py"
HELPER_FIRST_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "helper_first_guard.py"
TASK_AUTHORITY_SCHEMA_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "task_authority_schema_guard.py"
ROLE_WRITE_POLICY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "role_write_policy_guard.py"
CAUSE_INVESTIGATION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "cause_investigation_guard.py"
LOG_SURFACE_INVENTORY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "log_surface_inventory_guard.py"
NOTEBOOK_QUALITY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "notebook_quality_guard.py"
STYLE_CHECKER_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "style_checker_guard.py"
SKILL_USAGE_LOGGER = PROJECT_ROOT / ".codex" / "hooks" / "skill_usage_logger.py"
CODEX_RUNTIME_SUMMARY_LOGGER = PROJECT_ROOT / ".codex" / "hooks" / "codex_runtime_summary_logger.py"
RUNTIME_LOG_AUTO_SYNC = PROJECT_ROOT / ".codex" / "hooks" / "runtime_log_auto_sync.py"
LOG_ARCHIVE_MOUNT_WARNING = PROJECT_ROOT / ".codex" / "hooks" / "log_archive_mount_warning.py"
BRANCH_WORKTREE_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "branch_worktree_guard.py"
DIRECT_RG_CONTEXT_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "direct_rg_context_guard.py"
REFERENCE_CAPTURE_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "reference_capture_guard.py"
NOTEBOOK_MAJOR_VERSION = 4
NOTEBOOK_MINOR_VERSION = 5
OOP_READABILITY_MIN_SCORE = 95
EXPECTED_PROMPT_FEEDBACK_MIN = 3
EXPECTED_HOOK_EVENT_COUNT = 4


def write_sha256_baseline(path: Path, baseline_path: Path) -> None:
    """Write a test baseline sidecar for a runtime authority file."""
    baseline_path.write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n", encoding="utf-8")


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
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
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
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
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

    def _notebook_payload(self, source: str) -> str:
        """Return one minimal notebook document."""
        return json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": "# Demo\n\nReadable notebook narrative for users.",
                    },
                    {
                        "cell_type": "code",
                        "execution_count": 1,
                        "metadata": {},
                        "outputs": [],
                        "source": source,
                    },
                ],
                "metadata": {},
                "nbformat": NOTEBOOK_MAJOR_VERSION,
                "nbformat_minor": NOTEBOOK_MINOR_VERSION,
            }
        )

    def _run_notebook_guard_with_changed_notebook(
        self,
        source: str,
        hook_input: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Run notebook guard against one changed notebook in a temp repo."""
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
            checker = temp_root / "tools" / "validation" / "notebook_quality.py"
            checker.parent.mkdir(parents=True)
            checker.write_text(
                (PROJECT_ROOT / "tools" / "validation" / "notebook_quality.py").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            notebook_path = temp_root / "jupyter" / "demo.ipynb"
            notebook_path.parent.mkdir()
            notebook_path.write_text(
                self._notebook_payload(
                    "import matplotlib.pyplot as plt\nplt.plot([0], [0])\nplt.show()"
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            notebook_path.write_text(self._notebook_payload(source), encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "notebook.jsonl"

            result = subprocess.run(
                [sys.executable, str(NOTEBOOK_QUALITY_GUARD)],
                cwd=temp_root,
                input=hook_input,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
        return payload, log_entry

    def test_config_enables_hooks_and_hooks_file_exists(self) -> None:
        """Codex hooks must be enabled from the project config layer."""
        config_text = CONFIG.read_text(encoding="utf-8")

        self.assertIn("[features]", config_text)
        self.assertIn("hooks = true", config_text)
        self.assertNotIn("codex_hooks", config_text)
        self.assertTrue(HOOKS_JSON.exists())
        self.assertTrue(HOOK_DISPATCHER.exists())
        self.assertTrue(CODEX_RUNTIME_SUMMARY_LOGGER.exists())
        self.assertTrue(RUNTIME_LOG_AUTO_SYNC.exists())
        self.assertTrue(DIRECT_RG_CONTEXT_GUARD.exists())

    def test_hooks_json_uses_codex_supported_top_level_keys(self) -> None:
        """Codex hook configuration should keep only runtime-supported top-level keys."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

        self.assertEqual(set(hooks), {"hooks"})
        self.assertIsInstance(hooks["hooks"], dict)

    def _dispatcher_scripts(self, event: str) -> list[str]:
        """Return the child hook scripts configured for one dispatcher event."""
        result = subprocess.run(
            [sys.executable, str(HOOK_DISPATCHER), "--list", event],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = cast("dict[str, object]", json.loads(result.stdout))
        events = cast("dict[str, list[dict[str, object]]]", payload["events"])
        return [cast(str, row["script"]) for row in events[event]]

    def test_hooks_json_does_not_wire_mcp_context_hook(self) -> None:
        """MCP context is not a startup hook; active hooks stay guardrail-only."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

        session_start_hooks = hooks["hooks"].get("SessionStart", [])
        session_start_commands = [
            hook["command"]
            for group in session_start_hooks
            for hook in group.get("hooks", [])
        ]
        prompt_hooks = hooks["hooks"]["UserPromptSubmit"][0]["hooks"]
        prompt_commands = [hook["command"] for hook in prompt_hooks]
        pre_tool = hooks["hooks"]["PreToolUse"][0]
        pre_tool_commands = [hook["command"] for hook in pre_tool["hooks"]]
        post_tool = hooks["hooks"]["PostToolUse"][0]
        post_tool_commands = [hook["command"] for hook in post_tool["hooks"]]
        stop_hooks = hooks["hooks"]["Stop"][0]["hooks"]
        stop_commands = [hook["command"] for hook in stop_hooks]
        prompt_scripts = self._dispatcher_scripts("UserPromptSubmit")
        pre_tool_scripts = self._dispatcher_scripts("PreToolUse")
        post_tool_scripts = self._dispatcher_scripts("PostToolUse")
        stop_scripts = self._dispatcher_scripts("Stop")

        self.assertFalse(
            any("mcp_session_context.sh" in command for command in session_start_commands)
        )
        self.assertFalse(any("mcp_session_context.sh" in command for command in prompt_commands))
        self.assertEqual(len(prompt_commands), 1)
        self.assertIn("hook_dispatcher.py", prompt_commands[0])
        self.assertEqual(
            prompt_scripts,
            [
                "log_archive_mount_warning.py",
                "prompt_secret_guard.py",
                "skill_usage_logger.py",
                "reference_capture_guard.py",
            ],
        )
        self.assertIn("apply_patch", pre_tool["matcher"])
        self.assertEqual(len(pre_tool_commands), 1)
        self.assertIn("hook_dispatcher.py", pre_tool_commands[0])
        self.assertEqual(
            pre_tool_scripts,
            [
                "log_archive_mount_warning.py",
                "branch_worktree_guard.py",
                "direct_rg_context_guard.py",
                "cause_investigation_guard.py",
            ],
        )
        self.assertIn("apply_patch", post_tool["matcher"])
        self.assertIn("spawn_agent", post_tool["matcher"])
        self.assertIn("close_agent", post_tool["matcher"])
        self.assertEqual(len(post_tool_commands), 1)
        self.assertIn("hook_dispatcher.py", post_tool_commands[0])
        self.assertEqual(
            post_tool_scripts,
            [
                "skill_usage_logger.py",
                "reference_capture_guard.py",
                "task_authority_schema_guard.py",
                "role_write_policy_guard.py",
                "oop_readability_guard.py",
                "module_boundary_guard.py",
                "library_implementation_guard.py",
                "first_party_library_guard.py",
                "helper_inventory_guard.py",
                "helper_first_guard.py",
                "style_checker_guard.py",
                "log_surface_inventory_guard.py",
                "notebook_quality_guard.py",
            ],
        )
        self.assertEqual(len(stop_commands), 1)
        self.assertIn("hook_dispatcher.py", stop_commands[0])
        self.assertEqual(
            stop_scripts,
            [
                "goal_completion_guard.py",
                "task_authority_schema_guard.py",
                "role_write_policy_guard.py",
                "oop_readability_guard.py",
                "module_boundary_guard.py",
                "library_implementation_guard.py",
                "first_party_library_guard.py",
                "helper_inventory_guard.py",
                "helper_first_guard.py",
                "style_checker_guard.py",
                "log_surface_inventory_guard.py",
                "notebook_quality_guard.py",
                "reference_capture_guard.py",
                "skill_usage_logger.py",
                "codex_runtime_summary_logger.py",
                "runtime_log_auto_sync.py",
            ],
        )

    def test_log_archive_mount_warning_is_non_blocking_when_missing(self) -> None:
        """Missing log archive mount should warn without blocking the hook chain."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir) / "agent-canon"
            canon_root.mkdir()

            result = subprocess.run(
                [sys.executable, str(LOG_ARCHIVE_MOUNT_WARNING)],
                cwd=canon_root,
                input=json.dumps({"hookEventName": "UserPromptSubmit"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_LOG_ARCHIVE_WARNING_CANON_ROOT": str(canon_root),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))

        self.assertEqual(payload["decision"], "approve")
        self.assertIn("LOG_ARCHIVE_MOUNT_STATUS=missing", cast(str, payload["reason"]))
        self.assertEqual(
            payload["next_action"],
            "ensure_agent_canon_log_archive_mount_before_accumulating_logs",
        )

    def test_log_archive_mount_warning_is_quiet_when_mounted(self) -> None:
        """Mounted archive clone should produce no visible hook output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir) / "agent-canon"
            archive_git = mounted_log_archive_root(canon_root) / ".git"
            archive_git.mkdir(parents=True)

            result = subprocess.run(
                [sys.executable, str(LOG_ARCHIVE_MOUNT_WARNING)],
                cwd=canon_root,
                input=json.dumps({"hookEventName": "UserPromptSubmit"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_LOG_ARCHIVE_WARNING_CANON_ROOT": str(canon_root),
                },
            )

        self.assertEqual(result.stdout, "")

    def test_skill_usage_logger_routes_validation_failure_prompts(self) -> None:
        """Hook routing should classify validation failures as repair-owner work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": (
                            "failed validation; do not delete tests or weaken "
                            "oracle before repairing the failing contract"
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])
            candidate_workflows = cast("list[str]", entry["candidate_workflows"])
            candidate_skill_reasons = cast("list[str]", entry["candidate_skill_reasons"])

        self.assertEqual(result.stdout, "")
        self.assertIn("codex-task-workflow", candidate_skills)
        self.assertIn("test-design", candidate_skills)
        self.assertLess(
            candidate_skills.index("codex-task-workflow"),
            candidate_skills.index("test-design"),
        )
        self.assertIn("codex-task-workflow", candidate_workflows)
        self.assertTrue(
            any(
                "tests_are=validation_control_surface_not_default_work_owner"
                in reason
                for reason in candidate_skill_reasons
            )
        )
        self.assertIn("test-design:related_to=codex-task-workflow", candidate_skill_reasons)

    def test_skill_usage_logger_filters_reasons_for_declared_skills(self) -> None:
        """Candidate reasons should describe only final candidate_skills."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": (
                            "Use $codex-task-workflow for a validation failure; "
                            "do not delete tests or weaken the oracle."
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])
            candidate_skill_reasons = cast("list[str]", entry["candidate_skill_reasons"])
            selected_skills = cast("list[str]", entry["skills"])

        self.assertEqual(result.stdout, "")
        self.assertIn("codex-task-workflow", selected_skills)
        self.assertNotIn("codex-task-workflow", candidate_skills)
        self.assertTrue(
            all(
                reason.split(":", 1)[0] in candidate_skills
                for reason in candidate_skill_reasons
            )
        )

    def test_skill_usage_logger_routes_oracle_spec_mismatch_prompts(self) -> None:
        """Hook routing should still classify genuine test oracle design work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "The test oracle has a spec mismatch; fix test design.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])

        self.assertEqual(result.stdout, "")
        self.assertIn("test-design", candidate_skills)

    def test_skill_usage_logger_reuses_catalog_for_user_guided_debugging(self) -> None:
        """Hook prompt candidates should follow route.py catalog skill routing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": (
                            "Use user-guided refactor cadence: show one concrete issue, "
                            "patch only that target, and do not run validation unless I ask."
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])
            candidate_skill_reasons = cast("list[str]", entry["candidate_skill_reasons"])

        self.assertEqual(result.stdout, "")
        self.assertIn("user-guided-debugging", candidate_skills)
        self.assertTrue(
            any(
                reason.startswith("user-guided-debugging:")
                for reason in candidate_skill_reasons
            )
        )

    def test_skill_usage_logger_routes_parent_repo_skill_lane_prompts(self) -> None:
        """Hook routing should classify parent-repo-specific skill lane design."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "親レポに固有スキルを置けるようにする設計修正",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])
            candidate_skill_reasons = cast("list[str]", entry["candidate_skill_reasons"])

        self.assertEqual(result.stdout, "")
        self.assertIn("task-routing", candidate_skills)
        self.assertIn("structure-refactor", candidate_skills)
        self.assertTrue(
            any(
                "task-routing:structural_concept=parent_repo_project_skill_lane"
                in reason
                for reason in candidate_skill_reasons
            )
        )
        self.assertTrue(
            any(
                "structure-refactor:structural_concept=parent_repo_project_skill_lane"
                in reason
                for reason in candidate_skill_reasons
            )
        )

    def test_skill_usage_logger_advisory_prompt_does_not_log_base_candidates(
        self,
    ) -> None:
        """Routing-only advisory prompts should not report default runtime skills."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "skill_usage.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Which route contract applies for this repository task?",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )
            candidate_skills = cast("list[str]", entry["candidate_skills"])

        self.assertEqual(result.stdout, "")
        self.assertIn("task-routing", candidate_skills)
        self.assertNotIn("agent-orchestration", candidate_skills)
        self.assertNotIn("codex-task-workflow", candidate_skills)

    def test_runtime_log_auto_sync_is_fail_open_by_default(self) -> None:
        """Auto-sync hook should not block or emit context when archive sync fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "missing-canon"
            source_root.mkdir()
            subprocess.run(["git", "init"], cwd=source_root, check=True, capture_output=True)

            result = subprocess.run(
                [sys.executable, str(RUNTIME_LOG_AUTO_SYNC)],
                cwd=source_root,
                input=json.dumps({"hookEventName": "Stop"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_RUNTIME_LOG_AUTO_SYNC_CANON_ROOT": str(canon_root),
                },
            )

        self.assertEqual(result.stdout, "")

    def test_hooks_json_command_counts_contract(self) -> None:
        """Active hook configuration should stay collapsed to one command per event."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        counts = {
            event: sum(len(group.get("hooks", [])) for group in groups)
            for event, groups in hooks["hooks"].items()
        }
        commands_by_event = {
            event: [
                hook["command"]
                for group in groups
                for hook in group.get("hooks", [])
            ]
            for event, groups in hooks["hooks"].items()
        }

        self.assertEqual(
            counts,
            {
                "UserPromptSubmit": 1,
                "PreToolUse": 1,
                "PostToolUse": 1,
                "Stop": 1,
            },
        )
        self.assertEqual(sum(counts.values()), EXPECTED_HOOK_EVENT_COUNT)
        for event, commands in commands_by_event.items():
            self.assertEqual(len(commands), len(set(commands)), event)
            self.assertTrue(all("hook_dispatcher.py" in command for command in commands))

    def test_hook_dispatcher_runs_all_children_and_returns_first_block(self) -> None:
        """Dispatcher should preserve order while still giving every child a log chance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            child_payloads = {
                "log_archive_mount_warning.py": None,
                "prompt_secret_guard.py": {"decision": "block", "reason": "first block"},
                "skill_usage_logger.py": None,
                "reference_capture_guard.py": {"decision": "block", "reason": "later block"},
            }
            for script_name, output_payload in child_payloads.items():
                output_json = json.dumps(output_payload) if output_payload else ""
                (hook_dir / script_name).write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            "import os",
                            "import sys",
                            f"script_name = {script_name!r}",
                            "payload = sys.stdin.read()",
                            "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                            "    stream.write(f'{script_name}:{len(payload)}\\n')",
                            f"output = {output_json!r}",
                            "if output:",
                            "    print(output)",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "UserPromptSubmit"],
                cwd=temp_root,
                input="payload-data",
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            invocations = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(payload["decision"], "block")
        self.assertEqual(payload["reason"], "first block")
        self.assertEqual(
            invocations,
            [
                "log_archive_mount_warning.py:12",
                "prompt_secret_guard.py:12",
                "skill_usage_logger.py:12",
                "reference_capture_guard.py:12",
            ],
        )

    def test_hook_dispatcher_promotes_trace_alias_to_child_thread_env(self) -> None:
        """Dispatcher should make trace aliases available to child hooks."""
        cases: tuple[tuple[str, dict[str, object], dict[str, str], str], ...] = (
            ("payload_thread", {"thread_id": "thread-from-payload"}, {}, "thread-from-payload"),
            ("payload_session", {"session_id": "session-from-payload"}, {}, "session-from-payload"),
            (
                "payload_conversation",
                {"conversation_id": "conversation-from-payload"},
                {},
                "conversation-from-payload",
            ),
            ("env_session", {}, {"CODEX_SESSION_ID": "session-from-env"}, "session-from-env"),
            (
                "env_thread_wins",
                {"session_id": "session-from-payload"},
                {"CODEX_THREAD_ID": "thread-from-env"},
                "thread-from-env",
            ),
        )
        for label, payload_extra, env_extra, expected_trace in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                hook_dir = temp_root / "hooks"
                hook_dir.mkdir()
                log_path = temp_root / "trace-env.txt"
                for script_name in (
                    "log_archive_mount_warning.py",
                    "prompt_secret_guard.py",
                    "skill_usage_logger.py",
                    "reference_capture_guard.py",
                ):
                    (hook_dir / script_name).write_text(
                        "\n".join(
                            [
                                "#!/usr/bin/env python3",
                                "import os",
                                f"script_name = {script_name!r}",
                                "trace = os.environ.get('CODEX_THREAD_ID', '')",
                                "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                                "    stream.write(f'{script_name}:{trace}\\n')",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                child_env = {
                    key: value
                    for key, value in os.environ.items()
                    if key not in CODEX_TRACE_ENV_NAMES
                }
                child_env.update(
                    {
                        "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                        "HOOK_DISPATCH_TEST_LOG": str(log_path),
                        **env_extra,
                    }
                )

                result = subprocess.run(
                    [sys.executable, str(HOOK_DISPATCHER), "UserPromptSubmit"],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "UserPromptSubmit",
                            "prompt": "Use $agent-orchestration.",
                            **payload_extra,
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env=child_env,
                )
                invocations = log_path.read_text(encoding="utf-8").splitlines()

            self.assertEqual(result.stdout, "")
            self.assertEqual(
                invocations,
                [
                    f"log_archive_mount_warning.py:{expected_trace}",
                    f"prompt_secret_guard.py:{expected_trace}",
                    f"skill_usage_logger.py:{expected_trace}",
                    f"reference_capture_guard.py:{expected_trace}",
                ],
            )

    def test_hook_dispatcher_downgrades_noncritical_child_blocks(self) -> None:
        """Dispatcher should keep non-secret guard findings from stopping work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            child_payloads = {
                "log_archive_mount_warning.py": None,
                "prompt_secret_guard.py": None,
                "skill_usage_logger.py": None,
                "reference_capture_guard.py": {
                    "decision": "block",
                    "reason": "missing reference registration",
                    "remediation": ["register the reference"],
                },
            }
            for script_name, output_payload in child_payloads.items():
                output_json = json.dumps(output_payload) if output_payload else ""
                (hook_dir / script_name).write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            f"output = {output_json!r}",
                            "if output:",
                            "    print(output)",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "UserPromptSubmit"],
                cwd=temp_root,
                input="payload-data",
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))

        self.assertNotIn("decision", payload)
        self.assertEqual(payload["next_action"], "address_guardrail_finding_before_closeout")
        self.assertIn("downgraded it to a warning", cast(str, payload["systemMessage"]))
        self.assertIn("reference_capture_guard.py", cast(str, payload["systemMessage"]))
        self.assertIn("register the reference", cast("list[str]", payload["remediation"]))

    def test_hook_dispatcher_preserves_branch_worktree_guard_blocks(self) -> None:
        """Dispatcher should preserve the branch/worktree creation stop."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            for script_name in (
                "log_archive_mount_warning.py",
                "branch_worktree_guard.py",
                "direct_rg_context_guard.py",
                "cause_investigation_guard.py",
            ):
                output = (
                    {"decision": "block", "reason": "branch worktree stop"}
                    if script_name == "branch_worktree_guard.py"
                    else None
                )
                output_json = json.dumps(output) if output else ""
                (hook_dir / script_name).write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            f"output = {output_json!r}",
                            "if output:",
                            "    print(output)",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PreToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "git switch -c topic"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                },
            )

        payload = cast("dict[str, object]", json.loads(result.stdout))
        self.assertEqual(payload["decision"], "block")
        self.assertEqual(payload["reason"], "branch worktree stop")

    def test_hook_dispatcher_child_launch_failure_warns_after_later_hooks(self) -> None:
        """Dispatcher should fail open on child hook failures after later hooks run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            (hook_dir / "skill_usage_logger.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "import sys",
                        "payload = sys.stdin.read()",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write(f'skill_usage_logger.py:{len(payload)}\\n')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (hook_dir / "reference_capture_guard.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "import sys",
                        "payload = sys.stdin.read()",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write(f'reference_capture_guard.py:{len(payload)}\\n')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "UserPromptSubmit"],
                cwd=temp_root,
                input="payload-data",
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            invocations = log_path.read_text(encoding="utf-8").splitlines()

        self.assertNotIn("decision", payload)
        self.assertIn("hookSpecificOutput", payload)
        self.assertIn("log_archive_mount_warning.py", cast(str, payload["systemMessage"]))
        hook_output = cast("dict[str, object]", payload["hookSpecificOutput"])
        self.assertEqual(hook_output["hookEventName"], "UserPromptSubmit")
        self.assertIn(
            "fail-open by default",
            cast(str, hook_output["additionalContext"]),
        )
        self.assertEqual(
            invocations,
            [
                "skill_usage_logger.py:12",
                "reference_capture_guard.py:12",
            ],
        )

    def test_hook_dispatcher_post_tool_failure_is_quiet(self) -> None:
        """Verify PostToolUse fail-open diagnostics do not emit schema-sensitive stdout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            for script_name in self._dispatcher_scripts("PostToolUse"):
                body = (
                    "raise SystemExit(2)\n"
                    if script_name == "skill_usage_logger.py"
                    else ""
                )
                (hook_dir / script_name).write_text(
                    "\n".join(["#!/usr/bin/env python3", body]),
                    encoding="utf-8",
                )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PostToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {"patch": "*** Begin Patch\n*** End Patch\n"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                },
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_hook_dispatcher_combines_non_blocking_visible_outputs(self) -> None:
        """Dispatcher should not drop later non-blocking child diagnostics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            outputs = {
                "log_archive_mount_warning.py": "",
                "prompt_secret_guard.py": {
                    "decision": "approve",
                    "reason": "first warning",
                    "next_action": "first_action",
                    "remediation": ["first remediation"],
                },
                "skill_usage_logger.py": "plain diagnostic",
                "reference_capture_guard.py": "",
            }
            for script_name, output_payload in outputs.items():
                if isinstance(output_payload, dict):
                    output_text = json.dumps(output_payload)
                else:
                    output_text = output_payload
                (hook_dir / script_name).write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            f"output = {output_text!r}",
                            "if output:",
                            "    print(output)",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "UserPromptSubmit"],
                cwd=temp_root,
                input="payload-data",
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))

        self.assertNotIn("decision", payload)
        self.assertIn("hookSpecificOutput", payload)
        self.assertEqual(payload["child_output_count"], 2)
        self.assertIn("first warning", cast(str, payload["systemMessage"]))
        self.assertIn("plain diagnostic", cast(str, payload["systemMessage"]))
        self.assertEqual(payload["next_action"], "first_action")

    def test_hook_dispatcher_skips_git_status_tool_payloads(self) -> None:
        """GitStatus-style tool checks should not run blocking hook children."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            (hook_dir / "cause_investigation_guard.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write('called\\n')",
                        "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PreToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "GitStatus",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_hook_dispatcher_skips_read_only_git_status_bash_commands(self) -> None:
        """Read-only git status Bash commands should not trigger blocking children."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            (hook_dir / "skill_usage_logger.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write('called\\n')",
                        "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PostToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {
                            "cmd": "git -C vendor/agent-canon status --short --branch --untracked-files=all",
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_branch_worktree_guard_blocks_unconfirmed_creation(self) -> None:
        """Branch and worktree creation should require explicit route evidence."""
        commands = [
            "git switch -c topic/one",
            "git switch -ctopic/one-short",
            "git checkout -b topic/two",
            "git checkout -btopic/two-short",
            "git branch topic/three",
            "git branch -f topic/force main",
            "git branch --force topic/long-force main",
            "git -C vendor/agent-canon switch -C topic/four",
            "bash -lc 'git worktree add ../topic topic/five'",
            "git worktree add ../topic topic/six",
            "git worktree -v add ../topic topic/seven",
        ]
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(BRANCH_WORKTREE_GUARD)],
                    cwd=PROJECT_ROOT,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                )

                payload = cast("dict[str, object]", json.loads(result.stdout))
                self.assertEqual(payload["decision"], "block")
                self.assertIn("BRANCH_WORKTREE_CREATION_GUARD=block", cast(str, payload["reason"]))
                self.assertEqual(
                    payload["next_action"],
                    "reuse_current_checkout_or_record_branch_worktree_reason",
                )

    def test_branch_worktree_guard_allows_diagnostics_and_confirmed_creation(self) -> None:
        """Branch/worktree diagnostics and confirmed creation should stay quiet."""
        cases: list[tuple[str, dict[str, str]]] = [
            ("git branch --show-current", {}),
            ("git branch --list topic/*", {}),
            ("git branch -D topic/stale", {}),
            ("git branch -m topic/old topic/new", {}),
            ("git worktree list --porcelain", {}),
        ]
        for command, extra_env in cases:
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(BRANCH_WORKTREE_GUARD)],
                    cwd=PROJECT_ROOT,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={**os.environ, **extra_env},
                )

                self.assertEqual(result.stdout, "")

    def test_branch_worktree_guard_blocks_missing_authority(self) -> None:
        """A reason without authority should still block creation."""
        result = subprocess.run(
            [sys.executable, str(BRANCH_WORKTREE_GUARD)],
            cwd=PROJECT_ROOT,
            input=json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"cmd": "git switch -c topic/missing-authority"},
                }
            ),
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "AGENT_CANON_BRANCH_WORKTREE_REASON": "workflow-internal branch request",
            },
        )

        payload = cast("dict[str, object]", json.loads(result.stdout))
        self.assertEqual(payload["decision"], "block")

    def test_branch_worktree_guard_allows_authorized_creation(self) -> None:
        """Authorized branch creation should require route authority and reason."""
        cases: list[tuple[str, dict[str, str]]] = [
            (
                "git switch -c topic/confirmed",
                {
                    "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
                    "AGENT_CANON_BRANCH_WORKTREE_REASON": "explicit user branch request",
                },
            ),
            (
                "git switch -c agent-canon/update-route",
                {
                    "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "agent_canon_workflow",
                    "AGENT_CANON_BRANCH_WORKTREE_REASON": "AgentCanon branch PR workflow",
                },
            ),
        ]
        for command, extra_env in cases:
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(BRANCH_WORKTREE_GUARD)],
                    cwd=PROJECT_ROOT,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={**os.environ, **extra_env},
                )

                self.assertEqual(result.stdout, "")

    def test_direct_rg_context_guard_warns_on_broad_line_search(self) -> None:
        """Broad `rg -n` should warn before dumping repository matches."""
        commands = [
            "rg -n duplicate .",
            "bash -lc 'rg -n duplicate .'",
            "true && rg -n duplicate .",
        ]
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(DIRECT_RG_CONTEXT_GUARD)],
                    cwd=PROJECT_ROOT,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                )

                payload = cast("dict[str, object]", json.loads(result.stdout))
                self.assertEqual(payload["decision"], "approve")
                self.assertIn("DIRECT_RG_CONTEXT_RISK=warn", cast(str, payload["reason"]))
                self.assertEqual(
                    payload["next_action"],
                    "replace_broad_rg_with_bounded_or_compact_search",
                )

    def test_direct_rg_context_guard_allows_compact_and_bounded_searches(self) -> None:
        """Compact discovery or bounded file searches should stay quiet."""
        commands = [
            "rg -l duplicate agents/skills",
            "rg -n duplicate agents/skills",
            "rg -n duplicate agents/skills/agent-orchestration.md",
            "rg -n duplicate ./agents/skills/agent-orchestration.md",
            "bash -lc 'rg -n duplicate agents/skills/agent-orchestration.md'",
            "rg --files",
            "rg -n --max-count 20 duplicate .",
            "rg -n duplicate . -g '!reports/**' -g '!.agent-canon/log-archive/**' -g '!*.jsonl'",
        ]
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    [sys.executable, str(DIRECT_RG_CONTEXT_GUARD)],
                    cwd=PROJECT_ROOT,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.stdout, "")

    def test_hook_dispatcher_surfaces_direct_rg_warning(self) -> None:
        """Dispatcher should not bypass risky direct rg commands."""
        result = subprocess.run(
            [sys.executable, str(HOOK_DISPATCHER), "PreToolUse"],
            cwd=PROJECT_ROOT,
            input=json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"cmd": "rg -n duplicate ."},
                }
            ),
            check=True,
            capture_output=True,
            text=True,
        )

        payload = cast("dict[str, object]", json.loads(result.stdout))
        self.assertIn("DIRECT_RG_CONTEXT_RISK=warn", cast(str, payload["systemMessage"]))
        self.assertIn("hookSpecificOutput", payload)

    def test_hook_dispatcher_skips_git_push_tool_payloads(self) -> None:
        """GitPush-style publish tools should not run blocking hook children."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            (hook_dir / "cause_investigation_guard.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write('called\\n')",
                        "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PreToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "GitPush",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_hook_dispatcher_skips_github_publish_commands(self) -> None:
        """Gh PR and github_publish.py commands are publish work, not hook-stop points."""
        commands = [
            "git push -u origin topic",
            "gh pr create --repo owner/repo --base main --head topic --title T --body-file body.md",
            "python3 tools/agent_tools/github_publish.py publish-pr --user-task task --repo owner/repo --title T --body-file body.md",
        ]
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                hook_dir = temp_root / "hooks"
                hook_dir.mkdir()
                log_path = temp_root / "invocations.txt"
                (hook_dir / "style_checker_guard.py").write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            "import os",
                            "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                            "    stream.write('called\\n')",
                            "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [sys.executable, str(HOOK_DISPATCHER), "PostToolUse"],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "PostToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                        "HOOK_DISPATCH_TEST_LOG": str(log_path),
                    },
                )

                self.assertEqual(result.stdout, "")
                self.assertFalse(log_path.exists())

    def test_hook_dispatcher_skips_read_only_file_inspection_commands(self) -> None:
        """Read-only file inspection should not require disabling hook config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            hook_dir = temp_root / "hooks"
            hook_dir.mkdir()
            log_path = temp_root / "invocations.txt"
            (hook_dir / "skill_usage_logger.py").write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import os",
                        "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                        "    stream.write('called\\n')",
                        "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(HOOK_DISPATCHER), "PostToolUse"],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "sed -n '1,120p' .codex/hooks.json"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                    "HOOK_DISPATCH_TEST_LOG": str(log_path),
                },
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())

    def test_hook_dispatcher_skips_validation_commands(self) -> None:
        """Validation commands should not be blocked by post-tool hook children."""
        commands = [
            "python3 -m pytest tests/agent_tools/test_codex_hooks.py -q",
            "python3 tools/agent_tools/runtime_log_archive_git.py check-clean",
            "python3 tools/agent_tools/runtime_log_archive_git.py --source-root . --canon-root vendor/agent-canon status --porcelain",
            "bash tools/agent_tools/runtime_log_archive_git.py --source-root . repo-key",
            "bash tools/ci/check_agent_canon_latest.sh",
            "bash tools/update_agent_canon.sh plan",
            "bash tools/sync_agent_canon.sh status",
            "make agent-canon-latest-check agent-surface-checks",
        ]
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                hook_dir = temp_root / "hooks"
                hook_dir.mkdir()
                log_path = temp_root / "invocations.txt"
                (hook_dir / "style_checker_guard.py").write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            "import os",
                            "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                            "    stream.write('called\\n')",
                            "print('{\"decision\":\"block\",\"reason\":\"should not run\"}')",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [sys.executable, str(HOOK_DISPATCHER), "PostToolUse"],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "PostToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                        "HOOK_DISPATCH_TEST_LOG": str(log_path),
                    },
                )

                self.assertEqual(result.stdout, "")
                self.assertFalse(log_path.exists())

    def test_hook_dispatcher_runs_children_for_mutating_lookalikes(self) -> None:
        """Write-capable lookalikes should not use the read-only bypass."""
        commands = [
            "cat AGENTS.md > /tmp/out",
            "sed -ni '1,120p' .codex/hooks.json",
            "sed --in-place=.bak -n '1,120p' .codex/hooks.json",
            "git branch -D main",
            "git branch --list --delete main",
            "git switch -c topic/one",
            "git switch -ctopic/one-short",
            "git checkout -b topic/two",
            "git checkout -btopic/two-short",
            "git worktree add ../topic topic/three",
            "git worktree -v add ../topic topic/four",
            "git remote add x y",
            "git diff --output=/tmp/out",
            "git diff -o/tmp/out",
            "make ci deploy",
            "bash tools/update_agent_canon.sh latest",
            "bash tools/update_agent_canon.sh merge-main-into-current",
            "bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty",
            "bash tools/sync_agent_canon.sh ensure-latest",
            "bash tools/sync_agent_canon.sh link-root",
            "python3 tools/agent_tools/runtime_log_archive_git.py ensure",
            "python3 tools/agent_tools/runtime_log_archive_git.py sync",
            "bash tools/agent_tools/runtime_log_archive_git.py archive-agent-reports",
        ]
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                hook_dir = temp_root / "hooks"
                hook_dir.mkdir()
                log_path = temp_root / "invocations.txt"
                (hook_dir / "cause_investigation_guard.py").write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env python3",
                            "import os",
                            "with open(os.environ['HOOK_DISPATCH_TEST_LOG'], 'a', encoding='utf-8') as stream:",
                            "    stream.write('called\\n')",
                            "print('{\"decision\":\"block\",\"reason\":\"child ran\"}')",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [sys.executable, str(HOOK_DISPATCHER), "PreToolUse"],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "AGENT_CANON_HOOK_DISPATCHER_DIR": str(hook_dir),
                        "HOOK_DISPATCH_TEST_LOG": str(log_path),
                    },
                )

                self.assertIn("child ran", result.stdout)
                self.assertEqual(log_path.read_text(encoding="utf-8"), "called\n")

    def test_style_checker_guard_logs_markdown_and_unchecked_files(self) -> None:
        """Style hook should select Markdown checks and log changed files without a checker."""
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
            bin_dir = temp_root / "tools" / "bin"
            bin_dir.mkdir(parents=True)
            agent_canon = bin_dir / "agent-canon"
            agent_canon.write_text(
                "#!/usr/bin/env sh\n"
                "echo STYLE_TEST_CHECKER_OK=\"$*\"\n",
                encoding="utf-8",
            )
            agent_canon.chmod(0o755)
            readme = temp_root / "README.md"
            data = temp_root / "data.lock"
            root_jsonl = temp_root / "runtime.jsonl"
            hook_jsonl = temp_root / "agents" / "evals" / "results" / "hook-runs" / "run" / "hook.jsonl"
            readme.write_text("# Title\n\nInitial text.\n", encoding="utf-8")
            data.write_text("initial\n", encoding="utf-8")
            root_jsonl.write_text('{"event": "initial"}\n', encoding="utf-8")
            hook_jsonl.parent.mkdir(parents=True)
            hook_jsonl.write_text('{"event": "initial"}\n', encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            readme.write_text("# Title\n\nChanged text.\n", encoding="utf-8")
            data.write_text("changed\n", encoding="utf-8")
            root_jsonl.write_text('{"event": "changed"}\n', encoding="utf-8")
            hook_jsonl.write_text('{"event": "changed"}\n', encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "style.jsonl"

            result = subprocess.run(
                [sys.executable, str(STYLE_CHECKER_GUARD)],
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
                    "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH": str(log_path),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["selected_checkers"], ["agent_canon_docs_check"])
        self.assertEqual(log_entry["unchecked_count"], 1)
        self.assertEqual(
            cast("list[dict[str, object]]", log_entry["unchecked_files"])[0]["paths"],
            ["data.lock"],
        )

    def test_style_checker_guard_routes_generated_codex_guide_to_split_validator(self) -> None:
        """Generated Codex guide Markdown should use split validation, not prose lint."""
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
            bin_dir = temp_root / "tools" / "bin"
            bin_dir.mkdir(parents=True)
            agent_canon = bin_dir / "agent-canon"
            agent_canon.write_text("#!/usr/bin/env sh\nexit 99\n", encoding="utf-8")
            agent_canon.chmod(0o755)
            validator = temp_root / "codex-cli-guide" / "tools" / "validate_split.py"
            validator.parent.mkdir(parents=True)
            validator.write_text(
                "#!/usr/bin/env python3\nprint('split validation passed')\n",
                encoding="utf-8",
            )
            section = (
                temp_root
                / "codex-cli-guide"
                / "sections"
                / "08-additional-configuration-recipes-114-253.md"
            )
            section.parent.mkdir(parents=True)
            section.write_text("# Generated section\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            section.write_text("# Generated section\n\nChanged.\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "style.jsonl"

            result = subprocess.run(
                [sys.executable, str(STYLE_CHECKER_GUARD)],
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
                    "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH": str(log_path),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["selected_checkers"], ["codex_cli_guide_split"])
        self.assertEqual(log_entry["unchecked_count"], 0)

    def test_module_boundary_guard_blocks_public_surface_change_without_evidence(self) -> None:
        """Module hook should block forced module rewrites without tests or docs."""
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
            self._write_module_boundary_fixture(temp_root)
            module = temp_root / "app" / "module.py"
            module.parent.mkdir()
            module.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("def renamed() -> int:\n    return 1\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "module.jsonl"

            result = subprocess.run(
                [sys.executable, str(MODULE_BOUNDARY_GUARD)],
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
                    "AGENT_CANON_MODULE_BOUNDARY_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("public-surface-change-without-evidence", "\n".join(cast("list[str]", payload["findings"])))
        self.assertIn("next_action", payload)
        self.assertIn("remediation", payload)
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["changed_module_count"], 1)

    def test_module_boundary_guard_blocks_import_responsibility_failure(self) -> None:
        """Module hook should surface import responsibility failures immediately."""
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
            self._write_module_boundary_fixture(temp_root)
            module = temp_root / "app" / "module.py"
            module.parent.mkdir()
            module.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("import sys\n\nVALUE = 1\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "module.jsonl"

            result = subprocess.run(
                [sys.executable, str(MODULE_BOUNDARY_GUARD)],
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
                    "AGENT_CANON_MODULE_BOUNDARY_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("IMPORT_RESPONSIBILITY_FINDING=unused-import", "\n".join(cast("list[str]", payload["findings"])))
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(cast("list[dict[str, object]]", log_entry["import_checks"])[0]["returncode"], 1)

    def _write_module_boundary_fixture(self, root: Path) -> None:
        """Write fixture files needed by the module boundary hook."""
        checker = root / "tools" / "agent_tools" / "import_responsibility.py"
        checker.parent.mkdir(parents=True)
        checker.write_text(
            (PROJECT_ROOT / "tools" / "agent_tools" / "import_responsibility.py").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        (root / "responsibility-scope.toml").write_text(
            "\n".join(
                [
                    'catalog_kind = "agent_canon_responsibility_scope"',
                    "version = 1",
                    "[[scope]]",
                    'id = "app"',
                    'paths = ["app/**"]',
                    "",
                    "[[scope]]",
                    'id = "tools"',
                    'paths = ["tools/**"]',
                    "",
                    "[[import_rule]]",
                    'source = "app"',
                    'targets = ["app"]',
                    "",
                    "[[import_rule]]",
                    'source = "tools"',
                    'targets = ["tools", "app"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_library_implementation_guard_blocks_vendor_rewrite(self) -> None:
        """Library guard should block direct rewrites under vendored dependency paths."""
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
            library_file = temp_root / "vendor" / "thirdparty" / "lib.py"
            library_file.parent.mkdir(parents=True)
            library_file.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            library_file.write_text("def value() -> int:\n    return 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "library.jsonl"

            result = subprocess.run(
                [sys.executable, str(LIBRARY_IMPLEMENTATION_GUARD)],
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
                    "AGENT_CANON_LIBRARY_IMPLEMENTATION_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("library-implementation-rewrite", "\n".join(cast("list[str]", payload["findings"])))
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["changed_library_file_count"], 1)

    def test_task_authority_schema_guard_blocks_invalid_authority_payload(self) -> None:
        """Task authority schema guard should reject malformed authority files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            module = temp_root / "app.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("VALUE = 2\n", encoding="utf-8")
            authority = temp_root / "reports" / "agents" / "run-1" / "task_authority.yaml"
            authority.parent.mkdir(parents=True)
            authority.write_text("version: 2\nallowed_paths: {}\nroles: []\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "authority.jsonl"

            result = subprocess.run(
                [sys.executable, str(TASK_AUTHORITY_SCHEMA_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(payload["decision"], "block")
        self.assertIn("TASK_AUTHORITY_FINDING=invalid-version", "\n".join(cast("list[str]", payload["findings"])))
        self.assertIn("next_action", payload)
        self.assertEqual(log_entry["status"], "fail")

    def test_task_authority_schema_guard_allows_valid_authority_schema(self) -> None:
        """Task authority schema guard should accept a valid schema."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            module = temp_root / "app.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            authority = temp_root / "reports" / "agents" / "run-1" / "task_authority.yaml"
            authority.parent.mkdir(parents=True)
            authority.write_text(
                "version: 1\n"
                "run_id: run-1\n"
                "active_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n"
                "  - path: app.py\n"
                "    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities:\n"
                "  helper_change: []\n"
                "  first_party_library_change: []\n"
                "  public_api_change: []\n"
                "  workflow_change: []\n"
                "  shared_canon_change: []\n"
                "roles:\n"
                "  implementer:\n"
                "    can_modify_repo: true\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("VALUE = 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "authority.jsonl"

            result = subprocess.run(
                [sys.executable, str(TASK_AUTHORITY_SCHEMA_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH": str(log_path),
                },
            )
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")

    def test_role_write_policy_guard_blocks_artifact_only_repo_edit(self) -> None:
        """Role write policy guard should block artifact-only roles editing repo files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            module = temp_root / "app.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            report_dir = temp_root / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            authority = report_dir / "task_authority.yaml"
            authority.write_text(
                "version: 1\nrun_id: run-1\nactive_role: change_reviewer\n"
                "request_clauses: []\nallowed_paths: []\nforbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {change_reviewer: {can_modify_repo: false}}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("VALUE = 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "role.jsonl"

            result = subprocess.run(
                [sys.executable, str(ROLE_WRITE_POLICY_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(log_path),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(payload["decision"], "block")
        self.assertIn("write-scope-violation", "\n".join(cast("list[str]", payload["findings"])))
        self.assertNotIn("WORKTREE_SCOPE", "\n".join(cast("list[str]", payload["remediation"])))
        self.assertEqual(log_entry["status"], "fail")

    def test_role_write_policy_guard_allows_implementer_allowed_path_without_scope_file(
        self,
    ) -> None:
        """Implementer writes should use task authority paths, not WORKTREE_SCOPE.md."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            module = temp_root / "app.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            report_dir = temp_root / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            authority = report_dir / "task_authority.yaml"
            authority.write_text(
                "version: 1\n"
                "run_id: run-1\n"
                "active_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n"
                "  - path: app.py\n"
                "    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {implementer: {can_modify_repo: true}}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("VALUE = 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "role.jsonl"

            result = subprocess.run(
                [sys.executable, str(ROLE_WRITE_POLICY_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(log_path),
                },
            )
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")

    def test_role_write_policy_guard_blocks_implementer_outside_allowed_paths(
        self,
    ) -> None:
        """Task authority allowed_paths should be an active runtime write boundary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            module = temp_root / "app.py"
            module.write_text("VALUE = 1\n", encoding="utf-8")
            other = temp_root / "other.py"
            other.write_text("VALUE = 1\n", encoding="utf-8")
            report_dir = temp_root / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            authority = report_dir / "task_authority.yaml"
            authority.write_text(
                "version: 1\n"
                "run_id: run-1\n"
                "active_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n"
                "  - path: app.py\n"
                "    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {implementer: {can_modify_repo: true}}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            other.write_text("VALUE = 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "role.jsonl"

            result = subprocess.run(
                [sys.executable, str(ROLE_WRITE_POLICY_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(log_path),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(payload["decision"], "block")
        self.assertIn(
            "task-authority-path-violation",
            "\n".join(cast("list[str]", payload["findings"])),
        )
        self.assertEqual(log_entry["status"], "fail")

    def test_authority_guards_block_self_expansion_with_repo_edit(self) -> None:
        """Authority edits cannot authorize repo edits in the same hook cycle."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            (temp_root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            other = temp_root / "other.py"
            other.write_text("VALUE = 1\n", encoding="utf-8")
            report_root = temp_root / "reports" / "agents"
            report_dir = report_root / "run-1"
            report_dir.mkdir(parents=True)
            (report_root / ".active_run").write_text("reports/agents/run-1\n", encoding="utf-8")
            authority = report_dir / "task_authority.yaml"
            base_authority = (
                "version: 1\nrun_id: run-1\nactive_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n  - path: app.py\n    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {implementer: {can_modify_repo: true}}\n"
            )
            authority.write_text(base_authority, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            authority.write_text(
                base_authority.replace("allowed_paths:\n", "allowed_paths:\n  - path: other.py\n    actions: [modify]\n"),
                encoding="utf-8",
            )
            other.write_text("VALUE = 2\n", encoding="utf-8")
            hook_env = dict(os.environ)
            hook_env.pop("AGENT_CANON_TASK_AUTHORITY", None)

            for hook_script, log_name in (
                (TASK_AUTHORITY_SCHEMA_GUARD, "authority.jsonl"),
                (ROLE_WRITE_POLICY_GUARD, "role.jsonl"),
            ):
                result = subprocess.run(
                    [sys.executable, str(hook_script)],
                    cwd=temp_root,
                    input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **hook_env,
                        "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                        "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                    },
                )
                payload = cast("dict[str, object]", json.loads(result.stdout))
                self.assertEqual(payload["decision"], "block")
                self.assertIn(
                    "authority-mutated-with-repo-edit",
                    "\n".join(cast("list[str]", payload["findings"])),
                )

    def test_authority_guards_block_ignored_authority_self_expansion(self) -> None:
        """Ignored run-bundle authority edits cannot authorize repo edits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            (temp_root / ".gitignore").write_text("reports/agents/\nreports/hooks/\n", encoding="utf-8")
            (temp_root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            other = temp_root / "other.py"
            other.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)

            report_root = temp_root / "reports" / "agents"
            report_dir = report_root / "run-1"
            report_dir.mkdir(parents=True)
            active_pointer = report_root / ".active_run"
            active_pointer.write_text("reports/agents/run-1\n", encoding="utf-8")
            authority = report_dir / "task_authority.yaml"
            base_authority = (
                "version: 1\nrun_id: run-1\nactive_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n  - path: app.py\n    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {implementer: {can_modify_repo: true}}\n"
            )
            authority.write_text(base_authority, encoding="utf-8")
            write_sha256_baseline(active_pointer, report_root / ".active_run.sha256")
            write_sha256_baseline(authority, report_dir / "task_authority.yaml.sha256")
            authority.write_text(
                base_authority.replace("allowed_paths:\n", "allowed_paths:\n  - path: other.py\n    actions: [modify]\n"),
                encoding="utf-8",
            )
            other.write_text("VALUE = 2\n", encoding="utf-8")
            hook_env = dict(os.environ)
            hook_env.pop("AGENT_CANON_TASK_AUTHORITY", None)

            for hook_script, log_name in (
                (TASK_AUTHORITY_SCHEMA_GUARD, "authority.jsonl"),
                (ROLE_WRITE_POLICY_GUARD, "role.jsonl"),
            ):
                result = subprocess.run(
                    [sys.executable, str(hook_script)],
                    cwd=temp_root,
                    input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **hook_env,
                        "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                        "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                    },
                )
                payload = cast("dict[str, object]", json.loads(result.stdout))
                self.assertEqual(payload["decision"], "block")
                self.assertIn(
                    "authority-mutated-with-repo-edit",
                    "\n".join(cast("list[str]", payload["findings"])),
                )

    def test_authority_guards_block_active_run_pointer_self_expansion(self) -> None:
        """Ignored active-run pointer edits cannot be paired with repo edits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            (temp_root / ".gitignore").write_text("reports/agents/\nreports/hooks/\n", encoding="utf-8")
            app = temp_root / "app.py"
            app.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)

            report_root = temp_root / "reports" / "agents"
            report_dir = report_root / "run-1"
            report_dir.mkdir(parents=True)
            active_pointer = report_root / ".active_run"
            active_pointer.write_text("reports/agents/run-1\n", encoding="utf-8")
            (report_dir / "task_authority.yaml").write_text(
                "version: 1\nrun_id: run-1\nactive_role: implementer\n"
                "request_clauses: []\n"
                "allowed_paths:\n  - path: app.py\n    actions: [modify]\n"
                "forbidden_paths: []\n"
                "risky_authorities: {helper_change: [], first_party_library_change: [], public_api_change: [], workflow_change: [], shared_canon_change: []}\n"
                "roles: {implementer: {can_modify_repo: true}}\n",
                encoding="utf-8",
            )
            write_sha256_baseline(active_pointer, report_root / ".active_run.sha256")
            active_pointer.write_text("reports/agents/run-2\n", encoding="utf-8")
            app.write_text("VALUE = 2\n", encoding="utf-8")
            hook_env = dict(os.environ)
            hook_env.pop("AGENT_CANON_TASK_AUTHORITY", None)

            for hook_script, log_name in (
                (TASK_AUTHORITY_SCHEMA_GUARD, "authority.jsonl"),
                (ROLE_WRITE_POLICY_GUARD, "role.jsonl"),
            ):
                result = subprocess.run(
                    [sys.executable, str(hook_script)],
                    cwd=temp_root,
                    input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **hook_env,
                        "AGENT_CANON_TASK_AUTHORITY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                        "AGENT_CANON_ROLE_WRITE_POLICY_HOOK_LOG_PATH": str(temp_root / "reports" / "hooks" / log_name),
                    },
                )
                payload = cast("dict[str, object]", json.loads(result.stdout))
                self.assertEqual(payload["decision"], "block")
                self.assertIn(
                    "active-run-pointer-mutated-with-repo-edit",
                    "\n".join(cast("list[str]", payload["findings"])),
                )

    def test_first_party_library_guard_blocks_api_rewrite_without_authority(self) -> None:
        """First-party guard should block reusable API edits without task authority."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            api = temp_root / "python" / "pkg" / "api.py"
            api.parent.mkdir(parents=True)
            api.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            (temp_root / "responsibility-scope.toml").write_text(
                'catalog_kind = "agent_canon_responsibility_scope"\n'
                "version = 1\n"
                "[[scope]]\n"
                'id = "product-python"\n'
                'owner = "derived-project"\n'
                'class = "tooling"\n'
                'paths = ["python/**"]\n',
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            api.write_text("def value() -> int:\n    return 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "first-party.jsonl"

            result = subprocess.run(
                [sys.executable, str(FIRST_PARTY_LIBRARY_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_FIRST_PARTY_LIBRARY_HOOK_LOG_PATH": str(log_path),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        self.assertEqual(payload["decision"], "block")
        self.assertIn("first-party-library-change-without-authority", "\n".join(cast("list[str]", payload["findings"])))
        self.assertEqual(log_entry["status"], "fail")

    def test_first_party_library_guard_reports_malformed_scope_manifest(self) -> None:
        """First-party guard should report malformed scope manifests instead of crashing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=temp_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_root, check=True)
            api = temp_root / "python" / "pkg" / "api.py"
            api.parent.mkdir(parents=True)
            api.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
            (temp_root / "responsibility-scope.toml").write_text("[[scope]\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            api.write_text("def value() -> int:\n    return 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "first-party.jsonl"

            result = subprocess.run(
                [sys.executable, str(FIRST_PARTY_LIBRARY_GUARD)],
                cwd=temp_root,
                input=json.dumps({"hookEventName": "PostToolUse", "tool_name": "apply_patch"}),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_TASK_AUTHORITY": "",
                    "AGENT_CANON_FIRST_PARTY_LIBRARY_HOOK_LOG_PATH": str(log_path),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast("dict[str, object]", json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]))

        rendered = "\n".join(cast("list[str]", payload["findings"]))
        self.assertEqual(payload["decision"], "block")
        self.assertIn("first-party-manifest-parse-error", rendered)
        self.assertIn("first-party-library-change-without-authority", rendered)
        self.assertEqual(log_entry["status"], "fail")

    def test_cause_investigation_guard_blocks_code_edit_without_evidence(self) -> None:
        """Cause guard should block code edits before cause evidence exists."""
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
            (temp_root / "app").mkdir()
            (temp_root / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "cause.jsonl"

            result = subprocess.run(
                [sys.executable, str(CAUSE_INVESTIGATION_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "patch": (
                                "*** Begin Patch\n"
                                "*** Update File: app/module.py\n"
                                "@@\n"
                                "-VALUE = 1\n"
                                "+VALUE = 2\n"
                                "*** End Patch\n"
                            )
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH": str(log_path),
                },
            )
            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("CAUSE_INVESTIGATION_FINDING=", "\n".join(cast("list[str]", payload["findings"])))
        self.assertIn(
            "VALIDATION_FAILURE_CAUSE_CLASSIFICATION_REQUIRED=",
            "\n".join(cast("list[str]", payload["findings"])),
        )
        self.assertIn("failing_contract", json.dumps(payload))
        self.assertIn("intent_preservation", json.dumps(payload))
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["hook_log_namespace"], "test-container")
        self.assertTrue(log_entry["code_edit_detected"])
        self.assertEqual(log_entry["cause_evidence_status"], "fail")

    def test_cause_investigation_guard_allows_code_edit_with_evidence(self) -> None:
        """Cause guard should accept code edits when cause evidence is already recorded."""
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
            (temp_root / "app").mkdir()
            (temp_root / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            evidence = temp_root / "reports" / "agents" / "run-1" / "cause_investigation.md"
            evidence.parent.mkdir(parents=True)
            evidence.write_text(
                "Observation: app/module.py returns stale value.\n"
                "Hypothesis: app/module.py owns the value constant.\n"
                "Expected Fix Surface: app/module.py\n"
                "Validation Before Edit: run unit smoke after edit.\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "cause.jsonl"

            result = subprocess.run(
                [sys.executable, str(CAUSE_INVESTIGATION_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "patch": (
                                "*** Begin Patch\n"
                                "*** Update File: app/module.py\n"
                                "@@\n"
                                "-VALUE = 1\n"
                                "+VALUE = 2\n"
                                "*** End Patch\n"
                            )
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH": str(log_path),
                },
            )
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["hook_log_namespace"], "test-container")
        self.assertTrue(log_entry["code_edit_detected"])
        self.assertEqual(log_entry["cause_evidence_status"], "pass")

    def test_cause_investigation_guard_prioritizes_cause_evidence_over_many_logs(self) -> None:
        """Cause guard should not drop task cause evidence when many run logs exist."""
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
            (temp_root / "app").mkdir()
            (temp_root / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            for index in range(60):
                work_log = temp_root / "reports" / "agents" / f"run-{index:02d}" / "work_log.md"
                work_log.parent.mkdir(parents=True)
                work_log.write_text(f"# Work Log {index}\n", encoding="utf-8")
            evidence = temp_root / "reports" / "agents" / "run-current" / "cause_investigation.md"
            evidence.parent.mkdir(parents=True)
            evidence.write_text(
                "Observation: app/module.py returns stale value.\n"
                "Hypothesis: app/module.py owns the value constant.\n"
                "Expected Fix Surface: app/module.py\n"
                "Validation Before Edit: run unit smoke after edit.\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "cause.jsonl"

            result = subprocess.run(
                [sys.executable, str(CAUSE_INVESTIGATION_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "patch": (
                                "*** Begin Patch\n"
                                "*** Update File: app/module.py\n"
                                "@@\n"
                                "-VALUE = 1\n"
                                "+VALUE = 2\n"
                                "*** End Patch\n"
                            )
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH": str(log_path),
                },
            )
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["cause_evidence_status"], "pass")
        evidence_files = cast("list[dict[str, object]]", log_entry["cause_evidence_files"])
        self.assertTrue(
            any(file["path"] == "reports/agents/run-current/cause_investigation.md" for file in evidence_files)
        )

    def test_cause_investigation_guard_uses_only_active_workflow_monitoring(self) -> None:
        """Cause guard should not treat stale run workflow logs as current evidence."""
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
            (temp_root / "app").mkdir()
            (temp_root / "app" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            stale = temp_root / "reports" / "agents" / "run-old" / "workflow_monitoring.md"
            stale.parent.mkdir(parents=True)
            stale.write_text(
                "Observation: app/module.py returns stale value.\n"
                "Hypothesis: app/module.py owns the value constant.\n"
                "Expected Fix Surface: app/module.py\n"
                "Validation Before Edit: old run evidence must not authorize new edits.\n",
                encoding="utf-8",
            )
            active = temp_root / "reports" / "agents" / "run-current" / "workflow_monitoring.md"
            active.parent.mkdir(parents=True)
            active.write_text(
                "Observation: app/module.py returns stale value.\n"
                "Hypothesis: app/module.py owns the value constant.\n"
                "Expected Fix Surface: app/module.py\n"
                "Validation Before Edit: run unit smoke after edit.\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "cause.jsonl"

            result = subprocess.run(
                [sys.executable, str(CAUSE_INVESTIGATION_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PreToolUse",
                        "tool_name": "apply_patch",
                        "tool_input": {
                            "patch": (
                                "*** Begin Patch\n"
                                "*** Update File: app/module.py\n"
                                "@@\n"
                                "-VALUE = 1\n"
                                "+VALUE = 2\n"
                                "*** End Patch\n"
                            )
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(active.parent),
                    "AGENT_CANON_CAUSE_INVESTIGATION_HOOK_LOG_PATH": str(log_path),
                },
            )
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        evidence_files = cast("list[dict[str, object]]", log_entry["cause_evidence_files"])
        self.assertTrue(
            any(file["path"] == "reports/agents/run-current/workflow_monitoring.md" for file in evidence_files)
        )
        self.assertFalse(
            any(file["path"] == "reports/agents/run-old/workflow_monitoring.md" for file in evidence_files)
        )

    def test_helper_first_guard_blocks_helper_without_boundary_evidence(self) -> None:
        """Helper-first guard should block helper-like additions before ownership evidence."""
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
            inventory.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'records': [{"
                "'path': 'app/module.py', 'line': 1, 'kind': 'function', "
                "'domain': 'main', 'qualname': '_format_value', "
                "'helper_candidate': True, 'role': 'formatter_reporter', "
                "'candidate_rule': 'main:private-local-formatter_reporter', "
                "'incoming_count': 0, 'specialization': 'no_internal_call_sites'}]}))\n",
                encoding="utf-8",
            )
            module = temp_root / "app" / "module.py"
            module.parent.mkdir()
            module.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("def _format_value(value: int) -> str:\n    return str(value)\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "helper-first.jsonl"

            result = subprocess.run(
                [sys.executable, str(HELPER_FIRST_GUARD)],
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
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("HELPER_FIRST_FINDING=", "\n".join(cast("list[str]", payload["findings"])))
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["hook_log_namespace"], "test-container")
        self.assertEqual(log_entry["helper_candidate_record_count"], 1)
        self.assertEqual(log_entry["helper_first_candidate_count"], 1)
        self.assertFalse(log_entry["boundary_evidence_changed"])

    def test_helper_first_guard_logs_candidates_with_boundary_evidence(self) -> None:
        """Helper-first guard should record candidates while accepting boundary evidence."""
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
            inventory.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'records': [{"
                "'path': 'app/module.py', 'line': 1, 'kind': 'function', "
                "'domain': 'main', 'qualname': '_format_value', "
                "'helper_candidate': True, 'role': 'formatter_reporter', "
                "'candidate_rule': 'main:private-local-formatter_reporter', "
                "'incoming_count': 0, 'specialization': 'no_internal_call_sites'}]}))\n",
                encoding="utf-8",
            )
            module = temp_root / "app" / "module.py"
            module.parent.mkdir()
            module.write_text("VALUE = 1\n", encoding="utf-8")
            doc = temp_root / "documents" / "module-boundary.md"
            doc.parent.mkdir()
            doc.write_text("boundary evidence\n", encoding="utf-8")
            authority = temp_root / "reports" / "agents" / "run-1" / "task_authority.yaml"
            authority.parent.mkdir(parents=True)
            authority.write_text(
                "version: 1\n"
                "run_id: run-1\n"
                "request_clauses: []\n"
                "allowed_paths: []\n"
                "forbidden_paths: []\n"
                "risky_authorities:\n"
                "  helper_change:\n"
                "    - id: helper-format-value\n"
                "      path: app/module.py\n"
                "      qualname: _format_value\n"
                "      owning_module: app/module.py\n"
                "      caller_paths: [app/module.py]\n"
                "      existing_helper_gap: no existing formatter owns this module\n"
                "      tests: [tests/test_module.py]\n"
                "  first_party_library_change: []\n"
                "  public_api_change: []\n"
                "  workflow_change: []\n"
                "  shared_canon_change: []\n"
                "roles: {}\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            module.write_text("def _format_value(value: int) -> str:\n    return str(value)\n", encoding="utf-8")
            doc.write_text("boundary evidence\n\nformat ownership\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "helper-first.jsonl"

            result = subprocess.run(
                [sys.executable, str(HELPER_FIRST_GUARD)],
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
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_TASK_AUTHORITY": str(authority),
                    "AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH": str(log_path),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["hook_log_namespace"], "test-container")
        self.assertEqual(log_entry["helper_candidate_record_count"], 1)
        self.assertEqual(log_entry["helper_first_candidate_count"], 0)
        self.assertTrue(cast("list[dict[str, object]]", log_entry["helper_authority_checks"])[0]["matched"])
        self.assertTrue(log_entry["boundary_evidence_changed"])

    def test_style_checker_guard_selects_cpp_and_notebook_checkers(self) -> None:
        """Style hook should route changed C++ and notebook files to existing checkers."""
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
            cpp_checker = temp_root / "tools" / "oop" / "cpp" / "readability.py"
            notebook_checker = temp_root / "tools" / "validation" / "notebook_quality.py"
            cpp_checker.parent.mkdir(parents=True)
            notebook_checker.parent.mkdir(parents=True)
            pass_checker = "#!/usr/bin/env python3\nprint('STYLE_TEST_CHECKER_OK=1')\n"
            cpp_checker.write_text(pass_checker, encoding="utf-8")
            notebook_checker.write_text(pass_checker, encoding="utf-8")
            source = temp_root / "src" / "demo.cpp"
            notebook = temp_root / "jupyter" / "demo.ipynb"
            source.parent.mkdir()
            notebook.parent.mkdir()
            source.write_text("int value() { return 1; }\n", encoding="utf-8")
            notebook.write_text(self._notebook_payload("display(1)"), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            source.write_text("int value() { return 2; }\n", encoding="utf-8")
            notebook.write_text(self._notebook_payload("display(2)"), encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "style.jsonl"

            result = subprocess.run(
                [sys.executable, str(STYLE_CHECKER_GUARD)],
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
                    "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH": str(log_path),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(
            log_entry["selected_checkers"],
            ["cpp_readability", "notebook_quality"],
        )

    def test_style_checker_guard_blocks_failed_python_style(self) -> None:
        """Style hook should block when the selected Python checker fails."""
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
            source = temp_root / "sample.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            source.write_text("import os\n\nVALUE = 2\n", encoding="utf-8")
            log_path = temp_root / "reports" / "hooks" / "style.jsonl"

            result = subprocess.run(
                [sys.executable, str(STYLE_CHECKER_GUARD)],
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
                    "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH": str(log_path),
                },
            )

            payload = cast("dict[str, object]", json.loads(result.stdout))
            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("Style checker hook", cast(str, payload["reason"]))
        self.assertEqual(payload["next_action"], "run_selected_style_checkers_and_fix_findings")
        self.assertTrue(payload["remediation"])
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["selected_checkers"], ["ruff"])
        self.assertEqual(log_entry["unchecked_count"], 0)

    def test_style_checker_guard_skips_read_only_bash_payloads(self) -> None:
        """Bash tool names alone should not run style checks for read-only commands."""
        commands = (
            "git status --short --branch",
            "git -C /tmp status --short",
            "sed -n '1,20p' sample.py",
            "python3 -m ruff format sample.py",
        )
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
                source = temp_root / "sample.py"
                source.write_text("import os\n\nVALUE = 1\n", encoding="utf-8")
                log_path = temp_root / "reports" / "hooks" / "style.jsonl"

                result = subprocess.run(
                    [sys.executable, str(STYLE_CHECKER_GUARD)],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "PostToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "AGENT_CANON_STYLE_CHECKER_HOOK_LOG_PATH": str(log_path),
                    },
                )

            self.assertEqual(result.stdout, "")
            self.assertFalse(log_path.exists())

    def test_log_surface_inventory_guard_is_quiet_when_baseline_matches(self) -> None:
        """Log surface guard should not consume tokens on a passing inventory check."""
        result = subprocess.run(
            [sys.executable, str(LOG_SURFACE_INVENTORY_GUARD)],
            cwd=PROJECT_ROOT,
            input=json.dumps({"hookEventName": "Stop"}),
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout, "")

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
        self.assertEqual(payload["next_action"], "remove_secret_or_use_redacted_placeholder_then_retry")
        self.assertTrue(payload["remediation"])

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
        self.assertEqual(payload["next_action"], "run_next_goal_iteration_or_update_goal_evidence")
        self.assertTrue(payload["remediation"])

    def test_oop_readability_guard_warns_changed_python_findings(self) -> None:
        """OOP guard should warn after source edits when changed Python fails."""
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
                f"if sys.argv[sys.argv.index('--min-score') + 1] != '{OOP_READABILITY_MIN_SCORE}':\n"
                "    raise SystemExit(0)\n"
                "print('OOP_READABILITY=fail')\n"
                "raise SystemExit(1)\n"
            ),
        )
        self.assertEqual(payload["decision"], "approve")
        reason = payload["reason"]
        if not isinstance(reason, str):
            self.fail("OOP guard reason must be a string")
        self.assertIn("OOP readability hook", reason)
        self.assertIn("warning", reason)
        self.assertIn("--min-score 95", reason)
        self.assertIn("--baseline-ref HEAD", reason)
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["mode"], "diff")
        self.assertEqual(log_entry["baseline_ref"], "HEAD")
        self.assertEqual(log_entry["min_score"], OOP_READABILITY_MIN_SCORE)
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
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(
                        temp_root / ".agent-canon" / "archive" / "test-env"
                    ),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                },
            )
            durable_logs = sorted(
                (temp_root / ".agent-canon" / "archive" / "test-env" / "hook-runs").glob(
                    "*/test-container/oop_readability_guard-*.jsonl"
                )
            )
            durable_log = durable_logs[0]
            durable_log_exists = durable_log.exists()
            log_entry = json.loads(durable_log.read_text(encoding="utf-8").splitlines()[0])

        self.assertIn("decision", json.loads(result.stdout))
        self.assertEqual(len(durable_logs), 1)
        self.assertTrue(durable_log_exists)
        self.assertEqual(log_entry["status"], "warn")
        self.assertEqual(log_entry["mode"], "diff")
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

    def test_oop_readability_guard_requires_declared_hook_event(self) -> None:
        """OOP guard should not infer PostToolUse when hookEventName is missing."""
        payload, log_entry = self._run_oop_guard_with_changed_python(
            json.dumps({"tool_name": "apply_patch"})
        )
        self.assertEqual(payload, {})
        self.assertEqual(log_entry["event"], "UnknownHookEvent")
        self.assertEqual(log_entry["tool_name"], "apply_patch")
        self.assertEqual(log_entry["payload_status"], "valid")
        self.assertFalse(log_entry["event_declared"])
        self.assertFalse(log_entry["checked"])
        self.assertEqual(log_entry["failed_count"], 0)
        self.assertIn("hook_run_id", log_entry)
        self.assertIn("payload_fingerprint", log_entry)

    def test_oop_readability_guard_allows_preexisting_findings_by_default(self) -> None:
        """OOP guard should default to diff mode and allow preexisting findings."""
        payload, log_entry = self._run_oop_guard_with_preexisting_finding()

        self.assertEqual(payload, {})
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["mode"], "diff")
        self.assertEqual(log_entry["baseline_ref"], "HEAD")
        self.assertEqual(log_entry["failed_count"], 0)
        commands = cast(list[dict[str, object]], log_entry["commands"])
        command = commands[0]
        command_args = cast(list[str], command["command"])
        output_snippet = cast(str, command["output_snippet"])
        self.assertIn("--baseline-ref", command_args)
        self.assertIn("HEAD", command_args)
        self.assertIn("OOP_READABILITY_BASELINE=preexisting-only", output_snippet)

    def test_oop_readability_guard_warns_preexisting_findings_in_full_mode(self) -> None:
        """OOP guard should retain full-mode behavior when explicitly requested."""
        payload, log_entry = self._run_oop_guard_with_preexisting_finding(
            extra_env={"AGENT_CANON_OOP_HOOK_MODE": "full"}
        )

        self.assertEqual(payload["decision"], "approve")
        self.assertEqual(log_entry["status"], "warn")
        self.assertEqual(log_entry["mode"], "full")
        self.assertEqual(log_entry["baseline_ref"], "")
        self.assertEqual(log_entry["failed_count"], 1)
        commands = cast(list[dict[str, object]], log_entry["commands"])
        command = commands[0]
        command_args = cast(list[str], command["command"])
        output_snippet = cast(str, command["output_snippet"])
        self.assertNotIn("--baseline-ref", command_args)
        self.assertNotIn("OOP_READABILITY_BASELINE=preexisting-only", output_snippet)

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
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "sed -n '1,20p' README.md"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                },
        )

        self.assertEqual(result.stdout, "")

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
                            "hookEventName": "PostToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
                    check=True,
                    capture_output=True,
                    text=True,
                    env={
                        **os.environ,
                        "AGENT_CANON_OOP_HOOK_LOG_PATH": str(log_path),
                        "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    },
                )

            self.assertEqual(result.stdout, "")

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

    def test_helper_inventory_guard_blocks_name_gap_findings(self) -> None:
        """Helper inventory guard should count role/action naming review records."""
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
                "'qualname': '_x', 'helper_candidate': True, "
                "'candidate_rule': 'main:private-local-converter_normalizer', "
                "'searchable_name': False, "
                "'name_search_rule': 'role-token-review:converter_normalizer'}]}))\n"
            ),
        )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("role-token-review:converter_normalizer", cast(str, payload["reason"]))
        self.assertTrue(log_entry["checked"])
        self.assertEqual(log_entry["records"], 1)
        self.assertEqual(log_entry["violations"], 1)
        domain_counts = cast("dict[str, dict[str, int]]", log_entry["domain_counts"])
        self.assertEqual(domain_counts["main"]["name_gap"], 1)

    def test_helper_inventory_guard_skips_read_only_bash_payloads(self) -> None:
        """Helper inventory guard should not block read-only Bash commands."""
        commands = (
            "git status --short --branch",
            "git -C /tmp status --short",
            "sed -n '1,20p' changed.py",
            "python3 -m ruff check changed.py",
        )
        for command in commands:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
                source = temp_root / "changed.py"
                source.write_text("def value() -> int:\n    return 1\n", encoding="utf-8")
                log_path = temp_root / "reports" / "hooks" / "helper.jsonl"

                result = subprocess.run(
                    [sys.executable, str(HELPER_INVENTORY_GUARD)],
                    cwd=temp_root,
                    input=json.dumps(
                        {
                            "hookEventName": "PostToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"cmd": command},
                        }
                    ),
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

    def test_helper_inventory_guard_requires_repo_policy(self) -> None:
        """Missing repo-local policy should block until the policy exists."""
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
        self.assertEqual(log_entry["policy_status"], "error")
        self.assertIn("helper inventory policy is required", str(log_entry["policy_error"]))
        self.assertIn("repair_helper_inventory_policy", cast(str, payload["next_action"]))

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

    def test_notebook_quality_guard_blocks_test_like_notebook(self) -> None:
        """Notebook hook should block notebooks that embed fine-grained tests."""
        payload, log_entry = self._run_notebook_guard_with_changed_notebook(
            "assert True\nplt.plot([0], [0])\nplt.show()",
            json.dumps(
                {
                    "hookEventName": "PostToolUse",
                    "tool_name": "apply_patch",
                }
            ),
        )

        self.assertEqual(payload["decision"], "block")
        self.assertIn("Notebook quality hook", cast(str, payload["reason"]))
        self.assertEqual(log_entry["event"], "PostToolUse")
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["finding_count"], 2)
        self.assertEqual(log_entry["notebooks"], ["jupyter/demo.ipynb"])

    def test_notebook_quality_guard_skips_read_only_bash_payloads(self) -> None:
        """Read-only Bash payloads should not run notebook quality checks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "notebook.jsonl"
            result = subprocess.run(
                [sys.executable, str(NOTEBOOK_QUALITY_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "sed -n '1,20p' jupyter/demo.ipynb"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_NOTEBOOK_QUALITY_HOOK_LOG_PATH": str(log_path),
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
            env = {
                **os.environ,
                "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
            }

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
        self.assertEqual(entries[1]["selected_skills"], ["change-review"])
        self.assertEqual(entries[1]["skill_selection_kind"], "declared_skill")
        self.assertEqual(entries[1]["selected_workflow"], "Scoped Change")
        self.assertEqual(entries[1]["selected_workflows"], ["Scoped Change"])
        self.assertEqual(entries[1]["workflow"], ["Scoped Change"])
        self.assertEqual(entries[1]["workflow_family"], "Scoped Change")
        self.assertEqual(entries[1]["workflow_selection_kind"], "declared_workflow")
        self.assertEqual(entries[1]["selected_workflow_count"], 1)
        self.assertEqual(entries[2]["skills"], ["skill-creator"])
        self.assertTrue(all(entry["hook_run_id"].startswith("hook-") for entry in entries))
        self.assertTrue(all(entry["payload_fingerprint"] for entry in entries))
        self.assertEqual(entries[0]["skill_source_fields"], ["prompt"])
        self.assertEqual(entries[0]["prompt_capture_status"], "present")
        self.assertIn("Use $agent-orchestration", entries[0]["prompt_excerpt_redacted"])
        self.assertTrue(entries[0]["prompt_fingerprint"])
        self.assertEqual(entries[1]["skill_source_fields"], ["last_assistant_message"])
        self.assertEqual(entries[1]["prompt_capture_status"], "missing")
        self.assertEqual(entries[2]["observed_text_field_count"], 1)
        self.assertEqual(entries[2]["observed_text_value_count"], 1)
        self.assertTrue(all(entry["payload_key_count"] >= 2 for entry in entries))
        self.assertTrue(all(entry["event_declared"] is True for entry in entries))

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
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(
                        temp_root / ".agent-canon" / "archive" / "test-env"
                    ),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                },
            )
            log_paths = sorted(
                (temp_root / ".agent-canon" / "archive" / "test-env" / "hook-runs").glob(
                    "*/test-container/skill_usage-no-git-head.jsonl"
                )
            )
            log_path = log_paths[0]
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result.stdout, "")
        self.assertEqual(len(log_paths), 1)
        self.assertEqual(entries[0]["skills"], ["agent-orchestration"])
        self.assertTrue(entries[0]["hook_run_id"].startswith("hook-"))
        self.assertEqual(entries[0]["hook_log_namespace"], "test-container")
        self.assertTrue(entries[0]["source_repo_key"])
        self.assertEqual(entries[0]["skill_source_fields"], ["prompt"])
        self.assertEqual(entries[0]["observed_text_field_count"], 1)

    def test_skill_usage_logger_ensures_archive_branch_before_durable_write(self) -> None:
        """Durable hook output should select the archive branch before appending logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            archive_root = temp_root / ".agent-canon" / "archive"
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            archive_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=archive_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=archive_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=archive_root, check=True)
            (archive_root / "README.md").write_text("# Runtime Log Archive\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=archive_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=archive_root, check=True, capture_output=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=archive_root, check=True, capture_output=True)
            subprocess.run(
                ["git", "switch", "-c", "logs/test-env-other-thread"],
                cwd=archive_root,
                check=True,
                capture_output=True,
            )

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
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(archive_root),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_LOG_ENV": "test-env",
                    "CODEX_THREAD_ID": "thread-1",
                },
            )
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=archive_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            log_path = (
                archive_root
                / "hook-runs"
                / repo_log_key(temp_root)
                / "test-container"
                / "skill_usage-no-git-head.jsonl"
            )
            log_exists = log_path.exists()

        self.assertEqual(result.stdout, "")
        self.assertEqual(branch, "logs/test-env-thread-1")
        self.assertTrue(log_exists)

    def test_skill_usage_logger_honors_source_root_override(self) -> None:
        """Source-root override should route hook logs to the intended repo key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            active_root = temp_root / "parent"
            source_root = temp_root / "agent-canon"
            active_root.mkdir()
            source_root.mkdir()
            subprocess.run(["git", "init"], cwd=active_root, check=True, capture_output=True)
            subprocess.run(["git", "init"], cwd=source_root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=source_root, check=True)
            (source_root / "README.md").write_text("# Source\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=source_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=source_root, check=True, capture_output=True)
            source_head = subprocess.run(
                ["git", "-C", str(source_root), "rev-parse", "--verify", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            archive_root = temp_root / ".agent-canon" / "archive"
            trace_key = "thread-test-1"

            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=active_root,
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
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(archive_root),
                    "AGENT_CANON_HOOK_RUN_NAMESPACE": "test-container",
                    "AGENT_CANON_HOOK_SOURCE_ROOT": str(source_root),
                    "CODEX_THREAD_ID": trace_key,
                },
            )
            log_path = (
                archive_root
                / "hook-runs"
                / repo_log_key(source_root)
                / "test-container"
                / f"skill_usage-{source_head[:12]}.jsonl"
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["source_repo_key"], repo_log_key(source_root))
        self.assertEqual(entry["codex_trace_key"], trace_key)
        self.assertEqual(entry["codex_thread_id"], trace_key)
        self.assertEqual(entry["agent_canon_git_head"], source_head)
        self.assertEqual(entry["source_git_head"], source_head)

    def test_skill_usage_logger_skips_no_skill_payloads(self) -> None:
        """No-skill hook payloads should not dirty durable AgentCanon logs."""
        payloads: tuple[dict[str, object], ...] = (
            {},
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

    def test_skill_usage_logger_records_plain_prompt_capture(self) -> None:
        """Plain user prompts should be captured as redacted bounded evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "plain consultation with sk-abcdefghijklmnopqrstuvwxyz1234567890",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["prompt_capture_status"], "present")
        self.assertIn("plain consultation", entry["prompt_excerpt_redacted"])
        self.assertIn("[REDACTED_API_KEY]", entry["prompt_excerpt_redacted"])
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", entry["prompt_excerpt_redacted"])
        self.assertEqual(entry["skills"], [])
        self.assertEqual(entry["candidate_skills"], [])
        self.assertEqual(entry["candidate_tools"], [])

    def test_skill_usage_logger_records_post_tool_selection(self) -> None:
        """Tool selection logging should record PostToolUse metadata for later analysis."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "python3 -m pytest tests/agent_tools/test_codex_hooks.py"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["event"], "PostToolUse")
        self.assertEqual(entry["tool_name"], "Bash")
        self.assertEqual(entry["tool_selection_kind"], "executed_tool")
        self.assertEqual(entry["tool_command_verb"], "python3")
        self.assertEqual(entry["selected_tools"], [])
        self.assertEqual(entry["tool_input_keys"], ["cmd"])
        self.assertTrue(entry["tool_input_fingerprint"])
        self.assertFalse(entry["subagent_invoked"])

    def test_skill_usage_logger_inherits_workflow_context_for_post_tool(self) -> None:
        """The PostToolUse logs inherit the last declared workflow context."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            context_path = temp_root / "reports" / "hooks" / "skill_context.json"
            env = {
                **os.environ,
                "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                "AGENT_CANON_SKILL_CONTEXT_PATH": str(context_path),
            }

            declared = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": (
                            "workflow=Scoped Change skills=$agent-orchestration"
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            post_tool = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "python3 -m pytest tests"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(declared.stdout, "")
        self.assertEqual(post_tool.stdout, "")
        self.assertEqual(entries[0]["workflow_selection_kind"], "declared_workflow")
        self.assertEqual(entries[1]["selected_workflows"], ["Scoped Change"])
        self.assertEqual(entries[1]["workflow_selection_kind"], "inherited_workflow")
        self.assertEqual(entries[1]["workflow_context_workflows"], ["Scoped Change"])

    def test_skill_usage_logger_does_not_count_shell_variables_as_skills(self) -> None:
        """Bash variables in tool input should not become selected skills."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            command = (
                "latest=$(ls reports/*.md | tail -n 1); "
                "pid=$!; for f in reports/*.json; do run=$f; done; "
                "echo $latest $pid $f $run"
            )

            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": command},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["event"], "PostToolUse")
        self.assertEqual(entry["tool_name"], "Bash")
        self.assertEqual(entry["tool_selection_kind"], "executed_tool")
        self.assertEqual(entry["skills"], [])
        self.assertEqual(entry["selected_skills"], [])
        self.assertNotIn("skill:latest", entry["feedback_targets"])
        self.assertNotIn("skill:pid", entry["feedback_targets"])
        self.assertNotIn("skill:f", entry["feedback_targets"])
        self.assertNotIn("skill:run", entry["feedback_targets"])
        self.assertEqual(entry["skill_source_fields"], ["tool_input"])
        self.assertTrue(entry["tool_input_fingerprint"])

    def test_skill_usage_logger_does_not_treat_tool_input_search_as_routing_candidate(self) -> None:
        """Tool input mentions are execution evidence, not prompt-derived routing candidates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {
                            "command": (
                                "rg -n \"skill_usage_logger.py|agent-log-analysis\" "
                                ".codex/hooks tests"
                            )
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["candidate_skills"], [])
        self.assertEqual(entry["candidate_tools"], [])
        self.assertEqual(entry["selected_tools"], [])
        self.assertEqual(entry["skill_source_fields"], ["tool_input"])

    def test_skill_usage_logger_records_hook_tool_execution(self) -> None:
        """Direct hook script execution should remain selected repo-tool evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {
                            "command": "python3 .codex/hooks/skill_usage_logger.py"
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["candidate_tools"], [])
        self.assertEqual(entry["selected_tools"], ["skill_usage_logger.py"])

    def test_skill_usage_logger_does_not_count_prompt_shell_variables_as_skills(self) -> None:
        """Prompt dollar tokens should be known skills, not shell variable lookalikes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"

            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $latest and $PID and $USER, then decide skill routing.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["skills"], [])
        self.assertEqual(entry["selected_skills"], [])
        self.assertNotIn("skill:latest", entry["feedback_targets"])
        self.assertNotIn("latest", entry["candidate_skills"])
        self.assertIn("agent-orchestration", entry["candidate_skills"])
        self.assertEqual(entry["skill_source_fields"], ["prompt"])

    def test_skill_usage_logger_records_subagent_lifecycle_selection(self) -> None:
        """Subagent lifecycle logging should record spawn metadata without prompt text."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "spawn_agent",
                        "tool_input": {
                            "agent_type": "test_designer",
                            "model": "gpt-5.5",
                            "reasoning_effort": "high",
                            "fork_context": True,
                            "message": "Design tests for the changed hook.",
                            "items": [{"type": "text", "text": "packet"}],
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertTrue(entry["subagent_invoked"])
        self.assertEqual(entry["subagent_event_kind"], "spawn")
        self.assertEqual(entry["subagent_tool_name"], "spawn_agent")
        self.assertEqual(entry["subagent_agent_type"], "test_designer")
        self.assertEqual(entry["subagent_model"], "gpt-5.5")
        self.assertEqual(entry["subagent_reasoning_effort"], "high")
        self.assertTrue(entry["subagent_fork_context"])
        self.assertTrue(entry["subagent_prompt_fingerprint"])
        self.assertEqual(entry["subagent_prompt_char_count"], len("Design tests for the changed hook."))
        self.assertEqual(entry["subagent_item_count"], 1)
        self.assertNotIn("Design tests", json.dumps(entry, sort_keys=True))

    def test_skill_usage_logger_records_subagent_workflow_monitor_event(self) -> None:
        """Subagent lifecycle hooks should append run-bundle behavior evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports" / "agents" / "run-subagent"
            log_path = root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "spawn_agent",
                        "tool_input": {
                            "agent_type": "spark_worker",
                            "model": "gpt-5.3-codex-spark",
                            "reasoning_effort": "low",
                            "message": "Patch one explicit slice.",
                        },
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(report_dir),
                },
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["workflow_monitor_subagent_event_count"], 1)
        self.assertIn("subagent_lifecycle_event=spawn", monitoring)
        self.assertIn("subagent_agent_type=spark_worker", monitoring)
        self.assertIn("subagent_prompt_char_count=25", monitoring)

    def test_skill_usage_logger_uses_active_run_pointer_for_monitoring(self) -> None:
        """Run-bundle monitoring should work without per-hook report-dir env."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports" / "agents" / "run-active"
            report_dir.mkdir(parents=True)
            (report_dir / "workflow_monitoring.md").write_text(
                "# Workflow Monitoring\n\n## Behavior Events\n",
                encoding="utf-8",
            )
            pointer = root / "reports" / "agents" / ".active_run"
            pointer.write_text(str(report_dir) + "\n", encoding="utf-8")
            log_path = root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "close_agent",
                        "tool_input": {"target": "agent-123"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                    "AGENT_CANON_ACTIVE_RUN_POINTER": str(pointer),
                },
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["workflow_monitor_subagent_event_count"], 1)
        self.assertEqual(entry["workflow_monitor_report_dir"], str(report_dir))
        self.assertIn("subagent_lifecycle_event=close", monitoring)

    def test_skill_usage_logger_prefers_parent_active_run_for_vendored_agentcanon(self) -> None:
        """Vendored AgentCanon hook runs should not write workflow evidence to stale submodule reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent_root = Path(temp_dir) / "project_template"
            source_root = parent_root / "vendor" / "agent-canon"
            source_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=source_root, check=True, capture_output=True)

            parent_report = parent_root / "reports" / "agents" / "run-current"
            parent_report.mkdir(parents=True)
            (parent_report / "workflow_monitoring.md").write_text(
                "# Workflow Monitoring\n\n## Behavior Events\n",
                encoding="utf-8",
            )
            parent_pointer = parent_root / "reports" / "agents" / ".active_run"
            parent_pointer.write_text(str(parent_report) + "\n", encoding="utf-8")

            stale_report = source_root / "reports" / "agents" / "run-stale"
            stale_report.mkdir(parents=True)
            (stale_report / "workflow_monitoring.md").write_text(
                "# Workflow Monitoring\n\n## Behavior Events\n",
                encoding="utf-8",
            )
            stale_pointer = source_root / "reports" / "agents" / ".active_run"
            stale_pointer.write_text(str(stale_report) + "\n", encoding="utf-8")

            log_path = parent_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=source_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "close_agent",
                        "tool_input": {"target": "agent-123"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["workflow_monitor_report_dir"], str(parent_report))

    def test_skill_usage_logger_records_subagent_close_selection(self) -> None:
        """Subagent close logging should record lifecycle target metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "close_agent",
                        "tool_input": {"target": "agent-123"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertTrue(entry["subagent_invoked"])
        self.assertEqual(entry["subagent_event_kind"], "close")
        self.assertEqual(entry["subagent_target"], "agent-123")
        self.assertEqual(entry["subagent_target_count"], 1)

    def test_skill_usage_logger_records_start_declaration_selection(self) -> None:
        """Selection logging should parse workflow and skills from start declarations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": (
                            "START_DECLARATION=workflow=Comprehensive Development, "
                            "skills=$agent-orchestration,$codex-task-workflow, "
                            "review=local"
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["selected_workflow"], "Comprehensive Development")
        self.assertEqual(entry["selected_workflows"], ["Comprehensive Development"])
        self.assertEqual(entry["workflow_selection_kind"], "declared_workflow")
        self.assertEqual(entry["selected_skills"], ["agent-orchestration", "codex-task-workflow"])

    def test_skill_usage_logger_records_markdown_docs_signals(self) -> None:
        """Markdown prompts and docs-check commands should be measurable later."""
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
                        "prompt": "マークダウンの hook と agent-canon docs check が引っかかっていないか見たい。",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            tool = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "tools/bin/agent-canon docs check README.md"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(prompt.stdout, "")
        self.assertEqual(tool.stdout, "")
        self.assertIn("md-style-check", entries[0]["candidate_skills"])
        self.assertIn("agent-canon-cli", entries[0]["candidate_tools"])
        self.assertEqual(entries[1]["candidate_tools"], [])
        self.assertIn("agent-canon-cli", entries[1]["selected_tools"])

    def test_skill_usage_logger_records_computational_optimization_signals(self) -> None:
        """Optimization prompts should route to the computational optimization skill."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "計算最適化スキルを使って solver の residual と KKT 収束を見直して",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertIn("computational-optimization", entry["candidate_skills"])

    def test_skill_usage_logger_records_gpu_execution_signals(self) -> None:
        """GPU execution prompts should route to the GPU execution skill."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "GPU利用では Python 実行を ExperimentRunner に移譲して先取無効にする",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertIn("gpu-execution", entry["candidate_skills"])

    def test_skill_usage_logger_carries_recent_workflow_to_tool_events(self) -> None:
        """Tool events should inherit the latest declared workflow in the same log shard."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            env = {**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)}
            subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "workflow=Scoped Change skills=$agent-orchestration",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"cmd": "tools/bin/agent-canon docs check README.md"},
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result.stdout, "")
        self.assertEqual(entries[1]["selected_workflows"], ["Scoped Change"])
        self.assertEqual(entries[1]["workflow_selection_kind"], "context_workflow")
        self.assertEqual(entries[1]["workflow_context_source"], "recent_log")
        self.assertIn("agent-canon-cli", entries[1]["selected_tools"])

    def test_skill_usage_logger_treats_plain_prompt_skill_names_as_selected(self) -> None:
        """Plain public skill ids in user prompts should become selected skill evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "md-style-check と agent-learning の routing gap を直して",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["skills"], ["agent-learning", "md-style-check"])
        self.assertEqual(entry["selected_skills"], ["agent-learning", "md-style-check"])
        self.assertEqual(entry["candidate_skills"], [])
        self.assertEqual(entry["skill_selection_kind"], "declared_skill")
        self.assertEqual(entry["skill_source_fields"], ["prompt"])

    def test_skill_usage_logger_discovers_current_repo_skill_ids(self) -> None:
        """New AgentCanon skill shims should be counted without hand-editing the hook list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use $agent-log-analysis and $prose-reasoning-graph.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["selected_skills"], ["agent-log-analysis", "prose-reasoning-graph"])
        self.assertEqual(entry["skill_selection_kind"], "declared_skill")

    def test_skill_usage_logger_does_not_route_standalone_toolcall_prompt_to_log_analysis(self) -> None:
        """Standalone ToolCall implementation text should not imply log-analysis routing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Implement ToolCall parser support in the runtime adapter",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_SKILL_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertNotIn("agent-log-analysis", entry["candidate_skills"])

    def test_skill_usage_logger_records_prompt_feedback_routing(self) -> None:
        """Prompt feedback should be classified with bounded redacted prompt text."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "reports" / "agents" / "run-feedback"
            log_path = root / "reports" / "hooks" / "skills.jsonl"
            result = subprocess.run(
                [sys.executable, str(SKILL_USAGE_LOGGER)],
                cwd=PROJECT_ROOT,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": (
                            "人間からのフィードバックを受ける機構が弱い。"
                            "結果書き出しのスキルと入力プロンプトを解析して "
                            "workflow_monitor.py と Agent Improvement Guide に "
                            "ログに積む機構を組み込みたい。"
                        ),
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_SKILL_LOG_PATH": str(log_path),
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(report_dir),
                },
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            monitoring = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")

        self.assertEqual(result.stdout, "")
        self.assertIn("結果書き出し", entry["prompt_excerpt_redacted"])
        self.assertEqual(entry["skills"], [])
        self.assertIn("result-artifact-writeout", entry["candidate_skills"])
        self.assertIn("agent-learning", entry["candidate_skills"])
        self.assertIn("skill_usage_logger.py", entry["candidate_tools"])
        self.assertIn("workflow_monitor.py", entry["candidate_tools"])
        self.assertIn("generate_agent_improvement_guide.py", entry["candidate_tools"])
        self.assertTrue(entry["prompt_feedback_detected"])
        self.assertEqual(entry["feedback_action"], "prompt_repair")
        self.assertIn("quality_gap", entry["feedback_labels"])
        self.assertIn("repair_request", entry["feedback_labels"])
        self.assertIn("missing_mechanism", entry["feedback_labels"])
        self.assertGreaterEqual(
            entry["workflow_monitor_feedback_count"], EXPECTED_PROMPT_FEEDBACK_MIN
        )
        self.assertIn("runtime_feedback=observed", monitoring)
        self.assertIn("skill_candidate=$agent-learning", monitoring)
        self.assertIn("skill_candidate=$result-artifact-writeout", monitoring)
        self.assertIn("target=skill:result-artifact-writeout", monitoring)
        self.assertIn("target=tool:workflow_monitor.py", monitoring)

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
            log_path = log_dir / "test-container" / "skill_usage-no-git-head.jsonl"
            entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(result.stdout, "")
        self.assertEqual(entries[0]["skills"], ["agent-orchestration"])
        self.assertTrue(entries[0]["hook_run_id"].startswith("hook-"))
        self.assertEqual(entries[0]["payload_key_count"], 2)

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
        self.assertEqual(entry["workflow_monitor_report_dir"], str(report_dir))
        self.assertEqual(entry["skill_source_fields"], ["prompt"])
        self.assertIn(
            "skill_invocation=$agent-orchestration status=observed source=codex_hook",
            monitoring,
        )

    def test_reference_capture_guard_logs_prompt_urls_without_blocking(self) -> None:
        """Reference hook should log prompt URL capture requirements."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "references.jsonl"

            result = subprocess.run(
                [sys.executable, str(REFERENCE_CAPTURE_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "UserPromptSubmit",
                        "prompt": "Use https://example.com/paper.pdf as a source.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_REFERENCE_CAPTURE_HOOK_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["event"], "UserPromptSubmit")
        self.assertEqual(entry["missing_urls"], ["https://example.com/paper.pdf"])
        self.assertEqual(entry["decision"], "pass")
        self.assertEqual(entry["status"], "pass")

    def test_reference_capture_guard_blocks_stop_with_unregistered_url(self) -> None:
        """Reference hook should block completion when cited URLs are not captured."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "references.jsonl"

            result = subprocess.run(
                [sys.executable, str(REFERENCE_CAPTURE_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "I used https://example.com/report.html.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_REFERENCE_CAPTURE_HOOK_LOG_PATH": str(log_path)},
            )
            payload = json.loads(result.stdout)
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(payload["decision"], "block")
        self.assertIn("reference_materializer.py", payload["reason"])
        self.assertEqual(payload["next_action"], "materialize_external_references_then_retry")
        self.assertTrue(payload["remediation"])
        self.assertEqual(entry["missing_count"], 1)
        self.assertEqual(entry["status"], "fail")

    def test_reference_capture_guard_accepts_registered_reference_url(self) -> None:
        """Reference hook should pass when references contains the observed URL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            reference = temp_root / "references" / "external" / "report.md"
            reference.parent.mkdir(parents=True)
            reference.write_text(
                "# Report\n\n- source_url: https://example.com/report.html\n",
                encoding="utf-8",
            )
            log_path = temp_root / "reports" / "hooks" / "references.jsonl"

            result = subprocess.run(
                [sys.executable, str(REFERENCE_CAPTURE_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "I used https://example.com/report.html.",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_REFERENCE_CAPTURE_HOOK_LOG_PATH": str(log_path)},
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(result.stdout, "")
        self.assertEqual(entry["registered_count"], 1)
        self.assertEqual(entry["missing_count"], 0)
        self.assertEqual(entry["reference_files"], ["references/external/report.md"])

    def test_reference_capture_guard_ignores_operational_github_pr_urls(self) -> None:
        """Reference hook should ignore GitHub PR plumbing URLs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=temp_root, check=True, capture_output=True)
            log_path = temp_root / "reports" / "hooks" / "references.jsonl"

            result = subprocess.run(
                [sys.executable, str(REFERENCE_CAPTURE_GUARD)],
                cwd=temp_root,
                input=json.dumps(
                    {
                        "hookEventName": "Stop",
                        "last_assistant_message": "PR: https://github.com/org/repo/pull/123",
                    }
                ),
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "AGENT_CANON_REFERENCE_CAPTURE_HOOK_LOG_PATH": str(log_path)},
            )

        self.assertEqual(result.stdout, "")
        self.assertFalse(log_path.exists())
