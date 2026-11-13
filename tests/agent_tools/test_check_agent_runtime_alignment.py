"""Native integration tests for repository runtime alignment checks."""

# @dependency-start
# contract test
# responsibility Checks profile, catalog, role, hook, and public skill document drift through the native CLI.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/runtime_alignment.rs owns the native alignment checker
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", str(PROJECT_ROOT / "tools/bin/agent-canon"))
)


def alignment_workspace(tmp_path: Path) -> Path:
    """Copy the canonical role, skill, and Codex runtime surfaces into a fixture."""
    root = tmp_path / "root"
    shutil.copytree(PROJECT_ROOT / "agents", root / "agents")
    shutil.copytree(PROJECT_ROOT / ".codex", root / ".codex")
    return root


def run_alignment(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_CANON_CLI), "check-agent-runtime-alignment", "--root", str(root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_task_catalog_data() -> dict[str, object]:
    """Read the canonical task data used by native alignment tests."""
    return yaml.safe_load(
        (PROJECT_ROOT / "agents/task_catalog.yaml").read_text(encoding="utf-8")
    )


def test_native_runtime_alignment_passes_canonical_sources() -> None:
    result = run_alignment(PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.rstrip().endswith("AGENT_RUNTIME_ALIGNMENT=pass")


def test_canonical_role_data_keeps_integration_and_publisher_on_worker() -> None:
    """Role source maps integration and publication onto the worker executable."""
    aligned = run_alignment(PROJECT_ROOT)
    assert aligned.returncode == 0, aligned.stdout + aligned.stderr
    config = json.loads(
        (PROJECT_ROOT / "agents/agents_config.json").read_text(encoding="utf-8")
    )
    specialists = {str(role["id"]): role for role in config["specialist_roles"]}
    for role_id in ("integration_executor", "publisher"):
        assert specialists[role_id]["codex_agents"] == ["worker"]
    topology = load_task_catalog_data()["role_topology_defaults"]
    families = topology["role_families"]
    assert "integration_executor" in families["integration"]
    assert "publisher" in families["publication"]


def test_team_configuration_keeps_skill_evaluator_on_its_explicit_task() -> None:
    """Native alignment and source records reserve the evaluator for T14."""
    aligned = run_alignment(PROJECT_ROOT)
    assert aligned.returncode == 0, aligned.stdout + aligned.stderr
    config = json.loads(
        (PROJECT_ROOT / "agents/agents_config.json").read_text(encoding="utf-8")
    )
    evaluator = next(
        role for role in config["specialist_roles"] if role["id"] == "skill_evaluator"
    )
    assert evaluator["activation"] == "explicit_empirical_skill_evaluation"
    assert evaluator["codex_agents"] == ["skill_evaluator"]
    catalog = load_task_catalog_data()
    t14 = next(task for task in catalog["tasks"] if task["id"] == "T14")
    assert "skill_evaluator" in t14["specialists"]
    assert all(
        "skill_evaluator" not in task["specialists"]
        for task in catalog["tasks"]
        if task["id"] != "T14"
    )


def test_skill_evaluator_context_is_limited_to_its_scenario_packet() -> None:
    """Role source limits evaluator visibility to its scenario packet."""
    aligned = run_alignment(PROJECT_ROOT)
    assert aligned.returncode == 0, aligned.stdout + aligned.stderr
    config = json.loads(
        (PROJECT_ROOT / "agents/agents_config.json").read_text(encoding="utf-8")
    )
    policy = next(
        policy
        for policy in config["context_policies"]
        if policy.get("roles") == ["skill_evaluator"]
    )
    assert policy["share_only"] == [
        "current_scenario_packet",
        "packet_listed_evaluation_files",
    ]
    assert {
        "user_request_contract.md",
        "team_manifest.yaml",
        "agent_evaluation.md",
        "prior_answers",
        "prior_reports",
        "evaluator_artifacts",
        "full_session_context",
    }.issubset(set(policy["do_not_share"]))


def test_native_runtime_alignment_detects_profile_sandbox_policy_drift(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    registry = root / "agents/model_profiles.toml"
    registry.write_text(
        registry.read_text(encoding="utf-8").replace(
            'explorer = "read-only"', 'explorer = "workspace-write"'
        ),
        encoding="utf-8",
    )
    result = run_alignment(root)
    assert result.returncode == 1
    assert "sandbox-policy-expected-read-only" in result.stdout


def test_native_runtime_alignment_detects_task_family_role_drift(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    catalog_path = root / "agents/task_catalog.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    task = next(task for task in catalog["tasks"] if task["id"] == "T14")
    task["family"] = "comprehensive_development"
    catalog_path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")

    result = run_alignment(root)
    assert result.returncode == 1
    assert "must-use-skill-evaluation-family" in result.stdout


def test_native_runtime_alignment_reserves_skill_evaluator_from_other_roles(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    team_path = root / "agents/agents_config.json"
    team = json.loads(team_path.read_text(encoding="utf-8"))
    experimenter = next(
        role for role in team["specialist_roles"] if role["id"] == "experimenter"
    )
    experimenter["codex_agents"].append("skill_evaluator")
    team_path.write_text(json.dumps(team, indent=2) + "\n", encoding="utf-8")

    result = run_alignment(root)
    assert result.returncode == 1
    assert (
        "skill-evaluator-candidate-reserved-for-skill-evaluator-role" in result.stdout
    )


def test_native_runtime_alignment_detects_unregistered_public_skill_doc(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    (root / "agents/skills/unregistered-public-skill.md").write_text(
        "# Unregistered public skill\n", encoding="utf-8"
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "non-catalog-public-doc" in result.stdout


def test_native_runtime_alignment_detects_unregistered_public_skill_shim(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    shim = root / ".codex/personal/skills/unregistered-public-skill/SKILL.md"
    shim.parent.mkdir(parents=True)
    shim.write_text(
        "---\nname: unregistered-public-skill\ndescription: Extra.\n---\n",
        encoding="utf-8",
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "public-shim-missing-catalog-entry" in result.stdout


def test_native_runtime_alignment_keeps_official_system_skill_host_provided(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    shim = root / ".codex/personal/skills/openai-docs/SKILL.md"
    shim.parent.mkdir(parents=True)
    shim.write_text("---\nname: openai-docs\n---\n", encoding="utf-8")

    result = run_alignment(root)
    assert result.returncode == 1
    assert "host-provided-skill-must-not-be-local" in result.stdout


def test_native_runtime_alignment_rejects_duplicate_public_skill_readme_rows(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    readme = root / "agents/skills/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n| duplicate | `agents/skills/agent-orchestration.md` | `.codex/personal/skills/agent-orchestration/SKILL.md` |\n",
        encoding="utf-8",
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "duplicate-public-catalog-rows" in result.stdout


def test_native_runtime_alignment_detects_inactive_hook_registration(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    hooks_path = root / ".codex/hooks.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    hooks["hooks"]["Stop"] = []
    hooks_path.write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")

    result = run_alignment(root)
    assert result.returncode == 1
    assert "inactive-event-must-not-be-registered" in result.stdout


def test_native_runtime_alignment_detects_missing_role_authority_doc_marker(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    readme = root / ".codex/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "tools/bin/agent-canon evaluate-codex-agent-roles", "retired-role-tool"
        ),
        encoding="utf-8",
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "missing-role-profile-marker" in result.stdout


def test_native_runtime_alignment_requires_every_permanent_team_doc_mapping(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    subagents = root / "agents/canonical/CODEX_SUBAGENTS.md"
    subagents.write_text(
        subagents.read_text(encoding="utf-8").replace(
            "| `verifier` | prescribed validation runner |\n", ""
        ),
        encoding="utf-8",
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "permanent-team-mapping-missing:verifier" in result.stdout


def test_native_runtime_alignment_rejects_generated_role_authority_claim(
    tmp_path: Path,
) -> None:
    root = alignment_workspace(tmp_path)
    readme = root / ".codex/README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nChild model settings remain in role TOMLs.\n",
        encoding="utf-8",
    )

    result = run_alignment(root)
    assert result.returncode == 1
    assert "stale-generated-role-authority" in result.stdout
