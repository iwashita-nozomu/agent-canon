"""Checks for the host-only bootstrap adapter boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "bootstrap.sh"
ADAPTER = ROOT / "bootstrap" / "host" / "lifecycle" / "entrypoint.sh"
GPU006_FIXTURE = ROOT / "tests" / "fixtures" / "bootstrap" / "gpu006_stale_source_sync_resident.json"


def test_host_entrypoint_has_no_python_fallback() -> None:
    """A minimal host can reach Docker without importing AgentCanon Python."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "bootstrap_python_entrypoint" not in text
    assert "exec python3" not in text
    assert '"$AGENT_CANON_DOCKER_CMD" exec' in text
    assert "AGENT_CANON_CONTAINER_CONTROL" in text
    assert "docker.sock" not in text
    assert "AGENT_CANON_CONTAINER_NETWORK" in text
    assert "docker-rpc" not in text
    controller = (ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "AGENT_CANON_DOCKER_RPC" not in controller


def test_update_transaction_has_candidate_restore_path() -> None:
    """Host update retains the previous image until candidate finalization."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "old_image_id" in text
    assert "candidate_image_id" in text
    assert "_agent_canon_restore_candidate_failure" in text
    assert "AGENT_CANON_RESTORE_IMAGE_ID" in text
    assert 'image rm "$candidate_image_id"' in text
    assert "previous-image-id" in text
    assert "rollback-plan.tsv" in text
    assert "AGENT_CANON_ROLLBACK_IMAGE_ID" in text
    assert "image inspect" in text
    assert "container inspect" in text


def test_update_replacement_uses_one_host_owned_lock_without_bypass() -> None:
    """The host teardown-to-publication window has one non-bypassable lock."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "replacement.lock" in text
    assert "_agent_canon_replace_resident" in text
    assert 'flock -x "$lock_fd"' in text
    assert 'flock -u "$lock_fd"' in text
    assert "AGENT_CANON_LOCK_HELD" not in text
    assert "AGENT_CANON_LOCK_TOKEN" not in text
    assert "AGENT_CANON_LOCK_PID" not in text


def _run_forced_update_probe(
    tmp_path: Path,
    *,
    build_result: str,
    tag_result: str = "0",
    existing_plan: str = "",
    force_build: str | None = "1",
) -> tuple[subprocess.CompletedProcess[str], Path, Path, str, str]:
    """Exercise the forced-update ordering with a Docker-only fake."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    (runtime / "host-state").mkdir(parents=True)
    state_root.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    private_log = tmp_path / "agent-canon-log"
    private_log.mkdir()
    (state_root / "mounts.tsv").write_text("", encoding="utf-8")
    (state_root / "mounts.toml").write_text("", encoding="utf-8")
    (runtime / "source-sync.json").write_text("{}\n", encoding="utf-8")
    old_ref = "agent-canon-tools:active"
    old_id = "sha256:" + "0" * 64
    (runtime / "host-state" / "active-image.tsv").write_text(
        f"schema\tagent-canon.active-image.v1\nimage-ref\t{old_ref}\nimage-id\t{old_id}\n",
        encoding="utf-8",
    )
    if existing_plan:
        (state_root / "rollback-plan.tsv").write_text(existing_plan, encoding="utf-8")
    marker = tmp_path / "retained"
    calls = tmp_path / "docker.calls"
    replaced = tmp_path / "replaced"
    candidate_id = "sha256:" + "1" * 64
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(calls)!r}\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then\n"
        "  ref=\"${@: -1}\"\n"
        "  if [[ \"$ref\" == *rollback-* ]]; then\n"
        f"    [[ -f {str(marker)!r} ]] || exit 1\n    printf '%s\\n' {old_id!r}\n"
        "  else\n"
        f"    printf '%s\\n' {candidate_id!r}\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == tag ]]; then\n"
        f"  touch {str(marker)!r}\n  exit {tag_result}\n"
        "fi\n"
        "if [[ \"$1\" == build ]]; then\n"
        f"  [[ -f {str(marker)!r} ]] || exit 91\n"
        f"  exit {build_result}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}
AGENT_CANON_CONTROL_ROOT={str(control)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
AGENT_CANON_PRIVATE_LOG_ROOT={str(private_log)!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
AGENT_CANON_ALLOW_BUILD=1
{f'AGENT_CANON_FORCE_BUILD={force_build}' if force_build is not None else ''}
export AGENT_CANON_REPOSITORY_ROOT AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT
export AGENT_CANON_STATE_ROOT AGENT_CANON_PRIVATE_LOG_ROOT
export AGENT_CANON_DOCKER_CMD AGENT_CANON_ALLOW_BUILD
{f'export AGENT_CANON_FORCE_BUILD' if force_build is not None else ''}
_agent_canon_replace_resident_locked() {{
  printf '%s\\n' replaced > {str(replaced)!r}
  _agent_canon_commit_pending_rollback_plan
}}
_agent_canon_update_locked '' ignored
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    return completed, calls, marker, old_id, candidate_id


def test_same_source_update_reuses_exact_image_without_build(tmp_path: Path) -> None:
    """A same-source update reuses its exact image reference by default."""
    completed, calls, _marker, _old_id, _candidate_id = _run_forced_update_probe(
        tmp_path, build_result="0", force_build=None
    )
    assert completed.returncode == 0, completed.stderr
    operations = calls.read_text(encoding="utf-8").splitlines()
    assert any(operation.startswith("image inspect ") for operation in operations)
    assert not any(operation.startswith("build ") for operation in operations)


def test_explicit_force_build_rebuilds_same_source_image(tmp_path: Path) -> None:
    """An explicit FORCE_BUILD request still enters the candidate build path."""
    completed, calls, _marker, _old_id, _candidate_id = _run_forced_update_probe(
        tmp_path, build_result="0", force_build="1"
    )
    assert completed.returncode == 0, completed.stderr
    assert sum(
        operation.startswith("build ")
        for operation in calls.read_text(encoding="utf-8").splitlines()
    ) == 1


def test_forced_update_retains_same_reference_before_build(tmp_path: Path) -> None:
    """The active immutable ID is tagged before a same-reference build."""
    completed, calls, marker, old_id, _candidate_id = _run_forced_update_probe(
        tmp_path, build_result="0"
    )
    assert completed.returncode == 0, completed.stderr
    operations = calls.read_text(encoding="utf-8").splitlines()
    assert next(index for index, operation in enumerate(operations) if operation.startswith("tag " + old_id)) < operations.index(next(
        operation for operation in operations if operation.startswith("build ")
    ))
    assert marker.is_file()
    assert (tmp_path / "runtime" / "container-state" / "rollback-plan.tsv").is_file()
    assert "rollback_plan_invalid" not in completed.stderr


def test_forced_build_failure_preserves_previous_plan_and_active_image(
    tmp_path: Path,
) -> None:
    """A candidate build failure leaves the old resident metadata untouched."""
    previous_plan = "schema\tagent-canon.rollback-plan.v1\nimage-id\tsha256:previous\n"
    completed, calls, _marker, old_id, _candidate_id = _run_forced_update_probe(
        tmp_path, build_result="91", existing_plan=previous_plan
    )
    assert completed.returncode == 2
    assert '"code":"candidate_image_build_failed"' in completed.stderr
    assert not (tmp_path / "replaced").exists()
    assert (tmp_path / "runtime" / "host-state" / "active-image.tsv").read_text(
        encoding="utf-8"
    ).endswith(f"image-id\t{old_id}\n")
    assert (tmp_path / "runtime" / "container-state" / "rollback-plan.tsv").read_text(
        encoding="utf-8"
    ) == previous_plan
    assert not (tmp_path / "runtime" / "container-state" / ".pending-rollback-plan.tsv").exists()
    assert any(operation.startswith("build ") for operation in calls.read_text(encoding="utf-8").splitlines())


def test_forced_retention_failure_stops_before_build(tmp_path: Path) -> None:
    """A failed retention tag is terminal and cannot enter candidate build."""
    completed, calls, _marker, _old_id, _candidate_id = _run_forced_update_probe(
        tmp_path, build_result="0", tag_result="91"
    )
    assert completed.returncode == 2
    assert '"code":"rollback_plan_invalid"' in completed.stderr
    assert not any(
        operation.startswith("build ")
        for operation in calls.read_text(encoding="utf-8").splitlines()
    )
    assert not (tmp_path / "runtime" / "container-state" / ".pending-rollback-plan.tsv").exists()


@pytest.mark.parametrize(
    ("failure_hook", "failure_rc"),
    [
        ("classify", 17),
        ("prune", 18),
        ("validate", 19),
        ("require", 20),
    ],
)
def test_replacement_failure_hooks_abort_before_teardown_or_state_callbacks(
    tmp_path: Path, failure_hook: str, failure_rc: int
) -> None:
    """Each post-lock ownership/mount gate stops the transaction immediately."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    (runtime / "host-state").mkdir(parents=True)
    state_root.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    calls = tmp_path / "docker.calls"
    callbacks = tmp_path / "callbacks"
    docker = tmp_path / "docker"
    candidate_id = "sha256:" + "1" * 64
    old_id = "sha256:" + "0" * 64
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(calls)!r}\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then\n"
        f"  printf '%s\\n' {candidate_id!r}\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    active = runtime / "host-state" / "active-image.tsv"
    active.write_text(
        f"schema\tagent-canon.active-image.v1\n"
        f"image-ref\tactive\nimage-id\t{old_id}\n",
        encoding="utf-8",
    )
    hooks = {
        "classify": (
            "_agent_canon_classify_existing_container() { "
            f"printf '%s\\n' classify >> {str(callbacks)!r}; return {failure_rc}; }}"
        ),
        "prune": (
            "_agent_canon_classify_existing_container() { "
            "AGENT_CANON_OBSERVED_CONTAINER_ID=old; "
            "AGENT_CANON_OBSERVED_CONTAINER_RUNTIME=shared-v1; "
            "AGENT_CANON_OBSERVED_CONTAINER_CONTROL=$(_agent_canon_control_digest); }\n"
            "_agent_canon_prune_stale_target_manifest() { "
            f"printf '%s\\n' prune >> {str(callbacks)!r}; return {failure_rc}; }}"
        ),
        "validate": (
            "_agent_canon_classify_existing_container() { "
            "AGENT_CANON_OBSERVED_CONTAINER_ID=old; "
            "AGENT_CANON_OBSERVED_CONTAINER_RUNTIME=shared-v1; "
            "AGENT_CANON_OBSERVED_CONTAINER_CONTROL=$(_agent_canon_control_digest); }\n"
            "_agent_canon_prune_stale_target_manifest() { :; }\n"
            "_agent_canon_validate_target_manifest() { "
            f"printf '%s\\n' validate >> {str(callbacks)!r}; return {failure_rc}; }}"
        ),
        "require": (
            "_agent_canon_classify_existing_container() { "
            "AGENT_CANON_OBSERVED_CONTAINER_ID=old; "
            "AGENT_CANON_OBSERVED_CONTAINER_RUNTIME=shared-v1; "
            "AGENT_CANON_OBSERVED_CONTAINER_CONTROL=$(_agent_canon_control_digest); }\n"
            "_agent_canon_prune_stale_target_manifest() { :; }\n"
            "_agent_canon_validate_target_manifest() { :; }\n"
            "_agent_canon_write_rollback_plan() { :; }\n"
            "_agent_canon_use_active_image() { "
            f"AGENT_CANON_IMAGE_REF=active; AGENT_CANON_ACTIVE_IMAGE_ID={old_id}; "
            f"AGENT_CANON_EXPECTED_IMAGE_ID={old_id}; export AGENT_CANON_IMAGE_REF "
            "AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID; }\n"
            "_agent_canon_require_existing_container_identity() { "
            f"printf '%s\\n' require >> {str(callbacks)!r}; return {failure_rc}; }}"
        ),
    }
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_CONTROL_ROOT={str(control)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
AGENT_CANON_IMAGE_REF=candidate
AGENT_CANON_EXPECTED_IMAGE_ID={candidate_id}
export AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT AGENT_CANON_STATE_ROOT
export AGENT_CANON_DOCKER_CMD AGENT_CANON_IMAGE_REF AGENT_CANON_EXPECTED_IMAGE_ID
{hooks[failure_hook]}
_agent_canon_ensure_container() {{ printf '%s\\n' ensure >> {str(callbacks)!r}; return 0; }}
_agent_canon_run_controller() {{ printf '%s\\n' controller >> {str(callbacks)!r}; return 0; }}
_agent_canon_record_active_container() {{ printf '%s\\n' record >> {str(callbacks)!r}; return 0; }}
_agent_canon_install_global_links() {{ printf '%s\\n' links >> {str(callbacks)!r}; return 0; }}
_agent_canon_replace_resident candidate {candidate_id}
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == failure_rc
    assert not any(
        operation.split(" ", 1)[0] in {"build", "stop", "rm", "create", "start"}
        for operation in calls.read_text(encoding="utf-8").splitlines()
    )
    assert not (state_root / "previous-image-id").exists()
    assert active.read_text(encoding="utf-8").endswith(f"image-id\t{old_id}\n")
    assert callbacks.read_text(encoding="utf-8").splitlines() == [failure_hook]


@pytest.mark.parametrize("failure_hook", ["classify", "prune", "validate", "require"])
def test_public_update_locked_propagates_gate_failure(
    tmp_path: Path, failure_hook: str
) -> None:
    """The public update transaction returns injected gate failures unchanged."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    (runtime / "host-state").mkdir(parents=True)
    state_root.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    private_log = tmp_path / "agent-canon-log"
    private_log.mkdir()
    (state_root / "mounts.tsv").write_text("", encoding="utf-8")
    (state_root / "mounts.toml").write_text("", encoding="utf-8")
    (runtime / "source-sync.json").write_text("{}\n", encoding="utf-8")
    old_id = "sha256:" + "0" * 64
    candidate_id = "sha256:" + "1" * 64
    active = runtime / "host-state" / "active-image.tsv"
    if failure_hook != "classify":
        active.write_text(
            f"schema\tagent-canon.active-image.v1\n"
            f"image-ref\tactive\nimage-id\t{old_id}\n",
            encoding="utf-8",
        )
    calls = tmp_path / "docker.calls"
    callbacks = tmp_path / "callbacks"
    retained = tmp_path / "retained"
    control_digest = hashlib.sha256(str(control).encode("utf-8")).hexdigest()
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(calls)!r}\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then\n"
        "  ref=\"${@: -1}\"\n"
        f"  if [[ \"$ref\" == *rollback-* ]]; then [[ -f {str(retained)!r} ]] || exit 1; printf '%s\\n' {old_id!r}; "
        f"  else printf '%s\\n' {candidate_id!r}; fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == tag ]]; then\n"
        f"  touch {str(retained)!r}\n  exit 0\n"
        "fi\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then\n"
        "  format=\"${4:-}\"\n"
        "  case \"$format\" in\n"
        "    *Config.Image*) printf 'active\\n' ;;\n"
        "    *'{{.Id}}'*) printf 'old-container\\n' ;;\n"
        "    *io.agent-canon.runtime*) printf 'shared-v1\\n' ;;\n"
        f"    *io.agent-canon.control-root-digest*) printf '%s\\n' {control_digest!r} ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    hooks = {
        "classify": "_agent_canon_classify_existing_container() { return 17; }",
        "prune": "_agent_canon_prune_stale_target_manifest() { return 18; }",
        "validate": "_agent_canon_validate_target_manifest() { return 19; }",
        "require": "_agent_canon_require_existing_container_identity() { return 20; }",
    }
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}
AGENT_CANON_CONTROL_ROOT={str(control)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
AGENT_CANON_PRIVATE_LOG_ROOT={str(private_log)!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
AGENT_CANON_ALLOW_BUILD=1
AGENT_CANON_FORCE_BUILD=1
export AGENT_CANON_REPOSITORY_ROOT AGENT_CANON_CONTROL_ROOT AGENT_CANON_RUNTIME_ROOT
export AGENT_CANON_STATE_ROOT AGENT_CANON_PRIVATE_LOG_ROOT AGENT_CANON_DOCKER_CMD
export AGENT_CANON_ALLOW_BUILD AGENT_CANON_FORCE_BUILD
_agent_canon_image() {{
  printf '%s\\n' candidate >> {str(callbacks)!r}
  AGENT_CANON_IMAGE_REF=candidate
  export AGENT_CANON_IMAGE_REF
}}
_agent_canon_classify_existing_container() {{
  AGENT_CANON_OBSERVED_CONTAINER_ID=old-container
  AGENT_CANON_OBSERVED_CONTAINER_RUNTIME=shared-v1
  AGENT_CANON_OBSERVED_CONTAINER_CONTROL=$(_agent_canon_control_digest)
}}
{hooks[failure_hook]}
_agent_canon_ensure_container() {{ printf '%s\\n' ensure >> {str(callbacks)!r}; return 0; }}
_agent_canon_run_controller() {{ printf '%s\\n' controller >> {str(callbacks)!r}; return 0; }}
_agent_canon_record_active_container() {{ printf '%s\\n' record >> {str(callbacks)!r}; return 0; }}
_agent_canon_install_global_links() {{ printf '%s\\n' links >> {str(callbacks)!r}; return 0; }}
_agent_canon_update_locked '' candidate
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    expected_rc = {"classify": 17, "prune": 18, "validate": 19, "require": 20}[failure_hook]
    assert completed.returncode == expected_rc
    docker_calls = calls.read_text(encoding="utf-8").splitlines()
    assert not any(
        operation.split(" ", 1)[0] in {"build", "stop", "rm", "create", "start"}
        for operation in docker_calls
    )
    assert not (state_root / "previous-image-id").exists()
    if active.exists():
        assert active.read_text(encoding="utf-8").endswith(f"image-id\t{old_id}\n")
    assert not (state_root / ".pending-rollback-plan.tsv").exists()
    callbacks_text = callbacks.read_text(encoding="utf-8") if callbacks.exists() else ""
    assert "ensure" not in callbacks_text
    assert "controller" not in callbacks_text
    assert "record" not in callbacks_text


def test_fake_docker_install_two_forced_updates_and_rollback_toggle(
    tmp_path: Path,
) -> None:
    """The real shell adapter preserves A, then B, across forced updates."""
    home = tmp_path / "home"
    control = tmp_path / "control"
    repository = tmp_path / "agent-canon"
    home.mkdir()
    control.mkdir()
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "update-ref", "refs/heads/main", "HEAD"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "remote", "set-url", "origin", str(repository)],
        check=True,
    )
    fake_docker = ROOT / "tests" / "bootstrap" / "fake_docker.py"
    state_path = tmp_path / "docker-state.json"
    environment = {
        **os.environ,
        "HOME": str(home),
        "AGENT_CANON_DOCKER": str(fake_docker),
        "FAKE_DOCKER_STATE": str(state_path),
        "FAKE_DOCKER_VALID_IMAGE_IDS": "1",
        "AGENT_CANON_FORCE_BUILD": "1",
    }
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(control),
    ]
    runtime = repository / ".runtime"

    def run(operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*common, operation],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )

    def active_image() -> tuple[str, str]:
        values = dict(
            line.split("\t", 1)
            for line in (runtime / "host-state" / "active-image.tsv")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        return values["image-ref"], values["image-id"]

    def rollback_plan() -> tuple[str, str]:
        values = dict(
            line.split("\t", 1)
            for line in (runtime / "container-state" / "rollback-plan.tsv")
            .read_text(encoding="utf-8")
            .splitlines()
            if "\t" in line
        )
        return values["image-ref"], values["image-id"]

    installed = run("install")
    assert installed.returncode == 0, installed.stderr
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume = docker_state["volumes"][f"agent-canon-runtime-{control_digest}"]
    assert volume["UID"] == os.getuid()
    assert volume["GID"] == os.getgid()
    assert volume["Mode"] == "0700"
    assert volume["ResidentWriteReadback"] is True
    volume_root = Path(volume["Mountpoint"])

    def assert_volume_registry() -> None:
        registry = volume_root / "mount-registry.toml"
        assert registry.stat().st_mode & 0o777 == 0o444
        assert not os.access(registry, os.W_OK)

    assert_volume_registry()
    (volume_root / "host-mounts.tsv").write_text("stale\n", encoding="utf-8")
    copy_image = next(iter(docker_state["images"]))
    cleared = subprocess.run(
        [
            str(fake_docker),
            "run",
            "--rm",
            "--env",
            "AGENT_CANON_COPY_DIRECTION=clear",
            "--env",
            "AGENT_CANON_COPY_KIND=host-mounts",
            "--mount",
            f"type=volume,src={volume['Name']},dst=/var/lib/agent-canon",
            copy_image,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert cleared.returncode == 0
    assert not (volume_root / "host-mounts.tsv").exists()
    target = tmp_path / "target"
    target.mkdir()
    added = subprocess.run(
        [
            *common,
            "target",
            "add",
            "--root",
            str(target),
            "--mode",
            "read-only",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    assert added.returncode == 0, added.stderr
    assert_volume_registry()
    target_digest = hashlib.sha256(str(target.resolve()).encode("utf-8")).hexdigest()
    smoke = subprocess.run(
        [
            *common,
            "tool",
            "run",
            "--root",
            str(target),
            "generate-agent-improvement-guide",
            "--",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )
    assert smoke.returncode == 0, smoke.stderr
    active_ref, image_a = active_image()
    first = run("update")
    assert first.returncode == 0, first.stderr
    assert not first.stderr
    updated_ref, image_b = active_image()
    assert updated_ref == active_ref
    assert image_b != image_a
    assert_volume_registry()
    rollback_ref_a, rollback_id_a = rollback_plan()
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert rollback_id_a == image_a
    assert docker_state["images"][rollback_ref_a]["Id"] == image_a

    second = run("update")
    assert second.returncode == 0, second.stderr
    assert not second.stderr
    updated_ref, image_c = active_image()
    assert updated_ref == active_ref
    assert image_c not in {image_a, image_b}
    assert_volume_registry()
    rollback_ref_b, rollback_id_b = rollback_plan()
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert rollback_id_b == image_b
    assert docker_state["images"][rollback_ref_b]["Id"] == image_b

    rolled_back = run("rollback")
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert not rolled_back.stderr
    rollback_active_ref, rollback_active_id = active_image()
    assert rollback_active_id == image_b
    assert rollback_active_ref == image_b
    container_name = "agent-canon-tools-" + hashlib.sha256(
        str(control.resolve()).encode("utf-8")
    ).hexdigest()[:16]
    docker_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert docker_state["containers"][container_name]["Config"]["Image"] == image_b
    assert any(
        mount["Destination"] == f"/targets/{target_digest}"
        for mount in docker_state["containers"][container_name]["Mounts"]
    )
    assert_volume_registry()
    assert (runtime / "container-state" / "mounts.tsv").is_file()
    rollback_again = run("rollback")
    assert rollback_again.returncode == 0, rollback_again.stderr
    assert active_image()[1] == image_c
    assert_volume_registry()


def test_existing_controller_volume_requires_state_label(tmp_path: Path) -> None:
    """Volume adoption rejects a record without the controller state label."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    control.mkdir()
    runtime.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {
                            "io.agent-canon.runtime": "shared-v1",
                            "io.agent-canon.control-root-digest": control_digest,
                        },
                        "Mountpoint": str(tmp_path / "volume"),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"FAKE_DOCKER_STATE={str(state_path)!r}; export FAKE_DOCKER_STATE; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                "AGENT_CANON_IMAGE_REF=image; _agent_canon_init_state_volume"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "state_volume_ownership_mismatch"


def test_fake_volume_initializer_rejects_image_copy_up_without_nocopy(tmp_path: Path) -> None:
    """A fresh volume copy-up leaves an unmarked runtime and fails closed."""
    legacy = tmp_path / "legacy-state"
    legacy.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {
                            "io.agent-canon.runtime": "shared-v1",
                            "io.agent-canon.control-root-digest": control_digest,
                            "io.agent-canon.state": "controller-v1",
                        },
                        "Mountpoint": str(tmp_path / f".fake-volume-{volume_name}"),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            str(ROOT / "tests/bootstrap/fake_docker.py"),
            "run",
            "--rm",
            "--mount",
            f"type=volume,src={volume_name},dst=/var/lib/agent-canon",
            "--mount",
            f"type=bind,src={legacy},dst=/var/lib/agent-canon-legacy-state,readonly",
            "--env",
            "AGENT_CANON_VOLUME_UID=1000",
            "--env",
            "AGENT_CANON_VOLUME_GID=1000",
            "--env",
            f"AGENT_CANON_VOLUME_DIGEST={control_digest}",
            "image",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 1
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    assert (volume_root / "runtime").is_dir()
    assert not (volume_root / ".agent-canon-controller-volume-v1").exists()


def test_fake_volume_initializer_preserves_readonly_legacy_source(tmp_path: Path) -> None:
    """Fake volume initialization copies legacy input without mutating it."""
    legacy = tmp_path / "legacy-state"
    legacy.mkdir()
    (legacy / "state.json").write_text('{"legacy":true}\n', encoding="utf-8")
    (legacy / "state.json").chmod(0o400)
    legacy.chmod(0o500)
    control = tmp_path / "control"
    control.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(tmp_path / f".fake-volume-{volume_name}"),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    fake = ROOT / "tests/bootstrap/fake_docker.py"
    result = subprocess.run(
        [
            str(fake),
            "run",
            "--rm",
            "--mount",
            f"type=volume,src={volume_name},dst=/var/lib/agent-canon,volume-nocopy",
            "--mount",
            f"type=bind,src={legacy},dst=/var/lib/agent-canon-legacy-state,readonly",
            "--env",
            "AGENT_CANON_VOLUME_UID=1000",
            "--env",
            "AGENT_CANON_VOLUME_GID=1000",
            "--env",
            f"AGENT_CANON_VOLUME_DIGEST={control_digest}",
            "image",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 0, result.stderr
    assert (legacy / "state.json").read_text(encoding="utf-8") == '{"legacy":true}\n'
    assert (legacy / "state.json").stat().st_mode & 0o777 == 0o400
    assert legacy.stat().st_mode & 0o777 == 0o500
    volume_state = tmp_path / f".fake-volume-{volume_name}" / "runtime" / "state.json"
    assert volume_state.read_text(encoding="utf-8") == '{"legacy":true}\n'
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["volumes"][volume_name]["Mode"] == "0700"
    assert state["volumes"][volume_name]["UID"] == os.getuid()
    assert state["volumes"][volume_name]["GID"] == os.getgid()


def test_fake_marked_volume_adopts_divergent_legacy_state(tmp_path: Path) -> None:
    """A marked volume is adopted without comparing evolved host legacy state."""
    legacy = tmp_path / "legacy-state"
    (legacy / "receipts").mkdir(parents=True)
    (legacy / "receipts" / "old.json").write_text("host-only\n", encoding="utf-8")
    (legacy / "spool").mkdir()
    (legacy / "spool" / "host-only").write_text("preserve\n", encoding="utf-8")
    control = tmp_path / "control"
    control.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    (volume_root / "runtime" / "receipts").mkdir(parents=True)
    preserved_files = {
        "runtime/state.json": "state-owned\n",
        "runtime/receipts/current.json": "receipts-owned\n",
        "runtime/generations/current.tsv": "generations-owned\n",
        "runtime/tasks/current.json": "tasks-owned\n",
        "spool/owned.txt": "spool-owned\n",
        "archive/owned.txt": "archive-owned\n",
        "cache/owned.txt": "cache-owned\n",
        "codex-home/owned.txt": "codex-owned\n",
    }
    for directory in (
        "runtime/generations",
        "runtime/tasks",
        "spool",
        "archive",
        "cache",
        "codex-home",
    ):
        (volume_root / directory).mkdir(parents=True)
    for relative, content in preserved_files.items():
        (volume_root / relative).write_text(content, encoding="utf-8")
    for directory in (
        volume_root,
        volume_root / "runtime",
        volume_root / "spool",
        volume_root / "archive",
        volume_root / "cache",
        volume_root / "codex-home",
    ):
        directory.chmod(0o755)
    (volume_root / ".agent-canon-controller-volume-v1").write_text(
        f"agent-canon-controller-volume/v1\n{control_digest}\n", encoding="utf-8"
    )
    (volume_root / ".agent-canon-controller-volume-v1").chmod(0o640)
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {
                            "io.agent-canon.runtime": "shared-v1",
                            "io.agent-canon.control-root-digest": control_digest,
                            "io.agent-canon.state": "controller-v1",
                        },
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"FAKE_DOCKER_STATE={str(state_path)!r}; export FAKE_DOCKER_STATE; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(legacy)!r}; "
                f"AGENT_CANON_STATE_ROOT={str(legacy)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                "AGENT_CANON_IMAGE_REF=image; _agent_canon_init_state_volume"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 0, result.stderr
    for relative, content in preserved_files.items():
        assert (volume_root / relative).read_text(encoding="utf-8") == content
    assert (volume_root / "exchange").is_dir()
    assert (volume_root / "private-log").is_dir()
    for directory in (
        volume_root,
        volume_root / "runtime",
        volume_root / "exchange",
        volume_root / "private-log",
    ):
        assert directory.stat().st_mode & 0o777 == 0o700
    assert (
        volume_root / ".agent-canon-controller-volume-v1"
    ).stat().st_mode & 0o777 == 0o600
    assert (legacy / "spool" / "host-only").read_text(encoding="utf-8") == "preserve\n"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["volumes"][volume_name]["Mode"] == "0700"
    assert state["volumes"][volume_name]["UID"] == os.getuid()
    assert state["volumes"][volume_name]["GID"] == os.getgid()


def test_fake_marked_volume_rejects_invalid_marker(tmp_path: Path) -> None:
    """A marked volume with an invalid marker fails without creating paths."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    control.mkdir()
    runtime.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    (volume_root / "runtime" / "receipts").mkdir(parents=True)
    (volume_root / "runtime" / "generations").mkdir(parents=True)
    (volume_root / "runtime" / "tasks").mkdir(parents=True)
    for directory in ("spool", "archive", "cache", "codex-home"):
        (volume_root / directory).mkdir()
    marker = volume_root / ".agent-canon-controller-volume-v1"
    marker.write_text(
        "agent-canon-controller-volume/v1\nwrong-digest\n", encoding="utf-8"
    )
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {
                            "io.agent-canon.runtime": "shared-v1",
                            "io.agent-canon.control-root-digest": control_digest,
                            "io.agent-canon.state": "controller-v1",
                        },
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"FAKE_DOCKER_STATE={str(state_path)!r}; export FAKE_DOCKER_STATE; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                "AGENT_CANON_IMAGE_REF=image; _agent_canon_init_state_volume"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "state_volume_init_failed"
    assert marker.read_text(encoding="utf-8") == (
        "agent-canon-controller-volume/v1\nwrong-digest\n"
    )
    assert not (volume_root / "exchange").exists()
    assert not (volume_root / "private-log").exists()


def test_target_add_init_failure_restores_previous_fake_resident(tmp_path: Path) -> None:
    """Initializer failure aborts target replacement and restores the prior resident."""
    home = tmp_path / "home"
    control = tmp_path / "control"
    repository = tmp_path / "agent-canon"
    home.mkdir()
    control.mkdir()
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(repository), "update-ref", "refs/heads/main", "HEAD"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "remote", "set-url", "origin", str(repository)],
        check=True,
    )
    state_path = tmp_path / "docker-state.json"
    fake_docker = ROOT / "tests/bootstrap/fake_docker.py"
    environment = {
        **os.environ,
        "HOME": str(home),
        "AGENT_CANON_DOCKER": str(fake_docker),
        "FAKE_DOCKER_STATE": str(state_path),
        "FAKE_DOCKER_VALID_IMAGE_IDS": "1",
    }
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(control),
    ]
    installed = subprocess.run(
        [*common, "install"], check=False, capture_output=True, text=True, env=environment
    )
    assert installed.returncode == 0, installed.stderr
    state = json.loads(state_path.read_text(encoding="utf-8"))
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    container_name = f"agent-canon-tools-{control_digest[:16]}"
    old_container = state["containers"][container_name]
    old_image = old_container["Config"]["Image"]
    old_mounts = list(old_container["Mounts"])
    target = tmp_path / "target"
    target.mkdir()
    failed_environment = {**environment, "FAKE_DOCKER_FAIL_STATE_VOLUME_INIT_ONCE": "1"}
    failed = subprocess.run(
        [*common, "target", "add", "--root", str(target), "--mode", "read-only"],
        check=False,
        capture_output=True,
        text=True,
        env=failed_environment,
    )
    assert failed.returncode == 2
    assert '"code":"state_volume_init_failed"' in failed.stderr
    state = json.loads(state_path.read_text(encoding="utf-8"))
    restored = state["containers"][container_name]
    assert restored["Config"]["Image"] == old_image
    assert restored["Mounts"] == old_mounts
    assert (repository / ".runtime" / "container-state" / "mounts.tsv").read_text(
        encoding="utf-8"
    ) == ""


def test_volume_input_imports_use_exact_runtime_paths(tmp_path: Path) -> None:
    """Source-sync and registry imports land at their canonical volume paths."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    control.mkdir()
    runtime.mkdir()
    source_sync = runtime / "source-sync.json"
    registry = runtime / "mounts.toml"
    source_sync.write_text("source-sync\n", encoding="utf-8")
    registry.write_text("mount-registry\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    common = (
        f"source {str(ADAPTER)!r}; "
        f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
        f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
        f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
        f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
        f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
        f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
        "AGENT_CANON_IMAGE_REF=image; "
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            common
            + f"_agent_canon_volume_copy import source-sync {str(source_sync)!r}; "
            + f"_agent_canon_volume_copy import mount-registry {str(registry)!r}",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 0, result.stderr
    assert (volume_root / "source-sync.json").read_text(encoding="utf-8") == "source-sync\n"
    assert (volume_root / "mount-registry.toml").read_text(encoding="utf-8") == "mount-registry\n"


def test_volume_copy_runs_embedded_helper_with_real_posix_shell(tmp_path: Path) -> None:
    """The exact Docker run argv executes the embedded copy script with /bin/sh."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    codex_stage = tmp_path / "codex-stage"
    volume_root = tmp_path / "volume"
    fake_install = tmp_path / "fake-install"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    codex_stage.mkdir()
    (fake_install / ".codex" / "personal" / "skills" / "managed").mkdir(parents=True)
    (fake_install / ".codex" / "config.toml").write_text("config\n", encoding="utf-8")
    (fake_install / ".codex" / "personal" / "skills" / "managed" / "SKILL.md").write_text(
        "skill\n", encoding="utf-8"
    )
    (volume_root / "exchange").mkdir(parents=True)
    (volume_root / "codex-home").mkdir(parents=True)
    (volume_root / "codex-home" / "config.toml").symlink_to(
        fake_install / ".codex" / "config.toml"
    )
    (volume_root / "codex-home" / "skills").mkdir()
    (volume_root / "codex-home" / "skills" / "managed").mkdir()
    (volume_root / "codex-home" / "skills" / "managed" / "SKILL.md").symlink_to(
        fake_install / ".codex" / "personal" / "skills" / "managed" / "SKILL.md"
    )
    (codex_stage / "config.toml").write_text("stale\n", encoding="utf-8")
    source_sync = runtime / "source-sync.json"
    source_sync.write_text("source-sync\n", encoding="utf-8")
    (volume_root / "exchange" / "mounts.tsv").write_text("target\n", encoding="utf-8")
    (volume_root / "exchange" / "mounts.toml").write_text(
        'schema = "agent-canon.mount-registry.v2"\n', encoding="utf-8"
    )
    volume_name = "agent-canon-runtime-real-shell"
    docker = tmp_path / "docker-real-shell"
    docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "script= input= volume=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --mount)\n"
        "      shift\n"
        "      spec=$1\n"
        "      case \"$spec\" in\n"
        "        type=volume,src=*,dst=/var/lib/agent-canon)\n"
        "          volume=${spec#type=volume,src=}; volume=${volume%,dst=/var/lib/agent-canon} ;;\n"
        "        type=volume,src=*,dst=/var/lib/agent-canon,readonly)\n"
        "          volume=${spec#type=volume,src=}; volume=${volume%,dst=/var/lib/agent-canon,readonly} ;;\n"
        "        type=bind,src=*,dst=/agent-canon-copy-input,readonly)\n"
        "          input=${spec#type=bind,src=}; input=${input%,dst=/agent-canon-copy-input,readonly} ;;\n"
        "        type=bind,src=*,dst=/agent-canon-copy-output)\n"
        "          exit 91 ;;\n"
        "      esac ;;\n"
        "    --env) shift; export \"$1\" ;;\n"
        "    -c) shift; script=$1 ;;\n"
        "  esac\n"
        "  shift\n"
        "done\n"
        "[ \"$volume\" = \"$FAKE_VOLUME_NAME\" ]\n"
        "[ -n \"$script\" ]\n"
        "script=$(printf \"%s\" \"$script\" | sed -e \"s|/var/lib/agent-canon|$FAKE_VOLUME_ROOT|g\" -e \"s|/agent-canon-copy-input|$input|g\")\n"
        "exec /bin/sh -c \"$script\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    common = (
        f"source {str(ADAPTER)!r}; "
        f"AGENT_CANON_DOCKER_CMD={str(docker)!r}; "
        f"AGENT_CANON_REPOSITORY_ROOT={str(fake_install)!r}; "
        f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
        f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
        f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
        f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
        "AGENT_CANON_IMAGE_REF=image; "
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            common
            + f"_agent_canon_volume_copy import source-sync {str(source_sync)!r}; "
            + f"_agent_canon_volume_copy export projection {str(stage)!r}",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_VOLUME_NAME": volume_name,
            "FAKE_VOLUME_ROOT": str(volume_root),
        },
    )
    assert result.returncode == 0, result.stderr
    assert (volume_root / "source-sync.json").read_text(encoding="utf-8") == "source-sync\n"
    assert (stage / "mounts.tsv").read_text(encoding="utf-8") == "target\n"
    assert (stage / "mounts.toml").read_text(encoding="utf-8").startswith(
        'schema = "agent-canon.mount-registry.v2"'
    )
    codex_export = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy export codex-home {str(codex_stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_VOLUME_NAME": volume_name,
            "FAKE_VOLUME_ROOT": str(volume_root),
        },
    )
    assert codex_export.returncode == 0, codex_export.stderr
    assert codex_stage.is_dir()
    assert (codex_stage / "config.toml").is_symlink()
    assert (codex_stage / "config.toml").resolve() == (fake_install / ".codex" / "config.toml").resolve()
    assert (codex_stage / "skills" / "managed" / "SKILL.md").is_symlink()
    assert (codex_stage / "skills" / "managed" / "SKILL.md").resolve() == (
        fake_install / ".codex" / "personal" / "skills" / "managed" / "SKILL.md"
    ).resolve()
    (volume_root / "codex-home" / "agents").mkdir()
    (volume_root / "codex-home" / "agents" / "current.toml").write_text(
        "current\n", encoding="utf-8"
    )
    (codex_stage / "config.toml").unlink()
    (codex_stage / "config.toml").write_text("old\n", encoding="utf-8")
    (codex_stage / "agents").mkdir()
    (codex_stage / "agents" / "old.toml").write_text("old\n", encoding="utf-8")
    codex_failed = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy export codex-home {str(codex_stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_VOLUME_NAME": volume_name,
            "FAKE_VOLUME_ROOT": str(volume_root),
            "AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_AFTER": "codex-home",
        },
    )
    assert codex_failed.returncode == 2
    assert json.loads(codex_failed.stderr)["code"] == "volume_export_failed"
    assert (codex_stage / "config.toml").read_text(encoding="utf-8") == "old\n"
    assert (codex_stage / "agents" / "old.toml").read_text(encoding="utf-8") == "old\n"
    assert not (codex_stage / "agents" / "current.toml").exists()
    (volume_root / "codex-home" / "config.toml").unlink()
    (volume_root / "codex-home" / "config.toml").symlink_to("relative-config.toml")
    relative_rejected = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy export codex-home {str(codex_stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_VOLUME_NAME": volume_name,
            "FAKE_VOLUME_ROOT": str(volume_root),
        },
    )
    assert relative_rejected.returncode == 2
    assert json.loads(relative_rejected.stderr)["code"] == "volume_copy_failed"
    (volume_root / "codex-home" / "config.toml").unlink()
    (volume_root / "codex-home" / "config.toml").symlink_to(
        fake_install / ".codex" / "config.toml"
    )
    (volume_root / "codex-home" / "unexpected").symlink_to(tmp_path / "outside")
    rejected = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy export codex-home {str(codex_stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_VOLUME_NAME": volume_name,
            "FAKE_VOLUME_ROOT": str(volume_root),
        },
    )
    assert rejected.returncode == 2
    assert json.loads(rejected.stderr)["code"] == "volume_copy_failed"
    assert codex_stage.is_dir()


def test_volume_export_digest_corruption_is_rejected(tmp_path: Path) -> None:
    """A corrupted host projection fails the Docker copy readback digest."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    exchange = volume_root / "exchange"
    exchange.mkdir(parents=True)
    (exchange / "mounts.tsv").write_text("", encoding="utf-8")
    (exchange / "mounts.toml").write_text(
        'schema = "agent-canon.mount-registry.v2"\n', encoding="utf-8"
    )
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(control)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export projection {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_DOCKER_STATE": str(state_path),
            "FAKE_DOCKER_CORRUPT_COPY": "1",
        },
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "volume_copy_failed"


def test_volume_export_rejects_fifo_before_publish(tmp_path: Path) -> None:
    """A FIFO in a bounded tree export cannot reach the host projection."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    (stage / "old.txt").write_text("keep\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    skill = volume_root / "exchange" / "skill-projection"
    skill.mkdir(parents=True)
    os.mkfifo(skill / "unexpected.fifo")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export skill {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "volume_export_invalid"
    assert (stage / "old.txt").read_text(encoding="utf-8") == "keep\n"


def test_volume_export_list_failure_is_typed_and_preserves_destination(tmp_path: Path) -> None:
    """A malformed tar stream fails before touching the existing projection."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    (stage / "old.txt").write_text("keep\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    (volume_root / "exchange").mkdir(parents=True)
    (volume_root / "exchange" / "mounts.tsv").write_text("", encoding="utf-8")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export projection {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_DOCKER_STATE": str(state_path),
            "FAKE_DOCKER_MALFORMED_TAR": "1",
        },
    )
    assert result.returncode == 2
    assert json.loads(result.stderr.splitlines()[-1])["code"] == "volume_export_failed"
    assert (stage / "old.txt").read_text(encoding="utf-8") == "keep\n"


def test_projection_later_move_failure_restores_exact_previous_state(tmp_path: Path) -> None:
    """A later fixed-file move failure restores all prior files and absences."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    (stage / "mounts.toml").write_text("old-toml\n", encoding="utf-8")
    (stage / "mounts.tsv").write_text("old-tsv\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    exchange = volume_root / "exchange"
    exchange.mkdir(parents=True)
    (exchange / "mounts.toml").write_text("new-toml\n", encoding="utf-8")
    (exchange / "mounts.tsv").write_text("new-tsv\n", encoding="utf-8")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export projection {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_DOCKER_STATE": str(state_path),
            "AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_AFTER": "mounts.toml",
        },
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "volume_export_failed"
    assert (stage / "mounts.toml").read_text(encoding="utf-8") == "old-toml\n"
    assert (stage / "mounts.tsv").read_text(encoding="utf-8") == "old-tsv\n"
    assert not (stage / "rollback-plan.tsv").exists()
    assert not (stage / "rollback-mounts.tsv").exists()
    backup_failed = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export projection {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "FAKE_DOCKER_STATE": str(state_path),
            "AGENT_CANON_TEST_VOLUME_EXPORT_FAIL_BACKUP": "mounts.tsv",
        },
    )
    assert backup_failed.returncode == 2
    assert json.loads(backup_failed.stderr)["code"] == "volume_export_failed"
    assert (stage / "mounts.toml").read_text(encoding="utf-8") == "old-toml\n"
    assert (stage / "mounts.tsv").read_text(encoding="utf-8") == "old-tsv\n"
    assert not (stage / "rollback-plan.tsv").exists()
    assert not (stage / "rollback-mounts.tsv").exists()


def test_private_feedback_volume_copy_uses_canonical_subtree(tmp_path: Path) -> None:
    """Private feedback export selects its fixed volume subtree and ID."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    (stage / "stale.txt").write_text("stale\n", encoding="utf-8")
    feedback = volume_root / "spool" / "private-feedback"
    feedback.mkdir(parents=True)
    (feedback / "feedback.json").write_text("feedback\n", encoding="utf-8")
    (volume_root / "spool" / "other.txt").write_text("other\n", encoding="utf-8")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    common = (
        f"source {str(ADAPTER)!r}; "
        f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
        f"AGENT_CANON_REPOSITORY_ROOT={str(ROOT)!r}; "
        f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
        f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
        f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
        f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
        "AGENT_CANON_IMAGE_REF=image; "
    )
    exported = subprocess.run(
        [
            "bash",
            "-c",
            common
            + f"_agent_canon_volume_copy export private-feedback {str(stage)!r} private-feedback",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert exported.returncode == 0, exported.stderr
    assert not (stage / "stale.txt").exists()
    assert (stage / "feedback.json").read_text(encoding="utf-8") == "feedback\n"
    assert not (stage / "other.txt").exists()
    assert '_agent_canon_volume_copy export private-feedback "$spool" private-feedback' in ADAPTER.read_text(
        encoding="utf-8"
    )
    invalid = subprocess.run(
        [
            "bash",
            "-c",
            common
            + f"_agent_canon_volume_copy export private-feedback {str(stage)!r} bad/id",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert invalid.returncode == 2
    assert json.loads(invalid.stderr)["code"] == "volume_copy_invalid"


def test_codex_volume_copy_rejects_unexpected_symlink_target(tmp_path: Path) -> None:
    """Codex export accepts only managed links into the live .codex tree."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    fake_install = tmp_path / "fake-install"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    (fake_install / ".codex").mkdir(parents=True)
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    codex_home = volume_root / "codex-home"
    codex_home.mkdir(parents=True)
    (codex_home / "unexpected").symlink_to(tmp_path / "outside")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                f"source {str(ADAPTER)!r}; "
                f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
                f"AGENT_CANON_REPOSITORY_ROOT={str(fake_install)!r}; "
                f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
                f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
                f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
                f"AGENT_CANON_IMAGE_REF=image; "
                f"_agent_canon_volume_copy export codex-home {str(stage)!r}"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "volume_copy_failed"


def test_codex_volume_copy_roundtrips_managed_symlink(tmp_path: Path) -> None:
    """Managed Codex links retain their target and mode through both copies."""
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    stage = tmp_path / "stage"
    fake_install = tmp_path / "fake-install"
    control.mkdir()
    runtime.mkdir()
    stage.mkdir()
    (fake_install / ".codex").mkdir(parents=True)
    (fake_install / ".codex" / "config.toml").write_text("config\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    volume_name = f"agent-canon-runtime-{control_digest}"
    volume_root = tmp_path / f".fake-volume-{volume_name}"
    codex_home = volume_root / "codex-home"
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").symlink_to(fake_install / ".codex" / "config.toml")
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(
        json.dumps(
            {
                "images": {},
                "containers": {},
                "volumes": {
                    volume_name: {
                        "Name": volume_name,
                        "Labels": {},
                        "Mountpoint": str(volume_root),
                    }
                },
                "next": 1,
            }
        ),
        encoding="utf-8",
    )
    common = (
        f"source {str(ADAPTER)!r}; "
        f"AGENT_CANON_DOCKER_CMD={str(ROOT / 'tests/bootstrap/fake_docker.py')!r}; "
        f"AGENT_CANON_REPOSITORY_ROOT={str(fake_install)!r}; "
        f"AGENT_CANON_CONTROL_ROOT={str(control)!r}; "
        f"AGENT_CANON_STATE_VOLUME_NAME={volume_name!r}; "
        f"AGENT_CANON_STATE_ROOT={str(runtime)!r}; "
        f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}; "
        "AGENT_CANON_IMAGE_REF=image; "
    )
    exported = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy export codex-home {str(stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert exported.returncode == 0, exported.stderr
    assert (stage / "config.toml").is_symlink()
    assert (stage / "config.toml").resolve() == (fake_install / ".codex" / "config.toml").resolve()
    imported = subprocess.run(
        ["bash", "-c", common + f"_agent_canon_volume_copy import codex-home {str(stage)!r}"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_DOCKER_STATE": str(state_path)},
    )
    assert imported.returncode == 0, imported.stderr
    assert (codex_home / "config.toml").is_symlink()
    assert (codex_home / "config.toml").resolve() == (fake_install / ".codex" / "config.toml").resolve()


@pytest.mark.skipif(
    shutil.which("docker") is None
    or os.environ.get("AGENT_CANON_RUN_REAL_UPDATE_TESTS") != "1",
    reason="opt-in real Docker forced-update acceptance",
)
def test_real_docker_forced_updates_retain_previous_images(tmp_path: Path) -> None:
    """Run the same image/tag/rollback contract against the configured daemon."""
    docker = shutil.which("docker")
    assert docker is not None
    daemon = subprocess.run(
        [docker, "info"], check=False, capture_output=True, text=True, timeout=15
    )
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")
    home = tmp_path / "home"
    control = tmp_path / "control"
    repository = tmp_path / "agent-canon"
    home.mkdir()
    control.mkdir()
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(repository)],
        check=True,
        capture_output=True,
    )
    environment = {**os.environ, "HOME": str(home), "AGENT_CANON_DOCKER": docker}
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(control),
    ]
    runtime = repository / ".runtime"
    retained_images: dict[str, str] = {}

    def run(operation: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*common, operation],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=300,
        )

    def active_id() -> str:
        return next(
            line.split("\t", 1)[1]
            for line in (runtime / "host-state" / "active-image.tsv")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("image-id\t")
        )

    def plan_value(key: str) -> str:
        return next(
            line.split("\t", 1)[1]
            for line in (runtime / "container-state" / "rollback-plan.tsv")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith(key + "\t")
        )

    try:
        installed = run("install")
        assert installed.returncode == 0, installed.stderr
        image_a = active_id()
        first = run("update")
        assert first.returncode == 0, first.stderr
        assert not first.stderr
        image_b = active_id()
        retained_images[plan_value("image-ref")] = plan_value("image-id")
        assert image_b != image_a
        assert image_a in retained_images.values()
        second = run("update")
        assert second.returncode == 0, second.stderr
        assert not second.stderr
        image_c = active_id()
        retained_images[plan_value("image-ref")] = plan_value("image-id")
        assert image_c not in {image_a, image_b}
        assert image_b in retained_images.values()
        for image_ref, image_id in retained_images.items():
            inspected = subprocess.run(
                [docker, "image", "inspect", "--format", "{{.Id}}", image_ref],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert inspected.returncode == 0, inspected.stderr
            assert inspected.stdout.strip() == image_id
        rolled_back = run("rollback")
        assert rolled_back.returncode == 0, rolled_back.stderr
        assert not rolled_back.stderr
        assert active_id() == image_b
        rollback_again = run("rollback")
        assert rollback_again.returncode == 0, rollback_again.stderr
        assert not rollback_again.stderr
        assert active_id() == image_c
    finally:
        run("uninstall")
        for image_ref in retained_images:
            subprocess.run(
                [docker, "image", "rm", image_ref], check=False, capture_output=True
            )
        for image_id in retained_images.values():
            subprocess.run(
                [docker, "image", "rm", image_id], check=False, capture_output=True
            )


def test_sync_stages_source_before_live_fast_forward() -> None:
    """Source sync builds the candidate checkout before touching live source."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "source-staging/agent-canon" in text
    assert 'git clone --no-hardlinks "$install_root" "$staging_root"' in text
    assert 'git -C "$install_root" merge --ff-only "$remote/$branch"' in text
    assert text.index('git clone --no-hardlinks "$install_root" "$staging_root"') < text.rindex('git -C "$install_root" merge --ff-only "$remote/$branch"')
    assert text.index('bootstrap_host_entrypoint "$staging_root"') < text.index('git -C "$install_root" merge --ff-only "$remote/$branch"')


def test_source_sync_state_is_mounted_read_only_into_the_resident() -> None:
    """The host imports source-sync into the single resident volume."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "AGENT_CANON_SOURCE_SYNC_DESTINATION=/var/lib/agent-canon/source-sync.json" in text
    assert "_agent_canon_volume_copy import source-sync" in text
    assert "_agent_canon_volume_copy import mount-registry" in text
    assert 'mount-registry) destination="$root/mount-registry.toml"' in text
    assert 'dst=$AGENT_CANON_SOURCE_SYNC_DESTINATION,readonly' not in text
    assert "_agent_canon_ensure_source_sync_state" in text
    assert "container-state/source-sync.json" not in text


def test_source_sync_mount_migration_ignores_only_declared_destination(
    tmp_path: Path,
) -> None:
    """Legacy bind residents are stale and cannot pass exact mount readback."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    private_log = tmp_path / "agent-canon-log"
    control = tmp_path / "control"
    source_sync = runtime / "source-sync.json"
    mounts = state_root / "mounts.tsv"
    for path in (state_root, private_log, control):
        path.mkdir(parents=True)
    source_sync.write_text("{}\n", encoding="utf-8")
    mounts.write_text("", encoding="utf-8")
    control_digest = hashlib.sha256(str(control).encode("utf-8")).hexdigest()
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:image\\n'; exit 0; fi\n"
        "format=$4\n"
        "case \"$format\" in\n"
        "  *io.agent-canon.runtime*) printf 'shared-v1' ;;\n"
        "  *io.agent-canon.control-root-digest*) printf '" + control_digest + "' ;;\n"
        "  *Config.Image*) printf 'image' ;;\n"
        "  *NetworkMode*) printf 'none' ;;\n"
        "  *ReadonlyRootfs*) printf 'true' ;;\n"
        "  *CapDrop*) printf 'ALL' ;;\n"
        "  *SecurityOpt*) printf 'no-new-privileges' ;;\n"
        "  *NanoCpus*) printf '2000000000' ;;\n"
        "  *Memory*) printf '4294967296' ;;\n"
        "  *PidsLimit*) printf '512' ;;\n"
        "  *range[[:space:]].Mounts*) cat \"$FAKE_MOUNTS\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    common = (
        f"source {str(ADAPTER)!r}\n"
        "set -e\n"
        f"AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}\n"
        f"AGENT_CANON_STATE_ROOT={str(state_root)!r}\n"
        f"AGENT_CANON_CONTROL_ROOT={str(control)!r}\n"
        f"AGENT_CANON_PRIVATE_LOG_ROOT={str(private_log)!r}\n"
        "AGENT_CANON_IMAGE_REF=image\n"
        f"AGENT_CANON_DOCKER_CMD={str(docker)!r}\n"
        "_agent_canon_validate_existing_container container "
        f"{str(mounts)!r} 1 $REQUIRE_SYNC\n"
    )

    def validate(require_sync: int, mount_lines: str) -> int:
        mount_file = tmp_path / f"mounts-{require_sync}-{len(mount_lines)}.txt"
        mount_file.write_text(mount_lines, encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", common],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "FAKE_MOUNTS": str(mount_file),
                "REQUIRE_SYNC": str(require_sync),
            },
        )
        assert not result.stdout, result.stdout
        return result.returncode

    old_mounts = (
        f"{state_root}\t/var/lib/agent-canon/runtime\ttrue\n"
        f"{private_log}\t/var/lib/agent-canon/private-log\tfalse\n"
        f"{state_root / 'mounts.toml'}\t/var/lib/agent-canon/mount-registry.toml\tfalse\n"
    )
    new_mounts = old_mounts + (
        f"{source_sync}\t/var/lib/agent-canon/source-sync.json\tfalse\n"
    )
    assert validate(0, old_mounts) == 2
    assert validate(0, new_mounts) == 2
    assert validate(1, new_mounts) == 2
    assert validate(1, old_mounts) == 2


def test_install_target_pruning_removes_only_stale_derived_rows(tmp_path: Path) -> None:
    """Convergence drops missing/file/symlink targets and preserves valid rows."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    state_root.mkdir(parents=True)
    valid = tmp_path / "valid"
    valid.mkdir()
    regular_file = tmp_path / "file"
    regular_file.write_text("not a target directory\n", encoding="utf-8")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(valid, target_is_directory=True)
    missing = tmp_path / "missing"

    def digest(path: Path) -> str:
        return hashlib.sha256(str(path).encode("utf-8")).hexdigest()

    manifest = state_root / "mounts.tsv"
    manifest.write_text(
        "\n".join(
            (
                f"target\t{digest(missing)}\t{missing}\t/targets/{digest(missing)}\tread-only",
                f"target\t{digest(regular_file)}\t{regular_file}\t/targets/{digest(regular_file)}\tread-only",
                f"target\t{digest(symlink)}\t{symlink}\t/targets/{digest(symlink)}\tread-only",
                f"target\t{digest(valid)}\t{valid}\t/targets/{digest(valid)}\tread-only",
                "invalid\trow",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    script = f"""
source {str(ADAPTER)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
_agent_canon_prune_stale_target_manifest
printf '%s\\n' "$AGENT_CANON_TARGET_PRUNE_DIGESTS"
"""
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ",".join(
        (digest(missing), digest(regular_file), digest(symlink))
    )
    assert manifest.read_text(encoding="utf-8") == (
        f"target\t{digest(valid)}\t{valid}\t/targets/{digest(valid)}\tread-only\n"
        "invalid\trow\n"
    )


@pytest.mark.parametrize("install_option", ["separate", "equals"])
def test_sync_resolves_install_root_before_runtime_initialization(
    tmp_path: Path, install_option: str
) -> None:
    """A sync target owns the initial record even when it differs from the script root."""
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    target = tmp_path / "target"
    control = tmp_path / "control"
    control.mkdir()
    (tmp_path / "script-root").mkdir()
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "AgentCanon Test"], check=True)
    (seed / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-m", "one"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "origin", "main"], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(bare), str(target)], check=True, capture_output=True)
    install_arg = (
        f"--install-root={target}" if install_option == "equals" else "--install-root"
    )
    command = [str(BOOTSTRAP), "--repository-root", str(tmp_path / "script-root"),
               "--control-parent-root", str(control), "sync", install_arg]
    if install_option == "separate":
        command.append(str(target))
    command.extend(["--remote", "origin", "--branch", "main"])
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": "true"},
    )
    assert completed.returncode == 0, completed.stderr
    state = json.loads((target / ".runtime/source-sync.json").read_text(encoding="utf-8"))
    assert state["status"] == "success"
    assert state["code"] == "up_to_date"
    assert state["source_root"] == str(target.resolve())
    assert state["remote"] == "origin"
    assert state["branch"] == "main"
    assert len(state["source_head"]) == 40
    assert len(state["source_tree"]) == 40
    failed = subprocess.run(
        [*command[:-1], "missing"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": "true"},
    )
    assert failed.returncode == 2
    failed_state = json.loads((target / ".runtime/source-sync.json").read_text(encoding="utf-8"))
    assert failed_state["status"] == "failed"
    assert failed_state["source_root"] == str(target.resolve())
    assert failed_state["remote"] == "origin"
    assert failed_state["branch"] == "missing"
    assert len(failed_state["source_head"]) == 40
    assert len(failed_state["source_tree"]) == 40


def test_sync_invalid_install_root_fails_before_state_creation(tmp_path: Path) -> None:
    """An invalid target is rejected before a target runtime or misleading record exists."""
    control = tmp_path / "control"
    control.mkdir()
    (tmp_path / "script-root").mkdir()
    target = tmp_path / "missing-target"
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(tmp_path / "script-root"),
            "--control-parent-root",
            str(control),
            "sync",
            "--install-root",
            str(target),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": "true"},
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "install_root_invalid"
    assert not target.exists()


def test_managed_install_source_fetch_failure_preserves_checkout(tmp_path: Path) -> None:
    """A remote failure stops before source or Docker state advances."""
    home = tmp_path / "home"
    repository = home / "agent-canon"
    missing_remote = tmp_path / "missing-origin.git"
    home.mkdir()
    repository.mkdir()
    subprocess.run(
        ["git", "-C", str(repository), "init", "-b", "main"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "AgentCanon Test"],
        check=True,
    )
    (repository / "tracked.txt").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-m", "old"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "remote", "add", "origin", str(missing_remote)],
        check=True,
    )
    runtime = repository / ".runtime"
    docker_calls = tmp_path / "docker.calls"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' called >> {str(docker_calls)!r}\n"
        "exit 99\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(home),
            "install",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER": str(docker),
        },
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr.splitlines()[-1])["code"] == "source_remote_unavailable"
    assert (repository / "tracked.txt").read_text(encoding="utf-8") == "old\n"
    assert not runtime.exists()
    assert not docker_calls.exists()
    assert subprocess.run(
        ["git", "-C", str(repository), "symbolic-ref", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "main"


@pytest.mark.parametrize("checkout_state", ["dirty", "detached", "alternate"])
def test_install_source_admission_only_requires_matching_commit(
    tmp_path: Path, checkout_state: str
) -> None:
    """Install admission ignores branch, detached, dirty, and shallow state."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    repository = tmp_path / "agent-canon"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", "--no-hardlinks", str(ROOT), str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "push", str(origin), "HEAD:refs/heads/main"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "clone", "--no-hardlinks", str(origin), str(repository)], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if checkout_state == "dirty":
        with (repository / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("dirty\n")
    elif checkout_state == "detached":
        subprocess.run(["git", "-C", str(repository), "switch", "--detach", head], check=True, capture_output=True)
    else:
        subprocess.run(["git", "-C", str(repository), "switch", "-c", "alternate"], check=True, capture_output=True)
    script = f"""
source {str(ADAPTER)!r}
AGENT_CANON_REPOSITORY_ROOT={str(repository)!r}
AGENT_CANON_RUNTIME_ROOT={str(tmp_path / 'runtime')!r}
_agent_canon_install_source_admission "$AGENT_CANON_REPOSITORY_ROOT" >/dev/null
"""
    completed = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_install_source_admission_rejects_commit_mismatch(tmp_path: Path) -> None:
    """A fetched origin/main mismatch is a typed source admission failure."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    repository = tmp_path / "agent-canon"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "clone", "--no-hardlinks", str(ROOT), str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "push", str(origin), "HEAD:refs/heads/main"], cwd=seed, check=True, capture_output=True)
    subprocess.run(["git", "clone", "--no-hardlinks", str(origin), str(repository)], check=True, capture_output=True)
    with (repository / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("ahead\n")
    subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-m", "ahead"], check=True, capture_output=True)
    script = f"""
source {str(ADAPTER)!r}
AGENT_CANON_REPOSITORY_ROOT={str(repository)!r}
AGENT_CANON_RUNTIME_ROOT={str(tmp_path / 'runtime')!r}
_agent_canon_install_source_admission "$AGENT_CANON_REPOSITORY_ROOT"
"""
    completed = subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)
    assert completed.returncode == 2
    assert '"code":"source_sync_commit_mismatch"' in completed.stderr


def test_source_sync_state_writer_reconciles_terminal_records_atomically(
    tmp_path: Path,
) -> None:
    """Shell sync state clears stale failures and preserves them on interruption."""
    runtime = tmp_path / "runtime"
    script = f"""
source {str(ADAPTER)!r}
set +e
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
_agent_canon_source_sync_write failed old_failure /source \\
  0123456789012345678901234567890123456789 \\
  abcdefabcdefabcdefabcdefabcdefabcdefabcd origin remote-url main \\
  2026-08-27T00:00:00Z old_failure
_agent_canon_source_sync_write success up_to_date /source \\
  0123456789012345678901234567890123456789 \\
  abcdefabcdefabcdefabcdefabcdefabcdefabcd origin remote-url main \\
  2026-08-27T00:00:01Z
cp -- {str(runtime / "source-sync.json")!r} {str(tmp_path / "up-to-date.json")!r}
_agent_canon_source_sync_write success updated /source \\
  1111111111111111111111111111111111111111 \\
  2222222222222222222222222222222222222222 origin remote-url main \\
  2026-08-27T00:00:02Z
cp -- {str(runtime / "source-sync.json")!r} {str(tmp_path / "updated.json")!r}
_agent_canon_source_sync_write failed candidate_failed /source \\
  1111111111111111111111111111111111111111 \\
  2222222222222222222222222222222222222222 origin remote-url main \\
  2026-08-27T00:00:03Z candidate_failed
cp -- {str(runtime / "source-sync.json")!r} {str(tmp_path / "failed.json")!r}
before=$(< {str(runtime / "source-sync.json")!r})
AGENT_CANON_TEST_INTERRUPT_STATE_WRITE=1 _agent_canon_source_sync_write success up_to_date /source \\
  1111111111111111111111111111111111111111 \\
  2222222222222222222222222222222222222222 origin remote-url main \\
  2026-08-27T00:00:04Z
interrupted_rc=$?
test "$interrupted_rc" -eq 99
test "$before" = "$(< {str(runtime / "source-sync.json")!r})"
_agent_canon_source_sync_json
"""
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    up_to_date = json.loads((tmp_path / "up-to-date.json").read_text(encoding="utf-8"))
    updated = json.loads((tmp_path / "updated.json").read_text(encoding="utf-8"))
    failed = json.loads((tmp_path / "failed.json").read_text(encoding="utf-8"))
    final = json.loads(completed.stdout)
    assert up_to_date["status"] == "success"
    assert up_to_date["code"] == "up_to_date"
    assert "failure" not in up_to_date
    assert updated["status"] == "success"
    assert updated["code"] == "updated"
    assert updated["source_head"].startswith("1111")
    assert failed["status"] == "failed"
    assert failed["code"] == "candidate_failed"
    assert failed["failure"] == "candidate_failed"
    assert final == failed
    assert (runtime / "source-sync.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "invalid_state",
    [
        '{"failure":"old","schema":"agent-canon.source-sync.v1","status":"failed","updated_at":"2026-08-26T00:00:00Z"}',
        '{"schema":"agent-canon.source-sync.v1","status":7}',
        '{"schema":"agent-canon.source-sync.v1","status":"success","code":"up_to_date"}',
    ],
)
def test_source_sync_reader_rejects_legacy_missing_and_wrong_type_state(
    tmp_path: Path, invalid_state: str
) -> None:
    """Shell status treats every pre-contract state as unavailable."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "source-sync.json").write_text(invalid_state + "\n", encoding="utf-8")
    script = f"""
source {str(ADAPTER)!r}
set +e
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
if _agent_canon_source_sync_json >/dev/null; then
  exit 7
fi
"""
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_shell_status_reports_invalid_source_sync_as_unavailable(tmp_path: Path) -> None:
    """Shell status and dashboard share the unavailable result for legacy state."""
    repository = tmp_path / "repository"
    control = tmp_path / "control"
    runtime = control / "runtime"
    repository.mkdir()
    control.mkdir()
    runtime.mkdir(parents=True)
    (runtime / "source-sync.json").write_text(
        '{"failure":"old","schema":"agent-canon.source-sync.v1","status":"failed","updated_at":"2026-08-26T00:00:00Z"}\n',
        encoding="utf-8",
    )
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    docker.chmod(0o755)
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": str(docker)},
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["source_sync"] is None


def test_shell_source_sync_publishes_up_to_date_updated_and_failure_state(
    tmp_path: Path,
) -> None:
    """The active shell route records each source-sync terminal result."""
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    install = tmp_path / "install"
    publisher = tmp_path / "publisher"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(seed)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(seed), "config", "user.name", "AgentCanon Test"], check=True)
    (seed / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(seed), "commit", "-m", "one"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "origin", "main"], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(bare), str(install)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(install), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "clone", str(bare), str(publisher)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(publisher), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(publisher), "config", "user.name", "AgentCanon Test"], check=True)

    def run_sync(candidate_rc: int = 0) -> subprocess.CompletedProcess[str]:
        script = f"""
source {str(ADAPTER)!r}
set +e
AGENT_CANON_REPOSITORY_ROOT={str(install)!r}
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(tmp_path / "runtime")!r}
command_args=(sync --install-root {str(install)!r} --remote origin --branch main)
bootstrap_host_entrypoint() {{ return {candidate_rc}; }}
_agent_canon_install_global_links() {{ return 0; }}
_agent_canon_sync_operation
"""
        return subprocess.run(["bash", "-c", script], check=False, capture_output=True, text=True)

    current = run_sync()
    assert current.returncode == 0, current.stderr
    up_to_date = json.loads((tmp_path / "runtime/source-sync.json").read_text(encoding="utf-8"))
    assert up_to_date["status"] == "success"
    assert up_to_date["code"] == "up_to_date"
    (publisher / "tracked.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(publisher), "commit", "-am", "two"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(publisher), "push", "origin", "main"], check=True, capture_output=True)
    updated = run_sync()
    assert updated.returncode == 0, updated.stderr
    updated_state = json.loads((tmp_path / "runtime/source-sync.json").read_text(encoding="utf-8"))
    assert updated_state["status"] == "success"
    assert updated_state["code"] == "updated"
    assert (install / "tracked.txt").read_text(encoding="utf-8") == "two\n"
    (publisher / "tracked.txt").write_text("three\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(publisher), "commit", "-am", "three"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(publisher), "push", "origin", "main"], check=True, capture_output=True)
    failed = run_sync(candidate_rc=7)
    assert failed.returncode == 7
    failed_state = json.loads((tmp_path / "runtime/source-sync.json").read_text(encoding="utf-8"))
    assert failed_state["status"] == "failed"
    assert failed_state["code"] == "source_sync_candidate_failed"
    assert failed_state["failure"] == "source_sync_candidate_failed"
    assert (install / "tracked.txt").read_text(encoding="utf-8") == "two\n"


def test_source_sync_transports_remote_candidate_from_shallow_source(
    tmp_path: Path,
) -> None:
    """A shallow source stages a fetched remote candidate before live merge."""
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    publisher = tmp_path / "publisher"
    install = tmp_path / "install"
    observed = tmp_path / "observed"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(seed)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.name", "AgentCanon Test"],
        check=True,
    )
    (seed / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(seed), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "commit", "-m", "one"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(seed), "branch", "-M", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "remote", "add", "origin", str(bare)], check=True
    )
    subprocess.run(
        ["git", "-C", str(seed), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{bare}", str(install)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "clone", str(bare), str(publisher)], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(publisher),
            "config",
            "user.email",
            "test@example.invalid",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(publisher), "config", "user.name", "AgentCanon Test"],
        check=True,
    )
    (publisher / "tracked.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(publisher), "commit", "-am", "two"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(publisher), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )
    source_head = subprocess.run(
        ["git", "-C", str(install), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    candidate_head = subprocess.run(
        ["git", "-C", str(publisher), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert (
        subprocess.run(
            ["git", "-C", str(install), "rev-parse", "--is-shallow-repository"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "true"
    )

    def run_sync(candidate_rc: int = 0) -> subprocess.CompletedProcess[str]:
        script = f"""
source {str(ADAPTER)!r}
set +e
AGENT_CANON_REPOSITORY_ROOT={str(install)!r}
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(tmp_path / "runtime")!r}
command_args=(sync --install-root {str(install)!r} --remote origin --branch main)
bootstrap_host_entrypoint() {{
  printf 'live:%s\\n' "$(git -C {str(install)!r} rev-parse HEAD)" > {str(observed)!r}
  printf 'staging:%s\\n' "$(git -C "$1" rev-parse HEAD)" >> {str(observed)!r}
  test "$(git -C "$1" rev-parse HEAD)" = {candidate_head!r}
  test "$(git -C "$1" show HEAD:tracked.txt)" = two
  return {candidate_rc}
}}
_agent_canon_install_global_links() {{ return 0; }}
_agent_canon_sync_operation
"""
        return subprocess.run(
            ["bash", "-c", script], check=False, capture_output=True, text=True
        )

    failed = run_sync(candidate_rc=7)
    assert failed.returncode == 7, failed.stderr
    failed_observed = dict(
        line.split(":", 1)
        for line in observed.read_text(encoding="utf-8").splitlines()
    )
    assert failed_observed == {"live": source_head, "staging": candidate_head}
    assert (
        subprocess.run(
            ["git", "-C", str(install), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == source_head
    )
    assert (install / "tracked.txt").read_text(encoding="utf-8") == "one\n"

    completed = run_sync()
    assert completed.returncode == 0, completed.stderr
    observed_heads = dict(
        line.split(":", 1)
        for line in observed.read_text(encoding="utf-8").splitlines()
    )
    assert observed_heads == {"live": source_head, "staging": candidate_head}
    assert (
        subprocess.run(
            ["git", "-C", str(install), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == candidate_head
    )
    assert (install / "tracked.txt").read_text(encoding="utf-8") == "two\n"


def test_target_mount_manifest_is_strict_and_reused_on_create() -> None:
    """Target mounts are emitted as allowlisted TSV and applied by host Docker."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "mounts.tsv" in text
    assert 'target_mount_args+=(--mount "type=bind,src=$target_source,dst=$target_destination,readonly")' in text
    assert 'target mount destination or mode is invalid' in text


def test_structured_exec_target_digest_is_shell_validated_before_container_handoff() -> None:
    """Structured requests carry a typed digest; the shell never parses JSON."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "_agent_canon_extract_exec_target_digest" in text
    assert "--target-digest" in text
    assert 'AGENT_CANON_STATE_ROOT/mounts.tsv' in text
    assert 'AGENT_CANON_TARGET_DIGEST=$digest' in text
    assert 'install|update|start|stop|rollback|uninstall|target|tool|template|task|gc|eval|exec)' in text
    assert '" ${command_args[*]} " == *" --request-json "*' not in text


def test_exec_child_request_json_does_not_switch_to_structured_mode(tmp_path: Path) -> None:
    """A child argv token after ``--`` remains a generic exec command."""
    script = (
        f'source "{ADAPTER}"\n'
        'command_args=(exec --root /tmp/target -- tool --request-json value)\n'
        '_agent_canon_exec_is_structured_request\n'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_exec_request_json_before_separator_uses_typed_digest(tmp_path: Path) -> None:
    """A pre-separator request option consumes its digest and preserves its value."""
    state_root = tmp_path / "state"
    target = tmp_path / "target"
    state_root.mkdir()
    target.mkdir()
    digest = "typed-target"
    (state_root / "mounts.tsv").write_text(
        f"target\t{digest}\t{target}\t/targets/{digest}\tread-only\n",
        encoding="utf-8",
    )
    script = (
        f'source "{ADAPTER}"\n'
        f'AGENT_CANON_STATE_ROOT="{state_root}"\n'
        'AGENT_CANON_DOCKER_CMD=true\n'
        f'command_args=(exec --request-json "quoted value" --target-digest={digest})\n'
        '_agent_canon_exec_is_structured_request\n'
        '_agent_canon_extract_exec_target_digest\n'
        'printf "%s\\n" "$AGENT_CANON_TARGET_DIGEST" "${command_args[*]}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [digest, f'exec --request-json quoted value --target-digest {digest}']


def test_private_log_source_is_read_back_from_the_owned_mount() -> None:
    """Structured handoff uses the versioned private-log volume projection."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "_agent_canon_validate_private_log_mount" in text
    assert "AGENT_CANON_PRIVATE_LOG_ROOT=$AGENT_CANON_PRIVATE_LOG_DESTINATION" in text
    assert "_agent_canon_volume_copy import private-log" in text
    assert 'AGENT_CANON_PRIVATE_LOG_DESTINATION"' in text
    assert 'control_parent_root / "private-log"' not in (
        ROOT / "tools/runtime/container/bootstrap_runtime.py"
    ).read_text(encoding="utf-8")


def test_uninstall_preserves_foreign_links_and_restores_owned_config() -> None:
    """Uninstall scopes symlink removal by exact AgentCanon source prefixes."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "_agent_canon_remove_global_links" in text
    assert '"$skill_source_root"/*' in text
    assert '"$AGENT_CANON_REPOSITORY_ROOT/.codex/agents"/*' in text
    assert "cp --preserve=mode,timestamps" in text
    remove_section = text.split("_agent_canon_remove_global_links()", 1)[1].split(
        "_agent_canon_install_global_links()", 1
    )[0]
    assert 'for link in "$home_root/.agents/skills"/*' not in remove_section
    assert 'for link in "$home_root/.codex/agents"/*' not in remove_section


def test_container_controller_routes_non_docker_public_operations() -> None:
    """Documented non-Docker operations enter the resident Python owner."""
    controller = (ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text(
        encoding="utf-8"
    )
    for marker in (
        'if operation == "tool" and args.tool_operation == "run":',
        'if operation == "template" and args.template_operation == "export":',
        'if operation == "eval" and args.eval_operation == "collect":',
        'if operation == "task" and args.task_operation == "admit":',
        'if operation == "gc":',
        'if operation == "codex":',
        'if operation == "source-identity":',
    ):
        assert marker in controller


def test_host_configuration_is_fixed_and_not_a_toml_parser() -> None:
    """Pre-container configuration stays in fixed shell constants."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "AGENT_CANON_CONTAINER_CPUS=2" in text
    assert "AGENT_CANON_RUNTIME_DESTINATION=" in text
    assert "source \"$AGENT_CANON_REPOSITORY_ROOT/bootstrap/" not in text


def test_container_create_maps_caller_without_fixed_user_policy() -> None:
    """Resident creation inherits the invoking host UID/GID without policy overrides."""
    text = ADAPTER.read_text(encoding="utf-8")
    create = text.split('"$AGENT_CANON_DOCKER_CMD" create', 1)[1].split(
        '"$AGENT_CANON_IMAGE_REF"', 1
    )[0]
    assert "_agent_canon_caller_user" in text
    assert "caller_uid=$(id -u)" in text
    assert "caller_gid=$(id -g)" in text
    assert "local caller_user" in text
    assert '--user "$caller_user"' in create
    assert "AGENT_CANON_FIXED_UID" not in text
    assert "AGENT_CANON_USER" not in text
    dockerfile = (ROOT / "bootstrap/container/image/Dockerfile").read_text(encoding="utf-8")
    assert not any(line.lstrip().startswith("USER ") for line in dockerfile.splitlines())


def test_help_does_not_require_python_or_docker(tmp_path: Path) -> None:
    """Help is a shell-only route and is usable before image installation."""
    python_sentinel = tmp_path / "python3"
    python_sentinel.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    python_sentinel.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    completed = subprocess.run(
        [str(BOOTSTRAP), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0
    assert "AgentCanon Python and Rust" in completed.stdout


@pytest.mark.parametrize("operation", ["install", "update", "status", "sync"])
def test_operation_help_has_no_path_or_docker_side_effects(
    tmp_path: Path, operation: str
) -> None:
    """Operation help exits before validating or preparing any host state."""
    control = tmp_path / "missing-control"
    runtime = tmp_path / "missing-runtime"
    docker = tmp_path / "docker-counter"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' called >> {tmp_path / 'docker.calls'}\n"
        "exit 99\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(tmp_path / "missing-repository"),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(runtime),
            operation,
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": str(docker)},
    )
    assert completed.returncode == 0, completed.stderr
    assert f"bootstrap.sh {operation}" in completed.stdout
    assert not control.exists()
    assert not runtime.exists()
    assert not (tmp_path / "docker.calls").exists()


def _gc_fixture(
    tmp_path: Path,
    *,
    runtime: bool = True,
    active: tuple[str, str] | None = None,
    rollback: tuple[str, str] | None = None,
) -> tuple[dict, dict, Path, Path, Path, Path, str, dict[str, str]]:
    """Build a small Docker/runtime fixture for host GC contract tests."""
    control = tmp_path / "control"
    control.mkdir()
    # Use this Git checkout as a read-only source root; the explicit runtime
    # remains entirely inside the test-owned control root.
    repository = ROOT
    runtime_root = control / "runtime"
    if runtime:
        (runtime_root / "host-state").mkdir(parents=True)
        (runtime_root / "container-state").mkdir()
        (runtime_root / "host-state" / "replacement.lock").touch()
    digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    container_name = f"agent-canon-tools-{digest[:16]}"
    owned = {
        "io.agent-canon.runtime": "shared-v1",
        "io.agent-canon.control-root-digest": digest,
    }
    foreign = {
        "io.agent-canon.runtime": "shared-v1",
        "io.agent-canon.control-root-digest": "foreign-control",
    }

    def image(image_id: str, labels: dict[str, str]) -> dict:
        return {"Id": image_id, "Config": {"Labels": labels}}

    def container(container_id: str, image_ref: str, labels: dict[str, str]) -> dict:
        return {
            "Id": container_id,
            "Name": "/unused",
            "Config": {"Image": image_ref, "Labels": labels},
            "State": {"Running": False, "Health": {"Status": "healthy"}},
            "Mounts": [],
        }

    live_ref = "agent-canon-tools:live"
    stale_ref = "agent-canon-tools:stale"
    foreign_ref = "foreign-tools:keep"
    live_id = "sha256:" + "1" * 64
    stale_id = "sha256:" + "2" * 64
    foreign_id = "sha256:" + "3" * 64
    images = {
        live_ref: image(live_id, owned),
        stale_ref: image(stale_id, owned),
        foreign_ref: image(foreign_id, foreign),
    }
    containers = {
        container_name: container("container-live", live_ref, owned),
        "agent-canon-tools-stale": container("container-stale", stale_ref, owned),
        "foreign-resident": container("container-foreign", foreign_ref, foreign),
    }
    containers[container_name]["Name"] = "/" + container_name
    containers["agent-canon-tools-stale"]["Name"] = "/agent-canon-tools-stale"
    containers["foreign-resident"]["Name"] = "/foreign-resident"
    state = {"images": images, "containers": containers, "next": 1}
    state_path = tmp_path / "docker-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    if active is not None:
        active_ref, active_id = active
        (runtime_root / "host-state" / "active-image.tsv").write_text(
            "schema\tagent-canon.active-image.v1\n"
            f"image-ref\t{active_ref}\nimage-id\t{active_id}\n",
            encoding="utf-8",
        )
    if rollback is not None:
        rollback_ref, rollback_id = rollback
        (runtime_root / "container-state" / "rollback-plan.tsv").write_text(
            "schema\tagent-canon.rollback-plan.v1\n"
            f"image-id\t{rollback_id}\nimage-ref\t{rollback_ref}\n",
            encoding="utf-8",
        )
    calls_path = tmp_path / "docker.calls"
    fake_docker = ROOT / "tests" / "bootstrap" / "fake_docker.py"
    environment = {
        **os.environ,
        "AGENT_CANON_DOCKER": str(fake_docker),
        "FAKE_DOCKER_STATE": str(state_path),
        "FAKE_DOCKER_CALLS": str(calls_path),
    }
    return (
        state,
        owned,
        repository,
        control,
        runtime_root,
        state_path,
        container_name,
        environment,
    )


def _run_gc(
    repository: Path,
    control: Path,
    runtime: Path,
    environment: dict[str, str],
    *,
    dry_run: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the public GC route against the fixture Docker executable."""
    command = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(control),
        "--runtime-root",
        str(runtime),
        "gc",
    ]
    if dry_run:
        command.append("--dry-run")
    return subprocess.run(
        command, check=False, capture_output=True, text=True, env=environment
    )


def test_gc_dry_run_does_not_create_or_chmod_runtime_files(tmp_path: Path) -> None:
    """A preview is immutable, including when the runtime is absent."""
    _state, _owned, repository, control, runtime, state_path, _name, environment = (
        _gc_fixture(tmp_path, runtime=False)
    )
    completed = _run_gc(repository, control, runtime, environment, dry_run=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["code"] == "gc_plan"
    assert not runtime.exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["containers"]


def test_gc_keeps_live_resident_over_stale_persisted_container_id(
    tmp_path: Path,
) -> None:
    """The live named resident wins over a stale persisted container ID."""
    state, _owned, repository, control, runtime, state_path, name, environment = (
        _gc_fixture(tmp_path)
    )
    (runtime / "container-state" / "state.json").write_text(
        json.dumps({"container_id": "container-stale"}), encoding="utf-8"
    )
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["containers"][name]["Id"] == state["containers"][name]["Id"]
    assert "agent-canon-tools-stale" not in result["containers"]


def test_gc_keeps_live_resident_untagged_image_by_immutable_id(
    tmp_path: Path,
) -> None:
    """A live image without a tag remains protected by its immutable ID."""
    state, _owned, repository, control, runtime, state_path, name, environment = (
        _gc_fixture(tmp_path)
    )
    live_ref = state["containers"][name]["Config"]["Image"]
    live_image = state["images"].pop(live_ref)
    live_id = live_image["Id"]
    state["images"][f"untagged:{live_id}"] = live_image
    state["containers"][name]["Config"]["Image"] = live_id
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert f"untagged:{live_id}" in result["images"]


def test_gc_keeps_shared_active_and_rollback_image_id(tmp_path: Path) -> None:
    """Shared active/rollback identity is retained once by exact image ID."""
    shared_id = "sha256:" + "4" * 64
    active_ref = "agent-canon-tools:active"
    rollback_ref = "agent-canon-tools:rollback"
    state, owned, repository, control, runtime, state_path, _name, environment = (
        _gc_fixture(
            tmp_path,
            active=(active_ref, shared_id),
            rollback=(rollback_ref, shared_id),
        )
    )
    state["images"][active_ref] = {
        "Id": shared_id,
        "Config": {"Labels": owned},
    }
    state["images"][rollback_ref] = {
        "Id": shared_id,
        "Config": {"Labels": owned},
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert result["images"][active_ref]["Id"] == shared_id
    assert result["images"][rollback_ref]["Id"] == shared_id
    assert "agent-canon-tools:stale" not in result["images"]


def test_gc_removes_only_exact_stale_owned_resources(tmp_path: Path) -> None:
    """Stale owned IDs and tag references are the only Docker removals."""
    _state, _owned, repository, control, runtime, state_path, _name, environment = (
        _gc_fixture(tmp_path)
    )
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert "agent-canon-tools:stale" not in result["images"]
    assert "agent-canon-tools-stale" not in result["containers"]


def test_gc_preserves_foreign_resources(tmp_path: Path) -> None:
    """Foreign control-root labels are outside the cleanup set."""
    _state, _owned, repository, control, runtime, state_path, _name, environment = (
        _gc_fixture(tmp_path)
    )
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert "foreign-tools:keep" in result["images"]
    assert "foreign-resident" in result["containers"]


def test_gc_invokes_container_state_gc_and_combines_receipt(tmp_path: Path) -> None:
    """Host Docker cleanup retains the resident controller state transition."""
    _state, _owned, repository, control, runtime, _state_path, _name, environment = (
        _gc_fixture(tmp_path)
    )
    completed = _run_gc(repository, control, runtime, environment)
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["details"]["state"]["code"] == "state_gc_complete"
    calls = (tmp_path / "docker.calls").read_text(encoding="utf-8")
    assert "exec" in calls and "gc" in calls


def test_resident_replacement_lock_serializes_only_the_replacement(
    tmp_path: Path,
) -> None:
    """Concurrent replacement callbacks cannot overlap on one runtime."""
    runtime = tmp_path / "runtime"
    (runtime / "host-state").mkdir(parents=True)
    events = tmp_path / "events"
    script = f'''
set -eu
source {str(ADAPTER)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
_agent_canon_replace_resident_locked() {{
  printf '%s start\\n' "$AGENT_CANON_TEST_LABEL" >> {str(events)!r}
  sleep 0.15
  printf '%s end\\n' "$AGENT_CANON_TEST_LABEL" >> {str(events)!r}
}}
_agent_canon_replace_resident candidate sha256:candidate
'''
    environment = {**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    first = subprocess.Popen(
        ["bash", "-c", script],
        env={**environment, "AGENT_CANON_TEST_LABEL": "first"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    second = subprocess.Popen(
        ["bash", "-c", script],
        env={**environment, "AGENT_CANON_TEST_LABEL": "second"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    first_output, first_error = first.communicate(timeout=5)
    second_output, second_error = second.communicate(timeout=5)
    assert first.returncode == 0, first_error or first_output
    assert second.returncode == 0, second_error or second_output
    assert events.read_text(encoding="utf-8").splitlines() in (
        ["first start", "first end", "second start", "second end"],
        ["second start", "second end", "first start", "first end"],
    )


def test_replacement_candidate_inspect_failure_stops_before_transaction_callbacks(
    tmp_path: Path,
) -> None:
    """A missing candidate is reported before ensure or state publication."""
    runtime = tmp_path / "runtime"
    (runtime / "host-state").mkdir(parents=True)
    marker = tmp_path / "callbacks"
    docker_calls = tmp_path / "docker.calls"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' docker >> {str(docker_calls)!r}\n"
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(runtime / "container-state")!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
_agent_canon_ensure_container() {{ printf '%s\\n' ensure >> {str(marker)!r}; return 9; }}
_agent_canon_record_active_container() {{ printf '%s\\n' active >> {str(marker)!r}; return 0; }}
_agent_canon_replace_resident candidate sha256:candidate
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 2
    assert '"code":"candidate_image_missing"' in completed.stderr
    assert not marker.exists()
    assert "up_to_date" not in completed.stdout


def test_replacement_ensure_failure_does_not_publish_active_state(
    tmp_path: Path,
) -> None:
    """A failed candidate ensure returns a typed error before active write."""
    runtime = tmp_path / "runtime"
    (runtime / "host-state").mkdir(parents=True)
    marker = tmp_path / "callbacks"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:candidate\\n'; exit 0; fi\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then exit 1; fi\n"
        "if [[ \"$1:$2\" == image:rm ]]; then exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(runtime / "container-state")!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
_agent_canon_ensure_container() {{ printf '%s\\n' ensure >> {str(marker)!r}; return 9; }}
_agent_canon_record_active_container() {{ printf '%s\\n' active >> {str(marker)!r}; return 0; }}
_agent_canon_replace_resident candidate requested
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 2
    assert '"code":"candidate_unhealthy"' in completed.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["ensure"]
    assert not (runtime / "host-state" / "active-image.tsv").exists()
    assert "up_to_date" not in completed.stdout


def test_replacement_rollback_failure_is_reported_after_controller_failure(
    tmp_path: Path,
) -> None:
    """A failed recovery path remains a typed rollback failure."""
    runtime = tmp_path / "runtime"
    (runtime / "host-state").mkdir(parents=True)
    (runtime / "container-state").mkdir()
    docker = tmp_path / "docker"
    control_digest = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:candidate\\n'; fi\n"
        "if [[ \"$1:$2\" == container:inspect && \"$4\" == '{{.Id}}' ]]; then printf 'container-old\\n'; fi\n"
        "if [[ \"$1:$2\" == container:inspect && \"$4\" == *io.agent-canon.runtime* ]]; then printf 'shared-v1\\n'; fi\n"
        f"if [[ \"$1:$2\" == container:inspect && \"$4\" == *io.agent-canon.control-root-digest* ]]; then printf '{control_digest}\\n'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(runtime / "container-state")!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
mkdir -p "$AGENT_CANON_STATE_ROOT"
: > "$AGENT_CANON_STATE_ROOT/mounts.tsv"
_agent_canon_use_active_image() {{
  AGENT_CANON_IMAGE_REF=old-ref
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:old
  AGENT_CANON_EXPECTED_IMAGE_ID=sha256:old
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}}
_agent_canon_validate_existing_container() {{ :; }}
_agent_canon_write_rollback_plan() {{ :; }}
_agent_canon_ensure_container() {{ printf 'candidate\\n'; }}
_agent_canon_run_controller() {{ return 9; }}
_agent_canon_restore_candidate_failure() {{ return 7; }}
_agent_canon_replace_resident candidate requested
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 2
    assert '"code":"rollback_failed"' in completed.stderr
    assert "up_to_date" not in completed.stdout


@pytest.mark.parametrize(
    ("control_label", "mounts", "expected_rc", "expected_code", "expect_teardown"),
    [
        ("owned", "", 0, None, True),
        ("foreign", "", 2, "container_ownership_mismatch", False),
        (
            "owned",
            "target\tmissing-digest\t/tmp/does-not-exist\t/targets/missing-digest\tread-only\n",
            0,
            None,
            True,
        ),
        (
            "owned",
            "target\tbroad-digest\t__CONTROL_ROOT__\t/targets/broad-digest\tread-only\n",
            2,
            "mount_manifest_invalid",
            False,
        ),
    ],
)
def test_owned_resident_replacement_classifies_before_drift_and_teardown(
    tmp_path: Path,
    control_label: str,
    mounts: str,
    expected_rc: int,
    expected_code: str | None,
    expect_teardown: bool,
) -> None:
    """Repair owned drift, but preserve foreign or invalid-target residents."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    (runtime / "host-state").mkdir(parents=True)
    state_root.mkdir()
    mounts = mounts.replace("__CONTROL_ROOT__", str(tmp_path))
    (state_root / "mounts.tsv").write_text(mounts, encoding="utf-8")
    marker = tmp_path / "docker.calls"
    control_digest = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()
    owner_label = control_digest if control_label == "owned" else "foreign-control-root"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(marker)!r}\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:candidate\\n'; exit 0; fi\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then\n"
        "  if [[ \"${4:-}\" == '{{.Id}}' ]]; then printf 'container-old\\n'; fi\n"
        "  if [[ \"${4:-}\" == *io.agent-canon.runtime* ]]; then printf 'shared-v1\\n'; fi\n"
        f"  if [[ \"${{4:-}}\" == *io.agent-canon.control-root-digest* ]]; then printf '{owner_label}\\n'; fi\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
_agent_canon_use_active_image() {{
  AGENT_CANON_IMAGE_REF=candidate
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:candidate
  AGENT_CANON_EXPECTED_IMAGE_ID=sha256:candidate
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}}
_agent_canon_validate_existing_container() {{ return 9; }}
_agent_canon_write_rollback_plan() {{ :; }}
_agent_canon_ensure_container() {{ printf 'candidate\\n'; }}
    _agent_canon_run_controller() {{ :; }}
    _agent_canon_record_active_container() {{ :; }}
    _agent_canon_install_global_links() {{ :; }}
    _agent_canon_publish_controller_projection() {{ :; }}
    _agent_canon_replace_resident candidate requested
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == expected_rc
    if expected_code is not None:
        assert f'"code":"{expected_code}"' in completed.stderr
    calls = marker.read_text(encoding="utf-8").splitlines()
    teardown = any(call.startswith("stop ") for call in calls) and any(
        call.startswith("rm ") for call in calls
    )
    assert teardown is expect_teardown


def test_replacement_preserves_resident_when_identity_changes_before_teardown(
    tmp_path: Path,
) -> None:
    """Recheck the captured ID/labels under lock before any stop or rm."""
    runtime = tmp_path / "runtime"
    state_root = runtime / "container-state"
    (runtime / "host-state").mkdir(parents=True)
    state_root.mkdir()
    (state_root / "mounts.tsv").write_text("", encoding="utf-8")
    calls = tmp_path / "docker.calls"
    id_reads = tmp_path / "id-reads"
    id_reads.write_text("0\n", encoding="utf-8")
    control_digest = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(calls)!r}\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:candidate\\n'; exit 0; fi\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then\n"
        f"  if [[ \"${{4:-}}\" == *Id* ]]; then n=$(< {str(id_reads)!r}); n=$((n + 1)); printf '%s\\n' \"$n\" > {str(id_reads)!r}; if ((n == 1)); then printf 'container-old\\n'; else printf 'container-new\\n'; fi; fi\n"
        "  if [[ \"${4:-}\" == *io.agent-canon.runtime* ]]; then printf 'shared-v1\\n'; fi\n"
        f"  if [[ \"${{4:-}}\" == *io.agent-canon.control-root-digest* ]]; then printf '{control_digest}\\n'; fi\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    script = f'''
source {str(ADAPTER)!r}
set +e
AGENT_CANON_CONTROL_ROOT={str(tmp_path)!r}
AGENT_CANON_RUNTIME_ROOT={str(runtime)!r}
AGENT_CANON_STATE_ROOT={str(state_root)!r}
AGENT_CANON_DOCKER_CMD={str(docker)!r}
_agent_canon_use_active_image() {{
  AGENT_CANON_IMAGE_REF=old-ref
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:old
  AGENT_CANON_EXPECTED_IMAGE_ID=sha256:old
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}}
_agent_canon_write_rollback_plan() {{ :; }}
_agent_canon_replace_resident candidate requested
rc=$?
printf 'rc=%s\\n' "$rc"
exit "$rc"
'''
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 2
    assert '"code":"replacement_readback_failed"' in completed.stderr
    calls_text = calls.read_text(encoding="utf-8")
    assert "stop " not in calls_text
    assert "rm " not in calls_text


@pytest.mark.parametrize("operation", ["update"])
def test_install_update_reject_foreign_before_build_or_state_mutation(
    tmp_path: Path, operation: str
) -> None:
    """Update ownership preflight precedes build and runtime setup."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    repository.mkdir()
    control.mkdir()
    calls = tmp_path / "docker.calls"
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        f"printf '%s\\n' \"$*\" >> {str(calls)!r}\n"
        "if [[ \"$1:$2\" == container:inspect ]]; then\n"
        "  if [[ \"${4:-}\" == *io.agent-canon.runtime* ]]; then printf 'shared-v1\\n'; fi\n"
        "  if [[ \"${4:-}\" == *io.agent-canon.control-root-digest* ]]; then printf 'foreign-control-root\\n'; fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == build ]]; then exit 99; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            operation,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AGENT_CANON_DOCKER": str(docker)},
    )
    assert completed.returncode == 2
    assert '"code":"container_ownership_mismatch"' in completed.stderr
    assert "build " not in calls.read_text(encoding="utf-8")
    assert not (repository / ".runtime").exists()


@pytest.mark.parametrize("operation", ["install", "update"])
def test_gpu006_stale_source_sync_mount_is_recreated_by_public_route(
    tmp_path: Path, operation: str
) -> None:
    """GPU006 fixture: old owned resident converges through install/update."""
    fixture = json.loads(GPU006_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["fixture"] == "GPU006 stale source-sync mount"
    assert fixture["resident"]["missing_mounts"] == [
        "/var/lib/agent-canon/source-sync.json"
    ]
    repository = tmp_path / "agent-canon"
    # Both routes use a local origin.  Install deliberately exercises a
    # detached checkout whose HEAD already matches origin/main; source
    # admission must not require a branch name or a clean worktree.
    control = tmp_path
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "update-ref", "refs/heads/main", "HEAD"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "remote", "set-url", "origin", str(repository)],
        check=True,
    )
    if operation == "install":
        current_head = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(repository), "switch", "--detach", current_head],
            check=True,
            capture_output=True,
        )
    runtime = repository / ".runtime"
    state_path = tmp_path / "docker-state.json"
    calls_path = tmp_path / "docker-calls"
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    resident = fixture["resident"]
    old_image_ref = resident["image_ref"]
    old_image_id = resident["image_id"]
    container_name = f"agent-canon-tools-{control_digest[:16]}"
    private_log = tmp_path / "agent-canon-log"
    valid_target = tmp_path / "valid-target"
    valid_target.mkdir()
    stale_target = tmp_path / "removed-agent-canon"
    stale_digest = hashlib.sha256(str(stale_target).encode("utf-8")).hexdigest()
    valid_digest = hashlib.sha256(str(valid_target).encode("utf-8")).hexdigest()
    mount_manifest = runtime / "container-state" / "mounts.tsv"
    mount_manifest.parent.mkdir(parents=True)
    mount_manifest.write_text(
        f"target\t{stale_digest}\t{stale_target}\t/targets/{stale_digest}\tread-only\n"
        f"target\t{valid_digest}\t{valid_target}\t/targets/{valid_digest}\tread-only\n",
        encoding="utf-8",
    )
    old_mount_sources = {
        "container-state": (runtime / "container-state", "/var/lib/agent-canon/runtime", True),
        "private-log": (private_log, "/var/lib/agent-canon/private-log", False),
        "mount-registry": (runtime / "container-state" / "mounts.toml", "/var/lib/agent-canon/mount-registry.toml", False),
    }
    old_mounts = [
        {"Type": "bind", "Source": str(source), "Destination": destination, "RW": rw, "Mode": "rw" if rw else "ro"}
        for source, destination, rw in old_mount_sources.values()
    ]
    assert fixture["expected"]["source_sync_mount"] not in {
        mount["Destination"] for mount in old_mounts
    }
    old_labels = {
        key: value.replace("CONTROL_ROOT_DIGEST", control_digest)
        for key, value in resident["labels"].items()
    }
    state_path.write_text(
        json.dumps(
            {
                "images": {
                    old_image_ref: {
                        "Id": old_image_id,
                        "RepoTags": [old_image_ref],
                        "Config": {"Labels": old_labels},
                    }
                },
                "containers": {
                    container_name: {
                        "Id": resident["id"],
                        "Name": "/" + container_name,
                        "Config": {"Image": old_image_ref, "Labels": old_labels},
                        "State": {"Running": True, "Health": {"Status": "healthy"}},
                        "HostConfig": {
                            "ReadonlyRootfs": True,
                            "NetworkMode": "none",
                            "Memory": 4294967296,
                            "PidsLimit": 512,
                            "NanoCpus": 2000000000,
                            "CapDrop": ["ALL"],
                            "SecurityOpt": ["no-new-privileges"],
                            "Tmpfs": {"/tmp": ""},
                        },
                        "Mounts": old_mounts,
                        "MountSnapshots": {},
                    }
                },
                "next": 1,
                "next_image": 2,
            }
        ),
        encoding="utf-8",
    )
    fake_docker = ROOT / "tests" / "bootstrap" / "fake_docker.py"
    events = tmp_path / "events"
    tool_bin = tmp_path / "tool-bin"
    tool_bin.mkdir()
    git_wrapper = tool_bin / "git"
    git_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "for argument in \"$@\"; do\n"
        "  if [[ \"$argument\" == fetch ]]; then\n"
        f"    printf '%s\\n' git-fetch >> {str(events)!r}\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "exec /usr/bin/git \"$@\"\n",
        encoding="utf-8",
    )
    git_wrapper.chmod(0o755)
    completed = subprocess.run(
        [
            "timeout",
            "60s",
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            operation,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "PATH": f"{tool_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "AGENT_CANON_DOCKER": str(fake_docker),
            "FAKE_DOCKER_STATE": str(state_path),
            "FAKE_DOCKER_CALLS": str(calls_path),
            "FAKE_DOCKER_EVENTS": str(events),
            "FAKE_DOCKER_VALID_IMAGE_IDS": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert "container_ownership_mismatch" not in completed.stderr
    receipts = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
    assert receipts[-1]["status"] == "ok"
    assert receipts[-1]["operation"] == operation
    result = json.loads(state_path.read_text(encoding="utf-8"))
    assert resident["id"] not in {
        record["Id"] for record in result["containers"].values()
    }
    replacement = result["containers"][container_name]
    assert replacement["Config"]["Image"] != old_image_ref
    assert replacement["Config"]["Labels"] == {
        "io.agent-canon.runtime": "shared-v1",
        "io.agent-canon.control-root-digest": control_digest,
    }
    assert result["images"][replacement["Config"]["Image"]]["Id"] != old_image_id
    assert replacement["State"]["Health"]["Status"] == fixture["expected"]["health"]
    if operation == "install":
        assert events.read_text(encoding="utf-8").splitlines()[:2] == [
            "git-fetch",
            "docker",
        ]
        source_sync = json.loads(
            (runtime / "source-sync.json").read_text(encoding="utf-8")
        )
        source_head = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert source_sync["status"] == "success"
        assert source_sync["source_head"] == source_head
        assert result["images"][replacement["Config"]["Image"]]["Config"]["Labels"][
            "io.agent-canon.source-revision"
        ] == source_head
    expected_mounts = {
        "/var/lib/agent-canon",
    }
    expected_mounts.add(f"/targets/{valid_digest}")
    assert {mount["Destination"] for mount in replacement["Mounts"]} == expected_mounts
    assert f"/targets/{stale_digest}" not in {
        mount["Destination"] for mount in replacement["Mounts"]
    }
    security = fixture["expected"]["security"]
    assert replacement["HostConfig"]["ReadonlyRootfs"] is security["readonly_rootfs"]
    assert replacement["HostConfig"]["NetworkMode"] == security["network"]
    assert replacement["HostConfig"]["NanoCpus"] == security["cpus"]
    assert replacement["HostConfig"]["Memory"] == security["memory"]
    assert replacement["HostConfig"]["PidsLimit"] == security["pids"]
    assert replacement["HostConfig"]["CapDrop"] == security["cap_drop"]
    assert replacement["HostConfig"]["SecurityOpt"] == security["security_opt"]
    calls = calls_path.read_text(encoding="utf-8").splitlines()
    build_index = next(index for index, call in enumerate(calls) if call.startswith("build\t"))
    stop_index = next(index for index, call in enumerate(calls) if call.startswith("stop\t"))
    if operation == "install":
        assert stop_index < build_index
    else:
        assert build_index < stop_index
    assert resident["id"] in calls[stop_index]
    assert any(old_image_id in call for call in calls if call.startswith("tag\t"))
    if operation == "install":
        assert subprocess.run(
            ["git", "-C", str(repository), "symbolic-ref", "--quiet", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        ).returncode != 0
        assert subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() == subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "origin/main"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


def test_public_clean_install_materializes_source_view_and_first_target(
    tmp_path: Path,
) -> None:
    """Install from empty state, then reconstruct over stale runtime residue."""
    home = tmp_path / "home"
    home.mkdir()
    origin = tmp_path / "origin.git"
    publisher = tmp_path / "publisher"
    subprocess.run(
        ["git", "init", "--bare", str(origin)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(publisher)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(publisher), "push", str(origin), "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
    )
    repository = home / "agent-canon"
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(origin), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "branch", "-M", "main"],
        check=True,
        capture_output=True,
    )
    legacy_runtime = home / "workspace" / "agent-canon-runtime" / "host"
    fake_state = tmp_path / "docker-state.json"
    fake_docker = ROOT / "tests" / "bootstrap" / "fake_docker.py"
    environment = {
        **os.environ,
        "HOME": str(home),
        "AGENT_CANON_DOCKER": str(fake_docker),
        "FAKE_DOCKER_STATE": str(fake_state),
        "FAKE_DOCKER_VALID_IMAGE_IDS": "1",
    }
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(home),
        "--runtime-root",
        str(legacy_runtime),
    ]
    personal_skills = repository / ".codex" / "personal" / "skills"
    assert not (repository / ".runtime").exists()
    assert not personal_skills.exists()

    installed = subprocess.run(
        [*common, "install"], check=False, capture_output=True, text=True, env=environment
    )
    assert installed.returncode == 0, installed.stderr
    assert (repository / ".runtime").is_dir()
    assert personal_skills.is_dir()
    assert list(personal_skills.glob("*/SKILL.md"))
    assert not legacy_runtime.exists()
    assert subprocess.run(
        ["git", "-C", str(repository), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "main"
    assert subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "origin/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    started = subprocess.run(
        [*common, "start"], check=False, capture_output=True, text=True, env=environment
    )
    assert started.returncode == 0, started.stderr
    added = subprocess.run(
        [
            *common,
            "target",
            "add",
            "--root",
            str(repository),
            "--mode",
            "read-only",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert added.returncode == 0, added.stderr
    mounts = (repository / ".runtime" / "container-state" / "mounts.tsv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(mounts) == 1
    assert mounts[0].split("\t")[2] == str(repository.resolve())

    wrapper = subprocess.run(
        [str(repository / "tools" / "bin" / "agent-canon"), "--version"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **environment,
            "AGENT_CANON_CONTROL_PARENT_ROOT": str(home),
            "AGENT_CANON_RUNTIME_ROOT": str(legacy_runtime),
        },
    )
    assert wrapper.returncode == 0, wrapper.stderr
    assert wrapper.stdout.strip() == "agent-canon 0.1.0"

    # Keep an unrelated image in the daemon while the second install replaces
    # the resident.  Cleanup must remove only the generated rollback tag and
    # must leave the active image (even when both tags resolve to one ID) and
    # unrelated images untouched.
    foreign_ref = "foreign-tools:keep"
    foreign_id = "sha256:" + "f" * 64
    docker_state = json.loads(fake_state.read_text(encoding="utf-8"))
    docker_state["images"][foreign_ref] = {
        "Id": foreign_id,
        "RepoTags": [foreign_ref],
        "Config": {"Labels": {}},
        "SourceRoot": str(ROOT),
    }
    fake_state.write_text(json.dumps(docker_state), encoding="utf-8")

    state_root = repository / ".runtime" / "container-state"
    docker_state = json.loads(fake_state.read_text(encoding="utf-8"))
    control_digest = hashlib.sha256(str(home.resolve()).encode("utf-8")).hexdigest()
    volume_root = Path(
        docker_state["volumes"][f"agent-canon-runtime-{control_digest}"]["Mountpoint"]
    )
    stale_target = home / "removed-agent-canon"
    stale_digest = hashlib.sha256(str(stale_target).encode("utf-8")).hexdigest()
    stale_state = json.loads((volume_root / "runtime" / "state.json").read_text(encoding="utf-8"))
    stale_state["targets"] = {
        stale_digest: {
            "root": str(stale_target),
            "host_root": str(stale_target),
            "mode": "read-only",
            "digest": stale_digest,
        }
    }
    stale_state["rollback_generation"] = "generation-stale"
    (volume_root / "runtime" / "state.json").write_text(
        json.dumps(stale_state), encoding="utf-8"
    )
    (state_root / "mounts.tsv").write_text(
        f"target\t{stale_digest}\t{stale_target}\t/targets/{stale_digest}\tread-only\n",
        encoding="utf-8",
    )
    (state_root / "rollback-plan.tsv").write_text(
        "schema\tagent-canon.rollback-plan.v1\n", encoding="utf-8"
    )
    (volume_root / "runtime" / "generations" / "stale-generation").mkdir()
    preserved_surfaces = {}
    for name in ("spool", "archive", "cache", "codex-home"):
        preserved = state_root / name / "preexisting-host-data.txt"
        preserved.write_text(f"{name}\n", encoding="utf-8")
        preserved_surfaces[name] = preserved

    repeated_install = subprocess.run(
        [*common, "install"], check=False, capture_output=True, text=True, env=environment
    )
    assert repeated_install.returncode == 0, repeated_install.stderr
    assert not (state_root / "rollback-plan.tsv").exists()
    assert not (volume_root / "runtime" / "generations" / "stale-generation").exists()
    assert (state_root / "mounts.tsv").read_text(encoding="utf-8") == ""
    for name, preserved in preserved_surfaces.items():
        assert preserved.read_text(encoding="utf-8") == f"{name}\n"
    docker_state = json.loads(fake_state.read_text(encoding="utf-8"))
    active_values = dict(
        line.split("\t", 1)
        for line in (repository / ".runtime" / "host-state" / "active-image.tsv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert docker_state["images"][active_values["image-ref"]]["Id"] == active_values[
        "image-id"
    ]
    assert docker_state["images"][foreign_ref]["Id"] == foreign_id
    assert not any("-rollback-" in key for key in docker_state["images"])

    repeated_add = subprocess.run(
        [
            *common,
            "target",
            "add",
            "--root",
            str(repository),
            "--mode",
            "read-only",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert repeated_add.returncode == 0, repeated_add.stderr
    assert '"code": "target_registered"' in repeated_add.stdout
    assert len(
        (repository / ".runtime" / "container-state" / "mounts.tsv").read_text(
            encoding="utf-8"
        ).splitlines()
    ) == 1


def test_clean_install_failure_restores_resident_and_lifecycle_state(
    tmp_path: Path,
) -> None:
    """A failed replacement restores the pre-install resident and lifecycle."""
    home = tmp_path / "home"
    home.mkdir()
    origin = tmp_path / "origin.git"
    publisher = tmp_path / "publisher"
    subprocess.run(
        ["git", "init", "--bare", str(origin)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(publisher)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(publisher), "push", str(origin), "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
    )
    repository = home / "agent-canon"
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(origin), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "branch", "-M", "main"],
        check=True,
        capture_output=True,
    )

    fake_state = tmp_path / "docker-state.json"
    calls = tmp_path / "docker.calls"
    fake_docker = ROOT / "tests" / "bootstrap" / "fake_docker.py"
    legacy_runtime = home / "workspace" / "agent-canon-runtime" / "host"
    environment = {
        **os.environ,
        "HOME": str(home),
        "AGENT_CANON_DOCKER": str(fake_docker),
        "FAKE_DOCKER_STATE": str(fake_state),
        "FAKE_DOCKER_CALLS": str(calls),
        "FAKE_DOCKER_VALID_IMAGE_IDS": "1",
    }
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(home),
        "--runtime-root",
        str(legacy_runtime),
    ]

    installed = subprocess.run(
        [*common, "install"], check=False, capture_output=True, text=True, env=environment
    )
    assert installed.returncode == 0, installed.stderr

    runtime = repository / ".runtime"
    state_root = runtime / "container-state"
    active_image = runtime / "host-state" / "active-image.tsv"
    active_values = dict(
        line.split("\t", 1)
        for line in active_image.read_text(encoding="utf-8").splitlines()
    )
    container_name = "agent-canon-tools-" + hashlib.sha256(
        str(home.resolve()).encode("utf-8")
    ).hexdigest()[:16]
    before = json.loads(fake_state.read_text(encoding="utf-8"))
    old_resident = before["containers"][container_name]
    old_image_ref = active_values["image-ref"]
    old_image_id = active_values["image-id"]
    assert old_resident["Config"]["Image"] == old_image_ref

    foreign_ref = "foreign-tools:keep"
    foreign_record = {
        "Id": "sha256:" + "f" * 64,
        "RepoTags": [foreign_ref],
        "Config": {"Labels": {}},
        "SourceRoot": str(ROOT),
    }
    before["images"][foreign_ref] = foreign_record
    fake_state.write_text(json.dumps(before), encoding="utf-8")
    lifecycle_paths = [
        state_root / "state.json",
        state_root / "owner.json",
        state_root / "mounts.toml",
        state_root / "mounts.tsv",
        active_image,
    ]
    lifecycle_before = {
        path.relative_to(runtime).as_posix(): path.read_bytes() if path.exists() else None
        for path in lifecycle_paths
    }

    failed = subprocess.run(
        [*common, "install"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **environment,
            "FAKE_DOCKER_FAIL_CONTROLLER_OPERATION": "install",
            "FAKE_DOCKER_FAIL_CONTROLLER_RC": "41",
        },
    )
    assert failed.returncode != 0

    after = json.loads(fake_state.read_text(encoding="utf-8"))
    restored = after["containers"][container_name]
    assert restored["Config"]["Image"] == old_image_ref
    assert restored["Config"]["Labels"] == old_resident["Config"]["Labels"]
    assert restored["Mounts"] == old_resident["Mounts"]
    assert restored["HostConfig"] == old_resident["HostConfig"]
    assert restored["State"]["Running"] is True
    assert restored["State"]["Health"]["Status"] == "healthy"
    for relative, content in lifecycle_before.items():
        path = runtime / relative
        if content is None:
            assert not path.exists()
        else:
            assert path.read_bytes() == content
    assert not (state_root / "rollback-plan.tsv").exists()
    assert not (state_root / ".pending-rollback-plan.tsv").exists()

    rollback_refs = [
        fields[2]
        for fields in (
            line.split("\t")
            for line in calls.read_text(encoding="utf-8").splitlines()
        )
        if len(fields) == 3 and fields[0] == "tag" and "-rollback-" in fields[2]
    ]
    assert rollback_refs
    assert rollback_refs[-1] not in after["images"]
    assert after["images"][old_image_ref]["Id"] == old_image_id
    assert after["images"][foreign_ref] == foreign_record


def test_real_docker_public_clean_install_e2e(tmp_path: Path) -> None:
    """Run the exact clean public install path against a real Docker daemon."""
    if os.environ.get("AGENT_CANON_RUN_REAL_CLEAN_E2E") != "1":
        pytest.skip("set AGENT_CANON_RUN_REAL_CLEAN_E2E=1 to run the Docker acceptance")
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is unavailable")
    daemon = subprocess.run(
        [docker, "info"], check=False, capture_output=True, text=True, timeout=15
    )
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")
    docker_host = subprocess.check_output(
        [docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
    ).strip()

    home = tmp_path / "home"
    home.mkdir()
    origin = tmp_path / "origin.git"
    publisher = tmp_path / "publisher"
    subprocess.run(
        ["git", "init", "--bare", str(origin)], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(ROOT), str(publisher)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(publisher), "push", str(origin), "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
    )
    repository = home / "agent-canon"
    subprocess.run(
        ["git", "clone", "--no-hardlinks", str(origin), str(repository)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "branch", "-M", "main"],
        check=True,
        capture_output=True,
    )
    legacy_runtime = home / "workspace" / "agent-canon-runtime" / "host"
    personal_skills = repository / ".codex" / "personal" / "skills"
    runtime = repository / ".runtime"
    container_name = "agent-canon-tools-" + hashlib.sha256(
        str(home.resolve()).encode("utf-8")
    ).hexdigest()[:16]
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(repository),
        "--control-parent-root",
        str(home),
        "--runtime-root",
        str(legacy_runtime),
    ]
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "AGENT_CANON_DOCKER": docker,
        "DOCKER_HOST": docker_host,
    }
    assert not runtime.exists()
    assert not personal_skills.exists()
    assert subprocess.run(
        [docker, "container", "inspect", container_name],
        check=False,
        capture_output=True,
    ).returncode != 0

    try:
        installed = subprocess.run(
            [*common, "install"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=300,
        )
        assert installed.returncode == 0, installed.stderr
        assert runtime.is_dir()
        assert personal_skills.is_dir()
        assert list(personal_skills.glob("*/SKILL.md"))
        assert not legacy_runtime.exists()

        started = subprocess.run(
            [*common, "start"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )
        assert started.returncode == 0, started.stderr
        added = subprocess.run(
            [
                *common,
                "target",
                "add",
                "--root",
                str(repository),
                "--mode",
                "read-only",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )
        assert added.returncode == 0, added.stderr
        mounts = (runtime / "container-state" / "mounts.tsv").read_text(
            encoding="utf-8"
        ).splitlines()
        assert len(mounts) == 1
        assert mounts[0].split("\t")[2] == str(repository.resolve())

        version = subprocess.run(
            [str(repository / "tools" / "bin" / "agent-canon"), "--version"],
            check=False,
            capture_output=True,
            text=True,
            env={
                **environment,
                "AGENT_CANON_CONTROL_PARENT_ROOT": str(home),
                "AGENT_CANON_RUNTIME_ROOT": str(legacy_runtime),
            },
            timeout=120,
        )
        assert version.returncode == 0, version.stderr
        assert version.stdout.strip()

        repeated_install = subprocess.run(
            [*common, "install"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=300,
        )
        assert repeated_install.returncode == 0, repeated_install.stderr
        repeated_add = subprocess.run(
            [
                *common,
                "target",
                "add",
                "--root",
                str(repository),
                "--mode",
                "read-only",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )
        assert repeated_add.returncode == 0, repeated_add.stderr
        assert '"code":"target_unchanged"' in repeated_add.stdout
        assert len(
            (runtime / "container-state" / "mounts.tsv").read_text(
                encoding="utf-8"
            ).splitlines()
        ) == 1
    finally:
        subprocess.run(
            [*common, "uninstall"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=120,
        )


def test_missing_docker_is_typed_without_host_python(tmp_path: Path) -> None:
    """A missing Docker executable remains a host-adapter diagnostic."""
    control = tmp_path / "control"
    control.mkdir()
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--control-parent-root",
            str(control),
            "install",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": str(tmp_path / "missing-docker"),
        },
    )
    assert completed.returncode == 2
    receipt = json.loads(completed.stderr)
    assert receipt["code"] == "source_sync_commit_mismatch"


def test_legacy_runtime_argument_keeps_install_state_at_source_sibling_paths(
    tmp_path: Path,
) -> None:
    """The removed workspace default cannot receive new runtime or log state."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    repository.mkdir()
    control.mkdir()
    legacy = control / "workspace" / "agent-canon-runtime" / "host"
    fake_docker = tmp_path / "docker"
    fake_docker.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_docker.chmod(0o755)

    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(legacy),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": str(fake_docker),
        },
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["runtime_root"] == str(repository / ".runtime")
    assert (repository / ".runtime" / "container-state").is_dir()
    assert not legacy.exists()
    assert not (control / "agent-canon-log").exists()
    assert (tmp_path / "agent-canon-log").is_dir()


def test_symlinked_source_runtime_is_rejected_before_legacy_argument_mapping(
    tmp_path: Path,
) -> None:
    """A symlinked canonical runtime cannot redirect the legacy migration input."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    outside = tmp_path / "outside-runtime"
    repository.mkdir()
    control.mkdir()
    outside.mkdir()
    (outside / "sentinel").write_text("untouched\n", encoding="utf-8")
    (repository / ".runtime").symlink_to(outside, target_is_directory=True)
    legacy = control / "workspace" / "agent-canon-runtime" / "host"

    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(legacy),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": "missing-docker",
        },
    )

    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "symlink_path_rejected"
    assert (outside / "sentinel").read_text(encoding="utf-8") == "untouched\n"
    assert (repository / ".runtime").is_symlink()
    assert not (outside / "container-state").exists()
    assert not (control / "workspace").exists()
    assert not (tmp_path / "agent-canon-log").exists()


def test_symlinked_private_log_is_rejected_before_runtime_creation(
    tmp_path: Path,
) -> None:
    """A symlinked install sibling cannot redirect private log writes."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    outside = tmp_path / "outside-log"
    repository.mkdir()
    control.mkdir()
    outside.mkdir()
    (outside / "sentinel").write_text("untouched\n", encoding="utf-8")
    (tmp_path / "agent-canon-log").symlink_to(outside, target_is_directory=True)
    legacy = control / "workspace" / "agent-canon-runtime" / "host"

    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--repository-root",
            str(repository),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(legacy),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": "missing-docker",
        },
    )

    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "symlink_path_rejected"
    assert (outside / "sentinel").read_text(encoding="utf-8") == "untouched\n"
    assert not (repository / ".runtime").exists()
    assert not (control / "workspace").exists()


def test_runtime_escape_is_rejected_before_mkdir(tmp_path: Path) -> None:
    """Explicit runtime paths cannot create state outside the control root."""
    control = tmp_path / "control"
    outside = tmp_path / "outside"
    control.mkdir()
    outside.mkdir()
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(outside / "runtime"),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": "docker",
        },
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "runtime_root_escape"
    assert not (outside / "runtime").exists()


def test_symlink_escape_is_rejected_before_mount_creation(tmp_path: Path) -> None:
    """A symlinked runtime parent outside control cannot be adopted."""
    control = tmp_path / "control"
    outside = tmp_path / "outside"
    control.mkdir()
    outside.mkdir()
    (control / "link").symlink_to(outside, target_is_directory=True)
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(control / "link" / "runtime"),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": "docker",
        },
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "runtime_root_escape"
    assert not (outside / "runtime").exists()


def test_malicious_docker_environment_is_not_sourced(tmp_path: Path) -> None:
    """Environment values remain data and cannot execute shell substitutions."""
    control = tmp_path / "control"
    marker = tmp_path / "executed"
    control.mkdir()
    completed = subprocess.run(
        [
            str(BOOTSTRAP),
            "--control-parent-root",
            str(control),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": f"$(touch {marker})",
        },
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "runtime_unavailable"
    assert not marker.exists()


def test_container_controller_status_never_requires_docker(tmp_path: Path) -> None:
    """Container control state operations do not reach Docker lifecycle code."""
    control = tmp_path / "control"
    control.mkdir()
    completed = subprocess.run(
        [
            "python3",
            str(ROOT / "tools/runtime/container/bootstrap_runtime.py"),
            "--container-control",
            "--repository-root",
            str(ROOT),
            "--control-parent-root",
            str(control),
            "--runtime-root",
            str(control / "runtime"),
            "status",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": "missing-docker",
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["operation"] == "status"


def test_scheduler_template_invokes_shell_bootstrap() -> None:
    """Generated systemd units keep the shell boundary as their entrypoint."""
    text = (ROOT / "bootstrap/host/scheduler/systemd/user/agent-canon-sync.service.in").read_text(
        encoding="utf-8"
    )
    assert "ExecStart=@BOOTSTRAP@" in text
    assert "python3" not in text


def test_rollback_validates_current_mounts_before_previous_plan() -> None:
    """Current resident readback is bound to the live manifest before swap."""
    text = ADAPTER.read_text(encoding="utf-8")
    rollback = text.split('    rollback)\n', 1)[1].split('    target)\n', 1)[0]
    assert '_agent_canon_validate_existing_container "$rollback_container" \\' in rollback
    assert '"$AGENT_CANON_STATE_ROOT/mounts.tsv"' in rollback
    assert rollback.index('"$AGENT_CANON_STATE_ROOT/mounts.tsv"') < rollback.index(
        '"$AGENT_CANON_DOCKER_CMD" stop --time 10 "$rollback_container"'
    )
    assert 'AGENT_CANON_RESTORE_IMAGE_ID=$rollback_image_id' in rollback
    assert rollback.index('_agent_canon_run_controller "$rollback_candidate" rollback') > rollback.index(
        'rollback_candidate=$(_agent_canon_ensure_container)'
    )


def test_sync_never_projects_links_from_staging() -> None:
    """Only the live checkout may update the global link manifest."""
    text = ADAPTER.read_text(encoding="utf-8")
    staging = text.split('_agent_canon_sync_operation() (', 1)[1].split(
        '_agent_canon_control_digest()', 1
    )[0]
    assert 'AGENT_CANON_SUPPRESS_GLOBAL_LINKS=1 bootstrap_host_entrypoint "$staging_root"' in staging
    merge = 'git -C "$install_root" merge --ff-only "$remote/$branch"'
    assert staging.index('bootstrap_host_entrypoint "$staging_root"') < staging.index(merge)
    assert staging.index(merge) < staging.index('_agent_canon_install_global_links')
    post_merge_cleanup = staging.rindex('rm -rf -- "$staging_root"')
    assert staging.index('_agent_canon_install_global_links') < post_merge_cleanup


def test_target_generation_uses_reversible_shared_rollback_plan() -> None:
    """Target-only generations keep the same host rollback protocol."""
    controller = (ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text(encoding="utf-8")
    target_control = controller.split('def _container_control_run', 1)[1].split(
        '\ndef build_parser', 1
    )[0]
    assert target_control.count('_container_materialize_rollback_plan(runtime, state)') >= 2
    assert '"image_ref": image.get("tag")' in controller
    rollback = ADAPTER.read_text(encoding="utf-8").split('    rollback)\n', 1)[1].split(
        '    target)\n', 1
    )[0]
    assert 'rm -f -- "$AGENT_CANON_STATE_ROOT/rollback-plan.tsv"' not in rollback
    assert 'AGENT_CANON_CURRENT_IMAGE_REF=$current_image_ref' in rollback


def test_active_image_state_owns_ordinary_route_selection() -> None:
    """Ordinary routes consume the persisted exact resident image identity."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert 'active-image.tsv' in text
    assert '_agent_canon_write_active_image' in text
    assert '_agent_canon_read_active_image' in text
    assert '_agent_canon_record_active_container' in text
    assert text.count('_agent_canon_record_active_container') >= 3
    ordinary = text.split('    install|update|start|stop|rollback|uninstall|target|tool|template|task|gc|eval|exec)', 1)[1]
    assert '_agent_canon_use_active_image' in ordinary
    assert '_agent_canon_image "$image_ref"' not in ordinary
    assert 'AGENT_CANON_EXPECTED_IMAGE_ID=$candidate_image_id' in text
    assert 'AGENT_CANON_EXPECTED_IMAGE_ID=$rollback_image_id' in text
    assert 'AGENT_CANON_RUNTIME_ROOT/host-state/active-image.tsv' in text
    assert 'host-state' not in text.split('"$AGENT_CANON_DOCKER_CMD" create', 1)[1].split(
        '"$AGENT_CANON_IMAGE_REF"', 1
    )[0]
    assert 'AGENT_CANON_RUNTIME_ROOT/host-state' in text
    assert '_agent_canon_migrate_active_image' in text


def test_archive_and_codex_crossings_are_host_owned() -> None:
    """Resident routes produce requests; host owns archive and Codex launch."""
    text = ADAPTER.read_text(encoding="utf-8")
    eval_archive = text.split("_agent_canon_archive_eval_sync()", 1)[1].split(
        "_agent_canon_remove_global_links()", 1
    )[0]
    assert '_agent_canon_private_feedback_sync' in text
    assert '_agent_canon_private_feedback_identity' in text
    assert 'private_feedback.py' not in text
    assert 'source-identity --mode "$mode" --remote "$remote"' in text
    assert 'urlsplit' not in text
    assert 'source_identity=$(_agent_canon_private_feedback_identity "$container" "$source_remote" source)' in text
    assert 'remote_normalized=$(_agent_canon_private_feedback_identity "$container" "$remote" remote)' in text
    assert 'configured_normalized=$(_agent_canon_private_feedback_identity "$container" "$configured" remote)' in text
    assert 'remote_normalized" == "$configured_normalized"' in text
    assert 'if [[ "$mode" == source && -n "${AGENT_CANON_SOURCE_REPOSITORY_ID:-}" ]]' in text
    assert 'identity_args+=(--repository-id "$AGENT_CANON_SOURCE_REPOSITORY_ID")' in text
    assert 'git -C "$log_root" merge --ff-only "origin/$branch"' in text
    assert 'runtime_log_archive_git.py' in text
    assert '--archive-root "$AGENT_CANON_PRIVATE_LOG_ROOT"' in eval_archive
    assert eval_archive.index('--archive-root "$AGENT_CANON_PRIVATE_LOG_ROOT"') < eval_archive.index(
        'archive-eval --spool-root'
    )
    assert 'AGENT_CANON_CODEX' in text
    assert 'AGENT_CANON_CODEX_SESSION_ROOT' in text
    assert 'CODEX_HOME="$AGENT_CANON_STATE_ROOT/codex-home"' in text
    assert 'AGENT_CANON_PROJECT_ROOT="$codex_project"' in text
    assert 'AGENT_CANON_HOST_INSTALL_ROOT=$AGENT_CANON_REPOSITORY_ROOT' in text
    assert '_agent_canon_run_controller "$codex_container" codex prepare' in text
    assert '"$codex_executable" --project-root "$codex_project"' in text
    assert 'if ((rc == 0)) && [[ "$operation" == exec || "$operation" == tool ]]; then' in text
    controller = (ROOT / "tools/runtime/container/bootstrap_runtime.py").read_text(encoding="utf-8")
    assert 'source_identity = sub.add_parser' in controller
    assert 'normalize_remote' in controller
    container_control = controller.split('def _container_control_run', 1)[1].split(
        '\ndef build_parser', 1
    )[0]
    assert 'runtime_log_archive_git' not in container_control
    assert '_host_private_feedback_sync' not in container_control
    eval_sync = controller.split('    def eval_sync(', 1)[1].split(
        '    def eval_sync_prepare(', 1
    )[0]
    assert 'runtime_log_archive_git' not in eval_sync
    assert 'return self.eval_sync_prepare(run_id)' in eval_sync


def test_forced_rollback_recovery_failure_retains_mounted_backup(tmp_path: Path) -> None:
    """A failed state/readback recovery leaves its mounted manifest evidence."""
    control = tmp_path / "control"
    runtime = control / "runtime"
    control.mkdir()
    fake_docker = tmp_path / "docker"
    fake_docker.write_text(
        """#!/usr/bin/env bash
set -eu
if [[ "$1:$2" == container:inspect ]]; then
  if [[ "$4" == *Config.Image* ]]; then printf 'current-ref\\n'; else printf 'true\\n'; fi
elif [[ "$1:$2" == image:inspect ]]; then
  printf 'sha256:current-image-1234567890\\n'
fi
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    script = r'''
set -eu
source "$1/bootstrap/host/lifecycle/entrypoint.sh"
_agent_canon_validate_existing_container() { :; }
_agent_canon_use_active_image() {
  AGENT_CANON_IMAGE_REF=current-ref
  AGENT_CANON_ACTIVE_IMAGE_ID=sha256:current-image-1234567890
  AGENT_CANON_EXPECTED_IMAGE_ID=$AGENT_CANON_ACTIVE_IMAGE_ID
  export AGENT_CANON_IMAGE_REF AGENT_CANON_ACTIVE_IMAGE_ID AGENT_CANON_EXPECTED_IMAGE_ID
}
_agent_canon_read_rollback_plan() {
  AGENT_CANON_ROLLBACK_IMAGE_ID=sha256:previous-image-0987654321
  AGENT_CANON_ROLLBACK_IMAGE_REF=sha256:previous-image-0987654321
  AGENT_CANON_ROLLBACK_MOUNTS_FILE="$AGENT_CANON_STATE_ROOT/rollback-mounts.tsv"
  : > "$AGENT_CANON_ROLLBACK_MOUNTS_FILE"
  export AGENT_CANON_ROLLBACK_IMAGE_ID AGENT_CANON_ROLLBACK_IMAGE_REF AGENT_CANON_ROLLBACK_MOUNTS_FILE
}
_agent_canon_ensure_container() { printf 'rollback-candidate\n'; }
_agent_canon_run_controller() {
  [[ "$2" != rollback ]]
}
_agent_canon_restore_candidate_failure() {
  backup_name=${AGENT_CANON_RESTORE_TARGETS_FILE##*/}
  [[ -f "$AGENT_CANON_STATE_ROOT/$backup_name" ]]
  return 1
}
bootstrap_host_entrypoint "$1" \
  --control-parent-root "$2" \
  --runtime-root "$3" rollback
'''
    completed = subprocess.run(
        ["bash", "-c", script, "bootstrap-test", str(ROOT), str(control), str(runtime)],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "AGENT_CANON_DOCKER": str(fake_docker),
        },
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] == "rollback_failed"
    backups = list((runtime / "container-state").glob(".rollback-current-mounts.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b""


@pytest.mark.skipif(
    shutil.which("docker") is None
    or os.environ.get("AGENT_CANON_RUN_REAL_DOCKER_TESTS") != "1",
    reason="opt-in real Docker bootstrap test",
)
def test_real_resident_codex_projection_is_host_readable(tmp_path: Path) -> None:
    """Resident preparation leaves host-live links usable by host Codex."""
    control = tmp_path / "control"
    runtime = control / "runtime"
    project = tmp_path / "project"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    control.mkdir()
    project.mkdir()
    target_a.mkdir()
    target_b.mkdir()
    source_root = ROOT.resolve()
    control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
    container_name = f"agent-canon-tools-{control_digest[:16]}"
    environment = os.environ.copy()
    environment.update(
        {
            "AGENT_CANON_FORCE_BUILD": "1",
            "XDG_CONFIG_HOME": str(tmp_path / "xdg-config"),
        }
    )
    common = [
        str(BOOTSTRAP),
        "--repository-root",
        str(source_root),
        "--control-parent-root",
        str(control),
        "--runtime-root",
        str(runtime),
    ]
    try:
        installed = subprocess.run(
            [*common, "install"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert installed.returncode == 0, installed.stderr
        codex_home = runtime / "container-state" / "codex-home"
        manifest = json.loads((codex_home / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["source_root"] == str(source_root)
        managed = manifest["links"]
        assert managed
        for entry in managed:
            target = codex_home / Path(entry["target"]).relative_to(
                "/var/lib/agent-canon/runtime/codex-home"
            )
            source = Path(entry["source"])
            assert target.is_symlink()
            assert source.exists()
            assert target.resolve() == source.resolve()

        active_image = runtime / "host-state" / "active-image.tsv"
        resident_host_state = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "test",
                "!",
                "-e",
                "/var/lib/agent-canon/runtime/host-state/active-image.tsv",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert resident_host_state.returncode == 0, resident_host_state.stderr
        forged_state = runtime / "container-state" / "active-image.tsv"
        active_image.unlink()
        forged_state.write_text(
            "schema\tagent-canon.active-image.v1\n"
            "image-ref\tforged\n"
            "image-id\tsha256:forged\n",
            encoding="utf-8",
        )
        migrated_update = subprocess.run(
            [*common, "update"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert migrated_update.returncode == 0, migrated_update.stderr
        assert active_image.is_file()
        active_after_update = active_image.read_bytes()
        active_image.unlink()
        migrated_stop = subprocess.run(
            [*common, "stop"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert migrated_stop.returncode == 0, migrated_stop.stderr
        assert active_image.is_file()
        restarted = subprocess.run(
            [*common, "start"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert restarted.returncode == 0, restarted.stderr
        assert active_image.read_bytes() == active_after_update
        active_before = active_image.read_bytes()
        for target in (target_a, target_b):
            added = subprocess.run(
                [*common, "target", "add", "--root", str(target), "--mode", "read-only"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            assert added.returncode == 0, added.stderr
        rolled_back = subprocess.run(
            [*common, "rollback"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert rolled_back.returncode == 0, rolled_back.stderr
        active_after = {
            key: value
            for key, value in (
                line.split("\t", 1)
                for line in active_image.read_text(encoding="utf-8").splitlines()
            )
        }
        before_values = {
            key: value
            for key, value in (
                line.split("\t", 1)
                for line in active_before.decode("utf-8").splitlines()
            )
        }
        assert active_after["image-id"] == before_values["image-id"]
        actual_ref = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", container_name],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert active_after["image-ref"] == actual_ref
        active_snapshot = active_image.read_bytes()
        mounts_after_rollback = (runtime / "container-state" / "mounts.tsv").read_text(
            encoding="utf-8"
        )
        target_a_digest = hashlib.sha256(str(target_a.resolve()).encode("utf-8")).hexdigest()
        target_b_digest = hashlib.sha256(str(target_b.resolve()).encode("utf-8")).hexdigest()
        assert f"target\t{target_a_digest}\t" in mounts_after_rollback
        assert f"target\t{target_b_digest}\t" not in mounts_after_rollback
        toggled = subprocess.run(
            [*common, "rollback"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert toggled.returncode == 0, toggled.stderr
        mounts_after_toggle = (runtime / "container-state" / "mounts.tsv").read_text(
            encoding="utf-8"
        )
        assert f"target\t{target_a_digest}\t" in mounts_after_toggle
        assert f"target\t{target_b_digest}\t" in mounts_after_toggle
        active_snapshot = active_image.read_bytes()
        for command in (
            [*common, "start"],
            [*common, "status"],
            [
                *common,
                "tool",
                "run",
                "--root",
                str(target_a),
                "route",
                "--",
                "--list",
            ],
            [*common, "codex", "prepare"],
        ):
            checked = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            assert checked.returncode == 0, f"command={command!r}: {checked.stderr}"
            assert active_image.read_bytes() == active_snapshot

        stub = tmp_path / "codex-stub"
        stub.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -eu",
                    'test -f "$CODEX_HOME/config.toml"',
                    'test -f "$CODEX_HOME/agents/worker.toml"',
                    'test -f "$CODEX_HOME/skills/agent-orchestration/SKILL.md"',
                    'test -s "$CODEX_HOME/config.toml"',
                    'test -s "$CODEX_HOME/agents/worker.toml"',
                    'test -s "$CODEX_HOME/skills/agent-orchestration/SKILL.md"',
                    'printf "%s\\n" "$AGENT_CANON_PROJECT_ROOT" > "$CODEX_HOME/host-stub-project"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        launched = subprocess.run(
            [*common, "codex", "launch", "--project-root", str(project)],
            check=False,
            capture_output=True,
            text=True,
            env={
                **environment,
                "AGENT_CANON_FORCE_BUILD": "0",
                "AGENT_CANON_CODEX": str(stub),
            },
        )
        assert launched.returncode == 0, launched.stderr
        assert (codex_home / "host-stub-project").read_text(encoding="utf-8").strip() == str(project)
    finally:
        subprocess.run(
            [*common, "uninstall"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        control_digest = hashlib.sha256(str(control.resolve()).encode("utf-8")).hexdigest()
        container = f"agent-canon-tools-{control_digest[:16]}"
        subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True)
        image_ids = subprocess.run(
            [
                "docker",
                "image",
                "ls",
                "--filter",
                f"label=io.agent-canon.control-root-digest={control_digest}",
                "--format",
                "{{.ID}}",
            ],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for image_id in image_ids:
            subprocess.run(["docker", "image", "rm", image_id], check=False, capture_output=True)


def test_public_install_failure_is_terminal_before_follow_on_target(
    tmp_path: Path,
) -> None:
    """A typed install failure cannot fall through to start or target add."""
    repository = tmp_path / "agent-canon"
    control = tmp_path / "control"
    runtime = tmp_path / "runtime"
    marker = tmp_path / "phases"
    foreign = tmp_path / "foreign-resource"
    repository.mkdir()
    control.mkdir()
    foreign.write_text("foreign\n", encoding="utf-8")
    source_head = "0" * 40
    script = f"""
source {str(ADAPTER)!r}
_agent_canon_validate_roots() {{ :; }}
_agent_canon_install_source_admission() {{
  printf 'up_to_date\\t{source_head}\\t{source_head}\\torigin\\n'
}}
_agent_canon_prepare_host_runtime() {{
  AGENT_CANON_STATE_ROOT="$AGENT_CANON_RUNTIME_ROOT/container-state"
  export AGENT_CANON_STATE_ROOT
  mkdir -p "$AGENT_CANON_RUNTIME_ROOT/host-state" "$AGENT_CANON_STATE_ROOT"
}}
_agent_canon_source_sync_write() {{ :; }}
_agent_canon_finish_clean_install() {{
  printf '%s\\n' finish >> {str(marker)!r}
}}
_agent_canon_install_locked() {{
  printf '%s\\n' install >> {str(marker)!r}
  _agent_canon_json_error install_probe_failed "install transaction failed"
  printf '%s\\n' late-install >> {str(marker)!r}
}}
AGENT_CANON_DOCKER=/bin/true
export AGENT_CANON_DOCKER
set -e
bootstrap_host_entrypoint {str(repository)!r} \\
  --control-parent-root {str(control)!r} \\
  --runtime-root {str(runtime)!r} install
printf '%s\\n' start >> {str(marker)!r}
printf '%s\\n' target-add >> {str(marker)!r}
"""
    completed = subprocess.run(
        ["bash", "-c", script], check=False, capture_output=True, text=True
    )
    assert completed.returncode == 2
    assert completed.stderr.count('"code":"install_probe_failed"') == 1
    assert marker.read_text(encoding="utf-8").splitlines() == ["install"]
    assert foreign.read_text(encoding="utf-8") == "foreign\n"
