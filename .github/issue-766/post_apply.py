#!/usr/bin/env python3
"""Apply exact validation corrections after the Issue #766 source patch."""

from pathlib import Path

TEST = Path("tests/tools/test_save_experiment_result_annex.py")


def replace_once(old: str, new: str, label: str) -> None:
    """Replace one asserted generated-source fragment."""
    text = TEST.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} drifted: expected one match, found {count}")
    TEST.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    '''            str(SCRIPT),
            "--result-dir",
            str(tmp_path / "result"),
''',
    '''            str(SCRIPT),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--result-dir",
            str(tmp_path / "result"),
''',
    "whole-result compatibility rejection fixture",
)
