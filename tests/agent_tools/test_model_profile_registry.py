from __future__ import annotations

import json
import pytest

from tools.agent_tools.model_profile_registry import (
    ContextItem,
    DecisionSufficiencyRecord,
    EvidenceRequest,
    ToolCallMaterializationRequest,
    authorize_evidence_request,
    generate_role_views,
    load_model_profile_registry,
    main,
    materialize_contract_projection,
    materialize_prompt_capsule,
    materialize_route_packet,
    materialize_tool_call_token,
    validate_decision_sufficiency,
    validate_target_state_contract,
)


@pytest.fixture
def workspace(tmp_path):
    cfg_root = tmp_path / "root"
    cfg_root.mkdir()
    (cfg_root / "agents").mkdir()
    (cfg_root / ".codex" / "agents").mkdir(parents=True)

    (cfg_root / "agents" / "model_profiles.toml").write_text(
        """
schema_id = \"model_profile_registry_v1\"
registry_id = \"model_profile_registry\"
registry_version = 1

[[model_profiles]]
id = \"sol_parent_high\"
model_alias = \"sol\"
owner = \"sol_parent\"
role_template = \"{base_prompt}\"
prompt_capsule_schema_id = \"prompt_capsule_v1\"
prompt_capsule_template = \"SOL {role_id} {objective}\\n{context_block}\"
prompt_capsule_required_context = [\"objective\", \"context\"]
close_skill_id = \"subagent-bootstrap\"
close_tool_id = \"close_agent\"
close_tool_argument_schema_id = \"close_agent_args_v1\"
close_tool_failure_schema_id = \"close_agent_failure_v1\"
close_tool_target_binding = \"terminal_agent_id\"

[[model_profiles.role_instructions]]
id = \"sol_core\"
text = \"Use strict contracts.\"
priority = 1
""",
        encoding="utf-8",
    )
    (cfg_root / "agents" / "agents_config.json").write_text(
        json.dumps({"roles": [{"id": "sol_parent", "model_profile": "sol_parent_high"}]},
        indent=2),
        encoding="utf-8",
    )
    return cfg_root


@pytest.fixture
def pass_role_view_workspace(workspace):
    (workspace / ".codex" / "agents" / "sol_parent.toml").write_text(
        """# generated role view: generated_role_view_v1
name = "sol_parent"
developer_instructions = "Use strict contracts."
""",
        encoding="utf-8",
    )
    return workspace


@pytest.fixture
def drift_role_view_workspace(pass_role_view_workspace):
    role_view = pass_role_view_workspace / ".codex" / "agents" / "sol_parent.toml"
    role_view.write_text(
        """# generated role view: generated_role_view_v1
name = "sol_parent"
developer_instructions = "Drifted instructions."
""",
        encoding="utf-8",
    )
    return pass_role_view_workspace


def test_load_and_validate_registry(workspace):
    registry = load_model_profile_registry(workspace)
    assert registry.schema_id == "model_profile_registry_v1"
    assert len(registry.model_profiles) == 1


def test_prompt_capsule_materialization(workspace):
    registry = load_model_profile_registry(workspace)
    capsule = materialize_prompt_capsule(
        request=type(
            "_Request",
            (),
            {
                "profile_id": "sol_parent_high",
                "role_id": "sol_parent",
                "context": (ContextItem("objective", "build"), ContextItem("context", "x")),
                "objective": "build",
            },
        )(),
        registry=registry,
    )
    assert capsule.schema_id == "prompt_capsule_v1"
    assert "SOL sol_parent" in capsule.body


def test_tool_call_materialization(workspace):
    registry = load_model_profile_registry(workspace)
    token = materialize_tool_call_token(
        request=ToolCallMaterializationRequest(
            profile_id="sol_parent_high",
            terminal_agent_id="agent-123",
            route_id="r1",
        ),
        profile="sol_parent_high",
        registry=registry,
    )
    assert token.schema_id == "tool_call_token_v1"
    assert token.skill_id == "subagent-bootstrap"
    assert token.tool_id == "close_agent"
    assert token.arguments["terminal_agent_id"] == "agent-123"


def test_generated_role_views_and_projection(workspace):
    registry = load_model_profile_registry(workspace)
    views = generate_role_views(
        registry,
        workspace,
        target_state_contract={
            "contract_id": "tc1",
            "unit_id": "u",
            "owner": "x",
            "exact_owner": "y",
            "profiles": ["sol_parent_high"],
            "configured_supported_profiles": ["sol_parent_high"],
            "supported_role_profiles": {"sol_parent": "sol_parent_high"},
        },
    )
    assert views
    exec_contract = materialize_contract_projection(
        target_state_contract={
            "contract_id": "tc1",
            "unit_id": "u",
            "owner": "x",
            "exact_owner": "y",
            "profiles": ["sol_parent_high"],
            "configured_supported_profiles": ["sol_parent_high"],
            "supported_role_profiles": {"sol_parent": "sol_parent_high"},
        },
        root=workspace,
    )
    assert exec_contract.schema_id == "implementation_execution_contract_v1"


def test_decision_sufficiency_and_evidence(workspace):
    record = DecisionSufficiencyRecord(
        plausible_state_ids=("s1", "s2"),
        current_state_id="s1",
        requested_state_id="s2",
    )
    req = EvidenceRequest(
        evidence_request_id="er1",
        target_state_id="s2",
        rationale="for test",
    )
    result = validate_decision_sufficiency(record, req)
    assert result.valid

    decision = authorize_evidence_request(record, req)
    assert decision.authorized
    assert decision.evidence_request_id == "er1"


def test_route_packet_materialization(workspace):
    packet = materialize_route_packet(
        role_id="sol_parent",
        profile_id="sol_parent_high",
        objective="ship now",
        root=workspace,
        terminal_agent_id="agent-7",
        context=(ContextItem("objective", "ship now"), ContextItem("context", "now")),
    )
    assert packet.profile_id == "sol_parent_high"
    assert packet.prompt_capsule.schema_id == "prompt_capsule_v1"


def test_validate_target_state_contract_negative(workspace):
    registry = load_model_profile_registry(workspace)
    target = {
        "contract_id": "tc1",
        "unit_id": "u",
        "owner": "x",
        "exact_owner": "x",
        "profiles": ["unknown"],
    }
    result = validate_target_state_contract(target, registry)
    assert not result.valid
    assert len(result.issues) > 0


def test_contract_validation_raises_for_invalid_contract(workspace):
    registry = load_model_profile_registry(workspace)
    target = {
        "unit_id": "u",
        "owner": "x",
        "exact_owner": "x",
        "profiles": ["unknown"],
        "configured_supported_profiles": ["unknown"],
    }
    result = validate_target_state_contract(target, registry)
    assert not result.valid
    assert len(result.issues) > 0


def test_role_view_cli_passes_without_mutation(pass_role_view_workspace, capsys):
    role_view = pass_role_view_workspace / ".codex" / "agents" / "sol_parent.toml"
    original_bytes = role_view.read_bytes()

    result = main(["--root", str(pass_role_view_workspace), "--check-role-views"])

    assert result == 0
    assert capsys.readouterr().out == "MODEL_PROFILE_ROLE_VIEWS=pass\n"
    assert role_view.read_bytes() == original_bytes


def test_role_view_cli_reports_deterministic_drift(drift_role_view_workspace, capsys):
    result = main(["--root", str(drift_role_view_workspace), "--check-role-views"])

    assert result == 1
    assert capsys.readouterr().out == (
        'MODEL_PROFILE_ROLE_VIEW_ISSUE={"code":"role_view.content_drift",'
        '"location":".codex/agents/sol_parent.toml",'
        '"message":"generated instructions differ from executable role view",'
        '"schema_id":"model_profile_registry_cli_v1"}\n'
    )
