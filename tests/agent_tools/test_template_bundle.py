"""Focused external deterministic template bundle tests."""
# @dependency-start
# contract test
# responsibility Verifies export ownership, snapshot-bound resources, and Codex plugin layout.
# upstream implementation ../../tools/agent/templates/template_bundle.py export and verification owner
# upstream design ../../documents/contracts/template-bundle-manifest.toml selected profile inputs
# @dependency-end

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.agent.templates import template_bundle
from tools.agent.templates.template_bundle import (
    TemplateBundleError,
    bundle_identity,
    export_bundle,
    verify_codex_user_bundle,
)

ROOT = Path(__file__).resolve().parents[2]


def source_fixture(tmp_path: Path, body: str | None = None) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    hook = {"hooks": [{"type": "command", "command": "original-hook"}]}
    files = {
        "documents/contracts/template-bundle-manifest.toml": (
            'version = 1\n[profiles.codex-user]\nroots = ["ROOT_AGENTS.md", '
            '".codex/hooks.json", ".codex/personal/skills", "agents/skills", "LICENSE"]\n'
            '[profiles.experiment-scaffold]\nroots = ["templates/experiments"]\n'
        ),
        "ROOT_AGENTS.md": "# Common guidance\n",
        ".codex/hooks.json": json.dumps(
            {
                "hooks": {
                    name: [hook]
                    for name in ("UserPromptSubmit", "PreToolUse", "PostToolUse")
                }
            }
        ),
        ".codex/personal/skills/demo/SKILL.md": (
            "---\nname: demo\ndescription: Demonstrate a source-free workflow.\n---\n"
        ),
        "agents/skills/demo.md": body
        or (
            "# Demo\n<!--\n@dependency-start\ncontract skill\n"
            "responsibility Source maintenance metadata.\n@dependency-end\n-->\n"
            "[guide](../../references/guide.md#read)\n"
            "[peer](peer.md)\n![icon](../../assets/icon.svg)\n"
            "[external](https://example.com/guide)\n[section](#demo)\n"
            "`[literal](not-a-resource.md)`\n"
            "```markdown\n[example](not-a-resource-either.md)\n```\n"
            "[named][nested]\n[nested]: ../../references/nested.md#nested\n"
        ),
        "agents/skills/peer.md": "# Peer\n[shared](../../references/guide.md)\n",
        "references/guide.md": (
            "# Read\n[child](nested.md)\n[template](../templates/experiments/example)\n"
        ),
        "references/nested.md": "# Nested\n",
        "references/unrelated.md": "# Unreferenced document\n",
        "templates/experiments/example/README.md": "# Instance\n[future](../../consumer-doc.md)\n",
        "templates/experiments/example/input.json": '{"value": 1}\n',
        "assets/icon.svg": '<svg xmlns="http://www.w3.org/2000/svg"/>\n',
        "LICENSE": "Fixture license\n",
        "tests/unrelated.py": "# Unreferenced source is not a package resource.\n",
    }
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.name", "Bundle fixture"], check=True
    )
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "bundle@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "fixture"], check=True)
    return source


def test_codex_export_preserves_reachable_resources_and_template_inputs(
    tmp_path: Path,
) -> None:
    source = source_fixture(tmp_path)
    output = tmp_path / "bundle"
    export_bundle(
        source_root=source, source_ref="HEAD", profile="codex-user", output=output
    )
    body = (output / "skills/demo/SKILL.md").read_text()
    assert "@dependency-start" not in body
    assert (output / "agents/skills/demo.md").read_bytes() == (
        source / "agents/skills/demo.md"
    ).read_bytes()
    assert "[peer](../../agents/skills/peer.md)" in body
    assert "[guide](../../references/guide.md#read)" in body
    assert "[external](https://example.com/guide)" in body
    assert "[section](#demo)" in body
    assert "`[literal](not-a-resource.md)`" in body
    assert "[example](not-a-resource-either.md)" in body
    assert "[nested]: ../../references/nested.md#nested" in body
    for name in (
        "references/guide.md",
        "references/nested.md",
        "assets/icon.svg",
        "LICENSE",
        "templates/experiments/example/README.md",
        "templates/experiments/example/input.json",
    ):
        assert (output / name).read_bytes() == (source / name).read_bytes()
    manifest = json.loads((output / "codex-user-bundle.json").read_text())
    paths = [row["path"] for row in manifest["files"]]
    assert paths.count("references/guide.md") == 1
    assert "tests/unrelated.py" not in paths
    assert "references/unrelated.md" not in paths
    assert not (output / ".git").exists()


@pytest.mark.parametrize("target", ["../../missing.md", "../../../escape.md"])
def test_codex_export_rejects_unresolvable_local_resources(
    tmp_path: Path, target: str
) -> None:
    source = source_fixture(tmp_path, f"# Demo\n[resource]({target})\n")
    with pytest.raises(TemplateBundleError, match="Markdown resource"):
        export_bundle(
            source_root=source,
            source_ref="HEAD",
            profile="codex-user",
            output=tmp_path / "bundle",
        )


@pytest.mark.parametrize(
    "resource",
    [
        "skills/demo/SKILL.md",
        "guidance/AGENTS.md",
        "hooks/hooks.json",
        "plugin.json",
        ".agents/plugins/marketplace.json",
        "codex-user-bundle.json",
    ],
)
def test_codex_export_rejects_resources_at_generated_paths(
    tmp_path: Path, resource: str
) -> None:
    source = source_fixture(tmp_path, f"# Demo\n[resource](../../{resource})\n")
    path = source / resource
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Source resource.\n")
    subprocess.run(["git", "-C", str(source), "add", "--all"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "commit", "-qm", "resource collision"], check=True
    )
    with pytest.raises(TemplateBundleError, match="collides with source"):
        export_bundle(
            source_root=source,
            source_ref="HEAD",
            profile="codex-user",
            output=tmp_path / "bundle",
        )


@pytest.mark.parametrize(
    "relative", ["folder\\file.md", "C:note.md", "../note.md", "/note.md", "CON.txt"]
)
def test_bundle_destinations_reject_nonportable_file_names(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(TemplateBundleError, match="bundle file"):
        template_bundle._bundle_destination(tmp_path, relative)
    assert not list(tmp_path.iterdir())


def test_codex_resources_follow_the_requested_commit(tmp_path: Path) -> None:
    source = source_fixture(tmp_path)
    first = export_bundle(
        source_root=source,
        source_ref="HEAD",
        profile="codex-user",
        output=tmp_path / "first",
    )
    resource = source / "references/nested.md"
    resource.write_text("# Nested\nChanged resource.\n")
    unchanged = export_bundle(
        source_root=source,
        source_ref="HEAD",
        profile="codex-user",
        output=tmp_path / "unchanged",
    )
    assert unchanged["bundle_digest"] == first["bundle_digest"]
    subprocess.run(
        ["git", "-C", str(source), "add", "references/nested.md"], check=True
    )
    subprocess.run(
        ["git", "-C", str(source), "commit", "-qm", "resource change"], check=True
    )
    changed = export_bundle(
        source_root=source,
        source_ref="HEAD",
        profile="codex-user",
        output=tmp_path / "changed",
    )
    assert changed["bundle_digest"] != first["bundle_digest"]
    assert (
        tmp_path / "changed/references/nested.md"
    ).read_bytes() == resource.read_bytes()


def test_export_uses_its_own_composer_not_source_modules(tmp_path: Path) -> None:
    source = source_fixture(tmp_path)
    for relative in ("tools", "tools/agent", "tools/agent/templates"):
        directory = source / relative
        directory.mkdir(exist_ok=True)
        (directory / "__init__.py").write_text("")
    (source / "tools/agent/templates/entrypoint_composer.py").write_text(
        "Composition = None\n"
    )
    subprocess.run(["git", "-C", str(source), "add", "tools"], check=True)
    subprocess.run(
        ["git", "-C", str(source), "commit", "-qm", "independent source tools"],
        check=True,
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/agent/templates/template_bundle.py"),
            "export",
            "--source-root",
            str(source),
            "--source-ref",
            "HEAD",
            "--profile",
            "codex-user",
            "--output",
            str(tmp_path / "bundle"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "bundle/guidance/AGENTS.md").is_file()


def test_export_accepts_dispatcher_prepared_empty_directory(tmp_path: Path) -> None:
    output = tmp_path / "prepared"
    output.mkdir()
    result = export_bundle(
        source_root=ROOT, source_ref="HEAD", profile="agent-artifacts", output=output
    )
    assert result["output"] == str(output)
    assert (output / "template-bundle-provenance.json").is_file()


def test_export_rejects_existing_content_and_symlinks(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "user.txt").write_bytes(b"keep")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    for output in (occupied, link):
        with pytest.raises(TemplateBundleError, match="fresh"):
            export_bundle(
                source_root=ROOT,
                source_ref="HEAD",
                profile="agent-artifacts",
                output=output,
            )
    assert (occupied / "user.txt").read_bytes() == b"keep"
    assert not list(target.iterdir())


def test_export_does_not_overwrite_a_file_added_during_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "bundle"
    identity = template_bundle.bundle_identity
    collisions: list[Path] = []

    def with_collision(root: Path, source_ref: str, profile: str) -> dict[str, Any]:
        result = identity(root, source_ref, profile)
        target = output / result["paths"][0]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"concurrent user data")
        collisions.append(target)
        return result

    monkeypatch.setattr(template_bundle, "bundle_identity", with_collision)
    with pytest.raises(FileExistsError):
        export_bundle(
            source_root=ROOT,
            source_ref="HEAD",
            profile="agent-artifacts",
            output=output,
        )
    assert collisions[0].read_bytes() == b"concurrent user data"


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
        [
            sys.executable,
            "-c",
            "from tools.agent.templates.template_bundle import bundle_identity; print(bundle_identity.__name__)",
        ],
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
    assert stat.S_IMODE((first / "bootstrap.sh").stat().st_mode) == 0o755
    assert (first / "agents/skills/slides.md").is_file()
    assert (first / "agents/skills/README.md").is_file()
    assert (first / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    assert (
        first / "documents" / "runtime" / "runtime-profiles-and-check-matrix.json"
    ).is_file()
    assert (first / "plugin.json").is_file()
    assert (first / ".agents/plugins/marketplace.json").is_file()
    assert not (first / "marketplace.json").exists()
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
        (row["component"], row["destination"]) for row in verified["install_files"]
    }.issuperset({("guidance", "codex/AGENTS.md")})

    (first / "hooks" / "hooks.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(TemplateBundleError, match="digest differs"):
        verify_codex_user_bundle(first)
