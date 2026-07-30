#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Manages topic source clones and reconstructibility-gated cleanup while retaining topic-root container visibility.
# upstream design ../../documents/rule/dependency-module-changes.md generic dependency module policy
# upstream design ../../documents/design/dependency-manifest-design.md structured dependency ownership model
# upstream design ../../documents/design/request-intent-and-update-relation.md immediate dependency-clone cleanup executor and receipt projection
# upstream environment ../../.devcontainer/devcontainer.json selects the direct topic-root Compose source
# downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates lifecycle and refusal semantics
# downstream design ../../documents/tools/dependency_module_change.md documents the CLI surface
# @dependency-end
"""Manage one topic root containing one parent and its source clones.

The selected repository is never used as a vendored source branch.  A prepare
operation creates or reuses ``<parent-repo>/workspace/<topic-slug>`` and places
the parent clone and each managed dependency clone directly inside it. Branch
identity lives in Git and in a local marker; clone names do not encode
branches.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import posixpath
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

CONTAINER_WORKSPACE_ROOT = Path("/workspace")
MARKER_PREFIX = "agent-canon.topic"
INTEGRATION_REMOTE_REF = "refs/remotes/origin/main"
FULL_COMMIT_OID = re.compile(r"[0-9a-f]{40}")


class DependencyModuleChangeError(RuntimeError):
    """Raised when the topic-root contract cannot be satisfied."""


class GitCommandError(DependencyModuleChangeError):
    """Raised when a required Git operation fails."""

    def __init__(self, repo: Path, args: Sequence[str], stderr: str) -> None:
        super().__init__(f"git -C {repo} {' '.join(args)}: {stderr.strip() or 'command failed'}")


@dataclass(frozen=True)
class DependencyModule:
    """One structurally parsed ``.gitmodules`` entry."""

    path: str
    url: str
    branch: str | None

    @property
    def basename(self) -> str:
        return Path(self.path).name


@dataclass(frozen=True)
class CloneInspection:
    """Observable identity for one topic clone."""

    path: Path
    state: str
    role: str = ""
    module: str = ""
    url: str = ""
    branch: str = ""
    actual_branch: str = ""


def _run_git(repo: Path, args: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GitCommandError(repo, args, result.stderr)
    return result.stdout


def _git_succeeds(repo: Path, args: Sequence[str]) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )
    return result.returncode == 0


def _normalise_url(value: str) -> str:
    value = value.strip().rstrip("/")
    return value[:-4] if value.endswith(".git") else value


def _slug(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise DependencyModuleChangeError(f"{label} must be non-empty")
    result = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not result:
        raise DependencyModuleChangeError(f"{label} has no usable slug: {value!r}")
    return result


def _topic_name(topic: str) -> str:
    return _slug(topic, "topic")


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            raise DependencyModuleChangeError(
                f"{label} contains symlinked path component: {current}"
            )


def _assert_safe_contained_path(root: Path, candidate: Path, label: str) -> Path:
    root_absolute = root.absolute()
    candidate_absolute = candidate.absolute()
    _reject_symlink_components(root_absolute, "selected repository")
    _reject_symlink_components(candidate_absolute, label)
    if not _path_is_within(candidate_absolute, root_absolute):
        raise DependencyModuleChangeError(
            f"{label} fails lexical containment under {root_absolute}: {candidate_absolute}"
        )
    resolved_root = root_absolute.resolve(strict=False)
    resolved_candidate = candidate_absolute.resolve(strict=False)
    if not _path_is_within(resolved_candidate, resolved_root):
        raise DependencyModuleChangeError(
            f"{label} fails resolved containment under {resolved_root}: {resolved_candidate}"
        )
    return candidate_absolute


def _topic_workspace(root: Path, topic: str, *, create: bool) -> Path:
    _reject_symlink_components(root, "selected repository")
    expected_name = _topic_name(topic)
    if os.environ.get("AGENT_CANON_WORKSPACE_ROOT", "") == str(CONTAINER_WORKSPACE_ROOT):
        if root.parent != CONTAINER_WORKSPACE_ROOT:
            raise DependencyModuleChangeError(
                "container topic workspace must expose the selected repository directly below /workspace"
            )
        workspace_root = CONTAINER_WORKSPACE_ROOT
        _reject_symlink_components(workspace_root, "container workspace")
        return workspace_root
    if root.parent.parent.name == "workspace":
        if root.parent.name != expected_name:
            raise DependencyModuleChangeError(
                f"selected repository is already in workspace/{root.parent.name}, not workspace/{expected_name}"
            )
        topic_root = root.parent
        _assert_safe_contained_path(topic_root, root, "selected repository")
        return topic_root
    if root.parent.name.startswith("workspace-"):
        raise DependencyModuleChangeError(
            "legacy workspace-<topic-slug> topology is not supported; use workspace/<topic-slug>"
        )
    candidate = root / "workspace" / expected_name
    if not create and not candidate.is_dir():
        raise DependencyModuleChangeError(
            f"topic workspace is absent: {candidate}; run prepare --topic {topic} first"
        )
    if candidate.exists() and not candidate.is_dir():
        raise DependencyModuleChangeError(f"topic workspace path is not a directory: {candidate}")
    return _assert_safe_contained_path(root, candidate, "topic workspace")


def _container_workspace_root(root: Path) -> Path:
    configured = os.environ.get("AGENT_CANON_WORKSPACE_ROOT", "")
    if configured:
        if configured != str(CONTAINER_WORKSPACE_ROOT):
            raise DependencyModuleChangeError(
                "AGENT_CANON_WORKSPACE_ROOT must be the fixed container path /workspace"
            )
        if root.parent != CONTAINER_WORKSPACE_ROOT:
            raise DependencyModuleChangeError(
                "AGENT_CANON_WORKSPACE_ROOT=/workspace requires the selected repository "
                "to be directly below /workspace"
            )
        return CONTAINER_WORKSPACE_ROOT
    return root.parent


def _parse_gitmodules(root: Path) -> tuple[DependencyModule, ...]:
    manifest = root / ".gitmodules"
    if not manifest.is_file():
        raise DependencyModuleChangeError(f"missing structured manifest: {manifest}")
    result = subprocess.run(
        ["git", "-C", str(root), "config", "--file", str(manifest), "--null", "--list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitCommandError(root, ["config", "--file", str(manifest), "--null", "--list"], result.stderr)
    values: dict[str, dict[str, str]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        key, separator, value = record.partition("\n")
        if not separator:
            raise DependencyModuleChangeError(f"invalid structured .gitmodules record: {record!r}")
        match = re.fullmatch(r"submodule\.(.+)\.(path|url|branch)", key)
        if match:
            name, field = match.groups()
            values.setdefault(name, {})[field] = value
    modules: list[DependencyModule] = []
    for name, fields in sorted(values.items()):
        path = fields.get("path", "").strip()
        url = fields.get("url", "").strip()
        branch_value = fields.get("branch")
        branch = branch_value.strip() if branch_value is not None else None
        if not path or not url:
            raise DependencyModuleChangeError(
                f"submodule.{name} requires path and url in {manifest}"
            )
        path_object = Path(path)
        if path_object.is_absolute() or ".." in path_object.parts or not path_object.name:
            raise DependencyModuleChangeError(f"submodule.{name} has unsafe path: {path}")
        modules.append(DependencyModule(path, url, branch))
    if not modules:
        raise DependencyModuleChangeError(f"no submodules found in {manifest}")
    by_basename: dict[str, str] = {}
    for module in modules:
        if module.basename in by_basename:
            raise DependencyModuleChangeError(
                f"basename collision: {by_basename[module.basename]} and {module.path}"
            )
        by_basename[module.basename] = module.path
    return tuple(modules)


def _select_module(modules: Iterable[DependencyModule], value: str) -> DependencyModule:
    for module in modules:
        if module.path == value:
            return module
    raise DependencyModuleChangeError(
        f"unknown --module {value!r}; known: {', '.join(module.path for module in modules)}"
    )


def _remote_url(path: Path) -> str:
    return _run_git(path, ["config", "--get", "remote.origin.url"]).strip()


def _resolve_module_url(root: Path, value: str) -> str:
    """Resolve a Git-style relative submodule URL against the parent origin."""
    if not value.startswith(("./", "../")):
        return value
    parent_remote = _remote_url(root)
    if not parent_remote:
        raise DependencyModuleChangeError(
            f"relative submodule URL requires parent origin identity: {value}"
        )
    if "://" in parent_remote:
        parsed = urlsplit(parent_remote)
        resolved_path = posixpath.normpath(posixpath.join(parsed.path, value))
        return urlunsplit(
            (parsed.scheme, parsed.netloc, resolved_path, parsed.query, parsed.fragment)
        )
    scp_match = re.fullmatch(r"([^/:]+):(.+)", parent_remote)
    if scp_match:
        host, parent_path = scp_match.groups()
        return f"{host}:{posixpath.normpath(posixpath.join(parent_path, value))}"
    parent_path = Path(parent_remote)
    if not parent_path.is_absolute():
        parent_path = root / parent_path
    return posixpath.normpath(posixpath.join(str(parent_path), value))


def _remote_branch_exists(remote: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 2):
        raise DependencyModuleChangeError(
            f"cannot inspect remote branch {branch!r} on {_normalise_url(remote)}: "
            f"{result.stderr.strip() or 'git ls-remote failed'}"
        )
    return result.returncode == 0


def _checkout_task_branch(path: Path, remote: str, branch: str) -> None:
    """Track an existing remote task branch or create it from the base checkout."""
    _checkout_task_branch_from(path, remote, branch, base_ref=None)


def _checkout_task_branch_from(
    path: Path, remote: str, branch: str, *, base_ref: str | None
) -> None:
    """Track an existing task branch or create it from an explicit base ref."""
    if _actual_branch(path) == branch:
        return
    if _remote_branch_exists(remote, branch):
        _run_git(path, ["checkout", "--track", "-b", branch, f"origin/{branch}"])
        return
    if base_ref is None:
        _run_git(path, ["checkout", "-b", branch])
    else:
        _run_git(path, ["checkout", "-b", branch, base_ref])


def _clone_with_task_branch(
    runner: Path,
    remote: str,
    target: Path,
    *,
    base_branch: str | None,
    task_branch: str | None,
) -> None:
    args = ["clone"]
    if base_branch:
        args.extend(("--branch", base_branch))
    args.extend((remote, str(target)))
    _run_git(runner, args)
    if task_branch:
        _checkout_task_branch(target, remote, task_branch)


def _clone_from_latest_origin_main(remote: str, target: Path, branch: str) -> str:
    """Clone a source repository and create a task branch from latest origin/main."""
    _run_git(target.parent, ["clone", remote, str(target)])
    _run_git(target, ["fetch", "origin", "main"])
    try:
        base_sha = _run_git(target, ["rev-parse", "origin/main"]).strip()
    except GitCommandError as exc:
        raise DependencyModuleChangeError(
            f"source remote has no usable origin/main after fetch: {remote}"
        ) from exc
    _create_fresh_branch_from_origin_main(target, branch)
    return base_sha


def _clone_for_continuation(remote: str, target: Path, branch: str) -> str:
    """Clone and continue an already-published remote task branch."""
    if not _remote_branch_exists(remote, branch):
        raise DependencyModuleChangeError(
            f"workspace continuation requires existing remote branch: {branch}"
        )
    _run_git(target.parent, ["clone", remote, str(target)])
    _run_git(target, ["fetch", "origin", "main"])
    base_sha = _run_git(target, ["rev-parse", "origin/main"]).strip()
    _run_git(target, ["checkout", "--track", "-b", branch, f"origin/{branch}"])
    return base_sha


def _create_fresh_branch_from_origin_main(path: Path, branch: str) -> None:
    """Create a new local branch from the fetched origin/main ref."""
    _run_git(path, ["checkout", "-b", branch, "origin/main"])


def _actual_branch(path: Path) -> str:
    try:
        return _run_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
    except GitCommandError:
        return ""


def _marker(path: Path, field: str) -> str:
    try:
        return _run_git(path, ["config", "--local", "--get", f"{MARKER_PREFIX}.{field}"]).strip()
    except GitCommandError:
        return ""


def _inspect(
    path: Path,
    *,
    role: str,
    module: DependencyModule | None = None,
    topic: str = "",
    branch: str | None = None,
    placement: str | None = None,
    owner_evidence_sha256: str | None = None,
    topic_identity: str | None = None,
    module_url: str | None = None,
    allow_stale_membership: bool = False,
) -> CloneInspection:
    if not path.exists() and not path.is_symlink():
        return CloneInspection(path, "absent")
    if path.is_symlink():
        return CloneInspection(path, "unknown-path")
    if not path.is_dir() or not _git_succeeds(path, ["rev-parse", "--is-inside-work-tree"]):
        return CloneInspection(path, "not-git")
    try:
        remote = _remote_url(path)
    except GitCommandError:
        return CloneInspection(path, "missing-origin")
    actual = _actual_branch(path)
    marker_role = _marker(path, "role")
    marker_topic = _marker(path, "topic")
    marker_module = _marker(path, "module")
    marker_url = _marker(path, "url")
    marker_branch = _marker(path, "branch")
    if not allow_stale_membership and (marker_role != role or marker_topic != topic):
        return CloneInspection(path, "membership-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if placement is not None and _marker(path, "placement") != placement:
        return CloneInspection(path, "placement-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if topic_identity is not None and _marker(path, "topic-input") != topic_identity:
        return CloneInspection(path, "topic-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if (
        owner_evidence_sha256 is not None
        and _marker(path, "owner-evidence-sha256") != owner_evidence_sha256
    ):
        return CloneInspection(path, "owner-evidence-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if role == "module" and module is not None:
        expected_url = module_url if module_url is not None else module.url
        if marker_module != module.path or marker_url != _normalise_url(expected_url):
            return CloneInspection(path, "identity-mismatch", marker_role, marker_module, remote, marker_branch, actual)
        if _normalise_url(remote) != _normalise_url(expected_url):
            return CloneInspection(path, "url-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if role == "parent":
        if not marker_url:
            return CloneInspection(path, "identity-mismatch", marker_role, marker_module, remote, marker_branch, actual)
        if _normalise_url(remote) != marker_url:
            return CloneInspection(path, "url-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if not marker_branch or not actual or marker_branch != actual:
        return CloneInspection(path, "actual-branch-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if branch is not None and actual != branch:
        return CloneInspection(path, "branch-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    return CloneInspection(path, "ready", marker_role, marker_module, remote, marker_branch, actual)


def _set_marker(
    path: Path,
    *,
    topic: str,
    role: str,
    module: str,
    url: str,
    branch: str,
    placement: str | None = None,
    base_ref: str | None = None,
    base_sha: str | None = None,
    owner_evidence_sha256: str | None = None,
    topic_identity: str | None = None,
) -> None:
    values = {"topic": topic, "role": role, "module": module, "url": _normalise_url(url), "branch": branch}
    if placement is not None:
        values["placement"] = placement
    if base_ref is not None:
        values["base-ref"] = base_ref
    if base_sha is not None:
        values["base-sha"] = base_sha
    if owner_evidence_sha256 is not None:
        values["owner-evidence-sha256"] = owner_evidence_sha256
    if topic_identity is not None:
        values["topic-input"] = topic_identity
    for field, value in values.items():
        _run_git(path, ["config", "--local", f"{MARKER_PREFIX}.{field}", value])


def _require_evidence(root: Path, value: str) -> Path:
    evidence = Path(value)
    if not evidence.is_absolute():
        evidence = root / evidence
    if not evidence.is_file() or evidence.stat().st_size == 0:
        raise DependencyModuleChangeError(f"owner evidence must be a non-empty file: {evidence}")
    return evidence


def _evidence_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: str, label: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise DependencyModuleChangeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_named_branch(value: str) -> str:
    branch = value
    if not branch:
        raise DependencyModuleChangeError("branch must be non-empty")
    if branch != branch.strip() or any(character in branch for character in "\r\n\x00"):
        raise DependencyModuleChangeError(f"branch must be an exact named branch: {value!r}")
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DependencyModuleChangeError(f"branch is not a valid named branch: {value!r}")
    return branch


def _parent_remote(root: Path) -> str:
    try:
        return _remote_url(root)
    except GitCommandError as exc:
        raise DependencyModuleChangeError(f"selected repository has no usable parent remote: {exc}") from exc


def _existing_topic_parent(topic_root: Path, topic: str) -> Path | None:
    """Find the sole managed parent when the selected root is a source clone."""
    candidates = [
        child
        for child in topic_root.iterdir()
        if child.is_dir()
        and not child.is_symlink()
        and _marker(child, "role") == "parent"
        and _marker(child, "topic") == topic
    ] if topic_root.is_dir() else []
    if len(candidates) > 1:
        raise DependencyModuleChangeError(
            f"topic workspace has multiple managed parent clones: {', '.join(str(item) for item in candidates)}"
        )
    return candidates[0] if candidates else None


def _resolve_topic_parent(
    root: Path, topic: str, *, create: bool, allow_stale_membership: bool = False
) -> Path:
    """Resolve the parent clone even when --root points at a module clone."""
    topic_slug = _slug(topic, "topic")
    topic_root = _topic_workspace(root, topic, create=create)
    if root.parent == topic_root:
        selected = _inspect(
            root,
            role="parent",
            topic=topic_slug,
            allow_stale_membership=allow_stale_membership,
        )
        if selected.state == "ready":
            return root
        existing = _existing_topic_parent(topic_root, topic_slug)
        if existing is not None:
            return existing
        if not create:
            raise DependencyModuleChangeError(
                f"topic workspace has no managed parent clone: {topic_root}"
            )
    return topic_root / root.name


def _ensure_topic_parent(root: Path, topic: str, parent_branch: str | None) -> Path:
    topic_root = _topic_workspace(root, topic, create=True)
    if root.parent == topic_root:
        inspection = _inspect(
            root, role="parent", topic=_slug(topic, "topic"), branch=parent_branch
        )
        if inspection.state != "ready":
            existing = _existing_topic_parent(topic_root, _slug(topic, "topic"))
            if existing is None:
                raise DependencyModuleChangeError(
                    f"selected topic parent is not a managed clone: {root} ({inspection.state})"
                )
            existing_inspection = _inspect(
                existing,
                role="parent",
                topic=_slug(topic, "topic"),
                branch=parent_branch,
            )
            if existing_inspection.state != "ready":
                raise DependencyModuleChangeError(
                    f"topic parent branch is not reusable: {existing} ({existing_inspection.state})"
                )
            return existing
        return root
    topic_root.mkdir(parents=True, exist_ok=True)
    parent_path = _assert_safe_contained_path(
        topic_root, topic_root / root.name, "topic parent clone"
    )
    parent_remote = _parent_remote(root)
    inspection = _inspect(
        parent_path,
        role="parent",
        topic=_slug(topic, "topic"),
        branch=parent_branch,
    )
    if inspection.state == "absent":
        base_branch = (
            parent_branch
            if parent_branch and _remote_branch_exists(parent_remote, parent_branch)
            else None
        )
        _clone_with_task_branch(
            root,
            parent_remote,
            parent_path,
            base_branch=base_branch,
            task_branch=parent_branch,
        )
        branch = _actual_branch(parent_path)
        if not branch:
            raise DependencyModuleChangeError("new parent clone has no named branch")
        _set_marker(path=parent_path, topic=_slug(topic, "topic"), role="parent", module="", url=parent_remote, branch=branch)
        if _inspect(parent_path, role="parent", topic=_slug(topic, "topic")).state != "ready":
            raise DependencyModuleChangeError("new parent clone failed identity validation")
        return parent_path
    if inspection.state == "ready" and _normalise_url(inspection.url) == _normalise_url(parent_remote):
        return parent_path
    raise DependencyModuleChangeError(
        f"topic parent path is occupied or not managed: {parent_path} ({inspection.state})"
    )


def _prepare(
    root: Path,
    topic: str,
    module_value: str,
    branch: str,
    evidence_value: str,
    parent_branch: str | None,
) -> None:
    _require_evidence(root, evidence_value)
    parent_root = _ensure_topic_parent(root, topic, parent_branch)
    modules = _parse_gitmodules(parent_root)
    module = _select_module(modules, module_value)
    source_url = _resolve_module_url(parent_root, module.url)
    topic_slug = _slug(topic, "topic")
    topic_root = parent_root.parent
    if module.basename == parent_root.name:
        raise DependencyModuleChangeError("module basename collides with topic parent clone name")
    clone_path = _assert_safe_contained_path(
        topic_root, topic_root / module.basename, "module source clone"
    )
    inspection = _inspect(
        clone_path,
        role="module",
        module=module,
        topic=topic_slug,
        branch=branch,
        module_url=source_url,
    )
    if inspection.state == "ready":
        print(f"PARENT_ROOT={parent_root}")
        print(f"SOURCE_CLONE={clone_path}")
        print(f"CONTINUE_PATH={clone_path}")
        return
    if inspection.state != "absent":
        raise DependencyModuleChangeError(
            f"cannot prepare {module.path} at {clone_path}: {inspection.state}; "
            "use a different topic for a different branch or responsibility"
        )
    _clone_with_task_branch(
        parent_root,
        source_url,
        clone_path,
        base_branch=module.branch,
        task_branch=branch,
    )
    _set_marker(path=clone_path, topic=topic_slug, role="module", module=module.path, url=source_url, branch=branch)
    final = _inspect(
        clone_path,
        role="module",
        module=module,
        topic=topic_slug,
        branch=branch,
        module_url=source_url,
    )
    if final.state != "ready":
        raise DependencyModuleChangeError(f"new dependency clone failed identity validation: {final.state}")
    print(f"PARENT_ROOT={parent_root}")
    print(f"SOURCE_CLONE={clone_path}")
    print(f"CONTINUE_PATH={clone_path}")


def _workspace_clone_path(
    root: Path, topic: str, module: DependencyModule, *, create: bool
) -> Path:
    topic_root = _topic_workspace(root, topic, create=create)
    clone_path = topic_root / module.basename
    if clone_path == root.absolute():
        raise DependencyModuleChangeError(
            "--placement workspace requires a parent repository root, not the computed source clone"
        )
    return _assert_safe_contained_path(topic_root, clone_path, "workspace source clone")


def _workspace_source_identity(path: Path) -> tuple[str, str, str, str, str, str]:
    remote = _remote_url(path)
    base_ref = _marker(path, "base-ref")
    base_sha = _marker(path, "base-sha")
    owner_evidence_sha256 = _marker(path, "owner-evidence-sha256")
    branch = _actual_branch(path)
    head_sha = _run_git(path, ["rev-parse", "HEAD"]).strip()
    if (
        base_ref != "origin/main"
        or not re.fullmatch(r"[0-9a-f]{40}", base_sha)
        or not re.fullmatch(r"[0-9a-f]{64}", owner_evidence_sha256)
    ):
        raise DependencyModuleChangeError(
            f"workspace source clone has incomplete source/evidence identity: {path}"
        )
    if not branch:
        raise DependencyModuleChangeError(f"workspace source clone has no named branch: {path}")
    return remote, base_ref, base_sha, owner_evidence_sha256, branch, head_sha


def _print_workspace_source(
    path: Path,
    *,
    topic: str,
    module: DependencyModule,
    base_sha: str | None = None,
    placement: str = "workspace",
) -> None:
    (
        remote,
        base_ref,
        recorded_base_sha,
        owner_evidence_sha256,
        branch,
        head_sha,
    ) = _workspace_source_identity(path)
    if base_sha is not None and recorded_base_sha != base_sha:
        raise DependencyModuleChangeError(
            f"workspace source clone base identity changed during prepare: {path}"
        )
    print(f"PLACEMENT={placement}")
    print(f"TOPIC={topic}")
    print(f"MODULE={module.path}")
    print(f"SOURCE_CLONE={path}")
    print(f"CONTINUE_PATH={path}")
    print(f"SOURCE_REMOTE={remote}")
    print(f"SOURCE_BASE_REF={base_ref}")
    print(f"SOURCE_BASE_SHA={recorded_base_sha}")
    print(f"SOURCE_OWNER_EVIDENCE_SHA256={owner_evidence_sha256}")
    print(f"SOURCE_BRANCH={branch}")
    print(f"SOURCE_HEAD_SHA={head_sha}")


def _prepare_workspace(
    root: Path,
    topic: str,
    module_value: str,
    branch_value: str,
    evidence_value: str,
    parent_branch: str | None,
    *,
    placement: str,
) -> None:
    if parent_branch is not None:
        raise DependencyModuleChangeError(
            "--parent-branch is incompatible with --placement workspace"
        )
    if not topic or topic != topic.strip() or any(character in topic for character in "\r\n\x00"):
        raise DependencyModuleChangeError(f"topic must be an exact non-empty identity: {topic!r}")
    topic_slug = _topic_name(topic)
    branch = _require_named_branch(branch_value)
    evidence = _require_evidence(root, evidence_value)
    evidence_sha256 = _evidence_sha256(evidence)
    modules = _parse_gitmodules(root)
    module = _select_module(modules, module_value)
    source_url = _resolve_module_url(root, module.url)
    clone_path = _workspace_clone_path(root, topic_slug, module, create=True)
    if placement == "workspace" and _remote_branch_exists(source_url, branch):
        raise DependencyModuleChangeError(
            f"fresh workspace branch already exists remotely: {branch}"
        )
    if placement == "workspace" and clone_path.exists() and not clone_path.is_symlink():
        if _git_succeeds(clone_path, ["show-ref", "--verify", f"refs/heads/{branch}"]):
            raise DependencyModuleChangeError(
                f"fresh workspace branch already exists locally: {branch}"
            )
    inspection = _inspect(
        clone_path,
        role="module",
        module=module,
        topic=topic_slug,
        branch=branch,
        placement=placement,
        owner_evidence_sha256=evidence_sha256,
        topic_identity=topic,
        module_url=source_url,
    )
    if inspection.state == "ready":
        _print_workspace_source(
            clone_path,
            topic=topic_slug,
            module=module,
            placement=placement,
        )
        return
    if inspection.state != "absent":
        raise DependencyModuleChangeError(
            f"cannot prepare workspace source clone at {clone_path}: {inspection.state}; "
            "the computed clone is occupied by a different identity"
        )
    clone_path.parent.mkdir(parents=True, exist_ok=True)
    if placement == "workspace":
        base_sha = _clone_from_latest_origin_main(source_url, clone_path, branch)
    else:
        base_sha = _clone_for_continuation(source_url, clone_path, branch)
    _set_marker(
        path=clone_path,
        topic=topic_slug,
        role="module",
        module=module.path,
        url=source_url,
        branch=branch,
        placement=placement,
        base_ref="origin/main",
        base_sha=base_sha,
        owner_evidence_sha256=evidence_sha256,
        topic_identity=topic,
    )
    final = _inspect(
        clone_path,
        role="module",
        module=module,
        topic=topic_slug,
        branch=branch,
        placement=placement,
        owner_evidence_sha256=evidence_sha256,
        topic_identity=topic,
        module_url=source_url,
    )
    if final.state != "ready":
        raise DependencyModuleChangeError(
            f"new workspace source clone failed identity validation: {final.state}"
        )
    _print_workspace_source(
        clone_path,
        topic=topic_slug,
        module=module,
        base_sha=base_sha,
        placement=placement,
    )


def _module_path_states(
    parent_root: Path, modules: tuple[DependencyModule, ...], topic: str
) -> tuple[CloneInspection, ...]:
    """Return every present expected module path, including invalid clones."""
    states: list[CloneInspection] = []
    for module in modules:
        candidate = parent_root.parent / module.basename
        inspection = _inspect(
            candidate,
            role="module",
            module=module,
            topic=topic,
            module_url=_resolve_module_url(parent_root, module.url),
        )
        if inspection.state != "absent":
            states.append(inspection)
    return tuple(states)


def _topic_changed_paths(path: Path, topic_base: str, topic_tip: str) -> tuple[str, ...]:
    """Return topic paths without allowing Git rename similarity to hide entries."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            topic_base,
            topic_tip,
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GitCommandError(
            path,
            ["diff", "--name-only", "--no-renames", topic_base, topic_tip],
            result.stderr.decode(errors="replace"),
        )
    return tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    )


def _tree_entry(
    path: Path, commit: str, changed_path: str
) -> tuple[str, str, str, str] | None:
    """Read one tree entry as ``(path, object, mode, type)`` or absence."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
            "--",
            f":(literal){changed_path}",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise GitCommandError(
            path,
            ["ls-tree", "-r", "-z", commit, "--", changed_path],
            result.stderr.decode(errors="replace"),
        )
    records = [record for record in result.stdout.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1 or b"\t" not in records[0]:
        raise GitCommandError(
            path,
            ["ls-tree", "-r", "-z", commit, "--", changed_path],
            "expected exactly one tree entry",
        )
    metadata, returned_path = records[0].split(b"\t", 1)
    fields = metadata.split()
    if len(fields) != 3:
        raise GitCommandError(
            path,
            ["ls-tree", "-r", "-z", commit, "--", changed_path],
            "tree entry has unexpected fields",
        )
    object_mode, object_type, object_id = fields
    return (
        returned_path.decode("utf-8", errors="surrogateescape"),
        object_id.decode("ascii"),
        object_mode.decode("ascii"),
        object_type.decode("ascii"),
    )


def _remote_ref_contains_commit(path: Path, commit: str) -> bool:
    """Return whether any fetched remote ref retains the selected commit."""
    refs = _run_git(
        path, ["for-each-ref", "--format=%(refname)", "refs/remotes"]
    ).splitlines()
    return any(
        _git_succeeds(path, ["merge-base", "--is-ancestor", commit, ref])
        for ref in refs
    )


def _integrated_commit_failure(
    path: Path,
    topic_base: str,
    topic_paths: tuple[str, ...],
    topic_tip: str,
    integrated_commit: str,
) -> str | None:
    """Return a typed refusal unless every topic final tree entry is identical."""
    if not FULL_COMMIT_OID.fullmatch(integrated_commit):
        return "integrated-commit-invalid"
    if not _git_succeeds(path, ["cat-file", "-e", f"{integrated_commit}^{{commit}}"]):
        return "integrated-commit-not-found"
    if not _git_succeeds(
        path,
        ["merge-base", "--is-ancestor", integrated_commit, INTEGRATION_REMOTE_REF],
    ):
        return "integrated-commit-not-reachable-from-origin-main"
    if not _git_succeeds(
        path,
        ["merge-base", "--is-ancestor", topic_base, integrated_commit],
    ):
        return "integrated-commit-not-descendant-of-topic-base"
    if not topic_paths and not _remote_ref_contains_commit(path, topic_tip):
        return "integrated-commit-empty-topic-without-remote-tip"
    try:
        for changed_path in topic_paths:
            topic_entry = _tree_entry(path, topic_tip, changed_path)
            integrated_entry = _tree_entry(path, integrated_commit, changed_path)
            if topic_entry is not None and topic_entry[0] != changed_path:
                return "integrated-commit-not-equivalent"
            if integrated_entry is not None and integrated_entry[0] != changed_path:
                return "integrated-commit-not-equivalent"
            if topic_entry != integrated_entry:
                return "integrated-commit-not-equivalent"
    except GitCommandError:
        return "integrated-commit-evidence-unreadable"
    return None


def _discover_integrated_commit(
    path: Path, topic_base: str, topic_paths: tuple[str, ...], topic_tip: str
) -> str | None:
    """Find the newest equivalent commit on the canonical fetched main ref."""
    for candidate in _run_git(
        path, ["rev-list", "--first-parent", INTEGRATION_REMOTE_REF]
    ).splitlines():
        if (
            _integrated_commit_failure(path, topic_base, topic_paths, topic_tip, candidate)
            is None
        ):
            return candidate
    return None


def _cleanup_readiness(path: Path, integrated_commit: str | None = None) -> str | None:
    try:
        _run_git(path, ["fetch", "--all", "--prune"])
    except GitCommandError as exc:
        return f"fetch-failed:{exc}"
    if _run_git(path, ["status", "--porcelain=v1", "--untracked-files=all"]).strip():
        return "dirty-worktree-index-or-untracked"
    if sum(line.startswith("worktree ") for line in _run_git(path, ["worktree", "list", "--porcelain"]).splitlines()) > 1:
        return "linked-worktree-present"
    topic_tip = _run_git(path, ["rev-parse", "HEAD"]).strip()
    try:
        topic_base = _run_git(path, ["merge-base", topic_tip, INTEGRATION_REMOTE_REF]).strip()
    except GitCommandError:
        return "integrated-commit-base-unavailable"
    if not topic_base:
        return "integrated-commit-base-unavailable"
    unique_topic_commits = _run_git(
        path,
        ["rev-list", f"{topic_base}..{topic_tip}", "--not", "--remotes"],
    ).strip()
    if unique_topic_commits or integrated_commit is not None:
        try:
            topic_paths = _topic_changed_paths(path, topic_base, topic_tip)
        except GitCommandError:
            return "integrated-commit-evidence-unreadable"
        if integrated_commit is not None:
            failure = _integrated_commit_failure(
                path, topic_base, topic_paths, topic_tip, integrated_commit
            )
            if failure is not None:
                return failure
        elif _discover_integrated_commit(path, topic_base, topic_paths, topic_tip) is None:
            return "unique-local-commits"
    return None


def _require_cleanup_authority() -> None:
    if (
        os.environ.get("AGENT_CANON_BRANCH_WORKTREE_AUTHORITY", "") in {"user_request", "agent_canon_workflow"}
        and os.environ.get("AGENT_CANON_BRANCH_WORKTREE_REASON", "")
        and os.environ.get("AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY", "") == "explicit_user_approval"
        and os.environ.get("AGENT_CANON_DESTRUCTIVE_GIT_REASON", "")
    ):
        return
    raise DependencyModuleChangeError("cleanup --apply requires same-command authority/reason fields")


def _inspect_cleanup_parent(parent_root: Path, topic: str) -> CloneInspection:
    """Read parent membership before cleanup proof without making it a blocker."""
    strict = _inspect(parent_root, role="parent", topic=topic)
    if strict.state != "membership-mismatch":
        return strict
    relaxed = _inspect(
        parent_root,
        role="parent",
        topic=topic,
        allow_stale_membership=True,
    )
    print("CLEANUP parent marker-readback=membership-mismatch")
    return relaxed


def _cleanup_module(
    parent_root: Path,
    topic: str,
    module: DependencyModule,
    expected: Path,
    apply: bool,
    integrated_commit: str | None = None,
    parent_inspection: CloneInspection | None = None,
) -> None:
    clone = parent_root.parent / module.basename
    clone = _assert_safe_contained_path(parent_root.parent, clone, "module cleanup clone")
    if not expected.is_absolute() or expected != clone:
        raise DependencyModuleChangeError(f"--expected-clone must exactly equal {clone}")
    inspection = _inspect(
        clone,
        role="module",
        module=module,
        topic=topic,
        module_url=_resolve_module_url(parent_root, module.url),
    )
    marker_readback = inspection.state
    if inspection.state == "membership-mismatch":
        inspection = _inspect(
            clone,
            role="module",
            module=module,
            topic=topic,
            module_url=_resolve_module_url(parent_root, module.url),
            allow_stale_membership=True,
        )
        print(f"CLEANUP module={module.path} marker-readback={marker_readback}")
    if inspection.state == "absent":
        print(f"CLEANUP module={module.path} action=hold reason=absent")
        return
    if inspection.state != "ready":
        print(f"CLEANUP module={module.path} action=hold reason={inspection.state}")
        return
    reason = _cleanup_readiness(clone, integrated_commit)
    if reason:
        print(f"CLEANUP module={module.path} action=hold reason={reason}")
        return
    if parent_inspection is not None and parent_inspection.state != "ready":
        print(
            f"CLEANUP module={module.path} action=hold "
            f"reason=parent-{parent_inspection.state}"
        )
        return
    if not apply:
        print(f"CLEANUP module={module.path} action=would-remove path={clone}")
        return
    _require_cleanup_authority()
    clone = _assert_safe_contained_path(parent_root.parent, clone, "module cleanup clone")
    shutil.rmtree(clone)
    print(f"CLEANUP module={module.path} action=removed path={clone}")


def _cleanup_parent(
    parent_root: Path,
    modules: tuple[DependencyModule, ...],
    topic: str,
    expected: Path,
    apply: bool,
    integrated_commit: str | None = None,
    parent_inspection: CloneInspection | None = None,
) -> None:
    parent_root = _assert_safe_contained_path(
        parent_root.parent, parent_root, "parent cleanup clone"
    )
    if not expected.is_absolute() or expected != parent_root:
        raise DependencyModuleChangeError(f"--expected-parent must exactly equal {parent_root}")
    inspection = parent_inspection or _inspect_cleanup_parent(parent_root, topic)
    for module in modules:
        candidate = parent_root.parent / module.basename
        child_inspection = _inspect(
            candidate,
            role="module",
            module=module,
            topic=topic,
            module_url=_resolve_module_url(parent_root, module.url),
        )
        if child_inspection.state == "membership-mismatch":
            print(
                f"CLEANUP module={module.path} "
                f"marker-readback=membership-mismatch path={candidate}"
            )
    reason = _cleanup_readiness(parent_root, integrated_commit)
    if reason:
        print(f"CLEANUP parent action=hold reason={reason}")
        return
    blockers = _module_path_states(parent_root, modules, topic)
    if blockers:
        details = ", ".join(f"{item.path} ({item.state})" for item in blockers)
        raise DependencyModuleChangeError(
            f"parent clone cleanup refused while expected module paths exist: {details}"
        )
    expected_names = {parent_root.name, *(module.basename for module in modules)}
    unknown = tuple(
        child for child in parent_root.parent.iterdir() if child.name not in expected_names
    )
    if unknown:
        raise DependencyModuleChangeError(
            "parent clone cleanup refused by unknown topic entries: "
            + ", ".join(str(item) for item in unknown)
        )
    if inspection.state != "ready":
        print(f"CLEANUP parent action=hold reason={inspection.state}")
        return
    if not apply:
        print(f"CLEANUP parent action=would-remove path={parent_root}")
        return
    _require_cleanup_authority()
    topic_root = parent_root.parent
    _assert_safe_contained_path(topic_root, parent_root, "parent cleanup clone")
    shutil.rmtree(parent_root)
    print(f"CLEANUP parent action=removed path={parent_root}")
    if topic_root.exists() and not any(topic_root.iterdir()):
        topic_root.rmdir()
        print(f"CLEANUP topic action=removed path={topic_root}")


def _cleanup_workspace(
    root: Path,
    topic: str,
    module: DependencyModule,
    expected: Path,
    apply: bool,
    placement: str,
    owner_evidence_sha256: str | None,
    integrated_commit: str | None = None,
) -> None:
    if owner_evidence_sha256 is None:
        raise DependencyModuleChangeError(
            "--owner-evidence-sha256 is required with workspace cleanup"
        )
    _require_sha256(owner_evidence_sha256, "--owner-evidence-sha256")
    topic_root = _topic_workspace(root, topic, create=False)
    clone = topic_root / module.basename
    clone = _assert_safe_contained_path(topic_root, clone, "workspace cleanup clone")
    if not expected.is_absolute() or expected != clone:
        raise DependencyModuleChangeError(f"--expected-clone must exactly equal {clone}")
    inspection = _inspect(
        clone,
        role="module",
        module=module,
        topic=_topic_name(topic),
        placement=placement,
        owner_evidence_sha256=owner_evidence_sha256,
        module_url=_resolve_module_url(root, module.url),
    )
    marker_readback = inspection.state
    if inspection.state == "membership-mismatch":
        inspection = _inspect(
            clone,
            role="module",
            module=module,
            topic=_topic_name(topic),
            placement=placement,
            owner_evidence_sha256=owner_evidence_sha256,
            module_url=_resolve_module_url(root, module.url),
            allow_stale_membership=True,
        )
        print(
            f"CLEANUP module={module.path} placement={placement} "
            f"marker-readback={marker_readback}"
        )
    if inspection.state == "absent":
        print(f"CLEANUP module={module.path} placement={placement} action=hold reason=absent")
        return
    if inspection.state != "ready":
        print(f"CLEANUP module={module.path} placement={placement} action=hold reason={inspection.state}")
        return
    reason = _cleanup_readiness(clone, integrated_commit)
    if reason:
        print(f"CLEANUP module={module.path} placement={placement} action=hold reason={reason}")
        return
    if not apply:
        print(f"CLEANUP module={module.path} placement={placement} action=would-remove path={clone}")
        return
    _require_cleanup_authority()
    clone = _assert_safe_contained_path(topic_root, clone, "workspace cleanup clone")
    shutil.rmtree(clone)
    print(f"CLEANUP module={module.path} placement={placement} action=removed path={clone}")
    if topic_root != CONTAINER_WORKSPACE_ROOT and topic_root.exists() and not any(topic_root.iterdir()):
        _assert_safe_contained_path(root, topic_root, "workspace cleanup topic root")
        topic_root.rmdir()
        print(f"CLEANUP topic action=removed path={topic_root}")


def _status(parent_root: Path, modules: tuple[DependencyModule, ...], topic: str) -> None:
    print("DEPENDENCY_MODULE_CHANGE=status")
    print(f"TOPIC={topic}")
    print(f"TOPIC_ROOT={parent_root.parent}")
    print(f"PARENT_ROOT={parent_root}")
    for module in modules:
        inspection = _inspect(parent_root.parent / module.basename, role="module", module=module, topic=topic)
        print(f"MODULE={module.path} STATE={inspection.state} CLONE={inspection.path} BRANCH={inspection.actual_branch}")


def _status_workspace(root: Path, topic: str, placement: str) -> None:
    topic_slug = _topic_name(topic)
    modules = _parse_gitmodules(root)
    topic_root = _topic_workspace(root, topic_slug, create=False)
    print("DEPENDENCY_MODULE_CHANGE=status")
    print(f"PLACEMENT={placement}")
    print(f"TOPIC={topic_slug}")
    print(f"TOPIC_ROOT={topic_root}")
    for module in modules:
        clone = _assert_safe_contained_path(
            topic_root, topic_root / module.basename, "workspace status clone"
        )
        inspection = _inspect(
            clone,
            role="module",
            module=module,
            topic=topic_slug,
            placement=placement,
            module_url=_resolve_module_url(root, module.url),
        )
        print(f"MODULE={module.path} STATE={inspection.state} CLONE={clone} BRANCH={inspection.actual_branch}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Selected repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--topic", required=True)
    status.add_argument(
        "--placement", choices=("workspace", "workspace-continuation")
    )
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--topic", required=True)
    prepare.add_argument("--module", required=True)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--parent-branch")
    prepare.add_argument("--owner-evidence", required=True)
    prepare.add_argument(
        "--placement", choices=("workspace", "workspace-continuation")
    )
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--topic", required=True)
    cleanup.add_argument(
        "--placement", choices=("workspace", "workspace-continuation")
    )
    target = cleanup.add_mutually_exclusive_group(required=True)
    target.add_argument("--module")
    target.add_argument("--parent", action="store_true")
    cleanup.add_argument("--expected-clone")
    cleanup.add_argument("--expected-parent")
    cleanup.add_argument("--owner-evidence-sha256")
    cleanup.add_argument(
        "--integrated-commit",
        help="full OID of the PR-integrated commit on origin/main; omitted uses deterministic origin/main discovery",
    )
    cleanup.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.root).absolute()
    try:
        _container_workspace_root(root)
        if args.command == "prepare":
            if args.placement in {"workspace", "workspace-continuation"}:
                _prepare_workspace(
                    root,
                    args.topic,
                    args.module,
                    args.branch,
                    args.owner_evidence,
                    args.parent_branch,
                    placement=args.placement,
                )
            else:
                _prepare(
                    root,
                    args.topic,
                    args.module,
                    args.branch,
                    args.owner_evidence,
                    args.parent_branch,
                )
            return 0
        topic = _slug(args.topic, "topic")
        if args.placement in {"workspace", "workspace-continuation"}:
            if args.command == "status":
                _status_workspace(root, topic, args.placement)
                return 0
            if args.parent:
                raise DependencyModuleChangeError(
                    "--parent is incompatible with --placement workspace"
                )
            if not args.expected_clone:
                raise DependencyModuleChangeError(
                    "--expected-clone is required with --placement workspace"
                )
            modules = _parse_gitmodules(root)
            module = _select_module(modules, args.module)
            _cleanup_workspace(
                root,
                topic,
                module,
                Path(args.expected_clone).absolute(),
                args.apply,
                args.placement,
                args.owner_evidence_sha256,
                args.integrated_commit,
            )
            return 0
        cleanup_command = args.command == "cleanup"
        parent_root = _resolve_topic_parent(
            root,
            args.topic,
            create=False,
            allow_stale_membership=cleanup_command,
        )
        if not parent_root.is_dir():
            raise DependencyModuleChangeError(f"topic parent clone is absent: {parent_root}")
        if cleanup_command:
            parent_inspection = _inspect_cleanup_parent(parent_root, topic)
        else:
            parent_inspection = _inspect(parent_root, role="parent", topic=topic)
        if not cleanup_command and parent_inspection.state != "ready":
            raise DependencyModuleChangeError(
                f"topic parent clone failed identity validation: {parent_root} ({parent_inspection.state})"
            )
        modules = _parse_gitmodules(parent_root)
        if args.command == "status":
            _status(parent_root, modules, topic)
        elif args.parent:
            if not args.expected_parent:
                raise DependencyModuleChangeError("--expected-parent is required with --parent")
            _cleanup_parent(
                parent_root,
                modules,
                topic,
                Path(args.expected_parent).absolute(),
                args.apply,
                args.integrated_commit,
                parent_inspection,
            )
        else:
            if not args.expected_clone:
                raise DependencyModuleChangeError("--expected-clone is required with --module")
            module = _select_module(modules, args.module)
            _cleanup_module(
                parent_root,
                topic,
                module,
                Path(args.expected_clone).absolute(),
                args.apply,
                args.integrated_commit,
                parent_inspection,
            )
        return 0
    except (DependencyModuleChangeError, OSError) as exc:
        print(f"DEPENDENCY_MODULE_CHANGE_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
