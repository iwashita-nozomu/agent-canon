"""Tests for dependency manifest graph report rendering."""

# @dependency-start
# contract test
# responsibility Tests dependency manifest graph report rendering.
# upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT reports.
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh produces graph TSV inputs.
# upstream design ../../documents/tools/render_dependency_manifest_graph.md documents usage.
# @dependency-end

from __future__ import annotations

import importlib.util
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDER_GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "render_dependency_manifest_graph.py"


def load_renderer_module() -> types.ModuleType:
    """Load the renderer script as a module for focused helper tests."""
    spec = importlib.util.spec_from_file_location("render_dependency_manifest_graph_under_test", RENDER_GRAPH)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load renderer module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RenderDependencyManifestGraphTest(unittest.TestCase):
    """Validate graph report rendering."""

    def test_renders_markdown_and_dot_from_tsv(self) -> None:
        """Renderer should summarize cycles and broken targets from TSV."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / "a.md").write_text("a\n", encoding="utf-8")
            (temp_root / "b.md").write_text("b\n", encoding="utf-8")
            graph = temp_root / "graph.tsv"
            graph.write_text(
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\ta.md\tb.md\n"
                "upstream\tdesign\tb.md\ta.md\n"
                "downstream\timplementation\ta.md\tmissing.md\n"
                "upstream\tdesign\ta.md\tunsafe/<script>.md\n",
                encoding="utf-8",
            )
            markdown = temp_root / "graph.md"
            dot = temp_root / "graph.dot"
            html = temp_root / "graph.html"
            graph_ir = temp_root / "graph.ir.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                    "--graph-tsv",
                    str(graph),
                    "--ir-out",
                    str(graph_ir),
                    "--markdown-out",
                    str(markdown),
                    "--dot-out",
                    str(dot),
                    "--html-out",
                    str(html),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH=pass", result.stdout)
            self.assertIn("broken=2", result.stdout)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH_IR=", result.stdout)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH_HTML=", result.stdout)
            ir_payload = json.loads(graph_ir.read_text(encoding="utf-8"))
            self.assertEqual(ir_payload["schema"], "agent_canon.graph_ir.v1")
            self.assertEqual(ir_payload["source"]["kind"], "dependency_manifest_graph_tsv")
            self.assertEqual(ir_payload["summary"]["nodes"], 4)
            self.assertEqual(ir_payload["summary"]["edges"], 4)
            self.assertEqual(ir_payload["summary"]["directoryNodes"], 2)
            self.assertEqual(ir_payload["summary"]["containmentEdges"], 5)
            self.assertEqual(ir_payload["summary"]["totalNodes"], 6)
            self.assertEqual(ir_payload["summary"]["totalEdges"], 9)
            self.assertEqual(ir_payload["views"]["code_territory_map"]["projection"], "group_voronoi")
            self.assertEqual(ir_payload["views"]["dense_group_static_graph"]["node_label"], "display.label")
            missing_node = next(node for node in ir_payload["nodes"] if node["id"] == "missing.md")
            self.assertEqual(missing_node["display"]["label"], "missing.md")
            self.assertEqual(missing_node["payload_json"]["metrics"]["degree"], 1)
            directory_node = next(node for node in ir_payload["nodes"] if node["id"] == "dir:unsafe")
            self.assertEqual(directory_node["kind"], "directory")
            contains_edges = [edge for edge in ir_payload["edges"] if edge["relation"] == "contains"]
            self.assertEqual(len(contains_edges), 5)
            self.assertIn(
                ("dir:unsafe", "unsafe/<script>.md"),
                {(edge["source"], edge["target"]) for edge in contains_edges},
            )
            self.assertEqual(ir_payload["edges"][0]["payload_json"]["row"], 0)
            self.assertIn("a.md -> b.md -> a.md", markdown.read_text(encoding="utf-8"))
            self.assertIn("- directory nodes: 2", markdown.read_text(encoding="utf-8"))
            self.assertIn("- containment edges: 5", markdown.read_text(encoding="utf-8"))
            self.assertIn('"a.md" -> "b.md"', dot.read_text(encoding="utf-8"))
            self.assertNotIn("contains", dot.read_text(encoding="utf-8"))
            rendered_html = html.read_text(encoding="utf-8")
            self.assertIn("Code Space Dependency Graph", rendered_html)
            self.assertIn("Dependency Map", rendered_html)
            self.assertIn("Code Territory Map", rendered_html)
            self.assertIn('class="territory-cell"', rendered_html)
            self.assertIn("Full Graph Map", rendered_html)
            self.assertIn('id="static-zoom"', rendered_html)
            self.assertIn('data-static-zoom="4"', rendered_html)
            self.assertIn('data-base-width=', rendered_html)
            self.assertIn('data-base-height=', rendered_html)
            self.assertIn("setupStaticZoom();", rendered_html)
            self.assertIn("static-graph-content", rendered_html)
            self.assertIn("Complete node list (4)", rendered_html)
            self.assertIn('class="static-node', rendered_html)
            self.assertIn('class="static-edge design"', rendered_html)
            self.assertIn("Complete edge list (4)", rendered_html)
            self.assertIn("Directory containment (2 directories / 5 edges)", rendered_html)
            self.assertIn("<td><code>unsafe</code></td>", rendered_html)
            self.assertIn("Graph controls", rendered_html)
            self.assertIn("Node inspector", rendered_html)
            self.assertIn("unsafe/\\u003cscript\\u003e.md", rendered_html)
            self.assertNotIn("unsafe/<script>.md", rendered_html)
            self.assertIn("MAX_RENDER_NODES = 500", rendered_html)
            self.assertIn("buildAdjacency(edges)", rendered_html)
            self.assertIn("applyScale();", rendered_html)
            self.assertEqual([], list(temp_root.glob("*_zoom_*.html")))

    def test_html_output_is_deterministic_and_escapes_high_risk_payload(self) -> None:
        """HTML payload should be stable and safe for script data embedding."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            payload = 'unsafe/</script>"quote\\slash.md'
            graph = temp_root / "graph.tsv"
            graph.write_text(
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\ta.md\tb.md\n"
                f"upstream\tdesign\ta.md\t{payload}\n",
                encoding="utf-8",
            )
            first = temp_root / "first.html"
            second = temp_root / "second.html"
            command = [
                sys.executable,
                str(RENDER_GRAPH),
                "--root",
                str(temp_root),
                "--graph-tsv",
                str(graph),
                "--html-out",
            ]

            first_result = subprocess.run(
                [*command, str(first)],
                check=False,
                capture_output=True,
                text=True,
            )
            second_result = subprocess.run(
                [*command, str(second)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first_result.returncode, 0, first_result.stderr)
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            first_html = first.read_text(encoding="utf-8")
            second_html = second.read_text(encoding="utf-8")
            self.assertEqual(first_html, second_html)
            self.assertNotIn("unsafe/</script>", first_html)
            self.assertNotIn(payload, first_html)
            self.assertIn("\\u003c/script\\u003e", first_html)

            script_payload = 'unsafe/</script>"quote\\slash\u2028line\u2029end.md'
            script_json = getattr(load_renderer_module(), "script_json")
            encoded = script_json({"path": script_payload})
            self.assertNotIn("unsafe/</script>", encoded)
            self.assertNotIn("\u2028", encoded)
            self.assertNotIn("\u2029", encoded)
            self.assertIn("\\u003c/script\\u003e", encoded)
            self.assertIn("\\u2028", encoded)
            self.assertIn("\\u2029", encoded)

    def test_ir_directory_containment_skips_external_and_anchor_tokens(self) -> None:
        """Directory inference should stay limited to repository path tokens."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / "src" / "app").mkdir(parents=True)
            (temp_root / "src" / "app" / "main.py").write_text("main\n", encoding="utf-8")
            (temp_root / "src" / "app" / "util.py").write_text("util\n", encoding="utf-8")
            graph = temp_root / "graph.tsv"
            graph.write_text(
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\thttp://example.com/x\tsrc/app/main.py\n"
                "upstream\tdesign\t#internal\tsrc/app/main.py\n"
                "upstream\tdesign\tsrc/app/main.py\tsrc/app/util.py\n",
                encoding="utf-8",
            )

            renderer = load_renderer_module()
            report = renderer.build_report(temp_root, renderer.load_edges(graph))
            ir_payload = renderer.graph_ir(report, source_path=graph)
            directory_ids = {node["id"] for node in ir_payload["nodes"] if node["kind"] == "directory"}
            contains_pairs = {
                (edge["source"], edge["target"])
                for edge in ir_payload["edges"]
                if edge["relation"] == "contains"
            }
            payload = renderer.graph_payload(report)

            self.assertEqual(directory_ids, {"dir:.", "dir:src", "dir:src/app"})
            self.assertIn(("dir:src/app", "src/app/main.py"), contains_pairs)
            self.assertIn(("dir:src/app", "src/app/util.py"), contains_pairs)
            self.assertNotIn(("dir:http:", "http://example.com/x"), contains_pairs)
            self.assertNotIn(("dir:.", "#internal"), contains_pairs)
            self.assertEqual(len(contains_pairs), ir_payload["summary"]["containmentEdges"])
            self.assertEqual(payload["summary"]["nodes"], 4)
            self.assertEqual(len(payload["nodes"]), 4)
            self.assertEqual(len(payload["edges"]), 3)
            self.assertTrue(all(not str(node["id"]).startswith("dir:") for node in payload["nodes"]))
            self.assertEqual(len(payload["directoryTree"]["nodes"]), 3)

    def test_html_output_works_with_json_format(self) -> None:
        """JSON stdout should stay parseable when HTML output is requested."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            graph = temp_root / "graph.tsv"
            graph.write_text(
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\ta.md\tb.md\n",
                encoding="utf-8",
            )
            html = temp_root / "graph.html"
            graph_ir = temp_root / "graph.ir.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                    "--graph-tsv",
                    str(graph),
                    "--ir-out",
                    str(graph_ir),
                    "--html-out",
                    str(html),
                    "--title",
                    "Custom Graph",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["nodes"], ["a.md", "b.md"])
            self.assertTrue(html.exists())
            self.assertTrue(graph_ir.exists())
            ir_payload = json.loads(graph_ir.read_text(encoding="utf-8"))
            self.assertEqual(ir_payload["summary"]["nodes"], 2)
            self.assertEqual(ir_payload["summary"]["edges"], 1)
            self.assertEqual(ir_payload["summary"]["directoryNodes"], 1)
            self.assertEqual(ir_payload["summary"]["containmentEdges"], 2)
            self.assertIn("Custom Graph", html.read_text(encoding="utf-8"))
            self.assertNotIn("DEPENDENCY_MANIFEST_GRAPH_HTML=", result.stdout)

    def test_static_workbench_zoom_changes_svg_viewbox_when_playwright_is_available(self) -> None:
        """Browser validation should prove static graph zoom changes SVG scale in place."""
        if not shutil.which("node") or not shutil.which("npm") or not shutil.which("playwright"):
            self.skipTest("Node.js, npm, and Playwright CLI are required for browser validation")
        node_path_result = subprocess.run(
            ["npm", "root", "-g"],
            check=False,
            capture_output=True,
            text=True,
        )
        if node_path_result.returncode != 0:
            self.skipTest(f"could not resolve global npm root: {node_path_result.stderr}")
        node_env = os.environ.copy()
        node_env["NODE_PATH"] = node_path_result.stdout.strip()
        node_env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/usr/local/share/ms-playwright")
        playwright_probe = subprocess.run(
            ["node", "-e", "require('playwright');"],
            check=False,
            capture_output=True,
            text=True,
            env=node_env,
        )
        if playwright_probe.returncode != 0:
            self.skipTest("Playwright package is not importable from Node.js")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / "a.md").write_text("a\n", encoding="utf-8")
            (temp_root / "b.md").write_text("b\n", encoding="utf-8")
            graph = temp_root / "graph.tsv"
            graph.write_text(
                "direction\tkind\tsource\ttarget\n"
                "upstream\tdesign\ta.md\tb.md\n"
                "upstream\tdesign\tb.md\ta.md\n",
                encoding="utf-8",
            )
            html = temp_root / "graph.html"
            render_result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                    "--graph-tsv",
                    str(graph),
                    "--html-out",
                    str(html),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(render_result.returncode, 0, render_result.stderr)

            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(temp_root))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/graph.html"
                browser_script = r"""
const { chromium } = require('playwright');
const url = process.argv[2];
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 820 } });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForSelector('#static-graph .static-node');
  const before = await page.$eval('#static-graph', (svg) => ({
    viewBox: svg.getAttribute('viewBox'),
    nodes: svg.querySelectorAll('.static-node').length,
    edges: svg.querySelectorAll('.static-edge').length,
  }));
  await page.click('[data-static-zoom="4"]');
  await page.waitForTimeout(80);
  const after = await page.$eval('#static-graph', (svg) => ({
    viewBox: svg.getAttribute('viewBox'),
    zoom: document.getElementById('static-zoom').value,
    output: document.getElementById('static-zoom-value').value,
    url: location.href,
  }));
  await browser.close();
  console.log(JSON.stringify({ before, after }));
})();
"""
                browser_result = subprocess.run(
                    ["node", "-", url],
                    input=browser_script,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=node_env,
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
            if browser_result.returncode != 0 and "Executable doesn't exist" in browser_result.stderr:
                self.skipTest("Playwright Chromium browser is not installed")
            self.assertEqual(browser_result.returncode, 0, browser_result.stderr)
            result = json.loads(browser_result.stdout)
            before_box = [float(value) for value in result["before"]["viewBox"].split()]
            after_box = [float(value) for value in result["after"]["viewBox"].split()]
            self.assertEqual(result["before"]["nodes"], 2)
            self.assertEqual(result["before"]["edges"], 2)
            self.assertEqual(result["after"]["zoom"], "4")
            self.assertEqual(result["after"]["output"], "4.0x")
            self.assertEqual(result["after"]["url"], url)
            self.assertLess(after_box[2], before_box[2])
            self.assertLess(after_box[3], before_box[3])

    def test_renders_generated_tsv_even_when_checker_reports_cycle(self) -> None:
        """Renderer should still summarize a checker-generated TSV when graph check fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            checker = temp_root / "tools" / "agent_tools" / "check_dependency_graph.sh"
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "out=\"\"\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    --graph-tsv) out=\"$2\"; shift 2 ;;\n"
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "printf 'direction\\tkind\\tsource\\ttarget\\nupstream\\tdesign\\ta.md\\tb.md\\n' > \"$out\"\n"
                "exit 1\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            (temp_root / "a.md").write_text("a\n", encoding="utf-8")
            (temp_root / "b.md").write_text("b\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH=pass", result.stdout)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH_SOURCE_CHECK=fail returncode=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
