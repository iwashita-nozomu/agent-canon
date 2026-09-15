# @dependency-start
# contract test
# responsibility Verifies local Draft 2020-12 catalog schemas and native validator failures.
# upstream implementation ../../schemas/agent-canon/skill-catalog.schema.json owns skill catalog shape
# upstream implementation ../../schemas/agent-canon/skill-dependencies.schema.json owns dependency shape
# upstream implementation ../../schemas/agent-canon/tool-catalog.schema.json owns tool catalog shape
# upstream implementation ../../tools/agent/skills/skill_route_catalog.py owns explicit native validation argv
# @dependency-end
"""Focused positive/negative tests for catalog schema admission."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tools.agent.skills.skill_route_catalog import CapabilityRootError, validate_catalog_schemas

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "agent-canon"


def native_tools() -> tuple[str, str]:
    """Return the pinned native validator executables."""
    check_jsonschema = shutil.which("check-jsonschema")
    yamllint = shutil.which("yamllint")
    assert check_jsonschema is not None, "check-jsonschema is required by catalog validation"
    assert yamllint is not None, "yamllint is required by catalog validation"
    return check_jsonschema, yamllint


def test_canonical_catalogs_pass_explicit_native_validation() -> None:
    """All canonical sources pass YAML and per-file JSON Schema admission."""
    records = validate_catalog_schemas(ROOT)
    assert len(records) == 3
    assert all(item["exit_code"] == 0 for item in records)


@pytest.mark.parametrize("failure", [None, "missing", "yaml", "schema"])
def test_explicit_validation_executes_and_reports_failures(tmp_path: Path, failure: str | None) -> None:
    """Explicit checks execute afresh; missing tools and rejected input propagate."""
    success = subprocess.CompletedProcess([], 0)
    rejected = subprocess.CompletedProcess([], 1)
    outcomes = {
        None: [success] * 8,
        "missing": FileNotFoundError("yamllint"),
        "yaml": [rejected],
        "schema": [success, rejected],
    }
    with patch.object(subprocess, "run", side_effect=outcomes[failure]) as run:
        if failure is None:
            first = validate_catalog_schemas(tmp_path)
            assert validate_catalog_schemas(tmp_path) == first
            assert len(first) == 3
            assert [call.args[0][0] for call in run.call_args_list] == (
                ["yamllint"] + ["check-jsonschema"] * 3
            ) * 2
        elif failure == "missing":
            with pytest.raises(FileNotFoundError, match="yamllint"):
                validate_catalog_schemas(tmp_path)
        else:
            code = "catalog-yaml-invalid" if failure == "yaml" else "catalog-schema-invalid"
            with pytest.raises(CapabilityRootError, match=code):
                validate_catalog_schemas(tmp_path)


def test_schema_refs_are_local_only() -> None:
    """Schemas contain no remote reference resolution edges."""
    for path in SCHEMA_ROOT.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        refs = []

        def collect(value: object) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("$ref"), str):
                    refs.append(value["$ref"])
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(schema)
        assert all(ref.startswith("#/") for ref in refs), (path, refs)


def test_unknown_skill_field_is_rejected(tmp_path: Path) -> None:
    """Closed skill-family objects reject unknown fields through JSON Schema."""
    check_jsonschema, _ = native_tools()
    data = yaml.safe_load((ROOT / "agents/skills/catalog.yaml").read_text(encoding="utf-8"))
    data["skill_families"][0]["unexpected"] = True
    document = tmp_path / "catalog.yaml"
    document.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = subprocess.run(
        [check_jsonschema, "--schemafile", str(SCHEMA_ROOT / "skill-catalog.schema.json"), str(document)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unexpected" in result.stdout + result.stderr


def test_duplicate_dependency_array_value_is_rejected(tmp_path: Path) -> None:
    """Duplicate dependency references are structural uniqueItems violations."""
    check_jsonschema, _ = native_tools()
    data = yaml.safe_load((ROOT / "agents/skills/skill-dependencies.yaml").read_text(encoding="utf-8"))
    data["skill_dependencies"]["agent-orchestration"]["successors"] = ["task-routing", "task-routing"]
    document = tmp_path / "dependencies.yaml"
    document.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = subprocess.run(
        [check_jsonschema, "--schemafile", str(SCHEMA_ROOT / "skill-dependencies.schema.json"), str(document)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unique" in result.stdout + result.stderr


@pytest.mark.parametrize("field, value", [("stage_policy", "explicit_only"), ("reason", 3)])
def test_invalid_routing_fields_are_rejected_by_explicit_schema(
    tmp_path: Path, field: str, value: object
) -> None:
    """Schema authoring errors are rejected by the explicit native owner, not routing."""
    check_jsonschema, _ = native_tools()
    data = yaml.safe_load((ROOT / "agents/skills/catalog.yaml").read_text(encoding="utf-8"))
    entry = next(item for item in data["skill_families"] if item["id"] == "task-routing")
    entry["routing"][field] = value
    document = tmp_path / "catalog.yaml"
    document.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = subprocess.run(
        [check_jsonschema, "--schemafile", str(SCHEMA_ROOT / "skill-catalog.schema.json"), str(document)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert field in result.stdout + result.stderr


def test_wrong_tool_entry_type_is_rejected(tmp_path: Path) -> None:
    """Tool entry booleans remain closed and typed by the native schema."""
    check_jsonschema, _ = native_tools()
    data = yaml.safe_load((ROOT / "tools/catalog.yaml").read_text(encoding="utf-8"))
    data["entries"][0]["writes"] = "false"
    document = tmp_path / "tools.yaml"
    document.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = subprocess.run(
        [check_jsonschema, "--schemafile", str(SCHEMA_ROOT / "tool-catalog.schema.json"), str(document)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "false" in result.stdout + result.stderr
