"""Tests for eval accumulation validation."""

# @dependency-start
# contract test
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

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(root),
                "--family-registry",
                str(PROJECT_ROOT / "evidence" / "agent-evals" / "eval_result_families.toml"),
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_complete_fixture_passes(self) -> None:
        """A complete mounted archive fixture should pass."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            result = self.run_checker(root)

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

    def test_compact_out_limits_stdout_and_writes_summary(self) -> None:
        """Compact mode writes finding stats to JSON and keeps stdout bounded."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_path = self.hook_path(root)
            entry = self.hook_entry("hook-duplicate")
            hook_path.write_text(
                json.dumps(entry) + "\n" + json.dumps(entry) + "\n",
                encoding="utf-8",
            )
            compact = root / "compact.json"

            result = self.run_checker(root, "--compact-out", str(compact))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_COMPACT_OUT=", result.stdout)
            self.assertNotIn("EVAL_ACCUMULATION_FINDING=", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertGreater(payload["finding_count"], 0)
            self.assertIn("hook_run_id", payload["finding_counts"])
            self.assertIn("hook_legacy_missing_namespace", payload)
            self.assertIn("hook_namespace_debt", payload)

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
            self.assertIn("EVAL_ACCUMULATION_HOOK_NAMESPACE_DEBT=1", result.stdout)
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

    def test_external_hook_archive_malformed_json_is_warning(self) -> None:
        """Mounted hook archive parse debt should not block source-tree validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            hook_path = self.hook_path(root)
            hook_path.write_text("{not-json}\n", encoding="utf-8")
            compact = root / "compact.json"

            result = self.run_checker(root, "--compact-out", str(compact))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_FINDINGS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_BLOCKING_FINDINGS=0", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_WARNINGS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)
            payload = json.loads(compact.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["blocking_finding_count"], 0)
            self.assertEqual(payload["warning_count"], 1)

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
            self.assertIn("EVAL_ACCUMULATION_CODEX_AGENT_ROLE_REPORTS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_legacy_eval_archive_missing_run_id_is_warning(self) -> None:
        """Legacy imported eval reports without run ids should not block CI."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            legacy_dir = (
                mounted_log_archive_root(root)
                / "eval-results"
                / "legacy-import"
                / "skill-workflow-prompt"
            )
            legacy_dir.mkdir(parents=True)
            (
                legacy_dir
                / "skill-eval-20260511T071608729709Z-1a2183faf0-pass-agent-orchestration.md"
            ).write_text("# Legacy report without run id\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_FINDINGS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_BLOCKING_FINDINGS=0", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_WARNINGS=1", result.stdout)
            self.assertIn("EVAL_ACCUMULATION=pass", result.stdout)

    def test_unmounted_archive_is_environment_error(self) -> None:
        """Fresh CI checkouts must mount the external archive before validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results_dir = root / "agents" / "evals" / "results"
            hook_dir = results_dir / "hook-runs"
            hook_dir.mkdir(parents=True)
            (results_dir / "README.md").write_text("archive notice\n", encoding="utf-8")
            (hook_dir / "README.md").write_text("hook archive notice\n", encoding="utf-8")

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION=error", result.stdout)
            self.assertIn("EVAL_ACCUMULATION_ERROR_CODE=log_archive_required", result.stdout)
            self.assertIn("NEXT_ACTION=mount_.agent-canon/log-archive_or_set_AGENT_CANON_HOOK_ARCHIVE_DIR", result.stdout)

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

    def test_missing_codex_agent_role_eval_report_fails(self) -> None:
        """At least one accumulated Codex role eval report is required."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            for path in self.eval_family_dir(root, "codex-agent-role").glob("*.md"):
                path.unlink()

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("no-codex-agent-role-eval-reports", result.stdout)

    def test_registry_declared_family_is_counted_without_code_change(self) -> None:
        """New eval families should be added by registry contract, not checker code."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            registry_path = root / "evidence" / "agent-evals" / "eval_result_families.toml"
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            registry_path.write_text(
                (PROJECT_ROOT / "evidence" / "agent-evals" / "eval_result_families.toml").read_text(
                    encoding="utf-8"
                )
                + """

[[families]]
id = "abstract-review"
check_id = "abstract_review_eval"
count_label = "ABSTRACT_REVIEW_REPORTS"
summary = "Fixture for an abstract, non-code eval family."
producer = "tools/agent_tools/example.py --accumulate"
filename_regex = '^abstract-review-eval-\\d{8}T\\d{12}Z-[0-9a-f]{10}-(?:pass|fail)\\.md$'
run_id_regex = '\\bABSTRACT_REVIEW_EVAL_RUN_ID=([A-Za-z0-9_.:-]+)'
missing_reports_detail = "no-abstract-review-eval-reports"
missing_run_id_detail = "missing-abstract-review-eval-run-id"
duplicate_run_id_detail = "duplicate-abstract-review-eval-run-id"
""",
                encoding="utf-8",
            )
            abstract_dir = self.eval_family_dir(root, "abstract-review")
            abstract_dir.mkdir(parents=True)
            (abstract_dir / "abstract-review-eval-20260517T010203040506Z-1234567890-pass.md").write_text(
                "ABSTRACT_REVIEW_EVAL_RUN_ID=abstract-review-eval-20260517T010203040506Z-1234567890\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "--family-registry", str(registry_path))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("EVAL_ACCUMULATION_FAMILY_REPORTS=abstract-review:1", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a minimal eval result fixture."""
        evals_root = root / "evidence" / "agent-evals"
        evals_root.mkdir(parents=True, exist_ok=True)
        (evals_root / "README.md").write_text("# Eval fixture\n", encoding="utf-8")
        hook_dir = self.hook_path(root).parent
        skill_dir = self.eval_family_dir(root, "skill-workflow-prompt")
        local_llm_dir = self.eval_family_dir(root, "local-llm-responsibility")
        workflow_selection_dir = self.eval_family_dir(root, "workflow-selection")
        report_quality_dir = self.eval_family_dir(root, "report-quality")
        codex_agent_role_dir = self.eval_family_dir(root, "codex-agent-role")
        hook_dir.mkdir(parents=True)
        skill_dir.mkdir(parents=True)
        local_llm_dir.mkdir(parents=True)
        workflow_selection_dir.mkdir(parents=True)
        report_quality_dir.mkdir(parents=True)
        codex_agent_role_dir.mkdir(parents=True)
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
        (
            codex_agent_role_dir
            / "codex-agent-role-eval-20260517T010203040506Z-1234567890-pass.md"
        ).write_text(
            "CODEX_AGENT_ROLE_EVAL_RUN_ID=codex-agent-role-eval-20260517T010203040506Z-1234567890\n",
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
