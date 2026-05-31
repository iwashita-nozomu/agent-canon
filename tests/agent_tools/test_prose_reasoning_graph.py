# @dependency-start
# responsibility Tests prose reasoning graph CLI behavior.
# upstream implementation ../../tools/agent_tools/prose_reasoning_graph.py graph CLI
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

            ingest = run_graph("ingest", str(source), "--db", str(db))
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
            self.assertIn("$long-form-writing", handoff_targets(payload))
            self.assertIn("$experiment-lifecycle", handoff_targets(payload))

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
            self.assertIn("merge_paragraphs", integration_text)
            self.assertIn("add_bridge", integration_text)

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
            layers = payload["layers"]
            self.assertIsInstance(layers, dict)
            self.assertIn("edit-operation", cast(dict[str, object], layers))
            self.assertIn("$report-writing", handoff_targets(payload))
            stats_payload = cast(dict[str, object], json.loads(stats.read_text(encoding="utf-8")))
            self.assertEqual(stats_payload["schema"], "prose_reasoning_graph.stats.v1")

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


def diagnostic_rules(db: Path) -> list[str]:
    """Return diagnostic rules from the graph database."""
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT rule FROM diagnostics ORDER BY rule").fetchall()
    return [str(row[0]) for row in rows]


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
