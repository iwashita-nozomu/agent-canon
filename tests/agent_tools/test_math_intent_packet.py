# @dependency-start
# contract test
# responsibility Tests mathematical-intent packet normalization, bootstrap admission, and spawn scope.
# upstream implementation ../../tools/agent_tools/packets.py owns packet normalization and manifest identity
# upstream implementation ../../tools/agent_tools/bootstrap_agent_run.py owns normal run admission
# upstream implementation ../../tools/agent_tools/tool_calls.py owns spawn ToolCall admission
# upstream implementation ../../tools/agent_tools/writer_target.py owns math writer target narrowing
# @dependency-end

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS))

from packets import (  # noqa: E402
    MATHEMATICAL_INTENT_PACKET_SCHEMA,
    mathematical_intent_packet_mapping,
    normalize_mathematical_intent_packet,
    validate_mathematical_intent_route,
)
from tool_calls import materialize_subagent_spawn_tool_call  # noqa: E402
from implementation_dispatch import dispatch_subagent_wave  # noqa: E402
from team_config import SubagentWaveSlot  # noqa: E402
from writer_target import WriterTarget  # noqa: E402


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
    assert mathematical_intent_packet_mapping(normalized)["schema"] == MATHEMATICAL_INTENT_PACKET_SCHEMA
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
        validate_mathematical_intent_route({"owner_skill": "computational-optimization"})  # type: ignore[arg-type]


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
    with pytest.raises(RuntimeError, match="union_mismatch:missing=tests/math_oracle.py"):
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
        with pytest.raises(RuntimeError, match="math_packet_missing"):
            materialize_subagent_spawn_tool_call(
                role="mathematical_correctness_reviewer",
                agent_type="reviewer",
                input="math review",
                checkout_identity=identity(root),
                workspace_write_capable=False,
            )

        with pytest.raises(ValueError, match="forbidden_surface"):
            materialize_subagent_spawn_tool_call(
                role="implementer",
                agent_type="worker",
                input="math task",
                checkout_identity=identity(root),
                writer_target=target(root, ("src/runtime_solver.py",)),
                math_intent_route=MATH_ROUTE,
                math_intent_packet=packet(),
            )


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
        assert call["arguments"]["mathematical_intent_packet"]["schema"] == MATHEMATICAL_INTENT_PACKET_SCHEMA
        assert call["arguments"]["writer_target"]["allowed_paths"] == ["src/solver.py"]


def test_wave_blocks_before_callback_without_math_packet() -> None:
    """The normal AgentTeam wave cannot spawn a math writer without its packet."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        slot = SubagentWaveSlot(
            role_id="implementer",
            instance_id="math-worker",
            agent_type="worker",
            write_capable=True,
            writer_target=target(root),
            math_intent_route_id=MATH_ROUTE,
        )
        spawned: list[str] = []
        with pytest.raises(RuntimeError, match="math_packet_missing"):
            dispatch_subagent_wave(
                (slot,),
                {slot.executable_identity: "math task"},
                lambda _agent, _prompt: spawned.append("unexpected") or "agent",
                {slot.executable_identity: target(root)},
            )
        assert spawned == []


def test_math_wave_emits_separate_nonmath_handoff_without_arch_writer() -> None:
    """A JIT-looking symptom stays a deferred handoff beside math-only writers."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        worker = SubagentWaveSlot(
            role_id="implementer",
            instance_id="math-worker",
            agent_type="worker",
            write_capable=True,
            writer_target=target(root),
            math_intent_route_id=MATH_ROUTE,
        )
        reviewer = SubagentWaveSlot(
            role_id="mathematical_correctness_reviewer",
            instance_id="math-reviewer",
            agent_type="reviewer",
            write_capable=False,
        )
        prompts = {
            worker.executable_identity: "convergence math worker",
            reviewer.executable_identity: "convergence math review",
        }
        spawned: list[str] = []
        handoffs: list[Mapping[str, object]] = []
        result = dispatch_subagent_wave(
            (worker, reviewer),
            prompts,
            lambda agent, _prompt: spawned.append(agent) or agent,
            {worker.executable_identity: target(root)},
            math_intent_packet=packet(
                separate_handoff_targets=["architecture/JIT performance owner"]
            ),
            nonmath_handoff=handoffs.append,
        )
        assert result == ("worker", "reviewer")
        assert spawned == ["worker", "reviewer"]
        assert handoffs == [
            {
                "target": "architecture/JIT performance owner",
                "owner": "parent",
                "status": "deferred",
                "writer_tool_call": "none",
                "math_writer_paths": [],
            }
        ]


def run_bootstrap(*args: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run normal bootstrap against an external temporary runtime root."""
    runtime = Path(tempfile.mkdtemp(prefix="math-intent-runtime-"))
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS / "bootstrap_agent_run.py"),
            "--owner",
            "test",
            "--runtime-root",
            str(runtime),
            "--workspace-root",
            str(PROJECT_ROOT),
            "--skip-agent-canon-preflight",
            "--no-language-review-candidates",
            *args,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    report_dir = next(
        (
            Path(line.split("=", 1)[1])
            for line in result.stdout.splitlines()
            if line.startswith("REPORT_DIR=")
        ),
        runtime / "reports" / "agents",
    )
    return result, report_dir


def test_normal_math_bootstrap_requires_packet_before_run() -> None:
    """T4 math evidence blocks before a run can spawn without its packet."""
    result, runtime = run_bootstrap(
        "--task",
        "修正 solver residual の収束と更新式",
        "--task-id",
        "T4",
    )
    assert result.returncode == 2
    assert "math_packet_missing" in result.stdout
    shutil.rmtree(runtime.parents[2] if runtime.exists() else runtime.parents[1])


def test_normal_math_bootstrap_materializes_packet_and_reviewer() -> None:
    """A complete T4 packet activates the math reviewer and manifest route."""
    result, report_dir = run_bootstrap(
        "--task",
        "修正 solver residual の収束と実行速度。JIT 境界は症状だが変更しない",
        "--task-id",
        "T4",
        "--math-intent-packet",
        json.dumps(
            packet(separate_handoff_targets=["architecture/JIT owner"])
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATH_INTENT_ROUTE_STATUS=active" in result.stdout
    assert "MATH_INTENT_REVIEWER=mathematical_correctness_reviewer" in result.stdout
    manifest = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
    assert "mathematical_intent_packet:" in manifest
    assert "mathematical_correctness_reviewer" in manifest
    assert "architecture/JIT owner" in manifest
    assert "math_intent_write_scope: mapped_allowed_paths_only" in manifest
    assert "math_intent_forbidden_surfaces:" in manifest
    shutil.rmtree(report_dir.parents[2])


def test_normal_non_math_t4_bootstrap_does_not_require_packet() -> None:
    """The conditional route stays absent for an infrastructure-only T4 task."""
    result, runtime = run_bootstrap(
        "--task",
        "修正 Docker build cache とコンテナ起動",
        "--task-id",
        "T4",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATH_INTENT_ROUTE_STATUS=not_applicable" in result.stdout
    assert "mathematical_correctness_reviewer" not in result.stdout
    shutil.rmtree(runtime.parents[2])
