# @dependency-start
# contract test
# responsibility Tests test waterfall gate check behavior.
# upstream design ../../tools/README.md validated automation surface
# upstream implementation ../../tools/agent_tools/agent_team.py owns canonical active-packet projection loading
# @dependency-end

"""Tests for intermediate waterfall gate checks."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from agent_team import (  # noqa: E402
    RunBundleSpec,
    active_design_packet_mapping,
    active_design_reference_projection_mapping,
    build_active_design_reference_context,
    iter_artifacts,
    load_materialized_active_design_packet,
    load_team_config,
    parse_active_design_packet_input,
    render_active_design_packet_violation,
    resolve_active_design_packet,
    resolve_role,
)

BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
GATE_CHECK_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "waterfall_gate_check.py"
SECOND_DEPENDENCY_REF = (
    "header:upstream:implementation:repo:tools/agent_tools/graph_client.py"
    "->repo:rust/agent-canon/src/graph.rs"
)


def write_markdown(path: Path, lines: list[str]) -> None:
    """Write a compact Markdown fixture."""
    path.write_text("\n".join([*lines, ""]), encoding="utf-8")


def write_active_packet_manifest(
    report_dir: Path,
    *,
    design_artifact: str = "design_brief.md",
    design_review_artifact: str = "design_review.md",
    document_flow_review_artifact: str = "document_flow_review.md",
    document_flow_required: bool = True,
) -> None:
    """Persist a complete packet and projection through canonical owners."""
    report_dir.mkdir(parents=True, exist_ok=True)
    config = load_team_config()
    packet_mapping = active_design_packet_mapping(
        resolve_active_design_packet(
            config,
            workflow_family=None,
            explicit=None,
        )
    )
    design_output = f"artifact:{design_artifact}"
    packet_mapping.update(
        {
            "design_artifact": design_artifact,
            "design_review_artifact": design_review_artifact,
            "document_flow_review_artifact": document_flow_review_artifact,
            "document_flow_required": document_flow_required,
        }
    )
    for section in (
        "abstract_design_frame",
        "implementation_source_packet",
        "design_side_effect_map",
    ):
        cast("dict[str, object]", packet_mapping[section])["output_refs"] = [
            design_output
        ]
    cast("dict[str, object]", packet_mapping["design_to_implementation_trace"])[
        "output_refs"
    ] = [
        design_output,
        f"artifact:{design_review_artifact}",
        f"artifact:{document_flow_review_artifact}",
    ]
    source_packet = cast(
        "dict[str, object]",
        packet_mapping["implementation_source_packet"],
    )
    dependency_refs = cast("list[str]", source_packet["dependency_refs"])
    dependency_refs.append(SECOND_DEPENDENCY_REF)
    packet = parse_active_design_packet_input(
        json.dumps(packet_mapping, separators=(",", ":"))
    )
    if packet is None:
        raise AssertionError("canonical fixture packet unexpectedly resolved to null")
    roles = tuple(
        resolve_role(config, role_id)
        for role_id in (
            "designer",
            "design_reviewer",
            "document_flow_reviewer",
        )
    )
    spec = RunBundleSpec(
        config=config,
        report_dir=report_dir,
        run_id=report_dir.name,
        task="waterfall fixture",
        owner="test",
        created_at_iso="2026-07-13T00:00:00Z",
        roles=roles,
        workspace_root=PROJECT_ROOT,
        active_design_packet=packet,
    )
    rows = (
        (
            "upstream",
            "design",
            "agents/templates/design_brief.md",
            "documents/dependency-manifest-design.md",
        ),
        (
            "upstream",
            "implementation",
            "tools/agent_tools/graph_client.py",
            "rust/agent-canon/src/graph.rs",
        ),
    )
    with mock.patch("agent_team._canonical_dependency_rows", return_value=rows):
        context = build_active_design_reference_context(
            spec,
            packet,
            None,
            artifact_names=iter_artifacts(config, roles, packet),
        )
    manifest = {
        "run": {
            "workspace_root": str(PROJECT_ROOT.resolve()),
            "report_dir": str(report_dir.resolve()),
            "active_design_packet": packet_mapping,
            "active_design_packet_reference_projection": (
                active_design_reference_projection_mapping(context)
            ),
        }
    }
    (report_dir / "team_manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def rewrite_active_packet_field(
    report_dir: Path,
    field: str,
    value: object = None,
    *,
    remove: bool = False,
) -> None:
    """Mutate one persisted packet field for a negative loader oracle."""
    manifest_path = report_dir / "team_manifest.yaml"
    manifest = cast(
        "dict[str, object]",
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    run = cast("dict[str, object]", manifest["run"])
    packet = cast("dict[str, object]", run["active_design_packet"])
    if remove:
        packet.pop(field)
    else:
        packet[field] = value
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def read_active_packet_projection(
    report_dir: Path,
) -> tuple[Path, dict[str, object], dict[str, object]]:
    """Return one mutable manifest and its persisted projection fixture."""
    manifest_path = report_dir / "team_manifest.yaml"
    manifest = cast(
        "dict[str, object]",
        yaml.safe_load(manifest_path.read_text(encoding="utf-8")),
    )
    run = cast("dict[str, object]", manifest["run"])
    projection = cast(
        "dict[str, object]",
        run["active_design_packet_reference_projection"],
    )
    return manifest_path, manifest, projection


def write_active_packet_projection(
    manifest_path: Path,
    manifest: dict[str, object],
) -> None:
    """Persist one deliberately modified projection for a loader oracle."""
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )


def run_gate(report_dir: Path, gate: str) -> subprocess.CompletedProcess[str]:
    """Run one waterfall gate check."""
    return subprocess.run(
        [
            sys.executable,
            str(GATE_CHECK_SCRIPT),
            "--report-dir",
            str(report_dir),
            "--gate",
            gate,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_document_flow_review(
    report_dir: Path,
    review_target_sha256: str | None = None,
    design_artifact_path: str = "design_brief.md",
    review_artifact: str = "document_flow_review.md",
) -> None:
    """Write an approving document flow review fixture."""
    write_markdown(
        report_dir / review_artifact,
        [
            "# Document Flow Review",
            "",
            "## Findings",
            "No blockers.",
            f"- Design artifact path: {design_artifact_path}",
            *(
                [f"review_target_sha256={review_target_sha256}"]
                if review_target_sha256 is not None
                else []
            ),
            "## Decision",
            "approve",
        ],
    )


def approved_design_review_lines(
    *,
    include_abstract: bool = True,
    design_artifact_path: str = "design_brief.md",
    include_artifact_section: bool = True,
    include_revision: bool = True,
    include_source_packet: bool = True,
    include_reviewer_separation: bool = True,
) -> list[str]:
    """Return a design review fixture that satisfies the design gate."""
    lines = [
        "# Detailed Design Review",
        "",
        "## Findings",
        "No blockers.",
    ]
    if include_artifact_section:
        lines.extend(
            [
                "## Design Artifact Under Review",
                f"- Design artifact path: {design_artifact_path}",
            ]
        )
        if include_revision:
            lines.append(
                "- Design revision or section set: current sections through "
                "Design-To-Implementation Trace"
            )
        if include_source_packet:
            lines.append("- Source packet reviewed: design_brief.md Implementation Source Packet")
        if include_reviewer_separation:
            lines.append(
                "- Reviewer separation: design_reviewer is separate from designer"
            )
    lines.extend(
        [
            "## Upstream Requirement Packet Review",
            "The design cites the governing requirement and workflow documents.",
        ]
    )
    if include_abstract:
        lines.extend(
            [
                "## Abstract Design Frame Review",
                "The design starts from responsibility before file scope.",
            ]
        )
    lines.extend(
        [
            "## Implementation Source Packet Review",
            "The packet names every required read-before-edit artifact.",
            "## Canonical Tree-Head Review",
            "The design leaves only canonical tracked paths in the tree.",
            "## Design-To-Implementation Trace Review",
            "Each planned edit maps to the request clause and test plan.",
            "## Decision",
            "approve",
        ]
    )
    return lines


def design_brief_lines(
    *,
    include_abstract: bool = True,
    include_upstream: bool = True,
    include_implementation: bool = True,
    include_canonical: bool = True,
    include_trace: bool = True,
) -> list[str]:
    """Return a detailed design fixture with optional required sections."""
    lines = [
        "# Detailed Design Brief",
        "",
        "## Goals",
        "Implement the approved bounded change.",
        "## Existing Code And Docs To Reuse",
        "Mirror `tools/agent_tools/task_close.py`.",
    ]
    if include_abstract:
        lines.extend(
            [
                "## Abstract Design Frame",
                (
                    "Responsibility model: gate checks enforce design readiness "
                    "before implementation path selection."
                ),
                "Concept or layer model: requirements flow into design, review, implementation, and validation layers.",
                "Non-goals: the design does not let workers invent file scope from nearby helpers.",
                "Future extension layers: generated prompts and closeout gates can add stricter checks.",
                "Evaluation axes: readiness is judged by traceability, reviewability, and validation coverage.",
                "Canonical-surface relationships: the workflow, templates, tools, and tests stay aligned.",
            ]
        )
    if include_upstream:
        lines.extend(
            [
                "## Upstream Requirement Packet",
                (
                    "Read `user_request_contract.md`, `schedule.md`, `intent_brief.md`, "
                    "and `agents/workflows/implementation-waterfall-workflow.md`."
                ),
            ]
        )
    if include_implementation:
        lines.extend(
            [
                "## Implementation Source Packet",
                (
                    "Read `user_request_contract.md`, `design_review.md`, "
                    "`document_flow_review.md`, `test_plan.md`, and "
                    "`tools/agent_tools/task_close.py`."
                ),
            ]
        )
    lines.extend(
        [
            "## Design Side-Effect Map",
            (
                "The gate checker changes workflow readiness output; its tests and "
                "active-packet projection fixtures must change in the same slice."
            ),
        ]
    )
    if include_canonical:
        lines.extend(
            [
                "## Canonical Tree-Head Plan",
                (
                    "Keep `tools/agent_tools/waterfall_gate_check.py` as the only "
                    "canonical implementation path and do not leave backup files."
                ),
            ]
        )
    lines.extend(["## File-By-File Design", "Update the gate checker only."])
    if include_trace:
        lines.extend(
            [
                "## Design-To-Implementation Trace",
                "Slice A maps T1-C1 to the gate checker and test plan item T1.",
            ]
        )
    lines.extend(
        [
            "## Identifier And Naming Plan",
            "Use `waterfall_gate_check.py` after the existing task tool names.",
        ]
    )
    return lines


def write_approved_design_bundle(
    report_dir: Path,
    design_lines: list[str],
) -> None:
    """Write design artifacts with an approving review and document-flow review."""
    write_design_bundle_with_review(
        report_dir,
        design_lines,
        approved_design_review_lines(),
    )


def write_design_bundle_with_review(
    report_dir: Path,
    design_lines: list[str],
    design_review_lines: list[str],
) -> None:
    """Write design artifacts with caller-selected design-review lines."""
    write_markdown(report_dir / "design_brief.md", design_lines)
    design_sha256 = hashlib.sha256(
        (report_dir / "design_brief.md").read_bytes()
    ).hexdigest()
    review_lines = [
        *design_review_lines,
        f"review_target_sha256={design_sha256}",
    ]
    write_markdown(report_dir / "design_review.md", review_lines)
    write_document_flow_review(report_dir, design_sha256)
    write_active_packet_manifest(report_dir)


def write_unknown_requirement_bundle(report_dir: Path) -> None:
    """Write a requirement bundle with an invalid active unknown clause."""
    write_markdown(
        report_dir / "user_request_contract.md",
        [
            "# User Request Contract",
            "",
            "## Requirements Resolution Sweep",
            "Checked notes, documents, and local code precedent.",
            "## Resolved From Accumulated Context",
            "| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |",
            "| --------- | ------------- | ------------- | ---------- | -------------- |",
            "| T1-C0 | repo_or_code_precedent | documents/ | Existing workflow applies. | none |",
            "## Must-Do Clauses",
            (
                "| Clause ID | Source Bucket | User Wording Or Evidence | "
                "Operational Interpretation | Owner Stage | Evidence Path | Status |"
            ),
            (
                "| --------- | ------------- | ------------------------- | "
                "-------------------------- | ----------- | ------------- | ------ |"
            ),
            (
                "| T1-C1 | unknown_or_open_question | unclear | decide later | "
                "requirements | user_request_contract.md | active |"
            ),
            "## Must-Not-Do Clauses",
            "| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |",
            "| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |",
            "## Completion Evidence Clauses",
            "| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |",
            "| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |",
            "| T1-E1 | current_request | requirements review | management_review.md | requirements | active |",
        ],
    )
    write_markdown(
        report_dir / "management_review.md",
        [
            "# Management Review",
            "",
            "## Scope Review",
            "Scope is concrete.",
            "## Accumulated Context Resolution Review",
            "Resolution sweep is recorded.",
            "## Unknown Handling Review",
            "No unknowns should remain active.",
            "## Decision",
            "approve",
        ],
    )


class WaterfallGateCheckTest(unittest.TestCase):
    """Verify that intermediate waterfall gates fail closed."""

    def test_materialized_source_projection_rebinds_every_declared_tuple_field(
        self,
    ) -> None:
        """Persisted source rows cannot swap or rewrite canonical tuple fields."""
        cases = (
            "row_swap",
            "declared_ref",
            "root_key",
            "relative_path",
            "fragment_kind",
            "fragment_value",
        )
        for field in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp_dir:
                report_dir = Path(tmp_dir) / "reports" / field
                write_active_packet_manifest(report_dir)
                manifest_path, manifest, projection = read_active_packet_projection(
                    report_dir
                )
                rows = cast(
                    "list[dict[str, object]]",
                    projection["source_results"],
                )
                target_index = next(
                    index
                    for index, row in enumerate(rows)
                    if row["relative_path"] == "agents/templates/design_brief.md"
                )
                sibling_index = next(
                    index
                    for index, row in enumerate(rows)
                    if index != target_index
                    and row["relative_path"] == rows[target_index]["relative_path"]
                    and row["fragment_value"] != rows[target_index]["fragment_value"]
                )
                target = rows[target_index]
                sibling = rows[sibling_index]
                if field == "row_swap":
                    rows[target_index], rows[sibling_index] = sibling, target
                elif field == "declared_ref":
                    target[field] = sibling[field]
                elif field == "root_key":
                    target[field] = (
                        "workspace"
                        if target[field] == "agent_canon"
                        else "agent_canon"
                    )
                elif field == "relative_path":
                    target[field] = f"./{target[field]}"
                elif field == "fragment_kind":
                    target[field] = "none"
                else:
                    target[field] = sibling[field]
                write_active_packet_projection(manifest_path, manifest)

                loaded = load_materialized_active_design_packet(report_dir)

                self.assertIsNotNone(loaded.packet)
                self.assertIsNone(loaded.context)
                self.assertEqual(
                    tuple(
                        render_active_design_packet_violation(violation)
                        for violation in loaded.violations
                    ),
                    (
                        "team_manifest.yaml:active_design_packet_field_invalid:"
                        "active_design_packet_reference_projection",
                    ),
                )

    def test_materialized_dependency_projection_rebinds_every_declared_tuple_field(
        self,
    ) -> None:
        """Persisted dependency rows cannot swap or rewrite canonical edge tuples."""
        cases = (
            "row_swap",
            "declared_ref",
            "dependency_root_key",
            "normalized_key",
            "source_path",
            "target_path",
        )
        for field in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp_dir:
                report_dir = Path(tmp_dir) / "reports" / field
                write_active_packet_manifest(report_dir)
                manifest_path, manifest, projection = read_active_packet_projection(
                    report_dir
                )
                rows = cast(
                    "list[dict[str, object]]",
                    projection["dependency_results"],
                )
                target, sibling = rows
                if field == "row_swap":
                    rows[0], rows[1] = sibling, target
                elif field == "declared_ref":
                    target[field] = sibling[field]
                elif field == "dependency_root_key":
                    target[field] = (
                        "workspace"
                        if target[field] == "agent_canon"
                        else "agent_canon"
                    )
                elif field == "normalized_key":
                    target[field] = sibling[field]
                else:
                    target[field] = f"./{target[field]}"
                write_active_packet_projection(manifest_path, manifest)

                loaded = load_materialized_active_design_packet(report_dir)

                self.assertIsNotNone(loaded.packet)
                self.assertIsNone(loaded.context)
                self.assertEqual(
                    tuple(
                        render_active_design_packet_violation(violation)
                        for violation in loaded.violations
                    ),
                    (
                        "team_manifest.yaml:active_design_packet_field_invalid:"
                        "active_design_packet_reference_projection",
                    ),
                )

    def test_requirements_gate_rejects_active_unknown_clause(self) -> None:
        """Requirements should defer unknowns instead of leaving them active."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "unknown-requirement"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_unknown_requirement_bundle(report_dir)
            result = run_gate(report_dir, "requirements")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = "user_request_contract.md:active_unknown_clause:must_do_clauses"
            self.assertIn(expected_blocker, result.stdout)

    def test_requirements_gate_allows_dependency_header_comment(self) -> None:
        """Dependency headers should not make a filled artifact look like a template."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "dependency-header"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(
                report_dir / "user_request_contract.md",
                [
                    "# User Request Contract",
                    "<!--",
                    "@dependency-start",
                    "responsibility Documents run requirements.",
                    "@dependency-end",
                    "-->",
                    "",
                    "## Requirements Resolution Sweep",
                    "Checked repo docs, source packet, and local tests.",
                    "## Resolved From Accumulated Context",
                    "| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |",
                    "| --------- | ------------- | ------------- | ---------- | -------------- |",
                    "| T1-C0 | repo_or_code_precedent | documents/ | Existing workflow applies. | none |",
                    "## Must-Do Clauses",
                    (
                        "| Clause ID | Source Bucket | User Wording Or Evidence | "
                        "Operational Interpretation | Owner Stage | Evidence Path | Status |"
                    ),
                    (
                        "| --------- | ------------- | ------------------------- | "
                        "-------------------------- | ----------- | ------------- | ------ |"
                    ),
                    "| T1-C1 | current_request | fix gate | enforce requirements | requirements | user_request_contract.md | active |",
                    "## Must-Not-Do Clauses",
                    "| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |",
                    "| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |",
                    "| T1-N1 | repo_or_code_precedent | skip gate | unsafe | requirements | management_review.md | active |",
                    "## Completion Evidence Clauses",
                    "| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |",
                    "| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |",
                    "| T1-E1 | current_request | requirements review | management_review.md | requirements | active |",
                ],
            )
            write_markdown(
                report_dir / "management_review.md",
                [
                    "# Management Review",
                    "",
                    "## Scope Review",
                    "Scope is concrete.",
                    "## Accumulated Context Resolution Review",
                    "Resolution sweep is recorded.",
                    "## Unknown Handling Review",
                    "No unknowns remain active.",
                    "## Decision",
                    "approve",
                ],
            )

            result = run_gate(report_dir, "requirements")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertNotIn("template_or_placeholder_remaining", result.stdout)

    def test_design_gate_rejects_fresh_template_bundle(self) -> None:
        """A fresh bundle should not pass design gate without filled reviews."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            report_dir = report_root / "fresh-bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "waterfall gate smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "fresh-bundle",
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                    "--skip-agent-canon-preflight",
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WATERFALL_GATE_READY=no", result.stdout)
            self.assertIn(
                "design_brief.md:section_empty_or_missing:implementation_source_packet",
                result.stdout,
            )
            manifest = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            self.assertIn("schema: waterfall.design_packet.v1", manifest)
            self.assertIn("design_artifact: design_brief.md", manifest)
            self.assertIn("design_review_artifact: design_review.md", manifest)
            self.assertIn(
                "document_flow_review_artifact: document_flow_review.md",
                manifest,
            )
            for artifact in (
                "design_brief.md",
                "design_review.md",
                "document_flow_review.md",
            ):
                self.assertTrue((report_dir / artifact).is_file())
            self.assertIn("/design_brief.md", manifest)

    def test_document_flow_gate_is_ready_when_packet_marks_flow_inactive(self) -> None:
        """An inactive selected flow stage has no approval blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "design-only"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design_brief.md", design_brief_lines())
            write_markdown(
                report_dir / "design_review.md",
                approved_design_review_lines(),
            )
            design_sha256 = hashlib.sha256(
                (report_dir / "design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / "design_review.md",
                [
                    *approved_design_review_lines(),
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_active_packet_manifest(
                report_dir,
                document_flow_required=False,
                document_flow_review_artifact="inactive-flow-review.md",
            )
            write_markdown(
                report_dir / "inactive-flow-review.md",
                ["# Inactive flow review", "decision=revise"],
            )

            design_result = run_gate(report_dir, "design")
            document_flow_result = run_gate(report_dir, "document_flow")

            self.assertEqual(
                design_result.returncode,
                0,
                design_result.stdout + design_result.stderr,
            )
            self.assertIn("WATERFALL_GATE_READY=yes", design_result.stdout)
            self.assertEqual(
                document_flow_result.returncode,
                0,
                document_flow_result.stdout + document_flow_result.stderr,
            )
            self.assertIn("WATERFALL_GATE_READY=yes", document_flow_result.stdout)

    def test_document_flow_gate_uses_declared_graph_review_and_ignores_generic(
        self,
    ) -> None:
        """The standalone flow gate consumes only the manifest-selected review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "graph-flow"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "graph_design_brief.md", design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / "graph_design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(report_dir / "graph_design_review.md", ["# Review"])
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="graph_design_brief.md",
                review_artifact="graph_document_flow_review.md",
            )
            write_markdown(
                report_dir / "document_flow_review.md",
                ["# Generic sibling", "decision=revise"],
            )
            write_active_packet_manifest(
                report_dir,
                design_artifact="graph_design_brief.md",
                design_review_artifact="graph_design_review.md",
                document_flow_review_artifact="graph_document_flow_review.md",
            )

            selected_approve = run_gate(report_dir, "document_flow")
            write_markdown(
                report_dir / "graph_document_flow_review.md",
                [
                    "# Graph Document Flow Review",
                    "- Design artifact path: graph_design_brief.md",
                    f"review_target_sha256={design_sha256}",
                    "decision=revise",
                ],
            )
            write_markdown(
                report_dir / "document_flow_review.md",
                ["# Generic sibling", "decision=approve"],
            )
            selected_revise = run_gate(report_dir, "document_flow")

            self.assertEqual(
                selected_approve.returncode,
                0,
                selected_approve.stdout + selected_approve.stderr,
            )
            self.assertNotEqual(selected_revise.returncode, 0)
            self.assertIn(
                "graph_document_flow_review.md:decision_not_approve",
                selected_revise.stdout,
            )
            blocker_line = next(
                line
                for line in selected_revise.stdout.splitlines()
                if line.startswith("WATERFALL_GATE_BLOCKERS=")
            )
            blockers = blocker_line.removeprefix("WATERFALL_GATE_BLOCKERS=").split(",")
            self.assertNotIn("document_flow_review.md:decision_not_approve", blockers)

    def test_test_gate_rejects_dependency_header_only_plan(self) -> None:
        """Dependency headers alone should not satisfy the test-plan gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "dependency-header-only-test"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(
                report_dir / "test_plan.md",
                [
                    "# Test Plan",
                    "<!--",
                    "@dependency-start",
                    "responsibility Documents test plan.",
                    "@dependency-end",
                    "-->",
                    "",
                    "## Static Path Survey",
                    "<!-- Record static paths. -->",
                    "## Nasty Cases",
                    "| Target | Case | Why It Is Nasty | Expected Outcome | Status |",
                    "| ------ | ---- | --------------- | ---------------- | ------ |",
                    "## Regression Cases To Keep",
                    "<!-- Record regressions. -->",
                    "## Implementation Notes",
                    "<!-- Record implementation notes. -->",
                ],
            )

            result = run_gate(report_dir, "test")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test_plan.md:template_or_placeholder_remaining", result.stdout)

    def test_plan_gate_rejects_empty_todo_surface(self) -> None:
        """Plan gate should fail when schedule.md does not contain concrete TODO rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "empty-plan"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "schedule.md").write_text(
                "\n".join(
                    [
                        "# Schedule",
                        "",
                        "## Stage Plan",
                        "| Stage | Owner Agent | Review Agent | Inputs | Exit Criteria | Status |",
                        "| ----- | ----------- | ------------ | ------ | ------------- | ------ |",
                        "| requirements | manager | manager_reviewer | contract | fixed | done |",
                        "## Clause Coverage",
                        "| Clause ID | Covered By Stage | Review Gate | Status |",
                        "| --------- | ---------------- | ----------- | ------ |",
                        "| T1-C1 | requirements | requirements | done |",
                        "## Planned Work Units",
                        (
                            "| Unit ID | Clause IDs | Owner | Completion Evidence | "
                            "Next Gate | Status |"
                        ),
                        (
                            "| ------- | ---------- | ----- | ------------------- | "
                            "--------- | ------ |"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "schedule_review.md").write_text(
                "\n".join(
                    [
                        "# Schedule Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "plan",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("schedule.md:planned_work_units_empty", result.stdout)

    def test_design_gate_accepts_filled_approved_artifacts(self) -> None:
        """A filled design bundle should pass when both design reviews approve."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "filled"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_approved_design_bundle(report_dir, design_brief_lines())
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertIn("NEXT_ACTION=proceed_to_next_waterfall_gate", result.stdout)

    def test_design_gate_rejects_missing_abstract_design_frame(self) -> None:
        """Design gate should fail when design selects files without abstraction."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_abstract=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = (
                "design_brief.md:section_empty_or_missing:abstract_design_frame"
            )
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_accepts_path_sha_decision_without_abstract_review(
        self,
    ) -> None:
        """Review identity is governed by the declared packet and matching SHA."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-abstract-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(include_abstract=False),
            )
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_design_gate_rejects_missing_reviewed_artifact_section(self) -> None:
        """Each review must declare the manifest-selected design artifact path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-artifact-section"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(include_artifact_section=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_review.md:design_artifact_path_missing",
                result.stdout,
            )

    def test_design_gate_rejects_technical_review_wrong_path_with_same_sha(
        self,
    ) -> None:
        """Technical review path identity is independent of matching bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "stale-artifact-path"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(
                    design_artifact_path="reports/agents/old/design_brief.md"
                ),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_review.md:design_artifact_path_mismatch",
                result.stdout,
            )

    def test_design_gate_rejects_flow_review_wrong_path_with_same_sha(self) -> None:
        """Flow review path identity is independent of matching bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "wrong-flow-artifact-path"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design_brief.md", design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / "design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / "design_review.md",
                [
                    *approved_design_review_lines(),
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="historical/design_brief.md",
            )
            write_active_packet_manifest(report_dir)

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "document_flow_review.md:design_artifact_path_mismatch",
                result.stdout,
            )

    def test_design_gate_accepts_path_sha_decision_without_source_packet_metadata(
        self,
    ) -> None:
        """Review SHA and decision are the active packet review identity."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-review-evidence"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_design_bundle_with_review(
                report_dir,
                design_brief_lines(),
                approved_design_review_lines(
                    include_source_packet=False,
                    include_reviewer_separation=False,
                ),
            )
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_implementation_gate_requires_current_design_approval(self) -> None:
        """Implementation cannot proceed from an invalid active packet review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "implementation-design-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design_brief.md", design_brief_lines())
            write_markdown(
                report_dir / "change_review.md",
                [
                    "# Change Review",
                    "",
                    "## Design-Base Implementation Review",
                    "Implementation cites the design.",
                    "## Canonical Tree-Head Review",
                    "Tree head is canonical.",
                    "## Decision",
                    "approve",
                ],
            )
            design_sha256 = hashlib.sha256(
                (report_dir / "design_brief.md").read_bytes()
            ).hexdigest()
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="design_brief.md",
                review_artifact="graph_document_flow_review.md",
            )
            write_active_packet_manifest(
                report_dir,
                document_flow_review_artifact="graph_document_flow_review.md",
            )

            missing_review = run_gate(report_dir, "implementation")
            write_markdown(
                report_dir / "design_review.md",
                [
                    line.replace("approve", "revise")
                    for line in approved_design_review_lines()
                ]
                + [f"review_target_sha256={design_sha256}"],
            )
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="design_brief.md",
                review_artifact="graph_document_flow_review.md",
            )
            stale_review = run_gate(report_dir, "implementation")
            write_markdown(
                report_dir / "design_review.md",
                [*approved_design_review_lines(), f"review_target_sha256={design_sha256}"],
            )
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="design_brief.md",
                review_artifact="graph_document_flow_review.md",
            )
            approved_review = run_gate(report_dir, "implementation")

            self.assertNotEqual(missing_review.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_field_invalid:design_review_artifact",
                missing_review.stdout,
            )
            self.assertIn(
                "NEXT_ACTION=return_to_design_owner_until_gate_approves",
                missing_review.stdout,
            )
            self.assertNotEqual(stale_review.returncode, 0)
            self.assertIn("design_review.md:decision_not_approve", stale_review.stdout)
            self.assertIn(
                "NEXT_ACTION=return_to_design_owner_until_gate_approves",
                stale_review.stdout,
            )
            self.assertEqual(
                approved_review.returncode,
                0,
                approved_review.stdout + approved_review.stderr,
            )

    def test_custom_packet_review_routes_implementation_to_design_owner(self) -> None:
        """Typed packet blockers route independently of declared basenames."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "custom-owner-route"
            report_dir.mkdir(parents=True, exist_ok=True)
            design_artifact = "architecture-record.txt"
            design_review = "technical-approval-record.txt"
            flow_review = "reader-path-record.txt"
            write_markdown(report_dir / design_artifact, design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / design_artifact).read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / design_review,
                [
                    "# Technical Approval Record",
                    f"- Design artifact path: {design_artifact}",
                    "## Decision",
                    "decision=revise",
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path=design_artifact,
                review_artifact=flow_review,
            )
            write_markdown(
                report_dir / "change_review.md",
                [
                    "# Change Review",
                    "## Design-Base Implementation Review",
                    "Implementation cites the active packet.",
                    "## Canonical Tree-Head Review",
                    "Tree head is canonical.",
                    "## Decision",
                    "approve",
                ],
            )
            write_active_packet_manifest(
                report_dir,
                design_artifact=design_artifact,
                design_review_artifact=design_review,
                document_flow_review_artifact=flow_review,
            )

            result = run_gate(report_dir, "implementation")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "technical-approval-record.txt:decision_not_approve",
                result.stdout,
            )
            self.assertIn(
                "NEXT_ACTION=return_to_design_owner_until_gate_approves",
                result.stdout,
            )

    def test_design_gate_rejects_under_specified_abstract_design_frame(self) -> None:
        """Design gate should require the six abstract design frame dimensions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "thin-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            thin_design = design_brief_lines()
            thin_design = [
                line
                for line in thin_design
                if not line.startswith(
                    (
                        "Concept or layer model:",
                        "Non-goals:",
                        "Future extension layers:",
                        "Evaluation axes:",
                        "Canonical-surface relationships:",
                    )
                )
            ]
            write_approved_design_bundle(report_dir, thin_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:concept_or_layer_model",
                result.stdout,
            )
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:canonical_surface_relationships",
                result.stdout,
            )

    def test_design_gate_rejects_term_inventory_abstract_design_frame(self) -> None:
        """Design gate should reject a one-line inventory of ADF terms."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "inventory-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            inventory_design = design_brief_lines()
            start = inventory_design.index("## Abstract Design Frame")
            end = inventory_design.index("## Upstream Requirement Packet")
            inventory_design = (
                inventory_design[: start + 1]
                + [
                    (
                        "Responsibility model, concept graph, non-goals, future extension layers, "
                        "evaluation axes, and relationship to existing canonical surfaces."
                    )
                ]
                + inventory_design[end:]
            )
            write_approved_design_bundle(report_dir, inventory_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:responsibility_model",
                result.stdout,
            )
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:evaluation_axes",
                result.stdout,
            )

    def test_design_gate_rejects_placeholder_abstract_design_frame_values(self) -> None:
        """Design gate should reject ADF labels that still have placeholder values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "placeholder-abstract-frame"
            report_dir.mkdir(parents=True, exist_ok=True)
            placeholder_design = design_brief_lines()
            placeholder_design = [
                "Responsibility model: todo" if line.startswith("Responsibility model:") else line
                for line in placeholder_design
            ]
            write_approved_design_bundle(report_dir, placeholder_design)
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design_brief.md:abstract_design_frame_missing:responsibility_model",
                result.stdout,
            )

    def test_implementation_checkpoint_contract_requires_abstract_trace(self) -> None:
        """Checkpoint review surfaces should reject file-local-only justification."""
        template_text = (PROJECT_ROOT / "agents" / "templates" / "change_review.md").read_text(
            encoding="utf-8"
        )
        workflow_text = (
            PROJECT_ROOT / "agents" / "workflows" / "implementation-waterfall-workflow.md"
        ).read_text(encoding="utf-8")

        for text in (template_text, workflow_text):
            self.assertIn("Abstract Design Frame", text)
            self.assertIn("Implementation Source Packet", text)
            self.assertIn("nearest file", text)
            self.assertIn("helper", text)
            self.assertIn("current finding", text)

    def test_final_gate_rejects_empty_work_log(self) -> None:
        """Final gate should fail when work_log.md has no concrete entries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-empty-work-log"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Post-Fix Full Review Rerun Review",
                        "No post-review fixes occurred after the last full review pass.",
                        "## Canonical Tree-Head Acceptance",
                        "Only canonical tracked paths remain in the tree head.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("work_log.md:section_empty_or_missing:entries", result.stdout)

    def test_final_gate_rejects_missing_post_fix_full_review_section(self) -> None:
        """Final gate should fail when the post-fix full review evidence is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-missing-post-fix-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Canonical Tree-Head Acceptance",
                        "Only canonical tracked paths remain in the tree head.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        (
                            "- `2026-04-12 14:10 JST | review | final pass recorded | "
                            "request_clause_ids: T1-C1 | next: closeout`"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "final_review.md:section_empty_or_missing:post-fix_full_review_rerun_review",
                result.stdout,
            )

    def test_final_gate_rejects_missing_canonical_tree_head_section(self) -> None:
        """Final gate should fail when canonical tree-head acceptance is missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-missing-canonical-tree-head"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "final_review.md").write_text(
                "\n".join(
                    [
                        "# Final Review",
                        "",
                        "## Ship Blockers",
                        "| Finding | Severity | Status |",
                        "| ------- | -------- | ------ |",
                        "| none | info | resolved |",
                        "## Design Trace Acceptance",
                        "Trace is complete.",
                        "## Planned Work Completion Review",
                        "All planned work units are complete.",
                        "## Spec-To-Product Coverage Review",
                        "Every clause has a product surface.",
                        "## Review Finding Incorporation Review",
                        "All fix-now findings were integrated.",
                        "## Post-Fix Full Review Rerun Review",
                        "No post-review fixes occurred after the last full review pass.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "work_log.md").write_text(
                "\n".join(
                    [
                        "# Work Log",
                        "",
                        "## Purpose",
                        "- Required run log.",
                        "",
                        "## Entries",
                        (
                            "- `2026-04-16 11:50 JST | review | final pass recorded | "
                            "request_clause_ids: T1-C1 | next: closeout`"
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "final",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "final_review.md:section_empty_or_missing:canonical_tree-head_acceptance",
                result.stdout,
            )

    def test_design_gate_rejects_missing_source_packet(self) -> None:
        """A design review should not pass when the design lacks source packet trace."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-source-packet"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_implementation=False),
            )
            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            expected_blocker = (
                "design_brief.md:section_empty_or_missing:implementation_source_packet"
            )
            self.assertIn(expected_blocker, result.stdout)

    def test_design_gate_rejects_missing_upstream_requirement_packet(self) -> None:
        """The active packet gate does not substitute a legacy upstream basename check."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-upstream-packet"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_approved_design_bundle(
                report_dir,
                design_brief_lines(include_upstream=False),
            )
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_graph_packet_selection_ignores_historical_design_basenames(self) -> None:
        """The graph packet is selected by its declared paths only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "graph-packet"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "graph_design_brief.md", design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / "graph_design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / "graph_design_review.md",
                [
                    "# Graph Design Review",
                    "- Design artifact path: graph_design_brief.md",
                    "## Decision",
                    "approve",
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_document_flow_review(
                report_dir,
                design_sha256,
                design_artifact_path="graph_design_brief.md",
                review_artifact="graph_document_flow_review.md",
            )
            write_active_packet_manifest(
                report_dir,
                design_artifact="graph_design_brief.md",
                design_review_artifact="graph_design_review.md",
                document_flow_review_artifact="graph_document_flow_review.md",
            )
            write_markdown(
                report_dir / "design_brief.md",
                ["# Historical design", "## Decision", "decision=revise"],
            )
            write_markdown(
                report_dir / "design_review.md",
                ["# Historical review", "decision=revise"],
            )
            result = run_gate(report_dir, "design")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_graph_packet_revise_review_fails_closed(self) -> None:
        """A declared review with revise remains a design-gate blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "graph-revise"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "graph_design_brief.md", design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / "graph_design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / "graph_design_review.md",
                [
                    "# Graph Design Review",
                    "- Design artifact path: graph_design_brief.md",
                    "decision=revise",
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_markdown(
                report_dir / "graph_document_flow_review.md",
                [
                    "# Graph Document Flow Review",
                    "- Design artifact path: graph_design_brief.md",
                    "approve",
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_active_packet_manifest(
                report_dir,
                design_artifact="graph_design_brief.md",
                design_review_artifact="graph_design_review.md",
                document_flow_review_artifact="graph_document_flow_review.md",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("graph_design_review.md:decision_not_approve", result.stdout)

    def test_design_gate_rejects_missing_manifest(self) -> None:
        """The design gate must not infer a packet from nearby files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-manifest"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "graph_design_brief.md", design_brief_lines())

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("team_manifest.yaml:missing", result.stdout)

    def test_design_gate_rejects_missing_packet_field(self) -> None:
        """Every active packet field is mandatory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-packet-field"
            write_active_packet_manifest(report_dir)
            rewrite_active_packet_field(
                report_dir,
                "document_flow_review_artifact",
                remove=True,
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_field_missing:document_flow_review_artifact",
                result.stdout,
            )

    def test_design_gate_rejects_wrong_packet_field_type(self) -> None:
        """YAML scalar coercion cannot bypass packet path validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "wrong-packet-field-type"
            write_active_packet_manifest(report_dir)
            rewrite_active_packet_field(report_dir, "design_artifact", 7)

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_field_invalid:design_artifact",
                result.stdout,
            )

    def test_design_gate_rejects_absolute_packet_path(self) -> None:
        """Active packet paths are report-relative declarations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "absolute-packet-path"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_active_packet_manifest(report_dir)
            rewrite_active_packet_field(
                report_dir,
                "design_artifact",
                str((report_dir / "design_brief.md").resolve()),
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_field_invalid:design_artifact",
                result.stdout,
            )

    def test_design_gate_rejects_unknown_packet_schema(self) -> None:
        """Unknown active packet schemas are typed blockers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "unknown-schema"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_active_packet_manifest(report_dir)
            rewrite_active_packet_field(
                report_dir,
                "schema",
                "waterfall.design_packet.v0",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_schema_unknown:waterfall.design_packet.v0",
                result.stdout,
            )

    def test_design_gate_rejects_packet_path_outside_bundle(self) -> None:
        """Declared packet paths cannot escape the report bundle."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "outside-path"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_active_packet_manifest(report_dir)
            rewrite_active_packet_field(
                report_dir,
                "design_artifact",
                "../graph_design_brief.md",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "team_manifest.yaml:active_design_packet_path_outside_bundle:design_artifact",
                result.stdout,
            )

    def test_design_gate_rejects_final_component_symlink(self) -> None:
        """A declared packet file must itself be a lexical regular file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "final-symlink"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "design-target.md", design_brief_lines())
            (report_dir / "design-link.md").symlink_to("design-target.md")
            write_markdown(report_dir / "design_review.md", ["# Review"])
            write_markdown(report_dir / "document_flow_review.md", ["# Flow"])
            write_active_packet_manifest(
                report_dir,
                design_artifact="design-link.md",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "design-link.md:missing",
                result.stdout,
            )

    def test_design_gate_rejects_symlinked_parent(self) -> None:
        """No parent component of a packet declaration may be a symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "parent-symlink"
            packet_dir = report_dir / "packet-real"
            packet_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(packet_dir / "design.md", design_brief_lines())
            (report_dir / "packet-link").symlink_to(
                "packet-real",
                target_is_directory=True,
            )
            write_markdown(report_dir / "design_review.md", ["# Review"])
            write_markdown(report_dir / "document_flow_review.md", ["# Flow"])
            write_active_packet_manifest(
                report_dir,
                design_artifact="packet-link/design.md",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "packet-link/design.md:missing",
                result.stdout,
            )

    def test_design_gate_rejects_missing_required_flow_review(self) -> None:
        """A required document-flow review must be declared and present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "missing-flow-review"
            report_dir.mkdir(parents=True, exist_ok=True)
            write_markdown(report_dir / "graph_design_brief.md", design_brief_lines())
            design_sha256 = hashlib.sha256(
                (report_dir / "graph_design_brief.md").read_bytes()
            ).hexdigest()
            write_markdown(
                report_dir / "graph_design_review.md",
                [
                    "# Graph Design Review",
                    "- Design artifact path: graph_design_brief.md",
                    "## Decision",
                    "approve",
                    f"review_target_sha256={design_sha256}",
                ],
            )
            write_active_packet_manifest(
                report_dir,
                design_artifact="graph_design_brief.md",
                design_review_artifact="graph_design_review.md",
                document_flow_review_artifact="graph_document_flow_review.md",
            )

            result = run_gate(report_dir, "design")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "graph_document_flow_review.md:design_artifact_path_missing",
                result.stdout,
            )

if __name__ == "__main__":
    unittest.main()
