# @dependency-start
# contract test
# responsibility Tests the native hook-retirement manifest, caller checker, and captured Python CLI contract.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_retirement.rs owns typed retirement records and caller closure.
# upstream reference ../../tests/fixtures/hook_retirement/python_golden.json freezes the old CLI outcomes.
# @dependency-end
"""Focused tests for the native hook-retirement guard."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "hook_retirement"
GOLDEN_PATH = FIXTURE_ROOT / "python_golden.json"
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI") or os.environ.get(
    "AGENT_CANON_NATIVE_BIN"
)


def native_cli() -> str:
    if not AGENT_CANON_CLI:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return str(Path(AGENT_CANON_CLI).absolute())


class HookRetirementTest(unittest.TestCase):
    def materialize_fixture(self, name: str, root: Path) -> None:
        """Build the repository paths read by the checker from fixture assets."""
        fixture = FIXTURE_ROOT / name
        root.mkdir(parents=True)
        for relative in (".codex", "tools", "templates"):
            (root / relative).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture / "hooks.json", root / ".codex" / "hooks.json")
        shutil.copyfile(fixture / "catalog.yaml", root / "tools" / "catalog.yaml")
        shutil.copyfile(fixture / "template.md", root / "templates" / "example.md")

        inventory = json.loads((fixture / "inventory.json").read_text(encoding="utf-8"))
        retired_path = inventory.get("path")
        if retired_path:
            relative = Path(retired_path)
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()

    def materialize_golden_case(self, case: dict[str, Any], root: Path) -> None:
        root.mkdir(parents=True)
        for item in case["files"]:
            relative = Path(item["path"])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(item["base64"], validate=True))

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

    def test_actual_tree_distinguishes_moved_safety_source_from_retired_children(
        self,
    ) -> None:
        """The moved safety owner is allowed while its old hook path remains absent."""
        result, payload = self.run_checker(PROJECT_ROOT, "--check")
        caller_audit = payload["caller_audit"]

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload["missing_files"], [])
        self.assertEqual(payload["executable_references"], [])
        self.assertFalse(
            (PROJECT_ROOT / ".codex" / "hooks" / "hook_safety.py").exists()
        )
        self.assertTrue(
            (
                PROJECT_ROOT / "tools" / "runtime" / "authority" / "hook_safety.py"
            ).is_file()
        )
        self.assertEqual(
            caller_audit["moved_source_old_paths"], [".codex/hooks/hook_safety.py"]
        )
        self.assertNotIn("hook_safety.py", caller_audit["retired_child_basenames"])

    def test_clean_and_violation_fixtures_keep_their_retirement_contract(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            scratch_root = Path(scratch)
            clean_root = scratch_root / "clean"
            self.materialize_fixture("clean", clean_root)
            clean_result, clean_payload = self.run_checker(clean_root, "--check")
            self.assertEqual(
                clean_result.returncode, 0, clean_result.stdout + clean_result.stderr
            )
            self.assertEqual(clean_payload["missing_files"], [])
            self.assertEqual(clean_payload["executable_references"], [])
            self.assertEqual(
                clean_payload["active_events"],
                ["UserPromptSubmit", "PreToolUse", "PostToolUse"],
            )

            violation_root = scratch_root / "violation"
            self.materialize_fixture("violation", violation_root)
            violation_result, violation_payload = self.run_checker(
                violation_root, "--check"
            )
            self.assertEqual(violation_result.returncode, 1, violation_result.stdout)
            self.assertEqual(
                violation_payload["missing_files"],
                [".codex/hooks/branch_worktree_guard.py"],
            )
            self.assertEqual(
                violation_payload["executable_references"],
                [
                    {
                        "path": "templates/example.md",
                        "line": 9,
                        "retirement_kind": "retired_child_basename",
                        "token": "branch_worktree_guard.py",
                    },
                    {
                        "path": "tools/catalog.yaml",
                        "line": 6,
                        "retirement_kind": "retired_child_basename",
                        "token": "branch_worktree_guard.py",
                    },
                ],
            )
            self.assertEqual(violation_payload["active_events"], ["Stop"])
            self.assertEqual(
                violation_result.stderr,
                "hook retirement check failed: missing_files,executable_references,active_events\n",
            )

    def test_frozen_python_cli_corpus(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(golden["source"], "cdf54b674130cd9b058e6848b8fd815b6ea8bfa6")
        self.assertEqual(
            golden["checker_sha256"],
            "ae219e553c0040bc283fb5fc02a52e97165a621e15699cf3007df4e70362d487",
        )
        self.assertEqual(
            golden["manifest_sha256"],
            "dbc88be54c629fc3b36026064eb0aa79b5f4100504d85b335eda8a5d901cb68f",
        )
        self.assertEqual(
            [case["name"] for case in golden["cases"]],
            [
                "clean",
                "retired-and-reference",
                "unicode-lines",
                "invalid-utf8",
                "invalid-hooks",
            ],
        )

        run_count = 0
        with tempfile.TemporaryDirectory() as scratch:
            for case in golden["cases"]:
                case_root = Path(scratch) / case["name"]
                with self.subTest(case=case["name"]):
                    self.materialize_golden_case(case, case_root)
                    for run in case["runs"]:
                        run_count += 1
                        with self.subTest(case=case["name"], args=run["args"]):
                            result = subprocess.run(
                                [
                                    native_cli(),
                                    "hook-retirement-check",
                                    *run["args"],
                                ],
                                cwd=case_root,
                                check=False,
                                capture_output=True,
                                text=True,
                                encoding="utf-8",
                            )
                            self.assertEqual(result.returncode, run["exit"])
                            expected = run["stdout"]
                            digest_proof = json.loads(
                                (
                                    PROJECT_ROOT
                                    / "tests/fixtures/codex_runtime_summary/retirement_digest.json"
                                ).read_text(encoding="utf-8")
                            )
                            self.assertEqual(
                                digest_proof["old_digest"],
                                "7fe7b7ea25b13567ba27aa93235da043460df83132162818b93236fa4c4369b9",
                            )
                            relocations = [
                                (
                                    '"owner":"tools/runtime/archive/export_codex_runtime_summary.py"',
                                    '"owner":"tools/runtime/dispatch/agent-canon/src/codex_runtime_summary.rs"',
                                ),
                                (
                                    '"command_or_skill":"command-only:python3 tools/runtime/archive/export_codex_runtime_summary.py"',
                                    '"command_or_skill":"command-only:tools/bin/agent-canon export-codex-runtime-summary"',
                                ),
                                (
                                    digest_proof["old_digest"],
                                    digest_proof["new_digest"],
                                ),
                            ]
                            for old, new in relocations:
                                self.assertEqual(expected.count(old), 1)
                                expected = expected.replace(old, new)
                            self.assertEqual(result.stdout, expected)
                            self.assertEqual(result.stderr, run["stderr"])
        self.assertEqual(run_count, 7)


if __name__ == "__main__":
    unittest.main()
