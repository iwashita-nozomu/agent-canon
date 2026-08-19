# @dependency-start
# contract test
# responsibility Tests full-list validation before public test command execution.
# upstream implementation ../../test/testrunner.py typed schema owner
# downstream implementation ./test_testrunner.py tests execution receipts
# @dependency-end

"""Schema and fail-before-run tests for the source-owned test list."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "agent_canon_test_runner", PROJECT_ROOT / "test" / "testrunner.py"
)
assert SPEC is not None and SPEC.loader is not None
testrunner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = testrunner
SPEC.loader.exec_module(testrunner)


def valid_record(command: list[str] | None = None) -> dict[str, object]:
    """Return one valid record mapping."""
    return {
        "id": "valid",
        "environment": "product",
        "require": "docker",
        "code_owner": "test/testrunner.py",
        "responsibility_scope": "repository-test-runner",
        "command": command or ["python3", "-c", "raise SystemExit(0)"],
    }


def write_list(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    """Write records as simple TOML tables."""
    lines: list[str] = []
    for record in records:
        lines.append("[[tests]]")
        for key, value in record.items():
            lines.append(f"{key} = {json.dumps(value)}")
        lines.append("")
    path = tmp_path / "testlist.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_comments_and_complete_record_are_accepted(tmp_path: Path) -> None:
    """TOML comments are supported without changing the typed record."""
    path = write_list(tmp_path, [valid_record()])
    path.write_text(
        "# operator comment\n" + path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    records = testrunner.load_records(PROJECT_ROOT, path)

    assert len(records) == 1
    assert records[0].record_id == "valid"
    assert records[0].command[:2] == ("python3", "-c")


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda item: {**item, "unexpected": "field"}, "fields must be exactly"),
        (lambda item: {**item, "environment": "mixed"}, "environment must be"),
        (lambda item: {**item, "require": "host"}, "require must be"),
        (lambda item: {**item, "code_owner": "../outside"}, "code_owner escapes"),
        (
            lambda item: {**item, "code_owner": "missing.py"},
            "code_owner does not exist",
        ),
        (lambda item: {**item, "command": []}, "command must be"),
        (
            lambda item: {**item, "responsibility_scope": ""},
            "responsibility_scope must be",
        ),
    ),
)
def test_invalid_record_is_rejected(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    """Every invalid field fails before execution."""
    assert callable(mutation)
    path = write_list(tmp_path, [mutation(valid_record())])

    with pytest.raises(testrunner.SchemaError, match=message):
        testrunner.load_records(PROJECT_ROOT, path)


def test_duplicate_ids_are_rejected_before_execution(tmp_path: Path) -> None:
    """Duplicate record identity cannot overwrite lifecycle output."""
    path = write_list(tmp_path, [valid_record(), valid_record()])

    with pytest.raises(testrunner.SchemaError, match="duplicate test id"):
        testrunner.load_records(PROJECT_ROOT, path)


def test_empty_or_malformed_list_is_rejected(tmp_path: Path) -> None:
    """The list must provide one nonempty array of complete records."""
    empty = tmp_path / "empty.toml"
    empty.write_text("tests = []\n", encoding="utf-8")
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("[[tests]\n", encoding="utf-8")

    with pytest.raises(testrunner.SchemaError, match="at least one"):
        testrunner.load_records(PROJECT_ROOT, empty)
    with pytest.raises(testrunner.SchemaError, match="cannot load test list"):
        testrunner.load_records(PROJECT_ROOT, malformed)
