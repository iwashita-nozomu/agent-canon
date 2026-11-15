"""Tests for the active Codex project-local hook contract."""

# @dependency-start
# contract test
# responsibility Tests active codex hook behavior and retired-route contract.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares the three active hooks
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_safety.rs owns active safety leaves
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs owns the native typed event contract
# downstream implementation ../../tests/agent_tools/test_hook_event_log.py validates hook telemetry
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]

HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"

ACTIVE_EVENTS = ("UserPromptSubmit", "PostToolUse")


def codex_hook_command(*arguments: str) -> list[str]:
    """Select the registered native Hook route for integration tests."""
    selected_cli = os.environ.get("AGENT_CANON_CLI")
    if not selected_cli:
        raise RuntimeError("AGENT_CANON_CLI must select the native Hook CLI")
    return [selected_cli, "codex-hook", *arguments]


class CodexHooksTest(unittest.TestCase):
    """Validate active hook behavior without exercising retired hook scripts."""

    def _run_hook(
        self,
        event: str,
        payload: object,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the active dispatcher with its bounded telemetry rooted in a temp dir."""
        raw_payload = payload if isinstance(payload, str) else json.dumps(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            return subprocess.run(
                codex_hook_command(event),
                cwd=PROJECT_ROOT,
                input=raw_payload,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    **(extra_env or {}),
                    "AGENT_CANON_HOOK_SOURCE_ROOT": temp_dir,
                    "AGENT_CANON_RUNTIME_ROOT": (extra_env or {}).get(
                        "AGENT_CANON_RUNTIME_ROOT",
                        str(Path(temp_dir).parent / "hook-runtime"),
                    ),
                },
            )

    def _contract(self) -> dict[str, object]:
        result = subprocess.run(
            codex_hook_command("--contract"),
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return cast("dict[str, object]", json.loads(result.stdout))

    def _run_hook_in_root(
        self,
        root: Path,
        event: str,
        payload: object,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one hook against an isolated fixture root and return its readback."""
        raw_payload = payload if isinstance(payload, str) else json.dumps(payload)
        parent = root.parent
        if not (parent / ".git").exists():
            subprocess.run(["git", "init", "-q", str(parent)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/fixture.git",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent),
                    "-c",
                    "user.name=fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-qm",
                    "init",
                ],
                check=True,
            )
        return subprocess.run(
            codex_hook_command(event),
            cwd=PROJECT_ROOT,
            input=raw_payload,
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                **(extra_env or {}),
                "AGENT_CANON_HOOK_SOURCE_ROOT": str(root),
                "AGENT_CANON_PARENT_ROOT": (extra_env or {}).get(
                    "AGENT_CANON_PARENT_ROOT", str(parent)
                ),
                "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": (extra_env or {}).get(
                    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT", str(parent)
                ),
                "AGENT_CANON_RUNTIME_ROOT": (extra_env or {}).get(
                    "AGENT_CANON_RUNTIME_ROOT", str(parent)
                ),
            },
        )

    def _run_hook_in_layout(
        self,
        cwd: Path,
        event: str,
        payload: object,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one hook without the source-root test override."""
        raw_payload = payload if isinstance(payload, str) else json.dumps(payload)
        env = dict(os.environ)
        for key in (
            "AGENT_CANON_HOOK_EVENT_SPOOL_DIR",
            "AGENT_CANON_HOOK_SOURCE_ROOT",
            "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR",
            "AGENT_CANON_SOURCE_ROOT",
            "AGENT_CANON_ROOT",
            "AGENT_CANON_RUNTIME_ROOT",
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
        ):
            env.pop(key, None)
        env.update(extra_env or {})
        env.setdefault(
            "AGENT_CANON_RUNTIME_ROOT",
            str(cwd.parent / f".{cwd.name}-runtime"),
        )
        return subprocess.run(
            codex_hook_command(event),
            cwd=cwd,
            input=raw_payload,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    @staticmethod
    def _spooled_event(root: Path, pattern: str = "**/*.json") -> dict[str, object]:
        """Read the one isolated hook event emitted by a fixture invocation."""

        def event_paths(base: Path) -> list[Path]:
            result: list[Path] = []
            for path in base.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict) and "hook_run_id" in value:
                    result.append(path)
            return result

        paths = event_paths(root)
        if not paths:
            for runtime_root in (
                root.parent,
                root.parent / f".{root.name}-runtime",
            ):
                paths = event_paths(runtime_root)
                if paths:
                    break
        if len(paths) != 1:
            raise AssertionError(f"expected one spooled event, found {paths}")
        return cast(
            "dict[str, object]", json.loads(paths[0].read_text(encoding="utf-8"))
        )

    def test_active_hook_config_has_exact_two_events(self) -> None:
        """Project config registers prompt safety and execution-resource events."""
        hooks = cast(
            "dict[str, object]", json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
        )
        self.assertEqual(set(hooks), {"hooks"})
        hook_groups = cast("dict[str, object]", hooks["hooks"])
        self.assertEqual(set(hook_groups), set(ACTIVE_EVENTS))
        self.assertNotIn("Stop", hook_groups)

        prompt_group = cast("list[dict[str, object]]", hook_groups["UserPromptSubmit"])[
            0
        ]
        self.assertNotIn("PreToolUse", hook_groups)
        post_tool_group = cast("list[dict[str, object]]", hook_groups["PostToolUse"])[0]
        self.assertEqual(
            [
                hook["command"]
                for hook in cast("list[dict[str, object]]", prompt_group["hooks"])
            ],
            [
                'bash "$(git rev-parse --show-toplevel)/bootstrap.sh" --control-parent-root "${AGENT_CANON_CONTROL_PARENT_ROOT:-$HOME}" codex hook UserPromptSubmit'
            ],
        )
        post_matcher = cast(str, post_tool_group["matcher"])
        self.assertTrue(
            {
                "send_message",
                "followup_task",
                "list_agents",
                "interrupt_agent",
            }.issubset(set(post_matcher.split("|")))
        )
        self.assertEqual(
            [
                hook["command"]
                for hook in cast("list[dict[str, object]]", post_tool_group["hooks"])
            ],
            [
                'bash "$(git rev-parse --show-toplevel)/bootstrap.sh" --control-parent-root "${AGENT_CANON_CONTROL_PARENT_ROOT:-$HOME}" codex hook PostToolUse'
            ],
        )

        contract = self._contract()
        self.assertEqual(
            set(cast("list[str]", contract["active_events"])), set(ACTIVE_EVENTS)
        )

    def test_hook_contract_is_table_driven_static_and_stop_noop(self) -> None:
        """The static contract covers active events and inactive Stop."""
        contract = self._contract()
        events = cast("dict[str, dict[str, object]]", contract["events"])
        active_events = cast("list[str]", contract["active_events"])
        inactive_events = cast("list[str]", contract["inactive_events"])
        active_handlers = set(cast("list[str]", contract["active_handlers"]))

        self.assertEqual(set(active_events), set(ACTIVE_EVENTS))
        self.assertEqual(
            active_handlers,
            {
                "UserPromptSubmit.secret_safety",
                "PostToolUse.execution_resource_projection",
            },
        )
        self.assertEqual(inactive_events, ["PreToolUse", "Stop"])
        self.assertEqual(set(events), set((*ACTIVE_EVENTS, "PreToolUse", "Stop")))
        for event, expected_active in (
            *((event, True) for event in ACTIVE_EVENTS),
            ("PreToolUse", False),
            ("Stop", False),
        ):
            with self.subTest(event=event):
                self.assertEqual(events[event]["active"], expected_active)
                self.assertIsInstance(events[event]["matchers"], list)
                self.assertIsInstance(events[event]["failure"], str)
                self.assertIsInstance(events[event]["telemetry"], str)

        stop = self._run_hook("Stop", "not-json")
        self.assertEqual(stop.stdout, "")
        self.assertEqual(stop.stderr, "")

    def test_dispatcher_blocks_prompt_secret_without_echoing_secret(self) -> None:
        """UserPromptSubmit blocks an API key and keeps the secret out of output."""
        secret = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        result = self._run_hook(
            "UserPromptSubmit",
            {"hookEventName": "UserPromptSubmit", "prompt": f"use {secret}"},
        )
        payload = cast("dict[str, object]", json.loads(result.stdout))
        self.assertEqual(payload["decision"], "block")
        self.assertIn("API key", cast("str", payload["reason"]))
        self.assertEqual(
            payload["next_action"],
            "remove_secret_or_use_redacted_placeholder_then_retry",
        )
        self.assertTrue(payload["remediation"])
        self.assertNotIn(secret, result.stdout)

    def test_dispatcher_forwards_only_valid_execution_projection(self) -> None:
        """PostToolUse forwards one exact, validator-approved execution projection."""
        run_id = "r5-dispatch"
        projection = {
            "admission": None,
            "completion_coverage_path": f"reports/agents/{run_id}/runtime/completion_coverage.json",
            "error": None,
            "exit_code": 0,
            "plan_fingerprint": "b" * 64,
            "plan_path": f"reports/agents/{run_id}/runtime/execution_resource_plan.json",
            "projection": "post_tool_use",
            "run_id": run_id,
            "schema_version": "execution-resource-plan-projection/v2",
        }
        projection_stdout = (
            json.dumps(projection, sort_keys=True, separators=(",", ":")) + "\n"
        )
        raw = {
            "hookEventName": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python3 experiments/demo_topic/run.py"},
            "tool_response": {
                "exit_code": 0,
                "stderr": "",
                "stdout": projection_stdout,
            },
        }
        result = self._run_hook("PostToolUse", raw)
        payload = cast("dict[str, object]", json.loads(result.stdout))
        hook_output = cast("dict[str, object]", payload["hookSpecificOutput"])
        self.assertEqual(payload["schema"], "agent-canon.posttooluse-stop.v1")
        self.assertEqual(hook_output["hookEventName"], "PostToolUse")
        self.assertEqual(hook_output["additionalContext"], projection_stdout)

    def test_post_tool_projection_failure_keeps_one_redacted_behavior_event(
        self,
    ) -> None:
        """Ordinary results and foreign response shapes still record safe behavior."""
        cases = (
            (
                "Bash",
                {"command": "printf 'private-command-value'"},
                {"exit_code": 0, "stderr": "private-stderr", "stdout": "ok\n"},
            ),
            (
                "Bash",
                {"command": "printf 'private-command-value'"},
                {"exit_code": 0, "stderr": "", "stdout": "private-stdout"},
            ),
            (
                "apply_patch",
                {"patch": "private-patch-value"},
                {"result": "private-result-value"},
            ),
        )
        for tool, tool_input, response in cases:
            with (
                self.subTest(tool=tool, response=response),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp) / "source"
                root.mkdir()
                result = self._run_hook_in_root(
                    root,
                    "PostToolUse",
                    {
                        "hookEventName": "PostToolUse",
                        "tool_name": tool,
                        "tool_input": tool_input,
                        "tool_response": response,
                    },
                )
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
                event = self._spooled_event(root)
                self.assertEqual(event["status"], "invalid_projection")
                self.assertEqual(event["record_kind"], "behavior_event")
                self.assertEqual(event["tool_name"], tool)
                self.assertEqual(event["selected_tools"], [tool])
                serialized = json.dumps(event)
                for value in (
                    "private-command-value",
                    "private-stderr",
                    "private-stdout",
                    "private-patch-value",
                    "private-result-value",
                ):
                    self.assertNotIn(value, serialized)
                self.assertNotIn("tool_response", event)

    def test_coordination_receipt_uses_real_posttool_result(self) -> None:
        """Coordination receipts live in the base spool event, not behavior snapshots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "source"
            root.mkdir()
            payload = {
                "hookEventName": "PostToolUse",
                "tool_name": "send_message",
                "tool_input": {"to": "worker"},
                "tool_response": {"exit_code": 0, "stderr": "", "stdout": "sent"},
            }
            self._run_hook_in_root(root, "PostToolUse", payload)
            event = self._spooled_event(root)
            receipt = cast("dict[str, object]", event["coordination_receipt"])
            self.assertEqual(
                set(receipt),
                {
                    "schema",
                    "operation",
                    "capability_status",
                    "effective_operations",
                    "evidence_ref",
                    "transport",
                    "direct_peer",
                    "status",
                },
            )
            self.assertEqual(receipt["schema"], "agent-canon.coordination-receipt.v1")
            self.assertEqual(receipt["operation"], "send_message")
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(receipt["capability_status"], "unverified")
            self.assertEqual(receipt["transport"], "durable_artifact")
            self.assertFalse(receipt["direct_peer"])
            self.assertNotIn("coordination_mode", event)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "source"
            root.mkdir()
            payload = {
                "hookEventName": "PostToolUse",
                "tool_name": "send_message",
                "tool_input": {"to": "worker"},
                "tool_response": {"exit_code": 1, "stderr": "failed", "stdout": ""},
            }
            self._run_hook_in_root(root, "PostToolUse", payload)
            event = self._spooled_event(root)
            receipt = cast("dict[str, object]", event["coordination_receipt"])
            self.assertEqual(receipt["status"], "failed")

    def test_post_tool_malformed_json_and_schema_matrix_is_noop(self) -> None:
        """Malformed PostToolUse JSON, raw schema, and projection schema fail open quietly."""
        valid_projection = {
            "admission": None,
            "completion_coverage_path": "reports/agents/r5/runtime/completion_coverage.json",
            "error": None,
            "exit_code": 0,
            "plan_fingerprint": "c" * 64,
            "plan_path": "reports/agents/r5/runtime/execution_resource_plan.json",
            "projection": "post_tool_use",
            "run_id": "r5",
            "schema_version": "execution-resource-plan-projection/v2",
        }
        projection_stdout = (
            json.dumps(valid_projection, sort_keys=True, separators=(",", ":")) + "\n"
        )
        base = {
            "hookEventName": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python3 run.py"},
            "tool_response": {
                "exit_code": 0,
                "stderr": "",
                "stdout": projection_stdout,
            },
        }
        invalid_projection_schema = dict(valid_projection)
        invalid_projection_schema["schema_version"] = "wrong/v1"
        cases: tuple[tuple[str, object], ...] = (
            ("malformed-json", '{"hookEventName":'),
            ("json-array", []),
            ("missing-raw-key", {"hookEventName": "PostToolUse"}),
            ("extra-raw-key", {**base, "unexpected": True}),
            ("wrong-event", {**base, "hookEventName": "PreToolUse"}),
            ("tool-name-type", {**base, "tool_name": 1}),
            ("tool-input-type", {**base, "tool_input": []}),
            (
                "response-extra-key",
                {
                    **base,
                    "tool_response": {
                        **cast("dict[str, object]", base["tool_response"]),
                        "extra": True,
                    },
                },
            ),
            (
                "response-exit-bool",
                {
                    **base,
                    "tool_response": {
                        **cast("dict[str, object]", base["tool_response"]),
                        "exit_code": False,
                    },
                },
            ),
            (
                "response-stdout-type",
                {
                    **base,
                    "tool_response": {
                        **cast("dict[str, object]", base["tool_response"]),
                        "stdout": [],
                    },
                },
            ),
            (
                "projection-schema",
                {
                    **base,
                    "tool_response": {
                        **cast("dict[str, object]", base["tool_response"]),
                        "stdout": json.dumps(
                            invalid_projection_schema,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n",
                    },
                },
            ),
            (
                "projection-json",
                {
                    **base,
                    "tool_response": {
                        **cast("dict[str, object]", base["tool_response"]),
                        "stdout": "not-json\n",
                    },
                },
            ),
        )
        for name, payload in cases:
            with self.subTest(case=name):
                result = self._run_hook("PostToolUse", payload)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_retired_pretooluse_is_quiet_for_git_commands(self) -> None:
        for command in [
            "git worktree add -b topic path",
            "git switch topic",
            "git worktree remove path",
            "git reset --hard",
        ]:
            with self.subTest(command=command):
                result = self._run_hook(
                    "PreToolUse",
                    {"tool_name": "Bash", "tool_input": {"command": command}},
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_dispatcher_hot_path_has_no_child_process_or_network_calls(self) -> None:
        """The native dispatcher keeps direct process and network calls out."""
        source = (
            PROJECT_ROOT / "tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs"
        ).read_text(encoding="utf-8")
        for operation in (
            "std::process::Command",
            "Command::new(",
            "std::net::",
            "TcpStream",
            "UdpSocket",
            "reqwest::",
        ):
            self.assertNotIn(operation, source)


def test_hook_report_requires_parent_capability() -> None:
    """Report projection stays disabled until the parent capability is present."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir) / "source"
        target = root / "report"
        target.mkdir(parents=True)
        fixture = CodexHooksTest()
        result = fixture._run_hook_in_root(
            root,
            "UserPromptSubmit",
            {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"},
            extra_env={
                "AGENT_CANON_PARENT_ROOT": "",
                "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(target),
            },
        )
        assert result.stdout == ""
        assert not list(root.parent.glob("spool/hook-events/**/*.json"))
        assert not (target / "workflow_monitoring.md").exists()


if __name__ == "__main__":
    unittest.main()
