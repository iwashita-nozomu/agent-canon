#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reads compact discovered Skills and task-relevant canonical Skill sections in bounded UTF-8 chunks.
# upstream design ../../agents/skills/agent-orchestration.md owner-first Skill read and implementation admission
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md bounded Skill read admission
# downstream implementation ../../tests/agent_tools/test_skill_document_reader.py validates heading indexing, chunk boundaries, and admission state
# @dependency-end
"""Read Skill documents in bounded chunks without requiring full canonical files."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Iterable, Sequence


class SkillDocumentError(ValueError):
    """A typed error raised for an invalid Skill read request."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


@dataclass(frozen=True)
class Heading:
    """One Markdown ATX heading and its byte position."""

    heading: str
    title: str
    level: int
    line: int
    byte_start: int
    byte_end: int
    section_end: int

    def as_json(self) -> dict[str, object]:
        """Return the heading as JSON-compatible data."""
        return asdict(self)


@dataclass(frozen=True)
class DocumentChunk:
    """One bounded, UTF-8-safe document or section chunk."""

    path: str
    heading: str | None
    line_start: int | None
    line_end: int | None
    byte_start: int
    byte_end: int
    next_offset: int
    section_eof: bool
    file_eof: bool
    text: str

    def as_json(self) -> dict[str, object]:
        """Return the chunk as JSON-compatible data."""
        return asdict(self)


@dataclass(frozen=True)
class SkillReadAdmission:
    """Transient implementation-read state; no receipt is written."""

    compact_path: str
    compact_file_eof: bool
    owner_sections: tuple[DocumentChunk, ...]
    implementation_read: str

    def as_json(self) -> dict[str, object]:
        """Return the transient admission state as JSON-compatible data."""
        return {
            "compact_path": self.compact_path,
            "compact_file_eof": self.compact_file_eof,
            "owner_sections": [chunk.as_json() for chunk in self.owner_sections],
            "implementation_read": self.implementation_read,
        }


_HEADING_RE = re.compile(r"^( {0,3})(#{1,6})(?:[ \t]+(.*?)[ \t]*|[ \t]*)$")
DEFAULT_MAX_BYTES = 4_096


def _heading_from_line(line: str) -> tuple[str, str, int] | None:
    """Return an ATX heading while excluding trailing closing markers."""
    match = _HEADING_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    level = len(match.group(2))
    title = (match.group(3) or "").strip()
    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).rstrip()
    heading = f"{'#' * level}{(' ' + title) if title else ''}"
    return heading, title, level


def _line_table(data: bytes) -> tuple[tuple[int, int, str], ...]:
    """Build one-based line and exact UTF-8 byte range entries."""
    rows: list[tuple[int, int, str]] = []
    offset = 0
    for raw in data.splitlines(keepends=True):
        end = offset + len(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillDocumentError("invalid_utf8", f"byte={offset}") from exc
        rows.append((offset, end, text))
        offset = end
    if not data:
        return ()
    if not rows or offset < len(data):
        raw = data[offset:]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillDocumentError("invalid_utf8", f"byte={offset}") from exc
        rows.append((offset, len(data), text))
    return tuple(rows)


class SkillDocumentReader:
    """Index one UTF-8 Markdown document and serve bounded section chunks."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        try:
            self.data = self.path.read_bytes()
        except OSError as exc:
            raise SkillDocumentError("read_failed", str(self.path)) from exc
        self.lines = _line_table(self.data)
        self.headings = self._index_headings()

    def _index_headings(self) -> tuple[Heading, ...]:
        """Index Markdown headings outside fenced code blocks."""
        headings: list[tuple[str, str, int, int, int, int]] = []
        fence: str | None = None
        for line_number, (start, end, text) in enumerate(self.lines, start=1):
            stripped = text.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if fence is None:
                    fence = marker
                elif marker == fence:
                    fence = None
                continue
            if fence is not None:
                continue
            parsed = _heading_from_line(text)
            if parsed is not None:
                heading, title, level = parsed
                headings.append((heading, title, level, line_number, start, end))

        indexed: list[Heading] = []
        file_end = len(self.data)
        for index, (heading, title, level, line, start, end) in enumerate(headings):
            section_end = file_end
            for next_heading in headings[index + 1 :]:
                if next_heading[2] <= level:
                    section_end = next_heading[4]
                    break
            indexed.append(
                Heading(heading, title, level, line, start, end, section_end)
            )
        return tuple(indexed)

    def find_heading(self, requested: str) -> Heading:
        """Resolve one exact heading, accepting its title when unambiguous."""
        value = requested.strip()
        exact = [item for item in self.headings if item.heading == value]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise SkillDocumentError("heading_ambiguous", value)
        title_matches = [item for item in self.headings if item.title == value]
        if len(title_matches) == 1:
            return title_matches[0]
        if len(title_matches) > 1:
            raise SkillDocumentError("heading_ambiguous", value)
        raise SkillDocumentError("heading_not_found", value)

    def index(self) -> tuple[Heading, ...]:
        """Return the stable heading index."""
        return self.headings

    def chunk(
        self,
        *,
        heading: str | None = None,
        offset: int = 0,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> DocumentChunk:
        """Return one UTF-8-safe chunk from a file or named section.

        ``byte_start``, ``byte_end``, and ``next_offset`` use zero-based
        half-open file byte offsets. ``line_start`` and ``line_end`` are
        one-based inclusive line numbers for the returned bytes.
        """
        if max_bytes <= 0:
            raise SkillDocumentError("invalid_max_bytes", str(max_bytes))
        selected = self.find_heading(heading) if heading is not None else None
        section_start = selected.byte_start if selected else 0
        section_end = selected.section_end if selected else len(self.data)
        if offset == 0:
            offset = section_start
        if offset < section_start or offset > section_end:
            raise SkillDocumentError("offset_out_of_section", str(offset))
        if offset == section_end:
            raise SkillDocumentError("offset_at_eof", str(offset))

        requested_end = min(offset + max_bytes, section_end)
        end = requested_end
        while end > offset:
            try:
                text = self.data[offset:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        else:
            raise SkillDocumentError("max_bytes_splits_utf8", str(max_bytes))

        # Keep the promised upper bound while guaranteeing progress for a
        # multibyte character at the start of a chunk.
        if not text:
            raise SkillDocumentError("max_bytes_splits_utf8", str(max_bytes))
        line_starts = [row[0] for row in self.lines]
        first_line = bisect.bisect_right(line_starts, offset)
        last_line = bisect.bisect_right(line_starts, end - 1)
        line_start = first_line if self.lines else None
        line_end = last_line if self.lines else None
        return DocumentChunk(
            path=self.path.as_posix(),
            heading=selected.heading if selected else None,
            line_start=line_start,
            line_end=line_end,
            byte_start=offset,
            byte_end=end,
            next_offset=end,
            section_eof=end >= section_end,
            file_eof=end >= len(self.data),
            text=text,
        )

    def read_file(self, *, max_bytes: int = DEFAULT_MAX_BYTES) -> tuple[DocumentChunk, ...]:
        """Read the complete file as bounded chunks."""
        chunks: list[DocumentChunk] = []
        offset = 0
        if not self.data:
            return ()
        while offset < len(self.data):
            current = self.chunk(offset=offset, max_bytes=max_bytes)
            chunks.append(current)
            offset = current.next_offset
        return tuple(chunks)

    def read_section(
        self, heading: str, *, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> tuple[DocumentChunk, ...]:
        """Read one named section as bounded chunks."""
        selected = self.find_heading(heading)
        chunks: list[DocumentChunk] = []
        offset = selected.byte_start
        while offset < selected.section_end:
            current = self.chunk(
                heading=selected.heading, offset=offset, max_bytes=max_bytes
            )
            chunks.append(current)
            offset = current.next_offset
        return tuple(chunks)


def _read_owner_spec(value: str) -> tuple[Path, str]:
    """Parse one ``path#heading`` owner section reference."""
    path_text, separator, heading = value.partition("#")
    if not separator or not path_text or not heading.strip():
        raise SkillDocumentError("invalid_owner_section", value)
    return Path(path_text), heading.strip()


def admit_implementation_read(
    compact_path: Path | str,
    owner_sections: Sequence[tuple[Path | str, str]] = (),
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> SkillReadAdmission:
    """Return ready only after compact EOF and each requested section EOF."""
    compact_reader = SkillDocumentReader(compact_path)
    compact_chunks = compact_reader.read_file(max_bytes=max_bytes)
    compact_eof = bool(compact_chunks) and compact_chunks[-1].file_eof
    owner_chunks: list[DocumentChunk] = []
    for owner_path, owner_heading in owner_sections:
        reader = SkillDocumentReader(owner_path)
        chunks = reader.read_section(owner_heading, max_bytes=max_bytes)
        if chunks:
            owner_chunks.append(chunks[-1])
        else:
            owner_chunks.append(
                DocumentChunk(
                    path=Path(owner_path).as_posix(),
                    heading=owner_heading,
                    line_start=None,
                    line_end=None,
                    byte_start=0,
                    byte_end=0,
                    next_offset=0,
                    section_eof=False,
                    file_eof=False,
                    text="",
                )
            )
    ready = implementation_read_state(
        compact_eof, (chunk.section_eof for chunk in owner_chunks)
    ) == "ready"
    return SkillReadAdmission(
        compact_path=Path(compact_path).as_posix(),
        compact_file_eof=compact_eof,
        owner_sections=tuple(owner_chunks),
        implementation_read="ready" if ready else "locked",
    )


def implementation_read_state(
    compact_file_eof: bool, owner_section_eofs: Iterable[bool]
) -> str:
    """Return transient admission state from observed EOF flags."""
    return (
        "ready"
        if compact_file_eof and all(owner_section_eofs)
        else "locked"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the reader CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("index", "chunk", "admit"))
    parser.add_argument("--path", type=Path, help="Markdown document path.")
    parser.add_argument("--heading", help="Exact heading or unique heading title.")
    parser.add_argument("--offset", type=int, default=0, help="Zero-based file byte offset.")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--compact", type=Path, help="Generated compact SKILL.md path.")
    parser.add_argument(
        "--owner",
        action="append",
        default=[],
        metavar="PATH#HEADING",
        help="Canonical owner section; repeat for each delegated section.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _render_text(value: object) -> str:
    """Render a compact human-readable response without losing chunk text."""
    if isinstance(value, DocumentChunk):
        payload = value.as_json()
        return "\n".join(f"{key}={json.dumps(item, ensure_ascii=False)}" for key, item in payload.items())
    if isinstance(value, SkillReadAdmission):
        payload = value.as_json()
        return "\n".join(f"{key}={json.dumps(item, ensure_ascii=False)}" for key, item in payload.items())
    if isinstance(value, tuple):
        return json.dumps([item.as_json() for item in value], ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bounded Skill reader."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "index":
            if args.path is None:
                raise SkillDocumentError("path_required")
            result: object = tuple(SkillDocumentReader(args.path).index())
        elif args.command == "chunk":
            if args.path is None:
                raise SkillDocumentError("path_required")
            result = SkillDocumentReader(args.path).chunk(
                heading=args.heading,
                offset=args.offset,
                max_bytes=args.max_bytes,
            )
        else:
            if args.compact is None:
                raise SkillDocumentError("compact_required")
            owners = tuple(_read_owner_spec(value) for value in args.owner)
            result = admit_implementation_read(args.compact, owners, max_bytes=args.max_bytes)
        if args.format == "json":
            if isinstance(result, tuple):
                payload: object = [item.as_json() for item in result]
            else:
                payload = result.as_json()  # type: ignore[union-attr]
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        else:
            print(_render_text(result))
        return 0
    except SkillDocumentError as exc:
        print(f"SKILL_DOCUMENT_READER_ERROR={exc.code}:{exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
