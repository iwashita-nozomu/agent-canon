"""Static contract checks for the shared AgentCanon tool image."""

# @dependency-start
# contract test
# responsibility Verifies the shared tool image boundary, runtime invariants, and LSP/Rust scope.
# upstream design ../../documents/design/agent-canon-bootstrap-tool-runtime.md shared tool image contract
# upstream implementation ../../bootstrap/container/image/Dockerfile image definition
# upstream implementation ../../bootstrap/container/lifecycle/entrypoint.sh health and dispatch entrypoint
# upstream implementation ../../bootstrap/container/image/dependencies.toml typed image capabilities
# upstream implementation ../../tools/runtime/container/devcontainer_dependencies.py canonical Cargo snapshot digest owner
# @dependency-end

from __future__ import annotations

import hashlib
import re
import stat
import subprocess
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from tools.runtime.dispatch import tool_dispatch
from tools.runtime.container.devcontainer_dependencies import Installer


ROOT = Path(__file__).resolve().parents[2]
CONTAINER = ROOT / "bootstrap" / "container"
DOCKERFILE = CONTAINER / "image" / "Dockerfile"
ENTRYPOINT = CONTAINER / "lifecycle" / "entrypoint.sh"
DEPENDENCIES = CONTAINER / "image" / "dependencies.toml"
ROOT_DOCKERIGNORE = ROOT / ".dockerignore"
WRAPPER = CONTAINER / "dispatch" / "tool-wrapper.sh"


def test_legacy_agent_canon_devcontainer_surface_is_absent() -> None:
    """The shared tool runtime has no hidden compatibility devcontainer tree."""
    retired = (
        ROOT / ".devcontainer",
        ROOT / "tools/ci/container_config.py",
        ROOT / "tools/ci/run_codex_in_repo_container.py",
        ROOT / "tools/ci/codex-container-profiles.toml",
    )
    assert all(not path.exists() for path in retired)


def test_container_definition_has_only_expected_files() -> None:
    names = {path.name for path in CONTAINER.iterdir()}
    assert names <= {
        "image",
        "lifecycle",
        "dispatch",
        "README.md",
    }
    assert {"image", "lifecycle", "dispatch"} <= names
    assert {"Dockerfile", "dependencies.toml"} <= {
        path.name for path in (CONTAINER / "image").iterdir()
    }
    assert {"entrypoint.sh"} <= {
        path.name for path in (CONTAINER / "lifecycle").iterdir()
    }
    assert {"tool-wrapper.sh"} <= {
        path.name for path in (CONTAINER / "dispatch").iterdir()
    }


def test_dockerfile_is_digest_pinned_without_agentcanon_user_policy() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM node:22.14.0-bullseye-slim@sha256:" in text
    assert "FROM ubuntu:22.04@sha256:" in text
    assert "AGENT_CANON_RUNTIME_UID" not in text
    assert "AGENT_CANON_RUNTIME_GID" not in text
    assert "USER agentcanon" not in text
    assert "ENTRYPOINT [\"/usr/local/bin/agent-canon-container-entrypoint\"]" in text
    assert 'CMD ["resident"]' in text
    assert "rootless" not in text.lower()
    digests = re.findall(r"@sha256:([0-9a-f]{64})(?:\s|$)", text, re.MULTILINE)
    assert len(digests) == 2
    assert "--manifest /opt/agent-canon/bootstrap/container/image/dependencies.toml" in text
    assert "COPY bootstrap/container/image/dependencies.toml" in text
    assert "COPY tools /usr/local/share/agent-canon/runtime/tools" in text
    assert "skill_shim_materializer.py" in text
    assert "materialize --root /usr/local/share/agent-canon/runtime --all --image-build" in text
    assert "COPY .codex/personal/skills" not in text
    assert "COPY .codex/agents /usr/local/share/agent-canon/runtime/.codex/agents" in text
    assert "COPY eval/definitions /usr/local/share/agent-canon/runtime/eval/definitions" in text
    assert "COPY AGENTS.md ROOT_AGENTS.md /usr/local/share/agent-canon/runtime/" in text
    assert "COPY agents /usr/local/share/agent-canon/runtime/agents" in text
    assert "COPY schemas /usr/local/share/agent-canon/runtime/schemas" in text
    assert "PIPX_HOME=/usr/local/share/agent-canon/pipx" in text
    assert "PIPX_BIN_DIR=/usr/local/bin" in text
    assert "command -v yamllint" in text
    assert "command -v check-jsonschema" in text
    materializer_offset = text.index("skill_shim_materializer.py")
    assert text.index("command -v yamllint") < materializer_offset
    assert text.index("command -v check-jsonschema") < materializer_offset
    assert "runtime/schemas/agent-canon/skill-catalog.schema.json" in text
    assert "tools/catalog.yaml" in text
    assert "tools/runtime/dispatch/tool_dispatch.py" in text
    assert (
        "COPY tools/runtime/dispatch/agent-canon "
        "/opt/agent-canon/tools/runtime/dispatch/agent-canon"
    ) in text
    assert "COPY bootstrap/container/dispatch/tool-wrapper.sh" in text
    assert "COPY bootstrap/container/lifecycle/entrypoint.sh" in text
    assert "/.devcontainer/" not in text


def test_dockerfile_publishes_dispatcher_marker_contract() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    image_digest = "sha256:" + hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest()
    runtime_digest = "sha256:" + hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest()
    assert tool_dispatch.CONTAINER_MARKER == b"agent-canon-tool-container/v1\n"
    assert tool_dispatch.RUNTIME_MARKER == b"agent-canon-runtime/v1\n"
    assert "printf 'agent-canon-tool-container/v1\\n'" in text
    assert "printf 'agent-canon-runtime/v1\\n'" in text
    assert "chmod 0444" in text
    assert "stat -c '%a:%u:%g'" in text
    assert "444:0:0" in text
    assert "AGENT_CANON_IMAGE_ROOT=/usr/local/share/agent-canon" in text
    assert "AGENT_CANON_IMAGE_DEPENDENCIES_ROOT=/usr/local/share/agent-canon/image-dependencies" in text
    assert "AGENT_CANON_RUNTIME_TOOLS_ROOT=/usr/local/share/agent-canon/runtime" in text
    assert f"AGENT_CANON_IMAGE_MARKER_DIGEST={image_digest}" in text
    assert f"AGENT_CANON_RUNTIME_MARKER_DIGEST={runtime_digest}" in text


def test_dispatcher_marker_fixture_accepts_root_owned_read_only_files(tmp_path: Path) -> None:
    image_root = tmp_path / "image"
    runtime_root = image_root / "runtime"
    image_root.mkdir()
    runtime_root.mkdir()
    image_marker = image_root / tool_dispatch.CONTAINER_MARKER_NAME
    runtime_marker = runtime_root / tool_dispatch.RUNTIME_MARKER_NAME
    image_marker.write_bytes(tool_dispatch.CONTAINER_MARKER)
    runtime_marker.write_bytes(tool_dispatch.RUNTIME_MARKER)
    image_marker.chmod(0o444)
    runtime_marker.chmod(0o444)
    assert tool_dispatch._immutable_file(
        image_marker, tool_dispatch.CONTAINER_MARKER, field="image"
    ) == hashlib.sha256(tool_dispatch.CONTAINER_MARKER).hexdigest()
    assert tool_dispatch._immutable_file(
        runtime_marker, tool_dispatch.RUNTIME_MARKER, field="runtime"
    ) == hashlib.sha256(tool_dispatch.RUNTIME_MARKER).hexdigest()


def test_dockerfile_declares_run_side_contract_and_healthcheck() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    required = (
        'io.agent-canon.runtime="shared-v1"',
        'io.agent-canon.container.max-instances="1"',
        'io.agent-canon.run.read-only-rootfs="true"',
        'io.agent-canon.run.network="none"',
        'io.agent-canon.run.cap-drop="ALL"',
        'io.agent-canon.run.no-new-privileges="true"',
        'io.agent-canon.run.cpus="2"',
        'io.agent-canon.run.memory="4g"',
        'io.agent-canon.run.pids-limit="512"',
        'io.agent-canon.run.tmpfs="/tmp"',
        "HEALTHCHECK",
        '"/usr/local/bin/agent-canon-container-entrypoint", "health"',
    )
    for marker in required:
        assert marker in text
    for forbidden in ("--privileged", "docker.sock", "ssh-agent", "GH_TOKEN"):
        assert forbidden not in text


def test_dockerfile_does_not_duplicate_dependency_manifest_validation() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "container.platform must be linux/amd64" not in text
    assert "AGENT_CANON_RUNTIME_UID" not in text
    assert "AGENT_CANON_RUNTIME_GID" not in text


def test_dockerfile_does_not_pull_project_or_host_tooling() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    for forbidden in (
        "compose",
        "gpu",
        "codex-cli",
        "@openai/codex",
        "github cli",
        "sudo",
        "project_uid",
        "project_gid",
    ):
        assert forbidden not in text
    assert "      git \\" in text


def test_entrypoint_is_executable_and_has_strict_health_dispatch() -> None:
    mode = ENTRYPOINT.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert 'case "${1:-}" in' in text
    assert "health|--healthcheck)" in text
    assert '[[ "${uid}" == "0" ]]' not in text
    assert 'exec /usr/local/bin/agent-canon-tool "$@"' in text
    assert 'usage: $0 health | resident | tool run <catalog-id> -- [args...]' in text
    assert 'exec "$@"' not in text
    assert "sleep infinity" in text
    assert "resident)" in text
    subprocess.run(["bash", "-n", str(ENTRYPOINT)], check=True)


def test_entrypoint_rejects_untyped_command_and_accepts_typed_resident() -> None:
    rejected = subprocess.run(
        ["bash", str(ENTRYPOINT), "sleep", "infinity"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 64
    assert "resident" in rejected.stderr

    # Do not leave a test sleep process behind; timeout proves the resident
    # route entered its long-lived command and is terminated by the harness.
    resident = subprocess.run(
        ["timeout", "0.2", "bash", str(ENTRYPOINT), "resident"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert resident.returncode == 124


def test_typed_tool_wrapper_rejects_arbitrary_dispatch() -> None:
    mode = WRAPPER.stat().st_mode
    assert mode & stat.S_IXUSR
    text = WRAPPER.read_text(encoding="utf-8")
    assert "tool" in text and "run" in text
    assert "tool_dispatch.py" in text
    assert "--container-exec" in text
    assert "AGENT_CANON_EXECUTION_PLANE=tool-container" in text
    assert "--root /usr/local/share/agent-canon/runtime" in text
    assert "usage: agent-canon tool run" in text
    assert '[[ "${1:-}" != "tool" || "${2:-}" != "run" ]]' in text


def test_dependency_manifest_is_python_rust_lsp_only() -> None:
    document = tomllib.loads(DEPENDENCIES.read_text(encoding="utf-8"))
    assert document["schema"] == "agent-canon.tool-dependencies"
    assert document["schema_version"] == 2
    assert "container" not in document
    records = document["records"]
    ids = {record["id"] for record in records}
    assert ids == {
        "pipx",
        "check-jsonschema",
        "yamllint",
        "pyright-language-server",
        "bash-language-server",
        "jq",
        "tree",
        "clang-format",
        "clangd-language-server",
        "rust-toolchain",
        "agent-canon-cli",
    }
    assert not ids & {"github-cli", "codex-cli"}
    assert {record["method"] for record in records} <= {
        "apt-package",
        "apt-repository",
        "npm-global",
        "pipx",
        "rust-toolchain",
        "cargo-source-build",
    }
    cli = next(record for record in records if record["id"] == "agent-canon-cli")
    assert cli["source_identity"] == "canonical-snapshot"
    assert cli["locked"] is True
    assert len(cli["source_tree_sha256"]) == 64
    assert len(cli["cargo_lock_sha256"]) == 64
    source_digest, lock_digest = Installer._cargo_snapshot(
        ROOT / "tools/runtime/dispatch/agent-canon"
    )
    assert cli["source_tree_sha256"] == source_digest
    assert cli["cargo_lock_sha256"] == lock_digest
    assert cli["source"] == "tools/runtime/dispatch/agent-canon"
    assert all("project" not in str(record).lower() for record in records)


def test_single_repository_dockerignore_is_deny_by_default() -> None:
    lines = [
        line.strip()
        for line in ROOT_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines[0] == "**"
    assert "!bootstrap/container/**" in lines
    assert "tools/runtime/dispatch/agent-canon/target/**" in lines
    assert "**/__pycache__/**" in lines


def test_repository_root_dockerignore_exposes_every_copy_source() -> None:
    lines = {
        line.strip()
        for line in ROOT_DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "**" in lines
    for source in (
        "!bootstrap/container/**",
        "!.codex/agents/**",
        "!eval/**",
        "!references/**",
        "!templates/**",
        "!tools/**",
        "!tools/runtime/dispatch/agent-canon/**",
    ):
        assert source in lines
    assert ".codex/personal/**" in lines
    assert not any(line.startswith("!.devcontainer") for line in lines)
