#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Updates latest experiment result pointers.
# upstream design ../../documents/result-log-retention-and-visualization.md defines latest-result pointer policy.
# upstream design ../../documents/experiment-report-style.md defines experiment report artifact layout.
# downstream implementation ../../tests/tools/test_update_latest_result.py validates latest result pointer updates.
# @dependency-end
"""Update LATEST.json and LATEST.md for experiment result roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _manifest_path(result_dir: Path) -> Path:
    for name in ("result_manifest.json", "run_manifest.json"):
        candidate = result_dir / name
        if candidate.exists():
            return candidate
    return result_dir / "result_manifest.json"


def _visual_report_path(result_dir: Path) -> Path:
    candidates = (result_dir / "visual_diagnostics" / "report.html", result_dir / "report.html")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _existing_path_text(path: Path) -> str | None:
    if path.exists():
        return str(path)
    return None


def _result_timestamp(result_dir: Path) -> float:
    manifest_path = _manifest_path(result_dir)
    if manifest_path.exists():
        return manifest_path.stat().st_mtime
    return result_dir.stat().st_mtime


def latest_result_dir(result_root: Path) -> Path:
    """Return the newest result directory under a result root."""
    candidates = [path for path in result_root.iterdir() if path.is_dir()]
    if not candidates:
        raise SystemExit(f"no result directories under {result_root}")
    return max(candidates, key=_result_timestamp)


def _latest_result_dir(result_root: Path) -> Path:
    return latest_result_dir(result_root)


def _latest_payload(result_root: Path, result_dir: Path) -> dict[str, object]:
    manifest_path = _manifest_path(result_dir)
    summary_path = result_dir / "summary.json"
    report_path = _visual_report_path(result_dir)
    return {
        "result_root": str(result_root),
        "latest_result": str(result_dir),
        "latest_result_name": str(result_dir.relative_to(result_root)),
        "result_manifest": _existing_path_text(manifest_path),
        "summary_json": _existing_path_text(summary_path),
        "visual_report_html": _existing_path_text(report_path),
    }


def _write_latest_result_files(result_root: Path, payload: dict[str, object]) -> None:
    latest_json = result_root / "LATEST.json"
    latest_markdown = result_root / "LATEST.md"
    markdown = _latest_markdown(payload)
    latest_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_markdown.write_text(markdown, encoding="utf-8")


def _latest_markdown(payload: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Latest Experiment Result",
            "",
            f"- result: `{payload['latest_result']}`",
            f"- manifest: `{payload['result_manifest']}`",
            f"- summary: `{payload['summary_json']}`",
            f"- visual report: `{payload['visual_report_html']}`",
            "",
        ]
    )


def update_latest_result(result_root: Path, result_dir: Path) -> None:
    """Write latest-result pointers for an explicit result directory."""
    payload = _latest_payload(result_root, result_dir)
    _write_latest_result_files(result_root, payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--result-dir", type=Path, dest="result_dir")
    return parser.parse_args()


def main() -> None:
    """Run the latest-result pointer updater."""
    args = _parse_args()
    result_root = args.result_root
    result_dir = args.result_dir
    if result_dir is None:
        result_dir = latest_result_dir(result_root)
    update_latest_result(result_root, result_dir)
    print(f"latest_result_dir={result_dir}")


if __name__ == "__main__":
    main()
