"""Focused tests for bounded Skill document reads."""

# @dependency-start
# contract test
# responsibility Tests bounded UTF-8-safe Skill section reading and read admission.
# upstream implementation ../../tools/agent/skills/skill_document_reader.py owns the reader
# upstream design ../../agents/skills/agent-orchestration.md owns implementation-read admission
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.agent.skills.skill_document_reader import (
    SkillDocumentError,
    SkillDocumentReader,
    admit_implementation_read,
    implementation_read_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
READER = PROJECT_ROOT / "tools" / "agent" / "skills" / "skill_document_reader.py"


class SkillDocumentReaderTest(unittest.TestCase):
    """Cover the bounded reader's observable contract."""

    def write_document(self, root: Path, text: str) -> Path:
        """Write one UTF-8 Markdown fixture."""
        path = root / "skill.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_index_ignores_fenced_headings_and_computes_section_end(self) -> None:
        """Only real headings define sections, including nested heading scope."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(
                Path(temporary),
                "# Intro\n```text\n## hidden\n```\n## Details\nbody\n### Nested\nchild\n## End\nend\n",
            )

            reader = SkillDocumentReader(path)
            headings = reader.index()

            self.assertEqual([item.heading for item in headings], ["# Intro", "## Details", "### Nested", "## End"])
            self.assertEqual(headings[1].section_end, headings[3].byte_start)
            self.assertEqual(headings[2].section_end, headings[3].byte_start)

    def test_section_chunks_are_bounded_and_continue_to_section_eof(self) -> None:
        """A section can be consumed with next_offset until section EOF."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "## Details\n0123456789\nabcdefghij\n## End\n")
            reader = SkillDocumentReader(path)

            chunks = reader.read_section("## Details", max_bytes=9)

            self.assertGreater(len(chunks), 2)
            self.assertFalse(chunks[0].section_eof)
            self.assertTrue(chunks[-1].section_eof)
            self.assertEqual(chunks[-1].file_eof, False)
            self.assertEqual(
                b"".join(chunk.text.encode("utf-8") for chunk in chunks),
                b"## Details\n0123456789\nabcdefghij\n",
            )
            self.assertEqual(
                [chunk.next_offset for chunk in chunks[:-1]],
                [chunk.byte_start for chunk in chunks[1:]],
            )

    def test_utf8_boundary_never_splits_multibyte_character(self) -> None:
        """A byte limit ending inside UTF-8 backs off to a character boundary."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "## 詳細\nあいうえお\n")
            reader = SkillDocumentReader(path)
            heading = reader.find_heading("詳細")

            chunk = reader.chunk(heading=heading.heading, max_bytes=heading.byte_end - heading.byte_start + 2)

            self.assertLessEqual(chunk.byte_end - chunk.byte_start, heading.byte_end - heading.byte_start + 2)
            self.assertEqual(chunk.text.encode("utf-8"), reader.data[chunk.byte_start : chunk.byte_end])
            self.assertEqual(reader.data[chunk.byte_start : chunk.byte_end].decode("utf-8"), chunk.text)

    def test_file_eof_is_distinct_from_section_eof(self) -> None:
        """The final section reaches both EOF flags; an earlier one does not."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "## First\none\n## Last\n最後\n")
            reader = SkillDocumentReader(path)

            first = reader.read_section("First", max_bytes=100)[-1]
            last = reader.read_section("Last", max_bytes=100)[-1]

            self.assertTrue(first.section_eof)
            self.assertFalse(first.file_eof)
            self.assertTrue(last.section_eof)
            self.assertTrue(last.file_eof)

    def test_missing_heading_is_typed_failure(self) -> None:
        """Unknown owner sections cannot be treated as read."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "# Skill\n")

            with self.assertRaisesRegex(SkillDocumentError, "heading_not_found"):
                SkillDocumentReader(path).read_section("Missing")

    def test_admission_requires_compact_file_eof_and_owner_section_eof(self) -> None:
        """Compact shim and delegated owner section use separate EOF conditions."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compact = self.write_document(root, "# Compact\nshort\n")
            owner = root / "owner.md"
            owner.write_text("# Owner\n## Operation\nbody\n## Other\n", encoding="utf-8")

            result = admit_implementation_read(
                compact,
                ((owner, "Operation"),),
                max_bytes=8,
            )

            self.assertEqual(result.implementation_read, "ready")
            self.assertTrue(result.compact_file_eof)
            self.assertTrue(result.owner_sections[0].section_eof)

    def test_truncated_read_stays_locked(self) -> None:
        """A visible prefix cannot be promoted to implementation readiness."""
        self.assertEqual(implementation_read_state(False, ()), "locked")
        self.assertEqual(implementation_read_state(True, (False,)), "locked")

    def test_cli_reports_json_chunk_and_missing_heading(self) -> None:
        """The CLI exposes bounded chunks and a stable typed failure prefix."""
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_document(Path(temporary), "## Operation\n日本語\n")
            chunk_result = subprocess.run(
                [sys.executable, str(READER), "chunk", "--path", str(path), "--heading", "Operation", "--max-bytes", "10"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(chunk_result.returncode, 0, chunk_result.stderr)
            chunk = json.loads(chunk_result.stdout)
            self.assertIn("next_offset", chunk)
            self.assertIn("section_eof", chunk)
            self.assertIn("file_eof", chunk)

            missing_result = subprocess.run(
                [sys.executable, str(READER), "chunk", "--path", str(path), "--heading", "Missing"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing_result.returncode, 2)
            self.assertIn("SKILL_DOCUMENT_READER_ERROR=heading_not_found", missing_result.stderr)


    def test_admission_projection_keeps_metadata_without_repeating_text(self) -> None:
        """Only the serialized body is removed; all positions and EOF flags survive."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compact = self.write_document(root, "# Compact\nshort\n")
            owner = root / "owner.md"
            sections = ("First", "Second", "Last")
            owner.write_text(
                "".join(f"## {heading}\n" + "本文を再送しない\n" * 400 for heading in sections),
                encoding="utf-8",
            )
            result = admit_implementation_read(
                compact, tuple((owner, heading) for heading in sections)
            )
            expected = []
            for chunk in result.owner_sections:
                entry = chunk.as_json()
                self.assertTrue(entry.pop("text"))
                expected.append(entry)
            projection = result.as_json()
            self.assertEqual(projection["owner_sections"], expected)
            self.assertEqual(projection["implementation_read"], "ready")
            self.assertTrue(projection["compact_file_eof"])
            self.assertEqual([entry["file_eof"] for entry in expected], [False, False, True])

    def test_cli_admit_omits_text_in_json_and_text_formats(self) -> None:
        """Both output formats share the metadata projection, including empty inputs."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner = root / "owner.md"
            owner.write_text("## Operation\nBODY_MUST_NOT_BE_REPEATED\n", encoding="utf-8")
            for compact_text, owners, status in (
                ("# Compact\n", ["--owner", f"{owner}#Operation"], "ready"),
                ("", ["--owner", f"{owner}#Operation"], "locked"),
                ("# Compact\n", [], "ready"),
            ):
                compact = self.write_document(root, compact_text)
                outputs = []
                for output_format in ("json", "text"):
                    with self.subTest(status=status, owners=bool(owners), format=output_format):
                        result = subprocess.run(
                            [sys.executable, str(READER), "admit", "--compact", str(compact),
                             *owners, "--format", output_format],
                            cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        if output_format == "json":
                            payload = json.loads(result.stdout)
                        else:
                            payload = {
                                key: json.loads(value)
                                for key, value in (line.split("=", 1) for line in result.stdout.splitlines())
                            }
                        outputs.append(payload)
                        self.assertEqual(payload["implementation_read"], status)
                        self.assertNotIn("BODY_MUST_NOT_BE_REPEATED", result.stdout)
                        for section in payload["owner_sections"]:
                            self.assertNotIn("text", section)
                            self.assertTrue(section["section_eof"])
                self.assertEqual(outputs[0], outputs[1])

    def test_cli_chunk_preserves_body_in_both_formats(self) -> None:
        """The content route still returns every UTF-8 byte with resumable offsets."""
        with tempfile.TemporaryDirectory() as temporary:
            text = "## Operation\n日本語の本文\nline=value\n"
            path = self.write_document(Path(temporary), text)
            for output_format in ("json", "text"):
                offset = 0
                parts = []
                while True:
                    result = subprocess.run(
                        [sys.executable, str(READER), "chunk", "--path", str(path),
                         "--heading", "Operation", "--offset", str(offset),
                         "--max-bytes", "17", "--format", output_format],
                        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = json.loads(result.stdout) if output_format == "json" else {
                        key: json.loads(value)
                        for key, value in (line.split("=", 1) for line in result.stdout.splitlines())
                    }
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
        """Metadata-only output must not suppress input errors or manufacture readiness."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compact = self.write_document(root, "# Compact\n")
            owner = root / "owner.md"
            for body, heading, limit, error in (
                (b"## Operation\nbody\n", "Missing", "4096", "heading_not_found"),
                (b"## Operation\n## Operation\n", "Operation", "4096", "heading_ambiguous"),
                (b"## Operation\n\xff", "Operation", "4096", "invalid_utf8"),
                ("## Operation\n日本語\n".encode("utf-8"), "Operation", "1", "max_bytes_splits_utf8"),
                (b"## Operation\n", "Operation", "0", "invalid_max_bytes"),
                (None, "Operation", "4096", "read_failed"),
            ):
                with self.subTest(error=error):
                    if body is None:
                        owner.unlink()
                    else:
                        owner.write_bytes(body)
                    result = subprocess.run(
                        [sys.executable, str(READER), "admit", "--compact", str(compact),
                         "--owner", f"{owner}#{heading}", "--max-bytes", limit],
                        cwd=PROJECT_ROOT, check=False, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(f"SKILL_DOCUMENT_READER_ERROR={error}", result.stderr)


if __name__ == "__main__":
    unittest.main()
