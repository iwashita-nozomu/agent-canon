"""Tests for the shared work-log appender."""

# @dependency-start
# contract test
# responsibility Tests test work log behavior.
# upstream implementation ../../tools/agent_tools/work_log.py appends run-local logs
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORK_LOG_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "work_log.py"


class WorkLogTest(unittest.TestCase):
    """Verify run-local and worktree log updates."""

    def test_report_dir_only_updates_run_bundle_work_log(self) -> None:
        """Explicit report-dir mode should append the run-local work log."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = workspace_root / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORK_LOG_SCRIPT),
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--kind",
                    "edit",
                    "--request-clause-id",
                    "R1",
                    "--message",
                    "updated docs",
                    "--next",
                    "run tests",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WORK_LOG=", result.stdout)
            work_log_text = (report_dir / "work_log.md").read_text(encoding="utf-8")
            self.assertIn("updated docs", work_log_text)
            self.assertIn("request_clause_ids: R1", work_log_text)

    def test_active_run_pointer_updates_run_bundle_work_log(self) -> None:
        """Active-run pointer mode should append the run-local work log."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = workspace_root / "reports" / "agents" / "run-2"
            report_dir.mkdir(parents=True, exist_ok=True)
            active_pointer = workspace_root / "reports" / "agents" / ".active_run"
            active_pointer.write_text("run-2\n", encoding="utf-8")
            (report_dir / "user_request_contract.md").write_text(
                "# User Request Contract\n",
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORK_LOG_SCRIPT),
                    "--workspace-root",
                    str(workspace_root),
                    "--kind",
                    "test",
                    "--request-clause-id",
                    "R2",
                    "--message",
                    "ran targeted pytest",
                    "--next",
                    "update closeout",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "ran targeted pytest",
                (report_dir / "work_log.md").read_text(encoding="utf-8"),
            )

    def test_report_dir_allows_explicit_pre_contract_entry_without_clause_id(self) -> None:
        """Run-bundle preflight notes can be recorded before clauses exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = workspace_root / "reports" / "agents" / "run-3"

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORK_LOG_SCRIPT),
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--kind",
                    "preflight",
                    "--allow-missing-request-clause-id",
                    "--missing-request-clause-reason",
                    "contract not created yet",
                    "--message",
                    "checked MCP inventory",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            work_log_text = (report_dir / "work_log.md").read_text(encoding="utf-8")
            self.assertIn("checked MCP inventory", work_log_text)
            self.assertIn("request_clause_ids: unassigned", work_log_text)
            self.assertIn("missing_request_clause_reason: contract not created yet", work_log_text)

    def test_missing_clause_id_still_requires_explicit_reason(self) -> None:
        """Clause-free logging must be an explicit exception."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = workspace_root / "reports" / "agents" / "run-4"

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORK_LOG_SCRIPT),
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--kind",
                    "preflight",
                    "--allow-missing-request-clause-id",
                    "--message",
                    "checked MCP inventory",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--missing-request-clause-reason is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
