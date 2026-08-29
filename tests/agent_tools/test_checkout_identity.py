# @dependency-start
# contract test
# responsibility Verifies the bounded checkout identity readback and transition projections.
# upstream implementation ../../tools/runtime/authority/checkout_identity.py owns read-only checkout identity
# downstream implementation ../../tools/runtime/manifest/manifest_rendering.py projects the identity contract into handoffs
# @dependency-end
"""Focused tests for checkout identity boundaries."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools.runtime.authority.checkout_identity import resolve_checkout_identity


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "--initial-branch", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "AgentCanon test")
    (root / "README.md").write_text("identity\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    _git(root, "remote", "add", "origin", "git@github.com:Iwashita-Nozomu/Agent-Canon.git")
    return root


def test_identity_reports_branch_and_normalized_remote(tmp_path: Path) -> None:
    root = _repository(tmp_path)

    identity = resolve_checkout_identity(root)

    assert identity.cwd == str(root.resolve())
    assert identity.git_root == str(root.resolve())
    assert identity.branch == "main"
    assert len(identity.head) == 40
    assert identity.remote == "iwashita-nozomu/agent-canon"
    assert tuple(identity.as_dict()) == ("cwd", "git_root", "branch", "head", "remote")


def test_identity_reports_detached_head(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "--detach", head)

    identity = resolve_checkout_identity(root)

    assert identity.branch == "detached"
    assert identity.head == head


def test_identity_tracks_cwd_transition_without_mutating_checkout(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    nested = root / "nested"
    nested.mkdir()
    before = resolve_checkout_identity(root)
    after = resolve_checkout_identity(nested)

    assert after.cwd == str(nested.resolve())
    assert after.git_root == before.git_root
    assert after.branch == before.branch
    assert after.head == before.head
    assert _git(root, "status", "--porcelain") == ""


def test_non_repository_uses_typed_unknown_fields(tmp_path: Path) -> None:
    identity = resolve_checkout_identity(tmp_path)

    assert identity.git_root == "unknown"
    assert identity.branch == "unknown"
    assert identity.head == "unknown"
    assert identity.remote == "unknown"
