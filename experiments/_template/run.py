# @dependency-start
# contract reference
# responsibility Provides the template experiment entrypoint.
# upstream design ../../documents/experiment-registry.md defines the command protocol.
# upstream implementation ../../tools/experiments/create_experiment_topic.py copies this file.
# upstream implementation visualize.ipynb renders the reader notebook artifact.
# downstream implementation result stores per-run outputs for copied topics.
# @dependency-end
"""Template experiment entrypoint."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

VISUALIZE_NOTEBOOK_NAME = "visualize.ipynb"
EXECUTED_NOTEBOOK_NAME = "visualize_executed.ipynb"
DEFAULT_RUN_NAME_PREFIX = "run"


def compact_timestamp() -> str:
    """Return a compact UTC timestamp for direct run names."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_run_dir() -> Path:
    """Return the caller-provided or direct-run output directory."""
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR")
    if raw_run_dir:
        return Path(raw_run_dir).resolve()
    return (
        Path(__file__).resolve().parent
        / "result"
        / f"{DEFAULT_RUN_NAME_PREFIX}_{compact_timestamp()}"
    )


def run_case_worker(case: object, run_dir_text: str) -> object:
    """Run one case inside a worker process."""
    # IMPLEMENT HERE: import NumPy/JAX/EQX/Optax and project modules inside the worker.
    # IMPLEMENT HERE: compute one case and return a JSON-serializable result.
    # IMPLEMENT HERE: write worker-local logs under run_dir_text/logs/ if needed.
    return None


def run_experiment(run_dir) -> None:
    """Run the topic experiment and write artifacts into ``run_dir``."""
    # IMPLEMENT HERE: import only lightweight stdlib helpers or topic-local
    # config readers needed by the parent process.
    # IMPLEMENT HERE: load cases from cases.py/config.yaml.
    # IMPLEMENT HERE: dispatch cases to run_case_worker() when parallel workers
    # are needed; each worker must do its own imports inside run_case_worker().
    # IMPLEMENT HERE: write summary.json, cases.jsonl, and topic-specific
    # artifacts under run_dir.
    run_dir.mkdir(parents=True, exist_ok=True)


def execute_visualization_notebook(run_dir):
    """Execute the per-run visualization notebook."""
    import os
    import subprocess
    from pathlib import Path

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
    """Run one experiment invocation without CLI arguments."""
    # IMPLEMENT HERE: keep main() as orchestration only. Put experiment logic in
    # run_experiment() and process-local work in run_case_worker().
    run_dir = resolve_run_dir()
    run_experiment(run_dir)
    executed_notebook = execute_visualization_notebook(run_dir)
    print(f"run_dir={run_dir}")
    print(f"visualization={executed_notebook}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
