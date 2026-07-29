# @dependency-start
# contract test
# responsibility Tests test check agent runtime alignment behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates runtime alignment contracts
# @dependency-end

"""Integration test for the agent runtime alignment checker."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import cast
from unittest.mock import patch

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import check_agent_runtime_alignment as runtime_alignment  # noqa: E402
from agent_team import (  # noqa: E402
    TaskCatalog,
    codex_runtime_max_depth,
    load_team_config,
    resolve_active_design_packet_config,
    resolve_cross_cutting_document_packet,
    resolve_document_section_locators,
    resolve_role,
    resolve_role_document_packet,
    workflow_topology_policy_violations,
)
from check_agent_runtime_alignment import validate_permanent_team_mapping  # noqa: E402


def task_catalog_from_raw(raw: dict[str, object]) -> TaskCatalog:
    """Build a TaskCatalog value from parsed YAML."""
    return TaskCatalog(
        raw=raw,
        workflow_families=tuple(raw["workflow_families"]),  # type: ignore[arg-type]
        tasks=tuple(raw["tasks"]),  # type: ignore[arg-type]
        review_packs=tuple(raw["review_packs"]),  # type: ignore[arg-type]
    )


def loaded_task_catalog_raw() -> dict[str, object]:
    """Return a mutable copy of the checked-in task catalog."""
    return yaml.safe_load(
        (PROJECT_ROOT / "agents" / "task_catalog.yaml").read_text(encoding="utf-8")
    )


class AgentRuntimeAlignmentTest(unittest.TestCase):
    """Verify that the runtime alignment checker passes on the checked-in canon."""

    @staticmethod
    def write_minimal_dependency_map(root: Path) -> None:
        """Write the typed dependency record required by route catalog loading."""
        (root / "agents" / "skills" / "skill-dependencies.yaml").write_text(
            "\n".join(
                [
                    "version: 1",
                    "skill_dependencies:",
                    "  example:",
                    "    responsibility_group: fixture",
                    "    required_prerequisites: []",
                    "    routing_candidates: []",
                    "    successors: []",
                    "    order_constraints: []",
                    "    parallel_independent: []",
                ]
            ),
            encoding="utf-8",
        )

    def test_alignment_script_passes(self) -> None:
        """The runtime alignment checker should succeed without findings."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AGENT_RUNTIME_ALIGNMENT=pass", result.stdout)

    def test_permanent_team_mapping_requires_every_configured_role(self) -> None:
        """The CODEX_SUBAGENTS mapping should not omit configured team roles."""
        config = load_team_config()
        subagents_path = PROJECT_ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md"
        text = subagents_path.read_text(encoding="utf-8")
        text_without_verifier = text.replace("| `verifier` | parent validation runner |\n", "")

        with self.assertRaisesRegex(
            RuntimeError,
            "permanent-team mapping missing roles: verifier",
        ):
            validate_permanent_team_mapping(config, text_without_verifier)

    def test_skill_evaluator_is_staged_only_for_the_evaluation_route(self) -> None:
        """The evaluator is catalog-staged without becoming a default for other tasks."""
        config = load_team_config()
        evaluator = resolve_role(config, "skill_evaluator")
        self.assertIn(evaluator, config.specialist_roles)
        self.assertEqual(evaluator.activation, "explicit_empirical_skill_evaluation")
        catalog = loaded_task_catalog_raw()
        topology = cast(dict[str, object], catalog["role_topology_defaults"])
        stage_waves = cast(list[object], topology["stage_waves"])
        staged_ids: set[str] = set()
        intake_role_ids: list[str] = []
        evaluation_role_ids: list[str] = []
        for raw_wave in stage_waves:
            wave = cast(dict[str, object], raw_wave)
            wave_role_ids = cast(list[object], wave["role_ids"])
            if wave["id"] == "intake":
                intake_role_ids = [cast(str, role_id) for role_id in wave_role_ids]
            if wave["id"] == "skill_evaluation":
                evaluation_role_ids = [cast(str, role_id) for role_id in wave_role_ids]
            for raw_role_id in wave_role_ids:
                staged_ids.add(cast(str, raw_role_id))
        self.assertIn("skill_evaluator", staged_ids)
        self.assertEqual(intake_role_ids, ["manager"])
        self.assertEqual(evaluation_role_ids, ["skill_evaluator"])

    def test_full_team_keeps_skill_evaluator_isolated(self) -> None:
        """Full-team routes must not leak the empirical evaluator across workflows."""
        config = load_team_config()
        catalog = runtime_alignment.load_task_catalog(config)

        comprehensive_roles = runtime_alignment.select_roles(
            config,
            [],
            full_team=True,
            catalog=catalog,
            workflow_family_id="comprehensive_development",
        )
        evaluation_roles = runtime_alignment.select_roles(
            config,
            [],
            full_team=True,
            catalog=catalog,
            workflow_family_id="skill_evaluation",
        )

        self.assertNotIn("skill_evaluator", {role.id for role in comprehensive_roles})
        self.assertEqual([role.id for role in evaluation_roles], ["skill_evaluator"])

    def test_team_config_rejects_skill_evaluator_candidate_on_ordinary_role(self) -> None:
        """An ordinary role cannot retain the evaluator as a trailing fallback."""
        config = load_team_config()
        experimenter = resolve_role(config, "experimenter")
        mutated_experimenter = replace(
            experimenter,
            codex_agents=(*experimenter.codex_agents, "skill_evaluator"),
        )
        mutated_config = replace(
            config,
            specialist_roles=tuple(
                mutated_experimenter if role.id == "experimenter" else role
                for role in config.specialist_roles
            ),
        )

        with patch.object(runtime_alignment, "load_team_config", return_value=mutated_config):
            with self.assertRaisesRegex(
                RuntimeError,
                "experimenter codex_agents must not include skill_evaluator",
            ):
                runtime_alignment.validate_team_config_references()

    def test_team_config_rejects_unknown_active_design_packet_field(self) -> None:
        """Runtime alignment consumes the shared closed packet schema."""
        config = load_team_config()
        packet = cast(
            dict[str, object],
            config.artifact_registry["active_design_packet"],
        )
        mutated_config = replace(
            config,
            artifact_registry={
                **config.artifact_registry,
                "active_design_packet": {
                    **packet,
                    "unexpected_contract": True,
                },
            },
        )

        with patch.object(runtime_alignment, "load_team_config", return_value=mutated_config):
            with self.assertRaisesRegex(
                RuntimeError,
                r"^artifacts\.active_design_packet:field_unknown:unexpected_contract$",
            ):
                runtime_alignment.validate_team_config_references()

    def test_workflow_topology_rejects_evaluator_in_non_evaluation_family(self) -> None:
        """The shared topology policy must isolate the evaluator by family."""
        raw = loaded_task_catalog_raw()
        families = cast(list[dict[str, object]], raw["workflow_families"])
        comprehensive = next(
            family for family in families if family["id"] == "comprehensive_development"
        )
        roles = cast(dict[str, object], comprehensive["roles"])
        specialists = cast(list[str], roles["specialists"])
        specialists.append("skill_evaluator")
        catalog = task_catalog_from_raw(raw)

        self.assertIn(
            (
                "comprehensive_development",
                "skill-evaluator-only-in-skill-evaluation",
            ),
            workflow_topology_policy_violations(catalog),
        )

    def test_skill_evaluator_context_is_packet_only(self) -> None:
        """The evaluator receives only its scenario packet and listed files."""
        config = load_team_config()
        policy = next(
            policy
            for policy in config.context_policies
            if policy.get("roles") == ["skill_evaluator"]
        )

        self.assertEqual(
            policy["share_only"],
            ["current_scenario_packet", "packet_listed_evaluation_files"],
        )
        self.assertTrue(
            {
                "user_request_contract.md",
                "team_manifest.yaml",
                "agent_evaluation.md",
                "prior_answers",
                "prior_reports",
                "evaluator_artifacts",
                "full_session_context",
            }.issubset(set(cast(list[str], policy["do_not_share"]))),
        )

    def test_t14_materializes_only_skill_evaluator(self) -> None:
        """T14 must not inherit worker or reviewer waves from comprehensive delivery."""
        config = load_team_config()
        catalog = runtime_alignment.load_task_catalog(config)
        specialists = runtime_alignment.default_specialists_for_task(config, catalog, "T14")
        roles = runtime_alignment.select_roles(
            config,
            list(specialists),
            full_team=False,
            catalog=catalog,
            workflow_family_id="skill_evaluation",
        )
        active_budget, _ = runtime_alignment.workflow_spawn_budget(catalog, "skill_evaluation")
        initial_wave = runtime_alignment.recommended_initial_subagent_wave(
            roles, active_budget, catalog
        )
        expansion_waves = runtime_alignment.recommended_dynamic_expansion_wave_slots(
            roles, active_budget, initial_wave, catalog
        )
        materialized = list(initial_wave) + [
            slot.agent_type for wave in expansion_waves for slot in wave
        ]

        self.assertEqual([role.id for role in roles], ["skill_evaluator"])
        self.assertEqual(initial_wave, ("skill_evaluator",))
        self.assertEqual(expansion_waves, ())
        self.assertEqual(materialized, ["skill_evaluator"])
        self.assertNotIn("worker", materialized)
        self.assertNotIn("spark_worker", materialized)

    def test_task_catalog_rejects_t14_comprehensive_route(self) -> None:
        """Alignment must reject T14 when it regresses to the normal delivery family."""
        raw = loaded_task_catalog_raw()
        tasks = cast(list[dict[str, object]], raw["tasks"])
        t14 = next(task for task in tasks if task["id"] == "T14")
        t14["family"] = "comprehensive_development"
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "skill_evaluation workflow family"):
                runtime_alignment.validate_task_catalog_references()

    def test_task_catalog_rejects_stale_implementation_role_family(self) -> None:
        """Alignment must keep worker as the default implementation family member."""
        raw = loaded_task_catalog_raw()
        topology = cast(dict[str, object], raw["role_topology_defaults"])
        families = cast(dict[str, object], topology["role_families"])
        families["implementation"] = ["spark_worker", "worker"]
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "implementation role family"):
                runtime_alignment.validate_task_catalog_references()

    def test_checked_in_workflow_topologies_use_active_decision_roles(self) -> None:
        """Repo-changing families keep reviewers deferred until their decision exists."""
        catalog = task_catalog_from_raw(loaded_task_catalog_raw())

        self.assertEqual(workflow_topology_policy_violations(catalog), ())

    def test_workflow_topology_policy_rejects_always_on_delivery_reviewer(self) -> None:
        """A delivery reviewer must not return to an always-on child wave."""
        raw = loaded_task_catalog_raw()
        families = cast(list[dict[str, object]], raw["workflow_families"])
        scoped = next(family for family in families if family["id"] == "scoped_change")
        roles = cast(dict[str, object], scoped["roles"])
        always_on = cast(list[str], roles["always_on"])
        specialists = cast(list[str], roles["specialists"])
        always_on.append("manager_reviewer")
        specialists.remove("manager_reviewer")
        catalog = task_catalog_from_raw(raw)

        self.assertIn(
            ("scoped_change", "delivery-producer-core"),
            workflow_topology_policy_violations(catalog),
        )

    def test_alignment_rejects_worker_model_policy_drift(self) -> None:
        """Alignment enforces the exact worker model and effort."""
        configs = runtime_alignment.parse_codex_agents()
        configs["worker"] = {**configs["worker"], "model": "gpt-5.5"}

        with patch.object(runtime_alignment, "parse_codex_agents", return_value=configs):
            with self.assertRaisesRegex(
                RuntimeError,
                "worker model must project registry profile luna_implementation_xhigh",
            ):
                runtime_alignment.validate_codex_agent_settings()

    def test_alignment_assigns_mini_only_to_skill_evaluator(self) -> None:
        """Ordinary roles use Luna/high while T14 owns the mini exception."""
        configs = runtime_alignment.parse_codex_agents()

        for role_id in ("explorer", "experiment_runner"):
            self.assertEqual(configs[role_id]["model"], "gpt-5.6-luna")
            self.assertEqual(configs[role_id]["model_reasoning_effort"], "high")

        mini_roles = {
            role_id
            for role_id, config in configs.items()
            if config.get("model") == "gpt-5.4-mini"
        }
        self.assertEqual(mini_roles, {"skill_evaluator"})
        self.assertEqual(configs["skill_evaluator"]["model_reasoning_effort"], "medium")

    def test_decision_sufficiency_has_one_owner_and_pointer_only_consumers(self) -> None:
        """DSV semantics stay canonical while packets, Spark, closeout, and evals consume it."""
        owner = (
            PROJECT_ROOT / "agents" / "skills" / "agent-orchestration.md"
        ).read_text(encoding="utf-8")
        agent_team = (
            PROJECT_ROOT / "tools" / "agent_tools" / "agent_team.py"
        ).read_text(encoding="utf-8")
        lifecycle_contract = (
            PROJECT_ROOT
            / "tools"
            / "agent_tools"
            / "update_lifecycle_contract.py"
        ).read_text(encoding="utf-8")
        subagents = (
            PROJECT_ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md"
        ).read_text(encoding="utf-8")
        consumer_docs = [
            PROJECT_ROOT / ".agents" / "skills" / "agent-orchestration" / "SKILL.md",
            PROJECT_ROOT / "agents" / "skills" / "task-routing.md",
            PROJECT_ROOT / "agents" / "skills" / "agent-canon-update.md",
            PROJECT_ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md",
        ]

        self.assertEqual(owner.count("## Decision Sufficiency Packet"), 1)
        self.assertIn("唯一の意味論 owner", owner)
        self.assertNotIn("def validate_decision_sufficiency_packet", agent_team)
        self.assertNotIn("def validate_decision_sufficiency_packet", lifecycle_contract)
        self.assertIn(
            'DECISION_SUFFICIENCY_OWNER = "agents/skills/agent-orchestration.md#Decision Sufficiency Packet"',
            agent_team,
        )
        self.assertIn("import_decision_sufficiency_verdict", agent_team)
        self.assertIn("selected owner gate", subagents)
        self.assertIn("decision_sufficiency_packet_ref", agent_team)
        for path in consumer_docs:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("## Decision Sufficiency Packet", text)
                self.assertNotIn('"schema": "agent-canon.decision-sufficiency.v1"', text)

    def test_generated_role_views_cannot_claim_model_authority(self) -> None:
        """Both runtime docs reject generated-view authority and manual model edits."""
        docs = (
            PROJECT_ROOT / ".codex" / "README.md",
            PROJECT_ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md",
        )
        for path in docs:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    runtime_alignment.generated_role_authority_contradictions(text),
                    (),
                )
        stale_claims = (
            ".codex/agents/*.toml is the source of truth for model and reasoning.",
            "Update role TOMLs to change model reasoning.",
            "role model / reasoning を変えるときは .codex/agents/*.toml を更新します",
            "agent TOMLs are authoritative for model/reasoning.",
            "Edit generated role TOMLs manually.",
            "role の model / model_reasoning_effort は各 agent TOML が正本です。",
            "model / reasoning を変更するときは .codex/agents/*.toml を更新し、検証します。",
        )
        for path in docs:
            for claim in stale_claims:
                with self.subTest(path=path, claim=claim):
                    self.assertTrue(
                        runtime_alignment.generated_role_authority_contradictions(claim)
                    )

    def test_registry_generated_readback_wording_is_not_an_authority_contradiction(self) -> None:
        """Canonical source and generated-readback wording remains valid."""
        valid_claim = (
            "agents/model_profiles.toml is the canonical typed profile authority. "
            "tools/agent_tools/model_profile_registry.py materializes closed generated "
            ".codex/agents/*.toml and agents/agents_config.json views. Generated views "
            "are projection digest/readback surfaces and must never be edited manually; "
            "change registry/team/runtime source, regenerate, restart, and validate readback."
        )
        self.assertEqual(
            runtime_alignment.generated_role_authority_contradictions(valid_claim),
            (),
        )

    def test_alignment_rejects_mini_model_on_ordinary_role(self) -> None:
        """A normal role cannot claim the T14 skill-validation model."""
        configs = runtime_alignment.parse_codex_agents()
        configs["explorer"] = {
            **configs["explorer"],
            "model": "gpt-5.4-mini",
            "model_reasoning_effort": "medium",
        }

        with patch.object(runtime_alignment, "parse_codex_agents", return_value=configs):
            with self.assertRaisesRegex(
                RuntimeError,
                "explorer model must project registry profile luna_reasoning_high",
            ):
                runtime_alignment.validate_codex_agent_settings()

    def test_alignment_rejects_agent_tier_profile_keys(self) -> None:
        """Alignment rejects tier selectors in repository agent TOMLs."""
        configs = runtime_alignment.parse_codex_agents()
        configs["worker"] = {**configs["worker"], "service_tier": "unsupported"}

        with patch.object(runtime_alignment, "parse_codex_agents", return_value=configs):
            with self.assertRaisesRegex(RuntimeError, "unsupported profile keys: service_tier"):
                runtime_alignment.validate_codex_agent_settings()

    def test_capacity_request_is_derived_from_declared_topology(self) -> None:
        """Workflow capacity is sourced from declared topology rather than numeric budgets."""
        catalog = loaded_task_catalog_raw()
        topology = cast(dict[str, object], catalog["role_topology_defaults"])
        self.assertEqual(topology["capacity_derivation"], "declared_team_peak_plus_nested_reservations_v1")
        for family in cast(list[dict[str, object]], catalog["workflow_families"]):
            request = cast(dict[str, object], family["capacity_request"])
            self.assertEqual(request["topology_source"], "role_topology")
            self.assertEqual(request["write_scope_source"], "team_manifest.run.write_scopes")
            self.assertNotIn("spawn_budget", family)
    def test_project_config_rejects_agent_policy_scalar_keys(self) -> None:
        """Task policy strings must stay out of Codex's [agents] runtime table."""
        config = runtime_alignment.load_project_config_toml()
        config["agents"] = {
            **cast(dict[str, object], config["agents"]),
            "same_role_instances": "allowed_with_distinct_packets",
        }

        with (
            patch.object(runtime_alignment, "load_project_config_toml", return_value=config),
            patch.object(runtime_alignment, "validate_skill_config", return_value=None),
            patch.object(runtime_alignment, "parse_codex_agents", return_value={}),
            self.assertRaisesRegex(RuntimeError, "unsupported scalar keys under"),
        ):
            runtime_alignment.validate_project_config()

    def test_task_catalog_rejects_legacy_same_role_identity_key(self) -> None:
        """The alignment checker should reject the old role_type identity key."""
        raw = loaded_task_catalog_raw()
        raw["role_topology_defaults"]["same_role_parallel_instances"][  # type: ignore[index]
            "identity_key"
        ] = "role_type+instance_id"
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "role_id\\+instance_id\\+agent_type"):
                runtime_alignment.validate_task_catalog_references()

    def test_task_catalog_rejects_missing_stage_waves(self) -> None:
        """The task catalog must own materialization stage order."""
        raw = loaded_task_catalog_raw()
        del raw["role_topology_defaults"]["stage_waves"]  # type: ignore[index]
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "stage_waves"):
                runtime_alignment.validate_task_catalog_references()

    def test_task_catalog_rejects_reversed_producer_reviewer_order(self) -> None:
        """Producer stage indexes must be lower than their reviewer stages."""
        raw = loaded_task_catalog_raw()
        topology = cast(dict[str, object], raw["role_topology_defaults"])
        stage_waves = cast(list[dict[str, object]], topology["stage_waves"])
        intake_index = next(
            index for index, wave in enumerate(stage_waves) if wave["id"] == "intake"
        )
        review_index = next(
            index
            for index, wave in enumerate(stage_waves)
            if wave["id"] == "intake_review"
        )
        stage_waves[intake_index], stage_waves[review_index] = (
            stage_waves[review_index],
            stage_waves[intake_index],
        )
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "must precede reviewer"):
                runtime_alignment.validate_task_catalog_references()

    def test_task_catalog_rejects_missing_staged_role(self) -> None:
        """Every permanent role must be present in stage_waves exactly once."""
        raw = loaded_task_catalog_raw()
        topology = cast(dict[str, object], raw["role_topology_defaults"])
        stage_waves = topology["stage_waves"]
        self.assertIsInstance(stage_waves, list)
        final_stage = cast(dict[str, object], cast(list[object], stage_waves)[-1])
        role_ids = final_stage["role_ids"]
        self.assertIsInstance(role_ids, list)
        cast(list[object], role_ids).remove("auditor")
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "missing permanent roles"):
                runtime_alignment.validate_task_catalog_references()

    def test_task_catalog_rejects_t12_default_review_pack(self) -> None:
        """T12 should not inherit the repo integration review pack by default."""
        raw = loaded_task_catalog_raw()
        review_packs = raw["review_packs"]
        self.assertIsInstance(review_packs, list)
        matching_pack: dict[str, object] | None = None
        for raw_pack in cast(list[object], review_packs):
            if not isinstance(raw_pack, dict):
                continue
            candidate_pack = cast(dict[str, object], raw_pack)
            if candidate_pack.get("id") == "repo_integration_review":
                matching_pack = candidate_pack
                break
        self.assertIsNotNone(matching_pack)
        pack = cast(dict[str, object], matching_pack)
        default_for_tasks = pack["default_for_tasks"]
        self.assertIsInstance(default_for_tasks, list)
        cast(list[object], default_for_tasks).append("T12")
        catalog = task_catalog_from_raw(raw)

        with patch.object(runtime_alignment, "load_task_catalog", return_value=catalog):
            with self.assertRaisesRegex(RuntimeError, "T12 candidate specialists"):
                runtime_alignment.validate_task_catalog_references()

    def test_skill_config_accepts_project_owned_skill_overlay(self) -> None:
        """Parent repos may add skills through .codex/project-config.toml."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent_skill = root / ".agents" / "skills" / "agent-skill" / "SKILL.md"
            project_skill = root / ".codex" / "project-skills" / "project-skill" / "SKILL.md"
            agent_skill.parent.mkdir(parents=True)
            project_skill.parent.mkdir(parents=True)
            agent_skill.write_text("---\nname: agent-skill\n---\n", encoding="utf-8")
            project_skill.write_text("---\nname: project-skill\n---\n", encoding="utf-8")
            config_path = root / ".codex" / "config.toml"
            project_config_path = root / ".codex" / "project-config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("", encoding="utf-8")
            config: dict[str, object] = {
                "skills": {
                    "config": [
                        {
                            "path": "../.agents/skills/agent-skill/SKILL.md",
                            "enabled": True,
                        },
                    ]
                }
            }
            project_config: dict[str, object] = {
                "skills": {
                    "config": [
                        {
                            "path": "project-skills/project-skill/SKILL.md",
                            "enabled": True,
                        },
                    ]
                }
            }

            with (
                patch.object(runtime_alignment, "PROJECT_CONFIG_PATH", config_path),
                patch.object(runtime_alignment, "PROJECT_SKILL_CONFIG_PATH", project_config_path),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
                patch.object(
                    runtime_alignment,
                    "expected_skill_config_paths",
                    return_value=("../.agents/skills/agent-skill/SKILL.md",),
                ),
            ):
                self.assertTrue(runtime_alignment.is_project_skill_lane_path(project_skill))
                runtime_alignment.validate_skill_config(config, project_config)

    def test_shared_skill_config_rejects_project_owned_skill_entries(self) -> None:
        """Parent-owned skills must not be enabled from AgentCanon config.toml."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            project_skill = root / ".codex" / "project-skills" / "project-skill" / "SKILL.md"
            project_skill.parent.mkdir(parents=True)
            project_skill.write_text("---\nname: project-skill\n---\n", encoding="utf-8")
            config_path = root / ".codex" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("", encoding="utf-8")
            config: dict[str, object] = {
                "skills": {
                    "config": [
                        {
                            "path": "project-skills/project-skill/SKILL.md",
                            "enabled": True,
                        },
                    ]
                }
            }

            with (
                patch.object(runtime_alignment, "PROJECT_CONFIG_PATH", config_path),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
                patch.object(
                    runtime_alignment,
                    "expected_skill_config_paths",
                    return_value=(),
                ),
                self.assertRaisesRegex(RuntimeError, "project-config.toml"),
            ):
                runtime_alignment.validate_skill_config(config)

    def test_skill_config_rejects_paths_outside_agentcanon_and_project_lanes(
        self,
    ) -> None:
        """skills.config paths outside approved lanes must fail closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            outside_skill = root / "skills" / "project-skill" / "SKILL.md"
            outside_skill.parent.mkdir(parents=True)
            outside_skill.write_text("---\nname: project-skill\n---\n", encoding="utf-8")
            config_path = root / ".codex" / "config.toml"
            project_config_path = root / ".codex" / "project-config.toml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text("", encoding="utf-8")
            project_config: dict[str, object] = {
                "skills": {
                    "config": [
                        {
                            "path": "../skills/project-skill/SKILL.md",
                            "enabled": True,
                        },
                    ]
                }
            }

            with (
                patch.object(runtime_alignment, "PROJECT_CONFIG_PATH", config_path),
                patch.object(runtime_alignment, "PROJECT_SKILL_CONFIG_PATH", project_config_path),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
                patch.object(
                    runtime_alignment,
                    "expected_skill_config_paths",
                    return_value=(),
                ),
                self.assertRaisesRegex(RuntimeError, "outside allowed skill lanes"),
            ):
                runtime_alignment.validate_skill_config({"skills": {"config": []}}, project_config)

    def test_public_skill_document_contract_rejects_extra_public_doc(self) -> None:
        """Public skill docs must be catalog-backed instead of internal routines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            (root / "agents" / "skills" / "extra.md").write_text("# Extra\n", encoding="utf-8")
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            registrations = (("example", "agents/skills/example.md"),)

            with self.assertRaisesRegex(RuntimeError, "non-catalog public docs"):
                runtime_alignment.validate_public_skill_document_contract(registrations, root)

    def test_public_skill_document_contract_rejects_nested_extra_public_doc(self) -> None:
        """Nested Markdown in agents/skills also belongs to the public contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills" / "extra").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            (root / "agents" / "skills" / "extra" / "note.md").write_text(
                "# Extra\n",
                encoding="utf-8",
            )
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            registrations = (("example", "agents/skills/example.md"),)

            with self.assertRaisesRegex(RuntimeError, "non-catalog public docs"):
                runtime_alignment.validate_public_skill_document_contract(registrations, root)

    def test_public_skill_document_contract_accepts_catalog_docs_and_internal_routines(self) -> None:
        """Internal routines live outside the public skill doc contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            (root / "agents" / "internal-routines" / "review.md").write_text(
                "# Review\n",
                encoding="utf-8",
            )
            registrations = (("example", "agents/skills/example.md"),)

            runtime_alignment.validate_public_skill_document_contract(registrations, root)
            self.assertTrue((root / "agents" / "internal-routines" / "review.md").is_file())

    def test_public_skill_readme_rejects_duplicate_catalog_table(self) -> None:
        """The public skill list must stay in catalog.yaml, not README rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text(
                "\n".join(
                    [
                        "# Skills",
                        "",
                        "| Family | Purpose | Canonical Doc | Discovery Shim |",
                        "| ------ | ------- | ------------- | -------------- |",
                        "| `example` | Example | `agents/skills/example.md` | `.agents/skills/example/SKILL.md` |",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            registrations = (("example", "agents/skills/example.md"),)

            with self.assertRaisesRegex(RuntimeError, "must not duplicate public skill catalog rows"):
                runtime_alignment.validate_public_skill_document_contract(registrations, root)

    def test_public_skill_shims_reject_extra_shim_without_catalog_entry(self) -> None:
        """Runtime discovery shims must match the public skill catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / ".agents" / "skills" / "example").mkdir(parents=True)
            (root / ".agents" / "skills" / "extra").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: example",
                        "    purpose: Example public skill.",
                        "    canonical_doc: agents/skills/example.md",
                        "    shim: .agents/skills/example/SKILL.md",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            self.write_minimal_dependency_map(root)
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            (root / ".agents" / "skills" / "example" / "SKILL.md").write_text(
                "---\nname: example\n---\n# Example\n",
                encoding="utf-8",
            )
            (root / ".agents" / "skills" / "extra" / "SKILL.md").write_text(
                "---\nname: extra\n---\n# Extra\n",
                encoding="utf-8",
            )

            with (
                patch.object(runtime_alignment, "ROOT", root),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
                self.assertRaisesRegex(RuntimeError, "missing catalog entries: extra"),
            ):
                runtime_alignment.validate_public_skill_shims()

    def test_private_skill_shims_are_not_catalog_backed_public_skills(self) -> None:
        """Underscore-prefixed shims are runtime-internal and omitted from public catalog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / ".agents" / "skills" / "example").mkdir(parents=True)
            (root / ".agents" / "skills" / "_internal-example").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: example",
                        "    purpose: Example public skill.",
                        "    canonical_doc: agents/skills/example.md",
                        "    shim: .agents/skills/example/SKILL.md",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "example.md").write_text("# Example\n", encoding="utf-8")
            self.write_minimal_dependency_map(root)
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            (root / ".agents" / "skills" / "example" / "SKILL.md").write_text(
                "---\nname: example\ndescription: Public skill.\n---\n# Example\n",
                encoding="utf-8",
            )
            (root / ".agents" / "skills" / "_internal-example" / "SKILL.md").write_text(
                "---\nname: _internal-example\ndescription: Private skill.\n---\n# Internal\n",
                encoding="utf-8",
            )
            self.write_official_skill_delegation_docs(root)

            with (
                patch.object(runtime_alignment, "ROOT", root),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
            ):
                runtime_alignment.validate_public_skill_shims()
            self.assertTrue((root / ".agents" / "skills" / "_internal-example" / "SKILL.md").is_file())

    def test_public_skill_catalog_rejects_private_skill_id(self) -> None:
        """The public catalog is the user-facing skill surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "agents" / "skills").mkdir(parents=True)
            (root / "agents" / "internal-routines").mkdir(parents=True)
            (root / ".agents" / "skills" / "_private-example").mkdir(parents=True)
            (root / "agents" / "skills" / "README.md").write_text("# Skills\n", encoding="utf-8")
            (root / "agents" / "skills" / "catalog.yaml").write_text(
                "\n".join(
                    [
                        "version: 1",
                        "skill_families:",
                        "  - id: _private-example",
                        "    purpose: Private skill.",
                        "    canonical_doc: agents/skills/_private-example.md",
                        "    shim: .agents/skills/_private-example/SKILL.md",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "agents" / "skills" / "_private-example.md").write_text(
                "# Private\n",
                encoding="utf-8",
            )
            (root / "agents" / "internal-routines" / "README.md").write_text(
                "# Internal\n",
                encoding="utf-8",
            )
            (root / ".agents" / "skills" / "_private-example" / "SKILL.md").write_text(
                "---\nname: _private-example\ndescription: Private skill.\n---\n# Private\n",
                encoding="utf-8",
            )

            with (
                patch.object(runtime_alignment, "ROOT", root),
                patch.object(runtime_alignment, "SKILL_SHIM_ROOT", root / ".agents" / "skills"),
                self.assertRaisesRegex(RuntimeError, "blocked-by=catalog-gate"),
            ):
                runtime_alignment.validate_public_skill_shims()

    def write_official_skill_delegation_docs(
        self,
        root: Path,
        *,
        missing_skill: str | None = None,
    ) -> None:
        """Create the official system skill delegation docs for checker fixtures."""
        skill_lines = [
            f"- ${skill}"
            for skill in runtime_alignment.OFFICIAL_SYSTEM_SKILLS
            if skill != missing_skill
        ]
        text = "\n".join(
            (
                "# Fixture",
                "",
                "## Official System Skill Delegation",
                "",
                *skill_lines,
            )
        )
        for relative_path in runtime_alignment.OFFICIAL_SYSTEM_SKILL_DELEGATION_DOCS:
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def test_official_system_skills_stay_out_of_public_catalog(self) -> None:
        """Host-provided skills must not be re-declared as AgentCanon public skills."""
        catalog = {
            "skill_families": [
                {
                    "id": "skill-creator",
                    "canonical_doc": "agents/skills/skill-creator.md",
                    "shim": ".agents/skills/skill-creator/SKILL.md",
                }
            ]
        }

        with self.assertRaisesRegex(RuntimeError, "host-provided"):
            runtime_alignment.validate_official_system_skill_delegation(
                {entry["id"] for entry in catalog["skill_families"]},  # type: ignore[index]
                PROJECT_ROOT,
            )

    def test_official_system_skill_delegation_docs_must_name_every_route(self) -> None:
        """Delegation docs carry the official system skill routing map."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_official_skill_delegation_docs(root, missing_skill="imagegen")

            with self.assertRaisesRegex(RuntimeError, "missing official system skill route"):
                runtime_alignment.validate_official_system_skill_delegation(
                    {"skill_families": []},
                    root,
                )

    def test_official_system_skill_delegation_rejects_local_shim(self) -> None:
        """Official system skills stay host-provided instead of local shim backed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_official_skill_delegation_docs(root)
            shim = root / ".agents" / "skills" / "openai-docs" / "SKILL.md"
            shim.parent.mkdir(parents=True)
            shim.write_text("---\nname: openai-docs\n---\n# OpenAI Docs\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "local shim"):
                runtime_alignment.validate_official_system_skill_delegation(
                    {"skill_families": []},
                    root,
                )

    def test_runtime_max_depth_is_exposed_for_spawn_policy(self) -> None:
        """The generator must expose max_depth for delegated spawn policies."""
        self.assertEqual(codex_runtime_max_depth(), 2)

    def test_template_workspace_can_use_agent_canon_shared_docs(self) -> None:
        """Derived workspaces need not expose shared AgentCanon docs at root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            entries = resolve_cross_cutting_document_packet(workspace_root)
            review_process = (
                PROJECT_ROOT / "documents" / "conventions" / "REVIEW_PROCESS.md"
            ).resolve()

            self.assertIn(review_process, {entry.path for entry in entries})
            self.assertTrue(all(entry.path.exists() for entry in entries))

            config = load_team_config()
            role = resolve_role(config, "design_reviewer")
            active_design_packet = resolve_active_design_packet_config(config)
            self.assertEqual(
                active_design_packet.schema,
                "waterfall.design_packet.v1",
            )
            self.assertEqual(
                active_design_packet.implementation_source_packet.entry_id,
                "implementation-source-packet",
            )
            packet = resolve_role_document_packet(
                config=config,
                role=role,
                report_dir=workspace_root / "reports" / "agents" / "_packet_probe",
                workspace_root=workspace_root,
                active_design_packet=active_design_packet,
            )
            non_artifact_paths = {
                entry.path for entry in packet.read_before_work if not entry.rationale.startswith("run artifact:")
            }

            self.assertIn(review_process, non_artifact_paths)
            self.assertTrue(all(path.exists() for path in non_artifact_paths))

    def test_document_packet_sections_are_typed_and_required(self) -> None:
        """Section locators stay separate from paths and fail if required headings move."""
        config = load_team_config()
        role = resolve_role(config, "implementer")
        active_design_packet = resolve_active_design_packet_config(config)
        packet = resolve_role_document_packet(
            config=config,
            role=role,
            report_dir=PROJECT_ROOT / "reports" / "agents" / "_packet_probe",
            workspace_root=PROJECT_ROOT,
            active_design_packet=active_design_packet,
        )
        sectioned_entries = [
            entry for entry in packet.read_before_work if entry.sections
        ]

        self.assertTrue(sectioned_entries)
        self.assertTrue(all("#" not in str(entry.path) for entry in sectioned_entries))
        self.assertIn(
            "5. Implementation",
            {
                section.heading
                for entry in sectioned_entries
                for section in entry.sections
            },
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_heading_doc = Path(tmp_dir) / "CODEX_WORKFLOW.md"
            missing_heading_doc.write_text("# Workflow\n", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError,
                "section_locator_heading_missing:",
            ):
                resolve_document_section_locators(
                    "implementer",
                    "agents/canonical/CODEX_WORKFLOW.md",
                    missing_heading_doc,
                )


if __name__ == "__main__":
    unittest.main()
