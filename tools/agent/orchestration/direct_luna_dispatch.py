# @dependency-start
# contract tool
# responsibility Builds and verifies bounded direct-Luna subagent handoff packets.
# upstream design ../../agents/skills/direct-luna-communication.md direct Luna routing contract
# downstream implementation ../../tests/tools/test_direct_luna_dispatch.py validates packet behavior
# @dependency-end
"""Build and verify bounded direct-Luna subagent handoff packets.

Logical role, Skill procedure, execution profile, and authority remain
independent.  The parent selects role and Skills; this module only validates
and serializes the bounded handoff.  Requested runtime values alone are not
execution evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Literal, Sequence

LUNA_MODEL = "gpt-5.6-luna"
PACKET_SCHEMA_ID = "direct_luna_handoff_packet_v1"
EVIDENCE_SCHEMA_ID = "direct_luna_runtime_evidence_v1"
FORK_TURNS = "none"
CONTINUATION_POLICY = "active_child_update_or_fresh_bounded_spawn"
RESUME_POLICY = "unverified_native_resume_forbidden"

AuthorityMode = Literal["read-only", "workspace-write"]
ReasoningEffort = Literal["low", "medium", "high", "xhigh"]
_ALLOWED_AUTHORITY = frozenset({"read-only", "workspace-write"})
_ALLOWED_EFFORT = frozenset({"low", "medium", "high", "xhigh"})


@dataclass(frozen=True, slots=True)
class DirectLunaBlocker(Exception):
    """Typed blocker returned when direct-Luna execution cannot be proven."""

    code: Literal["direct_luna_unavailable", "direct_luna_unverified"]
    message: str
    requested_model: str
    requested_reasoning_effort: str
    effective_model: str | None = None
    effective_reasoning_effort: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "message": self.message,
            "requested_model": self.requested_model,
            "requested_reasoning_effort": self.requested_reasoning_effort,
            "effective_model": self.effective_model,
            "effective_reasoning_effort": self.effective_reasoning_effort,
        }


@dataclass(frozen=True, slots=True)
class DirectLunaHandoffPacket:
    logical_role_id: str
    skill_ids: tuple[str, ...]
    model: str
    reasoning_effort: ReasoningEffort
    authority: AuthorityMode
    allowed_paths: tuple[str, ...]
    do_not_read: tuple[str, ...]
    expected_output: str
    validation_route: str
    objective: str
    context: str
    request_clause_ids: tuple[str, ...] = ()
    schema_id: str = PACKET_SCHEMA_ID
    fork_turns: str = FORK_TURNS
    continuation_policy: str = CONTINUATION_POLICY
    resume_policy: str = RESUME_POLICY

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_id": self.schema_id,
            "logical_role_id": self.logical_role_id,
            "skill_ids": list(self.skill_ids),
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "authority": self.authority,
            "allowed_paths": list(self.allowed_paths),
            "do_not_read": list(self.do_not_read),
            "expected_output": self.expected_output,
            "validation_route": self.validation_route,
            "objective": self.objective,
            "context": self.context,
            "request_clause_ids": list(self.request_clause_ids),
            "fork_turns": self.fork_turns,
            "continuation_policy": self.continuation_policy,
            "resume_policy": self.resume_policy,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )


@dataclass(frozen=True, slots=True)
class DirectLunaRuntimeEvidence:
    requested_model: str
    requested_reasoning_effort: str
    effective_model: str
    effective_reasoning_effort: str
    schema_id: str = EVIDENCE_SCHEMA_ID

    def as_dict(self) -> dict[str, str]:
        return {
            "schema_id": self.schema_id,
            "requested_model": self.requested_model,
            "requested_reasoning_effort": self.requested_reasoning_effort,
            "effective_model": self.effective_model,
            "effective_reasoning_effort": self.effective_reasoning_effort,
        }


def _required_text(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _unique_ids(name: str, values: Sequence[str], *, required: bool) -> tuple[str, ...]:
    normalized = tuple(_required_text(name, value) for value in values)
    if required and not normalized:
        raise ValueError(f"{name} must contain at least one entry")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return normalized


def _bounded_paths(name: str, values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for raw in values:
        value = _required_text(name, raw).replace("\\", "/")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"{name} entries must be repository-relative and bounded: {raw!r}"
            )
        canonical = path.as_posix()
        if canonical in {"", "."}:
            raise ValueError(f"{name} entries must identify a bounded path")
        normalized.append(canonical)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(normalized)


def build_direct_luna_packet(
    *,
    logical_role_id: str,
    skill_ids: Sequence[str],
    reasoning_effort: ReasoningEffort,
    authority: AuthorityMode,
    allowed_paths: Sequence[str],
    do_not_read: Sequence[str],
    expected_output: str,
    validation_route: str,
    objective: str,
    context: str,
    request_clause_ids: Sequence[str] = (),
) -> DirectLunaHandoffPacket:
    if reasoning_effort not in _ALLOWED_EFFORT:
        raise ValueError(f"unsupported reasoning_effort: {reasoning_effort!r}")
    if authority not in _ALLOWED_AUTHORITY:
        raise ValueError(f"unsupported authority: {authority!r}")

    bounded_allowed_paths = _bounded_paths("allowed_paths", allowed_paths)
    bounded_do_not_read = _bounded_paths("do_not_read", do_not_read)
    if authority == "workspace-write" and not bounded_allowed_paths:
        raise ValueError("workspace-write authority requires at least one allowed path")
    overlap = set(bounded_allowed_paths) & set(bounded_do_not_read)
    if overlap:
        joined = ", ".join(sorted(overlap))
        raise ValueError(f"allowed_paths and do_not_read overlap: {joined}")

    return DirectLunaHandoffPacket(
        logical_role_id=_required_text("logical_role_id", logical_role_id),
        skill_ids=_unique_ids("skill_ids", skill_ids, required=True),
        model=LUNA_MODEL,
        reasoning_effort=reasoning_effort,
        authority=authority,
        allowed_paths=bounded_allowed_paths,
        do_not_read=bounded_do_not_read,
        expected_output=_required_text("expected_output", expected_output),
        validation_route=_required_text("validation_route", validation_route),
        objective=_required_text("objective", objective),
        context=_required_text("context", context),
        request_clause_ids=_unique_ids(
            "request_clause_ids", request_clause_ids, required=False
        ),
    )


def verify_direct_luna_runtime(
    packet: DirectLunaHandoffPacket,
    *,
    override_available: bool,
    effective_model: str | None,
    effective_reasoning_effort: str | None,
) -> DirectLunaRuntimeEvidence:
    if not override_available:
        raise DirectLunaBlocker(
            code="direct_luna_unavailable",
            message="the runtime rejected or does not expose direct model override",
            requested_model=packet.model,
            requested_reasoning_effort=packet.reasoning_effort,
            effective_model=effective_model,
            effective_reasoning_effort=effective_reasoning_effort,
        )
    if not effective_model or not effective_reasoning_effort:
        raise DirectLunaBlocker(
            code="direct_luna_unverified",
            message="effective model and reasoning effort readback are required",
            requested_model=packet.model,
            requested_reasoning_effort=packet.reasoning_effort,
            effective_model=effective_model,
            effective_reasoning_effort=effective_reasoning_effort,
        )
    if (
        effective_model != packet.model
        or effective_reasoning_effort != packet.reasoning_effort
    ):
        raise DirectLunaBlocker(
            code="direct_luna_unverified",
            message="effective child runtime does not match the requested profile",
            requested_model=packet.model,
            requested_reasoning_effort=packet.reasoning_effort,
            effective_model=effective_model,
            effective_reasoning_effort=effective_reasoning_effort,
        )
    return DirectLunaRuntimeEvidence(
        requested_model=packet.model,
        requested_reasoning_effort=packet.reasoning_effort,
        effective_model=effective_model,
        effective_reasoning_effort=effective_reasoning_effort,
    )
