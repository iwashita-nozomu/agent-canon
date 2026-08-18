#!/usr/bin/env python3
"""Apply exact validation and canonical skill corrections for Issue #766."""

from __future__ import annotations

import base64
import gzip
import subprocess
from pathlib import Path

ASSET_DIR = Path(".github/issue-766")
TEST = Path("tests/tools/test_save_experiment_result_annex.py")
RUNNER = Path("tools/experiments/run_managed_experiment.py")
BRANCH = "feat/766-split-raw-annex-results"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    """Replace one asserted generated-source fragment."""
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} drifted: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    TEST,
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

runner_text = RUNNER.read_text(encoding="utf-8")
raw_exclusion = '''EXCLUDED_SOURCE_SNAPSHOT_DIRS = frozenset(
    {
        ".git",
        "raw",
        "result",
'''
if raw_exclusion not in runner_text:
    replace_once(
        RUNNER,
        '''EXCLUDED_SOURCE_SNAPSHOT_DIRS = frozenset(
    {
        ".git",
        "result",
''',
        raw_exclusion,
        "raw source-snapshot exclusion owner",
    )

skill_parts = sorted(ASSET_DIR.glob("skill-part-*"))
if [path.name for path in skill_parts] != ["skill-part-00", "skill-part-01"]:
    raise SystemExit("canonical skill patch transport is incomplete")
encoded = "".join(path.read_text(encoding="utf-8") for path in skill_parts)
try:
    skill_source = gzip.decompress(
        base64.b64decode(encoded, validate=True)
    ).decode("utf-8")
except (ValueError, OSError, UnicodeError) as error:
    raise SystemExit(f"canonical skill patch transport is invalid: {error}") from error
exec(compile(skill_source, str(ASSET_DIR / "skill_patch.py"), "exec"))

# A pull_request workflow checks out the synthetic merge ref. Preserve the
# applied implementation while giving the existing commit step a real branch
# ref to push. The branch is later normalized to a clean main-based commit.
current_branch = subprocess.run(
    ["git", "branch", "--show-current"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()
if current_branch != BRANCH:
    subprocess.run(["git", "switch", "-C", BRANCH], check=True)
