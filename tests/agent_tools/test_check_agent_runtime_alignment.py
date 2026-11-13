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
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
import yaml

from tools.agent.orchestration.packets import (
    resolve_active_design_packet_config,
    resolve_cross_cutting_document_packet,
    resolve_document_section_locators,
    resolve_role_document_packet,
)
from tools.agent.orchestration.team_config import (
    TaskCatalog,
    load_team_config,
    resolve_role,
    select_roles,
)
from tools.repository.workspace.workspace_scope import (
    resolve_report_bundle_artifact_path,
)

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


def task_catalog_from_raw(raw: dict[str, object]) -> TaskCatalog:
    """Build the public TaskCatalog value from the shared configuration owner."""
    return TaskCatalog(
        raw=raw,
        workflow_families=tuple(raw["workflow_families"]),  # type: ignore[arg-type]
        tasks=tuple(raw["tasks"]),  # type: ignore[arg-type]
        review_packs=tuple(raw["review_packs"]),  # type: ignore[arg-type]
    )


def loaded_task_catalog_raw() -> dict[str, object]:
    """Return the checked-in task catalog as mutable data for direct API tests."""
    return yaml.safe_load(
        (PROJECT_ROOT / "agents/task_catalog.yaml").read_text(encoding="utf-8")
    )


def test_missing_report_bundle_path_uses_existing_git_parent(tmp_path: Path) -> None:
    """A future report bundle is resolved without being created."""
    parent = tmp_path / "parent"
    subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
    report_dir = parent / "reports/agents/future-run"
    resolved = resolve_report_bundle_artifact_path(report_dir, "intent_brief.md")
    assert resolved == report_dir / "intent_brief.md"
    assert not report_dir.exists()


def test_native_runtime_alignment_passes_canonical_sources() -> None:
    result = run_alignment(PROJECT_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.rstrip().endswith("AGENT_RUNTIME_ALIGNMENT=pass")


def test_team_configuration_keeps_integration_and_publisher_as_worker_mappings() -> (
    None
):
    """Integration and publication roles remain child mappings, not parent routes."""
    config = load_team_config()
    specialists = {
        str(role["id"]): role
        for role in cast(list[dict[str, object]], config.raw["specialist_roles"])
    }
    for role_id in ("integration_executor", "publisher"):
        assert specialists[role_id]["codex_agents"] == ["worker"]
    topology = cast(
        dict[str, object], loaded_task_catalog_raw()["role_topology_defaults"]
    )
    families = cast(dict[str, list[str]], topology["role_families"])
    assert "integration_executor" in families["integration"]
    assert "publisher" in families["publication"]


def test_team_configuration_keeps_skill_evaluator_on_its_explicit_task() -> None:
    """The evaluator is an optional specialist reserved for T14."""
    config = load_team_config()
    evaluator = resolve_role(config, "skill_evaluator")
    assert evaluator in config.specialist_roles
    assert evaluator.activation == "explicit_empirical_skill_evaluation"
    catalog = loaded_task_catalog_raw()
    t14 = next(task for task in catalog["tasks"] if task["id"] == "T14")
    assert "skill_evaluator" in t14["specialists"]
    assert all(
        "skill_evaluator" not in task["specialists"]
        for task in catalog["tasks"]
        if task["id"] != "T14"
    )


def test_full_team_role_selection_keeps_skill_evaluator_isolated() -> None:
    """Full-team selection never leaks the empirical evaluator across workflows."""
    config = load_team_config()
    catalog = task_catalog_from_raw(loaded_task_catalog_raw())
    comprehensive = select_roles(
        config,
        [],
        full_team=True,
        catalog=catalog,
        workflow_family_id="comprehensive_development",
    )
    evaluation = select_roles(
        config,
        [],
        full_team=True,
        catalog=catalog,
        workflow_family_id="skill_evaluation",
    )
    assert "skill_evaluator" not in {role.id for role in comprehensive}
    assert [role.id for role in evaluation] == ["skill_evaluator"]


def test_skill_evaluator_context_is_limited_to_its_scenario_packet() -> None:
    """The role context policy shares only its current packet and listed files."""
    config = load_team_config()
    policy = next(
        policy
        for policy in config.context_policies
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
    }.issubset(set(cast(list[str], policy["do_not_share"])))


def test_t14_role_selection_uses_only_skill_evaluator() -> None:
    """T14 selects the isolated evaluator through the shared team/task API."""
    config = load_team_config()
    catalog = task_catalog_from_raw(loaded_task_catalog_raw())
    evaluator_roles = select_roles(
        config,
        ["skill_evaluator"],
        full_team=False,
        catalog=catalog,
        workflow_family_id="skill_evaluation",
    )
    assert [role.id for role in evaluator_roles] == ["skill_evaluator"]
    assert evaluator_roles[0].codex_agents == ("skill_evaluator",)


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


def test_template_workspace_can_resolve_shared_document_packets() -> None:
    """Shared docs remain resolvable when the derived workspace omits AgentCanon."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        entries = resolve_cross_cutting_document_packet(workspace, PROJECT_ROOT)
        review_process = (
            PROJECT_ROOT / "documents/conventions/REVIEW_PROCESS.md"
        ).resolve()
        assert review_process in {entry.path for entry in entries}
        assert all(entry.path.exists() for entry in entries)

        config = load_team_config()
        role = resolve_role(config, "design_reviewer")
        active_packet = resolve_active_design_packet_config(config)
        assert active_packet.schema == "waterfall.design_packet.v1"
        assert (
            active_packet.implementation_source_packet.entry_id
            == "implementation-source-packet"
        )
        packet = resolve_role_document_packet(
            config=config,
            role=role,
            report_dir=workspace / "runtime/reports/agents/_packet_probe",
            workspace_root=workspace,
            active_design_packet=active_packet,
            agentcanon_source_root=PROJECT_ROOT,
        )
        non_artifact_paths = {
            entry.path
            for entry in packet.read_before_work
            if not entry.rationale.startswith("run artifact:")
        }
        assert review_process in non_artifact_paths
        assert all(entry.exists() for entry in non_artifact_paths)


def test_role_document_packets_use_typed_section_locators() -> None:
    """Document section selectors stay distinct from paths and fail if headings move."""
    config = load_team_config()
    role = resolve_role(config, "implementer")
    active_packet = resolve_active_design_packet_config(config)
    with tempfile.TemporaryDirectory() as tmp_dir:
        packet = resolve_role_document_packet(
            config=config,
            role=role,
            report_dir=Path(tmp_dir) / "runtime/reports/agents/_packet_probe",
            workspace_root=PROJECT_ROOT,
            active_design_packet=active_packet,
            agentcanon_source_root=PROJECT_ROOT,
        )
    sectioned_entries = [entry for entry in packet.read_before_work if entry.sections]
    assert sectioned_entries
    assert all("#" not in str(entry.path) for entry in sectioned_entries)
    for filename, heading in (
        ("CODEX_BOOTSTRAP.md", "4. Run Context"),
        ("CODEX_IMPLEMENTATION.md", "5. Implementation"),
    ):
        entry = next(
            entry for entry in sectioned_entries if entry.path.name == filename
        )
        assert {section.heading for section in entry.sections} == {heading}
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_heading_doc = Path(tmp_dir) / "CODEX_IMPLEMENTATION.md"
        missing_heading_doc.write_text("# Workflow\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="section_locator_heading_missing:"):
            resolve_document_section_locators(
                "implementer",
                "agents/canonical/CODEX_IMPLEMENTATION.md",
                missing_heading_doc,
            )
