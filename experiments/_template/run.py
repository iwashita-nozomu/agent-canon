# @dependency-start
# contract reference
# responsibility Provides the template managed experiment entrypoint.
# upstream design ../../documents/experiment-registry.md defines managed experiment command protocol.
# upstream implementation ../../tools/experiments/create_experiment_topic.py copies this entrypoint into project topics.
# upstream implementation ../../tools/experiments/run_managed_experiment.py runs project-owned registry commands for copied topics.
# upstream implementation visualize.ipynb is executed into each run directory as the reader notebook artifact.
# downstream implementation result stores per-run outputs after a copied topic implements this entrypoint.
# @dependency-end
"""Template experiment entrypoint."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")

DEFAULT_RUN_NAME_PREFIX = "run"
VISUALIZE_NOTEBOOK_NAME = "visualize.ipynb"
EXECUTED_NOTEBOOK_NAME = "visualize_executed.ipynb"


def compact_timestamp() -> str:
    """Return a compact UTC timestamp for local run directories."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def default_run_dir() -> Path:
    """Return the local run directory used when run.py is executed directly."""
    return (
        Path(__file__).resolve().parent
        / "result"
        / f"{DEFAULT_RUN_NAME_PREFIX}_{compact_timestamp()}"
    )


def execute_visualization_notebook(run_dir: Path) -> Path:
    """Execute the per-run visualization notebook."""
    notebook_path = Path(__file__).resolve().with_name(VISUALIZE_NOTEBOOK_NAME)
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["EXPERIMENT_RUN_DIR"] = str(run_dir.resolve())
    subprocess.run(
        [
            "jupyter",
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
    return run_dir / EXECUTED_NOTEBOOK_NAME


def main() -> int:
    """Create the executed visualization notebook artifact."""
    run_dir = default_run_dir()
    execute_visualization_notebook(run_dir)
    print(f"run_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
