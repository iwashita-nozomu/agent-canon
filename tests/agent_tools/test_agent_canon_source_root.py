"""Focused tests for agent_canon_source_root CLI delegation."""

# @dependency-start
# contract test
# responsibility Verifies the short `exec` CLI for source-root anchored command execution.
# downstream implementation ../../tools/agent_tools/agent_canon_source_root.py exports the owner source-root resolver
# downstream implementation ../../tools/agent_tools/agent_tools/skill_tool_commands.py reads delegated command packets through a stable resolver contract
# @dependency-end

from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

import sys

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
        parser = build_parser()
        parsed = parser.parse_args(["exec", "tools/sync_agent_canon.sh", "check"])
        self.assertEqual(parsed.mode, "exec")
        self.assertEqual(parsed.command, "tools/sync_agent_canon.sh")
        self.assertEqual(parsed.args, ["check"])

    def test_exec_command_runs_under_resolved_source_root(self) -> None:
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
            script.chmod(stat.S_IRWXU)

            parser = build_parser().parse_args(["exec", "tools/agent_tool.sh", "pass"])
            result = run(parser, resolver=lambda _: self._mock_resolution(root))
            self.assertEqual(result, 0)

    def test_exec_command_enforces_resolved_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            parser = build_parser().parse_args(
                ["exec", str(root / "outside.sh"), "pass"]
            )
            with self.assertRaises(SourceRootFailure):
                run(parser, resolver=lambda _: self._mock_resolution(root))
