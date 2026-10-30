# @dependency-start
# contract test
# responsibility Tests result-log conversion and summary tools.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md result policy
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/result_logs/mod.rs native transforms under test
# @dependency-end

"""Tests for result-log conversion and summary helpers."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def _run_native(*args: str) -> subprocess.CompletedProcess[str]:
    if AGENT_CANON_CLI is None:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return subprocess.run(
        [AGENT_CANON_CLI, *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_jsonl_to_md_writes_markdown_table(tmp_path: Path) -> None:
    """JSONL converter should keep preferred keys first and skip bad lines."""
    source = tmp_path / "events.jsonl"
    output = tmp_path / "events.md"
    source.write_text(
        "\n".join(
            [
                json.dumps({"case": "demo", "iter": 1, "metric": 2.5}, ensure_ascii=True),
                "not-json",
                json.dumps({"event": "done", "status": "ok"}, ensure_ascii=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_native("jsonl-to-md", str(source), str(output))

    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "# JSONL Report" in text
    assert "| case | demo |" in text
    assert "| iter | 1 |" in text
    assert "| event | done |" in text
    assert "not-json" not in text


def test_hlo_summary_counts_ops(tmp_path: Path) -> None:
    """HLO summary should count selected HLO records and operation tokens."""
    source = tmp_path / "hlo.jsonl"
    hlo_text = "\n".join(
        [
            "%0 = stablehlo.add(%arg0, %arg1) : tensor<f32>",
            "%1 = stablehlo.multiply(%0, %arg1) : tensor<f32>",
        ]
    )
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {"case": "hlo", "tag": "demo", "dialect": "stablehlo", "hlo": hlo_text},
                    ensure_ascii=True,
                ),
                json.dumps({"case": "other", "hlo": "%x = ignored()"}, ensure_ascii=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_native("summarize-hlo-jsonl", str(source))

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["total_records"] == 2
    assert summary["total_selected"] == 1
    assert ["demo", 1] in summary["tags"]
    assert ["stablehlo", 1] in summary["dialects"]
    assert ["stablehlo.add", 1] in summary["top_ops"]
    assert ["stablehlo.multiply", 1] in summary["top_ops"]
