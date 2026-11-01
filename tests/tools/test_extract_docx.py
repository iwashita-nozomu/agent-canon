# @dependency-start
# contract test
# responsibility Tests the native DOCX reference bundle command through its public CLI.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/extract_docx.rs owns DOCX decomposition and bundle output
# upstream implementation ../../tools/bin/agent-canon exposes the stable native command
# downstream design ../../documents/tools/extract_docx.md documents the bundle contract
# @dependency-end

from __future__ import annotations

import hashlib
import json
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def safe_document_xml() -> str:
    """Return the smallest useful Word document body."""
    return """
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


def write_docx(
    path: Path,
    document_xml: str | None = None,
    *,
    extra_members: tuple[str | zipfile.ZipInfo, ...] = (),
) -> None:
    """Write the smallest ZIP/XML document needed by the extractor tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml or safe_document_xml())
        archive.writestr("word/media/image1.emf", b"fake-emf")
        for member in extra_members:
            archive.writestr(member, b"extra")


def sha256(path: Path) -> str:
    """Hash one small test artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_zip_member_name(
    path: Path,
    original_name: str,
    raw_name: bytes,
    *,
    clear_utf8_flag: bool = False,
) -> None:
    """Patch a stored ZIP name without changing either header's byte length."""
    original = original_name.encode("utf-8")
    if len(original) != len(raw_name):
        raise ValueError("raw ZIP test names must preserve the encoded length")
    data = bytearray(path.read_bytes())
    local_count = 0
    offset = 0
    while data[offset : offset + 4] == b"PK\x03\x04":
        name_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
        name_start = offset + 30
        name_end = name_start + name_length
        if data[name_start:name_end] == original:
            data[name_start:name_end] = raw_name
            if clear_utf8_flag:
                flags = struct.unpack_from("<H", data, offset + 6)[0] & ~0x0800
                struct.pack_into("<H", data, offset + 6, flags)
            local_count += 1
        compressed_size = struct.unpack_from("<I", data, offset + 18)[0]
        offset = name_end + extra_length + compressed_size

    central_count = 0
    offset = data.find(b"PK\x01\x02")
    while offset >= 0 and data[offset : offset + 4] == b"PK\x01\x02":
        name_length, extra_length, comment_length = struct.unpack_from(
            "<HHH", data, offset + 28
        )
        name_start = offset + 46
        name_end = name_start + name_length
        if data[name_start:name_end] == original:
            data[name_start:name_end] = raw_name
            if clear_utf8_flag:
                flags = struct.unpack_from("<H", data, offset + 8)[0] & ~0x0800
                struct.pack_into("<H", data, offset + 8, flags)
            central_count += 1
        offset = name_end + extra_length + comment_length
        if data[offset : offset + 4] != b"PK\x01\x02":
            break
    if local_count != 1 or central_count != 1:
        raise AssertionError("expected exactly one local and central ZIP member header")
    path.write_bytes(data)


class ExtractDocxTest(unittest.TestCase):
    """Exercise DOCX extraction and archive safety through the CLI."""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the extractor and capture its output."""
        return subprocess.run(
            [str(AGENT_CANON_CLI), "extract-docx", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_no_staging_paths(self, bundle: Path) -> None:
        """No transaction scratch directory may survive a completed CLI call."""
        self.assertEqual(
            list(bundle.parent.glob(f".{bundle.name}.extract-*")),
            [],
        )

    def test_writes_searchable_text_raw_members_and_verified_manifest(self) -> None:
        """A DOCX becomes a complete bundle whose retained hashes read back."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "発表原稿.docx"
            bundle = root / "bundle"
            write_docx(source)

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 0, result.stderr)
            extracted = (bundle / "extracted.md").read_text(encoding="utf-8")
            self.assertIn("Peak-cut control", extracted)
            self.assertIn("L_t=C_t-x_t", extracted)
            self.assertIn("| school | 60% |", extracted)

            source_copy = bundle / "source" / source.name
            self.assertEqual(source_copy.read_bytes(), source.read_bytes())
            self.assertTrue((bundle / "raw" / "word" / "media" / "image1.emf").is_file())

            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["source"]["name"], source.name)
            self.assertEqual(manifest["source"]["size_bytes"], source_copy.stat().st_size)
            self.assertEqual(manifest["source"]["sha256"], sha256(source_copy))
            self.assertEqual(manifest["outputs"]["extracted_markdown"], "extracted.md")
            for member in manifest["zip_members"]:
                if member["directory"]:
                    continue
                raw = bundle / "raw" / Path(member["name"])
                self.assertEqual(member["size_bytes"], raw.stat().st_size)
                self.assertEqual(member["sha256"], sha256(raw))
            self.assert_no_staging_paths(bundle)

    def test_rejects_unsafe_zip_member_paths_before_output_creation(self) -> None:
        """Traversal, POSIX absolute, and Windows absolute paths fail closed."""
        unsafe_names = ("../escape.txt", "/escape.txt", r"C:\escape.txt")
        for index, unsafe_name in enumerate(unsafe_names):
            with self.subTest(unsafe_name=unsafe_name), tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                source = root / f"unsafe-{index}.docx"
                bundle = root / "bundle"
                write_docx(source, extra_members=(unsafe_name,))

                result = self.run_cli(str(source), "--output-dir", str(bundle))

                self.assertEqual(result.returncode, 1)
                self.assertIn("unsafe ZIP member path", result.stderr)
                self.assertFalse(bundle.exists())
                self.assert_no_staging_paths(bundle)

    def test_rejects_duplicate_normalized_or_portable_member_identity(self) -> None:
        """Slash aliases and case-fold aliases cannot map to the same output."""
        duplicate_names = (r"word\document.xml", "WORD/document.xml")
        for index, duplicate_name in enumerate(duplicate_names):
            with (
                self.subTest(duplicate_name=duplicate_name),
                tempfile.TemporaryDirectory() as tmp_dir,
            ):
                root = Path(tmp_dir)
                source = root / f"duplicate-{index}.docx"
                bundle = root / "bundle"
                write_docx(source, extra_members=(duplicate_name,))

                result = self.run_cli(str(source), "--output-dir", str(bundle))

                self.assertEqual(result.returncode, 1)
                self.assertIn("duplicate ZIP member identity", result.stderr)
                self.assertFalse(bundle.exists())
                self.assert_no_staging_paths(bundle)

    def test_rejects_portable_prefix_aliases(self) -> None:
        """Different spellings cannot create colliding implicit directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "prefix-alias.docx"
            bundle = root / "bundle"
            write_docx(source, extra_members=("Assets/a.bin", "assets/b.bin"))

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicate ZIP path-prefix identity", result.stderr)
            self.assertFalse(bundle.exists())
            self.assert_no_staging_paths(bundle)

    def test_rejects_file_parent_topology_conflict(self) -> None:
        """A file cannot also be a parent directory for another member."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "topology.docx"
            bundle = root / "bundle"
            write_docx(source, extra_members=("conflict", "conflict/child.txt"))

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("ZIP member path topology conflict", result.stderr)
            self.assertFalse(bundle.exists())
            self.assert_no_staging_paths(bundle)

    def test_rejects_advertised_symlink_member(self) -> None:
        """Unix symlink metadata is rejected during archive preflight."""
        link = zipfile.ZipInfo("word/media/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "symlink.docx"
            bundle = root / "bundle"
            write_docx(source, extra_members=(link,))

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("symlink ZIP member is not allowed", result.stderr)
            self.assertFalse(bundle.exists())
            self.assert_no_staging_paths(bundle)

    def test_member_names_use_zip_flags_cp437_and_nul_truncation(self) -> None:
        """Raw ZIP name flags match Python's CP437/UTF-8 selection and NUL cut."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "names.docx"
            bundle = root / "bundle"
            write_docx(
                source,
                extra_members=("assets/x.bin", "assets/é.bin", "assets/nameX.bin"),
            )
            rewrite_zip_member_name(source, "assets/x.bin", b"assets/\x82.bin")
            rewrite_zip_member_name(
                source,
                "assets/é.bin",
                "assets/é.bin".encode("utf-8"),
                clear_utf8_flag=True,
            )
            rewrite_zip_member_name(
                source,
                "assets/nameX.bin",
                b"assets/name\x00.bin",
            )

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            member_names = [member["name"] for member in manifest["zip_members"]]
            self.assertIn("assets/é.bin", member_names)
            self.assertIn("assets/├⌐.bin", member_names)
            self.assertIn("assets/name", member_names)
            self.assertEqual((bundle / "raw" / "assets" / "é.bin").read_bytes(), b"extra")
            self.assertEqual((bundle / "raw" / "assets" / "├⌐.bin").read_bytes(), b"extra")
            self.assertEqual((bundle / "raw" / "assets" / "name").read_bytes(), b"extra")

    def test_rejects_nonempty_output_directory_without_mutation(self) -> None:
        """Existing content is never overwritten implicitly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "input.docx"
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "keep.txt").write_text("keep", encoding="utf-8")
            write_docx(source)

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("output directory is not empty", result.stderr)
            self.assertEqual((bundle / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assert_no_staging_paths(bundle)

    def test_rejects_output_symlink_without_touching_target(self) -> None:
        """The final output component is checked before parent resolution can hide it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "input.docx"
            target = root / "target"
            bundle = root / "bundle"
            target.mkdir()
            write_docx(source)
            try:
                bundle.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("output directory must not be a symlink", result.stderr)
            self.assertEqual(list(target.iterdir()), [])
            self.assertTrue(bundle.is_symlink())
            self.assert_no_staging_paths(bundle)

    def test_invalid_xml_leaves_absent_output_absent(self) -> None:
        """A late projection failure never publishes the staged raw files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "invalid.docx"
            bundle = root / "bundle"
            write_docx(source, document_xml="<w:document")

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertIn("word/document.xml is not valid XML", result.stderr)
            self.assertFalse(bundle.exists())
            self.assert_no_staging_paths(bundle)

    def test_invalid_xml_preserves_preexisting_empty_output(self) -> None:
        """A late failure leaves an admitted empty destination empty."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "invalid.docx"
            bundle = root / "bundle"
            bundle.mkdir()
            write_docx(source, document_xml="<w:document")

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 1)
            self.assertTrue(bundle.is_dir())
            self.assertEqual(list(bundle.iterdir()), [])
            self.assert_no_staging_paths(bundle)

    def test_publishes_over_preexisting_empty_output(self) -> None:
        """A verified bundle replaces an unchanged empty output as one directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "input.docx"
            bundle = root / "bundle"
            bundle.mkdir()
            write_docx(source)

            result = self.run_cli(str(source), "--output-dir", str(bundle))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((bundle / "manifest.json").is_file())
            self.assertTrue((bundle / "source" / source.name).is_file())
            self.assert_no_staging_paths(bundle)

if __name__ == "__main__":
    unittest.main()
