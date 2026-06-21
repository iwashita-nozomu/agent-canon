"""Tests for JIT-canonical IR extraction and backend runtime routing."""

# @dependency-start
# contract test
# responsibility Tests JIT-canonical IR extraction and backend trace capture.
# upstream implementation ../../tools/agent_tools/jit_canonical_ir.py extracts StableHLO-derived IR.
# upstream design ../../documents/tools/jit_canonical_ir.md defines the extraction contract.
# upstream design ../../documents/tools/jit_ir_to_lean.md defines the Lean evidence boundary.
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Protocol, cast

import pytest


class _JitToolModule(Protocol):
    subprocess: types.ModuleType

    def resolve_runtime_backend_config(
        self,
        *,
        include_backend_trace: bool,
    ) -> object: ...

    def resolve_cuda_visible_devices(self, requested: str | None) -> str: ...


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _jit_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env


def _load_jit_tool_module() -> _JitToolModule:
    tool_path = Path(__file__).resolve().parents[2] / "tools/agent_tools/jit_canonical_ir.py"
    spec = importlib.util.spec_from_file_location("_agent_canon_test_jit_tool", tool_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(_JitToolModule, module)


def test_jit_canonical_ir_extracts_stablehlo_and_backend_trace(tmp_path: Path) -> None:
    """JIT IR extraction records StableHLO, public roots, and backend trace."""
    root = tmp_path / "jit_root.py"
    root.write_text(
        "\n".join(
            [
                "import jax.numpy as jnp",
                "",
                "def main(x):",
                "    return x * x + jnp.asarray(1.0, dtype=x.dtype)",
                "",
                "def example_inputs():",
                "    return (jnp.ones((2,), dtype=jnp.float32),), {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "ir.json"
    stablehlo = tmp_path / "root.stablehlo.mlir"
    backend_trace = tmp_path / "backend.json"
    backend_dir = tmp_path / "backend"
    subprocess.run(
        [
            sys.executable,
            "vendor/agent-canon/tools/agent_tools/jit_canonical_ir.py",
            "--python-symbol",
            f"{root}::main",
            "--input-factory",
            f"{root}::example_inputs",
            "--backend-trace-dir",
            str(backend_dir),
            "--out",
            str(out),
            "--stablehlo-out",
            str(stablehlo),
            "--backend-trace-out",
            str(backend_trace),
        ],
        cwd=_repo_root(),
        env=_jit_env(
            AGENT_CANON_JIT_JAX_PLATFORM="cpu",
            AGENT_CANON_JIT_BACKEND_TARGET="llvm-cpu",
        ),
        check=True,
    )

    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["schema"] == "agent-canon.jit-canonical-ir.v1"
    assert record["source_root"]["schema"] == "agent-canon.source-root.v1"
    assert record["source_root"]["python_symbol"] == f"{root}::main"
    assert record["source_root"]["parameters"] == ["x"]
    assert record["source_root"]["main_pattern"] is None
    assert record["public_interface"]["schema"] == "agent-canon.public-interface.v1"
    assert record["public_interface"]["argument_roots"][0]["name"] == "x"
    assert record["public_interface"]["coverage"]["argument_root_count"] == 1
    assert record["public_interface"]["coverage"]["return_leaf_count"] == 1
    assert record["public_interface"]["return_leaves"][0]["path"] == "return_0"
    assert record["stablehlo"]["sha256"]
    assert stablehlo.read_text(encoding="utf-8").count("f64") == 0
    kinds = {op["kind"] for op in record["operational_ir"]["ops"]}
    assert {"Function", "Primitive", "Return"}.issubset(kinds)
    assert record["backend_trace"]["schema"] == "agent-canon.typed-backend-trace.v1"
    assert record["backend_trace"]["coverage"] in {
        "generated_with_llvm",
        "generated_without_llvm_text",
        "phase_trace_until_flow_llvm_compile_failed",
        "phase_trace_until_stream_llvm_compile_failed",
        "phase_trace_until_executable-sources_llvm_compile_failed",
        "compiler_unavailable",
    }
    if shutil.which("iree-compile") is not None:
        assert record["backend_trace"]["compile_attempts"]
        assert record["backend_trace"]["coverage"] == "generated_with_llvm"
        assert record["backend_trace"]["llvm_ir"]
        llvm_modules = record["backend_trace"]["llvm_ir"]
        assert any(module["functions"] for module in llvm_modules)
        assert any(
            function["instructions"]
            for module in llvm_modules
            for function in module["functions"]
        )
        assert all(
            "instruction_id" in instruction
            for module in llvm_modules
            for function in module["functions"]
            for instruction in function["instructions"]
        )


def test_jit_canonical_ir_records_recursive_control_regions(tmp_path: Path) -> None:
    """Control-flow lowering records recursive region and expansion edges."""
    root = tmp_path / "while_root.py"
    root.write_text(
        "\n".join(
            [
                "import jax",
                "import jax.numpy as jnp",
                "",
                "def main(x):",
                "    def cond(carry):",
                "        i, y = carry",
                "        return i < 3",
                "",
                "    def body(carry):",
                "        i, y = carry",
                "        return i + 1, y + x",
                "",
                "    return jax.lax.while_loop(",
                "        cond,",
                "        body,",
                "        (jnp.asarray(0, dtype=jnp.int32), x),",
                "    )[1]",
                "",
                "def example_inputs():",
                "    return (jnp.ones((2,), dtype=jnp.float32),), {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "ir.json"
    subprocess.run(
        [
            sys.executable,
            "vendor/agent-canon/tools/agent_tools/jit_canonical_ir.py",
            "--python-symbol",
            f"{root}::main",
            "--input-factory",
            f"{root}::example_inputs",
            "--no-source-root",
            "--no-backend-trace",
            "--out",
            str(out),
        ],
        cwd=_repo_root(),
        env=_jit_env(AGENT_CANON_JIT_JAX_PLATFORM="cpu"),
        check=True,
    )

    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["source_root"]["status"] == "hlo_only"
    assert record["source_root"]["main_pattern"] is None
    assert record["public_interface"]["argument_roots"][0]["name"] == "x"
    assert record["public_interface"]["coverage"]["return_leaf_count"] == 1
    assert record["public_interface"]["return_leaves"][0]["root_name"] == "return_0"
    assert "backend_trace" not in record
    assert "backend_environment" not in record
    operational_ir = record["operational_ir"]
    assert operational_ir["schema"] == "agent-canon.thin-operational-ir.v2"
    assert operational_ir["coverage"]["unassigned_op_count"] == 0
    assert operational_ir["coverage"]["while_count"] >= 1
    assert operational_ir["coverage"]["region_count"] >= 3
    edge_kinds = {edge["kind"] for edge in operational_ir["expansion_edges"]}
    assert {"function_body", "while_cond", "while_do"}.issubset(edge_kinds)
    region_kinds = {region["kind"] for region in operational_ir["regions"]}
    assert {"module", "function_body", "while_cond", "while_do"}.issubset(region_kinds)
    assert all(op["region_id"] for op in operational_ir["ops"])


def test_jit_canonical_ir_extracts_answer_state_info_public_return(tmp_path: Path) -> None:
    """Answer/state/info tuple returns keep named public return leaves."""
    root = tmp_path / "asi_root.py"
    root.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import equinox as eqx",
                "import jax",
                "import jax.numpy as jnp",
                "",
                "class Problem(eqx.Module):",
                "    x: jax.Array",
                "",
                "class InitializeConfig(eqx.Module):",
                "    shift: jax.Array",
                "",
                "class Answer(eqx.Module):",
                "    objective_value: jax.Array",
                "    status: jax.Array",
                "",
                "class State(eqx.Module):",
                "    solver_x0: jax.Array",
                "    x: jax.Array",
                "",
                "class Info(eqx.Module):",
                "    step_count: jax.Array",
                "    ipm_res_final: jax.Array",
                "",
                "def main(",
                "    problem: Problem,",
                "    initialize_config: InitializeConfig,",
                ") -> tuple[Answer, State, Info]:",
                "    x = problem.x + initialize_config.shift",
                "    answer = Answer(",
                "        objective_value=jnp.sum(x),",
                "        status=jnp.asarray(0, dtype=jnp.int32),",
                "    )",
                "    state = State(solver_x0=initialize_config.shift, x=x)",
                "    info = Info(",
                "        step_count=jnp.asarray(1, dtype=jnp.int32),",
                "        ipm_res_final=jnp.max(jnp.abs(x)),",
                "    )",
                "    return answer, state, info",
                "",
                "def example_inputs():",
                "    return (",
                "        Problem(jnp.ones((2,), dtype=jnp.float32)),",
                "        InitializeConfig(jnp.ones((2,), dtype=jnp.float32)),",
                "    ), {}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "ir.json"
    subprocess.run(
        [
            sys.executable,
            "vendor/agent-canon/tools/agent_tools/jit_canonical_ir.py",
            "--python-symbol",
            f"{root}::main",
            "--input-factory",
            f"{root}::example_inputs",
            "--no-source-root",
            "--no-backend-trace",
            "--out",
            str(out),
        ],
        cwd=_repo_root(),
        env=_jit_env(AGENT_CANON_JIT_JAX_PLATFORM="cpu"),
        check=True,
    )

    record = json.loads(out.read_text(encoding="utf-8"))
    public_interface = record["public_interface"]
    assert public_interface["coverage"]["has_answer_state_info_return"] is True
    assert [
        root["label"] for root in public_interface["return_roots"]
    ] == ["answer", "state", "info"]
    assert [
        leaf["path"]
        for leaf in public_interface["return_leaves"]
        if leaf["root_name"] == "answer"
    ] == ["answer.objective_value", "answer.status"]
    assert [
        leaf["path"]
        for leaf in public_interface["return_leaves"]
        if leaf["root_name"] == "state"
    ] == ["state.solver_x0", "state.x"]
    assert [
        leaf["path"]
        for leaf in public_interface["return_leaves"]
        if leaf["root_name"] == "info"
    ] == ["info.step_count", "info.ipm_res_final"]


def test_jit_runtime_backend_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backend config resolution requires the explicit JIT platform env var."""
    tool = _load_jit_tool_module()
    monkeypatch.delenv("AGENT_CANON_JIT_JAX_PLATFORM", raising=False)

    with pytest.raises(SystemExit, match="backend_env_missing=AGENT_CANON_JIT_JAX_PLATFORM"):
        tool.resolve_runtime_backend_config(include_backend_trace=False)


def test_jit_gpu_platform_selects_open_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """GPU platform routing selects an idle visible device slot."""
    tool = _load_jit_tool_module()
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("NVIDIA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("AGENT_CANON_JIT_CUDA_VISIBLE_DEVICES", raising=False)

    def fake_run(
        command: list[str],
        *,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert command[0] == "nvidia-smi"
        assert text is True
        assert capture_output is True
        assert check is False
        assert timeout == 5
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="0, 2048, 80\n1, 0, 0\n",
            stderr="",
        )

    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    assert tool.resolve_cuda_visible_devices(None) == "1"
