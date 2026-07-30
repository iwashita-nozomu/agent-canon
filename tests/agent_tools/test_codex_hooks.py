"""Tests for the active Codex project-local hook contract."""

# @dependency-start
# contract test
# responsibility Tests active codex hook behavior and retired-route contract.
# upstream implementation ../../.codex/config.toml enables hooks
# upstream implementation ../../.codex/hooks.json declares the three active hooks
# upstream implementation ../../tools/agent_tools/hook_safety.py owns active safety leaves
# upstream implementation ../../.codex/hooks/hook_dispatcher.py owns the typed event contract
# downstream implementation ../../tests/agent_tools/test_hook_event_log.py validates hook telemetry
# @dependency-end

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG = PROJECT_ROOT / ".codex" / "config.toml"
HOOKS_JSON = PROJECT_ROOT / ".codex" / "hooks.json"
HOOK_DISPATCHER = PROJECT_ROOT / ".codex" / "hooks" / "hook_dispatcher.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from prompt_classifier import (  # noqa: E402
    PromptClassifierInputs,
    prompt_intake_signals,
)

ACTIVE_EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse")
RETIRED_ROUTE_TABLE = (
    "branch_worktree_guard.py",
    "cause_investigation_guard.py",
    "codex_runtime_summary_logger.py",
    "completion_review_guard.py",
    "direct_rg_context_guard.py",
    "execution_resource_plan_projection_guard.py",
    "first_party_library_guard.py",
    "goal_completion_guard.py",
    "helper_first_guard.py",
    "helper_inventory_guard.py",
    "library_implementation_guard.py",
    "log_archive_mount_warning.py",
    "log_surface_inventory_guard.py",
    "module_boundary_guard.py",
    "notebook_quality_guard.py",
    "oop_readability_guard.py",
    "prompt_secret_guard.py",
    "reference_capture_guard.py",
    "role_write_policy_guard.py",
    "runtime_log_auto_sync.py",
    "skill_usage_logger.py",
    "style_checker_guard.py",
    "task_authority_schema_guard.py",
)
RETIRED_ROUTE_FIELDS = {
    "filename",
    "artifact",
    "command_or_skill",
    "decision_semantics",
    "owner",
    "profile_trigger",
}


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
                [sys.executable, str(HOOK_DISPATCHER), event],
                cwd=PROJECT_ROOT,
                input=raw_payload,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    **(extra_env or {}),
                    "AGENT_CANON_HOOK_SOURCE_ROOT": temp_dir,
                },
            )

    def _contract(self) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(HOOK_DISPATCHER), "--contract"],
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
        return subprocess.run(
            [sys.executable, str(HOOK_DISPATCHER), event],
            cwd=PROJECT_ROOT,
            input=raw_payload,
            check=True,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                **(extra_env or {}),
                "AGENT_CANON_HOOK_SOURCE_ROOT": str(root),
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
        ):
            env.pop(key, None)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(HOOK_DISPATCHER), event],
            cwd=cwd,
            input=raw_payload,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    @staticmethod
    def _spooled_event(root: Path, pattern: str = ".agent-canon/**/*.json") -> dict[str, object]:
        """Read the one isolated hook event emitted by a fixture invocation."""
        paths = list(root.glob(pattern))
        if len(paths) != 1:
            raise AssertionError(f"expected one spooled event, found {paths}")
        return cast("dict[str, object]", json.loads(paths[0].read_text(encoding="utf-8")))

    def test_hook_report_target_precedence_and_spool_only_fallback(self) -> None:
        """Projection follows the explicit target, while no target remains spool-only."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pointer_target = root / "reports" / "agents" / "pointer-run"
            pointer_target.parent.mkdir(parents=True)
            (pointer_target.parent / ".active_run").write_text("pointer-run\n", encoding="utf-8")
            explicit_target = root / "explicit-run"
            explicit_target.mkdir()

            self._run_hook_in_root(
                root,
                "UserPromptSubmit",
                payload,
                extra_env={"AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(explicit_target)},
            )

            event = self._spooled_event(root)
            self.assertEqual(event["workflow_monitor_report_dir"], str(explicit_target))
            self.assertTrue((explicit_target / "workflow_monitoring.md").is_file())
            self.assertFalse((pointer_target / "workflow_monitoring.md").exists())
            self.assertFalse((root / "workflow_monitoring.md").exists())

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self._run_hook_in_root(root, "UserPromptSubmit", payload)

            event = self._spooled_event(root)
            self.assertEqual(event["workflow_monitor_report_dir"], "")
            self.assertFalse(any(root.rglob("workflow_monitoring.md")))

    def test_hook_report_target_uses_active_run_pointer(self) -> None:
        """An active run pointer selects the run bundle relative to its pointer."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            pointer = root / "reports" / "agents" / ".active_run"
            pointer.parent.mkdir(parents=True)
            pointer.write_text("pointer-run\n", encoding="utf-8")
            target = pointer.parent / "pointer-run"
            target.mkdir()

            self._run_hook_in_root(root, "UserPromptSubmit", payload)

            event = self._spooled_event(root)
            self.assertEqual(event["workflow_monitor_report_dir"], str(target))
            self.assertTrue((target / "workflow_monitoring.md").is_file())

    def test_standalone_report_target_uses_local_active_run_pointer(self) -> None:
        """Standalone AgentCanon may resolve its local active-run pointer."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "reports" / "agents" / "standalone-run"
            target.mkdir(parents=True)
            (root / ".active_run").write_text(
                "reports/agents/standalone-run\n",
                encoding="utf-8",
            )

            self._run_hook_in_root(root, "UserPromptSubmit", payload)

            event = self._spooled_event(root)
            self.assertEqual(event["workflow_monitor_report_dir"], str(target))
            self.assertTrue((target / "workflow_monitoring.md").is_file())

    def test_pointer_targets_reject_missing_and_containment_escapes(self) -> None:
        """Pointer targets must be existing run bundles contained by reports/agents."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        cases = ("missing-run", "../escape", "/absolute/escape", "symlink-escape")
        for declared in cases:
            with self.subTest(declared=declared), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                report_root = root / "reports" / "agents"
                report_root.mkdir(parents=True)
                outside = root / "outside"
                outside.mkdir()
                if declared == "symlink-escape":
                    (report_root / declared).symlink_to(outside, target_is_directory=True)
                (report_root / ".active_run").write_text(
                    declared + "\n",
                    encoding="utf-8",
                )

                self._run_hook_in_root(root, "UserPromptSubmit", payload)

                event = self._spooled_event(root)
                self.assertEqual(event["workflow_monitor_report_dir"], "")
                self.assertFalse(any(root.rglob("workflow_monitoring.md")))
                self.assertFalse((report_root / "missing-run").exists())

    def test_pointer_rejects_escaped_report_root_symlink(self) -> None:
        """The reports/agents identity itself must remain inside the active root."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            root = workspace / "active-root"
            root.mkdir()
            outside = workspace / "outside-reports"
            outside.mkdir()
            target = outside / "escaped-run"
            target.mkdir()
            report_parent = root / "reports"
            report_parent.mkdir()
            (report_parent / "agents").symlink_to(outside, target_is_directory=True)
            (outside / ".active_run").write_text("escaped-run\n", encoding="utf-8")

            self._run_hook_in_root(root, "UserPromptSubmit", payload)

            event = self._spooled_event(root)
            self.assertEqual(event["workflow_monitor_report_dir"], "")
            self.assertFalse((target / "workflow_monitoring.md").exists())

    def test_resolver_failure_is_spool_only_even_with_report_override(self) -> None:
        """A failed source-root resolution disables report projection as typed state."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            spool = root / "spool"
            report = root / "authority-report"
            report.mkdir()

            self._run_hook_in_layout(
                root,
                "UserPromptSubmit",
                payload,
                extra_env={
                    "AGENT_CANON_HOOK_EVENT_SPOOL_DIR": str(spool),
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(report),
                },
            )

            event = self._spooled_event(spool, "**/*.json")
            self.assertEqual(event["workflow_monitor_report_dir"], "")
            self.assertFalse((report / "workflow_monitoring.md").exists())

    def test_derived_submodule_cwd_uses_parent_active_root(self) -> None:
        """A real vendored layout resolves the parent without the hook override."""
        payload = {"hookEventName": "UserPromptSubmit", "prompt": "use $task-routing"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = Path(tmp_dir) / "parent"
            source = parent / "vendor" / "agent-canon"
            catalog = source / "agents" / "skills" / "catalog.yaml"
            (parent / ".git").mkdir(parents=True)
            source.mkdir(parents=True)
            (source / ".git").write_text(
                "gitdir: ../../.git/modules/vendor/agent-canon\n",
                encoding="utf-8",
            )
            catalog.parent.mkdir(parents=True)
            catalog.write_text("skills: []\n", encoding="utf-8")
            report = parent / "reports" / "agents" / "derived-run"
            report.mkdir(parents=True)
            (report.parent / ".active_run").write_text(
                "derived-run\n",
                encoding="utf-8",
            )

            self._run_hook_in_layout(source, "UserPromptSubmit", payload)

            event = self._spooled_event(parent)
            self.assertEqual(event["root"], str(parent))
            self.assertEqual(event["workflow_monitor_report_dir"], str(report))
            self.assertTrue((report / "workflow_monitoring.md").is_file())
            self.assertFalse((source / ".agent-canon").exists())

    def _run_shared_checkout_guard(
        self, command: str, *, extra_env: dict[str, str] | None = None
    ) -> dict[str, object] | None:
        """Run the active PreToolUse dispatcher for one shared-checkout command."""
        result = self._run_hook(
            "PreToolUse",
            {
                "hookEventName": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"cmd": command},
            },
            extra_env=extra_env,
        )
        return (
            cast("dict[str, object]", json.loads(result.stdout))
            if result.stdout
            else None
        )

    def test_active_hook_config_has_exact_three_events(self) -> None:
        """Project config and hooks JSON expose only the three active dispatcher events."""
        config_text = CONFIG.read_text(encoding="utf-8")
        self.assertIn("[features]", config_text)
        self.assertIn("hooks = true", config_text)
        self.assertNotIn("codex_hooks", config_text)

        hooks = cast("dict[str, object]", json.loads(HOOKS_JSON.read_text(encoding="utf-8")))
        self.assertEqual(set(hooks), {"hooks"})
        hook_groups = cast("dict[str, object]", hooks["hooks"])
        self.assertEqual(set(hook_groups), set(ACTIVE_EVENTS))
        self.assertNotIn("Stop", hook_groups)

        prompt_group = cast("list[dict[str, object]]", hook_groups["UserPromptSubmit"])[0]
        pre_tool_group = cast("list[dict[str, object]]", hook_groups["PreToolUse"])[0]
        post_tool_group = cast("list[dict[str, object]]", hook_groups["PostToolUse"])[0]
        self.assertEqual(
            [hook["command"] for hook in cast("list[dict[str, object]]", prompt_group["hooks"])],
            ["python3 .codex/hooks/hook_dispatcher.py UserPromptSubmit"],
        )
        self.assertEqual(
            pre_tool_group["matcher"], "Bash|apply_patch|python|python3"
        )
        self.assertEqual(
            [hook["command"] for hook in cast("list[dict[str, object]]", pre_tool_group["hooks"])],
            ["python3 .codex/hooks/hook_dispatcher.py PreToolUse"],
        )
        self.assertEqual(
            post_tool_group["matcher"],
            "Bash|apply_patch|python|python3|Task|spawn_agent|send_input|wait_agent|close_agent|resume_agent",
        )
        self.assertEqual(
            [hook["command"] for hook in cast("list[dict[str, object]]", post_tool_group["hooks"])],
            ["python3 .codex/hooks/hook_dispatcher.py PostToolUse"],
        )

        contract = self._contract()
        self.assertEqual(set(cast("list[str]", contract["active_events"])), set(ACTIVE_EVENTS))

    def test_hook_contract_is_table_driven_static_and_stop_noop(self) -> None:
        """The static contract covers active events, inactive Stop, and all retired routes."""
        contract = self._contract()
        events = cast("dict[str, dict[str, object]]", contract["events"])
        active_events = cast("list[str]", contract["active_events"])
        inactive_events = cast("list[str]", contract["inactive_events"])
        retired_rows = cast("list[dict[str, object]]", contract["retired_child_tombstones"])
        moved_rows = cast("list[dict[str, object]]", contract["moved_source_absences"])
        active_handlers = set(cast("list[str]", contract["active_handlers"]))

        self.assertEqual(set(active_events), set(ACTIVE_EVENTS))
        self.assertEqual(
            active_handlers,
            {
                "UserPromptSubmit.secret_safety",
                "PreToolUse.destructive_git_safety",
                "PostToolUse.execution_resource_projection",
            },
        )
        self.assertEqual(inactive_events, ["Stop"])
        self.assertEqual(set(events), set((*ACTIVE_EVENTS, "Stop")))
        retired_routes = {cast(str, row["filename"]): row for row in retired_rows}
        self.assertEqual(set(retired_routes), set(RETIRED_ROUTE_TABLE))
        self.assertEqual(len(retired_rows), 23)
        self.assertEqual(len(moved_rows), 1)
        self.assertTrue(set(retired_routes).isdisjoint(active_handlers))

        for event, expected_active in (
            *((event, True) for event in ACTIVE_EVENTS),
            ("Stop", False),
        ):
            with self.subTest(event=event):
                self.assertEqual(events[event]["active"], expected_active)
                self.assertIsInstance(events[event]["matchers"], list)
                self.assertIsInstance(events[event]["failure"], str)
                self.assertIsInstance(events[event]["telemetry"], str)

        for route_name in RETIRED_ROUTE_TABLE:
            with self.subTest(route=route_name):
                route = retired_routes[route_name]
                self.assertEqual(set(route), RETIRED_ROUTE_FIELDS)
                self.assertTrue(all(isinstance(value, str) and value for value in route.values()))

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
            "schema_version": "execution-resource-plan/v1",
        }
        projection_stdout = json.dumps(
            projection, sort_keys=True, separators=(",", ":")
        ) + "\n"
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
            "schema_version": "execution-resource-plan/v1",
        }
        projection_stdout = json.dumps(
            valid_projection, sort_keys=True, separators=(",", ":")
        ) + "\n"
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
            ("malformed-json", "{\"hookEventName\":"),
            ("json-array", []),
            ("missing-raw-key", {"hookEventName": "PostToolUse"}),
            ("extra-raw-key", {**base, "unexpected": True}),
            ("wrong-event", {**base, "hookEventName": "PreToolUse"}),
            ("tool-name-type", {**base, "tool_name": 1}),
            ("tool-input-type", {**base, "tool_input": []}),
            (
                "response-extra-key",
                {**base, "tool_response": {**cast("dict[str, object]", base["tool_response"]), "extra": True}},
            ),
            (
                "response-exit-bool",
                {**base, "tool_response": {**cast("dict[str, object]", base["tool_response"]), "exit_code": False}},
            ),
            (
                "response-stdout-type",
                {**base, "tool_response": {**cast("dict[str, object]", base["tool_response"]), "stdout": []}},
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

    def test_dispatcher_branch_payload_is_redacted(self) -> None:
        """Destructive Git output contains only the operation and command fingerprint."""
        command = "git -C vendor/agent-canon restore --worktree ."
        result = self._run_hook(
            "PreToolUse",
            {
                "hookEventName": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"cmd": command},
            },
        )
        payload = cast("dict[str, object]", json.loads(result.stdout))
        self.assertEqual(payload["decision"], "block")
        self.assertEqual(payload["operation"], "destructive_git:restore")
        self.assertEqual(
            payload["command_sha256"], hashlib.sha256(command.encode()).hexdigest()
        )
        self.assertNotIn(command, result.stdout)
        self.assertNotIn("cmd", payload)

    def test_dispatcher_hot_path_has_no_child_process_or_network_calls(self) -> None:
        """The active dispatcher remains in-process and local-only."""
        tree = ast.parse(HOOK_DISPATCHER.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        )
        self.assertNotIn("subprocess", imported)
        self.assertNotIn("socket", imported)
        self.assertNotIn("urllib", imported)
        forbidden_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {"run", "Popen", "check_call", "check_output", "urlopen"}
        ]
        self.assertEqual(forbidden_calls, [])

    def test_prompt_intake_signals_keeps_evaluator_classification_pure(self) -> None:
        """Prompt routing remains observable without JSONL or runtime-hook side effects."""
        cases = (
            {
                "name": "validation-repair",
                "prompt": "failed validation; do not delete tests or weaken oracle before repairing the failing contract",
            },
            {
                "name": "declared-skill",
                "prompt": "Use $codex-task-workflow for a validation failure; do not delete tests or weaken the oracle.",
                "selected": {"codex-task-workflow"},
                "forbidden_candidates": {"codex-task-workflow"},
            },
            {
                "name": "oracle-mismatch",
                "prompt": "The test oracle has a spec mismatch; fix test design.",
            },
            {
                "name": "user-guided-debugging",
                "prompt": "Use user-guided refactor cadence: show one concrete issue, patch only that target, and do not run validation unless I ask.",
                "forbidden_candidates": {"user-guided-debugging"},
            },
            {
                "name": "ordinary-docs",
                "prompt": "Please update the docs; no validation unless asked.",
                "forbidden_candidates": {"user-guided-debugging"},
            },
            {
                "name": "parent-repo-skill-lane",
                "prompt": "親レポに固有スキルを置けるようにする設計修正",
                "forbidden_candidates": {"task-routing", "structure-refactor"},
            },
            {
                "name": "advisory-routing",
                "prompt": "Which route contract applies for this repository task?",
                "forbidden_candidates": {"codex-task-workflow"},
            },
        )
        for case in cases:
            with self.subTest(case=case["name"]):
                signals = prompt_intake_signals(
                    PromptClassifierInputs(
                        prompt=cast(str, case["prompt"]),
                        repo_root=PROJECT_ROOT,
                        catalog={},
                        routing_rules={},
                    )
                )
                candidates = set(signals.candidate_skills)
                selected = set(signals.skills)
                self.assertTrue(
                    cast("set[str]", case.get("required_candidates", set()))
                    <= candidates
                )
                self.assertTrue(
                    cast("set[str]", case.get("selected", set())) <= selected
                )
                self.assertTrue(
                    cast("set[str]", case.get("required_workflows", set()))
                    <= set(signals.candidate_workflows)
                )
                self.assertTrue(
                    cast("set[str]", case.get("forbidden_candidates", set())).isdisjoint(
                        candidates
                    )
                )
                reason_fragment = case.get("reason_fragment")
                if reason_fragment is not None:
                    self.assertTrue(
                        any(reason_fragment in reason for reason in signals.candidate_skill_reasons)
                    )

    def test_shared_checkout_guard_blocks_destructive_git_parser_table(self) -> None:
        """Protected Git stays visible through prefixes, wrappers, options, and grouping."""
        commands = [
            "git -C vendor/agent-canon restore --worktree .",
            "git --no-pager reset --mixed HEAD",
            "git -P restore --staged file.py",
            "git -p checkout -- file.py",
            "git --exec-path=/tmp reset HEAD",
            "env -u HOME git restore .",
            "env --unset=HOME git reset HEAD",
            "command -- git clean -f",
            "command -p git stash push -m save",
            "( git checkout main )",
            "! git switch main",
            "time -p git worktree prune",
            "bash -lc 'git restore --worktree .'",
            "eval 'git reset --mixed HEAD'",
            "true && git clean --force -d",
            "git branch -Dtopic",
            "git branch -mtopic",
            "git branch --edit-description topic",
            "git worktree lock ../topic",
        ]
        for command in commands:
            with self.subTest(command=command):
                payload = self._run_shared_checkout_guard(command)
                self.assertIsNotNone(payload)
                self.assertEqual(cast("dict[str, object]", payload)["decision"], "block")
                self.assertIn(
                    "DESTRUCTIVE_GIT_GUARD=block",
                    cast("str", cast("dict[str, object]", payload)["reason"]),
                )

    def test_shared_checkout_guard_authority_is_same_segment_and_one_shot(self) -> None:
        """Ambient, incomplete, and earlier-segment authority never leaks to Git."""
        destructive = (
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved"
        )
        self.assertIsNone(
            self._run_shared_checkout_guard(f"{destructive} git restore file.py")
        )
        self.assertIsNone(
            self._run_shared_checkout_guard(f"env {destructive} git reset HEAD")
        )
        self.assertIsNotNone(
            self._run_shared_checkout_guard(
                "git restore file.py",
                extra_env={
                    "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                    "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "ambient must not count",
                },
            )
        )
        self.assertIsNotNone(
            self._run_shared_checkout_guard(
                "AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved git restore file.py"
            )
        )
        self.assertIsNotNone(
            self._run_shared_checkout_guard(f"{destructive} git restore file.py && git reset HEAD")
        )
        self.assertIsNotNone(
            self._run_shared_checkout_guard(f"{destructive}; git restore file.py")
        )

    def test_shared_checkout_guard_checks_opaque_protected_git_per_segment(self) -> None:
        """A parsed safe Git segment never hides opaque protected Git elsewhere."""
        commands = [
            "git status && sudo git reset --hard",
            "git status; nice git restore file.py",
            "git status && ( sudo git checkout main )",
            "sudo git " + "-A " * 2000 + "reset --hard HEAD",
        ]
        for command in commands:
            with self.subTest(command=command):
                payload = self._run_shared_checkout_guard(command)
                self.assertIsNotNone(payload)
                self.assertEqual(
                    cast("dict[str, object]", payload)["operation"],
                    "destructive_git:opaque",
                )
        self.assertIsNotNone(
            self._run_shared_checkout_guard(
                "git --config-env=core.editor=EDITOR reset --hard HEAD"
            )
        )

    def test_shared_checkout_guard_classifies_backtick_substitutions(self) -> None:
        """Executable or uncertain protected Git backticks block without broad matches."""
        blocked = (
            "echo `git reset --hard`",
            'echo "`git reset --hard`"',
            "echo `git reset --hard",
        )
        for command in blocked:
            with self.subTest(command=command):
                payload = self._run_shared_checkout_guard(command)
                self.assertIsNotNone(payload)
                self.assertEqual(
                    cast("dict[str, object]", payload)["operation"],
                    "destructive_git:reset",
                )
        benign = (
            "echo `date`",
            'echo "`date`"',
            "echo '`git reset --hard`'",
            "echo `git status`",
            "echo `date",
            "echo \\`git reset --hard\\`",
        )
        for command in benign:
            with self.subTest(command=command):
                self.assertIsNone(self._run_shared_checkout_guard(command))

    def test_shared_checkout_guard_ignores_backticks_in_shell_comments(self) -> None:
        """Only unquoted shell-comment boundaries suppress backtick execution."""
        comments = (
            "echo safe # `git reset --hard`",
            "echo safe # `git reset --hard",
            "echo safe;# `git reset --hard`",
            "echo '# `git reset --hard`'",
        )
        for command in comments:
            with self.subTest(command=command):
                self.assertIsNone(self._run_shared_checkout_guard(command))

        executable = (
            "echo safe#`git reset --hard`",
            'echo "# `git reset --hard`"',
            "echo \\#`git reset --hard`",
            "echo safe # `date`\necho `git reset --hard`",
        )
        for command in executable:
            with self.subTest(command=command):
                payload = self._run_shared_checkout_guard(command)
                self.assertIsNotNone(payload)
                self.assertEqual(
                    cast("dict[str, object]", payload)["operation"],
                    "destructive_git:reset",
                )

    def test_shared_checkout_guard_allows_explicit_read_only_table(self) -> None:
        """Read-only diagnostics and combined clean dry-run forms stay quiet."""
        commands = [
            "git status --short",
            "git diff --stat",
            "git branch",
            "git branch --show-current",
            "git branch --list 'topic/*'",
            "git worktree list --porcelain",
            "git stash list",
            "git stash show stash@{0}",
            "git clean -n",
            "git clean --dry-run -f",
            "git clean -fnx",
            "git clean -nfx",
            "git switch --help",
            "git checkout -h",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(self._run_shared_checkout_guard(command))

    def test_shared_checkout_guard_enforces_overlap_authority_matrix(self) -> None:
        """Creation and destructive-overwrite intents require their full authority sets."""
        creation = (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request "
            "AGENT_CANON_BRANCH_WORKTREE_REASON=requested"
        )
        workflow = (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=agent_canon_workflow "
            "AGENT_CANON_BRANCH_WORKTREE_REASON=pr-route"
        )
        destructive = (
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved"
        )
        normal_create = [
            "git switch -ctopic",
            "git checkout -btopic",
            "git checkout --orphan topic",
            "git branch -ctopic main",
            "git branch topic",
            "git branch --track topic origin/main",
            "git branch --track=direct topic origin/main",
            "git branch --no-track topic origin/main",
            "git branch --create-reflog topic origin/main",
            "git worktree add -b topic ../topic",
            "git worktree add --orphan topic ../topic",
        ]
        force_create = [
            "git switch -Ctopic",
            "git checkout -Btopic",
            "git branch -Ctopic main",
            "git branch -ftopic main",
            "git worktree add -B topic ../topic",
            "git worktree add -f ../topic topic",
            "git worktree add --force ../topic topic",
        ]
        for command in normal_create:
            with self.subTest(command=command, route="normal"):
                self.assertIsNotNone(self._run_shared_checkout_guard(command))
                self.assertIsNotNone(self._run_shared_checkout_guard(f"{creation} {command}"))
                self.assertIsNotNone(self._run_shared_checkout_guard(f"{workflow} {command}"))
                self.assertIsNone(
                    self._run_shared_checkout_guard(f"{creation} {destructive} {command}")
                )
                self.assertIsNone(
                    self._run_shared_checkout_guard(f"{workflow} {destructive} {command}")
                )
        for command in force_create:
            with self.subTest(command=command, route="force"):
                self.assertIsNotNone(self._run_shared_checkout_guard(f"{creation} {command}"))
                self.assertIsNotNone(self._run_shared_checkout_guard(f"{destructive} {command}"))
                self.assertIsNone(
                    self._run_shared_checkout_guard(f"{creation} {destructive} {command}")
                )

    def test_shared_checkout_guard_protects_agent_canon_update_wrappers(self) -> None:
        """Update wrappers inherit the creation plus destructive authority profile."""
        approved = (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request "
            "AGENT_CANON_BRANCH_WORKTREE_REASON=approved-update "
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved-update"
        )
        commands = [
            "bash tools/update_agent_canon.sh latest",
            "tools/update_agent_canon.sh latest",
            "./tools/update_agent_canon.sh apply",
            "bash tools/update_agent_canon.sh apply",
            "bash tools/update_agent_canon.sh merge-main-into-current",
            "bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty",
            "bash tools/sync_agent_canon.sh ensure-latest",
            "./tools/sync_agent_canon.sh ensure-latest",
            "bash --rcfile /tmp/agent-canon-test-rc tools/update_agent_canon.sh latest",
            "bash -o pipefail tools/update_agent_canon.sh latest",
            "exec ./tools/update_agent_canon.sh latest",
            "exec -- ./tools/sync_agent_canon.sh ensure-latest",
            "exec -a agent-canon ./tools/update_agent_canon.sh apply",
            "exec -a canon -c ./tools/update_agent_canon.sh latest",
            "exec -a canon -l ./tools/sync_agent_canon.sh ensure-latest",
            "exec -c ./tools/sync_agent_canon.sh ensure-latest",
            "exec -l ./tools/update_agent_canon.sh merge-main-into-current",
            "exec -cl ./tools/update_agent_canon.sh merge-main-into-current-preserve-dirty",
            "make agent-canon-ensure-latest",
            "make agent-canon-latest",
            "make agent-canon-update",
        ]
        for command in commands:
            with self.subTest(command=command):
                payload = self._run_shared_checkout_guard(command)
                self.assertIsNotNone(payload)
                assert payload is not None
                reason = cast("str", payload["reason"])
                self.assertIn("DESTRUCTIVE_GIT_GUARD=block", reason)
                self.assertIn("BRANCH_WORKTREE_CREATION_GUARD=block", reason)
                self.assertEqual(
                    payload["next_action"],
                    "request_explicit_user_approval_then_rerun_same_command_with_inline_git_authority_and_reason",
                )
                self.assertIsNone(self._run_shared_checkout_guard(f"{approved} {command}"))

    def test_shared_checkout_guard_wrapper_authority_does_not_leak(self) -> None:
        """Prior segments and ambient variables never authorize an update wrapper."""
        approved = (
            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request "
            "AGENT_CANON_BRANCH_WORKTREE_REASON=approved-update "
            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval "
            "AGENT_CANON_DESTRUCTIVE_GIT_REASON=approved-update"
        )
        commands = (
            "exec ./tools/update_agent_canon.sh latest",
            "exec -- ./tools/sync_agent_canon.sh ensure-latest",
            "exec -a canon -c ./tools/update_agent_canon.sh latest",
            "exec -a canon -l ./tools/sync_agent_canon.sh ensure-latest",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNotNone(
                    self._run_shared_checkout_guard(
                        command,
                        extra_env={
                            "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY": "user_request",
                            "AGENT_CANON_BRANCH_WORKTREE_REASON": "ambient",
                            "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY": "explicit_user_approval",
                            "AGENT_CANON_DESTRUCTIVE_GIT_REASON": "ambient",
                        },
                    )
                )
                self.assertIsNotNone(self._run_shared_checkout_guard(f"{approved}; {command}"))
                self.assertIsNotNone(self._run_shared_checkout_guard(f"export {approved}; {command}"))
                self.assertIsNotNone(
                    self._run_shared_checkout_guard(
                        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request " + command
                    )
                )
                self.assertIsNone(self._run_shared_checkout_guard(f"{approved} {command}"))

        self.assertIsNone(
            self._run_shared_checkout_guard(
                f"{approved} bash -o pipefail tools/update_agent_canon.sh latest"
            )
        )

    def test_shared_checkout_guard_blocks_generic_branch_worktree_mutation(self) -> None:
        """Only explicit branch/worktree read-only allowlists stay quiet."""
        commands = [
            "git branch --set-upstream-to=origin/main topic",
            "git branch --unset-upstream topic",
            "git branch -Mtopic",
            "git worktree remove ../topic",
            "git worktree move ../old ../new",
            "git worktree repair ../topic",
            "git worktree unlock ../topic",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNotNone(self._run_shared_checkout_guard(command))


if __name__ == "__main__":
    unittest.main()
