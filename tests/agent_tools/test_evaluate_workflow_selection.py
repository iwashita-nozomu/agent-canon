# @dependency-start
# contract test
# responsibility Tests workflow selection eval behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/workflow_selection_eval.rs runs workflow selection evals
# upstream design ../../eval/definitions/workflow_selection_eval.toml defines canonical workflow selection cases
# @dependency-end

"""Tests for workflow selection evals."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def native_cli() -> str:
    selected_cli = os.environ.get("AGENT_CANON_CLI")
    if not selected_cli:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return selected_cli


class EvaluateWorkflowSelectionTest(unittest.TestCase):
    """Exercise deterministic prompt-to-workflow routing evals."""

    def test_current_manifest_passes(self) -> None:
        """The canonical workflow selection manifest should pass."""
        result = subprocess.run(
            [
                native_cli(),
                "evaluate-workflow-selection",
                "--root",
                str(PROJECT_ROOT),
            ],
            cwd=PROJECT_ROOT,
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

    def test_accumulates_unique_report_without_prompt_text(self) -> None:
        """Accumulated reports should be uniquely named and not copy raw prompts."""
        source_run_id = "source-run-42"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = temp_root / "agent-canon-development" / "agent-canon"
            runtime_root = temp_root / "runtime"
            self.copy_runtime_fixture(root)
            before = self.snapshot_tree(root)
            archive_root = runtime_root / "archive" / "agent-canon-log"
            archive_root.mkdir(parents=True)

            result = subprocess.run(
                [
                    native_cli(),
                    "evaluate-workflow-selection",
                    "--root",
                    str(root),
                    "--runtime-root",
                    str(runtime_root),
                    "--accumulate",
                    "--run-id",
                    source_run_id,
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            reports = list(
                (archive_root / "eval-results" / "workflow-selection").glob("*.md")
            )
            report_text = reports[0].read_text(encoding="utf-8") if reports else ""
            self.assertEqual(before, self.snapshot_tree(root))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WORKFLOW_SELECTION_EVAL_REPORT=", result.stdout)
        self.assertIn(
            f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={source_run_id}", result.stdout
        )
        self.assertEqual(len(reports), 1)
        self.assertIn("WORKFLOW_SELECTION_EVAL_RUN_ID=", report_text)
        self.assertIn(
            f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={source_run_id}", report_text
        )
        self.assertIn("WORKFLOW_SELECTION_EVAL_EXPECTED_CASES=525", report_text)
        self.assertIn(
            "WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES=525", report_text
        )
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
            manifest = root / "eval" / "definitions" / "workflow_selection_eval.toml"
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
                    native_cli(),
                    "evaluate-workflow-selection",
                    "--root",
                    str(root),
                ],
                cwd=PROJECT_ROOT,
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
            manifest = root / "eval" / "definitions" / "workflow_selection_eval.toml"
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
                    native_cli(),
                    "evaluate-workflow-selection",
                    "--root",
                    str(root),
                ],
                cwd=PROJECT_ROOT,
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
            manifest = root / "eval" / "definitions" / "workflow_selection_eval.toml"
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
                    native_cli(),
                    "evaluate-workflow-selection",
                    "--root",
                    str(root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("WORKFLOW_SELECTION_EVAL_FAILED=0", result.stdout)
        self.assertIn(
            "WORKFLOW_SELECTION_EVAL_COUNT_FAILURES=expected_case_count=500 observed=1",
            result.stdout,
        )
        self.assertIn("WORKFLOW_SELECTION_EVAL_STATUS=fail", result.stdout)

    def copy_runtime_fixture(self, root: Path) -> None:
        """Copy the controlled manifest input for the native eval CLI."""
        for relative in ("eval/definitions/workflow_selection_eval.toml",):
            source = PROJECT_ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    @staticmethod
    def snapshot_tree(root: Path) -> tuple[tuple[str, str, int], ...]:
        """Capture source bytes and modes to prove eval output stays external."""
        entries: list[tuple[str, str, int]] = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            entries.append(
                (
                    str(path.relative_to(root)),
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    path.stat().st_mode & 0o777,
                )
            )
        return tuple(entries)


if __name__ == "__main__":
    unittest.main()
