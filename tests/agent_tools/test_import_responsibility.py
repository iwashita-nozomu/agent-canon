"""Tests for import responsibility checks."""

# @dependency-start
# contract test
# responsibility Tests import responsibility validation.
# upstream implementation ../../tools/agent_tools/import_responsibility.py checks import boundaries
# upstream design ../../responsibility-scope.toml declares scope import rules
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "import_responsibility.py"


class ImportResponsibilityTest(unittest.TestCase):
    """Exercise the import responsibility checker."""

    def run_checker(self, root: Path, *paths: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), *paths],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """Changed canonical files should satisfy import responsibility rules."""
        result = self.run_checker(PROJECT_ROOT, "--changed")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IMPORT_RESPONSIBILITY=pass", result.stdout)

    def test_unused_import_fails(self) -> None:
        """Unused imported aliases should be rejected before ruff is needed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(
                root,
                "app/main.py",
                "import os\nimport sys\n\nVALUE = os.name\n",
            )

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("unused-import:app/main.py:2:name:sys:module:sys", result.stdout)

    def test_wildcard_import_fails(self) -> None:
        """Wildcard imports hide the actual dependency surface."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "app/main.py", "from app.lib import *\n")
            self.write_file(root, "app/lib.py", "VALUE = 1\n")

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("wildcard-import:app/main.py:1:module:app.lib", result.stdout)

    def test_scope_import_violation_fails(self) -> None:
        """A scope cannot import a local file outside its declared import rules."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "app/main.py", "import tools.helper\n\nVALUE = tools.helper.VALUE\n")
            self.write_file(root, "tools/helper.py", "VALUE = 1\n")

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("scope-import:app/main.py:1:app->tools", result.stdout)

    def test_duplicate_scope_import_findings_are_collapsed(self) -> None:
        """One import statement should emit one stable scope finding."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(
                root,
                "app/main.py",
                "from tools.helper import OTHER, VALUE\n\nRESULT = OTHER + VALUE\n",
            )
            self.write_file(root, "tools/helper.py", "OTHER = 1\nVALUE = 2\n")

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("IMPORT_RESPONSIBILITY_FINDING="), 1)
            self.assertIn("IMPORT_RESPONSIBILITY_FINDINGS=1", result.stdout)

    def test_allowed_scope_import_passes(self) -> None:
        """Declared import rules allow intentional local scope crossings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            self.write_file(root, "tests/test_main.py", "import app.lib\n\nVALUE = app.lib.VALUE\n")
            self.write_file(root, "app/lib.py", "VALUE = 1\n")

            result = self.run_checker(root, "tests/test_main.py")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("IMPORT_RESPONSIBILITY=pass", result.stdout)

    def test_symlinked_root_view_uses_source_scope(self) -> None:
        """Root-view symlinks should be scoped by their AgentCanon source."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_file(
                root,
                "responsibility-scope.toml",
                "\n".join(
                    [
                        'catalog_kind = "agent_canon_responsibility_scope"',
                        "version = 1",
                        "[[scope]]",
                        'id = "agent-canon-runtime-view"',
                        'paths = ["vendor/agent-canon/**", "tools"]',
                        "",
                        "[[scope]]",
                        'id = "template-active-contract"',
                        'paths = ["tests/**"]',
                        "",
                    ]
                ),
            )
            self.write_file(
                root,
                "vendor/agent-canon/tests/agent_tools/test_helper.py",
                "from tools.agent_tools.helper import VALUE\n\nRESULT = VALUE\n",
            )
            self.write_file(
                root,
                "vendor/agent-canon/tools/agent_tools/helper.py",
                "VALUE = 1\n",
            )
            (root / "tests" / "agent_tools").mkdir(parents=True)
            (root / "tools").symlink_to("vendor/agent-canon/tools", target_is_directory=True)
            (root / "tests" / "agent_tools" / "test_helper.py").symlink_to(
                "../../vendor/agent-canon/tests/agent_tools/test_helper.py"
            )

            result = self.run_checker(root, "tests/agent_tools/test_helper.py")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("IMPORT_RESPONSIBILITY=pass", result.stdout)

    def test_full_repo_scan_skips_ignored_vendor_log_archive_python_files(self) -> None:
        """Repository-wide scans should not inspect ignored AgentCanon log archives."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            self.write_file(
                root,
                ".gitignore",
                "vendor/agent-canon/.agent-canon/log-archive/\n",
            )
            self.write_file(
                root,
                "responsibility-scope.toml",
                "\n".join(
                    [
                        'catalog_kind = "agent_canon_responsibility_scope"',
                        "version = 1",
                        "[[scope]]",
                        'id = "app"',
                        'paths = ["app/**"]',
                        "",
                        "[[import_rule]]",
                        'source = "app"',
                        'targets = ["app"]',
                        "",
                    ]
                ),
            )
            self.write_file(root, "app/lib.py", "VALUE = 1\n")
            self.write_file(root, "app/main.py", "import app.lib as lib\n\nVALUE = lib.VALUE\n")
            self.write_file(
                root,
                "vendor/agent-canon/.agent-canon/log-archive/run/bad.py",
                "def invalid syntax:\n",
            )

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IMPORT_RESPONSIBILITY_FILES=2", result.stdout)
        self.assertNotIn("IMPORT_RESPONSIBILITY_FINDING=", result.stdout)
        self.assertNotIn("bad.py", result.stdout + result.stderr)

    def test_full_repo_scan_skips_deleted_cached_python_paths(self) -> None:
        """Repository-wide scans should ignore tracked Python paths removed from disk."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            self.write_fixture(root)
            self.write_file(root, "app/live.py", "VALUE = 1\n")
            self.write_file(root, "app/deleted.py", "VALUE = 2\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
            (root / "app" / "deleted.py").unlink()

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IMPORT_RESPONSIBILITY=pass", result.stdout)
        self.assertNotIn("deleted.py", result.stdout + result.stderr)

    def test_exclude_paths_select_more_specific_responsibility_scope(self) -> None:
        """Excluded files should resolve to their owning scope for import rules."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            manifest = root / "responsibility-scope.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    'paths = ["app/**"]',
                    'paths = ["app/**"]\nexclude_paths = ["app/evidence.py"]',
                )
                + "\n".join(
                    [
                        "",
                        "[[scope]]",
                        'id = "evidence"',
                        'paths = ["app/evidence.py"]',
                        "",
                        "[[import_rule]]",
                        'source = "evidence"',
                        'targets = ["app", "evidence"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            self.write_file(root, "app/main.py", "import app.evidence\n\nVALUE = app.evidence.VALUE\n")
            self.write_file(root, "app/evidence.py", "VALUE = 1\n")

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("scope-import:app/main.py:1:app->evidence", result.stdout)

    def test_vendored_default_manifest_is_used_when_root_override_is_missing(self) -> None:
        """Derived repos may use the vendored AgentCanon default manifest."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root / "vendor" / "agent-canon")
            self.write_file(root, "app/main.py", "import app.lib\n\nVALUE = app.lib.VALUE\n")
            self.write_file(root, "app/lib.py", "VALUE = 1\n")

            result = self.run_checker(root, "app/main.py")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("IMPORT_RESPONSIBILITY=pass", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a bounded responsibility-scope fixture."""
        self.write_file(
            root,
            "responsibility-scope.toml",
            "\n".join(
                [
                    'catalog_kind = "agent_canon_responsibility_scope"',
                    "version = 1",
                    "[[scope]]",
                    'id = "app"',
                    'paths = ["app/**"]',
                    "",
                    "[[scope]]",
                    'id = "tools"',
                    'paths = ["tools/**"]',
                    "",
                    "[[scope]]",
                    'id = "tests"',
                    'paths = ["tests/**"]',
                    "",
                    "[[import_rule]]",
                    'source = "app"',
                    'targets = ["app"]',
                    "",
                    "[[import_rule]]",
                    'source = "tests"',
                    'targets = ["app", "tools", "tests"]',
                    "",
                ]
            ),
        )
        self.write_file(root, "app/__init__.py", "")
        self.write_file(root, "tools/__init__.py", "")
        self.write_file(root, "tests/__init__.py", "")

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
