"""Focused tests for agent_canon_source_root CLI delegation."""

# @dependency-start
# contract test
# responsibility Verifies CLI command execution anchored to the resolved source root.
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves source roots.
# downstream implementation ../../tools/agent_tools/skill_tool_commands.py handles delegated commands.
# @dependency-end

from __future__ import annotations

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
PUBLIC_RESOLVER = "tools/agent_tools/agent_canon_source_root.py"
sys.path.insert(0, str(TOOLS_ROOT))

from agent_canon_source_root import (  # noqa: E402
    LAYOUT_EXTERNAL,
    LAYOUT_STANDALONE,
    RootResolution,
    SourceRootFailure,
    _default_pythonpath,
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
    "AGENT_CANON_RUNTIME_ROOT",
    "AGENT_CANON_RUNTIME_ROOT_DEV",
    "AGENT_CANON_RUNTIME_ROOT_INO",
)


class AgentCanonSourceRootCLITests(unittest.TestCase):
    """Validate CLI subcommand wiring without touching real owner roots."""

    def setUp(self) -> None:
        """Track external runtime fixtures for exact test-owned cleanup."""
        self._runtime_dirs: list[Path] = []
        self.addCleanup(self._cleanup_runtime_dirs)

    def _cleanup_runtime_dirs(self) -> None:
        """Remove only runtime directories created by this test instance."""
        for path in self._runtime_dirs:
            shutil.rmtree(path, ignore_errors=True)

    def test_pythonpath_rejects_untyped_agent_tools_alias(self) -> None:
        """Inherited repository tool roots cannot shadow the selected source."""
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            tools = root / "tools"
            (tools / "agent_tools").mkdir(parents=True)
            with patch.dict(os.environ, {"PYTHONPATH": str(tools / "agent_tools")}):
                with self.assertRaises(SourceRootFailure) as raised:
                    _default_pythonpath(root=root)
            self.assertEqual(
                raised.exception.code,
                "agent_canon_source_root_pythonpath_conflict",
            )

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
        """Bind fixture child state to an external temporary runtime root."""
        environment = os.environ.copy()
        for key in _SYNTHETIC_ROOT_BOUNDARY_ENV_KEYS:
            environment.pop(key, None)
        fixture_runtime = Path(tempfile.mkdtemp(prefix="agent-canon-source-root-"))
        self._runtime_dirs.append(fixture_runtime)
        fixture_tmp = fixture_runtime / "tmp"
        fixture_tmp.mkdir()
        environment.update(
            {
                "TMPDIR": str(fixture_tmp),
                "TEMP": str(fixture_tmp),
                "TMP": str(fixture_tmp),
                "AGENT_CANON_RUNTIME_ROOT": str(fixture_runtime),
            }
        )
        if overrides:
            environment.update(overrides)
        return environment

    def test_exec_parser_accepts_command(self) -> None:
        """Accept an exact source-relative command and its arguments."""
        parser = build_parser()
        parsed = parser.parse_args(["exec", "tools/agent_tools/route.py", "--list"])
        self.assertEqual(parsed.mode, "exec")
        self.assertEqual(parsed.command, "tools/agent_tools/route.py")
        self.assertEqual(parsed.args, ["--list"])

    def test_public_entrypoints_are_executable_for_source_root_dispatch(self) -> None:
        """Source-root dispatch targets keep their shebang entrypoint mode."""
        for relative in ("bootstrap.sh", "tools/bin/agent-canon"):
            with self.subTest(path=relative):
                mode = (PROJECT_ROOT / relative).stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, relative)

    def test_exec_command_runs_tracked_entrypoint_script(self) -> None:
        """Run a source-owned route from an isolated development clone."""
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

            shutil.copytree(
                PROJECT_ROOT,
                clone,
                symlinks=True,
                ignore=copy_ignore,
            )
            subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    PUBLIC_RESOLVER,
                    "exec",
                    "python3",
                    "tools/agent_tools/route.py",
                    "--list",
                ],
                cwd=clone,
                check=False,
                capture_output=True,
                text=True,
                env=self._synthetic_root_environment(clone),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("surface", result.stdout)

    def test_exec_command_supports_python_source_contract_readback(self) -> None:
        """The source wrapper can run a Python checker with source-relative paths."""
        with tempfile.TemporaryDirectory() as workspace:
            clone = Path(workspace) / "agent-canon"

            def ignore_clone_links(directory: str, names: list[str]) -> set[str]:
                """Avoid copying the source self-view into the temporary clone."""
                ignored = set(
                    shutil.ignore_patterns(
                        ".git", ".agent-canon", "reports", "workspace"
                    )(directory, names)
                )
                return ignored

            shutil.copytree(
                PROJECT_ROOT,
                clone,
                symlinks=True,
                ignore=ignore_clone_links,
            )
            subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    PUBLIC_RESOLVER,
                    "exec",
                    "python3",
                    "tools/agent_tools/repo_structure_contract.py",
                    "--root",
                    ".",
                    "--contract",
                    "documents/structure/repo-structure-contract.toml",
                ],
                cwd=clone,
                env=self._synthetic_root_environment(clone),
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_exec_command_enforces_resolved_source_root(self) -> None:
        """Reject commands resolving outside the source-root contract."""
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            parser = build_parser().parse_args(
                ["exec", str(root / "outside.sh"), "pass"]
            )
            with self.assertRaises(SourceRootFailure):
                run(parser, resolver=lambda _: self._mock_resolution(root))

    def test_standalone_resolution_uses_the_source_checkout(self) -> None:
        """A standalone source checkout is resolved without a parent vendor tree."""
        with tempfile.TemporaryDirectory() as workspace:
            source = Path(workspace) / "agent-canon"
            catalog = source / "agents" / "skills" / "catalog.yaml"
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
            catalog.parent.mkdir(parents=True)
            catalog.write_text("skills: []\n", encoding="utf-8")

            resolution = resolve_agent_canon_source_root(source / "tools")

            self.assertEqual(resolution.current_repository_root, source.resolve())
            self.assertEqual(resolution.source_root, source.resolve())
            self.assertEqual(resolution.layout, LAYOUT_STANDALONE)

    def test_explicit_external_source_resolution_has_no_vendor_fallback(self) -> None:
        """A parent selects an external development clone explicitly."""
        with tempfile.TemporaryDirectory() as workspace:
            parent = Path(workspace) / "parent"
            source = Path(workspace) / "development" / "agent-canon"
            parent.mkdir()
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
            (source / "agents" / "skills").mkdir(parents=True)
            (source / "agents" / "skills" / "catalog.yaml").write_text(
                "skills: []\n", encoding="utf-8"
            )

            resolution = resolve_agent_canon_source_root(
                parent,
                source_root=source,
                canon_root=source,
            )

            self.assertEqual(resolution.current_repository_root, parent.resolve())
            self.assertEqual(resolution.source_root, source.resolve())
            self.assertEqual(resolution.canon_root, source.resolve())
            self.assertEqual(resolution.layout, LAYOUT_EXTERNAL)

    def test_parent_without_source_or_vendor_fails_closed(self) -> None:
        """A consumer cannot acquire AgentCanon by scanning an implicit path."""
        with tempfile.TemporaryDirectory() as workspace:
            parent = Path(workspace) / "parent"
            parent.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
            with self.assertRaises(SourceRootFailure) as raised:
                resolve_agent_canon_source_root(parent)
            self.assertEqual(raised.exception.code, "agent_canon_source_root_missing")
