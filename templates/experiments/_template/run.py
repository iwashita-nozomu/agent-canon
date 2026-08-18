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
最小の managed experiment entrypoint を提供します.

責務は managed runner の入口、case 実行の orchestration、実行状態の集約、各責務 module
への接続です。case model、artifact schema、record serialization、visualization 実行は
それぞれの replaceable module が所有し、topic 利用者はその境界から拡張します。
"""

from __future__ import annotations

import os
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
    PROVENANCE_SNAPSHOT_NAME,
    RESULT_CASES_NAME,
    RESULT_MANIFEST_NAME,
    RESULT_SUMMARY_NAME,
    VISUALIZATION_STATUS_NAME,
    CompletionProvenance,
    RunState,
    RunSummary,
)
from case_execution import execute_case, registry_failure
from case_model import CaseResult, CaseSpec
from visualization import (
    execute_visualization_notebook,
    write_visualization_not_requested_status,
)


def resolve_run_dir() -> Path:
    """
    Resolve the canonical result directory supplied by the producer.

    `EXPERIMENT_RUN_DIR` を producer が必ず供給します。resource admission と GPU
    visibility はここで決めません。

    Returns:
        この invocation が選択した absolute result directory。
    """
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR", "")
    if not raw_run_dir:
        raise RuntimeError("managed_runner_required=explicit EXPERIMENT_RUN_DIR")
    return Path(raw_run_dir).resolve()


def load_cases() -> tuple[CaseSpec, ...]:
    """
    実験の domain dependency を import せず topic-owned case registry を読み込みます.

    Returns:
        `cases.py` が宣言した immutable case specifications。

    Raises:
        ValueError: topic registry が valid case record の tuple でない場合。
    """
    from cases import CASES

    if not isinstance(CASES, tuple):
        raise ValueError("cases.py must expose CASES as a tuple")
    if not all(isinstance(case, CaseSpec) for case in CASES):
        raise ValueError("cases.py CASES must contain CaseSpec records")
    return CASES


def _case_state_counts(records: tuple[CaseResult, ...]) -> tuple[int, int, int]:
    """
    success、failed、blocked の case record 数を数えます.

    Args:
        records: current run が所有する materialized case records。

    Returns:
        success、failed、blocked の順の count。

    Side effects:
        渡された immutable record sequence だけを読みます。
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
    実行 case record から run status、failure class、close condition を導出します.

    Args:
        records: preserved failure を含む complete case execution records。

    Returns:
        導出した state、安定した failure class、required close condition。

    Side effects:
        artifact を書かず、record も変更しません。
    """
    if not completion.is_complete:
        return (
            RunState.INCOMPLETE,
            "expected_contract",
            "実行前に config.yaml と provenance.toml の completion が必要です",
        )
    if not records:
        return RunState.BLOCKED, "expected_contract", "cases.py に少なくとも一つの case を宣言してください"
    failed_records = [record for record in records if record.state == "failed"]
    if failed_records:
        return (
            RunState.FAILED,
            failed_records[0].failure_class,
            "failed case を修復して managed command を再実行してください",
        )
    blocked_records = [record for record in records if record.state == "blocked"]
    if blocked_records:
        return (
            RunState.BLOCKED,
            blocked_records[0].failure_class,
            "blocked case の owner を解決して managed command を再実行してください",
        )
    return (
        RunState.SUCCESS,
        "not_applicable",
        "summary、cases、manifest、validation oracle の readback が完了しました",
    )


def run_experiment(run_dir: Path) -> RunSummary:
    """
    一つの run を orchestration し、result set を atomic に公開します.

    空の `CASES` は `blocked` とし、failed または blocked case があれば成功 record を
    保持したまま failure evidence を書きます。空でない全成功 record と完了した
    visualization status がそろった場合だけ `success` にします。

    Args:
        run_dir: この run identity のために caller が所有する result directory。

    Returns:
        `summary.json` にも書く typed aggregate summary。

    Side effects:
        owning atomic I/O module を通して provenance、case、failure、visualization、summary、
        manifest artifact を生成します。
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
            status = RunState.FAILED
            failure_class = "infrastructure_environment"
            close_condition = "visualization runtime を用意して managed command を再実行してください"
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
        exit_status=0 if status is RunState.SUCCESS else 1,
        case_count=len(records),
        success_count=success_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
        failure_class=failure_class,
        failure_evidence=failure_evidence,
        preserved_artifacts=tuple(preserved),
        close_condition=close_condition,
        validation_oracle=(
            "pass: complete provenance、non-empty cases、terminal state invariant、"
            "全 artifact digest の readback"
            if status is RunState.SUCCESS
            else "incomplete: completion provenance が success の条件を満たしていません"
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
    直接の topic execution 前に managed runner manifest を要求します.

    Raises:
        RuntimeError: managed runner が manifest を提供しない場合。

    Side effects:
        caller environment だけを読み、experiment は開始しません。
    """
    if not os.environ.get("EXPERIMENT_RUN_MANIFEST", ""):
        raise RuntimeError(
            "managed_runner_required=tools/experiments/run_managed_experiment.py"
        )
    if not os.environ.get("EXPERIMENT_VARIANT", ""):
        raise RuntimeError("managed_runner_required=explicit EXPERIMENT_VARIANT")


def main() -> int:
    """
    選択した module を通して一つの managed experiment run を調整します.

    `main()` は引数なしの execution entrypoint です。algorithm、case、schema、serialization、
    visualization、oracle の選択は各 owning contract と replaceable module に残します。

    Returns:
        空でない成功 run では zero、failed または blocked result では one。

    Side effects:
        `run_experiment` が選択した complete run artifact set を公開します。
    """
    require_managed_runner_route()
    run_dir = resolve_run_dir()
    summary = run_experiment(run_dir)
    print(f"run_dir={run_dir}")
    print(f"status={summary.status.value}")
    print(f"summary={run_dir / RESULT_SUMMARY_NAME}")
    return summary.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
