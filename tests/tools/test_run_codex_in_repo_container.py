# @dependency-start
# contract test
# responsibility Tests nested Codex container runner behavior.
# upstream implementation ../../tools/ci/run_codex_in_repo_container.py runs Codex inside the repo container
# upstream implementation ../../.devcontainer/devcontainer.json selects runtime setup before nested Codex
# upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md opt-in in-container runtime identity oracle
# @dependency-end

"""Tests for the nested Codex container runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_codex_in_repo_container.py"
sys.path.insert(0, str(SCRIPT.parent))

from run_codex_in_repo_container import (  # noqa: E402
    DEFAULT_PROFILES_PATH,
    build_nested_codex_script,
    build_parser,
    load_profiles,
)


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


def test_default_profiles_are_agent_canon_owned_and_packless() -> None:
    """The default profile resolves from AgentCanon and needs no parent TOML."""
    args = build_parser().parse_args(["--list-profiles"])
    _, profiles = load_profiles(args.profiles)

    assert Path(args.profiles) == DEFAULT_PROFILES_PATH
    assert DEFAULT_PROFILES_PATH == (
        PROJECT_ROOT / "tools/ci/codex-container-profiles.toml"
    )
    assert [(profile.name, profile.pack) for profile in profiles] == [
        ("default", None)
    ]


def write_nested_profile_fixture(
    tmp_path: Path,
    *,
    profile_name: str = "default",
    pack_env: tuple[str, ...] = (),
    forward_env: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    """Write a minimal nested runner pack/profile pair for contract tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    pack = tmp_path / "pack.toml"
    pack.write_text(
        "\n".join(
            [
                "[pack]",
                'name = "nested-contract"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "nested-contract:test"',
                'platform = "linux/amd64"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                f"env = {json.dumps(list(pack_env))}",
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
                f"forward_env = {json.dumps(list(forward_env))}",
                "",
                "[[profile]]",
                f"name = {json.dumps(profile_name)}",
                f"pack = {json.dumps(str(pack))}",
                'description = "nested contract fixture"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workspace, profiles


def test_print_only_runs_shared_post_create_before_codex() -> None:
    """Codex and gh setup should come from shared post-create, not Dockerfile."""
    result = run_cli("--print-only")

    assert result.returncode == 0, result.stderr
    assert (
        "bash /workspace/vendor/agent-canon/.devcontainer/post-create.sh /workspace"
        in result.stdout
    )
    assert "--user root" in result.stdout
    assert "-e AGENT_CANON_CONTAINER_USER=" in result.stdout
    assert "setpriv --reuid" in result.stdout
    assert "/root/.codex" not in result.stdout
    assert "codex-state" not in result.stdout
    assert 'export AGENT_CANON_CODEX_SESSION_ROOT="${AGENT_CANON_CODEX_SESSION_ROOT:-$HOME/.codex/sessions}"' in result.stdout
    assert "exec codex" in result.stdout


def test_default_does_not_mount_host_docker_socket() -> None:
    """Default nested Codex keeps the host Docker socket outside its contract."""
    result = run_cli("--print-only")

    assert result.returncode == 0, result.stderr
    assert "-v /var/run/docker.sock:/var/run/docker.sock" not in result.stdout
    assert "-e AGENT_CANON_CONTAINER_USER=" in result.stdout
    assert (
        "bash /workspace/vendor/agent-canon/.devcontainer/post-create.sh /workspace"
        in result.stdout
    )
    assert "setpriv --reuid" in result.stdout


def test_nested_runner_xdg_state_allows_container_local_receipts(
    tmp_path: Path,
) -> None:
    """Nested generated env lets post-create write receipts outside workspace HOME."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    pack = tmp_path / "pack.toml"
    pack.write_text(
        "\n".join(
            [
                "[pack]",
                'name = "nested-receipt"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "nested-receipt:test"',
                'platform = "linux/amd64"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                "env = []",
                "mounts = []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    profile_name = "receipt-regression"
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
                "forward_env = []",
                "",
                "[[profile]]",
                f'name = "{profile_name}"',
                f'pack = "{pack}"',
                'description = "receipt state regression"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "--print-only",
        "--profiles",
        str(profiles),
        "--profile",
        profile_name,
        "--workspace-root",
        str(workspace),
    )
    assert result.returncode == 0, result.stderr
    xdg_state = Path(f"/tmp/agent-canon-xdg-state/{profile_name}")
    assert f"-e XDG_STATE_HOME={xdg_state}" in result.stdout
    assert f"-e HOME=/workspace/.state/nested-codex/{profile_name}" in result.stdout

    post_create = workspace / "vendor/agent-canon/.devcontainer/post-create.sh"
    post_create.parent.mkdir(parents=True)
    post_create.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'workspace="$1"\n'
        'state_home="${XDG_STATE_HOME:-$HOME/.local/state}"\n'
        'workspace_real="$(realpath -m -- "$workspace")"\n'
        'state_home="$(realpath -m -- "$state_home")"\n'
        'case "$state_home/" in "$workspace_real/"*) exit 41;; esac\n'
        'receipts="$state_home/agent-canon/dependency-receipts"\n'
        'mkdir -p "$receipts"\n'
        'printf receipt >"$receipts/regression.json"\n'
        'workspace_state="$workspace/.agent-canon"\n'
        'test ! -e "$workspace_state/dependency-receipts"\n',
        encoding="utf-8",
    )
    post_create.chmod(0o755)
    script = build_nested_codex_script(
        ["sh", "-c", "test -f \"$XDG_STATE_HOME/agent-canon/dependency-receipts/regression.json\""],
        mount_host_ssh_dir=False,
        workspace=str(workspace),
        run_uid=None,
        run_gid=None,
    )
    shutil.rmtree(xdg_state, ignore_errors=True)
    try:
        executed = subprocess.run(
            ["bash", "-c", script],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(workspace / ".state/nested-codex" / profile_name),
                "XDG_STATE_HOME": str(xdg_state),
            },
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert (xdg_state / "agent-canon/dependency-receipts/regression.json").is_file()
        assert not (workspace / ".agent-canon/dependency-receipts").exists()
    finally:
        shutil.rmtree(xdg_state, ignore_errors=True)


def test_nested_runner_rejects_owned_environment_overrides(tmp_path: Path) -> None:
    """Pack, profile, and CLI forwarding cannot shadow owned nested env values."""
    cases = (
        (("HOME=/tmp/override",), (), (), "pack runtime.env", "HOME"),
        ((), ("XDG_STATE_HOME",), (), "profile forward_env", "XDG_STATE_HOME"),
        ((), (), ("--forward-env", "AGENT_CANON_CONTAINER_USER"), "CLI --forward-env", "AGENT_CANON_CONTAINER_USER"),
    )
    for index, (pack_env, profile_env, cli_args, source, name) in enumerate(cases):
        workspace, profiles = write_nested_profile_fixture(
            tmp_path / f"case-{index}",
            pack_env=pack_env,
            forward_env=profile_env,
        )
        result = run_cli(
            "--print-only",
            "--profiles",
            str(profiles),
            "--workspace-root",
            str(workspace),
            *cli_args,
        )
        assert result.returncode == 2
        assert (
            f"{source} cannot override nested runtime-owned environment: {name}"
            in result.stderr
        )


def test_nested_runner_rejects_unsafe_profile_state_path(tmp_path: Path) -> None:
    """Profile names used in the XDG state path are one safe path segment."""
    for index, profile_name in enumerate(("../escape", "nested/profile", ".", "..")):
        workspace, profiles = write_nested_profile_fixture(
            tmp_path / f"unsafe-{index}",
            profile_name=profile_name,
        )
        result = run_cli(
            "--print-only",
            "--profiles",
            str(profiles),
            "--profile",
            profile_name,
            "--workspace-root",
            str(workspace),
        )
        assert result.returncode == 2
        assert "nested profile name must be one safe path segment" in result.stderr


def test_host_uid_setup_chowns_workspace_artifacts_before_setpriv() -> None:
    """Host-UID setup hands mounted post-create artifacts back to the host user."""
    result = run_cli("--print-only")

    assert result.returncode == 0, result.stderr
    output = result.stdout
    post_create = output.index(
        "bash /workspace/vendor/agent-canon/.devcontainer/post-create.sh /workspace"
    )
    workspace_marker = output.index('workspace_marker="$(mktemp)"')
    workspace_ownership = output.index(
        f"find -P /workspace -xdev -mindepth 1 -uid 0 -newer \"$workspace_marker\" "
        f"-exec chown -h {os.getuid()}:{os.getgid()} {{}} +",
        post_create,
    )
    marker_cleanup = output.index('rm -f "$workspace_marker"', workspace_ownership)
    setpriv = output.index("setpriv --reuid", workspace_ownership)
    assert workspace_marker < post_create < workspace_ownership < marker_cleanup < setpriv


def _write_executable(path: Path, contents: str) -> None:
    """Write one executable fixture script."""
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def test_host_uid_setup_executes_workspace_ownership_handoff(tmp_path: Path) -> None:
    """The handoff covers new parents and fails closed before setpriv on chown errors."""
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    log = tmp_path / "events.log"
    root_owned_manifest = tmp_path / "root-owned.txt"
    outside_target = tmp_path / "outside.txt"
    post_create = workspace / "vendor/agent-canon/.devcontainer/post-create.sh"
    generated_script = tmp_path / "nested-codex.sh"
    workspace.mkdir()
    home.mkdir()
    bin_dir.mkdir()
    (workspace / "pre-existing-root-owned.txt").write_text(
        "keep", encoding="utf-8"
    )
    outside_target.write_text("outside", encoding="utf-8")
    post_create.parent.mkdir(parents=True)
    post_create.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'workspace="$1"\n'
        'mkdir -p "$workspace/reports/agents/devcontainer/runtime"\n'
        'printf arbitrary >"$workspace/reports/agents/devcontainer/runtime/output.txt"\n'
        'mkdir -p "$workspace/.agent-canon"\n'
        'mkdir -p "$workspace/editable-install-output/package"\n'
        'printf editable >"$workspace/editable-install-output/package/module.py"\n'
        'ln -s "${OUTSIDE_TARGET:?}" "$workspace/new-outside-link"\n'
        'printf "%s\\n" '
        '"$workspace/reports/agents/devcontainer/runtime" '
        '"$workspace/reports/agents/devcontainer/runtime/output.txt" '
        '"$workspace/reports" '
        '"$workspace/reports/agents" '
        '"$workspace/reports/agents/devcontainer" '
        '"$workspace/.agent-canon" '
        '"$workspace/editable-install-output" '
        '"$workspace/editable-install-output/package" '
        '"$workspace/editable-install-output/package/module.py" '
        '"$workspace/new-outside-link" '
        '"$workspace/pre-existing-root-owned.txt" >"${ROOT_OWNED_MANIFEST:?}"\n',
        encoding="utf-8",
    )
    post_create.chmod(0o755)
    _write_executable(
        bin_dir / "id",
        "#!/usr/bin/env bash\n"
        'case "${1:-}" in\n'
        "  -u|-g) printf '0\\n' ;;\n"
        "  *) exec /usr/bin/id \"$@\" ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "find",
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "marker = Path(args[args.index('-newer') + 1])\n"
        "manifest = Path(os.environ['ROOT_OWNED_MANIFEST'])\n"
        "selected = {Path(line.strip()) for line in manifest.read_text().splitlines()}\n"
        "root = Path(args[1] if args[0] == '-P' else args[0])\n"
        "paths = []\n"
        "for directory, directories, files in os.walk(root, followlinks=False):\n"
        "    candidates = [Path(directory), *(Path(directory) / name for name in (*directories, *files))]\n"
        "    for candidate in candidates:\n"
        "        if candidate in selected and os.lstat(candidate).st_mtime_ns > marker.stat().st_mtime_ns:\n"
        "            paths.append(str(candidate))\n"
        "if not paths:\n"
        "    raise SystemExit(0)\n"
        "exec_index = args.index('-exec')\n"
        "chown_command = args[exec_index + 1]\n"
        "chown_args = [arg for arg in args[exec_index + 2:-2] if arg != '{}']\n"
        "raise SystemExit(subprocess.run([chown_command, *chown_args, *paths], check=False).returncode)\n",
    )
    _write_executable(
        bin_dir / "chown",
        "#!/usr/bin/env bash\n"
        'printf "chown %s\\n" "$*" >>"${EVENT_LOG:?}"\n'
        'if [[ "${FAIL_CHOWN:-0}" == 1 && "${1:-}" == "-h" ]]; then exit 42; fi\n'
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "rm",
        "#!/usr/bin/env bash\n"
        'printf "rm %s\\n" "$*" >>"${EVENT_LOG:?}"\n'
        'exec /usr/bin/rm "$@"\n',
    )
    _write_executable(
        bin_dir / "setpriv",
        "#!/usr/bin/env bash\n"
        'printf "setpriv-called\\n" >>"${EVENT_LOG:?}"\n'
        "while (($#)); do\n"
        '  case "$1" in\n'
        "    --reuid|--regid) shift 2 ;;\n"
        "    --clear-groups) shift ;;\n"
        "    *) break ;;\n"
        "  esac\n"
        "done\n"
        'exec "$@"\n',
    )
    _write_executable(
        bin_dir / "codex",
        "#!/usr/bin/env bash\n"
        'printf "codex-called\\n" >>"${EVENT_LOG:?}"\n',
    )
    generated_script.write_text(
        build_nested_codex_script(
            ["codex"],
            mount_host_ssh_dir=False,
            workspace=str(workspace),
            run_uid=os.getuid(),
            run_gid=os.getgid(),
        ),
        encoding="utf-8",
    )

    common_env = {
        **os.environ,
        "EVENT_LOG": str(log),
        "HOME": str(home),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "OUTSIDE_TARGET": str(outside_target),
        "ROOT_OWNED_MANIFEST": str(root_owned_manifest),
    }
    first = subprocess.run(
        ["bash", str(generated_script)],
        check=False,
        capture_output=True,
        text=True,
        env=common_env,
    )
    assert first.returncode == 0, first.stderr
    events = log.read_text(encoding="utf-8").splitlines()
    chown_events = [line for line in events if line.startswith("chown -h")]
    chown_targets = {target for line in chown_events for target in line.split()[2:]}
    assert str(workspace / "reports") in chown_targets
    assert str(workspace / "reports/agents") in chown_targets
    assert str(workspace / "reports/agents/devcontainer") in chown_targets
    assert str(workspace / "reports/agents/devcontainer/runtime") in chown_targets
    assert str(workspace / ".agent-canon") in chown_targets
    assert str(workspace / "editable-install-output/package/module.py") in chown_targets
    assert str(workspace / "new-outside-link") in chown_targets
    assert str(workspace / "pre-existing-root-owned.txt") not in chown_targets
    assert str(outside_target) not in chown_targets
    marker_cleanup_events = [line for line in events if line.startswith("rm ")]
    assert marker_cleanup_events
    assert events.index(chown_events[-1]) < events.index(marker_cleanup_events[-1])
    assert events.index(marker_cleanup_events[-1]) < events.index("setpriv-called")

    log.write_text("", encoding="utf-8")
    failed = subprocess.run(
        ["bash", str(generated_script)],
        check=False,
        capture_output=True,
        text=True,
        env={**common_env, "FAIL_CHOWN": "1"},
    )
    assert failed.returncode != 0
    assert "setpriv-called" not in log.read_text(encoding="utf-8")


def test_standalone_dockerfile_uses_canonical_project_identity() -> None:
    """Standalone source builds provide project UID/GID and container-local sudo."""
    dockerfile = (PROJECT_ROOT / ".devcontainer" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "ubuntu:22.04@sha256:" in dockerfile
    assert "ARG PROJECT_UID" in dockerfile
    assert "ARG PROJECT_GID" in dockerfile
    assert "groupadd --gid \"${PROJECT_GID}\" project" in dockerfile
    assert (
        'useradd --uid "${PROJECT_UID}" --gid project' in dockerfile
        or 'useradd --uid "${PROJECT_UID}" --gid "${PROJECT_GID}"' in dockerfile
    )
    assert "project ALL=(ALL) NOPASSWD:ALL" in dockerfile
    assert "USER project" in dockerfile


def test_runtime_identity(tmp_path: Path) -> None:
    """Nested Codex keeps opt-in identity scripts retained but unreachable by default."""
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
    gpu_admission = (
        PROJECT_ROOT / ".devcontainer" / "gpu-admission.sh"
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
    assert "-e AGENT_CANON_CONTAINER_USER=" in result.stdout
    assert "--user root" not in result.stdout
    devcontainer = (PROJECT_ROOT / ".devcontainer" / "devcontainer.json").read_text(
        encoding="utf-8"
    )
    assert "-e OPENAI_API_KEY=test-api-key" in result.stdout
    assert "-e OPENAI_BASE_URL=https://api.example.test/v1" in result.stdout
    assert "AGENT_CANON_PYTHON_EXTRAS" not in result.stdout
    assert "/root/.codex" not in result.stdout
    assert "umask 0007" in post_create
    assert '"$devcontainer_dir/finalize-shared-runtime.sh"' not in post_create
    assert "project-install --workspace" not in post_create
    assert "image-verify --workspace" in post_create
    assert "workspace_write_dir" not in post_create
    assert "workspace/.agent-canon" not in post_create
    assert 'workspace_write_probe="$(mktemp "$workspace/identity-write.XXXXXX")"' in post_create
    assert post_create.index("image-verify") < post_create.index(
        'workspace_write_probe="$(mktemp "$workspace/identity-write.XXXXXX")"'
    )
    assert "trap 'if [ -n \"${workspace_write_probe:-}\" ]; then rm -f -- \"$workspace_write_probe\"; fi' EXIT" in post_create
    assert 'cat "$workspace_write_probe"' in post_create
    assert 'rm -f -- "$workspace_write_probe"' in post_create
    assert "dependency_receipts" not in post_create
    assert ".agent-canon/dependency-receipts" not in post_create
    assert 'echo "codex-state: ${codex_state_status}"' in post_attach
    assert 'workspace_layout="${AGENT_CANON_WORKSPACE_LAYOUT:-managed-topic}"' in post_attach
    assert 'workspace_source="${DEPENDENCY_MODULE_CONTAINER_SOURCE:-}"' in post_attach
    assert 'workspace_target="${DEPENDENCY_MODULE_CONTAINER_TARGET:-}"' in post_attach
    assert "workspace_write_dir" not in post_attach
    assert "workspace/.agent-canon" not in post_attach
    assert 'workspace_write_probe="$(mktemp "$repo_root/identity-write.XXXXXX")"' in post_attach
    assert "trap 'if [ -n \"${workspace_write_probe:-}\" ]; then rm -f -- \"$workspace_write_probe\"; fi' EXIT" in post_attach
    assert 'cat "$workspace_write_probe"' in post_attach
    assert 'rm -f -- "$workspace_write_probe"' in post_attach
    assert 'DEPENDENCY_MODULE_CONTAINER_LAYOUT=${workspace_layout}' in post_attach
    assert 'DEPENDENCY_MODULE_CONTAINER_SOURCE=${workspace_source}' in post_attach
    assert 'DEPENDENCY_MODULE_CONTAINER_TARGET=${workspace_target}' in post_attach
    assert 'DEPENDENCY_MODULE_CONTAINER=not-selected layout=direct-repo' in post_attach
    assert '"${repo_root}/tools/agent_tools/dependency_module_change.py"' in post_attach
    assert (
        '"${repo_root}/vendor/agent-canon/tools/agent_tools/dependency_module_change.py"'
        in post_attach
    )
    assert 'if [ -f "$candidate" ]; then' in post_attach
    assert '"schema_version": "shared-runtime-readback/v1"' in finalize
    assert (
        'readback_receipt="${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-${runtime_root}/shared-runtime-readback.json}"'
        in finalize
    )
    assert 'bootstrap-dependencies.sh' not in gpu_admission
    assert 'runtime_source="$repository_root/.agent-canon/runtime"' in gpu_admission
    assert 'runtime_target="/var/lib/agent-canon/runtime"' in gpu_admission
    assert 'write_runtime_receipt_atomic' in gpu_admission
    assert "read_shared_runtime_provision" in finalize
    assert "container-usability-" in finalize
    assert ".st_uid" not in finalize
    assert ".st_gid" not in finalize
    assert "owner differs" not in finalize
    assert "group differs" not in finalize
    assert ".st_uid" not in gpu_admission
    assert ".st_gid" not in gpu_admission
    assert "owner differs" not in gpu_admission
    assert "group differs" not in gpu_admission
    assert "write_runtime_receipt_atomic" in gpu_admission
    assert "write_runtime_receipt_atomic" in finalize
    assert (PROJECT_ROOT / ".devcontainer" / "finalize-shared-runtime.sh").is_file()
    assert not (PROJECT_ROOT / ".devcontainer" / "bootstrap-dependencies.sh").exists()
    assert not (PROJECT_ROOT / ".devcontainer" / "bootstrap-shared-runtime.sh").exists()
    assert "bootstrap-shared-runtime.sh" not in devcontainer
    assert "finalize-shared-runtime.sh" not in devcontainer
    assert "nvidia-smi" not in compose
    assert "AGENT_CANON_PYTHON_EXTRAS" in compose
    assert "AGENT_CANON_DEPENDENCY_PROFILE" not in compose
    assert "DEVCONTAINER_GPU_REQUEST" in compose
    assert "group_add:" not in compose
    assert "gpus: all" in compose
    assert "/var/lib/agent-canon/runtime" in compose
    assert "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT" in compose
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
        (finalize, compose, environment_manifest, managed_runner)
    )
    assert "/receipts/shared-runtime-readback" not in "\n".join(
        (finalize, compose, environment_manifest, managed_runner)
    )
    assert "exec codex" in result.stdout
    assert "--platform linux/amd64" in result.stdout
