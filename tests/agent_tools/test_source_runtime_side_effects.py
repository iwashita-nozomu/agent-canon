"""Regression tests for source-tree runtime-output boundaries."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.analysis.proof.formal_proof import build_verification_commands

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SourceRuntimeBoundaryTest(unittest.TestCase):
    """Runtime reports and logs must not default into the checkout."""

    def test_formal_proof_checker_never_embeds_source_reports_default(self) -> None:
        """Generated checker commands do not point at source reports."""
        command = build_verification_commands("<out-dir>/claim.lean", "lean")[0]
        self.assertNotIn("reports/", command)
        self.assertIn("${AGENT_CANON_RUNTIME_ROOT}", command)

    def test_shell_loggers_fail_with_typed_missing_root(self) -> None:
        """Shell wrappers fail before writing when the runtime root is absent."""
        scripts = (
            PROJECT_ROOT / "tools" / "validation" / "tests" / "run_pytest_with_logs.sh",
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
                    str(
                        PROJECT_ROOT
                        / "tools"
                        / "validation"
                        / "tests"
                        / "run_pytest_with_logs.sh"
                    ),
                    str(
                        PROJECT_ROOT
                        / "tests"
                        / "agent_tools"
                        / "test_source_runtime_side_effects.py"
                    ),
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


if __name__ == "__main__":
    unittest.main()
