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
                root, "--root-only", "--json-out", str(json_out), "--markdown-out", str(markdown_out)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertEqual(payload["scopes"][0]["entries"][0]["path"], "product.md")
            self.assertNotIn("projection_producer", payload["scopes"][0]["entries"][0])
            self.assertIn("## Scope Summary", markdown_out.read_text(encoding="utf-8"))

    def test_agentcanon_only_uses_selected_source_root(self) -> None:
        """AgentCanon-only mode inventories the supplied source root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "README.md").write_text("# Canon\n", encoding="utf-8")
            self.init_git(root, "README.md")
            result = self.run_inventory(root, "--agentcanon-only")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FILE_SURFACE_INVENTORY_MODE=agentcanon-only", result.stdout)
            self.assertIn("FILE_SURFACE_INVENTORY_FILES=1", result.stdout)

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
            paths = [entry["path"] for entry in json.loads(output.read_text(encoding="utf-8"))["scopes"][0]["entries"]]
            self.assertEqual(paths, ["kept.md", "untracked.py"])

    def run_inventory(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run inventory through the explicitly selected native CLI."""
        self.assertIsNotNone(AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable")
        return subprocess.run(
            [str(AGENT_CANON_CLI), "file-surface-inventory", "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def init_git(self, root: Path, *paths: str) -> None:
        """Initialize a fixture repository and track selected paths."""
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "add", *paths], cwd=root, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
