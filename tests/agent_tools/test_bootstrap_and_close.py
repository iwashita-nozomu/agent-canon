# @dependency-start
# contract test
# responsibility Tests run bootstrap and close behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/agent_tools/agent_canon_preflight.py preflight routing under test
# upstream implementation ../../tools/agent_tools/packets.py owns packet normalization under test
# upstream implementation ../../tools/agent_tools/tool_calls.py owns typed lifecycle tool calls under test
# upstream implementation ../../tools/agent_tools/team_config.py owns team configuration under test
# upstream implementation ../../tools/agent_tools/implementation_dispatch.py owns dispatch under test
# @dependency-end

"""Tests for machine-driven run bootstrap and close commands."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "ci"))

from agent_canon_preflight import surface_manifest_paths  # noqa: E402
from check_agent_canon_pr import (  # noqa: E402
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)
from implementation_dispatch import (  # noqa: E402
    codex_runtime_max_threads,
    default_quality_check_agent_types,
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave,
    unique_codex_agents_for_roles,
    validate_agent_type_selections,
    workflow_spawn_budget,
)
from packets import (  # noqa: E402
    active_design_packet_mapping,
    resolve_active_design_packet_config,
)
from parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
)
from report_artifact_checks import (  # noqa: E402
    RUNTIME_PROFILE_TAXONOMY_PATH,
    _write_validation_leaf,
    write_completion_coverage_artifact,
)
from task_authority import hash_baseline_bytes  # noqa: E402
from task_close import update_lifecycle_closeout_consumer  # noqa: E402
from team_config import (  # noqa: E402
    AgentTypeSelection,
    load_task_catalog,
    load_team_config,
    select_roles,
)
from tool_calls import (  # noqa: E402
    CloseAgentLifecycleEvidence,
    materialize_close_agent_tool_call,
)
from tools.agent_tools.fixture_spawn import (  # noqa: E402
    bootstrap_fixture_public_environment,
)
from update_lifecycle_contract import (  # noqa: E402
    materialize_descendant_close_receipt,
    materialize_gate_verdict,
    materialize_reservation_release_receipt,
)
from work_log import append_ledger_event, read_ledger_snapshot  # noqa: E402

RUNTIME_PROFILE_INVENTORY = (
    PROJECT_ROOT / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
)
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
TASK_CLOSE_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "task_close.py"
WORKTREE_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "worktree_start.py"
SETUP_WORKTREE_SCRIPT = PROJECT_ROOT / "tools" / "setup_worktree.sh"
TEST_TEMP_ROOT = Path(tempfile.gettempdir())
TEST_PARENT_ROOT = Path(os.path.commonpath((PROJECT_ROOT, TEST_TEMP_ROOT))).resolve()


@contextmanager
def fixture_environment(parent_root: Path) -> Iterator[dict[str, str]]:
    """Bind fixture subprocesses to the current runner record capability."""
    previous_cwd = Path.cwd()
    try:
        with bootstrap_fixture_public_environment(
            mode="ordinary_tool",
            fixture_cwd=parent_root,
            base_env=os.environ,
        ) as fixture:
            authenticated_environment = dict(fixture.environment)
            with patch.dict(os.environ, authenticated_environment, clear=True):
                yield authenticated_environment
    finally:
        os.chdir(previous_cwd)


def seed_workspace_config(workspace_root: Path) -> None:
    """Seed parent state only; AgentCanon source stays outside the fixture."""
    config_path = workspace_root / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes((PROJECT_ROOT / ".codex" / "config.toml").read_bytes())


def materialize_derived_public_tool_view(workspace_root: Path) -> None:
    """Expose the vendored source tools through the canonical parent prefix."""
    public_tool_root = workspace_root / "tools" / "agent-canon"
    public_tool_root.parent.mkdir(parents=True, exist_ok=True)
    public_tool_root.symlink_to(
        "../vendor/agent-canon/tools",
        target_is_directory=True,
    )


def materialize_derived_source_tool_unit(source_root: Path) -> Path:
    """Copy the complete source-owned tool unit for a derived fixture."""
    source_tools = source_root / "tools" / "agent_tools"
    shutil.copytree(
        PROJECT_ROOT / "tools" / "agent_tools",
        source_tools,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache"),
    )
    return source_tools


def expected_workflow_spawn_budget(family_id: str) -> tuple[int, int]:
    """Read one workflow budget from the task catalog owner."""
    config = load_team_config()
    return workflow_spawn_budget(load_task_catalog(config), family_id)


def selected_active_design_packet(prefix: str) -> dict[str, object]:
    """Build a current closed packet while rebinding every selected output."""
    config = load_team_config()
    packet = deepcopy(
        active_design_packet_mapping(resolve_active_design_packet_config(config))
    )
    selected = {
        "design_artifact": f"{prefix}_design_brief.md",
        "design_review_artifact": f"{prefix}_design_review.md",
        "document_flow_review_artifact": f"{prefix}_document_flow_review.md",
    }
    packet.update(selected)
    default_to_selected = {
        "artifact:design_brief.md": f"artifact:{selected['design_artifact']}",
        "artifact:design_review.md": f"artifact:{selected['design_review_artifact']}",
        "artifact:document_flow_review.md": f"artifact:{selected['document_flow_review_artifact']}",
    }
    for entry_name in (
        "abstract_design_frame",
        "implementation_source_packet",
        "design_side_effect_map",
        "design_to_implementation_trace",
    ):
        entry = packet[entry_name]
        assert isinstance(entry, dict)
        entry["output_refs"] = [
            default_to_selected.get(reference, reference)
            for reference in entry["output_refs"]
        ]
    return packet


GRAPH_ACTIVE_DESIGN_PACKET = selected_active_design_packet("graph")
U2_ACTIVE_DESIGN_PACKET = selected_active_design_packet("u2")


def update_lifecycle_closeout_fixture() -> dict[str, object]:
    """Return one valid six-gate nested-lifecycle closeout artifact."""
    binding: dict[str, object] = {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": "3" * 40,
        "tree_sha": "4" * 40,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "update-lifecycle-closeout",
        "tool_version": "test.v1",
        "evidence_ref": "evidence:" + "6" * 64,
        "evidence_digest": "sha256:" + "7" * 64,
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }
    seed_ref = "evidence:" + "8" * 64
    gates: list[dict[str, object]] = []
    gate_contracts = {
        "G1": (
            "source_correctness",
            PROJECT_ROOT / "tools" / "agent_tools" / "publication_integrator.py",
            "resolve_publication_eligibility",
        ),
        "G3": (
            "pr_identity_cas",
            PROJECT_ROOT / "tools" / "agent_tools" / "github_publish.py",
            "materialize_pr_identity_gate",
        ),
        "G4": (
            "parent_projection_integrity",
            PROJECT_ROOT / "tools" / "update_agent_canon.sh",
            "accept_dependency_frontier",
        ),
        "G5": (
            "remote_publication_readback",
            PROJECT_ROOT / "tools" / "agent_tools" / "publication_integrator.py",
            "integrate_publication",
        ),
    }
    for index, gate_id in enumerate(("G1", "G3", "G4", "G5"), 1):
        evidence_refs = [
            cast("dict[str, object]", gate["binding"])["evidence_ref"]
            for gate in gates
        ]
        ordered_inputs = {
            "G1": [seed_ref],
            "G3": evidence_refs[:2],
            "G4": evidence_refs[2:3],
            "G5": evidence_refs[3:4],
        }[gate_id]
        invariant, owner_path, owner_symbol = gate_contracts[gate_id]
        gate = materialize_gate_verdict(
            binding=binding,
            gate_id=gate_id,
            ordered_input_evidence_refs=cast("list[str]", ordered_inputs),
            invariant=cast("str", invariant),
            output_digest="sha256:" + format(index, "x") * 64,
            owner=f"{owner_path}#{owner_symbol}",
            verdict="pass",
        )
        gates.append(gate)
        if gate_id == "G1":
            gates.append(
                materialize_generated_completeness_receipt(
                    g1_gate=gate,
                    candidate_sha=str(binding["candidate_sha"]),
                    tree_sha=str(binding["tree_sha"]),
                    check_results=[
                        {"check_id": check_id, "status": "pass"}
                        for check_id in GENERATED_COMPLETENESS_CHECK_IDS
                    ],
                )
            )
    handback: dict[str, object] = {
        "schema": "agent-canon.durable-handback.v1",
        "binding": binding,
        "agent_id": "agent:owner",
        "descendant_ids": ["agent:reviewer"],
        "reservation_ids": ["reservation:reviewer"],
        "evidence_ref": "evidence:" + "b" * 64,
        "state": "durable_handback",
    }
    owned_path = "/tmp/agent-canon-update-owned"
    gate_five_binding = cast("dict[str, object]", gates[4]["binding"])
    cleanup: dict[str, object] = {
        "schema": "agent-canon.cleanup-proof.v1",
        "binding": binding,
        "remote_readback_evidence_ref": gate_five_binding["evidence_ref"],
        "task_owned_paths": [owned_path],
        "task_owned_state_before": {owned_path: "present"},
        "task_owned_state_after": {owned_path: "removed"},
        "cleaned_paths": [owned_path],
        "unknown_shared_state_before_digest": "sha256:" + "c" * 64,
        "unknown_shared_state_after_digest": "sha256:" + "c" * 64,
        "unknown_shared_state_unchanged_evidence_ref": "evidence:" + "d" * 64,
        "evidence_ref": "evidence:" + "e" * 64,
        "state": "cleanup_proven",
    }
    descendants = [
        materialize_descendant_close_receipt(
            binding=binding,
            durable_handback=handback,
            agent_id="agent:reviewer",
            evidence_ref="evidence:" + "f" * 64,
        )
    ]
    reservations = [
        materialize_reservation_release_receipt(
            binding=binding,
            durable_handback=handback,
            reservation_id="reservation:reviewer",
            evidence_ref="evidence:" + "0" * 64,
        )
    ]
    closeout = materialize_close_agent_tool_call(
        run_id="run-update-lifecycle",
        agent_id="agent:owner",
        evidence=CloseAgentLifecycleEvidence(
            gate_verdicts=gates,
            cleanup_proof=cleanup,
            durable_handback=handback,
            descendant_close_receipts=descendants,
            reservation_release_receipts=reservations,
        ),
    )
    g6 = cast("dict[str, object]", closeout["g6_gate"])
    token = cast("dict[str, object]", closeout["close_agent_tool_call"])
    return {
        "schema": "agent-canon.update-lifecycle-closeout.v1",
        "gate_verdicts": [*gates, g6],
        "durable_handback": handback,
        "descendants": descendants,
        "reservations": reservations,
        "descendants_closed_evidence_ref": closeout[
            "descendants_closed_evidence_ref"
        ],
        "reservations_released_evidence_ref": closeout[
            "reservations_released_evidence_ref"
        ],
        "cleanup_proof": cleanup,
        "close_agent_tool_call": token,
    }


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
            if raw_path.startswith((b"reports/agents/", b".agent-canon/")):
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
        "## AgentCanon Latest Evidence",
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
        "- structure_activation: format_only",
        "- document_split_decision: not_applicable:format-only: fixture closeout bundle",
        "- structure_planning: not_applicable",
        "- prose_graph_activation: not_selected",
        "- prose_graph: not_applicable",
        "- structure_contract: skipped: fixture format-only route",
        "- structure_owner: not_applicable",
        "- structure_source: not_applicable",
        "- structure_reader: not_applicable",
        "- structure_layout: not_applicable",
        "- structure_validation_topology: not_applicable",
        "- md_style_check: pass",
        "- format_only_reason: fixture closeout bundle",
        "",
        "## Canonical Formatter And Static Evidence",
        "- canonical_format_check_route: tools/bin/agent-canon docs check fixture-format-only.md",
        "- canonical_format_check_status: pass",
        "- selected_non_python_static_evidence: fixture-static-evidence",
        "- typed_owner_boundary_status: pass",
        "- mapping_error_sets_empty: yes",
        "- canonical_dispatcher_schema_status: pass",
        "",
        "## CompletionCoverage And Failure Response Evidence",
        "- completion_coverage_artifact: completion_coverage.json",
        "- completion_coverage_consumer: yes",
        "- validation_failure_response_status: pass",
        "",
        "## Subagent Lifecycle Evidence",
        "- fresh_subagents_required: conditional",
        "- reuse_for_new_task: allowed_when_owner_context_compatible",
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
                    "| WAVE-1 | parent | parent | initial_intake | 0/12 | 1/12 | 26 | 2 | "
                    "requirements_organizer | "
                    "manager:manager_requirements_organizer:requirements_organizer:"
                    "team_manifest.yaml | none | reports/agents/run | "
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
                    "budget_after=1/12 runtime_max_threads=26 runtime_max_depth=2 "
                    "spawned_roles=requirements_organizer "
                    "role_instances=manager:manager_requirements_organizer:"
                    "requirements_organizer:team_manifest.yaml "
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
        role_instances = role_instances or f"{spawned_roles}:followup:{spawned_roles}:{updated_packet}"
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
            f"3/12 | 3/12 | 26 | 2 | {spawned_roles} | {role_instances} | {skipped_roles} | "
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
        "budget_before=3/12 budget_after=3/12 runtime_max_threads=26 "
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


def write_ready_completion_coverage(report_dir: Path, run_id: str) -> None:
    """Write the completion-coverage evidence consumed by task_close."""
    source_binding = {
        "run_id": run_id,
        "context_id": "fixture-context",
        "organizer_context_id": "fixture-organizer",
        "parent": "codex",
        "component_manager": "codex",
        "assigned_unit": "fixture-unit",
        "source_binding": {"run_id": run_id, "context_id": "fixture-context"},
        "source_refs": ["tests/agent_tools/test_bootstrap_and_close.py"],
    }
    append_ledger_event(
        report_dir,
        {
            "run_id": run_id,
            "context_id": "fixture-context",
            "event_id": "fixture-event-1",
            "semantic_kind": "request_clause",
            "owner": "codex",
            "state_owner": "codex",
            "api_owner": "codex",
            "dependency_owner": "codex",
            "responsibility_unit": "fixture-unit",
            "intent_id": "fixture-intent",
            "outcome": "complete",
            "clause_id": "T1-C1",
            "evidence_refs": ["fixture-evidence"],
            "artifact_refs": ["fixture-artifact"],
            "source_binding": source_binding["source_binding"],
            "gate_evidence": [
                {
                    "gate_id": "oop_readability_guard",
                    "stage": "review",
                    "owner": "codex",
                    "outcome": "pass",
                    "artifact_refs": ["fixture-oop"],
                    "source_event_refs": ["fixture-event-1"],
                    "scanned_paths": ["tools/agent_tools/task_close.py"],
                    "signal_counts": {"review_signal_findings": 0},
                    "typed_boundary_counts": {"api_boundary": 0},
                    "solid_counts": {"single responsibility": 0},
                    "typed_evidence_owner": "oop-readability-checker",
                },
                {
                    "gate_id": "solid_evidence_gate",
                    "stage": "review",
                    "owner": "codex",
                    "outcome": "pass",
                    "artifact_refs": ["fixture-solid"],
                    "source_event_refs": ["fixture-event-1"],
                    "scanned_paths": ["tools/agent_tools/task_close.py"],
                    "covered_paths": ["tools/agent_tools/task_close.py"],
                    "solid_counts": {"single responsibility": 0},
                },
                {
                    "gate_id": "canonical_formatter_static",
                    "stage": "validation",
                    "owner": "codex",
                    "outcome": "pass",
                    "artifact_refs": ["fixture-format"],
                    "source_event_refs": ["fixture-event-1"],
                },
            ],
        },
    )
    write_completion_coverage_artifact(
        report_dir,
        read_ledger_snapshot(report_dir, "fixture-snapshot"),
        source_binding,
        ["T1-C1"],
        {
            "owner": "codex",
            "state_owner": "codex",
            "api_owner": "codex",
            "dependency_owner": "codex",
        },
        {
            "w2_implementation_complete": True,
            "w2_review_complete": True,
            "source_freeze_review_complete": True,
            "formatter_and_static_checks_pass": True,
        },
        {"planned_work_complete": True},
        {"open_repairs": []},
        {"open_crossing_edges": []},
        {
            "run_id": run_id,
            "context_id": "fixture-context",
            "observation_ref": "fixture-topology",
            "global_publication_state": "publication_ready",
            "routing_gate": "verified",
            "writer_release_order_complete": True,
            "final_review_approved": True,
            "closeout_unlocked": True,
            "branch_creation_reason": (
                "convergence_w2_writer_owned_after_git_index_blocker"
            ),
            "source_freeze_before_review": True,
            "formatter_static_events": ["formatter", "static"],
            "writer_cardinality": 1,
            "writer_collision_state": "collision_preserved",
            "descendant_disposition": {"status": "none"},
            "topology_schema": "agent-canon.control-topology.v1",
            "topology_order": [
                "design_approved",
                "writer_released",
                "source_frozen",
                "change_review_approved",
            ],
        },
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
                "- mapping_error_sets_empty: yes",
                "- typed_owner_boundary_status: pass",
                "- canonical_dispatcher_schema_status: pass",
                *ready_closeout_evidence_lines(workspace=workspace),
            ]
        ),
        encoding="utf-8",
    )
    write_ready_schedule(report_dir)
    _log_ready_work(report_dir)
    write_ready_completion_coverage(report_dir, run_id)
    write_ready_workflow_monitoring(report_dir)
    write_ready_agent_evaluation(report_dir)
    write_ready_final_review(report_dir)


class BootstrapAndCloseTest(unittest.TestCase):
    """Verify machine-driven task start and close behavior."""

    def test_report_artifact_taxonomy_uses_runtime_inventory(self) -> None:
        """Completion coverage reads the canonical runtime inventory path."""
        self.assertEqual(RUNTIME_PROFILE_TAXONOMY_PATH, RUNTIME_PROFILE_INVENTORY)
        self.assertTrue(RUNTIME_PROFILE_TAXONOMY_PATH.is_file())

    def test_validation_leaf_first_publication_accepts_missing_parent_target(self) -> None:
        """Validation artifacts publish successfully when the optional leaf is absent."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            boundary = ParentRootSideEffectBoundary()
            attestation = boundary.attest(
                ParentRootAttestationRequest(
                    cwd=root, explicit_root=root, purpose="validation-artifact"
                )
            )
            target = root / "reports" / "validation.stdout"
            with (
                patch.dict(
                    os.environ,
                    {"AGENT_CANON_SIDE_EFFECT_PARENT_ROOT": str(root)},
                    clear=False,
                ),
                patch(
                    "report_artifact_checks.resolve_parent_writer_attestation",
                    return_value=attestation,
                ),
            ):
                _write_validation_leaf(target, b"first publication\n")
            self.assertEqual(target.read_bytes(), b"first publication\n")

    def setUp(self) -> None:
        """Keep subprocesses free of retired ambient parent authority."""

    def test_retired_tool_names_are_not_permanent_update_surfaces(self) -> None:
        """One-time transition candidates do not reserve future parent paths."""
        update_paths = set(surface_manifest_paths(PROJECT_ROOT))

        self.assertTrue(
            {
                "tools/sync_agent_canon.sh",
                "tools/agent_tools/surface_manifest.py",
                "tools/agent_tools/update_agent_canon.sh",
            }.isdisjoint(update_paths)
        )

    def consume_update_lifecycle_fixture(
        self,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """Persist and consume one isolated update-lifecycle closeout record."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            report_dir = Path(tmp_dir)
            (report_dir / "update_lifecycle_closeout.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            return update_lifecycle_closeout_consumer(report_dir)

    def test_update_lifecycle_terminal_tool_call_passes_after_cleanup(self) -> None:
        """The positive close route binds all six gates and terminal ToolCall."""
        payload = update_lifecycle_closeout_fixture()

        decision = self.consume_update_lifecycle_fixture(payload)

        token = cast("dict[str, object]", payload["close_agent_tool_call"])
        self.assertEqual(decision["ready"], True)
        self.assertEqual(decision["reason"], "pass")
        self.assertEqual(token["tool_id"], "close_agent")
        self.assertEqual(token["state"], "terminal")
        self.assertEqual(decision["close_agent_token_id"], token["token_id"])

    def test_update_lifecycle_rejects_completed_but_open_descendant(self) -> None:
        """A completed handback is not a substitute for closing the agent."""
        payload = update_lifecycle_closeout_fixture()
        descendants = cast("list[dict[str, object]]", payload["descendants"])
        descendants[0]["state"] = "completed"

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(decision["reason"], "close_agent:completed_but_open")

    def test_update_lifecycle_rejects_unknown_descendant(self) -> None:
        """Every observed descendant must exist in the durable handback ledger."""
        payload = update_lifecycle_closeout_fixture()
        descendants = cast("list[dict[str, object]]", payload["descendants"])
        unknown = dict(descendants[0])
        unknown["agent_id"] = "agent:unknown"
        unknown["evidence_ref"] = "evidence:" + "1" * 64
        descendants.append(unknown)

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(decision["reason"], "close_agent:unknown_descendant")

    def test_update_lifecycle_rejects_reservation_leak(self) -> None:
        """Closeout remains blocked until every declared reservation is released."""
        payload = update_lifecycle_closeout_fixture()
        reservations = cast("list[dict[str, object]]", payload["reservations"])
        reservations[0]["state"] = "reserved"

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(decision["reason"], "close_agent:reservation_leak")

    def test_update_lifecycle_rejects_cleanup_before_remote_readback(self) -> None:
        """Cleanup proof must point at the exact G5 publication evidence."""
        payload = update_lifecycle_closeout_fixture()
        cleanup = cast("dict[str, object]", payload["cleanup_proof"])
        cleanup["remote_readback_evidence_ref"] = "evidence:" + "2" * 64

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(decision["reason"], "close_agent:cleanup_before_remote_readback")

    def test_update_lifecycle_rejects_missing_gate_receipt(self) -> None:
        """Terminal close requires the ordered complete G1-G6 boundary set."""
        payload = update_lifecycle_closeout_fixture()
        gates = cast("list[dict[str, object]]", payload["gate_verdicts"])
        gates.pop()

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(decision["reason"], "close_agent:all_six_gate_evidence_required")

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
        self.assertEqual(
            same_role_policy["identity_key"],
            "role_id+instance_id+agent_type",
        )
        raw_same_role_fields = cast(
            "list[object]",
            same_role_policy["required_fields"],
        )
        self.assertLessEqual(
            {
                "role_id",
                "instance_id",
                "agent_type",
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
            "requirements_organizer:pending_explicit_runtime_spawn_authority",
            schedule_text,
        )
        self.assertNotIn("explorer:pending_explicit_runtime_spawn_authority", schedule_text)
        self.assertNotIn(
            "execution_planner:pending_explicit_runtime_spawn_authority",
            schedule_text,
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
        self,
        manifest: dict[str, object],
        expected_role_ids: set[str] | None = None,
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
            if expected_role_ids is not None and role_id not in expected_role_ids:
                continue
            self.assert_role_prompt_includes(manifest, role_id, fields)

    def assert_graph_active_packet_bundle(
        self,
        report_dir: Path,
        stdout: str,
    ) -> None:
        """Assert one entrypoint persisted and propagated the graph packet."""
        selected_paths = (
            "graph_design_brief.md",
            "graph_design_review.md",
            "graph_document_flow_review.md",
        )
        for path in selected_paths:
            self.assertTrue((report_dir / path).is_file(), path)
        for path in (
            "design_brief.md",
            "design_review.md",
            "document_flow_review.md",
        ):
            self.assertFalse((report_dir / path).exists(), path)

        manifest_text = (report_dir / "team_manifest.yaml").read_text(
            encoding="utf-8"
        )
        manifest_value: object = yaml.safe_load(manifest_text)
        self.assertIsInstance(manifest_value, dict)
        manifest = cast("dict[str, object]", manifest_value)
        run = cast("dict[str, object]", manifest["run"])
        self.assertEqual(run["active_design_packet"], GRAPH_ACTIVE_DESIGN_PACKET)
        projection = cast(
            "dict[str, object]",
            run["active_design_packet_reference_projection"],
        )
        self.assertEqual(
            projection["schema"],
            "waterfall.active_design_packet_materialization.v1",
        )
        self.assertEqual(len(cast("list[object]", projection["clause_results"])), 4)
        self.assertTrue(cast("list[object]", projection["source_results"]))
        self.assertTrue(cast("list[object]", projection["dependency_results"]))
        output_results = cast("list[object]", projection["output_results"])
        output_refs = {
            str(cast("dict[str, object]", result)["output_ref"])
            for result in output_results
            if isinstance(result, dict)
        }
        self.assertTrue(
            {
                "artifact:graph_design_brief.md",
                "artifact:graph_design_review.md",
                "artifact:graph_document_flow_review.md",
            }.issubset(output_refs)
        )
        pre_handoff_status = cast(
            "dict[str, object]",
            run["pre_handoff_gate_status"],
        )
        self.assertEqual(
            pre_handoff_status["applies_when"],
            "run.active_design_packet.design_artifact="
            "graph_design_brief.md;"
            "condition=exists_before_implementation_or_handoff",
        )
        for unselected_basename in (
            "design_brief.md",
            "design_review.md",
            "document_flow_review.md",
        ):
            self.assertNotIn(
                f"artifact:{unselected_basename}",
                output_refs,
                f"unselected packet output remains: {unselected_basename}",
            )
        artifact_inventory = cast("list[object]", manifest["artifacts"])
        for path in selected_paths:
            self.assertIn(path, artifact_inventory)

        role_entries = cast("list[object]", manifest["roles"])
        roles_by_id = {
            str(role["id"]): role
            for value in role_entries
            if isinstance(value, dict)
            for role in (cast("dict[str, object]", value),)
        }
        expected_outputs = {
            "designer": selected_paths[0],
            "design_reviewer": selected_paths[1],
            "document_flow_reviewer": selected_paths[2],
        }
        for role_id, expected_output in expected_outputs.items():
            role = roles_by_id[role_id]
            self.assertEqual(role["required_outputs"], [expected_output])
            write_policy = cast("dict[str, object]", role["write_policy"])
            self.assertEqual(
                write_policy["allowed_files"],
                [str((report_dir / expected_output).resolve())],
            )

        implementer = roles_by_id["implementer"]
        document_packet = cast("dict[str, object]", implementer["document_packet"])
        read_entries = cast(
            "list[object]",
            document_packet["role_specific_read_before_work"],
        )
        read_paths = {
            str(cast("dict[str, object]", entry)["path"])
            for entry in read_entries
            if isinstance(entry, dict)
        }
        for path in selected_paths:
            self.assertIn(str((report_dir / path).resolve()), read_paths)
            self.assertIn(path, stdout)

    def test_bootstrap_skips_agent_canon_preflight_in_source_repo(self) -> None:
        """Source AgentCanon runs do not require a derived-repo update target."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                "AGENT_CANON_PREFLIGHT_CHECKLIST=documents/agent-canon/agent-canon-parent-repo-latest-checklist.md",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present", result.stdout
            )

    def test_bootstrap_materializes_explicit_active_design_packet(self) -> None:
        """The run bootstrap persists and routes one typed packet end to end."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            report_root = root / f"reports-{BOOTSTRAP_SCRIPT.stem}"
            run_id = f"graph-{BOOTSTRAP_SCRIPT.stem}"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "graph active packet smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--active-design-packet",
                    json.dumps(GRAPH_ACTIVE_DESIGN_PACKET, separators=(",", ":")),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report_dir = report_root / run_id
            manifest = yaml.safe_load(
                (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["run"]["active_design_packet"],
                GRAPH_ACTIVE_DESIGN_PACKET,
            )
            for artifact in GRAPH_ACTIVE_DESIGN_PACKET.values():
                if isinstance(artifact, str) and artifact.endswith(".md"):
                    self.assertTrue((report_dir / artifact).is_file(), artifact)
                    self.assertIn(artifact, result.stdout)
            self.assertIn(
                "run.active_design_packet.design_artifact=graph_design_brief.md;",
                (report_dir / "team_manifest.yaml").read_text(encoding="utf-8"),
            )
            self.assert_graph_active_packet_bundle(report_dir, result.stdout)

    def test_bootstrap_rejects_invalid_active_design_packet_before_bundle_creation(
        self,
    ) -> None:
        """Malformed packet input fails before bootstrap creates a run."""
        cases = (
            (
                {key: value for key, value in U2_ACTIVE_DESIGN_PACKET.items() if key != "document_flow_review_artifact"},
                "active_design_packet:field_missing:document_flow_review_artifact",
            ),
            (
                {**U2_ACTIVE_DESIGN_PACKET, "design_artifact": "/tmp/u2_design.md"},
                "active_design_packet:field_invalid:design_artifact",
            ),
            (
                {**U2_ACTIVE_DESIGN_PACKET, "document_flow_required": "true"},
                "active_design_packet:field_invalid:document_flow_required",
            ),
            (
                {**U2_ACTIVE_DESIGN_PACKET, "unexpected_contract": True},
                "active_design_packet:field_unknown:unexpected_contract",
            ),
        )
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            for index, (packet, expected_error) in enumerate(cases):
                report_root = root / f"reports-{BOOTSTRAP_SCRIPT.stem}-{index}"
                run_id = f"invalid-{BOOTSTRAP_SCRIPT.stem}-{index}"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(BOOTSTRAP_SCRIPT),
                        "--task",
                        "invalid packet",
                        "--owner",
                        "codex",
                        "--run-id",
                        run_id,
                        "--workspace-root",
                        str(PROJECT_ROOT),
                        "--report-root",
                        str(report_root),
                        "--active-design-packet",
                        json.dumps(packet, separators=(",", ":")),
                        "--skip-agent-canon-preflight",
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stdout + result.stderr)
                self.assertFalse((report_root / run_id).exists())

    def test_hash_baseline_bytes_is_canonical(self) -> None:
        """Hash sidecars are derived from exact payload bytes with one newline."""
        payload = b"authority: exact\n"
        expected = (hashlib.sha256(payload).hexdigest() + "\n").encode("ascii")
        self.assertEqual(hash_baseline_bytes(payload), expected)

    def test_bootstrap_routes_dirty_shared_canon_to_pr_first_workflow(self) -> None:
        """Dirty shared-canon surfaces should not point only to commit-or-stash."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            seed_workspace_config(workspace_root)
            (workspace_root / "vendor" / "agent-canon").mkdir(parents=True)
            (workspace_root / "vendor" / "agent-canon" / "README.md").write_text(
                "shared canon candidate\n",
                encoding="utf-8",
            )
            (workspace_root / "Makefile").write_text(
                "agent-canon-update-plan:\n\t@touch plan-sentinel\n"
                "agent-canon-ensure-latest:\n\t@touch ensure-sentinel\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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
            self.assertIn("preserve_current_checkout", result.stdout)
            self.assertIn("request_current_task_user_approval", result.stdout)
            self.assertIn("four_inline_git_authority_and_reason", result.stdout)
            self.assertFalse((workspace_root / "plan-sentinel").exists())
            self.assertFalse((workspace_root / "ensure-sentinel").exists())
            self.assertNotIn(
                "AGENT_CANON_PREFLIGHT_NEXT=commit_or_stash_then_run_make_agent-canon-ensure-latest",
                result.stdout,
            )

    def test_bootstrap_reports_parent_repo_latest_checklist(self) -> None:
        """Parent repos should expose the AgentCanon latest-state checklist at task start."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            seed_workspace_config(workspace_root)
            checklist = (
                workspace_root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "agent-canon"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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
                "AGENT_CANON_PREFLIGHT_CHECKLIST=vendor/agent-canon/documents/agent-canon/agent-canon-parent-repo-latest-checklist.md",
                result.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present", result.stdout
            )

    def test_bootstrap_uses_read_only_plan_with_unrelated_parent_dirty_state(
        self,
    ) -> None:
        """A clean AgentCanon update surface may refresh despite unrelated parent dirt."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = workspace_root / "reports" / "agents"
            seed_workspace_config(workspace_root)
            checklist = (
                workspace_root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "agent-canon"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            (workspace_root / "Makefile").write_text(
                "agent-canon-update-plan:\n\t@echo agent_canon_plan_route=already_current_tree\n"
                "agent-canon-ensure-latest:\n\t@touch make-sentinel\n",
                encoding="utf-8",
            )
            source_root = workspace_root / "vendor" / "agent-canon"
            materialize_derived_source_tool_unit(source_root)
            (source_root / "agents" / "skills").mkdir(parents=True)
            (source_root / "agents" / "skills" / "catalog.yaml").write_text(
                "skills: []\n",
                encoding="utf-8",
            )
            (source_root / "tools" / "sync_agent_canon.sh").write_text(
                "#!/usr/bin/env bash\nset -eu\n[ \"${1:-}\" = check ]\n",
                encoding="utf-8",
            )
            (source_root / "tools" / "sync_agent_canon.sh").chmod(0o755)
            materialize_derived_public_tool_view(workspace_root)
            subprocess.run(["git", "init"], cwd=source_root, check=True)
            subprocess.run(["git", "add", "."], cwd=source_root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Start Test",
                    "-c",
                    "user.email=bootstrap@example.invalid",
                    "commit",
                    "-m",
                    "test: seed AgentCanon source",
                ],
                cwd=source_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "add",
                    "Makefile",
                    ".codex/config.toml",
                    "vendor/agent-canon",
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
                    "user.email=bootstrap@example.invalid",
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
            with fixture_environment(workspace_root) as environment:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(BOOTSTRAP_SCRIPT),
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
                    cwd=workspace_root,
                    env=environment,
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
            self.assertFalse((workspace_root / "make-sentinel").exists())
            self.assertTrue(
                (report_root / "parent-dirty-unrelated" / "schedule.md").is_file()
            )

    def test_bootstrap_blocks_eval_transient_until_explicit_cleanup(self) -> None:
        """Eval captures stop make, remain intact, and allow a rerun after cleanup."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            seed_workspace_config(workspace_root)
            checklist = (
                workspace_root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "agent-canon"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            (workspace_root / "Makefile").write_text(
                "agent-canon-update-plan:\n\t@echo agent_canon_plan_route=already_current_tree\n"
                "agent-canon-ensure-latest:\n\t@touch make-sentinel\n",
                encoding="utf-8",
            )
            (workspace_root / "tools").mkdir()
            (workspace_root / "tools" / "sync_agent_canon.sh").write_text(
                "#!/usr/bin/env bash\nset -eu\n[ \"${1:-}\" = check ]\n",
                encoding="utf-8",
            )
            source_root = workspace_root / "vendor" / "agent-canon"
            materialize_derived_source_tool_unit(source_root)
            source_root_entrypoint = (
                source_root
                / "tools"
                / "agent_tools"
                / "agent_canon_source_root.py"
            )
            source_root_entrypoint.parent.mkdir(parents=True, exist_ok=True)
            source_root_entrypoint.write_text(
                "#!/usr/bin/env python3\n"
                "import subprocess\n"
                "import sys\n"
                "raise SystemExit(subprocess.run(['bash', *sys.argv[2:]], check=False).returncode)\n",
                encoding="utf-8",
            )
            materialize_derived_public_tool_view(workspace_root)
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)
            subprocess.run(
                ["git", "add", "."],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Task Start Test",
                    "-c",
                    "user.email=bootstrap@example.invalid",
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
            capture = (
                workspace_root
                / "reports"
                / "agent-eval-runs"
                / "eval-run"
                / "01-skill.stdout.txt"
            )
            capture.parent.mkdir(parents=True)
            capture.write_text("diagnostic evidence\n", encoding="utf-8")

            blocked = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "eval transient blocks update",
                    "--owner",
                    "codex",
                    "--run-id",
                    "eval-transient-blocked",
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

            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_STATUS=blocked_eval_transient_artifacts",
                blocked.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_EVAL_TRANSIENT_BLOCKERS="
                "generated_report_artifact_untracked_left_in_tree:"
                "reports/agent-eval-runs/eval-run/01-skill.stdout.txt",
                blocked.stdout,
            )
            self.assertIn(
                "AGENT_CANON_PREFLIGHT_NEXT="
                "sync_eval_archive_then_summarize_and_delete_transient_captures_"
                "then_rerun_preflight",
                blocked.stdout,
            )
            self.assertFalse((workspace_root / "make-sentinel").exists())
            self.assertTrue(capture.is_file())

            capture.unlink()
            resumed = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "eval transient cleanup rerun",
                    "--owner",
                    "codex",
                    "--run-id",
                    "eval-transient-resumed",
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

            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=pass", resumed.stdout)
            self.assertFalse((workspace_root / "make-sentinel").exists())

    def test_bootstrap_emits_workflow_skills_and_language_review_candidates(
        self,
    ) -> None:
        """Bootstrap exposes owner-derived routing and creates one run bundle."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "comprehensive native implementation change",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-bootstrap-routing",
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
            expected_active, expected_write = expected_workflow_spawn_budget(
                "comprehensive_development"
            )
            self.assertIn("AGENT_CANON_PREFLIGHT_STATUS=skipped_by_flag", result.stdout)
            self.assertIn("REQUEST_CONTRACT_REQUIRED=yes", result.stdout)
            self.assertIn(
                f"RUNTIME_MAX_THREADS={codex_runtime_max_threads()}", result.stdout
            )
            self.assertIn("WORKFLOW_FAMILY=comprehensive_development", result.stdout)
            self.assertIn(
                f"WORKFLOW_ACTIVE_SPAWN_BUDGET={expected_active}", result.stdout
            )
            self.assertIn(
                f"WORKFLOW_MAX_WRITE_SUBAGENTS={expected_write}", result.stdout
            )
            self.assertIn("$comprehensive-development", result.stdout)
            self.assertIn("LANGUAGE_REVIEW_CANDIDATES=cpp_reviewer", result.stdout)

            report_dir = report_root / "test-bootstrap-routing"
            self.assertTrue((report_dir / "team_manifest.yaml").is_file())
            self.assertTrue((report_dir / "user_request_contract.md").is_file())
            manifest_text = (report_dir / "team_manifest.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("comprehensive_development", manifest_text)
            self.assertIn(f"active_subagents: {expected_active}", manifest_text)
            self.assertIn(f"max_write_subagents: {expected_write}", manifest_text)


    def test_empty_registry_does_not_materialize_configured_candidates(self) -> None:
        """Configured codex_agents are candidate order, not executable availability."""
        config = load_team_config()
        catalog = load_task_catalog(config)
        roles = select_roles(
            config,
            ["implementer", "change_reviewer", "docs_workflow_steward"],
            full_team=False,
            catalog=catalog,
            workflow_family_id="comprehensive_development",
        )
        active_subagents, _max_write_subagents = workflow_spawn_budget(
            catalog,
            "comprehensive_development",
        )

        self.assertIn("worker", unique_codex_agents_for_roles(roles))

        with patch("implementation_dispatch.registered_codex_agent_types", return_value=set()):
            initial_wave = recommended_initial_subagent_wave(
                roles,
                active_subagents,
                catalog,
            )
            dynamic_waves = recommended_dynamic_expansion_wave_slots(
                roles,
                active_subagents,
                initial_wave,
                catalog,
            )
            quality_agent_types = default_quality_check_agent_types(roles)

        self.assertEqual(initial_wave, ())
        self.assertEqual(dynamic_waves, ())
        self.assertEqual(quality_agent_types, ())

    def test_bootstrap_uses_default_worker_candidate(self) -> None:
        """The implementer role should materialize the first codex_agents entry by default."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "comprehensive workflow check",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-default-worker",
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
            self.assertIn("SUBAGENT_AGENT_TYPE_SELECTIONS=none", result.stdout)
            self.assertIn(
                "implementer:implementer_worker:worker",
                result.stdout,
            )
            self.assertNotIn(
                "implementer:implementer_spark_worker:spark_worker",
                result.stdout,
            )

    def test_agent_type_selection_preserves_explicit_empty_registry(self) -> None:
        """An injected empty registry must reject every selected candidate."""
        config = load_team_config()
        implementer = next(
            role
            for role in config.always_on_roles + config.specialist_roles
            if role.id == "implementer"
        )
        selection = AgentTypeSelection(
            role_id="implementer",
            agent_type="spark_worker",
            evidence="approved-bounded-slice",
        )
        registered_agents: set[str] = set()

        with self.assertRaisesRegex(
            RuntimeError,
            "agent type selection references unregistered Codex agent: spark_worker",
        ):
            validate_agent_type_selections(
                config,
                (implementer,),
                (selection,),
                registered_agents=registered_agents,
            )

    def test_bootstrap_selects_spark_worker_with_explicit_evidence(self) -> None:
        """A later implementer candidate requires explicit parent-packet evidence."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "comprehensive workflow check",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-spark-worker",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                    "--select-agent-type",
                    "implementer=spark_worker:approved-bounded-slice",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "SUBAGENT_AGENT_TYPE_SELECTIONS=implementer=spark_worker:approved-bounded-slice",
                result.stdout,
            )
            self.assertIn(
                "implementer:implementer_spark_worker:spark_worker",
                result.stdout,
            )
            manifest = yaml.safe_load(
                (report_root / "test-spark-worker" / "team_manifest.yaml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                manifest["run"]["spawn_wave_recommendation"]["agent_type_selections"],
                [
                    {
                        "role_id": "implementer",
                        "agent_type": "spark_worker",
                        "evidence": "approved-bounded-slice",
                    }
                ],
            )

    def test_bootstrap_rejects_invalid_agent_type_selection(self) -> None:
        """Invalid role-to-agent parent-packet selections should fail closed."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "comprehensive workflow check",
                    "--task-id",
                    "T12",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-invalid-selection",
                    "--workspace-root",
                    str(workspace_root),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                    "--select-agent-type",
                    "implementer=diff_triage_reviewer:not-an-implementer",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("agent type selection for implementer must be one of", result.stdout)
            self.assertFalse((report_root / "test-invalid-selection").exists())

    def test_bootstrap_plain_fix_activates_subagent_bootstrap(self) -> None:
        """Plain fix prompts should match route.py write-capable handoff."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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

    def test_bootstrap_plain_refactor_activates_subagent_bootstrap(self) -> None:
        """Plain refactor prompts should match route.py write-capable handoff."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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
            self.assertIn("SUGGESTED_SKILLS=", result.stdout)
            self.assertIn("ACTIVE_SKILLS=", result.stdout)
            for skill in (
                "$agent-orchestration",
                "$subagent-bootstrap",
                "$task-routing",
                "$refactor-loop",
                "$structure-refactor",
            ):
                self.assertIn(skill, result.stdout)
            self.assertIn("DEFERRED_SKILLS=$codex-task-workflow", result.stdout)
            self.assertIn("IMPLEMENTATION_HANDOFF_REQUIRED=yes", result.stdout)

    def test_bootstrap_review_only_does_not_activate_subagent_bootstrap(self) -> None:
        """Review-only do-not-edit prompts should not emit implementation handoff."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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

    def test_academic_route_uses_current_bounded_dynamic_waves(self) -> None:
        """Academic routing follows the current bounded designer/worker sequence."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
            self.assertEqual(
                dynamic_waves,
                "WAVE-2=detailed_designer;WAVE-3=worker",
            )
            self.assertNotIn("ship_reviewer", dynamic_waves)
            role_instances_match = re.search(
                r"^RECOMMENDED_DYNAMIC_EXPANSION_ROLE_INSTANCES=(.+)$",
                result.stdout,
                re.M,
            )
            self.assertIsNotNone(role_instances_match)
            role_instances = cast(re.Match[str], role_instances_match).group(1)
            self.assertIn(
                "WAVE-2=designer:designer_detailed_designer:detailed_designer",
                role_instances,
            )
            self.assertIn(
                "WAVE-3=implementer:implementer_worker:worker",
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
            self.assertEqual(wave_ids, [])

    def test_large_refactor_bootstrap_suggests_refactor_skill(self) -> None:
        """Large refactor should advertise the dedicated refactor skill."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            report_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
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
            expected_active, expected_write = expected_workflow_spawn_budget(
                "large_delivery"
            )
            self.assertIn(
                f"RUNTIME_MAX_THREADS={codex_runtime_max_threads()}", result.stdout
            )
            self.assertIn("RUNTIME_MAX_DEPTH=2", result.stdout)
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn(
                f"WORKFLOW_ACTIVE_SPAWN_BUDGET={expected_active}", result.stdout
            )
            self.assertIn(
                f"WORKFLOW_MAX_WRITE_SUBAGENTS={expected_write}", result.stdout
            )
            manifest_text = (
                report_root / "test-large-refactor" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            spawn_budget = manifest["run"]["spawn_budget"]
            write_scope_policy = manifest["run"]["write_scope_policy"]
            self.assertEqual(spawn_budget["active_subagents"], expected_active)
            self.assertEqual(spawn_budget["max_write_subagents"], expected_write)
            self.assertEqual(
                spawn_budget["runtime_max_threads"], codex_runtime_max_threads()
            )
            self.assert_current_checkout_write_policy(
                write_scope_policy, expected_write
            )
            self.assertIn("spawn_budget:", manifest_text)
            self.assertIn(f"active_subagents: {expected_active}", manifest_text)
            self.assertIn(f"max_write_subagents: {expected_write}", manifest_text)
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
            self.assertIn(
                f"RUNTIME_MAX_THREADS={codex_runtime_max_threads()}", result.stdout
            )
            report_dir = workspace_root / "reports" / "agents" / run_id
            self.assertIn(f"REPORT_DIR={report_dir}", result.stdout)
            self.assertIn(
                f"TASK_AUTHORITY={report_dir / 'task_authority.yaml'}", result.stdout
            )
            self.assertTrue(report_dir.is_dir())
            self.assertTrue((report_dir / "work_log.md").is_file())
            for packet_artifact in (
                "design_brief.md",
                "design_review.md",
                "document_flow_review.md",
            ):
                self.assertTrue((report_dir / packet_artifact).is_file())
            self.assertTrue((report_dir / "task_authority.yaml").is_file())
            self.assertTrue((report_dir / "task_authority.yaml.sha256").is_file())
            self.assertTrue(
                (workspace_root / "reports" / "agents" / ".active_run.sha256").is_file()
            )
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/conventions/REVIEW_PROCESS.md", result.stdout)
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
            self.assertIn("schema: waterfall.design_packet.v1", manifest_text)
            self.assertIn("design_artifact: design_brief.md", manifest_text)
            self.assertIn("design_review_artifact: design_review.md", manifest_text)
            self.assertIn(
                "document_flow_review_artifact: document_flow_review.md",
                manifest_text,
            )
            self.assertNotIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("must_cite_before_edit: true", manifest_text)
            self.assertIn(str(report_dir / "design_brief.md"), manifest_text)
            self.assertIn("/documents/conventions/REVIEW_PROCESS.md", manifest_text)
            self.assertIn("/notes/guardrails/README.md", manifest_text)
            self.assertNotIn("/docker/README.md", manifest_text)
            self.assertIn(
                "/agents/workflows/implementation-waterfall-workflow.md", manifest_text
            )

    def test_bootstrap_custom_report_root_writes_active_run_baseline_there(
        self,
    ) -> None:
        """Custom report-root mode should baseline the active pointer it writes."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "custom-reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
        """Bootstrap projects the task catalog budget into output and manifest."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
            expected_active, expected_write = expected_workflow_spawn_budget(
                "platform_and_environment"
            )
            self.assertIn("WORKFLOW_FAMILY=platform_and_environment", result.stdout)
            self.assertIn(
                f"WORKFLOW_ACTIVE_SPAWN_BUDGET={expected_active}", result.stdout
            )
            self.assertIn(
                f"WORKFLOW_MAX_WRITE_SUBAGENTS={expected_write}", result.stdout
            )
            self.assertIn("RECOMMENDED_INITIAL_SUBAGENT_WAVE=", result.stdout)
            self.assertIn("RECOMMENDED_DYNAMIC_EXPANSION_WAVES=", result.stdout)
            self.assertIn("TASK_ID_ROUTE_STATUS=explicit", result.stdout)

            manifest = yaml.safe_load(
                (
                    report_root
                    / "test-bootstrap-spawn-budget"
                    / "team_manifest.yaml"
                ).read_text(encoding="utf-8")
            )
            spawn_budget = manifest["run"]["spawn_budget"]
            self.assertEqual(spawn_budget["active_subagents"], expected_active)
            self.assertEqual(spawn_budget["max_write_subagents"], expected_write)
            self.assertEqual(
                spawn_budget["runtime_max_threads"], codex_runtime_max_threads()
            )
            self.assert_current_checkout_write_policy(
                manifest["run"]["write_scope_policy"], expected_write
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
                    "role_id+instance_id+agent_type",
                )
                self.assertFalse(
                    same_role_instances["runtime_threads_are_cardinality_source"]
                )

    def test_bootstrap_warns_when_multi_agent_task_lacks_task_id(self) -> None:
        """A repo-wide bootstrap without --task-id should not silently lose fan-out evidence."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
                default_quality_check_policy["candidate_roles"],
                ["change_reviewer"],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["task_default_specialists"],
                [],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["language_review_candidates"],
                [],
            )
            self.assertEqual(
                default_quality_check_policy["provenance"]["default_review_pack_ids"],
                [],
            )

    def test_all_task_ids_bootstrap_with_prompt_packet(self) -> None:
        """Every catalog task should create a workflow-specific subagent prompt packet."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
                self.assertEqual(
                    subagent_prompt_packet["tool_call_tokens"],
                    "run.repo_tool_routing_policy.sequential_tool_routes[].tool_call_token",
                )
                self.assertNotIn(
                    "tool_command_packet_command", subagent_prompt_packet
                )
                self.assertNotIn("tool_commands", subagent_prompt_packet)
                self.assert_role_prompt_includes(
                    manifest,
                    "implementer",
                    {"abstract_design_frame", "design_to_implementation_trace"},
                )
                roles_by_id = {role["id"]: role for role in manifest["roles"]}
                implementer_entries = roles_by_id["implementer"]["document_packet"][
                    "role_specific_read_before_work"
                ]
                sectioned_entries = [
                    entry for entry in implementer_entries if entry.get("sections")
                ]
                self.assertTrue(sectioned_entries)
                for entry in sectioned_entries:
                    self.assertNotIn("#", entry["path"])
                    self.assertIn("sections", entry)
                workflow_entry = next(
                    entry
                    for entry in sectioned_entries
                    if entry["path"].endswith("agents/canonical/CODEX_WORKFLOW.md")
                )
                self.assertIn(
                    "5. Implementation",
                    {section["heading"] for section in workflow_entry["sections"]},
                )

    def test_worktree_start_rejects_branch_kickoff(self) -> None:
        """worktree_start.py is cleanup-only and must not create branch worktrees."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                        "- mapping_error_sets_empty: yes",
                        "- typed_owner_boundary_status: pass",
                        "- canonical_dispatcher_schema_status: pass",
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
            write_ready_completion_coverage(report_dir, run_id)
            write_ready_diff_check_artifact(report_dir)
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

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_accepts_profile_selected_targeted_static_analysis(self) -> None:
        """task_close should allow targeted static analysis selected by the risk profile."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
            self.assertIn(
                "MECHANICAL_LOOP_STATIC_ANALYSIS_STATUS=targeted",
                result.stdout,
            )

    def test_task_close_rejects_pending_profile_selected_static_analysis(self) -> None:
        """task_close should not treat targeted routing as a waiver for pending checks."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
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
                ["git", "add", "."],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
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
                        "- mapping_error_sets_empty: yes",
                        "- typed_owner_boundary_status: pass",
                        "- canonical_dispatcher_schema_status: pass",
                        *ready_closeout_evidence_lines(workspace=workspace_root),
                    ]
                ),
                encoding="utf-8",
            )
            with fixture_environment(workspace_root):
                write_ready_schedule(report_dir)
                _log_ready_work(report_dir)
                write_ready_workflow_monitoring(report_dir)
                write_ready_agent_evaluation(report_dir)
                write_ready_final_review(report_dir)
                write_ready_completion_coverage(report_dir, run_id)
                write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
                write_ready_closeout_bundle(
                    report_dir,
                    run_id,
                    workspace=workspace_root,
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(TASK_CLOSE_SCRIPT),
                        "--run-id",
                        run_id,
                    ],
                    cwd=workspace_root,
                    env=os.environ.copy(),
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("ALL_PLANNED_CHUNKS_COMPLETE=yes", result.stdout)
            self.assertIn("OVERALL_DELIVERY_COMPLETE=yes", result.stdout)
            self.assertIn("COMPLETION_COVERAGE_CONSUMER_READY=True", result.stdout)
            self.assertIn("REVIEW_FINDINGS_INTEGRATED=yes", result.stdout)
            self.assertIn("POST_FIX_FULL_REVIEW_COMPLETE=yes", result.stdout)
            self.assertIn("MECHANICAL_COMPLETION_LOOP_COMPLETE=yes", result.stdout)
            self.assertIn("SUBAGENTS_CLOSED=yes", result.stdout)
            self.assertIn("DIFF_CHECK_AGENT_COMPLETE=yes", result.stdout)
            self.assertIn("CANONICAL_TREE_HEAD_COMPLETE=yes", result.stdout)
            self.assertIn("REQUEST_CONTRACT_RESOLVED=yes", result.stdout)

    def test_task_close_rejects_placeholder_final_review(self) -> None:
        """task_close should not accept an untouched final_review.md template."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir,
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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

    def test_task_close_rejects_missing_mechanical_loop_or_diff_check(self) -> None:
        """task_close should fail when parent-only closeout skips the final diff loop."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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

    def test_task_close_accepts_bounded_existing_topology_route(self) -> None:
        """A bounded Markdown edit may close with positive existing-topology evidence."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                "# Seed\n\nUpdated.\n", encoding="utf-8"
            )
            run_id = "test-task-close-doc-existing-topology"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with fixture_environment(workspace_root) as environment:
                write_ready_closeout_bundle(
                    report_dir, run_id, workspace=workspace_root
                )
                write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
                closeout_path = report_dir / "closeout_gate.md"
                text = closeout_path.read_text(encoding="utf-8")
                replacements = {
                    "- document_structure_status: skipped": "- document_structure_status: complete",
                    "- structure_activation: format_only": "- structure_activation: not_required",
                    "- document_split_decision: not_applicable:format-only: fixture closeout bundle": "- document_split_decision: keep:existing-topology:README.md",
                    "- structure_planning: not_applicable": "- structure_planning: not_required",
                    "- prose_graph: not_applicable": "- prose_graph: not_selected",
                    "- structure_contract: skipped: fixture format-only route": "- structure_contract: not_required:existing-topology:README.md",
                    "- structure_owner: not_applicable": "- structure_owner: README.md owner",
                    "- structure_source: not_applicable": "- structure_source: README.md canonical source",
                    "- structure_reader: not_applicable": "- structure_reader: repository entry reader",
                    "- structure_layout: not_applicable": "- structure_layout: existing README layout",
                    "- structure_validation_topology: not_applicable": "- structure_validation_topology: targeted Markdown check",
                }
                for old, new in replacements.items():
                    text = text.replace(old, new)
                closeout_path.write_text(text, encoding="utf-8")

                result = subprocess.run(
                    [sys.executable, str(TASK_CLOSE_SCRIPT), "--run-id", run_id],
                    cwd=workspace_root,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=yes", result.stdout)

    def test_task_close_rejects_required_structure_route_without_identity(self) -> None:
        """Required structure activation must identify its topology and owners."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                "# Seed\n\nUpdated.\n", encoding="utf-8"
            )
            run_id = "test-task-close-doc-required-identity"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with fixture_environment(workspace_root) as environment:
                write_ready_closeout_bundle(
                    report_dir, run_id, workspace=workspace_root
                )
                write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
                closeout_path = report_dir / "closeout_gate.md"
                text = closeout_path.read_text(encoding="utf-8")
                replacements = {
                    "- document_structure_status: skipped": "- document_structure_status: complete",
                    "- structure_activation: format_only": "- structure_activation: required",
                    "- document_split_decision: not_applicable:format-only: fixture closeout bundle": "- document_split_decision: keep:README topology",
                    "- structure_planning: not_applicable": "- structure_planning: complete",
                    "- prose_graph: not_applicable": "- prose_graph: not_selected",
                    "- structure_contract: skipped: fixture format-only route": "- structure_contract: required:README topology",
                }
                for old, new in replacements.items():
                    text = text.replace(old, new)
                closeout_path.write_text(text, encoding="utf-8")

                result = subprocess.run(
                    [sys.executable, str(TASK_CLOSE_SCRIPT), "--run-id", run_id],
                    cwd=workspace_root,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=no", result.stdout)

    def test_task_close_accepts_parent_owned_nested_workspace_without_git(self) -> None:
        """A nested workspace may use the authenticated outer Git identity."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            parent_root = Path(tmp_dir) / "parent"
            parent_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=parent_root,
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
                cwd=parent_root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/task-close-parent.git",
                ],
                cwd=parent_root,
                check=True,
                capture_output=True,
                text=True,
            )
            workspace_root = parent_root / "workspace" / "nested"
            workspace_root.mkdir(parents=True, exist_ok=True)
            run_id = "parent-owned-nested-closeout"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with fixture_environment(parent_root) as environment:
                write_ready_closeout_bundle(
                    report_dir, run_id, workspace=workspace_root
                )
                write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

                outer_head = current_git_head(parent_root)
                expected_outer_diff_ref = current_diff_ref(workspace_root)
                result = subprocess.run(
                    [sys.executable, str(TASK_CLOSE_SCRIPT), "--run-id", run_id],
                    cwd=workspace_root,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn(f"REPORT_DIR={report_dir}", result.stdout)
            self.assertIn(
                f"DIFF_CHECK_CURRENT_DIFF_REF={expected_outer_diff_ref}",
                result.stdout,
            )
            self.assertTrue(expected_outer_diff_ref.startswith(outer_head))
            self.assertNotIn("Unable to resolve git HEAD", result.stderr)
            self.assertTrue(report_dir.resolve().is_relative_to(parent_root.resolve()))

    def test_task_close_rejects_stale_closeout_and_artifact_diff_ref(self) -> None:
        """task_close should compare matching closeout/artifact refs to the current diff ref."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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

    def test_task_close_allows_tracked_other_agent_run_reports(self) -> None:
        """Pre-existing tracked agent run history is baseline state."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/task-close-tracked.git",
                ],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            run_id = "test-task-close-tracked-old-agent-run"
            report_dir = workspace_root / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with fixture_environment(workspace_root) as environment:
                write_ready_closeout_bundle(
                    report_dir, run_id, workspace=workspace_root
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
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)
            self.assertNotIn(
                "report_artifact_tracked_outside_current_run", result.stdout
            )

    def test_task_close_rejects_ignored_reports_outside_run_bundle(self) -> None:
        """Ignored generated report roots are still closeout blockers."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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

    def test_task_close_accepts_mid_task_user_input_wave_checkpoint(self) -> None:
        """A classified mid-task user input checkpoint should preserve closeout readiness."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                validation_route="bootstrap",
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                validation_route="bootstrap",
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                validation_route="bootstrap",
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
                validation_route="bootstrap",
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
            self.assertIn("completion_coverage_consumer", result.stdout)
            self.assertIn("review_findings_integrated", result.stdout)

    def test_task_close_rejects_missing_post_fix_full_review_completion(self) -> None:
        """task_close should fail when review-driven fixes skipped the final full rerun."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
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
