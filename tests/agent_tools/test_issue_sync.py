"""Tests for local issue and GitHub sync planning."""

# @dependency-start
# contract test
# responsibility Tests local issue validation and sync planning.
# upstream implementation ../../tools/agent_tools/issue_sync.py validates issue files
# upstream design ../../issues/README.md durable issue convention
# @dependency-end

from __future__ import annotations

import os
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

    def run_checker_with_env(
        self,
        root: Path,
        env: dict[str, str],
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run the issue sync checker with an explicit environment."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
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

    def test_github_check_passes_for_matching_link(self) -> None:
        """Read-only GitHub checks should pass when the mirror matches local state."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(
                root,
                title="Test Issue",
                body=issue.read_text(encoding="utf-8"),
                state="OPEN",
            )

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_GITHUB_CHECKED=1", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=0", result.stdout)

    def test_github_check_fails_on_state_drift(self) -> None:
        """Read-only GitHub checks should fail on linked mirror drift."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            issue = self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(
                root,
                title="Test Issue",
                body=issue.read_text(encoding="utf-8"),
                state="CLOSED",
            )

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("state-drift:expected=OPEN:actual=CLOSED", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=1", result.stdout)

    def test_github_check_fails_on_body_drift(self) -> None:
        """Read-only GitHub checks should fail when the mirror body is stale."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_fake_gh(root, title="Test Issue", body="stale body", state="OPEN")

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("body-drift", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=1", result.stdout)

    def test_github_check_can_treat_auth_failure_as_unavailable(self) -> None:
        """Actions read-only checks should not block when GitHub auth is unavailable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_issue(
                root,
                "open",
                "AC-20260517-test-issue",
                github_issue="https://github.com/owner/repo/issues/7",
            )
            bin_dir = self.write_failing_gh(root, "HTTP 401: Bad credentials (https://api.github.com/graphql)")

            result = self.run_checker_with_env(
                root,
                self.env_with_path(bin_dir),
                "--repo",
                "owner/repo",
                "--github-check",
                "--allow-github-auth-unavailable",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ISSUE_SYNC_GITHUB_CHECKED=0", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_DRIFT=0", result.stdout)
            self.assertIn("ISSUE_SYNC_GITHUB_UNAVAILABLE=1", result.stdout)
            self.assertIn("ISSUE_SYNC=pass", result.stdout)

    def test_summary_file_records_issue_mirror_status(self) -> None:
        """The checker can append a readable issue mirror summary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            summary = root / "summary.md"
            self.write_issue(root, "open", "AC-20260517-test-issue")

            result = self.run_checker(root, "--summary-file", str(summary))
            text = summary.read_text(encoding="utf-8")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("## Issue Mirror Check", text)
            self.assertIn("missing_github_links: `1`", text)

    def write_issue(
        self,
        root: Path,
        state: str,
        issue_id: str,
        *,
        github_issue: str = "",
    ) -> Path:
        """Write one local issue file."""
        path = root / "issues" / state / f"{issue_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        status = "resolved" if state == "closed" else "open"
        resolved_by = "resolved_by: fixture\n" if state == "closed" else ""
        github_line = f"github_issue: {github_issue}" if github_issue else ""
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
                    github_line,
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

    def write_fake_gh(self, root: Path, *, title: str, body: str, state: str) -> Path:
        """Write a fake gh executable for deterministic GitHub check tests."""
        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json",
                    "import sys",
                    "if sys.argv[1:3] == ['issue', 'view']:",
                    "    print(json.dumps("
                    f"{{'number': 7, 'title': {title!r}, 'body': {body!r}, "
                    f"'state': {state!r}, 'url': 'https://github.com/owner/repo/issues/7'}}"
                    "))",
                    "    raise SystemExit(0)",
                    "raise SystemExit('unexpected gh command: ' + ' '.join(sys.argv[1:]))",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return bin_dir

    def write_failing_gh(self, root: Path, message: str) -> Path:
        """Write a fake gh executable that fails with one message."""
        bin_dir = root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import sys",
                    f"print({message!r}, file=sys.stderr)",
                    "raise SystemExit(1)",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return bin_dir

    def env_with_path(self, bin_dir: Path) -> dict[str, str]:
        """Return an environment that resolves the fake gh first."""
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
        return env


if __name__ == "__main__":
    unittest.main()
