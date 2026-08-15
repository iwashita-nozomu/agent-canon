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
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "test" / "testrunner.sh"


class TestRunnerBehaviorTest(unittest.TestCase):
    """Exercise both route selectors and terminal receipt semantics."""

    def run_runner(
        self,
        root: Path,
        list_path: Path,
        route: str,
        *,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the runner with an explicit active route."""
        env = {
            **os.environ,
            "AGENT_CANON_TESTLIST": str(list_path),
            "AGENT_CANON_ACTIVE_ROUTE": route,
        }
        if extra_environment:
            env.update(extra_environment)
        return subprocess.run(
            ["bash", str(root / "test" / "testrunner.sh")],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        """Create a source fixture with two independently selectable records."""
        temp_dir = tempfile.TemporaryDirectory()
        parent_root = Path(temp_dir.name)
        root = parent_root / "vendor" / "agent-canon"
        root.mkdir(parents=True)
        (root / "test").mkdir()
        shutil.copy(PROJECT_ROOT / "test" / "testrunner.sh", root / "test" / "testrunner.sh")
        (root / "owner.py").write_text("# owner\n", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(parent_root)], check=True)
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        tool_dir = root / "tools" / "agent_tools"
        tool_dir.mkdir(parents=True)
        shutil.copy(
            PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            tool_dir / "parent_root_side_effects.py",
        )
        shutil.copy(
            PROJECT_ROOT / "tools" / "agent_tools" / "fixture_spawn.py",
            tool_dir / "fixture_spawn.py",
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
        (parent_root / ".gitmodules").write_text(
            '[submodule "vendor/agent-canon"]\n'
            "\tpath = vendor/agent-canon\n"
            "\turl = https://example.invalid/agent-canon.git\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(root), "add", "-A"], check=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Runner Fixture",
                "-c",
                "user.email=runner-fixture@example.invalid",
                "commit",
                "-q",
                "-m",
                "source fixture",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(parent_root), "add", ".gitmodules", "vendor/agent-canon"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(parent_root),
                "-c",
                "user.name=Runner Fixture",
                "-c",
                "user.email=runner-fixture@example.invalid",
                "commit",
                "-q",
                "-m",
                "parent fixture",
            ],
            check=True,
        )
        return temp_dir, root, list_path

    def records(self, result: subprocess.CompletedProcess[str]) -> list[dict[str, object]]:
        """Decode JSONL records while keeping command output on stderr."""
        return [json.loads(line) for line in result.stdout.splitlines()]

    def runner_module(self) -> dict[str, object]:
        """Load the embedded Python runner without starting a subprocess."""
        script = RUNNER.read_text(encoding="utf-8")
        start = script.index("<<'PY'\n") + len("<<'PY'\n")
        end = script.rindex("\nPY")
        namespace: dict[str, object] = {"__name__": "testrunner_test_module"}
        exec(compile(script[start:end], str(RUNNER), "exec"), namespace)
        return namespace

    def test_runner_admission_keeps_the_fixed_cleanup_boundary(self) -> None:
        """Record admission remains strict at the fixed cleanup boundary."""
        runner = self.runner_module()
        grace = int(runner["CLEANUP_GRACE_NS"])
        deadline = 14_400_000_000_000
        self.assertEqual(runner["command_deadline"](deadline), deadline - grace)  # type: ignore[operator]
        self.assertTrue(runner["admit_record"](deadline, deadline - grace - 1))  # type: ignore[operator]
        self.assertFalse(runner["admit_record"](deadline, deadline - grace))  # type: ignore[operator]
        self.assertFalse(  # type: ignore[operator]
            runner["admit_record"](deadline, deadline - grace - 1, cleanup_failed=True)
        )

    def test_parent_horizon_mismatch_is_rejected_before_child_use(self) -> None:
        """A parent API stub returning another expiry fails closed."""
        runner = self.runner_module()
        child = SimpleNamespace(record=SimpleNamespace(expires_mono_ns=999))
        with self.assertRaisesRegex(RuntimeError, "SESSION_HORIZON_MISMATCH"):
            runner["validate_child_horizon"](child, 1000)  # type: ignore[operator]

    def test_runner_passes_the_public_session_result_without_rediscovery(self) -> None:
        """The v2 result is explicit from public_session through record setup."""
        source = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("resolve_parent_side_effect_session", source)
        self.assertIn("with parent_side_effects._open_runner_session(", source)
        self.assertIn("parent_side_effects._RUNNER_CALLER_MARKER", source)
        self.assertIn(
            "return _run(source_root, list_path, active_route, session, horizon)",
            source,
        )
        self.assertIn("source_root, active_route, session", source)
        self.assertNotIn("import inspect", source)
        self.assertNotIn("getattr(", source)
        self.assertNotIn("bind_runner_horizon", source)

    def test_record_commands_receive_no_inherited_pythonpath(self) -> None:
        """Record setup removes inherited import paths before command launch."""
        fixture = self.fixture()
        fixture[1].joinpath("pythonpath_probe.py").write_text(
            """import os
print(os.environ.get("PYTHONPATH", "PYTHONPATH-absent"))
""",
            encoding="utf-8",
        )
        fixture[2].write_text(
            fixture[2]
            .read_text(encoding="utf-8")
            .replace(
                'command = ["python3", "-c", "import sys; sys.exit(0)"]',
                'command = ["python3", "pythonpath_probe.py"]',
                1,
            ),
            encoding="utf-8",
        )
        with fixture[0]:
            result = self.run_runner(
                fixture[1],
                fixture[2],
                "docker",
                extra_environment={"PYTHONPATH": "/host/entry:/current-user"},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PYTHONPATH-absent\n", result.stderr)

    def test_pytest_commands_require_the_source_owned_entrypoint(self) -> None:
        """Direct pytest commands are rejected before any record is launched."""
        runner = self.runner_module()
        validate = runner["validate_test_command_entrypoint"]
        schema_error = runner["SchemaError"]
        for command in (
            ["pytest", "tests"],
            ["pytest-wrapper", "tests"],
            ["python3", "-m", "pytest", "tests"],
            ["python", "-m", "pytest", "tests"],
            ["python3.12", "test/pytest_entrypoint.py", "tests"],
            ["python3", "run_pytest.py", "tests"],
            ["env", "PYTHONPATH=/tmp", "python3", "-m", "pytest", "tests"],
            ["bash", "-c", "python3 -m pytest tests"],
        ):
            with self.subTest(command=command), self.assertRaisesRegex(
                schema_error, "TEST_COMMAND_ENTRYPOINT_FORBIDDEN"
            ):
                validate(PROJECT_ROOT, command, "direct-pytest")

    def test_pytest_entrypoint_source_owns_exact_import_contract(self) -> None:
        """The entrypoint scrubs before importing pytest and fixes repository origins."""
        source = (PROJECT_ROOT / "test" / "pytest_entrypoint.py").read_text(encoding="utf-8")
        self.assertIn("REPOSITORY_ORIGINS = (", source)
        self.assertIn("SOURCE_ROOT / \"tools\"", source)
        self.assertIn("SOURCE_ROOT / \"tools\" / \"agent_tools\"", source)
        self.assertLess(source.index("configure_import_environment()"), source.index("import pytest"))

    def test_pytest_entrypoint_removes_nested_repository_origins(self) -> None:
        """Only interpreter paths precede the exact source-owned import suffix."""
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            sentinels = (
                temporary_root / "parent-repository",
                temporary_root / "parent-repository" / "vendor" / "agent-canon",
                temporary_root / "host-repository",
            )
            for sentinel in sentinels:
                sentinel.mkdir(parents=True)
                sentinel.joinpath(".git").mkdir()
            probe = """
import json
import runpy
import sys
import sysconfig
from pathlib import Path

namespace = runpy.run_path(sys.argv[1], run_name="pytest_entrypoint_probe")
sys.path[:0] = sys.argv[2:]
namespace["configure_import_environment"]()
managed = []
for name in ("stdlib", "platstdlib", "purelib", "platlib"):
    value = sysconfig.get_paths().get(name)
    if value:
        managed.append(str(Path(value).resolve()))
print(json.dumps({"paths": sys.path, "managed": managed}))
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    probe,
                    str(PROJECT_ROOT / "test" / "pytest_entrypoint.py"),
                    *(str(path) for path in sentinels),
                ],
                env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        paths = payload["paths"]
        managed = tuple(Path(value) for value in payload["managed"])
        expected_suffix = (
            str(PROJECT_ROOT),
            str(PROJECT_ROOT / "tools"),
            str(PROJECT_ROOT / "tools" / "agent_tools"),
        )
        self.assertEqual(tuple(paths[-len(expected_suffix) :]), expected_suffix)
        for sentinel in sentinels:
            self.assertNotIn(str(sentinel), paths)
        for entry in paths[: -len(expected_suffix)]:
            physical = Path(entry or ".").resolve()
            self.assertTrue(
                any(physical == root or root in physical.parents for root in managed)
                or any(part in {"site-packages", "dist-packages"} for part in physical.parts),
                entry,
            )

    def test_canonical_entrypoint_collects_agent_tools_and_tools(self) -> None:
        """The exact source entrypoint collects both suites without stdlib shadowing."""
        for suite in ("tests/agent_tools", "tests/tools"):
            with self.subTest(suite=suite):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(PROJECT_ROOT / "test" / "pytest_entrypoint.py"),
                        suite,
                        "--collect-only",
                        "-q",
                        "--tb=short",
                    ],
                    cwd=PROJECT_ROOT,
                    env=os.environ.copy(),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("No module named 'test.", result.stderr)
                self.assertIn("tests/", result.stdout)

    def test_cleanup_failed_rejects_next_record_admission(self) -> None:
        """A failed issuer/receipt cleanup closes admission for the next record."""
        runner = self.runner_module()
        deadline = 14_400_000_000_000 + 1000
        self.assertFalse(runner["admit_record"](deadline, 0, cleanup_failed=True))  # type: ignore[operator]

    def test_ignore_sigterm_receives_term_then_kill_after_exact_five_seconds(self) -> None:
        """An uncooperative record cannot outlive the exact TERM grace."""
        runner = self.runner_module()
        events: list[int] = []
        clock_ns = [0]

        class IgnoreTermProcess:
            pid = 321

            def poll(self) -> int | None:
                return None if not events or events[-1] != signal.SIGKILL else -signal.SIGKILL

            def wait(self) -> int:
                return -signal.SIGKILL

        def fake_clock() -> int:
            return clock_ns[0]

        def fake_sleep(seconds: float) -> None:
            clock_ns[0] += int(seconds * 1_000_000_000)

        def fake_killpg(_pid: int, signum: int) -> None:
            events.append(signum)

        with mock.patch.object(runner["os"], "killpg", side_effect=fake_killpg):  # type: ignore[index]
            killed = runner["terminate_process"](  # type: ignore[operator]
                IgnoreTermProcess(), clock=fake_clock, sleep=fake_sleep
            )
        self.assertTrue(killed)
        self.assertEqual(events, [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(clock_ns[0], int(runner["TERM_GRACE_NS"]))  # type: ignore[index]

    def test_watchdog_failure_is_published_without_token_mutation(self) -> None:
        """An issuer loss wakes the lifecycle owner and records a terminal failure."""
        runner = self.runner_module()

        class LostIssuer:
            @property
            def session(self) -> object:
                raise RuntimeError("issuer disappeared")

        wake = runner["threading"].Event()  # type: ignore[index]
        watchdog = runner["SupervisorWatchdog"](LostIssuer(), wake_event=wake)  # type: ignore[operator]
        watchdog.check_once()
        self.assertIsNotNone(watchdog.failure)
        self.assertTrue(wake.is_set())
        self.assertTrue(watchdog.stop_event.is_set())

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
        runtime_prefix = fixture[1].parent.parent / ".agent-canon" / "runtime" / "testrunner."
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
        """Each record receives parent-owned state without ambient repository identity."""
        fixture = self.fixture()
        text = fixture[2].read_text(encoding="utf-8")
        command = 'command = ["python3", "-c", "import sys; sys.exit(0)"]'
        prefix, separator, suffix = text.partition(command)
        self.assertEqual(separator, command)
        probe_command = (
            "import os; from pathlib import Path; "
            "root = Path.cwd(); parent = root.parent.parent; "
            "assert (root / '.git').is_dir(); "
            "identity = ('AGENT_CANON_PARENT_ROOT', 'AGENT_CANON_PARENT_ROOT_DEV', "
            "'AGENT_CANON_PARENT_ROOT_INO', 'AGENT_CANON_ACTIVE_REPOSITORY_ROOT', "
            "'AGENT_CANON_SOURCE_ROOT', 'AGENT_CANON_ROOT', "
            "'AGENT_CANON_CHILD_HANDOFF', 'AGENT_CANON_HANDOFF_AUDIENCE'); "
            "assert all(key not in os.environ for key in identity); "
            "assert os.environ['AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED'] == '1'; "
            "assert Path(os.environ['AGENT_CANON_SIDE_EFFECT_PARENT_ROOT']).resolve() == parent.resolve(); "
            "assert os.environ['AGENT_CANON_SIDE_EFFECT_HANDOFF']; "
            "assert Path(os.environ['TMPDIR']).is_relative_to(parent); "
            "assert Path(os.environ['AGENT_CANON_RECORD_ROOT']).is_relative_to(parent); "
            "assert Path(os.environ['AGENT_CANON_TOOLS_HOME']) == parent / '.agent-canon' / 'image-runtime' / 'tools'; "
            "print(parent)"
        )
        probe = f'command = ["python3", "-c", "{probe_command}"]'
        fixture[2].write_text(prefix + probe + suffix, encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("AGENT_CANON_TEST_PARENT_ROOT", None)
        with fixture[0]:
            result = subprocess.run(
                ["bash", str(fixture[1] / "test" / "testrunner.sh")],
                cwd=fixture[1],
                env={
                    **environment,
                    "AGENT_CANON_TESTLIST": str(fixture[2]),
                    "AGENT_CANON_ACTIVE_ROUTE": "docker",
                },
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{fixture[1].parent.parent}\n", result.stderr)
        self.assertNotIn("AGENT_CANON_TEST_PARENT_ROOT", result.stderr)

    def test_record_subprocess_starts_without_suite_identity_for_fixture_cwd(self) -> None:
        """The central fixture adapter starts nested work without suite identity."""
        fixture = self.fixture()
        fixture[1].joinpath("owner.py").write_text(
            """from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

fixture = Path(os.environ["TMPDIR"]) / "nested-fixture"
fixture.mkdir()
subprocess.run(["git", "init", "--quiet", str(fixture)], check=True)
from tools.agent_tools.fixture_spawn import (
    bootstrap_fixture_public_environment,
    record_session_from_environment,
)

source = Path.cwd()
with record_session_from_environment() as record:
    with bootstrap_fixture_public_environment(
        mode="ordinary_tool", record=record, fixture_cwd=fixture
    ) as ordinary:
        ordinary_result = subprocess.run(
            [sys.executable, "-c", "import os; assert os.environ['AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED'] == '1'"],
            cwd=source,
            env=dict(ordinary),
            check=False,
        )
        assert ordinary_result.returncode == 0
    with bootstrap_fixture_public_environment(
        mode="product_fixture",
        record=record,
        fixture_cwd=fixture,
        argv=(
            sys.executable,
            "-c",
            "import os, subprocess; assert not any(key.startswith('AGENT_CANON_SIDE_EFFECT_') for key in os.environ); assert 'PYTHONPATH' not in os.environ; print(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())",
        ),
    ) as product:
        assert product.receipt is not None
        assert product.receipt.returncode == 0
    with bootstrap_fixture_public_environment(
        mode="synthetic_tool", record=record, fixture_cwd=fixture
    ) as synthetic:
        synthetic_result = subprocess.run(
            [sys.executable, "-c", "import os; assert os.environ['AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED'] == '1'"],
            cwd=fixture,
            env=dict(synthetic),
            check=False,
        )
        assert synthetic_result.returncode == 0
    with bootstrap_fixture_public_environment(
        mode="ordinary_tool", record=record, fixture_cwd=fixture
    ) as final_ordinary:
        final_result = subprocess.run(
            [sys.executable, "-c", "import os; assert os.environ['AGENT_CANON_SIDE_EFFECT_SESSION_REQUIRED'] == '1'"],
            cwd=source,
            env=dict(final_ordinary),
            check=False,
        )
        assert final_result.returncode == 0
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

    def test_signal_between_record_admission_and_launch_is_nonzero_and_stops_route(self) -> None:
        """A control signal cannot admit a later record or produce a zero exit."""
        fixture = self.fixture()
        fixture[2].write_text(
            fixture[2].read_text(encoding="utf-8").replace(
                'command = ["python3", "-c", "import sys; sys.exit(0)"]',
                'command = ["python3", "-c", "import time; time.sleep(30)"]',
                1,
            )
            + """
[[tests]]
id = "docker-after-signal"
environment = "tooling"
require = "docker"
code_owner = "owner.py"
responsibility_scope = "container-test-route"
command = ["python3", "-c", "print('must-not-run')"]
""",
            encoding="utf-8",
        )
        with fixture[0]:
            process = subprocess.Popen(
                ["bash", str(fixture[1] / "test" / "testrunner.sh")],
                cwd=fixture[1],
                env={
                    **os.environ,
                    "AGENT_CANON_TESTLIST": str(fixture[2]),
                    "AGENT_CANON_ACTIVE_ROUTE": "docker",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.4)
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 128 + signal.SIGTERM, stderr)
        records = self.records(subprocess.CompletedProcess([], process.returncode, stdout, stderr))
        self.assertNotIn("docker-after-signal", [record["id"] for record in records])

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
