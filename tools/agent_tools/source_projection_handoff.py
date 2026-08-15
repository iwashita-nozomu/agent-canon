#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes the sole source-publication packet and hands it to the parent-owned update lifecycle namespace.
# upstream design ../../documents/agent-canon/source-publication-parent-handoff.md owns the cross-namespace handoff contract.
# upstream implementation ./update_lifecycle_contract.py owns source packet schemas, validation, and immutable replay.
# upstream implementation ./parent_root_side_effects.py owns attestation, no-replace publication, and race-safe readback.
# downstream implementation ../update_agent_canon.sh consumes the canonical parent-owned packet.
# downstream implementation ../../tests/agent_tools/test_source_projection_handoff.py validates materialization, replay, and conflict refusal.
# @dependency-end
"""Materialize and publish one source-projection packet to a parent repository."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    from .parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
    )
    from .update_lifecycle_contract import (
        SOURCE_PROJECTION_PACKET_SCHEMA,
        materialize_source_projection_packet,
        validate_immutable_replay,
        validate_source_projection_packet,
    )
except ImportError:
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
    )
    from update_lifecycle_contract import (  # type: ignore[no-redef]
        SOURCE_PROJECTION_PACKET_SCHEMA,
        materialize_source_projection_packet,
        validate_immutable_replay,
        validate_source_projection_packet,
    )

_COMPONENT_FIELDS = frozenset(
    {
        "binding",
        "source_main_rebind_receipt",
        "candidate_cas_receipt",
        "pull_request_lifecycle",
        "publication_readback_receipt",
        "source_gate_verdicts",
        "ordered_predecessor_evidence",
        "acceptance_evidence_ref",
    }
)


class SourceProjectionHandoffError(ValueError):
    """Typed materialization or handoff failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


@dataclass(frozen=True)
class SourceProjectionHandoffResult:
    """One immutable parent handoff result."""

    packet: dict[str, object]
    output_path: Path
    replayed: bool


def _json_mapping(path: Path) -> dict[str, object]:
    """Read one JSON object from an explicit regular file."""
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise SourceProjectionHandoffError(
            "source_projection_handoff:input_not_regular_file", str(resolved)
        )
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise SourceProjectionHandoffError(
            "source_projection_handoff:input_not_object", str(resolved)
        )
    return dict(value)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SourceProjectionHandoffError(
            "source_projection_handoff:component_not_object", field
        )
    return cast(Mapping[str, object], value)


def _mapping_sequence(value: object, field: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise SourceProjectionHandoffError(
            "source_projection_handoff:component_not_object_list", field
        )
    return cast(Sequence[Mapping[str, object]], value)


def materialize_handoff_input(value: Mapping[str, object]) -> dict[str, object]:
    """Validate a packet or materialize it from its exact predecessor records."""
    if "schema" in value:
        if value.get("schema") != SOURCE_PROJECTION_PACKET_SCHEMA:
            raise SourceProjectionHandoffError(
                "source_projection_handoff:schema_mismatch",
                str(value.get("schema")),
            )
        return validate_source_projection_packet(value)

    if set(value) != _COMPONENT_FIELDS:
        missing = sorted(_COMPONENT_FIELDS - set(value))
        unexpected = sorted(set(value) - _COMPONENT_FIELDS)
        detail = f"missing={missing};unexpected={unexpected}"
        raise SourceProjectionHandoffError(
            "source_projection_handoff:component_fields_mismatch", detail
        )

    acceptance_evidence_ref = value["acceptance_evidence_ref"]
    if not isinstance(acceptance_evidence_ref, str):
        raise SourceProjectionHandoffError(
            "source_projection_handoff:acceptance_evidence_not_string"
        )

    return materialize_source_projection_packet(
        binding=_mapping(value["binding"], "binding"),
        source_main_rebind_receipt=_mapping(
            value["source_main_rebind_receipt"], "source_main_rebind_receipt"
        ),
        candidate_cas_receipt=_mapping(
            value["candidate_cas_receipt"], "candidate_cas_receipt"
        ),
        pull_request_lifecycle=_mapping(
            value["pull_request_lifecycle"], "pull_request_lifecycle"
        ),
        publication_readback_receipt=_mapping(
            value["publication_readback_receipt"],
            "publication_readback_receipt",
        ),
        source_gate_verdicts=_mapping_sequence(
            value["source_gate_verdicts"], "source_gate_verdicts"
        ),
        ordered_predecessor_evidence=_mapping_sequence(
            value["ordered_predecessor_evidence"],
            "ordered_predecessor_evidence",
        ),
        acceptance_evidence_ref=acceptance_evidence_ref,
    )


def publish_source_projection_handoff(
    *,
    parent_root: Path,
    input_path: Path,
    output_path: Path | None = None,
) -> SourceProjectionHandoffResult:
    """Publish one immutable packet into the attested parent owner namespace."""
    root = parent_root.expanduser().resolve(strict=True)
    packet = materialize_handoff_input(_json_mapping(input_path))
    candidate = output_path or Path(
        ".agent-canon/update-lifecycle/state/source-publication-ready.json"
    )
    if not candidate.is_absolute():
        candidate = root / candidate

    boundary = ParentRootSideEffectBoundary()
    attestation = boundary.attest(
        ParentRootAttestationRequest(
            cwd=root,
            explicit_root=root,
            purpose="source-projection-handoff",
        )
    )
    directory = boundary.ensure_parent_owned_directory(
        attestation,
        candidate.parent,
        "source-projection-handoff",
    )
    target = directory.physical_path / candidate.name
    rendered = (json.dumps(packet, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

    outcome, detail = boundary.publish_parent_owned_file_noreplace(
        attestation,
        target,
        rendered,
        "source-projection-handoff",
    )
    if outcome not in {"spooled", "duplicate", "failed"}:
        raise SourceProjectionHandoffError(
            "source_projection_handoff:unexpected_publish_outcome", outcome
        )
    if outcome == "failed" and detail != "spool_conflict":
        raise SourceProjectionHandoffError(
            "source_projection_handoff:publish_failed", detail
        )

    receipt = boundary.resolve_parent_owned_path(
        attestation,
        target,
        "source-projection-handoff-readback",
    )
    existing = validate_source_projection_packet(
        json.loads(boundary.read_parent_owned_file(receipt).decode("utf-8"))
    )
    validate_immutable_replay(existing, packet, field=str(target))
    return SourceProjectionHandoffResult(
        packet=existing,
        output_path=target,
        replayed=outcome != "spooled",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and hand off one AgentCanon source projection packet."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish = subparsers.add_parser(
        "publish",
        help="validate/materialize one packet and write it to a parent namespace",
    )
    publish.add_argument("--root", required=True, type=Path)
    publish.add_argument("--input", required=True, type=Path)
    publish.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = publish_source_projection_handoff(
            parent_root=args.root,
            input_path=args.input,
            output_path=args.output,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"SOURCE_PROJECTION_HANDOFF_ERROR={exc}", file=sys.stderr)
        return 2

    publication = cast(
        Mapping[str, object], result.packet["publication_readback_receipt"]
    )
    pr_identity = cast(Mapping[str, object], publication["pr_identity"])
    print(
        "AGENT_CANON_SOURCE_PROJECTION_HANDOFF="
        + ("replayed" if result.replayed else "published")
    )
    print(f"AGENT_CANON_SOURCE_PROJECTION_PACKET={result.output_path}")
    print(
        "AGENT_CANON_SOURCE_PUBLICATION_COMMIT="
        f"{pr_identity['merge_commit_sha']}"
    )
    print(
        "AGENT_CANON_SOURCE_PUBLICATION_TREE="
        f"{pr_identity['merge_tree_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
