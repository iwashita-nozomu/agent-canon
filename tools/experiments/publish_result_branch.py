#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Publishes experiment result artifacts to a dedicated Git branch.
# upstream design ../../agents/workflows/experiment-workflow.md defines experiment execution and result publication flow.
# upstream design ../../documents/result-log-retention-and-visualization.md defines experiment result retention policy.
# upstream implementation run_managed_experiment.py records experiment source branch and commit manifests.
# downstream implementation ../../tests/tools/test_publish_result_branch.py validates result branch publication.
# @dependency-end

"""Publish one managed experiment result directory to a dedicated Git branch."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_REMOTE = "origin"
DEFAULT_SOURCE_BRANCH = "main"
EXPERIMENTS_DIR = "experiments"
REPORT_DIR = "report"
RESULT_DIR = "result"
EXPECTED_RESULT_PATH_PARTS = 4
EXPECTED_REPORT_PATH_PARTS = 3
TOPIC_PATH_INDEX = 1
RESULT_MARKER_PATH_INDEX = 2
RUN_NAME_PATH_INDEX = 3
REPORT_NAME_PATH_INDEX = 2


@dataclass(frozen=True)
class GitCommand:
    """Git command runner scoped to one repository and optional index file."""

    repo_root: Path
    env: Mapping[str, str] = field(default_factory=dict)

    def run(self, args: list[str], *, input_text: str = "") -> str:
        """Run one git command and return stdout."""
        command_env = dict(os.environ)
        command_env.update(self.env)
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            env=command_env,
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            command = "git " + " ".join(args)
            stderr = result.stderr.strip()
            raise RuntimeError(f"{command} failed: {stderr}")
        return result.stdout.strip()

    def maybe_run(self, args: list[str]) -> str:
        """Run one git command and return stdout only when it succeeds."""
        command_env = dict(os.environ)
        command_env.update(self.env)
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            env=command_env,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()


@dataclass(frozen=True)
class ResultDirectoryIdentity:
    """Repository-relative identity parsed from one result directory path."""

    topic: str
    run_name: str
    result_relative_path: Path


@dataclass(frozen=True)
class ResultIdentity:
    """Repository-relative identity parsed from result and report paths."""

    topic: str
    run_name: str
    result_relative_path: Path
    report_relative_path: Path


@dataclass(frozen=True)
class ArtifactPath:
    """One local artifact and the path it has in the result branch."""

    source_path: Path
    relative_path: Path


@dataclass(frozen=True)
class ResultArtifactSet:
    """The bounded artifact set that may be committed to a result branch."""

    identity: ResultIdentity
    artifacts: tuple[ArtifactPath, ...]
    removal_paths: tuple[Path, ...]


@dataclass(frozen=True)
class SourceProvenance:
    """Source branch and commit captured for the experiment run."""

    branch: str
    commit: str


@dataclass(frozen=True)
class PublicationResult:
    """Result branch update metadata."""

    branch: str
    commit: str
    parent: str
    source: SourceProvenance
    artifact_count: int
    pushed: bool


@dataclass(frozen=True)
class PublicationRequest:
    """Validated request for one result branch publication."""

    repo_root: Path
    result_dir: Path
    report_path: Path
    branch: str
    source_branch: str
    remote: str
    push: bool


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current directory.",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        required=True,
        help="Managed result directory: experiments/<topic>/result/<run_name>.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Optional report path. Defaults to experiments/report/<run_name>.md.",
    )
    parser.add_argument(
        "--branch",
        help="Result branch. Defaults to experiment-results/<topic>.",
    )
    parser.add_argument(
        "--source-branch",
        default=DEFAULT_SOURCE_BRANCH,
        help="Required source branch recorded by the run. Defaults to main.",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help="Remote used when --push is set.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the result branch after updating the local branch.",
    )
    return parser.parse_args()


def git_repo_root(path: Path) -> Path:
    """Return the canonical repository root."""
    candidate = path.resolve()
    repo_root = GitCommand(candidate).run(["rev-parse", "--show-toplevel"])
    return Path(repo_root).resolve()


def path_relative_to_repo(repo_root: Path, path: Path) -> Path:
    """Return a repository-relative path, requiring containment in the repo."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"path is outside repository: {path}") from exc


def parse_result_directory_identity(repo_root: Path, result_dir: Path) -> ResultDirectoryIdentity:
    """Parse topic/run identity from a managed result directory."""
    result_relative_path = path_relative_to_repo(repo_root, result_dir)
    parts = result_relative_path.parts
    if (
        len(parts) != EXPECTED_RESULT_PATH_PARTS
        or parts[0] != EXPERIMENTS_DIR
        or parts[RESULT_MARKER_PATH_INDEX] != RESULT_DIR
    ):
        raise ValueError(
            "result-dir must be experiments/<topic>/result/<run_name>: "
            f"{result_relative_path}"
        )
    return ResultDirectoryIdentity(
        topic=parts[TOPIC_PATH_INDEX],
        run_name=parts[RUN_NAME_PATH_INDEX],
        result_relative_path=result_relative_path,
    )


def parse_report_relative_path(repo_root: Path, report_path: Path, run_name: str) -> Path:
    """Parse and validate the report path for one run."""
    report_relative_path = path_relative_to_repo(repo_root, report_path)
    report_parts = report_relative_path.parts
    if (
        len(report_parts) != EXPECTED_REPORT_PATH_PARTS
        or report_parts[:RESULT_MARKER_PATH_INDEX] != (EXPERIMENTS_DIR, REPORT_DIR)
    ):
        raise ValueError(
            "report-path must be experiments/report/<run_name>.md: "
            f"{report_relative_path}"
        )
    expected_report_name = f"{run_name}.md"
    if report_parts[REPORT_NAME_PATH_INDEX] != expected_report_name:
        raise ValueError(
            "report-path must match result run name: "
            f"expected experiments/report/{expected_report_name}, got {report_relative_path}"
        )
    return report_relative_path


def parse_result_identity(
    repo_root: Path, result_dir: Path, report_path: Path
) -> ResultIdentity:
    """Parse topic/run identity from managed result and report paths."""
    result_identity = parse_result_directory_identity(repo_root, result_dir)
    report_relative_path = parse_report_relative_path(
        repo_root,
        report_path,
        result_identity.run_name,
    )
    return ResultIdentity(
        topic=result_identity.topic,
        run_name=result_identity.run_name,
        result_relative_path=result_identity.result_relative_path,
        report_relative_path=report_relative_path,
    )


def load_manifest_git(result_dir: Path) -> dict[str, object]:
    """Load the git section from run_manifest.json when present."""
    manifest_path = result_dir / "run_manifest.json"
    if not manifest_path.exists():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    git_payload = payload.get("git", {})
    if not isinstance(git_payload, dict):
        return {}
    return git_payload


def load_source_provenance(
    git: GitCommand, result_dir: Path, required_source_branch: str
) -> SourceProvenance:
    """Validate and return source branch provenance for one result."""
    current_branch = git.run(["branch", "--show-current"])
    if current_branch != required_source_branch:
        raise ValueError(
            f"current branch is {current_branch!r}; expected {required_source_branch!r}"
        )
    manifest_git = load_manifest_git(result_dir)
    manifest_branch = manifest_git.get("branch")
    if isinstance(manifest_branch, str) and manifest_branch != required_source_branch:
        raise ValueError(
            "run manifest branch is "
            f"{manifest_branch!r}; expected {required_source_branch!r}"
        )
    manifest_commit = manifest_git.get("commit")
    commit = manifest_commit if isinstance(manifest_commit, str) else git.run(["rev-parse", "HEAD"])
    return SourceProvenance(branch=required_source_branch, commit=commit)


def infer_result_branch(identity: ResultIdentity) -> str:
    """Infer the default result branch for one experiment topic."""
    return f"experiment-results/{identity.topic}"


def default_report_path(repo_root: Path, result_dir: Path) -> Path:
    """Return the conventional report path for one managed result directory."""
    identity = parse_result_directory_identity(repo_root, result_dir)
    return repo_root / EXPERIMENTS_DIR / REPORT_DIR / f"{identity.run_name}.md"


def build_publication_request(args: argparse.Namespace) -> PublicationRequest:
    """Build a publication request from parsed CLI args."""
    repo_root = git_repo_root(args.repo_root)
    result_dir = args.result_dir.resolve()
    report_path = (
        args.report_path.resolve()
        if args.report_path
        else default_report_path(repo_root, result_dir)
    )
    return PublicationRequest(
        repo_root=repo_root,
        result_dir=result_dir,
        report_path=report_path,
        branch=args.branch or "",
        source_branch=args.source_branch,
        remote=args.remote,
        push=args.push,
    )


def validate_result_branch(git: GitCommand, branch: str, source_branch: str) -> None:
    """Validate branch naming and source/result branch separation."""
    git.run(["check-ref-format", "--branch", branch])
    if branch == source_branch:
        raise ValueError("result branch must differ from the source branch")


def collect_result_artifacts(
    repo_root: Path, result_dir: Path, identity: ResultIdentity
) -> ResultArtifactSet:
    """Collect the bounded files to publish to the result branch."""
    if not result_dir.is_dir():
        raise ValueError(f"result directory does not exist: {result_dir}")
    artifacts: list[ArtifactPath] = []
    for path in sorted(result_dir.rglob("*")):
        if path.is_file() or path.is_symlink():
            artifacts.append(
                ArtifactPath(
                    source_path=path,
                    relative_path=path_relative_to_repo(repo_root, path),
                )
            )
    report_path = repo_root / identity.report_relative_path
    if report_path.exists():
        artifacts.append(
            ArtifactPath(
                source_path=report_path,
                relative_path=identity.report_relative_path,
            )
        )
    if not artifacts:
        raise ValueError(f"result directory contains no publishable files: {result_dir}")
    return ResultArtifactSet(
        identity=identity,
        artifacts=tuple(artifacts),
        removal_paths=(
            identity.result_relative_path,
            identity.report_relative_path,
        ),
    )


def branch_head(git: GitCommand, branch: str) -> str:
    """Return the current result branch head commit when it exists."""
    return git.maybe_run(["show-ref", "--verify", "--hash", f"refs/heads/{branch}"])


def artifact_mode(path: Path) -> str:
    """Return the Git file mode for one artifact path."""
    if path.is_symlink():
        return "120000"
    mode = path.stat().st_mode
    if mode & stat.S_IXUSR:
        return "100755"
    return "100644"


def git_hash_artifact(git: GitCommand, artifact: ArtifactPath) -> str:
    """Write one artifact blob and return its object id."""
    if artifact.source_path.is_symlink():
        target = os.readlink(artifact.source_path)
        return git.run(["hash-object", "-w", "--stdin"], input_text=target)
    return git.run(["hash-object", "-w", str(artifact.source_path)])


def remove_branch_paths(git: GitCommand, paths: tuple[Path, ...]) -> None:
    """Remove old branch entries for paths that will be replaced."""
    for path in paths:
        existing = git.maybe_run(["ls-files", "-z", "--", path.as_posix()])
        if not existing:
            continue
        for relative_path in existing.split("\0"):
            if relative_path:
                git.run(["update-index", "--force-remove", relative_path])


def build_result_tree(repo_root: Path, parent: str, artifact_set: ResultArtifactSet) -> str:
    """Build a result-branch tree using a temporary Git index."""
    with tempfile.TemporaryDirectory(prefix="agentcanon-result-index-") as temp_dir:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = str(Path(temp_dir) / "index")
        git = GitCommand(repo_root=repo_root, env=env)
        if parent:
            git.run(["read-tree", parent])
        else:
            git.run(["read-tree", "--empty"])
        remove_branch_paths(git, artifact_set.removal_paths)
        for artifact in artifact_set.artifacts:
            blob = git_hash_artifact(git, artifact)
            git.run(
                [
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"{artifact_mode(artifact.source_path)},{blob},{artifact.relative_path.as_posix()}",
                ]
            )
        return git.run(["write-tree"])


def commit_message(
    artifact_set: ResultArtifactSet, source: SourceProvenance, push_requested: bool
) -> str:
    """Return the result branch commit message."""
    push_text = "yes" if push_requested else "no"
    return "\n".join(
        [
            f"Archive experiment result {artifact_set.identity.run_name}",
            "",
            f"Topic: {artifact_set.identity.topic}",
            f"Run-Name: {artifact_set.identity.run_name}",
            f"Source-Branch: {source.branch}",
            f"Source-Commit: {source.commit or '(unknown)'}",
            f"Result-Dir: {artifact_set.identity.result_relative_path.as_posix()}",
            f"Report-Path: {artifact_set.identity.report_relative_path.as_posix()}",
            f"Push-Requested: {push_text}",
            "",
        ]
    )


def git_create_result_commit(
    git: GitCommand,
    parent: str,
    tree: str,
    artifact_set: ResultArtifactSet,
    source: SourceProvenance,
    pushed: bool,
) -> str:
    """Create one result branch commit and return its object id."""
    args = ["commit-tree", tree]
    if parent:
        args.extend(["-p", parent])
    return git.run(args, input_text=commit_message(artifact_set, source, pushed))


def update_result_branch(git: GitCommand, branch: str, parent: str, commit: str) -> None:
    """Move the local result branch ref to the new commit."""
    args = ["update-ref", f"refs/heads/{branch}", commit]
    if parent:
        args.append(parent)
    git.run(args)


def git_publish_result_branch(request: PublicationRequest) -> PublicationResult:
    """Publish result artifacts to a dedicated branch without checkout switching."""
    repo_root = request.repo_root
    result_dir = request.result_dir
    identity = parse_result_identity(repo_root, result_dir, request.report_path)
    result_branch = request.branch or infer_result_branch(identity)
    git = GitCommand(repo_root)
    source = load_source_provenance(git, result_dir, request.source_branch)
    validate_result_branch(git, result_branch, source.branch)
    artifact_set = collect_result_artifacts(repo_root, result_dir, identity)
    parent = branch_head(git, result_branch)
    tree = build_result_tree(repo_root, parent, artifact_set)
    commit = git_create_result_commit(
        git,
        parent,
        tree,
        artifact_set,
        source,
        request.push,
    )
    update_result_branch(git, result_branch, parent, commit)
    if request.push:
        git.run(
            [
                "push",
                request.remote,
                f"refs/heads/{result_branch}:refs/heads/{result_branch}",
            ]
        )
    return PublicationResult(
        branch=result_branch,
        commit=commit,
        parent=parent,
        source=source,
        artifact_count=len(artifact_set.artifacts),
        pushed=request.push,
    )


def print_publication_result(result: PublicationResult) -> None:
    """Print shell-readable publication metadata."""
    print(f"RESULT_BRANCH={result.branch}")
    print(f"RESULT_BRANCH_COMMIT={result.commit}")
    print(f"RESULT_BRANCH_PARENT={result.parent}")
    print(f"SOURCE_BRANCH={result.source.branch}")
    print(f"SOURCE_COMMIT={result.source.commit}")
    print(f"RESULT_ARTIFACT_COUNT={result.artifact_count}")
    print(f"RESULT_BRANCH_PUSHED={'yes' if result.pushed else 'no'}")


def main() -> int:
    """Run the CLI."""
    args = parse_args()
    try:
        result = git_publish_result_branch(build_publication_request(args))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print_publication_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
