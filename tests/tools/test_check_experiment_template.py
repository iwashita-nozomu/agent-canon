# @dependency-start
# contract test
# responsibility Tests the centralized experiment template smoke checker.
# upstream design ../../tools/ci/check_experiment_template.py temporary parent-shaped validation route
# downstream implementation ../../templates/experiments/_template/run.py experiment scaffold source
# @dependency-end

"""Tests for the temporary parent-shaped experiment template validation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "ci" / "check_experiment_template.py"


def test_centralized_experiment_template_smoke_is_copy_only() -> None:
    """The smoke checker creates and validates only an isolated generated topic."""
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "EXPERIMENT_TEMPLATE_SMOKE=pass" in result.stdout
    assert "EXPERIMENT_TEMPLATE_TOPIC=experiments/template-smoke" in result.stdout
    assert "EXPERIMENT_TEMPLATE_EXECUTION=not_run" in result.stdout
    assert not (PROJECT_ROOT / "experiments" / "template-smoke").exists()
