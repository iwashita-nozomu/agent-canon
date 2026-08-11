# @dependency-start
# contract test
# responsibility Verifies the PR gate uses an authenticated child environment and unique task-local scratch.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns AgentCanon PR validation orchestration.
# @dependency-end

"""Focused source checks for the parent-bounded AgentCanon PR gate."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"


def test_pr_gate_reexecs_with_verified_child_environment() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "--purpose agent-canon-pr-script" in source
    assert "verify-child" in source
    assert "exec-parent-bound" in source


def test_explicit_pr_temp_is_a_preserved_base_for_one_unique_child() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'AGENT_CANON_PR_TEMP_BASE="${AGENT_CANON_PR_TEMP_ROOT:-' in source
    assert '--candidate "${AGENT_CANON_PR_TEMP_BASE}"' in source
    assert "--prefix pr-check." in source
    assert '--candidate "${AGENT_CANON_PR_TEMP_ROOT}"' in source
    assert "--purpose agent-canon-pr-receipt" in source
