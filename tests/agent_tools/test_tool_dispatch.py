"""Focused tests for the versioned namespaced tool dispatcher."""

# @dependency-start
# contract test
# responsibility Tests typed catalog loading, parity gating, and argv-safe dispatch.
# upstream implementation ../../tools/agent_tools/tool_dispatch.py owns dispatcher behavior
# upstream design ../../tools/catalog.yaml owns runtime schema and public inventory
# downstream implementation ../../tools/bin/agent-canon owns the stable CLI namespace
# @dependency-end

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import yaml
from tools.agent_tools import tool_dispatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ToolDispatchTest(unittest.TestCase):
    """Exercise the dispatcher without starting Docker or a resident runtime."""

    def test_repository_inventory_is_typed_and_versioned(self) -> None:
        """The repository publishes every Python/Rust catalog surface."""
        specs, schema = tool_dispatch.load_specs(PROJECT_ROOT)
        self.assertEqual(schema["version"], 2)
        self.assertGreaterEqual(len(specs), 110)
        for spec in specs.values():
            self.assertIn(spec.runtime, {"python", "rust"})
            self.assertIsInstance(spec.argv, tuple)
            self.assertTrue(spec.argv)
            self.assertEqual(spec.execution_plane, "tool-container")
            self.assertIn(spec.cwd_policy, {"source-root", "task-root", "explicit"})
            self.assertIn(spec.env_policy, {"allowlisted", "clean"})
            self.assertIn(spec.side_effect_policy, {"read-only", "external-artifact", "explicit-target-write"})
            self.assertTrue(spec.parity_fixture)
        self.assertEqual(specs["rust-docs"].argv[:2], ("tools/bin/agent-canon", "docs"))
        self.assertEqual(specs["rust-python-module-groups-check"].runtime, "rust")

    def test_inventory_is_stable_json(self) -> None:
        """Inventory output has one versioned row per normalized surface."""
        payload = tool_dispatch.inventory(PROJECT_ROOT)
        self.assertEqual(payload["schema"], "agent-canon-tool-inventory/v1")
        rows = payload["entries"]
        self.assertEqual(len(rows), len({row["id"] for row in rows}))
        self.assertEqual(rows, sorted(rows, key=lambda row: row["id"]))

    def test_compatibility_adapters_remain_on_the_legacy_route(self) -> None:
        """A Python entry documented as a Rust adapter is not auto-cut over."""
        specs, _schema = tool_dispatch.load_specs(PROJECT_ROOT)
        self.assertEqual(specs["graph-client"].parity, "legacy")
        self.assertEqual(specs["pydocstyle-review"].parity, "legacy")

    def test_catalog_does_not_default_to_verified(self) -> None:
        """Listing a command cannot silently authorize a cutover."""
        specs, schema = tool_dispatch.load_specs(PROJECT_ROOT)
        self.assertEqual(schema["default_parity"], "legacy")
        self.assertEqual(
            {spec.tool_id for spec in specs.values() if spec.parity == "verified"},
            {"route", "template-bundle"},
        )

    def test_unknown_dispatch_option_is_rejected_before_catalog_lookup(self) -> None:
        """Dispatcher options cannot be smuggled into a child command."""
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            status = tool_dispatch.main(("run", "--not-a-dispatch-option", "route", "--"))
        self.assertEqual(status, 2)
        self.assertIn("unknown-option", error.getvalue())

    def test_cli_requires_explicit_external_runtime(self) -> None:
        """The public route cannot fall back to source-local cache state."""
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            status = tool_dispatch.main(("run", "route", "--", "--help"))
        self.assertEqual(status, 2)
        self.assertIn("runtime-root-required", error.getvalue())

    def test_child_arguments_are_not_shell_split(self) -> None:
        """The child delimiter preserves an argument containing whitespace."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
        )
        marker = root / "argument.json"
        (root / "tools" / "echo.py").write_text(
            "import json, pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n",
            encoding="utf-8",
        )
        status = tool_dispatch.run_tool(
            root,
            tool_dispatch.load_specs(root)[0]["echo"],
            (str(marker), "a value", "--literal"),
        )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), ["a value", "--literal"])

    def test_shell_string_descriptor_is_rejected(self) -> None:
        """A string argv cannot become dispatcher authority."""
        root = self._minimal_root(
            dispatch={"runtime": "python", "argv": "python3 tools/echo.py", "parity": "verified"}
        )
        with self.assertRaisesRegex(tool_dispatch.DispatchError, "shell-string-rejected"):
            tool_dispatch.load_specs(root)

    def test_parity_fixture_requires_all_observed_fields(self) -> None:
        """A fixture row without measured I/O/path fields cannot cut over."""
        root = self._minimal_root(
            dispatch={"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "verified"}
        )
        fixture = root / "tests/fixtures/tool_dispatch/public-command-parity.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["entries"][0]["observed"].pop("written_paths")
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(tool_dispatch.DispatchError, "parity-incomplete"):
            tool_dispatch.run_tool(root, tool_dispatch.load_specs(root)[0]["echo"], ())

    def test_parity_fixture_mismatch_is_rejected(self) -> None:
        """A stale observed route does not become an execution authority."""
        root = self._minimal_root(
            dispatch={"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "verified"}
        )
        fixture = root / "tests/fixtures/tool_dispatch/public-command-parity.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        payload["entries"][0]["observed"]["cwd"] = "task-root"
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(tool_dispatch.DispatchError, "parity-mismatch"):
            tool_dispatch.run_tool(root, tool_dispatch.load_specs(root)[0]["echo"], ())

    def test_unknown_agent_canon_environment_is_not_forwarded(self) -> None:
        """The dispatcher uses exact names, never an AGENT_CANON_* wildcard."""
        root = self._minimal_root(
            dispatch={"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "verified"}
        )
        previous = os.environ.get("AGENT_CANON_SECRET")
        os.environ["AGENT_CANON_SECRET"] = "canary"
        try:
            tool_dispatch.run_tool(root, tool_dispatch.load_specs(root)[0]["echo"], ())
        finally:
            if previous is None:
                os.environ.pop("AGENT_CANON_SECRET", None)
            else:
                os.environ["AGENT_CANON_SECRET"] = previous
        self.assertNotIn("AGENT_CANON_SECRET", tool_dispatch._environment(root, tool_dispatch.load_specs(root)[0]["echo"], root / "control/runtime", None))

    def test_container_exec_requires_authenticated_image_and_runtime(self) -> None:
        """The explicit container route executes locally only after marker checks."""
        image, root, control, runtime = self._container_root()
        previous = {
            key: os.environ.get(key)
            for key in (
                "AGENT_CANON_EXECUTION_PLANE",
                "AGENT_CANON_CONTAINER_USER",
                "AGENT_CANON_IMAGE_ROOT",
                "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT",
                "AGENT_CANON_RUNTIME_TOOLS_ROOT",
                "AGENT_CANON_IMAGE_MARKER_DIGEST",
                "AGENT_CANON_RUNTIME_MARKER_DIGEST",
                "AGENT_CANON_CONTROL_PARENT_ROOT",
                "AGENT_CANON_RUNTIME_ROOT",
                "AGENT_CANON_TARGET_ROOT",
            )
        }
        try:
            os.environ.update(
                {
                    "AGENT_CANON_EXECUTION_PLANE": "tool-container",
                    "AGENT_CANON_CONTAINER_USER": "agentcanon",
                    "AGENT_CANON_IMAGE_ROOT": str(image),
                    "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT": str(image / "image-dependencies"),
                    "AGENT_CANON_RUNTIME_TOOLS_ROOT": str(root),
                    "AGENT_CANON_IMAGE_MARKER_DIGEST": "sha256:" + hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest(),
                    "AGENT_CANON_RUNTIME_MARKER_DIGEST": "sha256:" + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest(),
                    "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime),
                }
            )
            status = tool_dispatch.main(
                ("--container-exec", "--root", str(root), "run", "echo", "--", "a value")
            )
            self.assertEqual(status, 0)
        finally:
            self._restore_environment(previous)

    def test_container_exec_rejects_spoofed_plane_or_marker(self) -> None:
        """A spoofed execution-plane variable cannot activate local execution."""
        _image, root, control, runtime = self._container_root()
        previous = {
            key: os.environ.get(key)
            for key in (
                "AGENT_CANON_EXECUTION_PLANE",
                "AGENT_CANON_CONTAINER_USER",
                "AGENT_CANON_IMAGE_ROOT",
                "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT",
                "AGENT_CANON_RUNTIME_TOOLS_ROOT",
                "AGENT_CANON_IMAGE_MARKER_DIGEST",
                "AGENT_CANON_RUNTIME_MARKER_DIGEST",
                "AGENT_CANON_CONTROL_PARENT_ROOT",
                "AGENT_CANON_RUNTIME_ROOT",
            )
        }
        try:
            os.environ.update(
                {
                    "AGENT_CANON_EXECUTION_PLANE": "host",
                    "AGENT_CANON_CONTAINER_USER": "agentcanon",
                    "AGENT_CANON_IMAGE_ROOT": str(_image),
                    "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT": str(_image / "image-dependencies"),
                    "AGENT_CANON_RUNTIME_TOOLS_ROOT": str(root),
                    "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime),
                }
            )
            with self.assertRaisesRegex(tool_dispatch.DispatchError, "container-exec-not-authorized"):
                tool_dispatch._validate_container_context(root)
            os.environ["AGENT_CANON_EXECUTION_PLANE"] = "tool-container"
            with self.assertRaisesRegex(tool_dispatch.DispatchError, "container-marker-digest-mismatch"):
                tool_dispatch._validate_container_context(root)
        finally:
            self._restore_environment(previous)

    def test_pending_parity_keeps_legacy_route(self) -> None:
        """An unverified entry is never cut over through the new route."""
        root = self._minimal_root(
            dispatch={"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "pending"}
        )
        specs = tool_dispatch.load_specs(root)[0]
        with self.assertRaisesRegex(tool_dispatch.DispatchError, "legacy-route"):
            tool_dispatch.run_tool(root, specs["echo"], ())

    def test_duplicate_ids_fail_closed(self) -> None:
        """Duplicate IDs cannot select an ambiguous execution target."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tools").mkdir()
            (root / "tests/fixtures/tool_dispatch").mkdir(parents=True)
            (root / "tools/echo.py").write_text("print('ok')\n", encoding="utf-8")
            catalog = self._catalog(
                [
                    self._entry("echo"),
                    self._entry("echo"),
                ]
            )
            (root / "tools/catalog.yaml").write_text(yaml.safe_dump(catalog), encoding="utf-8")
            (root / "tests/fixtures/tool_dispatch/public-command-parity.json").write_text(
                json.dumps({"schema": "agent-canon-tool-parity/v1", "version": 1, "entries": [{"id": "echo"}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(tool_dispatch.DispatchError, "duplicate-id"):
                tool_dispatch.load_specs(root)

    def _entry(self, tool_id: str, dispatch: dict[str, object] | None = None) -> dict[str, object]:
        """Build one minimal public entry for a fixture repository."""
        return {
            "id": tool_id,
            "path": "tools/echo.py",
            "summary": "fixture",
            "family": "agent_tools",
            "role": "helper",
            "status": "canonical",
            "command": "python3 tools/echo.py",
            "writes": False,
            "dispatch": dispatch or {"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "verified"},
        }

    def _catalog(self, entries: list[dict[str, object]]) -> dict[str, object]:
        """Build the smallest v2 runtime catalog."""
        return {
            "version": 1,
            "catalog_kind": "agent_canon_tool_catalog",
            "runtime_schema": {
                "version": 2,
                "default_parity": "legacy",
                "parity_fixture": "tests/fixtures/tool_dispatch/public-command-parity.json",
            },
            "entries": entries,
        }

    def _minimal_root(self, dispatch: dict[str, object]) -> Path:
        """Create a temporary public-tool fixture root."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "tools").mkdir()
        (root / "tests/fixtures/tool_dispatch").mkdir(parents=True)
        (root / "tools/echo.py").write_text("print('ok')\n", encoding="utf-8")
        bootstrap = root / "bootstrap.sh"
        bootstrap.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, subprocess, sys\n"
            "request = json.loads(sys.argv[sys.argv.index('--request-json') + 1])\n"
            "env = os.environ.copy(); env.update(request['environment'])\n"
            "raise SystemExit(subprocess.run(request['argv'], cwd=request['cwd'], env=env).returncode)\n",
            encoding="utf-8",
        )
        bootstrap.chmod(bootstrap.stat().st_mode | stat.S_IXUSR)
        control = root / "control"
        runtime = control / "runtime"
        runtime.mkdir(parents=True)
        previous = {
            key: os.environ.get(key)
            for key in (
                "AGENT_CANON_CONTROL_PARENT_ROOT",
                "AGENT_CANON_RUNTIME_ROOT",
            )
        }
        self.addCleanup(self._restore_environment, previous)
        os.environ["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(control)
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
        os.environ["AGENT_CANON_TARGET_ROOT"] = str(root)
        (runtime / "state.json").write_text(
            json.dumps({"targets": {"fixture": {"root": str(root)}}}),
            encoding="utf-8",
        )
        (root / "tools/catalog.yaml").write_text(
            yaml.safe_dump(self._catalog([self._entry("echo", dispatch)])),
            encoding="utf-8",
        )
        (root / "tests/fixtures/tool_dispatch/public-command-parity.json").write_text(
            json.dumps(
                {
                    "schema": "agent-canon-tool-parity/v2",
                    "version": 2,
                    "entries": [
                        {
                            "id": "echo",
                            "probe_args": [],
                            "observed": {
                                "argv": ["python3", "tools/echo.py"],
                                "cwd": "source-root",
                                "stdin": "inherited",
                                "stdout": "inherited",
                                "stderr": "inherited",
                                "exit": "propagate",
                                "signal": "propagate",
                                "written_paths": [],
                            },
                            "legacy_result": {
                                "exit_code": 0,
                                "stdout_sha256": "0" * 64,
                                "stderr_sha256": "0" * 64,
                                "written_paths": [],
                            },
                            "container_result": {
                                "exit_code": 0,
                                "stdout_sha256": "0" * 64,
                                "stderr_sha256": "0" * 64,
                                "written_paths": [],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return root

    def _container_root(self) -> tuple[Path, Path, Path, Path]:
        """Create a read-only image/runtime fixture with immutable markers."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        image = base / "image"
        root = image / "runtime"
        (root / "tools").mkdir(parents=True)
        (root / "tests/fixtures/tool_dispatch").mkdir(parents=True)
        (root / "tools/echo.py").write_text("import sys; print(*sys.argv[1:])\n", encoding="utf-8")
        (root / "tools/catalog.yaml").write_text(
            yaml.safe_dump(
                self._catalog(
                    [
                        self._entry(
                            "echo",
                            {"runtime": "python", "argv": ["python3", "tools/echo.py"], "parity": "verified"},
                        )
                    ]
                )
            ),
            encoding="utf-8",
        )
        (root / "tests/fixtures/tool_dispatch/public-command-parity.json").write_text(
            json.dumps(
                {
                    "schema": "agent-canon-tool-parity/v2",
                    "version": 2,
                    "entries": [
                        {
                            "id": "echo",
                            "probe_args": [],
                            "observed": {
                                "argv": ["python3", "tools/echo.py"],
                                "cwd": "source-root",
                                "stdin": "inherited",
                                "stdout": "inherited",
                                "stderr": "inherited",
                                "exit": "propagate",
                                "signal": "propagate",
                                "written_paths": [],
                            },
                            "legacy_result": {
                                "exit_code": 0,
                                "stdout_sha256": "0" * 64,
                                "stderr_sha256": "0" * 64,
                                "written_paths": [],
                            },
                            "container_result": {
                                "exit_code": 0,
                                "stdout_sha256": "0" * 64,
                                "stderr_sha256": "0" * 64,
                                "written_paths": [],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        dependencies = image / "image-dependencies"
        dependencies.mkdir(parents=True)
        (dependencies / "plan.json").write_text('{"schema":"fixture"}\n', encoding="utf-8")
        (image / tool_dispatch.CONTAINER_MARKER_NAME).write_bytes(tool_dispatch.CONTAINER_MARKER)
        (root / tool_dispatch.RUNTIME_MARKER_NAME).write_bytes(tool_dispatch.RUNTIME_MARKER)
        for path in (
            image / tool_dispatch.CONTAINER_MARKER_NAME,
            root / tool_dispatch.RUNTIME_MARKER_NAME,
            dependencies / "plan.json",
        ):
            path.chmod(0o444)
        root.chmod(0o555)
        control = base / "control"
        runtime = control / "runtime"
        runtime.mkdir(parents=True)
        return image, root, control, runtime

    @staticmethod
    def _restore_environment(previous: dict[str, str | None]) -> None:
        """Restore process environment after a fake bootstrap run."""
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
