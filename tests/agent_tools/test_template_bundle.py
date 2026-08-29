"""Focused external deterministic template bundle tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.agent.templates.template_bundle import TemplateBundleError, bundle_identity, export_bundle


ROOT = Path(__file__).resolve().parents[2]


def test_export_is_fresh_external_and_source_bound(tmp_path: Path) -> None:
    result = export_bundle(
        source_root=ROOT,
        source_ref="HEAD",
        profile="agent-artifacts",
        output=tmp_path / "bundle",
    )
    assert result["source_commit"]
    assert result["bundle_digest"]
    assert (tmp_path / "bundle/template-bundle-provenance.json").is_file()
    with pytest.raises(TemplateBundleError, match="outside"):
        export_bundle(
            source_root=ROOT,
            source_ref="HEAD",
            profile="agent-artifacts",
            output=ROOT / "workspace" / "template-output",
        )


def test_bundle_identity_has_profile_and_manifest_inputs() -> None:
    agent = bundle_identity(ROOT, "HEAD", "agent-artifacts")
    documents = bundle_identity(ROOT, "HEAD", "document-artifacts")
    assert agent["source_commit"] == documents["source_commit"]
    assert agent["manifest_digest"] == documents["manifest_digest"]
    assert agent["bundle_digest"] != documents["bundle_digest"]


def test_template_bundle_imports_on_runtime_python() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from tools.agent.templates.template_bundle import bundle_identity; print(bundle_identity.__name__)"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "bundle_identity"
