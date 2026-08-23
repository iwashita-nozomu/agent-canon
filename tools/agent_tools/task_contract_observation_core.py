#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Defines task-local contract observation schema and state transitions.
# upstream design ../../documents/runtime/task-contract-observation.md defines the state machine
# downstream implementation ./task_contract_observation.py records and evaluates run evidence
# downstream implementation ../../tests/agent_tools/test_task_contract_observation.py tests it
# @dependency-end
"""Task-local contract observation schema and state-machine evaluation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SCHEMA = "agent-canon.task-contract-observation.v1"
SCHEMA_KEY = "contract_observation_schema"
KIND_KEY = "contract_observation"
OBSERVED_KIND = "observed"
NONE_KIND = "none"
ARCHIVE_ROUTE = "agent-canon-log:agent-reports"
PHASES = frozenset(
    {
        "intake",
        "planning",
        "design",
        "implementation",
        "validation",
        "review",
        "closeout",
        "publication",
    }
)
TRIGGERS = frozenset(
    {"required", "selected", "guardrail", "warning", "failure", "rejection", "conflict"}
)
OPEN_OUTCOMES = frozenset({"blocked", "violated"})
TERMINAL_OUTCOMES = frozenset({"satisfied", "deferred_with_issue", "not_applicable"})
OUTCOMES = OPEN_OUTCOMES | TERMINAL_OUTCOMES
PLACEHOLDERS = frozenset({"", "-", "missing", "none", "pending", "tbd", "todo", "unknown"})
IDENTITY_FIELDS = ("contract_id", "contract_source", "phase", "trigger", "owner")
OBSERVED_REQUIRED = (
    SCHEMA_KEY,
    KIND_KEY,
    "observation_id",
    "sequence",
    *IDENTITY_FIELDS,
    "outcome",
    "evidence_ref",
    "response",
)
NONE_REQUIRED = (SCHEMA_KEY, KIND_KEY, "owner", "reason")
FIELD_ORDER = (
    SCHEMA_KEY,
    KIND_KEY,
    "observation_id",
    "sequence",
    "contract_id",
    "contract_source",
    "phase",
    "trigger",
    "outcome",
    "owner",
    "evidence_ref",
    "response",
    "issue_ref",
    "reason",
)
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@#,+-]*$")
OBSERVATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")


@dataclass(frozen=True)
class Finding:
    """One validation finding."""

    code: str
    line: int
    observation_id: str
    detail: str


@dataclass(frozen=True)
class ObservationState:
    """Latest accepted state for one immutable observation identity."""

    observation_id: str
    contract_id: str
    contract_source: str
    phase: str
    trigger: str
    owner: str
    sequence: int
    outcome: str
    evidence_ref: str
    response: str
    issue_ref: str


@dataclass(frozen=True)
class Evaluation:
    """Result for one observation stream."""

    status: str
    stream_digest: str
    event_count: int
    observation_count: int
    none_count: int
    unresolved_ids: tuple[str, ...]
    states: tuple[ObservationState, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class ParsedRecord:
    """Parsed record with source-line identity."""

    line: int
    fields: Mapping[str, str]


def parse_token_fields(payload: str) -> tuple[dict[str, str], str]:
    """Parse whitespace-delimited key=value tokens."""

    fields: dict[str, str] = {}
    for token in payload.strip().split():
        if "=" not in token:
            return {}, f"malformed-token:{token}"
        key, value = token.split("=", 1)
        if not key or key in fields:
            return {}, f"{'empty' if not key else 'duplicate'}-key:{key}"
        fields[key] = value
    return (fields, "") if fields else ({}, "empty-record")


def render_fields(fields: Mapping[str, str]) -> str:
    """Render fields in a stable order."""

    keys = [key for key in FIELD_ORDER if key in fields]
    keys.extend(sorted(set(fields) - set(FIELD_ORDER)))
    return " ".join(f"{key}={fields[key]}" for key in keys)


def event_payloads(text: str) -> tuple[ParsedRecord, ...]:
    """Extract schema-marked records from Markdown lines."""

    marker = f"{SCHEMA_KEY}="
    records: list[ParsedRecord] = []
    for line, raw in enumerate(text.splitlines(), start=1):
        start = raw.find(marker)
        if start < 0:
            continue
        fields, error = parse_token_fields(raw[start:])
        records.append(ParsedRecord(line, fields if not error else {"_parse_error": error}))
    return tuple(records)


def finding(code: str, record: ParsedRecord, detail: str) -> Finding:
    """Build a finding with stable identity."""

    return Finding(code, record.line, record.fields.get("observation_id", "-"), detail)


def placeholder(value: str) -> bool:
    """Return whether a value is unresolved."""

    return value.strip().casefold() in PLACEHOLDERS


def record_findings(record: ParsedRecord) -> list[Finding]:
    """Validate one record independently of stream transitions."""

    fields = record.fields
    if "_parse_error" in fields:
        return [finding("parse_error", record, fields["_parse_error"])]
    findings: list[Finding] = []
    if fields.get(SCHEMA_KEY) != SCHEMA:
        findings.append(finding("schema_invalid", record, fields.get(SCHEMA_KEY, "missing")))
    for key, value in fields.items():
        if TOKEN_RE.fullmatch(value) is None:
            findings.append(finding("token_value_invalid", record, key))

    kind = fields.get(KIND_KEY, "")
    required = OBSERVED_REQUIRED if kind == OBSERVED_KIND else NONE_REQUIRED
    if kind not in {OBSERVED_KIND, NONE_KIND}:
        findings.append(finding("kind_invalid", record, kind or "missing"))
        return findings
    for key in required:
        value = fields.get(key, "")
        if not value or (key != KIND_KEY and placeholder(value)):
            findings.append(finding("required_field_missing", record, key))
    if kind == NONE_KIND:
        return findings

    observation_id = fields.get("observation_id", "")
    if observation_id and OBSERVATION_ID_RE.fullmatch(observation_id) is None:
        findings.append(finding("observation_id_invalid", record, observation_id))
    sequence = fields.get("sequence", "")
    if sequence and (not sequence.isdigit() or int(sequence) < 1):
        findings.append(finding("sequence_invalid", record, sequence))
    for key, allowed in (("phase", PHASES), ("trigger", TRIGGERS), ("outcome", OUTCOMES)):
        value = fields.get(key, "")
        if value and value not in allowed:
            findings.append(finding(f"{key}_invalid", record, value))
    outcome = fields.get("outcome")
    if outcome == "deferred_with_issue" and placeholder(fields.get("issue_ref", "")):
        findings.append(finding("issue_ref_required", record, outcome))
    if outcome == "not_applicable" and placeholder(fields.get("reason", "")):
        findings.append(finding("reason_required", record, outcome))
    return findings


def transition_allowed(previous: str, current: str) -> bool:
    """Return whether an append-only state transition is legal."""

    if previous == "blocked":
        return current in {"blocked", "violated"} | TERMINAL_OUTCOMES
    if previous == "violated":
        return current in {"violated"} | TERMINAL_OUTCOMES
    return False


def _state(observation_id: str, record: ParsedRecord) -> ObservationState:
    fields = record.fields
    return ObservationState(
        observation_id=observation_id,
        contract_id=fields["contract_id"],
        contract_source=fields["contract_source"],
        phase=fields["phase"],
        trigger=fields["trigger"],
        owner=fields["owner"],
        sequence=int(fields["sequence"]),
        outcome=fields["outcome"],
        evidence_ref=fields["evidence_ref"],
        response=fields["response"],
        issue_ref=fields.get("issue_ref", ""),
    )


def evaluate_records(records: Sequence[ParsedRecord], *, require_terminal: bool) -> Evaluation:
    """Evaluate coverage, identity, sequence, and terminal-state invariants."""

    findings = [item for record in records for item in record_findings(record)]
    observed = [record for record in records if record.fields.get(KIND_KEY) == OBSERVED_KIND]
    none_records = [record for record in records if record.fields.get(KIND_KEY) == NONE_KIND]
    if not records:
        findings.append(Finding("coverage_missing", 0, "-", "no-records"))
    if observed and none_records:
        findings.append(
            Finding("coverage_ambiguous", none_records[0].line, "-", "none-and-observed")
        )
    canonical_none = {render_fields(record.fields) for record in none_records}
    if len(canonical_none) > 1:
        findings.append(
            Finding("none_record_collision", none_records[1].line, "-", "distinct-none")
        )

    latest: dict[str, ParsedRecord] = {}
    by_sequence: dict[tuple[str, int], str] = {}
    invalid_lines = {item.line for item in findings}
    for record in observed:
        fields = record.fields
        if record.line in invalid_lines:
            continue
        observation_id = fields["observation_id"]
        sequence = int(fields["sequence"])
        canonical = render_fields(fields)
        key = (observation_id, sequence)
        if key in by_sequence:
            if by_sequence[key] != canonical:
                findings.append(finding("sequence_collision", record, str(sequence)))
            continue
        by_sequence[key] = canonical
        previous = latest.get(observation_id)
        if previous is None:
            if sequence != 1:
                findings.append(finding("sequence_start_invalid", record, str(sequence)))
            else:
                latest[observation_id] = record
            continue

        previous_fields = previous.fields
        for identity_key in IDENTITY_FIELDS:
            if fields[identity_key] != previous_fields[identity_key]:
                findings.append(finding("identity_collision", record, identity_key))
        expected = int(previous_fields["sequence"]) + 1
        if sequence != expected:
            findings.append(
                finding("sequence_gap", record, f"expected={expected}:observed={sequence}")
            )
        if not transition_allowed(previous_fields["outcome"], fields["outcome"]):
            findings.append(
                finding(
                    "transition_invalid",
                    record,
                    f"{previous_fields['outcome']}->{fields['outcome']}",
                )
            )
        if not any(item.line == record.line for item in findings):
            latest[observation_id] = record

    unresolved = tuple(
        sorted(
            observation_id
            for observation_id, record in latest.items()
            if record.fields["outcome"] in OPEN_OUTCOMES
        )
    )
    if require_terminal:
        findings.extend(
            Finding("unresolved_observation", 0, observation_id, "nonterminal")
            for observation_id in unresolved
        )
    digest_input = "\n".join(render_fields(record.fields) for record in records)
    return Evaluation(
        status="pass" if not findings else "fail",
        stream_digest=hashlib.sha256(digest_input.encode()).hexdigest(),
        event_count=len(records),
        observation_count=len(latest),
        none_count=len(canonical_none),
        unresolved_ids=unresolved,
        states=tuple(_state(key, record) for key, record in sorted(latest.items())),
        findings=tuple(findings),
    )


def evaluate_text(text: str, *, require_terminal: bool = True) -> Evaluation:
    """Evaluate records extracted from workflow monitoring."""

    return evaluate_records(event_payloads(text), require_terminal=require_terminal)


def evaluate_payloads(payloads: Sequence[str]) -> Evaluation:
    """Evaluate direct payloads without Markdown transport."""

    records: list[ParsedRecord] = []
    for line, payload in enumerate(payloads, start=1):
        fields, error = parse_token_fields(payload)
        records.append(ParsedRecord(line, fields if not error else {"_parse_error": error}))
    return evaluate_records(records, require_terminal=True)


def derived_observation_id(fields: Mapping[str, str]) -> str:
    """Derive a stable id from immutable contract identity fields."""

    identity = "\0".join(fields.get(key, "") for key in IDENTITY_FIELDS)
    return f"contract-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"


def next_sequence(existing: Sequence[ParsedRecord], observation_id: str) -> int:
    """Return the next sequence for one observation id."""

    sequences = [
        int(record.fields["sequence"])
        for record in existing
        if record.fields.get("observation_id") == observation_id
        and record.fields.get("sequence", "").isdigit()
    ]
    return max(sequences, default=0) + 1


def normalize_record_argument(raw: str, existing: Sequence[ParsedRecord]) -> str:
    """Validate a CLI record and derive schema, identity, and sequence."""

    fields, error = parse_token_fields(raw)
    if error:
        raise ValueError(error)
    fields.setdefault(SCHEMA_KEY, SCHEMA)
    fields.setdefault(KIND_KEY, OBSERVED_KIND)
    if fields[KIND_KEY] == OBSERVED_KIND:
        fields.setdefault("observation_id", derived_observation_id(fields))
        fields.setdefault("sequence", str(next_sequence(existing, fields["observation_id"])))
    candidate = ParsedRecord(max((record.line for record in existing), default=0) + 1, fields)
    evaluation = evaluate_records((*existing, candidate), require_terminal=False)
    if evaluation.status != "pass":
        detail = ";".join(
            f"{item.code}:{item.observation_id}:{item.detail}" for item in evaluation.findings
        )
        raise ValueError(detail)
    return render_fields(fields)
