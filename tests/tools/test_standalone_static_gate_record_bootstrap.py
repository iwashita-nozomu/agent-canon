"""Tests for the standalone static-gate fixture-record bootstrap."""

# @dependency-start
# contract test
# responsibility Verifies unit-owned supervisor/record projection without per-test fixture allow-lists.
# upstream implementation ../../tools/ci/run_with_fixture_record.py unit-level signed capability adapter
# upstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh static-gate entrypoint
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py canonical session and environment owner
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools.parent_root_side_effects import (
    PRIVATE_RECORD_HANDOFF_ENV,
    PRIVATE_RECORD_PARENT_ROOT_ENV,
    PRIVATE_RECORD_REQUIRED_ENV,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
    ParentRootSideEffectError,
)
from tools.ci.run_with_fixture_record import _bootstrap_process_environment

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = PROJECT_ROOT / "tools" / "ci" / "run_with_fixture_record.py"
CHANNEL_KEYS = (
    SIDE_EFFECT_PARENT_ROOT_ENV,
    SIDE_EFFECT_HANDOFF_ENV,
    SIDE_EFFECT_REQUIRED_ENV,
    PRIVATE_RECORD_PARENT_ROOT_ENV,
    PRIVATE_RECORD_HANDOFF_ENV,
    PRIVATE_RECORD_REQUIRED_ENV,
)


class StandaloneStaticGateRecordBootstrapTest(unittest.TestCase):
    """Exercise transport classification and the real subprocess boundary."""

    def test_absent_channels_are_scrubbed_without_losing_ambient_input(self) -> None:
        environment = _bootstrap_process_environment({"KEEP_ME": "value"})
        self.assertEqual(environment, {"KEEP_ME": "value"})

    def test_complete_public_channel_is_replaced_by_unit_owned_identity(self) -> None:
        ambient = {
            "KEEP_ME": "value",
            SIDE_EFFECT_PARENT_ROOT_ENV: "/outer/repository",
            SIDE_EFFECT_HANDOFF_ENV: "outer-signed-handoff",
            SIDE_EFFECT_REQUIRED_ENV: "1",
        }
        environment = _bootstrap_process_environment(ambient)
        self.assertEqual(environment, {"KEEP_ME": "value"})

    def test_incomplete_channel_is_rejected_before_identity_projection(self) -> None:
        with self.assertRaisesRegex(
            ParentRootSideEffectError, "public_channel_incomplete"
        ):
            _bootstrap_process_environment(
                {SIDE_EFFECT_HANDOFF_ENV: "partial-handoff"}
            )

    def test_private_record_without_public_supervisor_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ParentRootSideEffectError, "private_record_without_public_supervisor"
        ):
            _bootstrap_process_environment(
                {
                    PRIVATE_RECORD_PARENT_ROOT_ENV: "/outer/repository",
                    PRIVATE_RECORD_HANDOFF_ENV: "private-signed-handoff",
                    PRIVATE_RECORD_REQUIRED_ENV: "1",
                }
            )

    def test_existing_complete_record_is_not_shadowed(self) -> None:
        with self.assertRaisesRegex(
            ParentRootSideEffectError, "fixture_record_capability_already_present"
        ):
            _bootstrap_process_environment(
                {
                    SIDE_EFFECT_PARENT_ROOT_ENV: "/outer/repository",
                    SIDE_EFFECT_HANDOFF_ENV: "outer-signed-handoff",
                    SIDE_EFFECT_REQUIRED_ENV: "1",
                    PRIVATE_RECORD_PARENT_ROOT_ENV: "/outer/repository",
                    PRIVATE_RECORD_HANDOFF_ENV: "private-signed-handoff",
                    PRIVATE_RECORD_REQUIRED_ENV: "1",
                }
            )

    def test_adapter_projects_distinct_public_and_private_channels(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agent-canon-static-record-") as directory:
            root = Path(directory).resolve()
            subprocess.run(
                ["git", "init", "-q", "-b", "main", str(root)],
                check=True,
                capture_output=True,
                text=True,
            )
            invocation_script = root / "static-gate-owner.py"
            invocation_script.write_text("# static gate owner\n", encoding="utf-8")
            probe = (
                "import json, os; "
                "print(json.dumps({"
                f"'public_parent': os.environ.get({SIDE_EFFECT_PARENT_ROOT_ENV!r}), "
                f"'public_handoff': bool(os.environ.get({SIDE_EFFECT_HANDOFF_ENV!r})), "
                f"'public_required': os.environ.get({SIDE_EFFECT_REQUIRED_ENV!r}), "
                f"'private_parent': os.environ.get({PRIVATE_RECORD_PARENT_ROOT_ENV!r}), "
                f"'private_handoff': bool(os.environ.get({PRIVATE_RECORD_HANDOFF_ENV!r})), "
                f"'private_required': os.environ.get({PRIVATE_RECORD_REQUIRED_ENV!r}), "
                "'cwd': os.getcwd()}))"
            )
            environment = os.environ.copy()
            for key in CHANNEL_KEYS:
                environment.pop(key, None)
            environment["PYTHONPATH"] = str(PROJECT_ROOT)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ADAPTER),
                    "--invocation-script",
                    str(invocation_script),
                    "--purpose",
                    "standalone-static-gate-record-test",
                    "--",
                    sys.executable,
                    "-c",
                    probe,
                ],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip())
            self.assertEqual(payload["public_parent"], str(root))
            self.assertTrue(payload["public_handoff"])
            self.assertEqual(payload["public_required"], "1")
            self.assertEqual(payload["private_parent"], str(root))
            self.assertTrue(payload["private_handoff"])
            self.assertEqual(payload["private_required"], "1")
            self.assertEqual(payload["cwd"], str(root))


if __name__ == "__main__":
    unittest.main()
