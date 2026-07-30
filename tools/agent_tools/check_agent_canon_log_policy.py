#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates the read-only AgentCanon-log legacy inventory contract.
# upstream design ../../documents/design/runtime-log-repository-lifecycle.md RL-009..RL-012 policy evidence
# downstream implementation ../../tests/agent_tools/test_agent_canon_log_policy.py exercises deterministic validation
# downstream implementation ../../tools/agent_tools/runtime_log_archive_git.py consumes legacy import/readback boundaries
# @dependency-end
"""Validate the fixed AgentCanon-log PR #4 legacy inventory blob."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

DEFAULT_REMOTE = "https://github.com/iwashita-nozomu/agent-canon-log.git"
DEFAULT_COMMIT = "9f10130184539beaebe8991bbcfb5665d476fbe5"
INVENTORY_PATH = "docs/migration/legacy-inventory.json"
EXPECTED_BLOB_SHA256 = "ad96c36a281ccea58bcd38166ae78ac1a61ad57362de57fdf5e92c82a0aa9d02"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_BLOCKERS = (
    "A source-remote authority manifest is required before any legacy branch can be migrated.",
    "Migration must be a dry-run manifest, explicit authority, and exact remote readback.",
    "This inventory performs no branch deletion, merge, rewrite, or data migration.",
)


class PolicyInventoryError(ValueError):
    """Raised when policy inventory data does not meet the fixed read-only contract."""

    def __init__(self, code: str) -> None:
        """Store the stable machine-readable failure code."""
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PolicyInventorySummary:
    """Deterministic counts and digest for one validated inventory blob."""

    blob_sha256: str
    legacy_branch_count: int
    mapping_count: int
    remote_ref_count: int
    read_only_blocker_count: int
    main_observation_count: int


def _object(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PolicyInventoryError(code)
    return cast(dict[str, object], value)


def _string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyInventoryError(code)
    return value


def validate_inventory_bytes(
    raw: bytes,
    *,
    expected_blob_sha256: str | None = None,
) -> PolicyInventorySummary:
    """Validate counts, keys, observations, blockers, and read-only policy state."""
    digest = hashlib.sha256(raw).hexdigest()
    if expected_blob_sha256 is not None and digest != expected_blob_sha256:
        raise PolicyInventoryError("policy_inventory_blob_digest_mismatch")
    try:
        payload = _object(json.loads(raw.decode("utf-8")), "policy_inventory_json_invalid")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyInventoryError("policy_inventory_json_invalid") from exc
    if payload.get("schema") != "agent-canon-log-legacy-inventory.v1":
        raise PolicyInventoryError("policy_inventory_schema_mismatch")
    if payload.get("policy_schema") != "agent-canon-log-policy.v1":
        raise PolicyInventoryError("policy_inventory_policy_schema_mismatch")
    if payload.get("mode") != "read_only":
        raise PolicyInventoryError("policy_inventory_not_read_only")
    if payload.get("remote") != DEFAULT_REMOTE:
        raise PolicyInventoryError("policy_inventory_remote_mismatch")

    branches_value = payload.get("legacy_branches")
    if not isinstance(branches_value, list) or len(branches_value) != 42:
        raise PolicyInventoryError("policy_inventory_legacy_branch_rows")
    branches = cast(list[object], branches_value)
    branch_names: set[str] = set()
    for row_value in branches:
        row = _object(row_value, "policy_inventory_branch_row_invalid")
        branch = _string(row.get("branch"), "policy_inventory_branch_name_invalid")
        if not branch.startswith("logs/") or branch in branch_names:
            raise PolicyInventoryError("policy_inventory_branch_name_invalid")
        branch_names.add(branch)
        count = row.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise PolicyInventoryError("policy_inventory_branch_count_invalid")
        if not HEX64.fullmatch(_string(row.get("digest"), "policy_inventory_branch_digest_invalid")):
            raise PolicyInventoryError("policy_inventory_branch_digest_invalid")
        if not HEX40.fullmatch(_string(row.get("head"), "policy_inventory_branch_head_invalid")):
            raise PolicyInventoryError("policy_inventory_branch_head_invalid")
        if not HEX40.fullmatch(_string(row.get("tree"), "policy_inventory_branch_tree_invalid")):
            raise PolicyInventoryError("policy_inventory_branch_tree_invalid")
    if payload.get("legacy_branch_count") != 42:
        raise PolicyInventoryError("policy_inventory_branch_count_mismatch")

    mappings = _object(payload.get("legacy_to_stable"), "policy_inventory_mapping_invalid")
    if len(mappings) != 42 or set(mappings) != branch_names:
        raise PolicyInventoryError("policy_inventory_mapping_coverage")
    for value in mappings.values():
        mapping = _object(value, "policy_inventory_mapping_row_invalid")
        if mapping.get("status") != "authority_required":
            raise PolicyInventoryError("policy_inventory_mapping_status")
        if mapping.get("stable_branch") != (
            "logs/github.com-iwashita-nozomu-agent-canon-log-b748513d5bba954b360f59d7"
        ):
            raise PolicyInventoryError("policy_inventory_mapping_stable_branch")
        if mapping.get("reason") != "source remote supplied for future migration authority; no data moved":
            raise PolicyInventoryError("policy_inventory_mapping_reason")

    ref_heads = _object(payload.get("remote_log_ref_heads"), "policy_inventory_remote_refs_invalid")
    if len(ref_heads) != 42 or set(ref_heads) != branch_names:
        raise PolicyInventoryError("policy_inventory_remote_ref_coverage")
    for value in ref_heads.values():
        if not HEX40.fullmatch(_string(value, "policy_inventory_remote_ref_head_invalid")):
            raise PolicyInventoryError("policy_inventory_remote_ref_head_invalid")

    blockers = payload.get("migration_blockers")
    if blockers != list(EXPECTED_BLOCKERS):
        raise PolicyInventoryError("policy_inventory_read_only_blockers")
    observation = _object(payload.get("observation_snapshot"), "policy_inventory_observation_invalid")
    if observation.get("remote_log_ref_count") != 42:
        raise PolicyInventoryError("policy_inventory_observation_count")
    observed_at = _string(observation.get("observed_at_utc"), "policy_inventory_observation_time")
    if not observed_at.endswith("Z"):
        raise PolicyInventoryError("policy_inventory_observation_time")
    if not HEX64.fullmatch(_string(observation.get("snapshot_id"), "policy_inventory_snapshot_id")):
        raise PolicyInventoryError("policy_inventory_snapshot_id")
    main_observation = _object(payload.get("main_legacy_import"), "policy_inventory_main_observation")
    main_count = main_observation.get("count")
    if not isinstance(main_count, int) or isinstance(main_count, bool) or main_count != 26:
        raise PolicyInventoryError("policy_inventory_main_observation_count")
    for name in ("digest", "head", "tree"):
        pattern = HEX64 if name == "digest" else HEX40
        if not pattern.fullmatch(_string(main_observation.get(name), "policy_inventory_main_observation")):
            raise PolicyInventoryError("policy_inventory_main_observation")
    return PolicyInventorySummary(
        blob_sha256=digest,
        legacy_branch_count=42,
        mapping_count=len(mappings),
        remote_ref_count=len(ref_heads),
        read_only_blocker_count=len(EXPECTED_BLOCKERS),
        main_observation_count=main_count,
    )


def retrieve_inventory_blob(remote: str, commit: str = DEFAULT_COMMIT) -> bytes:
    """Fetch one policy commit into a temporary Git object store, then read its blob."""
    with tempfile.TemporaryDirectory(prefix="agent-canon-log-policy-") as temp_dir:
        root = Path(temp_dir)
        init = subprocess.run(["git", "init", "-q", str(root)], check=False, capture_output=True)
        if init.returncode != 0:
            raise PolicyInventoryError("policy_inventory_fetch_init_failed")
        added = subprocess.run(
            ["git", "-C", str(root), "remote", "add", "origin", remote],
            check=False,
            capture_output=True,
        )
        if added.returncode != 0:
            raise PolicyInventoryError("policy_inventory_remote_invalid")
        fetched = subprocess.run(
            ["git", "-C", str(root), "fetch", "--no-tags", "--quiet", "origin", commit],
            check=False,
            capture_output=True,
            text=True,
        )
        if fetched.returncode != 0:
            raise PolicyInventoryError("policy_inventory_fetch_failed")
        shown = subprocess.run(
            ["git", "-C", str(root), "show", f"{commit}:{INVENTORY_PATH}"],
            check=False,
            capture_output=True,
        )
        if shown.returncode != 0:
            raise PolicyInventoryError("policy_inventory_blob_missing")
        return shown.stdout


def build_parser() -> argparse.ArgumentParser:
    """Build the policy verifier CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", type=Path, help="Validate a deterministic local fixture; never fetches.")
    source.add_argument("--remote", default=DEFAULT_REMOTE, help="Git remote used only for network retrieval.")
    parser.add_argument("--commit", default=DEFAULT_COMMIT, help="Policy commit to retrieve.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate one local fixture or retrieve one remote policy blob."""
    args = build_parser().parse_args(argv)
    try:
        raw = args.input.read_bytes() if args.input else retrieve_inventory_blob(args.remote, args.commit)
        expected = EXPECTED_BLOB_SHA256 if not args.input and args.commit == DEFAULT_COMMIT else None
        summary = validate_inventory_bytes(raw, expected_blob_sha256=expected)
    except (OSError, PolicyInventoryError) as exc:
        code = exc.code if isinstance(exc, PolicyInventoryError) else "policy_inventory_input_unavailable"
        print(f"AGENT_CANON_LOG_POLICY_ERROR_CODE={code}")
        print("AGENT_CANON_LOG_POLICY_VALIDATION=fail")
        return 1
    print(f"AGENT_CANON_LOG_POLICY_COMMIT={args.commit if args.input is None else 'deterministic-fixture'}")
    print(f"AGENT_CANON_LOG_POLICY_BLOB_SHA256={summary.blob_sha256}")
    print(f"AGENT_CANON_LOG_POLICY_LEGACY_BRANCH_ROWS={summary.legacy_branch_count}")
    print(f"AGENT_CANON_LOG_POLICY_MAPPINGS={summary.mapping_count}")
    print(f"AGENT_CANON_LOG_POLICY_REMOTE_LOG_REFS={summary.remote_ref_count}")
    print(f"AGENT_CANON_LOG_POLICY_READ_ONLY_BLOCKERS={summary.read_only_blocker_count}")
    print(f"AGENT_CANON_LOG_POLICY_MAIN_OBSERVATION_COUNT={summary.main_observation_count}")
    print("AGENT_CANON_LOG_POLICY_VALIDATION=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
