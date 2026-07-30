"""Focused tests for projection byte validation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "agent_tools"))
from execution_resource_projection import ProjectionError, validate_projection_bytes  # noqa: E402


class ExecutionResourceProjectionTest(unittest.TestCase):
    def test_rejects_oversized_projection(self) -> None:
        with self.assertRaises(ProjectionError):
            validate_projection_bytes("x" * (65 * 1024))


if __name__ == "__main__":
    unittest.main()
