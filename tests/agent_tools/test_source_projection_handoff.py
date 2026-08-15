# @dependency-start
# contract test
# responsibility Verifies source packet materialization, parent ownership, immutable replay, no-replace publication, and conflict refusal.
# upstream design ../../documents/agent-canon/source-publication-parent-handoff.md owns the handoff contract.
# upstream implementation ../../tools/agent_tools/source_projection_handoff.py owns packet publication.
# upstream implementation ../../tools/agent_tools/update_lifecycle_contract.py owns packet validation.
# @dependency-end
"""Focused tests for the source-publication to parent-projection handoff."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_TOOLS = PROJECT_ROOT / "tools" / "agent_tools"
CI_TOOLS = PROJECT_ROOT / "tools" / "ci"
sys.path.insert(0, str(AGENT_TOOLS))
sys.path.insert(0, str(CI_TOOLS))

from check_agent_canon_pr import (  # noqa: E402
    GENERATED_COMPLETENESS_CHECK_IDS,
    materialize_generated_completeness_receipt,
)
from github_publish import materialize_pr_identity_gate  # noqa: E402
from parent_root_side_effects import ParentRootSideEffectError  # noqa: E402
from source_projection_handoff import (  # noqa: E402
    publish_source_projection_handoff,
)
from update_lifecycle_contract import (  # noqa: E402
    SourceProjectionGateOwnerApis,
    materialize_fresh_clone_source_projection_packet,
    validate_source_projection_packet,
)


def source_packet(seed: int) -> dict[str, object]:
    """Return one valid packet with a distinct immutable source identity."""
    digits = "123456789abcdef"
    offset = seed * 4
    values = [digits[(offset + index) % len(digits)] * 40 for index in range(4)]
    return materialize_fresh_clone_source_projection_packet(
        candidate_sha=values[0],
        candidate_tree_sha=values[1],
        publication_sha=values[2],
        publication_tree_sha=values[3],
        gate_owner_apis=SourceProjectionGateOwnerApis(
            generated_completeness_check_ids=GENERATED_COMPLETENESS_CHECK_IDS,
            materialize_generated_completeness_receipt=(
                materialize_generated_completeness_receipt
            ),
            materialize_pr_identity_gate=materialize_pr_identity_gate,
        ),
    )


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_parent_repo(path: Path) -> Path:
    """Create the authenticated Git toplevel required by the owner boundary."""
    path.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def parent_packet_path(parent: Path) -> Path:
    return (
        parent
        / ".agent-canon"
        / "update-lifecycle"
        / "state"
        / "source-publication-ready.json"
    )


def test_component_records_materialize_in_parent_namespace_and_replay(
    tmp_path: Path,
) -> None:
    parent = initialize_parent_repo(tmp_path / "parent")
    packet = source_packet(0)
    component_input = {key: value for key, value in packet.items() if key != "schema"}
    input_path = tmp_path / "publication-components.json"
    write_json(input_path, component_input)

    first = publish_source_projection_handoff(
        parent_root=parent,
        input_path=input_path,
    )
    expected = parent_packet_path(parent)
    assert first.output_path == expected
    assert first.replayed is False
    assert validate_source_projection_packet(
        json.loads(expected.read_text(encoding="utf-8"))
    ) == packet

    second = publish_source_projection_handoff(
        parent_root=parent,
        input_path=input_path,
    )
    assert second.output_path == expected
    assert second.replayed is True
    assert second.packet == first.packet


def test_semantic_replay_preserves_existing_bytes(tmp_path: Path) -> None:
    parent = initialize_parent_repo(tmp_path / "parent")
    packet = source_packet(0)
    input_path = tmp_path / "packet.json"
    write_json(input_path, packet)
    target = parent_packet_path(parent)
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(packet, separators=(",", ":")),
        encoding="utf-8",
    )
    original = target.read_bytes()

    result = publish_source_projection_handoff(
        parent_root=parent,
        input_path=input_path,
    )

    assert result.replayed is True
    assert result.packet == packet
    assert target.read_bytes() == original


def test_conflicting_packet_is_not_overwritten(tmp_path: Path) -> None:
    parent = initialize_parent_repo(tmp_path / "parent")
    first_input = tmp_path / "first.json"
    second_input = tmp_path / "second.json"
    write_json(first_input, source_packet(0))
    write_json(second_input, source_packet(1))

    first = publish_source_projection_handoff(
        parent_root=parent,
        input_path=first_input,
    )
    original = first.output_path.read_bytes()

    with pytest.raises(ValueError):
        publish_source_projection_handoff(
            parent_root=parent,
            input_path=second_input,
        )

    assert first.output_path.read_bytes() == original


def test_existing_symlink_is_rejected_without_following(tmp_path: Path) -> None:
    parent = initialize_parent_repo(tmp_path / "parent")
    packet = source_packet(0)
    input_path = tmp_path / "packet.json"
    write_json(input_path, packet)
    outside = tmp_path / "outside.json"
    write_json(outside, packet)
    outside_before = outside.read_bytes()
    target = parent_packet_path(parent)
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)

    with pytest.raises(ParentRootSideEffectError):
        publish_source_projection_handoff(
            parent_root=parent,
            input_path=input_path,
        )

    assert target.is_symlink()
    assert outside.read_bytes() == outside_before


def test_output_outside_attested_parent_is_rejected(tmp_path: Path) -> None:
    parent = initialize_parent_repo(tmp_path / "parent")
    input_path = tmp_path / "packet.json"
    write_json(input_path, source_packet(0))

    with pytest.raises(ParentRootSideEffectError):
        publish_source_projection_handoff(
            parent_root=parent,
            input_path=input_path,
            output_path=tmp_path / "outside" / "packet.json",
        )
