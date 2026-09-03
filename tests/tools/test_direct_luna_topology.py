from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_physical_team_is_profile_sized_and_luna_first() -> None:
    topology = json.loads((ROOT / "agents/execution_topology.json").read_text())
    profiles = topology["physical_execution_profiles"]

    assert topology["default_subagent"]["model"] == "gpt-5.6-luna"
    assert topology["default_subagent"]["fork_turns"] == "none"
    assert topology["default_subagent"]["effective_runtime_readback"] == "required"
    assert len(profiles) == 6
    assert [profile["id"] for profile in profiles[:3]] == [
        "luna_reasoning_high",
        "luna_implementation_xhigh",
        "luna_ship_xhigh",
    ]
    assert all("logical_role_id" not in profile for profile in profiles)


def test_logical_roles_and_skills_keep_separate_owners() -> None:
    topology = json.loads((ROOT / "agents/execution_topology.json").read_text())

    assert topology["logical_role_owner"] == "agents/agents_config.json"
    assert topology["skill_owner"] == "agents/skills"
    assert topology["profile_binding_owner"].startswith("agents/model_profiles.toml")
    assert topology["communication_skill"] == "direct-luna-communication"
    assert topology["projection_policy"]["new_logical_role_may_add_physical_profile"] is False
    assert (ROOT / "agents/skills/direct-luna-communication.md").is_file()


def test_cleanup_historical_asset_universe_precedes_slice_formation() -> None:
    cleanup = " ".join((ROOT / "agents/skills/code-cleanup.md").read_text().split())
    dependency = " ".join(
        (ROOT / "agents/skills/dependency-analysis.md").read_text().split()
    )
    refactor = " ".join((ROOT / "agents/skills/refactor-loop.md").read_text().split())

    cleanup_asset = cleanup.index("file/worker slice より先に")
    cleanup_dependency = cleanup.index("`dependency-analysis`")
    assert cleanup_asset < cleanup_dependency
    assert "git log" in cleanup
    assert "predecessor tests" in cleanup
    assert "関連 design docs" in cleanup

    dependency_asset = dependency.index("shared current+historical asset universe")
    dependency_scope = dependency.index("各 candidate は既存")
    assert dependency_asset < dependency_scope
    assert "同じ asset context" in dependency[dependency_asset:]

    refactor_asset = refactor.index("Before target or slice formation")
    refactor_target = refactor.index("refactor-loop の対象 file")
    assert refactor_asset < refactor_target
    assert "merge slices touching the same asset" in refactor[refactor_asset:]
    assert "pass the same known asset context" in refactor[refactor_asset:]
    assert "existing `reuse_survey`" in refactor[refactor_asset:]


def test_reuse_admission_is_fail_closed_on_the_existing_handoff_path() -> None:
    cleanup = " ".join((ROOT / "agents/skills/code-cleanup.md").read_text().split())
    communication = " ".join(
        (ROOT / "agents/skills/direct-luna-communication.md").read_text().split()
    )

    for field in (
        "asset_path",
        "asset_origin",
        "capability",
        "disposition",
        "reason",
        "test_paths",
    ):
        assert field in cleanup
        assert field in communication
    for disposition in (
        "reuse",
        "extend",
        "restore",
        "consolidate",
        "replace",
        "delete",
        "reject",
    ):
        assert disposition in cleanup
        assert disposition in communication

    assert "write handoff へ進めない" in cleanup
    assert "workspace-write` fails closed" in communication
    assert "direct_luna_handoff_packet_v1" in communication
    assert "new search tool" not in communication
    assert "asset registry" not in communication
