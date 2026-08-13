"""Focused tests for agent_canon_source_root CLI delegation."""

# @dependency-start
# contract test
# responsibility Verifies CLI command execution anchored to the resolved source root.
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves source roots.
# downstream implementation ../../tools/agent_tools/skill_tool_commands.py handles delegated commands.
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
PUBLIC_RESOLVER = "tools/agent-canon/agent_tools/agent_canon_source_root.py"
sys.path.insert(0, str(TOOLS_ROOT))

from agent_canon_source_root import (  # noqa: E402
    LAYOUT_VENDORED,
    RootResolution,
    SourceRootFailure,
    build_parser,
    resolve_agent_canon_source_root,
    run,
)

_SYNTHETIC_ROOT_BOUNDARY_ENV_KEYS = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_PREFIX",
)


class AgentCanonSourceRootCLITests(unittest.TestCase):
    """Validate CLI subcommand wiring without touching real owner roots."""

    def _mock_resolution(self, command_root: Path) -> RootResolution:
        return RootResolution(
            current_repository_root=command_root,
            source_root=command_root,
            layout="standalone",
            canon_root=command_root,
        )

    def _synthetic_root_environment(
        self, command_root: Path, overrides: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Bind fixture child state to its synthetic repository root."""
        environment = os.environ.copy()
        for key in _SYNTHETIC_ROOT_BOUNDARY_ENV_KEYS:
            environment.pop(key, None)
        fixture_tmp = command_root / ".agent-canon" / "tmp"
        environment.update(
            {
                "TMPDIR": str(fixture_tmp),
                "TEMP": str(fixture_tmp),
                "TMP": str(fixture_tmp),
            }
        )
        if overrides:
            environment.update(overrides)
        return environment

    def _write_post_create_fixture(
        self, root: Path, *, derived: bool
    ) -> tuple[Path, Path, Path]:
        """Create a minimal standalone or vendored resolver lifecycle fixture."""
        parent = root / "parent"
        source = (
            parent / "vendor" / "agent-canon" if derived else root / "agent-canon"
        )
        workspace = parent if derived else source
        (source / "agents" / "skills").mkdir(parents=True)
        (source / "tools" / "agent_tools").mkdir(parents=True)
        (source / "agents" / "skills" / "catalog.yaml").write_text(
            "skills: []\n", encoding="utf-8"
        )
        resolver_source = (
            PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_source_root.py"
        )
        shutil.copy2(
            resolver_source,
            source / "tools" / "agent_tools" / resolver_source.name,
        )
        shutil.copy2(
            PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
            source / "tools" / "agent_tools" / "parent_root_side_effects.py",
        )
        devcontainer = source / ".devcontainer"
        devcontainer.mkdir(parents=True)
        shutil.copy2(
            PROJECT_ROOT / ".devcontainer" / "devcontainer.json",
            devcontainer / "devcontainer.json",
        )
        entrypoint_source = PROJECT_ROOT / ".devcontainer" / "post-create-entrypoint.sh"
        shutil.copy2(entrypoint_source, devcontainer / entrypoint_source.name)
        (devcontainer / entrypoint_source.name).chmod(0o755)
        (devcontainer / "post-create.sh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf 'shared\\n' >> \"$1/order.log\"\n"
            "exit \"${SHARED_STATUS:-0}\"\n",
            encoding="utf-8",
        )
        (devcontainer / "post-create.sh").chmod(0o755)
        (devcontainer / "generate-runtime-compose.sh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf 'initialize\\n' >> \"${AGENT_CANON_TEST_LOG}\"\n",
            encoding="utf-8",
        )
        (devcontainer / "generate-runtime-compose.sh").chmod(0o755)
        (devcontainer / "post-attach.sh").write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "printf 'attach\\n' >> \"${AGENT_CANON_TEST_LOG}\"\n",
            encoding="utf-8",
        )
        (devcontainer / "post-attach.sh").chmod(0o755)
        if derived:
            subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
            parent_devcontainer = parent / ".devcontainer"
            parent_devcontainer.mkdir(parents=True)
            (parent_devcontainer / "post-create-parent.sh").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "printf 'parent\\n' >> \"$1/order.log\"\n"
                "exit \"${PARENT_STATUS:-0}\"\n",
                encoding="utf-8",
            )
            (parent_devcontainer / "post-create-parent.sh").chmod(0o755)
            shutil.copy2(
                source / ".devcontainer" / "devcontainer.json",
                parent_devcontainer / "devcontainer.json",
            )
            (parent / "tools").mkdir(parents=True)
            (parent / "tools" / "agent-canon").symlink_to(
                "../vendor/agent-canon/tools", target_is_directory=True
            )
            command_root = parent
        else:
            subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
            (source / "tools" / "agent-canon").symlink_to(
                ".", target_is_directory=True
            )
            command_root = source
        return source, workspace, command_root

    def _run_post_create_fixture(
        self,
        workspace: Path,
        command_root: Path,
        *,
        shared_status: int = 0,
        parent_status: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        """Run the tracked post-create entrypoint through the public resolver."""
        return subprocess.run(
            [
                sys.executable,
                PUBLIC_RESOLVER,
                "exec",
                ".devcontainer/post-create-entrypoint.sh",
                str(workspace),
            ],
            cwd=command_root,
            env={
                **self._synthetic_root_environment(command_root),
                "SHARED_STATUS": str(shared_status),
                "PARENT_STATUS": str(parent_status),
            },
            check=False,
            capture_output=True,
            text=True,
        )

    def test_exec_parser_accepts_command(self) -> None:
        """Accept the exec mode with an AgentCanon entrypoint and arguments."""
        parser = build_parser()
        parsed = parser.parse_args(["exec", "tools/sync_agent_canon.sh", "check"])
        self.assertEqual(parsed.mode, "exec")
        self.assertEqual(parsed.command, "tools/sync_agent_canon.sh")
        self.assertEqual(parsed.args, ["check"])

    def test_public_entrypoints_are_executable_for_source_root_dispatch(self) -> None:
        """Source-root dispatch targets keep their shebang entrypoint mode."""
        for relative in (
            "tools/update_agent_canon.sh",
            "tools/ci/check_agent_canon_latest.sh",
            "tools/ci/check_agent_canon_pr.sh",
            "tools/agent_tools/surface_manifest.py",
            "tools/agent_tools/dependency_module_change.py",
        ):
            with self.subTest(path=relative):
                mode = (PROJECT_ROOT / relative).stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, relative)

    def test_exec_command_runs_tracked_entrypoint_script(self) -> None:
        """Run the public sync check in an isolated standalone source clone."""
        with tempfile.TemporaryDirectory() as workspace:
            clone = Path(workspace) / "agent-canon"
            copy_ignore = shutil.ignore_patterns(
                ".git",
                ".agent-canon",
                "reports",
                "workspace",
                "__pycache__",
                ".pytest_cache",
                ".ruff_cache",
            )

            def ignore_standalone_public_view(
                directory: str, names: list[str]
            ) -> set[str]:
                """Avoid following the source self-view while copying the fixture."""
                ignored = set(copy_ignore(directory, names))
                if Path(directory).resolve() == (PROJECT_ROOT / "tools").resolve():
                    ignored.add("agent-canon")
                return ignored

            shutil.copytree(
                PROJECT_ROOT,
                clone,
                symlinks=True,
                ignore=ignore_standalone_public_view,
            )
            subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
            (clone / "tools" / "agent-canon").symlink_to(
                ".", target_is_directory=True
            )
            public_view = clone / "tools" / "agent-canon"
            self.assertTrue(public_view.is_symlink())
            self.assertEqual(os.readlink(public_view), ".")
            script = clone / "tools" / "sync_agent_canon.sh"
            self.assertEqual(script.stat().st_mode & stat.S_IXUSR, stat.S_IXUSR)
            result = subprocess.run(
                [
                    sys.executable,
                    PUBLIC_RESOLVER,
                    "exec",
                    "tools/sync_agent_canon.sh",
                    "check",
                ],
                cwd=clone,
                check=False,
                capture_output=True,
                text=True,
                env=self._synthetic_root_environment(clone),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("shared surface source manifest is valid", result.stdout)

    def test_exec_command_propagates_nonzero_exit(self) -> None:
        """Propagate a non-zero delegated command return code to the caller."""
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            script = root / "tools" / "agent_tool.sh"
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                "#!/usr/bin/env sh\n"
                "if [ \"$1\" = \"pass\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n"
            )
            script.chmod(stat.S_IXUSR | stat.S_IRUSR)

            parser = build_parser().parse_args(["exec", "tools/agent_tool.sh", "fail"])
            with patch.dict(
                os.environ,
                self._synthetic_root_environment(root),
                clear=True,
            ):
                result = run(parser, resolver=lambda _: self._mock_resolution(root))
            self.assertEqual(result, 1)

    def test_post_create_entrypoint_runs_shared_then_derived_hook(self) -> None:
        """Standalone and derived layouts invoke the real entrypoint through resolver."""
        for derived in (False, True):
            with self.subTest(derived=derived):
                with tempfile.TemporaryDirectory() as workspace:
                    source, selected_workspace, command_root = self._write_post_create_fixture(
                        Path(workspace), derived=derived
                    )
                    result = self._run_post_create_fixture(
                        selected_workspace, command_root
                    )

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    expected = "shared\nparent\n" if derived else "shared\n"
                    self.assertEqual(
                        (selected_workspace / "order.log").read_text(encoding="utf-8"),
                        expected,
                    )

    def test_post_create_entrypoint_propagates_stage_status(self) -> None:
        """A failed shared or derived stage returns its exact status to the resolver."""
        cases = ((17, 0, 17, "shared\n"), (0, 23, 23, "shared\nparent\n"))
        for shared_status, parent_status, expected_status, expected_order in cases:
            with self.subTest(shared_status=shared_status, parent_status=parent_status):
                with tempfile.TemporaryDirectory() as workspace:
                    source, selected_workspace, command_root = self._write_post_create_fixture(
                        Path(workspace), derived=True
                    )
                    result = self._run_post_create_fixture(
                        selected_workspace,
                        command_root,
                        shared_status=shared_status,
                        parent_status=parent_status,
                    )

                    self.assertEqual(
                        result.returncode,
                        expected_status,
                        result.stdout + result.stderr,
                    )
                    self.assertEqual(
                        (selected_workspace / "order.log").read_text(encoding="utf-8"),
                        expected_order,
                    )

    def test_devcontainer_json_commands_use_public_view(self) -> None:
        """Run all lifecycle commands from the standalone and derived public view."""
        for derived in (False, True):
            with self.subTest(derived=derived):
                with tempfile.TemporaryDirectory() as workspace:
                    root = Path(workspace)
                    source, selected_workspace, command_root = (
                        self._write_post_create_fixture(root, derived=derived)
                    )
                    public_view = command_root / "tools" / "agent-canon"
                    self.assertTrue(public_view.is_symlink())
                    config_path = command_root / ".devcontainer" / "devcontainer.json"
                    self.assertTrue(config_path.is_file())
                    self.assertFalse(config_path.is_symlink())
                    if derived:
                        self.assertNotEqual(config_path, source / ".devcontainer" / "devcontainer.json")
                    config = json.loads(
                        (command_root / ".devcontainer" / "devcontainer.json")
                        .read_text(encoding="utf-8")
                    )
                    test_log = root / "devcontainer-command.log"
                    environment = self._synthetic_root_environment(
                        command_root,
                        {"AGENT_CANON_TEST_LOG": str(test_log)},
                    )
                    for key in (
                        "initializeCommand",
                        "postCreateCommand",
                        "postAttachCommand",
                    ):
                        command = str(config[key]).replace(
                            "/workspace/${localWorkspaceFolderBasename}",
                            str(selected_workspace),
                        )
                        self.assertIn(PUBLIC_RESOLVER, command)
                        result = subprocess.run(
                            ["bash", "-lc", command],
                            cwd=command_root,
                            env=environment,
                            check=False,
                            capture_output=True,
                            text=True,
                        )
                        self.assertEqual(
                            result.returncode,
                            0,
                            result.stdout + result.stderr,
                        )
                    self.assertEqual(
                        test_log.read_text(encoding="utf-8"),
                        "initialize\nattach\n",
                    )
                    expected = "shared\nparent\n" if derived else "shared\n"
                    self.assertEqual(
                        (selected_workspace / "order.log").read_text(encoding="utf-8"),
                        expected,
                    )

    def test_exec_command_enforces_resolved_source_root(self) -> None:
        """Reject commands resolving outside the source-root contract."""
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            parser = build_parser().parse_args(
                ["exec", str(root / "outside.sh"), "pass"]
            )
            with self.assertRaises(SourceRootFailure):
                run(parser, resolver=lambda _: self._mock_resolution(root))

    def test_vendored_submodule_cwd_resolves_parent_as_active_root(self) -> None:
        """Resolve the derived parent even when invocation starts in the submodule."""
        with tempfile.TemporaryDirectory() as workspace:
            parent = Path(workspace) / "parent"
            source = parent / "vendor" / "agent-canon"
            catalog = source / "agents" / "skills" / "catalog.yaml"
            subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
            catalog.parent.mkdir(parents=True)
            catalog.write_text("skills: []\n", encoding="utf-8")

            resolution = resolve_agent_canon_source_root(source / "tools")

            self.assertEqual(resolution.current_repository_root, parent.resolve())
            self.assertEqual(resolution.source_root, source.resolve())
            self.assertEqual(resolution.layout, LAYOUT_VENDORED)
