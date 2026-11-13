"""Native policy retrieval keeps Git work in an opened temporary directory."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.agent_tools.test_agent_canon_log_policy import (
    deterministic_inventory_fixture,
)


def test_local_policy_fixture_never_invokes_git(tmp_path: Path) -> None:
    source = tmp_path / "inventory.json"
    source.write_bytes(deterministic_inventory_fixture())
    result = subprocess.run(
        [
            os.environ["AGENT_CANON_CLI"],
            "check-agent-canon-log-policy",
            "--input",
            str(source),
        ],
        env={**os.environ, "PATH": ""},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(
    os.name != "posix", reason="the existing parent authority uses Linux descriptors"
)
@pytest.mark.parametrize("replace", [False, True])
def test_policy_git_uses_opened_target_and_preserves_replacement(
    tmp_path: Path, replace: bool
) -> None:
    parent = tmp_path / "parent"
    subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
    fixture = tmp_path / "inventory.json"
    fixture.write_bytes(deterministic_inventory_fixture())
    binary = tmp_path / "bin"
    binary.mkdir()
    fake_git = binary / "git"
    fake_git.write_text(
        "#!/bin/sh\nset -eu\n"
        "target=$(pwd -P)\n"
        'case "$target" in */policy-inventory/policy-*) ;; *) exec "$REAL_GIT" "$@";; esac\n'
        'if [ "$1" = init ] && [ "$REPLACE" = yes ]; then\n'
        '  mv "$target" "$target-moved"\n'
        '  mkdir "$target"\n'
        '  printf preserve > "$target/marker"\n'
        "fi\n"
        'if [ "$1" = show ]; then cat "$POLICY_FIXTURE"; fi\n',
    )
    fake_git.chmod(0o755)
    result = subprocess.run(
        [
            os.environ["AGENT_CANON_CLI"],
            "check-agent-canon-log-policy",
            "--remote",
            "https://example.invalid/log.git",
            "--commit",
            "fixture",
        ],
        env={
            **os.environ,
            "PATH": f"{binary}:{os.environ['PATH']}",
            "REAL_GIT": shutil.which("git"),
            "AGENT_CANON_PARENT_ROOT": str(parent),
            "POLICY_FIXTURE": str(fixture),
            "REPLACE": "yes" if replace else "no",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    staging = parent / ".agent-canon/tmp/policy-inventory"
    if replace:
        assert result.returncode == 1, result.stdout + result.stderr
        assert "policy_inventory_target_identity_changed" in result.stdout
        assert [entry.read_text() for entry in staging.glob("*/marker")] == ["preserve"]
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert not list(staging.iterdir())
