"""Focused CLI tests for bounded Skill document reads."""

# @dependency-start
# contract test
# responsibility Tests bounded UTF-8-safe Skill section reading and read admission.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/skill_document_reader.rs owns the reader
# upstream design ../../agents/skills/agent-orchestration.md owns implementation-read admission
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class SkillDocumentReaderCliTest(unittest.TestCase):
    """Cover the registered native reader command's observable contract."""

    def write_document(self, root: Path, text: str) -> Path:
        """Write one UTF-8 Markdown fixture."""
        path = root / "skill.md"
        path.write_text(text, encoding="utf-8")
        return path

    def run_reader(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the current native executable through its registered command."""
        self.assertIsNotNone(
            AGENT_CANON_CLI,
            "AGENT_CANON_CLI must select the current native executable",
        )
        return subprocess.run(
            [str(AGENT_CANON_CLI), "skill-document-reader", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def parse_text_output(output: str) -> dict[str, object]:
        """Decode the JSON values carried by the text format's key-value lines."""
        return {
            key: json.loads(value)
            for key, value in (line.split("=", 1) for line in output.splitlines())
        }

    def test_cli_reports_json_chunk_and_missing_heading(self) -> None:
        """The native command returns bounded chunks and stable typed failures."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "## Operation\n日本語\n")
            chunk_result = self.run_reader(
                "chunk",
                "--path",
                str(path),
                "--heading",
                "Operation",
                "--max-bytes",
                "10",
            )
            self.assertEqual(chunk_result.returncode, 0, chunk_result.stderr)
            chunk = json.loads(chunk_result.stdout)
            self.assertEqual(
                set(chunk),
                {
                    "path",
                    "heading",
                    "line_start",
                    "line_end",
                    "byte_start",
                    "byte_end",
                    "next_offset",
                    "section_eof",
                    "file_eof",
                    "text",
                },
            )
            self.assertEqual(chunk["text"], "## Operati")
            self.assertEqual(chunk["next_offset"], chunk["byte_end"])

            missing_result = self.run_reader(
                "chunk", "--path", str(path), "--heading", "Missing"
            )
            self.assertEqual(missing_result.returncode, 2)
            self.assertEqual(missing_result.stdout, "")
            self.assertEqual(
                missing_result.stderr,
                "SKILL_DOCUMENT_READER_ERROR=heading_not_found:Missing\n",
            )

    def test_cli_admit_omits_text_in_json_and_text_formats(self) -> None:
        """Both formats expose the same metadata projection, including empty inputs."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner = root / "owner.md"
            owner.write_text(
                "## Operation\nBODY_MUST_NOT_BE_REPEATED\n", encoding="utf-8"
            )
            for owners, status in (
                (["--owner", f"{owner}#Operation"], "ready"),
                ([], "locked"),
            ):
                outputs = []
                for output_format in ("json", "text"):
                    with self.subTest(
                        status=status, owners=bool(owners), format=output_format
                    ):
                        result = self.run_reader(
                            "admit", *owners, "--format", output_format
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        payload = (
                            json.loads(result.stdout)
                            if output_format == "json"
                            else self.parse_text_output(result.stdout)
                        )
                        outputs.append(payload)
                        self.assertEqual(payload["implementation_read"], status)
                        self.assertNotIn("BODY_MUST_NOT_BE_REPEATED", result.stdout)
                        for section in payload["owner_sections"]:
                            self.assertNotIn("text", section)
                            self.assertTrue(section["section_eof"])
                self.assertEqual(outputs[0], outputs[1])

    def test_cli_chunk_preserves_body_in_both_formats(self) -> None:
        """Content output preserves every UTF-8 byte with resumable offsets."""
        with tempfile.TemporaryDirectory() as temporary:
            text = "## Operation\n日本語の本文\nline=value\n"
            path = self.write_document(Path(temporary), text)
            for output_format in ("json", "text"):
                offset = 0
                parts = []
                while True:
                    result = self.run_reader(
                        "chunk",
                        "--path",
                        str(path),
                        "--heading",
                        "Operation",
                        "--offset",
                        str(offset),
                        "--max-bytes",
                        "17",
                        "--format",
                        output_format,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = (
                        json.loads(result.stdout)
                        if output_format == "json"
                        else self.parse_text_output(result.stdout)
                    )
                    self.assertEqual(payload["byte_start"], offset)
                    self.assertGreater(payload["next_offset"], offset)
                    self.assertLessEqual(len(payload["text"].encode("utf-8")), 17)
                    parts.append(payload["text"])
                    offset = payload["next_offset"]
                    if payload["section_eof"]:
                        self.assertTrue(payload["file_eof"])
                        break
                self.assertEqual("".join(parts), text)

    def test_cli_admission_failures_do_not_emit_partial_success(self) -> None:
        """Metadata output cannot hide input errors or manufacture readiness."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner = root / "owner.md"
            for body, heading, limit, error in (
                (b"", "Operation", "4096", "heading_not_found"),
                (b"## Operation\nbody\n", "Missing", "4096", "heading_not_found"),
                (
                    b"## Operation\n## Operation\n",
                    "Operation",
                    "4096",
                    "heading_ambiguous",
                ),
                (b"## Operation\n\xff", "Operation", "4096", "invalid_utf8"),
                (
                    "## Operation\n日本語\n".encode("utf-8"),
                    "Operation",
                    "1",
                    "max_bytes_splits_utf8",
                ),
                (b"## Operation\n", "Operation", "0", "invalid_max_bytes"),
                (None, "Operation", "4096", "read_failed"),
            ):
                with self.subTest(error=error):
                    if body is None:
                        owner.unlink(missing_ok=True)
                    else:
                        owner.write_bytes(body)
                    result = self.run_reader(
                        "admit",
                        "--owner",
                        f"{owner}#{heading}",
                        "--max-bytes",
                        limit,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(
                        result.stderr.split("=", 1)[0],
                        "SKILL_DOCUMENT_READER_ERROR",
                    )
                    self.assertIn(f"={error}:", result.stderr)

    def test_cli_index_then_selected_chunk_does_not_emit_branch_bodies(self) -> None:
        """Indexing lists headings while content remains limited to the selection."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(
                Path(temporary),
                "## Common\nconstraints\n### Active\nSELECTED_BODY\n"
                "#### Recovery\nDEFERRED_RECOVERY\n### Other\nDEFERRED_OTHER\n",
            )
            for args, expected in (
                (["index"], None),
                (["chunk", "--heading", "Common"], "## Common\nconstraints\n"),
                (["chunk", "--heading", "Active"], "### Active\nSELECTED_BODY\n"),
            ):
                with self.subTest(args=args):
                    result = self.run_reader(*args, "--path", str(path))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("DEFERRED_RECOVERY", result.stdout)
                    self.assertNotIn("DEFERRED_OTHER", result.stdout)
                    payload = json.loads(result.stdout)
                    if expected is None:
                        self.assertEqual(len(payload), 4)
                        self.assertNotIn("SELECTED_BODY", result.stdout)
                    else:
                        self.assertEqual(payload["text"], expected)
                        self.assertTrue(payload["section_eof"])
                        self.assertFalse(payload["file_eof"])

    def test_legacy_compact_admission_is_not_an_eager_fallback(self) -> None:
        """Removed compact admission is rejected instead of restoring whole-file reads."""
        result = self.run_reader("admit", "--compact", "skill.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
