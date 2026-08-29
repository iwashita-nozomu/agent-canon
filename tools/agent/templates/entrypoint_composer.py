#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Composes a consumer-root AGENTS.md from the AgentCanon ROOT_AGENTS.md base and consumer-owned instructions.
# upstream design ../../../documents/design/entrypoint-owner-map.md consumer root composition contract
# downstream design ../../../ROOT_AGENTS.md common consumer root instruction base
# downstream implementation ../../../tests/agent_tools/test_entrypoint_composer.py focused composition tests
# @dependency-end
"""Compose a source-free consumer root AGENTS.md from two explicit files."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


MANAGED_MARKER = b"<!-- agent-canon:consumer-root-agents:v1 -->\n"
BASE_START = b"<!-- agent-canon:consumer-root-base:start -->\n"
BASE_END = b"<!-- agent-canon:consumer-root-base:end -->\n"
SPECIFIC_START = b"<!-- agent-canon:consumer-root-specific:start -->\n"
SPECIFIC_END = b"<!-- agent-canon:consumer-root-specific:end -->\n"
COMPOSITION_SEPARATOR = b"\n"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")


class ComposeError(ValueError):
    """A typed fail-closed composition error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"ENTRYPOINT_COMPOSE_ERROR={code}:{detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Composition:
    """The exact inputs and output bytes for one composition."""

    source_commit: str
    base: bytes
    specific: bytes

    @property
    def base_sha256(self) -> str:
        """Return the digest of the exact base bytes."""
        return hashlib.sha256(self.base).hexdigest()

    @property
    def specific_sha256(self) -> str:
        """Return the digest of the exact consumer-owned bytes."""
        return hashlib.sha256(self.specific).hexdigest()

    def render(self) -> bytes:
        """Render a deterministic, self-contained managed file."""
        metadata = (
            MANAGED_MARKER
            + f"<!-- agent-canon:source-commit={self.source_commit} -->\n".encode()
            + f"<!-- agent-canon:base-sha256={self.base_sha256} -->\n".encode()
            + f"<!-- agent-canon:base-bytes={len(self.base)} -->\n".encode()
            + f"<!-- agent-canon:specific-sha256={self.specific_sha256} -->\n".encode()
            + f"<!-- agent-canon:specific-bytes={len(self.specific)} -->\n".encode()
        )
        return (
            metadata
            + BASE_START
            + self.base
            + COMPOSITION_SEPARATOR
            + BASE_END
            + SPECIFIC_START
            + self.specific
            + COMPOSITION_SEPARATOR
            + SPECIFIC_END
        )


def _read_regular(path: Path, label: str) -> bytes:
    """Read one existing non-symlink regular file."""
    if path.is_symlink():
        raise ComposeError("symlink", f"{label}={path}")
    if not path.exists():
        raise ComposeError("missing", f"{label}={path}")
    if not path.is_file():
        raise ComposeError("type", f"{label}={path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ComposeError("read", f"{label}={path}:{error}") from error


def _source_commit(source_root: Path) -> str:
    """Read the current source commit from the explicit source checkout."""
    if source_root.is_symlink() or not source_root.is_dir():
        raise ComposeError("source-root", str(source_root))
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ComposeError("source-commit-unavailable", str(error)) from error
    commit = result.stdout.strip()
    if result.returncode != 0 or not COMMIT_RE.fullmatch(commit):
        detail = result.stderr.strip() or str(source_root)
        raise ComposeError("source-commit-unavailable", detail)
    return commit


def _metadata_line(data: bytes, prefix: bytes, label: str) -> str:
    """Read one exact metadata line from a managed output."""
    if not data.startswith(prefix) or not data.endswith(b" -->\n"):
        raise ComposeError("partial", label)
    value = data[len(prefix) : -len(b" -->\n")].decode("ascii", errors="strict")
    if not value:
        raise ComposeError("partial", label)
    return value


def _parse_count(value: str, label: str) -> int:
    """Parse a non-negative byte count."""
    if not value.isdigit():
        raise ComposeError("partial", label)
    return int(value)


def _parse_marked(data: bytes) -> Composition:
    """Validate a marked file and recover its exact source segments."""
    if not data.startswith(MANAGED_MARKER):
        raise ComposeError("collision", "output is not a managed consumer AGENTS.md")
    cursor = len(MANAGED_MARKER)
    metadata: dict[str, str] = {}
    fields = (
        (b"<!-- agent-canon:source-commit=", "source-commit"),
        (b"<!-- agent-canon:base-sha256=", "base-sha256"),
        (b"<!-- agent-canon:base-bytes=", "base-bytes"),
        (b"<!-- agent-canon:specific-sha256=", "specific-sha256"),
        (b"<!-- agent-canon:specific-bytes=", "specific-bytes"),
    )
    for prefix, label in fields:
        end = data.find(b"\n", cursor)
        if end < 0:
            raise ComposeError("partial", label)
        metadata[label] = _metadata_line(data[cursor : end + 1], prefix, label)
        cursor = end + 1
    source_commit = metadata["source-commit"]
    if not COMMIT_RE.fullmatch(source_commit):
        raise ComposeError("partial", "source-commit")
    for label in ("base-sha256", "specific-sha256"):
        if not HEX_RE.fullmatch(metadata[label]):
            raise ComposeError("partial", label)
    base_size = _parse_count(metadata["base-bytes"], "base-bytes")
    specific_size = _parse_count(metadata["specific-bytes"], "specific-bytes")
    if not data.startswith(BASE_START, cursor):
        raise ComposeError("partial", "base-start")
    cursor += len(BASE_START)
    base = data[cursor : cursor + base_size]
    if len(base) != base_size:
        raise ComposeError("partial", "base-bytes")
    cursor += base_size
    if not data.startswith(COMPOSITION_SEPARATOR + BASE_END, cursor):
        raise ComposeError("partial", "base-end")
    cursor += len(COMPOSITION_SEPARATOR + BASE_END)
    if not data.startswith(SPECIFIC_START, cursor):
        raise ComposeError("partial", "specific-start")
    cursor += len(SPECIFIC_START)
    specific = data[cursor : cursor + specific_size]
    if len(specific) != specific_size:
        raise ComposeError("partial", "specific-bytes")
    cursor += specific_size
    if data[cursor:] != COMPOSITION_SEPARATOR + SPECIFIC_END:
        raise ComposeError("partial", "specific-end")
    if hashlib.sha256(base).hexdigest() != metadata["base-sha256"]:
        raise ComposeError("partial", "base-digest")
    if hashlib.sha256(specific).hexdigest() != metadata["specific-sha256"]:
        raise ComposeError("partial", "specific-digest")
    return Composition(source_commit, base, specific)


def _write_atomic(output: Path, data: bytes) -> None:
    """Replace the output with one regular file in the same directory."""
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ComposeError("output-parent", str(parent))
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{output.name}.", dir=str(parent)
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    except OSError as error:
        raise ComposeError("write", f"output={output}:{error}") from error
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def compose(
    *, base_path: Path, specific_path: Path, output_path: Path, source_root: Path
) -> tuple[str, Composition]:
    """Compose or update one consumer root instruction file."""
    base = _read_regular(base_path, "base")
    specific = _read_regular(specific_path, "specific")
    composition = Composition(_source_commit(source_root), base, specific)
    if output_path.is_symlink():
        raise ComposeError("symlink", f"output={output_path}")
    if output_path.exists():
        if not output_path.is_file():
            raise ComposeError("type", f"output={output_path}")
        _parse_marked(output_path.read_bytes())
        status = "updated"
    else:
        status = "created"
    _write_atomic(output_path, composition.render())
    return status, composition


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit composition command parser."""
    parser = argparse.ArgumentParser(
        description="Compose a source-free consumer AGENTS.md from explicit inputs."
    )
    parser.add_argument("--base", required=True, help="AgentCanon ROOT_AGENTS.md")
    parser.add_argument("--specific", required=True, help="consumer-owned instruction file")
    parser.add_argument("--output", required=True, help="consumer root AGENTS.md output")
    parser.add_argument(
        "--source-root",
        default=".",
        help="AgentCanon source checkout used for commit provenance (default: cwd)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the composition command and print a compact readback."""
    args = build_parser().parse_args(argv)
    try:
        status, composition = compose(
            base_path=Path(args.base),
            specific_path=Path(args.specific),
            output_path=Path(args.output),
            source_root=Path(args.source_root),
        )
    except ComposeError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"ENTRYPOINT_COMPOSE_STATUS={status}")
    print(f"ENTRYPOINT_COMPOSE_OUTPUT={Path(args.output)}")
    print(f"ENTRYPOINT_COMPOSE_SOURCE_COMMIT={composition.source_commit}")
    print(f"ENTRYPOINT_COMPOSE_BASE_SHA256={composition.base_sha256}")
    print(f"ENTRYPOINT_COMPOSE_SPECIFIC_SHA256={composition.specific_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
