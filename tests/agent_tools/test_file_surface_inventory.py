"""Tests for file surface inventory reports."""

# @dependency-start
# responsibility Tests file surface inventory scope classification.
# upstream implementation ../../tools/agent_tools/file_surface_inventory.py builds inventory reports
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared surface model
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = PROJECT_ROOT / "tools" / "agent_tools" / "file_surface_inventory.py"


class FileSurfaceInventoryTest(unittest.TestCase):
    """Verify root/submodule inventory behavior."""

    def test_submodule_aware_inventory_writes_json_and_markdown(self) -> None:
        """Inventory reports should classify root and AgentCanon surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "product.md").write_text("# Product\n", encoding="utf-8")
            canon_tools = root / "vendor" / "agent-canon" / "tools"
            canon_tools.mkdir(parents=True)
            (canon_tools / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tools").symlink_to(canon_tools, target_is_directory=True)
            json_out = root / "reports" / "inventory.json"
            markdown_out = root / "reports" / "inventory.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--submodule-aware",
                    "--json-out",
                    str(json_out),
                    "--markdown-out",
                    str(markdown_out),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FILE_SURFACE_INVENTORY=pass", result.stdout)
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            scopes = {scope["name"]: scope for scope in payload["scopes"]}
            self.assertIn("root", scopes)
            self.assertIn("agentcanon", scopes)
            root_kinds = {
                entry["path"]: entry["kind"] for entry in scopes["root"]["entries"]
            }
            canon_kinds = {
                entry["path"]: entry["kind"]
                for entry in scopes["agentcanon"]["entries"]
            }
            self.assertEqual(root_kinds["tools"], "agentcanon_tool_view")
            self.assertEqual(canon_kinds["tools/tool.py"], "agentcanon_tool_source")
            self.assertIn("## Scope Summary", markdown_out.read_text(encoding="utf-8"))

    def test_agentcanon_only_uses_vendor_source_when_present(self) -> None:
        """AgentCanon-only scope should target vendor/agent-canon in derived repos."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            canon = root / "vendor" / "agent-canon"
            canon.mkdir(parents=True)
            (canon / "README.md").write_text("# Canon\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--agentcanon-only",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("FILE_SURFACE_INVENTORY_MODE=agentcanon-only", result.stdout)
            self.assertIn("FILE_SURFACE_INVENTORY_FILES=1", result.stdout)

    def test_git_inventory_includes_untracked_and_skips_deleted(self) -> None:
        """Inventory should describe the current worktree, including untracked paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "kept.md").write_text("# Kept\n", encoding="utf-8")
            deleted = root / "deleted.md"
            deleted.write_text("# Deleted\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "add", "kept.md", "deleted.md"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            deleted.unlink()
            (root / "untracked.py").write_text("VALUE = 1\n", encoding="utf-8")
            json_out = root / "inventory.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--root-only",
                    "--json-out",
                    str(json_out),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            paths = [entry["path"] for entry in payload["scopes"][0]["entries"]]
            self.assertEqual(paths, ["kept.md", "untracked.py"])


if __name__ == "__main__":
    unittest.main()
