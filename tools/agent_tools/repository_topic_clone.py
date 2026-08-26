#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Implements repository-topic clone lifecycle with strict cleanup and evidence checks.
# upstream design ../../documents/rule/repository-topic-clone.md defines generic clone and cleanup behavior
# upstream implementation ./conflict_preservation.py captures conflict stages and validates finalization readback.
# downstream implementation ../../tests/agent_tools/test_repository_topic_clone.py validates repository-topic clone lifecycle.
# @dependency-end
"""Manage repository-topic clones with explicit receipts and strict cleanup gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

try:
    from .conflict_preservation import capture_inventory, validate_plan
except ImportError:  # direct CLI execution
    from conflict_preservation import capture_inventory, validate_plan

if TYPE_CHECKING:
    from . import parent_root_side_effects as _parent_boundary
elif __package__:
    from . import parent_root_side_effects as _parent_boundary
else:  # direct CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import parent_root_side_effects as _parent_boundary


def _attest_parent(
    request: _parent_boundary.ParentRootAttestationRequest,
) -> _parent_boundary.ParentRootAttestationReceipt:
    return _parent_boundary.attest_parent_root(request)


def _resolve_parent_path(
    attestation: _parent_boundary.ParentRootAttestationReceipt,
    candidate: Path | str,
    purpose: str,
) -> Path:
    return _parent_boundary.resolve_parent_owned_path(
        attestation, candidate, purpose, create=False
    ).physical_path


def _parent_request(
    root: Path,
    *,
    clone_root: Path | None = None,
    purpose: str,
) -> _parent_boundary.ParentRootAttestationRequest:
    return _parent_boundary.ParentRootAttestationRequest(
        cwd=root, explicit_root=root, clone_root=clone_root, purpose=purpose
    )


def _parent_error(exc: Exception) -> str:
    reject = getattr(getattr(exc, "reject", None), "value", "boundary")
    detail = getattr(exc, "detail", str(exc))
    return f"parent-root-attestation:{reject}:{detail}"


MARKER_PREFIX = "repository-topic-clone"
LEGACY_MARKER_PREFIX = "agent-canon.topic"
CANONICAL_MARKER_FIELDS = (
    "repository",
    "topic",
    "branch",
    "url",
    "owner-evidence-sha256",
)
LEGACY_MARKER_FIELDS = (
    "topic",
    "role",
    "module",
    "url",
    "branch",
    "placement",
    "owner-evidence-sha256",
)
TOPIC_RE = re.compile(r"[^A-Za-z0-9]+")


class RepositoryTopicCloneError(RuntimeError):
    """Raised when repository-topic clone lifecycle requirements cannot be satisfied."""


class GitCommandError(RepositoryTopicCloneError):
    """Raised when a required git command fails."""

    def __init__(self, repo: Path, args: Sequence[str], stderr: str) -> None:
        """Build command-specific error string."""
        super().__init__(
            f"git -C {repo} {' '.join(args)}: {stderr.strip() or 'command failed'}"
        )


def _run_git(repo: Path, args: Sequence[str], *, pass_fds: tuple[int, ...] = ()) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True,
        pass_fds=pass_fds,
    )
    if result.returncode != 0:
        raise GitCommandError(repo, args, result.stderr)
    return result.stdout


def _run_git_bool(repo: Path, args: Sequence[str]) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
        ).returncode
        == 0
    )


@dataclass(frozen=True)
class RepositoryTopicCloneRequest:
    """Normalized request for one repository-topic lifecycle operation."""

    url: str
    repository: str
    workspace_root: Path
    topic: str
    branch: str
    owner_evidence: Path
    parent_attestation: _parent_boundary.ParentRootAttestationReceipt | None = None


@dataclass(frozen=True)
class PrepareReceipt:
    """Receipt returned by a successful prepare."""

    request: RepositoryTopicCloneRequest
    clone: Path
    branch: str
    candidate_sha: str
    candidate_tree: str
    clone_dev: int | None = None
    clone_ino: int | None = None


@dataclass(frozen=True)
class MergeMainReceipt:
    """Receipt returned by merge_main."""

    request: RepositoryTopicCloneRequest
    clone: Path
    candidate_sha: str
    candidate_tree: str
    merged_sha: str
    merged_tree: str
    origin_main_sha: str


@dataclass(frozen=True)
class CleanupProof:
    """Proof that cleanup preflight passed and deletion action was executed."""

    request: RepositoryTopicCloneRequest
    clone: Path
    removed: bool
    evidence: str


@runtime_checkable
class RepositoryPolicyCallback(Protocol):
    """Optional post-operation callback hook."""

    def apply(
        self, *, operation: str, request: RepositoryTopicCloneRequest, receipt: object
    ) -> None:
        """Apply a callback after prepare/merge."""


@dataclass(frozen=True)
class CloneState:
    """Observed lifecycle state for one clone."""

    path: Path
    state: str


def _load_publication_contract():
    """Import the canonical publication transition validators lazily."""
    root = Path(__file__).parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    module = __import__(
        "update_lifecycle_contract",
        fromlist=[
            "validate_candidate_cas_pr_transition",
            "validate_publication_readback_transition",
        ],
    )
    return module


def topic_slug(value: str) -> str:
    """Return the canonical workspace slug for one topic."""
    value = value.strip()
    if not value:
        raise RepositoryTopicCloneError("topic must be non-empty")
    result = TOPIC_RE.sub("-", value).strip("-").lower()
    if not result:
        raise RepositoryTopicCloneError(f"topic has no usable slug: {value!r}")
    return result


def _normalise_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    return normalized[:-4] if normalized.endswith(".git") else normalized


def _repository_name(value: str) -> str:
    """Require one safe repository directory component."""
    if (
        not value
        or value in {".", ".."}
        or value != Path(value).name
        or any(character in value for character in "/\\\r\n\x00")
    ):
        raise RepositoryTopicCloneError(
            f"repository must be one safe path component: {value!r}"
        )
    return value


def _normalise_branch(value: str) -> str:
    if value != value.strip() or any(character in value for character in "\r\n\x00"):
        raise RepositoryTopicCloneError(
            f"branch must be an exact named branch: {value!r}"
        )
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", value],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RepositoryTopicCloneError(
            f"branch is not a valid named branch: {value!r}"
        )
    return value


def _require_evidence(evidence: Path | str, root: Path) -> Path:
    path = Path(evidence)
    if not path.is_absolute():
        path = root / path
    if not path.is_file() or path.stat().st_size == 0:
        raise RepositoryTopicCloneError(
            f"owner evidence must be a non-empty file: {path}"
        )
    return path


def _evidence_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_workspace_ignored(root: Path) -> None:
    """Require the repository-owned root ``.gitignore`` to own ``workspace/``."""
    ignore_file = root / ".gitignore"
    if ignore_file.is_symlink() or not ignore_file.is_file():
        raise RepositoryTopicCloneError(
            f"workspace root requires a regular .gitignore: {ignore_file}"
        )
    try:
        _run_git(root, ["ls-files", "--error-unmatch", "--", ".gitignore"])
    except GitCommandError as exc:
        raise RepositoryTopicCloneError(
            f"workspace root requires a tracked .gitignore: {ignore_file}"
        ) from exc

    probe = "workspace/.agent-canon-workspace-probe"
    try:
        output = _run_git(root, ["check-ignore", "-v", "--no-index", "--", probe])
    except GitCommandError as exc:
        raise RepositoryTopicCloneError(
            f"workspace root .gitignore must ignore {probe}"
        ) from exc
    line = output.strip().splitlines()
    if len(line) != 1:
        raise RepositoryTopicCloneError(
            f"workspace root .gitignore probe is ambiguous: {probe}"
        )
    source_and_pattern, separator, ignored_path = line[0].partition("\t")
    if not separator:
        raise RepositoryTopicCloneError(
            f"workspace root .gitignore probe is malformed: {line[0]}"
        )
    source_text = source_and_pattern.rsplit(":", 2)[0]
    source = Path(source_text)
    if not source.is_absolute():
        source = root / source
    try:
        source = source.resolve(strict=True)
        expected = ignore_file.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RepositoryTopicCloneError(
            f"workspace root .gitignore probe source is unavailable: {ignore_file}"
        ) from exc
    if source != expected or ignored_path.strip() != probe:
        raise RepositoryTopicCloneError(
            f"workspace root .gitignore must own the ignore for {probe}"
        )


def _repository_workspace_root(
    workspace_root: Path | str, *, require_ignore: bool
) -> Path:
    """Validate the selected repository root before lifecycle path handling."""
    root = Path(workspace_root).absolute()
    try:
        attestation = _attest_parent(
            _parent_request(root, purpose="repository-topic-clone")
        )
        root = Path(getattr(attestation, "parent_root"))
    except Exception as exc:
        raise RepositoryTopicCloneError(_parent_error(exc)) from exc
    _reject_symlink_components(root, "workspace root")
    _reject_symlink_components(root / "workspace", "workspace directory")
    if not root.is_dir():
        raise RepositoryTopicCloneError(
            f"workspace root must be a directory: {root}"
        )
    try:
        git_root = _run_git(root, ["rev-parse", "--show-toplevel"]).strip()
    except GitCommandError as exc:
        raise RepositoryTopicCloneError(
            f"workspace root must be a Git repository root: {root}"
        ) from exc
    try:
        resolved_git_root = Path(git_root).resolve(strict=True)
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RepositoryTopicCloneError(
            f"workspace root Git toplevel is unavailable: {root}"
        ) from exc
    if resolved_git_root != resolved_root:
        raise RepositoryTopicCloneError(
            f"workspace root must equal the Git toplevel: {root}"
        )
    if require_ignore:
        _require_workspace_ignored(root)
    return root


def _topic_root(workspace_root: Path, topic: str, *, create: bool) -> Path:
    workspace_dir = workspace_root / "workspace"
    root = workspace_dir / topic_slug(topic)
    if root.exists():
        if root.is_symlink():
            raise RepositoryTopicCloneError(
                f"topic workspace must not be a symlink: {root}"
            )
        if not root.is_dir():
            raise RepositoryTopicCloneError(
                f"topic workspace path is not a directory: {root}"
            )
    elif create:
        raise RepositoryTopicCloneError(
            f"topic workspace creation requires parent boundary capability: {root}"
        )
    else:
        raise RepositoryTopicCloneError(f"topic workspace is absent: {root}")
    return root


def _reject_symlink_components(path: Path, label: str) -> None:
    """Reject every existing symlink component in a lifecycle path."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            raise RepositoryTopicCloneError(
                f"{label} contains symlinked path component: {current}"
            )


def _safe_under(root: Path, candidate: Path, label: str) -> Path:
    root_absolute = root.absolute()
    candidate_absolute = candidate.absolute()
    _reject_symlink_components(root_absolute, "containment root")
    _reject_symlink_components(candidate_absolute, label)
    if (
        candidate_absolute != root_absolute
        and root_absolute not in candidate_absolute.parents
    ):
        raise RepositoryTopicCloneError(
            f"{label} is outside containment root {root_absolute}: {candidate_absolute}"
        )
    resolved_root = root_absolute.resolve(strict=False)
    resolved_candidate = candidate_absolute.resolve(strict=False)
    if (
        resolved_candidate != resolved_root
        and resolved_root not in resolved_candidate.parents
    ):
        raise RepositoryTopicCloneError(
            f"{label} escapes containment root {resolved_root}: {resolved_candidate}"
        )
    return candidate_absolute


def computed_clone_path(
    request: RepositoryTopicCloneRequest, *, create_topic: bool = False
) -> Path:
    """Return the sole lifecycle-owned clone path for a request."""
    _repository_name(request.repository)
    try:
        attestation = request.parent_attestation
        if attestation is None:
            attestation = _attest_parent(
                _parent_request(
                    request.workspace_root,
                    purpose="repository-topic-clone",
                )
            )
        if create_topic:
            _parent_boundary.ensure_parent_owned_directory(
                attestation,
                request.workspace_root / "workspace" / topic_slug(request.topic),
                "repository-topic-workspace",
            )
        workspace = _topic_root(request.workspace_root, request.topic, create=False)
        candidate = _safe_under(workspace, workspace / request.repository, "topic clone path")
        return _resolve_parent_path(attestation, candidate, "repository-topic-clone")
    except Exception as exc:
        raise RepositoryTopicCloneError(_parent_error(exc)) from exc


def projected_clone_path(
    workspace_root: Path | str, topic: str, repository: str
) -> Path:
    """Compute a clone path without creating or requiring its topic directory."""
    root = Path(workspace_root)
    _reject_symlink_components(root.absolute(), "workspace root")
    workspace = root / "workspace"
    if workspace.is_symlink():
        raise RepositoryTopicCloneError(
            f"workspace directory must not be a symlink: {workspace}"
        )
    _reject_symlink_components(workspace.absolute(), "workspace directory")
    topic_root = workspace / topic_slug(topic)
    candidate = _safe_under(
        topic_root,
        topic_root / _repository_name(repository),
        "topic clone path",
    )
    try:
        attestation = _attest_parent(
            _parent_request(root.absolute(), purpose="repository-topic-clone")
        )
        return _resolve_parent_path(attestation, candidate, "repository-topic-clone")
    except Exception as exc:
        raise RepositoryTopicCloneError(_parent_error(exc)) from exc


def _remote_url(path: Path) -> str:
    return _run_git(path, ["config", "--get", "remote.origin.url"]).strip()


def _marker(path: Path, field: str, *, prefix: str = MARKER_PREFIX) -> str:
    try:
        return _run_git(path, ["config", "--local", "--get", f"{prefix}.{field}"]).strip()
    except GitCommandError:
        return ""


def _marker_values(path: Path, prefix: str, fields: Sequence[str]) -> dict[str, str]:
    """Read a marker namespace without mutating local Git configuration."""
    return {field: _marker(path, field, prefix=prefix) for field in fields}


def _marker_namespace_present(path: Path, prefix: str) -> bool:
    """Return whether any local config key exists in a marker namespace."""
    try:
        output = _run_git(
            path,
            [
                "config",
                "--local",
                "--name-only",
                "--get-regexp",
                rf"^{re.escape(prefix)}\.",
            ],
        )
    except GitCommandError:
        return False
    return any(line.strip() for line in output.splitlines())


def _legacy_marker_matches(
    values: Mapping[str, str], request: RepositoryTopicCloneRequest, owner_sha: str
) -> bool:
    """Return whether the historical AgentCanon module marker is exact."""
    module = values["module"]
    return (
        values["topic"] == topic_slug(request.topic)
        and values["role"] == "module"
        and bool(module)
        and Path(module).name == request.repository
        and values["url"] == _normalise_url(request.url)
        and values["branch"] == request.branch
        and values["placement"] == "workspace-continuation"
        and values["owner-evidence-sha256"] == owner_sha
    )


def _set_marker(
    path: Path,
    request: RepositoryTopicCloneRequest,
    owner_sha: str,
    branch: str,
) -> None:
    for field, value in {
        "repository": request.repository,
        "topic": topic_slug(request.topic),
        "branch": branch,
        "url": _normalise_url(request.url),
        "owner-evidence-sha256": owner_sha,
    }.items():
        _run_git(path, ["config", "--local", f"{MARKER_PREFIX}.{field}", value])


def _write_conflict_inventory(
    clone: Path,
    *,
    base: str,
    ours: str,
    theirs: str,
) -> Path:
    """Persist the captured stages in the conflicted topic clone's ignored state."""
    inventory = capture_inventory(
        clone,
        base=base,
        ours=ours,
        theirs=theirs,
        repository=str(clone),
    )
    artifact = clone / ".agent-canon" / "conflict-preservation.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    exclude = Path(_run_git(clone, ["rev-parse", "--git-path", "info/exclude"]).strip())
    if not exclude.is_absolute():
        exclude = clone / exclude
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    markers = (
        ".agent-canon/conflict-preservation.json",
        ".agent-canon/conflict-preservation-plan.json",
    )
    missing = [marker for marker in markers if marker not in existing.splitlines()]
    if missing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as stream:
            if existing and not existing.endswith("\n"):
                stream.write("\n")
            stream.writelines(f"{marker}\n" for marker in missing)
    return artifact


def _inspect(
    path: Path, request: RepositoryTopicCloneRequest, *, owner_sha: str
) -> CloneState:
    if not path.exists():
        return CloneState(path, "absent")
    if not path.is_dir() or not _run_git_bool(
        path, ["rev-parse", "--is-inside-work-tree"]
    ):
        return CloneState(path, "not-git")
    if (path / ".git" / "MERGE_HEAD").exists() or (
        path / ".git" / "MERGE_MSG"
    ).exists():
        return CloneState(path, "merge-conflict-preserve")
    if _run_git(path, ["status", "--porcelain=v1", "--untracked-files=all"]).strip():
        return CloneState(path, "dirty-worktree-index-or-untracked")
    try:
        remote = _normalise_url(_remote_url(path))
    except GitCommandError:
        return CloneState(path, "missing-remote")
    requested_url = _normalise_url(request.url)
    canonical = _marker_values(path, MARKER_PREFIX, CANONICAL_MARKER_FIELDS)
    canonical_present = any(canonical.values()) or _marker_namespace_present(
        path, MARKER_PREFIX
    )
    marker_branch = ""
    if canonical_present:
        if not all(canonical.values()):
            return CloneState(path, "marker-incomplete")
        if remote != requested_url or canonical["url"] != requested_url:
            return CloneState(path, "url-mismatch")
        if canonical["repository"] != request.repository:
            return CloneState(path, "repository-mismatch")
        if canonical["topic"] != topic_slug(request.topic):
            return CloneState(path, "topic-mismatch")
        if canonical["owner-evidence-sha256"] != owner_sha:
            return CloneState(path, "owner-evidence-mismatch")
        marker_branch = canonical["branch"]
    else:
        legacy = _marker_values(path, LEGACY_MARKER_PREFIX, LEGACY_MARKER_FIELDS)
        if any(legacy.values()):
            if not all(legacy.values()):
                return CloneState(path, "legacy-marker-incomplete")
            remote_mismatch = remote != requested_url
            if remote_mismatch or not _legacy_marker_matches(
                legacy, request, owner_sha
            ):
                return CloneState(
                    path,
                    "url-mismatch" if remote_mismatch else "legacy-marker-mismatch",
                )
            marker_branch = legacy["branch"]
        else:
            return CloneState(path, "repository-mismatch")
    try:
        actual_branch = _run_git(
            path, ["symbolic-ref", "--quiet", "--short", "HEAD"]
        ).strip()
    except GitCommandError:
        return CloneState(path, "detached")
    if marker_branch != actual_branch:
        return CloneState(path, "actual-branch-mismatch")
    if actual_branch != request.branch:
        return CloneState(path, "branch-mismatch")
    return CloneState(path, "ready")


def _remote_branch_exists(remote: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 2):
        raise RepositoryTopicCloneError(
            f"cannot inspect remote branch {branch!r} on {_normalise_url(remote)}: "
            f"{result.stderr.strip() or 'git ls-remote failed'}"
        )
    return result.returncode == 0


def _has_local_branch(path: Path, branch: str) -> bool:
    return _run_git_bool(
        path, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]
    )


def _upstream(path: Path, branch: str) -> str:
    """Return the configured upstream ref, or an empty string."""
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _ensure_branch(path: Path, remote: str, branch: str) -> str:
    """Select the exact branch and return its verified source identity."""
    if _has_local_branch(path, branch):
        _run_git(path, ["checkout", branch])
        upstream = _upstream(path, branch)
        if upstream and upstream != f"origin/{branch}":
            raise RepositoryTopicCloneError(
                f"prepare collision: branch-upstream-mismatch ({upstream})"
            )
        return (
            f"origin/{branch}"
            if upstream == f"origin/{branch}"
            else f"local:{_run_git(path, ['rev-parse', branch]).strip()}"
        )

    remote_exists = _remote_branch_exists(remote, branch)
    if remote_exists:
        _run_git(path, ["fetch", "origin", branch])
        _run_git(path, ["checkout", "--track", "-b", branch, f"origin/{branch}"])
        return f"origin/{branch}"
    _run_git(path, ["fetch", "origin", "main"])
    base_sha = _run_git(path, ["rev-parse", "origin/main"]).strip()
    _run_git(path, ["checkout", "-b", branch, base_sha])
    return f"origin/main@{base_sha}"


def request(
    url: str,
    repository: str,
    workspace_root: Path | str,
    topic: str,
    branch: str,
    owner_evidence: Path | str,
    *,
    policy: RepositoryPolicyCallback | None = None,
) -> PrepareReceipt:
    """Prepare a topic clone and return a typed receipt."""
    repository_root = _repository_workspace_root(workspace_root, require_ignore=True)
    request_state = RepositoryTopicCloneRequest(
        url=str(url),
        repository=_repository_name(repository),
        workspace_root=repository_root,
        topic=topic,
        branch=_normalise_branch(branch),
        owner_evidence=_require_evidence(owner_evidence, repository_root),
    )
    try:
        request_state = RepositoryTopicCloneRequest(
            url=request_state.url,
            repository=request_state.repository,
            workspace_root=request_state.workspace_root,
            topic=request_state.topic,
            branch=request_state.branch,
            owner_evidence=request_state.owner_evidence,
            parent_attestation=_attest_parent(
                _parent_request(repository_root, purpose="repository-topic-clone")
            ),
        )
    except Exception as exc:
        raise RepositoryTopicCloneError(_parent_error(exc)) from exc
    owner_sha = _evidence_sha256(request_state.owner_evidence)
    clone = computed_clone_path(request_state, create_topic=True)
    if request_state.parent_attestation is None:
        raise RepositoryTopicCloneError("parent-root-attestation:boundary:attestation missing")
    state = _inspect(clone, request_state, owner_sha=owner_sha)
    if state.state in {
        "absent",
        "ready",
        "actual-branch-mismatch",
        "branch-mismatch",
    }:
        if state.state != "absent":
            branch_source = _ensure_branch(
                clone, request_state.url, request_state.branch
            )
        else:
            boundary = _parent_boundary.ParentRootSideEffectBoundary()
            target = boundary.open_parent_owned_target(
                request_state.parent_attestation,
                clone,
                "repository-topic-clone-create",
            )
            try:
                _run_git(
                    request_state.workspace_root,
                    ["clone", request_state.url, target.proc_path],
                    pass_fds=(target.target_fd,),
                )
                observed = os.fstat(target.target_fd)
                if (observed.st_dev, observed.st_ino) != (target.target_dev, target.target_ino):
                    raise RepositoryTopicCloneError(
                        "parent-root-attestation:root_race_detected:clone target identity changed"
                    )
            except Exception as exc:
                try:
                    boundary._abort_reserved_target(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                        request_state.parent_attestation,
                        target,
                        "repository-topic-clone-create-failure",
                    )
                except Exception as abort_exc:
                    raise RepositoryTopicCloneError(_parent_error(abort_exc)) from exc
                raise
            else:
                target.close()
            branch_source = _ensure_branch(
                clone, request_state.url, request_state.branch
            )
    elif state.state in {
        "dirty-worktree-index-or-untracked",
        "merge-conflict-preserve",
        "detached",
        "not-git",
        "missing-remote",
        "url-mismatch",
        "repository-mismatch",
        "topic-mismatch",
        "owner-evidence-mismatch",
    }:
        raise RepositoryTopicCloneError(f"prepare collision: {state.state}")
    else:
        raise RepositoryTopicCloneError(f"prepare rejected: {state.state}")

    branch_name = _run_git(
        clone, ["symbolic-ref", "--quiet", "--short", "HEAD"]
    ).strip()
    _set_marker(clone, request_state, owner_sha=owner_sha, branch=branch_name)
    _run_git(
        clone, ["config", "--local", f"{MARKER_PREFIX}.branch-source", branch_source]
    )
    final_state = _inspect(clone, request_state, owner_sha=owner_sha)
    if final_state.state != "ready":
        raise RepositoryTopicCloneError(
            f"prepared clone not ready: {final_state.state}"
        )
    candidate_sha = _run_git(clone, ["rev-parse", branch_name]).strip()
    candidate_tree = _run_git(clone, ["rev-parse", f"{candidate_sha}^{{tree}}"]).strip()
    clone_identity = clone.stat()
    receipt = PrepareReceipt(
        request=request_state,
        clone=clone,
        branch=branch_name,
        candidate_sha=candidate_sha,
        candidate_tree=candidate_tree,
        clone_dev=clone_identity.st_dev,
        clone_ino=clone_identity.st_ino,
    )
    if policy is not None:
        policy.apply(operation="prepare", request=request_state, receipt=receipt)
    return receipt


def merge_main(
    request_state: RepositoryTopicCloneRequest,
    *,
    policy: RepositoryPolicyCallback | None = None,
) -> MergeMainReceipt:
    """Fetch and merge origin/main with --no-edit and strict ancestor proof."""
    prepared = request(
        request_state.url,
        request_state.repository,
        request_state.workspace_root,
        request_state.topic,
        request_state.branch,
        request_state.owner_evidence,
        policy=None,
    )
    clone = prepared.clone
    _run_git(clone, ["fetch", "origin", "main"])
    candidate_sha = _run_git(clone, ["rev-parse", "HEAD"]).strip()
    candidate_tree = _run_git(clone, ["rev-parse", f"{candidate_sha}^{{tree}}"]).strip()
    origin_main_sha = _run_git(clone, ["rev-parse", "origin/main"]).strip()
    merge_base = _run_git(clone, ["merge-base", candidate_sha, origin_main_sha]).strip()
    try:
        _run_git(clone, ["merge", "--no-edit", "origin/main"])
    except GitCommandError as exc:
        if (clone / ".git" / "MERGE_HEAD").exists():
            try:
                inventory = _write_conflict_inventory(
                    clone,
                    base=merge_base,
                    ours=candidate_sha,
                    theirs=origin_main_sha,
                )
                inventory_note = f" inventory={inventory}"
            except Exception as inventory_exc:
                inventory_note = f" inventory_capture_failed={inventory_exc}"
            raise RepositoryTopicCloneError(
                "merge-conflict-preserve: normal origin/main merge requires intentional resolution;"
                + inventory_note
            ) from exc
        raise
    merged_sha = _run_git(clone, ["rev-parse", "HEAD"]).strip()
    merged_tree = _run_git(clone, ["rev-parse", f"{merged_sha}^{{tree}}"]).strip()
    _run_git(clone, ["merge-base", "--is-ancestor", candidate_sha, merged_sha])
    _run_git(clone, ["merge-base", "--is-ancestor", origin_main_sha, merged_sha])
    receipt = MergeMainReceipt(
        request=request_state,
        clone=clone,
        candidate_sha=candidate_sha,
        candidate_tree=candidate_tree,
        merged_sha=merged_sha,
        merged_tree=merged_tree,
        origin_main_sha=origin_main_sha,
    )
    if policy is not None:
        policy.apply(operation="merge_main", request=request_state, receipt=receipt)
    return receipt


def finalize_merge_main(
    request_state: RepositoryTopicCloneRequest,
    *,
    inventory_path: Path | str | None = None,
    plan_path: Path | str | None = None,
    policy: RepositoryPolicyCallback | None = None,
) -> MergeMainReceipt:
    """Commit a conflict only after its preservation plan and readback pass."""
    _repository_workspace_root(request_state.workspace_root, require_ignore=False)
    clone = computed_clone_path(request_state, create_topic=False)
    if not clone.is_dir() or not (clone / ".git").exists():
        raise RepositoryTopicCloneError("merge-finalize hold: clone is unavailable")
    if _normalise_url(_remote_url(clone)) != _normalise_url(request_state.url):
        raise RepositoryTopicCloneError("merge-finalize hold: remote identity mismatch")
    branch = _run_git(clone, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
    if branch != request_state.branch:
        raise RepositoryTopicCloneError(
            f"merge-finalize hold: branch mismatch ({branch})"
        )
    merge_result = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "MERGE_HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    merge_head = merge_result.stdout.strip()
    if not merge_head:
        raise RepositoryTopicCloneError("merge-finalize hold: merge is not in progress")
    inventory_file = Path(inventory_path) if inventory_path is not None else clone / ".agent-canon" / "conflict-preservation.json"
    plan_file = Path(plan_path) if plan_path is not None else clone / ".agent-canon" / "conflict-preservation-plan.json"
    inventory = _read_json_artifact(inventory_file, "conflict preservation inventory")
    plan = _read_json_artifact(plan_file, "conflict preservation plan")
    if not isinstance(inventory, Mapping) or not isinstance(plan, Mapping):
        raise RepositoryTopicCloneError("merge-finalize hold: preservation packets must be objects")
    ours_record = inventory.get("ours")
    theirs_record = inventory.get("theirs")
    if not isinstance(ours_record, Mapping) or not isinstance(theirs_record, Mapping):
        raise RepositoryTopicCloneError("merge-finalize hold: inventory stage identities are missing")
    candidate_sha = _run_git(clone, ["rev-parse", "HEAD"]).strip()
    if candidate_sha != ours_record.get("commit"):
        raise RepositoryTopicCloneError("merge-finalize hold: candidate moved after inventory capture")
    if merge_head != theirs_record.get("commit"):
        raise RepositoryTopicCloneError("merge-finalize hold: merge parent moved after inventory capture")
    _run_git(clone, ["fetch", "origin", "main"])
    origin_main_sha = _run_git(clone, ["rev-parse", "origin/main"]).strip()
    if origin_main_sha != theirs_record.get("commit"):
        raise RepositoryTopicCloneError("merge-finalize hold: origin/main moved after inventory capture")
    try:
        validate_plan(inventory, plan, repo=clone)
    except (ValueError, TypeError) as exc:
        raise RepositoryTopicCloneError(f"merge-finalize hold: preservation validation failed: {exc}") from exc
    candidate_tree = _run_git(clone, ["rev-parse", f"{candidate_sha}^{{tree}}"]).strip()
    _run_git(clone, ["commit", "--no-edit"])
    merged_sha = _run_git(clone, ["rev-parse", "HEAD"]).strip()
    merged_tree = _run_git(clone, ["rev-parse", f"{merged_sha}^{{tree}}"]).strip()
    _run_git(clone, ["merge-base", "--is-ancestor", candidate_sha, merged_sha])
    _run_git(clone, ["merge-base", "--is-ancestor", origin_main_sha, merged_sha])
    receipt = MergeMainReceipt(
        request=request_state,
        clone=clone,
        candidate_sha=candidate_sha,
        candidate_tree=candidate_tree,
        merged_sha=merged_sha,
        merged_tree=merged_tree,
        origin_main_sha=origin_main_sha,
    )
    if policy is not None:
        policy.apply(operation="finalize_merge_main", request=request_state, receipt=receipt)
    return receipt


def resume_merge_main(
    request_state: RepositoryTopicCloneRequest,
    *,
    inventory_path: Path | str | None = None,
    plan_path: Path | str | None = None,
    policy: RepositoryPolicyCallback | None = None,
) -> MergeMainReceipt:
    """Resume a stopped conflict through the same validated finalization route."""
    return finalize_merge_main(
        request_state,
        inventory_path=inventory_path,
        plan_path=plan_path,
        policy=policy,
    )


def _read_json_artifact(path: Path | str, label: str) -> object:
    """Read one JSON artifact with a typed lifecycle error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RepositoryTopicCloneError(f"{label} malformed: {exc}") from exc


def verify_publication(
    request_state: RepositoryTopicCloneRequest,
    *,
    candidate_cas: Path | str,
    pr_lifecycle: Path | str,
    publication_readback: Path | str | None = None,
) -> Mapping[str, object]:
    """Validate canonical PR-head or merged-publication lifecycle evidence."""
    contract = _load_publication_contract()
    cas = _read_json_artifact(candidate_cas, "candidate CAS receipt")
    lifecycle = _read_json_artifact(pr_lifecycle, "PR lifecycle receipt")
    try:
        if publication_readback is None:
            checked_lifecycle = contract.validate_candidate_cas_pr_transition(
                cas, lifecycle
            )
            checked_readback: Mapping[str, object] | None = None
        else:
            checked_readback = contract.validate_publication_readback_transition(
                cas,
                lifecycle,
                _read_json_artifact(
                    publication_readback, "publication readback receipt"
                ),
            )
            checked_lifecycle = contract.validate_candidate_cas_pr_transition(
                cas, lifecycle
            )
    except (TypeError, ValueError) as exc:
        raise RepositoryTopicCloneError(
            f"publication lifecycle evidence invalid: {exc}"
        ) from exc

    state = checked_lifecycle.get("state")
    if state not in {
        "draft",
        "ready",
        "changes_requested",
        "external_review",
        "merged",
    }:
        raise RepositoryTopicCloneError(
            f"publication lifecycle state does not prove a PR head: {state!r}"
        )
    if state == "merged" and checked_readback is None:
        raise RepositoryTopicCloneError(
            "publication lifecycle merged state requires publication readback"
        )
    if state != "merged" and checked_readback is not None:
        raise RepositoryTopicCloneError(
            "publication readback requires merged lifecycle state"
        )
    expected_head_ref = f"refs/heads/{request_state.branch}"
    remote = cast(Mapping[str, object], checked_lifecycle["remote_identity"])
    base = cast(Mapping[str, object], checked_lifecycle["base_identity"])
    head = cast(Mapping[str, object], checked_lifecycle["head_identity"])
    if (
        remote.get("remote_name") != "origin"
        or remote.get("repo_name") != request_state.repository
        or remote.get("ref") != expected_head_ref
        or head.get("repo_name") != request_state.repository
        or head.get("ref") != expected_head_ref
        or base.get("ref") != "refs/heads/main"
    ):
        raise RepositoryTopicCloneError(
            "publication lifecycle repository/branch identity mismatch"
        )
    return {
        "candidate_cas": cast(Mapping[str, object], cas),
        "pr_lifecycle": checked_lifecycle,
        "publication_readback": checked_readback,
    }


def cleanup(
    request_state: RepositoryTopicCloneRequest,
    *,
    candidate_cas: Path | str | None = None,
    pr_lifecycle: Path | str | None = None,
    publication_readback: Path | str | None = None,
    apply: bool,
) -> CleanupProof:
    """Validate reconstructibility evidence and remove the clone if authorized.

    A clean, identity-matched clone whose local head exactly matches the fetched
    topic branch is sufficient for ordinary cleanup. Publication receipts are
    optional enrichment; when one is supplied, the complete coherent lifecycle
    receipt set is validated before it can authorize cleanup.
    """
    has_lifecycle_evidence = any(
        artifact is not None
        for artifact in (candidate_cas, pr_lifecycle, publication_readback)
    )
    if has_lifecycle_evidence and (candidate_cas is None or pr_lifecycle is None):
        raise RepositoryTopicCloneError(
            "cleanup hold: candidate CAS and PR lifecycle evidence must be provided together"
        )
    _repository_workspace_root(request_state.workspace_root, require_ignore=False)
    clone = computed_clone_path(request_state, create_topic=False)
    topic_root = clone.parent
    owner_sha = _evidence_sha256(
        _require_evidence(request_state.owner_evidence, request_state.workspace_root)
    )
    state = _inspect(clone, request_state, owner_sha=owner_sha)
    if state.state != "ready":
        raise RepositoryTopicCloneError(f"cleanup hold: {state.state}")

    candidate_sha = _run_git(clone, ["rev-parse", "HEAD"]).strip()
    candidate_tree = _run_git(clone, ["rev-parse", f"{candidate_sha}^{{tree}}"]).strip()
    evidence = None
    if has_lifecycle_evidence:
        evidence = verify_publication(
            request_state,
            candidate_cas=cast(Path | str, candidate_cas),
            pr_lifecycle=cast(Path | str, pr_lifecycle),
            publication_readback=publication_readback,
        )
        lifecycle = cast(Mapping[str, object], evidence["pr_lifecycle"])
        head = cast(Mapping[str, object], lifecycle["head_identity"])
        if (
            head.get("commit_sha") != candidate_sha
            or head.get("tree_sha") != candidate_tree
        ):
            raise RepositoryTopicCloneError(
                "cleanup hold: local candidate identity mismatch"
            )

    if publication_readback is None:
        try:
            _run_git(clone, ["fetch", "origin", request_state.branch])
            remote_head = _run_git(
                clone, ["rev-parse", f"refs/remotes/origin/{request_state.branch}"]
            ).strip()
            remote_tree = _run_git(
                clone, ["rev-parse", f"{remote_head}^{{tree}}"]
            ).strip()
        except GitCommandError as exc:
            raise RepositoryTopicCloneError(
                f"cleanup hold: remote branch unavailable ({request_state.branch})"
            ) from exc
        if remote_head != candidate_sha or remote_tree != candidate_tree:
            raise RepositoryTopicCloneError("cleanup hold: remote branch head mismatch")
        evidence_kind = "publication-head" if has_lifecycle_evidence else "remote-head"
    else:
        _run_git(clone, ["fetch", "origin", "main"])
        origin_main_sha = _run_git(clone, ["rev-parse", "origin/main"]).strip()
        if evidence is None:
            raise RepositoryTopicCloneError(
                "cleanup hold: integrated publication evidence is missing"
            )
        readback = cast(Mapping[str, object], evidence["publication_readback"])
        pr_identity = cast(Mapping[str, object], readback["pr_identity"])
        merge_sha = cast(str, pr_identity["merge_commit_sha"])
        merge_tree = cast(str, pr_identity["merge_tree_sha"])
        observed_merge_tree = _run_git(
            clone, ["rev-parse", f"{merge_sha}^{{tree}}"]
        ).strip()
        if observed_merge_tree != merge_tree:
            raise RepositoryTopicCloneError("cleanup hold: merged tree mismatch")
        _run_git(clone, ["merge-base", "--is-ancestor", merge_sha, origin_main_sha])
        post_merge_base = cast(str, pr_identity["post_merge_base_ref_sha"])
        _run_git(
            clone, ["merge-base", "--is-ancestor", post_merge_base, origin_main_sha]
        )
        evidence_kind = "integrated-publication"

    if not apply:
        return CleanupProof(
            request=request_state, clone=clone, removed=False, evidence=evidence_kind
        )

    try:
        attestation = _attest_parent(
            _parent_request(
                request_state.workspace_root,
                purpose="repository-topic-clone-cleanup",
            )
        )
        capability = _parent_boundary.resolve_parent_owned_path(
            attestation, clone, "repository-topic-clone-cleanup", create=False
        )
        if capability.physical_path != clone or not capability.physical_path.is_dir():
            raise RepositoryTopicCloneError("cleanup hold: clone path identity changed")
        if capability.target_dev is None or capability.target_ino is None:
            raise RepositoryTopicCloneError("cleanup hold: clone identity receipt is missing")
    except Exception as exc:
        if isinstance(exc, RepositoryTopicCloneError):
            raise
        raise RepositoryTopicCloneError(f"cleanup hold: {_parent_error(exc)}") from exc
    _parent_boundary.ParentRootSideEffectBoundary().remove_parent_owned_tree(
        attestation, capability, "repository-topic-clone-cleanup"
    )
    topic_capability = _parent_boundary.resolve_parent_owned_path(
        attestation, topic_root, "repository-topic-workspace-cleanup", create=False
    )
    _parent_boundary.ParentRootSideEffectBoundary().remove_empty_parent_owned_directory(
        attestation, topic_capability, "repository-topic-workspace-cleanup"
    )
    return CleanupProof(
        request=request_state, clone=clone, removed=True, evidence=evidence_kind
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--url", required=True)
    prepare.add_argument("--repo-name", required=True)
    prepare.add_argument("--workspace-root", required=True)
    prepare.add_argument("--topic", required=True)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--owner-evidence", required=True)

    merge = commands.add_parser("merge-main")
    merge.add_argument("--url", required=True)
    merge.add_argument("--repo-name", required=True)
    merge.add_argument("--workspace-root", required=True)
    merge.add_argument("--topic", required=True)
    merge.add_argument("--branch", required=True)
    merge.add_argument("--owner-evidence", required=True)

    finalize = commands.add_parser(
        "finalize-merge",
        help="Commit an existing conflict only after preservation validation passes",
    )
    finalize.add_argument("--url", required=True)
    finalize.add_argument("--repo-name", required=True)
    finalize.add_argument("--workspace-root", required=True)
    finalize.add_argument("--topic", required=True)
    finalize.add_argument("--branch", required=True)
    finalize.add_argument("--owner-evidence", required=True)
    finalize.add_argument("--inventory")
    finalize.add_argument("--plan")

    resume = commands.add_parser(
        "resume-merge",
        help="Alias for finalize-merge after a preserved conflict is resolved",
    )
    resume.add_argument("--url", required=True)
    resume.add_argument("--repo-name", required=True)
    resume.add_argument("--workspace-root", required=True)
    resume.add_argument("--topic", required=True)
    resume.add_argument("--branch", required=True)
    resume.add_argument("--owner-evidence", required=True)
    resume.add_argument("--inventory")
    resume.add_argument("--plan")

    clean = commands.add_parser("cleanup")
    clean.add_argument("--url", required=True)
    clean.add_argument("--repo-name", required=True)
    clean.add_argument("--workspace-root", required=True)
    clean.add_argument("--topic", required=True)
    clean.add_argument("--branch", required=True)
    clean.add_argument("--owner-evidence", required=True)
    clean.add_argument("--candidate-cas")
    clean.add_argument("--pr-lifecycle")
    clean.add_argument("--publication-readback")
    clean.add_argument("--apply", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for repository-topic clone lifecycle operations."""
    args = _parse_args(argv)
    request_state = RepositoryTopicCloneRequest(
        url=args.url,
        repository=args.repo_name,
        workspace_root=Path(args.workspace_root),
        topic=args.topic,
        branch=_normalise_branch(args.branch),
        owner_evidence=_require_evidence(
            args.owner_evidence, Path(args.workspace_root)
        ),
    )
    try:
        if args.command == "prepare":
            receipt = request(
                args.url,
                args.repo_name,
                args.workspace_root,
                args.topic,
                args.branch,
                args.owner_evidence,
            )
            print("REQUEST_STATE=ready")
            print(f"REQUEST_REPO={receipt.request.repository}")
            print(f"REQUEST_TOPIC={topic_slug(receipt.request.topic)}")
            print(f"REQUEST_BRANCH={receipt.branch}")
            print(f"REQUEST_CLONE={receipt.clone}")
            print(f"REQUEST_CANDIDATE_SHA={receipt.candidate_sha}")
            print(f"REQUEST_CANDIDATE_TREE={receipt.candidate_tree}")
        elif args.command == "merge-main":
            receipt = merge_main(request_state)
            print("MERGE_STATUS=done")
            print(f"MERGE_CLONE={receipt.clone}")
            print(f"MERGE_CANDIDATE_SHA={receipt.candidate_sha}")
            print(f"MERGE_CANDIDATE_TREE={receipt.candidate_tree}")
            print(f"MERGE_INTEGRATED_SHA={receipt.merged_sha}")
            print(f"MERGE_INTEGRATED_TREE={receipt.merged_tree}")
            print(f"MERGE_ORIGIN_MAIN_SHA={receipt.origin_main_sha}")
        elif args.command in {"finalize-merge", "resume-merge"}:
            receipt = resume_merge_main(
                request_state,
                inventory_path=args.inventory,
                plan_path=args.plan,
            )
            print("MERGE_STATUS=finalized")
            print(f"MERGE_CLONE={receipt.clone}")
            print(f"MERGE_CANDIDATE_SHA={receipt.candidate_sha}")
            print(f"MERGE_CANDIDATE_TREE={receipt.candidate_tree}")
            print(f"MERGE_INTEGRATED_SHA={receipt.merged_sha}")
            print(f"MERGE_INTEGRATED_TREE={receipt.merged_tree}")
            print(f"MERGE_ORIGIN_MAIN_SHA={receipt.origin_main_sha}")
        else:
            proof = cleanup(
                request_state,
                candidate_cas=args.candidate_cas,
                pr_lifecycle=args.pr_lifecycle,
                publication_readback=args.publication_readback,
                apply=args.apply,
            )
            action = "removed" if args.apply else "would-remove"
            print(f"CLEANUP={proof.clone}:{action}")
    except RepositoryTopicCloneError as exc:
        print(f"REPOSITORY_TOPIC_CLONE_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
