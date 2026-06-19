# @dependency-start
# contract test
# responsibility Tests remote HTML artifact access command rendering.
# upstream design ../../documents/tools/html_artifact_access.md user-facing helper contract
# upstream design ../../documents/result-log-retention-and-visualization.md visual artifact policy
# upstream implementation ../../tools/experiments/html_artifact_access.py helper under test
# @dependency-end

"""Tests for remote HTML artifact browser access commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "experiments" / "html_artifact_access.py"


def command_env(**updates: str) -> dict[str, str]:
    """Return a subprocess environment with deterministic SSH-related fields."""
    env = os.environ.copy()
    for name in ("AGENT_CANON_SSH_HOST", "SSH_CONNECTION", "USER"):
        env.pop(name, None)
    env.update(updates)
    return env


def test_current_shell_plan_prints_server_tunnel_and_local_url(tmp_path: Path) -> None:
    """Current-shell mode should serve the report directory through an SSH tunnel."""
    report = tmp_path / "report.html"
    report.write_text("<html><body>ok</body></html>\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(report),
            "--port",
            "9000",
        ],
        check=False,
        capture_output=True,
        env=command_env(AGENT_CANON_SSH_HOST="user@hpc"),
        text=True,
    )

    assert result.returncode == 0, result.stderr
    expected_server = (
        f"python3 -m http.server 9000 --bind 127.0.0.1 --directory {tmp_path}"
    )
    assert "HTML_ARTIFACT_MODE=python-http-server" in result.stdout
    assert "HTML_ARTIFACT_SSH_HOST=user@hpc" in result.stdout
    assert "HTML_ARTIFACT_TUNNEL_TARGET=127.0.0.1" in result.stdout
    assert f"HTML_ARTIFACT_SERVER_COMMAND={expected_server}" in result.stdout
    assert "HTML_ARTIFACT_TUNNEL_COMMAND=ssh -N -L 9000:127.0.0.1:9000 user@hpc" in result.stdout
    assert "HTML_ARTIFACT_LOCAL_URL=http://127.0.0.1:9000/report.html" in result.stdout


def test_direct_container_plan_uses_python_http_server_and_tunnel_target() -> None:
    """Container mode should serve directly through Python http.server."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "/workspace/report.html",
            "--bind",
            "0.0.0.0",
            "--tunnel-target",
            "172.17.0.2",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        env=command_env(
            SSH_CONNECTION="198.51.100.10 60000 203.0.113.5 22",
            USER="hpcuser",
        ),
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["mode"] == "python-http-server"
    assert plan["report_path"] == "/workspace/report.html"
    assert plan["server_directory"] == "/workspace"
    assert plan["ssh_host"] == "hpcuser@203.0.113.5"
    assert plan["tunnel_target"] == "172.17.0.2"
    assert plan["server_command"] == (
        "python3 -m http.server 8765 --bind 0.0.0.0 --directory /workspace"
    )
    assert plan["local_url"] == "http://127.0.0.1:8765/report.html"
    assert plan["tunnel_command"] == "ssh -N -L 8765:172.17.0.2:8765 hpcuser@203.0.113.5"
