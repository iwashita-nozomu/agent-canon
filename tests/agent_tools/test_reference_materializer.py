# @dependency-start
# contract test
# responsibility Tests PDF/HTML reference materialization into Markdown.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/reference_materializer.rs converts external references
# upstream design ../../references/README.md defines reference capture policy
# @dependency-end

"""Tests for reference materialization."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", PROJECT_ROOT / "tools/bin/agent-canon")
)


class ReferenceMaterializerTest(unittest.TestCase):
    """Exercise the PDF/HTML reference materializer CLI."""

    def run_cli(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the reference materializer against a temp root."""
        return subprocess.run(
            [str(NATIVE_CLI), "reference-materializer", "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )

    def test_html_reference_is_written_as_markdown(self) -> None:
        """HTML input should produce a references Markdown file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(
                ["git", "init", "-q", "-b", "main", str(root)],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/parent.git",
                ],
                check=True,
            )
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
                env={"AGENT_CANON_PARENT_ROOT": str(root)},
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REFERENCE_MATERIALIZE=pass", result.stdout)
            path_line = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("REFERENCE_MATERIALIZE_PATH=")
            )
            output = root / path_line.partition("=")[2]
            text = output.read_text(encoding="utf-8")
            self.assertIn("@dependency-start", text)
            self.assertIn("source_url: https://example.com/reference.html", text)
            self.assertIn("source_kind: html", text)
            self.assertIn("Visible Heading", text)
            self.assertIn("Visible body text.", text)
            self.assertNotIn("hidden()", text)

    def test_pdf_literal_text_scanner_is_not_used(self) -> None:
        """PDF input should fail when configured extractors cannot read the source."""
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

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REFERENCE_MATERIALIZE=fail", result.stdout)
            self.assertRegex(
                result.stderr,
                r"REFERENCE_MATERIALIZE_ERROR=pdf-text-(?:extractor-required|extraction-failed)",
            )
            self.assertFalse((root / "references").exists())

    def test_existing_output_and_symlink_target_are_preserved(self) -> None:
        """No-force preserves a reference; force preserves a target outside the parent."""
        with (
            tempfile.TemporaryDirectory() as temporary,
            tempfile.TemporaryDirectory() as outside,
        ):
            root = Path(temporary).resolve()
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/parent.git",
                ],
                check=True,
            )
            source = root / "source.html"
            source.write_text(
                "<title>Reference</title><p>First body</p>", encoding="utf-8"
            )
            args = (
                "--url=https://example.com/reference",
                "--inp",
                str(source),
                "--format=json",
            )
            environment = {"AGENT_CANON_PARENT_ROOT": str(root)}
            first = self.run_cli(root, *args, env=environment)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            output = root / json.loads(first.stdout)["path"]
            before = output.read_bytes()
            source.write_text(
                "<title>Reference</title><p>Second body</p>", encoding="utf-8"
            )
            second = self.run_cli(root, *args, env=environment)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(output.read_bytes(), before)
            target = Path(outside) / "foreign.md"
            target.write_text("foreign", encoding="utf-8")
            output.unlink()
            output.symlink_to(target)
            forced = self.run_cli(root, *args, "--force", env=environment)
            self.assertNotEqual(forced.returncode, 0, forced.stdout + forced.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "foreign")

    def test_missing_parent_authority_keeps_output_absent(self) -> None:
        """Valid extraction alone grants no source write authority."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source.html"
            source.write_text("<title>Reference</title><p>Body</p>", encoding="utf-8")
            result = self.run_cli(
                root,
                "--url",
                "https://example.com/",
                "--input",
                str(source),
                env={"AGENT_CANON_PARENT_ROOT": ""},
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / "references").exists())

    def test_required_and_choice_arguments_keep_usage_exit_code(self) -> None:
        """Argparse-compatible input failures use exit code two."""
        for args in [
            (),
            ("--url", "x", "--source-kind", "invalid"),
            ("--url", "x", "--force=yes"),
        ]:
            with self.subTest(args=args):
                result = self.run_cli(PROJECT_ROOT, *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_fetch_reads_the_url_when_input_is_omitted(self) -> None:
        """The explicit fetch input reaches the same extraction and publication API."""
        content = b"<title>Fetched reference</title><p>Downloaded body</p>"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, format: str, *args: object) -> None:
                pass

        with (
            tempfile.TemporaryDirectory() as temporary,
            ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server,
        ):
            root = Path(temporary).resolve()
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/parent.git",
                ],
                check=True,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = self.run_cli(
                    root,
                    "--url",
                    f"http://127.0.0.1:{server.server_port}/reference.html",
                    "--fetch",
                    "--format",
                    "json",
                    env={"AGENT_CANON_PARENT_ROOT": str(root)},
                )
            finally:
                server.shutdown()
                thread.join()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = root / json.loads(result.stdout)["path"]
            self.assertIn("Downloaded body", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
