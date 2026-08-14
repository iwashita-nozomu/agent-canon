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
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

import skill_shim_evaluation  # noqa: E402
from skill_route_catalog import load_skill_catalog  # noqa: E402
from skill_shim_evaluation import (  # noqa: E402
    ProducerError,
    _host_envelope_value,
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
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir:
            output = Path(tmp_dir) / "measurement.json"
            environment = os.environ | {"AGENT_CANON_PARENT_ROOT": str(PROJECT_ROOT)}
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
                        / "evidence/agent-evals/skill_runtime_shim_eval.toml"
                    ),
                    "--host-evaluation-dir",
                    str(PROJECT_ROOT / "tests/fixtures/skill-runtime-shim/host-evaluations"),
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "agent_canon.skill_runtime_shim.measurement")
            self.assertEqual(payload["summary"]["scenario_row_count"], 12)
            catalog = load_skill_catalog(PROJECT_ROOT)
            self.assertEqual(
                payload["summary"]["candidate_row_count"],
                payload["summary"]["scenario_row_count"]
                + (2 * len(catalog["skill_families"])),
            )
            self.assertEqual(
                payload["summary"]["host_envelope_count"],
                (payload["summary"]["scenario_row_count"] // 2)
                + len(catalog["skill_families"]),
            )
            self.assertEqual(payload["summary"]["deterministic_reduction_status"], "pass")
            self.assertEqual(
                payload["summary"]["paired_reduction_row_count"],
                len(catalog["skill_families"]),
            )
            self.assertEqual(
                payload["summary"]["valid_denominator_row_count"],
                2 * len(catalog["skill_families"]),
            )
            self.assertEqual(payload["summary"]["not_applicable_row_count"], 0)
            self.assertEqual(payload["summary"]["non_positive_reduction_row_count"], 0)
            self.assertEqual(
                {row["variant"] for row in payload["candidate_rows"]},
                {"current", "generated"},
            )

    def test_host_envelope_uses_automatic_discovery_fields_only(self) -> None:
        """Measurement envelopes do not depend on materializer host_entries."""
        envelope = _host_envelope_value(
            "gpt-5.4-mini", "medium", "agent-orchestration", "a" * 64
        )
        self.assertEqual(
            set(envelope),
            {"model_id", "host_profile", "skill_id", "prompt_sha256"},
        )
        self.assertNotIn("config_entry_index", envelope)
        self.assertNotIn("config_order", envelope)
        self.assertNotIn("config_path", envelope)
        self.assertNotIn("enabled", envelope)

    def test_measurement_accepts_context_without_host_entries(self) -> None:
        """The evaluator consumes only the v2 context fields it needs."""
        context = SimpleNamespace(
            skill_ids=("agent-orchestration",),
            source_snapshot_digest="a" * 64,
        )
        observations = [
            {
                "skill_id": "agent-orchestration",
                "variant": variant,
                "prompt": "prompt",
                "scenario_id": "scenario",
                "packet_id": "packet",
                "iteration_id": f"iteration-{variant}",
                "input_tokens": 1,
                "canonical_followup_input_tokens": 0,
                "cache_fields_observed": {},
            }
            for variant in ("current", "generated")
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            host_dir = Path(tmp_dir) / "host"
            host_dir.mkdir()
            for variant in ("current", "generated"):
                (host_dir / f"{variant}.json").write_text("{}", encoding="utf-8")
            output = Path(tmp_dir) / "measurement.json"
            with mock.patch.object(
                skill_shim_evaluation, "build_context", return_value=context
            ), mock.patch.object(
                skill_shim_evaluation,
                "_packet_manifest",
                return_value=(
                    {},
                    [
                        {
                            "scenario_id": "scenario",
                            "id": "packet",
                            "category": "discovery-selection",
                            "packet_class": "full",
                            "packet_prompt_sha256": "0" * 64,
                            "target_skill_id": "agent-orchestration",
                            "iteration_ids": {},
                        }
                    ],
                ),
            ), mock.patch.object(
                skill_shim_evaluation, "_validate_host_observations"
            ), mock.patch.object(
                skill_shim_evaluation,
                "_host_observation",
                side_effect=observations,
            ), mock.patch.object(
                skill_shim_evaluation, "build_record", return_value={}
            ), mock.patch.object(
                skill_shim_evaluation, "render_shim", return_value="g"
            ), mock.patch.object(
                skill_shim_evaluation, "_git_content", return_value=b"current" * 20
            ), mock.patch.object(
                skill_shim_evaluation, "_parent_write"
            ):
                payload = skill_shim_evaluation.measurement(
                    PROJECT_ROOT,
                    "gpt-5.4-mini",
                    "medium",
                    Path(tmp_dir) / "manifest.toml",
                    host_dir,
                    output,
                )
        self.assertEqual(payload["summary"]["deterministic_reduction_status"], "pass")
        self.assertEqual(payload["summary"]["paired_reduction_row_count"], 1)
        self.assertEqual(payload["summary"]["host_envelope_count"], 2)
        self.assertTrue(payload["host_envelopes"])
        self.assertTrue(
            all(
                not {"config_entry_index", "config_order", "config_path", "enabled"}
                & set(envelope)
                for envelope in payload["host_envelopes"]
            )
        )


def test_route_golden_uses_parent_temp_receipt() -> None:
    """Route prompts are staged under one parent-owned temporary receipt."""
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
    created: list[object] = []
    original_create = skill_shim_evaluation.ParentRootSideEffectBoundary.create_parent_owned_temp_directory
    original_run = subprocess.run

    def capture_create(boundary, attestation, candidate, purpose, prefix):
        receipt = original_create(boundary, attestation, candidate, purpose, prefix)
        created.append(receipt)
        return receipt

    def fake_run(args, **kwargs):
        command = list(args)
        if "--prompt-file" in command:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps({"schema": "agent_canon.route.skill_route.v1"}).encode(),
                b"",
            )
        return original_run(args, **kwargs)

    with mock.patch.dict(
        os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent_root)}
    ), mock.patch.object(
        skill_shim_evaluation, "load_manifest", return_value=manifest
    ), mock.patch.object(
        skill_shim_evaluation.ParentRootSideEffectBoundary,
        "create_parent_owned_temp_directory",
        capture_create,
    ), mock.patch.object(skill_shim_evaluation.subprocess, "run", side_effect=fake_run):
        output = Path(
            os.environ.get(
                "TMPDIR", str(parent_root / ".agent-canon" / "validation")
            )
        ) / "route-golden.json"
        payload = route_golden(parent_root, parent_root / "manifest.toml", parent_root / "route.py", output)

    assert payload["case_count"] == 525
    assert len(created) == 1
    assert not created[0].physical_path.exists()
    with mock.patch.dict(
        os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent_root)}
    ):
        boundary, attestation = skill_shim_evaluation._parent_capability(
            "test-route-cleanup"
        )
        output_receipt = boundary.resolve_parent_owned_path(
            attestation, output, "test-route-cleanup", create=False
        )
        boundary.remove_parent_owned_file(output_receipt)

    def test_host_pairs_fail_closed_for_every_manifest_scenario(self) -> None:
        """Missing, duplicate, mismatched, and incomplete observations fail directly."""
        manifest = PROJECT_ROOT / "evidence/agent-evals/skill_runtime_shim_eval.toml"
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
                "host_envelope_id": "deterministic-skill-tools-00",
                "skill_id": "skill-tools-00",
                "variant": "current",
                "utf8_bytes": 300,
                "unicode_scalars": 300,
                "denominator_status": "valid",
            },
            {
                "row_type": "candidate",
                "candidate_row_id": "candidate-deterministic-skill-tools-00-generated",
                "host_envelope_id": "deterministic-skill-tools-00",
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
            "host_envelope_id": "deterministic-skill-openai-00",
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
