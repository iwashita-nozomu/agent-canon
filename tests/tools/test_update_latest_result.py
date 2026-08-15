# @dependency-start
# contract test
# responsibility Tests variant-scoped latest-result pointer update behavior.
# upstream implementation ../../tools/experiments/update_latest_result.py helper under test
# @dependency-end

"""Tests for variant-scoped latest-result pointers."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import tools.experiments.update_latest_result as latest_module
from tools.experiments.experiment_identity import ExperimentIdentity
from tools.experiments.update_latest_result import (
    latest_result_dir,
    update_latest_result,
)


def write_run(root: Path, variant: str, run_name: str, created_at: str) -> Path:
    """Write one complete nested result fixture for LATEST discovery."""
    run_dir = root / "experiments" / "demo.topic" / "result" / variant / run_name
    run_dir.mkdir(parents=True)
    identity = ExperimentIdentity("demo.topic", variant, run_name)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({**identity.to_dict(), "created_at_utc": created_at}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text('{"metric": 1}\n', encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>\n", encoding="utf-8")
    return run_dir


def test_update_latest_result_writes_variant_pointer(tmp_path: Path) -> None:
    """Write JSON and Markdown pointers below the selected variant root."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "smoke.v1", "run.a", "2026-01-01T00:00:00Z")

    update_latest_result(result_root, run_dir, "smoke.v1")

    payload = json.loads(
        (result_root / "smoke.v1" / "LATEST.json").read_text(encoding="utf-8")
    )
    assert payload["schema"] == "agentcanon.experiment-latest/v2"
    assert payload["identity"]["run_name"] == "run.a"
    assert payload["latest_result"] == "experiments/demo.topic/result/smoke.v1/run.a"
    assert payload["summary_json"].endswith("/summary.json")
    assert payload["visual_report_html"].endswith("/report.html")
    assert not (result_root / "LATEST.json").exists()


def test_latest_result_selects_newest_with_run_name_tie_break(tmp_path: Path) -> None:
    """Select the newest manifest timestamp within one variant."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    older = write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    newer = write_run(tmp_path, "smoke", "run.b", "2026-01-02T00:00:00Z")

    assert latest_result_dir(result_root, "smoke") == newer
    assert latest_result_dir(result_root, "smoke") != older


def test_latest_result_rejects_cross_variant_explicit_directory(tmp_path: Path) -> None:
    """Reject an explicit result directory from a different variant."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "formal", "run.a", "2026-01-01T00:00:00Z")

    with pytest.raises(ValueError, match="another variant"):
        update_latest_result(result_root, run_dir, "smoke")


def test_latest_result_requires_nested_v2_identity(tmp_path: Path) -> None:
    """Reject manifests that use the removed flat identity form."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = result_root / "smoke" / "run.a"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"topic": "demo", "run_name": "run.a"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="identity"):
        latest_result_dir(result_root, "smoke")


def test_latest_result_rejects_manifest_symlink(tmp_path: Path) -> None:
    """Reject a run manifest symlink even when it points inside the run."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    manifest = run_dir / "run_manifest.json"
    target = run_dir / "manifest-target.json"
    target.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(target.name)

    with pytest.raises(ValueError, match="symlink"):
        latest_result_dir(result_root, "smoke")


def test_latest_result_rejects_symlinked_topic_parent(tmp_path: Path) -> None:
    """Reject a topic-parent symlink before publishing pointers through it."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    topic_dir = result_root.parent
    redirected_topic = tmp_path / "redirected-topic"
    topic_dir.rename(redirected_topic)
    topic_dir.symlink_to(redirected_topic, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked ancestor"):
        latest_result_dir(result_root, "smoke")
    assert not (redirected_topic / "result" / "smoke" / "LATEST.json").exists()
    assert run_dir.is_dir()


def test_latest_result_requires_timezone_aware_utc(tmp_path: Path) -> None:
    """Reject a naive timestamp instead of mixing naive and aware values."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00")

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        latest_result_dir(result_root, "smoke")


def test_latest_result_rejects_mixed_timestamp_contracts(tmp_path: Path) -> None:
    """Reject a mixed offset/UTC set before timestamp ordering can crash."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    write_run(tmp_path, "smoke", "run.b", "2026-01-02T00:00:00+09:00")

    with pytest.raises(ValueError, match="UTC"):
        latest_result_dir(result_root, "smoke")


def test_latest_pointer_concurrency_keeps_newest_json_and_markdown_consistent(
    tmp_path: Path,
) -> None:
    """Serialize competing updates so an older run cannot overwrite the newest."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    older = write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    newer = write_run(tmp_path, "smoke", "run.b", "2026-01-02T00:00:00Z")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda run_dir: update_latest_result(result_root, run_dir, "smoke"),
                (older, newer),
            )
        )

    assert all(outcome in {older, newer} for outcome in outcomes)
    assert newer in outcomes
    latest_json = result_root / "smoke" / "LATEST.json"
    latest_markdown = result_root / "smoke" / "LATEST.md"
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert payload["identity"]["run_name"] == "run.b"
    assert payload["latest_result"].endswith("/smoke/run.b")
    assert "run.b" in latest_markdown.read_text(encoding="utf-8")
    assert latest_markdown.read_text(encoding="utf-8") == latest_module._latest_markdown(
        payload
    )


def test_latest_pointer_pair_failure_rolls_back_without_temp_residue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback the first replacement when the second pointer cannot replace."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "smoke", "run.a", "2026-01-01T00:00:00Z")
    original_replace = latest_module.os.replace

    def fail_markdown_replace(source: str | bytes, destination: str | bytes) -> None:
        if Path(destination).name == "LATEST.md":
            raise OSError("injected markdown publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(latest_module.os, "replace", fail_markdown_replace)
    with pytest.raises(OSError, match="injected markdown"):
        update_latest_result(result_root, run_dir, "smoke")

    variant_root = result_root / "smoke"
    assert not (variant_root / "LATEST.json").exists()
    assert not (variant_root / "LATEST.md").exists()
    assert not list(variant_root.glob(".*LATEST*"))
