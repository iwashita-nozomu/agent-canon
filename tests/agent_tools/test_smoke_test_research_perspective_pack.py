# @dependency-start
# contract test
# responsibility Tests test smoke test research perspective pack behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Smoke-test coverage for the research perspective pack helper."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import smoke_test_research_perspective_pack as smoke  # noqa: E402
from parent_root_side_effects import (  # noqa: E402
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
)


class ResearchPerspectivePackSmokeTest(unittest.TestCase):
    """Verify that the smoke-test helper exits successfully."""

    def test_run_bundle_includes_document_flow_review_artifact(self) -> None:
        """The always-on bundle should create the document flow review artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-document-flow-review"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "document flow reviewer smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("document_flow_review.md", result.stdout)
            self.assertIn("IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker", result.stdout)
            self.assertTrue((report_dir / "document_flow_review.md").is_file())
            manifest_text = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            self.assertIn("    codex_agents:\n      - worker\n      - spark_worker", manifest_text)

    def test_run_bundle_starts_with_locked_completion_gate(self) -> None:
        """Fresh bundles should lock user-facing completion until verifier/auditor closeout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-closeout-gate"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "closeout gate smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id
            verification_text = (report_dir / "verification.txt").read_text(encoding="utf-8")
            closeout_text = (report_dir / "closeout_gate.md").read_text(encoding="utf-8")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((report_dir / "closeout_gate.md").is_file())
            self.assertTrue((report_dir / "agent_evaluation.md").is_file())
            self.assertIn("user_completion_report=locked", verification_text)
            self.assertIn("closeout_gate_status=pending", verification_text)
            self.assertIn("- user_completion_report: locked", closeout_text)
            self.assertIn("- completion_coverage_consumer: no", closeout_text)
            self.assertIn("- repo_wide_dependency_tools_complete: no", closeout_text)
            self.assertIn("- repo_wide_static_analysis_complete: no", closeout_text)
            self.assertIn("- review_findings_integrated: no", closeout_text)
            self.assertIn("- post_fix_full_review_complete: no", closeout_text)
            self.assertIn("- canonical_tree_head_complete: no", closeout_text)
            self.assertIn("- agent_evaluation_complete: no", closeout_text)
            self.assertIn("- verifier_status: pending", closeout_text)
            self.assertIn("- auditor_status: pending", closeout_text)

    def test_run_bundle_can_enable_academic_writing_reviewers(self) -> None:
        """Academic writing reviewers should create their review artifacts when enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-academic-writing-reviewers"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "academic writing smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--enable",
                    "citation_evidence_reviewer",
                    "--enable",
                    "notation_definition_reviewer",
                    "--enable",
                    "logic_gap_reviewer",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("citation_evidence_review.md", result.stdout)
            self.assertIn("notation_definition_review.md", result.stdout)
            self.assertIn("logic_gap_review.md", result.stdout)
            self.assertTrue((report_dir / "citation_evidence_review.md").is_file())
            self.assertTrue((report_dir / "notation_definition_review.md").is_file())
            self.assertTrue((report_dir / "logic_gap_review.md").is_file())

    def test_task_id_t10_expands_paper_reviewers(self) -> None:
        """Academic-paper task bootstrap should include paper-specific reviewers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-id-t10"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "paper writing task",
                    "--task-id",
                    "T10",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TASK_ID=T10", result.stdout)
            self.assertIn("citation_evidence_reviewer", result.stdout)
            self.assertIn("citation_evidence_review.md", result.stdout)
            self.assertTrue((report_dir / "citation_evidence_review.md").is_file())
            self.assertTrue((report_dir / "notation_definition_review.md").is_file())
            self.assertTrue((report_dir / "logic_gap_review.md").is_file())

    def test_task_id_expands_default_research_reviewers(self) -> None:
        """Task-id bootstrap should expand default research reviewers and review packs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-id-t4"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "research-backed change",
                    "--task-id",
                    "T4",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TASK_ID=T4", result.stdout)
            self.assertIn("report_reviewer", result.stdout)
            self.assertNotIn("test_designer", result.stdout)
            self.assertIn("python_reviewer", result.stdout)
            self.assertFalse((report_dir / "test_plan.md").is_file())
            self.assertTrue((report_dir / "report_review.md").is_file())
            self.assertTrue((report_dir / "python_review.md").is_file())
            self.assertTrue((report_dir / "reproducibility_review.md").is_file())
            self.assertTrue((report_dir / "artifact_review.md").is_file())

            self.assertFalse((report_dir / "benchmark_review.md").is_file())

    def test_run_bundle_can_enable_full_research_perspective_pack(self) -> None:
        """Named optional review packs should expand to all pack specialists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-full-research-perspective-pack"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "full research perspective smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--enable",
                    "research_perspective_review",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("benchmark_reviewer", result.stdout)
            self.assertTrue((report_dir / "reproducibility_review.md").is_file())
            self.assertTrue((report_dir / "scientific_computing_review.md").is_file())
            self.assertTrue((report_dir / "benchmark_review.md").is_file())
            self.assertTrue((report_dir / "artifact_review.md").is_file())
            self.assertTrue((report_dir / "fair_data_review.md").is_file())
            self.assertTrue((report_dir / "ml_science_review.md").is_file())

    def test_run_bundle_can_enable_cpp_reviewer(self) -> None:
        """C++ reviewer should create its review artifact when enabled."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-cpp-reviewer"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "cpp reviewer smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--enable",
                    "cpp_reviewer",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("cpp_reviewer", result.stdout)
            self.assertIn("cpp_review.md", result.stdout)
            self.assertTrue((report_dir / "cpp_review.md").is_file())

    def test_bootstrap_discovers_language_review_candidate_from_changed_path_hint(
        self,
    ) -> None:
        """Changed-path hints should expose a C++ review candidate without activation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / "WORKTREE_SCOPE.md").write_text(
                "# Worktree Scope\n\n## Editable Directories\n- `src`\n- `include`\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT_PATH),
                    "--task",
                    "native language review candidate smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-language-cpp-candidate",
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(workspace_root),
                    "--changed-path",
                    "src/example.cpp",
                    "--changed-path",
                    "include/example.hpp",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / "test-language-cpp-candidate"

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("LANGUAGE_REVIEW_CANDIDATES=cpp_reviewer", result.stdout)
            self.assertIn("cpp_reviewer", result.stdout)
            self.assertFalse((report_dir / "cpp_review.md").exists())


def test_cleanup_parent_error_is_reported() -> None:
    """A temporary-report cleanup failure is surfaced and chains the primary error."""
    parent_root = PROJECT_ROOT
    created: list[tuple[ParentRootSideEffectBoundary, object, object]] = []
    original_create = ParentRootSideEffectBoundary.create_parent_owned_temp_directory
    original_remove = ParentRootSideEffectBoundary.remove_parent_owned_tree

    def capture_create(boundary, attestation, candidate, purpose, prefix):
        receipt = original_create(boundary, attestation, candidate, purpose, prefix)
        created.append((boundary, attestation, receipt))
        return receipt

    def fail_remove(boundary, attestation, candidate, purpose):
        raise ParentRootSideEffectError(
            ParentRootReject.ROOT_RACE_DETECTED, "injected cleanup failure"
        )

    with mock.patch.dict(
        smoke.os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent_root)}
    ), mock.patch.object(
        ParentRootSideEffectBoundary,
        "create_parent_owned_temp_directory",
        capture_create,
    ), mock.patch.object(
        ParentRootSideEffectBoundary,
        "remove_parent_owned_tree",
        fail_remove,
    ), mock.patch.object(smoke, "validate_task_catalog", side_effect=RuntimeError("primary")), mock.patch.object(
        sys, "argv", ["smoke_test_research_perspective_pack", "--run-id", "cleanup-test"]
    ):
        try:
            with unittest.TestCase().assertRaises(ParentRootSideEffectError) as raised:
                smoke.main()
            assert raised.exception.reject is ParentRootReject.ROOT_RACE_DETECTED
            assert isinstance(raised.exception.__cause__, RuntimeError)
        finally:
            for boundary, attestation, receipt in created:
                original_remove(boundary, attestation, receipt, "test-cleanup")


def test_run_bundle_can_enable_full_research_perspective_pack() -> None:
    """The full research perspective pack remains available through the smoke fixture."""
    ResearchPerspectivePackSmokeTest().test_run_bundle_can_enable_full_research_perspective_pack()


if __name__ == "__main__":
    unittest.main()
