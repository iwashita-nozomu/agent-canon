# @dependency-start
# contract test
# responsibility Verifies pre-review child state and report publication stay below the selected repository.
# upstream implementation ../../tools/ci/pre_review.sh owns verifier report and child orchestration.
# @dependency-end

"""Focused parent-boundary tests for the pre-review shell entrypoint."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "pre_review.sh"
BOUNDARY = PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py"
PATH_ENV_KEYS = {
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "PYTHONPYCACHEPREFIX",
    "TEMP",
    "TMP",
    "TMPDIR",
    "XDG_CACHE_HOME",
}


def test_pre_review_uses_boundary_report_and_parent_local_child_env(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    (parent / "tools" / "ci").mkdir(parents=True)
    (parent / "tools" / "agent_tools").mkdir(parents=True)
    shutil.copy2(SCRIPT, parent / "tools" / "ci" / SCRIPT.name)
    shutil.copy2(BOUNDARY, parent / "tools" / "agent_tools" / BOUNDARY.name)
    quality = parent / "tools" / "ci" / "run_python_quality_checks.sh"
    quality.write_text(
        "#!/bin/sh\n"
        'case "$TMPDIR:$CARGO_HOME" in "$PWD"/*:"$PWD"/*) exit 0 ;; esac\n'
        "exit 91\n",
        encoding="utf-8",
    )
    quality.chmod(0o755)
    subprocess.run(
        ("git", "init", "-q", "-b", "main"),
        cwd=parent,
        check=True,
        capture_output=True,
    )
    report_dir = parent / "reports" / "verification"
    env = {key: value for key, value in os.environ.items() if key not in PATH_ENV_KEYS}
    env["AGENT_REPORT_DIR"] = str(report_dir)

    result = subprocess.run(
        ("bash", str(parent / "tools" / "ci" / SCRIPT.name)),
        cwd=parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = (report_dir / "verification.txt").read_text(encoding="utf-8")
    assert "python_quality=pass\n" in report
    assert "status=passed\n" in report
    assert not (tmp_path / "outside-report.txt").exists()


def test_pre_review_rejects_external_report_dir_without_side_effect(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    (parent / "tools" / "ci").mkdir(parents=True)
    (parent / "tools" / "agent_tools").mkdir(parents=True)
    shutil.copy2(SCRIPT, parent / "tools" / "ci" / SCRIPT.name)
    shutil.copy2(BOUNDARY, parent / "tools" / "agent_tools" / BOUNDARY.name)
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=parent, check=True)
    outside = tmp_path / "outside-report"
    env = {key: value for key, value in os.environ.items() if key not in PATH_ENV_KEYS}
    env["AGENT_REPORT_DIR"] = str(outside)
    result = subprocess.run(
        ("bash", str(parent / "tools" / "ci" / SCRIPT.name)),
        cwd=parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "symlink_escape" in result.stderr or "outside" in result.stderr
    assert not outside.exists()
    assert not (parent / "reports").exists()
