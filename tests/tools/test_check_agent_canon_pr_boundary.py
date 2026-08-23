# @dependency-start
# contract test
# responsibility Verifies G2 receipt publication is delegated to the selected parent boundary.
# upstream implementation ../../tools/ci/check_agent_canon_pr.py owns G2 receipt publication.
# @dependency-end

"""Focused parent-boundary test for the G2 receipt adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = PROJECT_ROOT / "tools" / "ci"
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from check_agent_canon_pr import (
    _persist,  # pyright: ignore[reportPrivateUsage]  # noqa: E402
)
from parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationRequest,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
)


def test_g2_persist_publishes_only_below_attested_parent(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    subprocess.run(
        ("git", "init", "-q", "-b", "main"),
        cwd=parent,
        check=True,
        capture_output=True,
    )
    boundary = ParentRootSideEffectBoundary()
    attestation = boundary.attest(
        ParentRootAttestationRequest(
            cwd=parent,
            explicit_root=parent,
            purpose="g2-test",
        )
    )
    output = parent / "evidence" / "g2.json"
    receipt = {"fixture": "g2"}

    assert _persist(
        output,
        receipt,
        boundary=boundary,
        attestation=attestation,
    ) == receipt
    assert output.read_text(encoding="utf-8") == '{\n  "fixture": "g2"\n}\n'

    outside = tmp_path / "outside.json"
    try:
        _persist(
            outside,
            receipt,
            boundary=boundary,
            attestation=attestation,
        )
    except ParentRootSideEffectError:
        pass
    else:
        raise AssertionError("outside-parent G2 output was accepted")
    assert not outside.exists()
