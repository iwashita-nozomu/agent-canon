"""Tests for the AgentCanon Lean proof environment helper."""

# @dependency-start
# contract test
# responsibility Tests Lean Mathlib/Aesop/Plausible/LeanSearchClient proof environment setup commands.
# upstream implementation ../../tools/agent_tools/lean_proof_env.py creates reusable proof and counterexample environments.
# upstream design ../../documents/tools/lean_proof_env.md documents the CLI contract.
# upstream design ../../agents/skills/formal-proof-workflow.md routes Lean proofs through Mathlib/Aesop/Plausible/LeanSearchClient.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "lean_proof_env.py"


class LeanProofEnvToolTest(unittest.TestCase):
    """Validate generated Lake environment files and checker command routing."""

    def test_smoke_dry_run_writes_mathlib_aesop_environment(self) -> None:
        """Smoke action should generate a proof-search Lake package without executing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_dir = Path(tmp_dir) / "lean-env"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "smoke",
                    "--env-dir",
                    str(env_dir),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertFalse(payload["executed"])
            self.assertIn("lake update", payload["commands"])
            self.assertTrue((env_dir / "lakefile.lean").is_file())
            self.assertTrue((env_dir / "AgentCanonLeanProofEnv.lean").is_file())
            self.assertTrue((env_dir / "AgentCanonLeanProofEnvSmoke.lean").is_file())

            lakefile = (env_dir / "lakefile.lean").read_text(encoding="utf-8")
            module = (env_dir / "AgentCanonLeanProofEnv.lean").read_text(encoding="utf-8")
            smoke = (env_dir / "AgentCanonLeanProofEnvSmoke.lean").read_text(
                encoding="utf-8"
            )
            self.assertIn("require mathlib", lakefile)
            self.assertIn('"v4.30.0"', lakefile)
            self.assertIn("import Mathlib", module)
            self.assertIn("import Aesop", module)
            self.assertIn("import Plausible", module)
            self.assertIn("import LeanSearchClient", module)
            self.assertIn("aesop", smoke)
            self.assertIn("omega", smoke)
            self.assertIn("linarith", smoke)
            self.assertIn("grind", smoke)
            self.assertIn("Plausible.Testable.check", smoke)

    def test_all_smoke_dry_run_writes_agent_and_counterexample_surfaces(self) -> None:
        """all-smoke should include proof, search, and expected-counterexample checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_dir = Path(tmp_dir) / "lean-env"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "all-smoke",
                    "--env-dir",
                    str(env_dir),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertFalse(payload["executed"])
            self.assertTrue((env_dir / "AgentCanonLeanProofEnvSmoke.lean").is_file())
            self.assertTrue((env_dir / "AgentCanonLeanProofEnvAgent.lean").is_file())
            self.assertTrue(
                (env_dir / "AgentCanonLeanProofEnvCounterexample.lean").is_file()
            )
            self.assertIn("AgentCanonLeanProofEnvAgent.lean", "\n".join(payload["commands"]))
            self.assertIn(
                "expected Plausible counterexample", "\n".join(payload["commands"])
            )

            agent = (env_dir / "AgentCanonLeanProofEnvAgent.lean").read_text(
                encoding="utf-8"
            )
            counterexample = (
                env_dir / "AgentCanonLeanProofEnvCounterexample.lean"
            ).read_text(encoding="utf-8")
            self.assertIn("LeanSearchClient.SearchResult", agent)
            self.assertIn("LeanSearchClient.SearchServer", agent)
            self.assertIn("Plausible.Testable.check", counterexample)

    def test_check_file_dry_run_routes_external_stub_through_env(self) -> None:
        """check-file should keep theorem packages outside the generated env."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            env_dir = tmp_path / "lean-env"
            stub = tmp_path / "stub.lean"
            stub.write_text("import Mathlib\n\nexample : True := by trivial\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "check-file",
                    "--env-dir",
                    str(env_dir),
                    "--lean-file",
                    str(stub),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["lean_file"], str(stub.resolve()))
            self.assertIn(str(stub.resolve()), "\n".join(payload["commands"]))
            self.assertTrue((env_dir / "lakefile.lean").is_file())


if __name__ == "__main__":
    unittest.main()
