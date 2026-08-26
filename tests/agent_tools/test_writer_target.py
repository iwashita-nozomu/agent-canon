# @dependency-start
# contract test
# responsibility Reproduces shared-checkout writer collisions before spawn and target-bound mutation rejection.
# upstream implementation ../../tools/agent_tools/writer_target.py owns writer-target validation.
# upstream implementation ../../tools/agent_tools/implementation_dispatch.py materializes writer waves.
# upstream implementation ../../tools/agent_tools/mutation_authority.py owns active mutation admission.
# @dependency-end
"""Focused tests for task-scoped writer targets."""

from __future__ import annotations

from pathlib import Path
import pytest

from tools.agent_tools.implementation_dispatch import validate_writer_handoff_waves
from tools.agent_tools.mutation_authority import evaluate_mutation_authority
from tools.agent_tools.team_config import SubagentWaveSlot
from tools.agent_tools.writer_target import (
    WriterTarget,
    WriterTargetError,
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
                {"owner": "#927:worker", "write_capable": True, "writer_target": shared},
                {"owner": "#928:publisher", "write_capable": True, "writer_target": shared},
            )
        )


def test_distinct_topic_clones_and_readers_remain_admissible() -> None:
    admitted = validate_writer_target_allocations(
        (
            {"owner": "#927:worker", "write_capable": True, "writer_target": target("/tmp/a")},
            {"owner": "#928:publisher", "write_capable": True, "writer_target": target("/tmp/b")},
            {"owner": "#929:reviewer", "write_capable": False, "writer_target": None},
        )
    )
    assert [item.normalized_root for item in admitted] == ["/tmp/a", "/tmp/b"]


def test_writer_target_is_required_for_writer_and_not_for_reader() -> None:
    with pytest.raises(WriterTargetError, match="required_before_spawn"):
        validate_writer_target_allocations(
            ({"owner": "worker", "write_capable": True, "writer_target": None},)
        )
    assert validate_writer_target_allocations(
        ({"owner": "reader", "write_capable": False, "writer_target": None},)
    ) == ()


def test_wave_materializer_rejects_colliding_writer_slots() -> None:
    waves = (
        (
            SubagentWaveSlot("implementer", "worker-1", "worker", True),
            SubagentWaveSlot("integration_executor", "integration-1", "integration_executor", True),
        ),
    )
    shared = target("/tmp/one")
    with pytest.raises(WriterTargetError, match="checkout_root_collision"):
        validate_writer_handoff_waves(
            waves,
            {
                waves[0][0].executable_identity: shared,
                waves[0][1].executable_identity: shared,
            },
        )


def test_wave_materializer_allows_distinct_writer_slots() -> None:
    waves = ((SubagentWaveSlot("implementer", "worker-1", "worker", True),),)
    assert validate_writer_handoff_waves(
        waves,
        {waves[0][0].executable_identity: target("/tmp/one")},
    )[0].branch == "fix/942"


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


def test_hook_target_blocks_foreign_checkout_and_branch_switch() -> None:
    env = {
        "AGENT_CANON_CHECKOUT_ROOT": "/tmp/target",
        "AGENT_CANON_CHECKOUT_BRANCH": "fix/942",
    }
    foreign = evaluate_mutation_authority(
        {"tool_name": "Bash", "tool_input": {"command": "touch src/x.py"}},
        report_dir=None,
        active_root=Path("/tmp/foreign"),
        environment=env,
    )
    assert foreign.reason == "writer_target_checkout_root_mismatch"
    switch = evaluate_mutation_authority(
        {"tool_name": "Bash", "tool_input": {"command": "git switch fix/942"}},
        report_dir=None,
        active_root=Path("/tmp/target"),
        environment=env,
    )
    assert switch.reason == "writer_target_branch_switch_forbidden"


def test_writer_target_rejects_relative_root() -> None:
    with pytest.raises(WriterTargetError, match="checkout_root_must_be_absolute"):
        target("relative/path")
