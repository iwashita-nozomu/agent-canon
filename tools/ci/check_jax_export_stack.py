#!/usr/bin/env python3
# @dependency-start
# @dependency-end

"""Smoke-check the local jax.export + IREE stack and jaxlib C++ headers."""

from __future__ import annotations

import pathlib
import gc
import shutil
import sys

import jax
import jax.numpy as jnp
import jaxlib
import numpy as np
from jax import export as jax_export
from iree import compiler as ireec
from iree import runtime as ireert


def _module_name(vm_module: ireert.VmModule) -> str:
    """Return the decoded VM module name."""
    name = vm_module.name
    if isinstance(name, bytes):
        return name.decode()
    return str(name)


def _main_function(module_namespace: object) -> object:
    """Return the exported `main` function from one module namespace."""
    try:
        return module_namespace["main"]  # type: ignore[index]
    except TypeError:
        return getattr(module_namespace, "main")


def _to_host_array(value: object) -> np.ndarray:
    """Normalize one runtime result to a NumPy array."""
    if isinstance(value, tuple):
        if len(value) != 1:
            raise RuntimeError(f"unexpected tuple result from IREE runtime: {len(value)} values")
        return _to_host_array(value[0])
    if hasattr(value, "to_host"):
        return np.asarray(value.to_host())
    return np.asarray(value)


def main() -> int:
    """Validate that jax.export, IREE, and jaxlib headers are available."""
    include_dir = pathlib.Path(jaxlib.__file__).resolve().parent / "include"
    ffi_c_api = include_dir / "xla" / "ffi" / "api" / "c_api.h"
    ffi_cpp_api = include_dir / "xla" / "ffi" / "api" / "ffi.h"
    if not include_dir.is_dir():
        raise FileNotFoundError(f"jaxlib include directory not found: {include_dir}")
    if not ffi_c_api.is_file():
        raise FileNotFoundError(f"missing XLA FFI C API header: {ffi_c_api}")
    if not ffi_cpp_api.is_file():
        raise FileNotFoundError(f"missing XLA FFI C++ API header: {ffi_cpp_api}")
    if shutil.which("iree-compile") is None:
        raise FileNotFoundError("iree-compile not found on PATH")
    if shutil.which("iree-run-module") is None:
        raise FileNotFoundError("iree-run-module not found on PATH")

    def add_one(x: jax.Array) -> jax.Array:
        return x + 1

    signature = jax.ShapeDtypeStruct((2, 3), jnp.float32)
    exported = jax_export.export(jax.jit(add_one))(signature)
    serialized = exported.serialize()
    mlir_module = exported.mlir_module()
    roundtrip = exported.call(jnp.ones((2, 3), dtype=jnp.float32))

    if exported.calling_convention_version < 1:
        raise RuntimeError("invalid jax.export calling convention version")
    if not serialized:
        raise RuntimeError("jax.export serialize() returned empty bytes")
    if not mlir_module:
        raise RuntimeError("jax.export mlir_module() returned empty text")
    if roundtrip.shape != (2, 3):
        raise RuntimeError(f"unexpected exported.call result shape: {roundtrip.shape}")

    compiled_flatbuffer = ireec.tools.compile_str(
        mlir_module,
        input_type="stablehlo",
        target_backends=["vmvx"],
    )
    config = ireert.Config("local-task")
    context = ireert.SystemContext(config=config)
    vm_module = ireert.VmModule.copy_buffer(context.instance, compiled_flatbuffer)
    context.add_vm_module(vm_module)
    module_name = _module_name(vm_module)
    module_namespace = getattr(context.modules, module_name)
    main_function = _main_function(module_namespace)
    raw_iree_result = main_function(np.ones((2, 3), dtype=np.float32))
    iree_result = _to_host_array(raw_iree_result)
    expected = np.full((2, 3), 2.0, dtype=np.float32)
    if iree_result.shape != (2, 3):
        raise RuntimeError(f"unexpected IREE result shape: {iree_result.shape}")
    if not np.allclose(iree_result, expected):
        raise RuntimeError(f"unexpected IREE result values: {iree_result!r}")

    print(f"jax={jax.__version__}")
    print(f"jaxlib={jaxlib.__version__}")
    print(f"jax_export_calling_convention={exported.calling_convention_version}")
    print(
        "jax_export_supported_range="
        f"{jax_export.minimum_supported_calling_convention_version}.."
        f"{jax_export.maximum_supported_calling_convention_version}"
    )
    print(f"jaxlib_include_dir={include_dir}")
    print(f"jaxlib_ffi_c_api={ffi_c_api}")
    print(f"jaxlib_ffi_cpp_api={ffi_cpp_api}")
    print(f"iree_compile={shutil.which('iree-compile')}")
    print(f"iree_run_module={shutil.which('iree-run-module')}")
    print(f"iree_vm_module={module_name}")
    print("iree_driver=local-task")
    print(f"iree_result_shape={iree_result.shape}")

    del raw_iree_result
    del main_function
    del module_namespace
    del vm_module
    del context
    gc.collect()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"check_jax_export_stack.py: {exc}", file=sys.stderr)
        raise
