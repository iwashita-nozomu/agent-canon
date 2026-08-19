# @dependency-start
# contract test
# responsibility Tests exact postorder close tokens and lifecycle reservation release.
# upstream implementation ../../tools/agent_tools/task_close.py consumes the provider ledger
# upstream implementation ../../tools/agent_tools/capacity_handshake.py owns lifecycle state
# @dependency-end

"""Task-close tests for AgentCanon parent sync gating and lifecycle closeout."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from tools.agent_tools import capacity_handshake
from tools.agent_tools.task_close import (
    _gitlink_commit_resolvable,
    _gitlink_target_commit_resolvable,
    _gitlink_update_candidates,
    _parse_gitlink_ref_updates,
    agent_canon_parent_sync_gate_required,
    validate_capacity_lifecycle_closeout,
)


def test_agent_canon_parent_sync_gate_non_trigger_and_exact_symlink_path() -> None:
    """Active projection source roots are non-triggers; exact symlink links are triggers."""
    workspace = Path(__file__).resolve().parents[2]
    assert not agent_canon_parent_sync_gate_required(
        ("agents/foo.md",),
        workspace=workspace,
    )
    assert agent_canon_parent_sync_gate_required(
        ("AGENTS.md",),
        workspace=workspace,
    )
    assert agent_canon_parent_sync_gate_required(
        (".codex/config.toml",),
        workspace=workspace,
    )
    assert agent_canon_parent_sync_gate_required(
        ("tools/agent-canon",),
        workspace=workspace,
    )


def test_agent_canon_parent_sync_gate_ignores_symlink_source_changes() -> None:
    """Changes only under symlink source roots must skip root topology checks."""
    workspace = Path(__file__).resolve().parents[2]
    assert not agent_canon_parent_sync_gate_required(
        ("agents/foo.md", "documents/notes/knowledge/file.md"),
        workspace=workspace,
    )


def test_agent_canon_parent_sync_gate_ignores_sync_control_former_triggers() -> None:
    """Materialized copy paths that are no longer sync-control should be non-triggers."""
    workspace = Path(__file__).resolve().parents[2]
    assert not agent_canon_parent_sync_gate_required(
        ("tools/sync_agent_canon.sh",),
        workspace=workspace,
    )
    assert not agent_canon_parent_sync_gate_required(
        ("tools/agent_tools/surface_manifest.py",),
        workspace=workspace,
    )
    assert not agent_canon_parent_sync_gate_required(
        ("documents/runtime/shared-runtime-surfaces.toml",),
        workspace=workspace,
    )


def test_parse_gitlink_ref_updates_detects_rename_into_vendor_agent_canon() -> None:
    """Rename/copy into vendor/agent-canon should be treated as path-target update."""
    old, new = _parse_gitlink_ref_updates(
        (
            ":160000 160000 "
            "1111111111111111111111111111111111111111 "
            "2222222222222222222222222222222222222222 "
            "R100\tlegacy/agent-canon\tvendor/agent-canon",
        )
    )
    assert old == "1111111111111111111111111111111111111111"
    assert new == "2222222222222222222222222222222222222222"


def test_parse_gitlink_ref_updates_ignore_rename_out_of_vendor_agent_canon() -> None:
    """Rename out of vendor/agent-canon must not be treated as target update."""
    assert _parse_gitlink_ref_updates(
        (
            ":160000 160000 "
            "2222222222222222222222222222222222222222 "
            "1111111111111111111111111111111111111111 "
            "R100\tvendor/agent-canon\tlegacy/agent-canon",
        )
    ) == (None, None)


def test_agent_canon_parent_sync_gate_accepts_non_trigger_dirty_workspace_state() -> None:
    """Unknown local changes should not trigger full parent sync."""
    workspace = Path(__file__).resolve().parents[2]
    assert not agent_canon_parent_sync_gate_required(
        ("documents/notes/knowledge/non_trigger_file.md", "vendor/notes/other.txt"),
        workspace=workspace,
    )


def test_agent_canon_parent_sync_gate_accepts_gitlink_commit_without_branch_checks() -> None:
    """Gitlink integrity does not require branch- or detached-worktree assumptions."""
    workspace = Path(__file__).resolve().parents[2]
    commit = _gitlink_commit_resolvable(workspace)
    assert commit is None or len(commit) > 0


def test_agent_canon_parent_sync_gate_requires_no_full_sync_for_gitlink_only_update() -> None:
    """Vendor gitlink changes alone do not require parent full sync."""
    workspace = Path(__file__).resolve().parents[2]
    assert not agent_canon_parent_sync_gate_required(
        ("vendor/agent-canon",),
        workspace=workspace,
    )


def test_agent_canon_parent_gitlink_integrity_fails_for_unreachable_target(monkeypatch) -> None:
    """Unresolvable gitlink target must fail integrity requirement."""
    workspace = Path(__file__).resolve().parents[2]

    def fake_run(args, check=False, capture_output=False, text=False, cwd=None, **kwargs):
        if args[:2] == ["git", "diff"] and args[1] == "diff":
            return SimpleNamespace(
                returncode=0,
                stdout=":160000 160000 1111111111111111111111111111111111111111 2222222222222222222222222222222222222222 M\tvendor/agent-canon\n",
            )
        if args[:2] == ["git", "cat-file"] and args[1] == "cat-file":
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _gitlink_target_commit_resolvable(workspace) is None


def test_agent_canon_parent_sync_gate_internal_symlink_change_keeps_full_sync_and_integrity_false() -> None:
    """Internal source edits to symlink targets should not open full sync gate."""
    workspace = Path(__file__).resolve().parents[2]
    changed_paths = ("agents/foo.md", "documents/notes/knowledge/file.md")
    assert not agent_canon_parent_sync_gate_required(changed_paths, workspace=workspace)
    _, new_hash = _gitlink_update_candidates(workspace)
    assert new_hash is None
    assert _gitlink_target_commit_resolvable(workspace) is None


def _readback_record(work_id: str, parent: str) -> capacity_handshake.DescendantLifecycleRecord:
    return capacity_handshake.DescendantLifecycleRecord(
        work_id=work_id,
        parent_work_id=parent,
        status=capacity_handshake.LifecycleStatus.READBACK_VERIFIED,
        durable_result_evidence_ref=f"result://{work_id}",
        durable_handback=True,
        descendants_closed=True,
        close_readback=True,
        transition_generation=6,
    )


def _close_call(work_id: str) -> dict[str, object]:
    return {
        "agent_id": work_id,
        "tool_call_token": {
            "tool_id": "close_agent",
            "arguments": {"terminal_agent_id": work_id},
        },
    }


def _ledger() -> capacity_handshake.CapacityLedger:
    child = _readback_record("child", "parent-agent")
    parent = _readback_record("parent-agent", "root")
    return capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback(
            parent_work_id="root",
            descendants=(parent, child),
        ),
        open_records={"parent-agent": parent, "child": child},
        reservations={
            "parent-agent": capacity_handshake.ParentChildEdge("root", "parent-agent"),
            "child": capacity_handshake.ParentChildEdge("parent-agent", "child"),
        },
    )


def test_closeout_requires_exactly_one_schema_valid_postorder_token() -> None:
    """Closeout requires valid single postorder close token chain."""
    ledger = _ledger()
    ready, failures = validate_capacity_lifecycle_closeout(
        ledger,
        (_close_call("child"), _close_call("parent-agent")),
    )
    assert ready
    assert failures == ()
    assert ledger.reservations == {}
    assert set(ledger.open_records) == {"parent-agent", "child"}
    assert all(
        record.status == capacity_handshake.LifecycleStatus.RESERVATION_RELEASED
        for record in ledger.open_records.values()
    )


def test_closeout_rejects_duplicate_reverse_and_metadata_tokens() -> None:
    """Closeout rejects duplicate close tokens and metadata-enriched tokens."""
    reverse = validate_capacity_lifecycle_closeout(
        _ledger(),
        (_close_call("parent-agent"), _close_call("child")),
    )
    assert not reverse[0]
    assert "close_agent_tool_calls_not_postorder" in reverse[1]

    duplicate = validate_capacity_lifecycle_closeout(
        _ledger(),
        (_close_call("child"), _close_call("child"), _close_call("parent-agent")),
    )
    assert not duplicate[0]
    assert "child:duplicate_close_agent_tool_call" in duplicate[1]

    metadata_call = _close_call("child")
    token = metadata_call["tool_call_token"]
    assert isinstance(token, dict)
    token["metadata"] = {"reason": "arbitrary"}
    invalid = validate_capacity_lifecycle_closeout(
        _ledger(),
        (metadata_call, _close_call("parent-agent")),
    )
    assert not invalid[0]
    assert "child:close_agent_token_fields_invalid" in invalid[1]


def test_closeout_rejects_open_and_unknown_descendants_without_reclaim() -> None:
    """Closeout must reject open and unknown descendants with reclaim leaks."""
    record = capacity_handshake.DescendantLifecycleRecord(
        work_id="open",
        parent_work_id="root",
        status=capacity_handshake.LifecycleStatus.ACTIVE,
    )
    ledger = capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback("root", (record,)),
        open_records={"open": record, "unknown": record},
        reservations={"open": capacity_handshake.ParentChildEdge("root", "open")},
    )
    ready, failures = validate_capacity_lifecycle_closeout(ledger)
    assert not ready
    assert "open:open_descendant" in failures
    assert "unknown:unknown_descendant" in failures
    assert "open" in ledger.open_records
    assert "open" in ledger.reservations
