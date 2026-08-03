# @dependency-start
# contract test
# responsibility Tests experiment completion, terminal case invariants, and nested manifest readback.
# upstream implementation ../../templates/experiments/_template/artifact_io.py publishes artifacts.
# upstream implementation ../../templates/experiments/_template/artifact_schema.py owns schemas.
# upstream implementation ../../templates/experiments/_template/case_model.py owns case invariants.
# @dependency-end

"""experiment template の completion、state、manifest contract を検証します。"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates" / "experiments" / "_template"
sys.path.insert(0, str(TEMPLATE_ROOT))

from artifact_io import write_artifact_manifest  # noqa: E402
from artifact_schema import RunSummary  # noqa: E402
from case_model import CaseResult  # noqa: E402


def _timestamp() -> str:
    """検証用の RFC3339 timestamp を返します。"""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _result(**overrides: object) -> CaseResult:
    """最小の valid CaseResult を作ります。"""
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
    """nested manifest test 用の complete success summary を作ります。"""
    timestamp = _timestamp()
    return RunSummary(
        run_id="run",
        status="success",
        started_at=timestamp,
        finished_at=timestamp,
        exit_status=0,
        case_count=1,
        success_count=1,
        failed_count=0,
        blocked_count=0,
        failure_class="not_applicable",
        failure_evidence="not_applicable",
        preserved_artifacts=("summary.json",),
        close_condition="not_applicable",
        validation_oracle="pass: complete provenance",
        visualization_status="not_requested",
        template_complete=True,
        completion_provenance={"state": "complete"},
    )


def test_case_result_rejects_terminal_cross_field_mismatch() -> None:
    """success と failure field の混在を publication 前に拒否します。"""
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
    """manifest が nested regular file の normalized path と hash を含めます。"""
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
