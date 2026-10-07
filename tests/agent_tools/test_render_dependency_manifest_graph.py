"""Focused native-input/output tests for dependency graph rendering."""

# @dependency-start
# contract test
# responsibility Tests native dependency graph source, labels, relations, and output checks.
# upstream implementation ../../tools/analysis/dependencies/render_dependency_manifest_graph.py renders graph artifacts.
# upstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh produces graph TSV inputs.
# upstream design ../../documents/tools/render_dependency_manifest_graph.md defines renderer bundle and Graph IR contracts.
# @dependency-end

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDER_GRAPH = (
    PROJECT_ROOT
    / "tools"
    / "analysis"
    / "dependencies"
    / "render_dependency_manifest_graph.py"
)


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
    """Write a native dependency graph TSV fixture."""
    path.write_text(
        "direction\tkind\tsource\ttarget\n"
        + "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    """Return a file's lowercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RenderDependencyManifestGraphTest(unittest.TestCase):
    """Validate native graph inputs, labels, relations, and artifact readback."""

    def test_bundle_preserves_native_graph_and_artifact_descriptors(self) -> None:
        """Bundle mode emits all native artifacts and source summaries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checker = root / "tools" / "analysis" / "dependencies" / "check_dependency_graph.sh"
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "out=''\n"
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
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "agent_canon.dependency_graph_bundle.v1")
            self.assertEqual(manifest["status"], "pass")
            self.assertEqual(manifest["summary"]["node_count"], 2)
            self.assertEqual(manifest["summary"]["edge_count"], 1)
            self.assertNotIn("visualization_source_universe", manifest)
            self.assertNotIn("visualization_tool_calls", manifest)
            self.assertNotIn("visualization_coverage", manifest)
            for artifact in manifest["artifacts"]:
                self.assertEqual(
                    artifact["sha256"], sha256_file(bundle / artifact["path"])
                )

            graph_ir = json.loads(
                (bundle / "dependency_graph.ir.json").read_text(encoding="utf-8")
            )
            self.assertEqual(graph_ir["schema"], "agent_canon.graph_ir.v2")
            relations = {(edge["relation"], edge["label"]) for edge in graph_ir["edges"]}
            self.assertIn(("upstream", "design"), relations)
            self.assertIn(("contains", "contains"), relations)

    def test_projection_uses_native_tsv_and_rejects_invalid_mode(self) -> None:
        """Named projection mode keeps native source and output checks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
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
            self.assertEqual(envelope["source"]["origin_kind"], "supplied")
            self.assertEqual(envelope["summary"]["edge_count"], 1)
            self.assertTrue(html_out.exists())
            html_text = html_out.read_text(encoding="utf-8")
            self.assertIn("a.md", html_text)
            self.assertIn("b.md", html_text)

            missing_output = run_renderer("--root", str(root), "--graph-tsv", str(graph))
            self.assertEqual(missing_output.returncode, 2)
            self.assertIn("requires at least one named output", missing_output.stderr)

    def test_projection_rejects_duplicate_resolved_outputs(self) -> None:
        """Projection mode refuses aliases that resolve to one destination."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            (root / "nested").mkdir()
            sentinel = root / "same.out"
            sentinel.write_text("sentinel\n", encoding="utf-8")
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
            self.assertIn("conflicting projection output path", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel\n")


if __name__ == "__main__":
    unittest.main()
