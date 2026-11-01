# @dependency-start
# contract test
# responsibility Tests typed catalog loading and argv-safe native dispatch.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/tool_dispatch.rs owns dispatcher behavior
# upstream design ../../tools/catalog.yaml owns runtime schema and public inventory
# downstream implementation ../../tools/bin/agent-canon owns the stable CLI namespace
# @dependency-end

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTAINER_MARKER = b"agent-canon-tool-container/v1\n"
RUNTIME_MARKER = b"agent-canon-runtime/v1\n"
CONTAINER_MARKER_NAME = ".agent-canon-tool-container"
RUNTIME_MARKER_NAME = ".agent-canon-runtime"


def _native_binary() -> Path:
    """Resolve the already-built native CLI without a Python fallback."""
    configured = os.environ.get("AGENT_CANON_NATIVE_BIN")
    if configured:
        return Path(configured)
    crate = PROJECT_ROOT / "tools/runtime/dispatch/agent-canon"
    target = Path(os.environ.get("CARGO_TARGET_DIR") or crate / "target")
    for profile in ("debug", "release"):
        candidate = target / profile / "agent-canon"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    cache_root = Path(
        os.environ.get("AGENT_CANON_CACHE_ROOT") or "/var/lib/agent-canon/cache"
    )
    candidate = cache_root / "bin" / "agent-canon"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    raise AssertionError("the native agent-canon CLI must be built before tool dispatch tests")


def _entry(
    tool_id: str = "echo",
    *,
    path: str = "tools/echo.py",
    argv: list[str] | str | None = None,
    dispatch: dict[str, object] | None = None,
    writes: bool = False,
) -> dict[str, object]:
    descriptor: dict[str, object] = {
        "runtime": "python",
        "argv": ["python3", "tools/echo.py"] if argv is None else argv,
        "cwd": "target-root",
        "env": "allowlisted",
        "stdin": "captured",
        "stdout": "captured",
        "stderr": "captured",
        "exit": "propagate",
        "signal": "propagate",
        "side_effect": "read-only",
        "output_root": "none",
        "written_paths": [],
    }
    if dispatch is not None:
        descriptor.update(dispatch)
    return {
        "id": tool_id,
        "path": path,
        "command": "python3 tools/echo.py $(must-never-be-evaluated)",
        "writes": writes,
        "dispatch": descriptor,
    }


class NativeToolDispatchTests(unittest.TestCase):
    """Exercise native tool dispatch through its public JSON and process routes."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "source"
        self.tools = self.root / "tools"
        self.tools.mkdir(parents=True)
        self.target = self.base / "target"
        self.target.mkdir()
        self.control = self.base / "control"
        self.runtime = self.control / "runtime"
        self.runtime.mkdir(parents=True)
        self.image_number = 0
        (self.runtime / "state.json").write_text(
            json.dumps({"targets": {"fixture": {"root": str(self.target)}}}),
            encoding="utf-8",
        )
        self.captured_request = self.base / "request.json"
        self._write_echo_tool()
        self._write_bootstrap()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(self.control),
            "AGENT_CANON_RUNTIME_ROOT": str(self.runtime),
            "AGENT_CANON_TARGET_ROOT": str(self.target),
            "DISPATCH_TEST_SECRET": "must-not-be-forwarded",
            "AGENT_CANON_SECRET": "must-not-be-forwarded",
        }
        self._write_catalog([_entry()])

    def _write_echo_tool(self) -> None:
        (self.tools / "echo.py").write_text(
            "import json, os, signal, sys\n"
            "payload = {\n"
            "  'args': sys.argv[1:],\n"
            "  'cwd': os.getcwd(),\n"
            "  'secret': os.environ.get('DISPATCH_TEST_SECRET'),\n"
            "  'git_config_count': os.environ.get('GIT_CONFIG_COUNT'),\n"
            "  'git_config_key_0': os.environ.get('GIT_CONFIG_KEY_0'),\n"
            "  'git_config_value_0': os.environ.get('GIT_CONFIG_VALUE_0'),\n"
            "  'git_config_key_1': os.environ.get('GIT_CONFIG_KEY_1'),\n"
            "  'stdin': sys.stdin.buffer.read().decode('utf-8'),\n"
            "}\n"
            "print(json.dumps(payload, sort_keys=True))\n"
            "print('dispatch-stderr', file=sys.stderr)\n"
            "if payload['args'][:1] == ['exit']:\n"
            "    raise SystemExit(int(payload['args'][1]))\n"
            "if payload['args'][:1] == ['signal']:\n"
            "    os.kill(os.getpid(), signal.SIGTERM)\n",
            encoding="utf-8",
        )

    def _write_bootstrap(self) -> None:
        bootstrap = self.root / "bootstrap.sh"
        bootstrap.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            f"capture = pathlib.Path({str(self.captured_request)!r})\n"
            "if '--request-json' in sys.argv:\n"
            "    request = json.loads(sys.argv[sys.argv.index('--request-json') + 1])\n"
            "    capture.write_text(json.dumps(request, sort_keys=True))\n"
            "    if request['child_args'][:1] == ['exit']:\n"
            "        raise SystemExit(int(request['child_args'][1]))\n"
            "else:\n"
            "    capture.write_text(json.dumps({'argv': sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        bootstrap.chmod(bootstrap.stat().st_mode | stat.S_IXUSR)

    def _write_catalog(self, entries: list[dict[str, object]]) -> None:
        (self.tools / "catalog.yaml").write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "catalog_kind": "agent_canon_tool_catalog",
                    "runtime_schema": {"version": 2},
                    "entries": entries,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _run(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
        environment = dict(self.env)
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [str(_native_binary()), "tool", *args],
            cwd=self.root,
            env=environment,
            check=False,
            capture_output=True,
        )

    def _container_environment(self) -> dict[str, str]:
        image_root = self.base / f"image-{self.image_number}"
        self.image_number += 1
        dependencies_root = image_root / "image-dependencies"
        image_runtime = image_root / "runtime"
        dependencies_root.mkdir(parents=True)
        image_runtime.mkdir(parents=True)
        container_marker = image_root / CONTAINER_MARKER_NAME
        runtime_marker = image_runtime / RUNTIME_MARKER_NAME
        plan = dependencies_root / "plan.json"
        container_marker.write_bytes(CONTAINER_MARKER)
        runtime_marker.write_bytes(RUNTIME_MARKER)
        plan.write_text('{"schema":"agent-canon-test-image/v1"}\n', encoding="utf-8")
        for marker in (container_marker, runtime_marker, plan):
            marker.chmod(0o444)
        return {
            "AGENT_CANON_EXECUTION_PLANE": "tool-container",
            "AGENT_CANON_IMAGE_ROOT": str(image_root),
            "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT": str(dependencies_root),
            "AGENT_CANON_RUNTIME_TOOLS_ROOT": str(self.root),
            "AGENT_CANON_IMAGE_MARKER_DIGEST": "sha256:" + hashlib.sha256(CONTAINER_MARKER).hexdigest(),
            "AGENT_CANON_RUNTIME_MARKER_DIGEST": "sha256:" + hashlib.sha256(RUNTIME_MARKER).hexdigest(),
        }

    def test_inventory_is_a_stable_versioned_json_projection(self) -> None:
        first = self._run("inventory", "--root", str(self.root), "--json")
        second = self._run("inventory", "--root", str(self.root), "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["schema"], "agent-canon-tool-inventory/v1")
        self.assertEqual(payload["catalog_runtime_schema"], 2)
        self.assertEqual(payload["entries"][0]["id"], "echo")
        self.assertEqual(payload["entries"][0]["argv"], ["python3", "tools/echo.py"])
        self.assertEqual(payload["entries"][0]["cwd"], "target-root")
        self.assertEqual(payload["entries"][0]["side_effect"], "read-only")
        self.assertEqual(payload["entries"][0]["output_root"], "none")

    def test_repository_inventory_keeps_native_and_python_dispatch_entries(self) -> None:
        result = subprocess.run(
            [
                str(_native_binary()),
                "tool",
                "inventory",
                "--root",
                str(PROJECT_ROOT),
                "--json",
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = {
            entry["id"]: entry for entry in json.loads(result.stdout)["entries"]
        }
        self.assertEqual(entries["quarto"]["runtime"], "native")
        self.assertEqual(entries["quarto"]["argv"], ["quarto"])
        self.assertEqual(
            entries["quarto"]["path"],
            "tools/runtime/dispatch/agent-canon/src/tool_dispatch.rs",
        )
        self.assertEqual(entries["generate-agent-runtime-dashboard"]["runtime"], "python")
        for entry in entries.values():
            self.assertIn(entry["runtime"], {"python", "rust", "native"})
            self.assertTrue(entry["argv"])
            self.assertEqual(entry["execution_plane"], "tool-container")
            self.assertIn(entry["cwd"], {"source-root", "target-root", "task-root", "explicit"})
            self.assertIn(entry["env"], {"allowlisted", "clean"})
            self.assertIn(
                entry["side_effect"],
                {"read-only", "external-artifact", "explicit-target-write"},
            )
        self.assertEqual(
            entries["issue-sync"]["argv"],
            ["python3", "tools/repository/github/issue_sync.py"],
        )
        self.assertEqual(entries["issue-sync"]["output_root"], "external-runtime")
        self.assertEqual(
            entries["generate-agent-runtime-dashboard"]["side_effect"],
            "external-artifact",
        )

    def test_run_builds_typed_bootstrap_request_without_shell_splitting(self) -> None:
        result = self._run(
            "run",
            "--root",
            str(self.root),
            "echo",
            "--",
            "two words",
            "$(touch marker)",
            extra_env={
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "color.ui",
                "GIT_CONFIG_VALUE_0": "always",
                "GIT_CONFIG_KEY_1": "safe.directory",
                "GIT_CONFIG_VALUE_1": "*",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(self.captured_request.read_text(encoding="utf-8"))
        self.assertEqual(request["schema"], "agent-canon.tool-exec-request.v1")
        self.assertEqual(request["tool_id"], "echo")
        self.assertEqual(request["source_root"], str(self.root))
        self.assertEqual(request["argv"], ["python3", "tools/echo.py", "two words", "$(touch marker)"])
        self.assertEqual(request["child_args"], ["two words", "$(touch marker)"])
        self.assertEqual(request["cwd"], str(self.target))
        self.assertEqual(request["cwd_policy"], "target-root")
        self.assertEqual(request["target_root"], str(self.target))
        self.assertEqual(request["stdin"], "captured")
        self.assertEqual(request["stdout"], "captured")
        self.assertEqual(request["stderr"], "captured")
        self.assertEqual(request["exit"], "propagate")
        self.assertEqual(request["signal"], "propagate")
        self.assertEqual(request["environment"]["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(request["environment"]["GIT_CONFIG_KEY_0"], "safe.directory")
        self.assertEqual(request["environment"]["GIT_CONFIG_VALUE_0"], str(self.target))
        self.assertNotIn("command", request)
        self.assertNotIn("DISPATCH_TEST_SECRET", request["environment"])
        self.assertNotIn("AGENT_CANON_SECRET", request["environment"])
        self.assertNotIn("GIT_CONFIG_KEY_1", request["environment"])
        self.assertEqual(request["environment"]["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(request["environment"]["AGENT_CANON_DISPATCH_RUNTIME"], "python")

    def test_native_descriptor_uses_the_same_typed_bootstrap_envelope(self) -> None:
        self._write_catalog(
            [
                _entry(
                    path="documents/native-command.md",
                    dispatch={
                        "runtime": "native",
                        "argv": ["quarto"],
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
                    },
                )
            ]
        )
        output_root = self.runtime / "tool-output"
        result = self._run(
            "run",
            "--root",
            str(self.root),
            "echo",
            "--",
            "pandoc",
            "paper.md",
            extra_env={"AGENT_CANON_OUTPUT_ROOT": str(output_root)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(self.captured_request.read_text(encoding="utf-8"))
        self.assertEqual(request["argv"], ["quarto", "pandoc", "paper.md"])
        self.assertEqual(request["child_args"], ["pandoc", "paper.md"])
        self.assertEqual(request["environment"]["AGENT_CANON_DISPATCH_RUNTIME"], "native")
        self.assertEqual(request["side_effect"], "external-artifact")
        self.assertEqual(request["output_root"], str(output_root))
        self.assertNotIn("runtime", request)

    def test_host_dispatch_forwards_bootstrap_exit_status(self) -> None:
        result = self._run("run", "--root", str(self.root), "echo", "--", "exit", "7")
        self.assertEqual(result.returncode, 7)

    def test_rust_cli_route_uses_registered_target_and_forwards_argv(self) -> None:
        result = self._run(
            "rust-cli", "--root", str(self.root), "--", "--version", "two words"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        request = json.loads(self.captured_request.read_text(encoding="utf-8"))
        self.assertEqual(
            request["argv"],
            [
                "--control-parent-root",
                str(self.control),
                "--runtime-root",
                str(self.runtime),
                "exec",
                "--root",
                str(self.target),
                "--",
                "agent-canon",
                "--version",
                "two words",
            ],
        )

    def test_issue_sync_accepts_only_receipt_operations(self) -> None:
        self._write_catalog([_entry("issue-sync", path="tools/issue_sync.py")])
        rejected = self._run(
            "run", "--root", str(self.root), "issue-sync", "--", "--issues"
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=container-route-restricted:", rejected.stderr)
        self.assertFalse(self.captured_request.exists())
        accepted = self._run(
            "run",
            "--root",
            str(self.root),
            "issue-sync",
            "--",
            "--receipt-preflight",
            "--repo",
            "iwashita-nozomu/agent-canon",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        request = json.loads(self.captured_request.read_text(encoding="utf-8"))
        self.assertEqual(request["child_args"][0], "--receipt-preflight")

    def test_catalog_validation_fails_closed_for_shell_strings_missing_dispatch_and_duplicates(self) -> None:
        self._write_catalog([_entry(argv="python3 tools/echo.py")])
        shell_string = self._run("inventory", "--root", str(self.root), "--json")
        self.assertEqual(shell_string.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=shell-string-rejected:", shell_string.stderr)

        entry = _entry()
        del entry["dispatch"]
        self._write_catalog([entry])
        missing_dispatch = self._run("inventory", "--root", str(self.root), "--json")
        self.assertEqual(missing_dispatch.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=missing-dispatch:", missing_dispatch.stderr)

        self._write_catalog([_entry(), _entry()])
        duplicate = self._run("inventory", "--root", str(self.root), "--json")
        self.assertEqual(duplicate.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=duplicate-id:echo", duplicate.stderr)

    def test_cli_errors_retain_explicit_runtime_and_argument_boundaries(self) -> None:
        no_runtime = subprocess.run(
            [str(_native_binary()), "tool", "run", "--root", str(self.root), "echo", "--"],
            cwd=self.root,
            env={"PATH": self.env["PATH"]},
            check=False,
            capture_output=True,
        )
        self.assertEqual(no_runtime.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=runtime-root-required:", no_runtime.stderr)
        missing_delimiter = self._run("run", "--root", str(self.root), "echo")
        self.assertEqual(missing_delimiter.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=missing-argument-delimiter:echo", missing_delimiter.stderr)
        unknown_option = self._run("run", "--root", str(self.root), "--unknown")
        self.assertEqual(unknown_option.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=unknown-option:--unknown", unknown_option.stderr)
        unknown_id = self._run("run", "--root", str(self.root), "missing", "--")
        self.assertEqual(unknown_id.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=unknown-id:missing", unknown_id.stderr)

    def test_container_dispatch_authenticates_markers_and_uses_registered_target(self) -> None:
        environment = self._container_environment()
        environment["AGENT_CANON_OUTPUT_ROOT"] = ""
        environment["AGENT_CANON_TARGET_ROOT"] = str(self.target)
        self._write_catalog(
            [
                _entry(
                    dispatch={
                        "runtime": "python",
                        "argv": ["python3", "tools/echo.py"],
                        "cwd": "target-root",
                        "env": "clean",
                        "stdin": "captured",
                        "stdout": "captured",
                        "stderr": "captured",
                        "exit": "propagate",
                        "signal": "propagate",
                        "side_effect": "read-only",
                        "output_root": "none",
                        "written_paths": [],
                    }
                )
            ]
        )
        environment.pop("AGENT_CANON_OUTPUT_ROOT")
        result = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            "two words",
            "tools/relative-child.txt",
            extra_env={
                **environment,
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "color.ui",
                "GIT_CONFIG_VALUE_0": "always",
                "GIT_CONFIG_KEY_1": "safe.directory",
                "GIT_CONFIG_VALUE_1": "*",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["args"], ["two words", "tools/relative-child.txt"])
        self.assertEqual(payload["cwd"], str(self.target))
        self.assertIsNone(payload["secret"])
        self.assertEqual(payload["git_config_count"], "1")
        self.assertEqual(payload["git_config_key_0"], "safe.directory")
        self.assertEqual(payload["git_config_value_0"], str(self.target))
        self.assertIsNone(payload["git_config_key_1"])
        self.assertEqual(payload["stdin"], "")
        self.assertEqual(result.stderr, b"dispatch-stderr\n")

    def test_container_execution_requires_the_authenticated_plane(self) -> None:
        environment = self._container_environment()
        environment.pop("AGENT_CANON_EXECUTION_PLANE")
        result = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            extra_env=environment,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            b"TOOL_DISPATCH_ERROR=container-exec-not-authorized:", result.stderr
        )

    def test_container_dispatch_propagates_exit_and_signal_status(self) -> None:
        environment = self._container_environment()
        read_only = _entry()
        self._write_catalog([read_only])
        exit_result = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            "exit",
            "9",
            extra_env=environment,
        )
        self.assertEqual(exit_result.returncode, 9)
        signal_result = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            "signal",
            extra_env=environment,
        )
        self.assertEqual(signal_result.returncode, 128 + signal.SIGTERM)

    def test_container_dispatch_rejects_spoofed_or_writable_markers(self) -> None:
        environment = self._container_environment()
        environment["AGENT_CANON_IMAGE_MARKER_DIGEST"] = "sha256:" + "0" * 64
        spoofed = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            extra_env=environment,
        )
        self.assertEqual(spoofed.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=container-marker-digest-mismatch:image", spoofed.stderr)

        environment = self._container_environment()
        image_marker = Path(environment["AGENT_CANON_IMAGE_ROOT"]) / CONTAINER_MARKER_NAME
        image_marker.chmod(0o644)
        writable = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            extra_env=environment,
        )
        self.assertEqual(writable.returncode, 2)
        self.assertIn(b"TOOL_DISPATCH_ERROR=container-marker-writable:", writable.stderr)

    def test_external_artifact_output_root_is_created_only_inside_runtime(self) -> None:
        environment = self._container_environment()
        output = self.runtime / "tool-output"
        environment["AGENT_CANON_OUTPUT_ROOT"] = str(output)
        descriptor = _entry(
            writes=True,
            dispatch={
                "runtime": "python",
                "argv": ["python3", "tools/echo.py"],
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
            },
        )
        self._write_catalog([descriptor])
        result = self._run(
            "run",
            "--container-exec",
            "--root",
            str(self.root),
            "echo",
            "--",
            extra_env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.is_dir())


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
    for directory in (image_runtime, dependencies_root, runtime_root, target_root, home):
        directory.mkdir(parents=True, exist_ok=True)

    marker_paths = (
        image_root / CONTAINER_MARKER_NAME,
        image_runtime / RUNTIME_MARKER_NAME,
        dependencies_root / "plan.json",
    )
    marker_paths[0].write_bytes(CONTAINER_MARKER)
    marker_paths[1].write_bytes(RUNTIME_MARKER)
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
    monkeypatch.setenv("AGENT_CANON_IMAGE_DEPENDENCIES_ROOT", str(dependencies_root))
    monkeypatch.setenv("AGENT_CANON_RUNTIME_TOOLS_ROOT", str(PROJECT_ROOT))
    monkeypatch.setenv(
        "AGENT_CANON_IMAGE_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(CONTAINER_MARKER).hexdigest(),
    )
    monkeypatch.setenv(
        "AGENT_CANON_RUNTIME_MARKER_DIGEST",
        "sha256:" + hashlib.sha256(RUNTIME_MARKER).hexdigest(),
    )
    monkeypatch.setenv("AGENT_CANON_CONTROL_PARENT_ROOT", str(control_root))
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("AGENT_CANON_TARGET_ROOT", str(target_root))
    monkeypatch.setenv("AGENT_CANON_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGENT_CANON_MOUNT_REGISTRY", raising=False)
    return target_root, runtime_root, output_root


def test_vl_convert_renders_selected_spec_and_propagates_invalid_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The native renderer emits SVG and preserves its invalid-input failure."""
    target_root, _runtime_root, output_root = _native_vl_convert_route(
        tmp_path, monkeypatch
    )
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
    rendered = subprocess.run(
        [
            str(_native_binary()),
            "tool",
            "run",
            "--container-exec",
            "--root",
            str(PROJECT_ROOT),
            "vl-convert",
            "--",
            "vl2svg",
            "--input",
            input_path.name,
            "--output",
            str(output_path),
            "--vl-version",
            "6.1",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
    )
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    rendered_svg = output_path.read_bytes()
    assert b"<svg" in rendered_svg[:512]
    assert b"renderer smoke" in rendered_svg

    invalid_path = target_root / "invalid.vl.json"
    invalid_path.write_text("{", encoding="utf-8")
    failed_output = output_root / "invalid.svg"
    failed = subprocess.run(
        [
            str(_native_binary()),
            "tool",
            "run",
            "--container-exec",
            "--root",
            str(PROJECT_ROOT),
            "vl-convert",
            "--",
            "vl2svg",
            "--input",
            invalid_path.name,
            "--output",
            str(failed_output),
            "--vl-version",
            "6.1",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
    )
    assert failed.returncode != 0
    assert failed.stdout or failed.stderr
    assert not failed_output.exists()


if __name__ == "__main__":
    unittest.main()
