# @dependency-start
# contract test
# responsibility Verifies submodule authentication is process-local and parent-bounded.
# upstream implementation ../../.github/scripts/checkout_agent_canon_submodule.sh owns CI submodule checkout authentication.
# @dependency-end

"""Focused tests for AgentCanon submodule checkout authentication."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / ".github" / "scripts" / "checkout_agent_canon_submodule.sh"
BOUNDARY = PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py"
PARENT_PATH_ENV_KEYS = {
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "PYTHONPYCACHEPREFIX",
    "TEMP",
    "TMP",
    "TMPDIR",
    "XDG_CACHE_HOME",
}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


def _commit(repo: Path, message: str) -> None:
    _git("add", ".", cwd=repo)
    _git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        message,
        cwd=repo,
    )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    parent = tmp_path / "parent"
    submodule = parent / "vendor" / "agent-canon"
    submodule.mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=parent)
    _git("init", "-q", "-b", "main", cwd=submodule)
    boundary_target = submodule / "tools" / "agent_tools" / BOUNDARY.name
    boundary_target.parent.mkdir(parents=True)
    shutil.copy2(BOUNDARY, boundary_target)
    (submodule / "README.md").write_text("fixture\n", encoding="utf-8")
    _commit(submodule, "submodule fixture")
    (parent / ".gitmodules").write_text(
        '[submodule "vendor/agent-canon"]\n'
        "\tpath = vendor/agent-canon\n"
        "\turl = https://github.com/example/agent-canon.git\n",
        encoding="utf-8",
    )
    (parent / ".gitignore").write_text(".agent-canon/\n", encoding="utf-8")
    _commit(parent, "parent fixture")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    git_log = tmp_path / "git.log"
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$GIT_LOG"\n'
        'case " $* " in\n'
        '  *" ls-remote "*)\n'
        '    case " $* " in *"insteadOf="*) exit 0 ;; esac\n'
        '    exit 1\n'
        '    ;;\n'
        '  *" submodule sync "*|*" submodule update "*) exit 0 ;;\n'
        "esac\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    ssh_keyscan = fake_bin / "ssh-keyscan"
    ssh_keyscan.write_text('#!/bin/sh\nprintf "github.com ssh-ed25519 fixture\\n"\n', encoding="utf-8")
    ssh_keyscan.chmod(0o755)
    return parent, fake_bin, git_log


def test_checkout_uses_process_local_git_config_and_cleans_ssh_material(tmp_path: Path) -> None:
    parent, fake_bin, git_log = _fixture(tmp_path)
    preserved = parent / ".agent-canon" / "tmp" / "preexisting.txt"
    preserved.parent.mkdir(parents=True)
    preserved.write_text("keep\n", encoding="utf-8")
    env = {
        key: value for key, value in os.environ.items() if key not in PARENT_PATH_ENV_KEYS
    }
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["GIT_LOG"] = str(git_log)
    env["AGENT_CANON_REPO_SSH_KEY"] = "fixture-private-key"
    env.pop("AGENT_CANON_REPO_TOKEN", None)

    result = subprocess.run(
        ("bash", str(SCRIPT)),
        cwd=parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AGENT_CANON_SUBMODULE=ready" in result.stdout
    assert preserved.read_text(encoding="utf-8") == "keep\n"
    assert list((parent / ".agent-canon" / "tmp").iterdir()) == [preserved]
    commands = git_log.read_text(encoding="utf-8")
    assert "--global" not in commands
    assert f"safe.directory={parent}" in commands
    assert f"safe.directory={parent / 'vendor' / 'agent-canon'}" in commands


def test_checkout_script_has_no_global_config_or_host_temp_cleanup() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "git config --global" not in source
    assert "RUNNER_TEMP" not in source
    assert "mktemp" not in source
    assert "rm -rf" not in source
