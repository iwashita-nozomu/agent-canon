"""Safety boundaries shared by the bootstrap test modules."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterator

import pytest


def materialize_source_fixture(tmp_path: Path) -> Path:
    """Build a writable source view while leaving the checkout source untouched.

    Lifecycle tests intentionally exercise source-adjacent ``.runtime`` and
    managed Codex surfaces.  A view with symlinked source directories would
    still route those writes into the checkout, so ``.codex`` is copied while
    immutable source directories remain linked for speed.  The fixture root
    itself is test-owned and its ``.runtime`` is always newly created by the
    lifecycle owner.
    """
    source = tmp_path / "agent-canon-source"
    if source.exists():
        return source
    repository = Path(__file__).resolve().parents[2]
    source.mkdir()
    for entry in repository.iterdir():
        if entry.name == ".runtime":
            continue
        destination = source / entry.name
        if entry.name == ".codex":
            shutil.copytree(entry, destination, symlinks=True)
        elif entry.is_dir():
            destination.symlink_to(entry, target_is_directory=True)
        else:
            destination.symlink_to(entry)
    return source


@pytest.fixture(autouse=True)
def bootstrap_test_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Keep scheduler files and lifecycle control inside the current test."""
    xdg_config = tmp_path / "xdg-config"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "case \"$0\" in\n"
        "  \"$AGENT_CANON_TEST_ROOT\"/*) ;;\n"
        "  *) exit 125 ;;\n"
        "esac\n"
        "case \"${XDG_CONFIG_HOME:-}\" in\n"
        "  \"$AGENT_CANON_TEST_ROOT\"/*) ;;\n"
        "  *) exit 126 ;;\n"
        "esac\n"
        "printf 'binary\\t%s\\n' \"$0\" >> \"$AGENT_CANON_TEST_SYSTEMCTL_LOG\"\n"
        "printf 'xdg\\t%s\\n' \"$XDG_CONFIG_HOME\" >> \"$AGENT_CANON_TEST_SYSTEMCTL_LOG\"\n"
        "printf 'argv\\t%s\\n' \"$*\" >> \"$AGENT_CANON_TEST_SYSTEMCTL_LOG\"\n"
        "case \"$*\" in\n"
        "  \"--user show-environment\") ;;\n"
        "  \"--user daemon-reload\") ;;\n"
        "  \"--user enable --now agent-canon-sync.timer\") ;;\n"
        "  \"--user disable --now agent-canon-sync.timer\") ;;\n"
        "  \"--user show agent-canon-sync.timer --property=ActiveState,UnitFileState\")\n"
        "    printf '%s\\n' 'ActiveState=inactive' 'UnitFileState=disabled'\n"
        "    ;;\n"
        "  *) exit 127 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("AGENT_CANON_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENT_CANON_TEST_SYSTEMCTL_LOG", str(systemctl_log))
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    yield

    if not systemctl_log.exists():
        return
    records = [
        line.split("\t", 1)
        for line in systemctl_log.read_text(encoding="utf-8").splitlines()
    ]
    assert records
    allowed = {
        "--user show-environment",
        "--user daemon-reload",
        "--user enable --now agent-canon-sync.timer",
        "--user disable --now agent-canon-sync.timer",
        "--user show agent-canon-sync.timer --property=ActiveState,UnitFileState",
    }
    for key, value in records:
        if key == "binary":
            assert Path(value).resolve() == fake_systemctl.resolve()
        elif key == "xdg":
            assert Path(value).resolve().is_relative_to(tmp_path.resolve())
        elif key == "argv":
            assert value in allowed
        else:
            pytest.fail(f"unexpected fake systemctl record: {key!r}")
