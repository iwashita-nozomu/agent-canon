"""Focused tests for parent-owned policy inventory retrieval."""

# @dependency-start
# contract test
# responsibility Verifies parent-owned temporary retrieval and race-safe cleanup for the fixed AgentCanon-log policy inventory.
# upstream design ../../documents/design/runtime-log-repository-lifecycle.md RL-009..RL-012 policy evidence
# upstream implementation ../../tools/agent_tools/check_agent_canon_log_policy.py owns read-only inventory retrieval
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py owns temporary target capabilities and cleanup
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

import check_agent_canon_log_policy as policy  # noqa: E402


def test_policy_module_imports_as_package() -> None:
    """The policy tool supports both package and standalone entrypoints."""
    result = subprocess.run(
        [sys.executable, "-c", "import tools.agent_tools.check_agent_canon_log_policy"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_retrieve_inventory_blob_uses_parent_temp_receipt(tmp_path: Path) -> None:
    """Git retrieval uses a parent-owned temporary receipt and removes it."""
    parent = tmp_path / "parent"
    subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
    created: list[object] = []
    original_open = policy.ParentRootSideEffectBoundary.open_parent_owned_target

    def capture_open(boundary, attestation, candidate, purpose):
        handle = original_open(boundary, attestation, candidate, purpose)
        created.append(handle)
        return handle

    blob = b'{"schema":"agent-canon-log-legacy-inventory.v1"}\n'
    original_run = subprocess.run

    def fake_run(args, **kwargs):
        command = list(args)
        if command[0] != "git":
            return original_run(args, **kwargs)
        retrieval_operation = (
            command[1:3] in (["init", "-q"], ["remote", "add"])
            or command[1] == "fetch"
            or command[1] == "show"
        )
        if not retrieval_operation:
            return original_run(args, **kwargs)
        assert kwargs["cwd"].startswith("/proc/self/fd/")
        assert kwargs["pass_fds"]
        if command[1:3] == ["init", "-q"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if command[1:3] == ["remote", "add"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if "fetch" in command:
            return subprocess.CompletedProcess(args, 0, "", "")
        if "show" in command:
            return subprocess.CompletedProcess(args, 0, blob, b"")
        return original_run(args, **kwargs)

    with mock.patch.dict(
        os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}
    ), mock.patch.object(
        policy.ParentRootSideEffectBoundary,
        "open_parent_owned_target",
        capture_open,
    ), mock.patch.object(policy.subprocess, "run", side_effect=fake_run):
        observed = policy.retrieve_inventory_blob("https://example.invalid/policy.git", "abc")

    assert observed == blob
    assert len(created) == 1
    assert not created[0].physical_path.exists()


def test_retrieve_inventory_blob_rejects_replaced_target_without_outside_write(
    tmp_path: Path,
) -> None:
    """An in-parent target replacement is typed while Git retains the inherited fd."""
    parent = tmp_path / "parent"
    subprocess.run(["git", "init", "-q", "-b", "main", str(parent)], check=True)
    created: list[object] = []
    original_open = policy.ParentRootSideEffectBoundary.open_parent_owned_target
    original_run = subprocess.run
    blob = b"inventory"
    replaced = False
    target_path: Path | None = None
    moved_path: Path | None = None

    def capture_open(boundary, attestation, candidate, purpose):
        handle = original_open(boundary, attestation, candidate, purpose)
        created.append(handle)
        return handle

    def fake_run(args, **kwargs):
        nonlocal moved_path, replaced, target_path
        command = list(args)
        if command[0] != "git":
            return original_run(args, **kwargs)
        retrieval_operation = (
            command[1:3] in (["init", "-q"], ["remote", "add"])
            or command[1] == "fetch"
            or command[1] == "show"
        )
        if not retrieval_operation:
            return original_run(args, **kwargs)
        assert kwargs["cwd"].startswith("/proc/self/fd/")
        assert kwargs["pass_fds"]
        if not replaced:
            handle = created[0]
            target = handle.physical_path
            moved = target.with_name(target.name + "-moved")
            target.rename(moved)
            target.mkdir()
            target_path = target
            moved_path = moved
            replaced = True
        if command[1:3] == ["init", "-q"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if command[1:3] == ["remote", "add"]:
            return subprocess.CompletedProcess(args, 0, b"", b"")
        if command[1] == "fetch":
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, blob, b"")

    with mock.patch.dict(
        os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}
    ), mock.patch.object(
        policy.ParentRootSideEffectBoundary,
        "open_parent_owned_target",
        capture_open,
    ), mock.patch.object(policy.subprocess, "run", side_effect=fake_run):
        try:
            policy.retrieve_inventory_blob("https://example.invalid/policy.git", "abc")
        except policy.ParentRootSideEffectError as exc:
            assert exc.reject is policy.ParentRootReject.ROOT_RACE_DETECTED
        else:
            raise AssertionError("target replacement was not rejected")

    assert len(created) == 1
    assert target_path is not None and moved_path is not None
    with mock.patch.dict(
        os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}
    ):
        boundary, attestation = policy._parent_capability()
        for path in (target_path, moved_path):
            if not path.exists():
                continue
            receipt = boundary.resolve_parent_owned_path(
                attestation, path, "policy-replacement-test-cleanup"
            )
            boundary.remove_parent_owned_tree(
                attestation, receipt, "policy-replacement-test-cleanup"
            )
