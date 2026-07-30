"""Focused tests for shim route and measurement producers."""

# @dependency-start
# contract test
# responsibility Verifies route failure normalization and fresh measurement schemas.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md route/measurement producer contract
# upstream implementation ../../tools/agent_tools/skill_shim_evaluation.py evaluation producer
# upstream implementation ../../tools/agent_tools/route.py unchanged route CLI
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from skill_shim_evaluation import normalize_route_result  # noqa: E402


class SkillShimEvaluationTest(unittest.TestCase):
    """Verify exact producer failure and measurement contracts."""

    def test_route_golden_normalizes_argparse_error(self) -> None:
        """Argparse usage/error output maps to the stable producer failure."""
        completed = subprocess.CompletedProcess(
            args=["route.py"],
            returncode=2,
            stdout=b"",
            stderr=b"usage: route.py [-h]\nroute.py: error: argument --mode: invalid choice\n",
        )
        status, route, failure = normalize_route_result(completed, mode="repo-changing")
        self.assertEqual(status, "fail")
        self.assertEqual(route["schema"], "agent_canon.route.skill_route.v1")
        self.assertEqual(
            failure,
            {
                "code": "ARGUMENT_ERROR",
                "class": "argument",
                "exit_code": 2,
                "stderr_sha256": "8b45c9c12c52a327356b3fe26ee46f954b791b14bfd2fc3ba1883bba1a39a80f",
            },
        )

    def test_tokens_measurement_fixture_has_paired_rows(self) -> None:
        """The fresh host fixture has current/generated rows and no absent usage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "measurement.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "skill_shim_evaluation.py"),
                    "tokens",
                    "--root",
                    str(PROJECT_ROOT),
                    "--model",
                    "gpt-5.4-mini",
                    "--host-evaluation-dir",
                    str(PROJECT_ROOT / "tests/fixtures/skill-runtime-shim/host-evaluations"),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "agent_canon.skill_runtime_shim.measurement")
            self.assertEqual(payload["summary"]["scenario_row_count"], 12)
            self.assertEqual(payload["summary"]["candidate_row_count"], 132)
            self.assertEqual(payload["summary"]["deterministic_reduction_status"], "pass")
            self.assertEqual(
                {row["variant"] for row in payload["candidate_rows"]},
                {"current", "generated"},
            )


if __name__ == "__main__":
    unittest.main()
