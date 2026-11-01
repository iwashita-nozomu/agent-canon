# @dependency-start
# contract test
# responsibility Exercises the native docs link route and its exact source-mutation capability behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs native links command
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/source_mutation.rs exact source mutation capability
# downstream test ../../tools/runtime/dispatch/agent-canon/tests/source_mutation_native.rs capability boundary regressions
# @dependency-end
"""Native docs link route and source-mutation CLI regressions."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = PROJECT_ROOT / "tools" / "bin" / "agent-canon"
NATIVE_BIN_CANDIDATES = (
    PROJECT_ROOT / "tools/runtime/dispatch/agent-canon/target/release/agent-canon",
    PROJECT_ROOT / "tools/runtime/dispatch/agent-canon/target/debug/agent-canon",
)


class AuditAndFixLinksTest(unittest.TestCase):
    """Keep the former wrapper's four read-only/apply purposes on the Rust route."""

    def write_file(self, path: Path, contents: str) -> None:
        """Create one task-owned source fixture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def native_binary(self) -> Path:
        """Return the built native binary selected by the existing wrapper."""
        configured = os.environ.get("AGENT_CANON_NATIVE_BIN")
        candidates = (Path(configured),) if configured else NATIVE_BIN_CANDIDATES
        binary = next(
            (
                path
                for path in candidates
                if path.is_file() and os.access(path, os.X_OK)
            ),
            None,
        )
        if binary is None:
            self.fail("native agent-canon binary must be built before this source test")
        return binary

    def run_links(
        self, args: list[str], *, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run the stable command wrapper with the requested docs arguments."""
        return subprocess.run(
            [str(CLI_PATH), "docs", "links", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_check_uses_native_read_only_route_without_report_write(self) -> None:
        """Read-only link checks run in the native docs owner and create no report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = self.run_links(["--root", str(root), "--check", "missing.md"])
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse((root / "reports").exists())

    def test_selected_native_binary_override_runs_without_source_output(self) -> None:
        """The stable wrapper can select the immutable native executable directly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            environment = os.environ.copy()
            environment["AGENT_CANON_NATIVE_BIN"] = str(self.native_binary())
            environment["AGENT_CANON_SOURCE_ROOT"] = str(PROJECT_ROOT)
            completed = self.run_links(
                ["--root", str(root), "missing.md"], env=environment
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse((root / "reports").exists())

    def test_apply_requires_capability_and_preserves_source_on_failure(self) -> None:
        """An apply request without the exact source capability fails before writing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            guide = root / "docs" / "guide.md"
            self.write_file(guide, "[root](README.md)\n")
            before = guide.read_bytes()

            completed = self.run_links(["--root", str(root), "--apply", "docs"])

            self.assertEqual(completed.returncode, 2)
            self.assertEqual(guide.read_bytes(), before)
            self.assertFalse((root / "reports").exists())

    def test_apply_rewrites_only_capability_bound_source_file(self) -> None:
        """The explicit capability rewrites one allowed file and leaves adjacent source intact."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            guide = root / "docs" / "guide.md"
            untouched = root / "docs" / "untouched.md"
            self.write_file(guide, "[root](README.md)\n")
            self.write_file(untouched, "# Untouched\n")
            capability = (
                '{"allowed_paths":["docs/guide.md"],'
                '"purpose":"test","authority":"issue-1630"}'
            )

            completed = self.run_links(
                [
                    "--root",
                    str(root),
                    "--apply",
                    "--mutation-capability-json",
                    capability,
                    "docs",
                ]
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                guide.read_text(encoding="utf-8"), "[root](../README.md)\n"
            )
            self.assertEqual(untouched.read_text(encoding="utf-8"), "# Untouched\n")
            self.assertFalse((root / "reports").exists())


if __name__ == "__main__":
    unittest.main()
