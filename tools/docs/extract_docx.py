#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Decomposes an authorized DOCX reference into a searchable, auditable bundle.
# upstream design ../README.md shared documentation-tool placement and ownership
# downstream implementation ../../tests/tools/test_extract_docx.py tests the DOCX bundle contract
# downstream design ../../documents/tools/extract_docx.md documents the bundle layout and CLI
# @dependency-end
"""Extract a DOCX file into a searchable and auditable reference bundle.

The extractor deliberately uses only the Python standard library. A bundle
contains a copy of the source document, normalized paragraph/table text, the
raw ZIP members (including media and XML), and a manifest with hashes. It is
intended for local documents for which the caller is authorized to retain and
process the source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Iterable, Sequence
from xml.etree import ElementTree


SCHEMA_VERSION = 1
DOCUMENT_XML_MEMBER = "word/document.xml"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileDigest:
    """Size and SHA-256 read back from one file."""

    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ArchiveMember:
    """One validated ZIP member and its portable extraction identity."""

    info: zipfile.ZipInfo
    name: str
    parts: tuple[str, ...]
    identity_parts: tuple[str, ...]


@dataclass(frozen=True)
class OutputReservation:
    """Observed final-output state that must still hold at publication."""

    path: Path
    existed: bool
    device: int | None = None
    inode: int | None = None


def local_name(tag: str) -> str:
    """Return the namespace-free XML local name."""
    return tag.rsplit("}", 1)[-1]


def portable_part_identity(part: str) -> str:
    """Return a filesystem-portable identity for one archive path component."""
    return unicodedata.normalize("NFC", part).casefold()


def normalized_member_identity(name: str) -> tuple[str, tuple[str, ...]]:
    """Normalize one ZIP path and return its portable duplicate identity."""
    if not name or "\x00" in name:
        raise ValueError(f"unsafe ZIP member path: {name!r}")

    slash_name = name.replace("\\", "/")
    if slash_name.startswith("/") or PureWindowsPath(slash_name).drive:
        raise ValueError(f"unsafe ZIP member path: {name!r}")

    parts: list[str] = []
    for part in slash_name.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError(f"unsafe ZIP member path: {name!r}")
        parts.append(part)

    if not parts:
        raise ValueError(f"unsafe ZIP member path: {name!r}")

    normalized = "/".join(parts)
    if PurePosixPath(normalized).is_absolute():
        raise ValueError(f"unsafe ZIP member path: {name!r}")
    identity = tuple(portable_part_identity(part) for part in parts)
    return normalized, identity


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    """Return whether a ZIP member advertises a Unix symlink mode."""
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def inspect_archive(source: Path) -> list[ArchiveMember]:
    """Validate all archive identities and topology before any member is written."""
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not a readable DOCX ZIP archive: {source}") from exc

    members: list[ArchiveMember] = []
    identities: dict[tuple[str, ...], ArchiveMember] = {}
    prefix_spellings: dict[tuple[str, ...], tuple[str, ...]] = {}
    with archive:
        for info in archive.infolist():
            normalized, identity = normalized_member_identity(info.filename)
            parts = tuple(PurePosixPath(normalized).parts)
            if identity in identities:
                other = identities[identity]
                raise ValueError(
                    "duplicate ZIP member identity: "
                    f"{other.info.filename!r} and {info.filename!r} -> {normalized!r}"
                )
            for depth in range(1, len(identity) + 1):
                identity_prefix = identity[:depth]
                spelling = parts[:depth]
                previous = prefix_spellings.get(identity_prefix)
                if previous is not None and previous != spelling:
                    raise ValueError(
                        "duplicate ZIP path-prefix identity: "
                        f"{'/'.join(previous)!r} and {'/'.join(spelling)!r}"
                    )
                prefix_spellings[identity_prefix] = spelling
            if is_zip_symlink(info):
                raise ValueError(f"symlink ZIP member is not allowed: {info.filename!r}")
            member = ArchiveMember(
                info=info,
                name=normalized,
                parts=parts,
                identity_parts=identity,
            )
            identities[identity] = member
            members.append(member)

    for member in members:
        for depth in range(1, len(member.identity_parts)):
            parent = identities.get(member.identity_parts[:depth])
            if parent is not None and not parent.info.is_dir():
                raise ValueError(
                    "ZIP member path topology conflict: "
                    f"{parent.info.filename!r} is a file parent of {member.info.filename!r}"
                )

    document_identity = tuple(
        portable_part_identity(part)
        for part in PurePosixPath(DOCUMENT_XML_MEMBER).parts
    )
    document_member = identities.get(document_identity)
    if document_member is None or document_member.name != DOCUMENT_XML_MEMBER:
        raise ValueError(f"DOCX is missing {DOCUMENT_XML_MEMBER}")
    if document_member.info.is_dir():
        raise ValueError(f"DOCX member is not a file: {DOCUMENT_XML_MEMBER}")
    return members


def text_from_element(element: ElementTree.Element) -> str:
    """Collect Word and Office Math text while retaining simple breaks."""
    parts: list[str] = []
    for node in element.iter():
        name = local_name(node.tag)
        if name in {"t", "instrText"}:
            parts.append(node.text or "")
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def paragraph_style(paragraph: ElementTree.Element) -> str:
    """Return the optional Word paragraph style identifier."""
    for child in paragraph:
        if local_name(child.tag) != "pPr":
            continue
        for style in child:
            if local_name(style.tag) == "pStyle":
                return style.attrib.get(f"{{{WORD_NAMESPACE}}}val", "")
    return ""


def paragraph_markdown(paragraph: ElementTree.Element) -> str:
    """Render one Word paragraph as plain Markdown text."""
    text = text_from_element(paragraph)
    if not text:
        return ""
    style = paragraph_style(paragraph).lower()
    if "heading" in style or "見出し" in style:
        level = 1
        for character in reversed(style):
            if character.isdigit():
                level = max(1, min(6, int(character)))
                break
        return f"{'#' * level} {text}"
    return text


def table_markdown(table: ElementTree.Element) -> list[str]:
    """Render a Word table as a compact Markdown table."""
    rows: list[list[str]] = []
    for row in table.iter():
        if local_name(row.tag) != "tr":
            continue
        cells = [
            text_from_element(cell).replace("|", "\\|").replace("\n", "<br>")
            for cell in row
            if local_name(cell.tag) == "tc"
        ]
        if cells:
            rows.append(cells)
    if not rows:
        return []
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(padded[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return lines


def extract_markdown(document_xml: bytes, source_name: str) -> str:
    """Convert the main Word document body to searchable Markdown."""
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise ValueError("word/document.xml is not valid XML") from exc

    body = next((node for node in root.iter() if local_name(node.tag) == "body"), None)
    if body is None:
        raise ValueError("word/document.xml has no document body")

    lines = [
        "# DOCX extracted text",
        "",
        f"Source: `{source_name}`",
        "",
        "This is a searchable extraction. The source DOCX and raw XML/media in "
        "this bundle remain authoritative for layout and editable equations.",
        "",
        "## Body",
        "",
    ]
    for block in body:
        name = local_name(block.tag)
        if name == "p":
            rendered = paragraph_markdown(block)
            if rendered:
                lines.extend([rendered, ""])
        elif name == "tbl":
            rendered_table = table_markdown(block)
            if rendered_table:
                lines.extend(rendered_table)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def digest_stream(handle: BinaryIO) -> FileDigest:
    """Hash one binary stream from its current position."""
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
        digest.update(chunk)
        size += len(chunk)
    return FileDigest(size_bytes=size, sha256=digest.hexdigest())


def digest_file(path: Path) -> FileDigest:
    """Hash a file without loading the whole artifact into memory."""
    with path.open("rb") as handle:
        return digest_stream(handle)


def verify_file_digest(path: Path, expected: FileDigest, *, label: str) -> None:
    """Fail closed unless one file reads back with the expected size and hash."""
    observed = digest_file(path)
    if observed != expected:
        raise ValueError(
            f"{label} readback mismatch: expected {expected}, observed {observed}"
        )


def source_stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """Return source fields that must remain stable while the snapshot is copied."""
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def copy_source_snapshot(source: Path, target: Path) -> FileDigest:
    """Copy the source once, detect observable mutation, and verify the private copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as source_handle, target.open("xb") as target_handle:
        before = os.fstat(source_handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"input is not a regular file: {source}")
        for chunk in iter(lambda: source_handle.read(CHUNK_SIZE), b""):
            target_handle.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(source_handle.fileno())

    try:
        path_after = source.stat()
    except OSError as exc:
        raise ValueError(f"input path changed while snapshotting: {source}") from exc
    if (
        source_stat_identity(before) != source_stat_identity(after)
        or (path_after.st_dev, path_after.st_ino) != (after.st_dev, after.st_ino)
        or size != after.st_size
    ):
        raise ValueError(f"input changed while snapshotting: {source}")

    expected = FileDigest(size_bytes=size, sha256=digest.hexdigest())
    verify_file_digest(target, expected, label="source copy")
    return expected


def copy_archive_members(
    source_copy: Path,
    raw_root: Path,
    members: Iterable[ArchiveMember],
) -> list[dict[str, object]]:
    """Extract prevalidated ZIP members and verify each file by readback."""
    records: list[dict[str, object]] = []
    try:
        archive = zipfile.ZipFile(source_copy)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not a readable DOCX ZIP archive: {source_copy}") from exc

    with archive:
        for member in members:
            info = member.info
            target = raw_root.joinpath(*member.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or not target.is_dir():
                    raise ValueError(f"ZIP directory path conflict: {member.name!r}")
                records.append(
                    {"name": member.name, "directory": True, "size_bytes": 0}
                )
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            try:
                with archive.open(info) as source_handle, target.open("xb") as target_handle:
                    for chunk in iter(lambda: source_handle.read(CHUNK_SIZE), b""):
                        target_handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
            except (RuntimeError, zipfile.BadZipFile) as exc:
                raise ValueError(f"cannot read ZIP member: {info.filename!r}") from exc

            expected = FileDigest(size_bytes=size, sha256=digest.hexdigest())
            if size != info.file_size:
                raise ValueError(
                    f"ZIP member size mismatch: {info.filename!r}: "
                    f"expected {info.file_size}, observed {size}"
                )
            records.append(
                {
                    "name": member.name,
                    "directory": False,
                    "size_bytes": expected.size_bytes,
                    "sha256": expected.sha256,
                }
            )
    return records


def output_path_without_final_symlink(output_dir: Path) -> Path:
    """Resolve output parents while preserving the final component for lstat."""
    absolute = Path(os.path.abspath(os.fspath(output_dir.expanduser())))
    if not absolute.name:
        raise ValueError("output directory must not be a filesystem root")
    absolute.parent.mkdir(parents=True, exist_ok=True)
    return absolute.parent.resolve(strict=True) / absolute.name


def reserve_output_directory(output_dir: Path) -> OutputReservation:
    """Require an absent or empty non-symlink output path and record its identity."""
    output_dir = output_path_without_final_symlink(output_dir)
    try:
        info = output_dir.lstat()
    except FileNotFoundError:
        return OutputReservation(path=output_dir, existed=False)

    if stat.S_ISLNK(info.st_mode):
        raise ValueError(f"output directory must not be a symlink: {output_dir}")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"output path is not a directory: {output_dir}")
    if any(output_dir.iterdir()):
        raise ValueError(f"output directory is not empty: {output_dir}")
    return OutputReservation(
        path=output_dir,
        existed=True,
        device=info.st_dev,
        inode=info.st_ino,
    )


def verify_output_reservation(reservation: OutputReservation) -> None:
    """Fail closed when the final output path changed during bundle construction."""
    try:
        info = reservation.path.lstat()
    except FileNotFoundError:
        if reservation.existed:
            raise ValueError(
                f"output directory changed before publication: {reservation.path}"
            )
        return

    if not reservation.existed:
        raise ValueError(f"output path appeared before publication: {reservation.path}")
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or (info.st_dev, info.st_ino) != (reservation.device, reservation.inode)
        or any(reservation.path.iterdir())
    ):
        raise ValueError(
            f"output directory changed before publication: {reservation.path}"
        )


def verify_bundle_hashes(
    staging: Path,
    source_name: str,
    source_digest: FileDigest,
    raw_records: Sequence[dict[str, object]],
) -> None:
    """Read back all hash-described files immediately before publication."""
    verify_file_digest(
        staging / "source" / source_name,
        source_digest,
        label="source copy",
    )
    raw_root = staging / "raw"
    for record in raw_records:
        name = record["name"]
        if not isinstance(name, str):
            raise ValueError("invalid internal ZIP member record")
        path = raw_root.joinpath(*PurePosixPath(name).parts)
        if record.get("directory") is True:
            if path.is_symlink() or not path.is_dir():
                raise ValueError(f"ZIP directory readback mismatch: {name!r}")
            continue
        expected = FileDigest(
            size_bytes=int(record["size_bytes"]),
            sha256=str(record["sha256"]),
        )
        verify_file_digest(path, expected, label=f"ZIP member {name!r}")


def verify_manifest(path: Path, expected: dict[str, object]) -> None:
    """Parse-read back one manifest and require exact semantic equality."""
    try:
        observed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest readback failed") from exc
    if observed != expected:
        raise ValueError("manifest readback mismatch")


def write_manifest(staging: Path, manifest: dict[str, object]) -> None:
    """Write and parse-read back the manifest before publication."""
    manifest_path = staging / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verify_manifest(manifest_path, manifest)


def build_staged_bundle(source: Path, staging: Path) -> dict[str, object]:
    """Construct and verify the complete bundle in one private staging directory."""
    source_copy = staging / "source" / source.name
    source_digest = copy_source_snapshot(source, source_copy)
    members = inspect_archive(source_copy)

    raw_root = staging / "raw"
    raw_records = copy_archive_members(source_copy, raw_root, members)
    document_xml = (raw_root / DOCUMENT_XML_MEMBER).read_bytes()
    extracted_path = staging / "extracted.md"
    extracted_path.write_text(
        extract_markdown(document_xml, source.name), encoding="utf-8"
    )

    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": source.name,
            "size_bytes": source_digest.size_bytes,
            "sha256": source_digest.sha256,
        },
        "outputs": {
            "source_copy": f"source/{source.name}",
            "extracted_markdown": "extracted.md",
            "raw_members": "raw/",
            "document_xml": f"raw/{DOCUMENT_XML_MEMBER}",
        },
        "zip_members": raw_records,
    }
    verify_bundle_hashes(staging, source.name, source_digest, raw_records)
    write_manifest(staging, manifest)
    return manifest


def publish_staged_bundle(staging: Path, reservation: OutputReservation) -> None:
    """Publish a verified staging directory without exposing partial contents."""
    verify_output_reservation(reservation)
    staging_info = staging.lstat()
    backup = staging.with_name(f"{staging.name}.previous-empty-output")

    if reservation.existed:
        os.rename(reservation.path, backup)
        try:
            os.rename(staging, reservation.path)
        except Exception:
            try:
                os.rename(backup, reservation.path)
            except OSError:
                pass
            raise
        else:
            os.rmdir(backup)
    else:
        os.rename(staging, reservation.path)

    published = reservation.path.lstat()
    if (
        not stat.S_ISDIR(published.st_mode)
        or (published.st_dev, published.st_ino)
        != (staging_info.st_dev, staging_info.st_ino)
    ):
        raise ValueError(f"published output readback mismatch: {reservation.path}")


def extract_bundle(source: Path, output_dir: Path) -> dict[str, object]:
    """Build, verify, and atomically publish one DOCX reference bundle."""
    try:
        source = source.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"input file does not exist: {source}") from exc
    if source.suffix.lower() != ".docx":
        raise ValueError(f"input must have a .docx extension: {source}")
    if not source.is_file():
        raise ValueError(f"input is not a regular file: {source}")

    reservation = reserve_output_directory(output_dir)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{reservation.path.name}.extract-",
            dir=reservation.path.parent,
        )
    )
    try:
        manifest = build_staged_bundle(source, staging)
        publish_staged_bundle(staging, reservation)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Extract an authorized DOCX into a searchable reference bundle."
    )
    parser.add_argument("input", type=Path, help="input .docx file")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new or empty directory to receive the bundle",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the extractor CLI."""
    args = build_parser().parse_args(argv)
    try:
        manifest = extract_bundle(args.input, args.output_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"extract_docx: {exc}", file=sys.stderr)
        return 1
    source_name = manifest["source"]["name"]  # type: ignore[index]
    print(f"extracted {source_name} -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
