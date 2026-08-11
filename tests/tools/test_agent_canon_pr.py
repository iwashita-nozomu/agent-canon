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


def test_memory_cli_readback_uses_bounded_cargo_target() -> None:
    """The PR gate reads the executable from its parent-owned target."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert (
        'local memory_cli="${AGENT_CANON_CLI_TARGET_DIR}/debug/agent-canon"'
        in source
    )
    assert (
        'local memory_cli="${AGENT_CANON_SOURCE_ROOT}/rust/'
        'agent-canon/target/debug/agent-canon"'
        not in source
    )
    assert (
        "AGENT_CANON_MEMORY_CLI_REASON=rust build did not produce "
        "${memory_cli}"
        in source
    )
