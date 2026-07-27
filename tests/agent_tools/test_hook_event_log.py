"""Residual tests for the bounded PostToolUse hook-event spool."""

# @dependency-start
# contract test
# responsibility Tests O(1) hook spooling, no-replace identity, and dispatcher-clean failures.
# upstream design ../../documents/runtime/runtime-log-archive.md bounded hook-event spool and explicit checkpoint policy
# upstream implementation ../../.codex/hooks/hook_event_log.py publishes per-event spool files
# upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py checks hot-path reachability
# @dependency-end

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = PROJECT_ROOT / ".codex" / "hooks"
TOOLS_DIR = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(TOOLS_DIR))

import hook_dispatcher  # noqa: E402
import hook_event_log  # noqa: E402
import runtime_log_archive_git  # noqa: E402


def hook_entry(hook_run_id: str, *, status: str = "pass") -> dict[str, object]:
    """Return one minimal canonical hook entry before context-owned fields."""
    return {
        "hook_run_id": hook_run_id,
        "timestamp": "2026-07-18T00:00:00Z",
        "payload_fingerprint": f"fingerprint-{hook_run_id}",
        "status": status,
    }


class HookEventLogHotPathTest(unittest.TestCase):
    """Own H-01, H-02, and H-05 residual behavior."""

    def test_h01_static_checker_rejects_no_reachable_blocking_or_output_calls(self) -> None:
        hook_path = HOOKS_DIR / "hook_event_log.py"
        self.assertEqual(runtime_log_archive_git.check_hook_hot_path(hook_path), ())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = runtime_log_archive_git.command_check_hook_hot_path(hook_path)
        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                f"RUNTIME_LOG_HOT_PATH_PATH={hook_path}",
                "RUNTIME_LOG_HOT_PATH_FORBIDDEN_COUNT=0",
                "RUNTIME_LOG_HOT_PATH=pass",
            ],
        )

    def test_h01_static_checker_rejects_transitive_forbidden_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            hook_path = root / ".codex" / "hooks" / "hook_event_log.py"
            runtime_paths = root / "tools" / "agent_tools" / "runtime_log_paths.py"
            hook_path.parent.mkdir(parents=True)
            runtime_paths.parent.mkdir(parents=True)
            runtime_paths.write_text(
                "import subprocess as process\n"
                "execute = process.run\n"
                "\n"
                "def repo_log_key(root: object) -> str:\n"
                "    invoke = forbidden_helper\n"
                "    return invoke()\n"
                "\n"
                "def forbidden_helper() -> str:\n"
                "    local_execute = execute\n"
                "    local_execute(['git', 'status'])\n"
                "    return 'repo'\n",
                encoding="utf-8",
            )
            hook_path.write_text(
                "from __future__ import annotations\n"
                "from runtime_log_paths import repo_log_key as key\n"
                "\n"
                "class HookLogContext:\n"
                "    def append(self, entry: dict[str, object]) -> HookAppendResult:\n"
                "        key(entry)\n"
                "        return HookAppendResult()\n"
                "\n"
                "def canonical_hook_event_bytes(entry: dict[str, object]) -> bytes:\n"
                "    return b''\n"
                "\n"
                "def publish_hook_event_noreplace(path: object, bytes_: bytes) -> tuple[str, str]:\n"
                "    return ('spooled', '')\n",
                encoding="utf-8",
            )
            findings = runtime_log_archive_git.check_hook_hot_path(hook_path)
            self.assertIn("forbidden:subprocess.run", findings)

            runtime_paths.write_text(
                "def repo_log_key(root: object) -> str:\n"
                "    return 'repo'\n",
                encoding="utf-8",
            )
            hook_path.write_text(
                "from __future__ import annotations\n"
                "import sys as streams\n"
                "from runtime_log_paths import repo_log_key\n"
                "\n"
                "class HookLogContext:\n"
                "    def append(self, entry: dict[str, object]) -> HookAppendResult:\n"
                "        invoke = output_helper\n"
                "        invoke()\n"
                "        return HookAppendResult()\n"
                "\n"
                "def output_helper() -> None:\n"
                "    sink = streams.stderr.write\n"
                "    sink('forbidden')\n"
                "    other_sink = streams.stdout.write\n"
                "    other_sink('forbidden')\n"
                "    printer = print\n"
                "    printer('forbidden')\n"
                "\n"
                "def canonical_hook_event_bytes(entry: dict[str, object]) -> bytes:\n"
                "    return b''\n"
                "\n"
                "def publish_hook_event_noreplace(path: object, bytes_: bytes) -> tuple[str, str]:\n"
                "    return ('spooled', '')\n",
                encoding="utf-8",
            )
            output_findings = runtime_log_archive_git.check_hook_hot_path(hook_path)
            self.assertIn("output:sys.stderr.write", output_findings)
            self.assertIn("output:sys.stdout.write", output_findings)
            self.assertIn("output:print", output_findings)

    def test_h02_concurrent_events_use_independent_no_replace_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = hook_event_log.HookLogContext(
                root,
                "PostToolUse",
                str(root / "legacy-hook.jsonl"),
            )
            with patch.dict(
                os.environ,
                {"AGENT_CANON_HOOK_RUN_NAMESPACE": "test-runtime"},
                clear=False,
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = tuple(
                        executor.map(
                            context.append,
                            (hook_entry("event-a"), hook_entry("event-b", status="fail")),
                        )
                    )

                self.assertEqual({result.status for result in results}, {"spooled"})
                self.assertEqual(len({result.spool_path for result in results}), 2)
                for result in results:
                    self.assertTrue(result.spool_path.is_file())
                    self.assertEqual(
                        result.event_sha256,
                        hashlib.sha256(result.spool_path.read_bytes()).hexdigest(),
                    )

                same_entry = hook_entry("event-contended")
                with ThreadPoolExecutor(max_workers=2) as executor:
                    contended = tuple(
                        executor.map(context.append, (same_entry, dict(same_entry)))
                    )
                self.assertEqual(
                    sorted(result.status for result in contended),
                    ["duplicate", "spooled"],
                )
                self.assertEqual(len({result.spool_path for result in contended}), 1)
                contended_path = contended[0].spool_path
                contended_bytes = contended_path.read_bytes()
                self.assertTrue(contended_bytes.endswith(b"\n"))
                self.assertEqual(
                    {result.event_sha256 for result in contended},
                    {hashlib.sha256(contended_bytes).hexdigest()},
                )

                duplicate = context.append(hook_entry("event-a"))
                conflict = context.append(hook_entry("event-a", status="warn"))
                self.assertEqual((duplicate.status, duplicate.error_code), ("duplicate", ""))
                self.assertEqual(
                    (conflict.status, conflict.error_code),
                    ("failed", "spool_conflict"),
                )

    def test_h05_spool_failure_emits_nothing_and_dispatcher_json_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context = hook_event_log.HookLogContext(root, "PostToolUse", str(root / "events"))
            append_stdout = io.StringIO()
            append_stderr = io.StringIO()
            with (
                patch.object(
                    hook_event_log,
                    "publish_hook_event_noreplace",
                    return_value=("failed", "spool_io_failure"),
                ),
                contextlib.redirect_stdout(append_stdout),
                contextlib.redirect_stderr(append_stderr),
            ):
                append_result = context.append(hook_entry("event-failed"))
            self.assertEqual(append_result.status, "failed")
            self.assertEqual(append_stdout.getvalue(), "")
            self.assertEqual(append_stderr.getvalue(), "")

            spec = hook_dispatcher.HookCommandSpec("fixture.py", 1)

            def child_result(*_args: object, **_kwargs: object) -> hook_dispatcher.HookResult:
                with patch.object(
                    hook_event_log,
                    "publish_hook_event_noreplace",
                    return_value=("failed", "spool_io_failure"),
                ):
                    context.append(hook_entry("event-dispatch"))
                return hook_dispatcher.HookResult(
                    spec,
                    0,
                    json.dumps({"decision": "approve", "reason": "fixture"}),
                    "",
                )

            dispatcher_stdout = io.StringIO()
            with (
                patch.dict(hook_dispatcher.EVENT_COMMANDS, {"PostToolUse": (spec,)}),
                patch.object(hook_dispatcher, "run_hook_command", side_effect=child_result),
                patch.object(hook_dispatcher, "repo_root", return_value=root),
                patch.object(hook_dispatcher, "hook_directory", return_value=HOOKS_DIR),
                contextlib.redirect_stdout(dispatcher_stdout),
            ):
                result = hook_dispatcher.dispatch_event("PostToolUse", b'{"tool_name":"fixture"}')
            self.assertEqual(result, 0)
            self.assertIsInstance(json.loads(dispatcher_stdout.getvalue()), dict)


if __name__ == "__main__":
    unittest.main()
