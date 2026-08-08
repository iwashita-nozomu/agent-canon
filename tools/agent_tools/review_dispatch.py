#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes automatic independent-review candidates, frames, dispatch transitions, and decisions.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns candidate, frame, event, lineage, and handoff schemas.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md owns automatic-review state transitions and APPROVE-only publication.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md owns independent reviewer routing and same-context resume policy.
# upstream design ../../agents/skills/agent-orchestration.md owns automatic review workflow routing.
# upstream design ../../agents/skills/subagent-bootstrap.md owns review launch and resume mechanics.
# upstream design ../../agents/skills/change-review.md owns findings-first candidate review decisions.
# upstream design ../../agents/skills/pr-processing.md owns PR-head review handling.
# upstream implementation ./team_config.py resolves task, role, and resume routing.
# upstream implementation ./implementation_dispatch.py resolves agent type and dispatch routing.
# upstream implementation ./workflow_monitor.py produces write-result triggers and records review waves.
# upstream implementation ./github_publish.py produces verified PR-head update triggers.
# upstream implementation ./artifact_identity.py materializes review artifact byte identities.
# upstream implementation ./external_artifact_binding.py maps provider readback to local events.
# downstream implementation ./publication_integrator.py resolves current explicit APPROVE state.
# downstream implementation ./report_artifact_checks.py consumes unresolved automatic review evidence.
# downstream implementation ../../tests/agent_tools/test_review_dispatch.py validates automatic-review state and routing.
# @dependency-end
"""Drive automatic independent review from canonical repository state."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

import yaml
from artifact_identity import (
    canonical_body_sha256,
    canonical_json_bytes,
    materialize_artifact_identity,
)
from external_artifact_binding import (
    materialize_external_projection_acknowledgement,
)
from task_authority import ACTIVE_RUN_POINTER
from work_log import append_ledger_event, read_ledger_snapshot
from report_artifact_checks import markdown_without_adjudicated_rejected_hypotheses

REVIEW_CANDIDATE_SCHEMA = "agent-canon.review-candidate-event.v1"
REVIEW_INTENT_SCHEMA = "agent-canon.terminal-resume-intent.v1"
REVIEW_FRAME_SCHEMA = "agent-canon.review-frame.v3"
RESUME_EVENT_SCHEMA = "agent-canon.terminal-resume-event.v3"
REVIEW_DECISION_SCHEMA = "agent-canon.review-decision-event.v1"
MINIMAL_HANDOFF_KEYS = (
    "objective",
    "owner_unit",
    "fixed_source_packet",
    "acceptance_identity",
)
DECISION_PATTERN = re.compile(r"\b(APPROVE|REVISE|ESCALATE)\b", re.IGNORECASE)
DECISION_LINE_PATTERN = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:decision|review_decision)\s*[:=]\s*"
    r"(APPROVE|ACCEPT|REVISE|CHANGES-REQUIRED|ESCALATE)\s*$"
)
TERMINAL_RUNTIME_STATUSES = frozenset({"completed", "errored", "shutdown"})
ALLOWED_REVIEW_ROLES = {
    "change_reviewer": "diff_triage_reviewer",
    "final_reviewer": "ship_reviewer",
}

# Finding status is the review contract.  Keep the vocabulary small and
# explicit so that a style observation or an unanswered question cannot be
# promoted to a publication blocker by a renderer or a reviewer role.
FINDING_STATUSES = frozenset(
    {
        "blocking",
        "non-blocking",
        "question",
        "not-applicable",
        "accepted-risk",
    }
)
FINDING_STATUS_ALIASES = {
    "nonblocking": "non-blocking",
    "notapplicable": "not-applicable",
    "acceptedrisk": "accepted-risk",
}
DECISION_ALIASES = {
    "ACCEPT": "APPROVE",
    "CHANGES-REQUIRED": "REVISE",
}
REVIEW_OUTCOMES = frozenset({"accept", "changes-required"})


def normalize_finding_status(value: object) -> str:
    """Return one canonical finding status or reject an unknown value."""
    if not isinstance(value, str):
        raise AutomaticReviewError("automatic_review:finding_status_invalid")
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    normalized = FINDING_STATUS_ALIASES.get(normalized, normalized)
    if normalized not in FINDING_STATUSES:
        raise AutomaticReviewError(
            "automatic_review:finding_status_invalid",
            normalized or "empty",
        )
    return normalized


def canonicalize_review_decision(value: object) -> str:
    """Canonicalize template-facing decision aliases at the dispatch boundary."""
    if not isinstance(value, str):
        raise AutomaticReviewError("automatic_review:decision_invalid")
    normalized = value.strip().upper().replace("_", "-").replace(" ", "-")
    normalized = DECISION_ALIASES.get(normalized, normalized)
    if normalized not in {"APPROVE", "REVISE", "ESCALATE"}:
        raise AutomaticReviewError(
            "automatic_review:decision_invalid",
            normalized or "empty",
        )
    return normalized


def derive_review_outcome(findings: Sequence[Mapping[str, object]]) -> str:
    """Derive the review outcome from unresolved blocking findings only.

    Non-blocking findings, questions, not-applicable observations, and
    explicitly accepted risks remain useful review evidence but do not force a
    changes-required outcome.
    """
    for finding in findings:
        if normalize_finding_status(finding.get("status")) == "blocking":
            return "changes-required"
    return "accept"


def parse_finding_rows(markdown: str) -> tuple[dict[str, str], ...]:
    """Parse status-bearing Markdown finding rows for outcome derivation.

    The parser intentionally accepts the existing area/chunk/finding tables
    and does not make a particular review template a second policy source.
    Rows without a recognized status are ignored; malformed explicit statuses
    are rejected by the caller when a status-bearing row is present.
    """
    rows: list[dict[str, str]] = []
    lines = markdown.splitlines()

    def table_cells(line: str) -> list[str] | None:
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 2:
            return None
        return [cell.strip() for cell in stripped.strip("|").split("|")]

    def separator_row(cells: Sequence[str]) -> bool:
        return bool(cells) and all(
            bool(re.fullmatch(r":?-+:?", cell.replace(" ", "")))
            for cell in cells
        )

    def header_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")

    for index, line in enumerate(lines):
        header = table_cells(line)
        if header is None or separator_row(header):
            continue
        names = [header_name(cell) for cell in header]
        if "status" not in names:
            continue
        status_index = names.index("status")
        severity_index = names.index("severity") if "severity" in names else None
        row_index = index + 1
        while row_index < len(lines):
            cells = table_cells(lines[row_index])
            if cells is None:
                break
            row_index += 1
            if separator_row(cells) or status_index >= len(cells):
                continue
            status = cells[status_index].lower().replace("_", "-").replace(" ", "-")
            status = FINDING_STATUS_ALIASES.get(status, status)
            if status not in FINDING_STATUSES:
                continue
            severity = (
                cells[severity_index]
                if severity_index is not None and severity_index < len(cells)
                else ""
            )
            rows.append(
                {
                    "finding": cells[0] if cells else "",
                    "severity": severity,
                    "status": status,
                }
            )
    return tuple(rows)


class AutomaticReviewError(ValueError):
    """Typed automatic-review failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable error."""
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


RuntimeDispatcher = Callable[[Mapping[str, object]], Mapping[str, object]]


def _run_git(workspace: Path, args: Sequence[str]) -> str:
    """Run one read-only Git command."""
    completed = subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AutomaticReviewError(
            "automatic_review:git_read_failed",
            completed.stderr.strip(),
        )
    return completed.stdout.strip()


def _active_report_dir(workspace: Path) -> Path:
    """Resolve the canonical active run without a caller path override."""
    pointer = workspace / ACTIVE_RUN_POINTER
    if not pointer.is_file():
        raise AutomaticReviewError("automatic_review:active_run_missing")
    raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        raise AutomaticReviewError("automatic_review:active_run_missing")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    report_root = (workspace / "reports" / "agents").resolve()
    try:
        resolved.relative_to(report_root)
    except ValueError as exc:
        raise AutomaticReviewError("automatic_review:active_run_foreign") from exc
    if not resolved.is_dir():
        raise AutomaticReviewError("automatic_review:active_run_missing")
    return resolved


def _required_text(mapping: Mapping[str, object], field: str) -> str:
    """Return one exact non-empty text field."""
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AutomaticReviewError("automatic_review:routing_packet_missing", field)
    return value.strip()


def _required_event_order_index(mapping: Mapping[str, object]) -> int:
    """Return one typed automatic-review event order index."""
    value = mapping.get("event_order_index")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AutomaticReviewError("automatic_review:event_order_invalid")
    return value


def _record_id(prefix: str, payload: Mapping[str, object]) -> str:
    """Return a deterministic record ID."""
    return f"{prefix}:{hashlib.sha256(canonical_json_bytes(payload)).hexdigest()}"


def _ledger_events(report_dir: Path) -> list[dict[str, object]]:
    """Return canonical events in snapshot order."""
    snapshot = read_ledger_snapshot(
        report_dir,
        f"w2-current-ledger:{report_dir.name}",
    )
    events = snapshot.get("events")
    if not isinstance(events, list):
        raise AutomaticReviewError("automatic_review:ledger_invalid")
    return [event for event in events if isinstance(event, dict)]


def _automatic_payloads(
    report_dir: Path,
    kind: str | None = None,
) -> list[dict[str, object]]:
    """Return automatic-review payloads in event order."""
    payloads: list[dict[str, object]] = []
    for event in _ledger_events(report_dir):
        payload = event.get("automatic_review")
        if not isinstance(payload, dict):
            continue
        if kind is None or payload.get("record_kind") == kind:
            payloads.append(payload)
    return payloads


def _canonical_writer_identity(report_dir: Path) -> dict[str, str]:
    """Derive writer identity from task authority and the current team manifest."""
    manifest_path = report_dir / "team_manifest.yaml"
    if not manifest_path.is_file():
        raise AutomaticReviewError(
            "automatic_review:structure_owner_missing",
            "team_manifest.yaml",
        )
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AutomaticReviewError("automatic_review:routing_packet_missing", "roles")
    roles = raw.get("roles")
    if not isinstance(roles, list):
        raise AutomaticReviewError("automatic_review:routing_packet_missing", "roles")
    implementer = next(
        (
            role
            for role in roles
            if isinstance(role, Mapping) and role.get("id") == "implementer"
        ),
        None,
    )
    if not isinstance(implementer, Mapping):
        raise AutomaticReviewError(
            "automatic_review:structure_owner_missing",
            "implementer",
        )
    agent_types = implementer.get("codex_agents")
    if not isinstance(agent_types, list) or not agent_types:
        raise AutomaticReviewError(
            "automatic_review:routing_packet_missing",
            "implementer.codex_agents",
        )
    agent_type = str(agent_types[0])
    runtime_agent_id = f"writer:{report_dir.name}:implementer"
    context_id = f"writer-context:{report_dir.name}"
    instance_id = "implementer_worker"
    instance_key = f"implementer:{instance_id}:{agent_type}"
    writer_lineage_id = _record_id(
        "w2-writer-lineage",
        {
            "aggregate_identity": report_dir.name,
            "writer_context_id": context_id,
            "role_id": "implementer",
            "initial_instance_id": instance_id,
        },
    )
    return {
        "role_id": "implementer",
        "instance_id": instance_id,
        "agent_type": agent_type,
        "instance_key": instance_key,
        "runtime_agent_id": runtime_agent_id,
        "writer_context_id": context_id,
        "writer_lineage_id": writer_lineage_id,
    }


def _review_route(report_dir: Path, role_id: str) -> dict[str, str]:
    """Resolve the canonical reviewer role and artifact-only policy."""
    expected_agent_type = ALLOWED_REVIEW_ROLES.get(role_id)
    if expected_agent_type is None:
        raise AutomaticReviewError(
            "automatic_review:role_config_mismatch",
            role_id,
        )
    config_path = Path(__file__).resolve().parents[2] / "agents" / "agents_config.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    role_groups = (
        [raw.get("always_on_roles"), raw.get("specialist_roles")]
        if isinstance(raw, Mapping)
        else []
    )
    roles = [
        item
        for group in role_groups
        if isinstance(group, list)
        for item in group
        if isinstance(item, Mapping)
    ]
    role = next(
        (
            item
            for item in roles
            if isinstance(item, Mapping) and item.get("id") == role_id
        ),
        None,
    )
    if not isinstance(role, Mapping):
        raise AutomaticReviewError(
            "automatic_review:structure_owner_missing",
            role_id,
        )
    candidates = role.get("codex_agents")
    policy = role.get("write_policy")
    if (
        not isinstance(candidates, list)
        or expected_agent_type not in candidates
        or not isinstance(policy, Mapping)
        or policy.get("mode") != "artifacts_only"
    ):
        raise AutomaticReviewError(
            "automatic_review:role_config_mismatch",
            f"{role_id}:{expected_agent_type}",
        )
    return {
        "role_id": role_id,
        "agent_type": expected_agent_type,
        "write_policy": "artifacts_only",
        "team_manifest_role_instance_ref": (
            f"team_manifest.yaml#{role_id}:{role_id}_{expected_agent_type}"
        ),
        "review_artifact": "change_review.md"
        if role_id == "change_reviewer"
        else "final_review.md",
        "report_dir": str(report_dir),
    }


def _append_automatic_event(
    report_dir: Path,
    payload: Mapping[str, object],
    *,
    outcome: str,
) -> None:
    """Append one automatic-review record to canonical L."""
    record_id = _required_text(payload, "record_id")
    append_ledger_event(
        report_dir,
        {
            "run_id": report_dir.name,
            "context_id": report_dir.name,
            "event_id": record_id,
            "semantic_kind": "publication_state",
            "owner": "component_manager",
            "state_owner": "component_manager",
            "api_owner": "tools/agent_tools/review_dispatch.py",
            "dependency_owner": "agents/COMMUNICATION_PROTOCOL.md",
            "responsibility_unit": "completion_authority",
            "intent_id": "W2-completion-authority",
            "outcome": outcome,
            "evidence_refs": [
                "agents/COMMUNICATION_PROTOCOL.md",
                "agents/canonical/CODEX_WORKFLOW.md",
            ],
            "artifact_refs": ["team_manifest.yaml", "work_log.md"],
            "source_binding": {
                "run_id": report_dir.name,
                "context_id": report_dir.name,
            },
            "automatic_review": dict(payload),
        },
    )


def _current_candidate(report_dir: Path) -> dict[str, object]:
    """Return the unique highest review candidate."""
    candidates = _automatic_payloads(report_dir, "candidate")
    if not candidates:
        raise AutomaticReviewError("automatic_review:candidate_missing")
    by_revision: dict[int, dict[str, object]] = {}
    for candidate in candidates:
        revision = candidate.get("candidate_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise AutomaticReviewError("automatic_review:candidate_revision_invalid")
        if revision in by_revision and by_revision[revision] != candidate:
            raise AutomaticReviewError("automatic_review:candidate_revision_duplicate")
        by_revision[revision] = candidate
    revisions = sorted(by_revision)
    if revisions != list(range(1, revisions[-1] + 1)):
        raise AutomaticReviewError("automatic_review:candidate_revision_gap")
    return by_revision[revisions[-1]]


def materialize_review_candidate(
    workspace: Path,
    *,
    trigger_kind: str,
    acceptance_identity: Mapping[str, object],
) -> dict[str, object]:
    """Materialize the immutable current Git candidate for automatic review."""
    if trigger_kind not in {"write_result", "source_freeze", "pr_head_update"}:
        raise AutomaticReviewError("automatic_review:trigger_invalid")
    root = workspace.resolve()
    report_dir = _active_report_dir(root)
    commit = _run_git(root, ["rev-parse", "HEAD"])
    tree = _run_git(root, ["rev-parse", "HEAD^{tree}"])
    writer = _canonical_writer_identity(report_dir)
    existing = _automatic_payloads(report_dir, "candidate")
    if existing:
        current = _current_candidate(report_dir)
        if current.get("candidate_commit") == commit:
            return current
        prior_writer_lineage = current.get("writer_lineage_id")
        if prior_writer_lineage != writer["writer_lineage_id"]:
            raise AutomaticReviewError("automatic_review:writer_lineage_changed")
        previous_revision = current.get("candidate_revision")
        supersedes_value = current.get("candidate_id")
        if (
            not isinstance(previous_revision, int)
            or isinstance(previous_revision, bool)
            or previous_revision < 1
            or not isinstance(supersedes_value, str)
            or not supersedes_value
        ):
            raise AutomaticReviewError("automatic_review:candidate_identity_invalid")
        revision = previous_revision + 1
        supersedes = supersedes_value
    else:
        revision = 1
        supersedes = None
    candidate_seed = {
        "aggregate_identity": report_dir.name,
        "candidate_revision": revision,
        "commit": commit,
        "tree": tree,
        "writer_lineage_id": writer["writer_lineage_id"],
        "trigger_kind": trigger_kind,
    }
    candidate_id = _record_id("w2-review-candidate", candidate_seed)
    payload: dict[str, object] = {
        "schema": REVIEW_CANDIDATE_SCHEMA,
        "schema_version": 1,
        "record_kind": "candidate",
        "record_id": candidate_id,
        "candidate_id": candidate_id,
        "aggregate_identity": report_dir.name,
        "candidate_revision": revision,
        "supersedes_candidate_id": supersedes,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "candidate_body_sha256": "",
        "trigger_kind": trigger_kind,
        "writer": writer,
        "writer_lineage_id": writer["writer_lineage_id"],
        "acceptance_identity": dict(acceptance_identity),
        "state": "candidate_materialized",
        "event_order_index": len(_automatic_payloads(report_dir)) + 1,
    }
    payload["candidate_body_sha256"] = canonical_body_sha256(
        payload,
        "candidate_body_sha256",
    )
    _append_automatic_event(report_dir, payload, outcome="candidate_materialized")
    return payload


def _review_context(
    report_dir: Path,
    candidate: Mapping[str, object],
    role_id: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Build immutable intent, frame, and exact four-field handoff."""
    route = _review_route(report_dir, role_id)
    prior_frames = _automatic_payloads(report_dir, "frame")
    matching_prior = [
        frame
        for frame in prior_frames
        if frame.get("review_role_id") == role_id
        and frame.get("candidate_id") == candidate.get("candidate_id")
    ]
    prior = (
        matching_prior[-1]
        if matching_prior
        else next(
            (
                frame
                for frame in reversed(prior_frames)
                if frame.get("review_role_id") == role_id
            ),
            None,
        )
    )
    if prior is not None:
        review_request_id = _required_text(prior, "review_request_id")
        review_context_id = _required_text(prior, "review_context_id")
        review_lineage_id = _required_text(prior, "review_lineage_id")
        reviewer_assignment_id = _required_text(prior, "reviewer_assignment_id")
        assigned_runtime_agent_id = prior.get("assigned_runtime_agent_id")
        prior_events = [
            event
            for event in _automatic_payloads(report_dir, "resume_event")
            if event.get("review_frame_id") == prior.get("review_frame_id")
        ]
        if prior_events:
            observed_result = prior_events[-1].get("observed_result")
            if isinstance(observed_result, Mapping):
                assigned_runtime_agent_id = observed_result.get(
                    "nested_runtime_agent_id"
                )
    else:
        review_request_id = _record_id(
            "w2-review-request",
            {
                "aggregate_identity": report_dir.name,
                "role_id": role_id,
            },
        )
        review_context_id = _record_id(
            "w2-review-context",
            {"review_request_id": review_request_id},
        )
        reviewer_assignment_id = _record_id(
            "w2-reviewer-assignment",
            {
                "review_request_id": review_request_id,
                "role_id": role_id,
                "agent_type": route["agent_type"],
            },
        )
        review_lineage_id = _record_id(
            "w2-reviewer-lineage",
            {
                "review_request_id": review_request_id,
                "review_context_id": review_context_id,
                "reviewer_assignment_id": reviewer_assignment_id,
                "role_id": role_id,
                "agent_type": route["agent_type"],
            },
        )
        assigned_runtime_agent_id = None
    intent_seed = {
        "aggregate_identity": report_dir.name,
        "review_request_id": review_request_id,
        "review_context_id": review_context_id,
        "review_lineage_id": review_lineage_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
    }
    intent_id = _record_id("w2-review-resume-intent", intent_seed)
    intent: dict[str, object] = {
        "schema": REVIEW_INTENT_SCHEMA,
        "schema_version": 1,
        "record_kind": "intent",
        "record_id": intent_id,
        "resume_intent_id": intent_id,
        **intent_seed,
        "resume_intent_body_sha256": "",
        "event_order_index": len(_automatic_payloads(report_dir)) + 1,
    }
    intent["resume_intent_body_sha256"] = canonical_body_sha256(
        intent,
        "resume_intent_body_sha256",
    )
    handoff = {
        "objective": "Independently review the exact current W2 candidate and return findings plus APPROVE, REVISE, or ESCALATE.",
        "owner_unit": "completion_authority",
        "fixed_source_packet": {
            "candidate_id": candidate["candidate_id"],
            "candidate_revision": candidate["candidate_revision"],
            "candidate_commit": candidate["candidate_commit"],
            "candidate_tree": candidate["candidate_tree"],
            "candidate_body_sha256": candidate["candidate_body_sha256"],
        },
        "acceptance_identity": candidate["acceptance_identity"],
    }
    if tuple(handoff) != MINIMAL_HANDOFF_KEYS:
        raise AutomaticReviewError("automatic_review:handoff_key_mismatch")
    frame_seed = {
        "resume_intent_id": intent_id,
        "review_lineage_id": review_lineage_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
        "reviewer_assignment_id": reviewer_assignment_id,
    }
    frame_id = _record_id("w2-review-frame", frame_seed)
    frame: dict[str, object] = {
        "schema": REVIEW_FRAME_SCHEMA,
        "schema_version": 3,
        "record_kind": "frame",
        "record_id": frame_id,
        "review_frame_id": frame_id,
        "review_frame_body_sha256": "",
        "aggregate_identity": report_dir.name,
        "resume_intent_id": intent_id,
        "resume_intent_body_sha256": intent["resume_intent_body_sha256"],
        "review_request_id": review_request_id,
        "review_context_id": review_context_id,
        "review_lineage_id": review_lineage_id,
        "reviewer_assignment_id": reviewer_assignment_id,
        "review_role_id": role_id,
        "reviewer_agent_type": route["agent_type"],
        "assigned_runtime_agent_id": assigned_runtime_agent_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
        "candidate_body_sha256": candidate["candidate_body_sha256"],
        "candidate_commit": candidate["candidate_commit"],
        "candidate_tree": candidate["candidate_tree"],
        "handoff": handoff,
        "state": "dispatch_pending",
        "event_order_index": _required_event_order_index(intent) + 1,
    }
    frame["review_frame_body_sha256"] = canonical_body_sha256(
        frame,
        "review_frame_body_sha256",
    )
    return intent, frame, handoff


def dispatch_current_candidate_review(
    workspace: Path,
    dispatcher: RuntimeDispatcher,
    *,
    role_id: str = "change_reviewer",
) -> dict[str, object]:
    """Dispatch or resume the exact current reviewer through canonical routing."""
    root = workspace.resolve()
    report_dir = _active_report_dir(root)
    candidate = _current_candidate(report_dir)
    intent, frame, handoff = _review_context(report_dir, candidate, role_id)
    _append_automatic_event(report_dir, intent, outcome="dispatch_pending")
    _append_automatic_event(report_dir, frame, outcome="dispatch_pending")
    try:
        observed = dispatcher(handoff)
    except Exception as exc:
        blocker_id = _record_id(
            "w2-review-dispatch-blocked",
            {
                "frame_id": frame["review_frame_id"],
                "error_type": type(exc).__name__,
            },
        )
        blocker = {
            "schema": "agent-canon.review-dispatch-blocker.v1",
            "schema_version": 1,
            "record_kind": "dispatch_blocker",
            "record_id": blocker_id,
            "aggregate_identity": report_dir.name,
            "review_frame_id": frame["review_frame_id"],
            "candidate_id": candidate["candidate_id"],
            "code": "automatic_review:dispatch_blocked",
            "evidence": [type(exc).__name__],
            "state": "dispatch_blocked",
            "event_order_index": _required_event_order_index(frame) + 1,
        }
        _append_automatic_event(report_dir, blocker, outcome="dispatch_blocked")
        return blocker
    if not isinstance(observed, Mapping):
        raise AutomaticReviewError("automatic_review:dispatch_result_invalid")
    route = _review_route(report_dir, role_id)
    runtime_action = _required_text(observed, "runtime_action")
    runtime_id = _required_text(observed, "nested_runtime_agent_id")
    parent_runtime_id = _required_text(observed, "parent_runtime_agent_id")
    provider_status = _required_text(observed, "provider_status")
    if runtime_action not in {"resumed", "spawned"}:
        raise AutomaticReviewError("automatic_review:dispatch_result_invalid")
    if provider_status not in {"running", *TERMINAL_RUNTIME_STATUSES}:
        raise AutomaticReviewError("automatic_review:dispatch_result_invalid")
    writer = candidate.get("writer")
    if not isinstance(writer, Mapping):
        raise AutomaticReviewError("automatic_review:writer_lineage_missing")
    if runtime_id == writer.get("runtime_agent_id"):
        raise AutomaticReviewError("automatic_review:self_review_forbidden")
    prior_runtime = frame.get("assigned_runtime_agent_id")
    if prior_runtime is not None:
        if runtime_action != "resumed" or runtime_id != prior_runtime:
            raise AutomaticReviewError("automatic_review:fresh_reviewer_bypass")
    elif runtime_action == "resumed":
        raise AutomaticReviewError("automatic_review:resume_locator_missing")
    resume_mode = (
        "provider_resume_same_runtime"
        if runtime_action == "resumed"
        else "owner_selected_replacement_runtime"
    )
    event_seed = {
        "aggregate_identity": report_dir.name,
        "resume_intent_id": intent["resume_intent_id"],
        "review_frame_id": frame["review_frame_id"],
        "candidate_id": candidate["candidate_id"],
        "candidate_commit": candidate["candidate_commit"],
        "dispatch_attempt": 1,
        "resume_mode": resume_mode,
        "runtime_action": runtime_action,
        "provider_object_id": runtime_id,
        "provider_parent_object_id": parent_runtime_id,
        "provider_status": provider_status,
    }
    event_id = _record_id("w2-review-resume-event", event_seed)
    event: dict[str, object] = {
        "schema": RESUME_EVENT_SCHEMA,
        "schema_version": 3,
        "record_kind": "resume_event",
        "record_id": event_id,
        "resume_event_id": event_id,
        "event_kind": "terminal_resume_dispatch_observed",
        "aggregate_identity": report_dir.name,
        "resume_intent_id": intent["resume_intent_id"],
        "resume_intent_body_sha256": intent["resume_intent_body_sha256"],
        "review_frame_id": frame["review_frame_id"],
        "review_frame_body_sha256": frame["review_frame_body_sha256"],
        "review_lineage_id": frame["review_lineage_id"],
        "review_request_id": frame["review_request_id"],
        "review_context_id": frame["review_context_id"],
        "reviewer_assignment_id": frame["reviewer_assignment_id"],
        "reviewer_lineage_id": frame["review_lineage_id"],
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
        "candidate_body_sha256": candidate["candidate_body_sha256"],
        "candidate_commit": candidate["candidate_commit"],
        "candidate_tree": candidate["candidate_tree"],
        "dispatch_attempt": 1,
        "resume_mode": resume_mode,
        "observed_result": {
            "runtime_action": runtime_action,
            "runtime_provider": "codex",
            "provider_instance_id": _required_text(observed, "provider_instance_id"),
            "provider_operation_id": _required_text(observed, "provider_operation_id"),
            "provider_operation_version": _required_text(
                observed,
                "provider_operation_version",
            ),
            "provider_object_kind": "nested_agent_dispatch",
            "provider_object_id": runtime_id,
            "provider_parent_object_id": parent_runtime_id,
            "provider_status": provider_status,
            "parent_runtime_agent_id": parent_runtime_id,
            "nested_runtime_agent_id": runtime_id,
            "team_manifest_role_instance_ref": route["team_manifest_role_instance_ref"],
            "role_id": role_id,
            "agent_type": route["agent_type"],
            "reviewer_assignment_id": frame["reviewer_assignment_id"],
            "reviewer_lineage_id": frame["review_lineage_id"],
            "write_policy": "artifacts_only",
        },
        "same_context_fingerprint": hashlib.sha256(
            canonical_json_bytes(
                {
                    "review_request_id": frame["review_request_id"],
                    "review_context_id": frame["review_context_id"],
                    "review_lineage_id": frame["review_lineage_id"],
                    "reviewer_assignment_id": frame["reviewer_assignment_id"],
                }
            )
        ).hexdigest(),
        "proposed_from_review_state": "dispatch_pending",
        "proposed_to_review_state": "dispatched",
        "event_order_index": _required_event_order_index(frame) + 1,
        "observed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resume_event_body_sha256": "",
    }
    event["resume_event_body_sha256"] = canonical_body_sha256(
        event,
        "resume_event_body_sha256",
    )
    _append_automatic_event(report_dir, event, outcome="dispatched")
    provider_record = dict(observed)
    provider_record.setdefault("provider_kind", "codex_runtime")
    provider_record.setdefault("provider_object_kind", "nested_agent_dispatch")
    provider_record.setdefault("provider_object_id", runtime_id)
    provider_record.setdefault(
        "provider_object_version",
        _required_text(observed, "provider_operation_version"),
    )
    provider_record.setdefault("provider_parent_object_id", parent_runtime_id)
    provider_record.setdefault("acknowledgement_order_index", 1)
    acknowledgement = materialize_external_projection_acknowledgement(
        event,
        provider_record,
    )
    ack_payload = {
        **acknowledgement,
        "record_kind": "external_projection",
        "record_id": acknowledgement["external_projection_ack_id"],
    }
    _append_automatic_event(report_dir, ack_payload, outcome="dispatched")
    return {
        "schema": "agent-canon.review-dispatch-result.v1",
        "status": "dispatched",
        "candidate": candidate,
        "intent": intent,
        "frame": frame,
        "event": event,
        "external_projection": acknowledgement,
    }


def _review_text_without_rejected_hypotheses(text: str) -> str:
    """Exclude adjudicated rejected table rows from approval checks."""
    return markdown_without_adjudicated_rejected_hypotheses(text)


def record_current_review_decision(
    workspace: Path,
    *,
    role_id: str = "change_reviewer",
) -> dict[str, object]:
    """Bind the generated current review artifact to the exact candidate."""
    root = workspace.resolve()
    report_dir = _active_report_dir(root)
    candidate = _current_candidate(report_dir)
    frames = [
        frame
        for frame in _automatic_payloads(report_dir, "frame")
        if frame.get("review_role_id") == role_id
        and frame.get("candidate_id") == candidate.get("candidate_id")
    ]
    if len(frames) != 1:
        raise AutomaticReviewError("automatic_review:review_frame_missing")
    frame = frames[0]
    runtime_events = [
        event
        for event in _automatic_payloads(report_dir, "resume_event")
        if event.get("review_frame_id") == frame.get("review_frame_id")
    ]
    if len(runtime_events) != 1:
        raise AutomaticReviewError("automatic_review:reviewer_resume_locator_missing")
    event = runtime_events[0]
    artifact_path = Path(_review_route(report_dir, role_id)["review_artifact"])
    absolute_artifact = report_dir / artifact_path
    if not absolute_artifact.is_file():
        raise AutomaticReviewError("automatic_review:review_artifact_missing")
    identity = materialize_artifact_identity(root, absolute_artifact)
    text = absolute_artifact.read_text(encoding="utf-8")
    finding_rows = parse_finding_rows(text)
    derived_outcome = derive_review_outcome(finding_rows) if finding_rows else None
    decisions = DECISION_LINE_PATTERN.findall(text)
    if derived_outcome is None and not decisions:
        raise AutomaticReviewError("automatic_review:decision_missing")
    if decisions and len({decision.upper() for decision in decisions}) != 1:
        raise AutomaticReviewError("automatic_review:decision_ambiguous")
    decision = decisions[-1].upper() if decisions else derived_outcome.upper()
    if derived_outcome == "changes-required" and decision in {"APPROVE", "ACCEPT"}:
        raise AutomaticReviewError("automatic_review:approve_with_blocking_finding")
    if derived_outcome == "accept" and decision in {"REVISE", "ESCALATE"}:
        # A reviewer may still explicitly escalate a question, but a plain
        # non-blocking finding must not silently become a required change.
        if not re.search(r"(?im)^\s*(?:escalate|question)\b", text):
            decision = "ACCEPT"
    decision = canonicalize_review_decision(decision)
    if decision == "APPROVE" and re.search(
        r"(?im)^\s*(?:[-*]|\|)\s*.*\b(?:fail|revise|required_change|blocker)\b",
        _review_text_without_rejected_hypotheses(text),
    ):
        raise AutomaticReviewError("automatic_review:approve_with_findings")
    observed_result = event.get("observed_result")
    if not isinstance(observed_result, Mapping):
        raise AutomaticReviewError("automatic_review:resume_event_invalid")
    reviewer_runtime_agent_id = observed_result.get("nested_runtime_agent_id")
    if not isinstance(reviewer_runtime_agent_id, str) or not reviewer_runtime_agent_id:
        raise AutomaticReviewError("automatic_review:resume_event_invalid")
    decision_seed = {
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
        "review_frame_id": frame["review_frame_id"],
        "reviewer_runtime_agent_id": reviewer_runtime_agent_id,
        "decision": decision,
        "artifact_identity_record_id": identity["identity_record_id"],
    }
    decision_id = _record_id("w2-review-decision", decision_seed)
    payload: dict[str, object] = {
        "schema": REVIEW_DECISION_SCHEMA,
        "schema_version": 1,
        "record_kind": "decision",
        "record_id": decision_id,
        "event_id": decision_id,
        "event_kind": "review_decision_recorded",
        "event_body_sha256": "",
        "aggregate_identity": report_dir.name,
        "review_request_id": frame["review_request_id"],
        "review_context_id": frame["review_context_id"],
        "review_lineage_id": frame["review_lineage_id"],
        "review_frame_id": frame["review_frame_id"],
        "review_frame_body_sha256": frame["review_frame_body_sha256"],
        "reviewer_assignment_id": frame["reviewer_assignment_id"],
        "reviewer_runtime_agent_id": reviewer_runtime_agent_id,
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["candidate_revision"],
        "candidate_body_sha256": candidate["candidate_body_sha256"],
        "candidate_commit": candidate["candidate_commit"],
        "candidate_tree": candidate["candidate_tree"],
        "decision": decision,
        "review_artifact_identity": identity,
        "state": (
            "approved"
            if decision == "APPROVE"
            else "repair_returned_to_writer"
            if decision == "REVISE"
            else "dispatch_blocked"
        ),
        "event_order_index": len(_automatic_payloads(report_dir)) + 1,
    }
    payload["event_body_sha256"] = canonical_body_sha256(
        payload,
        "event_body_sha256",
    )
    _append_automatic_event(report_dir, payload, outcome=str(payload["state"]))
    return payload


def resolve_current_review_state(workspace: Path) -> dict[str, object]:
    """Return the unique current review state projected from canonical L."""
    report_dir = _active_report_dir(workspace.resolve())
    candidate = _current_candidate(report_dir)
    if candidate.get("candidate_body_sha256") != canonical_body_sha256(
        candidate, "candidate_body_sha256"
    ):
        raise AutomaticReviewError("automatic_review:candidate_body_hash_mismatch")
    decisions = [
        decision
        for decision in _automatic_payloads(report_dir, "decision")
        if decision.get("candidate_id") == candidate.get("candidate_id")
    ]
    decision = decisions[-1] if decisions else None
    if decision is not None:
        if decision.get("event_body_sha256") != canonical_body_sha256(
            decision, "event_body_sha256"
        ):
            raise AutomaticReviewError("automatic_review:decision_body_hash_mismatch")
        if decision.get("candidate_body_sha256") != candidate.get(
            "candidate_body_sha256"
        ):
            raise AutomaticReviewError("automatic_review:review_stale")
    dispatch_blockers = [
        blocker
        for blocker in _automatic_payloads(report_dir, "dispatch_blocker")
        if blocker.get("candidate_id") == candidate.get("candidate_id")
    ]
    return {
        "schema": "agent-canon.current-review-state.v1",
        "candidate": candidate,
        "decision": decision,
        "dispatch_blocker": dispatch_blockers[-1] if dispatch_blockers else None,
        "publication_unlocked": bool(
            isinstance(decision, Mapping)
            and decision.get("decision") == "APPROVE"
        ),
    }


def resolve_review_eligibility(workspace: Path) -> dict[str, object]:
    """Regenerate the current review eligibility from validation and L."""
    root = workspace.resolve()
    from report_artifact_checks import resolve_validation_result

    validation = resolve_validation_result(root)
    report_dir = _active_report_dir(root)
    candidate = _current_candidate(report_dir)
    frames = [
        frame
        for frame in _automatic_payloads(report_dir, "frame")
        if frame.get("candidate_id") == candidate.get("candidate_id")
        and frame.get("review_role_id") == "change_reviewer"
    ]
    failure_codes: list[str] = []
    frame = frames[-1] if frames else None
    if validation.get("outcome") != "pass":
        failure_codes.append("review_eligibility:validation_result_not_pass")
    validation_candidate = validation.get("candidate")
    validation_candidate_id = (
        validation_candidate.get("candidate_id")
        if isinstance(validation_candidate, Mapping)
        else None
    )
    if validation_candidate_id != candidate.get("candidate_id"):
        failure_codes.append("review_eligibility:candidate_mismatch")
    if frame is None:
        failure_codes.append("review_eligibility:frame_mismatch")
    else:
        if frame.get("review_frame_body_sha256") != canonical_body_sha256(
            frame,
            "review_frame_body_sha256",
        ):
            failure_codes.append("review_eligibility:frame_mismatch")
    assigned_runtime_agent_id = None
    if frame is not None:
        assigned_runtime_agent_id = frame.get("assigned_runtime_agent_id")
        for event in _automatic_payloads(report_dir, "resume_event"):
            if event.get("review_frame_id") == frame.get("review_frame_id"):
                observed = event.get("observed_result")
                if isinstance(observed, Mapping):
                    assigned_runtime_agent_id = observed.get("nested_runtime_agent_id")
    producer = validation.get("producer_evidence")
    producer_runtime_agent_id = (
        producer.get("producer_runtime_agent_id")
        if isinstance(producer, Mapping)
        else None
    )
    writer = candidate.get("writer")
    writer_runtime_agent_id = (
        writer.get("runtime_agent_id") if isinstance(writer, Mapping) else None
    )
    if assigned_runtime_agent_id != producer_runtime_agent_id:
        failure_codes.append("review_eligibility:producer_not_assigned_reviewer")
    if assigned_runtime_agent_id == writer_runtime_agent_id:
        failure_codes.append("review_eligibility:self_review_forbidden")
    if not isinstance(assigned_runtime_agent_id, str) or not assigned_runtime_agent_id:
        failure_codes.append("review_eligibility:dispatch_blocked")
    failure_codes = sorted(set(failure_codes), key=lambda item: item.encode("utf-8"))
    outcome = "eligible" if not failure_codes else "ineligible"
    frame_id = frame.get("review_frame_id") if isinstance(frame, Mapping) else None
    frame_hash = (
        frame.get("review_frame_body_sha256") if isinstance(frame, Mapping) else None
    )
    core: dict[str, object] = {
        "schema": "agent-canon.review-eligibility-projection.v1",
        "schema_version": 1,
        "validation_result_ref": {
            "validation_result_id": validation.get("validation_result_id"),
            "validation_result_body_sha256": validation.get(
                "validation_result_body_sha256"
            ),
        },
        "candidate_id": candidate.get("candidate_id"),
        "candidate_revision": candidate.get("candidate_revision"),
        "review_lineage_id": frame.get("review_lineage_id")
        if isinstance(frame, Mapping)
        else None,
        "review_frame_ref": {
            "review_frame_id": frame_id,
            "review_frame_body_sha256": frame_hash,
        },
        "reviewer": {
            "required_role_id": "change_reviewer",
            "assigned_runtime_agent_id": assigned_runtime_agent_id,
            "validation_producer_runtime_agent_id": producer_runtime_agent_id,
            "writer_runtime_agent_id": writer_runtime_agent_id,
        },
        "outcome": outcome,
        "failure_codes": failure_codes,
        "review_eligibility_body_sha256": "",
    }
    validation_ref = core["validation_result_ref"]
    if not isinstance(validation_ref, Mapping):
        raise AutomaticReviewError("review_eligibility:schema_mismatch")
    core["review_eligibility_id"] = (
        "review-eligibility:"
        + hashlib.sha256(
            canonical_json_bytes(
                {
                    "validation_result_id": validation_ref["validation_result_id"],
                    "validation_result_body_sha256": validation_ref[
                        "validation_result_body_sha256"
                    ],
                    "candidate_id": core["candidate_id"],
                    "candidate_revision": core["candidate_revision"],
                    "review_lineage_id": core["review_lineage_id"],
                    "review_frame_id": frame_id,
                    "review_frame_body_sha256": frame_hash,
                    "required_role_id": "change_reviewer",
                    "assigned_reviewer_runtime_agent_id": assigned_runtime_agent_id,
                    "outcome": outcome,
                    "failure_codes": failure_codes,
                }
            )
        ).hexdigest()
    )
    core["review_eligibility_body_sha256"] = canonical_body_sha256(
        core,
        "review_eligibility_body_sha256",
    )
    return core
