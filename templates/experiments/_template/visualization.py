# @dependency-start
# contract reference
# responsibility Owns the optional visualization consumer and its explicit status artifact.
# upstream design ../../../documents/experiments/experiment-registry.md defines visualization provenance.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation artifact_io.py owns atomic JSON publication.
# downstream implementation visualize.ipynb consumes the run artifact directory.
# @dependency-end

"""
Optional visualization consumer を明示的な status semantics で実行します.

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


def write_visualization_not_requested_status(run_dir: Path) -> str:
    """
    不完全 scaffold の可視化を実行せず、明示的な未要求状態を保存します.

    Args:
        run_dir: status artifact を所有する run directory。

    Returns:
        `not_requested` を返します。

    Side effects:
        visualization-status.json を atomic に書き込みます。
    """
    atomic_write_json(
        run_dir / VISUALIZATION_STATUS_NAME,
        {
            "state": "not_requested",
            "requested": False,
            "consumer": VISUALIZE_NOTEBOOK_NAME,
            "readback": "incomplete template did not execute visualization",
        },
    )
    return "not_requested"


def execute_visualization_notebook(run_dir: Path, template_dir: Path) -> str:
    """
    実行時に optional visualization consumer を実行し、terminal state を記録します.

    `EXPERIMENT_RUN_VISUALIZATION=1` で managed notebook execution を要求します。
    default の `not_requested` state は minimal scaffold の runnable 性を保ちます。

    Args:
        run_dir: status と notebook output を受け取る result directory。
        template_dir: notebook を含む materialized experiment directory。

    Returns:
        `not_requested`、`success`、または notebook 要求時の `blocked`。

    Raises:
        RuntimeError: visualization を要求したが Jupyter がない場合。
        subprocess.CalledProcessError: notebook execution に失敗した場合。

    Side effects:
        Jupyter を実行することがあり、visualization-status.json を atomic に書きます。
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
