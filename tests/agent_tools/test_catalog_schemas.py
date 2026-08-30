# @dependency-start
# contract test
# responsibility Verifies local Draft 2020-12 catalog schemas and native validator failures.
# upstream implementation ../../schemas/agent-canon/skill-catalog.schema.json owns skill catalog shape
# upstream implementation ../../schemas/agent-canon/skill-dependencies.schema.json owns dependency shape
# upstream implementation ../../schemas/agent-canon/tool-catalog.schema.json owns tool catalog shape
# upstream implementation ../../tools/agent/skills/skill_route_catalog.py owns native preflight argv
# @dependency-end
"""Focused positive/negative tests for catalog schema admission."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from tools.agent.skills.skill_route_catalog import validate_catalog_schemas

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "agent-canon"


def native_tools() -> tuple[str, str]:
    """Return the pinned native validator executables."""
    check_jsonschema = shutil.which("check-jsonschema")
    yamllint = shutil.which("yamllint")
    assert check_jsonschema is not None, "check-jsonschema is required by catalog validation"
    assert yamllint is not None, "yamllint is required by catalog validation"
    return check_jsonschema, yamllint


def test_canonical_catalogs_pass_native_preflight() -> None:
    """All canonical sources pass YAML and per-file JSON Schema admission."""
    records = validate_catalog_schemas(ROOT)
    assert len(records) == 3
    assert all(item["exit_code"] == 0 for item in records)


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
    data["skill_dependencies"]["agent-orchestration"]["successors"].append("task-routing")
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
