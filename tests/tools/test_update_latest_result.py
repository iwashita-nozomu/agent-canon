# @dependency-start
# contract test
# responsibility Tests latest-result pointer update helper behavior.
# upstream design ../../documents/result-log-retention-and-visualization.md result policy
# upstream implementation ../../tools/experiments/update_latest_result.py helper under test
# @dependency-end

"""Tests for latest-result pointer updates."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tools.experiments.update_latest_result import (
    latest_result_dir,
    update_latest_result,
)


def test_update_latest_result_writes_json_and_markdown(tmp_path: Path) -> None:
    """The helper should point to a selected result directory."""
    result_root = tmp_path / "result"
    run_dir = result_root / "run-a"
    visual_dir = run_dir / "visual_diagnostics"
    visual_dir.mkdir(parents=True)
    (run_dir / "result_manifest.json").write_text('{"status": "ok"}', encoding="utf-8")
    (run_dir / "summary.json").write_text('{"metric": 1}', encoding="utf-8")
    (visual_dir / "report.html").write_text("<html></html>", encoding="utf-8")

    update_latest_result(result_root, run_dir)

    payload = json.loads((result_root / "LATEST.json").read_text(encoding="utf-8"))
    assert payload["latest_result_name"] == "run-a"
    assert payload["summary_json"] == str(run_dir / "summary.json")
    assert payload["result_manifest"] == str(run_dir / "result_manifest.json")
    assert payload["visual_report_html"] == str(visual_dir / "report.html")
    latest_md = (result_root / "LATEST.md").read_text(encoding="utf-8")
    assert "Latest Experiment Result" in latest_md
    assert "run-a" in latest_md


def test_update_latest_result_selects_newest_manifest(tmp_path: Path) -> None:
    """Without explicit result-dir, the newest manifest directory is selected."""
    result_root = tmp_path / "result"
    old_dir = result_root / "old"
    new_dir = result_root / "new"
    old_dir.mkdir(parents=True)
    new_dir.mkdir()
    (old_dir / "result_manifest.json").write_text("{}", encoding="utf-8")
    (new_dir / "result_manifest.json").write_text("{}", encoding="utf-8")
    os.utime(old_dir / "result_manifest.json", ns=(1_000_000_000, 1_000_000_000))
    os.utime(new_dir / "result_manifest.json", ns=(2_000_000_000, 2_000_000_000))

    selected = latest_result_dir(result_root)

    assert selected == new_dir


def test_update_latest_result_accepts_managed_run_manifest_and_top_level_report(
    tmp_path: Path,
) -> None:
    """Managed experiment runs write run_manifest.json and top-level report.html."""
    result_root = tmp_path / "result"
    run_dir = result_root / "managed-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text('{"status": "ok"}', encoding="utf-8")
    (run_dir / "summary.json").write_text('{"metric": 1}', encoding="utf-8")
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")

    update_latest_result(result_root, run_dir)

    payload = json.loads((result_root / "LATEST.json").read_text(encoding="utf-8"))
    assert payload["latest_result_name"] == "managed-run"
    assert payload["summary_json"] == str(run_dir / "summary.json")
    assert payload["result_manifest"] == str(run_dir / "run_manifest.json")
    assert payload["visual_report_html"] == str(run_dir / "report.html")
