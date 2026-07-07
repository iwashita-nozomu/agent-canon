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
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import check_agent_runtime_alignment as runtime_alignment  # noqa: E402
from agent_team import (  # noqa: E402
    TaskCatalog,
    codex_runtime_max_depth,
    codex_runtime_max_threads,
    load_team_config,
    resolve_cross_cutting_document_packet,
    resolve_role,
    resolve_role_document_packet,
    workflow_spawn_budget,
)
from check_agent_runtime_alignment import validate_permanent_team_mapping  # noqa: E402


class AgentRuntimeAlignmentTest(unittest.TestCase):
    """Verify that the runtime alignment checker passes on the checked-in canon."""

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

    def test_workflow_spawn_budget_rejects_write_budget_above_active(self) -> None:
        """Write-capable subagents must be bounded by the active spawn budget."""
        catalog = TaskCatalog(
            raw={},
            workflow_families=(
                {
                    "id": "bad-budget",
                    "spawn_budget": {
                        "active_subagents": 2,
                        "max_write_subagents": 3,
                    },
                },
            ),
            tasks=(),
            review_packs=(),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "max_write_subagents exceeds active_subagents",
        ):
            workflow_spawn_budget(catalog, "bad-budget")

    def test_workflow_spawn_budget_rejects_active_budget_above_runtime_threads(self) -> None:
        """Workflow active budget must not exceed Codex runtime max_threads."""
        runtime_max_threads = codex_runtime_max_threads()
        catalog = TaskCatalog(
            raw={},
            workflow_families=(
                {
                    "id": "bad-runtime-budget",
                    "spawn_budget": {
                        "active_subagents": runtime_max_threads + 1,
                        "max_write_subagents": 1,
                    },
                },
            ),
            tasks=(),
            review_packs=(),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "active_subagents exceeds runtime max_threads",
        ):
            workflow_spawn_budget(catalog, "bad-runtime-budget")

    def test_workflow_spawn_budget_allows_active_equal_runtime_threads(self) -> None:
        """Workflow active budget may equal the runtime max_threads boundary."""
        runtime_max_threads = codex_runtime_max_threads()
        catalog = TaskCatalog(
            raw={},
            workflow_families=(
                {
                    "id": "boundary-budget",
                    "spawn_budget": {
                        "active_subagents": runtime_max_threads,
                        "max_write_subagents": 1,
                    },
                },
            ),
            tasks=(),
            review_packs=(),
        )

        self.assertEqual(
            workflow_spawn_budget(catalog, "boundary-budget"),
            (runtime_max_threads, 1),
        )

    def test_project_config_rejects_agent_policy_scalar_keys(self) -> None:
        """Task policy strings must stay out of Codex's [agents] runtime table."""
        config = {
            "review_model": "gpt-5.5",
            "model_context_window": runtime_alignment.EXPECTED_MODEL_CONTEXT_WINDOW,
            "tool_output_token_limit": runtime_alignment.EXPECTED_TOOL_OUTPUT_TOKEN_LIMIT,
            "features": {
                "hooks": True,
                "goals": True,
                "multi_agent": True,
            },
            "agents": {
                "max_threads": runtime_alignment.EXPECTED_MAX_THREADS,
                "max_depth": runtime_alignment.EXPECTED_MAX_DEPTH,
                "job_max_runtime_seconds": runtime_alignment.EXPECTED_JOB_MAX_RUNTIME_SECONDS,
                "same_role_instances": "allowed_with_distinct_packets",
            },
        }

        with (
            patch.object(runtime_alignment, "load_project_config_toml", return_value=config),
            patch.object(runtime_alignment, "validate_skill_config", return_value=None),
            patch.object(runtime_alignment, "parse_codex_agents", return_value={}),
            self.assertRaisesRegex(RuntimeError, "unsupported scalar keys under"),
        ):
            runtime_alignment.validate_project_config()

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

    def test_skill_routing_schema_rejects_unknown_stage_policy(self) -> None:
        """Skill routing stage policy values must match implemented behavior."""
        with self.assertRaisesRegex(RuntimeError, "routing.stage_policy"):
            runtime_alignment.validate_skill_routing_entry(
                "task-routing",
                {
                    "stage_policy": "explicit_only",
                    "reason": "fixture",
                    "triggers": [["routing"]],
                },
            )

    def test_skill_routing_schema_rejects_non_string_reason(self) -> None:
        """Skill routing reasons must be typed strings."""
        with self.assertRaisesRegex(RuntimeError, "routing.reason"):
            runtime_alignment.validate_skill_routing_entry(
                "task-routing",
                {
                    "stage_policy": "active",
                    "reason": 3,
                    "triggers": [["routing"]],
                },
            )

    def test_skill_related_schema_rejects_unknown_skill(self) -> None:
        """Related skill metadata must point to catalog-backed public skills."""
        families: list[object] = [
            {
                "id": "task-routing",
                "related_skills": ["missing-skill"],
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "unknown skill: missing-skill"):
            runtime_alignment.validate_skill_related_entries(families, {"task-routing"})

    def test_skill_related_schema_rejects_self_reference(self) -> None:
        """Related skill metadata must not point back to the same skill."""
        families: list[object] = [
            {
                "id": "task-routing",
                "related_skills": ["task-routing"],
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "must not self-reference"):
            runtime_alignment.validate_skill_related_entries(families, {"task-routing"})

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
            catalog = {
                "skill_families": [
                    {
                        "id": "example",
                        "canonical_doc": "agents/skills/example.md",
                        "shim": ".agents/skills/example/SKILL.md",
                    }
                ]
            }

            with self.assertRaisesRegex(RuntimeError, "non-catalog public docs"):
                runtime_alignment.validate_public_skill_document_contract(catalog, root)

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
            catalog = {
                "skill_families": [
                    {
                        "id": "example",
                        "canonical_doc": "agents/skills/example.md",
                        "shim": ".agents/skills/example/SKILL.md",
                    }
                ]
            }

            with self.assertRaisesRegex(RuntimeError, "non-catalog public docs"):
                runtime_alignment.validate_public_skill_document_contract(catalog, root)

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
            catalog = {
                "skill_families": [
                    {
                        "id": "example",
                        "canonical_doc": "agents/skills/example.md",
                        "shim": ".agents/skills/example/SKILL.md",
                    }
                ]
            }

            runtime_alignment.validate_public_skill_document_contract(catalog, root)
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
            catalog = {
                "skill_families": [
                    {
                        "id": "example",
                        "canonical_doc": "agents/skills/example.md",
                        "shim": ".agents/skills/example/SKILL.md",
                    }
                ]
            }

            with self.assertRaisesRegex(RuntimeError, "must not duplicate public skill catalog rows"):
                runtime_alignment.validate_public_skill_document_contract(catalog, root)

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
                self.assertRaisesRegex(RuntimeError, "must not start with _"),
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
            runtime_alignment.validate_official_system_skill_delegation(catalog, PROJECT_ROOT)

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
            review_process = (PROJECT_ROOT / "documents" / "REVIEW_PROCESS.md").resolve()

            self.assertIn(review_process, {entry.path for entry in entries})
            self.assertTrue(all(entry.path.exists() for entry in entries))

            config = load_team_config()
            role = resolve_role(config, "design_reviewer")
            packet = resolve_role_document_packet(
                config=config,
                role=role,
                report_dir=workspace_root / "reports" / "agents" / "_packet_probe",
                workspace_root=workspace_root,
            )
            non_artifact_paths = {
                entry.path for entry in packet.read_before_work if not entry.rationale.startswith("run artifact:")
            }

            self.assertIn(review_process, non_artifact_paths)
            self.assertTrue(all(path.exists() for path in non_artifact_paths))


if __name__ == "__main__":
    unittest.main()
