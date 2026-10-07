"""Opt-in native Docker regression for Issue #1370's cross-checkout authority."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from conftest import create_source_checkout

# Capture before bootstrap_test_isolation clears inherited controller settings.
LIVE_DOCKER = os.environ.get("AGENT_CANON_LIVE_DOCKER") == "1"
DOCKER = os.environ.get("AGENT_CANON_DOCKER", "docker")
pytestmark = pytest.mark.skipif(
    not LIVE_DOCKER,
    reason="set AGENT_CANON_LIVE_DOCKER=1 in the native Docker integration environment",
)
PROJECTIONS = ("mounts.toml", "mounts.tsv", "rollback-plan.tsv", "rollback-mounts.tsv")


def run(*arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, timeout=900, env=env
    )
    assert result.returncode == 0, (
        f"{arguments!r}\nexit={result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    return result.stdout


def bootstrap(source: Path, control: Path, *arguments: str) -> str:
    return run(
        "bash",
        str(source / "bootstrap.sh"),
        "--repository-root",
        str(source),
        "--control-parent-root",
        str(control),
        *arguments,
        env={**os.environ, "AGENT_CANON_DOCKER": DOCKER},
    )


def readback(source: Path, control: Path, targets: dict[str, Path]) -> dict[str, Any]:
    status = json.loads(bootstrap(source, control, "status"))
    runtime = control / ".runtime"
    digest = hashlib.sha256(str(control).encode()).hexdigest()
    name = f"agent-canon-tools-{digest[:16]}"
    assert status["runtime_root"] == str(runtime)
    assert status["container"]["name"] == name
    assert status["container"]["running"] is True
    assert status["container"]["health"] == "healthy"
    # Source-bind drift may be reported before a mutating call from the anchor;
    # status must not repair that drift or select another runtime projection.
    container = json.loads(run(DOCKER, "container", "inspect", name))[0]
    mounts = container["Mounts"]
    assert [
        (mount["Type"], mount.get("Name"), mount["RW"])
        for mount in mounts
        if mount["Destination"] == "/var/lib/agent-canon"
    ] == [("volume", f"agent-canon-runtime-{digest}", True)]
    assert run(
        DOCKER,
        "container",
        "ls",
        "--all",
        "--filter",
        f"label=io.agent-canon.control-root-digest={digest}",
        "--format",
        "{{.Names}}",
    ).splitlines() == [name]
    assert sorted(
        (mount["Source"], mount["Destination"], mount["RW"])
        for mount in mounts
        if mount["Destination"].startswith("/targets/")
    ) == sorted((str(path), f"/targets/{key}", False) for key, path in targets.items())

    # Read the actual named volume. There is no invented host registry bind,
    # modeled Docker response, or host-Python execution of the controller.
    resident = json.loads(
        run(
            DOCKER,
            "exec",
            name,
            "python3",
            "-c",
            """
import json
import sys
from pathlib import Path
root = Path('/var/lib/agent-canon')
projection = {}
for name in sys.argv[1:]:
    path = root / 'exchange' / name
    assert not path.is_symlink(), str(path)
    projection[name] = path.read_text() if path.exists() else None
print(json.dumps({'state': json.loads((root / 'runtime/state.json').read_text()),
                  'projection': projection}))
""",
            *PROJECTIONS,
        )
    )
    state = resident["state"]
    projection = resident["projection"]
    directories = (
        runtime / "container-state",
        runtime / "container-state/container-runtime",
    )
    for filename, contents in projection.items():
        for directory in directories:
            path = directory / filename
            assert not path.is_symlink(), str(path)
            assert (path.read_text() if path.exists() else None) == contents, str(path)
    registry = tomllib.loads(projection["mounts.toml"])
    assert registry["schema"] == "agent-canon.mount-registry.v2"
    for records in (state["targets"], registry.get("targets", {})):
        assert set(records) == set(targets)
        for key in targets:
            assert records[key]["root"] == f"/targets/{key}"
            assert records[key]["mode"] == "read-only"
    assert {key: record["host_root"] for key, record in state["targets"].items()} == {
        key: str(path) for key, path in targets.items()
    }
    assert sorted(projection["mounts.tsv"].splitlines()) == sorted(
        f"target\t{key}\t{path}\t/targets/{key}\tread-only"
        for key, path in targets.items()
    )
    for key, path in targets.items():
        assert run(DOCKER, "exec", name, "cat", f"/targets/{key}/marker.txt") == (
            path / "marker.txt"
        ).read_text()

    # Rollback describes its own prior generation, not the current target set.
    rollback = state.get("rollback_generation")
    if rollback:
        previous = state["generations"][rollback]["targets"]
        plan = projection["rollback-plan.tsv"]
        assert plan is not None
        assert plan.splitlines()[0] == "schema\tagent-canon.rollback-plan.v1"
        rows = [line.split("\t") for line in plan.splitlines()]
        assert sorted(
            (row[2], row[3], row[4])
            for row in rows
            if row[0] == "mount" and row[3].startswith("/targets/")
        ) == sorted(
            (record["host_root"], record["root"], "true")
            for record in previous.values()
        )
        rollback_mounts = projection["rollback-mounts.tsv"]
        if rollback_mounts is not None:
            assert sorted(rollback_mounts.splitlines()) == sorted(
                f"target\t{key}\t{record['host_root']}\t{record['root']}\tread-only"
                for key, record in previous.items()
            )
    return {"id": container["Id"], "image": container["Image"], **resident}


def test_topic_registration_anchor_status_remove_share_projection(
    tmp_path: Path,
) -> None:
    """Keep one control-root resident, including a nonempty rollback snapshot."""
    anchor = create_source_checkout(tmp_path / "anchor")
    topic = tmp_path / "topic"
    run(
        "git",
        "-C",
        str(anchor),
        "worktree",
        "add",
        "-b",
        "test/1370-topic",
        str(topic),
    )
    control = (tmp_path / "control").resolve()
    control.mkdir()
    targets: dict[str, Path] = {}
    for label in ("retained", "removed"):
        path = control / label
        path.mkdir()
        run("git", "-C", str(path), "init", "-q", "-b", "main")
        (path / "marker.txt").write_text(f"{label}\n", encoding="utf-8")
        run("git", "-C", str(path), "add", "marker.txt")
        run(
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=AgentCanon live test",
            "-c",
            "user.email=agent-canon-live@example.invalid",
            "commit",
            "-qm",
            "fixture",
        )
        run(
            "git",
            "-C",
            str(path),
            "remote",
            "add",
            "origin",
            f"https://github.com/example/issue-1370-{label}.git",
        )
        targets[hashlib.sha256(str(path).encode()).hexdigest()] = path

    cleanup_source = anchor
    try:
        # Unlike install, update --local-build does not fetch/reset source main.
        bootstrap(anchor, control, "update", "--local-build")
        initial = readback(anchor, control, {})
        state_root = control / ".runtime"
        relative_paths = [f"container-state/{name}" for name in PROJECTIONS]
        relative_paths.append("host-state/active-image.tsv")
        stale = {
            relative: (
                (state_root / relative).read_bytes()
                if (state_root / relative).exists()
                else None
            )
            for relative in relative_paths
        }
        # Only test-owned checkout-local decoys receive the pre-registration
        # snapshot. Never hand-edit the authority or its rollback files.
        for source in (anchor, topic):
            for relative, contents in stale.items():
                if contents is not None:
                    path = source / ".runtime" / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents)

        cleanup_source = topic
        for path in targets.values():
            bootstrap(topic, control, "target", "add", "--root", str(path))
        registered = readback(topic, control, targets)
        assert readback(anchor, control, targets) == registered
        assert registered["image"] == initial["image"]

        removed = next(key for key, path in targets.items() if path.name == "removed")
        cleanup_source = anchor
        bootstrap(anchor, control, "target", "remove", "--root", str(targets[removed]))
        assert targets[removed].is_dir()  # Not a missing-host-checkout scenario.
        remaining = {key: path for key, path in targets.items() if key != removed}
        after = readback(anchor, control, remaining)
        assert readback(topic, control, remaining) == after
        assert after["image"] == initial["image"]
        assert after["id"] != registered["id"]  # A real resident reconstruction.
        rollback = after["state"]["rollback_generation"]
        assert set(after["state"]["generations"][rollback]["targets"]) == set(targets)

        # Consume the same rollback plan through the public anchor lifecycle.
        bootstrap(anchor, control, "rollback")
        restored = readback(anchor, control, targets)
        assert readback(topic, control, targets) == restored
        assert restored["image"] == initial["image"]
        assert restored["id"] != after["id"]
        for source in (anchor, topic):
            for relative, contents in stale.items():
                path = source / ".runtime" / relative
                assert not path.is_symlink(), str(path)
                assert (path.read_bytes() if path.exists() else None) == contents
    finally:
        # Existing lifecycle owns teardown of this test's control-root resources.
        # A cleanup failure is visible; do not bypass ownership with raw deletion.
        bootstrap(cleanup_source, control, "uninstall")
