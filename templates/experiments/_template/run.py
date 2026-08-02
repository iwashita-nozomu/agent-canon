# @dependency-start
# contract reference
# responsibility Provides the template experiment entrypoint.
# upstream design ../../../documents/experiments/experiment-registry.md defines the selected command manifest.
# upstream implementation ../../../tools/experiments/execution_resource_plan.py owns GPU discovery/reservation and the frozen admission plan.
# upstream implementation ../../../tools/experiments/run_managed_experiment.py is the only authorized ExperimentRunner entrypoint and adapts main().
# upstream implementation ../../../tools/experiments/create_experiment_topic.py copies this file.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse Python projection traces.
# upstream implementation visualize.ipynb renders the reader notebook artifact.
# @dependency-end
"""Provide the managed experiment entrypoint template."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

VISUALIZE_NOTEBOOK_NAME = "visualize.ipynb"
EXECUTED_NOTEBOOK_NAME = "visualize_executed.ipynb"
DEFAULT_RUN_NAME_PREFIX = "run"


def compact_timestamp() -> str:
    """Create a compact UTC value for managed run names."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_run_dir() -> Path:
    """Select the caller-provided or timestamped output directory."""
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR")
    if raw_run_dir:
        return Path(raw_run_dir).resolve()
    return (
        Path(__file__).resolve().parent
        / "result"
        / f"{DEFAULT_RUN_NAME_PREFIX}_{compact_timestamp()}"
    )


def run_case_worker(case: object, run_dir_text: str) -> object:
    """Execute one case in worker-local context and return its serializable result."""
    # IMPLEMENT HERE: import NumPy/JAX/EQX/Optax and project modules inside the worker.
    # IMPLEMENT HERE: compute one case and return a JSON-serializable result.
    # IMPLEMENT HERE: write worker-local logs under run_dir_text/logs/ if needed.
    return None


def run_experiment(run_dir) -> None:
    """Dispatch topic cases and write their run artifacts into the output directory."""
    # IMPLEMENT HERE: import only lightweight stdlib helpers or topic-local
    # config readers needed by the parent process.
    # IMPLEMENT HERE: load cases from cases.py/config.yaml.
    # IMPLEMENT HERE: dispatch cases to run_case_worker() when parallel workers
    # are needed; each worker must do its own imports inside run_case_worker().
    # IMPLEMENT HERE: write summary.json, cases.jsonl, and topic-specific
    # artifacts under run_dir.
    run_dir.mkdir(parents=True, exist_ok=True)


def execute_visualization_notebook(run_dir):
    """Execute the run notebook and record its output artifact in the run directory."""
    notebook_path = Path(__file__).resolve().with_name(VISUALIZE_NOTEBOOK_NAME)
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["EXPERIMENT_RUN_DIR"] = str(run_dir.resolve())
    import subprocess

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


def require_managed_runner_route() -> None:
    """Require the managed runner manifest so direct topic execution fails closed."""
    if not os.environ.get("EXPERIMENT_RUN_MANIFEST"):
        raise RuntimeError(
            "managed_runner_required=tools/experiments/run_managed_experiment.py"
        )


def main() -> int:
    """Coordinate one managed experiment run and its visualization artifact."""
    require_managed_runner_route()
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
