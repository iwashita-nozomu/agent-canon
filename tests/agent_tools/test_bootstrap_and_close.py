# @dependency-start
# contract test
# responsibility Tests run bootstrap and close behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream test ../../tests/fixtures/generated_completeness/closeout_g1_g2.json freezes the G1/G2 closeout bundle.
# upstream implementation ../../tools/agent/orchestration/packets.py owns packet normalization under test
# upstream implementation ../../tools/agent/orchestration/tool_calls.py owns typed lifecycle tool calls under test
# upstream implementation ../../tools/agent/orchestration/team_config.py owns team configuration under test
# upstream implementation ../../tools/agent/orchestration/implementation_dispatch.py owns dispatch under test
# @dependency-end

"""Tests for machine-driven run bootstrap and close commands."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from atexit import register
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
G2_CLOSEOUT_FIXTURE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "generated_completeness"
    / "closeout_g1_g2.json"
)
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.agent.orchestration.implementation_dispatch import (  # noqa: E402
    default_quality_check_agent_types,
    unique_codex_agents_for_roles,
    validate_agent_type_selections,
)
from tools.agent.orchestration.packets import (  # noqa: E402
    active_design_packet_mapping,
    resolve_active_design_packet_config,
)
from tools.runtime.authority.task_authority import hash_baseline_bytes  # noqa: E402
from tools.runtime.authority.checkout_identity import resolve_checkout_identity  # noqa: E402
from tools.runtime.lifecycle.task_close import (  # noqa: E402
    _child_closeout_evidence,
    document_structure_evidence_ready,
    update_lifecycle_closeout_consumer,
)
from tools.agent.orchestration.team_config import (  # noqa: E402
    AgentTypeSelection,
    load_task_catalog,
    load_team_config,
    select_roles,
)
from tools.agent.orchestration.tool_calls import (  # noqa: E402
    CloseAgentLifecycleEvidence,
    materialize_close_agent_tool_call,
)
from tools.runtime.lifecycle.update_lifecycle_contract import (  # noqa: E402
    materialize_descendant_close_receipt,
    materialize_gate_verdict,
    materialize_reservation_release_receipt,
)
from tools.runtime.archive.work_log import append_ledger_event, read_ledger_snapshot  # noqa: E402
from tools.runtime.lifecycle.bootstrap_agent_run import (  # noqa: E402
    main as bootstrap_agent_run,
)

RUNTIME_PROFILE_INVENTORY = (
    PROJECT_ROOT / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
)
BOOTSTRAP_SCRIPT = (
    PROJECT_ROOT / "tools" / "runtime" / "lifecycle" / "bootstrap_agent_run.py"
)
TASK_CLOSE_SCRIPT = PROJECT_ROOT / "tools" / "runtime" / "lifecycle" / "task_close.py"
WORKTREE_START_SCRIPT = (
    PROJECT_ROOT / "tools" / "repository" / "workspace" / "worktree_start.py"
)
TEST_PARENT_ROOT = PROJECT_ROOT.parents[2]
# Keep test artifacts outside both the parent checkout and AgentCanon source;
# the exact process-owned root is removed when the test process exits.
_TEST_TEMP_ROOT = tempfile.TemporaryDirectory(prefix="agent-canon-bootstrap-")
TEST_TEMP_ROOT = Path(_TEST_TEMP_ROOT.name)
register(_TEST_TEMP_ROOT.cleanup)


def seed_workspace_config(workspace_root: Path) -> None:
    """Seed parent state only; AgentCanon source stays outside the fixture."""
    config_path = workspace_root / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_bytes((PROJECT_ROOT / ".codex" / "config.toml").read_bytes())


def snapshot_external_source(source_root: Path) -> tuple[tuple[str, str, int], ...]:
    """Capture external source bytes/modes while ignoring its Git metadata."""
    entries: list[tuple[str, str, int]] = []
    for path in sorted(source_root.rglob("*")):
        if path.is_symlink() or ".git" in path.parts or not path.is_file():
            continue
        entries.append(
            (
                str(path.relative_to(source_root)),
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mode & 0o777,
            )
        )
    return tuple(entries)


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
    bundle = json.loads(G2_CLOSEOUT_FIXTURE.read_text(encoding="utf-8"))
    context = bundle["contexts"][0]
    binding = deepcopy(context["binding"])
    gates: list[dict[str, object]] = deepcopy(context["gate_verdicts"])
    gate_contracts = {
        "G3": (
            "pr_identity_cas",
            PROJECT_ROOT / "tools" / "repository" / "github" / "github_publish.py",
            "materialize_pr_identity_gate",
        ),
        "G4": (
            "standalone_source_branch_integrity",
            PROJECT_ROOT
            / "tools"
            / "repository"
            / "workspace"
            / "repository_topic_clone.py",
            "_ensure_branch",
        ),
        "G5": (
            "remote_publication_readback",
            PROJECT_ROOT
            / "tools"
            / "repository"
            / "github"
            / "publication_integrator.py",
            "integrate_publication",
        ),
    }
    for index, gate_id in enumerate(("G3", "G4", "G5"), 2):
        evidence_refs = [
            cast("dict[str, object]", gate["binding"])["evidence_ref"] for gate in gates
        ]
        ordered_inputs = {
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
        "descendants_closed_evidence_ref": closeout["descendants_closed_evidence_ref"],
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


def initialize_clean_workspace(workspace: Path) -> None:
    """Create a clean Git checkout for no-change task-close fixtures."""
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q"],
        cwd=workspace,
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
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )


def mark_diff_check_not_applicable(report_dir: Path) -> None:
    """Mark an existing fixture as an explicitly unselected diff-check route."""
    closeout_path = report_dir / "closeout_gate.md"
    replacements = {
        "- required_reviews_complete: yes": "- required_reviews_complete: not_applicable",
        "- diff_check_agent_complete: yes": "- diff_check_agent_complete: not_applicable",
        "- diff_check_agent_role: reviewer": "- diff_check_agent_role: not_applicable",
        "- diff_check_agent_decision: approve": "- diff_check_agent_decision: not_applicable",
        "- diff_check_artifact: diff_check_review.md": "- diff_check_artifact: not_applicable",
    }
    lines = []
    for line in closeout_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- diff_check_latest_diff_ref: "):
            line = "- diff_check_latest_diff_ref: not_applicable"
        lines.append(replacements.get(line, line))
    closeout_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
        "## AgentCanon Source Evidence",
        "- agent_canon_source_checkout: standalone",
        "- agent_canon_source_status: inspected",
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
        "## Subagent Lifecycle Evidence",
        "- subagent_closeout_status: closed",
        "- open_subagent_instances: none",
        "- close_agent_evidence: orchestrator_no_open_subagents",
        "",
        "## Diff-Check Agent Evidence",
        "- diff_check_agent_role: reviewer",
        "- diff_check_agent_decision: approve",
        f"- diff_check_latest_diff_ref: {latest_diff_ref}",
        "- diff_check_artifact: diff_check_review.md",
        "",
        "## Runtime Log Archive Evidence",
        "- runtime_log_archive_sync_command: python3 tools/runtime/archive/runtime_log_archive_git.py sync",
        "- runtime_log_archive_sync_status: pass",
        (
            "- runtime_log_archive_check_clean_command: "
            "python3 tools/runtime/archive/runtime_log_archive_git.py check-clean --porcelain"
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
    """Write optional schedule prose without a machine task-stage ledger."""
    (report_dir / "schedule.md").write_text("# Schedule\n", encoding="utf-8")


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
                "## Behavior Events",
                "",
                "- tool_call=observed result=completed",
                "",
                "## Tool Warnings",
                "",
                "- tool_warnings_status: none",
                "",
            ]
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


def write_ready_closeout_bundle(
    report_dir: Path,
    run_id: str,
    workspace: Path = PROJECT_ROOT,
    *,
    commit_created: str = "yes",
    push_completed: str = "yes",
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
    runtime_dir = report_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    verifier_receipt = {
        "schema": "agent-canon.verifier-receipt.v1",
        "role_id": "verifier",
        "runtime_agent_id": "verifier-1",
        "status": "pass",
        "source_event_ids": ["verification-event-1"],
        "receipt_sha256": "",
    }
    verifier_unsigned = dict(verifier_receipt)
    verifier_unsigned.pop("receipt_sha256")
    verifier_receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            verifier_unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    (runtime_dir / "verifier_receipt.json").write_text(
        json.dumps(verifier_receipt, sort_keys=True) + "\n", encoding="utf-8"
    )
    parent_evidence = {
        "schema": "agent-canon.parent-mutation-evidence.v1",
        "status": "no_parent_mutation",
        "parent_agent_id": "parent-1",
        "source_event_ids": ["mutation-event-1"],
        "mutation_event_ids": [],
        "event_ledger_ref": "runtime/hook_events.jsonl",
        "receipt_sha256": "",
    }
    parent_unsigned = dict(parent_evidence)
    parent_unsigned.pop("receipt_sha256")
    parent_evidence["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            parent_unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    (runtime_dir / "parent_mutation_evidence.json").write_text(
        json.dumps(parent_evidence, sort_keys=True) + "\n", encoding="utf-8"
    )
    (runtime_dir / "hook_events.jsonl").write_text(
        json.dumps(
            {
                "hook_run_id": "mutation-event-1",
                "mutation_control": {"status": "not_applicable", "mutation": False},
            },
            sort_keys=True,
        )
        + "\n",
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
                "- verifier_role_id: verifier",
                "- verifier_runtime_agent_id: verifier-1",
                "- verifier_receipt_ref: runtime/verifier_receipt.json",
                "- parent_mutation_status: no_parent_mutation",
                "- parent_mutation_evidence_ref: runtime/parent_mutation_evidence.json",
                "- required_reviews_complete: yes",
                "- validation_complete: yes",
                "- request_contract_complete: yes",
                "- overall_delivery_complete: yes",
                "- dependency_headers_complete: yes",
                "- repo_wide_dependency_tools_complete: yes",
                "- repo_wide_static_analysis_complete: yes",
                "- agent_canon_latest_complete: yes",
                "- review_findings_integrated: yes",
                "- focused_recheck_complete: yes",
                "- tool_warnings_resolved: yes",
                "- subagents_closed: yes",
                "- diff_check_agent_complete: yes",
                "- canonical_tree_head_complete: yes",
                "- agent_evaluation_complete: yes",
                "- runtime_log_archive_synced: yes",
                f"- commit_created: {commit_created}",
                f"- push_completed: {push_completed}",
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
    write_ready_workflow_monitoring(report_dir)
    write_ready_agent_evaluation(report_dir)
    write_ready_final_review(report_dir)


class BootstrapAndCloseTest(unittest.TestCase):
    """Verify machine-driven task start and close behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        """Give external fixture artifacts one exact authenticated Git root."""
        subprocess.run(
            ["git", "init", "-q"],
            cwd=TEST_TEMP_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def setUp(self) -> None:
        """Place isolated fixtures under one authenticated parent checkout."""
        shutil.rmtree(TEST_TEMP_ROOT / "reports", ignore_errors=True)
        parent_env = patch.dict(
            os.environ,
            {
                "AGENT_CANON_PARENT_ROOT": str(PROJECT_ROOT),
                "AGENT_CANON_RUNTIME_ROOT": str(TEST_TEMP_ROOT),
            },
        )
        parent_env.start()
        self.addCleanup(parent_env.stop)

    def test_retired_tool_names_are_not_permanent_update_surfaces(self) -> None:
        """Retired repository synchronization wrappers are absent."""
        self.assertFalse((PROJECT_ROOT / "tools" / "sync_agent_canon.sh").exists())
        self.assertFalse((PROJECT_ROOT / "tools" / "update_agent_canon.sh").exists())

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

        self.assertEqual(
            decision["reason"], "close_agent:cleanup_before_remote_readback"
        )

    def test_update_lifecycle_rejects_missing_gate_receipt(self) -> None:
        """Terminal close requires the ordered complete G1-G6 boundary set."""
        payload = update_lifecycle_closeout_fixture()
        gates = cast("list[dict[str, object]]", payload["gate_verdicts"])
        gates.pop()

        decision = self.consume_update_lifecycle_fixture(payload)

        self.assertEqual(
            decision["reason"], "close_agent:all_six_gate_evidence_required"
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

        manifest_text = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
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

    def test_bootstrap_uses_source_workspace_without_classification(self) -> None:
        """Source AgentCanon runs do not require a derived-repo update target."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            source_root = PROJECT_ROOT
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "source canon workspace smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "source-canon-workspace",
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
                {
                    key: value
                    for key, value in U2_ACTIVE_DESIGN_PACKET.items()
                    if key != "document_flow_review_artifact"
                },
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

    def test_bootstrap_does_not_adopt_embedded_parent_agentcanon_state(self) -> None:
        """A source-free parent never acquires an embedded update workflow."""
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
                "unexpected-parent-agentcanon-command:\n\t@touch plan-sentinel ensure-sentinel\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "shared canon workspace route",
                    "--owner",
                    "codex",
                    "--run-id",
                    "shared-canon-workspace",
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
            self.assertFalse((workspace_root / "plan-sentinel").exists())
            self.assertFalse((workspace_root / "ensure-sentinel").exists())

    def test_bootstrap_uses_workspace_without_git_or_checklist_classification(
        self,
    ) -> None:
        """Git and checklist presence are not task-entry routing inputs."""
        for git_workspace, checklist_present in (
            (False, False),
            (False, True),
            (True, False),
            (True, True),
        ):
            with self.subTest(
                git_workspace=git_workspace, checklist_present=checklist_present
            ):
                with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
                    workspace_root = Path(tmp_dir) / "workspace"
                    report_root = Path(tmp_dir) / "reports"
                    seed_workspace_config(workspace_root)
                    if git_workspace:
                        subprocess.run(
                            ["git", "init", "-q"], cwd=workspace_root, check=True
                        )
                    if checklist_present:
                        checklist = (
                            workspace_root
                            / "documents/agent-canon/agent-canon-parent-repo-latest-checklist.md"
                        )
                        checklist.parent.mkdir(parents=True)
                        checklist.write_text("# Checklist\n", encoding="utf-8")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(BOOTSTRAP_SCRIPT),
                            "--task",
                            "selected workspace smoke",
                            "--owner",
                            "codex",
                            "--run-id",
                            "selected-workspace",
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
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertIn(f"WORKSPACE_ROOT={workspace_root}", result.stdout)
                    self.assertTrue(
                        (
                            report_root / "selected-workspace/team_manifest.yaml"
                        ).is_file()
                    )
                    monitoring = (
                        report_root / "selected-workspace/workflow_monitoring.md"
                    ).read_text(encoding="utf-8")
                    self.assertIn(
                        "web_research_not_required: bootstrap does not decide external research",
                        monitoring,
                    )

    def test_bootstrap_ignores_external_clone_for_source_free_parent(
        self,
    ) -> None:
        """Parent task entry neither runs nor mutates a separately selected clone."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            runtime_root = (
                workspace_root
                / "workspace"
                / "agent-canon-runtime"
                / "parent-dirty-unrelated"
            )
            report_root = runtime_root / "reports" / "agents"
            seed_workspace_config(workspace_root)
            checklist = (
                workspace_root
                / "documents"
                / "agent-canon"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            (workspace_root / "Makefile").write_text(
                "unexpected-parent-agentcanon-command:\n\t@touch make-sentinel\n",
                encoding="utf-8",
            )
            # AgentCanon is selected from an ignored external development
            # clone.  The parent fixture must not grow a vendor checkout or a
            # source projection merely to start a run.
            source_root = (
                workspace_root / "workspace" / "agent-canondevelop" / "agent-canon"
            )

            def ignore_source_links(path: str, names: list[str]) -> list[str]:
                """Do not reproduce source projections or dangling links."""
                ignored = set(
                    shutil.ignore_patterns(
                        ".git",
                        ".pytest_cache",
                        ".ruff_cache",
                        ".mypy_cache",
                        "__pycache__",
                        "target",
                        "tests",
                    )(path, names)
                )
                ignored.update(
                    name for name in names if (Path(path) / name).is_symlink()
                )
                return sorted(ignored)

            shutil.copytree(
                PROJECT_ROOT,
                source_root,
                ignore=ignore_source_links,
            )
            subprocess.run(["git", "init", "-q"], cwd=source_root, check=True)
            subprocess.run(
                ["git", "config", "user.name", "AgentCanon Source Fixture"],
                cwd=source_root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "source@example.invalid"],
                cwd=source_root,
                check=True,
            )
            subprocess.run(["git", "add", "-A"], cwd=source_root, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "fixture: standalone AgentCanon source"],
                cwd=source_root,
                check=True,
            )
            source_before = snapshot_external_source(source_root)
            subprocess.run(["git", "init"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "add",
                    "Makefile",
                    ".codex/config.toml",
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
            environment = dict(os.environ)
            environment.update(
                {
                    "AGENT_CANON_PARENT_ROOT": str(workspace_root),
                    "AGENT_CANON_SOURCE_ROOT": str(source_root),
                    "AGENT_CANON_ROOT": str(source_root),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )

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
                    "--runtime-root",
                    str(runtime_root),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
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
            self.assertFalse((workspace_root / "make-sentinel").exists())
            self.assertEqual(source_before, snapshot_external_source(source_root))
            self.assertTrue(
                (report_root / "parent-dirty-unrelated" / "schedule.md").is_file()
            )

    def test_source_free_parent_diagnostics_do_not_trigger_canon_sync(self) -> None:
        """Parent-local diagnostics remain parent-owned and do not trigger canon sync."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = Path(tmp_dir) / "reports"
            seed_workspace_config(workspace_root)
            checklist = (
                workspace_root
                / "documents"
                / "agent-canon"
                / "agent-canon-parent-repo-latest-checklist.md"
            )
            checklist.parent.mkdir(parents=True)
            checklist.write_text("# Checklist\n", encoding="utf-8")
            (workspace_root / "Makefile").write_text(
                "unexpected-parent-agentcanon-command:\n\t@touch make-sentinel\n",
                encoding="utf-8",
            )
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
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("REQUEST_CONTRACT_REQUIRED=yes", result.stdout)
            self.assertIn("WORKFLOW_FAMILY=comprehensive_development", result.stdout)
            self.assertIn("ADVERSARIAL_REQUIRED=yes", result.stdout)
            self.assertIn("terra:terra_terra:terra", result.stdout)
            self.assertIn(
                "START_DECLARATION=workflow=Comprehensive Development", result.stdout
            )
            start_declaration = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("START_DECLARATION=")
            )
            self.assertIn("terra", start_declaration)
            self.assertIn("$comprehensive-development", result.stdout)
            self.assertIn("LANGUAGE_REVIEW_CANDIDATES=cpp_reviewer", result.stdout)

            report_dir = report_root / "test-bootstrap-routing"
            self.assertTrue((report_dir / "team_manifest.yaml").is_file())
            self.assertTrue((report_dir / "user_request_contract.md").is_file())
            manifest_text = (report_dir / "team_manifest.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("comprehensive_development", manifest_text)
            self.assertNotIn("execution_graph:", manifest_text)
            self.assertNotIn("capacity_request:", manifest_text)
            terra_start = manifest_text.index("  - id: terra")
            terra_end = manifest_text.find("\n  - id: ", terra_start + 1)
            terra_block = manifest_text[terra_start:terra_end]
            self.assertIn("mode: read_only", terra_block)
            monitoring_text = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )
            self.assertRegex(monitoring_text, r"review=.*terra")

    def test_bootstrap_bounded_route_keeps_terra_inactive(self) -> None:
        """T1's ordinary typed route has no implicit cross-owner Terra wave."""
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
                    "local bounded fix",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-bootstrap-bounded-terra",
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

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ADVERSARIAL_REQUIRED=no", result.stdout)
            self.assertNotIn("terra:terra_terra:terra", result.stdout)
            self.assertNotIn(
                "terra",
                next(
                    line
                    for line in result.stdout.splitlines()
                    if line.startswith("START_DECLARATION=")
                ),
            )

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
        self.assertIn("worker", unique_codex_agents_for_roles(roles))

        with patch(
            "tools.agent.orchestration.implementation_dispatch.registered_codex_agent_types",
            return_value=set(),
        ):
            quality_agent_types = default_quality_check_agent_types(roles)

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
            self.assertNotIn("execution_graph", manifest["run"])
            self.assertIn("implementer", {role["id"] for role in manifest["roles"]})

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
                    "--select-agent-type",
                    "implementer=diff_triage_reviewer:not-an-implementer",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "agent type selection for implementer must be one of", result.stdout
            )
            self.assertFalse((report_root / "test-invalid-selection").exists())

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
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("$refactor-loop", result.stdout)
            self.assertNotIn("ACTIVE_SKILLS=", result.stdout)
            self.assertNotIn("DEFERRED_SKILLS=", result.stdout)
            manifest_text = (
                report_root / "test-large-refactor" / "team_manifest.yaml"
            ).read_text(encoding="utf-8")
            manifest = yaml.safe_load(manifest_text)
            self.assertNotIn("spawn_budget", manifest["run"])
            self.assertEqual(
                manifest["run"]["writer_target_policy"]["required_for"],
                "write_capable_handoffs",
            )

    def test_bootstrap_defaults_report_root_to_external_runtime(self) -> None:
        """bootstrap_agent_run defaults report output below external runtime."""
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
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                (TEST_TEMP_ROOT / "reports" / "agents" / ".active_run.sha256").is_file()
            )
            self.assertIn("CROSS_CUTTING_DOCUMENT_PACKET=", result.stdout)
            self.assertIn("/documents/conventions/REVIEW_PROCESS.md", result.stdout)
            self.assertIn("/notes/guardrails/README.md", result.stdout)
            self.assertNotIn("/docker/README.md", result.stdout)
            self.assertIn("/agents/skills/codex-task-workflow.md", result.stdout)
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
            self.assertIn("/agents/skills/codex-task-workflow.md", manifest_text)

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

    def test_task_workflow_context_roundtrips_through_the_active_hook_report(
        self,
    ) -> None:
        """The selected task family is stored in and read from its active run bundle."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            report_root = workspace_root / "reports" / "agents"
            hook_runtime = Path(tmp_dir) / "hook-runtime"
            workspace_root.mkdir(parents=True)
            seed_workspace_config(workspace_root)
            parent_root = Path(tmp_dir)
            subprocess.run(["git", "init", "-q", str(parent_root)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent_root),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/workflow-context-fixture.git",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(parent_root),
                    "-c",
                    "user.name=fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "--allow-empty",
                    "-qm",
                    "initialize workflow context fixture",
                ],
                check=True,
            )
            run_id = "test-workflow-context"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "workflow context producer to active hook reader",
                    "--task-id",
                    "T1",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
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
            report_dir = report_root / run_id
            context_path = report_dir / "skill_usage_context.json"
            stored_context = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(stored_context["workflows"], ["owner_bounded_change"])
            self.assertEqual(
                stored_context["source_event"], "bootstrap_agent_run.task_id"
            )
            stale_root_context = workspace_root / "skill_usage_context.json"
            stale_root_context.write_text(
                json.dumps(
                    {
                        "schema": "agent-canon.workflow-context.v1",
                        "workflows": ["stale-root-context"],
                        "timestamp": "stale",
                        "source_event": "legacy-root-path",
                    }
                ),
                encoding="utf-8",
            )
            hook_result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / ".codex/hooks/hook_dispatcher.py"),
                    "UserPromptSubmit",
                ],
                cwd=workspace_root,
                input=json.dumps({"hookEventName": "UserPromptSubmit"}),
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_HOOK_SOURCE_ROOT": str(workspace_root),
                    "AGENT_CANON_PARENT_ROOT": str(parent_root),
                    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": str(parent_root),
                    "AGENT_CANON_RUNTIME_ROOT": str(hook_runtime),
                },
            )

            self.assertEqual(hook_result.returncode, 0, hook_result.stderr)
            events = []
            for event_path in hook_runtime.rglob("*.json"):
                try:
                    event = json.loads(event_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(event, dict) and "hook_run_id" in event:
                    events.append(event)
            self.assertEqual(len(events), 1)
            self.assertEqual(
                events[0].get("workflow_context_workflows"),
                ["owner_bounded_change"],
                events[0],
            )
            self.assertEqual(
                events[0]["workflow_context_source_event"],
                "bootstrap_agent_run.task_id",
            )
            self.assertEqual(events[0]["workflow_attribution_kind"], "context")
            self.assertEqual(events[0]["workflow_monitor_report_dir"], str(report_dir))

    def test_task_catalog_workflow_families_define_role_sets(self) -> None:
        """Family role choices and same-role writer semantics remain declared."""
        catalog = yaml.safe_load(
            (PROJECT_ROOT / "agents" / "task_catalog.yaml").read_text(encoding="utf-8")
        )

        role_topology = catalog["role_topology_defaults"]
        same_role_instances = role_topology["same_role_parallel_instances"]
        self.assertIn("implementation", role_topology["role_families"])
        self.assertIn("review", role_topology["role_families"])
        self.assertEqual(same_role_instances["status"], "allowed_with_distinct_packets")
        self.assertEqual(
            same_role_instances["identity_key"], "role_id+instance_id+agent_type"
        )
        self.assertFalse(same_role_instances["runtime_threads_are_cardinality_source"])
        for workflow_family in catalog["workflow_families"]:
            with self.subTest(workflow_family=workflow_family["id"]):
                roles = workflow_family["roles"]
                self.assertIsInstance(roles.get("always_on"), list)
                self.assertIsInstance(roles.get("specialists"), list)

    def test_bootstrap_without_task_id_is_not_blocked_by_task_graph(self) -> None:
        """Optional task-catalog selection does not gate ordinary run-bundle creation."""
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
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("START_DECLARATION=workflow=Unspecified", result.stdout)
            self.assertIn("TASK_ID_ROUTE_STATUS=missing", result.stdout)
            self.assertNotIn("TASK_ID_ROUTE_REQUIRED_FOR_MULTI_AGENT", result.stdout)
            self.assertNotIn("EXECUTION_GRAPH", result.stdout)
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
            self.assertNotIn(
                "implementation_handoff_required",
                contract_complete_implementation_policy,
            )
            self.assertNotIn(
                "parent_repo_edits_allowed", contract_complete_implementation_policy
            )
            self.assertNotIn(
                "parent_orchestration_only", contract_complete_implementation_policy
            )
            self.assertNotIn(
                "write_capable_child_required", contract_complete_implementation_policy
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
                default_quality_check_policy["provenance"][
                    "language_review_candidates"
                ],
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
                    ],
                    cwd=PROJECT_ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                manifest_text = (report_root / run_id / "team_manifest.yaml").read_text(
                    encoding="utf-8",
                )
                self.assertIn("subagent_prompt_packet:", manifest_text)
                self.assertIn("prompt_preamble:", manifest_text)
                self.assertIn("workflow_focus:", manifest_text)
                self.assertIn("reviewer_prompt:", manifest_text)
                self.assertIn("subagent_lifecycle_policy:", manifest_text)
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
                    subagent_prompt_packet["native_argv"],
                    "run.repo_tool_routing_policy",
                )
                self.assertNotIn("tool_command_packet_command", subagent_prompt_packet)
                self.assertNotIn("tool_commands", subagent_prompt_packet)
                # The configured physical requirements_organizer is read-only;
                # it returns its assigned result inline without parent operations.
                roles_by_id = {role["id"]: role for role in manifest["roles"]}
                manager_prompt = roles_by_id["manager"]["prompt_contract"][
                    "assignment_prompt"
                ]
                self.assertIn("inline handoff", manager_prompt)
                self.assertIn("non-goals", manager_prompt)
                self.assertIn("completion conditions", manager_prompt)
                self.assertIn(
                    "The parent owns choosing the next instruction from linked task guidance",
                    manager_prompt,
                )
                self.assertIn("return its actual result inline", manager_prompt)
                self.assertIn("when present", manager_prompt)
                self.assertIn("respect supplied path boundaries", manager_prompt)
                self.assertIn(
                    "bounded writer when the physical sandbox and handoff permit writes; "
                    "otherwise inline handoff",
                    manager_prompt,
                )
                self.assert_role_prompt_includes(
                    manifest,
                    "implementer",
                    {"abstract_design_frame", "design_to_implementation_trace"},
                )
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
                    if entry["path"].endswith(
                        "agents/canonical/CODEX_IMPLEMENTATION.md"
                    )
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cleanup diagnostic only", result.stderr)
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
            parent_root = Path(tmp_dir) / "parent"
            workspace_root = parent_root
            report_root = parent_root / "reports" / "agents"
            workspace_root.mkdir(parents=True, exist_ok=True)
            report_root.mkdir(parents=True, exist_ok=True)
            seed_workspace_config(workspace_root)
            subprocess.run(
                ["git", "init", "-q", "--initial-branch=test/closeout"],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Task Close Test"],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "task-close@example.invalid"],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/iwashita-nozomu/agent-canon.git",
                ],
                cwd=workspace_root,
                check=True,
            )
            subprocess.run(["git", "add", "-A"], cwd=workspace_root, check=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "--quiet",
                    "-m",
                    "test: seed task close workspace",
                ],
                cwd=workspace_root,
                check=True,
            )
            environment = {
                **os.environ,
                "AGENT_CANON_PARENT_ROOT": str(parent_root),
            }
            run_id = "test-task-close-ready"
            report_dir = report_root / run_id
            args = [
                "--task",
                "closeout ready smoke",
                "--task-id",
                "T12",
                "--owner",
                "codex",
                "--run-id",
                run_id,
                "--workspace-root",
                str(workspace_root),
                "--report-root",
                str(report_root),
            ]
            bootstrap_output = io.StringIO()
            with (
                patch.dict(os.environ, environment),
                redirect_stdout(bootstrap_output),
            ):
                bootstrap_code = bootstrap_agent_run(args)
            self.assertEqual(bootstrap_code, 0, bootstrap_output.getvalue())
            manifest_path = report_dir / "team_manifest.yaml"
            self.assertTrue(manifest_path.is_file())
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn("execution_graph", manifest["run"])
            verification_path = report_dir / "verification.txt"
            verification_path.write_text(
                "\n".join(
                    [
                        f"run_id={run_id}",
                        "task=closeout ready smoke",
                        "owner=codex",
                        "created_at_utc=2026-04-08T00:00:00Z",
                        "status=pass",
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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: yes",
                        "- focused_recheck_complete: yes",
                        "- tool_warnings_resolved: yes",
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
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_final_review(report_dir)
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)
            write_ready_closeout_bundle(report_dir, run_id, workspace=workspace_root)
            verification_lines = [
                line
                for line in verification_path.read_text(encoding="utf-8").splitlines()
                if not line.startswith("user_completion_report=")
            ]
            verification_path.write_text(
                "\n".join(verification_lines) + "\n",
                encoding="utf-8",
            )
            self.assertNotIn(
                "user_completion_report=",
                verification_path.read_text(encoding="utf-8"),
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=workspace_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

            verification_path.write_text(
                verification_path.read_text(encoding="utf-8").replace(
                    "status=pass", "status=pending"
                ),
                encoding="utf-8",
            )
            pending_verification = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=workspace_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(pending_verification.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", pending_verification.stdout)
            self.assertIn("verification_status", pending_verification.stdout)
            self.assertNotIn("verification_unlock", pending_verification.stdout)

    def test_task_close_rejects_forged_verifier_or_parent_evidence(self) -> None:
        """Closeout cannot pass with a forged child receipt or mutation claim."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-forged-child-evidence"
            report_dir = report_root / run_id
            report_root.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            verifier = report_dir / "runtime" / "verifier_receipt.json"
            verifier.write_text(
                verifier.read_text(encoding="utf-8").replace("verifier-1", "forged"),
                encoding="utf-8",
            )
            ready, blockers = _child_closeout_evidence(
                report_dir,
                {
                    "verifier_role_id": "verifier",
                    "verifier_runtime_agent_id": "verifier-1",
                    "verifier_receipt_ref": "runtime/verifier_receipt.json",
                    "parent_mutation_status": "no_parent_mutation",
                    "parent_mutation_evidence_ref": "runtime/parent_mutation_evidence.json",
                },
            )
            self.assertFalse(ready)
            self.assertIn("runtime_verifier_receipt_invalid", blockers)

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
                "- selected_validation_status: pass",
                "- selected_validation_status: pass",
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
                "REPO_WIDE_STATIC_ANALYSIS_COMPLETE=profile_selected",
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
                "- selected_validation_status: pass",
                "- selected_validation_status: pending",
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
            self.assertIn("selected_validation_status", result.stdout)

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
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: yes",
                        "- focused_recheck_complete: yes",
                        "- tool_warnings_resolved: yes",
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
            write_ready_schedule(report_dir)
            _log_ready_work(report_dir)
            write_ready_workflow_monitoring(report_dir)
            write_ready_agent_evaluation(report_dir)
            write_ready_final_review(report_dir)
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
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
            self.assertIn("FOCUSED_RECHECK_COMPLETE=yes", result.stdout)
            self.assertIn("SUBAGENT_CLOSEOUT_STATUS=closed", result.stdout)
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

    def test_task_close_requires_actual_child_close_and_diff_check(self) -> None:
        """Closeout checks actual child lifecycle and selected diff review, not graph convergence."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-missing-child-close-and-diff-check"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_text = closeout_path.read_text(encoding="utf-8")
            closeout_path.write_text(
                closeout_text.replace(
                    "- subagents_closed: yes\n- diff_check_agent_complete: yes",
                    "- subagents_closed: no\n- diff_check_agent_complete: no",
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
                    "- close_agent_evidence: orchestrator_no_open_subagents",
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

    def test_task_close_accepts_unselected_diff_check_on_clean_no_change_workspace(
        self,
    ) -> None:
        """An unselected diff-check is valid only for a clean no-change checkout."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            workspace_root = root / "workspace"
            initialize_clean_workspace(workspace_root)
            report_dir = root / "reports" / "test-task-close-no-change"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(
                report_dir,
                "test-task-close-no-change",
                workspace_root,
                commit_created="not_applicable",
                push_completed="not_applicable",
            )
            mark_diff_check_not_applicable(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=workspace_root,
                env={
                    **os.environ,
                    "AGENT_CANON_PARENT_ROOT": str(workspace_root),
                    "AGENT_CANON_RUNTIME_ROOT": str(TEST_TEMP_ROOT),
                },
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)
            self.assertIn("DIFF_CHECK_AGENT_COMPLETE=not_applicable", result.stdout)

    def test_task_close_rejects_uncompleted_selected_push(self) -> None:
        """A selected push that remains incomplete keeps closeout blocked."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            workspace_root = root / "workspace"
            initialize_clean_workspace(workspace_root)
            report_dir = root / "reports" / "test-task-close-push-pending"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(
                report_dir,
                "test-task-close-push-pending",
                workspace_root,
                push_completed="no",
            )
            mark_diff_check_not_applicable(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=workspace_root,
                env={
                    **os.environ,
                    "AGENT_CANON_PARENT_ROOT": str(workspace_root),
                    "AGENT_CANON_RUNTIME_ROOT": str(TEST_TEMP_ROOT),
                },
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("push_completed", result.stdout)

    def test_task_close_rejects_unselected_diff_check_on_dirty_workspace(self) -> None:
        """A dirty checkout cannot use an unselected diff-check closeout."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            root = Path(tmp_dir)
            workspace_root = root / "workspace"
            initialize_clean_workspace(workspace_root)
            (workspace_root / "changed.txt").write_text("changed\n", encoding="utf-8")
            report_dir = root / "reports" / "test-task-close-dirty-no-change"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(
                report_dir, "test-task-close-dirty-no-change", workspace_root
            )
            mark_diff_check_not_applicable(report_dir)

            result = subprocess.run(
                [
                    sys.executable,
                    str(TASK_CLOSE_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                ],
                cwd=workspace_root,
                env={
                    **os.environ,
                    "AGENT_CANON_PARENT_ROOT": str(workspace_root),
                    "AGENT_CANON_RUNTIME_ROOT": str(TEST_TEMP_ROOT),
                },
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("diff_check_not_applicable_route", result.stdout)

    def test_task_close_rejects_incomplete_selected_validation_evidence(self) -> None:
        """task_close requires the selected validation evidence to be complete."""
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            run_id = "test-task-close-incomplete-mechanical-loop"
            report_dir = report_root / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            write_ready_closeout_bundle(report_dir, run_id)
            closeout_path = report_dir / "closeout_gate.md"
            closeout_path.write_text(
                closeout_path.read_text(encoding="utf-8").replace(
                    "- selected_validation_status: pass",
                    "- selected_validation_status: missing",
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
            self.assertIn("selected_validation_status", result.stdout)

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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DOCUMENT_STRUCTURE_STATUS=complete", result.stdout)
            self.assertIn("DOCUMENT_STRUCTURE_EVIDENCE=no", result.stdout)

    def test_document_structure_evidence_checks_graph_only_when_fields_are_supplied(
        self,
    ) -> None:
        """Graph closeout values are conditional evidence, not a selection detector."""
        evidence = {
            "document_structure_paths": "README.md",
            "document_structure_status": "complete",
            "structure_activation": "not_required",
            "document_split_decision": "keep:existing-topology:README.md",
            "structure_planning": "not_required",
            "structure_contract": "not_required:existing-topology:README.md",
            "structure_owner": "README.md owner",
            "structure_source": "README.md canonical source",
            "structure_reader": "repository entry reader",
            "structure_layout": "existing README layout",
            "structure_validation_topology": "targeted Markdown check",
        }

        self.assertTrue(document_structure_evidence_ready(["README.md"], evidence)[2])

        evidence["prose_graph_activation"] = "selected"
        evidence["prose_graph"] = "pending"
        self.assertFalse(document_structure_evidence_ready(["README.md"], evidence)[2])

        evidence["prose_graph"] = "complete"
        self.assertTrue(document_structure_evidence_ready(["README.md"], evidence)[2])

    def test_task_close_accepts_existing_topology_without_graph_selection_record(
        self,
    ) -> None:
        """A bounded Markdown edit closes without recording graph non-selection."""
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
            run_id = "test-task-close-doc-existing-topology-no-graph-record"
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            environment = {**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)}
            with patch.dict(
                os.environ, {"AGENT_CANON_PARENT_ROOT": str(workspace_root)}
            ):
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
                "- structure_contract: skipped: fixture format-only route": "- structure_contract: not_required:existing-topology:README.md",
                "- structure_owner: not_applicable": "- structure_owner: README.md owner",
                "- structure_source: not_applicable": "- structure_source: README.md canonical source",
                "- structure_reader: not_applicable": "- structure_reader: repository entry reader",
                "- structure_layout: not_applicable": "- structure_layout: existing README layout",
                "- structure_validation_topology: not_applicable": "- structure_validation_topology: targeted Markdown check",
            }
            for old, new in replacements.items():
                text = text.replace(old, new)
            text = text.replace("- prose_graph_activation: not_selected\n", "")
            text = text.replace("- prose_graph: not_applicable\n", "")
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            environment = {**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)}
            with patch.dict(
                os.environ, {"AGENT_CANON_PARENT_ROOT": str(workspace_root)}
            ):
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with patch.dict(os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent_root)}):
                write_ready_closeout_bundle(
                    report_dir, run_id, workspace=workspace_root
                )
            write_ready_diff_check_artifact(report_dir, workspace=workspace_root)

            environment = dict(os.environ)
            environment["AGENT_CANON_PARENT_ROOT"] = str(parent_root)
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
            self.assertTrue(
                report_dir.resolve().is_relative_to(TEST_TEMP_ROOT.resolve())
            )
            self.assertFalse(report_dir.resolve().is_relative_to(parent_root.resolve()))

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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLOSEOUT_READY=no", result.stdout)
            self.assertIn("diff_check_latest_diff_ref", result.stdout)

    def test_task_close_ignores_source_local_untracked_reports(self) -> None:
        """External runtime closeout ignores source-local report artifacts."""
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)

    def test_task_close_ignores_source_local_other_agent_reports(self) -> None:
        """External runtime closeout ignores source-local agent reports."""
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)

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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
            report_dir.mkdir(parents=True, exist_ok=True)
            with patch.dict(
                os.environ, {"AGENT_CANON_PARENT_ROOT": str(workspace_root)}
            ):
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)
            self.assertNotIn(
                "report_artifact_tracked_outside_current_run", result.stdout
            )

    def test_task_close_ignores_source_local_ignored_reports(self) -> None:
        """External runtime closeout ignores source-local ignored reports."""
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)

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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
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
            report_dir = TEST_TEMP_ROOT / "reports" / "agents" / run_id
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
                env={**os.environ, "AGENT_CANON_PARENT_ROOT": str(workspace_root)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPORT_ARTIFACT_PLACEMENT_CLEAN=yes", result.stdout)
            self.assertIn("CLOSEOUT_READY=yes", result.stdout)

    def test_task_close_rejects_unintegrated_review_findings(self) -> None:
        """Actual review findings still need disposition and integration."""
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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: no",
                        "- focused_recheck_complete: no",
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
            self.assertIn("review_findings_integrated", result.stdout)

    def test_task_close_rejects_missing_focused_recheck_completion(self) -> None:
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
                    "closeout missing focused recheck",
                    "--owner",
                    "codex",
                    "--run-id",
                    run_id,
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
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
                        "task=closeout missing focused recheck",
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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: yes",
                        "- focused_recheck_complete: no",
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
            self.assertIn("focused_recheck_complete", result.stdout)

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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: yes",
                        "- focused_recheck_complete: yes",
                        "- tool_warnings_resolved: yes",
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
                        "- overall_delivery_complete: yes",
                        "- dependency_headers_complete: yes",
                        "- repo_wide_dependency_tools_complete: yes",
                        "- repo_wide_static_analysis_complete: yes",
                        "- agent_canon_latest_complete: yes",
                        "- review_findings_integrated: yes",
                        "- focused_recheck_complete: yes",
                        "- tool_warnings_resolved: yes",
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
