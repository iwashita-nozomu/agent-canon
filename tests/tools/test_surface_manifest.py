"""Focused schema tests for the surface-manifest producer."""

# @dependency-start
# contract test
# responsibility Verifies current-schema parsing and bounded version-1 owner/class normalization.
# upstream design ../../documents/design/dependency-manifest-design.md current producer and exact-base authority
# upstream implementation ../../tools/agent_tools/surface_manifest.py normalized-snapshot producer
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCER = PROJECT_ROOT / "tools" / "agent_tools" / "surface_manifest.py"


def load_producer():
    """Load the producer from the checkout under test."""
    spec = importlib.util.spec_from_file_location("surface_manifest_under_test", PRODUCER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_manifest(root: Path, text: str) -> Path:
    """Write one isolated manifest fixture."""
    path = root / "manifest.toml"
    path.write_text(text, encoding="utf-8")
    return path


CURRENT_MANIFEST = """\
version = 1
prefix = "vendor/agent-canon"

[[surface]]
path = "AGENTS.md"
mode = "symlink"
source = "ROOT_AGENTS.md"
projection_producer = "agent-canon"
projection_kind = "runtime_surface"

[[group]]
mode = "regular"
projection_producer = "project"
projection_kind = "project_content"
paths = ["README.md"]
"""


LEGACY_MANIFEST = """\
version = 1
prefix = "vendor/agent-canon"

[[surface]]
path = "AGENTS.md"
mode = "symlink"
source = "ROOT_AGENTS.md"
owner = "agent-canon"
class = "runtime_surface"

[[group]]
mode = "regular"
owner = "project"
class = "project_content"
paths = ["README.md"]
"""


def test_current_schema_is_accepted_and_normalized_in_tmp_path(tmp_path: Path) -> None:
    """The current producer schema remains the normal path."""
    module = load_producer()
    write_manifest(tmp_path, CURRENT_MANIFEST)
    manifest = module.load_manifest(tmp_path, "", "manifest.toml")
    payload = module.normalized_snapshot(manifest)
    assert payload["schema"] == module.NORMALIZED_SNAPSHOT_SCHEMA
    entries = {entry["path"]: entry for entry in payload["entries"]}
    assert entries["AGENTS.md"]["projection_producer"] == "agent-canon"
    assert entries["README.md"]["projection_kind"] == "project_content"


def test_legacy_aliases_are_normalized_only_for_normalized_snapshot(
    tmp_path: Path,
) -> None:
    """Legacy owner/class fields are confined to the producer snapshot route."""
    module = load_producer()
    write_manifest(tmp_path, LEGACY_MANIFEST)
    with pytest.raises(ValueError, match="legacy aliases are unsupported"):
        module.load_manifest(tmp_path, "", "manifest.toml")

    manifest = module.load_manifest(
        tmp_path,
        "",
        "manifest.toml",
        allow_legacy_aliases=True,
    )
    payload = module.normalized_snapshot(manifest)
    entries = {entry["path"]: entry for entry in payload["entries"]}
    assert entries["AGENTS.md"]["projection_producer"] == "agent-canon"
    assert entries["AGENTS.md"]["projection_kind"] == "runtime_surface"

    result = subprocess.run(
        [
            sys.executable,
            str(PRODUCER),
            "--root",
            str(tmp_path),
            "--prefix",
            "",
            "--manifest",
            "manifest.toml",
            "normalized-snapshot",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    entries = {entry["path"]: entry for entry in json.loads(result.stdout)["entries"]}
    assert entries["AGENTS.md"]["projection_kind"] == "runtime_surface"

    link_result = subprocess.run(
        [
            sys.executable,
            str(PRODUCER),
            "--root",
            str(tmp_path),
            "--prefix",
            "",
            "--manifest",
            "manifest.toml",
            "link-specs",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert link_result.returncode == 1
    assert "legacy aliases are unsupported" in link_result.stderr


@pytest.mark.parametrize(
    ("label", "manifest"),
    (
        (
            "dual-pair",
            LEGACY_MANIFEST.replace(
                'owner = "agent-canon"\n',
                'owner = "agent-canon"\nprojection_producer = "agent-canon"\n',
            ),
        ),
        (
            "mixed-aliases",
            LEGACY_MANIFEST.replace(
                'owner = "project"\nclass = "project_content"\n',
                'projection_producer = "project"\nprojection_kind = "project_content"\n',
            ),
        ),
        (
            "missing-pair",
            LEGACY_MANIFEST.replace('class = "runtime_surface"\n', ""),
        ),
        (
            "unsupported-version",
            LEGACY_MANIFEST.replace("version = 1", "version = 2"),
        ),
        (
            "unknown-top-level",
            LEGACY_MANIFEST.replace(
                'prefix = "vendor/agent-canon"\n',
                'prefix = "vendor/agent-canon"\nextra = "reject"\n',
            ),
        ),
        (
            "unknown-surface-key",
            LEGACY_MANIFEST.replace(
                'path = "AGENTS.md"\n',
                'path = "AGENTS.md"\nunknown = "reject"\n',
            ),
        ),
        (
            "unknown-group-key",
            LEGACY_MANIFEST.replace(
                'paths = ["README.md"]\n',
                'paths = ["README.md"]\nunknown = "reject"\n',
            ),
        ),
        (
            "invalid-alias-value",
            LEGACY_MANIFEST.replace('owner = "agent-canon"', 'owner = "unknown"'),
        ),
    ),
)
def test_legacy_schema_failures_are_rejected_before_normalization(
    tmp_path: Path, label: str, manifest: str
) -> None:
    """Dual, mixed, missing, unknown, unsupported, and invalid data fail closed."""
    del label
    module = load_producer()
    write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError):
        module.load_manifest(
            tmp_path,
            "",
            "manifest.toml",
            allow_legacy_aliases=True,
        )
