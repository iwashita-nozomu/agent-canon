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
RESULT_SUMMARY_NAME = "summary.json"
RESULT_CASES_NAME = "cases.jsonl"
RESULT_MANIFEST_NAME = "artifact-manifest.json"


def compact_timestamp() -> str:
    """Create a compact UTC value for managed run names.

    責務: run identity の timestamp 部分だけを生成する。副作用はなく、UTC と
    caller/scheduler provenance の境界を変更しない。
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_run_dir() -> Path:
    """Select the caller-provided or timestamped output directory.

    責務: managed runner が渡す `EXPERIMENT_RUN_DIR` を優先し、未指定時だけ topic-local
    result path を選ぶ。resource admission や GPU visibility はここで決めない。
    """
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR")
    if raw_run_dir:
        return Path(raw_run_dir).resolve()
    return (
        Path(__file__).resolve().parent
        / "result"
        / f"{DEFAULT_RUN_NAME_PREFIX}_{compact_timestamp()}"
    )


def run_case_worker(case: object, run_dir_text: str) -> object:
    """Execute one case in worker-local context and return a serializable result.

    責務: 一つの case の domain computation と case-level failure evidence を扱う。
    入力/output schema、oracle、failure-cause classification は topic README と
    provenance TOML の algorithm contract を先に埋めてから実装する。
    """
    # IMPLEMENT HERE: import NumPy/JAX/EQX/Optax and project modules inside the worker.
    # IMPLEMENT HERE: compute one case and return a JSON-serializable result.
    # IMPLEMENT HERE: preserve expected/infrastructure/implementation/oracle/unknown
    # failure evidence under run_dir_text/logs/ when a case is not successful.
    return None


def run_experiment(run_dir: Path) -> None:
    """Dispatch cases and write summary, manifest, and result artifacts.

    責務: orchestration と artifact I/O を所有する。domain logic は worker、metric/oracle
    は topic contract、resource/env provenance は managed runner/caller が所有する。
    """
    # IMPLEMENT HERE: import only lightweight stdlib helpers or topic-local
    # config readers needed by the parent process.
    # IMPLEMENT HERE: load cases from cases.py/config.yaml.
    # IMPLEMENT HERE: dispatch cases to run_case_worker() when parallel workers
    # are needed; each worker must do its own imports inside run_case_worker().
    # IMPLEMENT HERE: write summary.json, cases.jsonl, artifact-manifest.json, and
    # topic-specific artifacts under run_dir. Include config/environment/source
    # snapshots and a typed result state: incomplete/success/failed/blocked.
    run_dir.mkdir(parents=True, exist_ok=True)


def execute_visualization_notebook(run_dir):
    """Execute the run notebook and record its output artifact.

    Notebook は result artifact を読む visualization consumer であり、formal run の
    代替 entrypoint ではない。実行後に output identity と source/result readback を記録する。
    """
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
    """Require the managed runner manifest so direct topic execution fails closed.

    `EXPERIMENT_RUN_MANIFEST` が無い場合は silent fallback をせず、原因を caller に返す。
    """
    if not os.environ.get("EXPERIMENT_RUN_MANIFEST"):
        raise RuntimeError(
            "managed_runner_required=tools/experiments/run_managed_experiment.py"
        )


def main() -> int:
    """Coordinate one managed experiment run and its visualization artifact.

    main() は引数なしの orchestration boundary とし、algorithm/test/oracle の判断を
    command-line convenience として追加しない。
    """
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
