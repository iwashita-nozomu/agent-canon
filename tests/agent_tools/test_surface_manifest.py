"""Focused tests for standalone runtime surface classification."""

# @dependency-start
# contract test
# responsibility Verifies standalone runtime inventory parsing and graph snapshot output.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/surface_manifest.rs parses runtime metadata
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns the reader boundary
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class SurfaceManifestTest(unittest.TestCase):
    """Verify source inventory behavior without parent synchronization."""

    def test_runtime_inventory_snapshot(self) -> None:
        result = self.run_surface(
            "--root", str(PROJECT_ROOT), "--prefix", ".", "normalized-snapshot"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "agent-canon.surface-manifest.v2")
        self.assertEqual(payload["prefix"], ".")
        self.assertTrue(payload["entries"])
        projections = cast(list[dict[str, str]], payload["generated_projections"])
        projection_paths = [projection["path"] for projection in projections]
        self.assertTrue(projections)
        self.assertEqual(projection_paths, sorted(projection_paths))
        self.assertEqual(len(projection_paths), len(set(projection_paths)))
        self.assertTrue(
            all(
                projection["projection_producer"] == "agent-canon-bootstrap"
                for projection in projections
            )
        )
        self.assertTrue(
            all(
                entry["mode"] in {"runtime", "tool", "eval"}
                for entry in payload["entries"]
            )
        )
        projections = {
            entry["path"]: entry for entry in payload["generated_projections"]
        }
        self.assertEqual(
            projections[".codex/personal/skills/agent-orchestration/SKILL.md"][
                "source"
            ],
            "agents/skills/agent-orchestration.md",
        )
        self.assertEqual(
            projections[".codex/personal/skills/_chatgpt-codex-routing/SKILL.md"][
                "source"
            ],
            "agents/internal-routines/chatgpt-codex-routing.md",
        )

    def test_sync_commands_are_not_exposed(self) -> None:
        result = self.run_surface("link-specs")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)

    def test_duplicate_private_projection_owner_is_typed_ambiguity(self) -> None:
        """A private shim with two routine owners must not use first-wins resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for name in ("one.md", "two.md"):
                path = root / "agents" / "internal-routines" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"downstream implementation ../../.codex/personal/skills/_duplicate/SKILL.md {name}\n",
                    encoding="utf-8",
                )
            (root / "manifest.toml").write_text(
                'version = 1\nintegration_mode = "agent-canon-runtime"\nselection = "explicit-opt-in"\n',
                encoding="utf-8",
            )
            result = self.run_surface(
                "--root",
                str(root),
                "--manifest",
                "manifest.toml",
                "normalized-snapshot",
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "generated_projection_ambiguous:.codex/personal/skills/_duplicate/SKILL.md:agents/internal-routines/one.md,agents/internal-routines/two.md",
                result.stderr,
            )

    def test_invalid_runtime_producer_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'version = 1\nprefix = "."\nintegration_mode = "agent-canon-runtime"\n'
                'default_consumer = true\nselection = "default"\n\n'
                '[[surface]]\npath = "bootstrap"\nmode = "runtime"\n'
                'projection_producer = "legacy"\nprojection_kind = "runtime_surface"\n',
                encoding="utf-8",
            )
            result = self.run_surface(
                "--root",
                str(root),
                "--prefix",
                ".",
                "--manifest",
                "manifest.toml",
                "normalized-snapshot",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported runtime surface producer", result.stderr)

    def test_native_snapshot_does_not_require_python_on_path(self) -> None:
        """The selected native CLI needs only source data for the default snapshot."""
        result = self.run_surface(
            "--root",
            str(PROJECT_ROOT),
            "normalized-snapshot",
            env={**os.environ, "PATH": ""},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["schema"], "agent-canon.surface-manifest.v2"
        )

    def run_surface(
        self, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Select the current built executable explicitly; never use a global stale CLI."""
        self.assertIsNotNone(
            AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
        )
        executable = Path(str(AGENT_CANON_CLI))
        self.assertTrue(
            executable.is_absolute(),
            "AGENT_CANON_CLI must be an absolute executable path",
        )
        return subprocess.run(
            [str(executable), "surface-manifest", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )


if __name__ == "__main__":
    unittest.main()
