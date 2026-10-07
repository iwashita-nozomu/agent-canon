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
