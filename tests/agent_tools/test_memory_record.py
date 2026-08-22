#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Verifies that the Python memory adapter transports validation to the Rust CLI.
# upstream implementation ../../tools/agent_tools/memory_record.py is a thin adapter only.
# upstream implementation ../../rust/agent-canon/src/memory.rs owns memory semantics.
# downstream implementation ../../memory/README.md defines the record contract.
# @dependency-end

"""Smoke-test the Python-to-Rust memory CLI boundary."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = PROJECT_ROOT / "tools" / "agent_tools" / "memory_record.py"


def test_memory_adapter_forwards_validation_to_cli() -> None:
    """The adapter forwards validation without requiring the shared runtime.

    The runtime/container boundary is exercised by bootstrap tests.  This
    unit owns only the Python adapter contract, so a mocked subprocess keeps
    the test independent of a host Docker daemon and of external runtime
    state.
    """
    spec = __import__("importlib.util").util.spec_from_file_location(
        "memory_record_adapter", ADAPTER
    )
    assert spec is not None and spec.loader is not None
    module = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(module)
    completed = subprocess.CompletedProcess([], 0, "MEMORY_RECORD_VALIDATION=pass\n", "")

    with patch.object(module.subprocess, "run", return_value=completed) as run:
        with patch.object(module.sys, "argv", [str(ADAPTER), "validate", "--root", "."]):
            assert module.main() == 0

    run.assert_called_once()
    command, kwargs = run.call_args
    assert command[0] == [
        str(PROJECT_ROOT / "tools" / "bin" / "agent-canon"),
        "memory",
        "validate",
        "--root",
        ".",
    ]
    assert kwargs["cwd"] == PROJECT_ROOT
    assert kwargs["env"] == module.os.environ
    assert kwargs["check"] is False


def test_memory_adapter_contains_no_record_schema_logic() -> None:
    """Schema and parser terms stay out of the Python adapter."""
    source = ADAPTER.read_text(encoding="utf-8")
    implementation = source.split("# @dependency-end", 1)[1]
    assert "Problem/Symptom" not in implementation
    assert "record_schema" not in implementation
    assert "duplicate" not in implementation
