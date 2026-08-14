"""Tests for route selection and JSONL evidence emitted by the public runner."""

# @dependency-start
# contract test
# responsibility Tests route selection, exact argv/ownership receipts, and selected-pass semantics for the public runner.
# upstream design ../../CONTAINER_OPERATIONS.md public standalone test boundary
# upstream implementation ../../test/testrunner.sh executes typed token arrays and emits receipts
# upstream implementation ../../test/testlist.toml declares route-aware commands
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py authenticates child environments
# downstream implementation ../../docker/Dockerfile publishes the source test image
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


class TestRunnerBehaviorTest(unittest.TestCase):
    """Exercise both route selectors and terminal receipt semantics."""

    def run_runner(self, root: Path, list_path: Path, route: str) -> subprocess.CompletedProcess[str]:
        """Run the runner with an explicit active route."""
        env = {
            **os.environ,
            "AGENT_CANON_PARENT_ROOT": str(root),
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

    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        """Create a source fixture with two independently selectable records."""
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
        (root / "responsibility-scope.toml").write_text(
            '[[scope]]\nid = "container-test-route"\npaths = ["**"]\n',
            encoding="utf-8",
        )
        list_path = root / "testlist.toml"
        list_path.write_text(
            """
[[tests]]
id = "docker-tooling"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "import sys; sys.exit(0)"]

[[tests]]
id = "devcontainer-product"
environment = "product"
require = "devcontainer"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "import sys; sys.exit(0)"]
""",
            encoding="utf-8",
        )
        return temp_dir, root, list_path

    def records(self, result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
        """Decode JSONL records while keeping command output on stderr."""
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_docker_route_selects_only_docker_and_reports_not_selected(self) -> None:
        """Docker route emits start/pass for Docker and not_selected for Dev Container."""
        fixture = self.fixture()
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "docker")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records(result)
        self.assertEqual([record["id"] for record in records], ["docker-tooling", "docker-tooling", "devcontainer-product"])
        self.assertEqual([record["status"] for record in records], ["start", "pass", "not_selected"])
        self.assertEqual(records[0]["argv"], ["python3", "-c", "import sys; sys.exit(0)"])
        self.assertEqual(records[0]["environment"], "tooling")
        self.assertEqual(records[0]["require"], "docker")
        self.assertEqual(records[0]["active_route"], "docker")
        self.assertEqual(records[0]["code_owner"], "owner.py")
        self.assertEqual(records[0]["responsibility_scope"], "container-test-route")
        self.assertIsNone(records[0]["exit_code"])
        self.assertEqual(records[1]["exit_code"], 0)
        self.assertIsNone(records[2]["exit_code"])

    def test_devcontainer_route_selects_only_devcontainer(self) -> None:
        """Dev Container route has the same explicit nonmatching-record semantics."""
        fixture = self.fixture()
        text = fixture[2].read_text(encoding="utf-8")
        command = 'command = ["python3", "-c", "import sys; sys.exit(0)"]'
        prefix, separator, suffix = text.rpartition(command)
        self.assertEqual(separator, command)
        fixture[2].write_text(
            prefix
            + 'command = ["python3", "-c", "import os; assert \'AGENT_CANON_PARENT_ROOT\' not in os.environ"]'
            + suffix,
            encoding="utf-8",
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "devcontainer")
        self.assertEqual(result.returncode, 0, result.stderr)
        records = self.records(result)
        self.assertEqual([record["status"] for record in records], ["not_selected", "start", "pass"])
        self.assertEqual(records[1]["environment"], "product")
        self.assertEqual(records[1]["require"], "devcontainer")
        self.assertEqual(records[1]["active_route"], "devcontainer")

    def test_child_output_is_live_on_stderr_and_receipts_stay_on_stdout(self) -> None:
        """Child streams use stderr while JSONL receipts remain stdout-only."""
        fixture = self.fixture()
        fixture[2].write_text(
            fixture[2]
            .read_text(encoding="utf-8")
            .replace(
                'command = ["python3", "-c", "import sys; sys.exit(0)"]',
                'command = ["python3", "-c", "import os; print(os.environ.get(\'AGENT_CANON_PARENT_ROOT\', \'authority-absent\')); print(os.environ.get(\'TMPDIR\', \'tmp-unset\')); print(\'child-stderr\', file=__import__(\'sys\').stderr)"]',
                1,
            ),
            encoding="utf-8",
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "docker")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authority-absent\n", result.stderr)
        runtime_prefix = fixture[1] / ".agent-canon" / "runtime" / "testrunner."
        self.assertIn(str(runtime_prefix), result.stderr)
        self.assertIn("child-stderr\n", result.stderr)
        lines = result.stdout.splitlines()
        self.assertTrue(lines)
        self.assertTrue(all(line.startswith("{") for line in lines))
        self.assertEqual(
            [record["status"] for record in self.records(result)],
            ["start", "pass", "not_selected"],
        )

    def test_docker_route_keeps_parent_state_without_exporting_identity(self) -> None:
        """Runner state stays parent-local without exporting repository authority."""
        fixture = self.fixture()
        text = fixture[2].read_text(encoding="utf-8")
        command = 'command = ["python3", "-c", "import sys; sys.exit(0)"]'
        prefix, separator, suffix = text.partition(command)
        self.assertEqual(separator, command)
        probe_command = (
            "import os; from pathlib import Path; "
            "root = Path.cwd(); assert (root / '.git').is_dir(); "
            "identity = ('AGENT_CANON_PARENT_ROOT', 'AGENT_CANON_PARENT_ROOT_DEV', "
            "'AGENT_CANON_PARENT_ROOT_INO', 'AGENT_CANON_ACTIVE_REPOSITORY_ROOT', "
            "'AGENT_CANON_SOURCE_ROOT', 'AGENT_CANON_ROOT', "
            "'AGENT_CANON_CHILD_HANDOFF', 'AGENT_CANON_CHILD_PURPOSE', "
            "'AGENT_CANON_HANDOFF_AUDIENCE', 'AGENT_CANON_TEST_PARENT_ROOT'); "
            "assert all(key not in os.environ for key in identity); "
            "assert Path(os.environ['TMPDIR']).is_relative_to(root); print(root)"
        )
        probe = f'command = ["python3", "-c", "{probe_command}"]'
        fixture[2].write_text(prefix + probe + suffix, encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("AGENT_CANON_TEST_PARENT_ROOT", None)
        with fixture[0]:
            result = subprocess.run(
                ["bash", str(RUNNER)],
                cwd=PROJECT_ROOT,
                env={
                    **environment,
                    "AGENT_CANON_PARENT_ROOT": str(fixture[1]),
                    "AGENT_CANON_SOURCE_ROOT": str(fixture[1]),
                    "AGENT_CANON_TESTLIST": str(fixture[2]),
                    "AGENT_CANON_ACTIVE_ROUTE": "docker",
                },
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{fixture[1]}\n", result.stderr)
        self.assertNotIn("agent-canon-test-parent-", result.stderr)

    def test_record_subprocess_resolves_its_fixture_cwd_without_suite_identity(self) -> None:
        """A record-owned nested fixture derives identity from its own cwd."""
        fixture = self.fixture()
        fixture[1].joinpath("owner.py").write_text(
            """from __future__ import annotations

import os
import subprocess
from pathlib import Path

fixture = Path(os.environ["TMPDIR"]) / "nested-fixture"
fixture.mkdir()
subprocess.run(["git", "init", "--quiet", str(fixture)], check=True)
environment = os.environ.copy()
for key in (
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
):
    assert key not in environment
observed = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"],
    cwd=fixture,
    env=environment,
    text=True,
).strip()
assert Path(observed).resolve() == fixture.resolve()
print(fixture)
""",
            encoding="utf-8",
        )
        fixture[2].write_text(
            fixture[2]
            .read_text(encoding="utf-8")
            .replace(
                'command = ["python3", "-c", "import sys; sys.exit(0)"]',
                'command = ["python3", "owner.py"]',
                1,
            ),
            encoding="utf-8",
        )

        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "docker")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nested-fixture", result.stderr)

    def test_selected_failure_fails_route_after_emitting_terminal_record(self) -> None:
        """A selected nonzero command emits fail and makes the route fail."""
        fixture = self.fixture()
        fixture[2].write_text(
            fixture[2].read_text(encoding="utf-8").replace("sys.exit(0)", "sys.exit(7)", 1),
            encoding="utf-8",
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "docker")
        self.assertEqual(result.returncode, 1)
        records = self.records(result)
        self.assertEqual([record["status"] for record in records], ["start", "fail", "not_selected"])
        self.assertEqual(records[1]["exit_code"], 7)

    def test_valid_route_with_no_selected_records_fails_explicitly(self) -> None:
        """A valid route with no matching require value fails explicitly."""
        fixture = self.fixture()
        fixture[2].write_text(
            """
[[tests]]
id = "docker-only"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "import sys; sys.exit(0)"]
""",
            encoding="utf-8",
        )
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "devcontainer")
        self.assertEqual(result.returncode, 1)
        self.assertIn("selected no test records", result.stderr)
        records = self.records(result)
        self.assertEqual([record["status"] for record in records], ["not_selected"])

    def test_unsupported_active_route_fails_before_selection(self) -> None:
        """An unsupported active route is a schema/input failure."""
        fixture = self.fixture()
        with fixture[0]:
            result = self.run_runner(fixture[1], fixture[2], "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("active route must be docker or devcontainer", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
