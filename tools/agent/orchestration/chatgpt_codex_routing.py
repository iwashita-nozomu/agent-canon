#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Decides ChatGPT conversation closure versus Codex workspace execution from explicit request facts.
# upstream design ../../agents/internal-routines/chatgpt-codex-routing.md owns route semantics and handoff policy.
# downstream implementation ../../tests/agent_tools/test_chatgpt_codex_routing.py validates the finite decision relation.
# @dependency-end
"""Deterministic ChatGPT/Codex request-modality routing."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

EXECUTION_REASON_FIELDS = (
    "explicit_codex_execution",
    "workspace_or_repository_mutation",
    "repository_local_or_uncommitted_state_required",
    "command_test_build_benchmark_runtime_observation_required",
    "iterative_inspect_edit_validate_loop_required",
    "durable_repository_delivery_required",
)
FACT_FIELDS = frozenset((*EXECUTION_REASON_FIELDS, "explicit_chat_only"))
INPUT_FIELDS = frozenset(
    {
        "requested_deliverable",
        "facts",
        "chatgpt_scope",
        "codex_scope",
        "validation_oracle",
    }
)


class RoutingInputError(ValueError):
    """Stable malformed-input error for callers and the CLI."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code}:{field}")

    def as_dict(self) -> dict[str, str]:
        """Return a stable machine-readable error payload."""
        return {"status": "fail", "code": self.code, "field": self.field}


@dataclass(frozen=True)
class RoutingFacts:
    """Explicit facts whose disjunction determines workspace execution need."""

    explicit_codex_execution: bool = False
    workspace_or_repository_mutation: bool = False
    repository_local_or_uncommitted_state_required: bool = False
    command_test_build_benchmark_runtime_observation_required: bool = False
    iterative_inspect_edit_validate_loop_required: bool = False
    durable_repository_delivery_required: bool = False
    explicit_chat_only: bool = False

    @property
    def execution_reason_codes(self) -> tuple[str, ...]:
        """Return true Codex reasons in canonical source order."""
        return tuple(
            field for field in EXECUTION_REASON_FIELDS if cast(bool, getattr(self, field))
        )


@dataclass(frozen=True)
class RoutePacket:
    """Canonical request-modality decision and handoff projection."""

    route: str
    reason_codes: tuple[str, ...]
    requested_deliverable: str
    chatgpt_scope: str
    codex_scope: str
    validation_oracle: str
    handoff: str
    blocked_dependency: str

    def as_dict(self) -> dict[str, object]:
        """Return JSON-compatible output with reason order preserved."""
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        return payload


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingInputError("invalid_text", field)
    return value.strip()


def facts_from_mapping(value: object) -> RoutingFacts:
    """Parse exact boolean facts and reject unknown classifier state."""
    if not isinstance(value, Mapping):
        raise RoutingInputError("invalid_mapping", "facts")
    raw = cast(Mapping[str, object], value)
    unknown = set(raw) - FACT_FIELDS
    if unknown:
        raise RoutingInputError("unknown_field", f"facts.{sorted(unknown)[0]}")
    parsed: dict[str, bool] = {}
    for field in FACT_FIELDS:
        item = raw.get(field, False)
        if type(item) is not bool:
            raise RoutingInputError("invalid_boolean", f"facts.{field}")
        parsed[field] = cast(bool, item)
    return RoutingFacts(**parsed)


def decide_route(
    *,
    facts: RoutingFacts,
    requested_deliverable: str,
    chatgpt_scope: str,
    codex_scope: str = "none",
    validation_oracle: str = "none",
) -> RoutePacket:
    """Apply the monotone execution predicate and project one route packet."""
    deliverable = _text(requested_deliverable, "requested_deliverable")
    conversation_scope = _text(chatgpt_scope, "chatgpt_scope")
    reasons = facts.execution_reason_codes

    if reasons:
        execution_scope = _text(codex_scope, "codex_scope")
        oracle = _text(validation_oracle, "validation_oracle")
        if execution_scope == "none":
            raise RoutingInputError("missing_execution_scope", "codex_scope")
        if oracle == "none":
            raise RoutingInputError("missing_validation_oracle", "validation_oracle")
        if facts.explicit_chat_only:
            return RoutePacket(
                route="chatgpt",
                reason_codes=("explicit_chat_only_conflict", *reasons),
                requested_deliverable=deliverable,
                chatgpt_scope=conversation_scope,
                codex_scope=execution_scope,
                validation_oracle=oracle,
                handoff="none",
                blocked_dependency=(
                    "workspace execution is required by the requested deliverable "
                    "but explicitly prohibited"
                ),
            )
        return RoutePacket(
            route="codex",
            reason_codes=reasons,
            requested_deliverable=deliverable,
            chatgpt_scope=conversation_scope,
            codex_scope=execution_scope,
            validation_oracle=oracle,
            handoff="agent-orchestration",
            blocked_dependency="none",
        )

    reason = "explicit_chat_only" if facts.explicit_chat_only else "conversation_closure"
    return RoutePacket(
        route="chatgpt",
        reason_codes=(reason,),
        requested_deliverable=deliverable,
        chatgpt_scope=conversation_scope,
        codex_scope="none",
        validation_oracle="none",
        handoff="none",
        blocked_dependency="none",
    )


def packet_from_mapping(value: object) -> RoutePacket:
    """Parse one exact JSON request and return its canonical route packet."""
    if not isinstance(value, Mapping):
        raise RoutingInputError("invalid_mapping", "input")
    raw = cast(Mapping[str, object], value)
    unknown = set(raw) - INPUT_FIELDS
    if unknown:
        raise RoutingInputError("unknown_field", sorted(unknown)[0])
    return decide_route(
        facts=facts_from_mapping(raw.get("facts", {})),
        requested_deliverable=_text(
            raw.get("requested_deliverable"), "requested_deliverable"
        ),
        chatgpt_scope=_text(raw.get("chatgpt_scope"), "chatgpt_scope"),
        codex_scope=cast(str, raw.get("codex_scope", "none")),
        validation_oracle=cast(str, raw.get("validation_oracle", "none")),
    )


def _load_input(path: str) -> object:
    try:
        if path == "-":
            return json.load(sys.stdin)
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoutingInputError("invalid_json", path) from exc


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="JSON request packet path, or '-' for stdin.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Route one explicit fact packet and print deterministic JSON."""
    args = build_parser().parse_args(argv)
    try:
        packet = packet_from_mapping(_load_input(args.input))
    except RoutingInputError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"status": "pass", **packet.as_dict()}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
