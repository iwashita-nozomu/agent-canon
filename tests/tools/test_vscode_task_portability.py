"""Focused tests for shared VS Code task command portability."""

# @dependency-start
# contract test
# responsibility Verifies VS Code commands resolve the canonical AgentCanon tool root in both layouts.
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared VS Code surface policy
# upstream implementation ../../tools/runtime/dispatch/tool_dispatch.py shared AgentCanon tool root
# downstream implementation ../../.vscode/tasks.json shared validation task commands
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASKS_JSON = PROJECT_ROOT / ".vscode" / "tasks.json"
SETTINGS_JSON = PROJECT_ROOT / ".vscode" / "settings.json"
def run_shell_command_in_workspace(workspace: Path, command: str) -> subprocess.CompletedProcess[str]:
    """Run one VS Code task command against a synthetic workspace."""
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "workspaceFolder": str(workspace)},
    )


class VscodeTaskPortabilityTest(unittest.TestCase):
    """Ensure task commands auto-detect standalone and parent tool layouts."""

    def write_exec(self, path: Path, text: str) -> None:
        """Write and chmod one executable shell stub."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        path.chmod(0o755)

    def write_py(self, path: Path, text: str) -> None:
        """Write and chmod one executable Python stub."""
        self.write_exec(path, "#!/usr/bin/env python3\n" + text)

    def task_commands(self) -> dict[str, str]:
        """Return task commands keyed by label."""
        tasks = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
        return {task["label"]: task["command"] for task in tasks["tasks"]}

    def test_settings_and_tasks_use_portable_tool_views(self) -> None:
        """Shared settings and tasks use only the standalone source checkout."""
        commands = self.task_commands()
        for label, command in commands.items():
            self.assertIn("${workspaceFolder}", command, label)
            self.assertNotIn("tools/repository/support/repo_paths.sh", command, label)
            self.assertNotIn("tools/agent-canon", command, label)
            self.assertNotIn("CANON_TOOLS_ROOT", command, label)
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        self.assertIn("./tools", settings["python.analysis.extraPaths"])
        self.assertNotIn("./tools/agent-canon", settings["python.analysis.extraPaths"])
        self.assertNotIn("./tools/agent-canon/agent_tools", settings["python.analysis.extraPaths"])
        self.assertFalse((PROJECT_ROOT / ".code-workspace").exists())

    def test_vscode_tasks_resolve_standalone_tools(self) -> None:
        """Task commands should resolve tools/agent_tools in standalone mode."""
        commands = self.task_commands()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            self.write_exec(
                workspace / "tools" / "bin" / "agent-canon",
                '#!/usr/bin/env bash\necho DOCS_BIN=standalone',
            )
            self.write_py(
                workspace / "tools" / "validation" / "semantic" / "convention" / "check_convention_compliance.py",
                'print("CONVENTION=standalone")',
            )
            self.write_py(
                workspace / "tools" / "validation" / "semantic" / "dependencies" / "check_dependency_headers.py",
                'print("DEP_HEADERS=standalone")',
            )
            self.write_exec(
                workspace / "tools" / "analysis" / "dependencies" / "scan_dependency_headers.sh",
                "echo SCAN_HEADERS=standalone",
            )
            self.write_exec(
                workspace / "tools" / "validation" / "semantic" / "dependencies" / "check_dependency_header_format.sh",
                "echo CHECK_HEADER_FORMAT=standalone",
            )

            self.assertIn("DOCS_BIN=standalone", run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Docs Check"]
            ).stdout)
            convention = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Convention Check"]
            )
            headers = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Dependency Headers"]
            )
            self.assertEqual(convention.returncode, 0, convention.stderr)
            self.assertIn("CONVENTION=standalone", convention.stdout)
            self.assertEqual(headers.returncode, 0, headers.stderr)
            self.assertIn("DEP_HEADERS=standalone", headers.stdout)

    def test_vscode_tasks_ignore_parent_tool_view(self) -> None:
        """Task commands must not revive a parent-local or vendor tool view."""
        commands = self.task_commands()
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            # A conflicting legacy view must never win over the source checkout.
            self.write_exec(workspace / "tools" / "agent-canon" / "bin" / "agent-canon", "echo BAD_PARENT_VIEW")
            self.write_exec(workspace / "tools" / "bin" / "agent-canon", "echo DOCS_BIN=standalone")
            self.write_py(
                workspace / "tools" / "validation" / "semantic" / "convention" / "check_convention_compliance.py",
                'print("CONVENTION=standalone")',
            )
            self.write_py(
                workspace / "tools" / "validation" / "semantic" / "dependencies" / "check_dependency_headers.py",
                'print("DEP_HEADERS=standalone")',
            )
            self.write_exec(
                workspace / "tools" / "analysis" / "dependencies" / "scan_dependency_headers.sh",
                "echo SCAN_HEADERS=standalone",
            )
            self.write_exec(
                workspace / "tools" / "validation" / "semantic" / "dependencies" / "check_dependency_header_format.sh",
                "echo CHECK_HEADER_FORMAT=standalone",
            )

            docs = run_shell_command_in_workspace(workspace, commands["AgentCanon: Docs Check"])
            convention = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Convention Check"]
            )
            headers = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Dependency Headers"]
            )
            self.assertEqual(docs.returncode, 0, docs.stderr)
            self.assertIn("DOCS_BIN=standalone", docs.stdout)
            self.assertNotIn("BAD_PARENT_VIEW", docs.stdout)
            self.assertEqual(convention.returncode, 0, convention.stderr)
            self.assertIn("CONVENTION=standalone", convention.stdout)
            self.assertEqual(headers.returncode, 0, headers.stderr)
            self.assertIn("DEP_HEADERS=standalone", headers.stdout)


if __name__ == "__main__":
    unittest.main()
