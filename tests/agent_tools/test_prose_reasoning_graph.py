# @dependency-start
# responsibility Tests prose reasoning graph CLI behavior.
# upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py graph CLI
# upstream design ../../documents/prose-reasoning-graph/dsl-spec.md graph DSL contract
# upstream design ../../documents/tools/prose_reasoning_graph.md tool contract
# @dependency-end
"""Tests for prose reasoning graph CLI."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import cast

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "prose_reasoning_graph.py"


def run_graph(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the prose reasoning graph CLI."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_graph_with_env(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Run the prose reasoning graph CLI with environment overrides."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )


def stdout_value(result: subprocess.CompletedProcess[str], key: str) -> str:
    """Return one KEY=value field from command stdout."""
    prefix = f"{key}="
    for line in result.stdout.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix)
    raise AssertionError(f"missing stdout key {key}: {result.stdout}")


class ProseReasoningGraphTest(unittest.TestCase):
    """Exercise graph ingest, analysis, projection, and handoff."""

    def test_ingest_defaults_db_to_user_home_cache(self) -> None:
        """DB-creating commands should use the user-home cache unless --db is explicit."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            cache_root = root / "cache"
            stats = root / "ingest.stats.json"
            source.write_text("# Sample\n\n根拠として本文を DB に入れる。", encoding="utf-8")

            ingest = run_graph_with_env(
                {"AGENT_CANON_PROSE_GRAPH_HOME": str(cache_root)},
                "ingest",
                str(source),
                "--stats-out",
                str(stats),
            )

            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            self.assertIn("PROSE_REASONING_GRAPH_STATS=", ingest.stdout)
            stats_payload = cast(dict[str, object], json.loads(stats.read_text(encoding="utf-8")))
            stats_fields = cast(dict[str, object], stats_payload["fields"])
            db_path = Path(cast(str, stats_fields["PROSE_REASONING_GRAPH_DB"]))
            self.assertTrue(db_path.exists(), db_path)
            self.assertEqual(db_path.name, "prose_graph.sqlite")
            self.assertTrue(
                db_path.resolve().as_posix().startswith(cache_root.resolve().as_posix()),
                db_path,
            )

    def test_ingest_set_defaults_db_to_user_home_cache(self) -> None:
        """Multi-document DB creation should also accept the default cache route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            first = root / "first.md"
            second = root / "second.md"
            first.write_text("# First\n\n第一文書は根拠を持つ。", encoding="utf-8")
            second.write_text("# Second\n\n第二文書も根拠を持つ。", encoding="utf-8")

            ingest = run_graph_with_env(
                {"AGENT_CANON_PROSE_GRAPH_HOME": str(cache_root)},
                "ingest-set",
                str(first),
                str(second),
            )

            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            db_path = Path(stdout_value(ingest, "PROSE_REASONING_GRAPH_DB"))
            self.assertTrue(db_path.exists(), db_path)
            self.assertEqual(stdout_value(ingest, "PROSE_REASONING_GRAPH_DOCUMENTS"), "2")
            self.assertTrue(
                db_path.resolve().as_posix().startswith(cache_root.resolve().as_posix()),
                db_path,
            )

    def test_ingest_uses_home_cache_when_cache_env_is_unset(self) -> None:
        """The default DB route should be under HOME when no cache override is set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            fake_home = root / "home"
            source = root / "sample.md"
            source.write_text("# Sample\n\nHOME 配下の cache に DB を作る。", encoding="utf-8")

            ingest = run_graph_with_env(
                {"HOME": str(fake_home), "AGENT_CANON_PROSE_GRAPH_HOME": ""},
                "ingest",
                str(source),
            )

            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            db_path = Path(stdout_value(ingest, "PROSE_REASONING_GRAPH_DB"))
            expected_root = fake_home / ".cache" / "agent-canon" / "prose-reasoning-graph"
            self.assertTrue(db_path.exists(), db_path)
            self.assertTrue(
                db_path.resolve().as_posix().startswith(expected_root.resolve().as_posix()),
                db_path,
            )

    def test_ingest_analyze_project_and_explain(self) -> None:
        """The CLI should persist layers and emit human-readable outputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            db = root / "graph.sqlite"
            projection = root / "projection.yaml"
            diagnostics = root / "diagnostics.md"
            explanation = root / "explanation.md"
            integration = root / "integration.md"
            handoff = root / "handoff.md"
            rewrite = root / "rewrite.md"
            source.write_text(sample_text(), encoding="utf-8")

            ingest = run_graph(
                "ingest",
                str(source),
                "--db",
                str(db),
                "--prompt",
                "学術分野のコーパスを決め、Python/Rust code documentationにも使う。",
            )
            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            self.assertIn("PROSE_REASONING_GRAPH_INGEST=pass", ingest.stdout)

            analyze = run_graph("analyze", "--db", str(db), "--profile", "all")
            self.assertEqual(analyze.returncode, 0, analyze.stdout + analyze.stderr)

            stored_layers = self.layer_counts(db)
            for layer in [
                "source",
                "form",
                "concept",
                "phase",
                "discourse",
                "argument",
                "evidence",
                "experiment",
                "presentation",
                "diagnostics",
                "edit-operation",
                "explanation",
                "projection",
            ]:
                self.assertGreater(stored_layers.get(layer, 0), 0, layer)

            project = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "all",
                "--format",
                "yaml",
                "--out",
                str(projection),
            )
            self.assertEqual(project.returncode, 0, project.stdout + project.stderr)
            payload = cast(dict[str, object], yaml.safe_load(projection.read_text(encoding="utf-8")))
            self.assertEqual(payload["profile"], "all")
            self.assertEqual(payload["canonical_graph"], "text_anchored_semantic_graph")
            corpus_hints = typed_items(payload, "corpus_hints")
            self.assertTrue(any(item.get("corpus_id") == "software_engineering" for item in corpus_hints))
            self.assertTrue(any(item.get("corpus_id") == "academic_writing" for item in corpus_hints))
            local_ir = cast(dict[str, object], payload["local_llm_prose_ir"])
            self.assertEqual(local_ir["schema"], "agent_canon.local_llm.prose_ir.v1")
            self.assertGreaterEqual(cast(int, local_ir["part_count"]), 1)
            dsl_seed = cast(dict[str, object], local_ir["dsl_seed"])
            self.assertGreaterEqual(len(cast(list[object], dsl_seed["nodes"])), 1)
            self.assertIn("$long-form-writing", handoff_targets(payload))
            self.assertIn("$experiment-lifecycle", handoff_targets(payload))
            self.assertIn("$formal-proof-workflow", handoff_targets(payload))
            diagnostics_payload = typed_items(payload, "diagnostics")
            verification_routes = {
                cast(dict[str, object], item.get("action", {})).get("verification_route")
                for item in diagnostics_payload
                if isinstance(item.get("action"), dict)
            }
            self.assertIn("claim_support_verification", verification_routes)
            self.assertIn("connection_verification", verification_routes)
            recursive_payloads = [
                cast(dict[str, object], cast(dict[str, object], item["action"])["recursive_verification"])
                for item in diagnostics_payload
                if isinstance(item.get("action"), dict)
                and isinstance(cast(dict[str, object], item["action"]).get("recursive_verification"), dict)
            ]
            self.assertTrue(any(payload.get("max_depth") == 3 for payload in recursive_payloads))
            source_anchors = typed_items(payload, "source_anchors")
            self.assertTrue(any(item.get("kind") == "sentence" for item in source_anchors))
            sentence_anchor = next(item for item in source_anchors if item.get("kind") == "sentence")
            sentence_payload = cast(dict[str, object], sentence_anchor["payload"])
            self.assertEqual(sentence_payload["span_kind"], "sentence")
            self.assertEqual(sentence_payload["segmentation_basis"], "sentence_split")
            projection_views = typed_items(payload, "projection_views")
            self.assertGreaterEqual(len(projection_views), 1)
            first_view = projection_views[0]
            self.assertTrue(str(first_view["view_id"]).startswith("view:all:"))
            self.assertIn("p:1", cast(list[str], first_view["members"]))
            self.assertIn("recommended_format", first_view)
            self.assertIn("format_reason", first_view)
            inference_basis = cast(dict[str, object], first_view["inference_basis"])
            self.assertEqual(inference_basis["source"], "canonical_graph_projection")
            self.assertTrue(
                any(
                    view.get("recommended_format") in {"figure", "table", "bulleted_list"}
                    for view in projection_views
                )
            )

            lint = run_graph("lint", "--db", str(db), "--profile", "all", "--out", str(diagnostics))
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            diagnostics_text = diagnostics.read_text(encoding="utf-8")
            self.assertIn("unsupported_claim", diagnostics_text)
            self.assertIn("metric_without_baseline", diagnostics_text)
            self.assertIn("verification_route=`claim_support_verification`", diagnostics_text)
            self.assertIn("verification_route=`connection_verification`", diagnostics_text)

            explain = run_graph("explain", "--db", str(db), "--profile", "all", "--out", str(explanation))
            self.assertEqual(explain.returncode, 0, explain.stdout + explain.stderr)
            explanation_text = explanation.read_text(encoding="utf-8")
            self.assertIn("Main Claim Path", explanation_text)
            self.assertIn("`claim:", explanation_text)

            integrate = run_graph("integrate", "--db", str(db), "--profile", "all", "--out", str(integration))
            self.assertEqual(integrate.returncode, 0, integrate.stdout + integrate.stderr)
            integration_text = integration.read_text(encoding="utf-8")
            self.assertIn("## Verification Routes", integration_text)
            self.assertIn("claim_support_verification", integration_text)
            self.assertIn("connection_verification", integration_text)
            self.assertIn("$literature-survey", integration_text)
            self.assertIn("recursive_max_depth", integration_text)
            self.assertIn("decompose_claim", integration_text)
            self.assertIn("verify_missing_premise", integration_text)
            operation_payload_by_kind = operation_payloads(db)
            for operation_kind in (
                "split_paragraph",
                "merge_paragraphs",
                "add_bridge",
                "reorder_paragraphs",
            ):
                self.assertIn(operation_kind, integration_text)
                self.assertIn(operation_kind, operation_payload_by_kind)
                self.assertEqual(
                    operation_payload_by_kind[operation_kind]["provenance"],
                    "source_graph_nodes",
                )
                self.assertEqual(
                    operation_payload_by_kind[operation_kind]["history_effect"],
                    "records_candidate_without_mutating_source",
                )

            op_id = first_operation_id(db, "merge_paragraphs")
            packet = run_graph("rewrite-packet", "--db", str(db), "--op", op_id, "--out", str(rewrite))
            self.assertEqual(packet.returncode, 0, packet.stdout + packet.stderr)
            self.assertIn("Do Not", rewrite.read_text(encoding="utf-8"))

            handoff_result = run_graph("skill-handoff", "--db", str(db), "--profile", "all", "--out", str(handoff))
            self.assertEqual(handoff_result.returncode, 0, handoff_result.stdout + handoff_result.stderr)
            handoff_text = handoff.read_text(encoding="utf-8")
            self.assertIn("$paper-writing", handoff_text)
            self.assertIn("citation-evidence-review", handoff_text)
            self.assertIn("projection_views[].recommended_format", handoff_text)
            self.assertIn("corpus_hints", handoff_text)
            self.assertIn("## Verification Routes", handoff_text)
            self.assertIn("$formal-proof-workflow", handoff_text)
            self.assertIn("recursive_steps", handoff_text)

    def test_json_projection_matches_layer_contract(self) -> None:
        """JSON projection should expose all requested layer keys."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            db = root / "graph.sqlite"
            output = root / "projection.json"
            stats = root / "project.stats.json"
            source.write_text(sample_text(), encoding="utf-8")
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)

            result = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "report",
                "--format",
                "json",
                "--out",
                str(output),
                "--stats-out",
                str(stats),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PROSE_REASONING_GRAPH_STATS=", result.stdout)
            payload = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
            self.assertIn("layers", payload)
            self.assertEqual(payload["canonical_graph"], "text_anchored_semantic_graph")
            self.assertIn("projection_views", payload)
            self.assertIn("source_anchors", payload)
            layers = payload["layers"]
            self.assertIsInstance(layers, dict)
            self.assertIn("edit-operation", cast(dict[str, object], layers))
            self.assertIn("$report-writing", handoff_targets(payload))
            stats_payload = cast(dict[str, object], json.loads(stats.read_text(encoding="utf-8")))
            self.assertEqual(stats_payload["schema"], "prose_reasoning_graph.stats.v1")

    def test_structured_analysis_db_without_edit_operations_can_project_and_integrate(self) -> None:
        """Document-canon graph DBs may have diagnostics without prose rewrite operations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            db = root / "structured.sqlite"
            projection = root / "projection.json"
            explanation = root / "explanation.md"
            integration = root / "integration.md"
            create_structured_analysis_style_db(db)

            project = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "all",
                "--format",
                "json",
                "--out",
                str(projection),
            )
            self.assertEqual(project.returncode, 0, project.stdout + project.stderr)
            payload = cast(dict[str, object], json.loads(projection.read_text(encoding="utf-8")))
            self.assertEqual(payload["edit_operations"], [])
            self.assertEqual(cast(dict[str, object], payload["layers"])["edit-operation"], 0)
            diagnostics_payload = typed_items(payload, "diagnostics")
            self.assertEqual(diagnostics_payload[0]["layer"], "document-canon")

            explain = run_graph("explain", "--db", str(db), "--profile", "all", "--out", str(explanation))
            self.assertEqual(explain.returncode, 0, explain.stdout + explain.stderr)
            self.assertIn("No edit operations recorded.", explanation.read_text(encoding="utf-8"))

            integrate = run_graph("integrate", "--db", str(db), "--profile", "all", "--out", str(integration))
            self.assertEqual(integrate.returncode, 0, integrate.stdout + integrate.stderr)
            integration_text = integration.read_text(encoding="utf-8")
            self.assertIn("No edit operations recorded.", integration_text)
            self.assertIn("document_responsibility_verification", integration_text)
            self.assertIn("expand_coverage_rule", integration_text)

    def test_check_document_runs_prose_and_document_canon_paths(self) -> None:
        """One command should run prose graph analysis and target document-canon import."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "documents" / "tools" / "example.md"
            inventory = root / "document_inventory.json"
            db = root / "graph.sqlite"
            out_dir = root / "out"
            stats = root / "check.stats.json"
            source.parent.mkdir(parents=True)
            source.write_text(sample_text(), encoding="utf-8")
            inventory.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "root": str(root),
                        "documents": [
                            {
                                "path": "documents/tools/example.md",
                                "title": "example",
                                "responsibility": "Documents example tool usage.",
                                "has_dependency_manifest": True,
                            },
                            {
                                "path": "documents/prose-reasoning-graph/dsl-spec.md",
                                "title": "DSL spec",
                                "responsibility": "Defines the graph contract.",
                                "has_dependency_manifest": True,
                            },
                        ],
                        "findings": [
                            {
                                "path": "documents/tools/example.md",
                                "kind": "document_responsibility_gap",
                                "canonical_path": "documents/prose-reasoning-graph/dsl-spec.md",
                                "action": "expand",
                                "reason": "missing_responsibility_coverage=`graph_format_trace`",
                            }
                        ],
                        "document_count": 2,
                        "finding_count": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = run_graph(
                "check-document",
                str(source),
                "--repo-root",
                str(root),
                "--structured-inventory-json",
                str(inventory),
                "--db",
                str(db),
                "--out-dir",
                str(out_dir),
                "--profile",
                "all",
                "--stats-out",
                str(stats),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            stats_payload = cast(dict[str, object], json.loads(stats.read_text(encoding="utf-8")))
            stats_fields = cast(dict[str, object], stats_payload["fields"])
            self.assertEqual(stats_fields["PROSE_REASONING_GRAPH_DOCUMENT_CANON_FINDINGS"], 1)
            self.assertGreater(cast(int, stats_fields["PROSE_REASONING_GRAPH_PROSE_DIAGNOSTICS"]), 0)
            for key in (
                "PROSE_REASONING_GRAPH_DOCUMENT_CHECK",
                "PROSE_REASONING_GRAPH_DIAGNOSTICS",
                "PROSE_REASONING_GRAPH_EXPLANATION",
                "PROSE_REASONING_GRAPH_INTEGRATION_PLAN",
                "PROSE_REASONING_GRAPH_SKILL_HANDOFF",
            ):
                self.assertTrue(Path(cast(str, stats_fields[key])).is_file(), key)

            report_text = (out_dir / "document_check.md").read_text(encoding="utf-8")
            self.assertIn("document-canon findings: `1`", report_text)
            self.assertIn("structured-analysis document-canon path", report_text)
            diagnostics_text = (out_dir / "prose_diagnostics.md").read_text(encoding="utf-8")
            self.assertIn("document_responsibility_gap", diagnostics_text)
            integration_text = (out_dir / "prose_integration.md").read_text(encoding="utf-8")
            self.assertIn("document_responsibility_verification", integration_text)
            self.assertIn("trace_downstream_claim", integration_text)
            self.assertIn("unsupported_claim", diagnostics_text)

            with sqlite3.connect(db) as connection:
                row = connection.execute(
                    "SELECT COUNT(*) FROM diagnostics WHERE layer = 'document-canon'"
                ).fetchone()
            self.assertEqual(row[0], 1)

    def test_projection_views_are_derived_from_canonical_anchors(self) -> None:
        """Projection views should keep anchor membership and not become source nodes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            db = root / "graph.sqlite"
            output = root / "projection.json"
            source.write_text(sample_text(), encoding="utf-8")
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "writing").returncode, 0)
            result = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "writing",
                "--format",
                "json",
                "--out",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            payload = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
            views = typed_items(payload, "projection_views")
            nodes = typed_items(payload, "nodes")
            node_ids = {str(item["node_id"]) for item in nodes}
            view_ids = {str(item["view_id"]) for item in views}

            self.assertGreater(len(views), 0)
            self.assertFalse(view_ids & node_ids)
            for view in views:
                members = cast(list[str], view["members"])
                self.assertGreater(len(members), 0)
                for member in members:
                    self.assertIn(member, node_ids)
                basis = cast(dict[str, object], view["inference_basis"])
                self.assertIn("member_anchor_ids", basis)

    def test_experiment_diagnostics_have_unique_rules(self) -> None:
        """Experiment coverage diagnostics should not overwrite one another."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "experiment_gap.md"
            db = root / "graph.sqlite"
            source.write_text(
                "The experiment compares workflows without enough planning detail.",
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "experiment").returncode, 0)

            rules = diagnostic_rules(db)

            for rule in (
                "experiment_without_hypothesis",
                "experiment_without_metric",
                "metric_without_baseline",
                "experiment_without_expected_result",
            ):
                self.assertIn(rule, rules)
            self.assertEqual(len(rules), len(set(rules)))

    def test_corpus_identifier_does_not_trigger_experiment_layer(self) -> None:
        """Corpus ids should not be mistaken for experiment-plan prose."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "corpus_id.md"
            db = root / "graph.sqlite"
            source.write_text(
                "The selected corpus id is `experimental_report`, used only as metadata.",
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)

            rules = diagnostic_rules(db)

            self.assertNotIn("experiment_without_hypothesis", rules)
            self.assertNotIn("experiment_without_metric", rules)
            self.assertNotIn("metric_without_baseline", rules)
            self.assertNotIn("experiment_without_expected_result", rules)
            self.assertEqual(nodes_by_layer(db, "experiment"), [])

    def test_all_profile_does_not_require_experiment_layer_without_empirical_cues(self) -> None:
        """Design prose should not need an experiment layer unless experiment cues apply."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tool_design.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # Tool Design

                    The tool must keep command output compact because large JSON artifacts belong in files.

                    Therefore the design separates command stats from stored graph records.
                    """
                ).strip(),
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            rules = diagnostic_rules(db)

            self.assertNotIn("missing_layer_representation", rules)
            self.assertEqual(nodes_by_layer(db, "experiment"), [])

    def test_mermaid_edges_do_not_create_topic_jump_findings(self) -> None:
        """Mermaid edge rows are structured presentation, not prose transitions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "diagram.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # Diagram

                    ```mermaid
                    flowchart LR
                      subgraph ingest_stage
                        docs[Documents]
                        ingest[Ingest]
                        db[(SQLite)]
                      end
                      docs --> ingest
                      ingest --> db
                    ```

                    この図は result surface の流れを示す。
                    """
                ).strip(),
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)

            self.assertNotIn("topic_jump_without_bridge", diagnostic_rules(db))

    def test_dependency_header_comment_is_not_an_edit_target(self) -> None:
        """Dependency headers are metadata, not prose rewrite targets."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "header.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    <!--
                    @dependency-start
                    responsibility Documents prose graph usage and contract.
                    upstream implementation tools/agent_tools/prose_reasoning_graph.py builds prose graph usage.
                    @dependency-end
                    -->

                    # Tool

                    This prose graph usage guide documents command surface and result surface.
                    """
                ).strip(),
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)

            self.assertNotIn("merge_paragraphs", operation_payloads(db))

    def test_experiment_vocabulary_explanation_does_not_trigger_plan_diagnostics(self) -> None:
        """Explaining experiment vocabulary should not become an experiment plan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tool_profile.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # Tool Profile

                    The experiment profile names hypothesis, metric, baseline, and expected result fields.

                    These names document routing vocabulary, not a run plan.
                    """
                ).strip(),
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            rules = diagnostic_rules(db)
            self.assertNotIn("experiment_without_hypothesis", rules)
            self.assertNotIn("experiment_without_metric", rules)
            self.assertNotIn("metric_without_baseline", rules)
            self.assertNotIn("experiment_without_expected_result", rules)

    def test_local_llm_ir_controls_experiment_plan_applicability(self) -> None:
        """Experiment-plan applicability should come from LocalLLM IR, not text cues alone."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tool_profile.md"
            ir = root / "local_ir.json"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # Tool Profile

                    The hypothesis is a routing vocabulary example. The metric is a field name.
                    """
                ).strip(),
                encoding="utf-8",
            )
            ir.write_text(
                json.dumps(
                    {
                        "schema": "agent_canon.local_llm.prose_ir.v1",
                        "task_owner": "local_llm",
                        "status": "extracted_intermediate_representation",
                        "analysis_intents": [
                            {
                                "intent": "experiment_plan",
                                "path": str(source),
                                "status": "vocabulary_only",
                                "field_kinds": [],
                                "vocabulary_kinds": ["hypothesis", "metric"],
                                "basis": "test-local-llm-ir",
                            }
                        ],
                        "corpus_hints": [],
                        "dsl_seed": {"nodes": [], "edges": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                run_graph("ingest", str(source), "--db", str(db), "--local-llm-ir-json", str(ir)).returncode,
                0,
            )
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            self.assertEqual(nodes_by_layer(db, "experiment"), [])
            rules = diagnostic_rules(db)
            self.assertNotIn("experiment_without_hypothesis", rules)
            self.assertNotIn("experiment_without_metric", rules)

    def test_missing_local_llm_ir_uses_warned_non_llm_fallback(self) -> None:
        """Non-LLM experiment fallback is allowed only with an explicit warning."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "legacy_experiment.md"
            db = root / "legacy.sqlite"
            source.write_text(
                "The experiment compares workflows without enough planning detail.",
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            with sqlite3.connect(db) as connection:
                connection.execute("DELETE FROM metadata WHERE key = ?", ("local_llm_prose_ir",))

            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            rules = diagnostic_rules(db)
            self.assertIn("non_llm_experiment_plan_fallback", rules)
            self.assertIn("experiment_without_hypothesis", rules)
            self.assertIn("experiment_without_metric", rules)

    def test_missing_local_llm_ir_warns_even_when_fallback_is_negative(self) -> None:
        """Fallback use is visible even when the non-LLM check finds no plan."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "plain_report.md"
            db = root / "plain.sqlite"
            source.write_text(
                "This tool writes a compact report artifact for reviewers.",
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            with sqlite3.connect(db) as connection:
                connection.execute("DELETE FROM metadata WHERE key = ?", ("local_llm_prose_ir",))

            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            rules = diagnostic_rules(db)
            self.assertIn("non_llm_experiment_plan_fallback", rules)
            self.assertNotIn("experiment_without_hypothesis", rules)
            self.assertNotIn("experiment_without_metric", rules)

    def test_one_sentence_can_materialize_multiple_experiment_fields(self) -> None:
        """One sentence may state more than one experiment-plan field."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "experiment_fields.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # Plan

                    The hypothesis is that graph checks improve drafts.

                    The metric is finding count and the baseline is the initial draft.

                    The expected result is fewer unresolved findings.
                    """
                ).strip(),
                encoding="utf-8",
            )
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            self.assertGreaterEqual(len(nodes_by_layer_kind(db, "experiment", "hypothesis")), 1)
            self.assertGreaterEqual(len(nodes_by_layer_kind(db, "experiment", "metric")), 1)
            self.assertGreaterEqual(len(nodes_by_layer_kind(db, "experiment", "baseline")), 1)
            self.assertGreaterEqual(len(nodes_by_layer_kind(db, "experiment", "expected_result")), 1)
            self.assertNotIn("experiment_without_metric", diagnostic_rules(db))

    def test_japanese_sentence_units_and_discourse_cues(self) -> None:
        """Japanese prose should split sentences and recognize local bridge cues."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "japanese_report.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # 状態報告

                    根拠として測定結果があり、したがって文章構造グラフは検査できる。

                    このため、現在の文章構造グラフの差分を説明する。

                    例えば、仮説は構造化で論理穴が減ることである。

                    例えば、指標は unsupported claim の件数で見る。

                    例えば、ベースラインは初稿の診断件数である。

                    例えば、期待結果は blocker が減ることである。

                    ただし、制限はヒューリスティックが残ることである。
                    """
                ).strip(),
                encoding="utf-8",
            )

            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)

            rules = diagnostic_rules(db)
            self.assertNotIn("topic_jump_without_bridge", rules)
            self.assertNotIn("experiment_without_hypothesis", rules)
            self.assertNotIn("experiment_without_metric", rules)
            self.assertNotIn("metric_without_baseline", rules)
            self.assertNotIn("experiment_without_expected_result", rules)
            self.assertNotIn("unsupported_claim", rules)
            self.assertGreaterEqual(len(nodes_by_layer_kind(db, "form", "sentence")), 7)

    def test_ascii_sentence_units_preserve_abbreviations_and_versions(self) -> None:
        """ASCII prose should not split common abbreviations or version strings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "ascii_report.md"
            db = root / "graph.sqlite"
            source.write_text(
                textwrap.dedent(
                    """
                    # ASCII Report

                    The method cites e.g. v1.2.3 and Fig. 2. It must still split here.
                    """
                ).strip(),
                encoding="utf-8",
            )

            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)

            sentences = node_texts_by_layer_kind(db, "form", "sentence")
            self.assertIn("The method cites e.g. v1.2.3 and Fig. 2.", sentences)
            self.assertIn("It must still split here.", sentences)
            self.assertNotIn("The method cites e.g.", sentences)
            self.assertNotIn("v1.2.3 and Fig.", sentences)

    def test_prompt_file_influences_corpus_hints_and_missing_file_errors(self) -> None:
        """Prompt files should feed corpus hints and fail clearly when absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            prompt = root / "prompt.txt"
            db = root / "graph.sqlite"
            projection = root / "projection.json"
            source.write_text("# Note\n\nPlain prose for routing.", encoding="utf-8")
            prompt.write_text("Python code documentation for an academic paper.", encoding="utf-8")

            ingest = run_graph(
                "ingest",
                str(source),
                "--db",
                str(db),
                "--prompt",
                "学術",
                "--prompt-file",
                str(prompt),
            )
            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            project = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "writing",
                "--format",
                "json",
                "--out",
                str(projection),
            )
            self.assertEqual(project.returncode, 0, project.stdout + project.stderr)

            payload = cast(dict[str, object], json.loads(projection.read_text(encoding="utf-8")))
            corpus_hints = typed_items(payload, "corpus_hints")
            self.assertTrue(any(item.get("corpus_id") == "software_engineering" for item in corpus_hints))
            self.assertTrue(any(item.get("corpus_id") == "academic_writing" for item in corpus_hints))
            local_ir = cast(dict[str, object], payload["local_llm_prose_ir"])
            self.assertEqual(local_ir["task_owner"], "local_llm")
            self.assertEqual(cast(dict[str, object], local_ir["partition"])["document_batch_size"], 4)

            missing = run_graph("ingest", str(source), "--db", str(db), "--prompt-file", str(root / "missing.txt"))
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("prompt file does not exist", missing.stderr)

    def test_ingest_set_stores_multiple_documents_in_one_db(self) -> None:
        """Multi-document ingest should preserve per-file text and source anchors."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first = root / "first.md"
            second = root / "second.md"
            db = root / "graph.sqlite"
            projection = root / "projection.json"
            first.write_text("# First\n\n根拠として第一文書は DB に入る。", encoding="utf-8")
            second.write_text("# Second\n\n根拠として第二文書も DB に入る。", encoding="utf-8")

            ingest = run_graph(
                "ingest-set",
                str(root),
                "--db",
                str(db),
                "--prompt",
                "structured analysis code dependency report",
                "--term",
                "第一文書",
                "--term",
                "第二文書",
                "--local-llm-document-batch-size",
                "1",
                "--local-llm-term-batch-size",
                "1",
            )
            self.assertEqual(ingest.returncode, 0, ingest.stdout + ingest.stderr)
            self.assertIn("PROSE_REASONING_GRAPH_INGEST_SET=pass", ingest.stdout)
            self.assertIn("PROSE_REASONING_GRAPH_DOCUMENTS=2", ingest.stdout)

            with sqlite3.connect(db) as connection:
                document_rows = connection.execute("SELECT id, path FROM documents ORDER BY id").fetchall()
                source_rows = connection.execute(
                    "SELECT id, document_id, text FROM nodes WHERE layer = 'source' ORDER BY id"
                ).fetchall()
                sentence_rows = connection.execute(
                    "SELECT id, document_id, text FROM nodes WHERE layer = 'form' AND kind = 'sentence' ORDER BY id"
                ).fetchall()

            self.assertEqual([row[0] for row in document_rows], ["doc:1", "doc:2", "doc:analysis"])
            self.assertIn(str(first), [row[1] for row in document_rows])
            self.assertIn(str(second), [row[1] for row in document_rows])
            self.assertEqual(len(source_rows), 2)
            self.assertTrue(any("第一文書" in row[2] for row in source_rows))
            self.assertTrue(any("第二文書" in row[2] for row in source_rows))
            self.assertTrue(any(str(row[0]).startswith("d1:s:") for row in sentence_rows))
            self.assertTrue(any(str(row[0]).startswith("d2:s:") for row in sentence_rows))

            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "report").returncode, 0)
            project = run_graph(
                "project",
                "--db",
                str(db),
                "--profile",
                "report",
                "--format",
                "json",
                "--out",
                str(projection),
            )
            self.assertEqual(project.returncode, 0, project.stdout + project.stderr)
            payload = cast(dict[str, object], json.loads(projection.read_text(encoding="utf-8")))
            documents = typed_items(payload, "documents")
            self.assertEqual(len(documents), 3)
            self.assertTrue(any(item.get("document_id") == "doc:analysis" for item in documents))
            local_ir = cast(dict[str, object], payload["local_llm_prose_ir"])
            self.assertEqual(local_ir["document_count"], 2)
            self.assertEqual(local_ir["term_count"], 2)
            self.assertEqual(local_ir["part_count"], 4)

    def test_rewrite_packet_reports_missing_operation(self) -> None:
        """Missing operation ids should fail clearly through the CLI."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.md"
            db = root / "graph.sqlite"
            output = root / "rewrite.md"
            source.write_text(sample_text(), encoding="utf-8")
            self.assertEqual(run_graph("ingest", str(source), "--db", str(db)).returncode, 0)
            self.assertEqual(run_graph("analyze", "--db", str(db), "--profile", "all").returncode, 0)

            result = run_graph("rewrite-packet", "--db", str(db), "--op", "missing", "--out", str(output))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing edit operation: missing", result.stderr)

    def layer_counts(self, db: Path) -> dict[str, int]:
        """Return layer counts from DB nodes/edges/diagnostics/operations."""
        with sqlite3.connect(db) as connection:
            counts: dict[str, int] = {}
            for table in ("nodes", "edges"):
                rows = connection.execute(f"SELECT layer, COUNT(*) FROM {table} GROUP BY layer")
                for layer, count in rows:
                    counts[str(layer)] = counts.get(str(layer), 0) + int(count)
            diagnostics = connection.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
            operations = connection.execute("SELECT COUNT(*) FROM edit_operations").fetchone()[0]
            counts["diagnostics"] = counts.get("diagnostics", 0) + int(diagnostics)
            counts["edit-operation"] = counts.get("edit-operation", 0) + int(operations)
        return counts


def sample_text() -> str:
    """Return a compact prose fixture."""
    return textwrap.dedent(
        """
        # Prose Graph

        Prose reasoning graph should make structure inspectable because graph evidence is stored. It must help reviewers.

        The graph should make structure inspectable because graph evidence is stored. It must help writing skills.

        Quantum kernels wander through orchard weather. This unrelated paragraph has no bridge.

        The hypothesis is that graph diagnostics improve revision quality. The experiment compares workflows. The metric is unsupported-claim count. The expected result is fewer gaps.
        """
    ).strip()


def create_structured_analysis_style_db(db: Path) -> None:
    """Create a structured-analysis-like graph DB without edit operations."""
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                layer TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                text TEXT NOT NULL,
                source_start INTEGER NOT NULL,
                source_end INTEGER NOT NULL,
                confidence REAL NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE edges (
                id TEXT PRIMARY KEY,
                layer TEXT NOT NULL,
                kind TEXT NOT NULL,
                from_node_id TEXT NOT NULL,
                to_node_id TEXT NOT NULL,
                order_kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_node_id TEXT,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE diagnostics (
                id TEXT PRIMARY KEY,
                layer TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                target_edge_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                rule TEXT NOT NULL,
                message TEXT NOT NULL,
                suggested_action_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            ("corpus_hints", "[]"),
        )
        connection.execute(
            "INSERT INTO documents(id, path, title, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            ("doc:structured", "documents/tools/example.md", "Tool Example", "document", "2026-06-04T00:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO nodes(
                id, document_id, layer, kind, label, text, source_start, source_end, confidence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "structured:p:1",
                "doc:structured",
                "form",
                "paragraph",
                "document responsibility paragraph",
                "The tool guide explains document responsibility coverage for graph records.",
                0,
                73,
                1.0,
                json.dumps({"span_kind": "paragraph", "segmentation_basis": "structured_analysis"}),
            ),
        )
        connection.execute(
            """
            INSERT INTO diagnostics(
                id, layer, target_node_id, target_edge_id, severity, rule, message, suggested_action_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "diag:doc:1",
                "document-canon",
                "structured:p:1",
                "",
                "warn",
                "document_responsibility_gap",
                "Document responsibility coverage needs verification before rewrite.",
                json.dumps(
                    {
                        "verification_route": "document_responsibility_verification",
                        "verification_question": "Does the downstream document cover the upstream rule?",
                        "verification_targets": ["structured:p:1"],
                        "recursive_verification": {
                            "max_depth": 3,
                            "closure_condition": "all declared coverage groups are verified or limited",
                            "unresolved_leaf_policy": "record blocker or warn",
                            "steps": [
                                {
                                    "id": "expand_coverage_rule",
                                    "route": "document-canon",
                                    "question": "Which coverage group is missing?",
                                    "if_unresolved": "keep diagnostic active",
                                }
                            ],
                        },
                    }
                ),
            ),
        )


def handoff_targets(payload: dict[str, object]) -> set[str]:
    """Return handoff target names from a projection payload."""
    handoffs = payload.get("skill_handoffs", [])
    if not isinstance(handoffs, list):
        return set()
    targets: set[str] = set()
    for item in cast(list[object], handoffs):
        if not isinstance(item, dict):
            continue
        target = cast(dict[str, object], item).get("target")
        if isinstance(target, str):
            targets.add(target)
    return targets


def typed_items(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    """Return a projection payload list of dictionaries."""
    raw_items = payload.get(key, [])
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, object]] = []
    for item in cast(list[object], raw_items):
        if isinstance(item, dict):
            items.append(cast(dict[str, object], item))
    return items


def diagnostic_rules(db: Path) -> list[str]:
    """Return diagnostic rules from the graph database."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT rule FROM diagnostics ORDER BY rule").fetchall()
    return [str(row[0]) for row in rows]


def nodes_by_layer_kind(db: Path, layer: str, kind: str) -> list[str]:
    """Return node ids for one layer and kind."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT id FROM nodes WHERE layer = ? AND kind = ? ORDER BY id",
            (layer, kind),
        ).fetchall()
    return [str(row[0]) for row in rows]


def node_texts_by_layer_kind(db: Path, layer: str, kind: str) -> list[str]:
    """Return node text for one layer and kind."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            "SELECT text FROM nodes WHERE layer = ? AND kind = ? ORDER BY id",
            (layer, kind),
        ).fetchall()
    return [str(row[0]) for row in rows]


def nodes_by_layer(db: Path, layer: str) -> list[str]:
    """Return node ids for one layer."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT id FROM nodes WHERE layer = ? ORDER BY id", (layer,)).fetchall()
    return [str(row[0]) for row in rows]


def operation_payloads(db: Path) -> dict[str, dict[str, object]]:
    """Return edit-operation payloads by operation kind."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT kind, payload_json FROM edit_operations").fetchall()
    return {str(kind): cast(dict[str, object], json.loads(str(payload))) for kind, payload in rows}


def first_operation_id(db: Path, kind: str) -> str:
    """Return the first operation id of a kind."""
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT id FROM edit_operations WHERE kind = ? ORDER BY id LIMIT 1",
            (kind,),
        ).fetchone()
    if row is None:
        raise AssertionError(f"missing operation kind: {kind}")
    return str(row[0])


if __name__ == "__main__":
    unittest.main()
