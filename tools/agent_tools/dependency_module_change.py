#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Manages topic source clones and reconstructibility-gated cleanup while retaining topic-root container visibility.
# upstream design ../../documents/rule/dependency-module-changes.md generic dependency module policy
# upstream design ../../documents/design/dependency-manifest-design.md structured dependency ownership model
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
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


CONTAINER_WORKSPACE_ROOT = Path("/workspace")
MARKER_PREFIX = "agent-canon.topic"


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


def _topic_workspace(root: Path, topic: str, *, create: bool) -> Path:
    expected_name = _topic_name(topic)
    if os.environ.get("AGENT_CANON_WORKSPACE_ROOT", "") == str(CONTAINER_WORKSPACE_ROOT):
        if root.parent != CONTAINER_WORKSPACE_ROOT:
            raise DependencyModuleChangeError(
                "container topic workspace must expose the selected repository directly below /workspace"
            )
        return CONTAINER_WORKSPACE_ROOT
    if root.parent.parent.name == "workspace":
        if root.parent.name != expected_name:
            raise DependencyModuleChangeError(
                f"selected repository is already in workspace/{root.parent.name}, not workspace/{expected_name}"
            )
        return root.parent
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
    return candidate


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
    if _actual_branch(path) == branch:
        return
    if _remote_branch_exists(remote, branch):
        _run_git(path, ["checkout", "--track", "-b", branch, f"origin/{branch}"])
        return
    _run_git(path, ["checkout", "-b", branch])


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


def _inspect(path: Path, *, role: str, module: DependencyModule | None = None, topic: str = "", branch: str | None = None) -> CloneInspection:
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
    if marker_role != role or marker_topic != topic:
        return CloneInspection(path, "membership-mismatch", marker_role, marker_module, remote, marker_branch, actual)
    if role == "module" and module is not None:
        if marker_module != module.path or marker_url != _normalise_url(module.url):
            return CloneInspection(path, "identity-mismatch", marker_role, marker_module, remote, marker_branch, actual)
        if _normalise_url(remote) != _normalise_url(module.url):
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


def _set_marker(path: Path, *, topic: str, role: str, module: str, url: str, branch: str) -> None:
    values = {"topic": topic, "role": role, "module": module, "url": _normalise_url(url), "branch": branch}
    for field, value in values.items():
        _run_git(path, ["config", "--local", f"{MARKER_PREFIX}.{field}", value])


def _require_evidence(root: Path, value: str) -> Path:
    evidence = Path(value)
    if not evidence.is_absolute():
        evidence = root / evidence
    if not evidence.is_file() or evidence.stat().st_size == 0:
        raise DependencyModuleChangeError(f"owner evidence must be a non-empty file: {evidence}")
    return evidence


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


def _resolve_topic_parent(root: Path, topic: str, *, create: bool) -> Path:
    """Resolve the parent clone even when --root points at a module clone."""
    topic_slug = _slug(topic, "topic")
    topic_root = _topic_workspace(root, topic, create=create)
    if root.parent == topic_root:
        selected = _inspect(root, role="parent", topic=topic_slug)
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
    parent_path = topic_root / root.name
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
    topic_slug = _slug(topic, "topic")
    topic_root = parent_root.parent
    if module.basename == parent_root.name:
        raise DependencyModuleChangeError("module basename collides with topic parent clone name")
    clone_path = topic_root / module.basename
    inspection = _inspect(clone_path, role="module", module=module, topic=topic_slug, branch=branch)
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
        module.url,
        clone_path,
        base_branch=module.branch,
        task_branch=branch,
    )
    _set_marker(path=clone_path, topic=topic_slug, role="module", module=module.path, url=module.url, branch=branch)
    final = _inspect(clone_path, role="module", module=module, topic=topic_slug, branch=branch)
    if final.state != "ready":
        raise DependencyModuleChangeError(f"new dependency clone failed identity validation: {final.state}")
    print(f"PARENT_ROOT={parent_root}")
    print(f"SOURCE_CLONE={clone_path}")
    print(f"CONTINUE_PATH={clone_path}")


def _module_path_states(
    parent_root: Path, modules: tuple[DependencyModule, ...], topic: str
) -> tuple[CloneInspection, ...]:
    """Return every present expected module path, including invalid clones."""
    states: list[CloneInspection] = []
    for module in modules:
        candidate = parent_root.parent / module.basename
        inspection = _inspect(candidate, role="module", module=module, topic=topic)
        if inspection.state != "absent":
            states.append(inspection)
    return tuple(states)


def _cleanup_readiness(path: Path) -> str | None:
    try:
        _run_git(path, ["fetch", "--all", "--prune"])
    except GitCommandError as exc:
        return f"fetch-failed:{exc}"
    if _run_git(path, ["status", "--porcelain=v1", "--untracked-files=all"]).strip():
        return "dirty-worktree-index-or-untracked"
    if sum(line.startswith("worktree ") for line in _run_git(path, ["worktree", "list", "--porcelain"]).splitlines()) > 1:
        return "linked-worktree-present"
    if _run_git(path, ["rev-list", "--all", "--not", "--remotes"]).strip():
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


def _cleanup_module(parent_root: Path, topic: str, module: DependencyModule, expected: Path, apply: bool) -> None:
    clone = parent_root.parent / module.basename
    if not expected.is_absolute() or expected != clone:
        raise DependencyModuleChangeError(f"--expected-clone must exactly equal {clone}")
    inspection = _inspect(clone, role="module", module=module, topic=topic)
    if inspection.state == "absent":
        print(f"CLEANUP module={module.path} action=hold reason=absent")
        return
    if inspection.state != "ready":
        print(f"CLEANUP module={module.path} action=hold reason={inspection.state}")
        return
    reason = _cleanup_readiness(clone)
    if reason:
        print(f"CLEANUP module={module.path} action=hold reason={reason}")
        return
    if not apply:
        print(f"CLEANUP module={module.path} action=would-remove path={clone}")
        return
    _require_cleanup_authority()
    shutil.rmtree(clone)
    print(f"CLEANUP module={module.path} action=removed path={clone}")


def _cleanup_parent(parent_root: Path, modules: tuple[DependencyModule, ...], topic: str, expected: Path, apply: bool) -> None:
    if not expected.is_absolute() or expected != parent_root:
        raise DependencyModuleChangeError(f"--expected-parent must exactly equal {parent_root}")
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
    inspection = _inspect(parent_root, role="parent", topic=topic)
    if inspection.state != "ready":
        print(f"CLEANUP parent action=hold reason={inspection.state}")
        return
    reason = _cleanup_readiness(parent_root)
    if reason:
        print(f"CLEANUP parent action=hold reason={reason}")
        return
    if not apply:
        print(f"CLEANUP parent action=would-remove path={parent_root}")
        return
    _require_cleanup_authority()
    topic_root = parent_root.parent
    shutil.rmtree(parent_root)
    print(f"CLEANUP parent action=removed path={parent_root}")
    if topic_root.exists() and not any(topic_root.iterdir()):
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Selected repository root.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--topic", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--topic", required=True)
    prepare.add_argument("--module", required=True)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--parent-branch")
    prepare.add_argument("--owner-evidence", required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--topic", required=True)
    target = cleanup.add_mutually_exclusive_group(required=True)
    target.add_argument("--module")
    target.add_argument("--parent", action="store_true")
    cleanup.add_argument("--expected-clone")
    cleanup.add_argument("--expected-parent")
    cleanup.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.root).absolute()
    try:
        _container_workspace_root(root)
        if args.command == "prepare":
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
        parent_root = _resolve_topic_parent(root, args.topic, create=False)
        if not parent_root.is_dir():
            raise DependencyModuleChangeError(f"topic parent clone is absent: {parent_root}")
        parent_inspection = _inspect(parent_root, role="parent", topic=topic)
        if parent_inspection.state != "ready":
            raise DependencyModuleChangeError(
                f"topic parent clone failed identity validation: {parent_root} ({parent_inspection.state})"
            )
        modules = _parse_gitmodules(parent_root)
        if args.command == "status":
            _status(parent_root, modules, topic)
        elif args.parent:
            if not args.expected_parent:
                raise DependencyModuleChangeError("--expected-parent is required with --parent")
            _cleanup_parent(parent_root, modules, topic, Path(args.expected_parent).absolute(), args.apply)
        else:
            if not args.expected_clone:
                raise DependencyModuleChangeError("--expected-clone is required with --module")
            module = _select_module(modules, args.module)
            _cleanup_module(parent_root, topic, module, Path(args.expected_clone).absolute(), args.apply)
        return 0
    except (DependencyModuleChangeError, OSError) as exc:
        print(f"DEPENDENCY_MODULE_CHANGE_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
