#!/usr/bin/env python3
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
"""Format one solver/optimizer run-log JSONL file."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jax_util.base._jsonl import read_jsonl_records


def _build_call_tree(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_call: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        call_id = record.get("call_id")
        if isinstance(call_id, str):
            by_call[call_id].append(record)

    calls: list[dict[str, Any]] = []
    for call_id, call_records in by_call.items():
        first = min(call_records, key=lambda record: int(record["seq"]))
        last = max(call_records, key=lambda record: int(record["seq"]))
        calls.append(
            {
                "call_id": call_id,
                "parent_call_id": first.get("parent_call_id"),
                "solver": first.get("solver"),
                "execution_kind": first.get("execution_kind"),
                "depth": first.get("depth"),
                "call_path": first.get("call_path"),
                "event_counts": dict(Counter(str(record.get("event")) for record in call_records)),
                "start_seq": first.get("seq"),
                "end_seq": last.get("seq"),
                "last_event": last.get("event"),
                "last_record": last,
            }
        )

    children: dict[str, list[dict[str, Any]]] = defaultdict(list)
    roots: list[dict[str, Any]] = []
    for call in calls:
        parent = call["parent_call_id"]
        if isinstance(parent, str):
            children[parent].append(call)
        else:
            roots.append(call)

    roots.sort(key=lambda call: int(call["start_seq"]))
    for child_calls in children.values():
        child_calls.sort(key=lambda call: int(call["start_seq"]))
    return roots, children


def _call_label(call: dict[str, Any]) -> str:
    solver = call["solver"]
    execution_kind = call["execution_kind"]
    return f"{solver}.{execution_kind}"


def _render_text(
    records: list[dict[str, Any]],
    roots: list[dict[str, Any]],
    children: dict[str, list[dict[str, Any]]],
) -> str:
    if not records:
        return "empty run log"

    header = records[0]
    lines = [
        f"run_id: {header.get('run_id')}",
        f"run_label: {header.get('run_label')}",
        f"top_solver: {header.get('top_solver')}",
        f"records: {len(records)}",
    ]

    def _append_call(call: dict[str, Any], indent: int) -> None:
        prefix = "  " * indent
        event_counts = ", ".join(
            f"{event}={count}" for event, count in sorted(call["event_counts"].items())
        )
        lines.append(
            f"{prefix}- {_call_label(call)} "
            f"[seq {call['start_seq']}..{call['end_seq']}] "
            f"last={call['last_event']} events({event_counts})"
        )
        for child in children.get(call["call_id"], []):
            _append_call(child, indent + 1)

    for root in roots:
        _append_call(root, 0)
    return "\n".join(lines)


def _build_summary(
    records: list[dict[str, Any]],
    roots: list[dict[str, Any]],
    children: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    def _summarize_call(call: dict[str, Any]) -> dict[str, Any]:
        return {
            "call_id": call["call_id"],
            "parent_call_id": call["parent_call_id"],
            "solver": call["solver"],
            "execution_kind": call["execution_kind"],
            "depth": call["depth"],
            "call_path": call["call_path"],
            "event_counts": call["event_counts"],
            "start_seq": call["start_seq"],
            "end_seq": call["end_seq"],
            "last_event": call["last_event"],
            "children": [_summarize_call(child) for child in children.get(call["call_id"], [])],
        }

    summary: dict[str, Any] = {
        "num_records": len(records),
        "runs": [],
    }
    if records:
        summary.update(
            {
                "run_id": records[0].get("run_id"),
                "run_label": records[0].get("run_label"),
                "top_solver": records[0].get("top_solver"),
            }
        )
    summary["runs"] = [_summarize_call(root) for root in roots]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path", type=Path, help="Path to one solver run-log JSONL file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable summary JSON instead of text",
    )
    args = parser.parse_args()

    records = read_jsonl_records(args.log_path)
    roots, children = _build_call_tree(records)
    if args.json:
        print(json.dumps(_build_summary(records, roots, children), ensure_ascii=True, indent=2))
    else:
        print(_render_text(records, roots, children))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
