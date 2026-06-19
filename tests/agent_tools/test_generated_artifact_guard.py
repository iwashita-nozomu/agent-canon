"""Tests for generated report artifact guard."""

# @dependency-start
# contract test
# responsibility Tests generated report artifact guard behavior.
# upstream implementation ../../tools/agent_tools/generated_artifact_guard.py rejects regenerated reports left in tree
# upstream implementation ../../tools/agent_tools/report_artifact_checks.py classifies report artifact paths
# upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md canonical artifact placement policy
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUARD_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "generated_artifact_guard.py"


class GeneratedArtifactGuardTest(unittest.TestCase):
    """Validate regenerated report artifact detection."""

    def init_repo(self, root: Path) -> None:
        """Create a minimal Git repository for guard tests."""
        subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Generated Artifact Guard Test",
                "-c",
                "user.email=generated-artifact-guard@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "init",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )

    def run_guard(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the guard against a test repository."""
        return subprocess.run(
            [sys.executable, str(GUARD_SCRIPT), "--root", str(root)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_rejects_untracked_dependency_review_artifact(self) -> None:
        """Dependency review report files are mechanically regenerated outputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.init_repo(root)
            artifact = root / "reports" / "dependency-review" / "run" / "dependency_graph.tsv"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("source\ttarget\n", encoding="utf-8")

            result = self.run_guard(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn("GENERATED_ARTIFACT_GUARD=fail", result.stdout)
            self.assertIn(
                "generated_report_artifact_untracked_left_in_tree:"
                "reports/dependency-review/run/dependency_graph.tsv",
                result.stdout,
            )

    def test_rejects_ignored_eval_run_artifact(self) -> None:
        """Ignored eval stdout/stderr logs are still source-tree leftovers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.init_repo(root)
            (root / ".gitignore").write_text(
                "reports/agent-eval-runs/\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Generated Artifact Guard Test",
                    "-c",
                    "user.email=generated-artifact-guard@example.invalid",
                    "commit",
                    "-m",
                    "ignore generated eval logs",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            artifact = root / "reports" / "agent-eval-runs" / "run" / "01-role.stdout.txt"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("ok\n", encoding="utf-8")

            result = self.run_guard(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "generated_report_artifact_ignored_left_in_tree:"
                "reports/agent-eval-runs/run/01-role.stdout.txt",
                result.stdout,
            )

    def test_rejects_tracked_generated_report_artifact(self) -> None:
        """Generated report roots should not become durable tracked source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.init_repo(root)
            artifact = root / "reports" / "agent-runtime-dashboard" / "index.html"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("<html></html>\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "reports/agent-runtime-dashboard/index.html"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Generated Artifact Guard Test",
                    "-c",
                    "user.email=generated-artifact-guard@example.invalid",
                    "commit",
                    "-m",
                    "track generated dashboard",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = self.run_guard(root)

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "generated_report_artifact_tracked_left_in_tree:"
                "reports/agent-runtime-dashboard/index.html",
                result.stdout,
            )

    def test_allows_run_bundle_reports_for_closeout_gate(self) -> None:
        """Run bundles are one-shot evidence and remain task_close.py responsibility."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.init_repo(root)
            (root / ".gitignore").write_text(
                "reports/agents/\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Generated Artifact Guard Test",
                    "-c",
                    "user.email=generated-artifact-guard@example.invalid",
                    "commit",
                    "-m",
                    "ignore run bundles",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_artifact = root / "reports" / "agents" / "run-1" / "work_log.md"
            run_artifact.parent.mkdir(parents=True, exist_ok=True)
            run_artifact.write_text("# Work Log\n", encoding="utf-8")

            result = self.run_guard(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("GENERATED_ARTIFACT_GUARD=pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
