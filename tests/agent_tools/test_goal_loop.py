# @dependency-start
# responsibility Tests goal loop automation.
# upstream implementation ../../tools/agent_tools/goal_loop.py goal loop CLI
# upstream design ../../goal.md top-level goal contract
# @dependency-end
"""Tests for goal.md loop automation."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "goal_loop.py"


def run_goal_loop(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    """Run the goal loop helper."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


class GoalLoopTest(unittest.TestCase):
    """Verify goal.md loop behavior."""

    def test_init_and_status_continue(self) -> None:
        """A fresh goal starts in continue state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            goal = Path(tmp_dir) / "goal.md"

            init = run_goal_loop(
                "init",
                "--goal-file",
                str(goal),
                "--objective",
                "Ship a deterministic goal loop.",
            )
            status = run_goal_loop("status", "--goal-file", str(goal))

            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("GOAL_LOOP_STATUS=continue", status.stdout)
            self.assertIn("GOAL_EXIT_CRITERIA_TOTAL=5", status.stdout)
            text = goal.read_text(encoding="utf-8")
            self.assertIn("run_repo_dependency_review.sh --fail-missing", text)
            self.assertIn("scan_code_dependencies.sh", text)
            self.assertIn("analyze_oop_readability.py", text)
            self.assertIn("make ci", text)

    def test_mark_done_and_goal_status_achieved(self) -> None:
        """A checked criterion plus achieved status closes the loop."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            goal = Path(tmp_dir) / "goal.md"
            run_goal_loop(
                "init",
                "--goal-file",
                str(goal),
                "--objective",
                "Close the goal.",
            )

            result = run_goal_loop(
                "mark",
                "--goal-file",
                str(goal),
                "--criterion",
                "G5",
                "--done",
            )
            for criterion in ("G1", "G2", "G3", "G4"):
                result = run_goal_loop(
                    "mark",
                    "--goal-file",
                    str(goal),
                    "--criterion",
                    criterion,
                    "--done",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            result = run_goal_loop(
                "mark",
                "--goal-file",
                str(goal),
                "--criterion",
                "G5",
                "--done",
                "--goal-status",
                "achieved",
            )
            status = run_goal_loop(
                "status",
                "--goal-file",
                str(goal),
                "--require-achieved",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("GOAL_LOOP_STATUS=achieved", status.stdout)
            self.assertIn("NEXT_ACTION=close_goal_loop", status.stdout)

    def test_status_report_is_written(self) -> None:
        """Status can write a Markdown artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            goal = Path(tmp_dir) / "goal.md"
            report = Path(tmp_dir) / "reports" / "goal-loop" / "status.md"
            run_goal_loop(
                "init",
                "--goal-file",
                str(goal),
                "--objective",
                "Write status.",
            )

            result = run_goal_loop(
                "status",
                "--goal-file",
                str(goal),
                "--report-out",
                str(report),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(report.exists())
            text = report.read_text(encoding="utf-8")
            self.assertIn("# Goal Loop Status", text)
            self.assertIn("goal_loop_status: `continue`", text)

    def test_run_repeats_until_command_marks_goal_achieved(self) -> None:
        """The run command repeats until goal.md reaches achieved state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            goal = root / "goal.md"
            worker = root / "worker.py"
            run_goal_loop(
                "init",
                "--goal-file",
                str(goal),
                "--objective",
                "Loop until worker marks completion.",
                "--max-iterations",
                "3",
            )
            worker.write_text(
                "\n".join(
                    [
                        "from pathlib import Path",
                        "import os",
                        "goal = Path(os.environ['GOAL_FILE'])",
                        "text = goal.read_text()",
                        "for criterion in ('G1', 'G2', 'G3', 'G4', 'G5'):",
                        "    text = text.replace(f'- [ ] {criterion}:', f'- [x] {criterion}:')",
                        "text = text.replace('- goal_status: active', '- goal_status: achieved')",
                        "goal.write_text(text)",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_goal_loop(
                "run",
                "--goal-file",
                str(goal),
                "--",
                sys.executable,
                str(worker),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GOAL_LOOP_STATUS=achieved", result.stdout)
            self.assertIn("- current_iteration: 1", goal.read_text(encoding="utf-8"))

    def test_run_stops_at_budget(self) -> None:
        """The run command stops when the goal budget is exhausted."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            goal = root / "goal.md"
            worker = root / "noop.py"
            run_goal_loop(
                "init",
                "--goal-file",
                str(goal),
                "--objective",
                "Never complete.",
                "--max-iterations",
                "1",
            )
            worker.write_text("pass\n", encoding="utf-8")

            result = run_goal_loop(
                "run",
                "--goal-file",
                str(goal),
                "--",
                sys.executable,
                str(worker),
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("GOAL_LOOP_STATUS=budget_exhausted", result.stdout)


if __name__ == "__main__":
    unittest.main()
