"""Target removal unit regressions; Docker/lifecycle I/O is modeled explicitly."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tools.runtime.container import bootstrap_runtime as runtime_module

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "bootstrap/host/lifecycle/entrypoint.sh"


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
    script = r'''
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
_agent_canon_validate_roots() { :; }
_agent_canon_prepare_host_runtime() { AGENT_CANON_STATE_ROOT="$fixture/state"; }
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
'''
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
    script = r'''
source "$1"
fixture=$2
docker_fixture() {
  [[ "$1" == container ]] && return 0
  printf '%s\n' "$1" >> "$fixture/mutations"
}
AGENT_CANON_DOCKER=docker_fixture
_agent_canon_validate_roots() { :; }
_agent_canon_prepare_host_runtime() { AGENT_CANON_STATE_ROOT="$fixture"; }
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
'''
    result = subprocess.run(
        ["bash", "-c", script, "test", str(ADAPTER), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, result.stderr
    assert "container_ownership_mismatch" in result.stderr
    assert not (tmp_path / "mutations").exists()


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("mounted", [False, True])
def test_remove_checks_registration_before_mount_existence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registered: bool, mounted: bool
) -> None:
    """Unknown digests use state; registered digests retain mount validation."""
    control = tmp_path / "control"
    private_log = control / "private-log"
    private_log.mkdir(parents=True)
    monkeypatch.setenv("AGENT_CANON_CONTAINER_CONTROL", "1")
    monkeypatch.setattr(runtime_module, "PRIVATE_LOG_DESTINATION", str(private_log))
    manager = runtime_module.BootstrapRuntime(
        control, control / "runtime", repository_root=ROOT
    )
    manager._ensure_layout()
    state = manager._new_state()
    state["state"] = "ready"
    state["current_generation"] = "generation-0"
    state["resources"]["image"] = {
        "id": "sha256:" + "a" * 64,
        "tag": "agent-canon-tools:fixture",
    }
    state["targets"]["keep"] = {
        "root": "/targets/keep",
        "host_root": str(tmp_path / "keep"),
        "mode": "read-only",
        "digest": "keep",
    }
    digest = "missing-target"
    host_root = str(tmp_path / "host-source")
    container_root = f"/targets/{digest}"
    if registered:
        state["targets"][digest] = {
            "root": container_root,
            "host_root": host_root,
            "mode": "read-only",
            "digest": digest,
        }
    manager._write_state(state)
    before = manager.paths.state.read_bytes()
    monkeypatch.setattr(runtime_module, "_runtime_from_args", lambda _args: manager)
    monkeypatch.setenv("AGENT_CANON_TARGET_HOST_ROOT", host_root)
    monkeypatch.setenv("AGENT_CANON_TARGET_CONTAINER_ROOT", container_root)
    monkeypatch.setenv("AGENT_CANON_TARGET_DIGEST", digest)
    original = runtime_module._existing_no_symlink
    mount_checks: list[Path] = []

    def missing_mount(path: Path, *, field: str) -> Path:
        if str(path) == container_root:
            mount_checks.append(path)
            if mounted:
                return path
            raise runtime_module.BootstrapError("path_missing", "fixture mount absent")
        return original(path, field=field)

    monkeypatch.setattr(runtime_module, "_existing_no_symlink", missing_mount)
    args = runtime_module.build_parser().parse_args(
        [
            "--container-control",
            "--repository-root",
            str(ROOT),
            "--control-parent-root",
            str(control),
            "target",
            "remove",
            "--root",
            container_root,
        ]
    )
    if registered and mounted:
        result = runtime_module._container_control_run(args)
        assert result["code"] == "target_removed"
        after = manager._read_state()
        assert set(after["targets"]) == {"keep"}
        previous = after["generations"][after["rollback_generation"]]
        assert set(previous["targets"]) == {"keep", digest}
        assert digest not in (manager.paths.container_runtime / "mounts.tsv").read_text(
            encoding="utf-8"
        )
    else:
        expected = "path_missing" if registered else "target_not_registered"
        with pytest.raises(runtime_module.BootstrapError) as error:
            runtime_module._container_control_run(args)
        assert error.value.code == expected
        assert manager.paths.state.read_bytes() == before
    assert mount_checks == ([Path(container_root)] if registered else [])
