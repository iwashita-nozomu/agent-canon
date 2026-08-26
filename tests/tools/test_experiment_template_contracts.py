# @dependency-start
# contract test
# responsibility Tests experiment completion, terminal case invariants, and nested manifest readback.
# upstream implementation ../../templates/experiments/_template/run.py owns schemas and artifact publication.
# upstream implementation ../../templates/experiments/_template/cases.py owns case invariants.
# upstream implementation ../../tools/experiments/create_experiment_topic.py owns topic materialization.
# @dependency-end

"""experiment template の completion、state、manifest contract を検証します."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[2] / "templates" / "experiments" / "_template"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREATE_TOPIC = PROJECT_ROOT / "tools" / "experiments" / "create_experiment_topic.py"
sys.path.insert(0, str(TEMPLATE_ROOT))

from run import (  # noqa: E402
    ArtifactManifest,
    CaseResult,
    RunState,
    RunSummary,
    load_completion_provenance,
    write_artifact_manifest,
)


def _timestamp() -> str:
    """検証用の RFC3339 timestamp を返します."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def test_created_topic_readme_keeps_research_acceptance_topic_owned(
    tmp_path: Path,
) -> None:
    """The creator must not regenerate a universal research acceptance gate."""
    parent_root = tmp_path / "parent"
    registry_path = parent_root / "experiments" / "registry.toml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        "\n".join(
            (
                "schema_version = 1",
                "topics = []",
                "",
                "[defaults]",
                'topic_template_dir = "templates/experiments/_template"',
                "",
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CREATE_TOPIC),
            "--repo-root",
            str(parent_root),
            "--status",
            "template",
            "acceptance-boundary",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    readme = (
        parent_root / "experiments" / "acceptance-boundary" / "README.md"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "受入条件",
        "## 完了条件",
        "completion gate",
        "non-empty observation",
    ):
        assert forbidden not in readme
    for required in (
        "## 計画・実行・結果解釈の境界",
        "topic / research owner",
        "run identity",
        "result/<run-id>/",
        "terminal / failure state",
        "failure evidence",
        "provenance / readback",
    ):
        assert required in readme


def test_provenance_template_keeps_plan_inputs_separate_from_verdicts() -> None:
    """Canonical provenance template has no plan-time research verdict fields."""
    provenance = (TEMPLATE_ROOT / "provenance.toml").read_text(encoding="utf-8")

    for required in (
        "observables",
        "evidence_targets",
        "variables",
        "comparison",
        "calculation",
        "expected_mechanism",
        "protocol",
        "impossibility_conditions",
        "input_conditions",
        "environment_conditions",
        "execution_evidence",
    ):
        assert required in provenance
    for forbidden in (
        "acceptance_oracle",
        "sufficient_observations",
        "[[plan.options]]",
        "[plan.selection]",
        "review_decision",
        "validation_oracle",
        "accepted_failure",
    ):
        assert forbidden not in provenance


def _result(**overrides: object) -> CaseResult:
    """最小の valid CaseResult を作ります."""
    values: dict[str, object] = {
        "case_id": "case",
        "state": "success",
        "result": {"observation": 1.0},
        "failure_class": "not_applicable",
        "failure_message": "",
        "failure_evidence": "not_applicable",
        "started_at": _timestamp(),
        "finished_at": _timestamp(),
        "duration_seconds": 0.1,
    }
    values.update(overrides)
    return CaseResult(**values)  # type: ignore[arg-type]


def _summary() -> RunSummary:
    """検証用 nested manifest の complete success summary を作ります."""
    timestamp = _timestamp()
    return RunSummary(
        run_id="run",
        status=RunState.SUCCESS,
        started_at=timestamp,
        finished_at=timestamp,
        exit_status=0,
        case_count=1,
        success_count=1,
        failed_count=0,
        blocked_count=0,
        failure_class="not_applicable",
        failure_evidence="not_applicable",
        preserved_artifacts=(
            "summary/summary.json",
            "summary/cases.jsonl",
            "summary/artifact-manifest.json",
            "summary/config_snapshot.json",
            "summary/environment.json",
            "summary/provenance_snapshot.toml",
            "summary/visualization-status.json",
        ),
        close_condition="not_applicable",
        execution_evidence="complete provenance and artifact readback",
        visualization_status="not_requested",
        template_complete=True,
        completion_provenance={
            "template_complete": True,
            "completion_status": "complete",
            "provenance_path": "provenance.toml",
            "missing_fields": [],
            "state": "complete",
        },
    )


def test_case_result_rejects_terminal_cross_field_mismatch() -> None:
    """Success と failure field の混在を publication 前に拒否します."""
    with pytest.raises(ValueError, match="successful case cannot carry failure fields"):
        _result(failure_class="implementation_algorithm", failure_message="unexpected")
    with pytest.raises(
        ValueError, match="failed or blocked case requires failure fields"
    ):
        _result(
            state="failed",
            result={"case_parameters": {}},
            failure_class="not_applicable",
            failure_message="",
            failure_evidence="not_applicable",
        )


def test_artifact_manifest_reads_nested_regular_files(tmp_path: Path) -> None:
    """Manifest が nested regular file の normalized path と hash を含めます."""
    (tmp_path / "summary").mkdir()
    (tmp_path / "summary" / "summary.json").write_text("{}\n", encoding="utf-8")
    nested = tmp_path / "logs" / "nested" / "trace.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("trace\n", encoding="utf-8")
    nested_manifest_name = tmp_path / "logs" / "artifact-manifest.json"
    nested_manifest_name.write_text("nested\n", encoding="utf-8")

    write_artifact_manifest(tmp_path, _summary())

    manifest = (tmp_path / "summary" / "artifact-manifest.json").read_text(
        encoding="utf-8"
    )
    expected_digest = hashlib.sha256(b"trace\n").hexdigest()
    assert "logs/nested/trace.txt" in manifest
    assert "logs/artifact-manifest.json" in manifest
    assert expected_digest in manifest


def test_completion_gate_rejects_malformed_yaml(tmp_path: Path) -> None:
    """Completion gate が malformed YAML を未完了として拒否します."""
    (tmp_path / "config.yaml").write_text("template_complete: [", encoding="utf-8")
    (tmp_path / "provenance.toml").write_text(
        'template_complete = false\ncompletion_status = "incomplete"\n',
        encoding="utf-8",
    )

    completion = load_completion_provenance(tmp_path)

    assert not completion.is_complete
    assert "config.yaml.parseable" in completion.missing_fields


def _write_minimal_topic(topic_dir: Path) -> str:
    """最小の計画と operational config を topic directory へ書きます."""
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "config.yaml").write_text(
        "\n".join(
            (
                "template_complete: true",
                "cases: {example: true}",
                "metric: {name: sum}",
                "runtime: {entrypoint: run.py}",
                "algorithm_contract: {entrypoint: run_case_worker}",
                "observables: {record: {type: scalar}}",
                "provenance: {owner: checker}",
                "failure: {classification: expected_contract}",
                "lifecycle: {cleanup: temporary}",
                "",
            )
        ),
        encoding="utf-8",
    )
    provenance_text = "\n".join(
        (
            "template_complete = true",
            'completion_status = "complete"',
            "[experiment]",
            'topic = "topic"',
            'owner = "owner"',
            'question = "question"',
            'hypothesis = "hypothesis"',
            'plan_digest = "digest"',
            "[plan]",
            'baseline = "baseline"',
            'candidate = "candidate"',
            'variables = ["variable"]',
            'cases = ["case"]',
            'observables = ["observation"]',
            'evidence_targets = ["summary/cases.jsonl", "summary/summary.json"]',
            'metrics = ["metric"]',
            'comparison = "compare and calculate"',
            'calculation = "calculate"',
            'expected_mechanism = "mechanism"',
            'protocol = "protocol"',
            'stopping_rule = "stop"',
            'impossibility_conditions = ["impossible"]',
            'input_conditions = ["input"]',
            'environment_conditions = ["environment"]',
            "[plan.algorithm_contract]",
            'public_entrypoint = "entrypoint"',
            'input_schema = "schema"',
            'state_transition = "transition"',
            'invariants = ["invariant"]',
            'stopping_rule = "stop"',
            'failure_semantics = "failure"',
            "[source]",
            'repository = "repo"',
            'branch = "main"',
            'commit = "commit"',
            'dirty_state = "clean"',
            "[resource]",
            'admission_owner = "caller"',
            'request = "cpu"',
            'selection_reason = "capability"',
            'gpu_visibility = "caller"',
            'parallelism_policy = "caller"',
            'environment_limit = "none"',
            'allocation_evidence = "record"',
            "[reproducibility]",
            'readback_command = "readback"',
            'required_artifacts = ["summary.json"]',
            'required_case_artifact = "cases.jsonl"',
            'environment_snapshot = "environment.json"',
            'retention_owner = "owner"',
            'cleanup_policy = "temporary"',
            'cleanup_command = "cleanup"',
            'reconstructibility_readback = "readback"',
            "",
        )
    )
    (topic_dir / "provenance.toml").write_text(provenance_text, encoding="utf-8")
    return provenance_text


def _run_topic(
    topic_dir: Path,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    """Run one copied topic and read its operational summary."""
    run_dir = topic_dir / "result" / "run"
    environment = {
        **os.environ,
        "EXPERIMENT_RUN_DIR": str(run_dir),
        "EXPERIMENT_RUN_MANIFEST": str(run_dir / "run-manifest.json"),
        "EXPERIMENT_VARIANT": "default",
    }
    result = subprocess.run(
        [sys.executable, str(topic_dir / "run.py")],
        cwd=topic_dir,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    summary = json.loads(
        (run_dir / "summary" / "summary.json").read_text(encoding="utf-8")
    )
    return result, summary


def test_completion_gate_accepts_minimal_plan_without_verdict_or_review(
    tmp_path: Path,
) -> None:
    """最小の計画は研究上の合否・選択・レビューなしで実行可能です."""
    _write_minimal_topic(tmp_path)

    completion = load_completion_provenance(tmp_path)

    assert completion.is_complete
    assert completion.missing_fields == ()

    provenance_text = (tmp_path / "provenance.toml").read_text(encoding="utf-8")
    for forbidden in (
        "acceptance_oracle",
        "sufficient_observations",
        "plan.options",
        "plan.selection",
        "review_decision",
        "validation_oracle",
        "accepted_failure",
    ):
        assert forbidden not in provenance_text

    (tmp_path / "provenance.toml").write_text(
        provenance_text.replace('protocol = "protocol"', 'protocol = "<protocol>"'),
        encoding="utf-8",
    )
    incomplete = load_completion_provenance(tmp_path)
    assert not incomplete.is_complete
    assert "plan.protocol" in incomplete.missing_fields


def test_minimal_plan_runs_without_research_verdict_or_review(tmp_path: Path) -> None:
    """Generated topic run は計画時の研究判定なしで完走します."""
    topic_dir = tmp_path / "topic"
    shutil.copytree(TEMPLATE_ROOT, topic_dir)
    _write_minimal_topic(topic_dir)
    result, summary = _run_topic(topic_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert summary["state"] == "success"
    assert "execution_evidence" in summary
    assert "validation_oracle" not in summary


def test_failed_case_preserves_failure_evidence_and_artifact_readback(
    tmp_path: Path,
) -> None:
    """Failed case は非 zero exit、failure evidence、manifest readback を残します."""
    topic_dir = tmp_path / "failed-topic"
    shutil.copytree(TEMPLATE_ROOT, topic_dir)
    _write_minimal_topic(topic_dir)
    cases_path = topic_dir / "cases.py"
    cases_path.write_text(
        cases_path.read_text(encoding="utf-8").replace(
            '"values": [1.0, 2.0, 3.0]', '"values": []'
        ),
        encoding="utf-8",
    )

    result, summary = _run_topic(topic_dir)
    run_dir = topic_dir / "result" / "run"
    failure_path = run_dir / "summary" / "failure-evidence.json"
    manifest_path = run_dir / "summary" / "artifact-manifest.json"

    assert result.returncode == 1
    assert summary["state"] == "failed"
    assert summary["exit_status"] == 1
    assert summary["failure_evidence"] == "summary/failure-evidence.json"
    assert failure_path.is_file()
    assert json.loads(failure_path.read_text(encoding="utf-8"))["state"] == "failed"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert any(
        entry["path"] == "summary/failure-evidence.json"
        for entry in manifest["artifacts"]
    )
    assert "summary/artifact-manifest.json" in summary["preserved_artifacts"]


def test_blocked_and_incomplete_states_remain_distinct_without_verdicts(
    tmp_path: Path,
) -> None:
    """Blocked と incomplete は別の operational state として保持されます."""
    blocked_topic = tmp_path / "blocked-topic"
    shutil.copytree(TEMPLATE_ROOT, blocked_topic)
    _write_minimal_topic(blocked_topic)
    cases_path = blocked_topic / "cases.py"
    cases_text = cases_path.read_text(encoding="utf-8")
    cases_path.write_text(
        cases_text[: cases_text.index("CASES: tuple[CaseSpec, ...] = (")]
        + "CASES: tuple[CaseSpec, ...] = ()\n",
        encoding="utf-8",
    )
    blocked_result, blocked_summary = _run_topic(blocked_topic)

    incomplete_topic = tmp_path / "incomplete-topic"
    shutil.copytree(TEMPLATE_ROOT, incomplete_topic)
    incomplete_result, incomplete_summary = _run_topic(incomplete_topic)

    assert blocked_result.returncode == 1
    assert blocked_summary["state"] == "blocked"
    assert blocked_summary["exit_status"] == 1
    assert blocked_summary["failure_evidence"] == "summary/failure-evidence.json"
    assert incomplete_result.returncode == 1
    assert incomplete_summary["state"] == "incomplete"
    assert incomplete_summary["exit_status"] == 1
    assert incomplete_summary["failure_evidence"] == "summary/failure-evidence.json"
    assert blocked_summary["state"] != incomplete_summary["state"]
    for summary in (blocked_summary, incomplete_summary):
        assert "validation_oracle" not in summary
        assert "accepted_failure" not in summary


def test_summary_exposes_operational_evidence_without_research_verdict() -> None:
    """Run summary は operational evidence だけを research verdict なしで公開します."""
    payload = _summary().to_dict()

    assert payload["execution_evidence"] == "complete provenance and artifact readback"
    for forbidden in (
        "validation_oracle",
        "accepted_failure",
        "accepted_failure_reason",
    ):
        assert forbidden not in payload


def test_summary_requires_run_state_enum_and_completion_readback() -> None:
    """Summary が enum state と completion readback の不一致を拒否します."""
    with pytest.raises(ValueError, match="RunState enum"):
        RunSummary(**{**_summary().__dict__, "status": "success"})
    with pytest.raises(ValueError, match="completion readback"):
        RunSummary(
            **{
                **_summary().__dict__,
                "completion_provenance": {
                    "template_complete": False,
                    "completion_status": "incomplete",
                    "provenance_path": "provenance.toml",
                    "missing_fields": ["config.template_complete=true"],
                    "state": "incomplete",
                },
            }
        )
    with pytest.raises(ValueError, match="non-zero exit status"):
        RunSummary(
            **{**_summary().__dict__, "status": RunState.FAILED, "exit_status": 0}
        )


def test_manifest_requires_run_state_enum() -> None:
    """Manifest schema が文字列 state を enum の代用として受け付けません."""
    with pytest.raises(ValueError, match="RunState enum"):
        ArtifactManifest(run_id="run", state="success", artifacts=())
