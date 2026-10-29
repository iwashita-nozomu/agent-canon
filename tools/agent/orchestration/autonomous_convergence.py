#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Projects owner-local closeout correspondence from validated owner receipts.
# upstream implementation ./packets.py owns owner-receipt normalization and compatibility.
# downstream implementation ../../../tests/agent_tools/test_distributed_guarantee.py exercises the owner-receipt projection.
# @dependency-end
"""Project owner-local closeout correspondence without central approval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .packets import (
    normalize_owner_guarantee_packet,
    owner_receipt_is_compatible,
    owner_receipt_key,
)


@dataclass(frozen=True)
class CloseoutProjectionDecision:
    ready: bool
    reasons: tuple[str, ...]


def owner_receipt_closeout_state(
    owner_receipts: Sequence[Mapping[str, object]],
    *,
    candidate_digest: str | None = None,
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> CloseoutProjectionDecision:
    """Project owner-local correspondence without central approval/blockers.

    This helper is intentionally a consumer: it validates receipt presence and
    tuple compatibility, but does not invoke an owner command or turn a review,
    Issue, or approval state into a guarantee.
    """
    seen: set[tuple[str, str, str, str, str]] = set()
    owners: set[str] = set()
    declared_edges: set[str] = set()
    reasons: list[str] = []
    for index, raw in enumerate(owner_receipts):
        try:
            packet = normalize_owner_guarantee_packet(raw, f"owner_receipts[{index}]")
            key = owner_receipt_key(packet)
        except (RuntimeError, TypeError, ValueError) as exc:
            reasons.append(str(exc))
            continue
        if key in seen:
            continue
        seen.add(key)
        if (
            packet["correspondence_state"] != "verified"
            or packet["observation_outcome"] != "observed_pass"
        ):
            continue
        if not owner_receipt_is_compatible(packet, candidate_digest=candidate_digest):
            reasons.append(f"incompatible:{packet['primary_observation_ref']}")
            continue
        owners.add(str(packet["owner_ref"]))
        declared_edges.update(str(edge) for edge in packet["downstream_edges"])
    reasons.extend(
        f"missing_owner:{owner}" for owner in required_owner_refs if owner not in owners
    )
    reasons.extend(
        f"missing_dependency_edge:{edge}"
        for edge in dependency_edges
        if edge not in declared_edges
    )
    return CloseoutProjectionDecision(not reasons, tuple(reasons))
