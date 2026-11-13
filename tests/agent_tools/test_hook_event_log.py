"""Native dispatcher hook-event failure and privacy regression tests."""

# @dependency-start
# contract test
# responsibility Tests native dispatcher event-spool failure and fingerprint-only privacy.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs dispatches native hook events
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_event_log.rs owns native event serialization and spool writes
# downstream implementation ../../tools/runtime/dispatch/agent-canon/tests/hook_event_log_native.rs validates append semantics and filesystem safety
# @dependency-end

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tests.agent_tools import test_codex_hooks as codex_hooks


class HookEventDispatchTest(unittest.TestCase):
    """Own H-05 native-dispatch failure and privacy behavior."""

    def test_h05_dispatch_failure_emits_nothing_and_json_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            results = source / "hook-results"
            results.mkdir(parents=True)
            spool_blocker = results / ".event-spool"
            spool_blocker.write_text("fixture append failure", encoding="utf-8")
            result = codex_hooks.CodexHooksTest()._run_hook_in_root(
                source,
                "UserPromptSubmit",
                {
                    "hookEventName": "UserPromptSubmit",
                    "prompt": "-----BEGIN PRIVATE KEY-----",
                },
                extra_env={"AGENT_CANON_HOOK_RESULTS_DIR": str(results)},
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["decision"], "block")
            self.assertEqual(
                spool_blocker.read_text(encoding="utf-8"), "fixture append failure"
            )

    def test_h05_dispatch_spool_is_fingerprint_only(self) -> None:
        payload = {
            "hookEventName": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"cmd": "git restore secret.py"},
        }
        raw = json.dumps(payload).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source"
            source.mkdir()
            result = codex_hooks.CodexHooksTest()._run_hook_in_root(
                source, "PreToolUse", payload
            )
            event = codex_hooks.CodexHooksTest()._spooled_event(source)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertEqual(event["payload_fingerprint"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(event["status"], "blocked_destructive_git")
        for field in (
            "prompt",
            "command",
            "tool_input",
            "tool_response",
            "stdout",
            "stderr",
        ):
            self.assertNotIn(field, event)


if __name__ == "__main__":
    unittest.main()
