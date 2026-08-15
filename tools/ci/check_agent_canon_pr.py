#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes the canonical G2 receipt after AgentCanon generated-completeness checks pass.
# upstream implementation ../agent_tools/update_lifecycle_contract.py owns gate identity and immutable replay.
# upstream implementation ../agent_tools/parent_root_side_effects.py owns atomic G2 publication.
# upstream implementation ./check_agent_canon_pr.sh owns the ordered generated-completeness check execution.
# downstream implementation ../../tests/agent_tools/test_github_publish.py consumes owner-produced G2 fixtures.
# downstream implementation ../../tests/tools/test_update_agent_canon.py consumes owner-produced G2 fixtures.
# @dependency-end
"""Own the G2 boundary emitted by the AgentCanon PR gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

AGENT_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "agent_tools"
if str(AGENT_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS_ROOT))

from artifact_identity import canonical_json_bytes  # noqa: E402
from parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationReceipt,
    ParentRootSideEffectBoundary,
    resolve_parent_writer_attestation,
)
from update_lifecycle_contract import (  # noqa: E402
    materialize_gate_verdict,
    validate_gate_chain,
    validate_gate_verdict,
    validate_immutable_replay,
)

GENERATED_COMPLETENESS_CHECK_IDS = (
    "standalone_static_gate_ci",
    "strict_dependency_review",
    "documentation_checks",
    "repository_quick_ci",
    "generated_artifact_guard",
)


def materialize_generated_completeness_receipt(
    *,
    g1_gate: Mapping[str, object],
    candidate_sha: str,
    tree_sha: str,
    check_results: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Materialize G2 only from the exact ordered passing owner checks."""
    g1 = validate_gate_chain(
        [g1_gate], expected_gate_ids=("G1",), require_pass=True
    )[0]
    binding = cast(Mapping[str, object], g1["binding"])
    if binding["candidate_sha"] != candidate_sha or binding["tree_sha"] != tree_sha:
        raise ValueError("generated_completeness:candidate_identity_mismatch")
    normalized: list[dict[str, str]] = []
    for result in check_results:
        if set(result) != {"check_id", "status"}:
            raise ValueError("generated_completeness:check_result_fields_invalid")
        check_id = result["check_id"]
        status = result["status"]
        if not isinstance(check_id, str) or not isinstance(status, str):
            raise ValueError("generated_completeness:check_result_invalid")
        normalized.append({"check_id": check_id, "status": status})
    if tuple(item["check_id"] for item in normalized) != GENERATED_COMPLETENESS_CHECK_IDS:
        raise ValueError("generated_completeness:check_order_invalid")
    if any(item["status"] != "pass" for item in normalized):
        raise ValueError("generated_completeness:check_not_passed")
    output = {
        "candidate_sha": candidate_sha,
        "tree_sha": tree_sha,
        "check_results": normalized,
    }
    return materialize_gate_verdict(
        binding=binding,
        gate_id="G2",
        ordered_input_evidence_refs=[
            cast(str, cast(Mapping[str, object], g1["binding"])["evidence_ref"])
        ],
        invariant="generated_completeness",
        output_digest="sha256:"
        + hashlib.sha256(canonical_json_bytes(output)).hexdigest(),
        owner=f"{Path(__file__).resolve()}#materialize_generated_completeness_receipt",
        verdict="pass",
    )


def _git_identity(source_root: Path) -> tuple[str, str]:
    values: list[str] = []
    for revision in ("HEAD", "HEAD^{tree}"):
        values.append(
            subprocess.run(
                ["git", "-C", str(source_root), "rev-parse", revision],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    return values[0], values[1]


def _persist(
    path: Path,
    receipt: Mapping[str, object],
    *,
    boundary: ParentRootSideEffectBoundary,
    attestation: ParentRootAttestationReceipt,
) -> dict[str, object]:
    capability = boundary.resolve_parent_owned_path(
        attestation, path, "agent-canon-g2-receipt"
    )
    if capability.target_dev is not None:
        existing = validate_gate_verdict(
            json.loads(boundary.read_parent_owned_file(capability).decode("utf-8"))
        )
        validate_immutable_replay(existing, receipt, field=str(path))
        return existing
    boundary.atomic_publish(
        capability,
        json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )
    return dict(receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g1-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    boundary = ParentRootSideEffectBoundary()
    attestation = resolve_parent_writer_attestation(purpose="agent-canon-g2")
    output_root = (args.output or source_root).resolve()
    try:
        output_root.relative_to(source_root)
    except ValueError as exc:
        raise SystemExit(
            "agent_canon_pr_gate:output must remain under source root"
        ) from exc
    payload_object: object = json.loads(args.g1_bundle.read_text(encoding="utf-8"))
    payload: Mapping[str, object]
    if isinstance(payload_object, dict):
        payload = cast(Mapping[str, object], payload_object)
    else:
        payload = {}
    values = payload.get("gate_verdicts")
    if not isinstance(values, list):
        raise SystemExit("agent_canon_pr_gate_bundle:gate_verdicts_missing")
    gate_values: list[Mapping[str, object]] = []
    for value in cast(list[object], values):
        if not isinstance(value, dict):
            raise SystemExit("agent_canon_pr_gate_bundle:gate_verdict_invalid")
        gate_values.append(cast(Mapping[str, object], value))
    g1 = validate_gate_chain(
        gate_values, expected_gate_ids=("G1",), require_pass=True
    )[0]
    g1_binding = cast(Mapping[str, object], g1["binding"])
    transaction_id = cast(str, g1_binding["transaction_id"])
    output = args.output or (
        source_root
        / ".agent-canon"
        / "update-lifecycle"
        / "evidence"
        / transaction_id.removeprefix("tx:")
        / "g2.generated-completeness.json"
    )
    candidate_sha, tree_sha = _git_identity(source_root)
    receipt = materialize_generated_completeness_receipt(
        g1_gate=g1,
        candidate_sha=candidate_sha,
        tree_sha=tree_sha,
        check_results=[
            {"check_id": check_id, "status": "pass"}
            for check_id in GENERATED_COMPLETENESS_CHECK_IDS
        ],
    )
    persisted = _persist(
        output,
        receipt,
        boundary=boundary,
        attestation=attestation,
    )
    persisted_binding = cast(Mapping[str, object], persisted["binding"])
    print("AGENT_CANON_G2_RECEIPT=materialized")
    print(f"AGENT_CANON_G2_OUTPUT={output}")
    print(f"AGENT_CANON_G2_EVIDENCE_REF={persisted_binding['evidence_ref']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
