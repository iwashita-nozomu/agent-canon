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
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable, Sequence
from xml.etree import ElementTree


SCHEMA_VERSION = 1
DOCUMENT_XML_MEMBER = "word/document.xml"
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def local_name(tag: str) -> str:
    """Return the namespace-free XML local name."""
    return tag.rsplit("}", 1)[-1]


def normalized_member_name(name: str) -> str:
    """Validate and normalize one ZIP member path."""
    normalized = name.replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    posix_path = PurePosixPath(normalized)
    if (
        not normalized
        or not posix_path.parts
        or normalized.startswith(("/", "\\"))
        or windows_path.drive
        or posix_path.is_absolute()
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise ValueError(f"unsafe ZIP member path: {name!r}")
    return "/".join(posix_path.parts)


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    """Return whether a ZIP member advertises a Unix symlink mode."""
    mode = (info.external_attr >> 16) & 0o170000
    return stat.S_ISLNK(mode)


def inspect_archive(source: Path) -> list[tuple[zipfile.ZipInfo, str]]:
    """Validate archive member paths and return their normalized names."""
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not a readable DOCX ZIP archive: {source}") from exc

    members: list[tuple[zipfile.ZipInfo, str]] = []
    seen: set[str] = set()
    with archive:
        for info in archive.infolist():
            normalized = normalized_member_name(info.filename)
            if normalized in seen:
                raise ValueError(f"duplicate ZIP member path: {normalized}")
            if is_zip_symlink(info):
                raise ValueError(f"symlink ZIP member is not allowed: {info.filename!r}")
            seen.add(normalized)
            members.append((info, normalized))
        if DOCUMENT_XML_MEMBER not in seen:
            raise ValueError(f"DOCX is missing {DOCUMENT_XML_MEMBER}")
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


def sha256_file(path: Path) -> str:
    """Hash a file without loading the whole artifact into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_archive_members(
    source: Path,
    raw_root: Path,
    members: Iterable[tuple[zipfile.ZipInfo, str]],
) -> list[dict[str, object]]:
    """Extract validated ZIP members and return their manifest records."""
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(source) as archive:
        for info, normalized in members:
            target = raw_root.joinpath(*PurePosixPath(normalized).parts)
            if info.is_dir() or info.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                records.append({"name": normalized, "directory": True, "size_bytes": 0})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with archive.open(info) as source_handle, target.open("wb") as target_handle:
                for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                    target_handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            records.append(
                {
                    "name": normalized,
                    "directory": False,
                    "size_bytes": size,
                    "sha256": digest.hexdigest(),
                }
            )
    return records


def prepare_output_directory(output_dir: Path) -> bool:
    """Create or validate an output directory; return whether this call created it."""
    if output_dir.is_symlink():
        raise ValueError(f"output directory must not be a symlink: {output_dir}")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            raise ValueError(f"output directory is not empty: {output_dir}")
        return False
    output_dir.mkdir(parents=True)
    return True


def extract_bundle(source: Path, output_dir: Path) -> dict[str, object]:
    """Write one DOCX bundle and return its manifest."""
    source = source.resolve()
    output_dir = output_dir.resolve()
    if source.suffix.lower() != ".docx":
        raise ValueError(f"input must have a .docx extension: {source}")
    if not source.is_file():
        raise ValueError(f"input file does not exist: {source}")

    members = inspect_archive(source)
    output_was_created = prepare_output_directory(output_dir)
    try:
        source_copy = output_dir / "source" / source.name
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, source_copy)

        raw_root = output_dir / "raw"
        raw_records = copy_archive_members(source, raw_root, members)
        document_xml = (raw_root / DOCUMENT_XML_MEMBER).read_bytes()
        extracted_path = output_dir / "extracted.md"
        extracted_path.write_text(
            extract_markdown(document_xml, source.name), encoding="utf-8"
        )

        manifest: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "name": source.name,
                "size_bytes": source.stat().st_size,
                "sha256": sha256_file(source),
            },
            "outputs": {
                "source_copy": f"source/{source.name}",
                "extracted_markdown": "extracted.md",
                "raw_members": "raw/",
                "document_xml": f"raw/{DOCUMENT_XML_MEMBER}",
            },
            "zip_members": raw_records,
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest
    except Exception:
        if output_was_created:
            shutil.rmtree(output_dir)
        raise


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
