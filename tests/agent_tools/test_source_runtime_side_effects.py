"""Regression tests for source-tree runtime-output boundaries."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.analysis.proof.formal_proof import build_verification_commands
from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactError, RuntimeRootRequired
from tools.audit.logging.audit_logger import AuditLogger

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SourceRuntimeBoundaryTest(unittest.TestCase):
    """Runtime reports and logs must not default into the checkout."""

    def test_audit_logger_requires_external_runtime_root(self) -> None:
        """The implicit audit destination requires an external runtime root."""
        with tempfile.TemporaryDirectory() as source_dir:
            source = Path(source_dir)
            old_value = os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
            try:
                with self.assertRaises(RuntimeRootRequired):
                    AuditLogger(source_root=source)
            finally:
                if old_value is not None:
                    os.environ["AGENT_CANON_RUNTIME_ROOT"] = old_value

    def test_audit_logger_writes_under_explicit_runtime_root(self) -> None:
        """Audit records are placed under the caller-selected runtime root."""
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as runtime_dir,
        ):
            logger = AuditLogger(
                source_root=Path(source_dir),
                runtime_root=Path(runtime_dir),
            )
            logger.record("test_action", "test_actor")
            self.assertTrue(logger.log_file.is_file())
            self.assertTrue(logger.log_file.is_relative_to(Path(runtime_dir)))
            self.assertFalse(logger.log_file.is_relative_to(Path(source_dir)))

    def test_audit_logger_rejects_source_local_explicit_destination(self) -> None:
        """An explicit log_dir cannot bypass the AgentCanon runtime boundary."""
        with (
            tempfile.TemporaryDirectory() as source_dir,
            tempfile.TemporaryDirectory() as runtime_dir,
        ):
            with self.assertRaises(RuntimeArtifactError):
                AuditLogger(
                    source_root=Path(source_dir),
                    runtime_root=Path(runtime_dir),
                    log_dir=Path(source_dir) / "reports" / "audit",
                )

    def test_audit_logger_does_not_infer_source_from_cwd(self) -> None:
        """A runtime root alone does not silently select a parent checkout."""
        with tempfile.TemporaryDirectory() as runtime_dir:
            with self.assertRaises(RuntimeRootRequired):
                AuditLogger(runtime_root=Path(runtime_dir))

    def test_formal_proof_checker_never_embeds_source_reports_default(self) -> None:
        """Generated checker commands do not point at source reports."""
        command = build_verification_commands("<out-dir>/claim.lean", "lean")[0]
        self.assertNotIn("reports/", command)
        self.assertIn("${AGENT_CANON_RUNTIME_ROOT}", command)

    def test_document_similarity_tools_require_external_output_and_preserve_source(
        self,
    ) -> None:
        """Similarity reports are runtime artifacts, never source-tree files."""
        scripts = (
            PROJECT_ROOT / "tools" / "analysis" / "documents" / "analysis" / "find_similar_documents.py",
            PROJECT_ROOT / "tools" / "analysis" / "documents" / "analysis" / "tfidf_similar_docs.py",
        )
        source_files = tuple(
            Path(path)
            for path in subprocess.check_output(
                ["git", "ls-files", "-z"], cwd=PROJECT_ROOT
            ).decode()
            .split("\0")
            if path
        )
        before = {
            path: (PROJECT_ROOT / path).read_bytes()
            for path in source_files
            if (PROJECT_ROOT / path).is_file()
        }
        for script in scripts:
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            env.pop("AGENT_CANON_RUNTIME_ROOT", None)
            missing = subprocess.run(
                ["python3", str(script), "--min", "1.1"],
                cwd=PROJECT_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 2, script)
            self.assertIn("runtime_root_error", missing.stderr, script)

        with (
            tempfile.TemporaryDirectory() as runtime_dir,
            tempfile.TemporaryDirectory() as documents_dir,
        ):
            documents = Path(documents_dir)
            (documents / "a.md").write_text("# A\nshared paragraph\n", encoding="utf-8")
            (documents / "b.md").write_text("# B\nother paragraph\n", encoding="utf-8")
            for script in scripts:
                completed = subprocess.run(
                    [
                        "python3",
                        str(script),
                        "--documents-root",
                        documents_dir,
                        "--runtime-root",
                        runtime_dir,
                        "--min",
                        "1.1",
                    ],
                    cwd=PROJECT_ROOT,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn(runtime_dir, completed.stdout)
            self.assertTrue(tuple(Path(runtime_dir).rglob("*.txt")))

        after = {
            path: (PROJECT_ROOT / path).read_bytes()
            for path in source_files
            if (PROJECT_ROOT / path).is_file()
        }
        self.assertEqual(before, after)

    def test_shell_loggers_fail_with_typed_missing_root(self) -> None:
        """Shell wrappers fail before writing when the runtime root is absent."""
        scripts = (
            PROJECT_ROOT / "tools" / "validation" / "tests" / "run_pytest_with_logs.sh",
            PROJECT_ROOT / "tools" / "validation" / "review" / "run_comprehensive_review.sh",
            PROJECT_ROOT / "tools" / "validation" / "documentation" / "checks" / "check_worktree_scopes.sh",
        )
        for script in scripts:
            env = os.environ.copy()
            env.pop("AGENT_CANON_RUNTIME_ROOT", None)
            args = ["bash", str(script)]
            if script.name == "run_pytest_with_logs.sh":
                args.append("--collect-only")
            result = subprocess.run(
                args,
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, script)
            self.assertIn("runtime_root_error", result.stderr, script)

    def test_shell_loggers_keep_artifacts_external(self) -> None:
        """The wrappers publish logs outside the AgentCanon source checkout."""
        with tempfile.TemporaryDirectory() as runtime_dir:
            env = os.environ.copy()
            env["AGENT_CANON_RUNTIME_ROOT"] = runtime_dir
            pytest_result = subprocess.run(
                [
                    "bash",
                    str(PROJECT_ROOT / "tools" / "validation" / "tests" / "run_pytest_with_logs.sh"),
                    str(PROJECT_ROOT / "tests" / "agent_tools" / "test_source_runtime_side_effects.py"),
                    "--collect-only",
                    "-q",
                ],
                cwd=PROJECT_ROOT.parent,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(pytest_result.returncode, 0, pytest_result.stderr)
            self.assertIn(str(Path(runtime_dir)), pytest_result.stdout)
            self.assertFalse((PROJECT_ROOT / "tests" / "logs").exists())

            scope_result = subprocess.run(
                ["bash", str(PROJECT_ROOT / "tools" / "validation" / "documentation" / "checks" / "check_worktree_scopes.sh")],
                cwd=PROJECT_ROOT.parent,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(scope_result.returncode, 0, scope_result.stderr)
            self.assertIn(str(Path(runtime_dir)), scope_result.stdout)


if __name__ == "__main__":
    unittest.main()
