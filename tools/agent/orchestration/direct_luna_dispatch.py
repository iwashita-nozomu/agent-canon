# @dependency-start
# contract tool
# responsibility Builds and verifies bounded direct-Luna subagent handoff packets.
# upstream design ../../../agents/skills/direct-luna-communication.md direct Luna routing contract
# downstream implementation ../../../tests/tools/test_direct_luna_dispatch.py validates packet behavior
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
ReuseDisposition = Literal[
    "reuse",
    "extend",
    "restore",
    "consolidate",
    "replace",
    "delete",
    "reject",
]
AssetOrigin = Literal["current", "history"]
ReuseScope = Literal["not_applicable", "current", "current_and_history"]
ReuseUniverseStatus = Literal["not_applicable", "complete", "bounded_omission"]
ReuseSurfaceAdmission = Literal[
    "not_applicable",
    "existing_asset",
    "new_surface",
]

_ALLOWED_AUTHORITY = frozenset({"read-only", "workspace-write"})
_ALLOWED_EFFORT = frozenset({"low", "medium", "high", "xhigh"})
_ALLOWED_DISPOSITIONS = frozenset(
    {"reuse", "extend", "restore", "consolidate", "replace", "delete", "reject"}
)
_ALLOWED_ORIGINS = frozenset({"current", "history"})
_ALLOWED_REUSE_SCOPES = frozenset(
    {"not_applicable", "current", "current_and_history"}
)
_ALLOWED_UNIVERSE_STATUS = frozenset(
    {"not_applicable", "complete", "bounded_omission"}
)
_ALLOWED_SURFACE_ADMISSION = frozenset(
    {"not_applicable", "existing_asset", "new_surface"}
)
_WRITE_DISPOSITIONS = frozenset(
    {"extend", "restore", "consolidate", "replace", "delete"}
)


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
class ReuseDecision:
    """One evidence-backed disposition for a discovered current or historical asset."""

    asset_path: str
    asset_origin: AssetOrigin
    capability: str
    disposition: ReuseDisposition
    reason: str
    test_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "asset_path": self.asset_path,
            "asset_origin": self.asset_origin,
            "capability": self.capability,
            "disposition": self.disposition,
            "reason": self.reason,
            "test_paths": list(self.test_paths),
        }


@dataclass(frozen=True, slots=True)
class ReuseSurvey:
    """The single pre-edit asset universe consumed by write and review packets."""

    scope: ReuseScope
    universe_status: ReuseUniverseStatus
    surface_admission: ReuseSurfaceAdmission
    decisions: tuple[ReuseDecision, ...]
    current_refs: tuple[str, ...]
    history_refs: tuple[str, ...]
    prior_work_refs: tuple[str, ...]
    design_refs: tuple[str, ...]
    bounded_omissions: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "universe_status": self.universe_status,
            "surface_admission": self.surface_admission,
            "decisions": [decision.as_dict() for decision in self.decisions],
            "current_refs": list(self.current_refs),
            "history_refs": list(self.history_refs),
            "prior_work_refs": list(self.prior_work_refs),
            "design_refs": list(self.design_refs),
            "bounded_omissions": list(self.bounded_omissions),
            "reason": self.reason,
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
    reuse_survey: ReuseSurvey | None = None
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
            "reuse_survey": (
                self.reuse_survey.as_dict() if self.reuse_survey is not None else None
            ),
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


def _paths_overlap(left: str, right: str) -> bool:
    return (
        left == right
        or left.startswith(f"{right}/")
        or right.startswith(f"{left}/")
    )


def _path_is_covered(path: str, roots: Sequence[str]) -> bool:
    return any(path == root or path.startswith(f"{root}/") for root in roots)


def _has_bounded_omission(category: str, omissions: Sequence[str]) -> bool:
    prefix = f"{category}:"
    return any(
        omission.startswith(prefix) and omission[len(prefix) :].strip()
        for omission in omissions
    )


def build_reuse_decision(
    *,
    asset_path: str,
    asset_origin: AssetOrigin,
    capability: str,
    disposition: ReuseDisposition,
    reason: str,
    test_paths: Sequence[str],
) -> ReuseDecision:
    """Build one complete candidate disposition."""
    if asset_origin not in _ALLOWED_ORIGINS:
        raise ValueError(f"unsupported asset_origin: {asset_origin!r}")
    if disposition not in _ALLOWED_DISPOSITIONS:
        raise ValueError(f"unsupported disposition: {disposition!r}")
    bounded_asset_path = _bounded_paths("asset_path", (asset_path,))[0]
    bounded_test_paths = _bounded_paths("test_paths", test_paths)
    if not bounded_test_paths:
        raise ValueError("test_paths must contain at least one entry")
    return ReuseDecision(
        asset_path=bounded_asset_path,
        asset_origin=asset_origin,
        capability=_required_text("capability", capability),
        disposition=disposition,
        reason=_required_text("reason", reason),
        test_paths=bounded_test_paths,
    )


def build_reuse_survey(
    *,
    scope: ReuseScope,
    universe_status: ReuseUniverseStatus,
    surface_admission: ReuseSurfaceAdmission,
    decisions: Sequence[ReuseDecision] = (),
    current_refs: Sequence[str] = (),
    history_refs: Sequence[str] = (),
    prior_work_refs: Sequence[str] = (),
    design_refs: Sequence[str] = (),
    bounded_omissions: Sequence[str] = (),
    reason: str,
) -> ReuseSurvey:
    """Build one total asset-disposition survey before any file or worker slice."""
    if scope not in _ALLOWED_REUSE_SCOPES:
        raise ValueError(f"unsupported reuse scope: {scope!r}")
    if universe_status not in _ALLOWED_UNIVERSE_STATUS:
        raise ValueError(f"unsupported universe_status: {universe_status!r}")
    if surface_admission not in _ALLOWED_SURFACE_ADMISSION:
        raise ValueError(f"unsupported surface_admission: {surface_admission!r}")

    normalized_reason = _required_text("reuse_survey reason", reason)
    normalized_current_refs = _unique_ids("current_refs", current_refs, required=False)
    normalized_history_refs = _unique_ids("history_refs", history_refs, required=False)
    normalized_prior_work_refs = _unique_ids(
        "prior_work_refs", prior_work_refs, required=False
    )
    normalized_design_refs = _unique_ids("design_refs", design_refs, required=False)
    normalized_omissions = _unique_ids(
        "bounded_omissions", bounded_omissions, required=False
    )
    normalized_decisions = tuple(
        build_reuse_decision(
            asset_path=decision.asset_path,
            asset_origin=decision.asset_origin,
            capability=decision.capability,
            disposition=decision.disposition,
            reason=decision.reason,
            test_paths=decision.test_paths,
        )
        for decision in decisions
    )

    asset_paths = tuple(decision.asset_path for decision in normalized_decisions)
    if len(set(asset_paths)) != len(asset_paths):
        raise ValueError("reuse_survey decisions must not duplicate asset_path")

    if scope == "not_applicable":
        if universe_status != "not_applicable" or surface_admission != "not_applicable":
            raise ValueError(
                "not_applicable reuse scope requires not_applicable status and surface"
            )
        if any(
            (
                normalized_decisions,
                normalized_current_refs,
                normalized_history_refs,
                normalized_prior_work_refs,
                normalized_design_refs,
                normalized_omissions,
            )
        ):
            raise ValueError("not_applicable reuse survey must not carry asset evidence")
    else:
        if universe_status == "not_applicable" or surface_admission == "not_applicable":
            raise ValueError(
                "applicable reuse scope requires an applicable status and surface"
            )
        if not normalized_decisions:
            raise ValueError(
                "applicable reuse_survey decisions must contain at least one candidate"
            )
        if universe_status == "complete" and normalized_omissions:
            raise ValueError("complete asset universe must not contain bounded omissions")
        if universe_status == "bounded_omission" and not normalized_omissions:
            raise ValueError(
                "bounded_omission asset universe requires bounded_omissions"
            )

        required_dimensions: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("current", normalized_current_refs),
        )
        if scope == "current_and_history":
            required_dimensions += (
                ("history", normalized_history_refs),
                ("prior_work", normalized_prior_work_refs),
                ("design", normalized_design_refs),
            )
        for category, refs in required_dimensions:
            if not refs and not _has_bounded_omission(category, normalized_omissions):
                raise ValueError(
                    f"{scope} reuse survey requires {category}_refs or a "
                    f"{category} bounded omission"
                )

        if surface_admission == "new_surface" and any(
            decision.disposition != "reject" for decision in normalized_decisions
        ):
            raise ValueError(
                "new_surface admission requires every candidate disposition to be reject"
            )
        if surface_admission == "existing_asset" and not any(
            decision.disposition != "reject" for decision in normalized_decisions
        ):
            raise ValueError(
                "existing_asset admission requires at least one non-reject disposition"
            )

    return ReuseSurvey(
        scope=scope,
        universe_status=universe_status,
        surface_admission=surface_admission,
        decisions=normalized_decisions,
        current_refs=normalized_current_refs,
        history_refs=normalized_history_refs,
        prior_work_refs=normalized_prior_work_refs,
        design_refs=normalized_design_refs,
        bounded_omissions=normalized_omissions,
        reason=normalized_reason,
    )


def _normalize_reuse_survey(survey: ReuseSurvey) -> ReuseSurvey:
    return build_reuse_survey(
        scope=survey.scope,
        universe_status=survey.universe_status,
        surface_admission=survey.surface_admission,
        decisions=survey.decisions,
        current_refs=survey.current_refs,
        history_refs=survey.history_refs,
        prior_work_refs=survey.prior_work_refs,
        design_refs=survey.design_refs,
        bounded_omissions=survey.bounded_omissions,
        reason=survey.reason,
    )


def _validate_reuse_authority(
    survey: ReuseSurvey,
    *,
    authority: AuthorityMode,
    allowed_paths: Sequence[str],
    do_not_read: Sequence[str],
) -> None:
    for decision in survey.decisions:
        evidence_paths = (decision.asset_path, *decision.test_paths)
        for evidence_path in evidence_paths:
            if any(_paths_overlap(evidence_path, forbidden) for forbidden in do_not_read):
                raise ValueError(
                    f"reuse evidence path overlaps do_not_read: {evidence_path}"
                )
        if (
            authority == "workspace-write"
            and decision.disposition in _WRITE_DISPOSITIONS
            and not _path_is_covered(decision.asset_path, allowed_paths)
        ):
            raise ValueError(
                "reuse decision requiring a write must be covered by allowed_paths: "
                f"{decision.asset_path}"
            )


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
    reuse_survey: ReuseSurvey | None = None,
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

    normalized_reuse_survey = (
        _normalize_reuse_survey(reuse_survey) if reuse_survey is not None else None
    )
    if authority == "workspace-write" and normalized_reuse_survey is None:
        raise ValueError("workspace-write authority requires a structured reuse_survey")
    if normalized_reuse_survey is not None:
        _validate_reuse_authority(
            normalized_reuse_survey,
            authority=authority,
            allowed_paths=bounded_allowed_paths,
            do_not_read=bounded_do_not_read,
        )

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
        reuse_survey=normalized_reuse_survey,
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
