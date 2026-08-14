"""Validate the public image's real parent/vendor Git topology."""

# @dependency-start
# contract test
# responsibility Verifies the immutable parent Git root, nested AgentCanon gitlink, prebuilt runtime, and container cleanup.
# upstream design ../../CONTAINER_OPERATIONS.md public Docker test boundary
# upstream implementation ../../docker/Dockerfile materializes the parent/vendor image topology
# upstream implementation ../../test/testrunner.sh authenticates and executes from the nested source root
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = PROJECT_ROOT / "docker" / "Dockerfile"
RUNNER = PROJECT_ROOT / "test" / "testrunner.sh"
IMAGE = os.environ.get("AGENT_CANON_TEST_IMAGE", "agent-canon")


def test_image_sources_define_real_parent_vendor_topology() -> None:
    """Static sources retain the topology and reject the synthetic-root route."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert "/opt/agent-canon-parent/vendor/agent-canon" in dockerfile
    assert '[submodule \"vendor/agent-canon\"]' in dockerfile
    assert "160000:commit:" in dockerfile
    assert "WORKDIR /opt/agent-canon-parent/vendor/agent-canon" in dockerfile
    assert "cargo test --locked --offline --no-run" in dockerfile
    assert "AGENT_CANON_TEST_PARENT_ROOT" not in runner
    assert "child_process_environment" not in runner


def test_built_image_exposes_exact_gitlink_and_is_removed_after_probe() -> None:
    """A no-mount probe sees exact identities and leaves no container behind."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable in this runtime")
    image = subprocess.run(
        [docker, "image", "inspect", IMAGE],
        check=False,
        capture_output=True,
        text=True,
    )
    if image.returncode != 0:
        pytest.skip(f"topology image is unavailable: {IMAGE}")

    container_name = f"agent-canon-topology-{os.getpid()}"
    probe = """
import json
import os
import subprocess
from pathlib import Path

parent = Path('/opt/agent-canon-parent')
source = parent / 'vendor' / 'agent-canon'

def git(root, *args):
    return subprocess.run(
        ['git', '-C', str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

source_head = git(source, 'rev-parse', 'HEAD')
gitlink = git(parent, 'ls-tree', 'HEAD', 'vendor/agent-canon').split()
assert Path.cwd() == source
assert git(parent, 'rev-parse', '--show-toplevel') == str(parent)
assert git(source, 'rev-parse', '--show-toplevel') == str(source)
assert gitlink[:3] == ['160000', 'commit', source_head]
assert git(source, 'symbolic-ref', 'HEAD') == 'refs/heads/main'
assert git(source, 'rev-parse', 'refs/heads/main') == source_head
expected_origins = {
    parent: 'https://github.com/iwashita-nozomu/project_template.git',
    source: 'https://github.com/iwashita-nozomu/agent-canon.git',
}
for root, expected_origin in expected_origins.items():
    assert git(root, 'remote') == 'origin'
    assert git(root, 'remote', 'get-url', 'origin') == expected_origin
    assert git(root, 'for-each-ref', '--format=%(refname)', 'refs/remotes') == ''
assert git(parent, 'config', '-f', '.gitmodules', '--get', 'submodule.vendor/agent-canon.url') == 'https://github.com/iwashita-nozomu/agent-canon.git'
for root in (parent, source):
    credentials = subprocess.run(
        ['git', '-C', str(root), 'config', '--get-regexp', '^credential\\.'],
        check=False,
        capture_output=True,
        text=True,
    )
    assert credentials.returncode == 1
runtime = parent / '.agent-canon' / 'image-runtime'
assert (runtime / 'tools' / 'agent-canon' / 'bin' / 'agent-canon').is_file()
assert os.access(runtime / 'tools' / 'agent-canon' / 'bin' / 'agent-canon', os.X_OK)
assert (runtime / 'cargo-target').is_dir()
assert 'AGENT_CANON_TEST_PARENT_ROOT' not in os.environ
print(json.dumps({'gitlink': source_head, 'parent': str(parent), 'source': str(source)}))
"""
    result = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--name",
            container_name,
            IMAGE,
            "python3",
            "-c",
            probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["parent"] == "/opt/agent-canon-parent"
    assert payload["source"] == "/opt/agent-canon-parent/vendor/agent-canon"
    absence = subprocess.run(
        [docker, "container", "inspect", container_name],
        check=False,
        capture_output=True,
        text=True,
    )
    assert absence.returncode != 0
