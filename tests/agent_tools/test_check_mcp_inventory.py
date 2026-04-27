"""Tests for the Codex MCP inventory checker."""

# @dependency-start
# upstream implementation ../../tools/agent_tools/check_mcp_inventory.py checks MCP inventory
# upstream implementation ../../.codex/config.toml declares repo_mcp_server
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


class McpInventoryCheckTest(unittest.TestCase):
    """Exercise MCP inventory checks through a fake Codex binary."""

    def write_fake_codex(self, directory: Path, payload: str, exit_code: int = 0) -> Path:
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
                '[{"name":"repo_mcp_server","command":"bash","args":["mcp/repo_mcp_server.sh"],"status":"enabled"}]',
            )
            mcp_dir = Path(tmp_dir) / "mcp"
            mcp_dir.mkdir()
            (mcp_dir / "repo_mcp_server.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
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
        self.assertIn("MCP_INVENTORY=pass", result.stdout)

    def test_required_server_fails_when_missing(self) -> None:
        """The checker fails closed instead of implying a local-process fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(Path(tmp_dir), "[]")
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
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("MISSING_MCP_SERVERS=repo_mcp_server", result.stdout)
        self.assertIn("NEXT_ACTION=configure_required_mcp_servers_before_work", result.stdout)

    def test_nested_codex_transport_shape_is_supported(self) -> None:
        """Current Codex JSON nests command and enabled status under transport/root fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(
                Path(tmp_dir),
                (
                    '[{"name":"repo_mcp_server","enabled":true,'
                    '"transport":{"type":"stdio","command":"bash","args":["mcp/repo_mcp_server.sh"]}}]'
                ),
            )
            mcp_dir = Path(tmp_dir) / "mcp"
            mcp_dir.mkdir()
            (mcp_dir / "repo_mcp_server.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
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

    def test_required_server_fails_when_launcher_path_is_missing(self) -> None:
        """A configured required server still fails if its repo-local launcher is absent."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            codex = self.write_fake_codex(
                Path(tmp_dir),
                '[{"name":"repo_mcp_server","command":"bash","args":["mcp/repo_mcp_server.sh"],"status":"enabled"}]',
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
        self.assertIn("NEXT_ACTION=fix_required_mcp_launcher_before_work", result.stdout)

    def test_empty_inventory_needs_explicit_allowance_without_requirements(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
