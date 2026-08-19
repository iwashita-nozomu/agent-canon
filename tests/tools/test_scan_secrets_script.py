# @dependency-start
# contract test
# responsibility Verifies secret-scan temporary state stays in the selected repository.
# upstream implementation ../../tools/ci/scan_secrets.sh owns scanner orchestration and cleanup.
# @dependency-end

"""Focused tests for the secret scanner shell entrypoint."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "scan_secrets.sh"
PATH_ENV_KEYS = {
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
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

    scan_source = tmp_path / "scan-source"
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
    fake_bin = tmp_path / "bin"
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
    env = {key: value for key, value in os.environ.items() if key not in PATH_ENV_KEYS}
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["SCAN_LOG"] = str(scan_log)
    env["AGENT_CANON_PARENT_ROOT"] = str(parent)

    result = subprocess.run(
        ("bash", str(SCRIPT), "--root", str(scan_source), "--current-only"),
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
