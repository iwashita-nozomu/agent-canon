"""Tests for dependency manifest graph report rendering."""

# @dependency-start
# responsibility Tests dependency manifest graph report rendering.
# upstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py renders Markdown and DOT reports.
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh produces graph TSV inputs.
# downstream design ../../documents/tools/render_dependency_manifest_graph.md documents usage.
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDER_GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "render_dependency_manifest_graph.py"


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
                "downstream\timplementation\ta.md\tmissing.md\n",
                encoding="utf-8",
            )
            markdown = temp_root / "graph.md"
            dot = temp_root / "graph.dot"

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
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DEPENDENCY_MANIFEST_GRAPH=pass", result.stdout)
            self.assertIn("broken=1", result.stdout)
            self.assertIn("a.md -> b.md -> a.md", markdown.read_text(encoding="utf-8"))
            self.assertIn('"a.md" -> "b.md"', dot.read_text(encoding="utf-8"))

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
