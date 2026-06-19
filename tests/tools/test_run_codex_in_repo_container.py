# @dependency-start
# contract test
# responsibility Tests nested Codex container runner behavior.
# upstream implementation ../../tools/ci/run_codex_in_repo_container.py runs Codex inside the repo container
# upstream design ../../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# @dependency-end

"""Tests for the nested Codex container runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_codex_in_repo_container.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the nested Codex runner and capture output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_print_only_runs_shared_post_create_before_codex() -> None:
    """Codex and gh setup should come from shared post-create, not Dockerfile."""
    result = run_cli("--print-only")

    assert result.returncode == 0, result.stderr
    assert "bash /workspace/.devcontainer/post-create.sh /workspace" in result.stdout
    assert "setpriv --reuid" in result.stdout
    assert "--user" not in result.stdout
    assert "exec codex" in result.stdout
