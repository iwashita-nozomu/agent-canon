"""Tests for workflow monitoring accumulation."""

# @dependency-start
# responsibility Tests workflow monitor accumulation behavior.
# upstream implementation ../../tools/agent_tools/workflow_monitor.py appends evidence
# upstream implementation ../../tools/agent_tools/bootstrap_agent_run.py seeds evidence
# upstream implementation ../../tools/agent_tools/task_start.py seeds evidence
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONITOR_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "workflow_monitor.py"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
TASK_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_start.py"
MCP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_mcp_inventory.py"


class WorkflowMonitorTest(unittest.TestCase):
    """Verify workflow monitoring is updated mechanically."""

    def test_monitor_appends_signals_interventions_and_decisions(self) -> None:
        """The monitor CLI should update all monitored sections."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(MONITOR_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--signal",
                    "skills=$agent-orchestration",
                    "--behavior-event",
                    "skill_invocation=$agent-orchestration status=observed",
                    "--intervention",
                    "spawned reviewer",
                    "--decision",
                    "workflow_improvement_decision=applied",
                    "--decision",
                    "memory_learning_decision=not_applicable",
                    "--timestamp",
                    "2026-04-30 12:00 JST",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn(
                "upstream design ../../../agents/templates/workflow_monitoring.md",
                text,
            )
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("skill_invocation=$agent-orchestration status=observed", text)
            self.assertIn("spawned reviewer", text)
            self.assertIn("- workflow_improvement_decision: applied", text)
            self.assertIn("- memory_learning_decision: not_applicable", text)

    def test_bootstrap_seeds_monitoring_with_routing_evidence(self) -> None:
        """bootstrap_agent_run should seed workflow monitoring without manual edits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "monitor bootstrap",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "monitor-bootstrap",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitor_path = report_root / "monitor-bootstrap" / "workflow_monitoring.md"
            text = monitor_path.read_text(encoding="utf-8")
            self.assertIn("workflow=Scoped Change", text)
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("stage owner routing active_roles=", text)
            self.assertIn("created run bundle", text)

    def test_task_start_seeds_monitoring_with_routing_evidence(self) -> None:
        """task_start should seed workflow monitoring without manual edits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "monitor task start",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "monitor-task-start",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            monitor_path = report_root / "monitor-task-start" / "workflow_monitoring.md"
            text = monitor_path.read_text(encoding="utf-8")
            self.assertIn("workflow=Scoped Change", text)
            self.assertIn("skills=$agent-orchestration", text)
            self.assertIn("stage owner routing active_roles=", text)
            self.assertIn("created run bundle", text)

    def test_mcp_inventory_records_monitoring_when_report_dir_is_given(self) -> None:
        """MCP inventory checks should record pass evidence when directed to a run."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report_dir = root / "reports" / "agents" / "run-2"
            codex = root / "fake-codex"
            codex.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' '[{\"name\":\"repo_mcp_server\","
                "\"enabled\":true,\"command\":\"bash\","
                "\"args\":[\"mcp/repo_mcp_server.sh\"]}]'\n",
                encoding="utf-8",
            )
            codex.chmod(0o755)
            mcp_dir = root / "mcp"
            mcp_dir.mkdir()
            (mcp_dir / "repo_mcp_server.sh").write_text(
                "#!/usr/bin/env bash\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(MCP_SCRIPT),
                    "--codex-bin",
                    str(codex),
                    "--require",
                    "repo_mcp_server",
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("mcp_inventory=pass", text)
            self.assertIn("check_mcp_inventory.py recorded MCP inventory pass", text)


if __name__ == "__main__":
    unittest.main()
