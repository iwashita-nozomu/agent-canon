#!/usr/bin/env python3
"""Smoke-check the local jax.export stack and jaxlib C++ headers."""

from __future__ import annotations

import pathlib
import sys

import jax
import jax.numpy as jnp
import jaxlib
from jax import export as jax_export


def main() -> int:
    """Validate that jax.export and jaxlib headers are available."""
    include_dir = pathlib.Path(jaxlib.__file__).resolve().parent / "include"
    ffi_c_api = include_dir / "xla" / "ffi" / "api" / "c_api.h"
    ffi_cpp_api = include_dir / "xla" / "ffi" / "api" / "ffi.h"
    if not include_dir.is_dir():
        raise FileNotFoundError(f"jaxlib include directory not found: {include_dir}")
    if not ffi_c_api.is_file():
        raise FileNotFoundError(f"missing XLA FFI C API header: {ffi_c_api}")
    if not ffi_cpp_api.is_file():
        raise FileNotFoundError(f"missing XLA FFI C++ API header: {ffi_cpp_api}")

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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"check_jax_export_stack.py: {exc}", file=sys.stderr)
        raise
