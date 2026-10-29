"""Tests for file-surface inventory reports."""

# @dependency-start
# contract test
# responsibility Tests file-surface inventory scope classification.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/file_surface_inventory.rs builds inventory reports
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class FileSurfaceInventoryTest(unittest.TestCase):
    """Verify root and AgentCanon source inventory behavior."""

    def test_inventory_writes_json_and_markdown(self) -> None:
        """Inventory reports describe tracked files without a projection manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "product.md").write_text("# Product\n", encoding="utf-8")
            self.init_git(root, "product.md")
            json_out = root / "reports" / "inventory.json"
            markdown_out = root / "reports" / "inventory.md"
            result = self.run_inventory(
                root,
                "--root-only",
                "--json-out",
                str(json_out),
                "--markdown-out",
                str(markdown_out),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["scopes"][0]["name"], "root")
            self.assertEqual(payload["scopes"][0]["entries"][0]["path"], "product.md")
            self.assertEqual(payload["scopes"][0]["entries"][0]["scope"], "root")
            self.assertEqual(payload["scopes"][0]["entries"][0]["kind"], "product_file")
            self.assertNotIn("projection_producer", payload["scopes"][0]["entries"][0])
            self.assertIn("## Scope Summary", markdown_out.read_text(encoding="utf-8"))

    def test_agentcanon_only_uses_selected_source_root(self) -> None:
        """AgentCanon-only mode inventories the supplied source root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "README.md").write_text("# Canon\n", encoding="utf-8")
            self.init_git(root, "README.md")
            json_out = root / "inventory.json"
            result = self.run_inventory(
                root, "--agentcanon-only", "--json-out", str(json_out)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FILE_SURFACE_INVENTORY_MODE=agentcanon-only", result.stdout)
            self.assertIn("FILE_SURFACE_INVENTORY_FILES=1", result.stdout)
            scope = json.loads(json_out.read_text(encoding="utf-8"))["scopes"][0]
            self.assertEqual(scope["name"], "agentcanon")
            self.assertEqual(scope["entries"][0]["scope"], "agentcanon")
            self.assertEqual(scope["entries"][0]["kind"], "canon_source")
            self.assertEqual(scope["by_kind"], {"canon_source": 1})

    def test_missing_option_values_followed_by_flags_do_not_write_reports(self) -> None:
        """Option flags cannot be consumed as output paths or repository roots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "product.md").write_text("# Product\n", encoding="utf-8")
            self.init_git(root, "product.md")
            root_flag = root / "--root-only"
            agentcanon_flag = root / "--agentcanon-only"
            root_output = root / "root-output.json"
            for sentinel in (root_flag, agentcanon_flag, root_output):
                sentinel.write_text("preserve this file\n", encoding="utf-8")

            cases = (
                (
                    ["--root", "--root-only", "--json-out", str(root_output)],
                    root_output,
                ),
                (["--root", str(root), "--json-out", "--root-only"], root_flag),
                (
                    ["--root", str(root), "--markdown-out", "--agentcanon-only"],
                    agentcanon_flag,
                ),
            )
            self.assertIsNotNone(
                AGENT_CANON_CLI,
                "AGENT_CANON_CLI must select the current native executable",
            )
            for args, sentinel in cases:
                with self.subTest(args=args):
                    result = subprocess.run(
                        [str(AGENT_CANON_CLI), "file-surface-inventory", *args],
                        cwd=root,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        result.returncode, 2, result.stdout + result.stderr
                    )
                    self.assertEqual(
                        sentinel.read_text(encoding="utf-8"), "preserve this file\n"
                    )

    def test_help_respects_argument_order_and_inline_path_values(self) -> None:
        """Help is an action in argument order; inline output values remain paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "product.md").write_text("# Product\n", encoding="utf-8")
            self.init_git(root, "product.md")
            output = root / "--help"
            output.write_text("preserve this file\n", encoding="utf-8")
            self.assertIsNotNone(
                AGENT_CANON_CLI,
                "AGENT_CANON_CLI must select the current native executable",
            )

            missing_value = subprocess.run(
                [
                    str(AGENT_CANON_CLI),
                    "file-surface-inventory",
                    "--root",
                    str(root),
                    "--json-out",
                    "--help",
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                missing_value.returncode, 2, missing_value.stdout + missing_value.stderr
            )
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve this file\n")

            help_result = subprocess.run(
                [str(AGENT_CANON_CLI), "file-surface-inventory", "--help"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("usage:", help_result.stdout)

            inline_path = subprocess.run(
                [
                    str(AGENT_CANON_CLI),
                    "file-surface-inventory",
                    "--root",
                    str(root),
                    "--json-out=--help",
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                inline_path.returncode, 0, inline_path.stdout + inline_path.stderr
            )
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["status"], "pass"
            )

    def test_git_inventory_skips_deleted_and_includes_untracked_files(self) -> None:
        """Inventory describes current worktree files, not deleted index entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "kept.md").write_text("# Kept\n", encoding="utf-8")
            deleted = root / "deleted.md"
            deleted.write_text("# Deleted\n", encoding="utf-8")
            self.init_git(root, "kept.md", "deleted.md")
            deleted.unlink()
            (root / "untracked.py").write_text("VALUE = 1\n", encoding="utf-8")
            output = root / "inventory.json"
            result = self.run_inventory(root, "--root-only", "--json-out", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            paths = [
                entry["path"]
                for entry in json.loads(output.read_text(encoding="utf-8"))["scopes"][
                    0
                ]["entries"]
            ]
            self.assertEqual(paths, ["kept.md", "untracked.py"])

    def run_inventory(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run inventory through the explicitly selected native CLI."""
        self.assertIsNotNone(
            AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
        )
        return subprocess.run(
            [
                str(AGENT_CANON_CLI),
                "file-surface-inventory",
                "--root",
                str(root),
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def init_git(self, root: Path, *paths: str) -> None:
        """Initialize a fixture repository and track selected paths."""
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "add", *paths], cwd=root, check=True, capture_output=True
        )


if __name__ == "__main__":
    unittest.main()
