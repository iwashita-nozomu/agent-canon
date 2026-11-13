# @dependency-start
# contract test
# responsibility Reproduces shared-checkout writer collisions and safe writer-target materialization.
# upstream implementation ../../tools/runtime/authority/writer_target.py owns writer-target validation.
# @dependency-end
"""Focused tests for task-scoped writer targets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.runtime.authority.writer_target import (  # noqa: E402
    WriterTarget,
    WriterTargetError,
    materialize_writer_target_packet,
    validate_writer_target_allocations,
    validate_writer_target_identity,
)


def target(root: str, branch: str = "fix/942") -> WriterTarget:
    return WriterTarget(root, branch, "iwashita-nozomu/agent-canon", ("tools/",))


def test_shared_checkout_writer_targets_are_rejected_before_spawn() -> None:
    shared = target("/tmp/agent-canon-shared")
    with pytest.raises(WriterTargetError, match="checkout_root_collision"):
        validate_writer_target_allocations(
            (
                {
                    "owner": "#927:worker",
                    "write_capable": True,
                    "writer_target": shared,
                },
                {
                    "owner": "#928:publisher",
                    "write_capable": True,
                    "writer_target": shared,
                },
            )
        )


def test_distinct_topic_clones_and_readers_remain_admissible() -> None:
    admitted = validate_writer_target_allocations(
        (
            {
                "owner": "#927:worker",
                "write_capable": True,
                "writer_target": target("/tmp/a"),
            },
            {
                "owner": "#928:publisher",
                "write_capable": True,
                "writer_target": target("/tmp/b"),
            },
            {"owner": "#929:reviewer", "write_capable": False, "writer_target": None},
        )
    )
    assert [item.normalized_root for item in admitted] == ["/tmp/a", "/tmp/b"]


def test_writer_target_is_required_for_writer_and_not_for_reader() -> None:
    with pytest.raises(ValueError, match="required_before_spawn"):
        validate_writer_target_allocations(
            ({"owner": "worker", "write_capable": True, "writer_target": None},)
        )
    assert (
        validate_writer_target_allocations(
            ({"owner": "reader", "write_capable": False, "writer_target": None},)
        )
        == ()
    )


def test_identity_must_match_prepared_target() -> None:
    writer = target("/tmp/prepared")
    identity = {
        "cwd": "/tmp/prepared",
        "git_root": "/tmp/prepared",
        "branch": "fix/942",
        "head": "a" * 40,
        "remote": "iwashita-nozomu/agent-canon",
    }
    assert validate_writer_target_identity(writer, identity) == writer
    with pytest.raises(WriterTargetError, match="branch_identity_mismatch"):
        validate_writer_target_identity(writer, {**identity, "branch": "main"})


def test_writer_target_rejects_relative_root() -> None:
    with pytest.raises(WriterTargetError, match="checkout_root_must_be_absolute"):
        target("relative/path")


def test_materialized_packet_contains_validated_identity(tmp_path: Path) -> None:
    writer = WriterTarget(str(tmp_path), "fix/942", "local/repo", ("src/",))
    identity = {
        "cwd": str(tmp_path),
        "git_root": str(tmp_path),
        "branch": "fix/942",
        "head": "b" * 40,
        "remote": "local/repo",
    }
    packet_path = materialize_writer_target_packet(writer, identity)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["checkout_root"] == str(tmp_path)
    assert packet["checkout_identity"] == identity


def test_materialize_rejects_symlink_packet_directory_without_external_write(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_packet = outside / "writer-target.json"
    original = b"external data must remain untouched\n"
    outside_packet.write_bytes(original)
    (checkout / ".agent-canon").symlink_to(outside, target_is_directory=True)
    writer = WriterTarget(str(checkout), "fix/942", "local/repo", ("src/",))
    identity = {
        "cwd": str(checkout),
        "git_root": str(checkout),
        "branch": "fix/942",
        "head": "b" * 40,
        "remote": "local/repo",
    }

    with pytest.raises(WriterTargetError, match="writer_target_packet_path_unsafe"):
        materialize_writer_target_packet(writer, identity)

    assert outside_packet.read_bytes() == original
