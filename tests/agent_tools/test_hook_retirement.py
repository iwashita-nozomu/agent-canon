# @dependency-start
# contract test
# responsibility Tests the native hook-retirement manifest and caller checker.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_retirement.rs owns typed retirement records and caller closure.
# @dependency-end
"""Focused tests for the native hook-retirement guard."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "hook_retirement"
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI") or os.environ.get(
    "AGENT_CANON_NATIVE_BIN"
)


def native_cli() -> str:
    if not AGENT_CANON_CLI:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return AGENT_CANON_CLI


class HookRetirementTest(unittest.TestCase):
    def run_checker(
        self, root: Path, *args: str
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        result = subprocess.run(
            [native_cli(), "hook-retirement-check", "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertTrue(result.stdout.endswith("\n"), result.stdout)
        payload = json.loads(result.stdout)
        self.assertIsInstance(payload, dict)
        return result, payload

    def test_manifest_counts_and_digest(self) -> None:
        result, payload = self.run_checker(PROJECT_ROOT, "--contract")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(payload["retired_child_tombstones"]), 23)
        self.assertEqual(len(payload["moved_source_absences"]), 1)
        self.assertEqual(payload["counts"]["retired_filenames"], 24)
        self.assertRegex(payload["source_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            payload["caller_audit"]["schema"],
            "agent-canon.hook-retirement-caller-audit.v1",
        )

    def test_actual_tree_distinguishes_moved_safety_source_from_retired_children(self) -> None:
        """The moved safety owner is allowed while its old hook path remains absent."""
        result, payload = self.run_checker(PROJECT_ROOT, "--check")
        caller_audit = payload["caller_audit"]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["missing_files"], [])
        self.assertEqual(payload["executable_references"], [])
        self.assertFalse((PROJECT_ROOT / ".codex" / "hooks" / "hook_safety.py").exists())
        self.assertTrue(
            (PROJECT_ROOT / "tools" / "runtime" / "authority" / "hook_safety.py").is_file()
        )
        self.assertEqual(caller_audit["moved_source_old_paths"], [".codex/hooks/hook_safety.py"])
        self.assertNotIn("hook_safety.py", caller_audit["retired_child_basenames"])

    def test_clean_and_violation_fixtures_keep_their_retirement_contract(self) -> None:
        clean_result, clean_payload = self.run_checker(FIXTURE_ROOT / "clean", "--check")
        self.assertEqual(
            clean_result.returncode, 0, clean_result.stdout + clean_result.stderr
        )
        self.assertEqual(clean_payload["missing_files"], [])
        self.assertEqual(clean_payload["executable_references"], [])
        self.assertEqual(
            clean_payload["active_events"],
            ["UserPromptSubmit", "PreToolUse", "PostToolUse"],
        )

        violation_result, violation_payload = self.run_checker(
            FIXTURE_ROOT / "violation", "--check"
        )
        self.assertEqual(violation_result.returncode, 1, violation_result.stdout)
        self.assertEqual(
            violation_payload["missing_files"],
            [".codex/hooks/branch_worktree_guard.py"],
        )
        self.assertEqual(violation_payload["active_events"], ["Stop"])
        self.assertEqual(
            violation_result.stderr,
            "hook retirement check failed: missing_files,active_events\n",
        )


if __name__ == "__main__":
    unittest.main()
