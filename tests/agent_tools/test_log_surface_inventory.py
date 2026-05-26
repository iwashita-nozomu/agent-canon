# @dependency-start
# responsibility Tests log surface inventory, Rust CLI field extraction, and baseline drift detection.
# upstream implementation ../../tools/agent_tools/log_surface_inventory.py inventories emitted machine-readable fields
# downstream implementation ../../.codex/hooks/log_surface_inventory_guard.py consumes inventory checks
# @dependency-end
"""Tests for log-surface field inventory."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "log_surface_inventory.py"


class LogSurfaceInventoryTest(unittest.TestCase):
    """Validate static log field extraction."""

    def test_extracts_python_shell_rust_and_skill_fields(self) -> None:
        """The inventory should find JSON, key-value, Rust, shell, and skill examples."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            hook = root / ".codex" / "hooks" / "sample.py"
            hook.parent.mkdir(parents=True)
            hook.write_text(
                "\n".join(
                    [
                        "import json",
                        "entry = {'status': 'pass', 'hook_run_id': 'h'}",
                        "print('SAMPLE_STATUS=pass')",
                        "print(json.dumps(entry))",
                    ]
                ),
                encoding="utf-8",
            )
            python_tool = root / "tools" / "sample.py"
            python_tool.parent.mkdir(parents=True)
            python_tool.write_text(
                "\n".join(
                    [
                        "lines = [f'LIST_STATUS={1}']",
                        "lines.append('APPEND_STATUS=1')",
                        "def render():",
                        "    return f'RETURN_STATUS={1}'",
                        "print('\\n'.join(lines))",
                        "print(render())",
                    ]
                ),
                encoding="utf-8",
            )
            shell = root / "tools" / "sample.sh"
            shell.write_text("echo TOOL_STATUS=pass\n", encoding="utf-8")
            rust_tool = root / "rust" / "agent-canon" / "src" / "sample.rs"
            rust_tool.parent.mkdir(parents=True)
            rust_tool.write_text(
                'fn main() {\n    println!("RUST_TOOL_STATUS=pass");\n}\n',
                encoding="utf-8",
            )
            skill = root / ".agents" / "skills" / "sample" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("```text\nSKILL_RESULT=pass\n```\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    ".codex",
                    "tools",
                    "rust",
                    ".agents",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        fields = {record["field"] for record in payload["records"]}
        self.assertIn("SAMPLE_STATUS", fields)
        self.assertIn("LIST_STATUS", fields)
        self.assertIn("APPEND_STATUS", fields)
        self.assertIn("RETURN_STATUS", fields)
        self.assertIn("status", fields)
        self.assertIn("hook_run_id", fields)
        self.assertIn("TOOL_STATUS", fields)
        self.assertIn("RUST_TOOL_STATUS", fields)
        self.assertIn("SKILL_RESULT", fields)

    def test_baseline_check_detects_and_accepts_regenerated_inventory(self) -> None:
        """Baseline mode should fail on drift and pass quietly after regeneration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            hook = root / ".codex" / "hooks" / "sample.py"
            hook.parent.mkdir(parents=True)
            hook.write_text("print('FIRST_FIELD=1')\n", encoding="utf-8")
            baseline = root / "documents" / "log-surface-inventory.json"

            subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--output",
                    "documents/log-surface-inventory.json",
                    "--quiet",
                    ".codex",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            hook.write_text(
                "print('FIRST_FIELD=1')\nprint('SECOND_FIELD=2')\n",
                encoding="utf-8",
            )
            drift = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--check",
                    "--baseline",
                    str(baseline),
                    ".codex",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(drift.returncode, 1)
            self.assertIn("LOG_SURFACE_FIELD_ADDED", drift.stdout)
            self.assertIn("SECOND_FIELD", drift.stdout)

            subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--output",
                    "documents/log-surface-inventory.json",
                    "--quiet",
                    ".codex",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            clean = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--check",
                    "--baseline",
                    str(baseline),
                    "--quiet",
                    ".codex",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(clean.returncode, 0)
            self.assertEqual(clean.stdout, "")

            hook.write_text(
                "\nprint('FIRST_FIELD=1')\nprint('SECOND_FIELD=2')\n",
                encoding="utf-8",
            )
            line_only_move = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--check",
                    "--baseline",
                    str(baseline),
                    "--quiet",
                    ".codex",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(line_only_move.returncode, 0)
            self.assertEqual(line_only_move.stdout, "")

    def test_check_uses_vendored_baseline_when_root_baseline_is_absent(self) -> None:
        """Derived repos should check the AgentCanon baseline under vendor/."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            canon = root / "vendor" / "agent-canon"
            hook = canon / ".codex" / "hooks" / "sample.py"
            hook.parent.mkdir(parents=True)
            hook.write_text("print('VENDORED_FIELD=1')\n", encoding="utf-8")

            subprocess.run(
                ["git", "init"],
                cwd=canon,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "add", ".codex/hooks/sample.py"],
                cwd=canon,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(canon),
                    "--output",
                    "documents/log-surface-inventory.json",
                    "--quiet",
                    ".codex",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--check",
                    "--quiet",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_discovers_surfaces_without_git_metadata(self) -> None:
        """Inventory should still work in mounted containers where git is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            hook = root / ".codex" / "hooks" / "sample.py"
            hook.parent.mkdir(parents=True)
            hook.write_text("print('NO_GIT_FIELD=1')\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        fields = {record["field"] for record in payload["records"]}
        self.assertIn("NO_GIT_FIELD", fields)


if __name__ == "__main__":
    unittest.main()
