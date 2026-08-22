#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Owns canonical PEP 508 requirements-lock parsing, logical records, hashes, and typed errors.
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md requirements lock parser ownership and checker projection
# downstream implementation ./devcontainer_dependencies.py consumes parsed records and error projections
# downstream implementation ../../tests/agent_tools/test_requirements_lock.py verifies parser behavior and error branches
# @dependency-end
"""Parse pip-compile requirements files into one canonical typed result."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

HASH_OPTION_PREFIX = "--hash=sha256:"
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class RequirementErrorCode(str, Enum):  # noqa: UP042
    """Stable error categories emitted by the requirements lock parser."""

    INVALID_REQUIREMENT = "invalid-requirement"
    MALFORMED_CONTINUATION = "malformed-continuation"
    ORPHAN_HASH = "orphan-hash"
    MALFORMED_HASH = "malformed-hash"
    INVALID_OPTION = "invalid-option"
    UNTERMINATED_CONTINUATION = "unterminated-continuation"


@dataclass(frozen=True)
class RequirementHash:
    """One validated hash option attached to a logical requirement record."""

    algorithm: str
    digest: str


@dataclass(frozen=True)
class RequirementRecord:
    """One PEP 508 requirement and its optional pip-compile hashes."""

    raw: str
    normalized_name: str
    extras: tuple[str, ...]
    specifier: str
    marker: str | None
    url: str | None
    hashes: tuple[RequirementHash, ...]
    line_number: int

    def is_active(self) -> bool:
        """Return whether this requirement marker applies in this environment."""
        if self.marker is None:
            return True
        return Marker(self.marker).evaluate()


@dataclass(frozen=True)
class RequirementParseError:
    """One typed rejection with a stable source location and detail."""

    path: Path
    code: RequirementErrorCode
    line_number: int
    detail: str

    def render(self) -> str:
        """Return the diagnostic used by consumer finding projections."""
        return f"{self.path}:{self.line_number}: {self.detail}"


@dataclass(frozen=True)
class RequirementParseResult:
    """Complete parser output, including valid records and all typed errors."""

    path: Path
    records: tuple[RequirementRecord, ...]
    errors: tuple[RequirementParseError, ...]

    @property
    def valid(self) -> bool:
        """Return whether the file contains no rejected records or lines."""
        return not self.errors


def _strip_comment(line: str) -> str:
    """Strip a requirements comment without changing URL fragments."""
    for index, character in enumerate(line):
        if character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].strip()
    return line.strip()


def _parse_record(
    path: Path,
    value: str,
    line_number: int,
    hashes: tuple[RequirementHash, ...],
) -> tuple[RequirementRecord | None, RequirementParseError | None]:
    """Parse one logical requirement after continuation folding."""
    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None, RequirementParseError(
            path,
            RequirementErrorCode.INVALID_REQUIREMENT,
            line_number,
            f"unsupported requirement syntax: {value}",
        )
    return (
        RequirementRecord(
            raw=value,
            normalized_name=canonicalize_name(requirement.name),
            extras=tuple(sorted(requirement.extras)),
            specifier=str(requirement.specifier),
            marker=str(requirement.marker) if requirement.marker is not None else None,
            url=requirement.url,
            hashes=hashes,
            line_number=line_number,
        ),
        None,
    )


def _split_continuation(line: str) -> tuple[str, bool]:
    """Return a comment-free line value and whether it continues."""
    continued = line.endswith("\\")
    return (line[:-1].rstrip() if continued else line, continued)


def _parse_hash_option(
    path: Path, value: str, line_number: int
) -> tuple[RequirementHash | None, RequirementParseError | None]:
    """Validate one hash option and return its normalized value."""
    if not value.startswith(HASH_OPTION_PREFIX):
        return None, RequirementParseError(
            path,
            RequirementErrorCode.MALFORMED_HASH,
            line_number,
            "malformed requirement hash",
        )
    digest = value[len(HASH_OPTION_PREFIX) :]
    if SHA256_RE.fullmatch(digest) is None:
        return None, RequirementParseError(
            path,
            RequirementErrorCode.MALFORMED_HASH,
            line_number,
            "malformed requirement hash",
        )
    return RequirementHash("sha256", digest.lower()), None


def _parse_continuation_line(
    path: Path, raw_line: str, line_number: int
) -> tuple[bool, bool, RequirementHash | None, RequirementParseError | None]:
    """Classify one physical continuation line and validate its hash."""
    line = _strip_comment(raw_line)
    if not line:
        return False, False, None, None

    value, continued = _split_continuation(line)
    if not value or not value.startswith("--hash"):
        return (
            True,
            False,
            None,
            RequirementParseError(
                path,
                RequirementErrorCode.MALFORMED_CONTINUATION,
                line_number,
                "malformed requirement continuation",
            ),
        )

    hash_value, error = _parse_hash_option(path, value, line_number)
    return True, continued, hash_value, error


def _parse_continued_record(
    path: Path,
    lines: tuple[str, ...],
    start_index: int,
    requirement: str,
    requirement_line_number: int,
) -> tuple[int, RequirementRecord | None, tuple[RequirementParseError, ...]]:
    """Consume hash continuation lines for one logical requirement."""
    hashes: list[RequirementHash] = []
    errors: list[RequirementParseError] = []
    invalid = False
    index = start_index + 1

    while index < len(lines):
        line_number = index + 1
        line_present, continued, hash_value, error = _parse_continuation_line(
            path, lines[index], line_number
        )
        if not line_present:
            if not invalid:
                errors.append(
                    RequirementParseError(
                        path,
                        RequirementErrorCode.MALFORMED_CONTINUATION,
                        line_number,
                        "malformed requirement continuation",
                    )
                )
            return index + 1, None, tuple(errors)

        if error is not None:
            if error.code is RequirementErrorCode.MALFORMED_CONTINUATION:
                if not invalid:
                    errors.append(error)
                return index + 1, None, tuple(errors)
            invalid = True
            errors.append(error)
        elif not invalid and hash_value is not None:
            hashes.append(hash_value)

        if not continued:
            if invalid:
                return index + 1, None, tuple(errors)
            record, error = _parse_record(
                path,
                requirement,
                requirement_line_number,
                tuple(hashes),
            )
            if error is not None:
                errors.append(error)
            return index + 1, record, tuple(errors)
        index += 1

    if not invalid:
        errors.append(
            RequirementParseError(
                path,
                RequirementErrorCode.UNTERMINATED_CONTINUATION,
                requirement_line_number,
                "unterminated requirement continuation",
            )
        )
    return index, None, tuple(errors)


def parse_requirements(path: Path) -> RequirementParseResult:
    """Parse one requirements file with strict pip-compile continuation rules."""
    records: list[RequirementRecord] = []
    errors: list[RequirementParseError] = []
    lines = tuple(path.read_text(encoding="utf-8").splitlines())
    index = 0

    while index < len(lines):
        line_number = index + 1
        line = _strip_comment(lines[index])
        if not line:
            index += 1
            continue

        value, continued = _split_continuation(line)
        if not value:
            errors.append(
                RequirementParseError(
                    path,
                    RequirementErrorCode.MALFORMED_CONTINUATION,
                    line_number,
                    "malformed requirement continuation",
                )
            )
            index += 1
            continue

        if value.startswith("--hash"):
            errors.append(
                RequirementParseError(
                    path,
                    RequirementErrorCode.ORPHAN_HASH,
                    line_number,
                    "orphan requirement hash",
                )
            )
            index += 1
            continue
        if value.startswith("-"):
            errors.append(
                RequirementParseError(
                    path,
                    RequirementErrorCode.INVALID_OPTION,
                    line_number,
                    "requirement option without requirement",
                )
            )
            index += 1
            continue

        if continued:
            index, record, record_errors = _parse_continued_record(
                path, lines, index, value, line_number
            )
            if record is not None:
                records.append(record)
            errors.extend(record_errors)
            continue

        record, error = _parse_record(path, value, line_number, ())
        if record is not None:
            records.append(record)
        if error is not None:
            errors.append(error)
        index += 1

    return RequirementParseResult(path, tuple(records), tuple(errors))
