"""Tests for dependency manifest graph report rendering."""

# @dependency-start
# responsibility Tests dependency manifest graph report rendering.
# upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT reports.
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh produces graph TSV inputs.
# upstream design ../../documents/tools/render_dependency_manifest_graph.md documents usage.
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
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

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                    "--graph-tsv",
                    str(graph),
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
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH_HTML=", result.stdout)
            self.assertIn("a.md -> b.md -> a.md", markdown.read_text(encoding="utf-8"))
            self.assertIn('"a.md" -> "b.md"', dot.read_text(encoding="utf-8"))
            rendered_html = html.read_text(encoding="utf-8")
            self.assertIn("Code Space Dependency Graph", rendered_html)
            self.assertIn("Graph controls", rendered_html)
            self.assertIn("Node inspector", rendered_html)
            self.assertIn("unsafe/\\u003cscript\\u003e.md", rendered_html)
            self.assertNotIn("unsafe/<script>.md", rendered_html)
            self.assertIn("MAX_RENDER_NODES = 500", rendered_html)
            self.assertIn("buildAdjacency(edges)", rendered_html)
            self.assertIn("applyScale();", rendered_html)

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

            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_GRAPH),
                    "--root",
                    str(temp_root),
                    "--graph-tsv",
                    str(graph),
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
            self.assertIn("Custom Graph", html.read_text(encoding="utf-8"))
            self.assertNotIn("DEPENDENCY_MANIFEST_GRAPH_HTML=", result.stdout)

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
