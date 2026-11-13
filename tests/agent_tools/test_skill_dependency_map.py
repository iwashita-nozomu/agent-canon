"""Independent CLI oracles for native skill-dependency graph generation."""

# @dependency-start
# contract test
# responsibility Verifies the public native graph writer and its external/source boundaries.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/catalog/skill_dependency_graph.rs owns graph construction, serialization, and writing
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/source_mutation.rs owns capability-bound tracked writes
# upstream design ../../documents/design/skill-tool-invocation-graph.md owns graph identity and readback clauses
# downstream implementation ../../documents/runtime/skill-dependency-graph.json is the generated machine-readable graph projection
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is the generated Mermaid reader projection
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_MARKDOWN = Path("documents/runtime/skill-dependency-graph.md")
GRAPH_JSON = Path("documents/runtime/skill-dependency-graph.json")
GRAPH_SCHEMA = "agent_canon.skill_tool_invocation_graph.v2"


def _native_cli() -> str:
    selected = os.environ.get("AGENT_CANON_CLI")
    if not selected:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return selected


def _copy_graph_inputs(root: Path) -> None:
    for relative in (
        "agents/skills/catalog.yaml",
        "agents/skills/skill-dependencies.yaml",
        "agents/canonical/skills.md",
        "documents/design/skill-tool-invocation-graph.md",
        GRAPH_MARKDOWN.as_posix(),
        GRAPH_JSON.as_posix(),
    ):
        source = PROJECT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mode & 0o777,
        )
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    }


def _run(
    root: Path,
    command: str,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _native_cli(),
            "skill-dependency-map",
            command,
            "--root",
            str(root),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _capability(path: Path, allowed_paths: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "allowed_paths": allowed_paths,
                "purpose": "refresh the canonical graph reader pair",
                "authority": "test-maintainer",
            }
        ),
        encoding="utf-8",
    )


def _assert_graph_identity_projection(graph: dict[str, Any]) -> None:
    records = graph["identity_records"]
    assert isinstance(records, list)
    keys = {(record["kind"], record["id"]) for record in records}
    payloads = {
        (
            record["kind"],
            json.dumps(
                record["canonical_payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for record in records
    }
    assert len(keys) == len(records)
    assert len(payloads) == len(records)
    records_by_id = {record["id"]: record for record in records}
    for field in ("skills", "phases", "commands", "tools", "capabilities"):
        for entry in graph[field]:
            expected = {"ref", "display_label"}
            if "order" in entry:
                expected.add("order")
            if field == "skills":
                expected.add("kind")
            assert set(entry) == expected
            reference = entry["ref"]
            assert records_by_id[reference["id"]]["digest"] == reference["digest"]
            assert "canonical_payload" not in entry
    for edge in graph["edges"]:
        for field in ("edge_ref", "source_ref", "target_ref"):
            reference = edge[field]
            assert records_by_id[reference["id"]]["digest"] == reference["digest"]


def test_graph_output_requires_an_explicit_external_runtime(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _copy_graph_inputs(root)
    before = _tree_snapshot(root)
    environment = os.environ.copy()
    environment.pop("AGENT_CANON_RUNTIME_ROOT", None)

    result = _run(root, "graph", env=environment)

    assert result.returncode == 2
    assert "runtime_root_required" in result.stderr
    assert _tree_snapshot(root) == before


def test_graph_writer_publishes_external_pair_without_changing_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    runtime = tmp_path / "runtime"
    root.mkdir()
    _copy_graph_inputs(root)
    before = _tree_snapshot(root)

    result = _run(root, "graph", "--runtime-root", str(runtime))

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SKILL_TOOL_INVOCATION_GRAPH=pass" in result.stdout
    markdown = runtime / "graphs/skill-dependency-graph.md"
    machine = runtime / "graphs/skill-dependency-graph.json"
    assert markdown.is_file()
    assert machine.is_file()
    graph = json.loads(machine.read_text(encoding="utf-8"))
    expected = json.loads(
        (
            PROJECT_ROOT / "tests/fixtures/skill_dependency_graph/expected.json"
        ).read_text(encoding="utf-8")
    )
    assert graph["schema"] == GRAPH_SCHEMA
    assert graph["skill_count"] == expected["skill_count"] == len(graph["skills"])
    assert len(graph["commands"]) == expected["command_count"]
    assert len(graph["tools"]) == expected["tool_count"]
    assert len(graph["edges"]) == expected["edge_count"]
    assert graph["phases"] == []
    assert graph["commands"] == []
    assert graph["tools"] == []
    assert "capability:code-visualization:dependency_manifest_graph" in {
        item["ref"]["id"] for item in graph["capabilities"]
    }
    _assert_graph_identity_projection(graph)
    serialized = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    assert str(root.resolve()) not in serialized
    assert "execution_argv" not in serialized
    mermaid = markdown.read_text(encoding="utf-8")
    assert mermaid.count("```mermaid") == 1
    assert "base64" not in mermaid.lower()
    assert _tree_snapshot(root) == before


def test_tracked_graph_pair_requires_exact_capability_and_external_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    runtime = tmp_path / "runtime"
    root.mkdir()
    _copy_graph_inputs(root)
    (root / GRAPH_MARKDOWN).write_text("before\n", encoding="utf-8")
    (root / GRAPH_JSON).write_text("before\n", encoding="utf-8")
    capability = tmp_path / "capability.json"
    _capability(capability, [GRAPH_JSON.as_posix(), GRAPH_MARKDOWN.as_posix()])
    before = _tree_snapshot(root)

    result = _run(
        root,
        "graph",
        "--output",
        GRAPH_MARKDOWN.as_posix(),
        "--runtime-root",
        str(runtime),
        "--source-mutation-capability-json",
        str(capability),
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    after = _tree_snapshot(root)
    changed = {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    }
    assert changed == {GRAPH_MARKDOWN.as_posix(), GRAPH_JSON.as_posix()}
    evidence_path = runtime / "graphs/skill-dependency-graph-source-mutation.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["schema"] == "agent_canon.skill_graph_source_mutation.v1"
    assert evidence["allowed_paths"] == [
        GRAPH_MARKDOWN.as_posix(),
        GRAPH_JSON.as_posix(),
    ]
    assert set(evidence["changed_paths"]) == changed
    checker = subprocess.run(
        [_native_cli(), "check-skill-tool-invocation-graph", "--root", str(root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checker.returncode == 0, checker.stdout + checker.stderr
    markdown = root / GRAPH_MARKDOWN
    generated = markdown.read_text(encoding="utf-8")
    edge_line = next(
        line
        for line in generated.splitlines()
        if line.lstrip().startswith("n_") and "-->" in line
    )
    markdown.write_text(generated.replace(f"{edge_line}\n", "", 1), encoding="utf-8")
    stale = _run(root, "check")
    assert stale.returncode == 2
    assert "readback" in stale.stderr


def test_tracked_graph_writer_rejects_capability_for_an_unrelated_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    runtime = tmp_path / "runtime"
    root.mkdir()
    _copy_graph_inputs(root)
    capability = tmp_path / "capability.json"
    _capability(capability, ["README.md"])
    before = _tree_snapshot(root)

    result = _run(
        root,
        "graph",
        "--output",
        GRAPH_MARKDOWN.as_posix(),
        "--runtime-root",
        str(runtime),
        "--source-mutation-capability-json",
        str(capability),
    )

    assert result.returncode == 2
    assert "source_mutation_capability_target_mismatch" in result.stderr
    assert _tree_snapshot(root) == before


def test_explicit_dependency_order_constraint_materializes_an_order_edge(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    runtime = tmp_path / "runtime"
    root.mkdir()
    _copy_graph_inputs(root)
    dependency_path = root / "agents/skills/skill-dependencies.yaml"
    dependency_map = yaml.safe_load(dependency_path.read_text(encoding="utf-8"))
    dependency_map["skill_dependencies"]["repo-onboarding"]["order_constraints"] = [
        {
            "before": "repo-onboarding",
            "after": "start-repository",
            "reason": "independent native graph oracle",
        }
    ]
    dependency_path.write_text(
        yaml.safe_dump(dependency_map, sort_keys=False), encoding="utf-8"
    )

    result = _run(root, "graph", "--runtime-root", str(runtime))

    assert result.returncode == 0, result.stdout + result.stderr
    graph = json.loads(
        (runtime / "graphs/skill-dependency-graph.json").read_text(encoding="utf-8")
    )
    order_edges = [
        (edge["source_ref"]["id"], edge["target_ref"]["id"])
        for edge in graph["edges"]
        if edge["display_label"] == "order"
    ]
    assert order_edges == [("skill:repo-onboarding", "skill:start-repository")]
    invocation_order = [record["ref"]["id"] for record in graph["invocation_order"]]
    assert invocation_order.index("skill:repo-onboarding") < invocation_order.index(
        "skill:start-repository"
    )
