"""Regression tests for AgentTeam state outside the AgentCanon source tree."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.agent_tools.task_authority import (  # noqa: E402
    AUTHORITY_FILE_NAME,
    find_authority_path,
)
from tools.agent_tools.workflow_monitor import (  # noqa: E402
    MonitoringEntries,
    append_monitoring,
)
from tools.agent_tools.workspace_scope import (  # noqa: E402
    resolve_report_root,
)
from tools.agent_tools.runtime_artifacts import RuntimeRootRequired  # noqa: E402


class AgentTeamRuntimeBoundaryTest(unittest.TestCase):
    """Ensure reports, pointers, ledgers, and authority stay external."""

    def test_default_report_root_requires_explicit_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            old = os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
            try:
                with self.assertRaises(RuntimeRootRequired):
                    resolve_report_root(None, source)
            finally:
                if old is not None:
                    os.environ["AGENT_CANON_RUNTIME_ROOT"] = old

    def test_two_external_runs_are_isolated_and_source_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir()
            source_file = source / "tracked.txt"
            source_file.write_text("before\n", encoding="utf-8")
            before = source_file.read_bytes()
            os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
            try:
                report_root = resolve_report_root(None, source)
                run_a = report_root / "run-a"
                run_b = report_root / "run-b"
                for run in (run_a, run_b):
                    run.mkdir(parents=True)
                    (run / "schedule.md").write_text(
                        "# Schedule\n\n## Agent Wave Ledger\n\n",
                        encoding="utf-8",
                    )
                    append_monitoring(
                        run,
                        MonitoringEntries(signals=(f"run={run.name}",)),
                    )
                self.assertIn("run=run-a", (run_a / "workflow_monitoring.md").read_text())
                self.assertNotIn("run=run-b", (run_a / "workflow_monitoring.md").read_text())
                self.assertIn("run=run-b", (run_b / "workflow_monitoring.md").read_text())
                self.assertEqual(source_file.read_bytes(), before)
                self.assertFalse((source / "reports").exists())
            finally:
                os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)

    def test_active_pointer_and_authority_are_external(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            run = runtime / "reports" / "agents" / "run-1"
            run.mkdir(parents=True)
            (runtime / "reports" / "agents" / ".active_run").write_text(
                str(run) + "\n", encoding="utf-8"
            )
            (run / AUTHORITY_FILE_NAME).write_text(
                "version: 1\nrun_id: run-1\n", encoding="utf-8"
            )
            old = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
            os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
            try:
                self.assertEqual(find_authority_path(root / "project"), run / AUTHORITY_FILE_NAME)
            finally:
                if old is None:
                    os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
                else:
                    os.environ["AGENT_CANON_RUNTIME_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
