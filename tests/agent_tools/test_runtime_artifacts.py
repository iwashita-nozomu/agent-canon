"""Tests for the external AgentCanon runtime artifact boundary."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_tools.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactBoundary,
    RuntimePathEscape,
    RuntimeRootRequired,
    RuntimeSymlinkEscape,
    SourceLocalArtifact,
    resolve_runtime_root,
    root_capability_environment,
    runtime_spool_boundary,
)


class RuntimeArtifactBoundaryTest(unittest.TestCase):
    """Exercise explicit root, containment, atomic write, and source safety."""

    def test_requires_explicit_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            previous = os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
            try:
                with self.assertRaises(RuntimeRootRequired):
                    resolve_runtime_root(source)
            finally:
                if previous is not None:
                    os.environ["AGENT_CANON_RUNTIME_ROOT"] = previous

    def test_rejects_runtime_root_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            with self.assertRaises(SourceLocalArtifact):
                RuntimeArtifactBoundary.for_source(source, source / ".agent-canon", create=True)
            with self.assertRaises(SourceLocalArtifact):
                RuntimeArtifactBoundary.for_source(source, source / ".runtime", create=True)
            with self.assertRaises(SourceLocalArtifact):
                RuntimeArtifactBoundary.for_source(source, source, create=True)

    def test_source_runtime_spool_boundary_is_exact_and_narrow(self) -> None:
        """Only the canonical source runtime spool/control paths are admitted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            runtime = source / ".runtime"
            boundary = runtime_spool_boundary(source, runtime, create=True)

            self.assertEqual(boundary.root, runtime)
            self.assertEqual(boundary.resolve("spool/events"), runtime / "spool" / "events")
            self.assertEqual(boundary.resolve("locks/archive.lock"), runtime / "locks" / "archive.lock")
            with self.assertRaises(SourceLocalArtifact):
                boundary.resolve("archive/report.json")
            with self.assertRaises(SourceLocalArtifact):
                boundary.resolve("tasks/request.json")
            with self.assertRaises(SourceLocalArtifact):
                runtime_spool_boundary(source, source / "other-runtime", create=True)
            with self.assertRaises(SourceLocalArtifact):
                runtime_spool_boundary(source, source / "nested" / ".runtime", create=True)

    def test_source_runtime_spool_boundary_rejects_symlink_root(self) -> None:
        """A source runtime alias cannot redirect the spool capability."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            outside = root / "outside"
            source.mkdir()
            outside.mkdir()
            (source / ".runtime").symlink_to(outside, target_is_directory=True)

            with self.assertRaises(RuntimeSymlinkEscape):
                runtime_spool_boundary(source, source / ".runtime", create=True)

    def test_atomic_write_is_external_and_preserves_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            source_file = source / "tracked.txt"
            source.mkdir()
            source_file.write_bytes(b"source-before\n")
            before = source_file.read_bytes()
            boundary = RuntimeArtifactBoundary.for_source(source, runtime, create=True)

            written = boundary.atomic_write_text("tasks/run/receipt.json", "runtime\n")

            self.assertEqual(written, runtime / "tasks" / "run" / "receipt.json")
            self.assertEqual(written.read_text(encoding="utf-8"), "runtime\n")
            self.assertEqual(source_file.read_bytes(), before)
            self.assertEqual(
                [path for path in source.rglob("*") if path.is_file()],
                [source_file],
            )
            self.assertFalse(list(runtime.rglob("*.tmp")))

    def test_rejects_traversal_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            outside = root / "outside"
            source.mkdir()
            outside.mkdir()
            boundary = RuntimeArtifactBoundary.for_source(source, runtime, create=True)

            with self.assertRaises(RuntimePathEscape):
                boundary.resolve("../outside/escape.json")
            link = runtime / "link"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(RuntimeSymlinkEscape):
                boundary.atomic_write_text("link/escape.json", "must-fail\n")
            self.assertFalse((outside / "escape.json").exists())

    def test_environment_root_is_explicit_and_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir()
            old = os.environ.get("AGENT_CANON_RUNTIME_ROOT")
            try:
                os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
                self.assertEqual(resolve_runtime_root(source, create=True), runtime)
            finally:
                if old is None:
                    os.environ.pop("AGENT_CANON_RUNTIME_ROOT", None)
                else:
                    os.environ["AGENT_CANON_RUNTIME_ROOT"] = old

    def test_child_capability_environment_drops_host_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            source.mkdir()
            runtime.mkdir()
            environment = root_capability_environment(
                source_root=source,
                runtime_root=runtime,
                base_env={
                    "PATH": "/usr/bin",
                    "LANG": "C.UTF-8",
                    "OPENAI_API_KEY": "secret",
                    "HTTPS_PROXY": "https://user:password@example.invalid",
                    "GITHUB_TOKEN": "secret",
                },
            )
            self.assertEqual(environment["PATH"], "/usr/bin")
            self.assertEqual(environment["LANG"], "C.UTF-8")
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("HTTPS_PROXY", environment)
            self.assertNotIn("GITHUB_TOKEN", environment)


if __name__ == "__main__":
    unittest.main()
