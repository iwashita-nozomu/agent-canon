# @dependency-start
# contract test
# responsibility Tests experiment completion, terminal case invariants, and nested manifest readback.
# upstream implementation ../../templates/experiments/_template/artifact_io.py publishes artifacts.
# upstream implementation ../../templates/experiments/_template/artifact_schema.py owns schemas.
# upstream implementation ../../templates/experiments/_template/case_model.py owns case invariants.
# @dependency-end

"""experiment template の completion、state、manifest contract を検証します."""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates" / "experiments" / "_template"
sys.path.insert(0, str(TEMPLATE_ROOT))

from artifact_io import load_completion_provenance, write_artifact_manifest  # noqa: E402
from artifact_schema import ArtifactManifest, RunState, RunSummary  # noqa: E402
from case_model import CaseResult  # noqa: E402


def _timestamp() -> str:
    """検証用の RFC3339 timestamp を返します."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
            "summary.json",
            "cases.jsonl",
            "artifact-manifest.json",
            "config_snapshot.json",
            "environment.json",
            "provenance_snapshot.toml",
            "visualization-status.json",
        ),
        close_condition="not_applicable",
        validation_oracle="pass: complete provenance",
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
    with pytest.raises(ValueError, match="failed or blocked case requires failure fields"):
        _result(
            state="failed",
            result={"case_parameters": {}},
            failure_class="not_applicable",
            failure_message="",
            failure_evidence="not_applicable",
        )


def test_artifact_manifest_reads_nested_regular_files(tmp_path: Path) -> None:
    """Manifest が nested regular file の normalized path と hash を含めます."""
    (tmp_path / "summary.json").write_text("{}\n", encoding="utf-8")
    nested = tmp_path / "logs" / "nested" / "trace.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("trace\n", encoding="utf-8")
    nested_manifest_name = tmp_path / "logs" / "artifact-manifest.json"
    nested_manifest_name.write_text("nested\n", encoding="utf-8")

    write_artifact_manifest(tmp_path, _summary())

    manifest = (tmp_path / "artifact-manifest.json").read_text(encoding="utf-8")
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


def test_completion_gate_recursively_rejects_nested_reviewer_placeholder(
    tmp_path: Path,
) -> None:
    """Completion gate が nested reviewer placeholder を再帰的に拒否します."""
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            (
                "template_complete: true",
                "cases: {example: true}",
                "metric: {name: sum}",
                "runtime: {entrypoint: run.py}",
                "algorithm_contract: {entrypoint: run_case_worker}",
                "oracle: {necessary: [record]}",
                "provenance: {owner: checker}",
                "failure: {classification: expected_contract}",
                "lifecycle: {cleanup: temporary}",
                "",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "provenance.toml").write_text(
        "\n".join(
            (
                'template_complete = true',
                'completion_status = "complete"',
                "[review]",
                'reviewer = { identity = "<nested-reviewer>" }',
                "",
            )
        ),
        encoding="utf-8",
    )

    completion = load_completion_provenance(tmp_path)

    assert not completion.is_complete
    assert "provenance.review.reviewer.identity unresolved" in completion.missing_fields


def test_completion_gate_requires_alternatives_selection_and_review_fields(
    tmp_path: Path,
) -> None:
    """Completion gate が複数案、selection、review の構造を要求します."""
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            (
                "template_complete: true",
                "cases: {example: true}",
                "metric: {name: sum}",
                "runtime: {entrypoint: run.py}",
                "algorithm_contract: {entrypoint: run_case_worker}",
                "oracle: {necessary: [record]}",
                "provenance: {owner: checker}",
                "failure: {classification: expected_contract}",
                "lifecycle: {cleanup: temporary}",
                "",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "provenance.toml").write_text(
        "\n".join(
            (
                'template_complete = true',
                'completion_status = "complete"',
                "[plan]",
                'options = [{ id = "option-a", mechanism = "m", status = "rejected", rejected_rationale = "r", selection_evidence = "e" }]',
                "[plan.selection]",
                'selected_option = "option-a"',
                "[review]",
                'independent_reviewer = ""',
                "",
            )
        ),
        encoding="utf-8",
    )

    completion = load_completion_provenance(tmp_path)

    assert "provenance.plan.options requires at least 2 records" in completion.missing_fields
    assert "provenance.plan.selection.rejected_rationale" in completion.missing_fields
    assert "provenance.review.independent_reviewer" in completion.missing_fields


@pytest.mark.parametrize(
    ("options", "selected_option", "expected_field"),
    (
        (
            (("option-a", "selected"), ("option-b", "rejected")),
            "missing-option",
            "provenance.plan.selection.selected_option must reference an option id",
        ),
        (
            (("option-a", "selected"), ("option-a", "rejected")),
            "option-a",
            "provenance.plan.options.id must be unique",
        ),
        (
            (("option-a", "rejected"), ("option-b", "rejected")),
            "option-a",
            "provenance.plan.options must contain exactly one selected option",
        ),
        (
            (("option-a", "selected"), ("option-b", "selected")),
            "option-a",
            "provenance.plan.options must contain exactly one selected option",
        ),
    ),
    ids=("invalid-selected-id", "duplicate-id", "no-selected", "multiple-selected"),
)
def test_completion_gate_rejects_option_selection_invariants(
    tmp_path: Path,
    options: tuple[tuple[str, str], ...],
    selected_option: str,
    expected_field: str,
) -> None:
    """Completion gate が options と selection の相互整合性を拒否します."""
    option_records = ", ".join(
        (
            '{ id = "'
            + option_id
            + '", mechanism = "m", status = "'
            + status
            + '", rejected_rationale = "r", selection_evidence = "e" }'
        )
        for option_id, status in options
    )
    (tmp_path / "config.yaml").write_text(
        "\n".join(
            (
                "template_complete: true",
                "cases: {example: true}",
                "metric: {name: sum}",
                "runtime: {entrypoint: run.py}",
                "algorithm_contract: {entrypoint: run_case_worker}",
                "oracle: {necessary: [record]}",
                "provenance: {owner: checker}",
                "failure: {classification: expected_contract}",
                "lifecycle: {cleanup: temporary}",
                "",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "provenance.toml").write_text(
        "\n".join(
            (
                'template_complete = true',
                'completion_status = "complete"',
                "[plan]",
                f"options = [{option_records}]",
                "[plan.selection]",
                f'selected_option = "{selected_option}"',
                'rejected_rationale = "r"',
                'selection_evidence = "e"',
                "[review]",
                'independent_reviewer = "reviewer"',
                'source_snapshot = "source"',
                'selection_evidence = "e"',
                'review_decision = "pass"',
                "",
            )
        ),
        encoding="utf-8",
    )

    completion = load_completion_provenance(tmp_path)

    assert not completion.is_complete
    assert expected_field in completion.missing_fields


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
        RunSummary(**{**_summary().__dict__, "status": RunState.FAILED, "exit_status": 0})


def test_manifest_requires_run_state_enum() -> None:
    """Manifest schema が文字列 state を enum の代用として受け付けません."""
    with pytest.raises(ValueError, match="RunState enum"):
        ArtifactManifest(run_id="run", state="success", artifacts=())
