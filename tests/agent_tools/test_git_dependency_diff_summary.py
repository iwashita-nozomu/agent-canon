"""Tests for Git diff and dependency summary aggregation."""

# @dependency-start
# contract test
# responsibility Tests Git diff and dependency summary aggregation tool behavior.
# upstream implementation ../../tools/agent_tools/git_dependency_diff_summary.py summarizes Git diffs with dependency expansion.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "git_dependency_diff_summary.py"

if str(TOOL.parent) not in sys.path:
    sys.path.insert(0, str(TOOL.parent))

import git_dependency_diff_summary as summary_tool  # noqa: E402


class GitDependencyDiffSummaryTest(unittest.TestCase):
    """Exercise the diff summary tool without running heavyweight dependency review."""

    def test_parse_name_status_keeps_rename_source(self) -> None:
        """Rename rows retain old and new paths."""
        rows = summary_tool.parse_name_status("M\talpha.py\nR100\told.py\tnew.py\n")

        self.assertEqual(rows[0].status, "M")
        self.assertEqual(rows[0].path, "alpha.py")
        self.assertEqual(rows[1].status, "R100")
        self.assertEqual(rows[1].old_path, "old.py")
        self.assertEqual(rows[1].path, "new.py")

    def test_parse_name_status_z_preserves_tab_in_path(self) -> None:
        """NUL-delimited name-status rows preserve tabs in paths."""
        rows = summary_tool.parse_name_status_z(b"M\x00tab\tname.py\x00")

        self.assertEqual(rows[0].status, "M")
        self.assertEqual(rows[0].path, "tab\tname.py")

    def test_parse_numstat_handles_binary_rows(self) -> None:
        """Binary numstat rows keep counts empty and mark binary."""
        stats = summary_tool.parse_numstat(
            "3\t4\talpha.py\n-\t-\timage.bin\n1\t0\told.py => new.py\n"
        )

        self.assertEqual(stats["alpha.py"], (3, 4, False))
        self.assertEqual(stats["image.bin"], (None, None, True))
        self.assertEqual(stats["new.py"], (1, 0, False))

    def test_parse_numstat_z_keys_renames_by_current_path(self) -> None:
        """Rename numstat rows use the new path as the stat key."""
        stats = summary_tool.parse_numstat_z(b"1\t0\t\x00old.py\x00new.py\x00")

        self.assertEqual(stats["new.py"], (1, 0, False))
        self.assertNotIn("old.py", stats)

    def test_parse_numstat_z_preserves_tab_in_path(self) -> None:
        """NUL-delimited numstat rows preserve tab characters in paths."""
        stats = summary_tool.parse_numstat_z(b"2\t1\ttab\tname.py\x00")

        self.assertEqual(stats["tab\tname.py"], (2, 1, False))

    def test_changed_file_list_includes_rename_source(self) -> None:
        """Dependency expansion seeds include both sides of a rename."""
        rows = [
            summary_tool.ChangedPath(status="R100", old_path="old.py", path="new.py")
        ]

        self.assertEqual(summary_tool.changed_file_list(rows), ["new.py", "old.py"])

    def test_cli_summarizes_worktree_diff_as_json(self) -> None:
        """The CLI reports modified and untracked files for a worktree diff."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
            subprocess.run(
                ("git", "config", "user.email", "test@example.com"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ("git", "config", "user.name", "Test User"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "alpha.py").write_text("value = 1\n", encoding="utf-8")
            subprocess.run(
                ("git", "add", "alpha.py"), cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                ("git", "commit", "-m", "initial"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "alpha.py").write_text("value = 2\n", encoding="utf-8")
            (root / "beta.py").write_text("import alpha\n", encoding="utf-8")
            report_dir = root / "report"

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--skip-code-dependencies",
                    "--skip-dependency-review",
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], summary_tool.SCHEMA)
            paths = {row["path"] for row in payload["changed_files"]}
            self.assertEqual(paths, {"alpha.py", "beta.py"})
            self.assertTrue((report_dir / "summary.md").is_file())

    def test_cli_preserves_rename_stats_and_seed_paths(self) -> None:
        """The CLI preserves rename line counts and dependency seeds."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
            subprocess.run(
                ("git", "config", "user.email", "test@example.com"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ("git", "config", "user.name", "Test User"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "old.py").write_text("value = 1\n", encoding="utf-8")
            subprocess.run(
                ("git", "add", "old.py"), cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                ("git", "commit", "-m", "initial"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ("git", "mv", "old.py", "new.py"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "new.py").write_text("value = 1\nextra = 2\n", encoding="utf-8")
            report_dir = root / "report"

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--skip-code-dependencies",
                    "--skip-dependency-review",
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            row = payload["changed_files"][0]
            self.assertTrue(row["status"].startswith("R"))
            self.assertEqual(row["old_path"], "old.py")
            self.assertEqual(row["path"], "new.py")
            self.assertEqual(row["additions"], 1)
            self.assertEqual(row["deletions"], 0)
            changed_seed_paths = (report_dir / "changed_files.txt").read_text(
                encoding="utf-8"
            )
            self.assertEqual(changed_seed_paths.splitlines(), ["new.py", "old.py"])

    def test_cli_preserves_tab_path_stats(self) -> None:
        """The CLI preserves stats for paths containing tab characters."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
            subprocess.run(
                ("git", "config", "user.email", "test@example.com"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ("git", "config", "user.name", "Test User"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            path = root / "tab\tname.py"
            path.write_text("value = 1\n", encoding="utf-8")
            subprocess.run(
                ("git", "add", "tab\tname.py"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ("git", "commit", "-m", "initial"),
                cwd=root,
                check=True,
                capture_output=True,
            )
            path.write_text("value = 1\nextra = 2\n", encoding="utf-8")
            report_dir = root / "report"

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--report-dir",
                    str(report_dir),
                    "--skip-code-dependencies",
                    "--skip-dependency-review",
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            row = payload["changed_files"][0]
            self.assertEqual(row["path"], "tab\tname.py")
            self.assertEqual(row["additions"], 1)
            self.assertEqual(row["deletions"], 0)


if __name__ == "__main__":
    unittest.main()
