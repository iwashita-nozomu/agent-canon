"""Tests for deterministic validation of the AgentCanon-log policy inventory."""

# @dependency-start
# contract test
# responsibility Verifies fixed 42-row read-only policy inventory validation without network access.
# upstream design ../../documents/design/runtime-log-repository-lifecycle.md RL-009..RL-012 policy evidence
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/log_policy.rs separates retrieval from validation
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

EXPECTED_BLOCKERS = (
    "A source-remote authority manifest is required before any legacy branch can be migrated.",
    "Migration must be a dry-run manifest, explicit authority, and exact remote readback.",
    "This inventory performs no branch deletion, merge, rewrite, or data migration.",
)


class PolicyInventoryError(ValueError):
    def __init__(self, code):
        self.code = code


def validate_inventory_bytes(raw: bytes):
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "input.json"
        source.write_bytes(raw)
        result = subprocess.run(
            [
                os.environ["AGENT_CANON_CLI"],
                "check-agent-canon-log-policy",
                "--input",
                str(source),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    fields = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    if result.returncode:
        raise PolicyInventoryError(fields["AGENT_CANON_LOG_POLICY_ERROR_CODE"])
    return SimpleNamespace(
        legacy_branch_count=int(fields["AGENT_CANON_LOG_POLICY_LEGACY_BRANCH_ROWS"]),
        mapping_count=int(fields["AGENT_CANON_LOG_POLICY_MAPPINGS"]),
        remote_ref_count=int(fields["AGENT_CANON_LOG_POLICY_REMOTE_LOG_REFS"]),
        read_only_blocker_count=int(
            fields["AGENT_CANON_LOG_POLICY_READ_ONLY_BLOCKERS"]
        ),
        main_observation_count=int(
            fields["AGENT_CANON_LOG_POLICY_MAIN_OBSERVATION_COUNT"]
        ),
    )


def deterministic_inventory_fixture() -> bytes:
    """Return a network-free 42-row fixture for the policy validator."""
    branches = [f"logs/fixture-{number:02d}" for number in range(1, 43)]
    rows = [
        {
            "branch": branch,
            "count": number,
            "digest": f"{number:064x}",
            "head": f"{number:040x}",
            "tree": f"{number + 100:040x}",
        }
        for number, branch in enumerate(branches, start=1)
    ]
    mapping = {
        branch: {
            "reason": "source remote supplied for future migration authority; no data moved",
            "stable_branch": "logs/github.com-iwashita-nozomu-agent-canon-log-b748513d5bba954b360f59d7",
            "status": "authority_required",
        }
        for branch in branches
    }
    payload = {
        "legacy_branch_count": 42,
        "legacy_branches": rows,
        "legacy_to_stable": mapping,
        "main_legacy_import": {
            "count": 26,
            "digest": "a" * 64,
            "head": "b" * 40,
            "tree": "c" * 40,
        },
        "migration_blockers": list(EXPECTED_BLOCKERS),
        "mode": "read_only",
        "observation_snapshot": {
            "observed_at_utc": "2026-07-30T00:00:00Z",
            "remote_log_ref_count": 42,
            "snapshot_id": "d" * 64,
        },
        "policy_schema": "agent-canon-log-policy.v1",
        "remote": "https://github.com/iwashita-nozomu/agent-canon-log.git",
        "remote_log_ref_heads": {branch: "e" * 40 for branch in branches},
        "schema": "agent-canon-log-legacy-inventory.v1",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AgentCanonLogPolicyTest(unittest.TestCase):
    """Exercise the deterministic policy contract and its coverage failures."""

    def test_fixture_covers_all_policy_evidence(self) -> None:
        """The local fixture proves 42 rows, mappings, refs, blockers, and main observation."""
        summary = validate_inventory_bytes(deterministic_inventory_fixture())
        self.assertEqual(summary.legacy_branch_count, 42)
        self.assertEqual(summary.mapping_count, 42)
        self.assertEqual(summary.remote_ref_count, 42)
        self.assertEqual(summary.read_only_blocker_count, 3)
        self.assertEqual(summary.main_observation_count, 26)

    def test_missing_branch_row_is_a_typed_failure(self) -> None:
        """A partial namespace cannot be accepted as a policy inventory."""
        payload = json.loads(deterministic_inventory_fixture())
        payload["legacy_branches"].pop()
        with self.assertRaises(PolicyInventoryError) as raised:
            validate_inventory_bytes(json.dumps(payload).encode("utf-8"))
        self.assertEqual(raised.exception.code, "policy_inventory_legacy_branch_rows")

    def test_network_retrieval_is_not_used_by_fixture_validation(self) -> None:
        """Validation accepts bytes directly, keeping network retrieval outside its oracle."""
        source = deterministic_inventory_fixture()
        self.assertEqual(validate_inventory_bytes(source).mapping_count, 42)


if __name__ == "__main__":
    unittest.main()
