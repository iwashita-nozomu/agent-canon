#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run-local work log automation.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md runtime preflight logging rules
# upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md run bundle artifact placement contract
# downstream implementation ./workflow_monitor.py projects semantic events into monitoring output
# downstream implementation ./workflow_monitor.py projects semantic monitoring events here
# downstream implementation ./report_artifact_checks.py materializes the checked completion read model from this ledger
# downstream implementation ../../tests/agent_tools/test_work_log.py verifies work log behavior
# @dependency-end
"""Append one timestamped run-local work-log entry."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from agent_team import resolve_report_root
from task_authority import ACTIVE_RUN_POINTER

LEDGER_SEMANTIC_KINDS = (
    "request_clause",
    "responsibility_unit",
    "decision",
    "change",
    "review_finding",
    "validation",
    "failure",
    "publication_state",
    "deferral",
)
NON_GROUPABLE_SEMANTIC_KINDS = frozenset(
    {"responsibility_unit", "decision", "failure", "deferral", "publication_state"}
)
MONITOR_PASSTHROUGH_FIELDS = frozenset(
    {
        "gate_evidence",
        "failure_response",
        "resource_certificate",
        "source_binding",
        "monitor_evidence",
        "monitoring_evidence",
    }
)


def _required_ledger_text(event: Mapping[str, object], field: str) -> str:
    """Return one required ledger text field."""
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ledger event requires {field}")
    return value.strip()


def _required_ledger_refs(event: Mapping[str, object], field: str) -> tuple[str, ...]:
    """Return non-empty evidence or artifact references."""
    value = event.get(field)
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"ledger event requires non-empty {field}")
    refs = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(refs) != len(value):
        raise ValueError(f"ledger event {field} must contain only non-empty strings")
    return refs


def _validate_ledger_event(event: Mapping[str, object], report_dir: Path) -> str:
    """Validate one append-only event and return its stable identity."""
    if not isinstance(event, Mapping):
        raise ValueError("ledger event must be an object")
    run_id = _required_ledger_text(event, "run_id")
    if run_id != report_dir.name:
        raise ValueError("ledger event run_id does not match report directory")
    _required_ledger_text(event, "context_id")
    identity = event.get("event_id", event.get("sequence"))
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("ledger event requires event_id or sequence")
    semantic_kind = _required_ledger_text(event, "semantic_kind")
    if semantic_kind not in LEDGER_SEMANTIC_KINDS:
        raise ValueError(f"unsupported semantic_kind: {semantic_kind}")
    for field in (
        "owner",
        "state_owner",
        "api_owner",
        "dependency_owner",
        "responsibility_unit",
        "intent_id",
        "outcome",
    ):
        _required_ledger_text(event, field)
    for field in ("evidence_refs", "artifact_refs"):
        _required_ledger_refs(event, field)
    clause_id = event.get("clause_id")
    if clause_id is not None and (not isinstance(clause_id, str) or not clause_id.strip()):
        raise ValueError("ledger event clause_id must be null or non-empty text")
    mapping_mode = event.get("mapping_mode", "direct")
    if not isinstance(mapping_mode, str) or not mapping_mode.strip():
        raise ValueError("ledger event mapping_mode must be non-empty text")
    mapping_mode = mapping_mode.strip()
    if mapping_mode not in {"direct", "group"}:
        raise ValueError("ledger event mapping_mode must be direct or group")
    if mapping_mode == "group" and semantic_kind in NON_GROUPABLE_SEMANTIC_KINDS:
        raise ValueError(f"{semantic_kind} ledger events cannot be grouped")
    if mapping_mode == "group":
        group_identity = event.get("group_identity", event.get("group_id"))
        if not isinstance(group_identity, str) or not group_identity.strip():
            raise ValueError("group ledger events require group_identity")
        members = event.get("member_clause_ids")
        if not isinstance(members, (list, tuple)) or len(members) < 2:
            raise ValueError("group ledger events require member_clause_ids")
        if any(not isinstance(member, str) or not member.strip() for member in members):
            raise ValueError("group member_clause_ids must be non-empty text")
        if len(set(member.strip() for member in members)) != len(members):
            raise ValueError("group member_clause_ids must be unique")
    source_binding = event.get("source_binding")
    if source_binding is not None:
        if not isinstance(source_binding, Mapping):
            raise ValueError("ledger event source_binding must be an object")
        binding_run_id = source_binding.get("run_id")
        binding_context_id = source_binding.get("context_id")
        if not isinstance(binding_run_id, str) or not binding_run_id.strip():
            raise ValueError("ledger event source_binding requires run_id")
        if not isinstance(binding_context_id, str) or not binding_context_id.strip():
            raise ValueError("ledger event source_binding requires context_id")
        if binding_run_id.strip() != run_id:
            raise ValueError("ledger event source_binding.run_id does not match run_id")
        if binding_context_id.strip() != _required_ledger_text(event, "context_id"):
            raise ValueError(
                "ledger event source_binding.context_id does not match context_id"
            )
    for field in MONITOR_PASSTHROUGH_FIELDS - {"source_binding"}:
        value = event.get(field)
        if value is None:
            continue
        if not isinstance(value, (Mapping, list, tuple)):
            raise ValueError(f"ledger event {field} must remain structured evidence")
    return str(identity).strip()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one run-local work-log entry.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root containing reports/agents/.active_run.",
    )
    parser.add_argument("--report-dir", help="Explicit run bundle directory to update.")
    parser.add_argument("--run-id", help="Run id under reports/agents/.")
    parser.add_argument(
        "--report-root",
        help=(
            "Optional directory that contains per-run report folders. Defaults to "
            "<workspace-root>/reports/agents."
        ),
    )
    parser.add_argument(
        "--kind",
        default="work",
        help="Short event kind, for example kickoff/test/edit/review.",
    )
    parser.add_argument("--message", required=True, help="What happened in this step.")
    parser.add_argument("--next", default="", help="Explicit next step.")
    parser.add_argument(
        "--request-clause-id",
        action="append",
        default=[],
        help="User request clause id covered by this log entry. Repeat to add multiple ids.",
    )
    parser.add_argument(
        "--design-ref",
        action="append",
        default=[],
        help="Approved design section or artifact clause used by this entry.",
    )
    parser.add_argument(
        "--allow-missing-request-clause-id",
        action="store_true",
        help=(
            "Allow a run-bundle-only pre-contract/runtime note without a clause id. "
            "Use only before a clause can reasonably exist."
        ),
    )
    parser.add_argument(
        "--missing-request-clause-reason",
        default="",
        help="Required reason when --allow-missing-request-clause-id is used.",
    )
    parser.add_argument(
        "--ref",
        action="append",
        default=[],
        help="Optional path or artifact reference. Repeat to add multiple refs.",
    )
    return parser


def append_ledger_event(report_dir: Path, event: dict[str, object]) -> Path:
    """Append one semantic event to the existing run-local work ledger."""
    event_identity = _validate_ledger_event(event, report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    work_log_path = report_dir / "work_log.md"
    if not work_log_path.exists():
        _log_run_work_entry(report_dir, "ledger_event=bootstrap")
    lines = work_log_path.read_text(encoding="utf-8").splitlines()
    heading = "## Ledger Events"
    if heading not in lines:
        lines.extend(["", heading, ""])
    payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
    line = f"- ledger_event={payload}"
    for existing_line in lines:
        if not existing_line.startswith("- ledger_event="):
            continue
        try:
            existing = json.loads(existing_line.removeprefix("- ledger_event="))
        except json.JSONDecodeError:
            continue
        if not isinstance(existing, dict):
            continue
        existing_identity = existing.get("event_id", existing.get("sequence"))
        if existing_identity == event_identity:
            if existing != event:
                raise ValueError(
                    f"ledger event conflict for event identity={event_identity}"
                )
            return work_log_path
    if line not in lines:
        lines.append(line)
        work_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return work_log_path


def read_ledger_snapshot(report_dir: Path, snapshot_identity: str) -> dict[str, object]:
    """Reconstruct one immutable logical-ledger snapshot from the run log."""
    if not snapshot_identity.strip():
        raise ValueError("snapshot_identity must not be empty")
    work_log_path = report_dir / "work_log.md"
    if not work_log_path.is_file():
        raise ValueError(f"missing work log: {work_log_path}")
    events: list[dict[str, object]] = []
    identities: set[str] = set()
    for line in work_log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ledger_event="):
            continue
        try:
            event = json.loads(line.removeprefix("- ledger_event="))
        except json.JSONDecodeError as exc:
            raise ValueError("malformed ledger event") from exc
        if not isinstance(event, dict):
            raise ValueError("ledger event must be an object")
        identity = _validate_ledger_event(event, report_dir)
        if identity in identities:
            raise ValueError(f"duplicate ledger event identity: {identity}")
        identities.add(identity)
        events.append(event)
    events.sort(
        key=lambda event: (
            str(event.get("sequence", "")),
            str(event.get("event_id", event.get("sequence", ""))),
        )
    )
    snapshot = {
        "snapshot_identity": snapshot_identity.strip(),
        "events": events,
        "event_identities": sorted(identities),
    }
    snapshot["snapshot_digest"] = ledger_snapshot_digest(snapshot)
    return snapshot


def ledger_snapshot_digest(snapshot: Mapping[str, object]) -> str:
    """Return the stable digest for the canonical ledger event projection."""
    events = snapshot.get("events")
    if not isinstance(events, list):
        raise ValueError("ledger snapshot events must be a list")
    payload = json.dumps(events, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_active_report_dir(workspace_root: Path, report_root: Path) -> Path | None:
    """Resolve the current run bundle from reports/agents/.active_run."""
    pointer = workspace_root / ACTIVE_RUN_POINTER
    if not pointer.is_file():
        return None
    active = pointer.read_text(encoding="utf-8").strip()
    if not active:
        return None
    active_path = Path(active)
    if active_path.is_absolute():
        return active_path
    if active_path.as_posix().startswith("reports/agents/"):
        return workspace_root / active_path
    return report_root / active_path


def _log_run_work_entry(report_dir: Path, entry: str) -> Path:
    """Append one entry to the run-bundle work log."""
    report_dir.mkdir(parents=True, exist_ok=True)
    work_log_path = report_dir / "work_log.md"
    if not work_log_path.exists():
        work_log_path.write_text(
            "\n".join(
                [
                    "# Work Log",
                    "",
                    f"- Run ID: {report_dir.name}",
                    "- Task:",
                    "- Owner:",
                    "",
                    "## Purpose",
                    "",
                    "- Chronological run-local work log.",
                    "",
                    "## Entries",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    with work_log_path.open("a", encoding="utf-8") as handle:
        if work_log_path.stat().st_size > 0:
            handle.write("\n")
        handle.write(f"- {entry}\n")
    return work_log_path


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    report_root = resolve_report_root(args.report_root, workspace_root)

    if args.report_dir and args.run_id:
        raise SystemExit("Provide at most one of --report-dir or --run-id.")
    if args.report_dir:
        report_dir = Path(args.report_dir).resolve()
    elif args.run_id:
        report_dir = report_root / str(args.run_id)
    else:
        report_dir = _resolve_active_report_dir(workspace_root, report_root)

    if not args.request_clause_id:
        if not args.allow_missing_request_clause_id:
            raise SystemExit(
                "At least one --request-clause-id is required unless "
                "--allow-missing-request-clause-id is set."
            )
        if not args.missing_request_clause_reason.strip():
            raise SystemExit(
                "--missing-request-clause-reason is required when clause ids are omitted."
            )
        if report_dir is None:
            raise SystemExit(
                "Missing clause ids are only allowed when --report-dir or --run-id "
                "or reports/agents/.active_run resolves a run bundle."
            )

    if report_dir is None:
        raise SystemExit(
            "No run bundle resolved. Provide --report-dir / --run-id or create reports/agents/.active_run."
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    if args.request_clause_id:
        clause_suffix = " | request_clause_ids: " + ",".join(args.request_clause_id)
    else:
        clause_suffix = (
            " | request_clause_ids: unassigned"
            f" | missing_request_clause_reason: {args.missing_request_clause_reason.strip()}"
        )
    ref_suffix = ""
    if args.ref:
        ref_suffix = " | refs: " + ", ".join(args.ref)
    design_suffix = ""
    if args.design_ref:
        design_suffix = " | design_refs: " + ", ".join(args.design_ref)
    next_suffix = ""
    if args.next:
        next_suffix = f" | next: {args.next}"
    entry = (
        f"`{timestamp} | {args.kind} | {args.message}"
        f"{clause_suffix}{design_suffix}{ref_suffix}{next_suffix}`"
    )
    work_log_path = _log_run_work_entry(report_dir, entry)
    print(f"WORK_LOG={work_log_path}")
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
