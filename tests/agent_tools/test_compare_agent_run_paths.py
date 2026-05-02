# @dependency-start
# responsibility Tests agent run path comparison behavior.
# upstream implementation ../../tools/agent_tools/compare_agent_run_paths.py compares runs  # noqa: E501
# upstream design ../../agents/workflows/adaptive-improvement-workflow.md compares reruns  # noqa: E501
# @dependency-end
"""Tests for two-run execution path comparison."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "compare_agent_run_paths.py"


def write_run(
    run_dir: Path,
    *,
    execution_path: str,
    route_efficiency: str,
    static_feedback: str = "applied",
) -> None:
    """Write minimal workflow monitoring evidence for one run."""
    run_dir.mkdir(parents=True)
    (run_dir / "workflow_monitoring.md").write_text(
        "\n".join(
            [
                "# Workflow Monitoring",
                "## Behavior Events",
                (
                    "- execution_path="
                    f"{execution_path} route_efficiency={route_efficiency} "
                    f"static_analysis_feedback={static_feedback}"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


class CompareAgentRunPathsTest(unittest.TestCase):
    """Verify path comparison status and reports."""

    def test_candidate_inefficient_route_fails(self) -> None:
        """A selected inefficient route should fail mechanically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline"
            candidate = root / "candidate"
            report = root / "comparison.md"
            write_run(
                baseline,
                execution_path="reuse-first",
                route_efficiency="efficient",
            )
            write_run(
                candidate,
                execution_path="new-tool-first",
                route_efficiency="inefficient",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--baseline-run",
                    str(baseline),
                    "--candidate-run",
                    str(candidate),
                    "--report-out",
                    str(report),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("RUN_PATH_COMPARISON=fail", result.stdout)
            self.assertIn("RUN_PATHS_DIFFER=yes", result.stdout)
            self.assertIn("NEXT_ACTION=repair_skill_workflow_prompt", result.stdout)
            text = report.read_text(encoding="utf-8")
            self.assertIn("selected_inefficient_route=yes", text)

    def test_candidate_efficient_route_passes(self) -> None:
        """An efficient selected route should pass and record feedback tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline"
            candidate = root / "candidate"
            write_run(
                baseline,
                execution_path="parent-only",
                route_efficiency="acceptable",
            )
            write_run(
                candidate,
                execution_path="reuse-first",
                route_efficiency="efficient",
                static_feedback="recorded",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--baseline-run",
                    str(baseline),
                    "--candidate-run",
                    str(candidate),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN_PATH_COMPARISON=pass", result.stdout)
            self.assertIn("SELECTED_INEFFICIENT_ROUTE=no", result.stdout)
            self.assertIn("STATIC_ANALYSIS_FEEDBACK=recorded", result.stdout)
