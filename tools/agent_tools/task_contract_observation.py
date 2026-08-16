#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Records and scores task-local contract observations in run bundles.
# upstream design ../../documents/runtime/task-contract-observation.md defines the collection flow
# upstream implementation ./task_contract_observation_core.py owns schema and transitions
# upstream implementation ./workflow_monitor.py owns locked monitoring append
# downstream data ../../evidence/agent-evals/agent_behavior_eval.toml requires coverage
# downstream implementation ../../tests/agent_tools/test_task_contract_observation.py tests it
# @dependency-end
"""Record and score task-local contract observations."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

if __package__:
    from .task_contract_observation_core import (
        ARCHIVE_ROUTE,
        KIND_KEY,
        SCHEMA,
        SCHEMA_KEY,
        Evaluation,
        ParsedRecord,
        evaluate_payloads,
        evaluate_text,
        event_payloads,
        normalize_record_argument,
        parse_token_fields,
    )
else:
    from task_contract_observation_core import (
        ARCHIVE_ROUTE,
        KIND_KEY,
        SCHEMA,
        SCHEMA_KEY,
        Evaluation,
        ParsedRecord,
        evaluate_payloads,
        evaluate_text,
        event_payloads,
        normalize_record_argument,
        parse_token_fields,
    )


def monitoring_text(report_dir: Path) -> str:
    """Read workflow monitoring or return an empty stream."""

    path = report_dir / "workflow_monitoring.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def append_behavior_events(report_dir: Path, events: Sequence[str], *, timestamp: str = "") -> None:
    """Append events through the canonical locked workflow monitor."""

    if not events:
        return
    if __package__:
        from .workflow_monitor import MonitoringEntries, append_monitoring
    else:
        from workflow_monitor import MonitoringEntries, append_monitoring
    append_monitoring(
        report_dir,
        MonitoringEntries(behavior_events=tuple(events), timestamp=timestamp),
    )


def record_observations(report_dir: Path, raw_records: Sequence[str]) -> tuple[str, ...]:
    """Validate and append observation records."""

    existing = list(event_payloads(monitoring_text(report_dir)))
    normalized: list[str] = []
    for raw in raw_records:
        event = normalize_record_argument(raw, existing)
        fields, _ = parse_token_fields(event)
        existing.append(ParsedRecord(len(existing) + 1, fields))
        normalized.append(event)
    append_behavior_events(report_dir, normalized)
    return tuple(normalized)


def summary_event(evaluation: Evaluation) -> str:
    """Render compact current-run evidence consumed by behavior evals."""

    unresolved = ",".join(evaluation.unresolved_ids) or "none"
    passed = evaluation.status == "pass" and not evaluation.unresolved_ids
    return " ".join(
        (
            f"task_contract_observation_eval_status={evaluation.status}",
            f"task_contract_observation_digest={evaluation.stream_digest}",
            f"task_contract_observation_coverage={'complete' if passed else 'incomplete'}",
            f"task_contract_resolution={'terminal' if passed else 'open'}",
            f"task_contract_observation_events={evaluation.event_count}",
            f"task_contract_observation_count={evaluation.observation_count}",
            f"task_contract_observation_none={evaluation.none_count}",
            f"task_contract_observation_unresolved={unresolved}",
            f"contract_archive_route={ARCHIVE_ROUTE}",
        )
    )


def append_evaluation_summary(report_dir: Path, evaluation: Evaluation) -> None:
    """Append the compact evaluation summary."""

    append_behavior_events(
        report_dir,
        (summary_event(evaluation),),
        timestamp="task-contract-observation-eval",
    )


def _base_payload(outcome: str, sequence: int = 1) -> str:
    return " ".join(
        (
            f"{SCHEMA_KEY}={SCHEMA}",
            f"{KIND_KEY}=observed",
            "observation_id=contract-alpha",
            f"sequence={sequence}",
            "contract_id=AGENTS.md#repository",
            "contract_source=AGENTS.md",
            "phase=implementation",
            "trigger=guardrail",
            f"outcome={outcome}",
            "owner=implementer",
            "evidence_ref=verification.txt",
            "response=repair-applied",
        )
    )


def run_self_check() -> tuple[bool, tuple[str, ...]]:
    """Run deterministic positive and negative schema cases."""

    cases = (
        ("satisfied", (_base_payload("satisfied"),), "pass"),
        (
            "blocked-then-satisfied",
            (_base_payload("blocked"), _base_payload("satisfied", 2)),
            "pass",
        ),
        (
            "explicit-none",
            (f"{SCHEMA_KEY}={SCHEMA} {KIND_KEY}=none owner=manager reason=no-contract-triggered",),
            "pass",
        ),
        ("unresolved", (_base_payload("blocked"),), "fail"),
        (
            "missing-source",
            (
                _base_payload("satisfied").replace(
                    "contract_source=AGENTS.md", "contract_source=missing"
                ),
            ),
            "fail",
        ),
        (
            "identity-collision",
            (
                _base_payload("blocked"),
                _base_payload("satisfied", 2).replace(
                    "contract_id=AGENTS.md#repository",
                    "contract_id=OTHER.md#repository",
                ),
            ),
            "fail",
        ),
    )
    lines: list[str] = []
    passed = True
    for case_id, payloads, expected in cases:
        observed = evaluate_payloads(payloads).status
        case_passed = observed == expected
        passed &= case_passed
        lines.append(
            f"TASK_CONTRACT_OBSERVATION_SELF_CHECK_CASE={case_id}:"
            f"{'pass' if case_passed else 'fail'}:expected={expected}:observed={observed}"
        )
    return passed, tuple(lines)


def print_evaluation(evaluation: Evaluation) -> None:
    """Print bounded machine-readable output."""

    print(f"TASK_CONTRACT_OBSERVATION_EVAL_STATUS={evaluation.status}")
    print(f"TASK_CONTRACT_OBSERVATION_DIGEST={evaluation.stream_digest}")
    print(f"TASK_CONTRACT_OBSERVATION_EVENTS={evaluation.event_count}")
    print(f"TASK_CONTRACT_OBSERVATION_COUNT={evaluation.observation_count}")
    print(f"TASK_CONTRACT_OBSERVATION_NONE={evaluation.none_count}")
    print(f"TASK_CONTRACT_OBSERVATION_UNRESOLVED={','.join(evaluation.unresolved_ids) or 'none'}")
    print(f"TASK_CONTRACT_OBSERVATION_ARCHIVE_ROUTE={ARCHIVE_ROUTE}")
    for state in evaluation.states:
        print(
            "TASK_CONTRACT_OBSERVATION_STATE="
            f"{state.observation_id}:contract={state.contract_id}:source={state.contract_source}:"
            f"phase={state.phase}:outcome={state.outcome}:owner={state.owner}:"
            f"evidence={state.evidence_ref}:response={state.response}"
        )
    for item in evaluation.findings:
        print(
            "TASK_CONTRACT_OBSERVATION_FINDING="
            f"{item.code}:line={item.line}:observation={item.observation_id}:detail={item.detail}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--record", action="append", default=[])
    parser.add_argument("--no-monitoring-summary", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute recording, evaluation, or self-check."""

    if args.self_check:
        passed, lines = run_self_check()
        print(*lines, sep="\n")
        print(f"TASK_CONTRACT_OBSERVATION_SELF_CHECK={'pass' if passed else 'fail'}")
        return 0 if passed else 1
    if args.report_dir is None:
        raise SystemExit("--report-dir is required unless --self-check is used")
    report_dir = args.report_dir.resolve()
    if args.record:
        recorded = record_observations(report_dir, tuple(args.record))
        for event in recorded:
            print(f"TASK_CONTRACT_OBSERVATION_RECORDED={event}")
        structural = evaluate_text(monitoring_text(report_dir), require_terminal=False)
        print(f"TASK_CONTRACT_OBSERVATION_RECORD_STATUS={structural.status}")
        print(f"TASK_CONTRACT_OBSERVATION_OPEN={','.join(structural.unresolved_ids) or 'none'}")
        return 0 if structural.status == "pass" else 1

    evaluation = evaluate_text(monitoring_text(report_dir))
    if not args.no_monitoring_summary:
        append_evaluation_summary(report_dir, evaluation)
    print_evaluation(evaluation)
    return 0 if evaluation.status == "pass" else 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
