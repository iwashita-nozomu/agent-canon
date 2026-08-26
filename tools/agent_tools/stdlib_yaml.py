#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides the dependency-free YAML subset needed by host bootstrap before the shared tool image exists.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md owns the single catalog-derived skill-view materializer.
# downstream implementation ./skill_route_catalog.py, ./skill_dependency_map.py, and ./skill_shim_materializer.py use it only when PyYAML is unavailable.
# downstream implementation ../../tests/agent_tools/test_skill_shim_materializer.py validates clean-host materialization through the stdlib fallback.
# @dependency-end
"""Parse the small YAML subset used by AgentCanon source catalogs.

The bootstrap materializer runs before the shared tool image exists.  Keeping
this parser limited to the declarative catalog grammar lets that first step
use Python's standard library without adding a host dependency or creating a
second catalog representation.  Full YAML remains the image/runtime parser;
this module is only its dependency-free fallback.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any


class YAMLError(ValueError):
    """Raised when a source catalog is outside the supported YAML subset."""


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


_INTEGER = re.compile(r"[-+]?(?:0|[1-9][0-9_]*)$")
_FLOAT = re.compile(
    r"[-+]?(?:(?:[0-9][0-9_]*)?\.[0-9_]+|[0-9][0-9_]*\.(?:[0-9][0-9_]*)?)(?:[eE][-+]?[0-9]+)?$"
)


def _starts_quote(text: str, index: int, char: str) -> bool:
    """Recognize a YAML quote delimiter, not an apostrophe in plain text."""
    if char not in {'"', "'"}:
        return False
    if index == 0:
        return True
    return text[index - 1].isspace() or text[index - 1] in "[{(,:"


def _strip_comment(text: str) -> str:
    """Remove one YAML comment while preserving quoted and flow text."""
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = ""
            continue
        if quote == "'":
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                continue
            if char == "'":
                quote = ""
            continue
        if _starts_quote(text, index, char):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "#" and depth == 0 and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
    if quote:
        raise YAMLError("unterminated quoted scalar")
    if depth:
        raise YAMLError("unbalanced flow collection")
    return text.rstrip()


def _prepare(text: str) -> list[_Line]:
    """Normalize comments and blank/document marker lines."""
    result: list[_Line] = []
    pending: str | None = None
    pending_number = 0

    def append_pending() -> None:
        nonlocal pending
        if pending is None:
            return
        number = pending_number
        stripped = _strip_comment(pending)
        if not stripped.strip() or stripped.strip() in {"---", "..."}:
            pending = None
            return
        prefix = stripped[: len(stripped) - len(stripped.lstrip(" "))]
        result.append(_Line(number, len(prefix), stripped[len(prefix) :].strip()))
        pending = None

    for number, raw in enumerate(text.replace("\r\n", "\n").splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip(" \t"))]:
            raise YAMLError(f"tabs are not supported in indentation at line {number}")
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if pending is None:
            pending = raw
            pending_number = number
            continue
        try:
            previous = _strip_comment(pending)
        except YAMLError:
            # Quoted and flow values may use YAML's folded physical lines.
            pending = pending.rstrip() + " " + raw.strip()
            continue
        previous_indent = len(previous) - len(previous.lstrip(" "))
        current_indent = len(raw) - len(raw.lstrip(" "))
        current = raw.strip()
        previous_value = previous.strip()
        previous_sequence_mapping = previous_value.startswith("-") and _mapping_separator(
            previous_value[1:].strip()
        ) is not None
        continuation = (
            current_indent > previous_indent
            and not (current == "-" or current.startswith("- "))
            and _mapping_separator(current) is None
            and not previous_value.endswith(":")
            and not previous_sequence_mapping
        )
        if continuation:
            pending = previous.rstrip() + " " + current
            continue
        append_pending()
        pending = raw
        pending_number = number
    append_pending()
    return result


def _mapping_separator(text: str) -> int | None:
    """Return the top-level key/value colon position."""
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = ""
            continue
        if quote == "'":
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                continue
            if char == "'":
                quote = ""
            continue
        if _starts_quote(text, index, char):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == ":" and depth == 0 and (
            index + 1 == len(text) or text[index + 1].isspace()
        ):
            return index
    return None


def _split_flow(text: str) -> list[str]:
    """Split a flow collection at commas outside nested/quoted values."""
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = ""
        elif quote == "'":
            if char == "'" and index + 1 < len(text) and text[index + 1] == "'":
                continue
            if char == "'":
                quote = ""
        elif _starts_quote(text, index, char):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    if quote or depth:
        raise YAMLError("invalid flow collection")
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _quoted(text: str) -> str | None:
    if len(text) < 2 or text[0] not in {'"', "'"} or text[-1] != text[0]:
        return None
    try:
        if text[0] == '"':
            return json.loads(text)
        return text[1:-1].replace("''", "'")
    except (ValueError, json.JSONDecodeError):
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError) as fallback:
            raise YAMLError(f"invalid quoted scalar: {text}") from fallback


def _scalar(text: str) -> Any:
    """Parse a scalar or flow collection without resolving external files."""
    text = text.strip()
    if not text:
        return None
    quoted = _quoted(text)
    if quoted is not None:
        return quoted
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [] if not inner else [_scalar(item) for item in _split_flow(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        mapping: dict[str, Any] = {}
        if not inner:
            return mapping
        for item in _split_flow(inner):
            separator = _mapping_separator(item)
            if separator is None:
                raise YAMLError(f"invalid flow mapping item: {item}")
            key = _scalar(item[:separator])
            if not isinstance(key, str):
                raise YAMLError("flow mapping keys must be strings")
            mapping[key] = _scalar(item[separator + 1 :])
        return mapping
    lowered = text.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if _INTEGER.fullmatch(text):
        return int(text.replace("_", ""))
    if _FLOAT.fullmatch(text):
        return float(text.replace("_", ""))
    return text


def _parse_pair(line: _Line) -> tuple[str, str]:
    separator = _mapping_separator(line.text)
    if separator is None:
        raise YAMLError(f"expected mapping entry at line {line.number}")
    key = _scalar(line.text[:separator].strip())
    if not isinstance(key, str) or not key:
        raise YAMLError(f"mapping keys must be non-empty strings at line {line.number}")
    return key, line.text[separator + 1 :].strip()


class _Parser:
    def __init__(self, lines: list[_Line]) -> None:
        self.lines = lines

    def parse(self) -> Any:
        if not self.lines:
            return None
        value, index = self._block(0, self.lines[0].indent)
        if index != len(self.lines):
            line = self.lines[index]
            raise YAMLError(f"unexpected content at line {line.number}")
        return value

    def _block(self, index: int, indent: int) -> tuple[Any, int]:
        if index >= len(self.lines) or self.lines[index].indent != indent:
            raise YAMLError("invalid indentation")
        if self.lines[index].text == "-" or self.lines[index].text.startswith("- "):
            return self._sequence(index, indent)
        return self._mapping(index, indent)

    def _child(self, index: int, parent_indent: int) -> tuple[Any, int]:
        if index >= len(self.lines) or self.lines[index].indent < parent_indent:
            return None, index
        return self._block(index, self.lines[index].indent)

    def _mapping(self, index: int, indent: int) -> tuple[dict[str, Any], int]:
        result: dict[str, Any] = {}
        while index < len(self.lines) and self.lines[index].indent == indent:
            line = self.lines[index]
            if line.text == "-" or line.text.startswith("- "):
                break
            key, remainder = _parse_pair(line)
            index += 1
            if remainder:
                result[key] = _scalar(remainder)
                continue
            if index < len(self.lines):
                child_indent = self.lines[index].indent
                # YAML permits an indentless sequence as a mapping value.
                if child_indent > indent or (
                    child_indent == indent
                    and (self.lines[index].text == "-" or self.lines[index].text.startswith("- "))
                ):
                    result[key], index = self._block(index, child_indent)
                    continue
            result[key] = None
        return result, index

    def _sequence(self, index: int, indent: int) -> tuple[list[Any], int]:
        result: list[Any] = []
        while index < len(self.lines) and self.lines[index].indent == indent:
            line = self.lines[index]
            if not (line.text == "-" or line.text.startswith("- ")):
                break
            remainder = line.text[1:].strip()
            index += 1
            if not remainder:
                value, index = self._child(index, indent + 1)
                result.append(value)
                continue
            separator = _mapping_separator(remainder)
            if separator is None:
                result.append(_scalar(remainder))
                continue
            key = _scalar(remainder[:separator].strip())
            if not isinstance(key, str) or not key:
                raise YAMLError(f"sequence mapping key must be a string at line {line.number}")
            item: dict[str, Any] = {key: _scalar(remainder[separator + 1 :])}
            if not remainder[separator + 1 :].strip() and index < len(self.lines):
                child_indent = self.lines[index].indent
                if child_indent > indent or (
                    child_indent == indent
                    and (self.lines[index].text == "-" or self.lines[index].text.startswith("- "))
                ):
                    item[key], index = self._block(index, child_indent)
            if index < len(self.lines) and self.lines[index].indent > indent:
                continuation, index = self._mapping(index, self.lines[index].indent)
                item.update(continuation)
            result.append(item)
        return result, index


def safe_load(text: str) -> Any:
    """Load one AgentCanon catalog using only Python standard-library code."""
    if not isinstance(text, str):
        raise YAMLError("safe_load expects text")
    return _Parser(_prepare(text)).parse()
