"""Regression tests for task-owned canonical deletion targets."""

# @dependency-start
# contract test
# responsibility Verifies parent projection deletion targets are admitted as canonical strict descendants before mutation.
# upstream implementation ../../tools/agent_tools/surface_manifest.py owns deletion target generation, normalization, and admission
# upstream implementation ../../tools/sync_agent_canon.sh consumes admitted root-absence records
# upstream implementation ../../tools/update_agent_canon.sh routes latest through sync ensure-latest
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns parent root projection safety
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-deletion-targets"
SURFACE_MANIFEST = PROJECT_ROOT / "tools" / "agent_tools" / "surface_manifest.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import ROOT_ABSENCE_TASK, load_manifest  # noqa: E402


class DeletionTargetTest(unittest.TestCase):
    """Exercise the sole deletion-target owner and line protocol."""

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Keep fixtures below AgentCanon's repository-owned temp boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    def write_manifest(
        self,
        root: Path,
        *,
        root_absent_paths: tuple[str, ...] = (),
        transition_paths: tuple[str, ...] = (),
    ) -> Path:
        """Write one minimal live-integration manifest."""
        lines = [
            "version = 1",
            'prefix = "."',
            'integration_mode = "live-agent-canon"',
            "default_consumer = false",
            'selection = "explicit-opt-in"',
        ]
        for path in root_absent_paths:
            lines.extend(
                [
                    "",
                    "[[surface]]",
                    f"path = {json.dumps(path)}",
                    'mode = "removed_legacy"',
                    'projection_producer = "legacy"',
                    'projection_kind = "removed_legacy"',
                    "local_override_allowed = false",
                ]
            )
        previous_pin = "a" * 40
        git_blob = "b" * 40
        content_sha256 = "c" * 64
        for index, path in enumerate(transition_paths):
            lines.extend(
                [
                    "",
                    "[[update_transition]]",
                    f'id = "fixture-{index}"',
                    f'from_agent_canon_pins = ["{previous_pin}"]',
                    "",
                    "[[update_transition.candidate]]",
                    f"path = {json.dumps(path)}",
                    "",
                    "[[update_transition.candidate.identity]]",
                    'kind = "regular"',
                    f'git_blob = "{git_blob}"',
                    f'content_sha256 = "{content_sha256}"',
                    'git_mode = "100644"',
                    'symlink_target = ""',
                ]
            )
        manifest = root / "manifest.toml"
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return manifest

    def run_manifest(
        self, root: Path, manifest: Path, command: str
    ) -> subprocess.CompletedProcess[str]:
        """Run one surface-manifest producer command."""
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

    def assert_rejected(self, root: Path, path: str) -> None:
        """Assert one root-absence claim is rejected without side effects."""
        sentinel = root / "parent-owned.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        manifest = self.write_manifest(
            root, root_absent_paths=(path,)
        )
        result = self.run_manifest(root, manifest, "root-absent-paths")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("SURFACE_MANIFEST_ERROR=", result.stderr)
        self.assertEqual(
            sentinel.read_text(encoding="utf-8"), "preserve\n"
        )

    def test_empty_sets_emit_zero_records(self) -> None:
        """An empty deletion set is EOF, never one empty record."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            manifest = self.write_manifest(root)
            for command in (
                "root-absent-paths",
                "removed-legacy-paths",
                "update-transition-specs",
            ):
                with self.subTest(command=command):
                    result = self.run_manifest(root, manifest, command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_unsafe_spellings_fail_closed(self) -> None:
        """Roots, absolute paths, and lexical escapes are rejected."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            unsafe_paths = (
                "",
                ".",
                "/",
                str(root.resolve()),
                "../outside",
                "nested/../../outside",
                "nested//retired",
                "nested/",
                "./retired",
                "line\nbreak",
                "tab\tbreak",
            )
            for path in unsafe_paths:
                with self.subTest(path=path):
                    self.assert_rejected(root, path)

    def test_intermediate_symlink_escape_fails_closed(self) -> None:
        """Canonical parent resolution rejects repository escapes."""
        with self.temporary_directory() as tmp_dir:
            sandbox = Path(tmp_dir)
            root = sandbox / "checkout"
            outside = sandbox / "outside"
            root.mkdir()
            outside.mkdir()
            os.symlink(outside, root / "outside-alias")
            self.assert_rejected(root, "outside-alias/retired")

    def test_final_symlink_is_admitted_as_an_lstat_leaf(self) -> None:
        """Admission does not dereference the leaf that removal unlinks."""
        with self.temporary_directory() as tmp_dir:
            sandbox = Path(tmp_dir)
            root = sandbox / "checkout"
            outside = sandbox / "outside"
            root.mkdir()
            outside.mkdir()
            os.symlink(outside, root / "retired")
            manifest_path = self.write_manifest(
                root, root_absent_paths=("retired",)
            )
            manifest = load_manifest(root, ".", manifest_path.name)
            target = manifest.deletion_targets[0]
            self.assertEqual(
                target.canonical_path, root.resolve() / "retired"
            )
            result = self.run_manifest(
                root, manifest_path, "root-absent-paths"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "retired\n")

    def test_safe_target_carries_owner_and_canonical_descendant(self) -> None:
        """An admitted target records ownership and strict containment."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            retired = root / "retired" / "path"
            retired.parent.mkdir()
            retired.write_text("legacy\n", encoding="utf-8")
            manifest_path = self.write_manifest(
                root, root_absent_paths=("retired/path",)
            )
            manifest = load_manifest(root, ".", manifest_path.name)
            target = manifest.deletion_targets[0]
            self.assertEqual(target.task, ROOT_ABSENCE_TASK)
            self.assertTrue(target.owner.startswith("surface:"))
            self.assertEqual(target.path, "retired/path")
            self.assertNotEqual(target.canonical_path, root.resolve())
            self.assertEqual(
                target.canonical_path.relative_to(root.resolve()),
                Path("retired/path"),
            )
            result = self.run_manifest(
                root, manifest_path, "root-absent-paths"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "retired/path\n")

    def test_update_transition_uses_the_same_owner(self) -> None:
        """Transition candidates cannot bypass deletion admission."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            rejected_manifest = self.write_manifest(
                root, transition_paths=(".",)
            )
            rejected = self.run_manifest(
                root, rejected_manifest, "update-transition-specs"
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertEqual(rejected.stdout, "")
            self.assertIn("SURFACE_MANIFEST_ERROR=", rejected.stderr)

            accepted_manifest = self.write_manifest(
                root, transition_paths=("legacy/retired",)
            )
            accepted = self.run_manifest(
                root, accepted_manifest, "update-transition-specs"
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn(
                "\tlegacy/retired\tregular\t", accepted.stdout
            )

    def test_workspace_checkout_survives_legacy_empty_record_loop(self) -> None:
        """A /workspace-style root receives no empty deletion record."""
        with self.temporary_directory() as tmp_dir:
            workspace = Path(tmp_dir) / "workspace"
            git_dir = workspace / ".git"
            git_dir.mkdir(parents=True)
            sentinel = git_dir / "HEAD"
            sentinel.write_text(
                "ref: refs/heads/main\n", encoding="utf-8"
            )
            manifest = self.write_manifest(workspace)
            produced = self.run_manifest(
                workspace, manifest, "root-absent-paths"
            )
            self.assertEqual(produced.returncode, 0, produced.stderr)
            self.assertEqual(produced.stdout, "")
            consumed = subprocess.run(
                [
                    "bash",
                    "-c",
                    """
                    set -euo pipefail
                    ROOT_DIR="$1"
                    while IFS= read -r path; do
                      rm -rf -- "$ROOT_DIR/$path"
                    done
                    """,
                    "legacy-root-absence-consumer",
                    str(workspace),
                ],
                input=produced.stdout,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(consumed.returncode, 0, consumed.stderr)
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "ref: refs/heads/main\n",
            )

    def test_parent_front_doors_share_the_admitted_producer(self) -> None:
        """Ensure-latest and update latest retain one parent projection route."""
        sync_text = (
            PROJECT_ROOT / "tools" / "sync_agent_canon.sh"
        ).read_text(encoding="utf-8")
        update_text = (
            PROJECT_ROOT / "tools" / "update_agent_canon.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "root-absent-paths",
            sync_text[sync_text.index("build_root_absent_paths() {"):],
        )
        self.assertIn("done < <(build_root_absent_paths)", sync_text)
        self.assertIn(
            'run_parent_bound_sync ensure-latest "$branch"',
            update_text,
        )


if __name__ == "__main__":
    unittest.main()
