"""Focused tests for shared-runtime manifest metadata validation."""

# @dependency-start
# contract test
# responsibility Verifies typed live/static integration metadata and fail-closed validation.
# upstream implementation ../../tools/agent_tools/surface_manifest.py parses shared-runtime metadata
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns the selection contract
# @dependency-end

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-surface-manifest"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import (  # noqa: E402
    SurfaceSelection,
    load_manifest,
    main,
    normalized_snapshot,
)


class SurfaceManifestMetadataTest(unittest.TestCase):
    """Verify explicit live/static metadata is typed and validated."""

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Keep test-only manifest fixtures below the clone's temp boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    def test_live_manifest_metadata_is_typed(self) -> None:
        """The checked-in live manifest exposes its selection metadata."""
        manifest = load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )

        self.assertEqual(manifest.integration_mode, "live-agent-canon")
        self.assertFalse(manifest.default_consumer)
        self.assertEqual(manifest.selection, "explicit-opt-in")
        self.assertIsInstance(manifest.surface_selection, SurfaceSelection)
        # The normalized snapshot remains the exact v1 DTO consumed by Rust;
        # selection metadata is represented by the typed manifest above.
        self.assertEqual(
            normalized_snapshot(manifest)["schema"], "agent-canon.surface-manifest.v1"
        )

    def test_invalid_metadata_is_rejected(self) -> None:
        """Unknown enum values, non-booleans, and inconsistent selections fail closed."""
        cases = (
            ("integration_mode = \"unknown\"\n", "invalid integration_mode"),
            ("selection = \"unknown\"\n", "invalid selection"),
            ("default_consumer = \"false\"\n", "default_consumer must be a boolean"),
            (
                "default_consumer = true\n",
                "live-agent-canon integration must not be the default consumer",
            ),
            (
                "selection = \"default\"\n",
                "live-agent-canon integration requires explicit-opt-in selection",
            ),
        )
        for replacement, expected in cases:
            with (
                self.subTest(replacement=replacement),
                self.temporary_directory() as tmp_dir,
            ):
                root = Path(tmp_dir)
                manifest_path = root / "manifest.toml"
                manifest_text = (
                    "version = 1\n"
                    'prefix = "vendor/agent-canon"\n'
                    'integration_mode = "live-agent-canon"\n'
                    "default_consumer = false\n"
                    'selection = "explicit-opt-in"\n'
                )
                key = replacement.split(" = ", 1)[0]
                manifest_text = "\n".join(
                    replacement.rstrip() if line.startswith(f"{key} =") else line
                    for line in manifest_text.splitlines()
                ) + "\n"
                manifest_path.write_text(manifest_text, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    load_manifest(root, ".", "manifest.toml")

    def test_invalid_static_metadata_combinations_are_rejected(self) -> None:
        """Static mode cannot weaken its default-consumer and selection contract."""
        cases = (
            ("default_consumer = false\n", "static-seed integration must be the default consumer"),
            ("selection = \"explicit-opt-in\"\n", "static-seed integration must be the default consumer"),
        )
        for replacement, expected in cases:
            with (
                self.subTest(replacement=replacement),
                self.temporary_directory() as tmp_dir,
            ):
                root = Path(tmp_dir)
                manifest_text = (
                    "version = 1\n"
                    'prefix = "vendor/agent-canon"\n'
                    'integration_mode = "static-seed"\n'
                    "default_consumer = true\n"
                    'selection = "default"\n'
                )
                key = replacement.split(" = ", 1)[0]
                manifest_text = "\n".join(
                    replacement.rstrip() if line.startswith(f"{key} =") else line
                    for line in manifest_text.splitlines()
                ) + "\n"
                (root / "manifest.toml").write_text(manifest_text, encoding="utf-8")

                with self.assertRaisesRegex(ValueError, expected):
                    load_manifest(root, ".", "manifest.toml")

    def test_unannotated_v1_manifest_uses_historical_live_selection(self) -> None:
        """Old v1 pins remain live only when all new metadata is absent."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'version = 1\n'
                'prefix = "vendor/agent-canon"\n\n'
                '[[surface]]\n'
                'path = "AGENTS.md"\n'
                'mode = "symlink"\n'
                'source = "ROOT_AGENTS.md"\n'
                'projection_producer = "agent-canon"\n'
                'projection_kind = "runtime_surface"\n',
                encoding="utf-8",
            )

            manifest = load_manifest(root, ".", "manifest.toml")

            self.assertEqual(manifest.integration_mode, "live-agent-canon")
            self.assertFalse(manifest.default_consumer)
            self.assertEqual(manifest.selection, "explicit-opt-in")

    def test_unannotated_manifest_requires_exact_legacy_version(self) -> None:
        """Only an explicitly declared integer version 1 gets legacy compatibility."""
        cases = (
            ("", "version = 1 is required"),
            ("version = 2\n", "integration metadata is required for non-v1"),
            ('version = "1"\n', "version must be an integer"),
        )
        for version, expected in cases:
            with (
                self.subTest(version=version),
                self.temporary_directory() as tmp_dir,
            ):
                root = Path(tmp_dir)
                (root / "manifest.toml").write_text(
                    version
                    + 'prefix = "vendor/agent-canon"\n'
                    + '[[surface]]\n'
                    + 'path = "AGENTS.md"\n'
                    + 'mode = "symlink"\n'
                    + 'source = "ROOT_AGENTS.md"\n'
                    + 'projection_producer = "agent-canon"\n'
                    + 'projection_kind = "runtime_surface"\n',
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ValueError, expected):
                    load_manifest(root, ".", "manifest.toml")

    def test_cli_reports_missing_legacy_version(self) -> None:
        """The command-line path reports a missing legacy version instead of rendering specs."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'prefix = "vendor/agent-canon"\n'
                '[[surface]]\n'
                'path = "AGENTS.md"\n'
                'mode = "symlink"\n'
                'source = "ROOT_AGENTS.md"\n'
                'projection_producer = "agent-canon"\n'
                'projection_kind = "runtime_surface"\n',
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = main(
                    [
                        "--root",
                        str(root),
                        "--prefix",
                        ".",
                        "--manifest",
                        "manifest.toml",
                        "link-specs",
                    ]
                )

            self.assertEqual(result, 1)
            self.assertIn("version = 1 is required", stderr.getvalue())

    def test_partial_metadata_is_rejected(self) -> None:
        """A partially annotated v1 manifest cannot mix old and new contracts."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'version = 1\n'
                'prefix = "vendor/agent-canon"\n'
                'integration_mode = "live-agent-canon"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "integration metadata must be complete"):
                load_manifest(root, ".", "manifest.toml")

    def test_static_seed_metadata_combination_is_allowed(self) -> None:
        """The enum/boolean contract also accepts the source-free default mode."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                "version = 1\n"
                'prefix = "vendor/agent-canon"\n'
                'integration_mode = "static-seed"\n'
                "default_consumer = true\n"
                'selection = "default"\n',
                encoding="utf-8",
            )
            manifest = load_manifest(root, ".", "manifest.toml")

            self.assertEqual(manifest.integration_mode, "static-seed")
            self.assertTrue(manifest.default_consumer)
            self.assertEqual(manifest.selection, "default")

    def test_complete_metadata_is_not_rejected_for_missing_version(self) -> None:
        """Complete typed metadata does not take the unannotated legacy branch."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'prefix = "vendor/agent-canon"\n'
                'integration_mode = "static-seed"\n'
                "default_consumer = true\n"
                'selection = "default"\n',
                encoding="utf-8",
            )

            manifest = load_manifest(root, ".", "manifest.toml")

            self.assertEqual(manifest.surface_selection, SurfaceSelection("static-seed", True, "default"))

    def test_missing_metadata_is_rejected(self) -> None:
        """A partial metadata set is rejected rather than silently defaulted."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'version = 1\nprefix = "vendor/agent-canon"\n'
                "default_consumer = false\nselection = \"explicit-opt-in\"\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "integration metadata must be complete"):
                load_manifest(root, ".", "manifest.toml")

    def test_static_seed_cannot_render_sync_specs(self) -> None:
        """A static consumer cannot produce sync specs, including symlink specs."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "manifest.toml").write_text(
                'version = 1\n'
                'prefix = "vendor/agent-canon"\n'
                'integration_mode = "static-seed"\n'
                'default_consumer = true\n'
                'selection = "default"\n\n'
                '[[surface]]\n'
                'path = "AGENTS.md"\n'
                'mode = "symlink"\n'
                'source = "ROOT_AGENTS.md"\n'
                'projection_producer = "agent-canon"\n'
                'projection_kind = "runtime_surface"\n',
                encoding="utf-8",
            )

            for command in (
                "link-specs",
                "copy-specs",
                "update-transition-specs",
                "regular-specs",
                "removed-legacy-paths",
                "root-absent-paths",
            ):
                with self.subTest(command=command):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        result = main(
                            [
                                "--root",
                                str(root),
                                "--prefix",
                                ".",
                                "--manifest",
                                "manifest.toml",
                                command,
                            ]
                        )
                    self.assertEqual(result, 1)
                    self.assertIn("requires live-agent-canon,false,explicit-opt-in", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
