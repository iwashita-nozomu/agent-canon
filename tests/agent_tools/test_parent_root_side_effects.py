# @dependency-start
# contract test
# responsibility Verifies authenticated parent capabilities, child state, publication, and exact cleanup.
# upstream implementation ../../tools/repository/workspace/parent_root_side_effects.py owns parent-local filesystem effects
# @dependency-end

"""Focused tests for the parent-root side-effect boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import tools.repository.workspace.parent_root_side_effects as side_effects
from tools.runtime.artifacts.runtime_artifacts import root_capability_environment
from tools.repository.workspace.parent_root_side_effects import (
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    child_environment,
    resolve_parent_owned_path,
)

_PARENT_BOUNDARY_PATH_KEYS = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_RUNTIME_ROOT",
    "AGENT_CANON_RUNTIME_ROOT_DEV",
    "AGENT_CANON_RUNTIME_ROOT_INO",
)


def _build_clean_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in _PARENT_BOUNDARY_PATH_KEYS:
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    return env


def git_repo(path: Path, *, remote: str | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    if remote is not None:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "--allow-empty",
                    "-m", "fixture"], check=True, capture_output=True)


def pending_handoff_nonces(root: Path) -> dict[str, object]:
    state = root / ".agent-canon" / "handoff" / "nonces.json"
    if not state.exists():
        return {}
    value = json.loads(state.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def attest(root: Path, **kwargs: object):
    git_repo(root, remote="https://example.invalid/parent.git")
    return ParentRootSideEffectBoundary().attest(
        ParentRootAttestationRequest(cwd=root, explicit_root=root, purpose="test", **kwargs)
    )


def test_attestation_binds_parent_source_and_clone_identities(tmp_path: Path) -> None:
    source = tmp_path / "vendor" / "agent-canon"
    clone = tmp_path / "workspace" / "topic" / "agent-canon"
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    git_repo(source, remote="https://example.invalid/source.git")
    git_repo(clone, remote="https://example.invalid/clone.git")
    module = tmp_path / ".gitmodules"
    module.write_text(
        "[submodule \"vendor/agent-canon\"]\n"
        "\tpath = vendor/agent-canon\n"
        "\turl = https://example.invalid/source.git\n", encoding="utf-8"
    )
    module_sha = hashlib.sha256(module.read_bytes()).hexdigest()
    source_commit = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    source_tree = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
    parent_repo_id = hashlib.sha256(
        f"{tmp_path.resolve()}\0https://example.invalid/parent.git".encode()
    ).hexdigest()
    subprocess.run([
        "git", "-C", str(tmp_path), "update-index", "--add", "--cacheinfo",
        f"160000,{source_commit},vendor/agent-canon",
    ], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c",
                    "user.email=test@example.invalid", "commit", "-m", "gitlink"],
                   check=True, capture_output=True)
    owner = tmp_path / "owner.json"
    owner_body = {
        "schema": "agent-canon.owner-evidence.v1", "parent_repo_id": parent_repo_id,
        "physical_parent": str(tmp_path), "module_path": "vendor/agent-canon",
        "remote_url": "https://example.invalid/parent.git", "observed_commit": source_commit,
        "observed_tree": source_tree,
    }
    owner_body["evidence_sha256"] = hashlib.sha256(
        json.dumps(owner_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    owner.write_text(json.dumps({**owner_body}, sort_keys=True), encoding="utf-8")
    owner_sha = hashlib.sha256(owner.read_bytes()).hexdigest()
    marker = tmp_path / "marker.json"
    marker.write_text(json.dumps({
        "schema": "agent-canon.repository-topic.v2", "parent_repo_id": parent_repo_id,
        "topic_slug": "topic", "repo_name": "agent-canon", "clone_path": str(clone),
        "remote_url": "https://example.invalid/clone.git", "branch": "main",
        "owner_evidence_sha256": owner_sha, "source_commit": source_commit,
        "source_tree": source_tree, "created_at": "2026-08-10T00:00:00Z", "nonce": "nonce",
    }), encoding="utf-8")
    receipt = ParentRootSideEffectBoundary().attest(
        ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            source_root=source,
            clone_root=clone,
            topic_marker=marker,
            gitmodules=module,
            owner_evidence=owner,
            expected_module_digest=module_sha,
            purpose="test",
        )
    )
    assert receipt.status == "attested"
    assert receipt.root_kind == "topic"
    assert receipt.parent_root == tmp_path.resolve()
    assert (receipt.parent_dev, receipt.parent_ino) != (0, 0)
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, source_root=source, clone_root=clone,
        topic_marker=marker, gitmodules=module, owner_evidence=owner, purpose="test",
        expected_module_digest=module_sha,
    )
    marker_value = json.loads(marker.read_text(encoding="utf-8"))
    marker_value["branch"] = "tampered"
    marker.write_text(json.dumps(marker_value), encoding="utf-8")
    with pytest.raises(ParentRootSideEffectError) as marker_tamper:
        ParentRootSideEffectBoundary().attest(request)
    assert marker_tamper.value.reject is ParentRootReject.MARKER_INVALID
    marker.write_text(json.dumps({**marker_value, "branch": "main"}), encoding="utf-8")
    module.write_text(
        "[submodule \"vendor/agent-canon\"]\n"
        "\tpath = vendor/agent-canon\n"
        "\turl = https://example.invalid/tampered.git\n", encoding="utf-8"
    )
    with pytest.raises(ParentRootSideEffectError) as module_tamper:
        ParentRootSideEffectBoundary().attest(request)
    assert module_tamper.value.reject is ParentRootReject.MODULE_INVALID


def test_missing_and_spoofed_roots_are_typed(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.attest(
            ParentRootAttestationRequest(
                cwd=tmp_path / "missing", explicit_root=tmp_path / "missing", purpose="test"
            )
        )
    assert missing.value.reject is ParentRootReject.ROOT_MISSING
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    with pytest.raises(ParentRootSideEffectError) as spoofed:
        boundary.attest(
            ParentRootAttestationRequest(
                cwd=outside, explicit_root=tmp_path, purpose="test"
            )
        )
    assert spoofed.value.reject is ParentRootReject.ROOT_SPOOFED


def test_arbitrary_directory_and_remote_spoof_are_rejected(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    with pytest.raises(ParentRootSideEffectError) as arbitrary:
        boundary.attest(ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test"))
    assert arbitrary.value.reject is ParentRootReject.ROOT_MISMATCH
    git_repo(tmp_path, remote="https://example.invalid/actual.git")
    with pytest.raises(ParentRootSideEffectError) as remote:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, expected_remote="https://example.invalid/expected.git", purpose="test"
        ))
    assert remote.value.reject is ParentRootReject.MARKER_INVALID


def test_missing_module_digest_and_exact_bound_schema_are_rejected(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    module = tmp_path / ".gitmodules"
    module.write_text("[submodule \"vendor/agent-canon\"]\n", encoding="utf-8")
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    boundary = ParentRootSideEffectBoundary()
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, gitmodules=module,
            expected_module_digest="0" * 64, purpose="test"
        ))
    assert missing.value.reject is ParentRootReject.MODULE_INVALID
    with pytest.raises(ParentRootSideEffectError) as absent:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path,
            expected_module_digest=digest, purpose="test"
        ))
    assert absent.value.reject is ParentRootReject.MODULE_INVALID
    marker = tmp_path / "marker.json"
    marker.write_text('{"schema":"agent-canon.repository-topic.v2","schema":"duplicate"}', encoding="utf-8")
    with pytest.raises(ParentRootSideEffectError) as malformed:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, topic_marker=marker, purpose="test"
        ))
    assert malformed.value.reject is ParentRootReject.MARKER_INVALID
    assert digest != "0" * 64


def test_regular_nested_git_is_not_a_submodule_gitlink(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    nested = tmp_path / "vendor" / "nested"
    git_repo(nested, remote="https://example.invalid/nested.git")
    module = tmp_path / ".gitmodules"
    module.write_text(
        "[submodule \"vendor/nested\"]\n"
        "\tpath = vendor/nested\n"
        "\turl = https://example.invalid/nested.git\n", encoding="utf-8"
    )
    with pytest.raises(ParentRootSideEffectError) as rejected:
        ParentRootSideEffectBoundary().attest(ParentRootAttestationRequest(
            cwd=tmp_path, explicit_root=tmp_path, source_root=nested,
            gitmodules=module, purpose="module-check",
        ))
    assert rejected.value.reject is ParentRootReject.MODULE_INVALID


def test_handoff_forgery_and_cross_instance_replay_are_rejected(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="test")
    request = ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=token)
    boundary.attest(request)
    with pytest.raises(ParentRootSideEffectError) as replay:
        ParentRootSideEffectBoundary().attest(request)
    assert replay.value.reject is ParentRootReject.HANDOFF_INVALID
    forged = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(ParentRootSideEffectError) as forgery:
        ParentRootSideEffectBoundary().attest(
            ParentRootAttestationRequest(cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=forged)
        )
    assert forgery.value.reject is ParentRootReject.HANDOFF_INVALID


def test_handoff_nonce_receipt_survives_a_new_process(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="process-test")
    code = (
        "from pathlib import Path; import sys; "
        "from tools.repository.workspace.parent_root_side_effects import *; "
        "request=ParentRootAttestationRequest(cwd=Path(sys.argv[1]), explicit_root=Path(sys.argv[1]), "
        "purpose='process-test', child_handoff_token=sys.argv[2]); "
        "ParentRootSideEffectBoundary().attest(request)"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(Path.cwd()),
        "PYTHONPYCACHEPREFIX": str(Path.cwd().parent / "test-tmp" / "pycache"),
    }
    accepted = subprocess.run([sys.executable, "-c", code, str(tmp_path), token], env=env, check=False)
    assert accepted.returncode == 0
    replayed = subprocess.run([sys.executable, "-c", code, str(tmp_path), token], env=env, check=False)
    assert replayed.returncode != 0


def test_handoff_source_and_clone_bindings_are_symmetric(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    source = tmp_path / "source"
    git_repo(source, remote="https://example.invalid/source.git")
    boundary = ParentRootSideEffectBoundary()
    token_with_source = boundary.issue_child_handoff(
        tmp_path, audience="test", source_root=source
    )
    with pytest.raises(ParentRootSideEffectError) as unexpected_source:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            purpose="test",
            child_handoff_token=token_with_source,
        ))
    assert unexpected_source.value.reject is ParentRootReject.HANDOFF_INVALID

    token_without_source = boundary.issue_child_handoff(tmp_path, audience="test")
    with pytest.raises(ParentRootSideEffectError) as missing_source:
        boundary.attest(ParentRootAttestationRequest(
            cwd=tmp_path,
            explicit_root=tmp_path,
            source_root=source,
            purpose="test",
            child_handoff_token=token_without_source,
        ))
    assert missing_source.value.reject is ParentRootReject.HANDOFF_INVALID


def test_clone_target_is_exclusively_reserved_and_fd_bound(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "workspace" / "topic" / "agent-canon"
    handle = boundary.open_parent_owned_target(receipt, target, "clone-target")
    try:
        assert handle.physical_path == target
        assert handle.proc_path == f"/proc/self/fd/{handle.target_fd}"
        assert os.fstat(handle.target_fd).st_ino == handle.target_ino
        assert os.listdir(handle.target_fd) == []
        with pytest.raises(ParentRootSideEffectError) as collision:
            boundary.open_parent_owned_target(receipt, target, "clone-target")
        assert collision.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    finally:
        handle.close()
    published = boundary.resolve_parent_owned_path(receipt, target, "clone-target")
    boundary.remove_parent_owned_tree(receipt, published, "clone-target-cleanup")
    assert not target.exists()


def test_tree_copy_uses_parent_owned_operations_and_preserves_exclusions(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    source = tmp_path / "source-tree"
    source.mkdir()
    (source / "keep.txt").write_text("keep\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "private").write_text("private\n", encoding="utf-8")
    target = tmp_path / "target-tree"
    target.mkdir()
    (target / "stale.txt").write_text("stale\n", encoding="utf-8")
    boundary.copy_parent_owned_tree(
        receipt, source, target, "tree-copy", exclude=(".git",)
    )
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (target / "stale.txt").exists()
    assert not (target / ".git").exists()


def test_git_config_add_uses_inherited_boundary_file_and_reads_back(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    config = tmp_path / "config" / "safe.directory.gitconfig"
    published = boundary.git_config_add(
        receipt, config, "safe.directory", str(tmp_path / "child"), "git-config-test"
    )
    value = subprocess.run(
        ["git", "config", "--file", str(config), "--get", "safe.directory"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert value == str(tmp_path / "child")
    assert published.target_dev is not None
    assert published.target_ino is not None


def test_checkout_index_uses_boundary_staging_and_atomic_publish(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("from-index\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "tracked",
        ],
        check=True,
        capture_output=True,
    )
    destination = tmp_path / "materialized" / "tracked.txt"
    published = boundary.checkout_index_parent_owned(
        receipt, tmp_path, "tracked.txt", destination, "checkout-index-test"
    )
    assert destination.read_text(encoding="utf-8") == "from-index\n"
    assert published.target_dev is not None
    assert published.target_ino is not None


def test_path_capability_accepts_in_root_symlink_and_rejects_escape(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "inside.txt"
    target.write_text("before", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    inside = boundary.resolve_parent_owned_path(receipt, link, "test")
    assert inside.physical_path == target
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    escaping = tmp_path / "escape.txt"
    escaping.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        resolve_parent_owned_path(receipt, escaping, "test")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    outside.unlink()


def test_remove_parent_owned_file_unlinks_directory_symlink_and_preserves_target(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "target-directory"
    target.mkdir()
    link = tmp_path / "tools-agent-canon"
    link.symlink_to(target, target_is_directory=True)
    capability = boundary.resolve_parent_owned_path(receipt, link, "lexical-link")

    boundary.remove_parent_owned_file(capability)

    assert not os.path.lexists(link)
    assert target.is_dir()


def test_remove_parent_owned_file_unlinks_direct_root_regular_file(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    regular = tmp_path / "direct-root-file"
    regular.write_text("remove me\n", encoding="utf-8")
    capability = boundary.resolve_parent_owned_path(receipt, regular, "regular-file")

    boundary.remove_parent_owned_file(capability)

    assert not regular.exists()


def test_remove_parent_owned_file_unlinks_broken_in_root_symlink(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    link = tmp_path / "broken-link"
    link.symlink_to("missing-target")
    capability = boundary.resolve_parent_owned_path(receipt, link, "broken-link")
    assert capability.target_dev is None
    assert capability.lexical_link_target == "missing-target"

    boundary.remove_parent_owned_file(capability)

    assert not os.path.lexists(link)


def test_external_missing_target_symlink_is_rejected_and_preserved(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    outside = tmp_path.parent / "missing-outside-target"
    link = tmp_path / "external-broken-link"
    link.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.resolve_parent_owned_path(receipt, link, "external-broken-link")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert os.path.lexists(link)


def test_lexical_symlink_replacement_is_rejected_without_removing_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    first_target = tmp_path / "first-target"
    second_target = tmp_path / "second-target"
    first_target.mkdir()
    second_target.mkdir()
    link = tmp_path / "replaced-link"
    link.symlink_to(first_target, target_is_directory=True)
    capability = boundary.resolve_parent_owned_path(receipt, link, "replacement-link")
    link.unlink()
    link.symlink_to(second_target, target_is_directory=True)

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.remove_parent_owned_file(capability)

    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert link.is_symlink()
    assert link.resolve() == second_target


def test_atomic_publish_and_child_environment_keep_home_unchanged(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    path = boundary.resolve_parent_owned_path(receipt, "reports/result.json", "report")
    boundary.atomic_publish(path, b"ok\n")
    assert path.physical_path.read_text(encoding="utf-8") == "ok\n"
    assert path.target_dev is None
    published = boundary.atomic_publish(path, b"updated\n")
    assert published.target_dev is not None
    assert published.target_ino is not None
    assert published.physical_path.read_text(encoding="utf-8") == "updated\n"
    original_home = os.environ.get("HOME")
    env = child_environment(
        receipt,
        {
            "HOME": original_home or "",
        },
    )
    assert env["HOME"] == (original_home or "")
    expected_tmp = (tmp_path / ".agent-canon" / "tmp").resolve()
    assert env["TMPDIR"] == str(expected_tmp)
    assert env["TEMP"] == str(expected_tmp)
    assert env["TMP"] == str(expected_tmp)
    assert env["AGENT_CANON_ACTIVE_REPOSITORY_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_PARENT_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_SOURCE_ROOT"] == str(tmp_path.resolve())
    assert env["AGENT_CANON_ROOT"] == env["AGENT_CANON_SOURCE_ROOT"]
    for name in (
        "TMPDIR", "TEMP", "TMP",
        "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX", "AGENT_CANON_TOOLS_HOME",
        "CARGO_HOME", "CARGO_TARGET_DIR", "AGENT_CANON_CLI_TARGET_DIR",
    ):
        assert Path(env[name]).resolve().is_relative_to(tmp_path.resolve())
    assert env["CARGO_TARGET_DIR"] == env["AGENT_CANON_CLI_TARGET_DIR"]


@pytest.mark.parametrize(
    "name",
    (
        "TMPDIR",
        "TEMP",
        "TMP",
        "XDG_CACHE_HOME",
        "PYTHONPYCACHEPREFIX",
        "AGENT_CANON_TOOLS_HOME",
        "AGENT_CANON_CLI_TARGET_DIR",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
    ),
)
def test_child_environment_rejects_external_override_before_creating_directories(
    tmp_path: Path,
    name: str,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    external = tmp_path.parent / f"external-child-{name.lower()}"

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.child_environment(
            receipt,
            {"HOME": "/unchanged/home", name: str(external)},
        )

    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert not (tmp_path / ".agent-canon" / "tmp").exists()
    assert not (tmp_path / ".agent-canon" / "cache").exists()
    assert not external.exists()


def test_abort_reserved_target_failure_leaves_target_absent(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    sibling = tmp_path / "workspace" / "topic" / "sibling"
    sibling.mkdir(parents=True)
    (sibling / "keep.txt").write_text("keep\n", encoding="utf-8")
    target = tmp_path / "workspace" / "topic" / "agent-canon"
    handle = boundary.open_parent_owned_target(receipt, target, "clone-target")
    (target / "partial" / "nested").mkdir(parents=True)
    (target / "partial" / "nested" / "residue.txt").write_text(
        "residue\n", encoding="utf-8"
    )

    boundary._abort_reserved_target(receipt, handle, "clone-failure")

    assert not target.exists()
    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    with pytest.raises(ParentRootSideEffectError):
        boundary._abort_reserved_target(receipt, handle, "clone-failure-reuse")


def test_abort_reserved_target_closes_fds_on_validation_error(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "workspace" / "topic" / "validation-error"
    handle = boundary.open_parent_owned_target(receipt, target, "validation-error")
    parent_fd, target_fd = handle.parent_fd, handle.target_fd
    handle.parent_dev += 1
    with pytest.raises(ParentRootSideEffectError):
        boundary._abort_reserved_target(receipt, handle, "validation-error")
    with pytest.raises(OSError):
        os.fstat(parent_fd)
    with pytest.raises(OSError):
        os.fstat(target_fd)
    published = boundary.resolve_parent_owned_path(receipt, target, "validation-error")
    boundary.remove_parent_owned_tree(receipt, published, "validation-error-cleanup")


def test_read_parent_owned_file_reads_exact_large_payload(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    payload = (b"0123456789abcdef" * ((16 * 1024 * 1024) // 16 + 1))[: 16 * 1024 * 1024 + 17]
    target = boundary.resolve_parent_owned_path(receipt, "reports/large.bin", "large-read")
    published = boundary.atomic_publish(target, payload)

    assert boundary.read_parent_owned_file(published) == payload


def test_read_parent_owned_bytes_returns_exact_capability_payload(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    payload = b"authenticated-parent-payload\x00\xff\n"
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.bin", "bytes-read")
    boundary.atomic_publish(target, payload)

    assert boundary.read_parent_owned_bytes(
        receipt, target.physical_path, "bytes-read"
    ) == payload


def test_read_presence_cli_has_typed_present_missing_and_reject_results(
    tmp_path: Path,
) -> None:
    attest(tmp_path)
    target = tmp_path / "reports" / "present.json"
    target.parent.mkdir()
    target.write_bytes(b"{}\n")
    cli = Path(side_effects.__file__).resolve()
    base = [sys.executable, str(cli), "read-presence", "--root", str(tmp_path)]
    env = _build_clean_env()

    present = subprocess.run(
        [*base, "--candidate", str(target), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (present.returncode, present.stdout, present.stderr) == (0, "present\n", "")

    missing = subprocess.run(
        [*base, "--candidate", str(tmp_path / "reports" / "missing.json"), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (missing.returncode, missing.stdout, missing.stderr) == (1, "missing\n", "")

    outside = tmp_path.parent / "presence-outside.json"
    outside.write_bytes(b"outside\n")
    escaping = tmp_path / "reports" / "escaping.json"
    escaping.symlink_to(outside)
    rejected = subprocess.run(
        [*base, "--candidate", str(escaping), "--purpose", "presence-test"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert rejected.returncode == 2
    assert rejected.stdout == ""
    assert "PARENT_ROOT_SIDE_EFFECT_ERROR=" in rejected.stderr


def test_read_parent_owned_file_rejects_in_root_inode_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "inode-race")
    published = boundary.atomic_publish(target, b"original\n")
    replacement = target.physical_path.with_name("replacement.txt")
    replacement.write_bytes(b"replacement\n")
    target.physical_path.unlink()
    replacement.rename(target.physical_path)

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.read_parent_owned_file(published)
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED


def test_read_parent_owned_file_rejects_intermediate_and_root_replacement(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/nested/result.txt", "component-race")
    published = boundary.atomic_publish(target, b"original\n")
    reports = tmp_path / "reports"
    moved_reports = tmp_path / "reports-moved"
    reports.rename(moved_reports)
    reports.mkdir()
    with pytest.raises(ParentRootSideEffectError) as intermediate_rejected:
        boundary.read_parent_owned_file(published)
    assert intermediate_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    shutil.rmtree(reports)
    moved_reports.rename(reports)

    replacement_root = tmp_path.with_name(f"{tmp_path.name}-root-replaced")
    tmp_path.rename(replacement_root)
    tmp_path.mkdir()
    try:
        with pytest.raises(ParentRootSideEffectError) as root_rejected:
            boundary.read_parent_owned_file(published)
        assert root_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    finally:
        shutil.rmtree(tmp_path)
        replacement_root.rename(tmp_path)


@pytest.mark.parametrize("replacement_kind", ["fifo", "directory"])
def test_read_parent_owned_file_rejects_nonregular_replacement_without_blocking(
    tmp_path: Path,
    replacement_kind: str,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "nonregular-race")
    published = boundary.atomic_publish(target, b"original\n")
    target.physical_path.unlink()
    if replacement_kind == "fifo":
        os.mkfifo(target.physical_path)
    else:
        target.physical_path.mkdir()

    started = time.monotonic()
    try:
        with pytest.raises(ParentRootSideEffectError) as rejected:
            boundary.read_parent_owned_file(published)
    finally:
        if target.physical_path.is_dir() and not target.physical_path.is_symlink():
            target.physical_path.rmdir()
        else:
            target.physical_path.unlink()
    assert time.monotonic() - started < 1.0
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED


def test_optional_missing_then_concurrent_create_preserves_winner_bytes(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "reports" / "winner.json"
    assert boundary.read_parent_owned_bytes(
        receipt, target, "concurrent-create", allow_missing=True
    ) is None
    target.parent.mkdir()
    target.write_bytes(b"winner\n")

    outcome, detail = boundary.publish_parent_owned_file_noreplace(
        receipt, target, b"loser\n", "concurrent-create"
    )
    assert (outcome, detail) == ("failed", "spool_conflict")
    assert boundary.read_parent_owned_bytes(receipt, target, "concurrent-create") == b"winner\n"


def test_child_environment_rejects_target_alias_mismatch_before_creating_directories(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.child_environment(
            receipt,
            {
                "CARGO_TARGET_DIR": str(tmp_path / "target-a"),
                "AGENT_CANON_CLI_TARGET_DIR": str(tmp_path / "target-b"),
            },
        )

    assert rejected.value.reject is ParentRootReject.ROOT_MISMATCH
    assert rejected.value.detail == "target_alias_mismatch"
    assert not (tmp_path / ".agent-canon" / "tmp").exists()
    assert not (tmp_path / ".agent-canon" / "cache").exists()


def test_child_environment_uses_attested_external_runtime_without_parent_writes(
    tmp_path: Path,
) -> None:
    """Runtime state uses its own capability and never becomes parent-owned."""
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    source_before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    runtime = tmp_path.parent / "external-runtime"
    runtime.mkdir()
    environment = root_capability_environment(
        source_root=tmp_path,
        runtime_root=runtime,
        base_env=_build_clean_env({"HOME": "/unchanged/home"}),
    )

    child = boundary.child_environment(receipt, environment, issue_handoff=False)

    assert Path(child["TMPDIR"]).is_relative_to(runtime.resolve())
    assert Path(child["CARGO_HOME"]).is_relative_to(runtime.resolve())
    assert Path(child["CARGO_TARGET_DIR"]).is_relative_to(runtime.resolve())
    assert child["AGENT_CANON_RUNTIME_ROOT"] == str(runtime.resolve())
    assert child["AGENT_CANON_RUNTIME_ROOT_DEV"]
    assert child["AGENT_CANON_RUNTIME_ROOT_INO"]
    source_after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert source_after == source_before


def test_child_environment_attests_and_initializes_explicit_runtime_root(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    runtime = tmp_path.parent / "unattested-runtime"
    runtime.mkdir()

    child = boundary.child_environment(
        receipt,
        _build_clean_env({"AGENT_CANON_RUNTIME_ROOT": str(runtime)}),
        issue_handoff=False,
    )
    assert child["AGENT_CANON_RUNTIME_ROOT_DEV"] == str(runtime.stat().st_dev)
    assert child["AGENT_CANON_RUNTIME_ROOT_INO"] == str(runtime.stat().st_ino)

    absent = tmp_path.parent / "missing-runtime"
    created = boundary.child_environment(
        receipt,
        _build_clean_env({"AGENT_CANON_RUNTIME_ROOT": str(absent)}),
        issue_handoff=False,
    )
    assert absent.is_dir()
    assert created["AGENT_CANON_RUNTIME_ROOT"] == str(absent.resolve())
    assert not (tmp_path / ".agent-canon").exists()


def test_child_environment_rejects_runtime_symlink_before_any_directory_creation(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    runtime = tmp_path.parent / "symlink-runtime"
    runtime.mkdir()
    outside = tmp_path.parent / "runtime-outside"
    outside.mkdir()
    redirected = runtime / "redirected"
    redirected.symlink_to(outside, target_is_directory=True)
    environment = root_capability_environment(
        source_root=tmp_path,
        runtime_root=runtime,
        base_env=_build_clean_env({"TMPDIR": str(redirected)}),
    )

    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.child_environment(receipt, environment)

    assert rejected.value.reject is ParentRootReject.RUNTIME_SYMLINK_ESCAPE
    assert not (outside / "cache").exists()
    assert not (tmp_path / ".agent-canon").exists()


def test_file_read_and_remove_reject_replaced_capability(tmp_path: Path) -> None:
    """A capability cannot be reused after its target inode is replaced."""
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = boundary.resolve_parent_owned_path(receipt, "reports/result.txt", "report")
    published = boundary.atomic_publish(target, b"original\n")
    replacement = tmp_path / "reports" / "replacement.txt"
    replacement.write_text("replacement\n", encoding="utf-8")
    (tmp_path / "reports" / "result.txt").unlink()
    (tmp_path / "reports" / "result.txt").symlink_to(replacement)
    with pytest.raises(ParentRootSideEffectError) as read_rejected:
        boundary.read_parent_owned_file(published)
    assert read_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    with pytest.raises(ParentRootSideEffectError) as remove_rejected:
        boundary.remove_parent_owned_file(published)
    assert remove_rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert replacement.exists()


def test_temp_directory_capability_is_exclusive_and_parent_bound(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    base = boundary.ensure_parent_owned_directory(receipt, ".agent-canon/tmp", "temp-base")
    temporary = boundary.create_parent_owned_temp_directory(
        receipt, base.physical_path, "temp-dir", "operation"
    )
    assert temporary.physical_path.is_dir()
    assert temporary.physical_path.parent == base.physical_path
    target = boundary.resolve_parent_owned_path(
        receipt, temporary.physical_path / "result.txt", "temp-result"
    )
    boundary.atomic_publish(target, b"owned\n")
    assert target.physical_path.read_text(encoding="utf-8") == "owned\n"
    boundary.remove_parent_owned_tree(receipt, temporary, "temp-dir-cleanup")
    assert not temporary.physical_path.exists()
    assert boundary.remove_empty_parent_owned_directory(receipt, base, "temp-base-cleanup")
    assert not base.physical_path.exists()


def test_temp_directory_replacement_is_typed_race(tmp_path: Path) -> None:
    """A replaced temporary-directory inode is rejected by its receipt."""
    boundary = ParentRootSideEffectBoundary()
    attestation = attest(tmp_path)
    temporary = boundary.create_parent_owned_temp_directory(
        attestation, tmp_path / "replacement", "replacement", "replacement"
    )
    original = temporary.physical_path
    moved = original.with_name(original.name + "-moved")
    os.rename(original, moved)
    os.mkdir(original)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.remove_parent_owned_tree(attestation, temporary, "replacement")
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED

    replacement_receipt = boundary.resolve_parent_owned_path(
        attestation, original, "replacement-cleanup", create=False
    )
    boundary.remove_parent_owned_tree(
        attestation, replacement_receipt, "replacement-cleanup"
    )
    moved_receipt = boundary.resolve_parent_owned_path(
        attestation, moved, "replacement-moved-cleanup", create=False
    )
    boundary.remove_parent_owned_tree(attestation, moved_receipt, "replacement-moved-cleanup")


def test_symlink_replacement_after_capability_is_typed_race(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "race" / "result.txt"
    capability = boundary.resolve_parent_owned_path(receipt, target, "race")
    outside = tmp_path.parent / "outside-race"
    outside.mkdir()
    (tmp_path / "race").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(capability, b"must-not-escape")
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE


def test_create_capability_uses_openat_and_rejects_final_symlink(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    created = boundary.resolve_parent_owned_path(receipt, "created/nested.txt", "create", create=True)
    assert created.physical_path.is_file()
    outside = tmp_path.parent / "create-outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    escaped = tmp_path / "escaped.txt"
    escaped.symlink_to(outside)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.resolve_parent_owned_path(receipt, escaped, "create", create=True)
    assert rejected.value.reject in {ParentRootReject.ROOT_RACE_DETECTED, ParentRootReject.SYMLINK_ESCAPE}


def test_open_parent_owned_file_a_plus_creates_and_locks(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    with boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=True, mode="a+"
    ) as handle:
        handle.write("created\n")
        handle.seek(0)
        assert handle.read() == "created\n"
    assert target.read_text(encoding="utf-8") == "created\n"


def test_open_parent_owned_file_r_plus_requires_existing_file_and_does_not_truncate(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    target.parent.mkdir()
    target.write_text("existing\n", encoding="utf-8")
    with boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=False, mode="r+"
    ) as handle:
        handle.seek(0)
        assert handle.read() == "existing\n"
    assert target.read_text(encoding="utf-8") == "existing\n"
    with pytest.raises(ParentRootSideEffectError) as missing:
        boundary.open_parent_owned_file(
            receipt,
            tmp_path / "monitor" / "missing.md",
            "workflow-monitoring",
            create=False,
            mode="r+",
        )
    assert missing.value.reject is ParentRootReject.ROOT_MISSING


def test_open_parent_owned_file_rejects_replaced_component(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    outside = tmp_path.parent / "outside-monitor"
    outside.mkdir()
    replaced = tmp_path / "monitor"
    replaced.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.open_parent_owned_file(
            receipt,
            replaced / "workflow_monitoring.md",
            "workflow-monitoring",
            create=True,
            mode="a+",
        )
    assert rejected.value.reject is ParentRootReject.SYMLINK_ESCAPE
    assert not (outside / "workflow_monitoring.md").exists()


def test_open_parent_owned_file_lock_blocks_until_release(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"
    first = boundary.open_parent_owned_file(
        receipt, target, "workflow-monitoring", create=True, mode="a+"
    )
    started = threading.Event()
    acquired = threading.Event()
    failures: list[BaseException] = []

    def acquire_second_handle() -> None:
        try:
            started.set()
            with boundary.open_parent_owned_file(
                receipt, target, "workflow-monitoring", create=False, mode="r+"
            ):
                acquired.set()
        except BaseException as exc:  # pragma: no cover - assertion below reports it
            failures.append(exc)

    worker = threading.Thread(target=acquire_second_handle)
    worker.start()
    assert started.wait(2)
    assert not acquired.wait(0.1)
    first.close()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not failures
    assert acquired.is_set()


def test_open_parent_owned_file_rolls_back_new_file_after_open_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    target = tmp_path / "monitor" / "workflow_monitoring.md"

    def fail_fdopen(*args: object, **kwargs: object) -> object:
        raise OSError("injected text-wrapper failure")

    monkeypatch.setattr(side_effects.os, "fdopen", fail_fdopen)
    with pytest.raises(ParentRootSideEffectError):
        boundary.open_parent_owned_file(
            receipt, target, "workflow-monitoring", create=True, mode="a+"
        )
    assert not target.exists()


def test_remove_parent_owned_tree_handles_deep_tree_without_recursion(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    temporary = boundary.create_parent_owned_temp_directory(
        receipt, tmp_path / "deep", "deep-tree", "deep-tree"
    )
    current = temporary.physical_path
    # Exercise iterative traversal without requiring more open descriptors
    # than a normal CI process is allowed to hold.
    for _ in range(128):
        current = current / "x"
        os.mkdir(current)
    boundary.remove_parent_owned_tree(receipt, temporary, "deep-tree-cleanup")
    assert not temporary.physical_path.exists()


def test_handoff_is_single_use_and_rejects_mutation_or_expiry(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    boundary = ParentRootSideEffectBoundary()
    token = boundary.issue_child_handoff(tmp_path, audience="test", ttl_seconds=30)
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=token
    )
    receipt = boundary.attest(request)
    assert receipt.handoff is not None
    with pytest.raises(ParentRootSideEffectError) as replay:
        boundary.attest(request)
    assert replay.value.reject is ParentRootReject.HANDOFF_INVALID
    expired = boundary.issue_child_handoff(tmp_path, audience="test", ttl_seconds=1)
    time.sleep(1.05)
    with pytest.raises(ParentRootSideEffectError) as stale:
        ParentRootSideEffectBoundary().attest(
            ParentRootAttestationRequest(
                cwd=tmp_path, explicit_root=tmp_path, purpose="test", child_handoff_token=expired
            )
        )
    assert stale.value.reject is ParentRootReject.HANDOFF_INVALID


def test_child_reattest_requires_handoff_even_when_root_env_is_present(tmp_path: Path) -> None:
    """Dropping the handoff token cannot be replaced by ambient root variables."""
    boundary = ParentRootSideEffectBoundary()
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    request = ParentRootAttestationRequest(
        cwd=tmp_path, explicit_root=tmp_path, purpose="test"
    )
    initial = boundary.attest(request)
    environment = boundary.child_environment(initial, {"HOME": "/unchanged/home"})
    child = boundary.reattest_child(request, environment)
    assert child.parent_root == tmp_path.resolve()
    environment.pop("AGENT_CANON_CHILD_HANDOFF")
    with pytest.raises(ParentRootSideEffectError) as dropped:
        boundary.reattest_child(request, environment)
    assert dropped.value.reject is ParentRootReject.HANDOFF_INVALID


def test_self_check_cli_reports_no_external_sentinel(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    sentinel = tmp_path.parent / ".pbr-sentinel-not-created"
    result = subprocess.run(
        [sys.executable, "tools/repository/workspace/parent_root_side_effects.py", "self-check",
         "--root", str(tmp_path), "--sentinel-outside", str(sentinel)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["home_unchanged"] is True
    assert payload["outside_sentinel_absent"] is True


def test_atomic_publish_handles_short_writes_and_rejects_zero_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    real_write = side_effects.os.write

    def short_write(fd: int, data: bytes) -> int:
        return real_write(fd, data[:2])

    monkeypatch.setattr(side_effects.os, "write", short_write)
    published = boundary.atomic_publish(
        boundary.resolve_parent_owned_path(receipt, "short/result.txt", "short"),
        b"short-write-payload",
    )
    assert boundary.read_parent_owned_file(published) == b"short-write-payload"

    def no_progress(_fd: int, _data: bytes) -> int:
        return 0

    monkeypatch.setattr(side_effects.os, "write", no_progress)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(
            boundary.resolve_parent_owned_path(receipt, "zero/result.txt", "zero"),
            b"must-fail",
        )
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert not list((tmp_path / "zero").glob("*.tmp"))


def test_receipt_rejects_replaced_intermediate_real_directory(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    nested = boundary.ensure_parent_owned_directory(receipt, "nested", "nested")
    capability = boundary.resolve_parent_owned_path(
        receipt, nested.physical_path / "result.txt", "nested-file"
    )
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    old = tmp_path / "nested-old"
    os.rename(tmp_path / "nested", old)
    os.rename(replacement, tmp_path / "nested")
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(capability, b"must-not-publish")
    assert rejected.value.reject is ParentRootReject.ROOT_RACE_DETECTED
    assert not (tmp_path / "nested" / "result.txt").exists()


def test_atomic_publish_surfaces_cleanup_failure_and_keeps_readback_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    real_unlink = side_effects.os.unlink

    def failing_temp_unlink(path: object, *args: object, **kwargs: object) -> None:
        if isinstance(path, str) and path.endswith(".tmp"):
            raise OSError(13, "injected cleanup failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(side_effects.os, "unlink", failing_temp_unlink)
    with pytest.raises(ParentRootSideEffectError) as rejected:
        boundary.atomic_publish(
            boundary.resolve_parent_owned_path(receipt, "cleanup/result.txt", "cleanup"),
            b"published-before-cleanup-error",
        )
    assert "cleanup failed" in str(rejected.value)
    assert (tmp_path / "cleanup" / "result.txt").read_bytes() == b"published-before-cleanup-error"


def test_capture_subprocess_publishes_and_replays_stdout(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    target = tmp_path / "reports" / "captured.txt"
    result = subprocess.run(
        [
            sys.executable,
            "tools/repository/workspace/parent_root_side_effects.py",
            "capture-subprocess",
            "--root",
            str(tmp_path),
            "--candidate",
            str(target),
            "--purpose",
            "capture-test",
            "--",
            sys.executable,
            "-c",
            "print('captured')",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_build_clean_env(),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "captured\n"
    assert target.read_text(encoding="utf-8") == "captured\n"
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_preserves_home_and_bindings(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    preserved_home = tmp_path / "outside-home"
    preserved_home.mkdir()
    env = _build_clean_env(
        {
            "HOME": str(preserved_home),
            "PYTHONPATH": os.getcwd(),
        }
    )
    code = (
        "import json, os; "
        "print(json.dumps({"
        "\"home\": os.environ.get(\"HOME\"), "
        "\"tmpdir\": os.environ.get(\"TMPDIR\"), "
        "\"temp\": os.environ.get(\"TEMP\"), "
        "\"tmp\": os.environ.get(\"TMP\"), "
        "\"cache\": os.environ.get(\"XDG_CACHE_HOME\"), "
        "\"tools\": os.environ.get(\"AGENT_CANON_TOOLS_HOME\"), "
        "\"cargo_target\": os.environ.get(\"CARGO_TARGET_DIR\"), "
        "\"cli_target\": os.environ.get(\"AGENT_CANON_CLI_TARGET_DIR\"), "
        "\"handoff\": os.environ.get(\"AGENT_CANON_CHILD_HANDOFF\"), "
        "\"purpose\": os.environ.get(\"AGENT_CANON_CHILD_PURPOSE\")"
        "}))"
    )
    result = subprocess.run(
        [
            sys.executable,
            "tools/repository/workspace/parent_root_side_effects.py",
            "exec-parent-bound",
            "--root",
            str(tmp_path),
            "--purpose",
            "exec-test",
            "--",
            sys.executable,
            "-c",
            code,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **env,
            "AGENT_CANON_CHILD_HANDOFF": "untrusted-inherited-token",
            "AGENT_CANON_HANDOFF_AUDIENCE": "untrusted-audience",
            "AGENT_CANON_CHILD_PURPOSE": "untrusted-purpose",
        },
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip())
    assert data["home"] == str(preserved_home)
    expected_tmp = str((tmp_path / ".agent-canon" / "tmp").resolve())
    assert data["tmpdir"] == expected_tmp
    assert data["temp"] == expected_tmp
    assert data["tmp"] == expected_tmp
    assert Path(data["cache"]).resolve().is_relative_to(tmp_path.resolve())
    assert Path(data["tools"]).resolve().is_relative_to(tmp_path.resolve())
    assert data["cargo_target"] == data["cli_target"]
    assert data["handoff"] is None
    assert data["purpose"] is None
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_failure_does_not_leave_pending_handoff(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    result = subprocess.run(
        [
            sys.executable,
            "tools/repository/workspace/parent_root_side_effects.py",
            "exec-parent-bound",
            "--root",
            str(tmp_path),
            "--purpose",
            "exec-failure-test",
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(17)",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_build_clean_env(),
    )
    assert result.returncode == 17
    assert pending_handoff_nonces(tmp_path) == {}


def test_exec_parent_bound_rejects_external_target_before_side_effects(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    external = tmp_path.parent / "external-target"
    result = subprocess.run(
        [
            sys.executable,
            "tools/repository/workspace/parent_root_side_effects.py",
            "exec-parent-bound",
            "--root",
            str(tmp_path),
            "--purpose",
            "exec-test",
            "--",
            "echo",
            "should-not-run",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_build_clean_env({"AGENT_CANON_CLI_TARGET_DIR": str(external)}),
    )
    assert result.returncode == 2
    assert external.exists() is False
    assert not (tmp_path / ".agent-canon" / "tmp").exists()


def test_child_environment_rejection_preserves_preexisting_entries(tmp_path: Path) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    preexisting_tmp = tmp_path / ".agent-canon" / "tmp"
    preexisting_cache = tmp_path / ".agent-canon" / "cache"
    preexisting_tmp.mkdir(parents=True)
    preexisting_cache.mkdir(parents=True)
    pre_token = json.dumps({"marker": "preexisting"})
    token_file = preexisting_tmp / "preexisting.txt"
    token_file.write_text(pre_token, encoding="utf-8")

    with pytest.raises(ParentRootSideEffectError):
        boundary.child_environment(receipt, {"AGENT_CANON_CLI_TARGET_DIR": str(tmp_path.parent / "external-target")})

    assert token_file.read_text(encoding="utf-8") == pre_token


def test_copy_mode_external_read_and_symlink_replacement_are_boundary_owned(
    tmp_path: Path,
) -> None:
    boundary = ParentRootSideEffectBoundary()
    receipt = attest(tmp_path)
    source = tmp_path / "build" / "agent-canon"
    source.parent.mkdir()
    source.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    source.chmod(0o755)
    installed = tmp_path / ".agent-canon" / "tools" / "agent-canon" / "bin" / "agent-canon"

    published = boundary.copy_parent_owned_file(
        receipt,
        source,
        installed,
        "executable-copy-test",
        preserve_mode=True,
    )
    assert published.physical_path == installed
    assert installed.stat().st_mode & 0o777 == 0o755

    link = tmp_path / ".agent-canon" / "tools" / "bin" / "agent-canon"
    link.parent.mkdir(parents=True)
    link.symlink_to("obsolete")
    assert boundary.replace_parent_owned_symlink(
        receipt, str(installed), link, "symlink-replacement-test"
    ) == link
    assert link.is_symlink()
    assert os.readlink(link) == str(installed)

    external = tmp_path.parent / "read-only-input.txt"
    external.write_text("external input\n", encoding="utf-8")
    snapshot = tmp_path / ".agent-canon" / "tmp" / "snapshot.txt"
    boundary.copy_read_only_file(
        receipt, external, snapshot, "read-only-copy-test"
    )
    assert snapshot.read_text(encoding="utf-8") == "external input\n"
    assert external.read_text(encoding="utf-8") == "external input\n"


def test_verify_child_rejects_forged_purpose_without_handoff(tmp_path: Path) -> None:
    git_repo(tmp_path, remote="https://example.invalid/parent.git")
    result = subprocess.run(
        [
            sys.executable,
            "tools/repository/workspace/parent_root_side_effects.py",
            "verify-child",
            "--root",
            str(tmp_path),
            "--purpose",
            "forged-child",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_build_clean_env({"AGENT_CANON_CHILD_PURPOSE": "forged-child"}),
    )
    assert result.returncode == 2
    assert "handoff_invalid" in result.stderr
