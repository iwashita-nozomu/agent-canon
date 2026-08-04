"""Focused lifecycle fixtures for the explicit GPU-admission devcontainer."""

# @dependency-start
# contract test
# responsibility Verifies GPU-admission profile selection, finalize resolution, and exact failure cleanup.
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission lifecycle and cleanup
# upstream implementation ../../.devcontainer/gpu-admission.sh owns host/bootstrap/up/finalize sequencing
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py resolves finalize in standalone and derived repositories
# @dependency-end

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = PROJECT_ROOT / ".devcontainer" / "gpu-admission.sh"


def write_executable(path: Path, content: str) -> None:
    """Write one executable fixture command."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def write_gpu_admission_fixture(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    """Create one repository with deterministic bootstrap and CLI fakes."""
    repository = tmp_path / "workspace" / "topic" / "derived-repo"
    orchestrator = repository / ".devcontainer" / "gpu-admission.sh"
    write_executable(orchestrator, ORCHESTRATOR.read_text(encoding="utf-8"))
    selector = repository / ".devcontainer" / "gpu-admission" / "devcontainer.json"
    selector.parent.mkdir(parents=True, exist_ok=True)
    selector.write_text("{}\n", encoding="utf-8")

    raw_host_groups = subprocess.run(
        ["id", "-G"], check=True, capture_output=True, text=True
    ).stdout.strip()
    host_groups = " ".join(
        str(group_id) for group_id in sorted({int(item) for item in raw_host_groups.split()})
    )
    runtime_gid = host_groups.split()[0]
    write_executable(
        repository / ".devcontainer" / "bootstrap-shared-runtime.sh",
        "\n".join(
            (
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"printf 'AGENT_CANON_RUNTIME_GID=%s\\n' {runtime_gid!r}",
                f"printf 'AGENT_CANON_HOST_SUPPLEMENTARY_GIDS=%s\\n' {host_groups!r}",
                "printf 'AGENT_CANON_SHARED_RUNTIME_SOURCE=%s\\n' '/var/lib/agent-canon/runtime'",
                "printf 'AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT=%s\\n' '/var/lib/agent-canon/runtime/shared-runtime-provision.json'",
                "",
            )
        ),
    )

    command_dir = tmp_path / "commands"
    log_path = tmp_path / "commands.log"
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
    printf 'name: fixture-gpu-admission\n' > "$GPU_TEST_REPOSITORY/.agent-canon/gpu-admission-compose.generated.yml"
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
exit "${GPU_TEST_DOCKER_RC:-0}"
""",
    )
    environment = {
        **os.environ,
        "PATH": f"{command_dir}:{os.environ['PATH']}",
        "AGENT_CANON_ACTIVE_REPOSITORY_ROOT": str(repository),
        "GPU_TEST_LOG": str(log_path),
        "GPU_TEST_REPOSITORY": str(repository),
    }
    return repository, environment, log_path


def test_profile_exec_uses_selector_and_source_root_finalize(tmp_path: Path) -> None:
    """Up and exec select one config, and finalize resolves from AgentCanon source."""
    repository, environment, log_path = write_gpu_admission_fixture(tmp_path)

    result = subprocess.run(
        [str(repository / ".devcontainer" / "gpu-admission.sh")],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    selector = repository / ".devcontainer/gpu-admission/devcontainer.json"
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert calls == [
        f"devcontainer <up> <--workspace-folder> <{repository}> <--config> <{selector}>",
        " ".join(
            (
                "devcontainer <exec>",
                f"<--workspace-folder> <{repository}>",
                f"<--config> <{selector}>",
                "<python3>",
                "</workspace/derived-repo/tools/agent-canon/agent_tools/agent_canon_source_root.py>",
                "<exec> <.devcontainer/finalize-shared-runtime.sh>",
            )
        ),
    ]
    assert "GPU_ADMISSION_PROFILE=pass" in result.stdout


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
    repository, environment, log_path = write_gpu_admission_fixture(tmp_path)
    environment.update(
        {"GPU_TEST_UP_RC": str(up_rc), "GPU_TEST_EXEC_RC": str(exec_rc)}
    )

    result = subprocess.run(
        [str(repository / ".devcontainer" / "gpu-admission.sh")],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == expected_rc
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any(call.startswith("devcontainer <exec>") for call in calls) is expects_exec
    compose = repository / ".agent-canon/gpu-admission-compose.generated.yml"
    assert calls[-1] == (
        "docker <compose> <--project-name> <fixture-gpu-admission> "
        f"<--file> <{compose}> <down> <--remove-orphans>"
    )
    assert (
        f"GPU_ADMISSION_CLEANUP=pass original_rc={expected_rc} "
        "project=fixture-gpu-admission"
    ) in result.stderr
