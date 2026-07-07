# @dependency-start
# contract test
# responsibility Tests workflow selection eval behavior.
# upstream implementation ../../tools/agent_tools/evaluate_workflow_selection.py runs workflow selection evals
# upstream design ../../evidence/agent-evals/workflow_selection_eval.toml defines canonical workflow selection cases
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
from evaluate_workflow_selection import load_manifest  # noqa: E402
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
        self.assertIn("WORKFLOW_SELECTION_EVAL_CASES=525", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_EXPECTED_CASES=525", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_GENERATED_CASES=525", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_COUNT_FAILURES=none", result.stdout)

    def test_current_manifest_expands_required_task_groups(self) -> None:
        """The canonical manifest should expand to 21 stable 25-case groups."""
        manifest = load_manifest(PROJECT_ROOT / "evidence" / "agent-evals" / "workflow_selection_eval.toml")
        expected_groups = {
            "routing-advisory",
            "scoped-lite-code",
            "scoped-change-behavior",
            "validation-failure-cause-analysis",
            "docs-structure",
            "markdown-style",
            "large-refactor",
            "platform-environment",
            "research-benchmark",
            "adaptive-loop",
            "computational-optimization",
            "experiment-html-report",
            "tool-finding-report",
            "agent-log-analysis",
            "agent-canon-update",
            "pr-processing",
            "repo-structure-drift",
            "academic-paper",
            "oop-readability",
            "user-guided-debugging",
            "run-report-archive",
        }

        self.assertEqual(len(manifest.cases), 525)
        self.assertEqual(manifest.generated_case_count, 525)
        self.assertEqual(manifest.expected_case_count, 525)
        self.assertEqual(manifest.expected_generated_case_count, 525)
        self.assertEqual(manifest.count_failures, ())
        self.assertEqual({case.group_id for case in manifest.cases}, expected_groups)
        for group_id in expected_groups:
            self.assertEqual(
                sum(1 for case in manifest.cases if case.group_id == group_id),
                25,
                group_id,
            )
        docs_cases = [case for case in manifest.cases if case.group_id == "docs-structure"]
        large_cases = [case for case in manifest.cases if case.group_id == "large-refactor"]
        validation_cases = [
            case
            for case in manifest.cases
            if case.group_id == "validation-failure-cause-analysis"
        ]
        self.assertTrue(
            all(
                {"structure-planning", "prose-reasoning-graph"}.issubset(case.expected_skills)
                for case in docs_cases
            )
        )
        self.assertTrue(all("subagent-bootstrap" in case.expected_skills for case in large_cases))
        self.assertTrue(
            all("codex-task-workflow" in case.expected_skills for case in validation_cases)
        )
        self.assertTrue(
            all("test-design" not in case.expected_skills for case in validation_cases)
        )

    def test_accumulates_unique_report_without_prompt_text(self) -> None:
        """Accumulated reports should be uniquely named and not copy raw prompts."""
        source_run_id = "source-run-42"
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
                    "--run-id",
                    source_run_id,
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
        self.assertIn(f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={source_run_id}", result.stdout)
        self.assertEqual(len(reports), 1)
        self.assertIn("WORKFLOW_SELECTION_EVAL_RUN_ID=", report_text)
        self.assertIn(f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={source_run_id}", report_text)
        self.assertIn("WORKFLOW_SELECTION_EVAL_EXPECTED_CASES=525", report_text)
        self.assertIn("WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES=525", report_text)
        self.assertIn("WORKFLOW_SELECTION_EVAL_COUNT_FAILURES=none", report_text)
        self.assertIn("routing-advisory-001", report_text)
        self.assertIn("selected skills", report_text)
        self.assertIn("candidate skills", report_text)
        self.assertIn("expected tools", report_text)
        self.assertIn("observed tools", report_text)
        self.assertNotIn("実装しないで相談だけ", report_text)

    def test_missing_expected_workflow_fails(self) -> None:
        """A manifest expectation not emitted by the classifier should fail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.copy_runtime_fixture(root)
            manifest = root / "evidence" / "agent-evals" / "workflow_selection_eval.toml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
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

    def test_advisory_report_words_do_not_force_codex_task_workflow(self) -> None:
        """Generic report/update words should not trigger codex-task-workflow by themselves."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.copy_runtime_fixture(root)
            manifest = root / "evidence" / "agent-evals" / "workflow_selection_eval.toml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        'catalog_kind = "agent_canon_workflow_selection_eval"',
                        "version = 1",
                        "",
                        "[[cases]]",
                        'id = "advisory-report-words"',
                        'prompt = "相談だけ、レポートの確認と更新方針を説明して"',
                        'expected_workflows = ["routing-only-advisory"]',
                        'forbidden_workflows = ["codex-task-workflow"]',
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

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WORKFLOW_SELECTION_EVAL_STATUS=pass", result.stdout)

    def test_count_mismatch_fails_even_when_case_route_passes(self) -> None:
        """A generated manifest with the wrong expected count should fail closed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.copy_runtime_fixture(root)
            manifest = root / "evidence" / "agent-evals" / "workflow_selection_eval.toml"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(
                "\n".join(
                    [
                        'catalog_kind = "agent_canon_workflow_selection_eval"',
                        "version = 2",
                        "expected_case_count = 500",
                        "expected_generated_case_count = 1",
                        "",
                        "[[case_groups]]",
                        'id = "count-mismatch"',
                        'expected_workflows = ["codex-task-workflow"]',
                        "limit = 1",
                        'prompt_templates = ["{subject} を実装して修正して"]',
                        'subjects = ["single generated case"]',
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
        self.assertIn("WORKFLOW_SELECTION_EVAL_FAILED=0", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_COUNT_FAILURES=expected_case_count=500 observed=1", result.stdout)
        self.assertIn("WORKFLOW_SELECTION_EVAL_STATUS=fail", result.stdout)

    def copy_runtime_fixture(self, root: Path) -> None:
        """Copy the classifier and manifest needed by the eval runner."""
        for relative in (
            ".codex/hooks/skill_usage_logger.py",
            ".codex/hooks/hook_event_log.py",
            "evidence/agent-evals/workflow_selection_eval.toml",
        ):
            source = PROJECT_ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
