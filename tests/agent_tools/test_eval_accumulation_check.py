"""Tests for eval accumulation validation."""

# @dependency-start
# responsibility Tests eval accumulation validation.
# upstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates eval result evidence
# upstream design ../../documents/runtime-log-archive.md eval result storage contract
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "eval_accumulation_check.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import mounted_log_archive_root, repo_log_key  # noqa: E402


class EvalAccumulationCheckTest(unittest.TestCase):
    """Exercise accumulated eval result validation."""

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical repository has readable accumulated eval evidence."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_duplicate_hook_run_id_fails(self) -> None:
        """Hook run ids must be unique even within the same JSONL file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_path = self.hook_path(root)
            entry = self.hook_entry("hook-duplicate")
            hook_path.write_text(
                json.dumps(entry) + "\n" + json.dumps(entry) + "\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("duplicate", result.stdout)

    def test_hook_entries_without_namespace_are_counted_not_failed(self) -> None:
        """Accumulated hook logs missing namespaces remain visible for repair."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_path = self.hook_path(root)
            entry = self.hook_entry("hook-legacy")
            entry.pop("hook_log_namespace")
            hook_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_HOOK_LEGACY_MISSING_NAMESPACE=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_external_hook_archive_entries_are_counted(self) -> None:
        """Mounted hook archive entries should satisfy hook accumulation evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            archive_root = mounted_log_archive_root(root)
            archive_hook_dir = (
                archive_root
                / "hook-runs"
                / repo_log_key(root)
                / "test"
            )
            archive_hook_dir.mkdir(parents=True, exist_ok=True)
            (archive_hook_dir / "hook.jsonl").write_text(
                json.dumps(self.hook_entry("hook-external")) + "\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_HOOK_FILES=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_HOOK_ENTRIES=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_external_eval_archive_entries_are_counted(self) -> None:
        """Mounted eval archive reports should satisfy eval accumulation evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_SKILL_REPORTS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_LOCAL_LLM_REPORTS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_WORKFLOW_SELECTION_REPORTS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_REPORT_QUALITY_REPORTS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_unmounted_archive_without_legacy_eval_dirs_is_nonblocking(self) -> None:
        """Fresh CI checkouts without the external archive should not fail."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results_dir = root / "agents" / "evals" / "results"
            hook_dir = results_dir / "hook-runs"
            hook_dir.mkdir(parents=True)
            (results_dir / "README.md").write_text("archive notice\n", encoding="utf-8")
            (hook_dir / "README.md").write_text("hook archive notice\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_SKILL_REPORTS=0", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_missing_skill_eval_report_fails(self) -> None:
        """At least one accumulated skill eval report is required."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            for path in self.eval_family_dir(root, "skill-workflow-prompt").glob("*.md"):
                path.unlink()

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no-skill-eval-reports", result.stdout)

    def test_missing_local_llm_eval_report_fails(self) -> None:
        """At least one accumulated local LLM eval report is required."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            for path in self.eval_family_dir(root, "local-llm-responsibility").glob("*.md"):
                path.unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no-local-llm-eval-reports", result.stdout)

    def test_missing_workflow_selection_eval_report_fails(self) -> None:
        """At least one accumulated workflow selection eval report is required."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            for path in self.eval_family_dir(root, "workflow-selection").glob("*.md"):
                path.unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no-workflow-selection-eval-reports", result.stdout)

    def test_missing_report_quality_eval_report_fails(self) -> None:
        """At least one accumulated report quality eval report is required."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            for path in self.eval_family_dir(root, "report-quality").glob("*.md"):
                path.unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no-report-quality-eval-reports", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a minimal eval result fixture."""
        hook_dir = self.hook_path(root).parent
        skill_dir = self.eval_family_dir(root, "skill-workflow-prompt")
        local_llm_dir = self.eval_family_dir(root, "local-llm-responsibility")
        workflow_selection_dir = self.eval_family_dir(root, "workflow-selection")
        report_quality_dir = self.eval_family_dir(root, "report-quality")
        hook_dir.mkdir(parents=True)
        skill_dir.mkdir(parents=True)
        local_llm_dir.mkdir(parents=True)
        workflow_selection_dir.mkdir(parents=True)
        report_quality_dir.mkdir(parents=True)
        (hook_dir / "hook.jsonl").write_text(
            json.dumps(self.hook_entry("hook-1")) + "\n",
            encoding="utf-8",
        )
        (skill_dir / "skill-eval-20260517T010203040506Z-1234567890-pass-agent-orchestration.md").write_text(
            "EVAL_RUN_ID=skill-eval-20260517T010203040506Z-1234567890\n",
            encoding="utf-8",
        )
        (local_llm_dir / "local-llm-eval-20260517T010203040506Z-1234567890-pass.md").write_text(
            "LOCAL_LLM_EVAL_RUN_ID=local-llm-eval-20260517T010203040506Z-1234567890\n",
            encoding="utf-8",
        )
        (
            workflow_selection_dir
            / "workflow-selection-eval-20260517T010203040506Z-1234567890-pass.md"
        ).write_text(
            "WORKFLOW_SELECTION_EVAL_RUN_ID=workflow-selection-eval-20260517T010203040506Z-1234567890\n",
            encoding="utf-8",
        )
        (report_quality_dir / "report-quality-eval-20260517T010203040506Z-1234567890-pass.md").write_text(
            "REPORT_QUALITY_EVAL_RUN_ID=report-quality-eval-20260517T010203040506Z-1234567890\n",
            encoding="utf-8",
        )

    def hook_path(self, root: Path) -> Path:
        """Return the archive hook fixture path."""
        return mounted_log_archive_root(root) / "hook-runs" / repo_log_key(root) / "test" / "hook.jsonl"

    def eval_family_dir(self, root: Path, family: str) -> Path:
        """Return one archive eval family fixture directory."""
        return mounted_log_archive_root(root) / "eval-results" / family

    def hook_entry(self, run_id: str) -> dict[str, str]:
        """Return one valid hook entry."""
        return {
            "hook_run_id": run_id,
            "timestamp": "2026-05-17T00:00:00Z",
            "status": "pass",
            "payload_fingerprint": "abcdef123456",
            "hook_log_namespace": "test",
        }


if __name__ == "__main__":
    unittest.main()
