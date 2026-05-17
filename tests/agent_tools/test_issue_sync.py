"""Tests for local issue and GitHub sync planning."""

# @dependency-start
# responsibility Tests local issue validation and sync planning.
# upstream implementation ../../tools/agent_tools/issue_sync.py validates issue files
# upstream design ../../issues/README.md durable issue convention
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "issue_sync.py"


class IssueSyncTest(unittest.TestCase):
    """Exercise local issue validation and sync planning."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the issue sync checker."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical local issue store is structurally valid."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ISSUE_SYNC=pass", result.stdout)

    def test_missing_required_field_fails(self) -> None:
        """Local issue files must keep required fields."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(root, "open", "AC-20260517-test-issue")
            issue.write_text(
                issue.read_text(encoding="utf-8").replace("edit_scope:", "scope:"),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing:edit_scope", result.stdout)

    def test_require_github_link_fails_when_missing(self) -> None:
        """Optional GitHub mirror links can be made mandatory by flag."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--require-github-link")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing-github_issue", result.stdout)

    def test_sync_plan_lists_unlinked_issue(self) -> None:
        """The checker prints a deterministic gh command plan for unlinked issues."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--repo", "owner/repo")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_PLAN=AC-20260517-test-issue:gh issue create", result.stdout)
            self.assertIn("--repo owner/repo", result.stdout)

    def write_issue(self, root: Path, state: str, issue_id: str) -> Path:
        """Write one local issue file."""
        path = root / "issues" / state / f"{issue_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "resolved" if state == "closed" else "open"
        resolved_by = "resolved_by: fixture\n" if state == "closed" else ""
        path.write_text(
            "\n".join(
                [
                    "# Test Issue",
                    "",
                    f"issue_id: {issue_id}",
                    f"status: {status}",
                    "source: user",
                    "severity: S1",
                    "evidence: fixture",
                    "affected_surfaces: tools/example.py",
                    "edit_scope: tools/example.py",
                    "required_action: Fix the fixture.",
                    "close_condition: The fixture passes.",
                    resolved_by.rstrip(),
                    "",
                ]
            ).replace("\n\n\n", "\n\n"),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
