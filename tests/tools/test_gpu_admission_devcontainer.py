"""Focused lifecycle fixtures for the explicit GPU-admission devcontainer."""

# @dependency-start
# contract test
# responsibility Verifies GPU-admission profile selection, finalize resolution, and exact failure cleanup.
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission lifecycle and cleanup
# upstream implementation ../../.devcontainer/gpu-admission.sh owns host/bootstrap/up/finalize sequencing
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves finalize in standalone and derived repositories
# @dependency-end

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.agent_tools.fixture_spawn import (
    bootstrap_fixture_public_environment,
    record_capability_from_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = PROJECT_ROOT / ".devcontainer" / "gpu-admission.sh"


@contextmanager
def fixture_session(
    repository: Path, environment: dict[str, str], command_dir: Path
):
    """Run one GPU fixture through an authenticated selected-root session."""
    with bootstrap_fixture_public_environment(
        mode="synthetic_tool",
        record_capability=record_capability_from_environment(),
        fixture_cwd=repository,
        base_env=environment,
        invocation_script=repository / ".devcontainer" / "gpu-admission.sh",
        purpose="gpu-admission-test",
        explicit_path_entries=(str(command_dir),),
    ) as fixture:
        yield dict(fixture.environment)


def run_gpu_admission(
    repository: Path, environment: dict[str, str], command_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run the fixture entrypoint with the selected repository session."""
    with fixture_session(repository, environment, command_dir) as child_environment:
        return subprocess.run(
            [str(repository / ".devcontainer" / "gpu-admission.sh")],
            cwd=repository,
            env=child_environment,
            check=False,
            capture_output=True,
            text=True,
        )


def test_gpu_runtime_checks_are_mapping_neutral_and_probe_cleanup_is_explicit() -> None:
    """GPU admission preserves within-side checks and uses a closed usability probe."""
    orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
    finalizer = (PROJECT_ROOT / ".devcontainer/finalize-shared-runtime.sh").read_text(
        encoding="utf-8"
    )

    assert ".st_uid" not in orchestrator
    assert ".st_gid" not in orchestrator
    assert "owner differs" not in orchestrator
    assert "group differs" not in orchestrator
    assert 'prefix=".container-usability-"' in finalizer
    assert "os.fsync(usability_fd)" in finalizer
    assert "observed != usability_payload" in finalizer
    assert "os.unlink(usability_probe_path)" in finalizer
    assert "except FileNotFoundError" in finalizer
    assert ".st_uid" not in finalizer
    assert ".st_gid" not in finalizer


def write_executable(path: Path, content: str) -> None:
    """Write one executable fixture command."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def write_gpu_admission_fixture(
    tmp_path: Path,
) -> tuple[Path, dict[str, str], Path, Path]:
    """Create one repository with deterministic bootstrap and CLI fakes."""
    repository = tmp_path / "workspace" / "topic" / "derived-repo"
    orchestrator = repository / ".devcontainer" / "gpu-admission.sh"
    write_executable(orchestrator, ORCHESTRATOR.read_text(encoding="utf-8"))
    selector = repository / ".devcontainer" / "gpu-admission" / "devcontainer.json"
    selector.parent.mkdir(parents=True, exist_ok=True)
    selector.write_text("{}\n", encoding="utf-8")
    for relative in (
        "tools/ci/container_runtime.py",
        "tools/agent_tools/parent_root_side_effects.py",
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (PROJECT_ROOT / relative).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    subprocess.run(
        ["git", "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )

    write_executable(
        repository / "tools/experiments/execution_resource_plan.py",
        "\n".join(
            (
                "import json",
                "from pathlib import Path",
                "def write_runtime_receipt_atomic(path, payload):",
                "    target = Path(path)",
                "    target.write_text(json.dumps(payload), encoding='utf-8')",
                "    target.chmod(0o660)",
                "",
            )
        ),
    )

    command_dir = repository / ".fixture-bin"
    log_path = tmp_path / "commands.log"
    state_path = tmp_path / "docker-state"
    removed_path = tmp_path / "docker-removed"
    write_executable(
        command_dir / "stat",
        """#!/usr/bin/env bash
if [ "${1:-}" = "-f" ]; then
  printf 'ext4\\n'
  exit 0
fi
exec /usr/bin/stat "$@"
""",
    )
    write_executable(
        command_dir / "nvidia-smi",
        "#!/usr/bin/env bash\n[ \"${1:-}\" = '-L' ]\n",
    )
    write_executable(
        command_dir / "devcontainer",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'devcontainer' >> "$GPU_TEST_LOG"
printf ' <%s>' "$@" >> "$GPU_TEST_LOG"
printf '\n' >> "$GPU_TEST_LOG"
case "${1:-}" in
  up)
    mkdir -p "$GPU_TEST_REPOSITORY/.agent-canon"
    printf 'name: %s\n' "$AGENT_CANON_EXPECTED_COMPOSE_PROJECT" > "$GPU_TEST_REPOSITORY/.agent-canon/gpu-admission-compose.generated.yml"
    printf '    image: "%s"\n' "$AGENT_CANON_EXPECTED_IMAGE_TAG" >> "$GPU_TEST_REPOSITORY/.agent-canon/gpu-admission-compose.generated.yml"
    : > "$GPU_TEST_DOCKER_STATE"
    exit "${GPU_TEST_UP_RC:-0}"
    ;;
  exec)
    exit "${GPU_TEST_EXEC_RC:-0}"
    ;;
esac
exit 2
""",
    )
    write_executable(
        command_dir / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'docker' >> "$GPU_TEST_LOG"
printf ' <%s>' "$@" >> "$GPU_TEST_LOG"
printf '\n' >> "$GPU_TEST_LOG"
if [ "${GPU_TEST_DOCKER_RC:-0}" -ne 0 ]; then
  exit "${GPU_TEST_DOCKER_RC}"
fi
if [ "${1:-}" = "version" ]; then
  printf '{"Server":{"Version":"fake"}}\n'
  exit 0
fi
if [ "${1:-}" = "image" ] && [ "${2:-}" = "ls" ]; then
  python3 - <<'PY'
import json
import os
from pathlib import Path
labels = {
    "com.agent-canon.lifecycle-id": os.environ["AGENT_CANON_LIFECYCLE_ID"],
    "com.agent-canon.repository": os.environ["AGENT_CANON_REPOSITORY_ID"],
    "com.agent-canon.task-id": os.environ["AGENT_CANON_TASK_ID"],
    "com.agent-canon.task-repository": os.environ["AGENT_CANON_TASK_ID"] + ":" + os.environ["AGENT_CANON_REPOSITORY_ID"],
}
removed_path = Path(os.environ["GPU_TEST_DOCKER_REMOVED"])
removed = set(removed_path.read_text().splitlines()) if removed_path.exists() else set()
rows = [{"ID":"sha256:preexisting", "RepoTags":["fixture:stable"], "Labels":{}}]
if Path(os.environ["GPU_TEST_DOCKER_STATE"]).exists() and "image:sha256:task" not in removed:
    rows.append({"ID":"sha256:task", "RepoTags":[os.environ["AGENT_CANON_EXPECTED_IMAGE_TAG"]], "Labels":labels})
for row in rows:
    print(json.dumps(row))
PY
  exit 0
fi
if [ "${1:-}" = "ps" ]; then
  python3 - <<'PY'
import json
import os
from pathlib import Path
removed_path = Path(os.environ["GPU_TEST_DOCKER_REMOVED"])
removed = set(removed_path.read_text().splitlines()) if removed_path.exists() else set()
if Path(os.environ["GPU_TEST_DOCKER_STATE"]).exists() and "container:ctr-task" not in removed:
    labels = {"com.agent-canon.lifecycle-id":os.environ["AGENT_CANON_LIFECYCLE_ID"], "com.agent-canon.repository":os.environ["AGENT_CANON_REPOSITORY_ID"], "com.agent-canon.task-id":os.environ["AGENT_CANON_TASK_ID"], "com.agent-canon.task-repository":os.environ["AGENT_CANON_TASK_ID"] + ":" + os.environ["AGENT_CANON_REPOSITORY_ID"]}
    print(json.dumps({"ID":"ctr-task", "Labels":labels, "ImageID":"sha256:task"}))
PY
  exit 0
fi
if [ "${1:-}" = "network" ] && [ "${2:-}" = "ls" ]; then
  python3 - <<'PY'
import json
import os
from pathlib import Path
removed_path = Path(os.environ["GPU_TEST_DOCKER_REMOVED"])
removed = set(removed_path.read_text().splitlines()) if removed_path.exists() else set()
if Path(os.environ["GPU_TEST_DOCKER_STATE"]).exists() and "network:net-task" not in removed:
    labels = {"com.agent-canon.lifecycle-id":os.environ["AGENT_CANON_LIFECYCLE_ID"], "com.agent-canon.repository":os.environ["AGENT_CANON_REPOSITORY_ID"], "com.agent-canon.task-id":os.environ["AGENT_CANON_TASK_ID"], "com.agent-canon.task-repository":os.environ["AGENT_CANON_TASK_ID"] + ":" + os.environ["AGENT_CANON_REPOSITORY_ID"]}
    print(json.dumps({"ID":"net-task", "Name":"fixture_default", "Labels":labels}))
PY
  exit 0
fi
if [ "${1:-}" = "volume" ] && [ "${2:-}" = "ls" ]; then
  python3 - <<'PY'
import json
import os
from pathlib import Path
removed_path = Path(os.environ["GPU_TEST_DOCKER_REMOVED"])
removed = set(removed_path.read_text().splitlines()) if removed_path.exists() else set()
if Path(os.environ["GPU_TEST_DOCKER_STATE"]).exists() and "volume:vol-task" not in removed:
    labels = {"com.agent-canon.lifecycle-id":os.environ["AGENT_CANON_LIFECYCLE_ID"], "com.agent-canon.repository":os.environ["AGENT_CANON_REPOSITORY_ID"], "com.agent-canon.task-id":os.environ["AGENT_CANON_TASK_ID"], "com.agent-canon.task-repository":os.environ["AGENT_CANON_TASK_ID"] + ":" + os.environ["AGENT_CANON_REPOSITORY_ID"]}
    print(json.dumps({"Name":"vol-task", "Labels":labels}))
PY
  exit 0
fi
if [ "${1:-}" = "inspect" ] || { [ "${1:-}" = "network" ] && [ "${2:-}" = "inspect" ]; } || { [ "${1:-}" = "volume" ] && [ "${2:-}" = "inspect" ]; } || { [ "${1:-}" = "image" ] && [ "${2:-}" = "inspect" ]; }; then
  kind="${1:-}"
  [ "$kind" = "inspect" ] && kind=container
  target="${@: -1}"
  if grep -qxF "$kind:$target" "${GPU_TEST_DOCKER_REMOVED}" 2>/dev/null; then
    printf 'no such object\n' >&2
    exit 1
  fi
  printf '{"Id":"%s"}\n' "$target"
  exit 0
fi
case "${1:-}:${2:-}" in
  rm:*|network:rm|volume:rm|image:rm)
    kind="${1:-}"
    target="${2:-}"
    [ "$kind" = "rm" ] && kind=container
    if [ "$kind" = "network" ] || [ "$kind" = "volume" ] || [ "$kind" = "image" ]; then
      target="${3:-}"
    fi
    if [ "${GPU_TEST_DOCKER_REMOVE_RC:-0}" -ne 0 ]; then
      exit "${GPU_TEST_DOCKER_REMOVE_RC}"
    fi
    printf '%s:%s\n' "$kind" "$target" >> "$GPU_TEST_DOCKER_REMOVED"
    exit 0
    ;;
esac
exit 0
""",
    )
    base_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("AGENT_CANON_") and key != "PYTHONPATH"
    }
    environment = {
        **base_environment,
        "GPU_TEST_LOG": str(log_path),
        "GPU_TEST_REPOSITORY": str(repository),
        "GPU_TEST_DOCKER_STATE": str(state_path),
        "GPU_TEST_DOCKER_REMOVED": str(removed_path),
        "AGENT_CANON_REPOSITORY_ID": str(repository.resolve()),
        "AGENT_CANON_LIFECYCLE_ID": "gpu-fixture-lifecycle",
        "AGENT_CANON_TASK_ID": "gpu-fixture-task",
    }
    return repository, environment, log_path, command_dir


def test_profile_exec_uses_selector_and_source_root_finalize(tmp_path: Path) -> None:
    """Up and exec select one config, and finalize resolves from AgentCanon source."""
    repository, environment, log_path, command_dir = write_gpu_admission_fixture(tmp_path)

    result = run_gpu_admission(repository, environment, command_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    selector = repository / ".devcontainer/gpu-admission/devcontainer.json"
    calls = log_path.read_text(encoding="utf-8").splitlines()
    up_index = next(index for index, call in enumerate(calls) if call.startswith("devcontainer <up>"))
    exec_index = next(index for index, call in enumerate(calls) if call.startswith("devcontainer <exec>"))
    assert up_index > 0
    assert exec_index > up_index
    assert all(call.startswith("docker <") for call in calls[:up_index])
    assert all(call.startswith("docker <") for call in calls[exec_index + 1 :])
    cleanup_calls = [call for call in calls if " <rm> " in call]
    assert cleanup_calls[-4:] == [
        "docker <rm> <ctr-task>",
        "docker <network> <rm> <net-task>",
        "docker <volume> <rm> <vol-task>",
        "docker <image> <rm> <sha256:task>",
    ]
    assert calls[up_index] == (
        f"devcontainer <up> <--workspace-folder> <{repository}> <--config> <{selector}>"
    )
    assert calls[exec_index] == " ".join(
        (
            "devcontainer <exec>",
            f"<--workspace-folder> <{repository}>",
            f"<--config> <{selector}>",
            "<python3>",
            "</workspace/derived-repo/tools/agent-canon/agent_tools/agent_canon_source_root.py>",
            "<exec> <.devcontainer/finalize-shared-runtime.sh>",
        )
    )
    assert "GPU_ADMISSION_PROFILE=pass" in result.stdout
    assert f"source={repository / '.agent-canon/runtime'}" in result.stdout
    assert "target=/var/lib/agent-canon/runtime" in result.stdout
    receipts = list((repository / ".agent-canon/container-lifecycle").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["lifecycle_id"]
    assert receipt["expected_image_tags"]
    assert receipt["state"] == "cleaned"


def test_profile_success_preserves_original_rc_when_cleanup_blocks(
    tmp_path: Path,
) -> None:
    """A successful command retains rc=0 while receipt records cleanup blocking."""
    repository, environment, _, command_dir = write_gpu_admission_fixture(tmp_path)
    environment["GPU_TEST_DOCKER_REMOVE_RC"] = "19"

    result = run_gpu_admission(repository, environment, command_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    receipts = list((repository / ".agent-canon/container-lifecycle").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["state"] == "cleanup-blocked"
    assert "GPU_ADMISSION_CLEANUP_RESULT=blocked" in result.stderr


def test_profile_failure_preserves_command_rc_when_cleanup_blocks(
    tmp_path: Path,
) -> None:
    """An up failure retains its rc even when exact cleanup also fails."""
    repository, environment, _, command_dir = write_gpu_admission_fixture(tmp_path)
    environment.update({"GPU_TEST_UP_RC": "23", "GPU_TEST_DOCKER_REMOVE_RC": "19"})

    result = run_gpu_admission(repository, environment, command_dir)

    assert result.returncode == 23
    assert "GPU_ADMISSION_CLEANUP_RESULT=failed" in result.stderr


def test_finalize_failure_preserves_command_rc_when_cleanup_blocks(
    tmp_path: Path,
) -> None:
    """A finalize failure retains its rc when exact cleanup also fails."""
    repository, environment, _, command_dir = write_gpu_admission_fixture(tmp_path)
    environment.update({"GPU_TEST_EXEC_RC": "37", "GPU_TEST_DOCKER_REMOVE_RC": "19"})

    result = run_gpu_admission(repository, environment, command_dir)

    assert result.returncode == 37
    assert "GPU_ADMISSION_CLEANUP_RESULT=failed" in result.stderr


@pytest.mark.parametrize(
    ("up_rc", "exec_rc", "expected_rc", "expects_exec"),
    ((23, 0, 23, False), (0, 37, 37, True)),
)
def test_profile_failure_cleans_exact_project_and_preserves_rc(
    tmp_path: Path,
    up_rc: int,
    exec_rc: int,
    expected_rc: int,
    expects_exec: bool,
) -> None:
    """Up/finalize failures tear down only the selected project and retain their rc."""
    repository, environment, log_path, command_dir = write_gpu_admission_fixture(tmp_path)
    environment.update(
        {"GPU_TEST_UP_RC": str(up_rc), "GPU_TEST_EXEC_RC": str(exec_rc)}
    )

    result = run_gpu_admission(repository, environment, command_dir)

    assert result.returncode == expected_rc
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any(call.startswith("devcontainer <exec>") for call in calls) is expects_exec
    assert not any("--remove-orphans" in call for call in calls)
    removed = Path(environment["GPU_TEST_DOCKER_REMOVED"]).read_text(encoding="utf-8").splitlines()
    assert [line.split(":", 1)[0] for line in removed] == [
        "container",
        "network",
        "volume",
        "image",
    ]
    assert "image:sha256:preexisting" not in removed
    assert "GPU_ADMISSION_CLEANUP=pass" in result.stderr
    receipts = list((repository / ".agent-canon/container-lifecycle").glob("*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text(encoding="utf-8"))["state"] == "cleaned"
