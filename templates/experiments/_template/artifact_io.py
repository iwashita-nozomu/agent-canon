# @dependency-start
# contract reference
# responsibility Owns atomic publication, provenance snapshots, serialization, and digest readback.
# upstream design ../../documents/experiment/experiment-provenance.template.toml defines reproducibility fields.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation artifact_schema.py defines published artifact schemas.
# @dependency-end

"""
experiment artifact を一つの atomic/readback boundary から公開します。

責務は JSON/JSONL serialization、config/environment provenance、atomic replacement、manifest
digest 作成です。case execution と run acceptance の判断は別 module が所有します。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from artifact_schema import (
    CONFIG_SNAPSHOT_NAME,
    ENVIRONMENT_SNAPSHOT_NAME,
    FAILURE_EVIDENCE_NAME,
    RESULT_CASES_NAME,
    RESULT_MANIFEST_NAME,
    RESULT_SUMMARY_NAME,
    ArtifactEntry,
    ArtifactManifest,
    CompletionProvenance,
    PROVENANCE_SNAPSHOT_NAME,
    RunSummary,
)
from case_model import CaseResult

REQUIRED_COMPLETION_FIELDS = (
    "experiment.topic",
    "experiment.owner",
    "experiment.question",
    "experiment.hypothesis",
    "experiment.plan_digest",
    "plan.baseline",
    "plan.candidate",
    "plan.cases",
    "plan.metrics",
    "plan.stopping_rule",
    "plan.acceptance_oracle",
    "plan.algorithm_contract.public_entrypoint",
    "plan.algorithm_contract.input_schema",
    "plan.algorithm_contract.state_transition",
    "plan.algorithm_contract.invariants",
    "plan.algorithm_contract.stopping_rule",
    "plan.algorithm_contract.failure_semantics",
    "plan.oracle_boundary.necessary_observations",
    "plan.oracle_boundary.sufficient_observations",
    "plan.oracle_boundary.test_activation",
    "source.repository",
    "source.branch",
    "source.commit",
    "source.dirty_state",
    "resource.admission_owner",
    "resource.request",
    "resource.selection_reason",
    "resource.gpu_visibility",
    "resource.parallelism_policy",
    "resource.environment_limit",
    "resource.allocation_evidence",
    "reproducibility.readback_command",
    "reproducibility.required_artifacts",
    "reproducibility.required_case_artifact",
    "reproducibility.environment_snapshot",
    "reproducibility.retention_owner",
    "reproducibility.cleanup_policy",
    "reproducibility.cleanup_command",
    "reproducibility.reconstructibility_readback",
)
PLACEHOLDER_RE = re.compile(r"<[^>]+>")
TEMPLATE_COMPLETE_RE = re.compile(r"(?m)^template_complete\s*:\s*(true|false)\s*(?:#.*)?$")


def _completion_value(data: object, path: str) -> object:
    """指定した TOML dotted path の値を取得します。"""
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_completed_value(value: object) -> bool:
    """空値または placeholder を completion failure として判定します。"""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER_RE.search(value)
    if isinstance(value, (list, tuple)):
        return bool(value) and all(_is_completed_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return True


def load_completion_provenance(template_dir: Path) -> CompletionProvenance:
    """
    config と provenance の completion contract を読み戻します。

    Args:
        template_dir: config.yaml と provenance.toml を含む materialized topic directory。

    Returns:
        完成状態と不足 field を持つ immutable provenance record。

    Side effects:
        config.yaml と provenance.toml を読みますが、書き込みは行いません。
    """
    config_path = template_dir / "config.yaml"
    provenance_path = template_dir / "provenance.toml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    config_match = TEMPLATE_COMPLETE_RE.search(config_text)
    missing = []
    config_complete = bool(config_match and config_match.group(1) == "true")
    if not config_match:
        missing.append("config.template_complete")
    elif not config_complete:
        missing.append("config.template_complete=true")
    if not provenance_path.is_file():
        missing.append("provenance.toml")
        return CompletionProvenance(
            template_complete=False,
            completion_status="incomplete",
            provenance_path="provenance.toml",
            missing_fields=tuple(missing),
        )
    try:
        provenance = tomllib.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        missing.append("provenance.toml.parseable")
        return CompletionProvenance(
            template_complete=False,
            completion_status="incomplete",
            provenance_path="provenance.toml",
            missing_fields=tuple(missing),
        )
    template_complete = provenance.get("template_complete") is True
    completion_status = str(provenance.get("completion_status", "incomplete"))
    if not template_complete:
        missing.append("provenance.template_complete=true")
    if completion_status != "complete":
        missing.append("provenance.completion_status=complete")
    for field in REQUIRED_COMPLETION_FIELDS:
        if not _is_completed_value(_completion_value(provenance, field)):
            missing.append(field)
    return CompletionProvenance(
        template_complete=config_complete and template_complete,
        completion_status=completion_status,
        provenance_path="provenance.toml",
        missing_fields=tuple(dict.fromkeys(missing)),
    )


def utc_now() -> str:
    """
    artifact provenance 用の RFC3339 UTC timestamp を返します。

    Returns:
        末尾に `Z` を持つ timezone-aware timestamp string。

    Side effects:
        system clock だけを読みます。
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def atomic_write_text(path: Path, content: str) -> None:
    """
    temporary sibling を flush した後に artifact 一件を atomic replace します。

    Args:
        path: この run が所有する destination artifact。
        content: 公開する完全な UTF-8 payload。

    Raises:
        OSError: destination directory または atomic replacement に失敗した場合。

    Side effects:
        temporary file を作成・flush し、`path` を atomic に置換します。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """
    JSON object 一件を serialize し、atomic_write_text 経由で公開します。

    Args:
        path: destination JSON artifact。
        payload: producer が所有する JSON-compatible object。

    Raises:
        TypeError: payload に JSON-serializable でない値がある場合。

    Side effects:
        destination file を atomic に作成または置換します。
    """
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def sha256_file(path: Path) -> str:
    """
    artifact-manifest.json が使う content digest を計算します。

    Args:
        path: bytes を読む既存 file。

    Returns:
        lowercase SHA-256 digest。

    Raises:
        OSError: file を読み出せない場合。

    Side effects:
        file 全体を読み、変更しません。
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_provenance_snapshots(
    run_dir: Path,
    template_dir: Path,
    completion: CompletionProvenance,
) -> tuple[str, str, str]:
    """
    case execution 前に config、completion、runtime identity を snapshot します。

    Args:
        run_dir: snapshot を受け取る result directory。
        template_dir: config.yaml と provenance.toml を含む materialized experiment directory。

    Returns:
        config、provenance、environment 順の安定した snapshot filename。

    Raises:
        OSError: 必須 snapshot を書けない場合。

    Side effects:
        config_snapshot.json、provenance_snapshot.toml、environment.json を atomic に書きます。
    """
    config_path = template_dir / "config.yaml"
    provenance_path = template_dir / "provenance.toml"
    config_content = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    atomic_write_json(
        run_dir / CONFIG_SNAPSHOT_NAME,
        {
            "path": "config.yaml",
            "state": "present" if config_content else "missing",
            "sha256": hashlib.sha256(config_content.encode("utf-8")).hexdigest(),
            "content": config_content,
            "completion": completion.to_dict(),
        },
    )
    provenance_content = (
        provenance_path.read_text(encoding="utf-8") if provenance_path.is_file() else ""
    )
    atomic_write_text(run_dir / PROVENANCE_SNAPSHOT_NAME, provenance_content)
    atomic_write_json(
        run_dir / ENVIRONMENT_SNAPSHOT_NAME,
        {
            "python": sys.version,
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "run_dir": str(run_dir.resolve()),
            "managed_runner_manifest": os.environ.get("EXPERIMENT_RUN_MANIFEST", ""),
            "resource_visibility": os.environ.get("CUDA_VISIBLE_DEVICES", "caller-managed"),
        },
    )
    return CONFIG_SNAPSHOT_NAME, PROVENANCE_SNAPSHOT_NAME, ENVIRONMENT_SNAPSHOT_NAME


def write_case_records(run_dir: Path, records: tuple[CaseResult, ...]) -> None:
    """
    typed case record 全件を一つの atomic JSONL artifact として serialize します。

    Args:
        run_dir: cases.jsonl を受け取る result directory。
        records: failure を含む完全な順序付き case record。

    Side effects:
        空の CASES でも空 file を含め、cases.jsonl を atomic replace します。
    """
    content = "".join(
        json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    atomic_write_text(run_dir / RESULT_CASES_NAME, content)


def write_failure_evidence(
    run_dir: Path,
    *,
    status: str,
    failure_class: str,
    records: tuple[CaseResult, ...],
    close_condition: str,
    visualization_error: str = "not_applicable",
) -> None:
    """
    failure-cause classification と rerun closure evidence を保持します。

    Args:
        run_dir: failure-evidence.json を受け取る result directory。
        status: 現在の run state。
        failure_class: owner boundary が選択した安定した cause category。
        records: failed または blocked の typed case record。
        close_condition: failure を close とみなす前に必要な action。
        visualization_error: 明示的な visualization error または not_applicable。

    Side effects:
        failure-evidence.json を atomic replace します。
    """
    atomic_write_json(
        run_dir / FAILURE_EVIDENCE_NAME,
        {
            "state": status,
            "failure_class": failure_class,
            "records": [record.to_dict() for record in records],
            "visualization_error": visualization_error,
            "close_condition": close_condition,
        },
    )


def write_summary(run_dir: Path, summary: RunSummary) -> None:
    """
    typed RunSummary を summary.json として atomic に公開します。

    Args:
        run_dir: summary.json を受け取る result directory。
        summary: orchestration が選択した完全な run-level schema。

    Side effects:
        summary.json を atomic replace します。
    """
    atomic_write_json(run_dir / RESULT_SUMMARY_NAME, summary.to_dict())


def write_artifact_manifest(run_dir: Path, summary: RunSummary) -> None:
    """
    manifest 自身を除く run artifact 全件の digest を公開します。

    Args:
        run_dir: 完全な run snapshot を含む result directory。
        summary: manifest に identity を記録する final run state。

    Raises:
        OSError: materialized artifact を読めない、または manifest の atomic replace に
            失敗した場合。

    Side effects:
        run_dir 内の nested regular file 全件を読み、manifest を atomic に書きます。
    """
    entries = tuple(
        ArtifactEntry(
            path=relative_path,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(run_dir.rglob("*"))
        if (
            path.is_file()
            and not path.is_symlink()
            and path != run_dir / RESULT_MANIFEST_NAME
        )
        for relative_path in (path.relative_to(run_dir).as_posix(),)
    )
    manifest = ArtifactManifest(
        run_id=summary.run_id,
        state=summary.status,
        artifacts=entries,
    )
    atomic_write_json(run_dir / RESULT_MANIFEST_NAME, manifest.to_dict())
