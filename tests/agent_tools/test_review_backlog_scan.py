"""Tests for the integrated review backlog scan wrapper."""

# @dependency-start
# responsibility Tests integrated review backlog scan reporting behavior.
# upstream implementation ../../tools/agent_tools/review_backlog_scan.sh runs scan wrapper
# upstream implementation ../../tools/agent_tools/file_surface_inventory.py writes inventory reports
# upstream design ../../tools/static_analysis/common/README.md documents scan entrypoint
# @dependency-end

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REVIEW_SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "review_backlog_scan.sh"


class ReviewBacklogScanTest(unittest.TestCase):
    """Verify integrated backlog scan behavior."""

    def test_inventory_check_writes_json_markdown_and_summary(self) -> None:
        """The inventory check should produce machine and human reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports"
            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(PROJECT_ROOT),
                    "--report-dir",
                    str(report_dir),
                    "--agentcanon-only",
                    "--check",
                    "inventory",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REVIEW_BACKLOG_SCAN=pass", result.stdout)
            self.assertTrue((report_dir / "file_surface_inventory.json").is_file())
            self.assertTrue((report_dir / "file_surface_inventory.md").is_file())
            summary = (report_dir / "review_backlog_scan.md").read_text(encoding="utf-8")
            self.assertIn("| inventory | 0 |", summary)

    def test_stale_search_excludes_git_paths(self) -> None:
        """The rg-based stale search should not read .git object databases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            git_object = root / ".git" / "objects" / "aa" / "leak.txt"
            git_object.parent.mkdir(parents=True)
            git_object.write_text("subtree legacy format\n", encoding="utf-8")
            (root / "README.md").write_text("# Clean\n", encoding="utf-8")
            report_dir = root / "reports"

            result = subprocess.run(
                [
                    "bash",
                    str(REVIEW_SCAN),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--root-only",
                    "--check",
                    "stale",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            stale_output = (report_dir / "stale_wording_search.txt").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("leak.txt", stale_output)
            self.assertIn("STALE_WORDING_SEARCH=no-matches", stale_output)


if __name__ == "__main__":
    unittest.main()
