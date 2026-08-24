"""Focused acceptance cases for distributed owner correspondence."""

# @dependency-start
# contract test
# responsibility Exercises owner-local guarantee receipts, existing-edge invalidation, and integration non-rerun projection.
# upstream implementation ../../tools/agent_tools/packets.py owns packet normalization and reuse tuple.
# upstream implementation ../../tools/agent_tools/autonomous_convergence.py owns closeout projection consumer.
# upstream implementation ../../tools/agent_tools/publication_integrator.py owns integration receipt projection.
# upstream implementation ../../tools/agent_tools/issue_sync.py owns Issue clause projection.
# @dependency-end

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from autonomous_convergence import owner_receipt_closeout_state  # noqa: E402
from issue_sync import GitHubIssueRecord, project_issue_clauses  # noqa: E402
from packets import (  # noqa: E402
    OWNER_GUARANTEE_PACKET_SCHEMA,
    OWNER_INVALIDATION_PACKET_SCHEMA,
    normalize_owner_invalidation_packet,
    owner_receipt_is_invalidated,
    owner_receipt_key,
)
from publication_integrator import owner_receipt_projection  # noqa: E402


def receipt(
    *,
    owner: str = "bootstrap-runtime-owner",
    property_ref: str = "contract:tool-image",
    plane: str = "tool-container",
    input_ref: str = "command:docker-build",
    state: str = "verified",
    outcome: str = "observed_pass",
    edges: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": OWNER_GUARANTEE_PACKET_SCHEMA,
        "owner_ref": owner,
        "candidate_digest": "candidate:1",
        "property_ref": property_ref,
        "mechanism_ref": "bootstrap.sh#build",
        "mechanism_transition": "checkout->image",
        "mechanism_sufficiency": "the image is produced by the selected build path",
        "not_guaranteed": ["host-daemon-capability", "project-tests"],
        "failure_semantics": "docker failure is returned without claiming success",
        "execution_plane": plane,
        "tool_input_locator": input_ref,
        "primary_observation_ref": f"receipt:{owner}:{property_ref}:{plane}",
        "observation_outcome": outcome,
        "correspondence_state": state,
        "invalidation_inputs": ["candidate_digest", "mechanism_ref", "effect_closure", "tool_input_locator"],
        "downstream_edges": list(edges or []),
        "source_snapshot": "git:2486f179",
        "authority_ref": "user:ordinary-docker-build",
    }


def test_grounded_receipt_and_speculative_hardening_are_distinct() -> None:
    grounded = receipt()
    speculative = receipt(
        owner="reviewer-hypothesis",
        property_ref="fsync-crash-recovery",
        state="advisory",
        outcome="inconclusive",
    )
    assert owner_receipt_projection([grounded, speculative])["publication_state"] == "ready"
    assert owner_receipt_projection([speculative])["publication_state"] == "ready"
    assert owner_receipt_projection([speculative])["owner_receipt_refs"] == []


def test_repeated_agent_claims_and_identical_receipts_are_one_lookup() -> None:
    first = receipt()
    duplicate = dict(first)
    duplicate["primary_observation_ref"] = "copied-agent-claim"
    projection = owner_receipt_projection([first, duplicate])
    assert projection["owner_receipt_refs"] == [first["primary_observation_ref"]]
    assert owner_receipt_key(first) == owner_receipt_key(duplicate)


def test_distinct_hosted_property_is_kept_once_and_missing_is_bounded() -> None:
    local = receipt()
    hosted = receipt(
        owner="hosted-publication-owner",
        property_ref="clean-host-publication",
        plane="remote-publication",
        input_ref="command:hosted-ci",
    )
    projection = owner_receipt_projection(
        [local, hosted],
        required_owner_refs=["bootstrap-runtime-owner", "hosted-publication-owner"],
    )
    assert projection["publication_state"] == "ready"
    assert len(projection["owner_receipt_refs"]) == 2
    missing = owner_receipt_projection([local], required_owner_refs=["hosted-publication-owner"])
    assert missing["publication_state"] == "blocked"
    assert missing["missing_or_incompatible"] == ["missing_owner:hosted-publication-owner"]


def test_invalidation_reaches_only_declared_dependency_edge() -> None:
    owner_a = receipt(owner="owner-a", edges=["owner-a->owner-b"])
    owner_b = receipt(owner="owner-b")
    owner_c = receipt(owner="owner-c")
    assert owner_receipt_closeout_state([owner_a, owner_b, owner_c], dependency_edges=["owner-a->owner-b"]).ready
    invalidation = normalize_owner_invalidation_packet(
        {
            "schema": OWNER_INVALIDATION_PACKET_SCHEMA,
            "from_owner": "owner-a",
            "to_owner": "owner-b",
            "candidate_digest": "candidate:1",
            "changed_mechanism_ref": "bootstrap.sh#build",
            "invalidated_property_ref": "contract:tool-image",
            "invalidated_receipt_ref": str(owner_a["primary_observation_ref"]),
            "reason": "mechanism_changed",
            "affected_edge": "owner-a->owner-b",
            "owner_action": "reevaluate_local_correspondence",
        }
    )
    assert invalidation["to_owner"] == "owner-b"
    assert owner_receipt_is_invalidated(owner_a, invalidation) is True
    assert owner_receipt_is_invalidated(owner_b, invalidation) is True
    assert owner_receipt_is_invalidated(owner_c, invalidation) is False
    assert owner_c["owner_ref"] == "owner-c"


def test_issue_excessive_done_is_advisory_while_grounded_problem_remains() -> None:
    issue = GitHubIssueRecord(
        repository="iwashita-nozomu/agent-canon",
        number="873",
        title="Distributed guarantee route",
        state="OPEN",
        url="https://github.com/iwashita-nozomu/agent-canon/issues/873",
        body="## Problem\nObserved reachable failure. Evidence: artifact:failure-1.\n\n## Done\nAdd fsync everywhere.",
    )
    projected = project_issue_clauses(issue)
    projected_states = {item["clause_kind"]: item["state"] for item in projected}
    assert projected_states["problem"] == "grounded"
    assert projected_states["done"] == "advisory"
    unsupported = issue.__class__(
        repository=issue.repository,
        number=issue.number,
        title=issue.title,
        state=issue.state,
        url=issue.url,
        body="## Problem\nObserved reachable failure.\n\n## Done\nAdd fsync everywhere.",
    )
    states = {item["clause_kind"]: item["state"] for item in project_issue_clauses(unsupported)}
    assert states["problem"] == "unproven"
    assert states["done"] == "advisory"


def test_integration_reports_mismatch_without_command_execution() -> None:
    projection = owner_receipt_projection(
        [receipt()],
        candidate_digest="candidate:other",
    )
    assert projection["publication_state"] == "blocked"
    assert any(str(value).startswith("incompatible:") for value in projection["missing_or_incompatible"])
