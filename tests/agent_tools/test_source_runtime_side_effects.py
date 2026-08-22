"""Regression tests for source-tree runtime-output boundaries."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools.formal_proof import build_verification_commands
from tools.agent_tools.runtime_artifacts import RuntimeRootRequired
from tools.audit.audit_logger import AuditLogger

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

    def test_formal_proof_checker_never_embeds_source_reports_default(self) -> None:
        """Generated checker commands do not point at source reports."""
        command = build_verification_commands("<out-dir>/claim.lean", "lean")[0]
        self.assertNotIn("reports/", command)
        self.assertIn("${AGENT_CANON_RUNTIME_ROOT}", command)

    def test_shell_loggers_fail_with_typed_missing_root(self) -> None:
        """Shell wrappers fail before writing when the runtime root is absent."""
        scripts = (
            PROJECT_ROOT / "tools" / "run_pytest_with_logs.sh",
            PROJECT_ROOT / "tools" / "run_comprehensive_review.sh",
            PROJECT_ROOT / "tools" / "docs" / "check_worktree_scopes.sh",
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


if __name__ == "__main__":
    unittest.main()
