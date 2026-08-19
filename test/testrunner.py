#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates and executes the source-owned typed test list.
# upstream design ../CONTAINER_OPERATIONS.md public standalone test boundary
# upstream implementation ./testlist.toml declares test commands and responsibility metadata
# downstream implementation ../tests/tools/test_testrunner.py verifies execution receipts
# downstream implementation ../tests/tools/test_testrunner_schema.py verifies fail-before-run validation
# @dependency-end

"""Execute source-owned test commands and emit responsibility-aware JSON records."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ALLOWED_ENVIRONMENTS = frozenset({"product", "tooling"})
ALLOWED_REQUIREMENTS = frozenset({"docker", "devcontainer"})
RECORD_FIELDS = frozenset(
    {"id", "environment", "require", "code_owner", "responsibility_scope", "command"}
)


class SchemaError(ValueError):
    """Raised before execution when the typed test list is malformed."""


@dataclass(frozen=True)
class TestRecord:
    """One validated source-owned test command."""

    record_id: str
    environment: str
    requirement: str
    code_owner: str
    responsibility_scope: str
    command: tuple[str, ...]

    def common_receipt(self) -> dict[str, object]:
        """Return metadata shared by every lifecycle receipt."""
        return {
            "id": self.record_id,
            "argv": list(self.command),
            "environment": self.environment,
            "require": self.requirement,
            "code_owner": self.code_owner,
            "responsibility_scope": self.responsibility_scope,
        }


def _text(mapping: Mapping[str, object], field: str, record_id: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise SchemaError(f"record {record_id!r}: {field} must be a non-empty string")
    return value


def load_records(source_root: Path, list_path: Path) -> tuple[TestRecord, ...]:
    """Load and fully validate all records before any command starts."""
    try:
        payload = tomllib.loads(list_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise SchemaError(f"cannot load test list {list_path}: {exc}") from exc
    if set(payload) != {"tests"} or not isinstance(payload["tests"], list):
        raise SchemaError("test list must contain exactly one [[tests]] array")

    records: list[TestRecord] = []
    identifiers: set[str] = set()
    for index, value in enumerate(payload["tests"]):
        if not isinstance(value, Mapping):
            raise SchemaError(f"tests[{index}] must be a table")
        if set(value) != RECORD_FIELDS:
            raise SchemaError(
                f"tests[{index}] fields must be exactly {sorted(RECORD_FIELDS)!r}"
            )
        record_id = _text(value, "id", f"tests[{index}]")
        if record_id in identifiers:
            raise SchemaError(f"duplicate test id: {record_id}")
        identifiers.add(record_id)
        environment = _text(value, "environment", record_id)
        if environment not in ALLOWED_ENVIRONMENTS:
            raise SchemaError(
                f"record {record_id!r}: environment must be product or tooling"
            )
        requirement = _text(value, "require", record_id)
        if requirement not in ALLOWED_REQUIREMENTS:
            raise SchemaError(
                f"record {record_id!r}: require must be docker or devcontainer"
            )
        code_owner = _text(value, "code_owner", record_id)
        owner_path = (source_root / code_owner).resolve()
        try:
            owner_path.relative_to(source_root)
        except ValueError as exc:
            raise SchemaError(
                f"record {record_id!r}: code_owner escapes source root"
            ) from exc
        if not owner_path.exists():
            raise SchemaError(
                f"record {record_id!r}: code_owner does not exist: {code_owner}"
            )
        responsibility_scope = _text(value, "responsibility_scope", record_id)
        raw_command = value.get("command")
        if (
            not isinstance(raw_command, list)
            or not raw_command
            or not all(
                isinstance(token, str) and token and "\x00" not in token
                for token in raw_command
            )
        ):
            raise SchemaError(
                f"record {record_id!r}: command must be a non-empty string token array"
            )
        records.append(
            TestRecord(
                record_id=record_id,
                environment=environment,
                requirement=requirement,
                code_owner=code_owner,
                responsibility_scope=responsibility_scope,
                command=tuple(raw_command),
            )
        )
    if not records:
        raise SchemaError("test list must declare at least one record")
    return tuple(records)


def emit(payload: Mapping[str, object]) -> None:
    """Write one stable JSON receipt to stdout."""
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def execute(records: Sequence[TestRecord], source_root: Path, requirement: str) -> int:
    """Execute every selected record and retain exact failure ownership metadata."""
    selected = [record for record in records if record.requirement == requirement]
    for record in records:
        if record.requirement != requirement:
            emit(
                {**record.common_receipt(), "status": "not_selected", "exit_code": None}
            )
    if not selected:
        raise SchemaError(f"active requirement {requirement!r} selects no test records")

    failures = 0
    for record in selected:
        emit({**record.common_receipt(), "status": "start", "exit_code": None})
        try:
            completed = subprocess.run(
                record.command,
                cwd=source_root,
                env=os.environ.copy(),
                check=False,
                stdout=sys.stderr,
                stderr=sys.stderr,
            )
            exit_code = int(completed.returncode)
        except OSError as exc:
            print(
                f"testrunner: command start failed for {record.record_id}: {exc}",
                file=sys.stderr,
            )
            exit_code = 127
        status = "pass" if exit_code == 0 else "fail"
        failures += int(exit_code != 0)
        emit({**record.common_receipt(), "status": status, "exit_code": exit_code})
    return 0 if failures == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--test-list", required=True)
    parser.add_argument(
        "--require", choices=sorted(ALLOWED_REQUIREMENTS), required=True
    )
    return parser


def fail(message: str) -> NoReturn:
    print(f"testrunner: schema failure: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_root = Path(args.source_root).resolve()
    list_path = Path(args.test_list).resolve()
    try:
        records = load_records(source_root, list_path)
        return execute(records, source_root, args.require)
    except SchemaError as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
