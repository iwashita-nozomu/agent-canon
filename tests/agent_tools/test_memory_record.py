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
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = PROJECT_ROOT / "tools" / "agent_tools" / "memory_record.py"


def test_memory_adapter_validates_repository_records() -> None:
    """The adapter forwards validate and returns the Rust CLI result."""
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "validate", "--root", str(PROJECT_ROOT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "MEMORY_RECORD_VALIDATION=pass" in result.stdout


def test_memory_adapter_contains_no_record_schema_logic() -> None:
    """Schema and parser terms stay out of the Python adapter."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert "Problem/Symptom" not in source
    assert "record_schema" not in source
    assert "duplicate" not in source
