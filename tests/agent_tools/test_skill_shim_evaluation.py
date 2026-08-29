"""Focused tests for shim route and measurement producers."""

# @dependency-start
# contract test
# responsibility Verifies route failure normalization and fresh measurement schemas.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md route/measurement producer contract
# upstream implementation ../../eval/producers/skill_shim_evaluation.py evaluation producer
# upstream implementation ../../tools/agent/orchestration/route.py unchanged route CLI
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "eval" / "producers"
sys.path.insert(0, str(PROJECT_ROOT))

from eval.producers import skill_shim_evaluation  # noqa: E402
from tools.agent.skills.skill_shim_materializer import build_context  # noqa: E402
from eval.producers.skill_shim_evaluation import (  # noqa: E402
    ProducerError,
    _host_observation,
    _packet_manifest,
    _paired_reduction_summary,
    _validate_host_observations,
    normalize_route_result,
    route_golden,
)


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
            runtime_root = Path(tmp_dir) / "runtime"
            output = runtime_root / "measurement.json"
            environment = os.environ.copy()
            environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime_root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "skill_shim_evaluation.py"),
                    "tokens",
                    "--root",
                    str(PROJECT_ROOT),
                    "--model",
                    "gpt-5.4-mini",
                    "--manifest",
                    str(
                        PROJECT_ROOT
                        / "eval/definitions/skill_runtime_shim_eval.toml"
                    ),
                    "--host-evaluation-dir",
                    str(PROJECT_ROOT / "tests/fixtures/skill-runtime-shim/host-evaluations"),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "agent_canon.skill_runtime_shim.measurement")
            self.assertEqual(payload["summary"]["scenario_row_count"], 12)
            context = build_context(PROJECT_ROOT)
            self.assertEqual(
                payload["summary"]["candidate_row_count"],
                2 * len(context.skill_ids) + payload["summary"]["scenario_row_count"],
            )
            self.assertEqual(payload["summary"]["deterministic_reduction_status"], "pass")
            self.assertEqual(
                payload["summary"]["paired_reduction_row_count"],
                len(context.skill_ids) + payload["summary"]["scenario_row_count"] // 2,
            )
            self.assertEqual(payload["summary"]["non_positive_reduction_row_count"], 0)
            self.assertEqual(
                {row["variant"] for row in payload["candidate_rows"]},
                {"current", "generated"},
            )


def test_route_golden_uses_external_runtime_receipt(tmp_path: Path) -> None:
    """Route prompts and output use one explicit external runtime receipt."""
    parent_root = PROJECT_ROOT
    cases = tuple(
        SimpleNamespace(case_id=f"case-{index:03d}", prompt=f"prompt-{index}")
        for index in range(525)
    )
    manifest = SimpleNamespace(
        expected_case_count=525,
        expected_generated_case_count=525,
        cases=cases,
    )
    runtime_root = tmp_path / "runtime"
    output = runtime_root / "reports" / "route-golden.json"
    source_tmp = parent_root / ".agent-canon" / "tmp"
    source_tmp_before = (
        tuple(sorted(path.relative_to(source_tmp) for path in source_tmp.rglob("*")))
        if source_tmp.exists()
        else ()
    )
    original_run = subprocess.run

    def fake_run(args, **kwargs):
        command = list(args)
        if "--prompt-file" in command:
            prompt_path = Path(command[command.index("--prompt-file") + 1])
            assert prompt_path.is_relative_to(runtime_root)
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps({"schema": "agent_canon.route.skill_route.v1"}).encode(),
                b"",
            )
        return original_run(args, **kwargs)

    with mock.patch.dict(
        os.environ, {"AGENT_CANON_RUNTIME_ROOT": str(runtime_root)}, clear=False
    ), mock.patch.object(
        skill_shim_evaluation, "load_manifest", return_value=manifest
    ), mock.patch.object(skill_shim_evaluation.subprocess, "run", side_effect=fake_run):
        payload = route_golden(
            parent_root,
            parent_root / "manifest.toml",
            parent_root / "route.py",
            output,
        )

    assert payload["case_count"] == 525
    assert output.is_file()
    source_tmp_after = (
        tuple(sorted(path.relative_to(source_tmp) for path in source_tmp.rglob("*")))
        if source_tmp.exists()
        else ()
    )
    assert source_tmp_after == source_tmp_before

    def test_host_pairs_fail_closed_for_every_manifest_scenario(self) -> None:
        """Missing, duplicate, mismatched, and incomplete observations fail directly."""
        manifest = PROJECT_ROOT / "eval/definitions/skill_runtime_shim_eval.toml"
        _, packets = _packet_manifest(manifest)
        host_dir = PROJECT_ROOT / "tests/fixtures/skill-runtime-shim/host-evaluations"
        rows = [_host_observation(path) for path in sorted(host_dir.glob("*.json"))]

        with self.assertRaisesRegex(ProducerError, "host_observation_missing"):
            _validate_host_observations(rows[:-1], packets)
        with self.assertRaisesRegex(ProducerError, "host_observation_duplicate"):
            _validate_host_observations(rows + [rows[0]], packets)
        mismatched = [dict(row) for row in rows]
        mismatched[0]["packet_id"] = "wrong-packet"
        with self.assertRaisesRegex(ProducerError, "host_observation_mismatch"):
            _validate_host_observations(mismatched, packets)

        wrong_category = [dict(row) for row in rows]
        wrong_category[0]["category"] = "toolcall-route"
        with self.assertRaisesRegex(ProducerError, "host_observation_mismatch"):
            _validate_host_observations(wrong_category, packets)

        wrong_packet_class = [dict(row) for row in rows]
        wrong_packet_class[0]["packet_class"] = "changed"
        with self.assertRaisesRegex(ProducerError, "host_observation_mismatch"):
            _validate_host_observations(wrong_packet_class, packets)

        unrelated = [dict(row) for row in rows]
        unrelated[0]["prompt"] = "UNRELATED PROMPT"
        with self.assertRaisesRegex(ProducerError, "host_observation_unrelated_prompt"):
            _validate_host_observations(unrelated, packets)

        wrong_skill = [dict(row) for row in rows]
        wrong_skill[0]["skill_id"] = "wrong-skill"
        with self.assertRaisesRegex(ProducerError, "host_observation_wrong_skill_id"):
            _validate_host_observations(wrong_skill, packets)

        wrong_iteration = [dict(row) for row in rows]
        wrong_iteration[0]["iteration_id"] = "fresh-generated-02"
        with self.assertRaisesRegex(ProducerError, "host_iteration_mismatch"):
            _validate_host_observations(wrong_iteration, packets)

        wrong_prompt_digest = dict(rows[0])
        wrong_prompt_digest["prompt_digest"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "wrong-prompt-digest.json"
            path.write_text(json.dumps(wrong_prompt_digest), encoding="utf-8")
            with self.assertRaisesRegex(ProducerError, "host_prompt_digest"):
                _host_observation(path)

        incomplete = dict(rows[0])
        incomplete.pop("input_tokens")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "incomplete.json"
            path.write_text(json.dumps(incomplete), encoding="utf-8")
            with self.assertRaisesRegex(ProducerError, "host_observation_incomplete"):
                _host_observation(path)

    def test_deterministic_reduction_status_requires_positive_pair_reduction(self) -> None:
        """One non-positive scenario pair must fail the all-pair status."""
        rows = [
            {
                "row_type": "candidate",
                "candidate_row_id": "candidate-scenario-current",
                "host_envelope_id": "host-scenario-current",
                "skill_id": "skill-openai-00",
                "variant": "current",
                "utf8_bytes": 500,
                "unicode_scalars": 500,
                "denominator_status": "valid",
            },
            {
                "row_type": "candidate",
                "candidate_row_id": "candidate-scenario-generated",
                "host_envelope_id": "host-scenario-generated",
                "skill_id": "skill-openai-00",
                "variant": "generated",
                "utf8_bytes": 500,
                "unicode_scalars": 500,
                "denominator_status": "valid",
            },
            {
                "row_type": "candidate",
                "candidate_row_id": "candidate-deterministic-skill-tools-00-current",
                "host_envelope_id": "deterministic-skill-tools-00-current",
                "skill_id": "skill-tools-00",
                "variant": "current",
                "utf8_bytes": 300,
                "unicode_scalars": 300,
                "denominator_status": "valid",
            },
            {
                "row_type": "candidate",
                "candidate_row_id": "candidate-deterministic-skill-tools-00-generated",
                "host_envelope_id": "deterministic-skill-tools-00-generated",
                "skill_id": "skill-tools-00",
                "variant": "generated",
                "utf8_bytes": 250,
                "unicode_scalars": 250,
                "denominator_status": "valid",
            },
        ]
        scenario_rows = [
            {
                "scenario_id": "scenario-openai",
                "candidate_row_id": "candidate-scenario-current",
                "variant": "current",
            },
            {
                "scenario_id": "scenario-openai",
                "candidate_row_id": "candidate-scenario-generated",
                "variant": "generated",
            },
        ]
        self.assertEqual(
            ("fail", 1, 1),
            _paired_reduction_summary(rows, scenario_rows),
        )

    def test_deterministic_reduction_status_fail_closed_for_duplicate_or_missing_pairs(self) -> None:
        """Duplicate or missing deterministic current/generated pairs fail closed."""
        current = {
            "row_type": "candidate",
            "candidate_row_id": "candidate-current",
            "host_envelope_id": "deterministic-skill-openai-00-current",
            "skill_id": "skill-openai-00",
            "variant": "current",
            "utf8_bytes": 500,
            "unicode_scalars": 500,
            "denominator_status": "valid",
        }
        duplicate = dict(current)
        duplicate["candidate_row_id"] = "candidate-current-duplicate"
        with self.assertRaisesRegex(ProducerError, "candidate_pair_duplicate"):
            _paired_reduction_summary(
                [
                    current,
                    duplicate,
                ]
            )
        with self.assertRaisesRegex(ProducerError, "candidate_pair_missing"):
            _paired_reduction_summary([current])


if __name__ == "__main__":
    unittest.main()
