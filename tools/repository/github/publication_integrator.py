#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves and executes canonical completion-authority publication with expected-old CAS.
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md owns active-W2 publication authority and route state.
# upstream design ../../documents/operations/BRANCH_SCOPE.md owns branch, push, merge, and main publication policy.
# upstream design ../../agents/workflows/main-integration-workflow.md owns main integration ordering.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md owns AgentCanon PR publication policy.
# upstream implementation ./review_dispatch.py resolves current candidate identity only.
# upstream implementation ./report_artifact_checks.py regenerates materializer-produced validation results.
# upstream implementation ./artifact_identity.py provides canonical serialization and artifact readback.
# upstream implementation ./packets.py owns owner-local receipt normalization and compatibility.
# upstream implementation ./update_lifecycle_contract.py owns G1/G3/G5 verdict identity and lifecycle guards.
# downstream implementation ./github_publish.py exposes verified remote and PR publication.
# downstream implementation ../../tests/agent_tools/test_publication_integrator.py validates CAS, dirty-checkout, and race behavior.
# @dependency-end
"""Publish the exact owner-receipted candidate through one expected-old-OID authority."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

try:
    from tools.repository.workspace.parent_root_side_effects import (
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )
except ImportError:
    from tools.repository.workspace.parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationRequest,
        ParentRootReject,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
    )

from tools.runtime.artifacts.artifact_identity import canonical_body_sha256, canonical_json_bytes
from tools.agent.orchestration.review_dispatch import resolve_current_review_state, resolve_review_eligibility
from tools.runtime.lifecycle.update_lifecycle_contract import (
    binding_identity,
    materialize_gate_verdict,
    validate_publication_readback_receipt,
    validate_record_binding,
)
from tools.agent.orchestration.packets import (
    normalize_owner_guarantee_packet,
    owner_receipt_is_compatible,
    owner_receipt_key,
)

TREE_DELTA_SCHEMA = "agent-canon.git-tree-delta-observation.v1"
TREE_DELTA_SERIALIZATION = "agent-canon.git-tree-delta.v1"
PUBLICATION_AUTHORITY_SCHEMA = "agent-canon.publication-authority.v3"
PUBLICATION_ELIGIBILITY_SCHEMA = "agent-canon.publication-eligibility-projection.v1"
CANONICAL_INTERFACE_PATH = (
    "reports/agents/convergence-w2-gates-completion-20260716/"
    "ordered_integration_interface.json"
)
ZERO_OID = "0" * 40
ALLOWED_MODES = frozenset({"100644", "100755", "120000"})


def _publication_temp_dir() -> str | None:
    """Return an attested parent-local staging directory for Git's index."""
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if not configured:
        raise ParentRootSideEffectError(
            ParentRootReject.HANDOFF_INVALID,
            "publication-staging: explicit parent root is required",
        )
    parent = Path(configured).resolve(strict=True)
    attestation = attest_parent_root(
        ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose="publication-integrator")
    )
    directory = ParentRootSideEffectBoundary().ensure_parent_owned_directory(
        attestation, parent / ".agent-canon" / "tmp" / "publication", "publication-staging"
    )
    return str(directory.physical_path)


class PublicationError(ValueError):
    """Typed publication authority or CAS failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable failure."""
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}:{detail}")


def owner_receipt_projection(
    owner_receipts: Sequence[Mapping[str, object]],
    *,
    candidate_digest: str | None = None,
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> dict[str, object]:
    """Consume owner-local receipts without rerunning their commands.

    The integrator checks only packet presence, tuple compatibility, and the
    already-declared dependency edges.  It never treats approval, a copied
    claim, or a local command invocation as owner evidence.
    """
    normalized: list[dict[str, object]] = []
    keys: set[tuple[str, str, str, str, str]] = set()
    missing: list[str] = []
    for index, raw in enumerate(owner_receipts):
        try:
            packet = normalize_owner_guarantee_packet(raw, f"owner_receipts[{index}]")
            key = owner_receipt_key(packet)
        except (RuntimeError, TypeError, ValueError) as exc:
            missing.append(f"owner_receipts[{index}]:{exc}")
            continue
        if key in keys:
            # Same property/owner/input is one receipt, not corroboration.
            continue
        keys.add(key)
        if packet["correspondence_state"] != "verified" or packet["observation_outcome"] != "observed_pass":
            # Advisory/unproven/refuted claims do not create integration blockers.
            continue
        if not owner_receipt_is_compatible(packet, candidate_digest=candidate_digest):
            missing.append(f"incompatible:{packet['primary_observation_ref']}")
            continue
        normalized.append(packet)

    owner_refs = {str(packet["owner_ref"]) for packet in normalized}
    for owner_ref in required_owner_refs:
        if owner_ref not in owner_refs:
            missing.append(f"missing_owner:{owner_ref}")
    declared_edges = {
        str(edge)
        for packet in normalized
        for edge in packet["downstream_edges"]
        if isinstance(packet["downstream_edges"], list)
    }
    missing.extend(
        f"missing_dependency_edge:{edge}"
        for edge in dependency_edges
        if edge not in declared_edges
    )
    return {
        "candidate_digest": candidate_digest,
        "owner_receipt_refs": [
            str(packet["primary_observation_ref"]) for packet in normalized
        ],
        "dependency_edges": list(dependency_edges),
        "missing_or_incompatible": missing,
        "publication_state": "ready" if not missing else "blocked",
    }


@dataclass(frozen=True)
class CommandResult:
    """One captured external command result."""

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[
    [Sequence[str], Mapping[str, str] | None, bytes | None], CommandResult
]
PrMergeAdapter = Callable[[Mapping[str, object]], Mapping[str, object]]


def subprocess_runner(
    command: Sequence[str],
    environment: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> CommandResult:
    """Run one Git/GitHub command."""
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        input=input_bytes,
        env=None if environment is None else dict(environment),
    )
    return CommandResult(
        args=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout.decode(errors="replace"),
        stderr=completed.stderr.decode(errors="replace"),
    )


def _run(
    runner: Runner,
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
    code: str,
) -> CommandResult:
    """Run one command and raise a typed publication failure."""
    result = runner(command, environment, input_bytes)
    if result.returncode != 0:
        raise PublicationError(code, result.stderr.strip())
    return result


def _git_text(
    workspace: Path,
    args: Sequence[str],
    *,
    runner: Runner = subprocess_runner,
    code: str = "publication_authority:git_read_failed",
) -> str:
    """Return stripped read-only Git output."""
    return _run(
        runner,
        ["git", "-C", str(workspace), *args],
        code=code,
    ).stdout.strip()


def _hex_oid(value: object, field: str) -> str:
    """Return one exact SHA-1 object ID."""
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PublicationError("publication_authority:oid_invalid", field)
    return value


def _flatten_tree(
    workspace: Path,
    tree: str,
    *,
    runner: Runner = subprocess_runner,
) -> dict[bytes, tuple[str, str]]:
    """Flatten one Git tree into raw path bytes, modes, and blob IDs."""
    result = _run(
        runner,
        ["git", "-C", str(workspace), "ls-tree", "-r", "-z", tree],
        code="ordered_integration:tree_read_failed",
    )
    raw = result.stdout.encode("utf-8", errors="surrogateescape")
    entries: dict[bytes, tuple[str, str]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode, object_kind, oid = metadata.decode("ascii").split()
        except (ValueError, UnicodeDecodeError) as exc:
            raise PublicationError("ordered_integration:tree_entry_invalid") from exc
        if object_kind != "blob" or mode not in ALLOWED_MODES:
            raise PublicationError("ordered_integration:tree_mode_invalid")
        if path in entries:
            raise PublicationError("ordered_integration:duplicate_path")
        try:
            path.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PublicationError("ordered_integration:path_not_utf8") from exc
        entries[path] = (mode, _hex_oid(oid, "tree_blob"))
    return entries


def serialize_git_tree_delta(
    workspace: Path,
    base_tree: str,
    target_tree: str,
    *,
    runner: Runner = subprocess_runner,
) -> tuple[bytes, list[dict[str, object]]]:
    """Serialize the exact W2 canonical Git tree delta."""
    base_tree = _hex_oid(base_tree, "base_tree")
    target_tree = _hex_oid(target_tree, "target_tree")
    base = _flatten_tree(workspace, base_tree, runner=runner)
    target = _flatten_tree(workspace, target_tree, runner=runner)
    entries: list[dict[str, object]] = []
    for path in sorted(set(base) | set(target)):
        old_mode, old_blob = base.get(path, ("000000", ZERO_OID))
        new_mode, new_blob = target.get(path, ("000000", ZERO_OID))
        if old_mode == new_mode and old_blob == new_blob:
            continue
        entries.append(
            {
                "path": path.decode("utf-8"),
                "path_bytes": path,
                "old_mode": old_mode,
                "new_mode": new_mode,
                "old_blob": old_blob,
                "new_blob": new_blob,
            }
        )
    stream = bytearray()
    stream.extend(b"agent-canon.git-tree-delta.v1\0")
    stream.extend(b"object-format=sha1\0")
    stream.extend(f"base-tree={base_tree}\0".encode())
    stream.extend(f"target-tree={target_tree}\0".encode())
    stream.extend(f"entry-count={len(entries):016x}\0".encode())
    for entry in entries:
        path_bytes = entry["path_bytes"]
        if not isinstance(path_bytes, bytes):
            raise PublicationError("ordered_integration:path_bytes_invalid")
        stream.extend(b"entry\0")
        stream.extend(f"path-length={len(path_bytes):016x}\0".encode())
        stream.extend(b"path=")
        stream.extend(path_bytes)
        stream.extend(b"\0")
        stream.extend(f"old-mode={entry['old_mode']}\0".encode())
        stream.extend(f"new-mode={entry['new_mode']}\0".encode())
        stream.extend(f"old-blob={entry['old_blob']}\0".encode())
        stream.extend(f"new-blob={entry['new_blob']}\0".encode())
    stream.extend(b"end\0")
    public_entries = [
        {key: value for key, value in entry.items() if key != "path_bytes"}
        for entry in entries
    ]
    return bytes(stream), public_entries


def observe_git_tree_delta(
    workspace: Path,
    base_tree: str,
    target_tree: str,
    *,
    runner: Runner = subprocess_runner,
) -> dict[str, object]:
    """Return the exact canonical tree-delta observation."""
    stream, entries = serialize_git_tree_delta(
        workspace,
        base_tree,
        target_tree,
        runner=runner,
    )
    return {
        "schema": TREE_DELTA_SCHEMA,
        "serialization": TREE_DELTA_SERIALIZATION,
        "object_format": "sha1",
        "base_tree": base_tree,
        "target_tree": target_tree,
        "byte_length": len(stream),
        "diff_sha256": hashlib.sha256(stream).hexdigest(),
        "changed_paths": [str(entry["path"]) for entry in entries],
        "entries": entries,
    }


def _target_tuple(candidate: Mapping[str, object]) -> dict[str, object]:
    """Return the frozen target tuple from canonical candidate acceptance identity."""
    acceptance = candidate.get("acceptance_identity")
    target = (
        acceptance.get("publication_target")
        if isinstance(acceptance, Mapping)
        else None
    )
    if not isinstance(target, Mapping):
        raise PublicationError("publication_authority:target_tuple_missing")
    expected_keys = {
        "repository_id",
        "route",
        "mode",
        "target_ref",
        "expected_target_oid",
        "expected_target_tree",
        "remote_name",
        "pr_owner_api",
    }
    if set(target) != expected_keys:
        raise PublicationError("publication_authority:target_tuple_mismatch")
    route = target.get("route")
    mode = target.get("mode")
    target_ref = target.get("target_ref")
    if route not in {"local_ref", "remote_ref", "pull_request"}:
        raise PublicationError("publication_authority:target_route_invalid")
    if mode not in {"direct_head", "merge", "cherry_pick"}:
        raise PublicationError("publication_authority:integration_mode_mismatch")
    if not isinstance(target_ref, str) or not target_ref.startswith("refs/heads/"):
        raise PublicationError("publication_authority:target_ref_not_full")
    _hex_oid(target.get("expected_target_oid"), "expected_target_oid")
    _hex_oid(target.get("expected_target_tree"), "expected_target_tree")
    if route == "remote_ref" and not isinstance(target.get("remote_name"), str):
        raise PublicationError("publication_authority:target_tuple_mismatch")
    if route == "pull_request" and not isinstance(target.get("pr_owner_api"), str):
        raise PublicationError("publication_authority:target_tuple_mismatch")
    return dict(target)


def _review_approval(workspace: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Return current candidate and exact explicit APPROVE event."""
    review_eligibility = resolve_review_eligibility(workspace)
    if review_eligibility.get("outcome") != "eligible":
        raise PublicationError("publication_eligibility:review_not_eligible")
    state = resolve_current_review_state(workspace)
    candidate = state.get("candidate")
    decision = state.get("decision")
    if not isinstance(candidate, Mapping):
        raise PublicationError("publication_authority:candidate_missing")
    if not isinstance(decision, Mapping):
        raise PublicationError("publication_eligibility:approve_missing")
    if decision.get("decision") != "APPROVE":
        raise PublicationError("publication_eligibility:decision_mismatch")
    if decision.get("candidate_id") != candidate.get("candidate_id"):
        raise PublicationError("publication_eligibility:review_stale")
    return dict(candidate), dict(decision)


def _review_candidate(workspace: Path) -> dict[str, object]:
    """Read the current candidate identity without consuming approval text."""
    review_eligibility = resolve_review_eligibility(workspace)
    if review_eligibility.get("outcome") != "eligible":
        raise PublicationError("publication_eligibility:review_not_eligible")
    state = resolve_current_review_state(workspace)
    candidate = state.get("candidate")
    if not isinstance(candidate, Mapping):
        raise PublicationError("publication_authority:candidate_missing")
    return dict(candidate)


def _validation_provenance(workspace: Path) -> dict[str, object]:
    """Regenerate materializer-only required validation provenance."""
    from tools.runtime.artifacts.report_artifact_checks import resolve_validation_result

    result = resolve_validation_result(workspace)
    if result.get("outcome") != "pass":
        raise PublicationError("publication_eligibility:validation_not_pass")
    return result


def _lifecycle_gate_inputs(
    binding: Mapping[str, object],
    ordered_input_evidence_refs: Sequence[str],
) -> tuple[str, ...]:
    """Return explicit ordered inputs, defaulting only to the bound evidence."""
    checked = validate_record_binding(binding)
    if ordered_input_evidence_refs:
        return tuple(ordered_input_evidence_refs)
    return (cast(str, checked["evidence_ref"]),)


def _publication_gate(
    *,
    binding: Mapping[str, object],
    gate_id: str,
    ordered_input_evidence_refs: Sequence[str],
    invariant: str,
    owner_symbol: str,
    output: Mapping[str, object],
    verdict: str,
) -> dict[str, object]:
    """Materialize one lifecycle verdict without rechecking earlier gates."""
    return materialize_gate_verdict(
        binding=binding,
        gate_id=gate_id,
        ordered_input_evidence_refs=_lifecycle_gate_inputs(
            binding, ordered_input_evidence_refs
        ),
        invariant=invariant,
        output_digest="sha256:"
        + hashlib.sha256(canonical_json_bytes(output)).hexdigest(),
        owner=f"{Path(__file__).resolve()}#{owner_symbol}",
        verdict=verdict,
        retry_reason=None,
        next_checkpoint=None,
    )


def resolve_publication_authority(
    workspace: Path,
    *,
    lifecycle_binding: Mapping[str, object] | None = None,
    ordered_input_evidence_refs: Sequence[str] = (),
    owner_receipts: Sequence[Mapping[str, object]] = (),
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> dict[str, object]:
    """Resolve publication inputs from owner receipts, never review approval."""
    root = workspace.resolve()
    candidate = _review_candidate(root)
    if not owner_receipts:
        raise PublicationError("publication_eligibility:owner_receipts_missing")
    candidate_digest = str(
        candidate.get("candidate_digest")
        or candidate.get("candidate_id")
        or candidate.get("candidate_commit")
        or ""
    ).strip()
    receipt_projection = owner_receipt_projection(
        owner_receipts,
        candidate_digest=candidate_digest or None,
        required_owner_refs=required_owner_refs,
        dependency_edges=dependency_edges,
    )
    if receipt_projection["publication_state"] != "ready":
        raise PublicationError(
            "publication_eligibility:owner_receipts_incompatible",
            ",".join(str(item) for item in receipt_projection["missing_or_incompatible"]),
        )
    validation = _validation_provenance(root)
    candidate_commit = _hex_oid(candidate.get("candidate_commit"), "candidate_commit")
    candidate_tree = _hex_oid(candidate.get("candidate_tree"), "candidate_tree")
    parents = _git_text(
        root, ["rev-list", "--parents", "-n", "1", candidate_commit]
    ).split()
    if len(parents) not in {2, 3}:
        raise PublicationError("publication_authority:candidate_parent_invalid")
    target = _target_tuple(candidate)
    expected_target = _hex_oid(target["expected_target_oid"], "expected_target_oid")
    parent_commits = tuple(_hex_oid(parent, "source_commit") for parent in parents[1:])
    if len(parent_commits) == 1:
        source_commit = parent_commits[0]
    else:
        source_candidates = tuple(
            parent for parent in parent_commits if parent != expected_target
        )
        if expected_target not in parent_commits or len(source_candidates) != 1:
            raise PublicationError("publication_authority:candidate_parent_invalid")
        source_commit = source_candidates[0]
    if target["route"] == "local_ref" and target["mode"] == "direct_head":
        if expected_target != source_commit:
            raise PublicationError("publication_authority:target_not_source_successor")
    elif target["route"] == "pull_request":
        if (
            _run(
                subprocess_runner,
                [
                    "git",
                    "-C",
                    str(root),
                    "merge-base",
                    "--is-ancestor",
                    expected_target,
                    source_commit,
                ],
                code="publication_authority:target_not_source_successor",
            ).returncode
            != 0
        ):
            raise PublicationError("publication_authority:target_not_source_successor")
    source_tree = _hex_oid(
        _git_text(root, ["rev-parse", f"{source_commit}^{{tree}}"]),
        "source_tree",
    )
    delta = observe_git_tree_delta(root, source_tree, candidate_tree)
    attestation_core = {
        "repository_id": root.name,
        "owner_identity": "completion_authority",
        "owner_surface": "agents/canonical/CODEX_WORKFLOW.md",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
        "candidate_parent": source_commit,
        "interface_delta": delta,
        "candidate_ref": f"refs/agent-canon/candidates/{candidate_commit}",
        "immutable_object_identity": candidate_commit,
        "intended_integration_target": target,
    }
    attestation_hash = hashlib.sha256(
        canonical_json_bytes(attestation_core)
    ).hexdigest()
    attestation = {
        "schema": "agent-canon.interface-candidate-attestation.v1",
        "schema_version": 1,
        "attestation_id": f"interface-candidate:{attestation_hash}",
        **attestation_core,
        "attestation_body_sha256": attestation_hash,
    }
    candidate_authority = {
        "attestation_id": attestation["attestation_id"],
        "attestation_body_sha256": attestation["attestation_body_sha256"],
        "candidate_ref": attestation["candidate_ref"],
        "candidate_commit": candidate_commit,
        "candidate_tree": candidate_tree,
    }
    selection_payload = {
        "candidate_authority": candidate_authority,
        "owner_receipt_projection": receipt_projection,
        "source": {"commit": source_commit, "tree": source_tree},
        "target": target,
        "validation_provenance_ref": {
            "validation_result_id": validation["validation_result_id"],
            "validation_result_body_sha256": validation[
                "validation_result_body_sha256"
            ],
        },
    }
    selection_sha256 = hashlib.sha256(
        canonical_json_bytes(selection_payload)
    ).hexdigest()
    authority: dict[str, object] = {
        "schema": PUBLICATION_AUTHORITY_SCHEMA,
        "schema_version": 3,
        "publication_id": f"w2-publication:{selection_sha256}:1",
        "state": "selected",
        "selection_version": 1,
        "selection_owner": "completion_authority",
        **selection_payload,
        "selection_sha256": selection_sha256,
        "owner_attestation": {
            "scheme": "agent-canon-ledger-publication-authority-v3",
            "owner": "completion_authority",
            "authority_event_id": None,
            "authority_revision": candidate.get("candidate_revision"),
            "candidate_attestation_sha256": attestation["attestation_body_sha256"],
            "owner_receipt_refs": receipt_projection["owner_receipt_refs"],
            "selection_sha256": selection_sha256,
            "status": "frozen",
        },
        "candidate_attestation": attestation,
        "result": None,
        "pr_identity_cas_gate": None,
        "publication_authority_body_sha256": "",
    }
    if lifecycle_binding is not None:
        authority["pr_identity_cas_gate"] = _publication_gate(
            binding=lifecycle_binding,
            gate_id="G3",
            ordered_input_evidence_refs=ordered_input_evidence_refs,
            invariant="pr_identity_cas",
            owner_symbol="resolve_publication_authority",
            output=selection_payload,
            verdict="pass",
        )
    authority["publication_authority_body_sha256"] = canonical_body_sha256(
        authority,
        "publication_authority_body_sha256",
    )
    return authority


def resolve_publication_eligibility(
    workspace: Path,
    *,
    lifecycle_binding: Mapping[str, object] | None = None,
    ordered_input_evidence_refs: Sequence[str] = (),
    owner_receipts: Sequence[Mapping[str, object]] = (),
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> dict[str, object]:
    """Return one pure publication-eligibility projection."""
    review_eligibility: dict[str, object] | None = None
    try:
        review_eligibility = resolve_review_eligibility(workspace)
        if review_eligibility.get("outcome") != "eligible":
            raise PublicationError("publication_eligibility:review_not_eligible")
        authority = resolve_publication_authority(
            workspace,
            lifecycle_binding=lifecycle_binding,
            ordered_input_evidence_refs=ordered_input_evidence_refs,
            owner_receipts=owner_receipts,
            required_owner_refs=required_owner_refs,
            dependency_edges=dependency_edges,
        )
    except (PublicationError, ValueError) as exc:
        failure_code = (
            exc.code
            if isinstance(exc, PublicationError)
            else f"publication_eligibility:{type(exc).__name__}"
        )
        failure_codes = [failure_code]
        outcome = "ineligible"
        authority = None
    else:
        failure_codes = []
        outcome = "eligible"
    seed = {
        "review_eligibility_id": None
        if review_eligibility is None
        else review_eligibility.get("review_eligibility_id"),
        "review_eligibility_body_sha256": None
        if review_eligibility is None
        else review_eligibility.get("review_eligibility_body_sha256"),
        "outcome": outcome,
        "failure_codes": failure_codes,
    }
    projection_id = (
        "publication-eligibility:"
        + hashlib.sha256(canonical_json_bytes(seed)).hexdigest()
    )
    projection: dict[str, object] = {
        "schema": PUBLICATION_ELIGIBILITY_SCHEMA,
        "schema_version": 1,
        "publication_eligibility_id": projection_id,
        "review_eligibility_ref": None
        if review_eligibility is None
        else {
            "review_eligibility_id": review_eligibility.get("review_eligibility_id"),
            "review_eligibility_body_sha256": review_eligibility.get(
                "review_eligibility_body_sha256"
            ),
        },
        "approval": None,
        "owner_receipts": owner_receipts,
        "publication_authority": authority,
        "outcome": outcome,
        "failure_codes": failure_codes,
        "source_correctness_gate": None,
        "publication_eligibility_body_sha256": "",
    }
    if lifecycle_binding is not None:
        projection["source_correctness_gate"] = _publication_gate(
            binding=lifecycle_binding,
            gate_id="G1",
            ordered_input_evidence_refs=ordered_input_evidence_refs,
            invariant="source_correctness",
            owner_symbol="resolve_publication_eligibility",
            output=seed,
            verdict="pass" if outcome == "eligible" else "fail",
        )
    projection["publication_eligibility_body_sha256"] = canonical_body_sha256(
        projection,
        "publication_eligibility_body_sha256",
    )
    return projection


def _worktree_status(
    workspace: Path,
    *,
    runner: Runner,
) -> str:
    """Return exact dirty-checkout evidence without modifying it."""
    return _git_text(
        workspace,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        runner=runner,
    )


def _checked_out_refs(
    workspace: Path,
    *,
    runner: Runner,
) -> set[str]:
    """Return all full refs checked out in linked worktrees."""
    text = _git_text(
        workspace,
        ["worktree", "list", "--porcelain"],
        runner=runner,
    )
    return {
        line.removeprefix("branch ")
        for line in text.splitlines()
        if line.startswith("branch refs/heads/")
    }


def _interface_entry(delta: Mapping[str, object]) -> Mapping[str, object]:
    """Return the sole canonical interface entry."""
    entries = delta.get("entries")
    if (
        not isinstance(entries, list)
        or len(entries) != 1
        or not isinstance(entries[0], Mapping)
        or entries[0].get("path") != CANONICAL_INTERFACE_PATH
    ):
        raise PublicationError("ordered_integration:path_set_mismatch")
    return entries[0]


def _construct_result_commit(
    workspace: Path,
    authority: Mapping[str, object],
    *,
    runner: Runner,
) -> str:
    """Construct the exact direct, merge, or cherry-pick result without moving a ref."""
    target = authority["target"]
    source = authority["source"]
    candidate = authority["candidate_authority"]
    attestation = authority["candidate_attestation"]
    if not all(
        isinstance(item, Mapping) for item in (target, source, candidate, attestation)
    ):
        raise PublicationError("publication_authority:schema_mismatch")
    target_map = cast(Mapping[str, object], target)
    source_map = cast(Mapping[str, object], source)
    candidate_map = cast(Mapping[str, object], candidate)
    attestation_map = cast(Mapping[str, object], attestation)
    mode = target_map["mode"]
    expected = _hex_oid(target_map["expected_target_oid"], "expected_target_oid")
    candidate_commit = _hex_oid(candidate_map["candidate_commit"], "candidate_commit")
    source_commit = _hex_oid(source_map["commit"], "source_commit")
    if target_map["route"] == "pull_request":
        return candidate_commit
    if mode == "direct_head":
        if expected != source_commit:
            raise PublicationError("publication_authority:target_not_source_successor")
        return candidate_commit
    delta = attestation_map.get("interface_delta")
    if not isinstance(delta, Mapping):
        raise PublicationError("publication_authority:delta_missing")
    entry = _interface_entry(delta)
    new_blob = _hex_oid(entry.get("new_blob"), "new_blob")
    new_mode = str(entry.get("new_mode"))
    if new_mode not in {"100644", "100755"}:
        raise PublicationError("ordered_integration:blob_mode_mismatch")
    if (
        _run(
            runner,
            [
                "git",
                "-C",
                str(workspace),
                "merge-base",
                "--is-ancestor",
                source_commit,
                expected,
            ],
            code="publication_authority:target_not_source_successor",
        ).returncode
        != 0
    ):
        raise PublicationError("publication_authority:target_not_source_successor")
    with tempfile.TemporaryDirectory(dir=_publication_temp_dir()) as temp_dir:
        index_path = Path(temp_dir) / "index"
        environment = {**os.environ, "GIT_INDEX_FILE": str(index_path)}
        _run(
            runner,
            ["git", "-C", str(workspace), "read-tree", expected],
            environment=environment,
            code="publication_integrator:result_tree_failed",
        )
        _run(
            runner,
            [
                "git",
                "-C",
                str(workspace),
                "update-index",
                "--add",
                "--cacheinfo",
                f"{new_mode},{new_blob},{CANONICAL_INTERFACE_PATH}",
            ],
            environment=environment,
            code="publication_integrator:result_tree_failed",
        )
        result_tree = _run(
            runner,
            ["git", "-C", str(workspace), "write-tree"],
            environment=environment,
            code="publication_integrator:result_tree_failed",
        ).stdout.strip()
    message = (
        f"Integrate owner-receipted W2 interface candidate {candidate_commit}\n"
    ).encode()
    commit_command = [
        "git",
        "-C",
        str(workspace),
        "commit-tree",
        result_tree,
        "-p",
        expected,
    ]
    if mode == "merge":
        commit_command.extend(["-p", candidate_commit])
    result_commit = _run(
        runner,
        commit_command,
        input_bytes=message,
        code="publication_integrator:result_commit_failed",
    ).stdout.strip()
    return _hex_oid(result_commit, "result_commit")


def integrate_publication(
    workspace: Path,
    *,
    runner: Runner = subprocess_runner,
    pr_merge_adapter: PrMergeAdapter | None = None,
    lifecycle_binding: Mapping[str, object] | None = None,
    ordered_input_evidence_refs: Sequence[str] = (),
    owner_receipts: Sequence[Mapping[str, object]] = (),
    required_owner_refs: Sequence[str] = (),
    dependency_edges: Sequence[str] = (),
) -> dict[str, object]:
    """Execute one publication CAS operation after consuming owner receipts."""
    root = workspace.resolve()
    authority = resolve_publication_authority(
        root,
        lifecycle_binding=lifecycle_binding,
        ordered_input_evidence_refs=ordered_input_evidence_refs,
        owner_receipts=owner_receipts,
        required_owner_refs=required_owner_refs,
        dependency_edges=dependency_edges,
    )
    target = authority.get("target")
    if not isinstance(target, Mapping):
        raise PublicationError("publication_authority:target_tuple_mismatch")
    target_ref = str(target["target_ref"])
    route = str(target["route"])
    expected = _hex_oid(target["expected_target_oid"], "expected_target_oid")
    observed_expected = _git_text(
        root,
        ["rev-parse", target_ref],
        runner=runner,
        code="publication_integrator:target_missing",
    )
    if observed_expected != expected:
        raise PublicationError("integration_target_moved")
    if (
        _git_text(
            root,
            ["rev-parse", f"{expected}^{{tree}}"],
            runner=runner,
        )
        != target["expected_target_tree"]
    ):
        raise PublicationError("publication_authority:target_tree_mismatch")
    status_before = _worktree_status(root, runner=runner)
    result_commit: str | None = None
    if route != "pull_request":
        result_commit = _construct_result_commit(root, authority, runner=runner)
    candidate_authority = cast(
        Mapping[str, object], authority["candidate_authority"]
    )
    candidate_commit = _hex_oid(
        candidate_authority["candidate_commit"], "candidate_commit"
    )
    candidate_tree = _hex_oid(
        candidate_authority["candidate_tree"], "candidate_tree"
    )
    publication_pr_number: int | None = None
    authority_second = resolve_publication_authority(
        root,
        lifecycle_binding=lifecycle_binding,
        ordered_input_evidence_refs=ordered_input_evidence_refs,
        owner_receipts=owner_receipts,
        required_owner_refs=required_owner_refs,
        dependency_edges=dependency_edges,
    )
    if authority_second != authority:
        raise PublicationError("publication_authority:readback_changed")
    if (
        _git_text(
            root,
            ["rev-parse", target_ref],
            runner=runner,
        )
        != expected
    ):
        raise PublicationError("integration_target_moved")
    if route == "local_ref":
        if result_commit is None:
            raise PublicationError("publication_integrator:result_commit_missing")
        if target_ref in _checked_out_refs(root, runner=runner):
            raise PublicationError("publication_integrator:checked_out_target")
        _run(
            runner,
            ["git", "-C", str(root), "update-ref", target_ref, result_commit, expected],
            code="integration_target_moved",
        )
        observed_result = _git_text(root, ["rev-parse", target_ref], runner=runner)
        observed_result_tree = _git_text(
            root, ["rev-parse", f"{observed_result}^{{tree}}"], runner=runner
        )
    elif route == "remote_ref":
        if result_commit is None:
            raise PublicationError("publication_integrator:result_commit_missing")
        remote = target.get("remote_name")
        if not isinstance(remote, str) or not remote:
            raise PublicationError("publication_authority:target_tuple_mismatch")
        _run(
            runner,
            [
                "git",
                "-C",
                str(root),
                "push",
                f"--force-with-lease={target_ref}:{expected}",
                remote,
                f"{result_commit}:{target_ref}",
            ],
            code="integration_target_moved",
        )
        observed_result = _git_text(
            root,
            ["ls-remote", remote, target_ref],
            runner=runner,
        ).split()[0]
        observed_result_tree = _git_text(
            root, ["rev-parse", f"{result_commit}^{{tree}}"], runner=runner
        )
    else:
        if pr_merge_adapter is None:
            raise PublicationError(
                "publication_integrator:pr_expected_oid_api_unavailable"
            )
        response = pr_merge_adapter(
            {
                "expected_base_oid": expected,
                "expected_base_tree": target["expected_target_tree"],
                "expected_head_oid": candidate_commit,
                "expected_head_tree": candidate_tree,
                "target": dict(target),
            }
        )
        if response.get("status") != "merged":
            raise PublicationError("integration_target_moved")
        try:
            readback_receipt = validate_publication_readback_receipt(
                response.get("publication_readback_receipt")
            )
        except (TypeError, ValueError) as exc:
            raise PublicationError(
                "publication_integrator:authoritative_pr_readback_invalid"
            ) from exc
        if lifecycle_binding is None or binding_identity(
            readback_receipt["binding"]
        ) != binding_identity(lifecycle_binding):
            raise PublicationError(
                "publication_integrator:authoritative_pr_readback_identity_mismatch"
            )
        readback_candidate = cast(
            Mapping[str, object], readback_receipt["candidate_identity"]
        )
        readback_pr = cast(Mapping[str, object], readback_receipt["pr_identity"])
        if (
            readback_candidate["candidate_sha"] != candidate_commit
            or readback_candidate["tree_sha"] != candidate_tree
            or readback_pr["head_sha"] != candidate_commit
            or readback_pr["merge_cas_base_sha"] != expected
            or readback_pr["merge_cas_base_tree_sha"]
            != target["expected_target_tree"]
        ):
            raise PublicationError("publication_integrator:pr_identity_mismatch")
        publication_pr_number = cast(int, readback_pr["number"])
        observed_result = _hex_oid(
            readback_pr["merge_commit_sha"], "merge_commit_sha"
        )
        observed_result_tree = _hex_oid(
            readback_pr["merge_tree_sha"], "merge_tree_sha"
        )
        post_cas_ref_oid = _hex_oid(
            response.get("post_cas_ref_oid"), "post_cas_ref_oid"
        )
        post_cas_tree_oid = _hex_oid(
            response.get("post_cas_tree_oid"), "post_cas_tree_oid"
        )
        if (
            post_cas_ref_oid != observed_result
            or post_cas_tree_oid != observed_result_tree
        ):
            raise PublicationError("publication_integrator:post_cas_readback_mismatch")
    if route != "pull_request" and observed_result != result_commit:
        raise PublicationError("publication_integrator:post_cas_readback_mismatch")
    status_after = _worktree_status(root, runner=runner)
    if status_after != status_before:
        raise PublicationError("publication_integrator:checkout_state_changed")
    receipt_core = {
        "publication_id": authority["publication_id"],
        "selection_sha256": authority["selection_sha256"],
        "route": route,
        "target_ref": target_ref,
        "expected_old_oid": expected,
        "candidate_oid": candidate_commit,
        "candidate_tree_oid": candidate_tree,
        "result_oid": observed_result,
        "result_tree_oid": observed_result_tree,
        "post_cas_ref_oid": observed_result,
        "post_cas_tree_oid": observed_result_tree,
        "pr_number": publication_pr_number,
        "checkout_status_before_sha256": hashlib.sha256(
            status_before.encode()
        ).hexdigest(),
        "checkout_status_after_sha256": hashlib.sha256(
            status_after.encode()
        ).hexdigest(),
    }
    receipt: dict[str, object] = {
        "schema": "agent-canon.integration-cas-receipt.v1",
        "schema_version": 1,
        "receipt_id": "integration-cas-receipt:"
        + hashlib.sha256(canonical_json_bytes(receipt_core)).hexdigest(),
        **receipt_core,
        "remote_publication_readback_gate": None,
        "receipt_body_sha256": "",
    }
    if lifecycle_binding is not None:
        receipt["remote_publication_readback_gate"] = _publication_gate(
            binding=lifecycle_binding,
            gate_id="G5",
            ordered_input_evidence_refs=ordered_input_evidence_refs,
            invariant="remote_publication_readback",
            owner_symbol="integrate_publication",
            output=receipt_core,
            verdict="pass",
        )
    receipt["receipt_body_sha256"] = canonical_body_sha256(
        receipt,
        "receipt_body_sha256",
    )
    return receipt
