#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enforces the machine-readable execution-time-aware orchestration contract and its exact consumer projections.
# upstream design ../../../../agents/skills/agent-orchestration.execution-contract.toml canonical machine contract
# upstream design ../../../../agents/skills/agent-orchestration.md sole execution-time-aware policy owner
# upstream implementation ../../../agent/skills/skill_tool_commands.py selected-skill required-command packet owner
# downstream implementation ../../../../tests/agent_tools/test_execution_time_aware_orchestration_contract.py negative contract tests
# downstream implementation ../../../catalog.yaml production tool registry
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


DEFAULT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONTRACT = Path("agents/skills/agent-orchestration.execution-contract.toml")
OWNER_REF = (
    "agents/skills/agent-orchestration.md#"
    "Execution-Time-Aware Work-Conservation Contract"
)
EXPECTED_SCHEMA = "agent-canon.execution-time-aware-orchestration.v3"
EXPECTED_OWNER_SKILL = "agent-orchestration"
EXPECTED_REQUIRED_FIELDS = (
    "dependency_dag",
    "responsibility_completeness",
    "correctness",
    "decision_relevant_total_work",
    "makespan_objective",
    "critical_path",
    "ready_set",
    "context_reuse",
    "affected_evidence_invalidation",
    "candidate_epoch",
    "blocking_finding_ids",
    "focused_recheck",
    "terminal_state",
)
EXPECTED_REJECTED_CLASSES = (
    "duplicate_local_scheduling_definition",
    "duration_or_timeout_scope_cutoff",
    "keyword_based_routing",
    "responsibility_scope_reduction",
    "same_state_same_action_repeat",
    "repeated_candidate_epoch",
    "evidence_ref_cycle_evasion",
    "terminal_gate_bypass",
    "advisory_rework",
    "unfocused_recheck_mutation",
    "validation_global_reopen",
    "broad_review_restart_without_new_epoch_evidence",
    "consumer_reference_without_executable_fields",
    "consumer_reference_mismatch",
)
EXPECTED_INVARIANTS = {
    "dag": "complete_dependency_dag_with_owner_and_consumer_closure",
    "objective": "lexicographic_completeness_correctness_then_decision_relevant_total_work_then_makespan",
    "dispatch": "all_non_conflicting_admissible_ready_nodes",
    "wait": "only_when_useful_ready_set_is_empty",
    "evidence": "warm_context_reuse_and_affected_evidence_only_invalidation",
    "review": "one_initial_review_per_candidate_epoch_then_focused_recheck",
    "candidate_epoch": "exact_request_candidate_identity_with_no_repeated_epoch",
    "convergence": "state_action_class_or_epoch_cycle_else_strict_measure_or_typed_decision_evidence",
    "terminal": "zero_blockers_clauses_and_validations_with_selected_validation_pass",
}
EXPECTED_CONVERGENCE = {
    "state_fields": [
        "request_digest",
        "candidate_digest",
        "candidate_epoch",
        "owner",
        "implementation_mechanism",
        "validation_route",
        "review_status",
        "blocking_finding_ids",
        "unresolved_validation_ids",
        "unresolved_request_clause_ids",
        "selected_validation_status",
        "terminal_state",
    ],
    "action_classes": [
        "initial_review",
        "repair",
        "focused_recheck",
        "clause_resolution",
        "validation",
        "advisory",
        "epoch_reopen",
        "ship",
    ],
    "decision_evidence_kinds": [
        "owner_change",
        "implementation_mechanism_change",
        "validation_route_change",
        "ship_state_change",
    ],
    "new_epoch_evidence_kinds": [
        "contract_change",
        "reachable_behavior_change",
        "structural_contradiction",
    ],
    "action_admission": [
        "one_initial_review_for_candidate_epoch",
        "typed_candidate_epoch_repair",
        "strict_unresolved_measure_decrease",
        "typed_new_epoch_evidence",
        "advisory_record_without_rework",
        "terminal_zero_measure",
    ],
    "action_fingerprint": "state_fingerprint_plus_action_class",
    "epoch_fingerprint": "request_digest_plus_candidate_digest",
    "repair_scope": "next_candidate_epoch_assigned_blockers_and_affected_validation_ids_only",
    "focused_recheck_scope": "targeted_blocker_ids_only",
    "validation_reopen_scope": "affected_validation_ids_only",
    "terminal_conditions": [
        "zero_open_blocking_findings",
        "zero_unresolved_request_clauses",
        "zero_unresolved_validation_ids",
        "selected_validation_pass_or_not_applicable",
    ],
    "cycle_stop": "non_convergent_cycle",
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
        "path": ".codex/personal/skills/agent-orchestration/SKILL.md",
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
        return (
            "EXECUTION_TIME_AWARE_ORCHESTRATION_FINDING="
            f"{self.category}:{self.path}:{self.detail}"
        )


def normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def add(
    findings: list[Finding],
    category: str,
    path: str,
    detail: str,
) -> None:
    findings.append(Finding(category, path, detail))


def read_text(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def nested_mapping(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def yaml_catalog(root: Path) -> Any:
    path = root / "agents/skills/catalog.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"catalog-load:{exc}") from exc


def catalog_skill(root: Path, skill: str) -> dict[str, Any] | None:
    data = yaml_catalog(root)
    families = data.get("skill_families") if isinstance(data, dict) else None
    if not isinstance(families, list):
        return None
    matches = [
        entry
        for entry in families
        if isinstance(entry, dict) and entry.get("id") == skill
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _check_exact_contract(
    findings: list[Finding],
    contract: dict[str, Any],
    contract_label: str,
) -> None:
    if contract.get("schema") != EXPECTED_SCHEMA:
        add(findings, "contract_schema", contract_label, "schema-mismatch")
    if contract.get("owner_skill") != EXPECTED_OWNER_SKILL:
        add(
            findings,
            "single_owner_semantics",
            contract_label,
            "owner-skill-mismatch",
        )
    if contract.get("owner_doc") != OWNER_REF.split("#", 1)[0]:
        add(
            findings,
            "single_owner_semantics",
            contract_label,
            "owner-doc-mismatch",
        )
    if contract.get("owner_heading") != OWNER_REF.split("#", 1)[1]:
        add(
            findings,
            "single_owner_semantics",
            contract_label,
            "owner-heading-mismatch",
        )
    if contract.get("owner_ref") != OWNER_REF:
        add(
            findings,
            "consumer_reference_mismatch",
            contract_label,
            "owner-ref-mismatch",
        )

    expected_command = (
        "python3 tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py --root ."
    )
    checker = contract.get("checker")
    checker_command = contract.get("checker_command")
    required_command = contract.get("required_skill_command")
    if checker != "tools/validation/semantic/orchestration/check_execution_time_aware_orchestration.py":
        add(findings, "contract_schema", contract_label, "checker-path-mismatch")
    if checker_command != expected_command or required_command != expected_command:
        add(
            findings,
            "required_command_route",
            contract_label,
            "checker-command-mismatch",
        )
    if checker_command != required_command:
        add(
            findings,
            "required_command_route",
            contract_label,
            "checker-command-not-identical",
        )

    fields = tuple(contract.get("required_fields", ()))
    if fields != EXPECTED_REQUIRED_FIELDS or len(set(fields)) != len(fields):
        add(
            findings,
            "consumer_reference_without_executable_fields",
            contract_label,
            "required-fields-mismatch",
        )
    rejected = tuple(contract.get("rejected_classes", ()))
    if rejected != EXPECTED_REJECTED_CLASSES or len(set(rejected)) != len(rejected):
        add(
            findings,
            "contract_schema",
            contract_label,
            "rejected-classes-mismatch",
        )
    if contract.get("invariants") != EXPECTED_INVARIANTS:
        add(findings, "contract_schema", contract_label, "invariants-mismatch")
    if contract.get("convergence") != EXPECTED_CONVERGENCE:
        add(findings, "contract_schema", contract_label, "convergence-mismatch")


def _check_owner(
    root: Path,
    findings: list[Finding],
    contract: dict[str, Any],
) -> None:
    owner_path = contract.get("owner_doc")
    if not isinstance(owner_path, str):
        return
    owner_file = root / owner_path
    if not owner_file.is_file():
        add(findings, "single_owner_semantics", owner_path, "owner-missing")
        return
    owner_text = read_text(root, owner_path)
    heading = f"## {OWNER_REF.split('#', 1)[1]}"
    if owner_text.count(heading) != 1:
        add(
            findings,
            "single_owner_semantics",
            owner_path,
            "owner-heading-count",
        )
    normalized = normalize(owner_text)
    for marker in contract.get("owner_markers", ()):
        if normalize(str(marker)) not in normalized:
            add(
                findings,
                "owner_contract",
                owner_path,
                f"missing-marker:{marker}",
            )


def _check_consumer_text(
    findings: list[Finding],
    contract: dict[str, Any],
    consumer_id: str,
    spec: dict[str, Any],
    text: str,
) -> None:
    path = str(spec["path"])
    normalized = normalize(text)
    if spec.get("reference_mode") == "text":
        count = text.count(OWNER_REF)
        if count != 1:
            add(
                findings,
                "consumer_reference_mismatch",
                path,
                f"owner-ref-count:{count}",
            )
        for field in EXPECTED_REQUIRED_FIELDS:
            if field not in normalized:
                add(
                    findings,
                    "consumer_reference_without_executable_fields",
                    path,
                    f"missing-field:{field}",
                )
    for marker in spec.get("required_markers", ()):
        if normalize(str(marker)) not in normalized:
            add(
                findings,
                "consumer_reference_without_executable_fields",
                path,
                f"missing-marker:{marker}",
            )

    rejected_marker_groups = (
        ("duplicate_local_scheduling_definition", "forbidden_consumer_markers"),
        ("duration_or_timeout_scope_cutoff", "scope_cutoff_markers"),
        ("keyword_based_routing", "keyword_routing_markers"),
        ("responsibility_scope_reduction", "scope_reduction_markers"),
    )
    for category, key in rejected_marker_groups:
        for marker in contract.get(key, ()):
            if normalize(str(marker)) in normalized:
                add(
                    findings,
                    category,
                    path,
                    f"forbidden-marker:{marker}",
                )

    owner_heading = str(contract.get("duplicate_definition_heading", ""))
    if (
        consumer_id != EXPECTED_OWNER_SKILL
        and owner_heading
        and text.count(owner_heading)
    ):
        add(
            findings,
            "duplicate_local_scheduling_definition",
            path,
            "owner-definition-present",
        )


def _check_consumers(
    root: Path,
    findings: list[Finding],
    contract: dict[str, Any],
    contract_label: str,
) -> dict[str, str]:
    consumers = contract.get("consumers")
    if not isinstance(consumers, list):
        add(findings, "contract_schema", contract_label, "consumers-not-list")
        return {}
    consumer_ids = tuple(item.get("id") for item in consumers if isinstance(item, dict))
    if consumer_ids != tuple(EXPECTED_CONSUMERS):
        add(
            findings,
            "consumer_reference_mismatch",
            contract_label,
            "consumer-set-mismatch",
        )

    texts: dict[str, str] = {}
    for spec in consumers:
        if not isinstance(spec, dict):
            add(
                findings,
                "contract_schema",
                contract_label,
                "consumer-not-mapping",
            )
            continue
        consumer_id = spec.get("id")
        path = spec.get("path")
        if not isinstance(consumer_id, str) or not isinstance(path, str):
            add(
                findings,
                "consumer_reference_mismatch",
                contract_label,
                "consumer-id-or-path-missing",
            )
            continue
        expected = EXPECTED_CONSUMERS.get(consumer_id)
        if expected is None or any(
            spec.get(key) != value for key, value in expected.items()
        ):
            add(
                findings,
                "consumer_reference_mismatch",
                path,
                "consumer-shape-mismatch",
            )
        if not (root / path).is_file():
            add(
                findings,
                "consumer_reference_mismatch",
                path,
                "consumer-missing",
            )
            continue
        text = read_text(root, path)
        texts[consumer_id] = text
        _check_consumer_text(findings, contract, consumer_id, spec, text)
    return texts


def _check_task_catalog(
    findings: list[Finding],
    contract: dict[str, Any],
    task_catalog_text: str | None,
) -> None:
    if task_catalog_text is None:
        return
    path = EXPECTED_CONSUMERS["task-catalog"]["path"]
    try:
        task_data = yaml.safe_load(task_catalog_text)
    except yaml.YAMLError as exc:
        add(
            findings,
            "consumer_reference_mismatch",
            path,
            f"yaml-parse:{exc}",
        )
        return
    policy = (
        task_data.get("execution_time_policy") if isinstance(task_data, dict) else None
    )
    if not isinstance(policy, dict):
        add(
            findings,
            "consumer_reference_mismatch",
            path,
            "execution-time-policy-missing",
        )
        return
    consumers = contract.get("consumers", ())
    spec = next(
        (
            item
            for item in consumers
            if isinstance(item, dict) and item.get("id") == "task-catalog"
        ),
        {},
    )
    if nested_mapping(task_data, tuple(spec.get("owner_ref_path", ()))) != OWNER_REF:
        add(
            findings,
            "consumer_reference_mismatch",
            path,
            "owner-ref-path-mismatch",
        )
    if nested_mapping(task_data, tuple(spec.get("fields_path", ()))) != list(
        EXPECTED_REQUIRED_FIELDS
    ):
        add(
            findings,
            "consumer_reference_without_executable_fields",
            path,
            "executable-fields-mismatch",
        )
    if nested_mapping(task_data, tuple(spec.get("projection_path", ()))) != spec.get(
        "projection_ref"
    ):
        add(
            findings,
            "consumer_reference_mismatch",
            path,
            "projection-ref-mismatch",
        )


def _check_required_command(
    root: Path,
    findings: list[Finding],
    contract: dict[str, Any],
    consumer_texts: dict[str, str],
) -> None:
    entry = catalog_skill(root, EXPECTED_OWNER_SKILL)
    expected_command = str(contract.get("required_skill_command"))
    if entry is None:
        add(
            findings,
            "required_command_route",
            "agents/skills/catalog.yaml",
            "agent-orchestration-entry-missing",
        )
        return
    tool_commands = entry.get("tool_commands")
    required = (
        tool_commands.get("required") if isinstance(tool_commands, dict) else None
    )
    if required != [expected_command] or len(set(required or ())) != len(
        required or ()
    ):
        add(
            findings,
            "required_command_route",
            "agents/skills/catalog.yaml",
            "required-checker-command-mismatch",
        )
    owner_text = read_text(root, "agents/skills/agent-orchestration.md")
    runtime_text = consumer_texts.get("runtime-shim", "")
    for path, text in (
        ("agents/skills/agent-orchestration.md", owner_text),
        (".codex/personal/skills/agent-orchestration/SKILL.md", runtime_text),
    ):
        if expected_command in text:
            add(
                findings,
                "required_command_route",
                path,
                "checker-command-copied-from-catalog",
            )


def check_contract(root: Path, contract_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    contract_label = contract_path.relative_to(root).as_posix()
    try:
        contract = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        add(
            findings,
            "contract_schema",
            contract_label,
            f"parse:{exc}",
        )
        return findings
    if not isinstance(contract, dict):
        add(findings, "contract_schema", contract_label, "not-mapping")
        return findings

    _check_exact_contract(findings, contract, contract_label)
    _check_owner(root, findings, contract)

    checker = contract.get("checker")
    if not isinstance(checker, str) or not (root / checker).is_file():
        add(
            findings,
            "contract_schema",
            str(checker),
            "checker-missing",
        )

    consumer_texts = _check_consumers(root, findings, contract, contract_label)
    _check_task_catalog(
        findings,
        contract,
        consumer_texts.get("task-catalog"),
    )
    _check_required_command(root, findings, contract, consumer_texts)
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="Repository root.",
    )
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_CONTRACT),
        help="Contract path relative to root.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = root / contract_path
    try:
        findings = check_contract(root, contract_path)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        findings = [
            Finding(
                "contract_schema",
                str(contract_path),
                f"checker-error:{exc}",
            )
        ]
    if args.format == "json":
        print(
            json.dumps(
                {
                    "status": "pass" if not findings else "fail",
                    "findings": [asdict(item) for item in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in findings:
            print(finding.render())
        print(f"EXECUTION_TIME_AWARE_ORCHESTRATION_FINDINGS={len(findings)}")
        print(
            f"EXECUTION_TIME_AWARE_ORCHESTRATION={'pass' if not findings else 'fail'}"
        )
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
