# @dependency-start
# contract test
# responsibility Tests agent run path comparison behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/compare_agent_run_paths.rs compares runs  # noqa: E501
# upstream design ../../agents/skills/adaptive-improvement-loop.md compares reruns  # noqa: E501
# @dependency-end
"""Tests for two-run execution path comparison."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def run_native(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    assert AGENT_CANON_CLI is not None, (
        "AGENT_CANON_CLI must select the current native executable"
    )
    executable = Path(AGENT_CANON_CLI)
    assert executable.is_absolute(), (
        "AGENT_CANON_CLI must be an absolute executable path"
    )
    return subprocess.run(
        [str(executable), "compare-agent-run-paths", *arguments],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


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

    def test_unambiguous_help_prefix_matches_long_help(self) -> None:
        """Argparse-compatible help prefixes remain available in the native CLI."""
        long_help = run_native(["--help"])
        self.assertEqual(long_help.returncode, 0, long_help.stderr)
        self.assertEqual(long_help.stderr, "")
        for option in ("-h", "--he"):
            with self.subTest(option=option):
                result = run_native([option])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, long_help.stdout)
                self.assertEqual(result.stderr, "")

        explicit_value = run_native(["--he=ignored"])
        self.assertEqual(explicit_value.returncode, 2)
        self.assertEqual(explicit_value.stdout, "")
        self.assertIn("ignored explicit argument 'ignored'", explicit_value.stderr)

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

            result = run_native(
                [
                    f"--baseline-run={baseline}",
                    f"--candidate-r={candidate}",
                    f"--report-out={report}",
                ]
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("RUN_PATH_COMPARISON=fail", result.stdout)
            self.assertIn("RUN_PATHS_DIFFER=yes", result.stdout)
            self.assertIn("NEXT_ACTION=repair_skill_workflow_prompt", result.stdout)
            text = report.read_text(encoding="utf-8")
            self.assertIn("selected_inefficient_route=yes", text)

    def test_unreadable_monitoring_input_exits_one(self) -> None:
        """Invalid UTF-8 is an input error, not an empty monitoring record."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = root / "baseline"
            candidate = root / "candidate"
            write_run(
                baseline,
                execution_path="reuse-first",
                route_efficiency="efficient",
            )
            candidate.mkdir()
            (candidate / "workflow_monitoring.md").write_bytes(b"\xff")

            result = run_native(
                ["--baseline-run", str(baseline), "--candidate-run", str(candidate)]
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertNotEqual(result.stderr, "")

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

            result = run_native(
                [
                    "--baseline-run",
                    str(baseline),
                    "--candidate-run",
                    str(candidate),
                ]
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RUN_PATH_COMPARISON=pass", result.stdout)
            self.assertIn("SELECTED_INEFFICIENT_ROUTE=no", result.stdout)
            self.assertIn("STATIC_ANALYSIS_FEEDBACK=recorded", result.stdout)
