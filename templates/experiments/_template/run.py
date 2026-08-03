# @dependency-start
# contract reference
# responsibility Provides the template experiment entrypoint and orchestration boundary.
# upstream design ../../../documents/experiments/experiment-registry.md defines the selected command manifest.
# upstream implementation ../../../tools/experiments/execution_resource_plan.py owns GPU discovery/reservation and the frozen admission plan.
# upstream implementation ../../../tools/experiments/run_managed_experiment.py is the only authorized ExperimentRunner entrypoint and adapts main().
# upstream implementation ../../../tools/experiments/create_experiment_topic.py copies this complete scaffold.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses and sparse Python projection traces.
# upstream implementation cases.py supplies the topic-owned case registry.
# upstream implementation case_execution.py owns case execution and typed records.
# upstream implementation artifact_io.py owns atomic artifact publication and readback.
# downstream implementation visualize.ipynb reads the materialized result artifacts.
# @dependency-end

"""
Provide the minimal complete managed experiment entrypoint.

責務は managed runner の入口、case 実行の orchestration、実行状態の集約、各責務 module
への接続です。case model、artifact schema、record serialization、visualization 実行は
それぞれの replaceable module が所有し、topic 利用者はその境界から拡張します。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from artifact_io import (
    load_completion_provenance,
    utc_now,
    write_artifact_manifest,
    write_case_records,
    write_failure_evidence,
    write_provenance_snapshots,
    write_summary,
)
from artifact_schema import (
    CONFIG_SNAPSHOT_NAME,
    ENVIRONMENT_SNAPSHOT_NAME,
    FAILURE_EVIDENCE_NAME,
    RESULT_CASES_NAME,
    RESULT_MANIFEST_NAME,
    RESULT_SUMMARY_NAME,
    PROVENANCE_SNAPSHOT_NAME,
    RunState,
    VISUALIZATION_STATUS_NAME,
    CompletionProvenance,
    RunSummary,
)
from case_execution import execute_case, registry_failure
from case_model import CaseResult, CaseSpec
from visualization import (
    execute_visualization_notebook,
    write_visualization_not_requested_status,
)

DEFAULT_RUN_NAME_PREFIX = "run"


def compact_timestamp() -> str:
    """
    Create a compact UTC value for managed run names.

    責務は run identity の timestamp 部分だけを生成することです。副作用はなく、UTC と
    caller/scheduler provenance の境界を変更しません。

    Returns:
        A compact UTC timestamp suitable for a topic-local result directory name.
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_run_dir() -> Path:
    """
    Select the caller-provided or timestamped output directory.

    `EXPERIMENT_RUN_DIR` を優先し、未指定時だけ topic-local result path を選びます。
    resource admission と GPU visibility はここで決めません。

    Returns:
        The absolute result directory selected for this invocation.
    """
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR", "")
    if raw_run_dir:
        return Path(raw_run_dir).resolve()
    return (
        Path(__file__).resolve().parent
        / "result"
        / f"{DEFAULT_RUN_NAME_PREFIX}_{compact_timestamp()}"
    )


def load_cases() -> tuple[CaseSpec, ...]:
    """
    Load the topic-owned case registry without importing domain dependencies.

    Returns:
        Immutable case specifications declared by `cases.py`.

    Raises:
        ValueError: If the topic registry is not a tuple of valid case records.
    """
    from cases import CASES

    if not isinstance(CASES, tuple):
        raise ValueError("cases.py must expose CASES as a tuple")
    if not all(isinstance(case, CaseSpec) for case in CASES):
        raise ValueError("cases.py CASES must contain CaseSpec records")
    return CASES


def _case_state_counts(records: tuple[CaseResult, ...]) -> tuple[int, int, int]:
    """
    Count successful, failed, and blocked case records.

    Args:
        records: Materialized case records owned by the current run.

    Returns:
        Counts in the stable order success, failed, blocked.

    Side effects:
        Reads only the supplied immutable record sequence.
    """
    return (
        sum(record.state == "success" for record in records),
        sum(record.state == "failed" for record in records),
        sum(record.state == "blocked" for record in records),
    )


def _run_acceptance(
    records: tuple[CaseResult, ...],
    completion: CompletionProvenance,
) -> tuple[RunState, str, str]:
    """
    Derive run status, failure class, and close condition from case records.

    Args:
        records: Complete case execution records, including preserved failures.

    Returns:
        The derived state, stable failure class, and required close condition.

    Side effects:
        Does not write artifacts or mutate records.
    """
    if not completion.is_complete:
        return (
            "incomplete",
            "expected_contract",
            "complete config.yaml and provenance.toml required before execution",
        )
    if not records:
        return "blocked", "expected_contract", "declare at least one case in cases.py"
    failed_records = [record for record in records if record.state == "failed"]
    if failed_records:
        return (
            "failed",
            failed_records[0].failure_class,
            "repair the failed case and rerun the managed command",
        )
    blocked_records = [record for record in records if record.state == "blocked"]
    if blocked_records:
        return (
            "blocked",
            blocked_records[0].failure_class,
            "resolve the blocked case owner and rerun the managed command",
        )
    return (
        "success",
        "not_applicable",
        "summary, cases, manifest, and validation oracle read back",
    )


def run_experiment(run_dir: Path) -> RunSummary:
    """
    Orchestrate one complete run and atomically publish its result set.

    Empty `CASES` is `blocked`; any failed or blocked case preserves all
    successful records and writes failure evidence. Only a non-empty set of
    successful records with a completed visualization status is `success`.

    Args:
        run_dir: Caller-owned result directory for this run identity.

    Returns:
        The typed aggregate summary also written to summary.json.

    Side effects:
        Creates provenance, case, failure, visualization, summary, and manifest
        artifacts through the owning atomic I/O module.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    template_dir = Path(__file__).resolve().parent
    completion = load_completion_provenance(template_dir)
    write_provenance_snapshots(run_dir, template_dir, completion)
    records_list: list[CaseResult] = []
    if completion.is_complete:
        try:
            cases = load_cases()
        except Exception as error:
            cases = ()
            records_list.append(registry_failure(error, started_at))
        for case in cases:
            records_list.append(execute_case(case, str(run_dir.resolve())))
    records = tuple(records_list)
    write_case_records(run_dir, records)
    success_count, failed_count, blocked_count = _case_state_counts(records)
    status, failure_class, close_condition = _run_acceptance(records, completion)
    failure_records = tuple(record for record in records if record.state != "success")
    failure_evidence = "not_applicable"
    if failure_records or not records:
        failure_evidence = FAILURE_EVIDENCE_NAME
        write_failure_evidence(
            run_dir,
            status=status,
            failure_class=failure_class,
            records=failure_records,
            close_condition=close_condition,
        )
    visualization_status = "not_requested"
    if completion.is_complete:
        try:
            visualization_status = execute_visualization_notebook(run_dir, template_dir)
        except Exception as error:
            visualization_status = "blocked"
            status = "failed"
            failure_class = "infrastructure_environment"
            close_condition = "provide the visualization runtime and rerun the managed command"
            failure_evidence = FAILURE_EVIDENCE_NAME
            write_failure_evidence(
                run_dir,
                status=status,
                failure_class=failure_class,
                records=failure_records,
                close_condition=close_condition,
                visualization_error=f"{type(error).__name__}: {error}",
            )
    else:
        visualization_status = write_visualization_not_requested_status(run_dir)
    finished_at = utc_now()
    preserved = [
        RESULT_SUMMARY_NAME,
        RESULT_CASES_NAME,
        RESULT_MANIFEST_NAME,
        CONFIG_SNAPSHOT_NAME,
        ENVIRONMENT_SNAPSHOT_NAME,
        PROVENANCE_SNAPSHOT_NAME,
        VISUALIZATION_STATUS_NAME,
    ]
    if failure_evidence != "not_applicable":
        preserved.append(FAILURE_EVIDENCE_NAME)
    summary = RunSummary(
        run_id=run_dir.name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        exit_status=0 if status == "success" else 1,
        case_count=len(records),
        success_count=success_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
        failure_class=failure_class,
        failure_evidence=failure_evidence,
        preserved_artifacts=tuple(preserved),
        close_condition=close_condition,
        validation_oracle=(
            "pass: complete provenance, non-empty cases, terminal state invariants, "
            "and every artifact digest read back"
            if status == "success"
            else "incomplete: completion provenance is not sufficient for success"
        ),
        visualization_status=visualization_status,
        template_complete=completion.is_complete,
        completion_provenance=completion.to_dict(),
    )
    write_summary(run_dir, summary)
    write_artifact_manifest(run_dir, summary)
    return summary


def require_managed_runner_route() -> None:
    """
    Require the managed runner manifest before direct topic execution.

    Raises:
        RuntimeError: If the managed runner did not provide its manifest.

    Side effects:
        Reads the caller environment and does not start an experiment.
    """
    if not os.environ.get("EXPERIMENT_RUN_MANIFEST", ""):
        raise RuntimeError(
            "managed_runner_required=tools/experiments/run_managed_experiment.py"
        )


def main() -> int:
    """
    Coordinate one managed experiment run through the selected modules.

    `main()` is the argument-free execution entrypoint. Algorithm, case,
    schema, serialization, visualization, and oracle choices remain in their
    owning contracts and replaceable modules.

    Returns:
        Zero for a successful non-empty run; one for failed or blocked results.

    Side effects:
        Publishes the complete run artifact set selected by `run_experiment`.
    """
    require_managed_runner_route()
    run_dir = resolve_run_dir()
    summary = run_experiment(run_dir)
    print(f"run_dir={run_dir}")
    print(f"status={summary.status}")
    print(f"summary={run_dir / RESULT_SUMMARY_NAME}")
    return summary.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
