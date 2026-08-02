# @dependency-start
# contract test
# responsibility Tests nested Codex container runner behavior.
# upstream implementation ../../tools/ci/run_codex_in_repo_container.py runs Codex inside the repo container
# upstream implementation ../../.devcontainer/devcontainer.json selects runtime setup before nested Codex
# upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md exact in-container runtime identity oracle
# @dependency-end

"""Tests for the nested Codex container runner."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_codex_in_repo_container.py"


def run_cli(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the nested Codex runner and capture output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def test_print_only_runs_shared_post_create_before_codex() -> None:
    """Codex and gh setup should come from shared post-create, not Dockerfile."""
    result = run_cli("--print-only")

    assert result.returncode == 0, result.stderr
    assert (
        "bash /workspace/vendor/agent-canon/.devcontainer/post-create.sh /workspace"
        in result.stdout
    )
    assert "setpriv --reuid" in result.stdout
    assert "--user" not in result.stdout
    assert "/root/.codex" not in result.stdout
    assert "codex-state" not in result.stdout
    assert "exec codex" in result.stdout


def test_runtime_identity(tmp_path: Path) -> None:
    """Nested Codex reaches the exact finalize/readback identity path before launch."""
    pack = tmp_path / "pack.toml"
    pack.write_text(
        "\n".join(
            [
                "[pack]",
                'name = "runtime-identity"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "agent-canon-runtime-identity:test"',
                'platform = "linux/amd64"',
                "",
                "[smoke]",
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                'dependency_profile = "gpu"',
                "env = []",
                "mounts = []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    profiles = tmp_path / "profiles.toml"
    profiles.write_text(
        "\n".join(
            [
                "[defaults]",
                'container_home_root = "/workspace/.state/nested-codex"',
                "use_host_user = false",
                "tty = false",
                "mount_host_gitconfig = false",
                "mount_host_git_credentials = false",
                "mount_host_ssh_dir = false",
                "forward_ssh_auth_sock = false",
                'forward_env = ["OPENAI_API_KEY", "OPENAI_BASE_URL"]',
                "",
                "[[profile]]",
                'name = "default"',
                f'pack = "{pack}"',
                'description = "runtime identity fixture"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = run_cli(
        "--print-only",
        "--profiles",
        str(profiles),
        env={
            "OPENAI_API_KEY": "test-api-key",
            "OPENAI_BASE_URL": "https://api.example.test/v1",
        },
    )
    post_create = (PROJECT_ROOT / ".devcontainer" / "post-create.sh").read_text(
        encoding="utf-8"
    )
    finalize = (
        PROJECT_ROOT / ".devcontainer" / "finalize-shared-runtime.sh"
    ).read_text(encoding="utf-8")
    post_attach = (PROJECT_ROOT / ".devcontainer" / "post-attach.sh").read_text(
        encoding="utf-8"
    )
    bootstrap = (
        PROJECT_ROOT / ".devcontainer" / "bootstrap-shared-runtime.sh"
    ).read_text(encoding="utf-8")
    compose = (
        PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh"
    ).read_text(encoding="utf-8")
    environment_manifest = (PROJECT_ROOT / "agent-canon-environment.toml").read_text(
        encoding="utf-8"
    )
    managed_runner = (
        PROJECT_ROOT / "tools" / "experiments" / "run_managed_experiment.py"
    ).read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert (
        "bash /workspace/vendor/agent-canon/.devcontainer/post-create.sh /workspace"
        in result.stdout
    )
    assert "-e OPENAI_API_KEY=test-api-key" in result.stdout
    assert "-e OPENAI_BASE_URL=https://api.example.test/v1" in result.stdout
    assert "-e AGENT_CANON_DEPENDENCY_PROFILE=gpu" in result.stdout
    assert "/root/.codex" not in result.stdout
    assert "umask 0007" in post_create
    assert '"$devcontainer_dir/finalize-shared-runtime.sh"' in post_create
    assert 'dependency_profile="${AGENT_CANON_DEPENDENCY_PROFILE:-full}"' in post_create
    assert '--profile "$dependency_profile"' in post_create
    assert 'echo "codex-state: ${codex_state_status}"' in post_attach
    assert '"schema_version": "shared-runtime-readback/v1"' in finalize
    assert 'readback_receipt="${runtime_root}/shared-runtime-readback.json"' in finalize
    assert (
        'provision_receipt="${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-${runtime_root}/shared-runtime-provision.json}"'
        in bootstrap
    )
    assert "read_shared_runtime_provision" in finalize
    assert "write_runtime_receipt_atomic" in bootstrap
    assert "write_runtime_receipt_atomic" in finalize
    assert "/var/lib/agent-canon/runtime/shared-runtime-provision.json" in compose
    assert (
        "/var/lib/agent-canon/runtime/shared-runtime-provision.json"
        in environment_manifest
    )
    assert (
        "/var/lib/agent-canon/runtime/shared-runtime-readback.json"
        in environment_manifest
    )
    assert "expected_provision_path" in managed_runner
    assert "/receipts/shared-runtime-provision" not in "\n".join(
        (bootstrap, finalize, compose, environment_manifest, managed_runner)
    )
    assert "/receipts/shared-runtime-readback" not in "\n".join(
        (bootstrap, finalize, compose, environment_manifest, managed_runner)
    )
    assert "exec codex" in result.stdout
    assert "--platform linux/amd64" in result.stdout
