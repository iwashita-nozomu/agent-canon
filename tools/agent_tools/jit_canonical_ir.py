#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Extracts JIT-canonical operational IR and backend witnesses from a lowered Python root.
# upstream design ../../documents/tools/jit_canonical_ir.md defines StableHLO/backend witness extraction.
# downstream implementation ../../rust/agent-canon/src/jit_ir_to_lean.rs lowers this JSON into Lean defs.
# downstream implementation ../../tests/agent_tools/test_jit_canonical_ir.py validates the schema on a tiny JAX root.
# @dependency-end
"""Extract a thin operational IR from a JIT-lowered Python root."""

from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

_OP_RE = re.compile(r"\b(?:stablehlo|mhlo|chlo|func|scf|arith)\.[A-Za-z0-9_]+|\breturn\b|\bcall\b")
_TENSOR_RE = re.compile(r"tensor<([^>]+)>")
_DTYPE_RE = re.compile(r"\b(?:bf16|f16|f32|f64|i1|i8|i16|i32|i64|ui8|ui16|ui32|ui64)\b")
_FUNC_NAME_RE = re.compile(r"\bfunc\.func(?:\s+public|\s+private)?\s+@(?P<name>[-A-Za-z0-9_.$]+)")
_CALL_TARGET_RE = re.compile(r"@(?P<name>[-A-Za-z0-9_.$]+)")
_STABLEHLO_ARG_RE = re.compile(r"%arg(?P<index>\d+):\s*(?P<type>tensor<[^>]+>)")
_STABLEHLO_RESULT_INFO_RE = re.compile(
    r"(?P<type>tensor<[^>]+>)\s*\{\s*jax\.result_info\s*=\s*\"(?P<result_info>[^\"]+)\"\s*\}"
)
_RESULT_INDEX_RE = re.compile(r"\[(?P<index>\d+)\]")
_LLVM_DEFINE_RE = re.compile(r"^define\s+(?P<attrs>.*?)\s*@(?P<name>[^(\s]+)\((?P<params>[^)]*)\)")
_LLVM_LABEL_RE = re.compile(r"^(?P<label>[-A-Za-z0-9_.$]+):(?:\s*;.*)?$")
_LLVM_RESULT_RE = re.compile(r"^(?P<result>%[-A-Za-z0-9_.$]+)\s*=\s*(?P<body>.*)$")
_LLVM_OPCODE_RE = re.compile(
    r"\b(?P<opcode>fadd|fsub|fmul|fdiv|frem|fcmp|select|call|br|phi|load|store|getelementptr|ret)\b(?P<tail>[^;]*)"
)
_MLIR_FAILURE_PASS_RE = re.compile(r"Pipeline failed while executing `(?P<pass_name>[^`]+)`")
_LLVM_FASTMATH_FLAGS = (
    "nnan",
    "ninf",
    "nsz",
    "arcp",
    "contract",
    "afn",
    "reassoc",
    "fast",
)
_LLVM_FLOAT_OPCODES = frozenset({"fadd", "fsub", "fmul", "fdiv", "frem", "fcmp"})
_IREE_PHASES = (
    "input",
    "abi",
    "preprocessing",
    "global-optimization",
    "dispatch-creation",
    "flow",
    "stream",
    "executable-sources",
    "executable-configurations",
    "executable-targets",
    "hal",
    "vm",
)
_PROBLEM_ASSUMPTION_ATTR = "__agent_canon_problem_assumptions__"
ENV_JIT_JAX_PLATFORM = "AGENT_CANON_JIT_JAX_PLATFORM"
ENV_JIT_BACKEND_TARGET = "AGENT_CANON_JIT_BACKEND_TARGET"
ENV_JIT_INPUT_DEVICE = "AGENT_CANON_JIT_INPUT_DEVICE"
ENV_JIT_CUDA_VISIBLE_DEVICES = "AGENT_CANON_JIT_CUDA_VISIBLE_DEVICES"
ENV_JIT_IREE_CUDA_TARGET = "AGENT_CANON_JIT_IREE_CUDA_TARGET"
ENV_GPU_SLOT_MAX_MEMORY_MIB = "AGENT_CANON_GPU_SLOT_MAX_MEMORY_MIB"
ENV_GPU_SLOT_MAX_UTILIZATION_PERCENT = "AGENT_CANON_GPU_SLOT_MAX_UTILIZATION_PERCENT"
_GPU_PLATFORM_NAMES = frozenset({"cuda", "gpu"})
_LLVM_DIS_CANDIDATES = (
    "llvm-dis",
    "llvm-dis-23",
    "llvm-dis-22",
    "llvm-dis-21",
    "llvm-dis-20",
    "llvm-dis-19",
    "llvm-dis-18",
    "llvm-dis-17",
    "llvm-dis-16",
    "llvm-dis-15",
    "llvm-dis-14",
)


@dataclasses.dataclass(frozen=True)
class _RuntimeBackendConfig:
    jax_platform: str
    input_device: str | None
    backend_target: str | None
    cuda_visible_devices: str | None
    iree_cuda_target: str | None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_llvm_dis() -> str | None:
    return next(
        (
            path
            for candidate in _LLVM_DIS_CANDIDATES
            if (path := shutil.which(candidate)) is not None
        ),
        None,
    )


def _env_text(name: str, *, keep_empty: bool = False) -> str | None:
    if name not in os.environ:
        return None
    value = os.environ[name].strip()
    if value or keep_empty:
        return value
    return None


def _required_env_text(name: str) -> str:
    value = _env_text(name)
    if value is None:
        raise SystemExit(f"backend_env_missing={name}")
    return value


def _env_int(name: str, default: int) -> int:
    value = _env_text(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"invalid_int_env={name}:{value}") from exc


def _parse_gpu_slot_line(line: str) -> dict[str, int | str] | None:
    cells = [cell.strip() for cell in line.split(",")]
    if len(cells) != 3:
        return None
    try:
        return {
            "index": cells[0],
            "memory_used_mib": int(cells[1]),
            "utilization_percent": int(cells[2]),
        }
    except ValueError:
        return None


def _query_gpu_slots() -> list[dict[str, int | str]]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"gpu_slot_blocker=nvidia_smi_unavailable:{exc}") from exc
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or str(result.returncode)
        raise SystemExit(f"gpu_slot_blocker=nvidia_smi_failed:{reason}")
    slots = [
        slot
        for line in result.stdout.splitlines()
        if (slot := _parse_gpu_slot_line(line)) is not None
    ]
    if not slots:
        raise SystemExit("gpu_slot_blocker=no_parseable_nvidia_smi_slots")
    return slots


def _select_available_gpu_slot() -> str:
    max_memory = _env_int(ENV_GPU_SLOT_MAX_MEMORY_MIB, 256)
    max_utilization = _env_int(ENV_GPU_SLOT_MAX_UTILIZATION_PERCENT, 5)
    for slot in _query_gpu_slots():
        if (
            int(slot["memory_used_mib"]) <= max_memory
            and int(slot["utilization_percent"]) <= max_utilization
        ):
            return str(slot["index"])
    raise SystemExit(
        "gpu_slot_blocker=no_available_slot:"
        f"memory_mib<={max_memory},utilization_percent<={max_utilization}"
    )


def resolve_cuda_visible_devices(requested: str | None) -> str:
    """Return the explicit or selected CUDA slot for a GPU JIT child."""
    standard = _env_text("CUDA_VISIBLE_DEVICES", keep_empty=True)
    agent_value = _env_text(ENV_JIT_CUDA_VISIBLE_DEVICES, keep_empty=True)
    if requested is not None:
        agent_value = requested.strip()
    if standard is not None and agent_value is not None and standard != agent_value:
        raise SystemExit(
            "gpu_slot_blocker=conflicting_cuda_visible_devices:"
            f"CUDA_VISIBLE_DEVICES={standard!r},"
            f"{ENV_JIT_CUDA_VISIBLE_DEVICES}={agent_value!r}"
        )
    selected = standard if standard is not None else agent_value
    if selected is not None:
        if not selected:
            raise SystemExit("gpu_slot_blocker=empty_cuda_visible_devices")
        return selected
    nvidia_visible = _env_text("NVIDIA_VISIBLE_DEVICES")
    if nvidia_visible and nvidia_visible.lower() != "all":
        return nvidia_visible
    return _select_available_gpu_slot()


def resolve_runtime_backend_config(
    *,
    include_backend_trace: bool,
) -> _RuntimeBackendConfig:
    """Read the JIT backend/runtime contract from environment variables."""
    jax_platform = _required_env_text(ENV_JIT_JAX_PLATFORM)
    backend_target = _env_text(ENV_JIT_BACKEND_TARGET)
    if include_backend_trace and backend_target is None:
        raise SystemExit(f"backend_env_missing={ENV_JIT_BACKEND_TARGET}")
    return _RuntimeBackendConfig(
        jax_platform=jax_platform,
        input_device=_env_text(ENV_JIT_INPUT_DEVICE),
        backend_target=backend_target,
        cuda_visible_devices=_env_text(ENV_JIT_CUDA_VISIBLE_DEVICES, keep_empty=True),
        iree_cuda_target=_env_text(ENV_JIT_IREE_CUDA_TARGET),
    )


def _backend_runtime_env_snapshot() -> dict[str, str]:
    names = (
        ENV_JIT_JAX_PLATFORM,
        ENV_JIT_BACKEND_TARGET,
        ENV_JIT_INPUT_DEVICE,
        ENV_JIT_CUDA_VISIBLE_DEVICES,
        ENV_JIT_IREE_CUDA_TARGET,
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "JAX_PLATFORMS",
        "JAX_PLATFORM_NAME",
    )
    return {name: os.environ[name] for name in names if name in os.environ}


def _symbol_path_and_qualname(symbol: str) -> tuple[Path, str]:
    if "::" not in symbol:
        raise SystemExit(f"symbol must be path.py::qualname, got {symbol!r}")
    path_text, qualname = symbol.split("::", 1)
    path = Path(path_text).resolve()
    if not path.exists():
        raise SystemExit(f"symbol path does not exist: {path}")
    return path, qualname


def _load_symbol(symbol: str) -> Callable[..., object]:
    path, qualname = _symbol_path_and_qualname(symbol)
    module_name = f"_agent_canon_jit_root_{_sha256_text(str(path))[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    value: object = module
    for part in qualname.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise SystemExit(f"resolved symbol is not callable: {symbol}")
    return value


def _find_function_def(tree: ast.AST, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    parts = qualname.split(".")
    current_nodes: Sequence[ast.AST] = [tree]
    for part in parts:
        next_node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None
        for node in current_nodes:
            body = getattr(node, "body", [])
            for child in body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child.name == part:
                    next_node = child
                    break
            if next_node is not None:
                break
        if next_node is None:
            return None
        if part == parts[-1]:
            if isinstance(next_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return next_node
            return None
        current_nodes = [next_node]
    return None


def _expr_to_source(source_text: str, expr: ast.AST | None) -> str:
    if expr is None:
        return ""
    segment = ast.get_source_segment(source_text, expr)
    if segment is not None:
        return segment.strip()
    try:
        return ast.unparse(expr)
    except Exception:
        return expr.__class__.__name__


def _call_name(expr: ast.AST) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        prefix = _call_name(expr.value)
        return f"{prefix}.{expr.attr}" if prefix else expr.attr
    if isinstance(expr, ast.Call):
        return _call_name(expr.func)
    return ""


def _target_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_target_names(item))
        return names
    return []


def _literal_value(source_text: str, expr: ast.AST) -> str | int:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, (str, int)):
        return expr.value
    return _expr_to_source(source_text, expr)


def _keyword_map(source_text: str, call: ast.Call) -> dict[str, str | int]:
    values: dict[str, str | int] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        values[keyword.arg] = _literal_value(source_text, keyword.value)
    return values


def _detect_source_main_pattern(
    source_text: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, object] | None:
    initialize_assign: dict[str, object] | None = None
    algorithm_call_assign: dict[str, object] | None = None
    returned: list[str] | None = None
    for statement in function.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            assigned = _target_names(statement.targets[0])
            value = statement.value
            if isinstance(value, ast.Call) and _call_name(value.func).endswith(".initialize"):
                initialize_assign = {
                    "assigned": assigned,
                    "callee": _call_name(value.func),
                    "args": [_expr_to_source(source_text, arg) for arg in value.args],
                }
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                solve_config: dict[str, object] = {}
                for arg in value.args:
                    if isinstance(arg, ast.Name) and arg.id == "solve_config":
                        solve_config = {
                            "source": "parameter",
                            "name": arg.id,
                        }
                    elif isinstance(arg, ast.Call) and _call_name(arg.func).endswith(".SolveConfig"):
                        solve_config = {
                            "constructor": _call_name(arg.func),
                            "keywords": _keyword_map(source_text, arg),
                        }
                        for keyword in arg.keywords:
                            if keyword.arg == "stopping" and isinstance(keyword.value, ast.Call):
                                solve_config["stopping_constructor"] = _call_name(keyword.value.func)
                                solve_config["stopping_keywords"] = _keyword_map(source_text, keyword.value)
                    else:
                        pass
                if solve_config:
                    algorithm_call_assign = {
                        "assigned": assigned,
                        "callee": value.func.id,
                        "args": [_expr_to_source(source_text, arg) for arg in value.args],
                        "solve_config": solve_config,
                    }
        if isinstance(statement, ast.Return):
            returned = _target_names(statement.value) if statement.value is not None else []
    if initialize_assign is None or algorithm_call_assign is None or returned is None:
        return None
    return {
        "pattern": "initialize_then_algorithm_call_return_tuple",
        "initialize": initialize_assign,
        "algorithm_call": algorithm_call_assign,
        "return": returned,
    }


def _extract_source_root(symbol: str) -> dict[str, object]:
    path, qualname = _symbol_path_and_qualname(symbol)
    source_text = path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    function = _find_function_def(tree, qualname)
    if function is None:
        return {
            "schema": "agent-canon.source-root.v1",
            "python_symbol": symbol,
            "path": str(path),
            "qualname": qualname,
            "status": "function_not_found",
        }
    source_segment = ast.get_source_segment(source_text, function) or ""
    parameters = [arg.arg for arg in function.args.args]
    return {
        "schema": "agent-canon.source-root.v1",
        "python_symbol": symbol,
        "path": str(path),
        "qualname": qualname,
        "name": function.name,
        "parameters": parameters,
        "return_annotation": _expr_to_source(source_text, function.returns),
        "source_sha256": _sha256_text(source_segment),
        "body_statement_count": len(function.body),
        "main_pattern": _detect_source_main_pattern(source_text, function),
    }


def _hlo_only_source_root(symbol: str) -> dict[str, object]:
    path, qualname = _symbol_path_and_qualname(symbol)
    return {
        "schema": "agent-canon.source-root.v1",
        "status": "hlo_only",
        "python_symbol": symbol,
        "path": str(path),
        "qualname": qualname,
        "name": qualname.rsplit(".", maxsplit=1)[-1],
        "parameters": [],
        "return_annotation": "",
        "source_sha256": "",
        "body_statement_count": 0,
        "main_pattern": None,
    }


def _extract_public_source_signature(symbol: str) -> dict[str, object]:
    path, qualname = _symbol_path_and_qualname(symbol)
    source_text = path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    function = _find_function_def(tree, qualname)
    if function is None:
        return {
            "schema": "agent-canon.public-source-signature.v1",
            "status": "function_not_found",
            "python_symbol": symbol,
            "path": str(path),
            "qualname": qualname,
            "name": qualname.rsplit(".", maxsplit=1)[-1],
            "parameters": [],
            "return_annotation": "",
        }
    return {
        "schema": "agent-canon.public-source-signature.v1",
        "status": "ok",
        "python_symbol": symbol,
        "path": str(path),
        "qualname": qualname,
        "name": function.name,
        "parameters": [
            {
                "index": index,
                "name": arg.arg,
                "annotation": _expr_to_source(source_text, arg.annotation),
            }
            for index, arg in enumerate(function.args.args)
        ],
        "return_annotation": _expr_to_source(source_text, function.returns),
    }


def _split_top_level_csv(text: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    pairs = {"[": "]", "(": ")", "{": "}"}
    closing = set(pairs.values())
    for index, ch in enumerate(text):
        if ch in pairs:
            depth += 1
        elif ch in closing and depth > 0:
            depth -= 1
        elif ch == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
    tail = text[start:].strip()
    if tail:
        items.append(tail)
    return items


def _return_roots_from_annotation(return_annotation: str) -> list[dict[str, object]]:
    annotation = return_annotation.strip()
    if annotation.startswith("tuple[") and annotation.endswith("]"):
        parts = _split_top_level_csv(annotation[len("tuple[") : -1])
    elif annotation.startswith("Tuple[") and annotation.endswith("]"):
        parts = _split_top_level_csv(annotation[len("Tuple[") : -1])
    else:
        parts = [annotation] if annotation else []
    roots: list[dict[str, object]] = []
    for index, part in enumerate(parts):
        class_name = part.rsplit(".", maxsplit=1)[-1].split("[", maxsplit=1)[0].strip()
        label = class_name[:1].lower() + class_name[1:] if class_name else f"return_{index}"
        roots.append(
            {
                "index": index,
                "label": label,
                "annotation": part,
                "path": f"result[{index}]",
            }
        )
    return roots


def _shape_text(value: object) -> str:
    shape = getattr(value, "shape", None)
    if shape is None:
        return ""
    return str(tuple(int(dim) for dim in shape))


def _dtype_text(value: object) -> str:
    dtype = getattr(value, "dtype", None)
    return "" if dtype is None else str(dtype)


def _tree_key_text(path: object) -> str:
    import jax

    return jax.tree_util.keystr(path)


def _collect_tree_leaves(root_name: str, root_index: int, value: object) -> list[dict[str, object]]:
    import jax

    leaves: list[dict[str, object]] = []
    for leaf_index, (path, leaf) in enumerate(jax.tree_util.tree_flatten_with_path(value)[0]):
        local_path = _tree_key_text(path)
        public_path = f"{root_name}{local_path}" if local_path else root_name
        leaves.append(
            {
                "leaf_index": leaf_index,
                "root_index": root_index,
                "root_name": root_name,
                "path": public_path,
                "local_path": local_path,
                "python_type": type(leaf).__name__,
                "shape": _shape_text(leaf),
                "dtype": _dtype_text(leaf),
            }
        )
    return leaves

def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _collect_problem_assumption_objects(
    root_name: str,
    root_index: int,
    value: object,
) -> list[dict[str, object]]:
    import jax

    def is_assumption_object(node: object) -> bool:
        return hasattr(node, _PROBLEM_ASSUMPTION_ATTR)

    records: list[dict[str, object]] = []
    leaves, _treedef = jax.tree_util.tree_flatten_with_path(value, is_leaf=is_assumption_object)
    for assumption_index, (path, leaf) in enumerate(leaves):
        if not is_assumption_object(leaf):
            continue
        local_path = _tree_key_text(path)
        public_path = f"{root_name}{local_path}" if local_path else root_name
        records.append(
            {
                "assumption_index": assumption_index,
                "root_index": root_index,
                "root_name": root_name,
                "path": public_path,
                "local_path": local_path,
                "python_type": type(leaf).__name__,
                "metadata": _json_safe(getattr(leaf, _PROBLEM_ASSUMPTION_ATTR)),
            }
        )
    return records


def _eval_shape(
    func: Callable[..., object],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> object:
    try:
        import equinox as eqx

        return eqx.filter_eval_shape(func, *args, **kwargs)
    except Exception:
        import jax

        return jax.eval_shape(func, *args, **kwargs)


def _entry_signature(operational_ir: Mapping[str, object], root_name: str) -> str:
    signatures = operational_ir.get("function_signatures", [])
    if not isinstance(signatures, list):
        return ""
    public_candidates = [
        str(signature)
        for signature in signatures
        if f"public @{root_name}" in str(signature) or f"@{root_name}(" in str(signature)
    ]
    return public_candidates[0] if public_candidates else (str(signatures[0]) if signatures else "")


def _parse_stablehlo_entry_signature(signature: str) -> dict[str, object]:
    arguments = [
        {
            "index": int(match.group("index")),
            "name": f"arg{match.group('index')}",
            "stablehlo_type": match.group("type"),
        }
        for match in _STABLEHLO_ARG_RE.finditer(signature)
    ]
    returns: list[dict[str, object]] = []
    for leaf_index, match in enumerate(_STABLEHLO_RESULT_INFO_RE.finditer(signature)):
        result_info = match.group("result_info")
        indexes = [int(item.group("index")) for item in _RESULT_INDEX_RE.finditer(result_info)]
        returns.append(
            {
                "leaf_index": leaf_index,
                "result_info": result_info,
                "stablehlo_type": match.group("type"),
                "result_indexes": indexes,
            }
        )
    return {
        "signature": signature,
        "arguments": arguments,
        "return_leaves": returns,
    }


def _collect_public_interface(
    *,
    python_symbol: str,
    func: Callable[..., object],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    operational_ir: Mapping[str, object],
) -> dict[str, object]:
    signature = _extract_public_source_signature(python_symbol)
    parameters = signature.get("parameters", [])
    parameter_names = [
        str(parameter.get("name", f"arg{index}"))
        for index, parameter in enumerate(parameters)
        if isinstance(parameter, Mapping)
    ]
    argument_leaves: list[dict[str, object]] = []
    problem_assumptions: list[dict[str, object]] = []
    for index, arg in enumerate(args):
        name = parameter_names[index] if index < len(parameter_names) else f"arg{index}"
        argument_leaves.extend(_collect_tree_leaves(name, index, arg))
        problem_assumptions.extend(_collect_problem_assumption_objects(name, index, arg))
    for offset, (name, value) in enumerate(sorted(kwargs.items())):
        argument_leaves.extend(_collect_tree_leaves(str(name), len(args) + offset, value))
        problem_assumptions.extend(
            _collect_problem_assumption_objects(str(name), len(args) + offset, value)
        )

    output_shape = _eval_shape(func, args, kwargs)
    output_roots = output_shape if isinstance(output_shape, tuple) else (output_shape,)
    return_roots = _return_roots_from_annotation(str(signature.get("return_annotation", "")))
    if not return_roots:
        return_roots = [
            {
                "index": index,
                "label": f"return_{index}",
                "annotation": "",
                "path": f"result[{index}]",
            }
            for index, _root in enumerate(output_roots)
        ]
    return_leaves: list[dict[str, object]] = []
    for root_index, root in enumerate(output_roots):
        root_label = (
            str(return_roots[root_index]["label"])
            if root_index < len(return_roots)
            else f"return_{root_index}"
        )
        return_leaves.extend(_collect_tree_leaves(root_label, root_index, root))

    root_name = str(signature.get("name") or python_symbol.rsplit("::", maxsplit=1)[-1])
    stablehlo_entry = _parse_stablehlo_entry_signature(
        _entry_signature(operational_ir, root_name)
    )
    return {
        "schema": "agent-canon.public-interface.v1",
        "python_symbol": python_symbol,
        "source_signature": signature,
        "argument_roots": parameters,
        "argument_leaves": argument_leaves,
        "return_annotation": signature.get("return_annotation", ""),
        "return_roots": return_roots,
        "return_leaves": return_leaves,
        "problem_assumptions": problem_assumptions,
        "stablehlo_entry": stablehlo_entry,
        "coverage": {
            "argument_root_count": len(parameters),
            "argument_leaf_count": len(argument_leaves),
            "return_root_count": len(return_roots),
            "return_leaf_count": len(return_leaves),
            "stablehlo_argument_count": len(stablehlo_entry["arguments"]),
            "stablehlo_return_leaf_count": len(stablehlo_entry["return_leaves"]),
            "problem_assumption_count": len(problem_assumptions),
            "has_answer_state_info_return": [
                root.get("label") for root in return_roots
            ] == ["answer", "state", "info"],
        },
    }


def _configure_jax_platform(
    platform_name: str | None,
    *,
    cuda_visible_devices: str | None,
    xla_flags: str | None,
    xla_dump_dir: Path | None,
) -> None:
    if "jax" in sys.modules or "jaxlib" in sys.modules:
        raise SystemExit(f"{ENV_JIT_JAX_PLATFORM} must be set before importing JAX")
    if xla_dump_dir is not None:
        if xla_dump_dir.exists():
            shutil.rmtree(xla_dump_dir)
        xla_dump_dir.mkdir(parents=True, exist_ok=True)
    requested_flags: list[str] = []
    if xla_flags:
        requested_flags.extend(xla_flags.split())
    if xla_dump_dir is not None:
        requested_flags.append(f"--xla_dump_to={xla_dump_dir}")
        requested_flags.append("--xla_dump_hlo_as_text")
        if platform_name in _GPU_PLATFORM_NAMES:
            requested_flags.append("--xla_gpu_dump_llvmir")
    if requested_flags:
        existing = os.environ.get("XLA_FLAGS", "").split()
        merged = [*existing]
        for flag in requested_flags:
            flag_key = flag.split("=", maxsplit=1)[0]
            if any(current.split("=", maxsplit=1)[0] == flag_key for current in merged):
                continue
            merged.append(flag)
        os.environ["XLA_FLAGS"] = " ".join(merged)
    if not platform_name:
        return
    platform_name = platform_name.strip()
    if not platform_name:
        return
    if platform_name == "cpu":
        # StableHLO extraction is a compiler action, not a numerical GPU run.
        # Keep it independent of CUDA device memory by avoiding CUDA discovery.
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        os.environ["JAX_PLATFORMS"] = "cpu"
    if platform_name in _GPU_PLATFORM_NAMES:
        platform_name = "gpu"
        resolved_cuda_visible_devices = resolve_cuda_visible_devices(cuda_visible_devices)
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", resolved_cuda_visible_devices)
        os.environ.setdefault("NVIDIA_VISIBLE_DEVICES", resolved_cuda_visible_devices)
        os.environ.setdefault("XLA_PYTHON_CLIENT_ALLOCATOR", "platform")
        os.environ.setdefault("XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR", "false")
    os.environ["JAX_PLATFORM_NAME"] = platform_name
    os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")


@contextlib.contextmanager
def _jax_default_device(device_kind: str | None) -> object:
    if not device_kind:
        yield
        return
    import jax

    devices = jax.devices(device_kind)
    if not devices:
        raise RuntimeError(f"No JAX devices for input device kind: {device_kind}")
    with jax.default_device(devices[0]):
        yield


def _normalize_inputs(value: object) -> tuple[tuple[object, ...], Mapping[str, object]]:
    if isinstance(value, Mapping):
        args_value = value.get("args", ())
        kwargs_value = value.get("kwargs", {})
        return tuple(args_value), dict(kwargs_value)
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], Mapping):
        return tuple(value[0]), dict(value[1])
    if isinstance(value, tuple):
        return value, {}
    if isinstance(value, list):
        return tuple(value), {}
    return (value,), {}

def _is_lower_dynamic_leaf(value: object) -> bool:
    import equinox as eqx
    import jax

    return eqx.is_array(value) or isinstance(value, jax.ShapeDtypeStruct)


def _has_abstract_dynamic_leaf(value: object) -> bool:
    import jax

    return any(isinstance(leaf, jax.ShapeDtypeStruct) for leaf in jax.tree_util.tree_leaves(value))


def _lower_abstract_inputs(
    func: Callable[..., object],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> object:
    import equinox as eqx
    import jax
    import jax.numpy as jnp
    import jax.tree_util as jtu
    from equinox._module import Static

    dynamic, static = eqx.partition((func, args, dict(kwargs)), _is_lower_dynamic_leaf)
    dynamic_flat, dynamic_treedef = jtu.tree_flatten(dynamic)

    def wrapped(*flat_dynamic: object) -> object:
        dynamic_tree = jtu.tree_unflatten(dynamic_treedef, flat_dynamic)
        call_func, call_args, call_kwargs = eqx.combine(dynamic_tree, static)
        out = call_func(*call_args, **call_kwargs)
        dynamic_out, static_out = eqx.partition(out, eqx.is_array)
        return jnp.array(0), dynamic_out, Static(static_out)

    return jax.jit(wrapped).lower(*dynamic_flat)


def _lower(
    func: Callable[..., object],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> object:
    if _has_abstract_dynamic_leaf((args, kwargs)):
        return _lower_abstract_inputs(func, args, kwargs)

    import equinox as eqx

    filter_jitted = eqx.filter_jit(func)
    return filter_jitted.lower(*args, **kwargs)


def _compiler_ir_text(lowered: object) -> tuple[str, str, list[str]]:
    errors: list[str] = []
    compiler_ir = getattr(lowered, "compiler_ir", None)
    if compiler_ir is not None:
        for dialect in ("stablehlo", "hlo"):
            try:
                return dialect, str(compiler_ir(dialect=dialect)), errors
            except Exception as exc:  # pragma: no cover - depends on jaxlib build.
                errors.append(f"{dialect}: {type(exc).__name__}: {exc}")
    as_text = getattr(lowered, "as_text", None)
    if as_text is not None:
        try:
            return "stablehlo", str(as_text()), errors
        except Exception as exc:
            errors.append(f"as_text: {type(exc).__name__}: {exc}")
    raise RuntimeError("failed to obtain compiler IR text: " + "; ".join(errors))


def _classify_opcode(opcode: str) -> str:
    if opcode == "func.func":
        return "Function"
    if opcode == "return":
        return "Return"
    if opcode in {"func.call", "call"}:
        return "Call"
    if opcode in {"stablehlo.while", "mhlo.while", "scf.while"}:
        return "While"
    if opcode in {"stablehlo.if", "mhlo.if", "scf.if"}:
        return "If"
    if opcode in {"stablehlo.case", "mhlo.case"}:
        return "Case"
    if opcode in {"stablehlo.tuple", "mhlo.tuple"}:
        return "Tuple"
    if opcode in {"stablehlo.get_tuple_element", "mhlo.get_tuple_element"}:
        return "Projection"
    return "Primitive"


def _open_region(
    *,
    regions: list[dict[str, object]],
    expansion_edges: list[dict[str, object]],
    region_stack: list[str],
    region_by_id: dict[str, dict[str, object]],
    kind: str,
    parent_function: str,
    parent_op_id: str,
    line_start: int,
    edge_kind: str,
    edge_from: str,
) -> str:
    region_id = f"region_{len(regions):05d}"
    region = {
        "region_id": region_id,
        "kind": kind,
        "parent_function": parent_function,
        "parent_op_id": parent_op_id,
        "depth": len(region_stack),
        "line_start": line_start,
        "line_end": None,
        "op_ids": [],
    }
    regions.append(region)
    region_by_id[region_id] = region
    region_stack.append(region_id)
    expansion_edges.append(
        {
            "edge_id": f"edge_{len(expansion_edges):05d}",
            "kind": edge_kind,
            "from": edge_from,
            "to": region_id,
        }
    )
    return region_id


def _close_region(
    *,
    line_no: int,
    region_stack: list[str],
    region_by_id: dict[str, dict[str, object]],
    function_stack: list[str],
    function_by_name: dict[str, dict[str, object]],
    while_owner_stack: list[str],
    case_owner_stack: list[dict[str, object]],
) -> dict[str, object] | None:
    if len(region_stack) <= 1:
        module_region = region_by_id.get(region_stack[0]) if region_stack else None
        if module_region is not None:
            module_region["line_end"] = line_no
        return module_region
    region_id = region_stack.pop()
    region = region_by_id[region_id]
    region["line_end"] = line_no
    kind = str(region["kind"])
    if kind == "function_body" and function_stack:
        function_name = function_stack.pop()
        if function_name in function_by_name:
            function_by_name[function_name]["line_end"] = line_no
    if kind == "while_do" and while_owner_stack:
        while_owner_stack.pop()
    if kind == "case_branch" and case_owner_stack and str(region["parent_op_id"]) == case_owner_stack[-1]["op_id"]:
        if str(region.get("close_reason", "")) == "case_end":
            case_owner_stack.pop()
    return region


def _current_region(
    *,
    region_stack: Sequence[str],
    region_by_id: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    return region_by_id[region_stack[-1]]


def _extract_operational_ir(stablehlo_text: str) -> dict[str, object]:
    ops: list[dict[str, object]] = []
    functions: list[dict[str, object]] = []
    regions: list[dict[str, object]] = []
    expansion_edges: list[dict[str, object]] = []
    function_by_name: dict[str, dict[str, object]] = {}
    region_by_id: dict[str, dict[str, object]] = {}
    region_stack: list[str] = []
    function_stack: list[str] = []
    while_owner_stack: list[str] = []
    case_owner_stack: list[dict[str, object]] = []
    function_signatures: list[str] = []
    _open_region(
        regions=regions,
        expansion_edges=expansion_edges,
        region_stack=region_stack,
        region_by_id=region_by_id,
        kind="module",
        parent_function="",
        parent_op_id="",
        line_start=1,
        edge_kind="program_root",
        edge_from="program",
    )
    for line_no, line in enumerate(stablehlo_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("})"):
            if region_stack:
                top_region = region_by_id[region_stack[-1]]
                top_region["close_reason"] = "case_end"
            _close_region(
                line_no=line_no,
                region_stack=region_stack,
                region_by_id=region_by_id,
                function_stack=function_stack,
                function_by_name=function_by_name,
                while_owner_stack=while_owner_stack,
                case_owner_stack=case_owner_stack,
            )
            continue

        if stripped.startswith("},"):
            _close_region(
                line_no=line_no,
                region_stack=region_stack,
                region_by_id=region_by_id,
                function_stack=function_stack,
                function_by_name=function_by_name,
                while_owner_stack=while_owner_stack,
                case_owner_stack=case_owner_stack,
            )
            if "{" in stripped and case_owner_stack:
                context = case_owner_stack[-1]
                branch_index = int(context["next_branch"])
                context["next_branch"] = branch_index + 1
                _open_region(
                    regions=regions,
                    expansion_edges=expansion_edges,
                    region_stack=region_stack,
                    region_by_id=region_by_id,
                    kind="case_branch",
                    parent_function=function_stack[-1] if function_stack else "",
                    parent_op_id=str(context["op_id"]),
                    line_start=line_no,
                    edge_kind=f"case_branch_{branch_index}",
                    edge_from=str(context["op_id"]),
                )
            continue

        if stripped.startswith("} do"):
            _close_region(
                line_no=line_no,
                region_stack=region_stack,
                region_by_id=region_by_id,
                function_stack=function_stack,
                function_by_name=function_by_name,
                while_owner_stack=while_owner_stack,
                case_owner_stack=case_owner_stack,
            )
            parent_op_id = while_owner_stack[-1] if while_owner_stack else ""
            if parent_op_id:
                _open_region(
                    regions=regions,
                    expansion_edges=expansion_edges,
                    region_stack=region_stack,
                    region_by_id=region_by_id,
                    kind="while_do",
                    parent_function=function_stack[-1] if function_stack else "",
                    parent_op_id=parent_op_id,
                    line_start=line_no,
                    edge_kind="while_do",
                    edge_from=parent_op_id,
                )
            continue

        if stripped.startswith("}"):
            _close_region(
                line_no=line_no,
                region_stack=region_stack,
                region_by_id=region_by_id,
                function_stack=function_stack,
                function_by_name=function_by_name,
                while_owner_stack=while_owner_stack,
                case_owner_stack=case_owner_stack,
            )
            continue

        if stripped == "cond {":
            parent_op_id = while_owner_stack[-1] if while_owner_stack else ""
            if parent_op_id:
                _open_region(
                    regions=regions,
                    expansion_edges=expansion_edges,
                    region_stack=region_stack,
                    region_by_id=region_by_id,
                    kind="while_cond",
                    parent_function=function_stack[-1] if function_stack else "",
                    parent_op_id=parent_op_id,
                    line_start=line_no,
                    edge_kind="while_cond",
                    edge_from=parent_op_id,
                )
            continue

        match = _OP_RE.search(stripped)
        if match is None:
            continue
        opcode = match.group(0)
        kind = _classify_opcode(opcode)
        current_region = _current_region(region_stack=region_stack, region_by_id=region_by_id)
        current_function = function_stack[-1] if function_stack else ""
        call_target = ""
        if kind == "Call":
            target_match = _CALL_TARGET_RE.search(stripped)
            if target_match is not None:
                call_target = target_match.group("name")
        if kind == "Function":
            function_signatures.append(stripped)
            func_match = _FUNC_NAME_RE.search(stripped)
            current_function = func_match.group("name") if func_match is not None else f"anonymous_{len(functions):05d}"
            function = {
                "function_id": f"function:{current_function}",
                "name": current_function,
                "signature": stripped,
                "line_start": line_no,
                "line_end": None,
                "body_region_id": "",
            }
            functions.append(function)
            function_by_name[current_function] = function
        tensor_types = _TENSOR_RE.findall(stripped)
        dtypes = sorted(set(_DTYPE_RE.findall(stripped)))
        op_id = f"op_{len(ops):05d}"
        region_path = list(region_stack)
        ops.append(
            {
                "op_id": op_id,
                "kind": kind,
                "opcode": opcode,
                "line": line_no,
                "text": stripped,
                "text_sha256": _sha256_text(stripped),
                "tensor_types": tensor_types,
                "dtypes": dtypes,
                "function": current_function,
                "region_id": current_region["region_id"],
                "region_path": region_path,
                "parent_op_id": current_region.get("parent_op_id", ""),
                "call_target": call_target,
            }
        )
        current_region["op_ids"].append(op_id)
        if call_target:
            expansion_edges.append(
                {
                    "edge_id": f"edge_{len(expansion_edges):05d}",
                    "kind": "call_target",
                    "from": op_id,
                    "to": f"function:{call_target}",
                }
            )
        if kind == "Function":
            body_region_id = _open_region(
                regions=regions,
                expansion_edges=expansion_edges,
                region_stack=region_stack,
                region_by_id=region_by_id,
                kind="function_body",
                parent_function=current_function,
                parent_op_id=op_id,
                line_start=line_no,
                edge_kind="function_body",
                edge_from=f"function:{current_function}",
            )
            function_by_name[current_function]["body_region_id"] = body_region_id
            function_stack.append(current_function)
        elif kind == "While":
            while_owner_stack.append(op_id)
        elif kind == "Case":
            case_owner_stack.append({"op_id": op_id, "next_branch": 1})
            _open_region(
                regions=regions,
                expansion_edges=expansion_edges,
                region_stack=region_stack,
                region_by_id=region_by_id,
                kind="case_branch",
                parent_function=function_stack[-1] if function_stack else "",
                parent_op_id=op_id,
                line_start=line_no,
                edge_kind="case_branch_0",
                edge_from=op_id,
            )
    line_count = len(stablehlo_text.splitlines())
    while len(region_stack) > 1:
        _close_region(
            line_no=line_count,
            region_stack=region_stack,
            region_by_id=region_by_id,
            function_stack=function_stack,
            function_by_name=function_by_name,
            while_owner_stack=while_owner_stack,
            case_owner_stack=case_owner_stack,
        )
    if region_stack:
        region_by_id[region_stack[0]]["line_end"] = line_count
    for region in regions:
        if region["line_end"] is None:
            region["line_end"] = line_count
    for function in functions:
        if function["line_end"] is None:
            function["line_end"] = line_count
    assigned_region_ids = {op["region_id"] for op in ops}
    known_region_ids = {region["region_id"] for region in regions}
    unassigned_ops = [
        op["op_id"]
        for op in ops
        if op["region_id"] not in known_region_ids
    ]
    unresolved_call_targets = sorted(
        {
            op["call_target"]
            for op in ops
            if op.get("call_target") and f"function:{op['call_target']}" not in {fn["function_id"] for fn in functions}
        }
    )
    return {
        "schema": "agent-canon.thin-operational-ir.v2",
        "allowed_kinds": [
            "Function",
            "Let",
            "Call",
            "If",
            "While",
            "Case",
            "Tuple",
            "Projection",
            "Primitive",
            "Return",
        ],
        "function_signatures": function_signatures,
        "functions": functions,
        "regions": regions,
        "expansion_edges": expansion_edges,
        "ops": ops,
        "coverage": {
            "function_count": len(functions),
            "region_count": len(regions),
            "expansion_edge_count": len(expansion_edges),
            "op_count": len(ops),
            "assigned_region_count": len(assigned_region_ids),
            "unassigned_op_count": len(unassigned_ops),
            "unassigned_op_ids": unassigned_ops,
            "unresolved_call_targets": unresolved_call_targets,
            "max_region_depth": max((int(region["depth"]) for region in regions), default=0),
            "while_count": sum(1 for op in ops if op["kind"] == "While"),
            "case_count": sum(1 for op in ops if op["kind"] == "Case"),
            "if_count": sum(1 for op in ops if op["kind"] == "If"),
            "call_count": sum(1 for op in ops if op["kind"] == "Call"),
        },
    }


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _count_mlir_ops(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in _OP_RE.finditer(text):
        opcode = match.group(0)
        counts[opcode] = counts.get(opcode, 0) + 1
    return dict(sorted(counts.items()))


def _parse_llvm_functions(text: str) -> list[dict[str, object]]:
    functions: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_block = "entry"
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        define_match = _LLVM_DEFINE_RE.match(line)
        if define_match is not None:
            current = {
                "name": define_match.group("name"),
                "signature": line.strip(),
                "return_and_attrs": define_match.group("attrs").strip(),
                "params": define_match.group("params").strip(),
                "op_counts": {},
                "fast_math_flags": {},
                "basic_blocks": [
                    {
                        "label": "entry",
                        "line": line_no,
                        "instruction_ids": [],
                    }
                ],
                "instructions": [],
            }
            current_block = "entry"
            functions.append(current)
            continue
        if current is None:
            continue
        if stripped.startswith("}"):
            current = None
            continue

        label_match = _LLVM_LABEL_RE.match(stripped)
        if label_match is not None:
            current_block = label_match.group("label")
            current["basic_blocks"].append(
                {
                    "label": current_block,
                    "line": line_no,
                    "instruction_ids": [],
                }
            )
            continue

        result_name = ""
        instruction_body = stripped
        result_match = _LLVM_RESULT_RE.match(stripped)
        if result_match is not None:
            result_name = result_match.group("result")
            instruction_body = result_match.group("body")

        opcode_match = _LLVM_OPCODE_RE.search(instruction_body)
        if opcode_match is None:
            continue
        opcode = opcode_match.group("opcode")
        op_counts = current["op_counts"]
        op_counts[opcode] = op_counts.get(opcode, 0) + 1
        tail = opcode_match.group("tail")
        flag_counts = current["fast_math_flags"]
        flags: list[str] = []
        for flag in _LLVM_FASTMATH_FLAGS:
            if re.search(rf"\b{re.escape(flag)}\b", tail):
                flag_counts[flag] = flag_counts.get(flag, 0) + 1
                flags.append(flag)
        instruction_id = f"{current['name']}:inst_{len(current['instructions']):05d}"
        instruction = {
            "instruction_id": instruction_id,
            "function": current["name"],
            "basic_block": current_block,
            "line": line_no,
            "result_name": result_name,
            "opcode": opcode,
            "operand_text": tail.strip(),
            "text": stripped,
            "text_sha256": _sha256_text(stripped),
            "fast_math_flags": flags,
            "is_float_op": opcode in _LLVM_FLOAT_OPCODES,
        }
        current["instructions"].append(instruction)
        if current["basic_blocks"]:
            current["basic_blocks"][-1]["instruction_ids"].append(instruction_id)
    for function in functions:
        function["op_counts"] = dict(sorted(function["op_counts"].items()))
        function["fast_math_flags"] = dict(sorted(function["fast_math_flags"].items()))
        function["instruction_count"] = len(function["instructions"])
        function["float_instruction_count"] = sum(
            1
            for instruction in function["instructions"]
            if instruction["is_float_op"]
        )
    return functions


def _copy_text_artifact(source: Path, output_dir: Path, *, relative_prefix: str) -> dict[str, object]:
    text = source.read_text(encoding="utf-8", errors="replace")
    destination = output_dir / relative_prefix / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    if source.suffix == ".ll":
        functions = _parse_llvm_functions(text)
        op_counts: dict[str, int] = {}
        fast_math_flags: dict[str, int] = {}
        instruction_count = 0
        float_instruction_count = 0
        basic_block_count = 0
        for function in functions:
            for opcode, count in function["op_counts"].items():
                op_counts[opcode] = op_counts.get(opcode, 0) + int(count)
            for flag, count in function["fast_math_flags"].items():
                fast_math_flags[flag] = fast_math_flags.get(flag, 0) + int(count)
            instruction_count += int(function["instruction_count"])
            float_instruction_count += int(function["float_instruction_count"])
            basic_block_count += len(function["basic_blocks"])
        return {
            "path": str(destination),
            "sha256": _sha256_text(text),
            "kind": "llvm_ir",
            "functions": functions,
            "op_counts": dict(sorted(op_counts.items())),
            "fast_math_flags": dict(sorted(fast_math_flags.items())),
            "basic_block_count": basic_block_count,
            "instruction_count": instruction_count,
            "float_instruction_count": float_instruction_count,
        }
    return {
        "path": str(destination),
        "sha256": _sha256_text(text),
        "kind": "mlir_text",
        "op_counts": _count_mlir_ops(text),
    }


def _copy_binary_artifact(source: Path, output_dir: Path, *, relative_prefix: str, kind: str) -> dict[str, object]:
    data = source.read_bytes()
    destination = output_dir / relative_prefix / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {
        "path": str(destination),
        "sha256": hashlib.sha256(data).hexdigest(),
        "kind": kind,
        "size_bytes": len(data),
    }


def _iree_target_args(
    target_backend: str,
    *,
    input_type: str = "stablehlo",
    iree_cuda_target: str | None = None,
) -> list[str]:
    args = [
        f"--iree-input-type={input_type}",
        f"--iree-hal-target-backends={target_backend}",
        "--mlir-disable-threading",
    ]
    if iree_cuda_target:
        args.append(f"--iree-cuda-target={iree_cuda_target}")
    return args


def _copy_llvm_bitcode_as_text(
    bitcode_path: Path,
    output_dir: Path,
    *,
    relative_prefix: str,
) -> dict[str, object] | None:
    llvm_dis = _find_llvm_dis()
    if llvm_dis is None:
        return None
    with tempfile.TemporaryDirectory(prefix="agent-canon-llvm-dis-") as tmp_text:
        text_path = Path(tmp_text) / f"{bitcode_path.stem}.ll"
        result = subprocess.run(
            [llvm_dis, str(bitcode_path), "-o", str(text_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not text_path.exists():
            return None
        copied = _copy_text_artifact(text_path, output_dir, relative_prefix=relative_prefix)
        copied["source_bitcode"] = str(bitcode_path)
        return copied


def _collect_dump_artifacts(
    dump_dir: Path,
    output_dir: Path,
    *,
    relative_prefix: str,
) -> dict[str, list[dict[str, object]]]:
    artifacts: dict[str, list[dict[str, object]]] = {
        "executable_sources": [],
        "llvm_ir": [],
        "llvm_bitcode": [],
        "object_files": [],
        "assembly": [],
        "other": [],
    }
    if not dump_dir.exists():
        return artifacts
    for path in sorted(dump_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        prefix = f"{relative_prefix}/{path.parent.relative_to(dump_dir)}"
        prefix = prefix.rstrip("/.")
        if suffix == ".ll":
            artifacts["llvm_ir"].append(_copy_text_artifact(path, output_dir, relative_prefix=prefix))
        elif suffix == ".bc":
            artifacts["llvm_bitcode"].append(
                _copy_binary_artifact(path, output_dir, relative_prefix=prefix, kind="llvm_bitcode")
            )
            disassembled = _copy_llvm_bitcode_as_text(path, output_dir, relative_prefix=prefix)
            if disassembled is not None:
                artifacts["llvm_ir"].append(disassembled)
        elif suffix == ".mlir":
            artifacts["executable_sources"].append(
                _copy_text_artifact(path, output_dir, relative_prefix=prefix)
            )
        elif suffix == ".s":
            copied = _copy_text_artifact(path, output_dir, relative_prefix=prefix)
            copied["kind"] = "assembly"
            artifacts["assembly"].append(copied)
        elif suffix == ".ptx":
            copied = _copy_text_artifact(path, output_dir, relative_prefix=prefix)
            copied["kind"] = "ptx"
            artifacts["assembly"].append(copied)
        elif suffix == ".o":
            artifacts["object_files"].append(
                _copy_binary_artifact(path, output_dir, relative_prefix=prefix, kind="object_file")
            )
        else:
            artifacts["other"].append(
                _copy_binary_artifact(path, output_dir, relative_prefix=prefix, kind="backend_artifact")
            )
    return artifacts


def _collect_xla_dump_artifacts(
    dump_dir: Path,
    output_dir: Path,
) -> dict[str, list[dict[str, object]]]:
    artifacts: dict[str, list[dict[str, object]]] = {
        "executable_sources": [],
        "llvm_ir": [],
        "llvm_bitcode": [],
        "object_files": [],
        "assembly": [],
        "other": [],
    }
    if not dump_dir.exists():
        return artifacts
    for path in sorted(dump_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        suffix = path.suffix.lower()
        if name.startswith("LLVMDialectModule.pass-"):
            continue
        if suffix == ".ll" and ".ir-" not in name:
            continue
        if suffix not in {".ll", ".bc", ".ptx", ".s"}:
            continue
        prefix = f"xla_dump/{path.parent.relative_to(dump_dir)}"
        prefix = prefix.rstrip("/.")
        if suffix == ".ll":
            artifacts["llvm_ir"].append(_copy_text_artifact(path, output_dir, relative_prefix=prefix))
        elif suffix == ".bc":
            artifacts["llvm_bitcode"].append(
                _copy_binary_artifact(path, output_dir, relative_prefix=prefix, kind="llvm_bitcode")
            )
            disassembled = _copy_llvm_bitcode_as_text(path, output_dir, relative_prefix=prefix)
            if disassembled is not None:
                artifacts["llvm_ir"].append(disassembled)
        elif suffix == ".ptx":
            copied = _copy_text_artifact(path, output_dir, relative_prefix=prefix)
            copied["kind"] = "ptx"
            artifacts["assembly"].append(copied)
        else:
            copied = _copy_text_artifact(path, output_dir, relative_prefix=prefix)
            copied["kind"] = "assembly"
            artifacts["assembly"].append(copied)
    return artifacts


def _merge_artifacts(
    target: dict[str, list[dict[str, object]]],
    source: dict[str, list[dict[str, object]]],
) -> None:
    seen = {
        key: {item.get("sha256") for item in target.get(key, [])}
        for key in source
    }
    for key, items in source.items():
        target.setdefault(key, [])
        for item in items:
            digest = item.get("sha256")
            if digest in seen.setdefault(key, set()):
                continue
            target[key].append(item)
            seen[key].add(digest)


def _run_iree_compile_attempt(
    *,
    name: str,
    command: list[str],
    dump_dir: Path,
    output_path: Path,
    output_dir: Path,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    artifacts = _collect_dump_artifacts(
        dump_dir,
        output_dir,
        relative_prefix=f"compile_attempts/{name}",
    )
    record: dict[str, object] = {
        "name": name,
        "compile_command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "artifact_counts": {key: len(value) for key, value in artifacts.items()},
    }
    if result.returncode != 0:
        record["diagnostic_summary"] = _summarize_mlir_failure(result.stderr)
    if output_path.exists():
        data = output_path.read_bytes()
        destination = output_dir / "compile_attempts" / name / output_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        record["output"] = {
            "path": str(destination),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
    if result.returncode != 0:
        failure = _collect_mlir_failure_reproducer(
            command,
            output_dir,
            relative_prefix=f"compile_attempts/{name}",
        )
        if failure is not None:
            record["failure_reproducer"] = failure
    return record, artifacts


def _run_executable_configuration_translation_attempt(
    *,
    compiler: str,
    source_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, object] | None, dict[str, list[dict[str, object]]]]:
    configured_sources = sorted(
        path for path in source_dir.rglob("configured_*.mlir")
        if path.is_file()
    )
    artifacts: dict[str, list[dict[str, object]]] = {
        "executable_sources": [],
        "llvm_ir": [],
        "llvm_bitcode": [],
        "object_files": [],
        "assembly": [],
        "other": [],
    }
    if not configured_sources:
        return None, artifacts

    child_records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="agent-canon-iree-executable-config-") as tmp_text:
        tmp = Path(tmp_text)
        for source in configured_sources:
            child_name = source.stem
            child_dump = tmp / child_name / "dump"
            child_output = tmp / child_name / f"{child_name}.vmfb"
            command = [
                compiler,
                str(source),
                "--compile-from=executable-configurations",
                f"--iree-hal-dump-executable-files-to={child_dump}",
                "-o",
                str(child_output),
            ]
            child_record, child_artifacts = _run_iree_compile_attempt(
                name=f"translate_executable_configurations/{child_name}",
                command=command,
                dump_dir=child_dump,
                output_path=child_output,
                output_dir=output_dir,
            )
            child_record["source"] = str(source)
            child_records.append(child_record)
            _merge_artifacts(artifacts, child_artifacts)

    failed = [
        record for record in child_records
        if record.get("returncode") != 0
    ]
    return (
        {
            "name": "translate_executable_configurations",
            "source_count": len(configured_sources),
            "success_count": len(child_records) - len(failed),
            "failure_count": len(failed),
            "artifact_counts": {key: len(value) for key, value in artifacts.items()},
            "children": child_records,
        },
        artifacts,
    )


def _compile_lowered_for_backend_dump(lowered: object) -> dict[str, object]:
    compile_fn = getattr(lowered, "compile", None)
    if compile_fn is None:
        return {
            "available": False,
            "returncode": None,
            "status": "compile_method_unavailable",
        }
    try:
        compiled = compile_fn()
    except Exception as exc:  # pragma: no cover - backend dependent.
        return {
            "available": True,
            "returncode": 1,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "available": True,
        "returncode": 0,
        "status": "succeeded",
        "compiled_type": type(compiled).__name__,
    }


def _summarize_mlir_failure(stderr: str) -> dict[str, str | None]:
    first_error: str | None = None
    for line in stderr.splitlines():
        if " error: " in line or line.startswith("error: "):
            first_error = line.strip()
            break
    pass_match = _MLIR_FAILURE_PASS_RE.search(stderr)
    return {
        "first_error": first_error,
        "failed_pass": pass_match.group("pass_name") if pass_match is not None else None,
    }


def _collect_mlir_failure_reproducer(
    command: Sequence[str],
    output_dir: Path,
    *,
    relative_prefix: str,
) -> dict[str, object] | None:
    compiler = command[0]
    with tempfile.TemporaryDirectory(prefix="agent-canon-iree-repro-") as tmp_text:
        tmp = Path(tmp_text)
        reproducer_path = tmp / "reproducer.mlir"
        debug_flags = [
            "--mlir-disable-threading",
            f"--mlir-pass-pipeline-crash-reproducer={reproducer_path}",
            "--mlir-pass-pipeline-local-reproducer",
        ]
        try:
            output_index = list(command).index("-o")
        except ValueError:
            output_index = len(command)
        rerun_command = [
            *command[:output_index],
            *debug_flags,
            *command[output_index:],
        ]
        result = subprocess.run(rerun_command, text=True, capture_output=True, check=False)
        match = _MLIR_FAILURE_PASS_RE.search(result.stderr)
        record: dict[str, object] = {
            "command": rerun_command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if match is not None:
            record["failed_pass"] = match.group("pass_name")
        if reproducer_path.exists():
            destination = output_dir / relative_prefix / "failure_reproducer.mlir"
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = reproducer_path.read_bytes()
            destination.write_bytes(data)
            record["artifact"] = {
                "path": str(destination),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        input_path = Path(command[1]) if len(command) > 1 else None
        if input_path is not None and input_path.exists():
            destination = output_dir / relative_prefix / "failure_input.mlir"
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = input_path.read_bytes()
            destination.write_bytes(data)
            record["input_artifact"] = {
                "path": str(destination),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        if "artifact" not in record and "input_artifact" not in record and "failed_pass" not in record:
            return None
        record["compiler"] = compiler
        return record


def _collect_backend_trace(
    stablehlo_text: str,
    *,
    output_dir: Path | None,
    target_backend: str,
    iree_cuda_target: str | None,
    compiler_errors: Sequence[str],
    xla_dump_dir: Path | None,
    xla_compile_record: Mapping[str, object] | None,
) -> dict[str, object]:
    executables = {
        "iree-compile": shutil.which("iree-compile"),
        "iree-run-module": shutil.which("iree-run-module"),
        "llvm-dis": _find_llvm_dis(),
    }
    base: dict[str, object] = {
        "schema": "agent-canon.typed-backend-trace.v1",
        "target_backend": target_backend,
        "target_options": {
            "iree_cuda_target": iree_cuda_target,
        },
        "executables": executables,
        "compiler_ir_errors": list(compiler_errors),
        "compile_command": [],
        "coverage": "not_generated",
        "phase_traces": [],
        "compile_attempts": [],
        "xla_compile": dict(xla_compile_record or {}),
        "executable_sources": [],
        "llvm_ir": [],
        "llvm_bitcode": [],
        "object_files": [],
        "assembly": [],
    }
    compiler = executables["iree-compile"]
    if compiler is None:
        base["coverage"] = "compiler_unavailable"
        return base
    if output_dir is None:
        base["coverage"] = "output_dir_not_requested"
        return base
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-canon-iree-") as tmp_text:
        tmp = Path(tmp_text)
        stablehlo_path = tmp / "input_stablehlo.mlir"
        stablehlo_path.write_text(stablehlo_text, encoding="utf-8")
        phase_records = []
        last_phase = "none"
        last_phase_path: Path | None = None
        for phase in _IREE_PHASES:
            phase_out = tmp / f"{phase}.mlir"
            phase_cmd = [
                compiler,
                str(stablehlo_path),
                *_iree_target_args(target_backend, iree_cuda_target=iree_cuda_target),
                f"--compile-to={phase}",
                "--output-format=vm-asm",
                "-o",
                str(phase_out),
            ]
            phase_result = subprocess.run(phase_cmd, text=True, capture_output=True, check=False)
            phase_record: dict[str, object] = {
                "phase": phase,
                "compile_command": phase_cmd,
                "returncode": phase_result.returncode,
                "stdout": phase_result.stdout,
                "stderr": phase_result.stderr,
            }
            if phase_result.returncode == 0 and phase_out.exists():
                copied = _copy_text_artifact(
                    phase_out,
                    output_dir,
                    relative_prefix="backend_phases",
                )
                copied["phase"] = phase
                phase_record["artifact"] = copied
                last_phase = phase
                last_phase_path = phase_out
            elif phase_result.returncode != 0:
                phase_record["diagnostic_summary"] = _summarize_mlir_failure(phase_result.stderr)
                failure_command = phase_cmd
                if last_phase_path is not None:
                    failure_command = [
                        compiler,
                        str(last_phase_path),
                        *_iree_target_args(
                            target_backend,
                            input_type="none",
                            iree_cuda_target=iree_cuda_target,
                        ),
                        f"--compile-from={last_phase}",
                        f"--compile-to={phase}",
                        "--output-format=vm-asm",
                        "-o",
                        str(phase_out),
                    ]
                failure = _collect_mlir_failure_reproducer(
                    failure_command,
                    output_dir,
                    relative_prefix=f"backend_phases/{phase}",
                )
                if failure is not None:
                    phase_record["failure_reproducer"] = failure
            phase_records.append(phase_record)
            if phase_result.returncode != 0:
                break
        base["phase_traces"] = phase_records
        base["last_successful_phase"] = last_phase

        collected: dict[str, list[dict[str, object]]] = {
            "executable_sources": [],
            "llvm_ir": [],
            "llvm_bitcode": [],
            "object_files": [],
            "assembly": [],
            "other": [],
        }
        attempts: list[tuple[str, list[str], Path, Path]] = []
        embedded_dump = tmp / "full_dump_embedded"
        embedded_vmfb = tmp / "full_embedded.vmfb"
        attempts.append(
            (
                "full_dump_embedded",
                [
                    compiler,
                    str(stablehlo_path),
                    *_iree_target_args(target_backend, iree_cuda_target=iree_cuda_target),
                    f"--iree-hal-dump-executable-files-to={embedded_dump}",
                    "-o",
                    str(embedded_vmfb),
                ],
                embedded_dump,
                embedded_vmfb,
            )
        )
        executable_targets_dump = tmp / "executable_targets_dump"
        executable_targets_out = tmp / "executable_targets.mlir"
        attempts.append(
            (
                "compile_to_executable_targets",
                [
                    compiler,
                    str(stablehlo_path),
                    *_iree_target_args(target_backend, iree_cuda_target=iree_cuda_target),
                    "--compile-to=executable-targets",
                    "--output-format=vm-asm",
                    f"--iree-hal-dump-executable-files-to={executable_targets_dump}",
                    "-o",
                    str(executable_targets_out),
                ],
                executable_targets_dump,
                executable_targets_out,
            )
        )

        compile_attempt_records = []
        for name, cmd, dump_dir, output_path in attempts:
            attempt_record, artifacts = _run_iree_compile_attempt(
                name=name,
                command=cmd,
                dump_dir=dump_dir,
                output_path=output_path,
                output_dir=output_dir,
            )
            compile_attempt_records.append(attempt_record)
            _merge_artifacts(collected, artifacts)
            if collected["llvm_ir"]:
                break
            if name == "compile_to_executable_targets" and attempt_record["returncode"] == 0:
                translated_record, translated_artifacts = _run_executable_configuration_translation_attempt(
                    compiler=compiler,
                    source_dir=dump_dir,
                    output_dir=output_dir,
                )
                if translated_record is not None:
                    compile_attempt_records.append(translated_record)
                    _merge_artifacts(collected, translated_artifacts)
                if collected["llvm_ir"]:
                    break

        if xla_dump_dir is not None:
            xla_artifacts = _collect_xla_dump_artifacts(
                xla_dump_dir,
                output_dir,
            )
            _merge_artifacts(collected, xla_artifacts)
            base["xla_compile"] = {
                **dict(xla_compile_record or {}),
                "dump_source": "xla_dump_dir",
                "artifact_counts": {
                    key: len(value) for key, value in xla_artifacts.items()
                },
            }

        base["compile_attempts"] = compile_attempt_records
        base["compile_command"] = compile_attempt_records[0]["compile_command"] if compile_attempt_records else []
        if compile_attempt_records:
            first_attempt = compile_attempt_records[0]
            base["returncode"] = first_attempt["returncode"]
            base["stdout"] = first_attempt["stdout"]
            base["stderr"] = first_attempt["stderr"]
            if "output" in first_attempt:
                base["vmfb"] = first_attempt["output"]
        base["executable_sources"] = collected["executable_sources"]
        base["llvm_ir"] = collected["llvm_ir"]
        base["llvm_bitcode"] = collected["llvm_bitcode"]
        base["object_files"] = collected["object_files"]
        base["assembly"] = collected["assembly"]
        if collected["llvm_ir"]:
            base["coverage"] = "generated_with_llvm"
        elif any(record["returncode"] == 0 for record in compile_attempt_records):
            base["coverage"] = "generated_without_llvm_text"
        else:
            base["coverage"] = f"phase_trace_until_{last_phase}_llvm_compile_failed"
        return base


def _backend_environment(dialect: str, compiler_errors: Sequence[str]) -> dict[str, object]:
    import jax

    executables = {
        "iree-compile": shutil.which("iree-compile"),
        "iree-run-module": shutil.which("iree-run-module"),
        "llvm-dis": _find_llvm_dis(),
    }
    packages = {
        name: _package_version(name)
        for name in (
            "jax",
            "jaxlib",
            "equinox",
            "iree-base-compiler",
            "iree-base-runtime",
            "iree-compiler",
            "iree-runtime",
        )
    }
    try:
        devices = [str(device) for device in jax.devices()]
    except Exception as exc:  # pragma: no cover - environment dependent.
        devices = [f"unavailable: {type(exc).__name__}: {exc}"]
    return {
        "schema": "agent-canon.backend-environment.v1",
        "dialect": dialect,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "jax_default_backend": jax.default_backend(),
        "jax_devices": devices,
        "runtime_selection_env": _backend_runtime_env_snapshot(),
        "executables": executables,
        "compiler_ir_errors": list(compiler_errors),
        "float_semantics_policy": "Backend FP semantics are generated from backend trace coverage, not accepted as an external axiom.",
    }


def build_jit_canonical_ir(
    *,
    python_symbol: str,
    input_factory_symbol: str,
    input_device: str | None,
    backend_trace_dir: Path | None,
    backend_target: str | None,
    iree_cuda_target: str | None,
    xla_dump_dir: Path | None,
    include_source_root: bool,
    include_backend_trace: bool,
) -> dict[str, object]:
    """Build the JIT-canonical IR record for one lowered Python root."""
    repo_root = Path.cwd().resolve()
    with _jax_default_device(input_device):
        func = _load_symbol(python_symbol)
        input_factory = _load_symbol(input_factory_symbol)
        args, kwargs = _normalize_inputs(input_factory())
    lowered = _lower(func, args, kwargs)
    dialect, stablehlo_text, compiler_errors = _compiler_ir_text(lowered)
    xla_compile_record: Mapping[str, object] | None = None
    if include_backend_trace and xla_dump_dir is not None:
        xla_compile_record = _compile_lowered_for_backend_dump(lowered)
    operational_ir = _extract_operational_ir(stablehlo_text)
    public_interface = _collect_public_interface(
        python_symbol=python_symbol,
        func=func,
        args=args,
        kwargs=kwargs,
        operational_ir=operational_ir,
    )
    stablehlo_sha256 = _sha256_text(stablehlo_text)
    source_root = (
        _extract_source_root(python_symbol)
        if include_source_root
        else _hlo_only_source_root(python_symbol)
    )
    record: dict[str, object] = {
        "schema": "agent-canon.jit-canonical-ir.v1",
        "root": {
            "python_symbol": python_symbol,
            "input_factory_symbol": input_factory_symbol,
            "repo_root": str(repo_root),
            "jit_kind": "filter_jit",
        },
        "stablehlo": {
            "dialect": dialect,
            "sha256": stablehlo_sha256,
            "text": stablehlo_text,
            "line_count": len(stablehlo_text.splitlines()),
        },
        "public_interface": public_interface,
        "operational_ir": operational_ir,
        "source_root": source_root,
    }
    if include_backend_trace:
        if backend_target is None:
            raise SystemExit(f"backend_env_missing={ENV_JIT_BACKEND_TARGET}")
        record["backend_environment"] = _backend_environment(dialect, compiler_errors)
        record["backend_trace"] = _collect_backend_trace(
            stablehlo_text,
            output_dir=backend_trace_dir,
            target_backend=backend_target,
            iree_cuda_target=iree_cuda_target,
            compiler_errors=compiler_errors,
            xla_dump_dir=xla_dump_dir,
            xla_compile_record=xla_compile_record,
        )
    return record


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Backend/runtime selection is read from environment variables: "
            f"{ENV_JIT_JAX_PLATFORM}, {ENV_JIT_BACKEND_TARGET}, "
            f"{ENV_JIT_INPUT_DEVICE}, {ENV_JIT_CUDA_VISIBLE_DEVICES}, "
            f"{ENV_JIT_IREE_CUDA_TARGET}."
        ),
    )
    parser.add_argument("--python-symbol", required=True, help="JIT root as path.py::qualname.")
    parser.add_argument("--input-factory", required=True, help="Concrete lowering input factory as path.py::qualname.")
    parser.add_argument(
        "--xla-flags",
        help="Additional XLA_FLAGS appended before JAX import, for example '--xla_gpu_dump_llvmir'.",
    )
    parser.add_argument(
        "--xla-dump-dir",
        help="Directory for XLA CUDA LLVM/PTX dumps collected into the backend trace.",
    )
    parser.add_argument("--backend-trace-dir", help="Directory for generated backend MLIR/LLVM artifacts.")
    parser.add_argument(
        "--no-source-root",
        action="store_true",
        help="Do not derive source-level algorithm boundaries from the Python AST; keep only HLO-root metadata.",
    )
    parser.add_argument(
        "--no-backend-trace",
        action="store_true",
        help="Do not collect IREE/backend/LLVM traces; emit only StableHLO-derived operational IR.",
    )
    parser.add_argument("--out", required=True, help="Output JSON path.")
    parser.add_argument("--stablehlo-out", help="Optional StableHLO text output path.")
    parser.add_argument("--backend-trace-out", help="Optional backend trace JSON output path.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the JIT-canonical IR extractor."""
    args = parse_args(argv)
    runtime_config = resolve_runtime_backend_config(
        include_backend_trace=not args.no_backend_trace,
    )
    _configure_jax_platform(
        runtime_config.jax_platform,
        cuda_visible_devices=runtime_config.cuda_visible_devices,
        xla_flags=args.xla_flags,
        xla_dump_dir=Path(args.xla_dump_dir) if args.xla_dump_dir else None,
    )
    record = build_jit_canonical_ir(
        python_symbol=args.python_symbol,
        input_factory_symbol=args.input_factory,
        input_device=runtime_config.input_device,
        backend_trace_dir=Path(args.backend_trace_dir) if args.backend_trace_dir else None,
        backend_target=runtime_config.backend_target,
        iree_cuda_target=runtime_config.iree_cuda_target,
        xla_dump_dir=Path(args.xla_dump_dir) if args.xla_dump_dir else None,
        include_source_root=not args.no_source_root,
        include_backend_trace=not args.no_backend_trace,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.stablehlo_out:
        stablehlo_path = Path(args.stablehlo_out)
        stablehlo_path.parent.mkdir(parents=True, exist_ok=True)
        stablehlo_path.write_text(record["stablehlo"]["text"], encoding="utf-8")
    if args.backend_trace_out and "backend_trace" in record:
        trace_path = Path(args.backend_trace_out)
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(record["backend_trace"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
