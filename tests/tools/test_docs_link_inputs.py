"""Canonical source docs must not be confused with generated runtime directories."""

# @dependency-start
# contract test
# responsibility Verifies literal-directory exclusions in the native link checker.
# upstream implementation ../../tools/validation/documentation/config/lychee.toml configured source selection
# @dependency-end

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tools/validation/documentation/config/lychee.toml"


@pytest.mark.parametrize(
    "relative,checked",
    [
        ("documents/runtime/source.md", True),
        ("documents/targeting.md", True),
        (".runtime/generated.md", False),
    ],
)
def test_native_link_filter_selects_directory_components(tmp_path, relative, checked):
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    source.write_text("# Fixture\n\n[Missing](missing.md)\n", encoding="utf-8")
    actual = subprocess.run(
        ["lychee", "--config", str(CONFIG), "--hidden", "--no-ignore", "./" + relative],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (actual.returncode != 0) is checked, actual.stdout + actual.stderr
    if checked:
        assert "missing.md" in actual.stdout + actual.stderr
