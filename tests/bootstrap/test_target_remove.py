"""Target removal unit regressions; Docker/lifecycle I/O is modeled explicitly."""

# @dependency-start
# contract test
# responsibility Verifies target-removal phase ordering and ownership guards.
# upstream implementation ../../bootstrap/host/lifecycle/entrypoint.sh target lifecycle
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/bootstrap_runtime.rs native target command
# @dependency-end

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "bootstrap/host/lifecycle/entrypoint.sh"


@pytest.mark.parametrize(
    "arguments",
    [["--mode", "explicit-target-write"], ["--mutation-capability-json", "{}"]],
)
def test_native_target_owner_rejects_unsupported_write_mode(arguments: list[str]) -> None:
    source = (ROOT / "tools/runtime/dispatch/agent-canon/src/bootstrap_runtime.rs").read_text()
    target_contract = source.split("fn target_record(", 1)[1].split("fn task_process_lease_path(", 1)[0]
    assert 'mode != "read-only"' in target_contract
    assert "unsupported target mode" in target_contract


def test_git_metadata_failure_is_not_a_successful_empty_plan(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: /does-not-exist\n")
    manifest = tmp_path / "mounts.tsv"
    manifest.write_text("")
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; AGENT_CANON_REPOSITORY_ROOT=$2; _agent_canon_git_mounts "$3"',
            "test",
            str(ADAPTER),
            str(tmp_path),
            str(manifest),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "arguments", ["--mode explicit-target-write", "--mutation-capability-json {}"]
)
def test_target_rejects_unsupported_write_before_docker(
    tmp_path: Path, arguments: str
) -> None:
    """Unsupported public write arguments cannot be silently admitted as read-only."""
    script = (
        r"""
source "$1"
_agent_canon_validate_roots() { :; }
_agent_canon_prepare_host_runtime() { :; }
docker_fixture() { printf 'unexpected Docker call\n' >&2; return 91; }
AGENT_CANON_DOCKER=docker_fixture
bootstrap_host_entrypoint "$2" --control-parent-root "$2" target add --root "$2" """
        + arguments
    )
    result = subprocess.run(
        ["bash", "-c", script, "test", str(ADAPTER), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unexpected Docker call" not in result.stderr
    assert '"status":"ok"' not in result.stdout


def test_linked_targets_share_native_read_only_git_mount(tmp_path: Path) -> None:
    """Two worktrees need one common Git bind, preserving their native HEAD files."""
    repository = tmp_path / "source"
    repository.mkdir()
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "seed",
        ],
        check=True,
        capture_output=True,
    )
    first, second = tmp_path / "first", tmp_path / "second"
    for path in (first, second):
        subprocess.run(
            ["git", "-C", str(repository), "worktree", "add", "--detach", str(path)],
            check=True,
            capture_output=True,
        )
    manifest = tmp_path / "mounts.tsv"
    manifest.write_text(
        f"target\tfirst\t{first}\t/targets/first\tread-only\n", encoding="utf-8"
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; AGENT_CANON_REPOSITORY_ROOT=$2; AGENT_CANON_TARGET_PENDING_SOURCE=$3; _agent_canon_git_mounts "$4"',
            "test",
            str(ADAPTER),
            str(repository),
            str(second),
            str(manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    common = repository / ".git"
    assert result.stdout == f"{common}\t{common}\tfalse\n"


def test_rollback_metadata_allows_retired_checkout(tmp_path: Path) -> None:
    """Reading a GC plan needs identities, not a still-existing checkout mount."""
    missing = tmp_path / "deleted"
    plan = tmp_path / "rollback-plan.tsv"
    plan.write_text(
        "schema\tagent-canon.rollback-plan.v1\nimage-id\t"
        + "sha256:"
        + "a" * 64
        + "\nimage-ref\tagent-canon-tools:rollback\n"
        + f"mount\tmount\t{missing}\t/targets/old\ttrue\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; AGENT_CANON_STATE_ROOT=$2; _agent_canon_read_rollback_plan "$3"',
            "test",
            str(ADAPTER),
            str(tmp_path),
            str(tmp_path / "projection.tsv"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not missing.exists()
    assert (
        tmp_path / "projection.tsv"
    ).read_text() == f"target\told\t{missing}\t/targets/old\tread-only\n"


@pytest.mark.parametrize("failure", ["", "stop", "rm", "ensure", "start", "validate"])
def test_remove_recreates_before_final_readback(tmp_path: Path, failure: str) -> None:
    """Exercise the real host dispatch with modeled Docker/controller boundaries."""
    state = tmp_path / "state"
    state.mkdir()
    removed = tmp_path / "removed"
    retained = tmp_path / "retained"
    removed.mkdir()
    retained.mkdir()
    digest = hashlib.sha256(str(removed).encode()).hexdigest()
    keep = f"target\tkeep\t{retained}\t/targets/keep\tread-only\n"
    manifest = f"target\t{digest}\t{removed}\t/targets/{digest}\tread-only\n" + keep
    (state / "mounts.tsv").write_text(manifest, encoding="utf-8")
    (tmp_path / "observed").write_text(manifest, encoding="utf-8")
    script = r"""
source "$1"
fixture=$2
failure=$3
record() { printf '%s\n' "$1" >> "$fixture/events"; }
phase() {
  record "$1"
  [[ ! -f "$fixture/committed" || "$failure" != "$1" ]] || return 17
}
docker_fixture() {
  case "$1" in
    container) return 0 ;;
    stop|rm) phase "$1" ;;
    *) return 99 ;;
  esac
}
AGENT_CANON_DOCKER=docker_fixture
_agent_canon_validate_roots() { AGENT_CANON_RUNTIME_ROOT="$fixture/.runtime"; }
_agent_canon_select_existing_runtime() { :; }
_agent_canon_prepare_host_runtime() {
  AGENT_CANON_STATE_ROOT="$fixture/state"
  mkdir -p "$AGENT_CANON_RUNTIME_ROOT/host-state"
}
_agent_canon_container_name() { printf 'resident\n'; }
_agent_canon_classify_existing_container() { record classify; }
_agent_canon_use_active_image() {
  AGENT_CANON_IMAGE_REF=shared
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:shared
}
_agent_canon_ensure_container() {
  phase ensure || return $?
  cp "$fixture/state/mounts.tsv" "$fixture/observed"
  printf 'resident\n'
}
_agent_canon_run_controller() {
  if [[ "$2" == target ]]; then
    record target_remove
    awk -F '\t' -v digest="$AGENT_CANON_TARGET_DIGEST" \
      '$2 != digest' "$fixture/state/mounts.tsv" > "$fixture/projection"
    touch "$fixture/committed"
  else
    phase start
  fi
}
_agent_canon_publish_controller_projection() {
  record publish
  cp "$fixture/projection" "$fixture/state/mounts.tsv"
}
_agent_canon_validate_existing_container() {
  phase validate || return $?
  diff -u "$fixture/state/mounts.tsv" "$fixture/observed" >&2 || return 2
}
_agent_canon_restore_candidate_failure() { record restore; }
bootstrap_host_entrypoint "$fixture" --control-parent-root "$fixture" \
  target remove --root "$fixture/removed" --mode read-only
"""
    result = subprocess.run(
        ["bash", "-c", script, "test", str(ADAPTER), str(tmp_path), failure],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    events = (tmp_path / "events").read_text(encoding="utf-8").splitlines()
    transition = events[events.index("target_remove") :]
    phases = ["target_remove", "publish", "stop", "rm", "ensure", "start", "validate"]
    assert (state / "mounts.tsv").read_text(encoding="utf-8") == keep
    if failure:
        assert result.returncode == 17, result.stderr
        assert transition == phases[: phases.index(failure) + 1] + ["restore"]
    else:
        assert result.returncode == 0, result.stderr
        assert transition == phases
        assert (tmp_path / "observed").read_text(encoding="utf-8") == keep


def test_remove_rejects_foreign_resident_before_teardown(tmp_path: Path) -> None:
    """Remove must invoke the ownership gate even with retained active-image state."""
    target = tmp_path / "target"
    target.mkdir()
    script = r"""
source "$1"
fixture=$2
docker_fixture() {
  [[ "$1" == container ]] && return 0
  printf '%s\n' "$1" >> "$fixture/mutations"
}
AGENT_CANON_DOCKER=docker_fixture
_agent_canon_validate_roots() { AGENT_CANON_RUNTIME_ROOT="$fixture/.runtime"; }
_agent_canon_prepare_host_runtime() {
  AGENT_CANON_STATE_ROOT="$fixture"
  mkdir -p "$AGENT_CANON_RUNTIME_ROOT/host-state"
}
_agent_canon_classify_existing_container() {
  _agent_canon_json_error container_ownership_mismatch "foreign resident"
}
_agent_canon_target_digest() { :; }
_agent_canon_use_active_image() {
  AGENT_CANON_IMAGE_REF=retained-image
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:retained
}
_agent_canon_validate_existing_container() { return 2; }
_agent_canon_ensure_container() { return 19; }
_agent_canon_restore_candidate_failure() { :; }
bootstrap_host_entrypoint "$fixture" --control-parent-root "$fixture" \
  target remove --root "$fixture/target" --mode read-only
"""
    result = subprocess.run(
        ["bash", "-c", script, "test", str(ADAPTER), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stderr
    assert "container_ownership_mismatch" in result.stderr
    assert not (tmp_path / "mutations").exists()
