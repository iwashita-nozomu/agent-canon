# @dependency-start
# contract test
# responsibility Tests canonical behavior-event assembly and cardinality.
# upstream implementation ../../tools/runtime/archive/behavior_event_assembly.py owns behavior-event assembly.
# @dependency-end
"""Focused tests for pure behavior-record assembly."""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from tools.runtime.archive.behavior_event_assembly import (  # noqa: E402
    FinalHandlerResult,
    HookInvocationParts,
    record_hook_invocation,
)
from tools.agent.orchestration.prompt_classifier import PromptClassifierInputs  # noqa: E402
from tools.agent.orchestration.tool_selection import select_tools  # noqa: E402
from tools.agent.orchestration.subagent_selection import select_subagents  # noqa: E402
from tools.agent.orchestration.workflow_context import WorkflowContext  # noqa: E402


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

    def test_missing_prompt_has_typed_empty_capture_fields(self) -> None:
        """An eligible tool event still records a coherent missing prompt."""
        parts = HookInvocationParts(
            hook_event_name="PostToolUse",
            hook_invocation_id="missing-prompt",
            hook_payload={"tool_name": "Bash"},
            classifier_rules=PromptClassifierInputs("", Path("."), {}, {}),
            tool_selection=select_tools({"tool_name": "Bash"}),
            payload_fingerprint="f" * 64,
            timestamp="2026-01-01T00:00:00Z",
            root=Path("."),
        )

        event = record_hook_invocation(parts)

        self.assertIsNotNone(event)
        data = event.as_dict() if event is not None else {}
        self.assertEqual(data["prompt_capture_status"], "missing")
        self.assertEqual(data["prompt_excerpt_redacted"], "")
        self.assertEqual(data["prompt_fingerprint"], "")
        self.assertEqual(data["prompt_char_count"], 0)
        self.assertFalse(data["prompt_excerpt_truncated"])

    def test_context_workflow_attribution_is_explicit(self) -> None:
        """Inherited workflow evidence is represented by context fields."""
        parts = HookInvocationParts(
            hook_event_name="PostToolUse",
            hook_invocation_id="context-workflow",
            hook_payload={"tool_name": "Bash"},
            classifier_rules=PromptClassifierInputs("", Path("."), {}, {}),
            workflow_context=WorkflowContext(("scoped-change",), "2026-01-01T00:00:00Z", "UserPromptSubmit"),
            payload_fingerprint="f" * 64,
            timestamp="2026-01-01T00:00:01Z",
            root=Path("."),
        )

        event = record_hook_invocation(parts)

        self.assertIsNotNone(event)
        data = event.as_dict() if event is not None else {}
        self.assertEqual(data["workflow_attribution_kind"], "context")
        self.assertEqual(data["workflow_context_workflows"], ["scoped-change"])
        self.assertEqual(data["workflow_owner_workflows"], [])

    def test_collaboration_operation_records_honest_transport(self) -> None:
        """Observed operation names do not imply direct peer capability."""
        parts = HookInvocationParts(
            hook_event_name="PostToolUse",
            hook_invocation_id="collaboration-operation",
            hook_payload={"tool_name": "send_message"},
            classifier_rules=PromptClassifierInputs("", Path("."), {}, {}),
            subagent_selection=select_subagents({"tool_name": "send_message"}),
            payload_fingerprint="f" * 64,
            timestamp="2026-01-01T00:00:00Z",
            root=Path("."),
        )
        event = record_hook_invocation(parts)
        self.assertIsNotNone(event)
        data = event.as_dict() if event is not None else {}
        self.assertEqual(data["subagent_event_kind"], "send_message")
        self.assertNotIn("coordination_capability_status", data)
        self.assertNotIn("coordination_mode", data)
        self.assertNotIn("coordination_receipt_status", data)


if __name__ == "__main__":
    unittest.main()
