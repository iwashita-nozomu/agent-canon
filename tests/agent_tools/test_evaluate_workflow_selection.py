# @dependency-start
# responsibility Tests workflow selection eval behavior.
# upstream implementation ../../tools/agent_tools/evaluate_workflow_selection.py runs workflow selection evals
# upstream design ../../agents/evals/workflow_selection_eval.toml defines canonical workflow selection cases
# @dependency-end

"""Tests for workflow selection evals."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "evaluate_workflow_selection.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import mounted_log_archive_root  # noqa: E402


class EvaluateWorkflowSelectionTest(unittest.TestCase):
    """Exercise deterministic prompt-to-workflow routing evals."""

    def test_current_manifest_passes(self) -> None:
        """The canonical workflow selection manifest should pass."""
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(PROJECT_ROOT),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WORKFLOW_SELECTION_EVAL_STATUS=pass", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_CASES=", result.stdout)

    def test_accumulates_unique_report_without_prompt_text(self) -> None:
        """Accumulated reports should be uniquely named and not copy raw prompts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.copy_runtime_fixture(root)
            archive_root = mounted_log_archive_root(root)
            archive_root.mkdir(parents=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--accumulate",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            reports = list(
                (archive_root / "eval-results" / "workflow-selection").glob("*.md")
            )
            report_text = reports[0].read_text(encoding="utf-8") if reports else ""

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WORKFLOW_SELECTION_EVAL_REPORT=", result.stdout)
        self.assertEqual(len(reports), 1)
        self.assertIn("WORKFLOW_SELECTION_EVAL_RUN_ID=", report_text)
        self.assertIn("environment-maintenance-container-ci", report_text)
        self.assertIn("selected skills", report_text)
        self.assertIn("candidate skills", report_text)
        self.assertNotIn("Docker devcontainer GitHub Actions", report_text)

    def test_missing_expected_workflow_fails(self) -> None:
        """A manifest expectation not emitted by the classifier should fail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.copy_runtime_fixture(root)
            manifest = root / "agents" / "evals" / "workflow_selection_eval.toml"
            manifest.write_text(
                "\n".join(
                    [
                        'catalog_kind = "agent_canon_workflow_selection_eval"',
                        "version = 1",
                        "",
                        "[[cases]]",
                        'id = "missing-route"',
                        'prompt = "単純な質問です"',
                        'expected_workflows = ["environment-maintenance"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("WORKFLOW_SELECTION_EVAL_STATUS=fail", result.stdout)

    def copy_runtime_fixture(self, root: Path) -> None:
        """Copy the classifier and manifest needed by the eval runner."""
        for relative in (
            ".codex/hooks/skill_usage_logger.py",
            ".codex/hooks/hook_event_log.py",
            "agents/evals/workflow_selection_eval.toml",
        ):
            source = PROJECT_ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
