"""Tests for owner-eligible publication and expected-old CAS behavior."""

# @dependency-start
# contract test
# responsibility Tests owner-eligible publication and expected-old CAS behavior.
# upstream implementation ../../tools/repository/github/publication_integrator.py resolves publication authority and CAS eligibility
# @dependency-end

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest.mock import patch

from tools.repository.github.publication_integrator import (
    CANONICAL_INTERFACE_PATH,
    CommandResult,
    PublicationAuthority,
    PublicationError,
    integrate_publication,
    resolve_publication_eligibility,
)
from tools.runtime.lifecycle.update_lifecycle_contract import (
    materialize_gate_verdict,
)
from tools.runtime.values import is_string_object_mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def lifecycle_binding() -> dict[str, object]:
    """Return one exact identity reused across publication boundary receipts."""
    return {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": "3" * 40,
        "tree_sha": "4" * 40,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "publication-integrator",
        "tool_version": "test.v1",
        "evidence_ref": "evidence:" + "6" * 64,
        "evidence_digest": "sha256:" + "7" * 64,
        "timing": {
            "started_at": "2026-07-18T00:00:00Z",
            "finished_at": "2026-07-18T00:00:00Z",
            "last_attempt_at": "2026-07-18T00:00:00Z",
            "duration_ms": 0,
            "attempt": 1,
            "replayed": False,
        },
    }


def publication_readback_receipt(
    *,
    post_merge_base_ref_sha: str,
    merge_cas_base_sha: str,
    merge_cas_base_tree: str,
    candidate_sha: str,
    candidate_tree: str,
    merge_sha: str,
    merge_tree: str,
) -> dict[str, object]:
    """Return one canonical-shaped authoritative PR readback receipt."""
    publication_ref = "evidence:" + "9" * 64
    binding = lifecycle_binding()
    binding["evidence_ref"] = publication_ref
    binding["evidence_digest"] = "sha256:" + "9" * 64
    return {
        "schema": "agent-canon.publication-readback-receipt.v1",
        "readback_receipt_id": "publication-readback:" + "a" * 64,
        "binding": binding,
        "predecessor_evidence_id": "evidence:" + "b" * 64,
        "rebind_receipt_evidence_id": "rebind:" + "c" * 64,
        "candidate_identity": {
            "candidate_sha": candidate_sha,
            "tree_sha": candidate_tree,
        },
        "pr_identity": {
            "number": 7,
            "remote_name": "origin",
            "base_ref": "refs/heads/main",
            "head_ref": "refs/heads/topic",
            "head_repo_owner": "owner",
            "head_repo_name": "repo",
            "post_merge_base_ref_sha": post_merge_base_ref_sha,
            "merge_cas_base_sha": merge_cas_base_sha,
            "merge_cas_base_tree_sha": merge_cas_base_tree,
            "head_sha": candidate_sha,
            "merge_commit_sha": merge_sha,
            "merge_tree_sha": merge_tree,
        },
        "publication_evidence_ref": publication_ref,
        "authoritative_readback_digest": "sha256:" + "9" * 64,
        "readback_stage": "publication_readback",
    }


class PublicationIntegratorTest(unittest.TestCase):
    """Verify owner-eligible publication remains bound to the selected candidate."""

    def test_ordered_integration_uses_durable_interface_path(self) -> None:
        """The public CAS route accepts only the durable interface path."""
        self.assertEqual(
            CANONICAL_INTERFACE_PATH,
            "documents/contracts/ordered_integration_interface.json",
        )
        base_oid = "1" * 40
        base_tree = "2" * 40
        source_commit = "3" * 40
        source_tree = "4" * 40
        candidate_commit = "5" * 40
        candidate_tree = "6" * 40
        result_tree = "7" * 40
        result_commit = "8" * 40
        target_ref = "refs/heads/main"

        with tempfile.TemporaryDirectory() as parent_root_text:
            parent_root = Path(parent_root_text)
            subprocess.run(
                ("git", "init", "-q", "--initial-branch=main", str(parent_root)),
                check=True,
            )
            subprocess.run(
                ("git", "-C", str(parent_root), "config", "user.name", "Test"),
                check=True,
            )
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(parent_root),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ),
                check=True,
            )
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(parent_root),
                    "remote",
                    "add",
                    "origin",
                    "https://example.invalid/agent-canon-test.git",
                ),
                check=True,
            )
            subprocess.run(
                (
                    "git",
                    "-C",
                    str(parent_root),
                    "commit",
                    "--allow-empty",
                    "-q",
                    "-m",
                    "fixture",
                ),
                check=True,
            )

            current_ref = base_oid
            executed: list[tuple[str, ...]] = []

            def runner(
                command: Sequence[str],
                _environment: Mapping[str, str] | None = None,
                _input_bytes: bytes | None = None,
            ) -> CommandResult:
                nonlocal current_ref
                args = tuple(command)
                executed.append(args)
                operation = args[3]
                if operation == "rev-parse":
                    revision = args[-1]
                    if revision == target_ref:
                        stdout = current_ref
                    elif revision == f"{base_oid}^{{tree}}":
                        stdout = base_tree
                    elif revision == f"{result_commit}^{{tree}}":
                        stdout = result_tree
                    else:
                        raise AssertionError(args)
                elif operation == "merge-base":
                    stdout = ""
                elif operation == "write-tree":
                    stdout = result_tree
                elif operation == "commit-tree":
                    stdout = result_commit
                elif operation == "update-ref":
                    current_ref = result_commit
                    stdout = ""
                elif operation in {"read-tree", "update-index", "status", "worktree"}:
                    stdout = ""
                else:
                    raise AssertionError(args)
                return CommandResult(args, 0, stdout, "")

            def authority_for(interface_path: str) -> PublicationAuthority:
                return {
                    "schema": "agent-canon.publication-authority.v3",
                    "schema_version": 3,
                    "publication_id": "w2-publication:test",
                    "state": "selected",
                    "selection_version": 1,
                    "selection_owner": "completion_authority",
                    "candidate_authority": {
                        "attestation_id": "attestation:test",
                        "attestation_body_sha256": "a" * 64,
                        "candidate_ref": f"refs/agent-canon/candidates/{candidate_commit}",
                        "candidate_commit": candidate_commit,
                        "candidate_tree": candidate_tree,
                    },
                    "owner_receipt_projection": {
                        "candidate_digest": candidate_commit,
                        "owner_receipt_refs": [],
                        "dependency_edges": [],
                        "missing_or_incompatible": [],
                        "publication_state": "ready",
                    },
                    "source": {"commit": source_commit, "tree": source_tree},
                    "target": {
                        "repository_id": "agent-canon-test",
                        "route": "local_ref",
                        "mode": "merge",
                        "target_ref": target_ref,
                        "expected_target_oid": base_oid,
                        "expected_target_tree": base_tree,
                        "remote_name": "origin",
                        "pr_owner_api": "owner/repo",
                    },
                    "validation_provenance_ref": {},
                    "selection_sha256": "b" * 64,
                    "owner_attestation": {},
                    "candidate_attestation": {
                        "interface_delta": {
                            "entries": [
                                {
                                    "path": interface_path,
                                    "new_blob": "9" * 40,
                                    "new_mode": "100644",
                                }
                            ]
                        }
                    },
                    "result": None,
                    "pr_identity_cas_gate": None,
                    "publication_authority_body_sha256": "c" * 64,
                }

            def integrate(interface_path: str) -> dict[str, object]:
                nonlocal current_ref
                current_ref = base_oid
                authority = authority_for(interface_path)
                with (
                    patch.dict(
                        os.environ,
                        {
                            "AGENT_CANON_PARENT_ROOT": str(parent_root),
                            "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": str(parent_root),
                        },
                    ),
                    patch(
                        "tools.repository.github.publication_integrator.resolve_publication_authority",
                        side_effect=[authority, authority],
                    ),
                ):
                    return integrate_publication(PROJECT_ROOT, runner=runner)

            valid_receipt = integrate(CANONICAL_INTERFACE_PATH)
            self.assertEqual(valid_receipt["result_oid"], result_commit)
            self.assertIn(
                (
                    "git",
                    "-C",
                    str(PROJECT_ROOT.resolve()),
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{'9' * 40},{CANONICAL_INTERFACE_PATH}",
                ),
                executed,
            )

            retired_path = "reports/agents/ordered_integration_interface.json"
            executed.clear()
            with self.assertRaisesRegex(
                PublicationError,
                "ordered_integration:path_set_mismatch",
            ):
                integrate(retired_path)
            self.assertFalse(any(args[3] == "update-index" for args in executed))

    def test_ineligible_review_never_produces_publication_authority(self) -> None:
        """A non-eligible review fails closed before authority derivation."""
        with patch(
            "tools.repository.github.publication_integrator.resolve_review_eligibility",
            return_value={"outcome": "ineligible"},
        ):
            projection = resolve_publication_eligibility(PROJECT_ROOT)

        self.assertEqual(projection["outcome"], "ineligible")
        self.assertIsNone(projection["publication_authority"])
        self.assertEqual(
            projection["failure_codes"],
            ["publication_eligibility:review_not_eligible"],
        )

    def test_pull_request_receipt_binds_server_result_readback(self) -> None:
        """A PR receipt records the actual merge result and post-CAS readback."""
        expected_base = "a" * 40
        expected_tree = "b" * 40
        candidate = "3" * 40
        candidate_tree = "4" * 40
        server_result = "d" * 40
        server_tree = "e" * 40
        authority = {
            "publication_id": "w2-publication:test",
            "selection_sha256": "e" * 64,
            "target": {
                "route": "pull_request",
                "target_ref": "refs/heads/main",
                "mode": "merge",
                "expected_target_oid": expected_base,
                "expected_target_tree": expected_tree,
            },
            "candidate_authority": {
                "candidate_commit": candidate,
                "candidate_tree": candidate_tree,
            },
        }

        def read_git(_workspace: Path, command: list[str], **_kwargs: object) -> str:
            if command[-1] == "refs/heads/main":
                return expected_base
            if command[-1] == f"{expected_base}^{{tree}}":
                return expected_tree
            raise AssertionError(command)

        with (
            patch(
                "tools.repository.github.publication_integrator.resolve_publication_authority",
                side_effect=[authority, authority],
            ),
            patch(
                "tools.repository.github.publication_integrator._git_text",
                side_effect=read_git,
            ),
            patch(
                "tools.repository.github.publication_integrator._worktree_status",
                return_value="",
            ),
        ):
            receipt = integrate_publication(
                PROJECT_ROOT,
                pr_merge_adapter=lambda _request: {
                    "status": "merged",
                    "publication_readback_receipt": publication_readback_receipt(
                        post_merge_base_ref_sha=server_result,
                        merge_cas_base_sha=expected_base,
                        merge_cas_base_tree=expected_tree,
                        candidate_sha=candidate,
                        candidate_tree=candidate_tree,
                        merge_sha=server_result,
                        merge_tree=server_tree,
                    ),
                    "post_cas_ref_oid": server_result,
                    "post_cas_tree_oid": server_tree,
                },
                lifecycle_binding=lifecycle_binding(),
                ordered_input_evidence_refs=["evidence:" + "8" * 64],
            )

        self.assertEqual(receipt["candidate_oid"], candidate)
        self.assertEqual(receipt["candidate_tree_oid"], candidate_tree)
        self.assertEqual(receipt["result_oid"], server_result)
        self.assertEqual(receipt["result_tree_oid"], server_tree)
        self.assertEqual(receipt["post_cas_ref_oid"], server_result)
        gate = receipt["remote_publication_readback_gate"]
        if not is_string_object_mapping(gate):
            raise AssertionError("publication omitted its readback gate")
        self.assertEqual(gate.get("gate_id"), "G5")

    def test_boundary_gate_identity_is_distinct_and_replay_stable(self) -> None:
        """The lifecycle owner separates gate identities and stabilizes replay."""
        binding = lifecycle_binding()

        def gate_for(
            gate_id: str,
            invariant: str,
            owner_symbol: str,
        ) -> dict[str, object]:
            return materialize_gate_verdict(
                binding=binding,
                gate_id=gate_id,
                ordered_input_evidence_refs=["evidence:" + "8" * 64],
                invariant=invariant,
                output_digest="sha256:" + "a" * 64,
                owner=(
                    f"{PROJECT_ROOT / 'tools/repository/github/publication_integrator.py'}"
                    f"#{owner_symbol}"
                ),
                verdict="pass",
                retry_reason=None,
                next_checkpoint=None,
            )

        gates = [
            gate_for(gate_id, invariant, owner_symbol)
            for gate_id, invariant, owner_symbol in (
                ("G1", "source_correctness", "resolve_publication_eligibility"),
                ("G3", "pr_identity_cas", "resolve_publication_authority"),
                ("G5", "remote_publication_readback", "integrate_publication"),
            )
        ]
        replay = gate_for("G3", "pr_identity_cas", "resolve_publication_authority")

        evidence_refs: list[str] = []
        for gate in gates:
            gate_binding = gate.get("binding")
            if not is_string_object_mapping(gate_binding):
                raise AssertionError("materialized gate has no typed binding")
            evidence_ref = gate_binding.get("evidence_ref")
            if not isinstance(evidence_ref, str):
                raise AssertionError("materialized gate has no evidence reference")
            evidence_refs.append(evidence_ref)
        replay_binding = replay.get("binding")
        if not is_string_object_mapping(replay_binding):
            raise AssertionError("replayed gate has no typed binding")
        self.assertEqual(len(set(evidence_refs)), 3)
        self.assertEqual(replay_binding.get("evidence_ref"), evidence_refs[1])

    def test_pull_request_post_cas_readback_mismatch_fails_closed(self) -> None:
        """A server result and publication readback mismatch cannot emit G5."""
        expected_base = "a" * 40
        expected_tree = "b" * 40
        candidate = "3" * 40
        candidate_tree = "4" * 40
        server_result = "d" * 40
        server_tree = "e" * 40
        authority = {
            "publication_id": "w2-publication:test",
            "selection_sha256": "e" * 64,
            "target": {
                "route": "pull_request",
                "target_ref": "refs/heads/main",
                "mode": "merge",
                "expected_target_oid": expected_base,
                "expected_target_tree": expected_tree,
            },
            "candidate_authority": {
                "candidate_commit": candidate,
                "candidate_tree": candidate_tree,
            },
        }

        def read_git(_workspace: Path, command: list[str], **_kwargs: object) -> str:
            return expected_tree if command[-1].endswith("^{tree}") else expected_base

        with (
            patch(
                "tools.repository.github.publication_integrator.resolve_publication_authority",
                return_value=authority,
            ),
            patch(
                "tools.repository.github.publication_integrator._git_text",
                side_effect=read_git,
            ),
            patch(
                "tools.repository.github.publication_integrator._worktree_status",
                return_value="",
            ),
            self.assertRaises(PublicationError) as raised,
        ):
            integrate_publication(
                PROJECT_ROOT,
                pr_merge_adapter=lambda _request: {
                    "status": "merged",
                    "publication_readback_receipt": publication_readback_receipt(
                        post_merge_base_ref_sha=server_result,
                        merge_cas_base_sha=expected_base,
                        merge_cas_base_tree=expected_tree,
                        candidate_sha=candidate,
                        candidate_tree=candidate_tree,
                        merge_sha=server_result,
                        merge_tree=server_tree,
                    ),
                    "post_cas_ref_oid": "f" * 40,
                    "post_cas_tree_oid": server_tree,
                },
                lifecycle_binding=lifecycle_binding(),
            )

        self.assertEqual(
            raised.exception.code,
            "publication_integrator:post_cas_readback_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
