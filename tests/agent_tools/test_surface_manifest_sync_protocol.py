"""Regression tests for the surface-manifest sync line protocol."""

# @dependency-start
# contract test
# responsibility Verifies empty sync sets cannot become checkout-root mutation records.
# upstream implementation ../../tools/agent_tools/surface_manifest.py validates and serializes sync targets
# upstream implementation ../../tools/sync_agent_canon.sh consumes newline-delimited sync records
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns parent root projection safety
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SURFACE_MANIFEST = PROJECT_ROOT / "tools" / "agent_tools" / "surface_manifest.py"
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-sync-spec-protocol"
EMPTY_SYNC_COMMANDS = (
    "copy-specs",
    "link-specs",
    "regular-specs",
    "removed-legacy-paths",
    "root-absent-paths",
    "update-transition-specs",
)


class SurfaceManifestSyncProtocolTest(unittest.TestCase):
    """Verify the producer language excludes the empty/root record."""

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Keep test repositories below AgentCanon's temporary boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    def write_manifest(self, root: Path, path: str | None = None) -> Path:
        """Write one minimal live-integration manifest."""
        lines = [
            "version = 1",
            'prefix = "."',
            'integration_mode = "live-agent-canon"',
            "default_consumer = false",
            'selection = "explicit-opt-in"',
        ]
        if path is not None:
            lines.extend(
                [
                    "",
                    "[[surface]]",
                    f"path = {json.dumps(path)}",
                    'mode = "regular"',
                    'projection_producer = "project"',
                    'projection_kind = "project_content"',
                    "local_override_allowed = true",
                ]
            )
        manifest = root / "manifest.toml"
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return manifest

    def run_manifest(
        self, root: Path, manifest: Path, command: str
    ) -> subprocess.CompletedProcess[str]:
        """Run one sync-protocol producer command."""
        return subprocess.run(
            [
                sys.executable,
                str(SURFACE_MANIFEST),
                "--root",
                str(root),
                "--prefix",
                ".",
                "--manifest",
                manifest.name,
                command,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_empty_sync_sets_emit_zero_bytes(self) -> None:
        """The empty set is EOF, never one empty line record."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            manifest = self.write_manifest(root)

            for command in EMPTY_SYNC_COMMANDS:
                with self.subTest(command=command):
                    result = self.run_manifest(root, manifest, command)
                    self.assertEqual(
                        result.returncode,
                        0,
                        result.stdout + result.stderr,
                    )
                    self.assertEqual(result.stdout, "")

    def test_legacy_consumer_preserves_absolute_workspace_root(self) -> None:
        """A 6d6ab427-style loop receives no record and cannot delete root."""
        with self.temporary_directory() as tmp_dir:
            workspace = Path(tmp_dir) / "workspace"
            git_dir = workspace / ".git"
            git_dir.mkdir(parents=True)
            sentinel = git_dir / "HEAD"
            sentinel.write_text("ref: refs/heads/main\n", encoding="utf-8")
            manifest = self.write_manifest(workspace)
            produced = self.run_manifest(workspace, manifest, "regular-specs")
            self.assertEqual(
                produced.returncode,
                0,
                produced.stdout + produced.stderr,
            )

            legacy = subprocess.run(
                [
                    "bash",
                    "-c",
                    """
                    set -euo pipefail
                    ROOT_DIR="$1"
                    while IFS= read -r spec; do
                      path="${spec%%:*}"
                      rm -rf -- "$ROOT_DIR/$path"
                    done
                    """,
                    "legacy-consumer",
                    str(workspace),
                ],
                input=produced.stdout,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertTrue(workspace.is_dir())
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "ref: refs/heads/main\n",
            )

    def test_unsafe_targets_fail_before_output_or_mutation(self) -> None:
        """Only normalized, task-declared strict descendants enter the protocol."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            sentinel = root / "parent-owned.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")
            unsafe_paths = (
                "",
                ".",
                "/",
                str(root),
                "../outside",
                "nested/../../outside",
                "nested//target",
                "nested/",
                ".git",
                ".git/config",
                "target:other",
                r"target\other",
            )

            for unsafe_path in unsafe_paths:
                with self.subTest(path=unsafe_path):
                    manifest = self.write_manifest(root, unsafe_path)
                    result = self.run_manifest(root, manifest, "regular-specs")
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(
                        "SURFACE_MANIFEST_ERROR=surface path must be a "
                        "normalized non-root repository-relative POSIX path",
                        result.stderr,
                    )
                    self.assertEqual(
                        sentinel.read_text(encoding="utf-8"),
                        "preserve\n",
                    )

    def test_valid_target_is_exactly_one_nonempty_record(self) -> None:
        """A valid record retains the existing trailing-newline protocol."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            manifest = self.write_manifest(root, "safe/target")

            result = self.run_manifest(root, manifest, "regular-specs")

            self.assertEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            self.assertEqual(result.stdout, "safe/target:\n")


if __name__ == "__main__":
    unittest.main()
