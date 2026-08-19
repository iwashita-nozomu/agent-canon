"""Focused regression tests for the live Rust projection boundary."""

# @dependency-start
# contract test
# responsibility Verifies that Rust/Cargo standalone source cannot become a live parent projection or cleanup path.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns Rust and parent-artifact classification
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml declares projection-forbidden roots
# upstream implementation ../../tools/agent_tools/surface_manifest.py rejects intersecting targets, sources, and transitions
# downstream implementation ../../tools/sync_agent_canon.sh consumes only validated manifest renderers
# @dependency-end

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-rust-projection-boundary"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import (  # noqa: E402
    entry_source_for_projection_policy,
    load_manifest,
    main,
    normalized_snapshot,
    path_intersects_root,
    render_actionable_root_absent_paths,
    render_root_absent_paths,
)


class RustProjectionBoundaryTest(unittest.TestCase):
    """Verify that standalone Rust ownership cannot enter live projection data."""

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Keep generated fixtures below the repository local-state boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    @staticmethod
    def manifest_header() -> str:
        """Return a minimal explicit-live manifest with the Rust exclusion."""
        return (
            "version = 1\n"
            'prefix = "vendor/agent-canon"\n'
            'integration_mode = "live-agent-canon"\n'
            "default_consumer = false\n"
            'selection = "explicit-opt-in"\n'
            'projection_forbidden_roots = ["rust"]\n\n'
        )

    def write_manifest(self, root: Path, body: str) -> None:
        """Write one temporary manifest."""
        (root / "manifest.toml").write_text(
            self.manifest_header() + body,
            encoding="utf-8",
        )

    def checked_in_manifest(self):
        """Load the exact live manifest under test."""
        return load_manifest(
            PROJECT_ROOT,
            ".",
            "documents/runtime/shared-runtime-surfaces.toml",
        )

    def assert_manifest_rejected(self, body: str, finding: str) -> None:
        """Assert one manifest fails with the expected projection finding."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_manifest(root, body)
            with self.assertRaisesRegex(ValueError, finding):
                load_manifest(root, ".", "manifest.toml")

    def test_checked_in_contract_has_empty_rust_intersection(self) -> None:
        """Targets, sources, transitions, cleanup, and the v1 snapshot exclude Rust."""
        manifest = self.checked_in_manifest()
        self.assertEqual(manifest.projection_forbidden_roots, ("rust",))
        for entry in manifest.entries:
            with self.subTest(path=entry.path, field="target"):
                self.assertFalse(path_intersects_root(entry.path, "rust"))
            source = entry_source_for_projection_policy(entry)
            if source:
                with self.subTest(path=entry.path, field="source"):
                    self.assertFalse(path_intersects_root(source, "rust"))
        for transition in manifest.update_transitions:
            for candidate in transition.candidates:
                self.assertFalse(path_intersects_root(candidate.path, "rust"))

        snapshot = normalized_snapshot(manifest)
        self.assertEqual(snapshot["schema"], "agent-canon.surface-manifest.v1")
        self.assertNotIn("projection_forbidden_roots", snapshot)
        root_absent = set(render_root_absent_paths(manifest.entries).splitlines())
        self.assertFalse(any(path == "rust" or path.startswith("rust/") for path in root_absent))

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = main(
                [
                    "--root",
                    str(PROJECT_ROOT),
                    "--prefix",
                    ".",
                    "--manifest",
                    "documents/runtime/shared-runtime-surfaces.toml",
                    "projection-forbidden-roots",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().splitlines(), ["rust"])

    def test_every_ownership_mode_rejects_a_rust_target(self) -> None:
        """Active, state, standalone, and cleanup modes cannot claim Rust paths."""
        cases = (
            ("symlink", "agent-canon", "runtime_surface", 'source = "ROOT_AGENTS.md"\n'),
            ("copy", "agent-canon", "runtime_surface", 'source = "ROOT_AGENTS.md"\n'),
            ("regular", "template", "shared_template", 'source = "ROOT_AGENTS.md"\n'),
            ("repo_state", "agent-canon-update", "transaction_state", ""),
            ("standalone_only", "agent-canon-standalone", "standalone_only", ""),
            ("removed_legacy", "legacy", "removed_legacy", ""),
        )
        for mode, producer, kind, source in cases:
            with self.subTest(mode=mode):
                self.assert_manifest_rejected(
                    "[[surface]]\n"
                    'path = "rust/agent-canon"\n'
                    f'mode = "{mode}"\n'
                    + source
                    + f'projection_producer = "{producer}"\n'
                    + f'projection_kind = "{kind}"\n',
                    "manifest-owned path intersects projection-forbidden root rust",
                )

    def test_rust_sources_and_update_candidates_are_rejected(self) -> None:
        """Aliases and history-bound cleanup cannot acquire standalone Rust bytes."""
        for mode, producer, kind in (
            ("symlink", "agent-canon", "runtime_surface"),
            ("copy", "agent-canon", "runtime_surface"),
            ("regular", "template", "shared_template"),
        ):
            with self.subTest(mode=mode):
                self.assert_manifest_rejected(
                    "[[surface]]\n"
                    'path = ".agent-canon-rust-view"\n'
                    f'mode = "{mode}"\n'
                    'source = "rust/agent-canon"\n'
                    f'projection_producer = "{producer}"\n'
                    f'projection_kind = "{kind}"\n',
                    "source rust/agent-canon intersects projection-forbidden root rust",
                )

        self.assert_manifest_rejected(
            "[[update_transition]]\n"
            'id = "retire-rust-copy"\n'
            'from_agent_canon_pins = ["0000000000000000000000000000000000000000"]\n\n'
            "[[update_transition.candidate]]\n"
            'path = "rust/agent-canon/tests/python_algorithm_contract_cli.rs"\n\n'
            "[[update_transition.candidate.identity]]\n"
            'kind = "regular"\n'
            'git_blob = "1111111111111111111111111111111111111111"\n'
            'content_sha256 = "2222222222222222222222222222222222222222222222222222222222222222"\n'
            'git_mode = "100644"\n'
            'symlink_target = ""\n',
            "update transition candidate intersects projection-forbidden root rust",
        )

    def test_sync_preflight_emits_no_rust_spec(self) -> None:
        """Sync renderers fail before output instead of maintaining a shell allowlist."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_manifest(
                root,
                "[[surface]]\n"
                'path = ".agent-canon-rust-view"\n'
                'mode = "symlink"\n'
                'source = "rust/agent-canon"\n'
                'projection_producer = "agent-canon"\n'
                'projection_kind = "runtime_surface"\n',
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
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
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("projection-forbidden root rust", stderr.getvalue())

    def test_parent_regular_rust_content_is_not_cleanup_owned(self) -> None:
        """The exclusion preserves regular parent bytes and documents owner routing."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            artifact = root / "rust" / "agent-canon" / "tests" / "fixture.rs"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("// parent-owned historical artifact\n", encoding="utf-8")
            self.write_manifest(root, "")
            manifest = load_manifest(root, ".", "manifest.toml")
            self.assertEqual(render_actionable_root_absent_paths(manifest.entries, root), "")
            self.assertTrue(artifact.is_file())
            self.assertFalse(artifact.is_symlink())

        document = (
            PROJECT_ROOT / "documents" / "runtime" / "SHARED_RUNTIME_SURFACES.md"
        ).read_text(encoding="utf-8")
        for marker in (
            "parent-owned regular directory or file",
            "generated copy",
            "symlink resolving into",
            "gitlink / submodule",
            "tools/ci/run_standalone_static_gate_unit.sh",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, document)


if __name__ == "__main__":
    unittest.main()
