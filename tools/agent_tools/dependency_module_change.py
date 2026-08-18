#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Manages one dependency module source clone through generic repository-topic lifecycle primitives.
# upstream design ../../documents/rule/dependency-module-changes.md generic dependency module policy
# upstream design ../../documents/design/dependency-manifest-design.md structured dependency ownership model
# upstream design ../../documents/design/request-intent-and-update-relation.md one-to-one lifecycle adapter and evidence projection
# downstream implementation ../../tests/agent_tools/test_dependency_module_change.py validates dependency identity gate and generic-call behavior
# downstream design ../../documents/tools/dependency_module_change.md documents the CLI surface
# @dependency-end
"""Dependency module lifecycle adapter backed by generic repository-topic clone primitives."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    from . import parent_root_side_effects as _parent_boundary
except ImportError:  # direct CLI execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import parent_root_side_effects as _parent_boundary  # type: ignore[no-redef]

from repository_topic_clone import (
    RepositoryTopicCloneError,
    RepositoryTopicCloneRequest,
    projected_clone_path,
    topic_slug,
)
from repository_topic_clone import (
    cleanup as generic_cleanup,
)
from repository_topic_clone import (
    merge_main as generic_merge_main,
)
from repository_topic_clone import (
    request as generic_request,
)


class DependencyModuleChangeError(RuntimeError):
    """Raised when dependency module lifecycle metadata cannot be projected."""


def _attested_workspace_root(root: Path) -> Path:
    """Resolve the selected parent through the shared side-effect boundary."""
    try:
        return _parent_boundary.attest_parent_root(
            _parent_boundary.ParentRootAttestationRequest(
                cwd=root, explicit_root=root, purpose="dependency-module-change"
            )
        ).parent_root
    except Exception as exc:
        reject = getattr(getattr(exc, "reject", None), "value", "boundary")
        detail = getattr(exc, "detail", str(exc))
        raise DependencyModuleChangeError(
            f"parent-root-attestation:{reject}:{detail}"
        ) from exc


class GitCommandError(DependencyModuleChangeError):
    """Raised when a required Git operation fails."""

    def __init__(self, path: Path, args: Sequence[str], stderr: str) -> None:
        """Capture the full command failure context."""
        super().__init__(
            f"git -C {path} {' '.join(args)}: {stderr.strip() or 'command failed'}"
        )


@dataclass(frozen=True)
class DependencyModule:
    """One structured ``.gitmodules`` entry used by the adapter."""

    path: str
    url: str
    branch: str | None

    @property
    def basename(self) -> str:
        """Return the last path component for workspace projection."""
        return Path(self.path).name


def _run_git(repo: Path, args: Sequence[str]) -> str:
    """Run git and raise DependencyModuleChangeError on failure."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise GitCommandError(repo, args, result.stderr)
    return result.stdout


def _parse_gitmodules(root: Path) -> tuple[DependencyModule, ...]:
    """Parse dependency module metadata from the working .gitmodules."""
    manifest = root / ".gitmodules"
    if not manifest.is_file():
        raise DependencyModuleChangeError(
            f"topic-identity-required: missing .gitmodules at {manifest}"
        )
    result = subprocess.run(
        ["git", "-C", str(root), "config", "--file", str(manifest), "--null", "--list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DependencyModuleChangeError(
            f"topic-identity-required: cannot read {manifest}"
        )
    values: dict[str, dict[str, str]] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        key, sep, value = record.partition("\n")
        if not sep:
            continue
        match = re.fullmatch(r"submodule\.(.+)\.(path|url|branch)", key)
        if match:
            name, field = match.groups()
            values.setdefault(name, {})[field] = value
    modules: list[DependencyModule] = []
    for name, fields in sorted(values.items()):
        path = fields.get("path", "").strip()
        url = fields.get("url", "").strip()
        if not path:
            raise DependencyModuleChangeError(
                f"topic-identity-required: missing path in {manifest}"
            )
        if not url:
            raise DependencyModuleChangeError(
                f"topic-identity-required: missing url in {manifest}"
            )
        if path.startswith("/"):
            raise DependencyModuleChangeError(
                f"topic-identity-required: submodule path must be relative: {path!r}"
            )
        modules.append(DependencyModule(path, url, fields.get("branch")))
    if not modules:
        raise DependencyModuleChangeError(
            f"topic-identity-required: no dependency modules found in {manifest}"
        )
    return tuple(modules)


def _select_module(
    modules: tuple[DependencyModule, ...], path: str
) -> DependencyModule:
    """Find module entry for the requested module path."""
    for module in modules:
        if module.path == path:
            return module
    raise DependencyModuleChangeError(
        f"topic-identity-required: unknown --module {path!r}"
    )


def _normalise_url(value: str) -> str:
    """Strip trailing .git for downstream tooling compatibility."""
    value = value.strip()
    return value[:-4] if value.endswith(".git") else value


def _resolve_module_url(root: Path, value: str) -> str:
    """Resolve module URLs, including relative URLs against parent remote."""
    if not value.startswith(("./", "../")):
        return _normalise_url(value)
    parent_remote = _run_git(root, ["config", "--get", "remote.origin.url"]).strip()
    if not parent_remote:
        raise DependencyModuleChangeError(
            "topic-identity-required: relative module url requires parent remote"
        )
    if "://" in parent_remote:
        return _normalise_url(parent_remote.rsplit("/", 1)[0] + "/" + value)
    # best effort for SCP/absolute paths
    return _normalise_url(str(Path(parent_remote).parent / value))


def _topic_request_from_args(
    root: Path,
    topic: str,
    module_path: str,
    branch: str,
    owner_evidence: Path,
) -> RepositoryTopicCloneRequest:
    root = _attested_workspace_root(root)
    modules = _parse_gitmodules(root)
    module = _select_module(modules, module_path)
    if not module.basename:
        raise DependencyModuleChangeError(
            "topic-identity-required: module path has no basename"
        )
    module_url = _resolve_module_url(root, module.url)
    if module.basename == topic_slug(topic):
        raise DependencyModuleChangeError(
            "topic-identity-required: module basename collides with topic container"
        )
    return RepositoryTopicCloneRequest(
        url=module_url,
        repository=module.basename,
        workspace_root=root,
        topic=topic,
        branch=branch,
        owner_evidence=owner_evidence,
    )


def _prepare(args: argparse.Namespace, *, command: str) -> int:
    """Handle prepare and merge-main by deferring to generic owner implementation."""
    workspace_root = Path(args.root).absolute()
    owner_evidence = workspace_root / args.owner_evidence
    request = _topic_request_from_args(
        workspace_root,
        args.topic,
        args.module,
        args.branch,
        owner_evidence,
    )
    if command == "prepare":
        receipt = generic_request(
            request.url,
            request.repository,
            request.workspace_root,
            request.topic,
            request.branch,
            request.owner_evidence,
        )
        topic_root = receipt.clone.parent
        print(f"TOPIC_ROOT={topic_root}")
        print(f"SOURCE_CLONE={receipt.clone}")
        print(f"SOURCE_BRANCH={receipt.branch}")
    elif command == "merge-main":
        merged = generic_merge_main(request)
        print(f"MERGE_CANDIDATE_SHA={merged.candidate_sha}")
        print(f"MERGE_INTEGRATED_SHA={merged.merged_sha}")
    else:
        raise DependencyModuleChangeError(
            f"topic-identity-required: unknown command {command!r}"
        )
    return 0


def _status(args: argparse.Namespace) -> int:
    """Emit dependency module status for requested topic/module."""
    root = Path(args.root).absolute()
    modules = _parse_gitmodules(root)
    modules_to_report = (
        (_select_module(modules, args.module),) if args.module else modules
    )
    slug = topic_slug(args.topic)
    print("DEPENDENCY_MODULE_CHANGE=status")
    print(f"TOPIC={slug}")
    for module in modules_to_report:
        clone = projected_clone_path(root, slug, module.basename)
        print(f"TOPIC_ROOT={clone.parent}")
        state = "absent" if not clone.exists() else "ready"
        print(f"MODULE={module.path} STATE={state} CLONE={clone}")
    return 0


def _cleanup(args: argparse.Namespace) -> int:
    """Handle cleanup by delegating to generic cleanup."""
    workspace_root = Path(args.root).absolute()
    owner_evidence = workspace_root / args.owner_evidence
    request = _topic_request_from_args(
        workspace_root,
        args.topic,
        args.module,
        args.branch,
        owner_evidence,
    )
    result = generic_cleanup(
        request,
        candidate_cas=args.candidate_cas,
        pr_lifecycle=args.pr_lifecycle,
        publication_readback=args.publication_readback,
        apply=args.apply,
    )
    action = "removed" if result.removed else "would-remove"
    print(
        f"CLEANUP module={args.module} topic={topic_slug(args.topic)} action={action} path={result.clone}"
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Selected repository root.")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--topic", required=True)
    prepare.add_argument("--module", required=True)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--owner-evidence", required=True)

    merge = commands.add_parser("merge-main")
    merge.add_argument("--topic", required=True)
    merge.add_argument("--module", required=True)
    merge.add_argument("--branch", required=True)
    merge.add_argument("--owner-evidence", required=True)

    status = commands.add_parser("status")
    status.add_argument("--topic", required=True)
    status.add_argument("--module")

    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--topic", required=True)
    cleanup.add_argument("--module", required=True)
    cleanup.add_argument("--branch", required=True)
    cleanup.add_argument("--owner-evidence", required=True)
    cleanup.add_argument("--candidate-cas")
    cleanup.add_argument("--pr-lifecycle")
    cleanup.add_argument("--publication-readback")
    cleanup.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run adapter CLI commands."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            return _prepare(args, command="prepare")
        if args.command == "merge-main":
            return _prepare(args, command="merge-main")
        if args.command == "status":
            return _status(args)
        if args.command == "cleanup":
            return _cleanup(args)
        raise DependencyModuleChangeError(
            f"topic-identity-required: unknown command {args.command!r}"
        )
    except DependencyModuleChangeError as exc:
        print(f"DEPENDENCY_MODULE_CHANGE_ERROR={exc}", file=sys.stderr)
        return 2
    except RepositoryTopicCloneError as exc:
        print(f"REPOSITORY_TOPIC_CLONE_ERROR={exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"DEPENDENCY_MODULE_CHANGE_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
