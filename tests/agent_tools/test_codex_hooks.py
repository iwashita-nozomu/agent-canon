"""Tests for Codex project-local hook wiring."""

# @dependency-start
# responsibility Tests test codex hooks behavior.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares MCP context hooks
# upstream implementation ../../.codex/hooks/mcp_session_context.sh emits hook JSON
# upstream implementation ../../.codex/hooks/helper_inventory_guard.py blocks helper inventory findings
# upstream implementation ../../.codex/hooks/module_boundary_guard.py blocks forced module rewrites
# upstream implementation ../../.codex/hooks/library_implementation_guard.py blocks library implementation rewrites
# upstream implementation ../../.codex/hooks/helper_first_guard.py blocks helper-first implementation drift
# upstream implementation ../../.codex/hooks/notebook_quality_guard.py blocks notebook quality findings
# upstream implementation ../../.codex/hooks/oop_readability_guard.py logs and blocks OOP findings
# upstream implementation ../../.codex/hooks/log_surface_inventory_guard.py blocks log surface drift
# upstream implementation ../../.codex/hooks/style_checker_guard.py logs style checker coverage
# upstream implementation ../../.codex/hooks/skill_usage_logger.py logs observed skill usage
# upstream implementation ../../.codex/hooks/reference_capture_guard.py logs reference capture coverage
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
MODULE_BOUNDARY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "module_boundary_guard.py"
LIBRARY_IMPLEMENTATION_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "library_implementation_guard.py"
HELPER_FIRST_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "helper_first_guard.py"
LOG_SURFACE_INVENTORY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "log_surface_inventory_guard.py"
NOTEBOOK_QUALITY_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "notebook_quality_guard.py"
STYLE_CHECKER_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "style_checker_guard.py"
SKILL_USAGE_LOGGER = PROJECT_ROOT / ".codex" / "hooks" / "skill_usage_logger.py"
REFERENCE_CAPTURE_GUARD = PROJECT_ROOT / ".codex" / "hooks" / "reference_capture_guard.py"
NOTEBOOK_MAJOR_VERSION = 4
NOTEBOOK_MINOR_VERSION = 5
OOP_READABILITY_MIN_SCORE = 95
EXPECTED_PROMPT_FEEDBACK_MIN = 3


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
        self.assertTrue(HOOK_SCRIPT.exists())

    def test_hooks_json_wires_mcp_context_hook(self) -> None:
        """Only session startup should point at the repo-local MCP context script."""
        hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))

        session_start = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        prompt_hooks = hooks["hooks"]["UserPromptSubmit"][0]["hooks"]
        prompt_commands = [hook["command"] for hook in prompt_hooks]
        post_tool = hooks["hooks"]["PostToolUse"][0]
        post_tool_commands = [hook["command"] for hook in post_tool["hooks"]]
        stop_hooks = hooks["hooks"]["Stop"][0]["hooks"]
        stop_commands = [hook["command"] for hook in stop_hooks]

        self.assertIn("SessionStart", session_start["command"])
        self.assertIn("mcp_session_context.sh", session_start["command"])
        self.assertFalse(any("mcp_session_context.sh" in command for command in prompt_commands))
        self.assertTrue(any("prompt_secret_guard.py" in command for command in prompt_commands))
        self.assertTrue(any("skill_usage_logger.py" in command for command in prompt_commands))
        self.assertTrue(any("reference_capture_guard.py" in command for command in prompt_commands))
        self.assertNotIn("PreToolUse", hooks["hooks"])
        self.assertIn("apply_patch", post_tool["matcher"])
        self.assertTrue(any("skill_usage_logger.py" in command for command in post_tool_commands))
        self.assertTrue(any("reference_capture_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("oop_readability_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("module_boundary_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("library_implementation_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("helper_first_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("goal_completion_guard.py" in command for command in stop_commands))
        self.assertTrue(any("oop_readability_guard.py" in command for command in stop_commands))
        self.assertTrue(any("module_boundary_guard.py" in command for command in stop_commands))
        self.assertTrue(any("library_implementation_guard.py" in command for command in stop_commands))
        self.assertTrue(any("helper_first_guard.py" in command for command in stop_commands))
        self.assertTrue(any("helper_inventory_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("helper_inventory_guard.py" in command for command in stop_commands))
        self.assertTrue(any("log_surface_inventory_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("log_surface_inventory_guard.py" in command for command in stop_commands))
        self.assertTrue(any("notebook_quality_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("notebook_quality_guard.py" in command for command in stop_commands))
        self.assertTrue(any("style_checker_guard.py" in command for command in post_tool_commands))
        self.assertTrue(any("style_checker_guard.py" in command for command in stop_commands))
        self.assertTrue(any("skill_usage_logger.py" in command for command in stop_commands))
        self.assertTrue(any("reference_capture_guard.py" in command for command in stop_commands))

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
            docs_dir = temp_root / "tools" / "docs"
            docs_dir.mkdir(parents=True)
            checker_text = (
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('STYLE_TEST_CHECKER_OK=' + ','.join(sys.argv[1:]))\n"
            )
            (docs_dir / "check_markdown_lint.py").write_text(checker_text, encoding="utf-8")
            (docs_dir / "check_markdown_math.py").write_text(checker_text, encoding="utf-8")
            readme = temp_root / "README.md"
            data = temp_root / "data.lock"
            readme.write_text("# Title\n\nInitial text.\n", encoding="utf-8")
            data.write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=temp_root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_root, check=True, capture_output=True)
            readme.write_text("# Title\n\nChanged text.\n", encoding="utf-8")
            data.write_text("changed\n", encoding="utf-8")
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
        self.assertEqual(log_entry["selected_checkers"], ["markdown_lint", "markdown_math"])
        self.assertEqual(log_entry["unchecked_count"], 1)
        self.assertEqual(
            cast("list[dict[str, object]]", log_entry["unchecked_files"])[0]["paths"],
            ["data.lock"],
        )

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
                    "AGENT_CANON_HELPER_FIRST_HOOK_LOG_PATH": str(log_path),
                },
            )

            log_entry = cast(
                "dict[str, object]",
                json.loads(log_path.read_text(encoding="utf-8").splitlines()[0]),
            )

        self.assertEqual(result.stdout, "")
        self.assertEqual(log_entry["status"], "pass")
        self.assertEqual(log_entry["helper_candidate_record_count"], 1)
        self.assertEqual(log_entry["helper_first_candidate_count"], 0)
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
        self.assertEqual(log_entry["status"], "fail")
        self.assertEqual(log_entry["selected_checkers"], ["ruff"])
        self.assertEqual(log_entry["unchecked_count"], 0)

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
        self.assertIn("ordinary consultation", hook_output["additionalContext"])
        self.assertIn("not repository tasks", hook_output["additionalContext"])
        self.assertIn("Do not run check_mcp_inventory.py", hook_output["additionalContext"])
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
                f"if sys.argv[sys.argv.index('--min-score') + 1] != '{OOP_READABILITY_MIN_SCORE}':\n"
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
        output_snippet = cast(str, command["output_snippet"])
        self.assertNotIn("OOP_READABILITY_BASELINE=preexisting-only", output_snippet)

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
        command_args = cast(list[str], command["command"])
        output_snippet = cast(str, command["output_snippet"])
        self.assertIn("--baseline-ref", command_args)
        self.assertIn("HEAD", command_args)
        self.assertIn("OOP_READABILITY_BASELINE=preexisting-only", output_snippet)

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
        self.assertEqual(entries[0]["skill_source_fields"], ["prompt"])
        self.assertEqual(entries[0]["prompt_capture_status"], "present")
        self.assertIn("Use $agent-orchestration", entries[0]["prompt_excerpt_redacted"])
        self.assertTrue(entries[0]["prompt_fingerprint"])
        self.assertEqual(entries[1]["skill_source_fields"], ["last_assistant_message"])
        self.assertEqual(entries[1]["prompt_capture_status"], "missing")
        self.assertEqual(entries[2]["observed_text_field_count"], 1)
        self.assertEqual(entries[2]["observed_text_value_count"], 1)
        self.assertTrue(all(entry["payload_key_count"] >= 2 for entry in entries))
        self.assertTrue(all(entry["event_fallback"] is False for entry in entries))

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
        self.assertEqual(entries[0]["skill_source_fields"], ["prompt"])
        self.assertEqual(entries[0]["observed_text_field_count"], 1)

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
        self.assertEqual(entry["tool_input_keys"], ["cmd"])
        self.assertTrue(entry["tool_input_fingerprint"])

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
                        "prompt": "マークダウンの hook と docs-check が引っかかっていないか見たい。",
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
                        "tool_input": {"cmd": "bash tools/ci/run_docs_checks.sh"},
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
        self.assertIn("run_docs_checks.sh", entries[0]["candidate_tools"])
        self.assertIn("run_docs_checks.sh", entries[1]["candidate_tools"])

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
            log_path = log_dir / "test-container" / "skill_usage.jsonl"
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
