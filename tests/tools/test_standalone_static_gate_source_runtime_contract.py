"""Static ownership checks for source/runtime validation routing."""

# @dependency-start
# contract test
# responsibility Verifies standalone static units own no-runtime dependency regressions and prompt-eval skill evidence.
# upstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh owns contract and eval unit commands
# upstream implementation ../../tools/agent_tools/run_accumulated_agent_evals.py consumes explicit skill-used evidence
# upstream design ../../documents/design/source-owned-dependency-validation.md source and persisted graph authority split
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs selected unit owners
# @dependency-end

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "ci" / "run_standalone_static_gate_unit.sh"

SOURCE_REGRESSION_MODULES = (
    "tests.agent_tools.test_graph_client_source_projection",
    "tests.tools.test_agent_canon_pr_dependency_source_gate",
    "tests.tools.test_agent_canon_pr_graph_gate_integration",
    "tests.agent_tools.test_check_dependency_headers",
    "tests.agent_tools.test_check_design_doc_claims",
    "tests.agent_tools.test_tool_drift",
    "tests.agent_tools.test_vector_search",
    "tests.agent_tools.test_dependency_manifest_tools",
)


def function_body(text: str, name: str, next_name: str) -> str:
    """Return one shell function body using adjacent owner declarations."""
    return text.split(f"{name}() {{", 1)[1].split(f"\n}}\n\n{next_name}", 1)[0]


def test_contract_unit_runs_all_source_runtime_regressions() -> None:
    """Every affected source consumer is validated by the contract unit."""
    text = RUNNER.read_text(encoding="utf-8")
    body = function_body(text, "run_contracts", "run_eval() (")
    remainder = text.replace(body, "", 1)

    for module in SOURCE_REGRESSION_MODULES:
        assert module in body
        assert module not in remainder


def test_eval_unit_declares_the_skills_used_by_its_prompt_evaluation() -> None:
    """Prompt eval receives run-owned skill evidence instead of false negatives."""
    text = RUNNER.read_text(encoding="utf-8")
    body = text.split("run_eval() (", 1)[1].split("\n)\n\nrun_workflow_container()", 1)[0]
    remainder = text.replace(body, "", 1)

    for skill in ("agent-orchestration", "result-artifact-writeout"):
        command = f"--skill-used {skill}"
        assert body.count(command) == 1
        assert command not in remainder


def test_eval_failure_evidence_is_filtered_before_temporary_cleanup() -> None:
    """Failure rows remain observable even though bounded captures are deleted."""
    text = RUNNER.read_text(encoding="utf-8")
    body = text.split("run_eval() (", 1)[1].split("\n)\n\nrun_workflow_container()", 1)[0]

    assert "AGENT_CANON_STATIC_EVAL_FAILURE_LINES_BEGIN" in body
    assert "status=fail|_STATUS=fail|_FAILED=[1-9][0-9]*" in body
    assert body.index("AGENT_CANON_STATIC_EVAL_FAILURE_LINES_BEGIN") < body.index(
        "return \"${primary_status}\""
    )


def test_all_source_gate_entrypoints_require_distinct_control_and_runtime_roots() -> None:
    """A source checkout cannot become either the control or runtime owner."""
    source = (ROOT / "tools" / "ci" / "run_standalone_static_gate_unit.sh").read_text(
        encoding="utf-8"
    )
    run_all = (ROOT / "tools" / "ci" / "run_all_checks.sh").read_text(
        encoding="utf-8"
    )
    pr = (ROOT / "tools" / "ci" / "check_agent_canon_pr.sh").read_text(
        encoding="utf-8"
    )
    for text in (source, run_all, pr):
        assert "control_parent_root_required" in text
        assert "runtime_root_required" in text
        assert "control_parent_root_is_source" in text
        assert "AGENT_CANON_PARENT_ROOT=\"${AGENT_CANON_CONTROL_PARENT_ROOT}\"" in text
        assert "${RUNNER_TEMP:-${TMPDIR:-/tmp}}" not in text
