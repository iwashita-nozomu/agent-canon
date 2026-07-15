# @dependency-start
# contract test
# responsibility Tests agent team template rendering behavior.
# upstream design ../../agents/templates/README.md template partial contract
# upstream implementation ../../tools/agent_tools/agent_team.py renders templates and owns atomic bookkeeping promotion
# @dependency-end

"""Tests for run artifact template rendering."""

from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest import mock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import agent_team  # noqa: E402
from agent_team import (  # noqa: E402
    RunBundleMaterialization,
    RunBundleSpec,
    TaskCatalog,
    create_run_bundle,
    load_task_catalog,
    load_team_config,
    render_template,
    resolve_active_design_packet,
    resolve_role,
    suggested_public_skills,
)


class AgentTeamTemplateTest(unittest.TestCase):
    """Verify reusable template partial expansion."""

    def create_bundle(self, spec: RunBundleSpec) -> RunBundleMaterialization:
        """Materialize with the already-tested canonical dependency projection."""
        rows = (
            (
                "upstream",
                "design",
                "agents/templates/design_brief.md",
                "documents/dependency-manifest-design.md",
            ),
        )
        with mock.patch("agent_team._canonical_dependency_rows", return_value=rows):
            return create_run_bundle(spec)

    def test_dependency_references_consume_one_verified_graph_query(self) -> None:
        """Packet dependency references should consume graph facts without TSV transport."""
        client = mock.Mock()
        client.status.return_value = SimpleNamespace(
            status="fresh",
            payload={
                "integration_record": {
                    "verified": True,
                    "profile": "default",
                    "source_snapshot_profile": "parent",
                }
            },
        )
        client.query.return_value = SimpleNamespace(
            status="fresh",
            payload={},
            dependency_facts=(
                SimpleNamespace(
                    direction="upstream",
                    kind="design",
                    source="agents/templates/design_brief.md",
                    target="documents/dependency-manifest-design.md",
                ),
            ),
        )
        with mock.patch("agent_team.GraphClient", return_value=client):
            rows = getattr(agent_team, "_canonical_dependency_rows")(PROJECT_ROOT)

        self.assertEqual(
            rows,
            (
                (
                    "upstream",
                    "design",
                    "agents/templates/design_brief.md",
                    "documents/dependency-manifest-design.md",
                ),
            ),
        )
        client.status.assert_called_once_with()
        client.query.assert_called_once_with(
            all=True,
            relation="dependency",
            direction="both",
            depth=0,
        )

    def test_bookkeeping_promotion_preserves_identity_across_mode_transition(
        self,
    ) -> None:
        """A 0600-to-0644 promotion changes permission state, not object identity."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir)
            temp_path = report_root / ".active_run.tmp.fixture"
            content = b"/canonical/run\n"
            temp_path.write_bytes(content)
            temp_path.chmod(agent_team.PRIVATE_TEMP_MODE)
            identity, mode, payload, digest = agent_team._capture_regular_path(
                temp_path
            )
            temp = agent_team.BookkeepingTempState(
                path=temp_path,
                identity=identity,
                permission_mode=mode,
                size=len(payload),
                sha256=digest,
                content=payload,
            )
            lock = cast("agent_team.MaterializationLock", object())

            with mock.patch.object(
                agent_team,
                "_assert_materialization_lock_owned",
            ):
                promoted = agent_team._promote_bookkeeping_temp(
                    report_root=report_root,
                    lock=lock,
                    temp=temp,
                )

            promoted_identity, promoted_mode, promoted_payload, promoted_digest = (
                agent_team._capture_regular_path(temp_path)
            )
            self.assertEqual(mode, 0o600)
            self.assertEqual(promoted_mode, 0o644)
            self.assertEqual(promoted_identity, identity)
            self.assertEqual(promoted.identity, identity)
            self.assertEqual(promoted.permission_mode, promoted_mode)
            self.assertEqual(promoted_payload, content)
            self.assertEqual(promoted_digest, digest)
            self.assertTrue(agent_team._temp_matches(temp_path, promoted))

    def test_review_template_expands_partials_and_replacements(self) -> None:
        """Rendered review artifacts should contain expanded tables and run metadata."""
        rendered = render_template(
            "artifact_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "template refactor",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("- Run ID: test-run", rendered)
        self.assertIn("- Task: template refactor", rendered)
        self.assertIn("| Finding | Severity | Required Change | Evidence | Status |", rendered)
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_decision_partial_expands_without_manifest_leak(self) -> None:
        """Decision partials should render as normal sections inside top-level templates."""
        rendered = render_template(
            "research_review.md",
            {
                "RUN_ID": "test-run",
                "TASK": "research review",
                "OWNER": "codex",
                "CREATED_AT": "2026-05-24T00:00:00Z",
            },
        )

        self.assertNotIn("{{>", rendered)
        self.assertIn("## Decision", rendered)
        self.assertIn("<!-- Record approve, revise, or escalate. -->", rendered)
        self.assertEqual(rendered.count("@dependency-start"), 1)

    def test_research_driven_skill_calls_literature_survey_first(self) -> None:
        """Research-driven run bundles should call literature-survey before research-workflow."""
        skills = suggested_public_skills(None, "research_driven_change")

        self.assertIn("$literature-survey", skills)
        self.assertIn("$research-workflow", skills)
        self.assertLess(
            skills.index("$literature-survey"),
            skills.index("$research-workflow"),
        )

    def test_workflow_selected_packet_is_materialized_and_owned_by_roles(self) -> None:
        """A workflow packet selection controls files and role manifest paths."""
        config = load_team_config()
        base_catalog = load_task_catalog(config)
        selected_family = next(
            family
            for family in base_catalog.workflow_families
            if family.get("id") == "scoped_change"
        )
        custom_packet_value = deepcopy(config.artifact_registry["active_design_packet"])
        self.assertIsInstance(custom_packet_value, dict)
        custom_packet = cast("dict[str, object]", custom_packet_value)
        custom_packet.update(
            {
                "design_artifact": "packet/custom-design.md",
                "design_review_artifact": "packet/custom-technical-review.md",
                "document_flow_review_artifact": "packet/custom-flow-review.md",
                "document_flow_required": True,
            }
        )
        design_output = "artifact:packet/custom-design.md"
        for section in (
            "abstract_design_frame",
            "implementation_source_packet",
            "design_side_effect_map",
        ):
            entry = custom_packet[section]
            self.assertIsInstance(entry, dict)
            cast("dict[str, object]", entry)["output_refs"] = [design_output]
        trace = custom_packet["design_to_implementation_trace"]
        self.assertIsInstance(trace, dict)
        cast("dict[str, object]", trace)["output_refs"] = [
            design_output,
            "artifact:packet/custom-technical-review.md",
            "artifact:packet/custom-flow-review.md",
        ]
        custom_family = {
            **selected_family,
            "active_design_packet": custom_packet,
        }
        catalog = TaskCatalog(
            raw=base_catalog.raw,
            workflow_families=tuple(
                custom_family if family is selected_family else family
                for family in base_catalog.workflow_families
            ),
            tasks=base_catalog.tasks,
            review_packs=base_catalog.review_packs,
        )
        roles = tuple(
            resolve_role(config, role_id)
            for role_id in (
                "designer",
                "design_reviewer",
                "document_flow_reviewer",
            )
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "custom-packet"
            report_dir.parent.mkdir(parents=True)
            spec = RunBundleSpec(
                config=config,
                report_dir=report_dir,
                run_id="custom-packet",
                task="materialize selected packet",
                owner="codex",
                created_at_iso="2026-07-13T00:00:00Z",
                roles=roles,
                workspace_root=PROJECT_ROOT,
                workflow_family_id="scoped_change",
                task_catalog=catalog,
            )

            created = self.create_bundle(spec)

            selected_paths = (
                "packet/custom-design.md",
                "packet/custom-technical-review.md",
                "packet/custom-flow-review.md",
            )
            for path in selected_paths:
                self.assertIn(path, created.created_files)
                self.assertTrue((report_dir / path).is_file())
            for path in (
                "design_brief.md",
                "design_review.md",
                "document_flow_review.md",
            ):
                self.assertFalse((report_dir / path).exists())

            manifest_value = yaml.safe_load(
                (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            )
            self.assertIsInstance(manifest_value, dict)
            manifest = manifest_value
            packet = manifest["run"]["active_design_packet"]
            self.assertEqual(packet["design_artifact"], selected_paths[0])
            self.assertEqual(packet["design_review_artifact"], selected_paths[1])
            self.assertEqual(
                packet["document_flow_review_artifact"],
                selected_paths[2],
            )
            roles_by_id = {role["id"]: role for role in manifest["roles"]}
            expected_outputs = {
                "designer": selected_paths[0],
                "design_reviewer": selected_paths[1],
                "document_flow_reviewer": selected_paths[2],
            }
            for role_id, expected_output in expected_outputs.items():
                role = roles_by_id[role_id]
                self.assertEqual(role["required_outputs"], [expected_output])
                self.assertEqual(
                    role["write_policy"]["allowed_files"],
                    [str((report_dir / expected_output).resolve())],
                )
            read_paths = {
                entry["path"]
                for entry in roles_by_id["design_reviewer"]["document_packet"][
                    "role_specific_read_before_work"
                ]
            }
            self.assertIn(
                str((report_dir / selected_paths[0]).resolve()),
                read_paths,
            )
            packet_artifacts = {
                "design_brief.md": selected_paths[0],
                "design_review.md": selected_paths[1],
                "document_flow_review.md": selected_paths[2],
            }
            rendered_policies = cast(
                "list[dict[str, object]]",
                manifest["context_policies"],
            )
            self.assertEqual(len(rendered_policies), len(config.context_policies))
            for configured, rendered in zip(
                config.context_policies,
                rendered_policies,
                strict=True,
            ):
                configured_share_only = cast(
                    "list[str]",
                    configured["share_only"],
                )
                rendered_share_only = cast(
                    "list[str]",
                    rendered["share_only"],
                )
                self.assertEqual(
                    rendered_share_only,
                    [
                        packet_artifacts.get(artifact, artifact)
                        for artifact in configured_share_only
                    ],
                )
            self.assertEqual(
                manifest["run"]["pre_handoff_gate_status"]["applies_when"],
                "run.active_design_packet.design_artifact="
                "packet/custom-design.md;"
                "condition=exists_before_implementation_or_handoff",
            )

    def test_generation_and_manifest_reject_selected_final_symlink(self) -> None:
        """A selected final symlink cannot write or publish outside the bundle."""
        config = load_team_config()
        roles = tuple(
            resolve_role(config, role_id)
            for role_id in (
                "designer",
                "design_reviewer",
                "document_flow_reviewer",
            )
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report_dir = root / "reports" / "final-symlink"
            report_dir.mkdir(parents=True)
            outside_path = root / "outside-design.md"
            outside_path.write_text("outside sentinel\n", encoding="utf-8")
            (report_dir / "design_brief.md").symlink_to(outside_path)
            spec = RunBundleSpec(
                config=config,
                report_dir=report_dir,
                run_id="final-symlink",
                task="reject final symlink",
                owner="codex",
                created_at_iso="2026-07-13T00:00:00Z",
                roles=roles,
                workspace_root=PROJECT_ROOT,
            )

            with self.assertRaisesRegex(RuntimeError, "render:render_invalid"):
                self.create_bundle(spec)

            self.assertEqual(
                outside_path.read_text(encoding="utf-8"),
                "outside sentinel\n",
            )
            self.assertFalse((report_dir / "team_manifest.yaml").exists())

    def test_generation_and_manifest_reject_selected_symlink_parent(self) -> None:
        """A selected symlink parent cannot write or publish outside the bundle."""
        config = load_team_config()
        roles = (
            resolve_role(config, "designer"),
            resolve_role(config, "design_reviewer"),
            resolve_role(config, "document_flow_reviewer"),
        )
        base_packet = resolve_active_design_packet(
            config,
            workflow_family=None,
            explicit=None,
        )
        design_output = "artifact:packet/graph_design_brief.md"
        packet = replace(
            base_packet,
            design_artifact="packet/graph_design_brief.md",
            design_review_artifact="packet/graph_design_review.md",
            document_flow_review_artifact="packet/graph_document_flow_review.md",
            document_flow_required=True,
            abstract_design_frame=replace(
                base_packet.abstract_design_frame,
                output_refs=(design_output,),
            ),
            implementation_source_packet=replace(
                base_packet.implementation_source_packet,
                output_refs=(design_output,),
            ),
            design_side_effect_map=replace(
                base_packet.design_side_effect_map,
                output_refs=(design_output,),
            ),
            design_to_implementation_trace=replace(
                base_packet.design_to_implementation_trace,
                output_refs=(
                    design_output,
                    "artifact:packet/graph_design_review.md",
                    "artifact:packet/graph_document_flow_review.md",
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report_dir = root / "reports" / "parent-symlink"
            outside_dir = root / "outside-packet"
            report_dir.mkdir(parents=True)
            outside_dir.mkdir()
            (report_dir / "packet").symlink_to(
                outside_dir,
                target_is_directory=True,
            )
            spec = RunBundleSpec(
                config=config,
                report_dir=report_dir,
                run_id="parent-symlink",
                task="reject symlink parent",
                owner="codex",
                created_at_iso="2026-07-13T00:00:00Z",
                roles=roles,
                workspace_root=PROJECT_ROOT,
                active_design_packet=packet,
            )

            with self.assertRaisesRegex(RuntimeError, "render:render_invalid"):
                self.create_bundle(spec)

            self.assertEqual(tuple(outside_dir.iterdir()), ())
            self.assertFalse((report_dir / "team_manifest.yaml").exists())

    def test_generation_rejects_existing_nonregular_packet_target(self) -> None:
        """An existing packet target must be a regular file."""
        config = load_team_config()
        roles = tuple(
            resolve_role(config, role_id)
            for role_id in (
                "designer",
                "design_reviewer",
                "document_flow_reviewer",
            )
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "nonregular-target"
            (report_dir / "design_brief.md").mkdir(parents=True)
            spec = RunBundleSpec(
                config=config,
                report_dir=report_dir,
                run_id="nonregular-target",
                task="reject nonregular target",
                owner="codex",
                created_at_iso="2026-07-13T00:00:00Z",
                roles=roles,
                workspace_root=PROJECT_ROOT,
            )

            with self.assertRaisesRegex(RuntimeError, "render:render_invalid"):
                self.create_bundle(spec)

            self.assertFalse((report_dir / "team_manifest.yaml").exists())


if __name__ == "__main__":
    unittest.main()
