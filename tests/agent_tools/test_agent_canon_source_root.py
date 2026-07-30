"""Focused tests for agent_canon_source_root CLI delegation."""

# @dependency-start
# contract test
# responsibility Verifies CLI command execution
#              anchored to the resolved source root.
# implementation: ../../tools/agent_tools/agent_canon_source_root.py
#              resolves source roots.
# implementation: ../../tools/agent_tools/skill_tool_commands.py
#              handles delegated commands.
# @dependency-end

from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from agent_canon_source_root import (  # noqa: E402
    RootResolution,
    SourceRootFailure,
    build_parser,
    run,
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

    def test_exec_parser_accepts_command(self) -> None:
        """Accept the exec mode with an AgentCanon entrypoint and arguments."""
        parser = build_parser()
        parsed = parser.parse_args(["exec", "tools/sync_agent_canon.sh", "check"])
        self.assertEqual(parsed.mode, "exec")
        self.assertEqual(parsed.command, "tools/sync_agent_canon.sh")
        self.assertEqual(parsed.args, ["check"])

    def test_exec_command_runs_tracked_entrypoint_script(self) -> None:
        """Run sync_agent_canon.sh through source-root exec."""
        script = PROJECT_ROOT / "tools" / "sync_agent_canon.sh"
        self.assertEqual(script.stat().st_mode & stat.S_IXUSR, stat.S_IXUSR)
        parser = build_parser().parse_args(
            ["exec", "tools/sync_agent_canon.sh", "check"]
        )
        result = run(parser, resolver=lambda _: self._mock_resolution(PROJECT_ROOT))
        self.assertNotEqual(result, 0)

    def test_exec_command_propagates_nonzero_exit(self) -> None:
        """Propagate a non-zero delegated command return code to the caller."""
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
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
