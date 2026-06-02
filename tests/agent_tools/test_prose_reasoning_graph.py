# @dependency-start
# responsibility Tests prose reasoning graph CLI behavior.
# upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py graph CLI
# upstream design ../../documents/prose-reasoning-graph/dsl-spec.md graph DSL contract
# upstream design ../../documents/tools/prose_reasoning_graph.md tool contract
# @dependency-end
"""Tests for prose reasoning graph CLI."""

from __future__ import annotations

import json
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


class ProseReasoningGraphTest(unittest.TestCase):
    """Exercise graph ingest, analysis, projection, and handoff."""

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
            self.assertIn("$long-form-writing", handoff_targets(payload))
            self.assertIn("$experiment-lifecycle", handoff_targets(payload))
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

            explain = run_graph("explain", "--db", str(db), "--profile", "all", "--out", str(explanation))
            self.assertEqual(explain.returncode, 0, explain.stdout + explain.stderr)
            explanation_text = explanation.read_text(encoding="utf-8")
            self.assertIn("Main Claim Path", explanation_text)
            self.assertIn("`claim:", explanation_text)

            integrate = run_graph("integrate", "--db", str(db), "--profile", "all", "--out", str(integration))
            self.assertEqual(integrate.returncode, 0, integrate.stdout + integrate.stderr)
            integration_text = integration.read_text(encoding="utf-8")
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

            missing = run_graph("ingest", str(source), "--db", str(db), "--prompt-file", str(root / "missing.txt"))
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("prompt file does not exist", missing.stderr)

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
