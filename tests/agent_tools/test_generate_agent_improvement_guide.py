# @dependency-start
# contract test
# responsibility Tests AgentCanon improvement guide generation.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/agent_runtime_dashboard.rs generates guide reports
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs supplies native historical skill-usage readback
# @dependency-end

"""Tests for generated AgentCanon improvement guides."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = "generate-agent-improvement-guide"
HOOK_ARCHIVE_DIR_ENV = "AGENT_CANON_HOOK_ARCHIVE_DIR"


def mounted_log_archive_root(_root: Path) -> Path:
    return Path(os.environ["AGENT_CANON_RUNTIME_ROOT"]) / "archive" / "agent-canon-log"


class GenerateAgentImprovementGuideTest(unittest.TestCase):
    """Verify deterministic guide output from accumulated evidence."""

    def setUp(self) -> None:
        self._runtime_temp = tempfile.TemporaryDirectory()
        self._previous_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
        self._previous_log = os.environ.get("AGENT_CANON_LOG_ROOT")
        self._previous_archive = os.environ.pop(HOOK_ARCHIVE_DIR_ENV, None)
        self.runtime_root = Path(self._runtime_temp.name) / "runtime"
        self.runtime_root.mkdir()
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(self.runtime_root)
        os.environ["AGENT_CANON_LOG_ROOT"] = str(self.runtime_root / "agent-canon-log")

    def tearDown(self) -> None:
        if self._previous_runtime is None:
            os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
        else:
            os.environ["AGENT_CANON_RUNTIME_ROOT"] = self._previous_runtime
        if self._previous_log is None:
            os.environ.pop("AGENT_CANON_LOG_ROOT", None)
        else:
            os.environ["AGENT_CANON_LOG_ROOT"] = self._previous_log
        if self._previous_archive is None:
            os.environ.pop(HOOK_ARCHIVE_DIR_ENV, None)
        else:
            os.environ[HOOK_ARCHIVE_DIR_ENV] = self._previous_archive
        self._runtime_temp.cleanup()

    def run_cli(
        self, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Translate the old producer-shaped test argv to the native selector."""
        command = list(command)
        if command[:2] == [sys.executable, SCRIPT]:
            native = os.environ.get("AGENT_CANON_NATIVE_BIN") or os.environ.get(
                "AGENT_CANON_CLI"
            )
            if not native:
                self.fail(
                    "AGENT_CANON_NATIVE_BIN or AGENT_CANON_CLI must select the native executable"
                )
            command = [native, SCRIPT, *command[2:]]
            if "--runtime-root" not in command:
                command.extend(["--runtime-root", str(self.runtime_root)])
            environment = os.environ.copy()
            environment["AGENT_CANON_RUNTIME_ROOT"] = str(self.runtime_root)
            environment["AGENT_CANON_LOG_ROOT"] = str(
                self.runtime_root / "agent-canon-log"
            )
            environment.pop(HOOK_ARCHIVE_DIR_ENV, None)
            kwargs["env"] = environment
            kwargs.setdefault("check", False)
            kwargs.setdefault("capture_output", True)
            kwargs.setdefault("text", True)
        return subprocess.run(command, check=kwargs.pop("check", False), **kwargs)

    def test_usage_counts_do_not_create_repair_obligations(self) -> None:
        """Overlapping or repeated candidate observations do not prove an omission."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_skill_usage_fixture(
                root,
                {
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "skills": ["agent-orchestration"],
                    "candidate_skills": ["agent-orchestration"],
                    "feedback_targets": ["skill:agent-orchestration"],
                    "feedback_labels": ["quality_gap"],
                    "skill_source_fields": ["prompt"],
                },
            )
            output = self.runtime_root / "reports" / "guide.md"
            result = self.run_cli(
                [sys.executable, SCRIPT, "--root", str(root), "--out", str(output)]
            )
            guide = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Skill Routing Gaps", guide)
        self.assertNotIn("Repair skill-selection routing", guide)

    def test_empty_guide_does_not_activate_recording_or_repair(self) -> None:
        """Reading a report with no evidence does not create a workflow obligation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "eval" / "definitions").mkdir(parents=True)
            output = self.runtime_root / "reports" / "empty-guide.md"
            result = self.run_cli(
                [sys.executable, SCRIPT, "--root", str(root), "--out", str(output)]
            )
            guide = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("required_tokens:", guide)
        self.assertNotIn("next_repair_branch:", guide)
        self.assertNotIn("github_issue_lookup_required", guide)
        self.assertNotIn("make the actual skill/workflow/tool edits", guide)

    def test_output_mode_defaults_to_private_and_allows_explicit_644(self) -> None:
        """Guide artifacts retain their private default and public opt-in mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            default = self.runtime_root / "reports" / "guide-private.md"
            public = self.runtime_root / "reports" / "guide-public.md"
            for output, options in ((default, []), (public, ["--output-mode", "644"])):
                result = self.run_cli(
                    [
                        sys.executable,
                        SCRIPT,
                        "--root",
                        str(root),
                        "--out",
                        str(output),
                        *options,
                    ]
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(default.stat().st_mode & 0o777, 0o600)
            self.assertEqual(public.stat().st_mode & 0o777, 0o644)

    def test_observed_failure_keeps_evidence_without_claiming_its_cause(self) -> None:
        """A genuine hook failure remains visible with its affected input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            log = (
                mounted_log_archive_root(root)
                / "hook-runs"
                / "legacy-import"
                / "test-container"
                / "execution.jsonl"
            )
            raw = (
                json.dumps(
                    {
                        "status": "fail",
                        "event": "PostToolUse",
                        "hook_run_id": "execution-failed",
                        "payload_fingerprint": "execution-input",
                        "hook_log_namespace": "test-container",
                        "failure_fingerprint": "current-failure",
                        "commands": [
                            {
                                "command": ["ruff", "check", "src/product.py"],
                                "returncode": 1,
                                "output_snippet": "reported failure on the input",
                            }
                        ],
                    }
                )
                + "\n"
            )
            log.write_text(raw, encoding="utf-8")
            output = self.runtime_root / "reports" / "failure-guide.md"
            result = self.run_cli(
                [sys.executable, SCRIPT, "--root", str(root), "--out", str(output)]
            )
            guide = output.read_text(encoding="utf-8")
            self.assertEqual(log.read_text(encoding="utf-8"), raw)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("current-failure", guide)
        self.assertIn("src/product.py", guide)
        self.assertIn("affected inputs, not established cause locations", guide)
        self.assertIn("locate the concrete cause", guide)

    def test_native_oop_checker_failure_keeps_the_target_path(self) -> None:
        """Retargeted native OOP commands still identify the affected source input."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            target = "tools/runtime/lifecycle/bootstrap_agent_run.py"
            log = (
                mounted_log_archive_root(root)
                / "hook-runs"
                / "legacy-import"
                / "test-container"
                / "oop_readability_guard.jsonl"
            )
            log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "native-oop-failed",
                        "hook_log_namespace": "test-container",
                        "event": "PostToolUse",
                        "status": "fail",
                        "payload_fingerprint": "native-oop-input",
                        "failure_fingerprint": "native-oop-failure",
                        "commands": [
                            {
                                "command": [
                                    "tools/bin/agent-canon",
                                    "oop-python-readability",
                                    "--root",
                                    str(root),
                                    target,
                                ],
                                "returncode": 1,
                                "output_snippet": "readability review failed",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = self.runtime_root / "reports" / "native-oop-guide.md"
            result = self.run_cli(
                [sys.executable, SCRIPT, "--root", str(root), "--out", str(output)]
            )
            guide = output.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("native-oop-failure", guide)
        self.assertIn(target, guide)

    def test_generates_guidance_from_issues_knowledge_and_hook_logs(self) -> None:
        """The guide should summarize every evidence family."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            output = self.runtime_root / "reports" / "guide.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            guide = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AGENT_IMPROVEMENT_GUIDE=", result.stdout)
        self.assertIn("github_issue_refs: `1`", guide)
        self.assertIn("skill_usage_counts:", guide)
        self.assertIn("agent-orchestration", guide)
        self.assertNotIn("- `latest`: `1`", guide)
        self.assertNotIn("- `skill-name`: `1`", guide)
        self.assertNotIn("skill:latest", guide)
        self.assertNotIn("skill:skill-name", guide)
        self.assertIn("tool_input_skill_usage_ignored", guide)
        self.assertIn("noncanonical_skill_usage_ignored", guide)
        self.assertIn("agent-orchestration@UserPromptSubmit", guide)
        self.assertIn("hook_tool_counts:", guide)
        self.assertIn("apply_patch", guide)
        self.assertIn("hook_namespace_counts:", guide)
        self.assertIn("test-container", guide)
        self.assertIn("skill_source_counts:", guide)
        self.assertIn("prompt", guide)
        self.assertIn("prompt_candidate_skill_counts:", guide)
        self.assertIn("result-artifact-writeout", guide)
        self.assertNotIn("Skill Routing Gaps", guide)
        self.assertIn(
            "prompt_candidate_skill_counts: `{'result-artifact-writeout': 1}`", guide
        )
        self.assertIn("prompt_candidate_workflow_counts:", guide)
        self.assertIn("codex-task-workflow", guide)
        self.assertIn("prompt_candidate_tool_counts:", guide)
        self.assertIn("workflow_monitor.py", guide)
        self.assertIn("human_feedback_label_counts:", guide)
        self.assertIn("quality_gap", guide)
        self.assertIn("human_feedback_target_counts:", guide)
        self.assertIn("skill:result-artifact-writeout", guide)
        self.assertIn("human_feedback_action_counts:", guide)
        self.assertIn("prompt_repair", guide)
        self.assertIn("Observed Failure Targets", guide)
        self.assertIn("tools/runtime/lifecycle/bootstrap_agent_run.py", guide)
        self.assertIn("hook_quality_counts:", guide)
        self.assertIn("unknown_event", guide)
        self.assertIn("Hook Observability Counters", guide)
        self.assertNotIn("Protocol Feedback Coverage", guide)
        self.assertNotIn("required_tokens:", guide)
        self.assertNotIn("failure-a", guide)
        self.assertIn("agent-canon-log/knowledge", guide)
        self.assertIn("observability limits", guide)
        self.assertNotIn("Repair skill or workflow prompt surfaces", guide)
        self.assertNotIn("repair unknown events", guide)

    def test_skill_counts_ignore_pre_cutover_skill_logs(self) -> None:
        """Skill source updates should exclude older observations from current counters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_cutover_fixture(root)
            output = self.runtime_root / "reports" / "guide.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            guide = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill_usage_counts: `{}`", guide)
        self.assertIn("prompt_candidate_skill_counts: `{}`", guide)
        self.assertIn("human_feedback_target_counts: `{}`", guide)
        self.assertIn("skill_routing_signal_before_cutover_ignored", guide)
        self.assertIn(
            "skill_routing_signal_before_cutover_ignored:agent-orchestration",
            guide,
        )

    def test_skill_counts_keep_post_cutover_observations_without_inventing_gaps(
        self,
    ) -> None:
        """The same selected event may also be a candidate and feedback observation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_cutover_fixture(root, include_post_cutover=True)
            output = self.runtime_root / "reports" / "guide.md"

            result = self.run_cli(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--out",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            guide = output.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill_usage_counts: `{'agent-orchestration': 1}`", guide)
        self.assertIn(
            "prompt_candidate_skill_counts: `{'agent-orchestration': 1}`", guide
        )
        self.assertIn(
            "human_feedback_target_counts: `{'skill:agent-orchestration': 1}`", guide
        )
        self.assertNotIn("Skill Routing Gaps", guide)
        self.assertNotIn("Repair skill-selection routing", guide)

    def write_skill_usage_fixture(self, root: Path, record: dict[str, object]) -> None:
        """Write one historical skill-usage event through the archive owner."""
        skill = (
            root / ".codex" / "personal" / "skills" / "agent-orchestration" / "SKILL.md"
        )
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("# Agent orchestration\n", encoding="utf-8")
        hook = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / "legacy-import"
            / "test-container"
            / "skill_usage.jsonl"
        )
        hook.parent.mkdir(parents=True, exist_ok=True)
        record.setdefault("hook_run_id", "native-guide-fixture")
        record.setdefault("hook_log_namespace", "test-container")
        record.setdefault("timestamp", "2026-11-12T10:00:00Z")
        hook.write_text(json.dumps(record) + "\n", encoding="utf-8")

    def write_fixture(self, root: Path) -> None:
        """Write a small AgentCanon-like evidence tree."""
        root.mkdir(parents=True, exist_ok=True)
        evals_root = root / "eval" / "definitions"
        evals_root.mkdir(parents=True, exist_ok=True)
        (evals_root / "README.md").write_text("# Eval fixture\n", encoding="utf-8")
        archive_root = mounted_log_archive_root(root)
        hook_results = archive_root / "hook-runs" / "legacy-import" / "test-container"
        hook_results.mkdir(parents=True)
        issue_packets = (
            self.runtime_root
            / "agent-canon-log"
            / "feedback"
            / "issue-packets"
            / "pending"
        )
        issue_packets.mkdir(parents=True)
        (issue_packets / "AC-20260513-open.json").write_text(
            json.dumps(
                {
                    "issue_url": "https://github.com/iwashita-nozomu/agent-canon/issues/20260513",
                    "repository": "iwashita-nozomu/agent-canon",
                    "number": "20260513",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        knowledge = (
            self.runtime_root
            / "agent-canon-log"
            / "knowledge"
            / "topics"
            / "durable-learning"
        )
        knowledge.mkdir(parents=True)
        (knowledge / "candidate.md").write_text(
            "# Durable learning\n", encoding="utf-8"
        )
        for skill in (
            "agent-orchestration",
            "codex-task-workflow",
            "result-artifact-writeout",
        ):
            skill_path = root / ".codex" / "personal" / "skills" / skill / "SKILL.md"
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            skill_path.write_text(
                f"---\nname: {skill}\ndescription: test skill\n---\n\n# {skill}\n",
                encoding="utf-8",
            )
        (hook_results / "oop_readability_guard.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "hook-test",
                    "hook_log_namespace": "test-container",
                    "event": "PostToolUse",
                    "status": "warn",
                    "payload_fingerprint": "payload-a",
                    "tool_name": "apply_patch",
                    "review_signal_count": 1,
                    "commands": [
                        {
                            "command": [
                                "tools/bin/agent-canon",
                                "oop-python-readability",
                                "--root",
                                str(root),
                                "tools/runtime/lifecycle/bootstrap_agent_run.py",
                            ],
                            "returncode": 0,
                            "output_snippet": (
                                "OOP_READABILITY_REVIEW_SIGNAL_FINDINGS=1\n"
                                'OOP_READABILITY_TYPED_BOUNDARY_COUNTS={\\"api_boundary\\": 1}'
                            ),
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (hook_results / "skill_usage.jsonl").write_text(
            json.dumps(
                {
                    "hook_run_id": "skill-hook-test",
                    "event": "UserPromptSubmit",
                    "status": "pass",
                    "payload_fingerprint": "payload-skill-a",
                    "hook_log_namespace": "test-container",
                    "skills": ["agent-orchestration", "codex-task-workflow"],
                    "skill_count": 2,
                    "candidate_skills": ["result-artifact-writeout"],
                    "candidate_workflows": ["codex-task-workflow"],
                    "candidate_tools": ["workflow_monitor.py"],
                    "prompt_feedback_detected": True,
                    "feedback_labels": ["quality_gap", "repair_request"],
                    "feedback_targets": [
                        "skill:result-artifact-writeout",
                        "tool:workflow_monitor.py",
                    ],
                    "feedback_action": "prompt_repair",
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-shell-vars",
                    "event": "PostToolUse",
                    "status": "pass",
                    "payload_fingerprint": "payload-shell-vars",
                    "hook_log_namespace": "test-container",
                    "skills": ["latest"],
                    "skill_count": 1,
                    "feedback_targets": ["skill:latest"],
                    "skill_source_fields": ["tool_input"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "tool_name": "Bash",
                    "tool_command_verb": "latest=$(ls",
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-placeholder",
                    "event": "Stop",
                    "status": "pass",
                    "payload_fingerprint": "payload-placeholder",
                    "hook_log_namespace": "test-container",
                    "skills": ["skill-name"],
                    "skill_count": 1,
                    "feedback_targets": ["skill:skill-name"],
                    "skill_source_fields": ["last_assistant_message"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 0,
                }
            )
            + "\n"
            + json.dumps(
                {
                    "hook_run_id": "skill-hook-empty",
                    "event": "UnknownHookEvent",
                    "status": "pass",
                    "payload_fingerprint": "payload-skill-empty",
                    "hook_log_namespace": "test-container",
                    "skills": [],
                    "skill_count": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def write_cutover_fixture(
        self,
        root: Path,
        *,
        include_post_cutover: bool = False,
    ) -> None:
        """Write a Git-backed fixture with hook evidence older than skill source."""
        root.mkdir(parents=True, exist_ok=True)
        evals_root = root / "agents" / "evals"
        evals_root.mkdir(parents=True, exist_ok=True)
        (evals_root / "README.md").write_text("# Eval fixture\n", encoding="utf-8")
        skill_path = (
            root / ".codex" / "personal" / "skills" / "agent-orchestration" / "SKILL.md"
        )
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(
            "---\nname: agent-orchestration\ndescription: test skill\n---\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init"], cwd=root, check=True, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "add", ".codex/personal/skills/agent-orchestration/SKILL.md"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_env = os.environ.copy()
        commit_env.update(
            {
                "GIT_AUTHOR_DATE": "2026-05-21T10:00:00+00:00",
                "GIT_COMMITTER_DATE": "2026-05-21T10:00:00+00:00",
            }
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=AgentCanon Test",
                "-c",
                "user.email=agentcanon-test@example.invalid",
                "commit",
                "-m",
                "update agent orchestration skill",
            ],
            cwd=root,
            env=commit_env,
            check=True,
            capture_output=True,
            text=True,
        )
        hook_results = (
            mounted_log_archive_root(root)
            / "hook-runs"
            / "legacy-import"
            / "test-container"
        )
        hook_results.mkdir(parents=True)
        entries: list[dict[str, object]] = [
            {
                "hook_run_id": "skill-hook-before-cutover",
                "event": "UserPromptSubmit",
                "timestamp": "2026-05-20T10:00:00Z",
                "status": "pass",
                "payload_fingerprint": "payload-before-cutover",
                "hook_log_namespace": "test-container",
                "candidate_skills": ["agent-orchestration"],
                "feedback_targets": ["skill:agent-orchestration"],
                "feedback_labels": ["repair_request"],
                "skill_source_fields": ["prompt"],
                "observed_text_field_count": 1,
                "observed_text_value_count": 1,
                "workflow_monitor_event_count": 1,
                "workflow_monitor_report_dir": "reports/agents/test",
            }
        ]
        if include_post_cutover:
            entries.append(
                {
                    "hook_run_id": "skill-hook-after-cutover",
                    "event": "UserPromptSubmit",
                    "timestamp": "2026-05-22T10:00:00Z",
                    "status": "pass",
                    "payload_fingerprint": "payload-after-cutover",
                    "hook_log_namespace": "test-container",
                    "skills": ["agent-orchestration"],
                    "skill_count": 1,
                    "candidate_skills": ["agent-orchestration"],
                    "feedback_targets": ["skill:agent-orchestration"],
                    "feedback_labels": ["repair_request"],
                    "skill_source_fields": ["prompt"],
                    "observed_text_field_count": 1,
                    "observed_text_value_count": 1,
                    "workflow_monitor_event_count": 1,
                    "workflow_monitor_report_dir": "reports/agents/test",
                }
            )
        (hook_results / "skill_usage.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
