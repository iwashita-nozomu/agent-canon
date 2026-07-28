"""Focused tests for shared VS Code task command portability."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASKS_JSON = PROJECT_ROOT / ".vscode" / "tasks.json"


def run_shell_command_in_workspace(workspace: Path, command: str) -> subprocess.CompletedProcess[str]:
    """Run one .vscode task command against a synthetic workspace."""
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
        """Write and chmod one executable python stub."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env python3\n" + text + "\n", encoding="utf-8")
        path.chmod(0o755)

    def test_vscode_tasks_are_portable(self) -> None:
        """Task commands should resolve in both standalone and parent topologies."""
        tasks = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
        commands = {
            task["label"]: task["command"] for task in tasks["tasks"]
        }

        for label, command in commands.items():
            self.assertIn("tools/agent-canon", command, label)
            self.assertIn("AGENT_CANON", command, label)

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "tools" / "bin").mkdir(parents=True)
            self.write_exec(
                workspace / "tools" / "bin" / "agent-canon",
                '#!/usr/bin/env bash\necho DOCS_BIN=standalone',
            )
            self.write_py(
                workspace / "tools" / "agent_tools" / "check_convention_compliance.py",
                'print("CONVENTION=standalone")',
            )
            self.write_py(
                workspace / "tools" / "agent_tools" / "check_dependency_headers.py",
                'print("DEP_HEADERS=standalone")',
            )
            self.write_exec(
                workspace / "tools" / "agent_tools" / "scan_dependency_headers.sh",
                '#!/usr/bin/env bash\necho SCAN_HEADERS=standalone',
            )
            self.write_exec(
                workspace / "tools" / "agent_tools" / "check_dependency_header_format.sh",
                '#!/usr/bin/env bash\necho CHECK_HEADER_FORMAT=standalone',
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
            self.assertEqual(convention.returncode, 0, convention.stderr)
            self.assertIn("CONVENTION=standalone", convention.stdout)
            self.assertEqual(headers.returncode, 0, headers.stderr)
            self.assertIn("DEP_HEADERS=standalone", headers.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            (workspace / "tools" / "agent-canon" / "agent_tools").mkdir(parents=True)
            self.write_exec(
                workspace / "tools" / "agent-canon" / "bin" / "agent-canon",
                '#!/usr/bin/env bash\necho DOCS_BIN=parent',
            )
            self.write_py(
                workspace / "tools" / "agent-canon" / "agent_tools" / "check_convention_compliance.py",
                'print("CONVENTION=parent")',
            )
            self.write_py(
                workspace / "tools" / "agent-canon" / "agent_tools" / "check_dependency_headers.py",
                'print("DEP_HEADERS=parent")',
            )
            self.write_exec(
                workspace / "tools" / "agent-canon" / "agent_tools" / "scan_dependency_headers.sh",
                '#!/usr/bin/env bash\necho SCAN_HEADERS=parent',
            )
            self.write_exec(
                workspace / "tools" / "agent-canon" / "agent_tools" / "check_dependency_header_format.sh",
                '#!/usr/bin/env bash\necho CHECK_HEADER_FORMAT=parent',
            )

            docs = run_shell_command_in_workspace(workspace, commands["AgentCanon: Docs Check"])
            convention = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Convention Check"]
            )
            headers = run_shell_command_in_workspace(
                workspace, commands["AgentCanon: Dependency Headers"]
            )
            self.assertEqual(docs.returncode, 0, docs.stderr)
            self.assertIn("DOCS_BIN=parent", docs.stdout)
            self.assertEqual(convention.returncode, 0, convention.stderr)
            self.assertIn("CONVENTION=parent", convention.stdout)
            self.assertEqual(headers.returncode, 0, headers.stderr)
            self.assertIn("DEP_HEADERS=parent", headers.stdout)


if __name__ == "__main__":
    unittest.main()
