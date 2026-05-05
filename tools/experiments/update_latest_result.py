# @dependency-start
# responsibility Updates latest-result pointers for experiment result directories.
# upstream design ../../documents/result-log-retention-and-visualization.md result retention policy
# upstream design ../../documents/experiment-report-style.md experiment report policy
# @dependency-end
"""Update ``LATEST.json`` and ``LATEST.md`` for an experiment result root."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    """Return a UTC timestamp for reporting artifacts."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _latest_result_dir(result_root: Path, /) -> Path:
    """Return the newest child directory that contains ``result_manifest.json``."""
    candidates = [
        path.parent
        for path in result_root.glob("*/result_manifest.json")
        if path.is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No result_manifest.json found below result root: {result_root}"
        )
    return max(
        enumerate(candidates),
        key=lambda item: (
            (item[1] / "result_manifest.json").stat().st_mtime_ns,
            item[0],
        ),
    )[1]


def _latest_payload(result_dir: Path, /) -> dict[str, object]:
    """Return the latest-result pointer payload."""
    summary_path = result_dir / "summary.json"
    manifest_path = result_dir / "result_manifest.json"
    visual_report = result_dir / "visual_diagnostics" / "report.html"
    return {
        "schema_version": 1,
        "run_name": result_dir.name,
        "result_dir": str(result_dir),
        "summary": str(summary_path),
        "result_manifest": str(manifest_path),
        "visual_report_html": str(visual_report) if visual_report.exists() else None,
        "updated_at_utc": _utc_now(),
    }


def update_latest_result(result_root: Path, result_dir: Path | None = None, /) -> Path:
    """Write latest-result pointer files and return the selected result dir."""
    selected = result_dir if result_dir is not None else _latest_result_dir(result_root)
    payload = _latest_payload(selected)
    result_root.mkdir(parents=True, exist_ok=True)
    (result_root / "LATEST.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (result_root / "LATEST.md").write_text(
        "\n".join(
            [
                "# Latest Experiment Result",
                "",
                f"- Run name: `{payload['run_name']}`",
                f"- Result directory: `{payload['result_dir']}`",
                f"- Summary: `{payload['summary']}`",
                f"- Result manifest: `{payload['result_manifest']}`",
                f"- Visual report HTML: `{payload['visual_report_html']}`",
                f"- Updated at UTC: `{payload['updated_at_utc']}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return selected


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Update LATEST.json and LATEST.md for an experiment result root."
    )
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--result-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    """Run the latest-result pointer update."""
    args = _parse_args()
    selected = update_latest_result(args.result_root, args.result_dir)
    print(f"latest_result_dir={selected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
