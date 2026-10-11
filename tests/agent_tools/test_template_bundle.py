"""Focused external deterministic template bundle tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.agent.templates.template_bundle import (
    TemplateBundleError,
    bundle_identity,
    export_bundle,
    verify_codex_user_bundle,
)


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


def test_codex_user_profile_exports_source_free_plugin_and_verified_projection(
    tmp_path: Path,
) -> None:
    """A source-free plugin bundle verifies without Git and binds copied views."""
    first = tmp_path / "codex-user"
    second = tmp_path / "codex-user-repeat"
    identity = export_bundle(
        source_root=ROOT,
        source_ref="HEAD",
        profile="codex-user",
        output=first,
    )
    repeated = export_bundle(
        source_root=ROOT,
        source_ref="HEAD",
        profile="codex-user",
        output=second,
    )

    assert identity["bundle_digest"] == repeated["bundle_digest"]
    assert identity["source_bundle_digest"] == repeated["source_bundle_digest"]
    assert not (first / ".git").exists()
    assert not (first / "tests").exists()
    assert not (first / "documents" / "design").exists()
    assert (
        first / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
    ).is_file()
    assert (first / "plugin.json").is_file()
    assert (first / "marketplace.json").is_file()
    assert (first / "hooks" / "hooks.json").is_file()
    hook_config = json.loads((first / "hooks" / "hooks.json").read_text())
    assert set(hook_config["hooks"]) == {
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
    }
    for event, groups in hook_config["hooks"].items():
        assert all(
            hook["command"].startswith('bash "${PLUGIN_ROOT}/bootstrap.sh"')
            and f"codex hook {event}" in hook["command"]
            for group in groups
            for hook in group["hooks"]
        )
    assert (first / "skills" / "agent-canon-bootstrap" / "SKILL.md").is_file()
    assert "## User Flow" in (
        first / "skills" / "agent-canon-bootstrap" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert (first / "tools/runtime/container/bootstrap_runtime.py").is_file()

    verified = verify_codex_user_bundle(first)
    assert verified["bundle_digest"] == identity["bundle_digest"]
    assert any(row["component"] == "agent" for row in verified["install_files"])
    assert {
        (row["component"], row["destination"])
        for row in verified["install_files"]
    }.issuperset({("guidance", "codex/AGENTS.md")})

    (first / "hooks" / "hooks.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(TemplateBundleError, match="digest differs"):
        verify_codex_user_bundle(first)
