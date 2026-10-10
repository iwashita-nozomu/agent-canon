"""Regression cases for automatic delivery and acknowledged spool cleanup."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "bootstrap/host/lifecycle/entrypoint.sh"


def run_adapter(tmp_path: Path, script: str) -> subprocess.CompletedProcess[str]:
    """Use the real shell owner with only external operations substituted."""
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", "-c", f"source {shlex.quote(str(ADAPTER))}\n{script}"],
        env={
            **os.environ,
            "AGENT_CANON_STATE_ROOT": str(state),
            "AGENT_CANON_RUNTIME_ROOT": str(tmp_path),
            "AGENT_CANON_REPOSITORY_ROOT": str(tmp_path),
            "TEST_CALLS": str(tmp_path / "calls"),
        },
        check=False,
        capture_output=True,
        text=True,
    )


def test_resident_request_is_exported_before_host_request_lookup(
    tmp_path: Path,
) -> None:
    """A request that only exists in the volume still reaches the publisher."""
    result = run_adapter(
        tmp_path,
        r"""
_agent_canon_volume_copy() {
  printf '%s\n' "$1 $2" >> "$TEST_CALLS"
  mkdir -p "$3"
  printf 'invalid-request\n' > "$3/sync-request.json"
}
_agent_canon_private_feedback_sync resident
""",
    )
    calls = tmp_path / "calls"
    assert calls.exists(), "resident spool was never exported"
    assert calls.read_text().splitlines() == ["export private-feedback"]
    assert result.returncode == 2
    assert "private_feedback_sync_request_invalid" in result.stderr


@pytest.mark.parametrize("fetch_status", [0, 1])
def test_source_sync_attempts_pending_delivery_independently(
    tmp_path: Path, fetch_status: int
) -> None:
    """Unchanged source and failed source fetch both attempt pending delivery."""
    archive_owner = tmp_path / "tools/runtime/archive/runtime_log_archive_git.py"
    archive_owner.parent.mkdir(parents=True)
    archive_owner.write_text("# fixture archive owner entrypoint\n", encoding="utf-8")
    result = run_adapter(
        tmp_path,
        r"""
command_args=(sync --install-root "$AGENT_CANON_REPOSITORY_ROOT")
_agent_canon_source_sync_write() { :; }
_agent_canon_image_reference() { AGENT_CANON_IMAGE_REF=fixture; }
_agent_canon_image() { AGENT_CANON_IMAGE_REF=fixture; }
_agent_canon_replace_resident_locked() { :; }
_agent_canon_scheduler_locked() { :; }
_agent_canon_use_active_image() { :; }
_agent_canon_container_name() { printf 'fixture-container'; }
_agent_canon_ensure_container() { printf 'fixture-container'; }
_agent_canon_init_state_volume() { :; }
_agent_canon_volume_copy() {
  case "$1:$2" in
    list:eval) printf 'run-1\n' ;;
    export:eval) printf 'eval-export %s\n' "$4" >> "$TEST_CALLS" ;;
    *) return 99 ;;
  esac
}
_agent_canon_archive_eval_sync() {
  printf 'eval-sync %s\n' "$1" >> "$TEST_CALLS"
}
_agent_canon_private_feedback_sync() {
  printf 'feedback-sync\n' >> "$TEST_CALLS"
}
python3() {
  printf 'hook-sync\n' >> "$TEST_CALLS"
}
fixture_docker() { printf 'sha256:fixture\n'; }
AGENT_CANON_DOCKER_CMD=fixture_docker
git() {
  case "$3" in
    fetch) return FETCH_STATUS ;;
    rev-parse) printf '1111111111111111111111111111111111111111\n' ;;
    checkout) return 0 ;;
    *) return 99 ;;
  esac
}
_agent_canon_sync_operation
""".replace("FETCH_STATUS", str(fetch_status)),
    )
    calls = tmp_path / "calls"
    assert calls.exists(), "source synchronization never attempted archive delivery"
    assert calls.read_text().splitlines() == [
        "hook-sync",
        "eval-export run-1",
        "eval-sync run-1",
        "feedback-sync",
    ]
    assert result.returncode == (0 if fetch_status == 0 else 2), result.stderr
