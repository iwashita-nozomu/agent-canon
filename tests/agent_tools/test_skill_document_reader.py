"""Focused tests for bounded Skill document reads."""

# @dependency-start
# contract test
# responsibility Tests bounded UTF-8-safe Skill section reading and read admission.
# upstream implementation ../../tools/agent_tools/skill_document_reader.py owns the reader
# upstream design ../../agents/skills/agent-orchestration.md owns implementation-read admission
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.agent_tools.skill_document_reader import (
    SkillDocumentError,
    SkillDocumentReader,
    admit_implementation_read,
    implementation_read_state,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
READER = PROJECT_ROOT / "tools" / "agent_tools" / "skill_document_reader.py"


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


if __name__ == "__main__":
    unittest.main()
