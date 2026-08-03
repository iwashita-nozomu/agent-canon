# @dependency-start
# contract reference
# responsibility Owns the optional visualization consumer and its explicit status artifact.
# upstream design ../../../documents/experiments/experiment-registry.md defines visualization provenance.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation artifact_io.py owns atomic JSON publication.
# downstream implementation visualize.ipynb consumes the run artifact directory.
# @dependency-end

"""
Execute the optional visualization consumer with explicit status semantics.

責務は notebook の optional execution と `visualization-status.json` の publication です。
minimal run は `not_requested`、要求済みで runtime 不足なら `blocked` になります。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from artifact_io import atomic_write_json
from artifact_schema import (
    EXECUTED_NOTEBOOK_NAME,
    VISUALIZATION_STATUS_NAME,
    VISUALIZE_NOTEBOOK_NAME,
)


def execute_visualization_notebook(run_dir: Path, template_dir: Path) -> str:
    """
    Execute the optional visualization consumer and record its terminal state.

    Set `EXPERIMENT_RUN_VISUALIZATION=1` to require managed notebook execution.
    The default `not_requested` state keeps the complete minimal scaffold runnable.

    Args:
        run_dir: Result directory receiving status and notebook output.
        template_dir: Materialized experiment directory containing the notebook.

    Returns:
        `not_requested`, `success`, or `blocked` when the notebook was requested.

    Raises:
        RuntimeError: If visualization was requested but Jupyter is unavailable.
        subprocess.CalledProcessError: If notebook execution fails.

    Side effects:
        May execute Jupyter and atomically writes visualization-status.json.
    """
    status_path = run_dir / VISUALIZATION_STATUS_NAME
    requested = os.environ.get("EXPERIMENT_RUN_VISUALIZATION", "0") == "1"
    if not requested:
        atomic_write_json(
            status_path,
            {
                "state": "not_requested",
                "requested": False,
                "consumer": VISUALIZE_NOTEBOOK_NAME,
                "readback": "visualization was not part of the minimal run",
            },
        )
        return "not_requested"
    jupyter = shutil.which("jupyter")
    if not jupyter:
        atomic_write_json(
            status_path,
            {
                "state": "blocked",
                "requested": True,
                "consumer": VISUALIZE_NOTEBOOK_NAME,
                "failure_class": "infrastructure_environment",
                "failure_message": "jupyter executable is unavailable",
            },
        )
        raise RuntimeError("visualization_requested_but_jupyter_unavailable")
    notebook_path = template_dir / VISUALIZE_NOTEBOOK_NAME
    env = os.environ.copy()
    env["EXPERIMENT_RUN_DIR"] = str(run_dir.resolve())
    subprocess.run(
        [
            jupyter,
            "nbconvert",
            "--execute",
            "--to",
            "notebook",
            "--output",
            EXECUTED_NOTEBOOK_NAME,
            "--output-dir",
            str(run_dir),
            str(notebook_path),
        ],
        check=True,
        env=env,
    )
    atomic_write_json(
        status_path,
        {
            "state": "success",
            "requested": True,
            "consumer": VISUALIZE_NOTEBOOK_NAME,
            "output": EXECUTED_NOTEBOOK_NAME,
        },
    )
    return "success"
