"""Native integration tests for generated role-view write and readback."""

# @dependency-start
# contract test
# responsibility Verifies native role-view materialization, projection metadata, and drift detection.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/model_profiles.rs owns role view generation and readback
# downstream implementation ../../tools/bin/agent-canon evaluate-codex-agent-roles owns the public CLI
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", str(PROJECT_ROOT / "tools/bin/agent-canon"))
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "agents").mkdir(parents=True)
    (root / ".codex/agents").mkdir(parents=True)
    (root / "agents/model_profiles.toml").write_text(
        """schema_id = "model_profile_registry_v1"
registry_id = "test"
registry_version = 1
[writer_isolation_policy]
current_checkout_mode = "parallel_only_for_disjoint_paths_without_shared_state"
parallel_requirements = ["disjoint_paths", "no_shared_git_index_or_head", "no_generated_or_formatter_effects"]
collision_action = "reject_same_checkout_root_before_spawn"
isolated_worktree_mode = "explicit_alternative_implementation_experiment_only"
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
role_template = "{role_id} {model_alias} {base_prompt}"
capabilities = ["orchestration"]
allowed_context = ["objective", "context"]
forbidden_context = ["raw_history"]
return_schema_id = "claim_evidence.v1"
checkpoint_policy = "observation"
continuation_policy = "same_session"
projection_digest = "computed_sha256_v1"
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
""",
        encoding="utf-8",
    )
    (root / "agents/agents_config.json").write_text(
        json.dumps(
            {
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
    (root / ".codex/config.toml").write_text(
        "model_context_window = 1050000\n"
        "model_auto_compact_token_limit = 900000\n"
        "[agents]\nmax_threads = 1\n"
        '[agents.sol_parent]\ndescription = "Parent"\nconfig_file = "agents/sol_parent.toml"\n',
        encoding="utf-8",
    )
    return root


def run_role_views(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(AGENT_CANON_CLI),
            "evaluate-codex-agent-roles",
            "--root",
            str(root),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_native_role_view_generation_and_readback(workspace: Path) -> None:
    """The native writer renders both Codex and consumer-static views."""
    result = run_role_views(workspace, "--generate-role-views")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "MODEL_PROFILE_ROLE_VIEWS=generated:1\n"

    role_text = (workspace / ".codex/agents/sol_parent.toml").read_text(
        encoding="utf-8"
    )
    assert "generated role view: generated_role_view_v1" in role_text
    assert "@dependency-start" not in role_text
    assert 'model = "model-sol"' in role_text
    assert "model_context_window = 1050000" in role_text
    assert "model_auto_compact_token_limit = 900000" in role_text
    assert "Use the role-specific contract." in role_text
    projection = json.loads(
        (workspace / "agents/agents_config.json").read_text(encoding="utf-8")
    )
    assert projection["roles"][0]["projection_digest"]
    assert projection["generated_profile_projection"]["materializer"] == (
        "tools/bin/agent-canon evaluate-codex-agent-roles --generate-role-views"
    )

    check = run_role_views(workspace, "--check-role-views")
    assert check.returncode == 0, check.stdout + check.stderr
    assert check.stdout == "MODEL_PROFILE_ROLE_VIEWS=pass\n"


def test_native_role_view_check_reports_role_file_drift(workspace: Path) -> None:
    generated = run_role_views(workspace, "--generate-role-views")
    assert generated.returncode == 0, generated.stdout + generated.stderr
    role_file = workspace / ".codex/agents/sol_parent.toml"
    role_file.write_text(
        role_file.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8"
    )

    result = run_role_views(workspace, "--check-role-views")
    assert result.returncode == 1
    assert (
        f"role_view.content_drift:{role_file.relative_to(workspace)}" in result.stdout
    )


def test_native_role_view_generation_rejects_unregistered_configured_role(
    workspace: Path,
) -> None:
    config = workspace / ".codex/config.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[agents.extra]\ndescription = "Extra"\nconfig_file = "agents/extra.toml"\n',
        encoding="utf-8",
    )
    result = run_role_views(workspace, "--generate-role-views")
    assert result.returncode == 1
    assert "role_projection:binding_registration_set_mismatch" in result.stdout
