"""Tests for the source-owned typed test-list schema."""

# @dependency-start
# contract test
# responsibility Tests comment handling, ownership validation, and fail-before-execution semantics for the public test list.
# upstream design ../../CONTAINER_OPERATIONS.md public standalone test boundary
# upstream implementation ../../test/testrunner.sh validates the typed test list
# upstream implementation ../../test/testlist.toml declares source test commands
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py authenticates child environments
# downstream implementation ../../tests/tools/test_testrunner.py covers route receipts and execution
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "test" / "testrunner.sh"


class TestRunnerSchemaTest(unittest.TestCase):
    """Exercise schema validation before command execution."""

    def run_runner(
        self,
        root: Path,
        list_path: Path,
        *,
        route: str = "docker",
    ) -> subprocess.CompletedProcess[str]:
        """Run the public runner against a temporary source root/list."""
        env = {
            **os.environ,
            "AGENT_CANON_SOURCE_ROOT": str(root),
            "AGENT_CANON_TESTLIST": str(list_path),
            "AGENT_CANON_ACTIVE_ROUTE": route,
        }
        return subprocess.run(
            ["bash", str(RUNNER)],
            cwd=PROJECT_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def fixture(self, record_text: str) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        """Create a minimal source root with one declared owner/scope."""
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        (root / "owner.py").write_text("# owner\n", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        tool_dir = root / "tools" / "agent_tools"
        tool_dir.mkdir(parents=True)
        shutil.copy(
            PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            tool_dir / "parent_root_side_effects.py",
        )
        (root / "owner-dir").mkdir()
        (root / "responsibility-scope.toml").write_text(
            '[[scope]]\nid = "container-test-route"\npaths = ["**"]\n',
            encoding="utf-8",
        )
        list_path = root / "testlist.toml"
        list_path.write_text(record_text, encoding="utf-8")
        return temp_dir, root, list_path

    def test_comments_and_required_typed_fields_are_accepted(self) -> None:
        """TOML comments do not alter the typed record contract."""
        fixture = self.fixture(
            """
# comments are part of the supported TOML format
[[tests]]
id = "commented"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "import sys; sys.exit(0)"]
"""
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2])
        self.assertEqual(result.returncode, 0, result.stderr)
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([record["status"] for record in records], ["start", "pass"])

    def test_existing_directory_owner_is_accepted(self) -> None:
        """A responsibility owner may identify a source directory."""
        fixture = self.fixture(
            """
[[tests]]
id = "directory-owner"
environment = "tooling"
require = "docker"
code_owner = "owner-dir"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "import sys; sys.exit(0)"]
"""
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_field_fails_before_command_execution(self) -> None:
        """A malformed record cannot run its command as a partial suite."""
        fixture = self.fixture(
            """
[[tests]]
id = "missing-command"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
"""
        )
        marker = fixture[1] / "executed"
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema failure", result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(result.stdout, "")

    def test_non_string_route_fields_fail_before_command_execution(self) -> None:
        """Array/table route fields are schema failures, not runtime type errors."""
        for field, environment_value, require_value, expected in (
            ("environment", '["tooling"]', '"docker"', "environment must"),
            ("require", '"tooling"', '{route = "docker"}', "require must"),
        ):
            fixture = self.fixture(
                f"""
[[tests]]
id = "malformed-{field}"
environment = {environment_value}
require = {require_value}
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "from pathlib import Path; Path('executed').touch()"]
"""
            )
            with fixture[0]:
                result = self.run_runner(fixture[1], fixture[2])
            self.assertEqual(result.returncode, 2)
            self.assertIn("schema failure", result.stderr)
            self.assertIn(expected, result.stderr)
            self.assertFalse((fixture[1] / "executed").exists())
            self.assertEqual(result.stdout, "")

    def test_duplicate_and_unsupported_records_fail_before_execution(self) -> None:
        """Duplicate IDs and unsupported fields are rejected atomically."""
        fixture = self.fixture(
            """
[[tests]]
id = "duplicate"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "raise SystemExit(0)"]

[[tests]]
id = "duplicate"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "raise SystemExit(0)"]
"""
        )
        with fixture[0]:
            duplicate = self.run_runner(fixture[1], fixture[2])
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("duplicate test ids", duplicate.stderr)
        self.assertEqual(duplicate.stdout, "")

        fixture = self.fixture(
            """
[[tests]]
id = "unsupported"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "raise SystemExit(0)"]
extra = "reject me"
"""
        )
        with fixture[0]:
            unsupported = self.run_runner(fixture[1], fixture[2])
        self.assertNotEqual(unsupported.returncode, 0)
        self.assertIn("unsupported fields", unsupported.stderr)
        self.assertEqual(unsupported.stdout, "")

    def test_owner_and_scope_are_validated_as_source_contract_fields(self) -> None:
        """Absolute/missing owners and undeclared scopes fail schema validation."""
        for owner, scope, expected in (
            ("/owner.py", "container-test-route", "source-relative"),
            ("missing.py", "container-test-route", "does not exist"),
            ("owner.py", "unknown-scope", "undeclared"),
        ):
            fixture = self.fixture(
                f"""
[[tests]]
id = "invalid-owner-or-scope"
environment = "tooling"
require = "docker"
code_owner = "{owner}"
responsibility_scope = "{scope}"
command = ["python3", "-c", "raise SystemExit(0)"]
"""
            )
            with fixture[0]:
                result = self.run_runner(fixture[1], fixture[2])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
