# @dependency-start
# responsibility Tests PDF/HTML reference materialization into Markdown.
# upstream implementation ../../tools/agent_tools/reference_materializer.py converts external references
# upstream design ../../references/README.md defines reference capture policy
# @dependency-end

"""Tests for reference materialization."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "reference_materializer.py"


class ReferenceMaterializerTest(unittest.TestCase):
    """Exercise the PDF/HTML reference materializer CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the reference materializer against a temp root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_html_reference_is_written_as_markdown(self) -> None:
        """HTML input should produce a references Markdown file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            html_path = root / "source.html"
            html_path.write_text(
                (
                    "<html><head><title>Example Reference</title>"
                    "<script>hidden()</script></head>"
                    "<body><h1>Visible Heading</h1><p>Visible body text.</p></body></html>"
                ),
                encoding="utf-8",
            )

            result = self.run_cli(
                root,
                "--url",
                "https://example.com/reference.html",
                "--input",
                str(html_path),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REFERENCE_MATERIALIZE=pass", result.stdout)
            path_line = next(line for line in result.stdout.splitlines() if line.startswith("REFERENCE_MATERIALIZE_PATH="))
            output = root / path_line.partition("=")[2]
            text = output.read_text(encoding="utf-8")
            self.assertIn("@dependency-start", text)
            self.assertIn("source_url: https://example.com/reference.html", text)
            self.assertIn("source_kind: html", text)
            self.assertIn("Visible Heading", text)
            self.assertIn("Visible body text.", text)
            self.assertNotIn("hidden()", text)

    def test_pdf_literal_text_fallback_is_written_as_markdown(self) -> None:
        """PDF input should keep extracted text in a references Markdown file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf_path = root / "source.pdf"
            pdf_path.write_bytes(
                b"%PDF-1.1\n1 0 obj<<>>stream\nBT (PDF Visible Text) Tj ET\nendstream\nendobj\n%%EOF\n"
            )

            result = self.run_cli(
                root,
                "--url",
                "https://example.com/source.pdf",
                "--input",
                str(pdf_path),
                "--source-kind",
                "pdf",
                "--title",
                "PDF Reference",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REFERENCE_MATERIALIZE_SOURCE_KIND=pdf", result.stdout)
            self.assertIn("REFERENCE_MATERIALIZE=pass", result.stdout)
            path_line = next(line for line in result.stdout.splitlines() if line.startswith("REFERENCE_MATERIALIZE_PATH="))
            output = root / path_line.partition("=")[2]
            text = output.read_text(encoding="utf-8")
            self.assertIn("source_url: https://example.com/source.pdf", text)
            self.assertIn("PDF Visible Text", text)


if __name__ == "__main__":
    unittest.main()
