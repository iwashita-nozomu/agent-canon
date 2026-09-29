"""Git owns skill delivery; bootstrap only connects stable discovery paths."""

# @dependency-start
# contract test
# responsibility Verifies Git-only skill updates and fixed discovery links.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md Git delivery contract
# upstream implementation ../../bootstrap/host/lifecycle/entrypoint.sh global link installation
# upstream implementation ../../tools/runtime/container/bootstrap_runtime.py isolated directory registration
# @dependency-end

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.runtime.container.bootstrap_runtime import BootstrapError, BootstrapRuntime

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "bootstrap/host/lifecycle/entrypoint.sh"
SKILLS = Path(".codex/personal/skills")


def git(root: Path, *args: str) -> str:
    """Run the actual Git operation against an isolated fixture repository."""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "Skill delivery test",
            "GIT_AUTHOR_EMAIL": "skill-test@example.invalid",
            "GIT_COMMITTER_NAME": "Skill delivery test",
            "GIT_COMMITTER_EMAIL": "skill-test@example.invalid",
        },
    ).stdout.strip()


def install_links(home: Path, checkout: Path) -> subprocess.CompletedProcess[str]:
    """Exercise the production host link owner without starting Docker."""
    state = home / "state"
    state.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", "-c", 'source "$1"; _agent_canon_install_global_links', "--", str(ADAPTER)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_CONTROL_ROOT": str(home),
            "AGENT_CANON_REPOSITORY_ROOT": str(checkout),
            "AGENT_CANON_STATE_ROOT": str(state),
        },
    )


def test_every_public_skill_is_tracked_and_matches_catalog() -> None:
    """A clean Git checkout carries valid adapters for the complete catalog."""
    catalog = yaml.safe_load((ROOT / "agents/skills/catalog.yaml").read_text())
    expected = {entry["shim"]: entry for entry in catalog["skill_families"]}
    actual = set(git(ROOT, "ls-files", str(SKILLS / "*/SKILL.md")).splitlines())
    assert actual == set(expected)
    for relative, entry in expected.items():
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        metadata = yaml.safe_load(text.split("---", 2)[1])
        assert metadata["name"] == entry["discovery"]["name"]
        assert metadata["description"] == entry["discovery"]["description"]
        assert (ROOT / entry["canonical_doc"]).is_file()
        assert "../../../../" + entry["canonical_doc"] in text
    for private in ("config.toml", "auth.json", "sessions/session.json"):
        assert git(ROOT, "check-ignore", ".codex/personal/" + private)


def test_git_pull_updates_adds_and_removes_skills_without_relinking(tmp_path: Path) -> None:
    """A fixed global and isolated directory link see the same Git update."""
    publisher = tmp_path / "publisher"
    publisher.mkdir()
    git(publisher, "init", "-b", "main")
    shutil.copyfile(ROOT / ".gitignore", publisher / ".gitignore")
    for skill in ("devcontainer-exec", "integration"):
        source = publisher / SKILLS / skill / "SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_bytes((ROOT / SKILLS / skill / "SKILL.md").read_bytes())
    git(publisher, "add", ".")
    git(publisher, "commit", "-m", "Initial distribution")
    home = tmp_path / "home"
    home.mkdir()
    git(home, "clone", "--no-hardlinks", str(publisher), "agent-canon")
    checkout = home / "agent-canon"
    installed = install_links(home, checkout)
    assert installed.returncode == 0, installed.stderr
    global_link = home / ".agents/skills"
    global_identity = global_link.lstat()
    manager = BootstrapRuntime(
        home, home / "runtime", repository_root=checkout,
        manifest_path=ROOT / "bootstrap/host/manifest.toml",
    )
    manager.codex_prepare()
    isolated_link = manager.paths.codex_home / "skills/agent-canon"
    isolated_identity = isolated_link.lstat()
    # The user config is not part of the distribution and survives source pulls.
    personal = checkout / ".codex/personal/config.toml"
    personal.write_text("# personal configuration\n")
    (publisher / SKILLS / "devcontainer-exec/SKILL.md").unlink()
    integration = publisher / SKILLS / "integration/SKILL.md"
    integration.write_text(integration.read_text() + "\nUpdated instructions.\n")
    added = publisher / SKILLS / "new-skill/SKILL.md"
    added.parent.mkdir()
    added.write_text("---\nname: new-skill\ndescription: Test addition\n---\nNew skill.\n")
    git(publisher, "add", "-A")
    git(publisher, "commit", "-m", "Change, add and remove skills")
    git(checkout, "pull", "--ff-only")
    # No bootstrap command or generator runs between pull and these readbacks.
    for link in (global_link, isolated_link):
        assert (link / "integration/SKILL.md").read_bytes() == integration.read_bytes()
        assert (link / "new-skill/SKILL.md").read_bytes() == added.read_bytes()
        assert not (link / "devcontainer-exec/SKILL.md").exists()
    assert personal.read_text() == "# personal configuration\n"
    repeated = install_links(home, checkout)
    assert repeated.returncode == 0, repeated.stderr
    manager.codex_prepare()
    for link, before in ((global_link, global_identity), (isolated_link, isolated_identity)):
        assert (link.lstat().st_ino, link.lstat().st_mtime_ns) == (
            before.st_ino, before.st_mtime_ns,
        )
    assert git(checkout, "status", "--porcelain") == ""
    assert not (manager.paths.container_runtime / "skill-projection").exists()


@pytest.mark.parametrize("dangling", [False, True])
def test_global_foreign_skill_link_is_preserved(tmp_path: Path, dangling: bool) -> None:
    """A different checkout is not silently deleted, followed, or retargeted."""
    home = tmp_path / "home"
    (home / ".agents").mkdir(parents=True)
    checkout = tmp_path / "checkout"
    (checkout / SKILLS).mkdir(parents=True)
    foreign = tmp_path / "foreign"
    if not dangling:
        foreign.mkdir()
    link = home / ".agents/skills"
    link.symlink_to(foreign, target_is_directory=True)
    before = link.lstat()
    result = install_links(home, checkout)
    assert result.returncode == 2
    assert "skill_link_collision" in result.stderr
    assert link.readlink() == foreign
    assert link.lstat().st_ino == before.st_ino


def test_missing_distribution_fails_without_creating_an_empty_view(tmp_path: Path) -> None:
    """Bootstrap cannot report success for an absent Git distribution."""
    home = tmp_path / "home"
    home.mkdir()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    result = install_links(home, checkout)
    assert result.returncode == 2
    assert "skill_source_missing" in result.stderr
    assert not (checkout / SKILLS).exists()
    assert not (home / ".agents/skills").is_symlink()
    manager = BootstrapRuntime(
        home, home / "runtime", repository_root=checkout,
        manifest_path=ROOT / "bootstrap/host/manifest.toml",
    )
    with pytest.raises(BootstrapError, match="skill_source_missing"):
        manager.codex_prepare()


def test_runtime_has_no_skill_writer_or_transfer() -> None:
    """Only the explicit source-authoring owner can write distribution bytes."""
    controller = (ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text()
    shell = ADAPTER.read_text()
    assert "skill_shim_materializer" not in controller
    assert "_materialize_skill_view" not in controller
    assert "_agent_canon_sync_personal_skill_view" not in shell
    assert "skill-projection" not in shell


def test_pull_migrates_ignored_adapters_without_removing_personal_config(tmp_path: Path) -> None:
    """Git replaces previously ignored adapters when the distribution is tracked."""
    publisher = tmp_path / "publisher"
    publisher.mkdir()
    git(publisher, "init", "-b", "main")
    (publisher / ".gitignore").write_text(".codex/personal/\n")
    git(publisher, "add", ".gitignore")
    git(publisher, "commit", "-m", "Ignored legacy distribution")
    home = tmp_path / "home"
    home.mkdir()
    git(home, "clone", str(publisher), "agent-canon")
    checkout = home / "agent-canon"
    old = checkout / SKILLS / "integration/SKILL.md"
    old.parent.mkdir(parents=True)
    old.write_text("old generated adapter\n")
    config = checkout / ".codex/personal/config.toml"
    config.write_text("# private settings\n")
    (home / ".agents").mkdir()
    link = home / ".agents/skills"
    link.symlink_to(checkout / SKILLS, target_is_directory=True)
    before = link.lstat()
    shutil.copyfile(ROOT / ".gitignore", publisher / ".gitignore")
    new = publisher / SKILLS / "integration/SKILL.md"
    new.parent.mkdir(parents=True)
    new.write_bytes((ROOT / SKILLS / "integration/SKILL.md").read_bytes())
    git(publisher, "add", ".")
    git(publisher, "commit", "-m", "Track distribution")
    git(checkout, "pull", "--ff-only")
    assert (link / "integration/SKILL.md").read_bytes() == new.read_bytes()
    assert config.read_text() == "# private settings\n"
    assert (link.lstat().st_ino, link.lstat().st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert git(checkout, "status", "--porcelain") == ""


def test_isolated_prepare_retires_only_previous_managed_file_links(tmp_path: Path) -> None:
    """The prior per-file manifest converges to the fixed public directory link."""
    import json

    home = tmp_path / "home"
    home.mkdir()
    checkout = tmp_path / "checkout"
    shutil.copytree(ROOT / SKILLS, checkout / SKILLS)
    manager = BootstrapRuntime(
        home, home / "runtime", repository_root=checkout,
        manifest_path=ROOT / "bootstrap/host/manifest.toml",
    )
    manager.codex_prepare()
    codex_home = manager.paths.codex_home
    directory_link = codex_home / "skills/agent-canon"
    directory_link.unlink()
    old_target = codex_home / "skills/integration/SKILL.md"
    old_target.parent.mkdir(parents=True)
    source = checkout / SKILLS / "integration/SKILL.md"
    old_target.symlink_to(source)
    foreign = codex_home / "skills/foreign/SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("user-owned skill\n")
    manifest = codex_home / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["links"] = [
        entry for entry in payload["links"] if entry["surface"] != "skills"
    ] + [{"target": str(old_target), "source": str(source), "managed": True}]
    manifest.write_text(json.dumps(payload))
    manager.codex_prepare()
    assert directory_link.resolve() == checkout / SKILLS
    assert not old_target.is_symlink()
    assert foreign.read_text() == "user-owned skill\n"
    assert (directory_link / "integration/SKILL.md").read_bytes() == source.read_bytes()
