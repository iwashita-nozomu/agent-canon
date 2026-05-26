"""Tests for the Codex MCP inventory checker."""

# @dependency-start
# responsibility Tests test check mcp inventory behavior.
# upstream implementation ../../tools/agent_tools/check_mcp_inventory.py checks inventory  # noqa: E501
# upstream implementation ../../.codex/config.toml declares repo_mcp_server
# upstream design ../../mcp/README.md documents AgentCanon repo MCP ownership
# upstream design ../../.codex/README.md documents Codex MCP registration ownership
# upstream design ../../agents/skills/codex-task-workflow.md routes MCP preflight
# @dependency-end

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_mcp_inventory.py"
MCP_README = PROJECT_ROOT / "mcp" / "README.md"
CODEX_README = PROJECT_ROOT / ".codex" / "README.md"
CODEX_WORKFLOW = PROJECT_ROOT / "agents" / "canonical" / "CODEX_WORKFLOW.md"
CODEX_CONFIG_REFERENCE = PROJECT_ROOT / "documents" / "codex-configuration-reference.md"
CODEX_CONFIG_SLIDES = PROJECT_ROOT / "documents" / "codex-configuration-slides.md"
CODEX_TASK_SKILL = PROJECT_ROOT / "agents" / "skills" / "codex-task-workflow.md"


class McpInventoryCheckTest(unittest.TestCase):
    """Exercise MCP inventory checks through a fake Codex binary."""

    def write_fake_codex(
        self,
        directory: Path,
        payload: str,
        exit_code: int = 0,
    ) -> Path:
        """Create a fake Codex executable that emits one inventory payload."""
        codex = directory / "fake-codex"
        codex.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import sys
                if sys.argv[1:] != ["mcp", "list", "--json"]:
                    raise SystemExit(64)
                sys.stdout.write({payload!r})
                raise SystemExit({exit_code})
                """
            ),
            encoding="utf-8",
        )
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
        return codex

    def test_required_server_passes_when_present(self) -> None:
        """The checker accepts configured required servers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(
                Path(tmp_dir),
                (
                    '[{"name":"repo_mcp_server","command":"bash",'
                    '"args":["mcp/repo_mcp_server.sh"],"cwd":".",'
                    '"status":"enabled"}]'
                ),
            )
            mcp_dir = Path(tmp_dir) / "mcp"
            mcp_dir.mkdir()
            (mcp_dir / "repo_mcp_server.sh").write_text(
                "#!/usr/bin/env bash\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=Path(tmp_dir),
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ},
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MCP_SERVER=repo_mcp_server", result.stdout)
        self.assertIn("command=bash", result.stdout)
        self.assertIn("args=mcp/repo_mcp_server.sh", result.stdout)
        self.assertIn("cwd=.", result.stdout)
        self.assertIn("MCP_INVENTORY=pass", result.stdout)

    def test_required_server_fails_when_missing(self) -> None:
        """The checker fails closed instead of implying a local-process fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            codex = self.write_fake_codex(root, "[]")
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING_MCP_SERVERS=repo_mcp_server", result.stdout)
        self.assertIn(
            "NEXT_ACTION=configure_required_mcp_servers_before_work",
            result.stdout,
        )

    def test_missing_inventory_reports_ignored_project_config(self) -> None:
        """Report likely config loading failure when project config declares the MCP."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            codex = self.write_fake_codex(root, "[]")
            config_dir = root / ".codex"
            config_dir.mkdir()
            (config_dir / "config.toml").write_text(
                textwrap.dedent(
                    """\
                    [mcp_servers.repo_mcp_server]
                    command = "bash"
                    args = ["mcp/repo_mcp_server.sh"]
                    cwd = "."
                    enabled = true
                    """
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("PROJECT_CODEX_CONFIG_DECLARES_MISSING_MCP=yes", result.stdout)
        self.assertIn(
            "LIKELY_CAUSE=project_config_not_loaded_or_project_not_trusted",
            result.stdout,
        )
        self.assertIn(
            "EXPECTED_REPO_MCP_LAUNCHER=.codex/config.toml -> "
            "bash mcp/repo_mcp_server.sh",
            result.stdout,
        )
        self.assertIn(
            "REPAIR_REPO_MCP=trust_project_or_restore_.codex_and_mcp_link_root",
            result.stdout,
        )
        self.assertIn(
            "NEXT_ACTION=trust_project_or_fix_codex_config_loading_before_work",
            result.stdout,
        )

    def test_nested_codex_transport_shape_is_supported(self) -> None:
        """Support current Codex JSON transport nesting."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(
                Path(tmp_dir),
                (
                    '[{"name":"repo_mcp_server","enabled":true,'
                    '"transport":{"type":"stdio","command":"bash",'
                    '"args":["mcp/repo_mcp_server.sh"],"cwd":"."}}]'
                ),
            )
            mcp_dir = Path(tmp_dir) / "mcp"
            mcp_dir.mkdir()
            (mcp_dir / "repo_mcp_server.sh").write_text(
                "#!/usr/bin/env bash\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=Path(tmp_dir),
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("status=enabled", result.stdout)
        self.assertIn("command=bash", result.stdout)
        self.assertIn("args=mcp/repo_mcp_server.sh", result.stdout)
        self.assertIn("cwd=.", result.stdout)

    def test_required_server_fails_when_configured_cwd_is_missing(self) -> None:
        """The checker validates the configured MCP launcher cwd."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            codex = self.write_fake_codex(
                root,
                (
                    '[{"name":"repo_mcp_server","command":"bash",'
                    '"args":["mcp/repo_mcp_server.sh"],"cwd":"missing",'
                    '"status":"enabled"}]'
                ),
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "MCP_LAUNCHER_ERROR=repo_mcp_server: launcher cwd path not found: "
            "missing",
            result.stdout,
        )

    def test_required_server_fails_when_launcher_path_is_missing(self) -> None:
        """A required server fails when its repo-local launcher is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(
                Path(tmp_dir),
                (
                    '[{"name":"repo_mcp_server","command":"bash",'
                    '"args":["mcp/repo_mcp_server.sh"],"status":"enabled"}]'
                ),
            )
            command = [
                sys.executable,
                str(SCRIPT),
                "--codex-bin",
                str(codex),
                "--require",
                "repo_mcp_server",
            ]
            result = subprocess.run(
                command,
                cwd=Path(tmp_dir),
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "MCP_LAUNCHER_ERROR=repo_mcp_server: launcher argument path not found: "
            "mcp/repo_mcp_server.sh",
            result.stdout,
        )
        self.assertIn(
            "NEXT_ACTION=fix_required_mcp_launcher_before_work",
            result.stdout,
        )

    def test_empty_inventory_needs_explicit_allowance_without_requirements(
        self,
    ) -> None:
        """A bare inventory check should not silently accept no configured servers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(Path(tmp_dir), "[]")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--codex-bin", str(codex)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("MCP_INVENTORY_EMPTY=yes", result.stdout)

    def test_mcp_role_docs_separate_agentcanon_and_codex_surfaces(self) -> None:
        """Docs must keep repo MCP implementation separate from Codex runtime tools."""
        mcp_readme = MCP_README.read_text(encoding="utf-8")
        codex_readme = CODEX_README.read_text(encoding="utf-8")
        codex_workflow = CODEX_WORKFLOW.read_text(encoding="utf-8")
        codex_config_reference = CODEX_CONFIG_REFERENCE.read_text(encoding="utf-8")
        codex_config_slides = CODEX_CONFIG_SLIDES.read_text(encoding="utf-8")
        codex_task_skill = CODEX_TASK_SKILL.read_text(encoding="utf-8")

        for content in (mcp_readme, codex_readme, codex_workflow, codex_task_skill):
            self.assertIn("AgentCanon", content)
            self.assertIn("mcp/repo_mcp_server.sh", content)
            self.assertIn("mcp/repo_mcp_server.py", content)
            self.assertIn("Codex", content)

        self.assertIn("not the file-edit surface", mcp_readme)
        self.assertIn("Codex-provided apps", mcp_readme)
        self.assertIn("apps / external connectors / tool availability", codex_readme)
        self.assertIn("file edit、GitHub 操作、shell 実行、web access", codex_readme)
        self.assertIn("apps, external connectors, and available session tools", codex_workflow)
        self.assertIn("Do not add file edit, GitHub connector", codex_workflow)
        self.assertIn("AgentCanon-owned repo MCP implementation", codex_config_reference)
        self.assertIn("Codex-owned registration and runtime plane", codex_config_reference)
        self.assertIn("Do not reimplement file edit, GitHub, shell, web", codex_config_reference)
        self.assertIn("Codex-provided tool / connector surface", codex_task_skill)
        self.assertIn("apps / external connectors / session tool availability", codex_config_slides)
        self.assertIn("repo context / goal loop 専用", codex_config_slides)


if __name__ == "__main__":
    unittest.main()
