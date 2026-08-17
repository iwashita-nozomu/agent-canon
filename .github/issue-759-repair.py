#!/usr/bin/env python3
"""Materialize the reviewed #759 implementation from checked-in transport payloads."""

from __future__ import annotations

import base64
import hashlib
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = [
    (
        "tools/agent_tools/autonomous_convergence.py",
        ".github/issue-759-payload-autonomous.txt",
        "d8c015131a6d21e5ada871073b1f9836acc29b703851bc24904e08accbd42453",
    ),
    (
        "tests/agent_tools/test_autonomous_convergence.py",
        ".github/issue-759-payload-autonomous-tests.txt",
        "08dc2824884191e633d6b848b728138218be56fb19407c813937229808a5d6a2",
    ),
    (
        "agents/skills/agent-orchestration.execution-contract.toml",
        ".github/issue-759-payload-contract.txt",
        "e5a65f979d2474508f2b668d873979e05d1fcd1095452361e8e2a1aae1dce9a1",
    ),
    (
        "tools/agent_tools/check_execution_time_aware_orchestration.py",
        ".github/issue-759-payload-checker.txt",
        "2016d8c7bdf84c97ec3c1fef07c0a8fc6e635b9c748538ce9f394f10d315b271",
    ),
    (
        "tests/agent_tools/test_execution_time_aware_orchestration_contract.py",
        ".github/issue-759-payload-contract-tests.txt",
        "507dda78aabf127631818de841a12bef6477c8303f4d6db105918d6767aeb5dc",
    ),
]


def main() -> int:
    for target_rel, payload_rel, expected_sha256 in PAYLOADS:
        compressed = base64.b64decode((ROOT / payload_rel).read_text(encoding="ascii"))
        content = zlib.decompress(compressed)
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != expected_sha256:
            raise SystemExit(
                f"payload digest mismatch for {target_rel}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        target = ROOT / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
