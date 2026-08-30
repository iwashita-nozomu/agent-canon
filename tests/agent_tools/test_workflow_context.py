# @dependency-start
# contract test
# responsibility Tests workflow-context storage and fail-open readback.
# upstream implementation ../../tools/agent/orchestration/workflow_context.py owns workflow context.
# @dependency-end
"""Focused tests for workflow context fail-open storage."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from tools.agent.orchestration.workflow_context import WorkflowContext, load_workflow_context, store_workflow_context  # noqa: E402


class WorkflowContextTest(unittest.TestCase):
    def test_store_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "context.json"
            self.assertEqual(store_workflow_context(path, WorkflowContext(("route",), "t", "event")).status, "stored")
            self.assertEqual(load_workflow_context(path).workflows, ("route",))


if __name__ == "__main__":
    unittest.main()
