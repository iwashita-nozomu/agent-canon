# @dependency-start
# contract test
# responsibility Tests mathematical-intent packet normalization and spawn scope.
# upstream implementation ../../tools/agent/orchestration/packets.py owns packet normalization and manifest identity
# upstream implementation ../../tools/agent/orchestration/tool_calls.py owns spawn ToolCall admission
# upstream implementation ../../tools/runtime/authority/writer_target.py owns math writer target narrowing
# @dependency-end

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS))

from tools.agent.orchestration.packets import (  # noqa: E402
    MATHEMATICAL_INTENT_PACKET_SCHEMA,
    mathematical_intent_packet_mapping,
    math_intent_route_id_from_context,
    normalize_mathematical_intent_packet,
    validate_mathematical_intent_route,
)
from tools.agent.orchestration.tool_calls import materialize_subagent_spawn_tool_call  # noqa: E402
from tools.runtime.authority.writer_target import WriterTarget  # noqa: E402


FORBIDDEN = [
    "architecture",
    "framework",
    "jit",
    "compiler",
    "backend",
    "runtime",
    "container",
    "docker",
    "routing",
    "environment",
    "common infrastructure",
    "proof infrastructure",
    "ir infrastructure",
]
MATH_ROUTE = "mathematical_correction"


def packet(
    *,
    allowed: list[str] | None = None,
    separate_handoff_targets: list[str] | None = None,
) -> dict[str, object]:
    """Return one complete typed math packet fixture."""
    return {
        "schema": MATHEMATICAL_INTENT_PACKET_SCHEMA,
        "math_object": "root of f(x)",
        "problem": "find x such that f(x)=0",
        "variables": "x in R",
        "domains": "R",
        "units": "dimensionless",
        "objective": "not_applicable: root finding",
        "residual": "r(x)=f(x)",
        "constraints": "not_applicable",
        "equations": "f(x)=0",
        "definitions": "r := f(x)",
        "assumptions": "f is continuous near the root",
        "approximations": "not_applicable",
        "derivation": "Newton update follows from first-order expansion",
        "iteration_map": "x_next = x - f(x)/f'(x)",
        "update_map": "state is x and residual is f(x)",
        "invariants": "finite x and residual",
        "limits": "x converges to a root under local assumptions",
        "stopping_scalar": "abs(f(x))",
        "failure_semantics": "zero derivative and non-finite state are failures",
        "equation_to_code_map": [
            {
                "equation": "f(x)=0",
                "code_path": "src/solver.py",
                "symbol_or_call_path": "newton_step",
            }
        ],
        "math_oracle": "exact quadratic root and residual bound",
        "counterexample": "zero derivative initial point",
        "mathematical_definition_paths": ["src/solver.py"],
        "mathematical_oracle_paths": ["tests/math_oracle.py"],
        "mathematical_documentation_paths": ["documents/math.md"],
        "allowed_write_paths": allowed
        or ["src/solver.py", "tests/math_oracle.py", "documents/math.md"],
        "forbidden_surfaces": FORBIDDEN,
        "separate_handoff_targets": separate_handoff_targets or [],
    }


def identity(root: Path, branch: str = "fix/math") -> dict[str, object]:
    """Return a writer target checkout identity fixture."""
    return {
        "cwd": str(root),
        "git_root": str(root),
        "branch": branch,
        "head": "a" * 40,
        "remote": "owner/repository",
    }


def target(root: Path, paths: tuple[str, ...] = ("src/solver.py",)) -> WriterTarget:
    """Return one prepared writer target fixture."""
    return WriterTarget(str(root), "fix/math", "owner/repository", paths)


def test_packet_normalization_is_closed_and_serializable() -> None:
    """A complete packet round-trips without adding an identity registry."""
    normalized = normalize_mathematical_intent_packet(packet())
    assert (
        mathematical_intent_packet_mapping(normalized)["schema"]
        == MATHEMATICAL_INTENT_PACKET_SCHEMA
    )
    assert normalized.allowed_write_paths == (
        "src/solver.py",
        "tests/math_oracle.py",
        "documents/math.md",
    )


def test_math_route_accepts_only_canonical_route_id() -> None:
    """Spawn callers cannot replace the task-catalog math route with a mapping."""
    assert validate_mathematical_intent_route(MATH_ROUTE) == MATH_ROUTE
    with pytest.raises(RuntimeError, match="unknown_id"):
        validate_mathematical_intent_route("caller_supplied_route")
    with pytest.raises(RuntimeError, match="unknown_id"):
        validate_mathematical_intent_route(
            {"owner_skill": "computational-optimization"}
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "skill",
    ("algorithm-proof-exploration", "lean-algorithm-design", "formal-proof-workflow"),
)
def test_proof_skills_do_not_imply_math_route(skill: str) -> None:
    """Proof and theorem infrastructure selection alone is not math intent."""
    assert math_intent_route_id_from_context((skill,)) is None


@pytest.mark.parametrize(
    "skill",
    ("algorithm-proof-exploration", "lean-algorithm-design", "formal-proof-workflow"),
)
def test_explicit_math_route_with_proof_skill_resolves_canonical_route(
    skill: str,
) -> None:
    """An explicit canonical math route overrides proof-skill ambiguity."""
    assert (
        math_intent_route_id_from_context(
            (skill,),
            explicit_route_id=MATH_ROUTE,
        )
        == MATH_ROUTE
    )


def test_packet_missing_field_stops() -> None:
    """Missing math evidence cannot be inferred at the packet boundary."""
    value = packet()
    del value["equation_to_code_map"]
    with pytest.raises(RuntimeError, match="field_missing:equation_to_code_map"):
        normalize_mathematical_intent_packet(value)


def test_packet_rejects_unmapped_equation_code_path() -> None:
    """Every mapped code path must be inside the declared math write set."""
    value = packet()
    value["equation_to_code_map"] = [
        {
            "equation": "f(x)=0",
            "code_path": "src/other.py",
            "symbol_or_call_path": "newton_step",
        }
    ]
    with pytest.raises(RuntimeError, match="union_mismatch"):
        normalize_mathematical_intent_packet(value)


def test_packet_rejects_extra_or_missing_allowed_write_path() -> None:
    """The writer whitelist is exactly the explicit mathematical path union."""
    extra = packet()
    extra["allowed_write_paths"] = [
        "src/solver.py",
        "tests/math_oracle.py",
        "documents/math.md",
        "src/extra.py",
    ]
    with pytest.raises(RuntimeError, match="union_mismatch:extra=src/extra.py"):
        normalize_mathematical_intent_packet(extra)

    missing = packet()
    missing["allowed_write_paths"] = ["src/solver.py", "documents/math.md"]
    with pytest.raises(
        RuntimeError, match="union_mismatch:missing=tests/math_oracle.py"
    ):
        normalize_mathematical_intent_packet(missing)


def test_spawn_requires_packet_and_rejects_non_math_writer_path() -> None:
    """Math spawn admission requires the packet and keeps infra out of its target."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        writer = target(root)
        with pytest.raises(RuntimeError, match="math_packet_missing"):
            materialize_subagent_spawn_tool_call(
                role="implementer",
                agent_type="worker",
                input="math task",
                checkout_identity=identity(root),
                writer_target=writer,
                math_intent_route=MATH_ROUTE,
            )
        reviewer_call = materialize_subagent_spawn_tool_call(
            role="mathematical_correctness_reviewer",
            agent_type="reviewer",
            input="non-math review",
            checkout_identity=identity(root),
            workspace_write_capable=False,
        )
        assert "mathematical_intent_packet" not in reviewer_call["arguments"]

        with pytest.raises(ValueError, match="path_not_in_packet"):
            materialize_subagent_spawn_tool_call(
                role="implementer",
                agent_type="worker",
                input="math task",
                checkout_identity=identity(root),
                writer_target=target(root, ("src/runtime_solver.py",)),
                math_intent_route=MATH_ROUTE,
                math_intent_packet=packet(),
            )

        mapped_runtime = packet()
        mapped_runtime["equation_to_code_map"] = [
            {
                "equation": "f(x)=0",
                "code_path": "src/runtime_solver.py",
                "symbol_or_call_path": "newton_step",
            }
        ]
        mapped_runtime["mathematical_definition_paths"] = ["src/runtime_solver.py"]
        mapped_runtime["allowed_write_paths"] = [
            "src/runtime_solver.py",
            "tests/math_oracle.py",
            "documents/math.md",
        ]
        call = materialize_subagent_spawn_tool_call(
            role="implementer",
            agent_type="worker",
            input="math task",
            checkout_identity=identity(root),
            writer_target=target(root, ("src/runtime_solver.py",)),
            math_intent_route=MATH_ROUTE,
            math_intent_packet=mapped_runtime,
        )
        assert call["arguments"]["writer_target"]["allowed_paths"] == [
            "src/runtime_solver.py"
        ]


def test_spawn_carries_valid_packet_and_narrowed_target() -> None:
    """A valid math spawn carries both packet and its mapped writer target."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        call = materialize_subagent_spawn_tool_call(
            role="implementer",
            agent_type="worker",
            input="math task",
            checkout_identity=identity(root),
            writer_target=target(root),
            math_intent_route=MATH_ROUTE,
            math_intent_packet=packet(),
        )
        assert (
            call["arguments"]["mathematical_intent_packet"]["schema"]
            == MATHEMATICAL_INTENT_PACKET_SCHEMA
        )
        assert call["arguments"]["writer_target"]["allowed_paths"] == ["src/solver.py"]
