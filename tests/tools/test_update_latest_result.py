# @dependency-start
# contract test
# responsibility Tests flat-result variant-scoped latest pointer update behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/latest_result.rs helper under test
# @dependency-end

"""Tests for flat-result variant-scoped latest pointers."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def invoke_latest(result_root: Path, variant: str, *options: str) -> Path:
    result = subprocess.run(
        [
            os.environ["AGENT_CANON_CLI"],
            "update-latest-result",
            str(result_root),
            "--variant",
            variant,
            *options,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip())
    return Path(result.stdout.strip().removeprefix("latest_result_dir="))


def latest_result_dir(result_root: Path, variant: str) -> Path:
    return invoke_latest(result_root, variant, "--select-only")


def update_latest_result(
    result_root: Path, result_dir: Path | None, variant: str
) -> Path:
    options = ("--result-dir", str(result_dir)) if result_dir is not None else ()
    return invoke_latest(result_root, variant, *options)


def test_native_latest_entrypoint_help() -> None:
    result = subprocess.run(
        [os.environ["AGENT_CANON_CLI"], "update-latest-result", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def write_run(root: Path, variant: str, run_name: str, created_at: str) -> Path:
    """Write one complete flat result fixture for LATEST discovery."""
    run_dir = root / "experiments" / "demo.topic" / "result" / run_name
    run_dir.mkdir(parents=True)
    identity = {
        "schema": "agentcanon.experiment-run-identity/v2",
        "topic": "demo.topic",
        "variant": variant,
        "run_name": run_name,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"identity": identity, "created_at_utc": created_at}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary").mkdir()
    (run_dir / "summary" / "summary.json").write_text(
        '{"metric": 1}\n', encoding="utf-8"
    )
    (run_dir / "summary" / "report.html").write_text(
        "<html></html>\n", encoding="utf-8"
    )
    return run_dir


def test_update_latest_result_writes_flat_result_pointer(tmp_path: Path) -> None:
    """Write JSON and Markdown pointers below the flat result root."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = write_run(tmp_path, "smoke.v1", "run.a", "2026-01-01T00:00:00Z")

    update_latest_result(result_root, run_dir, "smoke.v1")

    payload = json.loads(
        (result_root / "LATEST.smoke.v1.json").read_text(encoding="utf-8")
    )
    assert payload["schema"] == "agentcanon.experiment-latest/v2"
    assert payload["identity"]["run_name"] == "run.a"
    assert payload["latest_result"] == "experiments/demo.topic/result/run.a"
    assert payload["summary_json"].endswith("/summary/summary.json")
    assert payload["visual_report_html"].endswith("/summary/report.html")
    assert payload["identity"]["variant"] == "smoke.v1"


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

    with pytest.raises(ValueError, match="manifest identity"):
        update_latest_result(result_root, run_dir, "smoke")


def test_latest_result_requires_variant_metadata(tmp_path: Path) -> None:
    """Reject manifests that omit variant metadata from the flat run directory."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    run_dir = result_root / "run.a"
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
    assert not (redirected_topic / "result" / "LATEST.smoke.json").exists()
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


def test_variant_pointers_are_independent_under_flat_result_root(
    tmp_path: Path,
) -> None:
    """A→B→A updates preserve independent variant pointer pairs."""
    result_root = tmp_path / "experiments" / "demo.topic" / "result"
    smoke = write_run(tmp_path, "smoke", "run.smoke", "2026-01-01T00:00:00Z")
    formal = write_run(tmp_path, "formal", "run.formal", "2026-01-02T00:00:00Z")

    update_latest_result(result_root, smoke, "smoke")
    update_latest_result(result_root, formal, "formal")
    update_latest_result(result_root, smoke, "smoke")

    smoke_payload = json.loads(
        (result_root / "LATEST.smoke.json").read_text(encoding="utf-8")
    )
    formal_payload = json.loads(
        (result_root / "LATEST.formal.json").read_text(encoding="utf-8")
    )
    assert smoke_payload["latest_result"].endswith("/result/run.smoke")
    assert formal_payload["latest_result"].endswith("/result/run.formal")
    assert smoke_payload["identity"]["variant"] == "smoke"
    assert formal_payload["identity"]["variant"] == "formal"
    assert not (result_root / "LATEST.json").exists()
    assert not (result_root / "LATEST.md").exists()


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
    latest_json = result_root / "LATEST.smoke.json"
    latest_markdown = result_root / "LATEST.smoke.md"
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert payload["identity"]["run_name"] == "run.b"
    assert payload["latest_result"].endswith("/result/run.b")
    assert "run.b" in latest_markdown.read_text(encoding="utf-8")
    identity_text = json.dumps(
        payload["identity"], sort_keys=True, separators=(",", ":")
    )
    assert latest_markdown.read_text(encoding="utf-8") == (
        "# Latest Experiment Result\n\n"
        f"- identity: `{identity_text}`\n"
        "- result: `experiments/demo.topic/result/run.b`\n"
        "- manifest: `experiments/demo.topic/result/run.b/run_manifest.json`\n"
        "- report: `experiments/demo.topic/report/run.b.md`\n"
        "- summary: `experiments/demo.topic/result/run.b/summary/summary.json`\n"
        "- visual report: `experiments/demo.topic/result/run.b/summary/report.html`\n"
    )
