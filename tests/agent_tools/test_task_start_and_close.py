# @dependency-start
# contract test
# responsibility Tests test task start and close behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/agent_tools/agent_canon_preflight.py preflight routing under test
# @dependency-end

"""Tests for machine-driven task start and close commands."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_start.py"
TASK_CLOSE_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_close.py"
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
WORKTREE_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "worktree_start.py"
SETUP_WORKTREE_SCRIPT = PROJECT_ROOT / "tools" / "setup_worktree.sh"


def current_git_head(workspace: Path = PROJECT_ROOT) -> str:
    """Return the current repository commit for closeout fixtures."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_diff_ref(workspace: Path = PROJECT_ROOT) -> str:
    """Return the current tracked diff ref expected by task_close."""
    head = current_git_head(workspace)
    unstaged = subprocess.run(
        ["git", "diff", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--binary"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    diff_bytes = unstaged.stdout + staged.stdout
    if untracked.returncode == 0 and untracked.stdout:
        for raw_path in sorted(path for path in untracked.stdout.split(b"\0") if path):
            if raw_path.startswith(b"reports/agents/"):
                continue
            path = workspace / raw_path.decode("utf-8", errors="surrogateescape")
            diff_bytes += b"\0UNTRACKED\0" + raw_path + b"\0"
            if path.is_file():
                diff_bytes += path.read_bytes()
    if not diff_bytes:
        return head
    return f"{head}-dirty-{hashlib.sha256(diff_bytes).hexdigest()}"


def current_changed_markdown_paths(workspace: Path = PROJECT_ROOT) -> tuple[str, ...]:
    """Return source Markdown paths changed in the workspace."""
    paths: set[str] = set()
    commands = (
        ("git", "diff", "--name-only"),
        ("git", "diff", "--cached", "--name-only"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    for command in commands:
        result = subprocess.run(
            list(command),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            path = line.strip()
            if path.endswith(".md") and not path.startswith(
                ("reports/", ".agent-canon/log-archive/")
            ):
                paths.add(path)
    return tuple(sorted(paths))


def ready_closeout_evidence_lines(
    diff_ref: str | None = None, workspace: Path = PROJECT_ROOT
) -> list[str]:
    """Return structured closeout evidence lines for a ready bundle."""
    latest_diff_ref = diff_ref or current_diff_ref(workspace)
    changed_markdown = current_changed_markdown_paths(workspace)
    document_structure_paths = (
        ",".join(changed_markdown) if changed_markdown else "fixture-format-only.md"
    )
    return [
        "",
        "## AgentCanon Latest And CI Gate Evidence",
        "- agent_canon_latest_command: make agent-canon-ensure-latest",
        "- agent_canon_latest_status: pass",
        "- agent_canon_submodule_status: fixture-clean",
        "- agent_canon_source_head: fixture-source-head",
        "- agent_canon_parent_pin: fixture-parent-pin",
        "",
        "## Mechanical Completion Loop Evidence",
        "- mechanical_loop_iterations: 1",
        "- mechanical_loop_open_items: none",
        "- mechanical_loop_stop_reason: all structured loop fields complete",
        "- mechanical_loop_planned_work_status: complete",
        "- mechanical_loop_review_findings_status: none",
        "- mechanical_loop_validation_status: pass",
        "- mechanical_loop_dependency_review_status: pass",
        "- mechanical_loop_static_analysis_status: pass",
        "- mechanical_loop_commit_push_status: complete",
        "- mechanical_loop_canon_sync_status: complete",
        "- mechanical_loop_follow_up_status: none",
        "",
        "## Tool Warning Evidence",
        "- tool_warning_monitoring_status: none",
        "- tool_warning_open_items: none",
        "- tool_warning_resolution_evidence: workflow_monitoring.md no warnings observed",
        "",
        "## Document Structure Evidence",
        f"- document_structure_paths: {document_structure_paths}",
        "- document_structure_status: skipped",
        "- document_split_decision: not_applicable:format-only: fixture closeout bundle",
        "- structure_planning: not_applicable",
        "- prose_graph: not_applicable",
        "- structure_contract: skipped: fixture format-only route",
        "- md_style_check: pass",
        "- format_only_reason: fixture closeout bundle",
        "",
        "## Subagent Lifecycle Evidence",
        "- fresh_subagents_required: yes",
        "- reuse_for_new_task: forbidden",
        "- previous_task_subagent_reuse: none",
        "- agent_wave_ledger_status: complete",
        "- planned_vs_actual_wave_status: reconciled",
        "- dynamic_spawn_policy_status: applied",
        "- subagent_closeout_status: closed",
        "- open_subagent_instances: none",
        "- close_agent_evidence: parent_direct_no_open_subagents",
        "",
        "## Diff-Check Agent Evidence",
        "- diff_check_agent_role: reviewer",
        "- diff_check_agent_decision: approve",
        f"- diff_check_latest_diff_ref: {latest_diff_ref}",
        "- diff_check_artifact: diff_check_review.md",
        "",
        "## Runtime Log Archive Evidence",
        "- runtime_log_archive_sync_command: python3 tools/agent_tools/runtime_log_archive_git.py sync",
        "- runtime_log_archive_sync_status: pass",
        (
            "- runtime_log_archive_check_clean_command: "
            "python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain"
        ),
        "- runtime_log_archive_check_clean_status: pass",
        "- runtime_log_archive_repo_key: fixture-repo",
        "- runtime_log_archive_branch: logs/fixture-repo",
        "- runtime_log_archive_branch_match: yes",
        "- runtime_log_archive_dirty: no",
        "- runtime_log_archive_foreign_dirty: no",
        "- runtime_log_archive_commit: no-op",
        "- runtime_log_archive_push: no-op",
        "",
    ]


def write_ready_schedule(report_dir: Path) -> None:
    """Write a filled schedule artifact."""
    (report_dir / "schedule.md").write_text(
        "\n".join(
            [
                "# Schedule",
                "",
                "## Stage Plan",
                "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                "| requirements | manager | manager_reviewer | contract | fixed | done |",
                "## Clause Coverage",
                "| Clause ID | Covered By Stage | Review Gate | Status |",
                "| --------- | ---------------- | ----------- | ------ |",
                "| T1-C1 | requirements | requirements | done |",
                "## Planned Work Units",
                "| Unit ID | Clause IDs | Owner | Completion Evidence | Next Gate | Status |",
                "| ------- | ---------- | ----- | ------------------- | --------- | ------ |",
                "| W1 | T1-C1 | codex | tests | final | done |",
                "## Agent Wave Ledger",
                (
                    "| Wave ID | Parent Or Delegate | Spawn Authority | Trigger | Budget Before | "
                    "Budget After | Runtime Max Threads | Runtime Max Depth | Spawned Roles | "
                    "Role Instances | Skipped Roles / Rationale | Allowed Paths | Do Not Read | Write Scope | "
                    "Validation Route | Review Gate | Handoff Artifacts | Delegated Policy Ref | Status |"
                ),
                (
                    "| ------- | ------------------ | --------------- | ------- | ------------- | "
                    "------------ | ------------------- | ----------------- | ------------- | "
                    "-------------- | ------------------------- | ------------- | ----------- | ----------- | "
                    "---------------- | ----------- | ----------------- | -------------------- | ------ |"
                ),
                (
                    "| WAVE-1 | parent | parent | initial_intake | 0/12 | 3/12 | 24 | 2 | "
                    "requirements_organizer,explorer,execution_planner | "
                    "requirements_organizer:intake_requirements:team_manifest.yaml,"
                    "explorer:intake_explorer:team_manifest.yaml,"
                    "execution_planner:intake_plan:team_manifest.yaml | none | reports/agents/run | "
                    "unrelated | read-only | pytest | schedule_review | team_manifest.yaml | "
                    "team_manifest.yaml#run.delegated_spawn_policy | done |"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _log_ready_work(report_dir: Path) -> None:
    """Write a filled work-log artifact."""
    (report_dir / "work_log.md").write_text(
        "\n".join(
            [
                "# Work Log",
                "",
                "## Purpose",
                "- Record meaningful execution steps.",
                "",
                "## Entries",
                (
                    "- `2026-04-08 09:00 JST | kickoff | fixed request clauses | "
                    "request_clause_ids: T1-C1 | next: implement`"
                ),
                (
                    "- `2026-04-08 09:30 JST | test | passed closeout checks | "
                    "request_clause_ids: T1-C1 | next: close`"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ready_workflow_monitoring(report_dir: Path) -> None:
    """Write workflow monitoring evidence with no open tool warnings."""
    (report_dir / "workflow_monitoring.md").write_text(
        "\n".join(
            [
                "# Workflow Monitoring",
                "",
                "## Actual Wave Events",
                "",
                (
                    "- wave_event=recorded wave_id=WAVE-1 event_kind=initial_intake "
                    "spawn_authority=parent trigger=initial_intake budget_before=0/12 "
                    "budget_after=3/12 runtime_max_threads=24 runtime_max_depth=2 "
                    "spawned_roles=requirements_organizer,explorer,execution_planner "
                    "role_instances=requirements_organizer:intake_requirements:team_manifest.yaml,"
                    "explorer:intake_explorer:team_manifest.yaml,"
                    "execution_planner:intake_plan:team_manifest.yaml "
                    "skipped_roles=none allowed_paths=reports/agents/run "
                    "do_not_read=unrelated write_scope=read-only validation_route=pytest "
                    "review_gate=schedule_review handoff_artifacts=team_manifest.yaml status=done"
                ),
                "",
                "## Tool Warnings",
                "",
                "- tool_warnings_status: none",
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_mid_task_wave_checkpoint(
    report_dir: Path,
    *,
    updated_packet: str = "reports/agents/run/user_delta_001.md",
    input_classification: str = "same_active_task_delta",
    scope_status: str | None = None,
    redispatch_action: str | None = None,
    spawn_authority: str | None = None,
    target_agents: str | None = None,
    spawned_roles: str | None = None,
    role_instances: str | None = None,
    skipped_roles: str | None = None,
    allowed_paths: str = "reports/agents/run",
    do_not_read: str = "unrelated",
    write_scope: str = "read-only",
    validation_route: str = "pytest",
    review_gate: str = "parent_review",
    handoff_artifacts: str = "reports/agents/run/user_delta_001.md",
    status: str = "checkpointed",
    fresh_wave_evidence: str | None = None,
    fresh_run_bundle: str | None = None,
) -> None:
    """Append a matching mid-task user input wave checkpoint fixture."""
    if input_classification == "same_active_task_delta":
        scope_status = scope_status or "unchanged"
        redispatch_action = redispatch_action or "send_input"
        spawn_authority = spawn_authority or "parent_checkpoint_then_send_input"
        target_agents = target_agents or "explorer"
        spawned_roles = spawned_roles or "none"
        role_instances = role_instances or "none"
        skipped_roles = skipped_roles or f"{target_agents}:reused_run_local_send_input"
    elif input_classification == "scope_or_contract_change":
        scope_status = scope_status or "changed"
        redispatch_action = redispatch_action or "fresh_followup_wave"
        spawn_authority = spawn_authority or "parent_checkpoint_then_spawn_fresh_wave"
        target_agents = target_agents or "worker"
        spawned_roles = spawned_roles or target_agents
        role_instances = role_instances or f"{spawned_roles}:followup:{updated_packet}"
        skipped_roles = skipped_roles or "none"
    elif input_classification == "new_task":
        scope_status = scope_status or "new_task"
        redispatch_action = redispatch_action or "fresh_run"
        spawn_authority = spawn_authority or "fresh_run_required"
        target_agents = target_agents or "none"
        spawned_roles = spawned_roles or "none"
        role_instances = role_instances or "none"
        skipped_roles = skipped_roles or "none"
    else:
        raise ValueError(f"unsupported test classification: {input_classification}")
    extra_fields = ""
    if fresh_wave_evidence is not None:
        extra_fields += f" fresh_wave_evidence={fresh_wave_evidence}"
    if fresh_run_bundle is not None:
        extra_fields += f" fresh_run_bundle={fresh_run_bundle}"
    schedule_path = report_dir / "schedule.md"
    schedule_text = schedule_path.read_text(encoding="utf-8")
    schedule_path.write_text(
        schedule_text.rstrip()
        + "\n"
        + (
            f"| WAVE-2 | parent | {spawn_authority} | mid_task_user_input | "
            f"3/12 | 3/12 | 24 | 2 | {spawned_roles} | {role_instances} | {skipped_roles} | "
            f"{allowed_paths} | {do_not_read} | {write_scope} | "
            f"{validation_route} | {review_gate} | {handoff_artifacts} | "
            f"team_manifest.yaml#run.subagent_lifecycle_policy | {status} |"
        )
        + "\n",
        encoding="utf-8",
    )
    monitoring_path = report_dir / "workflow_monitoring.md"
    monitoring_text = monitoring_path.read_text(encoding="utf-8")
    actual_event = (
        "- wave_event=recorded wave_id=WAVE-2 event_kind=mid_task_user_input "
        f"spawn_authority={spawn_authority} trigger=mid_task_user_input "
        "budget_before=3/12 budget_after=3/12 runtime_max_threads=24 "
        f"runtime_max_depth=2 spawned_roles={spawned_roles} "
        f"role_instances={role_instances} "
        f"skipped_roles={skipped_roles} allowed_paths={allowed_paths} "
        f"do_not_read={do_not_read} write_scope={write_scope} "
        f"validation_route={validation_route} review_gate={review_gate} "
        f"handoff_artifacts={handoff_artifacts} status={status} "
        f"input_classification={input_classification} "
        f"updated_packet={updated_packet} redispatch_action={redispatch_action} "
        f"target_agents={target_agents} scope_status={scope_status} "
        "lifecycle_policy_ref=team_manifest.yaml#run.subagent_lifecycle_policy"
        f"{extra_fields}"
    )
    monitoring_path.write_text(
        monitoring_text.replace(
            "\n## Tool Warnings", f"\n{actual_event}\n\n## Tool Warnings"
        ),
        encoding="utf-8",
    )


def write_ready_agent_evaluation(report_dir: Path) -> None:
    """Write a passing agent-evaluation artifact."""
    (report_dir / "agent_evaluation.md").write_text(
        "\n".join(
            [
                "# Agent Evaluation",
                "",
                "- evaluation_status: pass",
                "- score: 100",
                "- max_score: 100",
                "- threshold: 85",
                "- feedback_actions_resolved: yes",
                "- learning_capture_complete: yes",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ready_diff_check_artifact(
    report_dir: Path,
    *,
    workspace: Path = PROJECT_ROOT,
    role: str = "reviewer",
    decision: str = "approve",
    diff_ref: str | None = None,
    read_only: str = "yes",
    independent: str = "yes",
    findings_status: str = "none",
) -> None:
    """Write a passing independent diff-check review artifact."""
    latest_diff_ref = diff_ref or current_diff_ref(workspace)
    (report_dir / "diff_check_review.md").write_text(
        "\n".join(
            [
                "# Diff Check Review",
                "",
                "## Diff-Check Review",
                f"- diff_check_agent_role: {role}",
                f"- diff_check_agent_decision: {decision}",
                f"- diff_check_latest_diff_ref: {latest_diff_ref}",
                f"- diff_check_read_only: {read_only}",
                f"- diff_check_independent_agent: {independent}",
                f"- diff_check_findings_status: {findings_status}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ready_final_review(report_dir: Path) -> None:
    """Write a concrete approving final-review artifact."""
    (report_dir / "final_review.md").write_text(
        "\n".join(
            [
                "# Final Review",
                "",
                "## Decision",
                "",
                "approve",
                "",
                "## Evidence",
                "",
                "- Closeout fixture has concrete review evidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ready_closeout_bundle(
    report_dir: Path, run_id: str, workspace: Path = PROJECT_ROOT
) -> None:
    """Write ready closeout artifacts except the diff-check artifact."""
    active_run_path = report_dir.parent / ".active_run"
    if not active_run_path.exists():
        active_run_path.write_text(f"{run_id}\n", encoding="utf-8")
    (report_dir / "verification.txt").write_text(
        "\n".join(
            [
                f"run_id={run_id}",
                "task=diff artifact field smoke",
                "owner=codex",
                "created_at_utc=2026-04-08T00:00:00Z",
                "status=pass",
                "user_completion_report=unlocked",
                "closeout_gate_status=resolved",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "user_request_contract.md").write_text(
        "\n".join(
            [
                "# User Request Contract",
                "",
                "- all_clauses_resolved: yes",
                "- forbidden_drift_detected: no",
                "- deferred_clause_ids:",
                "- unresolved_clause_ids:",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (report_dir / "closeout_gate.md").write_text(
        "\n".join(
            [
                "# Closeout Gate",
                "",
                "## Gate Status",
                "",
                "- verifier_status: pass",
                "- auditor_status: resolved",
                "- required_reviews_complete: yes",
                "- validation_complete: yes",
                "- request_contract_complete: yes",
                "- all_planned_chunks_complete: yes",
                "- overall_delivery_complete: yes",
                "- unfinished_tasks_absent: yes",
                "- dependency_headers_complete: yes",
                "- repo_wide_dependency_tools_complete: yes",
                "- repo_wide_static_analysis_complete: yes",
                "- agent_canon_latest_complete: yes",
                "- make_ci_status: pass",
                "- spec_product_coverage_complete: yes",
                "- review_findings_integrated: yes",
                "- post_fix_full_review_complete: yes",
                "- tool_warnings_resolved: yes",
                "- mechanical_completion_loop_complete: yes",
                "- subagents_closed: yes",
                "- diff_check_agent_complete: yes",
                "- canonical_tree_head_complete: yes",
                "- agent_evaluation_complete: yes",
                "- runtime_log_archive_synced: yes",
                "- commit_created: yes",
                "- push_completed: yes",
                "- user_completion_report: unlocked",
                *ready_closeout_evidence_lines(workspace=workspace),
            ]
        ),
        encoding="utf-8",
    )
    write_ready_schedule(report_dir)
    _log_ready_work(report_dir)
    write_ready_workflow_monitoring(report_dir)
    write_ready_agent_evaluation(report_dir)
    write_ready_final_review(report_dir)


class TaskStartAndCloseTest(unittest.TestCase):
    """Verify machine-driven task start and close behavior."""

    def assert_current_checkout_write_policy(
        self,
        write_scope_policy: dict[str, object],
        max_write_subagents: int,
    ) -> None:
        """Assert the current-checkout writer serialization contract."""
        self.assertEqual(write_scope_policy["max_write_subagents"], max_write_subagents)
        self.assertEqual(
            write_scope_policy["overlapping_write_scopes"],
            "serialize_current_checkout_waves",
        )
        self.assertNotIn("active_subagents", write_scope_policy)

    def assert_same_role_runtime_policy(
        self,
        delegated_spawn_policy: dict[str, object],
    ) -> None:
        """Assert delegated spawn policy preserves same-role instance identity."""
        raw_handoff_fields = cast(
            "list[object]",
            delegated_spawn_policy["handoff_required_fields"],
        )
        handoff_required_fields = {str(field) for field in raw_handoff_fields}
        self.assertLessEqual(
            {
                "owner",
                "child_role",
                "child_instance_id",
                "input_packet",
                "allowed_paths",
                "do_not_read",
                "expected_output",
                "write_scope",
                "validation_route",
                "review_gate",
                "remaining_spawn_budget",
            },
            handoff_required_fields,
        )
        same_role_policy = cast(
            "dict[str, object]",
            delegated_spawn_policy["same_role_instances"],
        )
        self.assertEqual(
            same_role_policy["status"],
            "allowed_with_distinct_packets",
        )
        self.assertEqual(same_role_policy["identity_key"], "role_type+instance_id")
        raw_same_role_fields = cast(
            "list[object]",
            same_role_policy["required_fields"],
        )
        self.assertLessEqual(
            {
                "role_type",
                "instance_id",
                "input_packet",
                "allowed_paths",
                "do_not_read",
            },
            {str(field) for field in raw_same_role_fields},
        )

    def assert_initial_wave_execution_gate(self, report_dir: Path) -> None:
        """Assert generated run bundles expose the parent wave execution gate."""
        schedule_text = (report_dir / "schedule.md").read_text(encoding="utf-8")
        monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
            encoding="utf-8"
        )
        expected_schedule = (
            "| WAVE-1 | parent | parent_runtime_authority_required | "
            "bootstrap_initial_intake_wave |"
        )
        self.assertIn(expected_schedule, schedule_text)
        self.assertIn(
            "requirements_organizer,explorer,execution_planner", schedule_text
        )
        self.assertIn("Role Instances", schedule_text)
        self.assertIn("role_instances=none", monitoring_text)
        self.assertIn("blocked_authority_required", schedule_text)
        self.assertIn("wave_event=recorded wave_id=WAVE-1", monitoring_text)
        self.assertIn("event_kind=authority_blocker", monitoring_text)
        self.assertIn(
            "spawn_authority=parent_runtime_authority_required", monitoring_text
        )
        self.assertIn("status=blocked_authority_required", monitoring_text)
        self.assertIn(
            "handoff_artifacts=team_manifest.yaml#run.spawn_wave_recommendation",
            monitoring_text,
        )

    def assert_role_prompt_includes(
        self,
        manifest: dict[str, object],
        role_id: str,
        required_fields: set[str],
    ) -> None:
        """Assert one generated role prompt contract includes required fields."""
        roles = cast("list[object]", manifest["roles"])
        self.assertIsInstance(roles, list)
        role: dict[str, object] | None = None
        for candidate in roles:
            if not isinstance(candidate, dict):
                continue
            candidate_map = cast("dict[str, object]", candidate)
            if candidate_map.get("id") == role_id:
                role = candidate_map
                break
        self.assertIsNotNone(role, role_id)
        if role is None:
            return
        prompt_contract = cast("dict[str, object]", role["prompt_contract"])
        self.assertIsInstance(prompt_contract, dict)
        self.assertEqual(
            prompt_contract["common_prompt_must_include_ref"],
            "run.handoff_context_policy.common_prompt_must_include",
        )
        run = cast("dict[str, object]", manifest["run"])
        context_policy = cast("dict[str, object]", run["handoff_context_policy"])
        common_fields = cast(
            "list[object]", context_policy["common_prompt_must_include"]
        )
        role_fields = cast("list[object]", prompt_contract["role_prompt_must_include"])
        prompt_fields = {str(field) for field in (*common_fields, *role_fields)}
        self.assertTrue(required_fields.issubset(prompt_fields), role_id)

    def assert_abstract_design_prompt_contracts(
        self, manifest: dict[str, object]
    ) -> None:
        """Assert ADF prompt contracts for generated design and review roles."""
        expected = {
            "designer": {
                "abstract_design_frame",
                "responsibility_model",
                "concept_or_layer_model",
            },
            "design_reviewer": {
                "abstract_design_frame_review",
                "adf_before_file_scope",
                "adf_to_implementation_trace",
            },
            "implementer": {
                "abstract_design_frame",
                "implementation_source_packet",
                "design_to_implementation_trace",
            },
            "change_reviewer": {
                "abstract_design_frame_trace",
                "implementation_source_packet_entry",
                "revise_if_slice_only_justified_by_nearest_file_helper_or_current_finding",
            },
            "final_reviewer": {
                "abstract_design_frame_trace",
                "spec_to_product_trace",
                "review_finding_incorporation_trace",
            },
        }
        for role_id, fields in expected.items():
            self.assert_role_prompt_includes(manifest, role_id, fields)

    def test_bootstrap_skips_agent_canon_preflight_in_source_repo(self) -> None:
        """Source AgentCanon runs do not require a derived-repo update target."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_root = PROJECT_ROOT / "vendor" / "agent-canon"
            if not source_root.exists():
                source_root = PROJECT_ROOT
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "source canon preflight smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "source-canon-preflight",
                    "--workspace-root",
                    str(source_root),
                    "--report-root",
                    str(Path(tmp_dir) / "reports"),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_STATUS=skipped_source_canon", result.stdout
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST=documents/agent-canon-parent-repo-latest-checklist.md",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present", result.stdout
            )

    def test_task_start_routes_dirty_shared_canon_to_pr_first_workflow(self) -> None:
        """Dirty shared-canon surfaces should not point only to commit-or-stash."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            (workspace_root / "vendor" / "agent-canon").mkdir(parents=True)
            (workspace_root / "vendor" / "agent-canon" / "README.md").write_text(
                "shared canon candidate\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "shared canon preflight route",
                    "--owner",
                    "codex",
                    "--run-id",
                    "shared-canon-preflight",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_STATUS=blocked_shared_canon_workflow",
                result.stdout,
            )
            self.assertIn("open_agent-canon_PR", result.stdout)
            self.assertNotIn(
                "AGENT_CANON_PREFLIGHT_NEXT=commit_or_stash_then_run_make_agent-canon-ensure-latest",
                result.stdout,
            )

    def test_task_start_reports_parent_repo_latest_checklist(self) -> None:
        """Parent repos should expose the AgentCanon latest-state checklist at task start."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            checklist = (
                workspace_root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "parent checklist smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "parent-checklist",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST=vendor/agent-canon/documents/agent-canon-parent-repo-latest-checklist.md",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present", result.stdout
            )

    def test_task_start_allows_unrelated_parent_dirty_state_for_submodule_update(
        self,
    ) -> None:
        """A clean AgentCanon update surface may refresh despite unrelated parent dirt."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            checklist = (
                workspace_root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            (workspace_root / "Makefile").write_text(
                "agent-canon-ensure-latest:\n\t@echo latest-ok\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "add",
                    "Makefile",
                    "vendor/agent-canon/documents/agent-canon-parent-repo-latest-checklist.md",
                ],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Start Test",
                    "-c",
                    "user.email=task-start@example.invalid",
                    "commit",
                    "-m",
                    "test: seed workspace",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / "local-note.md").write_text(
                "unrelated\n", encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "parent dirty unrelated smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "parent-dirty-unrelated",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            assert result.returncode == 0
            self.assertIn("RUN_ID=parent-dirty-unrelated", result.stdout)
            self.assertIn(
                f"REPORT_DIR={report_root / 'parent-dirty-unrelated'}",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_PARENT_DIRTY_OUTSIDE_UPDATE_SURFACE=yes",
                result.stdout,
            )
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=pass", result.stdout)
            self.assertNotIn(
                "AGENT_CANON_PREFLIGHT_STATUS=blocked_shared_canon_workflow",
                result.stdout,
            )
            self.assertTrue(
                (report_root / "parent-dirty-unrelated" / "schedule.md").is_file()
            )

    def test_task_start_emits_workflow_skills_and_auto_specialists(self) -> None:
        """task_start should emit machine-friendly workflow and reviewer data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "comprehensive native implementation change",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-task-start",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--changed-path",
                    "src/example.cpp",
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_COMMAND=make agent-canon-ensure-latest",
                result.stdout,
            )
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=skipped_by_flag", result.stdout)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn("RUNTIME_MAX_DEPTH=2", result.stdout)
            self.assertIn("WORKFLOW_FAMILY=comprehensive_development", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=12", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=4", result.stdout)
            self.assertIn("INITIAL_THREE_AGENT_INTAKE_IS_TOTAL_CAP=no", result.stdout)
            self.assertIn("DYNAMIC_SUBAGENT_EXPANSION=allowed", result.stdout)
            self.assertIn(
                "DYNAMIC_SUBAGENT_EXPANSION_LEDGER=schedule.md#Agent Wave Ledger",
                result.stdout,
            )
            self.assertIn(
                "SUBAGENT_WAVE_RECORD_COMMAND=python3 tools/agent_tools/workflow_monitor.py --report-dir",
                result.stdout,
            )
            self.assertIn("--subagent-wave", result.stdout)
            self.assertIn(
                "PARENT_WAVE_EXECUTION_GATE=required_before_implementation",
                result.stdout,
            )
            self.assertIn(
                "PARENT_WAVE_EXECUTION_GATE_STATUS=blocked_authority_required",
                result.stdout,
            )
            self.assertIn(
                "PARENT_WAVE_EXECUTION_GATE_ARTIFACTS="
                "schedule.md#Agent Wave Ledger,workflow_monitoring.md#Actual Wave Events",
                result.stdout,
            )
            first_wave_match = re.search(
                r"^RECOMMENDED_INITIAL_SUBAGENT_WAVE=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(first_wave_match)
            first_wave = cast(re.Match[str], first_wave_match).group(1).split(",")
            self.assertEqual(
                first_wave,
                ["requirements_organizer", "explorer", "execution_planner"],
            )
            dynamic_waves_match = re.search(
                r"^RECOMMENDED_DYNAMIC_EXPANSION_WAVES=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(dynamic_waves_match)
            dynamic_waves = cast(re.Match[str], dynamic_waves_match).group(1)
            self.assertIn("WAVE-2=manager_reviewer", dynamic_waves)
            role_instances_match = re.search(
                r"^RECOMMENDED_DYNAMIC_EXPANSION_ROLE_INSTANCES=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(role_instances_match)
            role_instances = cast(re.Match[str], role_instances_match).group(1)
            self.assertIn("researcher:explorer:researcher_explorer", role_instances)
            self.assertIn(
                "research_reviewer:reviewer:research_reviewer_reviewer", role_instances
            )
            self.assertIn(
                "infra_reviewer:reviewer:infra_reviewer_reviewer", role_instances
            )
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$comprehensive-development",
                result.stdout,
            )
            self.assertIn(
                "ACTIVE_SKILLS=$agent-orchestration,$subagent-bootstrap,$comprehensive-development",
                result.stdout,
            )
            self.assertIn(
                "DEFERRED_SKILLS=$codex-task-workflow",
                result.stdout,
            )
            self.assertIn("AUTO_SPECIALISTS=cpp_reviewer", result.stdout)
            self.assertIn(
                "IMPLEMENTATION_CODEX_AGENTS=spark_worker,worker", result.stdout
            )
            self.assertIn(
                "SAME_ROLE_SUBAGENT_INSTANCES=allowed_with_distinct_packets",
                result.stdout,
            )
            self.assertIn(
                "SAME_ROLE_SUBAGENT_INSTANCE_KEY=role_type+instance_id",
                result.stdout,
            )
            self.assertIn(
                "STANDARD_AGENT_WAVE_SEQUENCE=plan,review,edit",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_SCOPE_POLICY=discovery_before_handoff_scope",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_SCOPE_SEQUENCE=surface_route_seed,responsibility_search,reuse_survey,stale_surface_scan,dependency_expansion,handoff_scope",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_SCOPE_STATUS=seed_then_expand_before_handoff",
                result.stdout,
            )
            self.assertIn("USER_FACING_LANGUAGE=ja", result.stdout)
            self.assertIn(
                "USER_FACING_LANGUAGE_SOURCE=AGENTS.md#Template Context",
                result.stdout,
            )
            self.assertIn(
                "USER_FACING_LANGUAGE_SCOPE=updates,final_reports,review_summaries,handoff_guidance,reader_facing_docs",
                result.stdout,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete",
                result.stdout,
            )
            self.assertIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)
            self.assertIn("PARENT_REPO_EDITS_ALLOWED=no", result.stdout)
            self.assertIn(
                "PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes",
                result.stdout,
            )
            self.assertIn(
                "PARENT_DIRECT_WRITE_EXCEPTION=-",
                result.stdout,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETENESS_SCOPE_BASIS=contract_required_behavior",
                result.stdout,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETENESS_REQUIRED_INPUTS=request_clause_ids,acceptance_contract,implementation_source_packet,design_to_implementation_trace,dependency_expanded_scope,pre_handoff_gate_status,validation_route,review_gate",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_GATE_STATUS=pending_design_review_gate_check",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE=current_design_brief,design_review_artifact_under_review,design_review_decision_approve,waterfall_gate_check_design_pass,document_flow_review_when_active",
                result.stdout,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETENESS_ROUTE_SIGNALS=apparent_breadth,owner_bounded_change,mvp,thin_slice",
                result.stdout,
            )
            self.assertIn(
                "IMPLEMENTATION_COMPLETENESS_ESCALATION=design_issue_blocker_to_gate_5_6",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_POLICY=selected_skill_command_packets",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_EXECUTION_MODE=sequential_by_skill_and_stage",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_SEQUENCE=show_skill_packet,run_required_commands,run_task_matching_conditional_commands,run_validation_commands",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_NEXT_COMMAND=python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text",
                result.stdout,
            )
            self.assertIn(
                "REPO_DYNAMIC_SKILL_ROUTING_POLICY=related_skill_candidates",
                result.stdout,
            )
            self.assertIn(
                "REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES=$task-routing",
                result.stdout,
            )
            self.assertIn("DEFAULT_QUALITY_CHECKS=enabled", result.stdout)
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_SOURCE=agents/canonical/CODEX_SUBAGENTS.md#Quality Check Default",
                result.stdout,
            )
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_AGENT_TYPES=test_designer,docs_workflow_steward,python_reviewer,cpp_reviewer,diff_triage_reviewer,reviewer",
                result.stdout,
            )
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_STAGES=review_before_edit_handoff,post_edit_review",
                result.stdout,
            )
            self.assertIn("DEFAULT_QUALITY_CHECK_REVIEW_PACKS=active", result.stdout)
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_DEFAULT_REVIEW_PACKS=repo_integration_review",
                result.stdout,
            )
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_AUTO_LANGUAGE_REVIEWERS=cpp_reviewer",
                result.stdout,
            )
            self.assertIn("ROLE_MODEL_MATRIX=", result.stdout)
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/REVIEW_PROCESS.md", result.stdout)
            self.assertIn("/notes/guardrails/README.md", result.stdout)
            self.assertNotIn("/docker/README.md", result.stdout)
            self.assertIn(
                "/agents/workflows/implementation-waterfall-workflow.md", result.stdout
            )
            self.assertIn("DESIGN_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("IMPLEMENTATION_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("REQUEST_CONTRACT_REQUIRED=yes", result.stdout)
            self.assertIn("REQUEST_CONTRACT=", result.stdout)
            self.assertIn(
                "START_DECLARATION=workflow=Comprehensive Development", result.stdout
            )
            self.assertIn(
                "skills=$agent-orchestration,$subagent-bootstrap,$comprehensive-development",
                result.stdout,
            )
            self.assertIn("cpp_reviewer", result.stdout)
            manifest_text = (
                report_root / "test-task-start" / "team_manifest.yaml"
            ).read_text(
                encoding="utf-8",
            )
            manifest = yaml.safe_load(manifest_text)
            spawn_budget = manifest["run"]["spawn_budget"]
            standard_wave_sequence = manifest["run"]["standard_wave_sequence"]
            pre_handoff_scope_policy = manifest["run"]["pre_handoff_scope_policy"]
            default_quality_check_policy = manifest["run"][
                "default_quality_check_policy"
            ]
            delegated_spawn_policy = manifest["run"]["delegated_spawn_policy"]
            handoff_context_policy = manifest["run"]["handoff_context_policy"]
            write_scope_policy = manifest["run"]["write_scope_policy"]
            spawn_wave_recommendation = manifest["run"]["spawn_wave_recommendation"]
            role_topology = spawn_wave_recommendation["role_topology"]
            same_role_instances = role_topology["same_role_parallel_instances"]
            self.assertEqual(spawn_budget["active_subagents"], 12)
            self.assertEqual(spawn_budget["max_write_subagents"], 4)
            self.assertEqual(spawn_budget["runtime_max_threads"], 24)
            self.assertEqual(spawn_budget["runtime_max_depth"], 2)
            self.assertFalse(spawn_budget["initial_three_agent_intake_is_total_cap"])
            self.assertIn("workflow_families[].spawn_budget", spawn_budget["source"])
            self.assertEqual(
                delegated_spawn_policy["dynamic_mid_task_spawn"],
                "allowed",
            )
            self.assertEqual(
                standard_wave_sequence["stages"], ["plan", "review", "edit"]
            )
            self.assertEqual(
                standard_wave_sequence["gate_order"],
                "plan_packet,review_gate,edit_handoff",
            )
            self.assertTrue(pre_handoff_scope_policy["enabled"])
            self.assertEqual(
                pre_handoff_scope_policy["status"],
                "seed_then_expand_before_handoff",
            )
            self.assertEqual(
                pre_handoff_scope_policy["sequence"],
                [
                    "surface_route_seed",
                    "responsibility_search",
                    "reuse_survey",
                    "stale_surface_scan",
                    "dependency_expansion",
                    "handoff_scope",
                ],
            )
            self.assertEqual(
                pre_handoff_scope_policy["source_packet_seed"],
                "implementation_surface_route",
            )
            self.assertIn(
                "dependency_edit_scope",
                pre_handoff_scope_policy["expansion_artifacts"],
            )
            user_facing_language_policy = manifest["run"]["user_facing_language_policy"]
            self.assertTrue(user_facing_language_policy["enabled"])
            self.assertEqual(user_facing_language_policy["language"], "ja")
            self.assertEqual(
                user_facing_language_policy["source"],
                "AGENTS.md#Template Context",
            )
            self.assertIn("final_reports", user_facing_language_policy["scope"])
            self.assertEqual(
                user_facing_language_policy["machine_fields"],
                "canonical_keys_commands_paths_role_ids_schemas",
            )
            contract_complete_implementation_policy = manifest["run"][
                "contract_complete_implementation_policy"
            ]
            repo_tool_routing_policy = manifest["run"]["repo_tool_routing_policy"]
            self.assertTrue(contract_complete_implementation_policy["enabled"])
            self.assertEqual(
                contract_complete_implementation_policy["scope_basis"],
                "contract_required_behavior",
            )
            self.assertIn(
                "implementation_source_packet",
                contract_complete_implementation_policy["required_inputs"],
            )
            self.assertIn(
                "pre_handoff_gate_status",
                contract_complete_implementation_policy["required_inputs"],
            )
            self.assertIn(
                "mvp",
                contract_complete_implementation_policy["route_signals"],
            )
            self.assertEqual(
                contract_complete_implementation_policy["escalation"],
                "design_issue_blocker_to_gate_5_6",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "implementation_handoff_required"
                ],
                "yes",
            )
            self.assertEqual(
                contract_complete_implementation_policy["parent_repo_edits_allowed"],
                "no",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "parent_direct_write_exception_required"
                ],
                "yes",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "parent_direct_write_exception"
                ],
                "-",
            )
            self.assertTrue(repo_tool_routing_policy["enabled"])
            self.assertEqual(
                repo_tool_routing_policy["execution_mode"],
                "sequential_by_skill_and_stage",
            )
            self.assertEqual(
                repo_tool_routing_policy["sequence"],
                [
                    "show_skill_packet",
                    "run_required_commands",
                    "run_task_matching_conditional_commands",
                    "run_validation_commands",
                ],
            )
            self.assertIn(
                "$task-routing",
                repo_tool_routing_policy["dynamic_skill_routing"]["candidates"],
            )
            first_tool_route = repo_tool_routing_policy["sequential_tool_routes"][0]
            self.assertEqual(first_tool_route["skill"], "agent-orchestration")
            self.assertIn(
                'python3 tools/agent_tools/route.py --prompt "<user request>" --format json',
                first_tool_route["commands"]["task_matching_conditional_commands"],
            )
            self.assertIn(
                "python3 tools/agent_tools/skill_tool_commands.py check",
                first_tool_route["commands"]["validation_commands"],
            )
            self.assertTrue(default_quality_check_policy["enabled"])
            self.assertEqual(
                default_quality_check_policy["source"],
                "agents/canonical/CODEX_SUBAGENTS.md#Quality Check Default",
            )
            self.assertEqual(
                default_quality_check_policy["wave_sequence_ref"],
                "run.standard_wave_sequence",
            )
            self.assertEqual(
                default_quality_check_policy["stages"],
                ["review_before_edit_handoff", "post_edit_review"],
            )
            self.assertEqual(
                default_quality_check_policy["roles"],
                [
                    "test_designer",
                    "docs_workflow_steward",
                    "python_reviewer",
                    "cpp_reviewer",
                    "change_reviewer",
                ],
            )
            self.assertEqual(
                default_quality_check_policy["codex_agent_types"],
                [
                    "test_designer",
                    "docs_workflow_steward",
                    "python_reviewer",
                    "cpp_reviewer",
                    "diff_triage_reviewer",
                    "reviewer",
                ],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_packs"],
                "active",
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_pack_ids"],
                ["repo_integration_review"],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["auto_language_reviewers"],
                ["cpp_reviewer"],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["manual_specialists"],
                [],
            )
            self.assertIn(
                "tools/bin/agent-canon docs check <changed-markdown-paths>",
                default_quality_check_policy["static_check_commands"],
            )
            self.assertIn(
                "default_quality_check_policy",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertIn(
                "pre_handoff_scope_policy",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertIn(
                "pre_handoff_gate_status",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertIn(
                "user_facing_language_policy",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertIn(
                "contract_complete_implementation_policy",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertIn(
                "repo_tool_routing_policy",
                handoff_context_policy["common_prompt_must_include"],
            )
            self.assertEqual(
                spawn_wave_recommendation["standard_sequence_ref"],
                "run.standard_wave_sequence",
            )
            self.assertEqual(
                spawn_wave_recommendation["initial_wave_agent_types"], first_wave
            )
            self.assertIn(
                "role_instances",
                spawn_wave_recommendation["dynamic_expansion_waves"][0],
            )
            self.assertIn("implementation", role_topology["role_families"])
            self.assertIn("review", role_topology["role_families"])
            self.assertEqual(
                same_role_instances["status"],
                "allowed_with_distinct_packets",
            )
            self.assertEqual(
                same_role_instances["identity_key"],
                "role_type+instance_id",
            )
            self.assertFalse(
                same_role_instances["runtime_threads_are_cardinality_source"]
            )
            self.assertLessEqual(len(first_wave), spawn_budget["active_subagents"])
            self.assert_current_checkout_write_policy(write_scope_policy, 4)
            self.assert_same_role_runtime_policy(delegated_spawn_policy)
            self.assert_initial_wave_execution_gate(report_root / "test-task-start")
            self.assert_abstract_design_prompt_contracts(manifest)

    def test_task_start_plain_fix_activates_subagent_bootstrap(self) -> None:
        """Plain fix prompts should match route.py write-capable handoff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "Fix the failing tests in the repository.",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-plain-fix-route-parity",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap",
                result.stdout,
            )
            self.assertIn(
                "ACTIVE_SKILLS=$agent-orchestration,$subagent-bootstrap",
                result.stdout,
            )
            self.assertIn("DEFERRED_SKILLS=$codex-task-workflow", result.stdout)
            self.assertIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)

    def test_task_start_plain_refactor_activates_subagent_bootstrap(self) -> None:
        """Plain refactor prompts should match route.py write-capable handoff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "Refactor the repository routing helpers.",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-plain-refactor-route-parity",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$refactor-loop,$structure-refactor",
                result.stdout,
            )
            self.assertIn(
                "ACTIVE_SKILLS=$agent-orchestration,$subagent-bootstrap,$refactor-loop,$structure-refactor",
                result.stdout,
            )
            self.assertIn("DEFERRED_SKILLS=$codex-task-workflow", result.stdout)
            self.assertIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)

    def test_task_start_review_only_does_not_activate_subagent_bootstrap(self) -> None:
        """Review-only do-not-edit prompts should not emit implementation handoff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "Use subagents for review only; do not edit files.",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-review-only-no-edit",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap",
                result.stdout,
            )
            self.assertIn("ACTIVE_SKILLS=$agent-orchestration", result.stdout)
            self.assertIn(
                "DEFERRED_SKILLS=$codex-task-workflow,$subagent-bootstrap",
                result.stdout,
            )
            self.assertNotIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)
            self.assertNotIn("PARENT_REPO_EDITS_ALLOWED=no", result.stdout)
            self.assertNotIn("PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes", result.stdout)
            self.assertNotIn("PARENT_DIRECT_WRITE_EXCEPTION=-", result.stdout)
            manifest_text = (
                report_root / "test-review-only-no-edit" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            contract_policy = manifest["run"]["contract_complete_implementation_policy"]
            self.assertNotIn("implementation_handoff_required", contract_policy)
            self.assertNotIn("parent_repo_edits_allowed", contract_policy)
            self.assertNotIn("parent_direct_write_exception_required", contract_policy)
            self.assertNotIn("parent_direct_write_exception", contract_policy)

    def test_academic_reviewers_precede_ship_review_in_dynamic_waves(self) -> None:
        """Task-specific academic reviewers should run before final review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "academic draft",
                    "--task-id",
                    "T10",
                    "--owner",
                    "codex",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--run-id",
                    "test-academic-wave-order",
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            dynamic_waves_match = re.search(
                r"^RECOMMENDED_DYNAMIC_EXPANSION_WAVES=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(dynamic_waves_match)
            dynamic_waves = cast(re.Match[str], dynamic_waves_match).group(1)
            self.assertLess(
                dynamic_waves.index("report_reviewer"),
                dynamic_waves.index("ship_reviewer"),
            )
            self.assertLess(
                dynamic_waves.index("citation_evidence_reviewer"),
                dynamic_waves.index("ship_reviewer"),
            )
            self.assertLess(
                dynamic_waves.index("notation_definition_reviewer"),
                dynamic_waves.index("ship_reviewer"),
            )
            self.assertLess(
                dynamic_waves.index("logic_gap_reviewer"),
                dynamic_waves.index("ship_reviewer"),
            )
            role_instances_match = re.search(
                r"^RECOMMENDED_DYNAMIC_EXPANSION_ROLE_INSTANCES=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(role_instances_match)
            role_instances = cast(re.Match[str], role_instances_match).group(1)
            self.assertIn(
                "research_reviewer:reviewer:research_reviewer_reviewer", role_instances
            )
            self.assertIn(
                "citation_evidence_reviewer:citation_evidence_reviewer:"
                "citation_evidence_reviewer_citation_evidence_reviewer",
                role_instances,
            )
            manifest_text = (
                report_root / "test-academic-wave-order" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            wave_ids = [
                wave["wave_id"]
                for wave in manifest["run"]["spawn_wave_recommendation"][
                    "dynamic_expansion_waves"
                ]
                if any(
                    "citation_evidence_reviewer" in item
                    for item in wave["role_instances"]
                )
            ]
            self.assertEqual(wave_ids, ["WAVE-6"])

    def test_large_refactor_task_start_suggests_refactor_skill(self) -> None:
        """Large refactor should advertise the dedicated refactor skill."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_START_SCRIPT),
                    "--task",
                    "large refactor",
                    "--task-id",
                    "T6",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-large-refactor",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--changed-path",
                    "python/example.py",
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn("RUNTIME_MAX_DEPTH=2", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=10", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=3", result.stdout)
            manifest_text = (
                report_root / "test-large-refactor" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            spawn_budget = manifest["run"]["spawn_budget"]
            write_scope_policy = manifest["run"]["write_scope_policy"]
            self.assertEqual(spawn_budget["active_subagents"], 10)
            self.assertEqual(spawn_budget["max_write_subagents"], 3)
            self.assertEqual(spawn_budget["runtime_max_threads"], 24)
            self.assert_current_checkout_write_policy(write_scope_policy, 3)
            self.assertIn("spawn_budget:", manifest_text)
            self.assertIn("active_subagents: 10", manifest_text)
            self.assertIn("max_write_subagents: 3", manifest_text)
            self.assertIn(
                "max_write_subagents_scope: 'write-capable subagents only'",
                manifest_text,
            )
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$refactor-loop",
                result.stdout,
            )
            self.assertIn(
                "ACTIVE_SKILLS=$agent-orchestration,$subagent-bootstrap,$refactor-loop",
                result.stdout,
            )
            self.assertIn(
                "DEFERRED_SKILLS=$codex-task-workflow",
                result.stdout,
            )

    def test_bootstrap_defaults_report_root_to_workspace_reports_agents(self) -> None:
        """bootstrap_agent_run should default report output under the workspace root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            run_id = "test-default-workspace-report-root"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workspace-local report root",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(workspace_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=skipped_by_flag", result.stdout)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            report_dir = workspace_root / "reports" / "agents" / run_id
            self.assertIn(f"REPORT_DIR={report_dir}", result.stdout)
            self.assertIn(
                f"TASK_AUTHORITY={report_dir / 'task_authority.yaml'}", result.stdout
            )
            self.assertTrue(report_dir.is_dir())
            self.assertTrue((report_dir / "work_log.md").is_file())
            self.assertTrue((report_dir / "task_authority.yaml").is_file())
            self.assertTrue((report_dir / "task_authority.yaml.sha256").is_file())
            self.assertTrue(
                (workspace_root / "reports" / "agents" / ".active_run.sha256").is_file()
            )
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/REVIEW_PROCESS.md", result.stdout)
            self.assertIn("/notes/guardrails/README.md", result.stdout)
            self.assertNotIn("/docker/README.md", result.stdout)
            self.assertIn(
                "/agents/workflows/implementation-waterfall-workflow.md", result.stdout
            )
            self.assertIn("DESIGN_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("IMPLEMENTATION_DOCUMENT_PACKET=", result.stdout)
            manifest_text = (report_dir / "team_manifest.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("cross_cutting_document_packet:", manifest_text)
            self.assertIn("document_packet:", manifest_text)
            self.assertNotIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("must_cite_before_edit: true", manifest_text)
            self.assertIn(str(report_dir / "design_brief.md"), manifest_text)
            self.assertIn("/documents/REVIEW_PROCESS.md", manifest_text)
            self.assertIn("/notes/guardrails/README.md", manifest_text)
            self.assertNotIn("/docker/README.md", manifest_text)
            self.assertIn(
                "/agents/workflows/implementation-waterfall-workflow.md", manifest_text
            )

    def test_bootstrap_custom_report_root_writes_active_run_baseline_there(
        self,
    ) -> None:
        """Custom report-root mode should baseline the active pointer it writes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "custom-reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            run_id = "test-custom-report-root"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workspace-local report root",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((report_root / ".active_run").is_file())
            self.assertTrue((report_root / ".active_run.sha256").is_file())
            self.assertFalse(
                (workspace_root / "reports" / "agents" / ".active_run.sha256").exists()
            )
            self.assertTrue(
                (report_root / run_id / "task_authority.yaml.sha256").is_file()
            )

    def test_bootstrap_emits_mechanical_spawn_budget_for_task(self) -> None:
        """bootstrap_agent_run should emit runtime and workflow spawn limits for machine use."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "mechanical spawn budget",
                    "--task-id",
                    "T8",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-bootstrap-spawn-budget",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RUNTIME_MAX_THREADS=24", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("WORKFLOW_ACTIVE_SPAWN_BUDGET=10", result.stdout)
            self.assertIn("WORKFLOW_MAX_WRITE_SUBAGENTS=2", result.stdout)
            self.assertIn("INITIAL_THREE_AGENT_INTAKE_IS_TOTAL_CAP=no", result.stdout)
            self.assertIn("DYNAMIC_SUBAGENT_EXPANSION=allowed", result.stdout)
            self.assertIn(
                "DYNAMIC_SUBAGENT_EXPANSION_MONITOR=workflow_monitoring.md#Behavior Events",
                result.stdout,
            )
            self.assertIn(
                "SUBAGENT_WAVE_RECORD_COMMAND=python3 tools/agent_tools/workflow_monitor.py --report-dir",
                result.stdout,
            )
            self.assertIn("--subagent-wave", result.stdout)
            self.assertIn(
                "PARENT_WAVE_EXECUTION_GATE=required_before_implementation",
                result.stdout,
            )
            self.assertIn(
                "PARENT_WAVE_EXECUTION_GATE_STATUS=blocked_authority_required",
                result.stdout,
            )
            self.assertIn("RECOMMENDED_INITIAL_SUBAGENT_WAVE=", result.stdout)
            self.assertIn("RECOMMENDED_DYNAMIC_EXPANSION_WAVES=", result.stdout)
            self.assertIn(
                "SAME_ROLE_SUBAGENT_INSTANCES=allowed_with_distinct_packets",
                result.stdout,
            )
            self.assertIn(
                "SAME_ROLE_SUBAGENT_INSTANCE_KEY=role_type+instance_id",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_SCOPE_POLICY=discovery_before_handoff_scope",
                result.stdout,
            )
            self.assertIn(
                "PRE_HANDOFF_SCOPE_STATUS=seed_then_expand_before_handoff",
                result.stdout,
            )
            self.assertNotIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)
            self.assertNotIn("PARENT_REPO_EDITS_ALLOWED=no", result.stdout)
            self.assertNotIn("PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes", result.stdout)
            self.assertNotIn("PARENT_DIRECT_WRITE_EXCEPTION=-", result.stdout)
            self.assertIn("DEFAULT_QUALITY_CHECKS=enabled", result.stdout)
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_ROLES=test_designer,docs_workflow_steward,python_reviewer,change_reviewer",
                result.stdout,
            )
            self.assertIn(
                "DEFAULT_QUALITY_CHECK_DEFAULT_REVIEW_PACKS=-",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_POLICY=selected_skill_command_packets",
                result.stdout,
            )
            self.assertIn(
                "REPO_TOOL_ROUTING_SEQUENCE=show_skill_packet,run_required_commands,run_task_matching_conditional_commands,run_validation_commands",
                result.stdout,
            )
            self.assertIn(
                "REPO_DYNAMIC_SKILL_ROUTING_NEXT=add_skill_then_regenerate_repo_tool_routes",
                result.stdout,
            )
            self.assertIn("TASK_ID_ROUTE_STATUS=explicit", result.stdout)
            self.assertIn("PLANNED_ACTIVE_ROLE_COUNT=", result.stdout)
            self.assertIn(
                "SUBAGENT_FANOUT_EXPECTATION=record_skipped_roles_when_below_family_default",
                result.stdout,
            )
            self.assertIn("IMPLEMENTATION_SURFACE_ROUTE_STATUS=pending", result.stdout)
            self.assertIn(
                "TOOL_REUSE_LEDGER_STATUS=required_before_custom_implementation",
                result.stdout,
            )
            self.assertIn("PRE_EDIT_REJECTION_PREDICTION_STATUS=pending", result.stdout)
            self.assertIn("AGENT_REPORT_COLLECTION_STATUS=available", result.stdout)
            self.assertIn(
                "AGENT_REPORT_COLLECTION_STATUS_COMMAND=python3 tools/agent_tools/runtime_log_archive_git.py status",
                result.stdout,
            )
            self.assertIn(
                "AGENT_REPORT_ARCHIVE_RUN_COMMAND=python3 tools/agent_tools/runtime_log_archive_git.py "
                "archive-agent-report --report-dir",
                result.stdout,
            )
            manifest_text = (
                report_root / "test-bootstrap-spawn-budget" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            spawn_budget = manifest["run"]["spawn_budget"]
            standard_wave_sequence = manifest["run"]["standard_wave_sequence"]
            pre_handoff_scope_policy = manifest["run"]["pre_handoff_scope_policy"]
            default_quality_check_policy = manifest["run"][
                "default_quality_check_policy"
            ]
            delegated_spawn_policy = manifest["run"]["delegated_spawn_policy"]
            validation_failure_policy = delegated_spawn_policy[
                "validation_failure_triage_policy"
            ]
            spawn_wave_recommendation = manifest["run"]["spawn_wave_recommendation"]
            role_topology = spawn_wave_recommendation["role_topology"]
            same_role_instances = role_topology["same_role_parallel_instances"]
            write_scope_policy = manifest["run"]["write_scope_policy"]
            handoff_context_policy = manifest["run"]["handoff_context_policy"]
            implementation_gate_defaults = manifest["run"][
                "implementation_gate_defaults"
            ]
            agent_report_collection = manifest["run"]["agent_report_collection"]
            repo_tool_routing_policy = manifest["run"]["repo_tool_routing_policy"]
            self.assertEqual(spawn_budget["active_subagents"], 10)
            self.assertEqual(spawn_budget["max_write_subagents"], 2)
            self.assertGreater(
                spawn_budget["active_subagents"],
                spawn_budget["max_write_subagents"],
            )
            self.assertEqual(spawn_budget["runtime_max_threads"], 24)
            self.assertEqual(spawn_budget["runtime_max_depth"], 2)
            self.assertFalse(spawn_budget["initial_three_agent_intake_is_total_cap"])
            self.assertLessEqual(
                spawn_budget["active_subagents"],
                spawn_budget["runtime_max_threads"],
            )
            planned_match = re.search(
                r"^PLANNED_ACTIVE_ROLE_COUNT=(\d+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(planned_match)
            self.assertEqual(
                int(cast(re.Match[str], planned_match).group(1)),
                len(manifest["roles"]),
            )
            self.assertIn("workflow_families[].spawn_budget", spawn_budget["source"])
            self.assertEqual(
                same_role_instances["status"],
                "allowed_with_distinct_packets",
            )
            self.assertEqual(
                same_role_instances["identity_key"],
                "role_type+instance_id",
            )
            self.assertFalse(
                same_role_instances["runtime_threads_are_cardinality_source"]
            )
            self.assertIn("implementation", role_topology["role_families"])
            self.assertIn("review", role_topology["role_families"])
            self.assertEqual(
                delegated_spawn_policy["dynamic_mid_task_spawn"], "allowed"
            )
            self.assertEqual(
                standard_wave_sequence["stages"], ["plan", "review", "edit"]
            )
            self.assertEqual(
                pre_handoff_scope_policy["status"],
                "seed_then_expand_before_handoff",
            )
            self.assertEqual(
                write_scope_policy["scope_source_ref"],
                "run.pre_handoff_scope_policy",
            )
            self.assertEqual(
                write_scope_policy["handoff_scope_status"],
                "seed_then_expand_before_handoff",
            )
            self.assertEqual(
                default_quality_check_policy["roles"],
                [
                    "test_designer",
                    "docs_workflow_steward",
                    "python_reviewer",
                    "change_reviewer",
                ],
            )
            self.assertEqual(
                default_quality_check_policy["codex_agent_types"],
                [
                    "test_designer",
                    "docs_workflow_steward",
                    "python_reviewer",
                    "cpp_reviewer",
                    "diff_triage_reviewer",
                    "reviewer",
                ],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_packs"],
                "active",
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_pack_ids"],
                [],
            )
            self.assertEqual(
                spawn_wave_recommendation["standard_sequence_ref"],
                "run.standard_wave_sequence",
            )
            self.assertEqual(
                delegated_spawn_policy["delegated_child_spawn"],
                "allowed_with_bounded_packet",
            )
            self.assertIn(
                "workflow_monitor.py",
                delegated_spawn_policy["wave_record_command"],
            )
            self.assertIn(
                "--subagent-wave",
                delegated_spawn_policy["wave_record_command"],
            )
            self.assert_same_role_runtime_policy(delegated_spawn_policy)
            self.assertIn(
                "validation_failure_requires_parallel_triage",
                delegated_spawn_policy["expansion_triggers"],
            )
            self.assertEqual(
                validation_failure_policy["trigger"],
                "validation_failure_requires_parallel_triage",
            )
            self.assertEqual(
                validation_failure_policy["triage_write_scope"],
                "read_only_until_cause_identified",
            )
            self.assertEqual(
                validation_failure_policy["repair_required_fields"],
                [
                    "failing_contract",
                    "observation_level",
                    "cause_classification",
                    "intent_preservation",
                    "evidence",
                ],
            )
            self.assertIn(
                "repair_same_intent",
                validation_failure_policy["intent_preservation_values"],
            )
            self.assertIn(
                "schedule.md Agent Wave Ledger row with spawn_authority, budget, runtime ceilings, paths, validation_route, review_gate, handoff_artifacts, and delegated policy ref",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                (
                    "validation_failure_requires_parallel_triage waves stay read-only "
                    "until failing_contract, observation_level, cause_classification, "
                    "intent_preservation, and evidence are recorded for same-intent repair "
                    "or escalation"
                ),
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "run delegated_spawn_policy.wave_record_command after any actual parent or delegated child spawn; delegated child waves must include remaining_spawn_budget",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "plan artifact, review gate decision, and edit handoff evidence following run.standard_wave_sequence",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "include run.default_quality_check_policy in review and edit handoff packets",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "include run.pre_handoff_scope_policy and dependency-expanded handoff scope evidence",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                (
                    "include run.pre_handoff_gate_status before implementation or "
                    "write-capable handoff when design_brief.md exists"
                ),
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "include run.repo_tool_routing_policy selected-skill command sequence, dynamic skill candidates, and tool evidence in every handoff packet",
                delegated_spawn_policy["required_before_spawn"],
            )
            self.assertIn(
                "tool_route", delegated_spawn_policy["handoff_required_fields"]
            )
            self.assertIn(
                "tool_commands", delegated_spawn_policy["handoff_required_fields"]
            )
            self.assertIn(
                "tool_evidence", delegated_spawn_policy["handoff_required_fields"]
            )
            self.assertIn(
                "plan_artifact", delegated_spawn_policy["handoff_required_fields"]
            )
            self.assertIn(
                "edit_handoff", delegated_spawn_policy["handoff_required_fields"]
            )
            self.assertIn(
                "pre_handoff_gate_status",
                delegated_spawn_policy["handoff_required_fields"],
            )
            first_wave = spawn_wave_recommendation["initial_wave_agent_types"]
            self.assertEqual(
                first_wave,
                ["requirements_organizer", "explorer", "execution_planner"],
            )
            self.assertLessEqual(len(first_wave), spawn_budget["active_subagents"])
            self.assertIn("requirements_organizer", first_wave)
            self.assert_current_checkout_write_policy(write_scope_policy, 2)
            self.assertIn("spawn_budget:", manifest_text)
            self.assertIn("active_subagents: 10", manifest_text)
            self.assertIn("max_write_subagents: 2", manifest_text)
            self.assertIn("runtime_max_threads: 24", manifest_text)
            self.assertIn("runtime_max_depth: 2", manifest_text)
            self.assertIn("standard_wave_sequence:", manifest_text)
            self.assertIn(
                "STANDARD_AGENT_WAVE_SEQUENCE=plan,review,edit", result.stdout
            )
            self.assertIn("spawn_wave_recommendation:", manifest_text)
            self.assertIn("delegated_spawn_policy:", manifest_text)
            self.assertIn(
                "max_write_subagents_scope: 'write-capable subagents only'",
                manifest_text,
            )
            self.assertIn("write_scope_policy:", manifest_text)
            self.assertIn("parent_managed: true", manifest_text)
            self.assertIn("workflow_family:", manifest_text)
            self.assertIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("subagent_lifecycle_policy:", manifest_text)
            self.assertIn("fresh_subagents_required: true", manifest_text)
            self.assertIn("reuse_for_new_task: forbidden", manifest_text)
            self.assertIn("previous_task_subagent_reuse: forbidden", manifest_text)
            lifecycle_policy = manifest["run"]["subagent_lifecycle_policy"]
            self.assertEqual(
                lifecycle_policy["mid_task_user_input_policy"],
                "parent_checkpoint_then_route_delta",
            )
            self.assertEqual(
                lifecycle_policy["same_task_delta_reuse"],
                "allowed_with_updated_packet",
            )
            self.assertEqual(
                lifecycle_policy["scope_change_reuse"],
                "forbidden_spawn_fresh_wave",
            )
            self.assertEqual(
                lifecycle_policy["new_task_reuse"],
                "forbidden_spawn_fresh_run",
            )
            common_prompt_fields = handoff_context_policy["common_prompt_must_include"]
            self.assertIn("context_artifacts", common_prompt_fields)
            self.assertIn("allowed_paths", common_prompt_fields)
            self.assertIn("do_not_read", common_prompt_fields)
            self.assertIn("expected_output_schema", common_prompt_fields)
            self.assertIn("pre_handoff_gate_status", common_prompt_fields)
            pre_handoff_gate_status = manifest["run"]["pre_handoff_gate_status"]
            self.assertEqual(
                pre_handoff_gate_status["status"],
                "pending_design_review_gate_check",
            )
            self.assertIn(
                "design_review_decision_approve",
                pre_handoff_gate_status["required_evidence"],
            )
            for role in cast("list[object]", manifest["roles"]):
                role_map = cast("dict[str, object]", role)
                prompt_contract = cast(
                    "dict[str, object]", role_map["prompt_contract"]
                )
                self.assertEqual(
                    prompt_contract["common_prompt_must_include_ref"],
                    "run.handoff_context_policy.common_prompt_must_include",
                )
            self.assertEqual(
                repo_tool_routing_policy["route_basis"],
                "selected_public_skills",
            )
            self.assertEqual(
                repo_tool_routing_policy["dynamic_skill_routing"]["next"],
                "add_skill_then_regenerate_repo_tool_routes",
            )
            self.assertIn(
                "$task-routing",
                repo_tool_routing_policy["dynamic_skill_routing"]["candidates"],
            )
            self.assertEqual(
                repo_tool_routing_policy["sequential_tool_routes"][0]["commands"][
                    "show_skill_packet"
                ],
                [
                    "python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text"
                ],
            )
            self.assertEqual(
                implementation_gate_defaults["tool_reuse_ledger_status"],
                "required_before_custom_implementation",
            )
            self.assertEqual(
                implementation_gate_defaults["pre_edit_rejection_prediction_status"],
                "pending",
            )
            self.assertEqual(
                agent_report_collection["status_command"],
                "python3 tools/agent_tools/runtime_log_archive_git.py status",
            )
            self.assertIn(
                "archive-agent-report --report-dir",
                agent_report_collection["archive_current_run_command"],
            )
            self.assertEqual(
                agent_report_collection["archive_index"],
                ".agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl",
            )
            self.assert_initial_wave_execution_gate(
                report_root / "test-bootstrap-spawn-budget"
            )

    def test_task_catalog_workflow_families_define_role_topology(self) -> None:
        """Every workflow family should define role topology separately from thread budget."""
        catalog = yaml.safe_load(
            (PROJECT_ROOT / "agents" / "task_catalog.yaml").read_text(encoding="utf-8")
        )

        for workflow_family in catalog["workflow_families"]:
            with self.subTest(workflow_family=workflow_family["id"]):
                role_topology = workflow_family["role_topology"]
                same_role_instances = role_topology["same_role_parallel_instances"]
                self.assertIn("role_families", role_topology)
                self.assertIn("implementation", role_topology["role_families"])
                self.assertIn("review", role_topology["role_families"])
                self.assertEqual(
                    same_role_instances["status"],
                    "allowed_with_distinct_packets",
                )
                self.assertEqual(
                    same_role_instances["identity_key"],
                    "role_type+instance_id",
                )
                self.assertFalse(
                    same_role_instances["runtime_threads_are_cardinality_source"]
                )

    def test_bootstrap_warns_when_multi_agent_task_lacks_task_id(self) -> None:
        """A repo-wide bootstrap without --task-id should not silently lose fan-out evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "review agent routing with multiple agents and implementation repair",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-bootstrap-missing-task-id",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("START_DECLARATION=workflow=Unspecified", result.stdout)
            self.assertIn("TASK_ID_ROUTE_STATUS=missing", result.stdout)
            self.assertIn("TASK_ID_ROUTE_REQUIRED_FOR_MULTI_AGENT=yes", result.stdout)
            self.assertIn("TASK_ID_ROUTE_RECOMMENDED_TASK_IDS=T11,T12", result.stdout)
            self.assertIn(
                "SUBAGENT_FANOUT_EXPECTATION=blocked_until_task_id_or_explicit_family",
                result.stdout,
            )
            manifest_text = (
                report_root / "test-bootstrap-missing-task-id" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            user_facing_language_policy = manifest["run"]["user_facing_language_policy"]
            contract_complete_implementation_policy = manifest["run"][
                "contract_complete_implementation_policy"
            ]
            default_quality_check_policy = manifest["run"][
                "default_quality_check_policy"
            ]
            self.assertIn("prompt_contract:", manifest_text)
            self.assertIn("subagent_lifecycle_policy", manifest_text)
            self.assertEqual(user_facing_language_policy["language"], "ja")
            self.assertEqual(
                contract_complete_implementation_policy["scope_basis"],
                "contract_required_behavior",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "implementation_handoff_required"
                ],
                "yes",
            )
            self.assertEqual(
                contract_complete_implementation_policy["parent_repo_edits_allowed"],
                "no",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "parent_direct_write_exception_required"
                ],
                "yes",
            )
            self.assertEqual(
                contract_complete_implementation_policy[
                    "parent_direct_write_exception"
                ],
                "-",
            )
            self.assertEqual(
                default_quality_check_policy["roles"],
                ["test_designer", "change_reviewer"],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["task_default_specialists"],
                [],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["auto_language_reviewers"],
                [],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_pack_ids"],
                [],
            )

    def test_all_task_ids_bootstrap_with_prompt_packet(self) -> None:
        """Every catalog task should create a workflow-specific subagent prompt packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)

            for task_id in [f"T{index}" for index in range(1, 14)]:
                run_id = f"test-prompt-{task_id.lower()}"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(BOOTSTRAP_SCRIPT),
                        "--task",
                        f"prompt packet {task_id}",
                        "--task-id",
                        task_id,
                        "--owner",
                        "codex",
                        "--run-id",
                        run_id,
                        "--workspace-root",
                        str(workspace_root),
                        "--report-root",
                        str(report_root),
                        "--skip-agent-canon-preflight",
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                    result.stdout,
                )
                manifest_text = (report_root / run_id / "team_manifest.yaml").read_text(
                    encoding="utf-8",
                )
                self.assertIn("subagent_prompt_packet:", manifest_text)
                self.assertIn("prompt_preamble:", manifest_text)
                self.assertIn("workflow_focus:", manifest_text)
                self.assertIn("reviewer_prompt:", manifest_text)
                self.assertIn("subagent_lifecycle_policy:", manifest_text)
                self.assertIn("mid_task_user_input_policy:", manifest_text)
                self.assertIn("closeout_gate_key: subagents_closed", manifest_text)
                self.assertIn(
                    "subagent_startup_route: 'agents/internal-routines/subagent-startup.md'",
                    manifest_text,
                )
                self.assertIn("prompt_contract:", manifest_text)
                manifest = yaml.safe_load(manifest_text)
                subagent_prompt_packet = manifest["run"]["subagent_prompt_packet"]
                self.assertEqual(
                    subagent_prompt_packet["subagent_startup_route"],
                    "agents/internal-routines/subagent-startup.md",
                )
                self.assertIn(
                    "agents/internal-routines/subagent-startup.md",
                    subagent_prompt_packet["internal_skill_routes"],
                )
                self.assert_role_prompt_includes(
                    manifest,
                    "implementer",
                    {"abstract_design_frame", "design_to_implementation_trace"},
                )

    def test_worktree_start_rejects_branch_kickoff(self) -> None:
        """worktree_start.py is cleanup-only and must not create branch worktrees."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init"], cwd=workspace_root, check=True, capture_output=True
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(WORKTREE_START_SCRIPT),
                    "feature/demo",
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cleanup diagnostic only", result.stderr)
            self.assertFalse((workspace_root / ".worktrees").exists())

    def test_setup_worktree_wrapper_rejects_legacy_creation(self) -> None:
        """setup_worktree.sh should warn and stop instead of creating worktrees."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init"], cwd=workspace_root, check=True, capture_output=True
            )

            result = subprocess.run(
                [
                    "bash",
                    str(SETUP_WORKTREE_SCRIPT),
                    "feature/demo",
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("SETUP_WORKTREE_FORWARDER=deprecated", result.stderr)
            self.assertIn("CALLER_CHAIN=", result.stderr)
            self.assertFalse((workspace_root / ".worktrees").exists())

    def test_task_close_rejects_locked_bundle(self) -> None:
        """task_close should fail while closeout is still locked."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout lock smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-task-close-locked",
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_root / "test-task-close-locked"),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("CLOSEOUT_BLOCKERS=", result.stdout)

    def test_task_close_accepts_unlocked_bundle(self) -> None:
        """task_close should pass after verification and closeout statuses are resolved."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-ready"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout ready smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout ready smoke",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- tool_warnings_resolved: yes",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_final_review(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_accepts_profile_selected_targeted_static_analysis(self) -> None:
        """task_close should allow targeted static analysis selected by the risk profile."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-targeted-static-analysis"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_text = closeout_path.read_text(encoding="utf-8")
            closeout_text = closeout_text.replace(
                "- repo_wide_static_analysis_complete: yes",
                "- repo_wide_static_analysis_complete: profile_selected",
            )
            closeout_text = closeout_text.replace(
                "- make_ci_status: pass",
                "- make_ci_status: targeted",
            )
            closeout_text = closeout_text.replace(
                "- mechanical_loop_static_analysis_status: pass",
                "- mechanical_loop_static_analysis_status: targeted",
            )
            closeout_path.write_text(closeout_text, encoding="utf-8")
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("MAKE_CI_STATUS=targeted", result.stdout)

    def test_task_close_rejects_pending_profile_selected_static_analysis(self) -> None:
        """task_close should not treat targeted routing as a waiver for pending checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-pending-targeted-static-analysis"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_text = closeout_path.read_text(encoding="utf-8")
            closeout_text = closeout_text.replace(
                "- repo_wide_static_analysis_complete: yes",
                "- repo_wide_static_analysis_complete: profile_selected",
            )
            closeout_text = closeout_text.replace(
                "- make_ci_status: pass",
                "- make_ci_status: targeted",
            )
            closeout_text = closeout_text.replace(
                "- mechanical_loop_static_analysis_status: pass",
                "- mechanical_loop_static_analysis_status: pending",
            )
            closeout_path.write_text(closeout_text, encoding="utf-8")
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("mechanical_loop_static_analysis_status", result.stdout)

    def test_task_close_rejects_open_tool_warning(self) -> None:
        """task_close should fail while workflow monitoring has open tool warnings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-open-tool-warning"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)
            (report_dir / "workflow_monitoring.md").write_text(
                "\n".join(
                    [
                        "# Workflow Monitoring",
                        "",
                        "## Tool Warnings",
                        "",
                        "- tool_warnings_status: resolved",
                        (
                            "- tool_warning=recorded warning_id=W1 "
                            "source_tool=legacy-forwarder severity=warning "
                            "status=open message=deprecated_wrapper "
                            "repair_command=agent-canon_cli"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("workflow_tool_warnings_closed", result.stdout)
            self.assertIn("tool warning remains open: W1", result.stdout)

    def test_task_close_defaults_report_root_to_workspace_cwd(self) -> None:
        """task_close --run-id should resolve reports/agents under the current workspace."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Task Close Test"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "task-close@example.invalid"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "init"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-workspace-default"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workspace closeout ready",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(workspace_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report_dir = workspace_root / "reports" / "agents" / run_id
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=workspace closeout ready",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- tool_warnings_resolved: yes",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(workspace=workspace_root),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_final_review(report_dir)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("ALL_PLANNED_CHUNKS_COMPLETE=yes", result.stdout)
            self.assertIn("OVERALL_DELIVERY_COMPLETE=yes", result.stdout)
            self.assertIn("SPEC_PRODUCT_COVERAGE_COMPLETE=yes", result.stdout)
            self.assertIn("REVIEW_FINDINGS_INTEGRATED=yes", result.stdout)
            self.assertIn("POST_FIX_FULL_REVIEW_COMPLETE=yes", result.stdout)
            self.assertIn("MECHANICAL_COMPLETION_LOOP_COMPLETE=yes", result.stdout)
            self.assertIn("SUBAGENTS_CLOSED=yes", result.stdout)
            self.assertIn("DIFF_CHECK_AGENT_COMPLETE=yes", result.stdout)
            self.assertIn("CANONICAL_TREE_HEAD_COMPLETE=yes", result.stdout)
            self.assertIn("REQUEST_CONTRACT_RESOLVED=yes", result.stdout)

    def test_task_close_rejects_placeholder_final_review(self) -> None:
        """task_close should not accept an untouched final_review.md template."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-placeholder-final-review"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)
            (report_dir / "final_review.md").write_text(
                "# Final Review\n\n## Decision\n\n<!-- reviewer decision -->\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("final_review_artifact_complete", result.stdout)

    def test_task_close_rejects_negative_final_review_decision_text(self) -> None:
        """Final review decisions containing approve as a substring must not pass."""
        cases = {
            "revise-do-not-approve": "revise: do not approve",
            "not-approved": "not approved",
        }
        for case_id, decision in cases.items():
            with (
                self.subTest(case_id=case_id),
                tempfile.TemporaryDirectory() as tmp_dir,
            ):
                report_root = Path(tmp_dir) / "reports"
                run_id = f"test-task-close-negative-final-review-{case_id}"
                report_dir = report_root / run_id
                report_dir.mkdir(parents=True, exist_ok=True)
                write_ready_closeout_bundle(report_dir, run_id)
                write_ready_diff_check_artifact(report_dir)
                (report_dir / "final_review.md").write_text(
                    f"# Final Review\n\n## Decision\n\n{decision}\n",
                    encoding="utf-8",
                )

                result = subprocess.run(
                    [
                        sys.executable,
                        str(TASK_CLOSE_SCRIPT),
                        "--report-dir",
                        str(report_dir),
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("CLOSEOUT_READY=no", result.stdout)
                self.assertIn("final_review.md:decision_not_approve", result.stdout)

    def test_task_close_rejects_stale_inactive_report_bundle(self) -> None:
        """task_close should reject a report bundle when .active_run points elsewhere."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-inactive-run"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_root / ".active_run").write_text("another-run\n", encoding="utf-8")
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ACTIVE_RUN=another-run", result.stdout)
            self.assertIn("REPORT_ACTIVE_RUN_MATCH=no", result.stdout)
            self.assertIn("report_active_run_match", result.stdout)

    def test_task_close_rejects_missing_active_run_marker(self) -> None:
        """task_close should reject a report bundle when .active_run is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-active-run"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)
            (report_root / ".active_run").unlink()

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ACTIVE_RUN=", result.stdout)
            self.assertIn("REPORT_ACTIVE_RUN_MATCH=no", result.stdout)
            self.assertIn("report_active_run_match", result.stdout)

    def test_task_close_rejects_failed_agent_canon_latest_status(self) -> None:
        """task_close should require an explicit pass latest-route status."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-failed-agent-canon-latest-status"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- agent_canon_latest_status: pass",
                    "- agent_canon_latest_status: fail",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("AGENT_CANON_LATEST_STATUS=fail", result.stdout)
            self.assertIn("agent_canon_latest_status", result.stdout)

    def test_task_close_rejects_missing_mechanical_loop_or_diff_check(self) -> None:
        """task_close should fail when parent-only closeout skips the final diff loop."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-diff-loop"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_text = closeout_path.read_text(encoding="utf-8")
            closeout_path.write_text(
                closeout_text.replace(
                    "- mechanical_completion_loop_complete: yes\n"
                    "- subagents_closed: yes\n"
                    "- diff_check_agent_complete: yes",
                    "- mechanical_completion_loop_complete: no\n"
                    "- subagents_closed: no\n"
                    "- diff_check_agent_complete: no",
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("mechanical_completion_loop_complete", result.stdout)
            self.assertIn("diff_check_agent_complete", result.stdout)

    def test_task_close_rejects_missing_subagent_lifecycle_evidence(self) -> None:
        """task_close should fail when run-local subagent close evidence is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-subagent-lifecycle"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8")
                .replace("- subagents_closed: yes", "- subagents_closed: no")
                .replace(
                    "- close_agent_evidence: parent_direct_no_open_subagents",
                    "- close_agent_evidence: none",
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("subagents_closed", result.stdout)
            self.assertIn("close_agent_evidence", result.stdout)

    def test_task_close_rejects_policy_value_as_observed_subagent_reuse(self) -> None:
        """task_close should require observed prior-task subagent reuse to be none."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-policy-value-is-not-observation"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- previous_task_subagent_reuse: none",
                    "- previous_task_subagent_reuse: forbidden",
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("previous_task_subagent_reuse", result.stdout)

    def test_task_close_rejects_missing_diff_check_artifact(self) -> None:
        """task_close should fail when diff-check evidence points to a missing artifact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-diff-artifact"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("diff_check_artifact_exists", result.stdout)

    def test_task_close_rejects_invalid_diff_check_artifact_fields(self) -> None:
        """task_close should fail when the diff-check artifact is not an approval."""
        cases = [
            ("role-mismatch", {"role": "project_reviewer"}, "diff_check_artifact_role"),
            ("decision-revise", {"decision": "revise"}, "diff_check_artifact_decision"),
            (
                "diff-ref-mismatch",
                {"diff_ref": "old-head"},
                "diff_check_artifact_latest_diff_ref",
            ),
            ("read-only-no", {"read_only": "no"}, "diff_check_artifact_read_only"),
            (
                "independent-no",
                {"independent": "no"},
                "diff_check_artifact_independent",
            ),
            (
                "findings-unresolved",
                {"findings_status": "unresolved"},
                "diff_check_artifact_findings_status",
            ),
        ]
        for case_id, artifact_kwargs, expected_blocker in cases:
            with self.subTest(case_id=case_id):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    report_root = Path(tmp_dir) / "reports"
                    run_id = f"test-task-close-invalid-diff-artifact-{case_id}"
                    report_dir = report_root / run_id
                    report_dir.mkdir(parents=True, exist_ok=True)
                    write_ready_closeout_bundle(report_dir, run_id)
                    write_ready_diff_check_artifact(
                        report_dir,
                        role=artifact_kwargs.get("role", "reviewer"),
                        decision=artifact_kwargs.get("decision", "approve"),
                        diff_ref=artifact_kwargs.get("diff_ref"),
                        read_only=artifact_kwargs.get("read_only", "yes"),
                        independent=artifact_kwargs.get("independent", "yes"),
                        findings_status=artifact_kwargs.get("findings_status", "none"),
                    )

                    result = subprocess.run(
                        [
                            sys.executable,
                            str(TASK_CLOSE_SCRIPT),
                            "--report-dir",
                            str(report_dir),
                        ],
                        cwd=PROJECT_ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("CLOSEOUT_READY=no", result.stdout)
                    self.assertIn(expected_blocker, result.stdout)

    def test_task_close_rejects_incomplete_mechanical_loop_evidence(self) -> None:
        """task_close should fail when mechanical loop structured evidence is incomplete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-incomplete-mechanical-loop"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- mechanical_loop_validation_status: pass",
                    "- mechanical_loop_validation_status: missing",
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("mechanical_loop_validation_status", result.stdout)

    def test_task_close_rejects_markdown_change_without_structure_evidence(
        self,
    ) -> None:
        """Changed source Markdown paths require document structure evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace_root, check=True)
            (workspace_root / "README.md").write_text("# Seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed markdown",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / "README.md").write_text(
                "# Seed\n\nUpdated.\n",
                encoding="utf-8",
            )
            run_id = "test-task-close-doc-structure"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- structure_contract: skipped: fixture format-only route",
                    "- structure_contract: missing",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DOCUMENT_STRUCTURE_REQUIRED=yes", result.stdout)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=no", result.stdout)
            self.assertIn("document_structure_evidence", result.stdout)

    def test_task_close_rejects_markdown_change_with_mismatched_structure_paths(
        self,
    ) -> None:
        """Document structure evidence must cover the changed Markdown paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace_root, check=True)
            (workspace_root / "README.md").write_text("# Seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed markdown",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / "README.md").write_text(
                "# Seed\n\nUpdated.\n",
                encoding="utf-8",
            )
            run_id = "test-task-close-doc-structure-paths"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- document_structure_paths: README.md",
                    "- document_structure_paths: docs/other.md",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "DOCUMENT_STRUCTURE_CHANGED_MARKDOWN=README.md", result.stdout
            )
            self.assertIn("document_structure_paths_recorded", result.stdout)

    def test_task_close_rejects_markdown_change_without_split_decision(self) -> None:
        """Document structure closeout must include split decision evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace_root, check=True)
            (workspace_root / "README.md").write_text("# Seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed markdown",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / "README.md").write_text(
                "# Seed\n\nUpdated.\n",
                encoding="utf-8",
            )
            run_id = "test-task-close-doc-split-decision"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- document_split_decision: "
                    "not_applicable:format-only: fixture closeout bundle",
                    "- document_split_decision: missing",
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DOCUMENT_SPLIT_DECISION_EVIDENCE=no", result.stdout)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=no", result.stdout)
            self.assertIn("document_split_decision_evidence", result.stdout)

    def test_task_close_rejects_complete_structure_route_with_skip_contract(
        self,
    ) -> None:
        """A complete document structure route requires a real structure contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q"], cwd=workspace_root, check=True)
            (workspace_root / "README.md").write_text("# Seed\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed markdown",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / "README.md").write_text(
                "# Seed\n\nUpdated.\n",
                encoding="utf-8",
            )
            run_id = "test-task-close-doc-structure-contract"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            closeout_path = report_dir / "closeout_gate.md"
            text = closeout_path.read_text(encoding="utf-8")
            text = text.replace(
                "- document_structure_status: skipped",
                "- document_structure_status: complete",
            )
            text = text.replace(
                "- structure_planning: not_applicable",
                "- structure_planning: complete",
            )
            text = text.replace(
                "- prose_graph: not_applicable",
                "- prose_graph: complete",
            )
            closeout_path.write_text(text, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DOCUMENT_STRUCTURE_STATUS=complete", result.stdout)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=no", result.stdout)

    def test_task_close_rejects_non_git_workspace(self) -> None:
        """task_close should fail closed when it cannot resolve the current diff ref."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_dir = workspace_root / "reports" / "agents" / "non-git-closeout"
            report_dir.mkdir(parents=True, exist_ok=True)
            run_id = "non-git-closeout"
            write_ready_closeout_bundle(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unable to resolve git HEAD", result.stderr)

    def test_task_close_rejects_stale_closeout_and_artifact_diff_ref(self) -> None:
        """task_close should compare matching closeout/artifact refs to the current diff ref."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-stale-diff-ref"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            stale_ref = "stale-diff-ref"
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    f"- diff_check_latest_diff_ref: {current_diff_ref()}",
                    f"- diff_check_latest_diff_ref: {stale_ref}",
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir, diff_ref=stale_ref)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("diff_check_latest_diff_ref", result.stdout)

    def test_task_close_diff_ref_includes_untracked_files(self) -> None:
        """Untracked workspace files should make captured diff-check refs stale."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-untracked-diff-ref"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            (workspace_root / "new-untracked.md").write_text(
                "new file\n", encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("diff_check_latest_diff_ref", result.stdout)

    def test_task_close_rejects_untracked_reports_outside_run_bundle(self) -> None:
        """Generated report files outside reports/agents should block closeout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            stray_report = (
                workspace_root
                / "reports"
                / "dependency-review"
                / "agent-canon-pr"
                / "workflow_monitoring.md"
            )
            stray_report.parent.mkdir(parents=True, exist_ok=True)
            stray_report.write_text("# stray report\n", encoding="utf-8")
            run_id = "test-task-close-stray-report"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=no", result.stdout)
            self.assertIn(
                "reports/dependency-review/agent-canon-pr/workflow_monitoring.md",
                result.stdout,
            )
            self.assertIn("report_artifact_placement_clean", result.stdout)

    def test_task_close_rejects_other_agent_run_reports(self) -> None:
        """Only the current run bundle may carry untracked agent reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            old_run = workspace_root / "reports" / "agents" / "old-run"
            old_run.mkdir(parents=True, exist_ok=True)
            (old_run / "workflow_monitoring.md").write_text(
                "# old run\n", encoding="utf-8"
            )
            run_id = "test-task-close-current-run-only"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=no", result.stdout)
            self.assertIn(
                "reports/agents/old-run/workflow_monitoring.md", result.stdout
            )

    def test_task_close_rejects_tracked_other_agent_run_reports(self) -> None:
        """Tracked old agent run bundles are not durable source canon."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            old_run = workspace_root / "reports" / "agents" / "old-run"
            old_run.mkdir(parents=True, exist_ok=True)
            (old_run / "workflow_monitoring.md").write_text(
                "# old run\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "add", "reports/agents/old-run/workflow_monitoring.md"],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed tracked old agent report",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-tracked-old-agent-run"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=no", result.stdout)
            self.assertIn("report_artifact_tracked_outside_current_run", result.stdout)
            self.assertIn(
                "reports/agents/old-run/workflow_monitoring.md", result.stdout
            )

    def test_task_close_rejects_ignored_reports_outside_run_bundle(self) -> None:
        """Ignored generated report roots are still closeout blockers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            (workspace_root / ".gitignore").write_text(
                "reports/dependency-review/\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", ".gitignore"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed ignored report root",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            ignored_report = (
                workspace_root
                / "reports"
                / "dependency-review"
                / "ignored-run"
                / "workflow_monitoring.md"
            )
            ignored_report.parent.mkdir(parents=True, exist_ok=True)
            ignored_report.write_text("# ignored report\n", encoding="utf-8")
            run_id = "test-task-close-ignored-report"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=no", result.stdout)
            self.assertIn(
                "reports/dependency-review/ignored-run/workflow_monitoring.md",
                result.stdout,
            )

    def test_task_close_allows_ignored_old_agent_run_reports(self) -> None:
        """Ignored agent run bundles are local log cache, not source-tree leakage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            (workspace_root / ".gitignore").write_text(
                "reports/agents/\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "add", ".gitignore"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed ignored agent reports",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            old_run = workspace_root / "reports" / "agents" / "old-run"
            old_run.mkdir(parents=True, exist_ok=True)
            (old_run / "workflow_monitoring.md").write_text(
                "# old run\n", encoding="utf-8"
            )
            run_id = "test-task-close-ignored-old-agent-run"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)

    def test_task_close_allows_tracked_durable_reports(self) -> None:
        """Tracked durable reports are repository canon, not run-bundle leakage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            durable_report = workspace_root / "reports" / "project" / "report.md"
            durable_report.parent.mkdir(parents=True, exist_ok=True)
            durable_report.write_text("# Durable Report\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "reports/project/report.md"],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "-m",
                    "seed durable report",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-tracked-report"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_rejects_missing_actual_wave_event(self) -> None:
        """The lifecycle status must reconcile schedule rows with observed wave events."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-missing-wave-event"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            (report_dir / "workflow_monitoring.md").write_text(
                "\n".join(
                    [
                        "# Workflow Monitoring",
                        "",
                        "## Actual Wave Events",
                        "",
                        "## Tool Warnings",
                        "",
                        "- tool_warnings_status: none",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:actual_wave_missing:WAVE-1", result.stdout
            )
            self.assertIn("subagent_wave_reconciliation_clean", result.stdout)

    def test_task_close_rejects_comment_only_actual_wave_event(self) -> None:
        """Commented wave rows are documentation, not observed wave evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Close Test",
                    "-c",
                    "user.email=task-close@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-comment-only-wave-event"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            (report_dir / "workflow_monitoring.md").write_text(
                "\n".join(
                    [
                        "# Workflow Monitoring",
                        "",
                        "## Actual Wave Events",
                        "",
                        (
                            "<!-- - wave_event=recorded wave_id=WAVE-1 event_kind=initial_intake "
                            "spawn_authority=parent trigger=initial_intake budget_before=0/12 "
                            "budget_after=3/12 runtime_max_threads=24 runtime_max_depth=2 "
                            "spawned_roles=requirements_organizer,explorer,execution_planner "
                            "role_instances=requirements_organizer:intake_requirements:team_manifest.yaml,"
                            "explorer:intake_explorer:team_manifest.yaml,"
                            "execution_planner:intake_plan:team_manifest.yaml "
                            "skipped_roles=none allowed_paths=reports/agents/run "
                            "do_not_read=unrelated write_scope=read-only validation_route=pytest "
                            "review_gate=schedule_review handoff_artifacts=team_manifest.yaml status=done -->"
                        ),
                        "",
                        "## Tool Warnings",
                        "",
                        "- tool_warnings_status: none",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--run-id",
                    run_id,
                ],
                cwd=workspace_root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:actual_wave_missing:WAVE-1", result.stdout
            )
            self.assertIn("subagent_wave_reconciliation_clean", result.stdout)

    def test_task_close_accepts_mid_task_user_input_wave_checkpoint(self) -> None:
        """A classified mid-task user input checkpoint should preserve closeout readiness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-mid-task-user-input"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=\n", result.stdout)

    def test_task_close_rejects_mid_task_user_input_without_packet(self) -> None:
        """Mid-task user input rows should include a checkpoint packet path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-mid-task-user-input-missing-packet"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(report_dir, updated_packet="none")
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                "WAVE-2:updated_packet",
                result.stdout,
            )
            self.assertIn("subagent_wave_reconciliation_clean", result.stdout)

    def test_task_close_rejects_scope_change_without_fresh_wave_evidence(self) -> None:
        """Scope-changing additions should not close without fresh wave evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-scope-change-missing-fresh-wave"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="scope_or_contract_change",
                allowed_paths="tools/agent_tools",
                do_not_read="reports/agents/other",
                write_scope="tools/agent_tools",
                validation_route="pytest",
                review_gate="python_review",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                "WAVE-2:fresh_wave_evidence",
                result.stdout,
            )

    def test_task_close_accepts_scope_change_with_fresh_wave_evidence(self) -> None:
        """Scope-changing additions may close after fresh wave evidence exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-scope-change-fresh-wave"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            fresh_wave_evidence = report_dir / "fresh_wave_evidence.md"
            fresh_wave_evidence.write_text(
                "fresh follow-up wave completed\n", encoding="utf-8"
            )
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="scope_or_contract_change",
                allowed_paths="tools/agent_tools",
                do_not_read="reports/agents/other",
                write_scope="tools/agent_tools",
                validation_route="pytest",
                review_gate="python_review",
                fresh_wave_evidence=str(fresh_wave_evidence),
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_rejects_scope_change_with_unrelated_wave_evidence(self) -> None:
        """Fresh-wave evidence should be scoped to the current run bundle."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            unrelated_evidence = Path(tmp_dir) / "unrelated-wave.md"
            unrelated_evidence.write_text(
                "not a current-run wave artifact\n", encoding="utf-8"
            )
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-scope-change-unrelated-fresh-wave"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="scope_or_contract_change",
                allowed_paths="tools/agent_tools",
                do_not_read="reports/agents/other",
                write_scope="tools/agent_tools",
                validation_route="pytest",
                review_gate="python_review",
                fresh_wave_evidence=str(unrelated_evidence),
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_evidence_outside_scope:"
                f"WAVE-2:fresh_wave_evidence:{unrelated_evidence}",
                result.stdout,
            )

    def test_task_close_rejects_new_task_without_fresh_run_bundle(self) -> None:
        """New tasks should not be absorbed into the current run without a fresh run."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-new-task-missing-fresh-run"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="new_task",
                allowed_paths="reports/agents/new-run",
                do_not_read="reports/agents/run",
                write_scope="none",
                validation_route="task_start",
                review_gate="manager_review",
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_field_missing:"
                "WAVE-2:fresh_run_bundle",
                result.stdout,
            )

    def test_task_close_rejects_new_task_with_missing_fresh_run_path(self) -> None:
        """Fresh-run evidence should point at an existing run bundle directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-new-task-missing-fresh-run-path"
            report_dir = report_root / run_id
            missing_fresh_run = report_root / "missing-new-task-run"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="new_task",
                allowed_paths="reports/agents/missing-new-task-run",
                do_not_read="reports/agents/run",
                write_scope="none",
                validation_route="task_start",
                review_gate="manager_review",
                fresh_run_bundle=str(missing_fresh_run),
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_evidence_missing:"
                f"WAVE-2:fresh_run_bundle:{missing_fresh_run}",
                result.stdout,
            )

    def test_task_close_rejects_new_task_with_unrelated_fresh_run_dir(self) -> None:
        """Fresh-run evidence should be a sibling reports/agents run directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            unrelated_run_dir = Path(tmp_dir) / "unrelated-run"
            unrelated_run_dir.mkdir(parents=True, exist_ok=True)
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-new-task-unrelated-fresh-run"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="new_task",
                allowed_paths="reports/agents/unrelated-run",
                do_not_read="reports/agents/run",
                write_scope="none",
                validation_route="task_start",
                review_gate="manager_review",
                fresh_run_bundle=str(unrelated_run_dir),
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SUBAGENT_WAVE_RECONCILIATION_BLOCKERS=", result.stdout)
            self.assertIn(
                "workflow_monitoring.md:mid_task_user_input_evidence_outside_scope:"
                f"WAVE-2:fresh_run_bundle:{unrelated_run_dir}",
                result.stdout,
            )

    def test_task_close_accepts_new_task_with_fresh_run_bundle(self) -> None:
        """Current run closeout may pass after the new task has a fresh run bundle."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-new-task-fresh-run"
            report_dir = report_root / run_id
            fresh_run_bundle = report_root / "fresh-new-task-run"
            report_dir.mkdir(parents=True, exist_ok=True)
            fresh_run_bundle.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            append_mid_task_wave_checkpoint(
                report_dir,
                input_classification="new_task",
                allowed_paths="reports/agents/fresh-new-task-run",
                do_not_read="reports/agents/run",
                write_scope="none",
                validation_route="task_start",
                review_gate="manager_review",
                fresh_run_bundle=str(fresh_run_bundle),
            )
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_rejects_chunk_only_completion(self) -> None:
        """task_close should fail when only a chunk is complete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-chunk-only"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=chunk only closeout smoke",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: no",
                        "- overall_delivery_complete: no",
                        "- unfinished_tasks_absent: no",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- tool_warnings_resolved: yes",
                        "- mechanical_completion_loop_complete: no",
                        "- diff_check_agent_complete: no",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("all_planned_chunks_complete", result.stdout)
            self.assertIn("overall_delivery_complete", result.stdout)
            self.assertIn("unfinished_tasks_absent", result.stdout)

    def test_task_close_rejects_partial_spec_or_ignored_review_findings(self) -> None:
        """task_close should fail when spec coverage or review integration is incomplete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-partial-spec"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=partial spec closeout smoke",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: no",
                        "- review_findings_integrated: no",
                        "- post_fix_full_review_complete: no",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("spec_product_coverage_complete", result.stdout)
            self.assertIn("review_findings_integrated", result.stdout)

    def test_task_close_rejects_missing_post_fix_full_review_completion(self) -> None:
        """task_close should fail when review-driven fixes skipped the final full rerun."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-post-fix-review"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout missing post-fix full review",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout missing post-fix full review",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: no",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("post_fix_full_review_complete", result.stdout)

    def test_task_close_rejects_missing_canonical_tree_head_completion(self) -> None:
        """task_close should fail when canonical tree-head cleanup is incomplete."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-canonical-tree-head"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout missing canonical tree head completion",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- tool_warnings_resolved: yes",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: no",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("canonical_tree_head_complete", result.stdout)

    def test_task_close_rejects_empty_work_log(self) -> None:
        """task_close should fail when the run-local work log is still empty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-empty-work-log"
            report_dir = report_root / run_id
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "closeout ready except work log",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            (report_dir / "verification.txt").write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout ready except work log",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
                        "user_completion_report=unlocked",
                        "closeout_gate_status=resolved",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "user_request_contract.md").write_text(
                "\n".join(
                    [
                        "# User Request Contract",
                        "",
                        "- all_clauses_resolved: yes",
                        "- forbidden_drift_detected: no",
                        "- deferred_clause_ids:",
                        "- unresolved_clause_ids:",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "closeout_gate.md").write_text(
                "\n".join(
                    [
                        "# Closeout Gate",
                        "",
                        "## Gate Status",
                        "",
                        "- verifier_status: pass",
                        "- auditor_status: resolved",
                        "- required_reviews_complete: yes",
                        "- validation_complete: yes",
                        "- request_contract_complete: yes",
                        "- all_planned_chunks_complete: yes",
                        "- overall_delivery_complete: yes",
                        "- unfinished_tasks_absent: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- make_ci_status: pass",
                        "- spec_product_coverage_complete: yes",
                        "- review_findings_integrated: yes",
                        "- post_fix_full_review_complete: yes",
                        "- tool_warnings_resolved: yes",
                        "- mechanical_completion_loop_complete: yes",
                        "- subagents_closed: yes",
                        "- diff_check_agent_complete: yes",
                        "- canonical_tree_head_complete: yes",
                        "- agent_evaluation_complete: yes",
                        "- runtime_log_archive_synced: yes",
                        "- commit_created: yes",
                        "- push_completed: yes",
                        "- user_completion_report: unlocked",
                        *ready_closeout_evidence_lines(),
                    ]
                ),
                encoding="utf-8",
            )
            write_ready_schedule(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_diff_check_artifact(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WORK_LOG_COMPLETE=no", result.stdout)
            self.assertIn("work_log_complete", result.stdout)


if __name__ == "__main__":
    unittest.main()
