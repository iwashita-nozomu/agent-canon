# @dependency-start
# contract test
# responsibility Tests AgentCanon latest command TODO routing in small focused fixtures.
# upstream design ../../tools/README.md documents the high-level AgentCanon latest route.
# upstream implementation ../../tools/update_agent_canon.sh routes pending parent-repo TODOs.
# upstream implementation ../../tools/agent_tools/agent_canon_update_todos.py defines TODO tool output.
# upstream implementation ../../tests/tools/test_update_agent_canon.py provides submodule update fixtures.
# @dependency-end

"""Focused tests for AgentCanon latest TODO routing."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.tools.test_update_agent_canon import (
    AGENT_CANON_IS_SUBMODULE,
    SubmoduleUpdateAgentCanonTest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from update_lifecycle_contract import materialize_gate_verdict  # noqa: E402


def lifecycle_binding() -> dict[str, object]:
    """Return one fixed G4/G5 consumer identity."""
    return {
        "transaction_id": "tx:" + "1" * 64,
        "snapshot_id": "snapshot:" + "2" * 64,
        "candidate_sha": "3" * 40,
        "tree_sha": "4" * 40,
        "input_digest": "sha256:" + "5" * 64,
        "tool_id": "agent-canon-latest",
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


def test_latest_consumes_g4_g5_receipts_without_rechecking_source(tmp_path: Path) -> None:
    """The downstream latest gate trusts one ordered projection/readback bundle."""
    binding = lifecycle_binding()
    g4 = materialize_gate_verdict(
        binding=binding,
        gate_id="G4",
        ordered_input_evidence_refs=["evidence:" + "8" * 64],
        invariant="parent_projection_integrity",
        output_digest="sha256:" + "9" * 64,
        owner=str(PROJECT_ROOT / "tools" / "update_agent_canon.sh") + "#accept_dependency_frontier",
        verdict="pass",
    )
    g5 = materialize_gate_verdict(
        binding=binding,
        gate_id="G5",
        ordered_input_evidence_refs=[g4["binding"]["evidence_ref"]],
        invariant="remote_publication_readback",
        output_digest="sha256:" + "a" * 64,
        owner=str(PROJECT_ROOT / "tools" / "agent_tools" / "publication_integrator.py")
        + "#integrate_publication",
        verdict="pass",
    )
    bundle = tmp_path / "g4-g5.json"
    bundle.write_text(json.dumps({"gate_verdicts": [g4, g5]}), encoding="utf-8")

    result = subprocess.run(
        ["bash", "tools/ci/check_agent_canon_latest.sh"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "AGENT_CANON_LATEST_GATE_BUNDLE": str(bundle)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AGENT_CANON_LATEST_GATE_ORDER=G4,G5" in result.stdout
    assert "AGENT_CANON_LATEST_ROUTE=lifecycle_readback_receipt" in result.stdout
    assert "agent_canon_plan_route=" not in result.stdout


@pytest.mark.skipif(
    not AGENT_CANON_IS_SUBMODULE,
    reason="submodule wrapper tests only apply when vendor/agent-canon is a submodule",
)
def test_latest_reports_pending_update_todos_without_failing(tmp_path: Path) -> None:
    """Pending parent-repo update TODOs route work without failing latest."""
    fixture = SubmoduleUpdateAgentCanonTest(
        methodName="test_ensure_latest_reports_already_current_submodule"
    )
    bare_repo, _work_dir = fixture.make_agent_canon_remote(tmp_path)
    repo = fixture.make_superproject(tmp_path, bare_repo)
    todo_tool = repo / "tools" / "agent_tools" / "agent_canon_update_todos.py"
    todo_tool.parent.mkdir(parents=True)
    todo_tool.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import sys",
                "if sys.argv[1:] == ['plan', '--write']:",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1')",
                "    print('AGENT_CANON_UPDATE_TODO_PENDING=ACUT-test')",
                "    raise SystemExit(0)",
                "if sys.argv[1:] == ['acknowledge']:",
                "    print('unexpected acknowledge')",
                "    raise SystemExit(0)",
                "raise SystemExit(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    todo_tool.chmod(0o755)

    latest = subprocess.run(
        ["bash", "tools/update_agent_canon.sh", "latest"],
        cwd=repo,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert latest.returncode == 0, latest.stdout + latest.stderr
    assert "AGENT_CANON_UPDATE_TODO_PENDING_COUNT=1" in latest.stdout
    assert "AGENT_CANON_LATEST_TODOS=pending" in latest.stdout
    assert "AGENT_CANON_LATEST_TOOL_RESULT=updated_with_pending_todos" in latest.stdout
    assert "NEXT_ACTION=apply_agent_canon_update_todos_then_rerun_latest" in latest.stdout
    assert "unexpected acknowledge" not in latest.stdout
