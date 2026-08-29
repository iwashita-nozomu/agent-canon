"""Tests for canonical artifact byte identity materialization."""

# @dependency-start
# contract test
# responsibility Tests exact artifact identity and stable source readback.
# upstream implementation ../../tools/runtime/artifacts/artifact_identity.py materializes and verifies artifact identities
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.runtime.artifacts.artifact_identity import (  # noqa: E402
    ArtifactIdentityError,
    canonical_json_bytes,
    materialize_artifact_identity,
    verify_identity_record,
)


class ArtifactIdentityTest(unittest.TestCase):
    """Verify exact bytes remain the only artifact identity authority."""

    def test_materialize_and_verify_current_source(self) -> None:
        """A tracked source file round-trips through identity readback."""
        record = materialize_artifact_identity(
            PROJECT_ROOT,
            Path("tools/runtime/artifacts/artifact_identity.py"),
        )

        verified = verify_identity_record(PROJECT_ROOT, record)

        self.assertTrue(verified["ok"])
        self.assertEqual(
            verified["artifact_path"], "tools/runtime/artifacts/artifact_identity.py"
        )
        self.assertEqual(verified["identity_record_id"], record["identity_record_id"])

    def test_canonical_json_rejects_floating_point_identity_fields(self) -> None:
        """Identity serialization rejects values outside the closed schema domain."""
        with self.assertRaises(ArtifactIdentityError) as raised:
            canonical_json_bytes({"value": 1.5})

        self.assertEqual(raised.exception.code, "artifact_identity:float_forbidden")


if __name__ == "__main__":
    unittest.main()
