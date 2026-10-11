"""Focused tests for the versioned namespaced tool dispatcher."""

# @dependency-start
# contract test
# responsibility Tests typed catalog loading, parity gating, and argv-safe dispatch.
# upstream implementation ../../tools/runtime/dispatch/tool_dispatch.py owns dispatcher behavior
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
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from tools.runtime.dispatch import tool_dispatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ToolDispatchTest(unittest.TestCase):
    """Exercise the dispatcher without starting Docker or a resident runtime."""

    def test_repository_inventory_is_typed_and_versioned(self) -> None:
        """The repository publishes typed Python, Rust, and native catalog surfaces."""
        specs, schema = tool_dispatch.load_specs(PROJECT_ROOT)
        self.assertEqual(schema["version"], 2)
        for spec in specs.values():
            self.assertIn(spec.runtime, {"python", "rust", "native"})
            self.assertIsInstance(spec.argv, tuple)
            self.assertTrue(spec.argv)
            self.assertEqual(spec.execution_plane, "tool-container")
            self.assertIn(
                spec.cwd_policy, {"source-root", "target-root", "task-root", "explicit"}
            )
            self.assertIn(spec.env_policy, {"allowlisted", "clean"})
            self.assertIn(
                spec.side_effect_policy,
                {"read-only", "external-artifact", "explicit-target-write"},
            )
            self.assertTrue(spec.parity_fixture)
        self.assertEqual(specs["rust-docs"].argv[:2], ("tools/bin/agent-canon", "docs"))
        self.assertEqual(specs["rust-python-module-groups-check"].runtime, "rust")
        self.assertEqual(specs["quarto"].runtime, "native")
        self.assertEqual(specs["quarto"].argv, ("quarto",))
        self.assertEqual(specs["vl-convert"].runtime, "native")
        self.assertEqual(specs["vl-convert"].argv, ("vl-convert",))

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

    def test_catalog_does_not_default_to_verified(self) -> None:
        """Listing a command cannot silently authorize a cutover."""
        specs, schema = tool_dispatch.load_specs(PROJECT_ROOT)
        self.assertEqual(schema["default_parity"], "legacy")
        self.assertEqual(
            {spec.tool_id for spec in specs.values() if spec.parity == "verified"},
            {
                "generate-agent-improvement-guide",
                "generate-agent-runtime-dashboard",
                "issue-sync",
                "quarto",
                "route",
                "skill-document-reader",
                "template-bundle",
                "vl-convert",
            },
        )

    def test_issue_sync_uses_resident_container_and_external_receipt_route(
        self,
    ) -> None:
        """Issue publication receipts use the registered container tool route."""
        specs, _schema = tool_dispatch.load_specs(PROJECT_ROOT)
        issue_sync = specs["issue-sync"]
        self.assertEqual(
            issue_sync.argv,
            ("python3", "tools/repository/github/issue_sync.py"),
        )
        self.assertEqual(issue_sync.execution_plane, "tool-container")
        self.assertEqual(issue_sync.cwd_policy, "target-root")
        self.assertEqual(issue_sync.side_effect_policy, "external-artifact")
        self.assertEqual(issue_sync.output_root, "external-runtime")
        self.assertEqual(issue_sync.parity, "verified")

    def test_issue_sync_rejects_online_issue_lookup_on_container_route(self) -> None:
        """Online GitHub reads cannot cross the body-free receipt boundary."""
        specs, _schema = tool_dispatch.load_specs(PROJECT_ROOT)
        with self.assertRaisesRegex(
            tool_dispatch.DispatchError, "container-route-restricted"
        ):
            tool_dispatch.run_tool(
                PROJECT_ROOT,
                specs["issue-sync"],
                ("--issue-url", "https://github.com/owner/repo/issues/1"),
            )

    def test_dashboard_uses_container_and_external_artifact_route(self) -> None:
        """The canonical dashboard route keeps source read-only and output external."""
        specs, _schema = tool_dispatch.load_specs(PROJECT_ROOT)
        dashboard = specs["generate-agent-runtime-dashboard"]
        self.assertEqual(
            dashboard.argv,
            ("python3", "eval/producers/generate_agent_runtime_dashboard.py"),
        )
        self.assertEqual(dashboard.execution_plane, "tool-container")
        self.assertEqual(dashboard.cwd_policy, "target-root")
        self.assertEqual(dashboard.side_effect_policy, "external-artifact")
        self.assertEqual(dashboard.output_root, "external-runtime")
        self.assertEqual(dashboard.written_paths, ())
        self.assertEqual(dashboard.parity, "verified")

    def test_dashboard_route_builds_typed_bootstrap_request(self) -> None:
        """Dashboard dispatch starts at bootstrap, never at a host Python path."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": [
                    "python3",
                    "eval/producers/generate_agent_runtime_dashboard.py",
                ],
                "execution_plane": "tool-container",
                "cwd": "target-root",
                "env": "allowlisted",
                "stdin": "inherited",
                "stdout": "inherited",
                "stderr": "inherited",
                "exit": "propagate",
                "signal": "propagate",
                "side_effect": "external-artifact",
                "output_root": "external-runtime",
                "written_paths": [],
                "parity": "verified",
            },
            tool_id="generate-agent-runtime-dashboard",
            path="eval/producers/generate_agent_runtime_dashboard.py",
        )
        output_root = root / "control" / "runtime" / "reports"
        output_root.mkdir()
        previous_target_digest = os.environ.pop("AGENT_CANON_TARGET_DIGEST", None)
        self.addCleanup(
            self._restore_optional_environment,
            "AGENT_CANON_TARGET_DIGEST",
            previous_target_digest,
        )
        previous_output_root = os.environ.get("AGENT_CANON_OUTPUT_ROOT")
        self.addCleanup(
            self._restore_optional_environment,
            "AGENT_CANON_OUTPUT_ROOT",
            previous_output_root,
        )
        os.environ["AGENT_CANON_OUTPUT_ROOT"] = str(output_root)
        fixture = root / "tests/fixtures/tool_dispatch/public-command-parity.json"
        parity = json.loads(fixture.read_text(encoding="utf-8"))
        parity["entries"][0]["id"] = "generate-agent-runtime-dashboard"
        parity["entries"][0]["observed"]["argv"] = [
            "python3",
            "eval/producers/generate_agent_runtime_dashboard.py",
        ]
        parity["entries"][0]["observed"]["cwd"] = "target-root"
        fixture.write_text(json.dumps(parity), encoding="utf-8")
        with patch(
            "tools.runtime.dispatch.tool_dispatch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0),
        ) as run:
            status = tool_dispatch.run_tool(
                root,
                tool_dispatch.load_specs(root)[0]["generate-agent-runtime-dashboard"],
                (
                    "--root",
                    ".",
                    "--compact-out",
                    "reports/agent-runtime-dashboard/compact.md",
                    "--api-out",
                    "reports/agent-runtime-dashboard/api.json",
                ),
            )

        self.assertEqual(status, 0)
        command = run.call_args.args[0]
        request = json.loads(command[command.index("--request-json") + 1])
        self.assertEqual(command[0], str(root / "bootstrap.sh"))
        digest_index = command.index("--target-digest")
        self.assertEqual(
            command[digest_index + 1],
            hashlib.sha256(str(root).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(request["tool_id"], "generate-agent-runtime-dashboard")
        self.assertEqual(request["side_effect"], "external-artifact")
        self.assertEqual(request["output_root"], str(output_root))
        self.assertEqual(
            request["argv"],
            [
                "python3",
                "eval/producers/generate_agent_runtime_dashboard.py",
                "--root",
                ".",
                "--compact-out",
                "reports/agent-runtime-dashboard/compact.md",
                "--api-out",
                "reports/agent-runtime-dashboard/api.json",
            ],
        )

    def test_dashboard_container_route_selects_container_executor(self) -> None:
        """The verified dashboard route is delegated to the resident container."""
        spec = tool_dispatch.load_specs(PROJECT_ROOT)[0][
            "generate-agent-runtime-dashboard"
        ]
        with patch.object(
            tool_dispatch, "_run_container_spec", return_value=0
        ) as container_run:
            status = tool_dispatch._run_spec(
                PROJECT_ROOT,
                spec,
                ("--help",),
                require_parity=True,
                container_exec=True,
            )

        self.assertEqual(status, 0)
        container_run.assert_called_once_with(PROJECT_ROOT, spec, ("--help",))

    def test_native_tool_route_selects_container_executor(self) -> None:
        """Native catalog runtimes use the same authenticated container route."""
        spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["quarto"]
        with patch.object(
            tool_dispatch, "_run_container_spec", return_value=0
        ) as container_run:
            status = tool_dispatch._run_spec(
                PROJECT_ROOT,
                spec,
                ("pandoc", "--version"),
                require_parity=False,
                container_exec=True,
            )

        self.assertEqual(status, 0)
        container_run.assert_called_once_with(
            PROJECT_ROOT, spec, ("pandoc", "--version")
        )

    def test_native_runtime_does_not_require_a_python_or_rust_source_path(self) -> None:
        """A native executable can use its existing catalog owner document path."""
        root = self._minimal_root(
            dispatch={
                "runtime": "native",
                "argv": ["quarto"],
                "parity": "pending",
            },
            path="documents/native-command.md",
        )

        spec = tool_dispatch.load_specs(root)[0]["echo"]

        self.assertEqual(spec.runtime, "native")
        self.assertEqual(spec.path, "documents/native-command.md")

    def test_native_tool_builds_the_existing_typed_bootstrap_request(self) -> None:
        """The host route carries a native argv through the existing request envelope."""
        root = self._minimal_root(
            dispatch={
                "runtime": "native",
                "argv": ["quarto"],
                "output_root": "external-runtime",
                "side_effect": "external-artifact",
                "parity": "pending",
            },
            path="documents/native-command.md",
        )
        spec = tool_dispatch.load_specs(root)[0]["echo"]
        runtime = Path(os.environ["AGENT_CANON_RUNTIME_ROOT"])
        target = Path(os.environ["AGENT_CANON_TARGET_ROOT"])
        output = runtime / "tool-output"

        command, environment = tool_dispatch._bootstrap_command(
            root,
            runtime,
            spec,
            ("pandoc", "paper.md"),
            target,
            output,
        )
        request = json.loads(command[command.index("--request-json") + 1])

        self.assertNotIn("runtime", request)
        self.assertEqual(request["argv"], ["quarto", "pandoc", "paper.md"])
        self.assertEqual(request["child_args"], ["pandoc", "paper.md"])
        self.assertEqual(
            request["environment"]["AGENT_CANON_DISPATCH_RUNTIME"], "native"
        )
        self.assertEqual(environment["AGENT_CANON_RUNTIME_ROOT"], str(runtime))

    def test_native_arguments_remain_relative_to_registered_target(self) -> None:
        """Only catalog-owned source paths are rebased into the image source."""
        spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["quarto"]
        args = ("pandoc", "--bibliography", "tools/catalog.yaml")

        self.assertEqual(
            tool_dispatch._resolve_container_argv(PROJECT_ROOT, spec, args),
            ["quarto", *args],
        )

    def test_unknown_dispatch_option_is_rejected_before_catalog_lookup(self) -> None:
        """Dispatcher options cannot be smuggled into a child command."""
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            status = tool_dispatch.main(
                ("run", "--not-a-dispatch-option", "route", "--")
            )
        self.assertEqual(status, 2)
        self.assertIn("unknown-option", error.getvalue())

    def test_cli_requires_explicit_external_runtime(self) -> None:
        """The public route cannot fall back to source-local cache state."""
        root_environment = (
            "AGENT_CANON_CONTROL_PARENT_ROOT",
            "AGENT_CANON_RUNTIME_ROOT",
            "AGENT_CANON_TARGET_ROOT",
            "AGENT_CANON_MOUNT_REGISTRY",
            "AGENT_CANON_OUTPUT_ROOT",
        )
        previous = {key: os.environ.get(key) for key in root_environment}
        try:
            for key in root_environment:
                os.environ.pop(key, None)
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                status = tool_dispatch.main(("run", "route", "--", "--help"))
        finally:
            self._restore_environment(previous)
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
        self.assertEqual(
            json.loads(marker.read_text(encoding="utf-8")), ["a value", "--literal"]
        )

    def test_shell_string_descriptor_is_rejected(self) -> None:
        """A string argv cannot become dispatcher authority."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": "python3 tools/echo.py",
                "parity": "verified",
            }
        )
        with self.assertRaisesRegex(
            tool_dispatch.DispatchError, "shell-string-rejected"
        ):
            tool_dispatch.load_specs(root)

    def test_missing_dispatch_fails_before_execution(self) -> None:
        """An executable catalog entry must declare an explicit argv route."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
        )
        catalog_path = root / "tools/catalog.yaml"
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        catalog["entries"][0].pop("dispatch")
        catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")
        with self.assertRaisesRegex(tool_dispatch.DispatchError, "missing-dispatch"):
            tool_dispatch.load_specs(root)

    def test_command_display_metadata_is_never_tokenized(self) -> None:
        """Shell-looking display metadata cannot alter the explicit argv route."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
        )
        catalog_path = root / "tools/catalog.yaml"
        catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        catalog["entries"][0]["command"] = (
            "python3 tools/echo.py | touch SHOULD_NOT_EXIST"
        )
        catalog_path.write_text(yaml.safe_dump(catalog), encoding="utf-8")
        specs, _ = tool_dispatch.load_specs(root)
        self.assertEqual(specs["echo"].argv, ("python3", "tools/echo.py"))

    def test_parity_fixture_requires_all_observed_fields(self) -> None:
        """A fixture row without measured I/O/path fields cannot cut over."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
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
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
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
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            }
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
        self.assertNotIn(
            "AGENT_CANON_SECRET",
            tool_dispatch._environment(
                root,
                tool_dispatch.load_specs(root)[0]["echo"],
                root / "control/runtime",
                None,
            ),
        )

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
                    "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT": str(
                        image / "image-dependencies"
                    ),
                    "AGENT_CANON_RUNTIME_TOOLS_ROOT": str(root),
                    "AGENT_CANON_IMAGE_MARKER_DIGEST": "sha256:"
                    + hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest(),
                    "AGENT_CANON_RUNTIME_MARKER_DIGEST": "sha256:"
                    + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest(),
                    "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime),
                }
            )
            status = tool_dispatch.main(
                (
                    "--container-exec",
                    "--root",
                    str(root),
                    "run",
                    "echo",
                    "--",
                    "a value",
                )
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
                    "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT": str(
                        _image / "image-dependencies"
                    ),
                    "AGENT_CANON_RUNTIME_TOOLS_ROOT": str(root),
                    "AGENT_CANON_IMAGE_MARKER_DIGEST": "sha256:" + "0" * 64,
                    "AGENT_CANON_RUNTIME_MARKER_DIGEST": "sha256:"
                    + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest(),
                    "AGENT_CANON_CONTROL_PARENT_ROOT": str(control),
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime),
                }
            )
            with self.assertRaisesRegex(
                tool_dispatch.DispatchError, "container-exec-not-authorized"
            ):
                tool_dispatch._validate_container_context(root)
            os.environ["AGENT_CANON_EXECUTION_PLANE"] = "tool-container"
            with self.assertRaisesRegex(
                tool_dispatch.DispatchError, "container-marker-digest-mismatch"
            ):
                tool_dispatch._validate_container_context(root)
        finally:
            self._restore_environment(previous)

    def test_pending_parity_keeps_legacy_route(self) -> None:
        """An unverified entry is never cut over through the new route."""
        root = self._minimal_root(
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "pending",
            }
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
            (root / "tools/catalog.yaml").write_text(
                yaml.safe_dump(catalog), encoding="utf-8"
            )
            (
                root / "tests/fixtures/tool_dispatch/public-command-parity.json"
            ).write_text(
                json.dumps(
                    {
                        "schema": "agent-canon-tool-parity/v1",
                        "version": 1,
                        "entries": [{"id": "echo"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(tool_dispatch.DispatchError, "duplicate-id"):
                tool_dispatch.load_specs(root)

    def _entry(
        self,
        tool_id: str,
        dispatch: dict[str, object] | None = None,
        path: str = "tools/echo.py",
    ) -> dict[str, object]:
        """Build one minimal public entry for a fixture repository."""
        return {
            "id": tool_id,
            "path": path,
            "summary": "fixture",
            "family": "agent_tools",
            "role": "helper",
            "status": "canonical",
            "command": "python3 tools/echo.py",
            "writes": False,
            "dispatch": dispatch
            or {
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
                "parity": "verified",
            },
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

    def _minimal_root(
        self,
        dispatch: dict[str, object],
        *,
        tool_id: str = "echo",
        path: str = "tools/echo.py",
    ) -> Path:
        """Create a temporary public-tool fixture root."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "tools").mkdir()
        (root / "tests/fixtures/tool_dispatch").mkdir(parents=True)
        tool_path = root / path
        tool_path.parent.mkdir(parents=True, exist_ok=True)
        tool_path.write_text("print('ok')\n", encoding="utf-8")
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
                "AGENT_CANON_TARGET_ROOT",
                "AGENT_CANON_MOUNT_REGISTRY",
                "AGENT_CANON_OUTPUT_ROOT",
            )
        }
        self.addCleanup(self._restore_environment, previous)
        os.environ["AGENT_CANON_CONTROL_PARENT_ROOT"] = str(control)
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
        os.environ["AGENT_CANON_TARGET_ROOT"] = str(root)
        # The fixture's state.json owns its targets; do not inherit the
        # resident's read-only mount registry for a different checkout.
        os.environ.pop("AGENT_CANON_MOUNT_REGISTRY", None)
        os.environ.pop("AGENT_CANON_OUTPUT_ROOT", None)
        (runtime / "state.json").write_text(
            json.dumps({"targets": {"fixture": {"root": str(root)}}}),
            encoding="utf-8",
        )
        (root / "tools/catalog.yaml").write_text(
            yaml.safe_dump(self._catalog([self._entry(tool_id, dispatch, path)])),
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
        (root / "tools/echo.py").write_text(
            "import sys; print(*sys.argv[1:])\n", encoding="utf-8"
        )
        (root / "tools/catalog.yaml").write_text(
            yaml.safe_dump(
                self._catalog(
                    [
                        self._entry(
                            "echo",
                            {
                                "runtime": "python",
                                "argv": ["python3", "tools/echo.py"],
                                "parity": "verified",
                            },
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
        (dependencies / "plan.json").write_text(
            '{"schema":"fixture"}\n', encoding="utf-8"
        )
        (image / tool_dispatch.CONTAINER_MARKER_NAME).write_bytes(
            tool_dispatch.CONTAINER_MARKER
        )
        (root / tool_dispatch.RUNTIME_MARKER_NAME).write_bytes(
            tool_dispatch.RUNTIME_MARKER
        )
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

    @staticmethod
    def _restore_optional_environment(key: str, value: str | None) -> None:
        """Restore one optional environment variable after a focused test."""
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _native_vl_convert_route(
    tmp_path: Path,
    monkeypatch,
) -> tuple[Path, Path, Path]:
    """Set up an isolated authenticated-tool context for a native render fixture."""
    image_root = tmp_path / "image"
    image_runtime = image_root / "runtime"
    dependencies_root = image_root / "image-dependencies"
    control_root = tmp_path / "control"
    runtime_root = control_root / "runtime"
    target_root = tmp_path / "target"
    output_root = runtime_root / "tool-output"
    home = runtime_root / "cache" / "home"
    for directory in (
        image_runtime,
        dependencies_root,
        runtime_root,
        target_root,
        home,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    marker_paths = (
        image_root / tool_dispatch.CONTAINER_MARKER_NAME,
        image_runtime / tool_dispatch.RUNTIME_MARKER_NAME,
        dependencies_root / "plan.json",
    )
    marker_paths[0].write_bytes(tool_dispatch.CONTAINER_MARKER)
    marker_paths[1].write_bytes(tool_dispatch.RUNTIME_MARKER)
    marker_paths[2].write_text(
        '{"schema":"agent-canon-test-image/v1"}\n', encoding="utf-8"
    )
    for marker in marker_paths:
        marker.chmod(0o444)
    (runtime_root / "state.json").write_text(
        json.dumps({"targets": {"fixture": {"root": str(target_root)}}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("AGENT_CANON_EXECUTION_PLANE", "tool-container")
    monkeypatch.setenv("AGENT_CANON_IMAGE_ROOT", str(image_root))
    monkeypatch.setenv(
        "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT", str(dependencies_root)
    )
    monkeypatch.setenv("AGENT_CANON_RUNTIME_TOOLS_ROOT", str(PROJECT_ROOT))
    monkeypatch.setenv(
        "AGENT_CANON_IMAGE_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest(),
    )
    monkeypatch.setenv(
        "AGENT_CANON_RUNTIME_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest(),
    )
    monkeypatch.setenv("AGENT_CANON_CONTROL_PARENT_ROOT", str(control_root))
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("AGENT_CANON_TARGET_ROOT", str(target_root))
    monkeypatch.setenv("AGENT_CANON_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGENT_CANON_MOUNT_REGISTRY", raising=False)
    return target_root, runtime_root, output_root


def test_vl_convert_native_argv_matches_direct_probe_and_parity_record(
    tmp_path: Path,
    monkeypatch,
    capfd,
) -> None:
    """The generic native route preserves the official renderer CLI contract."""
    target_root, runtime_root, output_root = _native_vl_convert_route(
        tmp_path, monkeypatch
    )
    spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["vl-convert"]
    probe_args = ("--version",)
    environment = tool_dispatch._environment(
        PROJECT_ROOT, spec, runtime_root, output_root
    )
    direct = subprocess.run(
        [*spec.argv, *probe_args],
        cwd=target_root,
        env=environment,
        check=False,
        capture_output=True,
    )
    routed_status = tool_dispatch._run_spec(
        PROJECT_ROOT,
        spec,
        probe_args,
        require_parity=False,
        container_exec=True,
    )
    routed_output = capfd.readouterr()
    direct_result = {
        "exit_code": direct.returncode,
        "stdout_sha256": hashlib.sha256(direct.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(direct.stderr).hexdigest(),
        "written_paths": [],
    }
    routed_result = {
        "exit_code": routed_status,
        "stdout_sha256": hashlib.sha256(routed_output.out.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(routed_output.err.encode("utf-8")).hexdigest(),
        "written_paths": [],
    }
    assert routed_result == direct_result
    parity_path = PROJECT_ROOT / spec.parity_fixture
    fixture = json.loads(parity_path.read_text(encoding="utf-8"))
    row = next(
        (entry for entry in fixture["entries"] if entry.get("id") == spec.tool_id),
        None,
    )
    if row is None:
        raise AssertionError(
            json.dumps(
                {
                    "id": spec.tool_id,
                    "probe_args": list(probe_args),
                    "observed": {
                        "argv": list(spec.argv),
                        "cwd": spec.cwd_policy,
                        "stdin": spec.stdin_policy,
                        "stdout": spec.stdout_policy,
                        "stderr": spec.stderr_policy,
                        "exit": spec.exit_policy,
                        "signal": spec.signal_policy,
                        "written_paths": list(spec.written_paths),
                    },
                    "legacy_result": direct_result,
                    "container_result": routed_result,
                },
                sort_keys=True,
            )
        )
    tool_dispatch._check_parity_fixture(PROJECT_ROOT, spec)
    assert row["probe_args"] == list(probe_args)


def test_vl_convert_renders_selected_spec_and_propagates_invalid_input(
    tmp_path: Path,
    monkeypatch,
    capfd,
) -> None:
    """The native renderer emits SVG and preserves its invalid-input failure."""
    target_root, runtime_root, output_root = _native_vl_convert_route(
        tmp_path, monkeypatch
    )
    spec = tool_dispatch.load_specs(PROJECT_ROOT)[0]["vl-convert"]
    input_path = target_root / "figure.vl.json"
    input_path.write_text(
        json.dumps(
            {
                "$schema": "https://vega.github.io/schema/vega-lite/v6.1.json",
                "description": "A static renderer smoke input with no domain data.",
                "data": {"values": [{"label": "renderer smoke"}]},
                "mark": "text",
                "encoding": {"text": {"field": "label", "type": "nominal"}},
            }
        ),
        encoding="utf-8",
    )
    output_path = output_root / "figure.svg"
    rendered = tool_dispatch.run_container_tool(
        PROJECT_ROOT,
        spec,
        (
            "vl2svg",
            "--input",
            input_path.name,
            "--output",
            str(output_path),
            "--vl-version",
            "6.1",
        ),
    )
    assert rendered == 0
    rendered_svg = output_path.read_bytes()
    assert b"<svg" in rendered_svg[:512]
    assert b"renderer smoke" in rendered_svg

    invalid_path = target_root / "invalid.vl.json"
    invalid_path.write_text("{", encoding="utf-8")
    failed_output = output_root / "invalid.svg"
    failure_status = tool_dispatch.run_container_tool(
        PROJECT_ROOT,
        spec,
        (
            "vl2svg",
            "--input",
            invalid_path.name,
            "--output",
            str(failed_output),
            "--vl-version",
            "6.1",
        ),
    )
    failure_output = capfd.readouterr()
    assert failure_status != 0
    assert failure_output.err or failure_output.out
    assert not failed_output.exists()


if __name__ == "__main__":
    unittest.main()
