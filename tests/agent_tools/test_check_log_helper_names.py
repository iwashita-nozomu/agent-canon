# @dependency-start
# responsibility Tests log helper naming checker.
# upstream implementation ../../tools/agent_tools/check_log_helper_names.py checker under test
# @dependency-end
"""Tests for ``check_log_helper_names.py``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "agent_tools" / "check_log_helper_names.py"


def run_checker(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the checker against a temporary source tree."""
    return subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_rejects_public_write_log_helper(tmp_path: Path) -> None:
    """Log-writing helpers must use the _log prefix."""
    source = tmp_path / "sample.py"
    source.write_text(
        "from pathlib import Path\n"
        "\n"
        "def write_log_record(path: Path, text: str) -> None:\n"
        "    path.write_text(text)\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "LOG_HELPER_NAMES=fail" in result.stdout
    assert "write_log_record" in result.stdout
    assert "rename-to-_log_write_log_record" in result.stdout


def test_accepts_private_log_prefix(tmp_path: Path) -> None:
    """The canonical _log prefix passes."""
    source = tmp_path / "sample.py"
    source.write_text(
        "from pathlib import Path\n"
        "\n"
        "def _log_record(path: Path, text: str) -> None:\n"
        "    path.write_text(text)\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0
    assert "LOG_HELPER_NAMES=pass" in result.stdout


def test_ignores_non_emitting_work_log_check(tmp_path: Path) -> None:
    """Functions that inspect log artifacts without emitting logs are not helpers."""
    source = tmp_path / "sample.py"
    source.write_text(
        "def check_work_log_artifact(text: str) -> list[str]:\n"
        "    return [] if 'work_log' in text else ['missing']\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0
    assert "LOG_HELPER_NAMES=pass" in result.stdout
