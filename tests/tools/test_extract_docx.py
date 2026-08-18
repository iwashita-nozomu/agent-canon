# @dependency-start
# contract test
# responsibility Tests the standard-library DOCX reference bundle extractor.
# upstream implementation ../../tools/docs/extract_docx.py owns DOCX decomposition and bundle output
# downstream design ../../documents/tools/extract_docx.md documents the bundle contract
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "extract_docx.py"


def write_docx(path: Path, document_xml: str, *, unsafe_member: str | None = None) -> None:
    """Write the smallest ZIP/XML document needed by the extractor tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/media/image1.emf", b"fake-emf")
        if unsafe_member is not None:
            archive.writestr(unsafe_member, b"unsafe")


class ExtractDocxTest(unittest.TestCase):
    """Exercise DOCX extraction and archive safety through the CLI."""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the extractor and capture its output."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_writes_searchable_text_raw_members_and_manifest(self) -> None:
        """A DOCX becomes a complete, hash-described reference bundle."""
        document_xml = """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <w:body>
            <w:p><w:r><w:t>Peak-cut control</w:t></w:r></w:p>
            <w:p><m:oMath><m:r><m:t>L_t=C_t-x_t</m:t></m:r></m:oMath></w:p>
            <w:tbl>
              <w:tr><w:tc><w:p><w:r><w:t>site</w:t></w:r></w:p></w:tc>
                   <w:tc><w:p><w:r><w:t>reduction</w:t></w:r></w:p></w:tc></w:tr>
              <w:tr><w:tc><w:p><w:r><w:t>school</w:t></w:r></w:p></w:tc>
                   <w:tc><w:p><w:r><w:t>60%</w:t></w:r></w:p></w:tc></w:tr>
            </w:tbl>
          </w:body>
        </w:document>
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "発表原稿.docx"
            bundle = root / "bundle"
            write_docx(source, document_xml)

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 0, result.stderr)
            extracted = (bundle / "extracted.md").read_text(encoding="utf-8")
            self.assertIn("Peak-cut control", extracted)
            self.assertIn("L_t=C_t-x_t", extracted)
            self.assertIn("| school | 60% |", extracted)
            self.assertTrue((bundle / "source" / source.name).is_file())
            self.assertTrue((bundle / "raw" / "word" / "media" / "image1.emf").is_file())

            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["source"]["name"], source.name)
            self.assertEqual(manifest["outputs"]["extracted_markdown"], "extracted.md")
            members = {member["name"] for member in manifest["zip_members"]}
            self.assertIn("word/document.xml", members)
            self.assertIn("word/media/image1.emf", members)

    def test_rejects_unsafe_zip_member(self) -> None:
        """Archive traversal paths are rejected before extraction."""
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>safe</w:t></w:r></w:p></w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "unsafe.docx"
            bundle = root / "bundle"
            write_docx(source, document_xml, unsafe_member="../escape.txt")

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsafe ZIP member path", result.stderr)
            self.assertFalse(bundle.exists())

    def test_rejects_nonempty_output_directory(self) -> None:
        """Existing content is never overwritten implicitly."""
        document_xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>safe</w:t></w:r></w:p></w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "input.docx"
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "keep.txt").write_text("keep", encoding="utf-8")
            write_docx(source, document_xml)

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("output directory is not empty", result.stderr)
            self.assertEqual((bundle / "keep.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
