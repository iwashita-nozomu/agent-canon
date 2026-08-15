# @dependency-start
# contract test
# responsibility Locks parent-owned lifecycle materialization and fresh-clone production-path coverage.
# upstream design ../../documents/agent-canon/source-publication-parent-handoff.md owns the handoff contract.
# upstream implementation ../../tools/update_agent_canon.sh owns parent lifecycle advancement.
# upstream implementation ../../tools/ci/check_fresh_clone.sh exercises the empty-parent namespace.
# @dependency-end
"""Static contract tests for issue #724's parent lifecycle wiring."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SCRIPT = PROJECT_ROOT / "tools" / "update_agent_canon.sh"
FRESH_CLONE = PROJECT_ROOT / "tools" / "ci" / "check_fresh_clone.sh"


def update_text() -> str:
    return UPDATE_SCRIPT.read_text(encoding="utf-8")


def fresh_clone_text() -> str:
    return FRESH_CLONE.read_text(encoding="utf-8")


def test_lifecycle_namespace_is_owned_by_explicit_parent_root() -> None:
    script = update_text()
    assert (
        'UPDATE_OWNER_NAMESPACE="$PARENT_ROOT_DIR/.agent-canon/update-lifecycle"'
        in script
    )
    assert 'UPDATE_OWNER_NAMESPACE="$ROOT_DIR/.agent-canon/update-lifecycle"' not in script


def test_front_door_materializes_packet_before_frontier_requirement() -> None:
    script = update_text()
    start = script.index("require_accepted_dependency_frontier() {")
    end = script.index("\ncmd_plan()", start)
    function = script[start:end]
    assert "ensure_source_projection_lifecycle" in function
    assert function.index("ensure_source_projection_lifecycle") < function.index(
        'local current_marker="$UPDATE_STATE_DIR/current-transaction"'
    )
    assert "AGENT_CANON_PARENT_PROJECTION_BLOCKER=source_publication_handoff_missing" in script
    assert "manual_gitlink_or_receipt_copy_forbidden" in script


def test_parent_remote_readback_uses_declared_submodule_remote() -> None:
    script = update_text()
    start = script.index("advance_source_projection() {")
    end = script.index("\nrequire_accepted_dependency_frontier()", start)
    function = script[start:end]
    assert 'source_remote="$(submodule_remote_url)"' in function
    assert 'resolve_remote_branch_sha "$source_remote" main' in function
    assert 'ensure_remote_commit_object "$AGENT_CANON_DIR" origin "$source_main_sha"' in function


def test_parent_lifecycle_uses_only_boundary_reads_and_noreplace_publication() -> None:
    script = update_text()
    start = script.index("emit_queue_receipt() {")
    end = script.index("\nrequire_accepted_dependency_frontier()", start)
    lifecycle = script[start:end]
    assert "Path.read_text" not in lifecycle
    assert "Path.read_bytes" not in lifecycle
    assert ".is_file()" not in lifecycle
    assert "open(path" not in lifecycle
    assert "[ -f \"$UPDATE" not in script
    assert "[ -f \"$SOURCE_PROJECTION_PACKET" not in script
    assert lifecycle.count("publish_parent_owned_file_noreplace") == 5
    assert lifecycle.count("write_parent_owned_file") == 0


def test_parent_lifecycle_readback_is_bytes_before_parser() -> None:
    script = update_text()
    start = script.index("emit_queue_receipt() {")
    end = script.index("\nrequire_accepted_dependency_frontier()", start)
    lifecycle = script[start:end]
    assert lifecycle.count("read_parent_owned_bytes") >= 10
    assert "raw.decode(\"utf-8\")" in lifecycle
    assert "object_pairs_hook=reject_duplicate_pairs" in lifecycle


def test_fresh_clone_hands_off_only_packet_and_derives_parent_receipts() -> None:
    script = fresh_clone_text()
    assert 'packet_path="${target_namespace}/state/source-publication-ready.json"' in script
    assert 'run_update_for_parent_root \\\n      "${CLONE_DIR}"' in script
    assert "AGENT_CANON_SOURCE_PROJECTION_HANDOFF" in script
    assert 'parent_copy_file "${source_namespace}/${lifecycle_path}"' not in script
    assert "for lifecycle_path in" not in script
    assert "AGENT_CANON_FRESH_CLONE_DERIVED_RECEIPT_COPY=forbidden" in script
