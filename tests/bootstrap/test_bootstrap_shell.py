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
ADAPTER = ROOT / "bootstrap" / "lib" / "entrypoint.sh"


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
    controller = (ROOT / "tools/agent_tools/bootstrap_runtime.py").read_text(
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


def test_sync_stages_source_before_live_fast_forward() -> None:
    """Source sync builds the candidate checkout before touching live source."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "source-staging/agent-canon" in text
    assert 'git clone --no-hardlinks "$install_root" "$staging_root"' in text
    assert 'git -C "$install_root" merge --ff-only "$remote/$branch"' in text
    assert text.index('git clone --no-hardlinks "$install_root" "$staging_root"') < text.rindex('git -C "$install_root" merge --ff-only "$remote/$branch"')
    assert text.index('bootstrap_host_entrypoint "$staging_root"') < text.index('git -C "$install_root" merge --ff-only "$remote/$branch"')


def test_source_sync_state_is_mounted_read_only_into_the_resident() -> None:
    """The resident reads the host-owned source-sync file through one mount."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "AGENT_CANON_SOURCE_SYNC_DESTINATION=/var/lib/agent-canon/source-sync.json" in text
    assert 'src=$AGENT_CANON_RUNTIME_ROOT/source-sync.json' in text
    assert 'dst=$AGENT_CANON_SOURCE_SYNC_DESTINATION,readonly' in text
    assert '"$AGENT_CANON_RUNTIME_ROOT/source-sync.json" "$AGENT_CANON_SOURCE_SYNC_DESTINATION"' in text
    assert "_agent_canon_ensure_source_sync_state" in text
    assert "container-state/source-sync.json" not in text


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
    """Structured handoff uses the declared install-sibling private log source."""
    text = ADAPTER.read_text(encoding="utf-8")
    assert "_agent_canon_validate_private_log_mount" in text
    assert "AGENT_CANON_PRIVATE_LOG_ROOT=$AGENT_CANON_PRIVATE_LOG_ROOT" in text
    assert 'AGENT_CANON_PRIVATE_LOG_DESTINATION"' in text
    assert 'control_parent_root / "private-log"' not in (
        ROOT / "tools/agent_tools/bootstrap_runtime.py"
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
    controller = (ROOT / "tools/agent_tools/bootstrap_runtime.py").read_text(
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
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1:$2\" == image:inspect ]]; then printf 'sha256:candidate\\n'; fi\n"
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
    assert receipt["code"] == "runtime_unavailable"


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
            str(ROOT / "tools/agent_tools/bootstrap_runtime.py"),
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
    text = (ROOT / "bootstrap/systemd/user/agent-canon-sync.service.in").read_text(
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
    controller = (ROOT / "tools/agent_tools/bootstrap_runtime.py").read_text(encoding="utf-8")
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
    controller = (ROOT / "tools/agent_tools/bootstrap_runtime.py").read_text(encoding="utf-8")
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
source "$1/bootstrap/lib/entrypoint.sh"
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
