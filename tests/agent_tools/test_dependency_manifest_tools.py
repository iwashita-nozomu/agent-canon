"""Tests for dependency manifest shell tools."""

# @dependency-start
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream implementation ../../tools/agent_tools/scan_dependency_headers.sh scans manifest markers
# upstream implementation ../../tools/agent_tools/check_dependency_header_format.sh format checks
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh graph checks
# @dependency-end

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "scan_dependency_headers.sh"
FORMAT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_header_format.sh"
GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_graph.sh"


def run_tool(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    """Run a dependency manifest shell tool."""
    return subprocess.run(
        ["bash", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class DependencyManifestToolTest(unittest.TestCase):
    """Exercise the dependency manifest shell tools."""

    def test_scan_reports_missing_manifest(self) -> None:
        """The scan tool reports missing markers and can fail on request."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            doc.write_text("# Doc\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(doc),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=doc.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)

    def test_format_accepts_line_comment_manifest(self) -> None:
        """Line-comment manifests are valid for Python-like files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# upstream implementation target.py target contract",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_json_string_manifest(self) -> None:
        """JSON files can keep valid syntax by storing manifest lines as strings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.json"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "{",
                        '  "_dependency_manifest": [',
                        '    "@dependency-start",',
                        '    "upstream implementation target.py target contract",',
                        '    "@dependency-end"',
                        "  ],",
                        '  "ok": true',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_invalid_direction(self) -> None:
        """The format checker rejects unknown directions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# sideways implementation target.py invalid direction",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid direction", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_graph_accepts_bidirectional_edges(self) -> None:
        """Matching upstream/downstream reverse edges pass graph validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# upstream implementation a.py a is consumed by b",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(GRAPH), "--root", str(root), str(a), str(b), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)

    def test_graph_rejects_isolated_manifest(self) -> None:
        """The graph checker rejects manifests that do not connect to any edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(GRAPH), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("isolated dependency manifest", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_missing_reverse_edge(self) -> None:
        """Strict bidirectional mode requires the matching reverse edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text("# no manifest\n", encoding="utf-8")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--check-bidirectional",
                str(a),
                str(b),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing reverse upstream implementation edge", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_upstream_cycles(self) -> None:
        """The graph checker detects cycles in the upstream graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# upstream implementation b.py b is prerequisite",
                        "# downstream implementation b.py b also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# upstream implementation a.py a is prerequisite",
                        "# downstream implementation a.py a also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(GRAPH), "--root", str(root), str(a), str(b), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cycle includes", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)


if __name__ == "__main__":
    unittest.main()
