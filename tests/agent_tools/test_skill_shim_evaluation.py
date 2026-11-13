"""Native integration coverage for Skill shim evaluation artifacts."""

# @dependency-start
# contract test
# responsibility Verifies native route-golden and fresh measurement CLI schemas and runtime receipts.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md route/measurement producer contract
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/skill_shim_evaluation.rs native evaluation producer
# downstream implementation ../../tools/bin/agent-canon native producer entrypoint
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", str(PROJECT_ROOT / "tools/bin/agent-canon"))
)
EVAL_MANIFEST = PROJECT_ROOT / "eval/definitions/skill_runtime_shim_eval.toml"
ROUTE_MANIFEST = PROJECT_ROOT / "eval/definitions/workflow_selection_eval.toml"
HOST_EVALUATIONS = PROJECT_ROOT / "tests/fixtures/skill-runtime-shim/host-evaluations"


class SkillShimEvaluationTest(unittest.TestCase):
    """Verify native producer outputs through the public CLI boundary."""

    def run_producer(
        self, *args: str, runtime_root: Path
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime_root)
        return subprocess.run(
            [str(AGENT_CANON_CLI), "skill-shim-evaluation", *args],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_route_golden_uses_native_selector_and_external_runtime_receipt(
        self,
    ) -> None:
        """Frozen prompts are routed natively and written under the explicit runtime root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime_root = Path(tmp_dir) / "runtime"
            output = runtime_root / "reports/route-golden.json"
            source_tmp = PROJECT_ROOT / ".agent-canon/tmp"
            before = (
                tuple(
                    sorted(
                        path.relative_to(source_tmp) for path in source_tmp.rglob("*")
                    )
                )
                if source_tmp.exists()
                else ()
            )
            result = self.run_producer(
                "route-golden",
                "--root",
                str(PROJECT_ROOT),
                "--manifest",
                str(ROUTE_MANIFEST),
                "--output",
                str(output),
                runtime_root=runtime_root,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["status"], "pass")
            self.assertEqual(envelope["schema"], "agent_canon.route_golden")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["case_count"], 525)
            self.assertEqual(payload["schema"], "agent_canon.route_golden")
            self.assertEqual(
                payload["cases"][0]["invocation"]["cli"], "tools/bin/agent-canon route"
            )
            after = (
                tuple(
                    sorted(
                        path.relative_to(source_tmp) for path in source_tmp.rglob("*")
                    )
                )
                if source_tmp.exists()
                else ()
            )
            self.assertEqual(after, before)

    def test_tokens_measurement_has_paired_host_observations(self) -> None:
        """The native measurement preserves all fixture scenarios and paired reductions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime_root = Path(tmp_dir) / "runtime"
            output = runtime_root / "reports/measurement.json"
            result = self.run_producer(
                "tokens",
                "--root",
                str(PROJECT_ROOT),
                "--model",
                "gpt-5.4-mini",
                "--manifest",
                str(EVAL_MANIFEST),
                "--host-evaluation-dir",
                str(HOST_EVALUATIONS),
                "--output",
                str(output),
                runtime_root=runtime_root,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["status"], "pass")
            self.assertEqual(
                envelope["schema"], "agent_canon.skill_runtime_shim.measurement"
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["schema"], "agent_canon.skill_runtime_shim.measurement"
            )
            summary = payload["summary"]
            self.assertEqual(summary["scenario_row_count"], 12)
            self.assertGreater(summary["candidate_row_count"], 12)
            self.assertEqual(summary["deterministic_reduction_status"], "pass")
            self.assertEqual(summary["non_positive_reduction_row_count"], 0)
            self.assertEqual(
                {row["variant"] for row in payload["candidate_rows"]},
                {"current", "generated"},
            )


if __name__ == "__main__":
    unittest.main()
