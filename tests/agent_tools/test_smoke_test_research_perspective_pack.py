# @dependency-start
# contract test
# responsibility Tests test smoke test research perspective pack behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Smoke-test coverage for the research perspective pack helper."""

from __future__ import annotations

from contextlib import contextmanager
import subprocess
import sys
import tempfile
import unittest
import os
from pathlib import Path
from typing import Iterator
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


@contextmanager
def temporary_smoke_runtime() -> Iterator[tuple[Path, Path, Path]]:
    """Allocate parent, workspace, and report state outside the source tree."""
    with tempfile.TemporaryDirectory(prefix="agent-canon-research-smoke-") as tmp_dir:
        runtime_root = Path(tmp_dir)
        workspace_root = runtime_root / "workspace"
        report_root = runtime_root / "reports"
        (runtime_root / "tmp").mkdir()
        (runtime_root / "pycache").mkdir()
        workspace_root.mkdir()
        report_root.mkdir()
        (workspace_root / ".codex").mkdir()
        (workspace_root / ".codex" / "config.toml").write_bytes(
            (PROJECT_ROOT / ".codex" / "config.toml").read_bytes()
        )
        subprocess.run(
            ["git", "init", "--quiet", str(runtime_root)], check=True
        )
        subprocess.run(
            ["git", "-C", str(runtime_root), "config", "user.email", "agent-canon-test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(runtime_root), "config", "user.name", "AgentCanon test"],
            check=True,
        )
        yield runtime_root, workspace_root, report_root


def smoke_environment(runtime_root: Path) -> dict[str, str]:
    """Route child-process caches and temporary files outside AgentCanon source."""
    return {
        **os.environ,
        "AGENT_CANON_PARENT_ROOT": str(runtime_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": str(runtime_root / "pycache"),
        "TMPDIR": str(runtime_root / "tmp"),
        "TEMP": str(runtime_root / "tmp"),
        "TMP": str(runtime_root / "tmp"),
        "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": str(runtime_root),
    }


class ResearchPerspectivePackSmokeTest(unittest.TestCase):
    """Verify that the smoke-test helper exits successfully."""

    def test_run_bundle_includes_document_flow_review_artifact(self) -> None:
        """The always-on bundle should create the document flow review artifact."""
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
            self.assertIn("- focused_recheck_complete: not_applicable", closeout_text)
            self.assertIn("- canonical_tree_head_complete: no", closeout_text)
            self.assertIn("- agent_evaluation_complete: no", closeout_text)
            self.assertIn("- verifier_status: pending", closeout_text)
            self.assertIn("- auditor_status: pending", closeout_text)

    def test_run_bundle_can_enable_academic_writing_reviewers(self) -> None:
        """Academic writing reviewers should create their review artifacts when enabled."""
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                    "--enable",
                    "citation_evidence_reviewer",
                    "--enable",
                    "notation_definition_reviewer",
                    "--enable",
                    "logic_gap_reviewer",
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / run_id

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("TASK_ID=T10", result.stdout)
            self.assertIn("citation_evidence_reviewer", result.stdout)
            self.assertNotIn("citation_evidence_review.md", result.stdout)
            self.assertFalse((report_dir / "citation_evidence_review.md").is_file())
            self.assertFalse((report_dir / "notation_definition_review.md").is_file())
            self.assertFalse((report_dir / "logic_gap_review.md").is_file())

    def test_task_id_expands_default_research_reviewers(self) -> None:
        """Task-id bootstrap should expand default research reviewers and review packs."""
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
            self.assertFalse((report_dir / "report_review.md").is_file())
            self.assertFalse((report_dir / "python_review.md").is_file())
            self.assertFalse((report_dir / "reproducibility_review.md").is_file())
            self.assertFalse((report_dir / "artifact_review.md").is_file())

            self.assertFalse((report_dir / "benchmark_review.md").is_file())

    def test_run_bundle_can_enable_full_research_perspective_pack(self) -> None:
        """Named optional review packs should expand to all pack specialists."""
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                    "--enable",
                    "research_perspective_review",
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
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
                    str(workspace_root),
                    "--enable",
                    "cpp_reviewer",
                ],
                cwd=PROJECT_ROOT,
                env=smoke_environment(runtime_root),
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
        with temporary_smoke_runtime() as (runtime_root, workspace_root, report_root):
            (workspace_root / ".codex").mkdir(parents=True, exist_ok=True)
            (workspace_root / ".codex" / "config.toml").write_bytes(
                (PROJECT_ROOT / ".codex" / "config.toml").read_bytes()
            )
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
                env=smoke_environment(runtime_root),
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
    runtime = tempfile.TemporaryDirectory(prefix="agent-canon-research-cleanup-")
    parent_root = Path(runtime.name)
    subprocess.run(["git", "init", "--quiet", str(parent_root)], check=True)
    subprocess.run(
        ["git", "-C", str(parent_root), "config", "user.email", "agent-canon-test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(parent_root), "config", "user.name", "AgentCanon test"],
        check=True,
    )
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
            runtime.cleanup()


def test_run_bundle_can_enable_full_research_perspective_pack() -> None:
    """The full research perspective pack remains available through the smoke fixture."""
    ResearchPerspectivePackSmokeTest().test_run_bundle_can_enable_full_research_perspective_pack()


if __name__ == "__main__":
    unittest.main()
