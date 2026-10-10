# @dependency-start
# contract test
# responsibility Tests exact execution-resource projection validation.
# upstream implementation ../../tools/runtime/container/execution_resource_projection.py owns projection validation.
# @dependency-end
"""Focused tests for projection byte validation."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from tools.runtime.container.execution_resource_projection import ProjectionError, validate_projection_bytes  # noqa: E402


class ExecutionResourceProjectionTest(unittest.TestCase):
    def test_rejects_oversized_projection(self) -> None:
        with self.assertRaises(ProjectionError):
            validate_projection_bytes("x" * (65 * 1024))

    def test_runtime_identity_projection_rejects_legacy_receipt_field(self) -> None:
        projection = {
            "admission": {
                "admission_fingerprint": "a" * 64,
                "guarantee": "run-level-opaque-uuid-admission",
                "namespace_id": "pid:[4026531836]",
                "runtime_identity_fingerprint": "b" * 64,
                "selected_uuids": ["GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            },
            "completion_coverage_path": "reports/agents/run/runtime/completion_coverage.json",
            "error": None,
            "exit_code": 0,
            "plan_fingerprint": "c" * 64,
            "plan_path": "reports/agents/run/runtime/execution_resource_plan.json",
            "projection": "post_tool_use",
            "run_id": "run",
            "schema_version": "execution-resource-plan-projection/v2",
        }
        output = json.dumps(projection, sort_keys=True, separators=(",", ":")) + "\n"
        validated = validate_projection_bytes(output)
        self.assertEqual(
            validated["admission"]["runtime_identity_fingerprint"],
            "b" * 64,
        )

        admission = projection["admission"]
        admission["provision_receipt_fingerprint"] = admission.pop(
            "runtime_identity_fingerprint"
        )
        output = json.dumps(projection, sort_keys=True, separators=(",", ":")) + "\n"
        with self.assertRaises(ProjectionError):
            validate_projection_bytes(output)


if __name__ == "__main__":
    unittest.main()
