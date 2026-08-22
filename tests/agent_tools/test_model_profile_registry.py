# @dependency-start
# contract test
# responsibility Tests the closed model-profile registry, prompt/token materializers, and generated projections.
# upstream implementation ../../agents/model_profiles.toml declares the canonical profile schema
# upstream implementation ../../tools/agent_tools/model_profile_registry.py implements registry behavior
# downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py consumes generated projections
# @dependency-end

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.agent_tools import model_profile_registry as registry_module
from tools.agent_tools.model_profile_registry import (
    REQUIRED_STATIC_OBLIGATION_SETS,
    STATIC_OBLIGATION_TABLE,
    ContextItem,
    ModelProfileRegistryError,
    PromptMaterializationRequest,
    ToolCallMaterializationRequest,
    generate_role_views,
    load_model_profile_registry,
    main,
    materialize_prompt_capsule,
    materialize_tool_call_token,
    validate_claim_evidence_result,
    validate_common_return_schema,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "agents").mkdir(parents=True)
    (root / ".codex" / "agents").mkdir(parents=True)
    (root / "agents" / "model_profiles.toml").write_text(
        '''schema_id = "model_profile_registry_v1"
registry_id = "test"
registry_version = 1
[role_profile_bindings]
sol_parent = "sol_parent_high"
[role_sandbox_bindings]
sol_parent = "workspace-write"
[role_instruction_templates]
[[role_instruction_templates.sol_parent]]
id = "role-contract"
text = "Use the role-specific contract."
priority = 100
[standalone_role_metadata]
[[model_profiles]]
id = "sol_parent_high"
model_alias = "sol"
model = "model-sol"
reasoning_effort = "high"
owner = "sol_parent"
capabilities = ["orchestration"]
allowed_context = ["objective", "context"]
forbidden_context = ["raw_history"]
return_schema_id = "result_v1"
checkpoint_policy = "observation"
continuation_policy = "same_session"
projection_digest = "computed_sha256_v1"
role_template = "{role_id} {model_alias} {base_prompt}"
prompt_capsule_schema_id = "prompt_capsule_v1"
prompt_capsule_template = "{role_id} {objective} {context_block}"
prompt_capsule_required_context = ["objective", "context"]
close_skill_id = "subagent-bootstrap"
close_tool_id = "close_agent"
close_tool_argument_schema_id = "close_agent_args_v1"
close_tool_failure_schema_id = "close_agent_failure_v1"
close_tool_target_binding = "terminal_agent_id"
[[model_profiles.role_instructions]]
id = "core"
text = "Use closed contracts."
priority = 1
''',
        encoding="utf-8",
    )
    (root / "agents" / "agents_config.json").write_text(
        json.dumps(
            {
                "_dependency_manifest": ["@dependency-start", "@dependency-end"],
                "always_on_roles": [
                    {
                        "id": "manager",
                        "codex_agents": ["sol_parent"],
                        "write_policy": {"mode": "artifacts_only"},
                    }
                ],
                "specialist_roles": [],
            }
        ),
        encoding="utf-8",
    )
    (root / ".codex" / "config.toml").write_text(
        '[agents]\nmax_threads = 1\n[agents.sol_parent]\ndescription = "Parent"\nconfig_file = "agents/sol_parent.toml"\n',
        encoding="utf-8",
    )
    return root


def _context() -> tuple[ContextItem, ...]:
    return (ContextItem("objective", "build"), ContextItem("context", "fixed"))


def test_registry_is_closed_and_has_typed_projection(workspace: Path) -> None:
    registry = load_model_profile_registry(workspace)
    profile = registry.by_profile("sol_parent_high")
    assert profile.model == "model-sol"
    assert profile.reasoning_effort == "high"
    assert len(profile.projection_digest) == 64
    assert profile.capabilities == ("orchestration",)
    assert registry.instruction_clauses_for_role("sol_parent")[-1].text == (
        "Use the role-specific contract."
    )


def test_registry_reads_explicit_source_root_when_state_root_differs(
    workspace: Path,
) -> None:
    """Derived state does not become an implicit AgentCanon source."""
    source = workspace / "agentcanon-source"
    source_registry = source / "agents" / "model_profiles.toml"
    source_registry.parent.mkdir(parents=True)
    source_registry.write_bytes(
        (workspace / "agents" / "model_profiles.toml").read_bytes()
    )
    (workspace / "agents" / "model_profiles.toml").unlink()
    loaded = load_model_profile_registry(workspace, source_root=source)
    assert loaded.registry_id == "test"


def test_common_claim_evidence_contract_is_validated(workspace: Path) -> None:
    registry = load_model_profile_registry(workspace)
    assert not validate_common_return_schema(registry).valid
    assert validate_claim_evidence_result(
        {"status": "pass", "claim": "bounded", "evidence": ["test:1"]}
    ).valid
    assert not validate_claim_evidence_result(
        {"status": "pass", "claim": "", "evidence": []}
    ).valid


def test_registry_rejects_unknown_profile_field(workspace: Path) -> None:
    path = workspace / "agents" / "model_profiles.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('model_alias = "sol"', 'model_alias = "sol"\nfallback = "worker"'), encoding="utf-8")
    with pytest.raises(ModelProfileRegistryError, match="unknown_fields"):
        load_model_profile_registry(workspace)


def test_prompt_rejects_unknown_duplicate_and_forbidden_context(workspace: Path) -> None:
    registry = load_model_profile_registry(workspace)
    with pytest.raises(ModelProfileRegistryError, match="unknown"):
        materialize_prompt_capsule(
            PromptMaterializationRequest("sol_parent_high", "sol_parent", _context() + (ContextItem("extra", "x"),), "build"),
            registry,
        )
    with pytest.raises(ModelProfileRegistryError, match="duplicate"):
        materialize_prompt_capsule(
            PromptMaterializationRequest("sol_parent_high", "sol_parent", _context() + (ContextItem("context", "again"),), "build"),
            registry,
        )


def test_close_token_is_target_only_and_request_schema_is_closed(workspace: Path) -> None:
    registry = load_model_profile_registry(workspace)
    token = materialize_tool_call_token(
        ToolCallMaterializationRequest("sol_parent_high", "agent-1"),
        "sol_parent_high",
        registry,
    )
    assert token.tool_id == "close_agent"
    assert token.arguments == {"terminal_agent_id": "agent-1"}
    assert set(token.__dict__) == {"tool_id", "arguments"}
    with pytest.raises(TypeError):
        ToolCallMaterializationRequest("sol_parent_high", "agent-1", metadata={})  # type: ignore[call-arg]


def test_registry_exposes_no_decision_sufficiency_policy_api() -> None:
    forbidden = {
        "DecisionSufficiencyRecord",
        "EvidenceRequest",
        "OwnerEditValidationAction",
        "PlausibleDecisionBranch",
        "authorize_evidence_request",
        "parse_decision_sufficiency_record",
        "validate_decision_sufficiency",
    }
    assert forbidden.isdisjoint(vars(registry_module))
    assert "decision_sufficiency" not in registry_module.SCHEMA_IDS


def test_canonical_generator_and_readback(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(workspace), "--generate-role-views"]) == 0
    assert capsys.readouterr().out == "MODEL_PROFILE_ROLE_VIEWS=generated:1\n"
    role_text = (workspace / ".codex" / "agents" / "sol_parent.toml").read_text(encoding="utf-8")
    assert "generated role view: generated_role_view_v1" in role_text
    assert "@dependency-start" not in role_text
    assert 'model = "model-sol"' in role_text
    assert "Use the role-specific contract." in role_text
    projection = json.loads((workspace / "agents" / "agents_config.json").read_text(encoding="utf-8"))
    assert projection["roles"][0]["projection_digest"]
    assert main(["--root", str(workspace), "--check-role-views"]) == 0
    assert capsys.readouterr().out == "MODEL_PROFILE_ROLE_VIEWS=pass\n"


def test_generator_rejects_unbound_registered_role(workspace: Path) -> None:
    config = workspace / ".codex" / "config.toml"
    config.write_text(config.read_text(encoding="utf-8") + '\n[agents.extra]\ndescription = "Extra"\nconfig_file = "agents/extra.toml"\n', encoding="utf-8")
    registry = load_model_profile_registry(workspace)
    with pytest.raises(ModelProfileRegistryError, match="binding_registration_set_mismatch"):
        generate_role_views(registry, workspace)


def test_canonical_consumer_static_projection_is_typed_closed_and_mode_invariant() -> None:
    """All canonical roles have source-free static clauses and one digest."""
    root = Path(__file__).resolve().parents[2]
    registry = load_model_profile_registry(root)
    live = {view.role_id: view for view in generate_role_views(registry, root, projection="live")}
    static = {
        view.role_id: view
        for view in generate_role_views(registry, root, projection="consumer-static")
    }
    assert len(live) == len(static) == 35
    assert set(live) == set(registry.role_profile_bindings)
    assert [item.obligation_id for item in STATIC_OBLIGATION_TABLE] == [
        "validation_owner",
        "parent_assignment",
        "parent_authority",
        "stop_handback",
    ]
    clauses = {
        clause.clause_id: clause
        for role_id in registry.role_profile_bindings
        for clause in registry.instruction_clauses_for_role(role_id)
    }
    for clause_id, required in REQUIRED_STATIC_OBLIGATION_SETS.items():
        projection = clauses[clause_id].consumer_static_projection
        assert projection is not None
        assert set(projection.static_obligations) == required
    for role_id in live:
        before, after = live[role_id], static[role_id]
        for field in (
            "name",
            "description",
            "nickname_candidates",
            "sandbox_mode",
            "approval_policy",
            "model",
            "reasoning_effort",
        ):
            assert getattr(before, field) == getattr(after, field)
        assert before.source_canonical_digest == after.source_canonical_digest
        assert all(
            prefix not in after.rendered_instructions.casefold()
            for prefix in (
                "agents/skills/",
                "agents/model_profiles.toml",
                "tools/agent_tools/",
                "../../agents/",
                "../../tools/",
            )
        )
    for role_id in ("python_reviewer", "spark_worker", "worker"):
        assert live[role_id].rendered_instructions != static[role_id].rendered_instructions
    generated_config = json.loads(
        (root / "agents" / "agents_config.json").read_text(encoding="utf-8")
    )
    for role_id, view in static.items():
        assert generated_config["agent_views"][role_id]["developer_instructions"] == (
            view.rendered_instructions
        )
    assert len(generated_config["agent_views"]) == len(generated_config["roles"]) == 35


def test_missing_projection_for_path_bearing_clause_is_rejected(workspace: Path) -> None:
    """A producer path cannot silently enter a consumer-static render."""
    path = workspace / "agents" / "model_profiles.toml"
    text = path.read_text(encoding="utf-8").replace(
        'text = "Use closed contracts."',
        'text = "Use agents/skills/not-a-consumer-path."',
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ModelProfileRegistryError, match="consumer_static_projection_required"):
        load_model_profile_registry(workspace)


@pytest.mark.parametrize(
    ("clause_id", "replacement"),
    (
        ("python_solid_boundary", 'static_obligations = ["validation_owner"]'),
        (
            "luna_impl",
            'static_obligations = ["validation_owner", "parent_assignment", "parent_authority"]',
        ),
    ),
)
def test_canonical_clause_obligation_omission_or_wrong_set_is_rejected(
    clause_id: str,
    replacement: str,
    tmp_path: Path,
) -> None:
    """Canonical path-bearing clauses require their exact closed obligation sets."""
    root = tmp_path / "canonical-root"
    path = root / "agents" / "model_profiles.toml"
    path.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "agents" / "model_profiles.toml",
        path,
    )
    original = path.read_text(encoding="utf-8")
    if clause_id == "python_solid_boundary":
        needle = 'static_obligations = ["validation_owner", "parent_assignment"]'
    else:
        needle = (
            'static_obligations = ["validation_owner", "parent_assignment", '
            '"parent_authority", "stop_handback"]'
        )
    assert needle in original
    mutated = original.replace(needle, replacement, 1)
    path.write_text(mutated, encoding="utf-8")
    try:
        with pytest.raises(ModelProfileRegistryError, match="required_static_obligations_mismatch"):
            load_model_profile_registry(root)
    finally:
        path.write_text(original, encoding="utf-8")
