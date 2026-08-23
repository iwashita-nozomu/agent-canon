"""Public contract tests for dependency manifest graph rendering."""

# @dependency-start
# contract test
# responsibility Tests dependency manifest graph bundle and projection public contracts.
# upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders deterministic graph bundles and projections.
# upstream implementation ../../tools/agent_tools/visualization_contract.py validates complete projection and readback coverage.
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh produces graph TSV inputs.
# upstream design ../../documents/tools/render_dependency_manifest_graph.md defines renderer bundle, projection, and Graph IR contracts.
# @dependency-end

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDER_GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "render_dependency_manifest_graph.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import visualization_contract as contract  # noqa: E402
from render_dependency_manifest_graph import HTML_SCRIPT, GraphIR  # noqa: E402


def run_renderer(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the renderer CLI and capture text output."""
    return subprocess.run(
        [sys.executable, str(RENDER_GRAPH), *args],
        cwd=cwd or PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_graph(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """Write a dependency graph TSV fixture."""
    path.write_text(
        "direction\tkind\tsource\ttarget\n"
        + "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """Return a file's lowercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle_artifact_hashes(bundle: Path) -> dict[str, str]:
    """Return committed bundle artifact hashes by fixed artifact name."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    return {str(artifact["path"]): str(artifact["sha256"]) for artifact in artifacts}


class RenderDependencyManifestGraphContractTest(unittest.TestCase):
    """Validate TP-01 through TP-04 renderer public behavior."""

    def test_tp01_bundle_transaction_manifest_and_scope_generation(self) -> None:
        """Bundle mode rejects existing targets and commits exactly six deterministic files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checker = root / "tools" / "agent_tools" / "check_dependency_graph.sh"
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "out=''\n"
                "printf '%s\\n' \"$*\" > checker.args\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    --graph-tsv) out=\"$2\"; shift 2 ;;\n"
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "printf 'direction\\tkind\\tsource\\ttarget\\nupstream\\tdesign\\ta.md\\tb.md\\n' > \"$out\"\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            bundle = root / "bundle"

            result = run_renderer(
                "--root",
                str(root),
                "--scope",
                "changed",
                "--bundle-dir",
                str(bundle),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                sorted(path.name for path in bundle.iterdir()),
                [
                    "dependency_graph.dot",
                    "dependency_graph.html",
                    "dependency_graph.ir.json",
                    "dependency_graph.md",
                    "dependency_graph.tsv",
                    "manifest.json",
                ],
            )
            self.assertIn("--changed", (root / "checker.args").read_text(encoding="utf-8"))
            stdout_manifest = json.loads(result.stdout)
            committed_manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(stdout_manifest["schema"], "agent_canon.dependency_graph_bundle.v1")
            self.assertEqual(stdout_manifest["status"], "pass")
            self.assertEqual(stdout_manifest["scope"], "changed")
            self.assertEqual(stdout_manifest["source"]["origin_kind"], "generated")
            self.assertEqual(
                stdout_manifest["source"]["origin_locator"],
                "tools/agent_tools/check_dependency_graph.sh#graph-tsv",
            )
            self.assertEqual(stdout_manifest["source"]["root"], root.resolve().as_posix())
            self.assertEqual(stdout_manifest["checker"]["status"], "pass")
            self.assertEqual(stdout_manifest["summary"]["node_count"], 2)
            self.assertEqual(stdout_manifest["summary"]["edge_count"], 1)
            universe = stdout_manifest["visualization_source_universe"]
            self.assertEqual(len(universe["items"]), 6)
            self.assertEqual(
                {item["origin"] for item in universe["items"]},
                {"literal_request", "dependency_closure"},
            )
            calls = stdout_manifest["visualization_tool_calls"]
            self.assertEqual(
                [(call["tool_id"], call["argument_schema"]) for call in calls],
                [
                    (
                        "agent_canon.visualization.coverage",
                        "agent_canon.visualization.arguments.coverage.v1",
                    ),
                    (
                        "agent_canon.visualization.adapter.dependency_manifest",
                        "agent_canon.visualization.arguments.dependency_manifest.v1",
                    ),
                ],
            )
            coverage = stdout_manifest["visualization_coverage"]
            self.assertEqual(
                set(coverage),
                {
                    "dependency_graph.ir.json",
                    "dependency_graph.md",
                    "dependency_graph.dot",
                    "dependency_graph.html",
                },
            )
            for artifact_coverage in coverage.values():
                report = artifact_coverage["report"]
                self.assertEqual(report["status"], "pass")
                self.assertEqual(set(report["source_counts"]), {
                    "identity", "edge", "field", "phase", "branch", "module", "evidence", "time"
                })
                self.assertEqual(report["source_counts"]["identity"], 2)
                self.assertEqual(report["source_counts"]["edge"], 3)
                self.assertEqual(report["source_counts"]["module"], 1)
                self.assertEqual(report["source_counts"], report["rendered_counts"])
                self.assertEqual(report["source_counts"], report["readback_counts"])
                self.assertEqual(report["violations"], [])
                self.assertEqual(len(report["coverage_digest"]), 64)
                self.assertEqual(artifact_coverage["readback"]["status"], "pass")
            ir_payload = json.loads(
                (bundle / "dependency_graph.ir.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                ir_payload["visualization_coverage"]["marker"].startswith(
                    "agent_canon_visualization_coverage_v1:"
                )
            )
            directory_ids = {
                node["id"] for node in ir_payload["nodes"] if node["kind"] == "directory"
            }
            containment_ids = {
                edge["id"]
                for edge in ir_payload["edges"]
                if edge["relation"] == "contains"
            }
            universe_directory_ids = {
                item["item_id"] for item in universe["items"] if item["kind"] == "module"
            }
            derived_edge_ids = {
                item["item_id"]
                for item in universe["items"]
                if json.loads(item["payload_json"]).get("provenance_kind")
                == "derived_directory_containment"
                and item["kind"] == "edge"
            }
            self.assertEqual(universe_directory_ids, directory_ids)
            self.assertEqual(derived_edge_ids, containment_ids)
            universe_ids = {item["item_id"] for item in universe["items"]}
            for artifact_coverage in coverage.values():
                self.assertEqual(
                    {
                        entry["source_item_id"]
                        for entry in artifact_coverage["manifest"]["entries"]
                    },
                    universe_ids,
                )
            markdown = (bundle / "dependency_graph.md").read_text(encoding="utf-8")
            self.assertIn("agent_canon_visualization_coverage_v1:", markdown)
            self.assertIn("-->\n```mermaid", markdown)
            self.assertEqual(markdown.count("```mermaid"), 1)
            self.assertTrue(
                (bundle / "dependency_graph.dot")
                .read_text(encoding="utf-8")
                .startswith("// agent_canon_visualization_coverage_v1:")
            )
            rendered_html = (bundle / "dependency_graph.html").read_text(encoding="utf-8")
            self.assertIn('id="agent-canon-visualization-coverage"', rendered_html)
            self.assertFalse((bundle / "dependency_graph.coverage.json").exists())
            self.assertEqual(stdout_manifest["manifest_sha256"], sha256_file(bundle / "manifest.json"))
            self.assertEqual(
                {artifact["path"] for artifact in committed_manifest["artifacts"]},
                {
                    "dependency_graph.tsv",
                    "dependency_graph.ir.json",
                    "dependency_graph.md",
                    "dependency_graph.dot",
                    "dependency_graph.html",
                },
            )
            for artifact in committed_manifest["artifacts"]:
                artifact_path = bundle / str(artifact["path"])
                self.assertEqual(artifact["bytes"], artifact_path.stat().st_size)
                self.assertEqual(artifact["sha256"], sha256_file(artifact_path))

            reject = run_renderer("--root", str(root), "--bundle-dir", str(bundle), "--format", "json")
            self.assertEqual(reject.returncode, 2)
            self.assertEqual(reject.stdout, "")
            self.assertIn("bundle target already exists", reject.stderr)

    def test_tp01_supplied_tsv_is_copied_into_bundle_without_rewrite(self) -> None:
        """Supplied TSV mode copies the source bytes and records not_run checker status."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "source.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            bundle = root / "copied"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(bundle),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((bundle / "dependency_graph.tsv").read_bytes(), graph.read_bytes())
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["origin_kind"], "supplied")
            self.assertEqual(manifest["source"]["origin_locator"], graph.resolve().as_posix())
            self.assertEqual(manifest["checker"]["status"], "not_run")
            self.assertNotIn("dependency_graph.tsv", manifest["visualization_coverage"])

    def test_tp02_projection_envelope_and_cli_mode_rules(self) -> None:
        """Projection mode writes only requested named outputs and returns schema envelopes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            ir_out = root / "nested" / "graph.ir.json"
            html_out = root / "graph.html"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--ir-out",
                str(ir_out),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["schema"], "agent_canon.dependency_graph_projection.v1")
            self.assertEqual(envelope["status"], "pass")
            self.assertEqual(envelope["scope"], "full")
            self.assertEqual(envelope["source"]["origin_kind"], "supplied")
            self.assertEqual(
                [artifact["path"] for artifact in envelope["artifacts"]],
                ["dependency_graph.html", "dependency_graph.ir.json"],
            )
            self.assertTrue(ir_out.exists())
            self.assertTrue(html_out.exists())
            self.assertEqual(
                set(envelope["visualization_coverage"]),
                {"dependency_graph.html", "dependency_graph.ir.json"},
            )
            self.assertEqual(
                [call["tool_id"] for call in envelope["visualization_tool_calls"]],
                [
                    "agent_canon.visualization.coverage",
                    "agent_canon.visualization.adapter.dependency_manifest",
                ],
            )
            for artifact_coverage in envelope["visualization_coverage"].values():
                self.assertEqual(artifact_coverage["report"]["status"], "pass")
                self.assertEqual(artifact_coverage["readback"]["status"], "pass")
            for artifact in envelope["artifacts"]:
                output_path = html_out if artifact["path"] == "dependency_graph.html" else ir_out
                self.assertEqual(artifact["sha256"], sha256_file(output_path))

            missing_output = run_renderer("--root", str(root), "--graph-tsv", str(graph))
            self.assertEqual(missing_output.returncode, 2)
            self.assertEqual(missing_output.stdout, "")
            self.assertIn("requires at least one named output", missing_output.stderr)

            mutually_exclusive = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(root / "bundle"),
                "--ir-out",
                str(root / "x.json"),
            )
            self.assertEqual(mutually_exclusive.returncode, 2)
            self.assertEqual(mutually_exclusive.stdout, "")
            self.assertIn("mutually exclusive", mutually_exclusive.stderr)

            text_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--markdown-out",
                str(root / "graph.md"),
            )
            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            self.assertIn("schema=agent_canon.dependency_graph_projection.v1", text_result.stdout)
            self.assertIn("summary.node_count=2", text_result.stdout)

    def test_regression_projection_rejects_duplicate_resolved_named_outputs(self) -> None:
        """Projection mode rejects aliases resolving to the same output before writing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            (root / "nested").mkdir()
            sentinel = root / "same.out"
            sentinel.write_text("sentinel\n", encoding="utf-8")
            sentinel_hash = sha256_file(sentinel)

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(root / "nested" / ".." / "same.out"),
                "--ir-out",
                str(sentinel),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("--html-out", result.stderr)
            self.assertIn("--ir-out", result.stderr)
            self.assertIn(str(sentinel.resolve()), result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel\n")
            self.assertEqual(sha256_file(sentinel), sentinel_hash)

    def test_regression_projection_rejects_supplied_tsv_output_collision_before_write(self) -> None:
        """Projection output cannot replace the supplied TSV before hashing it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            original_bytes = graph.read_bytes()

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--markdown-out",
                str(root / "nested" / ".." / "graph.tsv"),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("conflicting output path", result.stderr)
            self.assertIn("--graph-tsv", result.stderr)
            self.assertEqual(graph.read_bytes(), original_bytes)
            self.assertEqual(list(root.glob(".graph.tsv.tmp-*")), [])

    def test_tp03_ir_contains_directional_cycles_and_graph_dsl_locators(self) -> None:
        """IR exposes per-direction cycles and source locator fields for nodes and edges."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("a.md", "b.md", "c.md", "d.md"):
                (root / name).write_text(name, encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(
                graph,
                [
                    ("upstream", "design", "a.md", "b.md"),
                    ("upstream", "design", "b.md", "a.md"),
                    ("downstream", "implementation", "c.md", "d.md"),
                    ("downstream", "implementation", "d.md", "c.md"),
                ],
            )
            ir_out = root / "graph.ir.json"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--ir-out",
                str(ir_out),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            ir_payload = cast(
                GraphIR,
                json.loads(ir_out.read_text(encoding="utf-8")),
            )
            self.assertEqual(ir_payload["schema"], "agent_canon.graph_ir.v2")
            self.assertEqual(ir_payload["summary"]["upstreamCycles"], 1)
            self.assertEqual(ir_payload["summary"]["downstreamCycles"], 1)
            self.assertEqual(ir_payload["cycles"]["upstream"], [["a.md", "b.md", "a.md"]])
            self.assertEqual(ir_payload["cycles"]["downstream"], [["c.md", "d.md", "c.md"]])
            repo_node = next(node for node in ir_payload["nodes"] if node["id"] == "a.md")
            self.assertEqual(repo_node["document_id"], "dependency-manifest-graph")
            self.assertEqual(repo_node["source_locator"], "a.md")
            self.assertIn("source_start", repo_node)
            dependency_edge = next(edge for edge in ir_payload["edges"] if edge["id"] == "edge:000000")
            self.assertEqual(dependency_edge["relation"], "upstream")
            self.assertEqual(dependency_edge["source_locator"], "dependency_graph.tsv:2")
            self.assertEqual(dependency_edge["source_start"], 2)
            self.assertEqual(dependency_edge["source_end"], 2)
            markdown = (root / "graph.md")
            markdown_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--markdown-out",
                str(markdown),
            )
            self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
            rendered_markdown = markdown.read_text(encoding="utf-8")
            self.assertIn("## Upstream Directional Topology Diagnostics", rendered_markdown)
            self.assertIn("a.md -> b.md -> a.md", rendered_markdown)
            self.assertIn("## Downstream Directional Topology Diagnostics", rendered_markdown)
            self.assertIn("c.md -> d.md -> c.md", rendered_markdown)

    def test_regression_bundle_artifact_hashes_are_path_stable(self) -> None:
        """Supplied-TSV bundles in different dirs have identical artifact hashes and live locators."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "source.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "nested/b.md")])
            bundle_a = root / "bundle-a"
            bundle_b = root / "bundle-b"

            first = run_renderer("--root", str(root), "--graph-tsv", str(graph), "--bundle-dir", str(bundle_a))
            second = run_renderer("--root", str(root), "--graph-tsv", str(graph), "--bundle-dir", str(bundle_b))

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(bundle_artifact_hashes(bundle_a), bundle_artifact_hashes(bundle_b))
            combined = "\n".join(
                [
                    (bundle_a / "dependency_graph.ir.json").read_text(encoding="utf-8"),
                    (bundle_a / "dependency_graph.html").read_text(encoding="utf-8"),
                    (bundle_a / "manifest.json").read_text(encoding="utf-8"),
                    (bundle_b / "dependency_graph.ir.json").read_text(encoding="utf-8"),
                    (bundle_b / "dependency_graph.html").read_text(encoding="utf-8"),
                    (bundle_b / "manifest.json").read_text(encoding="utf-8"),
                ]
            )
            self.assertNotIn(".staging", combined)
            self.assertIn('"path": "dependency_graph.tsv"', combined)
            self.assertIn("Source graph: <code>dependency_graph.tsv</code>", combined)

    def test_regression_generated_checker_nonzero_aborts_without_bundle(self) -> None:
        """Generated TSV mode preserves checker authority even when a TSV was written."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checker = root / "tools" / "agent_tools" / "check_dependency_graph.sh"
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "out=''\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    --graph-tsv) out=\"$2\"; shift 2 ;;\n"
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "printf 'direction\\tkind\\tsource\\ttarget\\nupstream\\tdesign\\ta.md\\tb.md\\n' > \"$out\"\n"
                "printf 'checker stdout evidence\\n'\n"
                "printf 'checker stderr evidence\\n' >&2\n"
                "exit 7\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            bundle = root / "bundle"

            result = run_renderer("--root", str(root), "--bundle-dir", str(bundle), "--format", "json")

            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout, "")
            self.assertIn("checker stdout evidence", result.stderr)
            self.assertIn("checker stderr evidence", result.stderr)
            self.assertFalse(bundle.exists())

    def test_regression_bundle_fail_on_broken_exits_after_selected_output(self) -> None:
        """Bundle mode respects fail-on-broken after committing and printing the selected format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "missing.md")])
            bundle = root / "bundle"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(bundle),
                "--fail-on-broken",
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue((bundle / "manifest.json").exists())
            self.assertIn("schema=agent_canon.dependency_graph_bundle.v1", result.stdout)
            self.assertIn("summary.broken_target_count=1", result.stdout)
            self.assertIn("manifest.path=", result.stdout)
            self.assertIn("manifest.hash=", result.stdout)

    def test_regression_graph_ir_v2_edges_documents_metadata_diagnostics(self) -> None:
        """Graph IR v1 edges use required endpoints and expose deterministic support collections."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(
                graph,
                [
                    ("upstream", "design", "a.md", "nested/b.md"),
                    ("upstream", "design", "nested/b.md", "a.md"),
                    ("downstream", "implementation", "a.md", "missing.md"),
                ],
            )
            ir_out = root / "graph.ir.json"

            result = run_renderer("--root", str(root), "--graph-tsv", str(graph), "--ir-out", str(ir_out))

            self.assertEqual(result.returncode, 0, result.stderr)
            ir_payload = cast(
                GraphIR,
                json.loads(ir_out.read_text(encoding="utf-8")),
            )
            self.assertIn("documents", ir_payload)
            self.assertIn("metadata", ir_payload)
            self.assertIn("diagnostics", ir_payload)
            self.assertEqual(ir_payload["documents"][0]["created_at"], "unknown")
            self.assertIn({"name": "created_at", "value": "unknown"}, ir_payload["metadata"])
            dependency_edge = next(edge for edge in ir_payload["edges"] if edge["id"] == "edge:000000")
            containment_edge = next(edge for edge in ir_payload["edges"] if edge["id"] == "contains:000000")
            for edge in (dependency_edge, containment_edge):
                self.assertIn("from_node_id", edge)
                self.assertIn("to_node_id", edge)
                self.assertEqual(edge["order_kind"], "none")
                self.assertIn("confidence", edge)
                self.assertIn("payload_json", edge)
                self.assertNotIn("source", edge)
                self.assertNotIn("target", edge)
            self.assertEqual(dependency_edge["payload_json"]["source"], "a.md")
            self.assertEqual(dependency_edge["payload_json"]["target"], "nested/b.md")
            severities = {diagnostic["kind"]: diagnostic["severity"] for diagnostic in ir_payload["diagnostics"]}
            self.assertEqual(severities["directional_topology_cycle"], "info")
            self.assertEqual(severities["broken_target"], "warn")
            cycle_diagnostic = next(
                diagnostic
                for diagnostic in ir_payload["diagnostics"]
                if diagnostic["kind"] == "directional_topology_cycle"
            )
            self.assertIn("directional topology diagnostic", cycle_diagnostic["message"])
            self.assertFalse(cycle_diagnostic["payload_json"]["checker_failure"])

    def test_regression_no_fixed_evidence_caps_and_large_focus_options(self) -> None:
        """High-degree, diagnostic, broken target, and focus evidence is not fixed-count sliced."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            rows = [
                ("upstream", "design", f"node-{index}.md", f"node-{index + 1}.md")
                for index in range(1205)
            ]
            write_graph(graph, rows)
            html_out = root / "graph.html"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            coverage = envelope["visualization_coverage"]["dependency_graph.html"]
            report = coverage["report"]
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["source_counts"]["identity"], 1206)
            self.assertEqual(report["source_counts"]["edge"], 2411)
            self.assertEqual(report["source_counts"]["module"], 1)
            self.assertEqual(report["source_counts"], report["rendered_counts"])
            self.assertEqual(report["source_counts"], report["readback_counts"])
            rendered_html = html_out.read_text(encoding="utf-8")
            self.assertIn("nodeRecords.forEach", rendered_html)
            self.assertIn("Complete node list (1206)", rendered_html)
            self.assertIn("node-1205.md", rendered_html)
            self.assertNotIn("trimVisibleModel", rendered_html)

    def test_regression_bundle_text_and_json_formats(self) -> None:
        """Bundle stdout respects --format for text and JSON envelopes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            text_bundle = root / "text-bundle"
            json_bundle = root / "json-bundle"

            text_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(text_bundle),
            )
            json_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(json_bundle),
                "--format",
                "json",
            )

            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            self.assertIn("schema=agent_canon.dependency_graph_bundle.v1", text_result.stdout)
            self.assertIn("manifest.path=", text_result.stdout)
            self.assertIn("manifest.hash=", text_result.stdout)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(text_result.stdout)
            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            payload = json.loads(json_result.stdout)
            self.assertEqual(payload["schema"], "agent_canon.dependency_graph_bundle.v1")
            self.assertIn("manifest_path", payload)
            self.assertIn("manifest_sha256", payload)

    def test_tp04_html_embeds_complete_ir_and_accessible_static_evidence(self) -> None:
        """HTML is self-contained, accessible, and retains filtering/focus/static evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            rows = [
                ("upstream", "design", f"node-{index}.md", f"node-{index + 1}.md")
                for index in range(505)
            ]
            write_graph(graph, rows)
            html_out = root / "graph.html"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--title",
                "Accessible Dependency Graph",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered_html = html_out.read_text(encoding="utf-8")
            self.assertIn('<script id="graph-data" type="application/json">', rendered_html)
            embedded = rendered_html.split('<script id="graph-data" type="application/json">', 1)[1].split(
                "</script>",
                1,
            )[0]
            ir_payload = json.loads(embedded)
            self.assertEqual(ir_payload["schema"], "agent_canon.graph_ir.v2")
            self.assertEqual(ir_payload["summary"]["nodes"], 506)
            self.assertEqual(ir_payload["summary"]["edges"], 505)
            coverage = json.loads(result.stdout)["visualization_coverage"][
                "dependency_graph.html"
            ]
            report = coverage["report"]
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["source_counts"]["identity"], 506)
            self.assertEqual(report["source_counts"]["edge"], 1011)
            self.assertEqual(report["source_counts"]["module"], 1)
            self.assertEqual(report["source_counts"], report["rendered_counts"])
            self.assertEqual(report["source_counts"], report["readback_counts"])
            self.assertEqual(report["violations"], [])
            self.assertIn('id="direction-filters"', rendered_html)
            self.assertIn('id="focus"', rendered_html)
            self.assertIn('id="inspector-content"', rendered_html)
            self.assertIn('id="static-graph"', rendered_html)
            self.assertIn('aria-live="polite"', rendered_html)
            self.assertIn('role: "button"', rendered_html)
            self.assertIn('"aria-label": `Inspect ${node.id}`', rendered_html)
            self.assertIn('event.key === "Enter" || event.key === " "', rendered_html)
            self.assertIn("<noscript>", rendered_html)
            self.assertIn("Static SVG maps and complete node, edge, and directory tables remain evidence", rendered_html)
            self.assertIn("Complete node list (506)", rendered_html)
            self.assertIn("Complete edge list (505)", rendered_html)
            self.assertIn("node-505.md", rendered_html)

    def test_algorithm_like_full_mapping_fixture_has_no_identity_loss(self) -> None:
        """JIT/HLO, branch, helper, proof, evidence, phase, and time identities survive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "algorithm.tsv"
            identities = [
                "jit-op-entry",
                "hlo-op-dot",
                "branch-accept",
                "helper-line-search",
                "phase-backend-lowering",
                "dtype-fp64-evidence",
                "proof-overlay-descent",
                "timing-iteration-17",
            ]
            write_graph(
                graph,
                [
                    ("downstream", "implementation", source, target)
                    for source, target in zip(identities, identities[1:])
                ],
            )
            html_out = root / "algorithm.html"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            coverage = json.loads(result.stdout)["visualization_coverage"][
                "dependency_graph.html"
            ]
            report = coverage["report"]
            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                sum(report["source_counts"].values()),
                len(identities) + len(identities) - 1 + 1 + len(identities),
            )
            self.assertEqual(report["source_counts"], report["readback_counts"])
            rendered_html = html_out.read_text(encoding="utf-8")
            for identity in identities:
                self.assertIn(identity, rendered_html)

    def test_issue694_html_readback_uses_visible_nested_records_and_ir_order(self) -> None:
        """Visible deletion/decoys fail while nested IR and input-order joins remain exact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for path in ("root.md", "a/b/c.md", "a/b/deep/d.py"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(path, encoding="utf-8")
            graph = root / "graph.tsv"
            rows = [
                ("downstream", "implementation", "a/b/deep/d.py", "root.md"),
                ("upstream", "design", "root.md", "a/b/c.md"),
            ]
            write_graph(graph, rows)
            html_out = root / "graph.html"
            result = run_renderer(
                "--root", str(root), "--graph-tsv", str(graph),
                "--html-out", str(html_out), "--format", "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            coverage = envelope["visualization_coverage"]["dependency_graph.html"]
            self.assertEqual(coverage["report"]["status"], "pass")
            rendered = html_out.read_text(encoding="utf-8")
            embedded = rendered.split(
                '<script id="graph-data" type="application/json">', 1
            )[1].split("</script>", 1)[0]
            ir = json.loads(embedded)
            universe = envelope["visualization_source_universe"]
            universe_ids = {item["item_id"] for item in universe["items"]}
            ir_node_ids = {node["id"] for node in ir["nodes"]}
            ir_edge_ids = {edge["id"] for edge in ir["edges"]}
            self.assertTrue({"dir:.", "dir:a", "dir:a/b", "dir:a/b/deep"} <= ir_node_ids)
            self.assertTrue(
                {item_id for item_id in universe_ids if item_id.startswith("dir:")} <= ir_node_ids
            )
            self.assertTrue(
                {item_id for item_id in universe_ids if item_id.startswith("contains:")} <= ir_edge_ids
            )
            for item in universe["items"]:
                if item["item_id"].startswith("edge:") and item["item_id"].split(":", 2)[1].isdigit():
                    ordinal = int(item["item_id"].split(":", 2)[1])
                    edge = next(edge for edge in ir["edges"] if edge["id"] == f"edge:{ordinal:06d}")
                    payload = json.loads(item["payload_json"])
                    self.assertEqual(edge["payload_json"]["direction"], payload["direction"])
                    self.assertEqual(edge["payload_json"]["kind"], payload["kind"])
                    self.assertEqual(edge["payload_json"]["source"], payload["source"])
                    self.assertEqual(edge["payload_json"]["target"], payload["target"])
                    self.assertEqual(edge["payload_json"]["row"], ordinal)

            def readback(value: str) -> contract.ReadbackProjection:
                return contract.readback_projection(
                    value, "html", artifact_id="dependency_graph.html",
                    renderer_id="dependency-manifest-graph",
                )

            without_svg = re.sub(
                r'<svg id="static-graph".*?</svg>', "", rendered, count=1, flags=re.S
            )
            deleted = readback(without_svg)
            self.assertEqual(deleted["status"], "fail")
            self.assertIn("visible_surface_missing", {v["code"] for v in deleted["violations"]})
            with_hidden_decoy = rendered.replace(
                "</body>",
                '<div hidden data-agent-canon-source-id="node:decoy">node:decoy</div></body>',
            )
            self.assertEqual(readback(with_hidden_decoy)["status"], "pass")
            without_nodes = re.sub(
                r'<table id="node-table".*?</table>', "", rendered, count=1, flags=re.S
            )
            missing_table = readback(without_nodes)
            self.assertEqual(missing_table["status"], "fail")
            self.assertIn("visible_surface_missing", {v["code"] for v in missing_table["violations"]})

    def test_issue694_html_resource_graph_is_context_sensitive(self) -> None:
        """Resource-bearing contexts fail offline while graph text and strings remain data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "https://text.example", "node.md")])
            (root / "node.md").write_text("node", encoding="utf-8")
            output = root / "graph.html"
            result = run_renderer(
                "--root", str(root), "--graph-tsv", str(graph),
                "--html-out", str(output), "--format", "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")

            def readback(value: str) -> contract.ReadbackProjection:
                return contract.readback_projection(
                    value, "html", artifact_id="dependency_graph.html",
                    renderer_id="dependency-manifest-graph",
                )

            text_only = rendered.replace(
                "</body>",
                "<p>https://text.example fetch( XMLHttpRequest import(</p></body>",
            )
            self.assertEqual(readback(text_only)["status"], "pass")
            html_resource = rendered.replace(
                "</head>", '<link rel="stylesheet" href="https://example.invalid/x.css"></head>',
            )
            self.assertIn("external_resource", {v["code"] for v in readback(html_resource)["violations"]})
            css_resource = rendered.replace(
                "</head>", "<style>.x { background: url(https://example.invalid/x.png) }</style></head>",
            )
            self.assertIn("external_resource", {v["code"] for v in readback(css_resource)["violations"]})
            js_string = rendered.replace(
                "</body>", '<script>const label = "fetch(https://example.invalid)";</script></body>',
            )
            self.assertEqual(readback(js_string)["status"], "pass")
            js_api = rendered.replace(
                "</body>", '<script>fetch("https://example.invalid");</script></body>',
            )
            self.assertIn("script_network_api", {v["code"] for v in readback(js_api)["violations"]})

    def test_issue694_html_visible_payload_and_graph_ir_duplicates_fail_closed(self) -> None:
        """Exact visible fields, duplicate IR records, and edge endpoints are authoritative."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(
                graph,
                [
                    ("upstream", "design", "a.md", "a/b.md"),
                    ("downstream", "implementation", "a/b.md", "a.md"),
                ],
            )
            (root / "a.md").write_text("a", encoding="utf-8")
            (root / "a").mkdir()
            (root / "a" / "b.md").write_text("b", encoding="utf-8")
            output = root / "graph.html"
            result = run_renderer(
                "--root", str(root), "--graph-tsv", str(graph),
                "--html-out", str(output), "--format", "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = output.read_text(encoding="utf-8")
            data_start = '<script id="graph-data" type="application/json">'
            embedded = rendered.split(data_start, 1)[1].split("</script>", 1)[0]

            def readback(value: str) -> contract.ReadbackProjection:
                return contract.readback_projection(
                    value, "html", artifact_id="dependency_graph.html",
                    renderer_id="dependency-manifest-graph",
                )

            exact_field = rendered.replace(
                '<tr data-agent-canon-source-id="node:a.md"><td>root</td><td><code>a.md</code></td><td><code>root</code></td><td><code>a.md</code></td>',
                '<tr data-agent-canon-source-id="node:a.md"><td>root</td><td><code>a.md</code></td><td><code>root</code></td><td><code>a.md2</code></td>',
                1,
            )
            exact_failure = readback(exact_field)
            self.assertEqual(exact_failure["status"], "fail")
            self.assertIn(
                "ir_surface_mismatch",
                {violation["code"] for violation in exact_failure["violations"]},
            )

            ir = json.loads(embedded)

            def with_ir(mutator: object) -> str:
                changed = json.loads(embedded)
                mutator(changed)
                return rendered.replace(embedded, json.dumps(changed, ensure_ascii=False), 1)

            duplicate_mutators = {
                "native node": lambda value: value["nodes"].append(value["nodes"][0]),
                "directory node": lambda value: value["nodes"].append(
                    next(node for node in value["nodes"] if node["kind"] == "directory")
                ),
                "dependency edge": lambda value: value["edges"].append(
                    next(edge for edge in value["edges"] if edge["relation"] != "contains")
                ),
                "containment edge": lambda value: value["edges"].append(
                    next(edge for edge in value["edges"] if edge["relation"] == "contains")
                ),
            }
            self.assertTrue(ir["nodes"])
            for label, mutator in duplicate_mutators.items():
                with self.subTest(label=label):
                    duplicate = readback(with_ir(mutator))
                    self.assertEqual(duplicate["status"], "fail")
                    self.assertIn(
                        "ir_surface_mismatch",
                        {violation["code"] for violation in duplicate["violations"]},
                    )

            def swap_dependency_endpoints(value: dict[str, object]) -> None:
                edge = next(edge for edge in value["edges"] if edge["relation"] != "contains")
                edge["from_node_id"], edge["to_node_id"] = edge["to_node_id"], edge["from_node_id"]

            endpoint_failure = readback(with_ir(swap_dependency_endpoints))
            self.assertEqual(endpoint_failure["status"], "fail")
            self.assertIn(
                "ir_surface_mismatch",
                {violation["code"] for violation in endpoint_failure["violations"]},
            )

    def test_issue694_node_vm_model_region_preserves_filter_semantics(self) -> None:
        """The exact inline model region executes offline for default/query/focus/filter states."""
        model = HTML_SCRIPT.split("/* AGENT_CANON_MODEL_BEGIN */", 1)[1].split(
            "/* AGENT_CANON_MODEL_END */", 1
        )[0]
        nodes = [{"id": f"node-{index:04d}.md", "group": "root"} for index in range(2048)]
        edges = [
            {"direction": "upstream", "kind": "design", "source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
            for index in range(2047)
        ]
        harness = f"""
const vm = require('vm');
const DATA = {json.dumps({'nodes': nodes, 'edges': edges, 'directions': ['upstream'], 'kinds': ['design']})};
const nodeRecords = DATA.nodes.map((node) => ({{...node, search: node.id.toLowerCase()}}));
const edgeRecords = DATA.edges.map((edge, index) => ({{...edge, index, sourceSearch: edge.source.toLowerCase(), targetSearch: edge.target.toLowerCase()}}));
const byId = new Map(nodeRecords.map((node) => [node.id, node]));
const state = {{query: '', focus: '', depth: 1, directions: new Set(DATA.directions), kinds: new Set(DATA.kinds)}};
function addListValue(map, key, value) {{ if (!map.has(key)) map.set(key, []); map.get(key).push(value); }}
{model}
function check(actual, expected, name) {{ if (actual !== expected) throw new Error(name + ': ' + actual + ' != ' + expected); }}
let result = visibleModel(); check(result.nodes.length, 2048, 'default nodes'); check(result.edges.length, 2047, 'default edges');
state.query = 'node-0001'; result = visibleModel(); check(result.edges.length, 2, 'query edges'); check(result.nodes.length, 3, 'query nodes');
state.query = ''; state.focus = 'node-1000.md'; state.depth = 0; result = visibleModel(); check(result.nodes.length, 1, 'focus depth 0 nodes'); check(result.edges.length, 0, 'focus depth 0 edges');
state.depth = 1; result = visibleModel(); check(result.nodes.length, 3, 'focus depth 1 nodes'); check(result.edges.length, 2, 'focus depth 1 edges');
state.focus = ''; state.directions.clear(); result = visibleModel(); check(result.nodes.length, 2048, 'filter retains isolated nodes'); check(result.edges.length, 0, 'filter edges');
state.query = 'no-match'; result = visibleModel(); check(result.nodes.length, 0, 'empty query nodes'); check(result.edges.length, 0, 'empty query edges');
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as script:
            script.write(harness)
            script.flush()
            result = subprocess.run(["node", script.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
