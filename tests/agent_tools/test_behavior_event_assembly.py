# @dependency-start
# contract test
# responsibility Tests canonical behavior-event assembly and cardinality.
# upstream implementation ../../tools/agent_tools/behavior_event_assembly.py owns behavior-event assembly.
# @dependency-end
"""Focused tests for pure behavior-record assembly."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from behavior_event_assembly import (  # noqa: E402
    FinalHandlerResult,
    HookInvocationParts,
    record_hook_invocation,
)
from prompt_classifier import PromptClassifierInputs  # noqa: E402
from tool_selection import select_tools  # noqa: E402
from workflow_context import WorkflowContext  # noqa: E402


class BehaviorEventAssemblyTest(unittest.TestCase):
    def test_eligible_record_has_deterministic_identity(self) -> None:
        payload = {"prompt": "use $task-routing"}
        parts = HookInvocationParts(
            "UserPromptSubmit", "run-1", payload, "parsed", FinalHandlerResult(),
            PromptClassifierInputs(payload["prompt"], Path("."), {}, {}), select_tools(payload), None,
            WorkflowContext(), "f" * 64, "2026-01-01T00:00:00Z", Path("."),
        )
        first = record_hook_invocation(parts)
        second = record_hook_invocation(parts)
        self.assertIsNotNone(first)
        self.assertEqual(first.event_id, second.event_id if second else "")

    def test_report_directory_is_empty_when_no_run_bundle_is_active(self) -> None:
        """A spool-only behavior event must not invent a source-root report path."""
        parts = HookInvocationParts(
            hook_event_name="UserPromptSubmit",
            hook_invocation_id="run-no-report",
            hook_payload={"prompt": "use $task-routing"},
            handler_result=FinalHandlerResult(),
            classifier_rules=PromptClassifierInputs("use $task-routing", Path("/active-root"), {}, {}),
            payload_fingerprint="f" * 64,
            timestamp="2026-01-01T00:00:00Z",
            root=Path("/active-root"),
        )

        event = record_hook_invocation(parts)

        self.assertIsNotNone(event)
        self.assertEqual(event.as_dict()["workflow_monitor_report_dir"], "")
        self.assertEqual(
            record_hook_invocation(replace(parts, report_dir=Path("/run-bundle"))).as_dict()[
                "workflow_monitor_report_dir"
            ],
            "/run-bundle",
        )


if __name__ == "__main__":
    unittest.main()
