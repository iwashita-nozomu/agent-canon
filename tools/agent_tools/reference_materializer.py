#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes cited PDF or HTML references as Markdown under references/.
# upstream design ../../references/README.md external reference capture policy
# downstream implementation ../../tests/agent_tools/test_reference_materializer.py verifies extraction behavior
# @dependency-end
"""Materialize external PDF or HTML references as Markdown files."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

FETCH_TIMEOUT_SECONDS = 30
PDF_TEXT_TIMEOUT_SECONDS = 30
HASH_LENGTH = 12
MAX_TITLE_LENGTH = 90
MAX_SNIPPET_LENGTH = 200_000
DEFAULT_OUTPUT_DIR = Path("references/external")


@dataclass(frozen=True)
class LoadedSource:
    """Loaded source bytes plus path metadata."""

    data: bytes
    path_text: str
    suffix_seed: str

    @property
    def has_local_path(self) -> bool:
        """Return whether the source came from a local file."""
        return bool(self.path_text)

    @property
    def local_path(self) -> Path:
        """Return the local path when available."""
        return Path(self.path_text)


@dataclass(frozen=True)
class ExtractedReference:
    """Extracted source material ready for Markdown rendering."""

    url: str
    source_kind: str
    title: str
    text: str
    content_sha256: str
    extraction_status: str
    extraction_method: str
    retrieved_at_utc: str

    @property
    def status(self) -> str:
        """Return pass when meaningful text was extracted."""
        return "pass" if self.text.strip() else "warn"


class HtmlTextExtractor(HTMLParser):
    """Small stdlib HTML-to-text extractor for reference capture."""

    def __init__(self) -> None:
        """Initialize parser state."""
        super().__init__(convert_charrefs=True)
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._hidden_depth = 0
        self._in_title = False

    @property
    def title(self) -> str:
        """Return the parsed HTML title."""
        return normalize_whitespace(" ".join(self._title_parts))

    @property
    def text(self) -> str:
        """Return visible text extracted from the document."""
        return normalize_whitespace(" ".join(self._text_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track hidden and title regions."""
        del attrs
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "template"}:
            self._hidden_depth += 1
        if normalized == "title":
            self._in_title = True
        if normalized in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Close hidden and title regions."""
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "template"} and self._hidden_depth:
            self._hidden_depth -= 1
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        """Collect visible text and title text."""
        if self._in_title:
            self._title_parts.append(data)
        if not self._hidden_depth and data.strip():
            self._text_parts.append(data)


@dataclass(frozen=True)
class SourceLoader:
    """Load reference bytes from a local file or a URL."""

    url: str
    input_path: Path
    fetch: bool

    def load(self) -> LoadedSource:
        """Return loaded bytes and source metadata."""
        if str(self.input_path):
            data = self.input_path.read_bytes()
            return LoadedSource(data=data, path_text=str(self.input_path), suffix_seed=self.input_path.suffix)
        if not self.fetch:
            raise ValueError("--input is required unless --fetch is set")
        return LoadedSource(
            data=self.fetch_url(),
            path_text="",
            suffix_seed=Path(urlparse(self.url).path).suffix,
        )

    def fetch_url(self) -> bytes:
        """Fetch the configured URL."""
        request = urllib.request.Request(
            self.url,
            headers={"User-Agent": "agent-canon-reference-materializer/1"},
        )
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            return response.read()


@dataclass(frozen=True)
class PdfExtractor:
    """Extract PDF text using configured PDF text tools."""

    source: LoadedSource

    def extract(self) -> tuple[str, str]:
        """Return extracted PDF text and method."""
        extractor_available = importlib.util.find_spec("pypdf") is not None or shutil.which("pdftotext") is not None
        if not extractor_available:
            raise ValueError("pdf-text-extractor-required: install pypdf or pdftotext")
        pypdf_text = extract_pdf_with_pypdf(self.source.data)
        if pypdf_text:
            return pypdf_text, "pypdf"
        pdftotext_text = self.extract_with_pdftotext()
        if pdftotext_text:
            return pdftotext_text, "pdftotext"
        raise ValueError("pdf-text-extraction-failed: repair pypdf or pdftotext extraction")

    def extract_with_pdftotext(self) -> str:
        """Extract PDF text with the pdftotext binary when available."""
        binary = shutil.which("pdftotext")
        if binary is None:
            return ""
        if self.source.has_local_path:
            return run_pdftotext(binary, self.source.local_path)
        return self.extract_temp_pdf_with_pdftotext(binary)

    def extract_temp_pdf_with_pdftotext(self, binary: str) -> str:
        """Write fetched PDF bytes to a temp file and run pdftotext."""
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temp_file:
            temp_file.write(self.source.data)
            temp_file.flush()
            return run_pdftotext(binary, Path(temp_file.name))


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--url", required=True, help="Canonical source URL.")
    parser.add_argument("--input", type=Path, default=Path(""), help="Local PDF or HTML file to convert.")
    parser.add_argument("--fetch", action="store_true", help="Fetch --url directly before conversion.")
    parser.add_argument("--title", default="", help="Reference title override.")
    parser.add_argument(
        "--source-kind",
        choices=("auto", "pdf", "html"),
        default="auto",
        help="Input source kind. Defaults to URL/path autodetection.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing Markdown reference.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def utc_now() -> str:
    """Return one UTC timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_whitespace(value: str) -> str:
    """Return readable single-spaced text with paragraph breaks preserved."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line
        if blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = blank
    return "\n".join(collapsed).strip()


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def infer_source_kind(source: LoadedSource, requested: str) -> str:
    """Return pdf or html for the input source."""
    if requested != "auto":
        return requested
    suffix = source.suffix_seed.lower()
    return "pdf" if suffix == ".pdf" else "html"


def extract_html(data: bytes, title_override: str) -> tuple[str, str, str]:
    """Extract title and visible text from HTML bytes."""
    text = data.decode("utf-8", errors="replace")
    parser = HtmlTextExtractor()
    parser.feed(text)
    title = title_override or parser.title
    return title, parser.text, "stdlib-html-parser"


def extract_pdf_with_pypdf(data: bytes) -> str:
    """Extract PDF text with pypdf when installed."""
    if importlib.util.find_spec("pypdf") is None:
        return ""
    try:
        import pypdf  # type: ignore[import-not-found]

        reader = pypdf.PdfReader(BytesIO(data))
        return normalize_whitespace("\n".join(page.extract_text() or "" for page in reader.pages))
    except Exception:
        return ""


def run_pdftotext(binary: str, input_path: Path) -> str:
    """Run pdftotext and return normalized output."""
    result = subprocess.run(
        [binary, "-layout", str(input_path), "-"],
        check=False,
        capture_output=True,
        text=True,
        timeout=PDF_TEXT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return ""
    return normalize_whitespace(result.stdout)


def require_title(title: str) -> str:
    """Return a normalized title or fail when the source did not provide one."""
    normalized = normalize_whitespace(title)
    if not normalized:
        raise ValueError("reference title is required: pass --title or provide an HTML <title>")
    return normalized


def slugify(value: str) -> str:
    """Return a stable filename slug."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").casefold()
    return slug[:MAX_TITLE_LENGTH].strip("-") or "external-reference"


def output_path(root: Path, output_dir: Path, url: str, title: str) -> Path:
    """Return the Markdown output path for one reference."""
    directory = output_dir if output_dir.is_absolute() else root / output_dir
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:HASH_LENGTH]
    return directory / f"{slugify(title)}-{digest}.md"


def path_relative_to(start: Path, target: Path) -> str:
    """Return a POSIX relative path."""
    return Path(os.path.relpath(target.resolve(), start.resolve())).as_posix()


def render_markdown(root: Path, path: Path, reference: ExtractedReference) -> str:
    """Render one extracted reference as Markdown."""
    readme = path_relative_to(path.parent, root / "references" / "README.md")
    tool = path_relative_to(path.parent, root / "tools" / "agent_tools" / "reference_materializer.py")
    text = reference.text[:MAX_SNIPPET_LENGTH].strip()
    if len(reference.text) > MAX_SNIPPET_LENGTH:
        text += "\n\n[Extraction truncated by reference_materializer.py.]"
    return "\n".join(
        [
            f"# {reference.title}",
            "",
            "<!--",
            "@dependency-start",
            f"responsibility Stores extracted reference material for {reference.url}.",
            f"upstream design {readme} reference capture policy",
            f"upstream implementation {tool} created this Markdown reference",
            "@dependency-end",
            "-->",
            "",
            "## Metadata",
            "",
            f"- source_url: {reference.url}",
            f"- source_kind: {reference.source_kind}",
            f"- retrieved_at_utc: {reference.retrieved_at_utc}",
            f"- content_sha256: {reference.content_sha256}",
            f"- extraction_status: {reference.extraction_status}",
            f"- extraction_method: {reference.extraction_method}",
            "",
            "## Extracted Text",
            "",
            text or "_No text extracted. Keep this metadata record if the source was still consulted._",
            "",
        ]
    )


def build_reference(args: argparse.Namespace) -> ExtractedReference:
    """Load and extract one reference."""
    source = SourceLoader(args.url, args.input, args.fetch).load()
    source_kind = infer_source_kind(source, args.source_kind)
    if source_kind == "pdf":
        extracted_text, method = PdfExtractor(source).extract()
        title = require_title(args.title)
    else:
        title, extracted_text, method = extract_html(source.data, args.title)
        title = require_title(title)
    return ExtractedReference(
        url=args.url,
        source_kind=source_kind,
        title=title,
        text=extracted_text,
        content_sha256=sha256_hex(source.data),
        extraction_status="text-extracted" if extracted_text.strip() else "metadata-only",
        extraction_method=method,
        retrieved_at_utc=utc_now(),
    )


def write_reference(root: Path, output_dir: Path, reference: ExtractedReference, force: bool) -> Path:
    """Write one Markdown reference file."""
    path = output_path(root, output_dir, reference.url, reference.title)
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(root, path, reference), encoding="utf-8")
    return path


def render_text(reference: ExtractedReference, path: Path, root: Path) -> str:
    """Render stable key-value output."""
    rel_path = path_relative_to(root, path)
    return "\n".join(
        [
            f"REFERENCE_MATERIALIZE_PATH={rel_path}",
            f"REFERENCE_MATERIALIZE_URL={reference.url}",
            f"REFERENCE_MATERIALIZE_SOURCE_KIND={reference.source_kind}",
            f"REFERENCE_MATERIALIZE_EXTRACTION_METHOD={reference.extraction_method}",
            f"REFERENCE_MATERIALIZE_EXTRACTION_STATUS={reference.extraction_status}",
            f"REFERENCE_MATERIALIZE_CONTENT_SHA256={reference.content_sha256}",
            f"REFERENCE_MATERIALIZE={reference.status}",
        ]
    )


def render_json(reference: ExtractedReference, path: Path, root: Path) -> str:
    """Render JSON output."""
    import json

    return json.dumps(
        {
            "status": reference.status,
            "path": path_relative_to(root, path),
            "url": reference.url,
            "source_kind": reference.source_kind,
            "extraction_method": reference.extraction_method,
            "extraction_status": reference.extraction_status,
            "content_sha256": reference.content_sha256,
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the reference materializer."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        reference = build_reference(args)
        path = write_reference(root, args.output_dir, reference, args.force)
    except (OSError, ValueError) as exc:
        print(f"REFERENCE_MATERIALIZE_ERROR={exc}", file=sys.stderr)
        print("REFERENCE_MATERIALIZE=fail")
        return 1
    if args.format == "json":
        print(render_json(reference, path, root))
    else:
        print(render_text(reference, path, root))
    return 0 if reference.status in {"pass", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
