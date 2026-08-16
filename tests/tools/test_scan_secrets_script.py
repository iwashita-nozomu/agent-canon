# @dependency-start
# contract test
# responsibility Verifies secret-scan temporary state stays in the selected repository.
# upstream implementation ../../tools/ci/scan_secrets.sh owns scanner orchestration and cleanup.
# @dependency-end

"""Focused tests for the secret scanner shell entrypoint."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import shutil
import subprocess
from pathlib import Path

from tools.agent_tools.fixture_spawn import (
    bootstrap_fixture_public_environment,
    record_capability_from_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "scan_secrets.sh"
def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


def _pending_handoff_nonces(root: Path) -> dict[str, object]:
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@contextmanager
def fixture_session(
    parent: Path,
    invocation: Path,
    explicit_path_entries: tuple[Path, ...] = (),
):
    """Issue an authenticated session rooted at the selected scanner fixture."""
    with bootstrap_fixture_public_environment(
        mode="synthetic_tool",
        record_capability=record_capability_from_environment(),
        fixture_cwd=parent,
        base_env=os.environ.copy(),
        invocation_script=invocation,
        purpose="scan-secrets-test",
        explicit_path_entries=tuple(str(path) for path in explicit_path_entries),
    ) as fixture:
        yield dict(fixture.environment)


def test_scan_uses_parent_local_temp_and_preserves_existing_entries(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    _git("init", "-q", "-b", "main", cwd=parent)
    (parent / ".gitignore").write_text(".agent-canon/\n", encoding="utf-8")
    _git("add", ".", cwd=parent)
    _git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "parent fixture",
        cwd=parent,
    )

    (parent / "tools" / "ci").mkdir(parents=True)
    (parent / "tools" / "agent_tools").mkdir(parents=True)
    invocation = parent / "tools" / "ci" / SCRIPT.name
    shutil.copy2(SCRIPT, invocation)
    shutil.copy2(
        PROJECT_ROOT / "tools" / "agent_tools" / "parent_root_side_effects.py",
        parent / "tools" / "agent_tools" / "parent_root_side_effects.py",
    )

    scan_source = parent / "scan-source"
    scan_source.mkdir()
    _git("init", "-q", "-b", "main", cwd=scan_source)
    (scan_source / "tracked.txt").write_text("safe\n", encoding="utf-8")
    _git("add", ".", cwd=scan_source)
    _git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "scan fixture",
        cwd=scan_source,
    )

    preexisting = parent / ".agent-canon" / "tmp" / "preexisting.txt"
    preexisting.parent.mkdir(parents=True)
    preexisting.write_text("keep\n", encoding="utf-8")
    fake_bin = parent / ".fixture-bin"
    fake_bin.mkdir()
    scan_log = parent / ".agent-canon" / "scanner-child.log"
    _write_executable(
        fake_bin / "gitleaks",
        '#!/bin/sh\nprintf "gitleaks %s tmp=%s cargo=%s\\n" "$*" "$TMPDIR" "$CARGO_HOME" >> "$SCAN_LOG"\n',
    )
    _write_executable(
        fake_bin / "trufflehog",
        '#!/bin/sh\nprintf "trufflehog %s tmp=%s cargo=%s\\n" "$*" "$TMPDIR" "$CARGO_HOME" >> "$SCAN_LOG"\n',
    )
    _write_executable(
        fake_bin / "detect-secrets",
        '#!/bin/sh\nprintf "detect-secrets %s tmp=%s cargo=%s\\n" "$*" "$TMPDIR" "$CARGO_HOME" >> "$SCAN_LOG"\nprintf \'{"results": {}}\\n\'\n',
    )
    with fixture_session(parent, invocation, (fake_bin,)) as env:
        env["SCAN_LOG"] = str(scan_log)
        for name, relative in (
            ("TMPDIR", Path(".agent-canon") / "tmp"),
            ("TEMP", Path(".agent-canon") / "tmp"),
            ("TMP", Path(".agent-canon") / "tmp"),
            ("CARGO_HOME", Path(".agent-canon") / "cache" / "cargo-home"),
        ):
            value = parent / relative
            value.mkdir(parents=True, exist_ok=True)
            env[name] = str(value)
        result = subprocess.run(
            ("bash", str(invocation), "--root", str(scan_source), "--current-only"),
            cwd=parent,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SECRET_SCAN=pass" in result.stdout
    assert preexisting.read_text(encoding="utf-8") == "keep\n"
    temp_entries = list((parent / ".agent-canon" / "tmp").iterdir())
    assert temp_entries == [preexisting]
    assert not (scan_source / ".agent-canon").exists()
    assert _pending_handoff_nonces(parent) == {}
    for line in scan_log.read_text(encoding="utf-8").splitlines():
        assert f"tmp={parent / '.agent-canon' / 'tmp'}" in line
        assert f"cargo={parent / '.agent-canon' / 'cache' / 'cargo-home'}" in line
        if "/.agent-canon/tmp/" in line:
            assert str(parent / ".agent-canon" / "tmp") in line


def test_scan_script_has_no_host_temp_or_raw_recursive_cleanup() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "mktemp" not in source
    assert "RUNNER_TEMP" not in source
    assert "rm -rf" not in source
    assert "rm -f" not in source
