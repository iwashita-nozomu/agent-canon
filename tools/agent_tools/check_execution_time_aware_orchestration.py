#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enforces the machine-readable execution-time-aware orchestration contract and its exact consumer projections.
# upstream design ../../agents/skills/agent-orchestration.execution-contract.toml canonical machine contract
# upstream design ../../agents/skills/agent-orchestration.md sole execution-time-aware policy owner
# upstream implementation ./skill_tool_commands.py selected-skill required-command packet owner
# downstream implementation ../../tests/agent_tools/test_execution_time_aware_orchestration_contract.py negative contract tests
# downstream implementation ../catalog.yaml production tool registry
# @dependency-end
"""Check the canonical execution-time-aware orchestration owner closure."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

try:  # pragma: no cover - Python 3.11+ uses the standard library path.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for older runners.
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = Path("agents/skills/agent-orchestration.execution-contract.toml")
OWNER_REF = (
    "agents/skills/agent-orchestration.md#"
    "Execution-Time-Aware Work-Conservation Contract"
)
EXPECTED_SCHEMA = "agent-canon.execution-time-aware-orchestration.v1"
EXPECTED_OWNER_SKILL = "agent-orchestration"
EXPECTED_ACTIVATION_PREDICATE = "selected_edge_type_present"
EXPECTED_DEFAULT_STATE = "bounded_single_owner"
EXPECTED_CANDIDATE_COUNT_ALONE = False
EXPECTED_SELECTED_EDGE_TYPES = (
    "ordering",
    "dependency",
    "collision",
    "publication",
)
EXPECTED_ALWAYS_REQUIRED_FIELDS = (
    "owner",
    "schema",
    "dependency",
    "validation",
    "correctness",
    "publication_scope",
)
EXPECTED_GRAPH_ONLY_FIELDS = (
    "dag",
    "critical_path",
    "ready_set",
    "queue_snapshot",
    "makespan_objective",
)
EXPECTED_TASK_CATALOG_FIELDS = (
    "dependency_dag",
    "responsibility_completeness",
    "correctness",
    "context_reuse",
    "affected_evidence_invalidation",
)
EXPECTED_REJECTED_CLASSES = (
    "duplicate_local_scheduling_definition",
    "duration_or_timeout_scope_cutoff",
    "keyword_based_routing",
    "responsibility_scope_reduction",
    "consumer_reference_without_executable_fields",
    "consumer_reference_mismatch",
)
EXPECTED_INVARIANTS = {
    "activation": "selected_edge_type_present",
    "default": "bounded_single_owner",
    "candidate_count": "candidate_count_alone_false",
    "always": "owner_schema_dependency_validation_correctness_publication_scope",
    "graph": "dag_critical_path_ready_set_queue_snapshot_makespan_objective",
    "dispatch": "all_non_conflicting_ready_nodes",
    "wait": "only_when_useful_ready_set_is_empty",
    "evidence": "warm_context_reuse_and_affected_evidence_only_invalidation",
    "review": "closure_before_one_exact_candidate_review",
    "scope": "no_timeout_elapsed_time_or_capacity_cutoff",
}
EXPECTED_CONSUMERS = {
    "pr-processing": {
        "path": "agents/skills/pr-processing.md",
        "kind": "specialization",
        "reference_mode": "text",
    },
    "task-catalog": {
        "path": "agents/task_catalog.yaml",
        "kind": "structured_reference",
        "reference_mode": "yaml",
    },
    "schedule": {
        "path": "templates/agents/schedule.md",
        "kind": "schedule_projection",
        "reference_mode": "text",
    },
    "runtime-shim": {
        "path": ".agents/skills/agent-orchestration/SKILL.md",
        "kind": "runtime_reference",
        "reference_mode": "reference",
    },
}


@dataclass(frozen=True)
class Finding:
    """One stable contract finding."""

    category: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one machine-readable text finding."""
        return f"EXECUTION_TIME_AWARE_ORCHESTRATION_FINDING={self.category}:{self.path}:{self.detail}"


def normalize(text: str) -> str:
    """Collapse Markdown/YAML whitespace for exact semantic marker checks."""
    return " ".join(text.split()).lower()


def add(
    findings: list[Finding],
    category: str,
    path: str,
    detail: str,
) -> None:
    """Append one finding without hiding the first failure in a category."""
    findings.append(Finding(category, path, detail))


def read_text(root: Path, relative_path: str) -> str:
    """Read one required consumer/owner path."""
    return (root / relative_path).read_text(encoding="utf-8")


def nested_mapping(value: Any, path: tuple[str, ...]) -> Any:
    """Read one exact nested YAML value, returning None when absent."""
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def yaml_catalog(root: Path) -> Any:
    """Load the public skill catalog for required-command route checks."""
    path = root / "agents/skills/catalog.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"catalog-load:{exc}") from exc


def catalog_skill(root: Path, skill: str) -> dict[str, Any] | None:
    """Return one exact public skill catalog entry."""
    data = yaml_catalog(root)
    families = data.get("skill_families") if isinstance(data, dict) else None
    if not isinstance(families, list):
        return None
    matches = [entry for entry in families if isinstance(entry, dict) and entry.get("id") == skill]
    if len(matches) != 1:
        return None
    return matches[0]


def _non_empty(value: Any) -> bool:
    """Return whether one graph evidence value is materially present."""
    if value is None or value is False:
        return False
    if isinstance(value, (str, bytes)):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def classify_execution_route(
    decision: Any,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one explicit execution decision without inferring from count.

    The classifier is deliberately independent from repository prose.  A
    decision remains bounded single-owner unless a selected edge type is
    present.  Once a selected edge is present, every graph-only evidence field
    is required and malformed edge/node references are rejected.
    """
    contract_values = contract or {}
    edge_types = tuple(contract_values.get("selected_edge_types", EXPECTED_SELECTED_EDGE_TYPES))
    graph_fields = tuple(contract_values.get("graph_only_fields", EXPECTED_GRAPH_ONLY_FIELDS))
    default_state = str(contract_values.get("default_state", EXPECTED_DEFAULT_STATE))
    findings: list[Finding] = []
    if not isinstance(decision, dict):
        findings.append(Finding("execution_graph", "decision", "decision-not-mapping"))
        return {
            "status": "reject",
            "state": default_state,
            "graph_active": False,
            "active_edge_types": [],
            "findings": [asdict(item) for item in findings],
        }

    nodes = decision.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        findings.append(Finding("execution_graph", "decision", "missing-nodes"))
        return {
            "status": "reject",
            "state": default_state,
            "graph_active": False,
            "active_edge_types": [],
            "findings": [asdict(item) for item in findings],
        }
    node_ids: list[str] = []
    for index, node in enumerate(nodes):
        node_id = node.get("id") if isinstance(node, dict) else node
        if not isinstance(node_id, str) or not node_id:
            findings.append(Finding("execution_graph", f"nodes[{index}]", "invalid-node-id"))
        elif node_id in node_ids:
            findings.append(Finding("execution_graph", f"nodes[{index}]", "duplicate-node-id"))
        else:
            node_ids.append(node_id)

    edges = decision.get("edges", [])
    if not isinstance(edges, list):
        findings.append(Finding("execution_graph", "edges", "invalid-edges"))
        edges = []
    active_edges: list[dict[str, Any]] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            findings.append(Finding("execution_graph", f"edges[{index}]", "invalid-edge"))
            continue
        selected = edge.get("selected", True)
        if not isinstance(selected, bool):
            findings.append(Finding("execution_graph", f"edges[{index}]", "invalid-selected-flag"))
            continue
        edge_type = edge.get("type", edge.get("edge_type"))
        if not selected or edge_type not in edge_types:
            continue
        source = edge.get("source")
        target = edge.get("target")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in node_ids
            or target not in node_ids
            or source == target
        ):
            findings.append(Finding("execution_graph", f"edges[{index}]", "invalid-selected-edge"))
            continue
        active_edges.append(edge)

    if findings:
        return {
            "status": "reject",
            "state": default_state,
            "graph_active": False,
            "active_edge_types": sorted({str(edge.get("type", edge.get("edge_type"))) for edge in active_edges}),
            "findings": [asdict(item) for item in findings],
        }

    if not active_edges:
        return {
            "status": "pass",
            "state": default_state,
            "graph_active": False,
            "candidate_count": len(node_ids),
            "active_edge_types": [],
            "graph_fields": [],
            "findings": [],
        }

    graph = decision.get("graph_evidence")
    if not isinstance(graph, dict):
        findings.append(Finding("execution_graph", "graph_evidence", "missing-graph-evidence"))
    else:
        for field in graph_fields:
            if field not in graph or not _non_empty(graph[field]):
                findings.append(Finding("execution_graph", "graph_evidence", f"missing-or-invalid:{field}"))
        scoped_nodes = graph.get("node_ids")
        if scoped_nodes is not None:
            if not isinstance(scoped_nodes, list) or any(
                not isinstance(node_id, str) or node_id not in node_ids for node_id in scoped_nodes
            ):
                findings.append(Finding("execution_graph", "graph_evidence.node_ids", "outside-selected-subgraph"))

    if findings:
        return {
            "status": "reject",
            "state": "selected_edge_graph",
            "graph_active": True,
            "candidate_count": len(node_ids),
            "active_edge_types": sorted({str(edge.get("type", edge.get("edge_type"))) for edge in active_edges}),
            "findings": [asdict(item) for item in findings],
        }
    return {
        "status": "pass",
        "state": "selected_edge_graph",
        "graph_active": True,
        "candidate_count": len(node_ids),
        "active_edge_types": sorted({str(edge.get("type", edge.get("edge_type"))) for edge in active_edges}),
        "graph_fields": list(graph_fields),
        "findings": [],
    }


def check_contract(root: Path, contract_path: Path) -> list[Finding]:
    """Validate the canonical contract, owner, route, and all projections."""
    findings: list[Finding] = []
    contract_label = contract_path.relative_to(root).as_posix()
    try:
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        add(findings, "contract_schema", contract_label, f"parse:{exc}")
        return findings

    if contract.get("schema") != EXPECTED_SCHEMA:
        add(findings, "contract_schema", contract_label, "schema-mismatch")
    if contract.get("owner_skill") != EXPECTED_OWNER_SKILL:
        add(findings, "single_owner_semantics", contract_label, "owner-skill-mismatch")
    if contract.get("owner_doc") != OWNER_REF.split("#", 1)[0]:
        add(findings, "single_owner_semantics", contract_label, "owner-doc-mismatch")
    if contract.get("owner_heading") != OWNER_REF.split("#", 1)[1]:
        add(findings, "single_owner_semantics", contract_label, "owner-heading-mismatch")
    if contract.get("owner_ref") != OWNER_REF:
        add(findings, "consumer_reference_mismatch", contract_label, "owner-ref-mismatch")

    checker = contract.get("checker")
    checker_command = contract.get("checker_command")
    required_skill_command = contract.get("required_skill_command")
    expected_command = "python3 tools/agent_tools/check_execution_time_aware_orchestration.py --root ."
    if checker != "tools/agent_tools/check_execution_time_aware_orchestration.py":
        add(findings, "contract_schema", contract_label, "checker-path-mismatch")
    if checker_command != expected_command or required_skill_command != expected_command:
        add(findings, "required_command_route", contract_label, "checker-command-mismatch")
    if checker_command != required_skill_command:
        add(findings, "required_command_route", contract_label, "checker-command-not-identical")

    if contract.get("activation_predicate") != EXPECTED_ACTIVATION_PREDICATE:
        add(findings, "contract_schema", contract_label, "activation-predicate-mismatch")
    if contract.get("default_state") != EXPECTED_DEFAULT_STATE:
        add(findings, "contract_schema", contract_label, "default-state-mismatch")
    if contract.get("candidate_count_alone") is not EXPECTED_CANDIDATE_COUNT_ALONE:
        add(findings, "contract_schema", contract_label, "candidate-count-policy-mismatch")
    if tuple(contract.get("selected_edge_types", ())) != EXPECTED_SELECTED_EDGE_TYPES:
        add(findings, "contract_schema", contract_label, "selected-edge-types-mismatch")
    always_fields = tuple(contract.get("always_required_fields", ()))
    if always_fields != EXPECTED_ALWAYS_REQUIRED_FIELDS or len(set(always_fields)) != len(always_fields):
        add(findings, "consumer_reference_without_executable_fields", contract_label, "always-fields-mismatch")
    graph_fields = tuple(contract.get("graph_only_fields", ()))
    if graph_fields != EXPECTED_GRAPH_ONLY_FIELDS or len(set(graph_fields)) != len(graph_fields):
        add(findings, "consumer_reference_without_executable_fields", contract_label, "graph-fields-mismatch")
    task_catalog_fields = tuple(contract.get("task_catalog_fields", ()))
    if task_catalog_fields != EXPECTED_TASK_CATALOG_FIELDS or len(set(task_catalog_fields)) != len(task_catalog_fields):
        add(findings, "consumer_reference_without_executable_fields", contract_label, "task-catalog-fields-mismatch")
    rejected = tuple(contract.get("rejected_classes", ()))
    if rejected != EXPECTED_REJECTED_CLASSES or len(set(rejected)) != len(rejected):
        add(findings, "contract_schema", contract_label, "rejected-classes-mismatch")
    invariants = contract.get("invariants")
    if invariants != EXPECTED_INVARIANTS:
        add(findings, "contract_schema", contract_label, "invariants-mismatch")

    owner_path = contract.get("owner_doc")
    if isinstance(owner_path, str):
        owner_file = root / owner_path
        if not owner_file.is_file():
            add(findings, "single_owner_semantics", owner_path, "owner-missing")
        else:
            owner_text = read_text(root, owner_path)
            heading = f"## {OWNER_REF.split('#', 1)[1]}"
            if owner_text.count(heading) != 1:
                add(findings, "single_owner_semantics", owner_path, "owner-heading-count")
            owner_normalized = normalize(owner_text)
            for marker in contract.get("owner_markers", ()):
                if normalize(str(marker)) not in owner_normalized:
                    add(findings, "owner_contract", owner_path, f"missing-marker:{marker}")

    contract_checker = root / str(checker)
    if not contract_checker.is_file():
        add(findings, "contract_schema", str(checker), "checker-missing")

    consumers = contract.get("consumers")
    if not isinstance(consumers, list):
        add(findings, "contract_schema", contract_label, "consumers-not-list")
        return findings
    consumer_ids = tuple(
        item.get("id") for item in consumers if isinstance(item, dict)
    )
    if consumer_ids != tuple(EXPECTED_CONSUMERS):
        add(findings, "consumer_reference_mismatch", contract_label, "consumer-set-mismatch")

    consumer_texts: dict[str, str] = {}
    for item in consumers:
        if not isinstance(item, dict):
            add(findings, "contract_schema", contract_label, "consumer-not-mapping")
            continue
        consumer_id = item.get("id")
        path = item.get("path")
        if not isinstance(consumer_id, str) or not isinstance(path, str):
            add(findings, "consumer_reference_mismatch", contract_label, "consumer-id-or-path-missing")
            continue
        expected = EXPECTED_CONSUMERS.get(consumer_id)
        if expected is None or any(item.get(key) != value for key, value in expected.items()):
            add(findings, "consumer_reference_mismatch", path, "consumer-shape-mismatch")
        if not (root / path).is_file():
            add(findings, "consumer_reference_mismatch", path, "consumer-missing")
            continue
        text = read_text(root, path)
        consumer_texts[consumer_id] = text
        normalized = normalize(text)
        if item.get("reference_mode") == "text":
            count = text.count(OWNER_REF)
            if count != 1:
                add(findings, "consumer_reference_mismatch", path, f"owner-ref-count:{count}")
            for field in item.get("required_fields", ()):
                if field not in normalized:
                    add(findings, "consumer_reference_without_executable_fields", path, f"missing-field:{field}")
        for marker in item.get("required_markers", ()):
            if normalize(str(marker)) not in normalized:
                add(findings, "consumer_reference_without_executable_fields", path, f"missing-marker:{marker}")

        for marker in contract.get("forbidden_consumer_markers", ()):
            if normalize(str(marker)) in normalized:
                add(findings, "duplicate_local_scheduling_definition", path, f"forbidden-policy-marker:{marker}")
        for marker in contract.get("scope_cutoff_markers", ()):
            if normalize(str(marker)) in normalized:
                add(findings, "duration_or_timeout_scope_cutoff", path, f"scope-cutoff-marker:{marker}")
        for marker in contract.get("keyword_routing_markers", ()):
            if normalize(str(marker)) in normalized:
                add(findings, "keyword_based_routing", path, f"keyword-routing-marker:{marker}")
        for marker in contract.get("scope_reduction_markers", ()):
            if normalize(str(marker)) in normalized:
                add(findings, "responsibility_scope_reduction", path, f"scope-reduction-marker:{marker}")

    owner_heading = str(contract.get("duplicate_definition_heading", ""))
    if owner_heading:
        for path, text in ((str(contract.get("owner_doc")), consumer_texts.get("owner", "")),):
            if text and text.count(owner_heading) != 1:
                add(findings, "single_owner_semantics", path, "owner-definition-count")
        for consumer_id, text in consumer_texts.items():
            if consumer_id == EXPECTED_OWNER_SKILL:
                continue
            if text.count(owner_heading):
                add(findings, "duplicate_local_scheduling_definition", EXPECTED_CONSUMERS[consumer_id]["path"], "owner-definition-present")

    task_catalog = consumer_texts.get("task-catalog")
    if task_catalog is not None:
        try:
            task_data = yaml.safe_load(task_catalog)
        except yaml.YAMLError as exc:
            add(findings, "consumer_reference_mismatch", EXPECTED_CONSUMERS["task-catalog"]["path"], f"yaml-parse:{exc}")
            task_data = None
        policy = task_data.get("execution_time_policy") if isinstance(task_data, dict) else None
        if not isinstance(policy, dict):
            add(findings, "consumer_reference_mismatch", EXPECTED_CONSUMERS["task-catalog"]["path"], "execution-time-policy-missing")
        else:
            task_spec = next((item for item in consumers if isinstance(item, dict) and item.get("id") == "task-catalog"), {})
            if nested_mapping(task_data, tuple(task_spec.get("owner_ref_path", ()))) != OWNER_REF:
                add(findings, "consumer_reference_mismatch", EXPECTED_CONSUMERS["task-catalog"]["path"], "owner-ref-path-mismatch")
            if nested_mapping(task_data, tuple(task_spec.get("fields_path", ()))) != list(EXPECTED_TASK_CATALOG_FIELDS):
                add(findings, "consumer_reference_without_executable_fields", EXPECTED_CONSUMERS["task-catalog"]["path"], "executable-fields-mismatch")
            projection_path = tuple(task_spec.get("projection_path", ()))
            if nested_mapping(task_data, projection_path) != task_spec.get("projection_ref"):
                add(findings, "consumer_reference_mismatch", EXPECTED_CONSUMERS["task-catalog"]["path"], "projection-ref-mismatch")

    catalog_entry = catalog_skill(root, EXPECTED_OWNER_SKILL)
    expected_command = str(required_skill_command)
    if catalog_entry is None:
        add(findings, "required_command_route", "agents/skills/catalog.yaml", "agent-orchestration-entry-missing")
    else:
        tool_commands = catalog_entry.get("tool_commands")
        required_commands = tool_commands.get("required") if isinstance(tool_commands, dict) else None
        if required_commands != [expected_command] or len(set(required_commands or ())) != len(required_commands or ()):
            add(findings, "required_command_route", "agents/skills/catalog.yaml", "required-checker-command-mismatch")
        for path in (
            "agents/skills/agent-orchestration.md",
            ".agents/skills/agent-orchestration/SKILL.md",
        ):
            text = consumer_texts.get("runtime-shim") if path.startswith(".agents") else read_text(root, path)
            if expected_command in text:
                add(findings, "required_command_route", path, "checker-command-copied-from-catalog")

    return findings


def build_parser() -> argparse.ArgumentParser:
    """Build the checker command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Repository root.")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT), help="Contract path relative to root.")
    parser.add_argument(
        "--decision",
        help="Classify one explicit execution decision JSON fixture instead of checking the owner closure.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    """Run the contract checker and return a strict status code."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = root / contract_path
    if args.decision:
        try:
            contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
            decision = json.loads(Path(args.decision).read_text(encoding="utf-8"))
            route = classify_execution_route(decision, contract)
        except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError, ValueError) as exc:
            route = {
                "status": "reject",
                "state": EXPECTED_DEFAULT_STATE,
                "graph_active": False,
                "active_edge_types": [],
                "findings": [asdict(Finding("execution_graph", args.decision, f"fixture-error:{exc}"))],
            }
        if args.format == "json":
            print(json.dumps(route, indent=2, sort_keys=True))
        else:
            for item in route["findings"]:
                print(Finding(**item).render())
            print(f"EXECUTION_TIME_AWARE_ORCHESTRATION_ROUTE_STATE={route['state']}")
            print(f"EXECUTION_TIME_AWARE_ORCHESTRATION_GRAPH_ACTIVE={str(route['graph_active']).lower()}")
            print(f"EXECUTION_TIME_AWARE_ORCHESTRATION={'pass' if route['status'] == 'pass' else 'fail'}")
        return 0 if route["status"] == "pass" else 1
    try:
        findings = check_contract(root, contract_path)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        findings = [Finding("contract_schema", str(contract_path), f"checker-error:{exc}")]
    if args.format == "json":
        print(json.dumps({"status": "pass" if not findings else "fail", "findings": [asdict(item) for item in findings]}, indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(finding.render())
        print(f"EXECUTION_TIME_AWARE_ORCHESTRATION_FINDINGS={len(findings)}")
        print(f"EXECUTION_TIME_AWARE_ORCHESTRATION={'pass' if not findings else 'fail'}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
