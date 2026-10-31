"""Tests for the shared work-log appender."""

# @dependency-start
# contract test
# responsibility Tests run-local work-log CLI behavior against the native owner.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/work_log.rs appends run-local logs
# upstream implementation ../../tools/runtime/archive/work_log.py supplies the independent local-clock oracle
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def _native_command(*arguments: str) -> list[str]:
    assert AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
    executable = Path(AGENT_CANON_CLI)
    assert (
        executable.is_absolute()
        and executable.is_file()
        and os.access(executable, os.X_OK)
    )
    return [str(executable), "work-log", *arguments]


def _timestamp_from_output(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    entry = next(
        line for line in result.stdout.splitlines() if line.startswith("`")
    )
    return entry[1:].split(" | ", 1)[0]


class WorkLogTest(unittest.TestCase):
    """Verify run-local and worktree log updates."""

    def test_report_dir_only_updates_run_bundle_work_log(self) -> None:
        """Explicit report-dir mode should append the run-local work log."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            runtime_root = Path(tmp_dir) / "runtime"
            report_dir = runtime_root / "reports" / "agents" / "run-1"
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
                _native_command(
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--runtime-root",
                    str(runtime_root),
                    "--kind",
                    "edit",
                    "--request-clause-id",
                    "R1",
                    "--message",
                    "updated docs",
                    "--next",
                    "run tests",
                ),
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
            runtime_root = Path(tmp_dir) / "runtime"
            # Full checks supply a runtime root, so keep the active pointer external too.
            report_dir = runtime_root / "reports" / "agents" / "run-2"
            report_dir.mkdir(parents=True, exist_ok=True)
            active_pointer = runtime_root / "reports" / "agents" / ".active_run"
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
                _native_command(
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
                ),
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "ran targeted pytest",
                (report_dir / "work_log.md").read_text(encoding="utf-8"),
            )

    def test_report_dir_allows_explicit_pre_contract_entry_without_clause_id(
        self,
    ) -> None:
        """Run-bundle preflight notes can be recorded before clauses exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            runtime_root = Path(tmp_dir) / "runtime"
            report_dir = runtime_root / "reports" / "agents" / "run-3"

            result = subprocess.run(
                _native_command(
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--runtime-root",
                    str(runtime_root),
                    "--kind",
                    "preflight",
                    "--allow-missing-request-clause-id",
                    "--missing-request-clause-reason",
                    "contract not created yet",
                    "--message",
                    "checked MCP inventory",
                ),
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            work_log_text = (report_dir / "work_log.md").read_text(encoding="utf-8")
            self.assertIn("checked MCP inventory", work_log_text)
            self.assertIn("request_clause_ids: unassigned", work_log_text)
            self.assertIn(
                "missing_request_clause_reason: contract not created yet", work_log_text
            )

    def test_missing_clause_id_still_requires_explicit_reason(self) -> None:
        """Clause-free logging must be an explicit exception."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            runtime_root = Path(tmp_dir) / "runtime"
            report_dir = runtime_root / "reports" / "agents" / "run-4"

            result = subprocess.run(
                _native_command(
                    "--workspace-root",
                    str(workspace_root),
                    "--report-dir",
                    str(report_dir),
                    "--runtime-root",
                    str(runtime_root),
                    "--kind",
                    "preflight",
                    "--allow-missing-request-clause-id",
                    "--message",
                    "checked MCP inventory",
                ),
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--missing-request-clause-reason is required", result.stderr)

    def test_native_timestamp_uses_the_host_local_clock(self) -> None:
        """Compare native minute stamps to the retained Python owner in child TZs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime_root = Path(tmp_dir) / "runtime"
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir()
            zones = [None] if os.name == "nt" else ["UTC", "Asia/Tokyo"]

            for zone_index, timezone in enumerate(zones):
                child_env = os.environ.copy()
                if timezone is not None:
                    child_env["TZ"] = timezone
                else:
                    child_env.pop("TZ", None)

                def run(owner: str, sample: int) -> subprocess.CompletedProcess[str]:
                    run_id = f"clock-{zone_index}-{sample}"
                    common = [
                        "--workspace-root",
                        str(workspace_root),
                        "--report-dir",
                        str(runtime_root / "reports" / "agents" / run_id),
                        "--runtime-root",
                        str(runtime_root),
                        "--request-clause-id",
                        "CLOCK-1",
                        "--message",
                        "sample local timestamp",
                    ]
                    command = (
                        [
                            sys.executable,
                            "-m",
                            "tools.runtime.archive.work_log",
                            *common,
                        ]
                        if owner == "python"
                        else _native_command(*common)
                    )
                    return subprocess.run(
                        command,
                        cwd=PROJECT_ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                        env=child_env,
                    )

                before = _timestamp_from_output(run("python", 0))
                native = _timestamp_from_output(run("native", 1))
                after = _timestamp_from_output(run("python", 2))
                self.assertIn(
                    native,
                    {before, after},
                    f"native local-clock stamp diverged for TZ={timezone!r}",
                )


if __name__ == "__main__":
    unittest.main()
