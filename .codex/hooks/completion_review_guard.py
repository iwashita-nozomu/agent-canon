#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Blocks completion while the current W2 candidate lacks an explicit independent-review APPROVE.
# upstream implementation ../../tools/agent_tools/review_dispatch.py reconciles the canonical candidate and review state.
# downstream design ./hook_dispatcher.py RETIRED_HOOK_ROUTES assigns this explicit review route.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook wiring and decisions.
# @dependency-end

"""Block Stop closeout until the canonical W2 review state is APPROVE."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path


def load_payload() -> dict[str, object]:
    """Read one hook payload without treating prose as authority."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def repo_root() -> Path:
    """Resolve the repository root used by the canonical review resolver."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def current_review_state(root: Path) -> Mapping[str, object] | None:
    """Return current review state, or no state when W2 is not active."""
    tools_root = root / "tools" / "agent_tools"
    if not tools_root.is_dir():
        return None
    sys.path.insert(0, str(tools_root))
    try:
        from review_dispatch import resolve_current_review_state

        return resolve_current_review_state(root)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def emit_block(state: Mapping[str, object]) -> None:
    """Emit the critical structured Stop decision."""
    candidate = state.get("candidate")
    candidate_id = (
        candidate.get("candidate_id") if isinstance(candidate, Mapping) else None
    )
    decision = state.get("decision")
    decision_name = decision.get("decision") if isinstance(decision, Mapping) else None
    json.dump(
        {
            "decision": "block",
            "reason": (
                "Current W2 candidate has no current independent-review APPROVE; "
                "publication and completion remain locked."
            ),
            "next_action": "resume_same_reviewer_and_record_current_candidate_approve",
            "candidate_id": candidate_id,
            "observed_decision": decision_name,
            "remediation": [
                "Have the parent or integration owner adjudicate each current-candidate hypothesis.",
                "Repair accepted findings that change the contract decision; record rejected findings with reason_code and evidence_ref before approval.",
                "Do not publish or report completion before the current candidate is approved.",
            ],
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def main() -> int:
    """Allow non-Stop activity and block only unresolved W2 completion."""
    payload = load_payload()
    if payload.get("hookEventName") != "Stop":
        return 0
    state = current_review_state(repo_root())
    if state is None:
        return 0
    candidate = state.get("candidate")
    decision = state.get("decision")
    if not isinstance(candidate, Mapping) or not isinstance(decision, Mapping):
        emit_block(state)
        return 0
    if decision.get("decision") == "APPROVE" and decision.get(
        "candidate_id"
    ) == candidate.get("candidate_id"):
        return 0
    emit_block(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
