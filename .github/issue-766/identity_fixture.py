#!/usr/bin/env python3
"""Prepare or restore the asserted Issue #766 identity test fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

PATH = Path("tests/tools/test_experiment_identity.py")

CURRENT_IMPORTS = '''    contained_path,
    load_json_text,
    report_relative_path,
    result_relative_path,
'''
ASSERTED_IMPORTS = '''    contained_path,
    identity_from_manifest,
    load_json_file,
    load_json_text,
    report_relative_path,
    result_relative_path,
'''
CURRENT_ASSERTIONS = '''    assert result_relative_path(identity) == Path("experiments/topic.v1/result/smoke.v2/run.3")
    assert report_relative_path(identity) == Path("experiments/report/topic.v1/smoke.v2/run.3.md")
'''
ASSERTED_ASSERTIONS = '''    assert result_relative_path(identity) == Path("experiments/demo/result/formal/run-a")
    assert report_relative_path(identity) == Path(
        "experiments/report/demo/formal/run-a.md"
    )
'''
PATCHED_IMPORTS = '''    contained_path,
    identity_from_manifest,
    identity_from_raw_relative_path,
    load_json_file,
    load_json_text,
    raw_relative_path,
    report_relative_path,
    result_relative_path,
'''
CANONICAL_IMPORTS = '''    contained_path,
    identity_from_raw_relative_path,
    load_json_text,
    raw_relative_path,
    report_relative_path,
    result_relative_path,
'''
PATCHED_ASSERTIONS = '''    assert result_relative_path(identity) == Path("experiments/demo/result/formal/run-a")
    assert raw_relative_path(identity) == Path("experiments/demo/raw/formal/run-a")
    assert identity_from_raw_relative_path(raw_relative_path(identity)) == identity
    assert report_relative_path(identity) == Path(
        "experiments/report/demo/formal/run-a.md"
    )
'''
CANONICAL_ASSERTIONS = '''    assert result_relative_path(identity) == Path("experiments/topic.v1/result/smoke.v2/run.3")
    assert raw_relative_path(identity) == Path("experiments/topic.v1/raw/smoke.v2/run.3")
    assert identity_from_raw_relative_path(raw_relative_path(identity)) == identity
    assert report_relative_path(identity) == Path("experiments/report/topic.v1/smoke.v2/run.3.md")
'''


def replace_pair(old_imports: str, new_imports: str, old_assertions: str, new_assertions: str) -> None:
    text = PATH.read_text(encoding="utf-8")
    if text.count(old_imports) != 1 or text.count(old_assertions) != 1:
        raise SystemExit("identity test fixture drifted")
    PATH.write_text(
        text.replace(old_imports, new_imports, 1).replace(
            old_assertions, new_assertions, 1
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "restore"))
    mode = parser.parse_args().mode
    if mode == "prepare":
        replace_pair(CURRENT_IMPORTS, ASSERTED_IMPORTS, CURRENT_ASSERTIONS, ASSERTED_ASSERTIONS)
    else:
        replace_pair(PATCHED_IMPORTS, CANONICAL_IMPORTS, PATCHED_ASSERTIONS, CANONICAL_ASSERTIONS)


if __name__ == "__main__":
    main()
