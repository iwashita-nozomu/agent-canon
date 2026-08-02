#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Selects and evaluates parent PR graph gating from canonical owners, a validated diff base, and persisted graph reachability.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json canonical validation profile owner
# upstream design ../../documents/design/dependency-manifest-design.md canonical dependency surface owner and parent gate contract
# downstream implementation ./check_agent_canon_pr.sh consumes the typed selector verdict
# downstream implementation ../../tests/tools/test_agent_canon_pr_graph_selector.py verifies required, skipped, and fail-closed selections
# @dependency-end
"""Select and evaluate parent AgentCanon PR dependency graph acceptance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import posixpath
import re
import sqlite3
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import quote

PROFILE_INVENTORY = Path("documents/runtime/runtime-profiles-and-check-matrix.json")
DEPENDENCY_SURFACE_OWNER = Path("documents/design/dependency-manifest-design.md")
EXIT_REQUIRED = 0
EXIT_FAILURE = 2
EXIT_SKIPPED = 10
MANIFEST_CHANGE_RE = re.compile(
    r"^[+-](?![+-])(?:.*@dependency-(?:start|end)|"
    r"[\t #*/-]*(?:contract|responsibility|upstream|downstream)\s)",
    re.MULTILINE,
)
HEX_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
FULL_HISTORY_DEEPEN = "2147483647"


class SelectorFailure(RuntimeError):
    """One typed selector failure."""

    def __init__(self, reason: str, evidence: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


@dataclass(frozen=True)
class DiffEvidence:
    """Validated base and exact PR diff evidence."""

    base_sha: str
    base_source: str
    head_sha: str
    changed_paths: tuple[str, ...]
    patch: str


@dataclass(frozen=True)
class ProfileEvidence:
    """Validated canonical profile selection."""

    selected: tuple[str, ...]
    graph_required: tuple[str, ...]


@dataclass(frozen=True)
class Selection:
    """One strict-graph gate selection."""

    status: str
    reason: str
    evidence: str


@dataclass(frozen=True)
class PreparedBase:
    """One trusted CI base preparation result."""

    base_sha: str
    base_source: str
    fetched: bool


@dataclass(frozen=True)
class GraphAcceptance:
    """Changed-responsibility acceptance for one incomplete parent graph."""

    status: str
    reason: str
    evidence: str
    report: Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Create the selector CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Parent repository root.")
    parser.add_argument(
        "--source-root",
        required=True,
        help="AgentCanon source root containing canonical owner manifests.",
    )
    parser.add_argument(
        "--prepare-ci-base",
        action="store_true",
        help="Fetch the trusted GitHub PR base into a shallow checkout.",
    )
    parser.add_argument(
        "--trusted-base-sha",
        help="Trusted base SHA prepared by the GitHub PR entrypoint.",
    )
    parser.add_argument(
        "--evaluate-built-graph",
        action="store_true",
        help="Classify an incomplete built graph against the validated PR diff.",
    )
    parser.add_argument(
        "--graph-result",
        help="JSON result emitted by the incomplete graph build.",
    )
    parser.add_argument(
        "--report-out",
        help="Write changed-responsibility and baseline diagnostics as JSON.",
    )
    return parser


def emit(status: str, reason: str, evidence: str) -> None:
    """Emit one line-safe typed verdict."""
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH={status}")
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH_REASON={reason}")
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH_EVIDENCE={evidence}")


def emit_base(status: str, reason: str, evidence: str, base_sha: str = "") -> None:
    """Emit one line-safe trusted-base preparation result."""
    print(f"AGENT_CANON_PR_BASE_FETCH={status}")
    print(f"AGENT_CANON_PR_BASE_FETCH_REASON={reason}")
    print(f"AGENT_CANON_PR_BASE_FETCH_EVIDENCE={evidence}")
    if base_sha:
        print(f"AGENT_CANON_PR_TRUSTED_BASE_SHA={base_sha}")


def emit_acceptance(status: str, reason: str, evidence: str) -> None:
    """Emit one line-safe changed-responsibility graph verdict."""
    print(f"AGENT_CANON_PR_GRAPH_ACCEPTANCE={status}")
    print(f"AGENT_CANON_PR_GRAPH_ACCEPTANCE_REASON={reason}")
    print(f"AGENT_CANON_PR_GRAPH_ACCEPTANCE_EVIDENCE={evidence}")


def run_git(
    root: Path,
    args: Sequence[str],
    extra_environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one selector or explicit trusted-base preparation Git command."""
    environment = os.environ.copy()
    if extra_environment is not None:
        environment.update(extra_environment)
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def git_output(
    root: Path,
    args: Sequence[str],
    failure_reason: str,
    extra_environment: Mapping[str, str] | None = None,
) -> str:
    """Return Git stdout or raise one typed failure."""
    result = run_git(root, args, extra_environment)
    if result.returncode != 0:
        command = args[0] if args else "unknown"
        stderr = result.stderr.strip().replace("\n", " ")
        evidence = f"command=git_{command};exit={result.returncode}"
        if stderr:
            evidence += f";stderr_sha256={hashlib.sha256(stderr.encode()).hexdigest()}"
        raise SelectorFailure(failure_reason, evidence)
    return result.stdout


def github_event_base(environment: Mapping[str, str]) -> tuple[str, str]:
    """Resolve the trusted base SHA from one GitHub pull request event."""
    override = environment.get("AGENT_CANON_PR_BASE_REF", "").strip()
    if override:
        raise SelectorFailure(
            "ci_base_override_forbidden",
            "source=AGENT_CANON_PR_BASE_REF",
        )
    if environment.get("GITHUB_ACTIONS", "").lower() != "true":
        raise SelectorFailure(
            "trusted_pr_base_unavailable",
            "source=GITHUB_ACTIONS",
        )
    if environment.get("GITHUB_EVENT_NAME") not in {
        "pull_request",
        "pull_request_target",
    }:
        raise SelectorFailure(
            "trusted_pr_base_unavailable",
            "source=GITHUB_EVENT_NAME",
        )
    event_path = environment.get("GITHUB_EVENT_PATH", "").strip()
    if not event_path:
        raise SelectorFailure(
            "trusted_pr_base_unavailable",
            "source=GITHUB_EVENT_PATH",
        )
    try:
        payload: object = json.loads(Path(event_path).read_text(encoding="utf-8"))
        pull_request = cast(dict[str, object], payload)["pull_request"]
        base = cast(dict[str, object], pull_request)["base"]
        base_sha = cast(dict[str, object], base)["sha"]
    except (OSError, ValueError, KeyError, TypeError):
        raise SelectorFailure(
            "trusted_pr_base_invalid",
            f"event_path_sha256={hashlib.sha256(event_path.encode()).hexdigest()}",
        ) from None
    if not isinstance(base_sha, str) or not HEX_SHA_RE.fullmatch(base_sha):
        raise SelectorFailure(
            "trusted_pr_base_invalid",
            "field=pull_request.base.sha",
        )
    return base_sha.lower(), "github_event_pull_request_base_sha"


def trusted_base_ref(
    environment: Mapping[str, str],
    trusted_base_sha: str | None = None,
) -> tuple[str, str]:
    """Resolve a prepared CI base or an explicit validated local/test override."""
    github_actions = environment.get("GITHUB_ACTIONS", "").lower() == "true"
    if github_actions:
        event_base, source = github_event_base(environment)
        prepared = (trusted_base_sha or "").strip()
        if not HEX_SHA_RE.fullmatch(prepared):
            raise SelectorFailure(
                "trusted_pr_base_argument_invalid",
                "argument=trusted_base_sha",
            )
        if prepared.lower() != event_base:
            raise SelectorFailure(
                "trusted_pr_base_argument_mismatch",
                f"source={source}",
            )
        return event_base, source

    if trusted_base_sha is not None:
        raise SelectorFailure(
            "local_trusted_base_argument_forbidden",
            "argument=trusted_base_sha",
        )
    override = environment.get("AGENT_CANON_PR_BASE_REF", "").strip()

    if not override:
        raise SelectorFailure(
            "local_base_override_required",
            "source=AGENT_CANON_PR_BASE_REF",
        )
    if (
        override.startswith("-")
        or any(character.isspace() for character in override)
        or "\x00" in override
    ):
        raise SelectorFailure(
            "local_base_override_invalid",
            "source=AGENT_CANON_PR_BASE_REF",
        )
    return override, "explicit_local_base_override"


def base_history_ready(root: Path, base_sha: str, head_sha: str) -> bool:
    """Return whether the exact base object and common history are available."""
    resolved = run_git(
        root,
        ["rev-parse", "--verify", "--end-of-options", f"{base_sha}^{{commit}}"],
    )
    if resolved.returncode != 0:
        return False
    if resolved.stdout.strip().lower() != base_sha:
        raise SelectorFailure(
            "pr_base_object_identity_mismatch",
            "source=existing_object",
        )
    merge_base = run_git(root, ["merge-base", base_sha, head_sha])
    return merge_base.returncode == 0 and bool(merge_base.stdout.strip())


def github_fetch_environment(read_token: str) -> dict[str, str]:
    """Return process-local Git configuration for one authenticated fetch."""
    basic = base64.b64encode(f"x-access-token:{read_token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    }


def prepare_ci_base(root: Path, environment: Mapping[str, str]) -> PreparedBase:
    """Prepare the trusted PR base and connected history when they are absent."""
    base_sha, source = github_event_base(environment)
    head_sha = git_output(root, ["rev-parse", "HEAD"], "pr_head_unresolved").strip()
    if base_sha == head_sha:
        raise SelectorFailure(
            "pr_base_equals_head",
            f"base={base_sha};source={source}",
        )
    if base_history_ready(root, base_sha, head_sha):
        return PreparedBase(base_sha, source, False)

    read_token = environment.get("AGENT_CANON_PR_READ_TOKEN", "").strip()
    if not read_token:
        raise SelectorFailure(
            "pr_base_read_credential_missing",
            "source=AGENT_CANON_PR_READ_TOKEN",
        )
    shallow = git_output(
        root,
        ["rev-parse", "--is-shallow-repository"],
        "pr_checkout_depth_unresolved",
    ).strip()
    if shallow not in {"true", "false"}:
        raise SelectorFailure(
            "pr_checkout_depth_invalid",
            f"value_sha256={hashlib.sha256(shallow.encode()).hexdigest()}",
        )
    fetch_args = ["fetch", "--no-tags", "--no-recurse-submodules"]
    if shallow == "true":
        fetch_args.extend(("--deepen", FULL_HISTORY_DEEPEN))
    fetch_args.extend(("origin", base_sha))
    git_output(
        root,
        fetch_args,
        "pr_base_fetch_failed",
        github_fetch_environment(read_token),
    )
    resolved = git_output(
        root,
        ["rev-parse", "--verify", "--end-of-options", f"{base_sha}^{{commit}}"],
        "pr_base_unresolved",
    ).strip()
    if resolved.lower() != base_sha:
        raise SelectorFailure(
            "pr_base_fetch_identity_mismatch",
            f"source={source}",
        )
    git_output(
        root,
        ["merge-base", base_sha, head_sha],
        "pr_base_unreachable_from_head",
    )
    return PreparedBase(base_sha, source, True)


def load_diff(
    root: Path,
    environment: Mapping[str, str],
    trusted_base_sha: str | None = None,
) -> DiffEvidence:
    """Validate the selected base and load exact changed-path and patch evidence."""
    base_ref, base_source = trusted_base_ref(environment, trusted_base_sha)
    base_sha = git_output(
        root,
        ["rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}"],
        "pr_base_unresolved",
    ).strip()
    head_sha = git_output(root, ["rev-parse", "HEAD"], "pr_head_unresolved").strip()
    if base_sha == head_sha:
        raise SelectorFailure(
            "pr_base_equals_head",
            f"base={base_sha};source={base_source}",
        )
    git_output(
        root,
        ["merge-base", base_sha, head_sha],
        "pr_base_unreachable_from_head",
    )
    changed_text = git_output(
        root,
        ["diff", "--name-only", f"{base_sha}...{head_sha}", "--"],
        "pr_changed_paths_diff_failed",
    )
    patch = git_output(
        root,
        [
            "diff",
            "--unified=0",
            "--no-ext-diff",
            f"{base_sha}...{head_sha}",
            "--",
            ".",
            ":(exclude)vendor/agent-canon",
        ],
        "pr_manifest_diff_failed",
    )
    changed_paths = tuple(line for line in changed_text.splitlines() if line)
    return DiffEvidence(base_sha, base_source, head_sha, changed_paths, patch)


def normalize_manifest_line(raw_line: str) -> str:
    """Normalize one dependency header line without interpreting its target."""
    line = raw_line.strip()
    for prefix in ("<!--", "#", "//", "*"):
        if line.startswith(prefix):
            line = line[len(prefix) :].strip()
    if line.endswith("-->"):
        line = line[:-3].strip()
    return line


def dependency_surface_paths(source_root: Path) -> frozenset[str]:
    """Read dependency-gate surfaces from the canonical design owner's manifest."""
    owner = source_root / DEPENDENCY_SURFACE_OWNER
    try:
        lines = owner.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SelectorFailure(
            "dependency_surface_owner_unavailable",
            f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};error={type(error).__name__}",
        ) from None

    in_manifest = False
    found_manifest = False
    found_end = False
    surfaces = {DEPENDENCY_SURFACE_OWNER.as_posix()}
    for raw_line in lines:
        line = normalize_manifest_line(raw_line)
        if line == "@dependency-start":
            if in_manifest or found_manifest:
                raise SelectorFailure(
                    "dependency_surface_manifest_invalid",
                    f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};detail=duplicate_start",
                )
            in_manifest = True
            found_manifest = True
            continue
        if line == "@dependency-end":
            if not in_manifest:
                raise SelectorFailure(
                    "dependency_surface_manifest_invalid",
                    f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};detail=unmatched_end",
                )
            found_end = True
            break
        if not in_manifest or not line.startswith("downstream "):
            continue
        fields = line.split(maxsplit=3)
        if len(fields) != 4:
            raise SelectorFailure(
                "dependency_surface_manifest_invalid",
                f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};detail=downstream_shape",
            )
        target = fields[2]
        resolved = (owner.parent / target).resolve()
        try:
            relative = resolved.relative_to(source_root.resolve()).as_posix()
        except ValueError:
            raise SelectorFailure(
                "dependency_surface_manifest_invalid",
                f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};detail=target_escape",
            ) from None
        if not resolved.exists():
            raise SelectorFailure(
                "dependency_surface_manifest_invalid",
                f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};missing={relative}",
            )
        surfaces.add(relative)

    if not found_manifest or not found_end:
        raise SelectorFailure(
            "dependency_surface_manifest_invalid",
            f"owner={DEPENDENCY_SURFACE_OWNER.as_posix()};detail=markers",
        )
    return frozenset(surfaces)


def load_profiles(source_root: Path, environment: Mapping[str, str]) -> ProfileEvidence:
    """Validate selected profile IDs against the canonical runtime inventory."""
    singular = environment.get("AGENT_CANON_PR_VALIDATION_PROFILE", "").strip()
    plural = environment.get("AGENT_CANON_PR_VALIDATION_PROFILES", "").strip()
    if singular and plural:
        raise SelectorFailure(
            "validation_profile_selection_ambiguous",
            "fields=AGENT_CANON_PR_VALIDATION_PROFILE,AGENT_CANON_PR_VALIDATION_PROFILES",
        )
    if singular and "," in singular:
        raise SelectorFailure(
            "validation_profile_selection_invalid",
            "field=AGENT_CANON_PR_VALIDATION_PROFILE",
        )
    raw_profiles = plural or singular
    selected = tuple(item.strip() for item in raw_profiles.split(",") if item.strip())
    if raw_profiles and (not selected or len(selected) != len(raw_profiles.split(","))):
        raise SelectorFailure(
            "validation_profile_selection_invalid",
            "detail=empty_profile_id",
        )
    if len(set(selected)) != len(selected):
        raise SelectorFailure(
            "validation_profile_selection_invalid",
            "detail=duplicate_profile_id",
        )

    inventory_path = source_root / PROFILE_INVENTORY
    try:
        payload: object = json.loads(inventory_path.read_text(encoding="utf-8"))
        profile_classes = cast(dict[str, object], payload)["profile_classes"]
    except (OSError, ValueError, KeyError, TypeError):
        raise SelectorFailure(
            "validation_profile_inventory_invalid",
            f"inventory={PROFILE_INVENTORY.as_posix()}",
        ) from None
    if not isinstance(profile_classes, list):
        raise SelectorFailure(
            "validation_profile_inventory_invalid",
            "field=profile_classes",
        )

    requirements: dict[str, bool] = {}
    for raw_profile in cast(list[object], profile_classes):
        if not isinstance(raw_profile, dict):
            raise SelectorFailure(
                "validation_profile_inventory_invalid",
                "field=profile_classes.entry",
            )
        profile = cast(dict[str, object], raw_profile)
        profile_id = profile.get("id")
        graph_required = profile.get("strict_dependency_graph_required")
        if (
            not isinstance(profile_id, str)
            or not profile_id
            or not isinstance(graph_required, bool)
            or profile_id in requirements
        ):
            raise SelectorFailure(
                "validation_profile_inventory_invalid",
                "fields=profile_classes.id,profile_classes.strict_dependency_graph_required",
            )
        requirements[profile_id] = graph_required

    unknown = tuple(profile for profile in selected if profile not in requirements)
    if unknown:
        raise SelectorFailure(
            "unknown_validation_profile",
            f"profiles={','.join(unknown)};inventory={PROFILE_INVENTORY.as_posix()}",
        )
    required = tuple(profile for profile in selected if requirements[profile])
    return ProfileEvidence(selected, required)


def migration_requested(environment: Mapping[str, str]) -> bool:
    """Validate and return the explicit parent graph migration declaration."""
    raw = environment.get("AGENT_CANON_PR_PARENT_GRAPH_MIGRATION", "").strip().lower()
    if raw in {"", "0", "false", "no"}:
        return False
    if raw in {"1", "true", "yes"}:
        return True
    raise SelectorFailure(
        "parent_graph_migration_value_invalid",
        "field=AGENT_CANON_PR_PARENT_GRAPH_MIGRATION",
    )


def changed_paths_digest(paths: Sequence[str]) -> str:
    """Return a stable digest for exact changed-path evidence."""
    payload = "\0".join(paths).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(payload).hexdigest()


def path_is_changed(path: str, changed_paths: Sequence[str]) -> bool:
    """Return whether an exact changed path owns the graph path."""
    return any(
        path == changed or path.startswith(f"{changed.rstrip('/')}/")
        for changed in changed_paths
    )


def diagnostic_source_path(
    target_node_id: str,
    message: str,
    node_paths: Mapping[str, str],
) -> str:
    """Resolve the declaring source path for one persisted graph diagnostic."""
    if target_node_id in node_paths:
        return node_paths[target_node_id]
    return message.partition(":")[0]


def diagnostic_target_path(source_path: str, code: str, message: str) -> str:
    """Resolve a target diagnostic's declared path without touching the filesystem."""
    if not code.startswith("target-"):
        return ""
    fields = message.split(":", 2)
    if len(fields) != 3 or not source_path or fields[0] != source_path:
        return ""
    declared = fields[2]
    if declared.startswith("/"):
        return ""
    normalized = posixpath.normpath(
        posixpath.join(posixpath.dirname(source_path), declared)
    )
    if normalized == ".." or normalized.startswith("../"):
        return ""
    return normalized


def graph_database_path(root: Path, graph_result_path: Path) -> Path:
    """Validate the graph result and return its canonical persisted database."""
    try:
        payload: object = json.loads(graph_result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SelectorFailure(
            "graph_build_result_invalid",
            f"path={graph_result_path}",
        ) from None
    if not isinstance(payload, dict):
        raise SelectorFailure("graph_build_result_invalid", "detail=not_object")
    result = cast(dict[str, object], payload)
    if (
        result.get("schema") != "agent-canon.graph.build.v1"
        or result.get("status") != "incomplete"
        or result.get("exit_code") != 1
    ):
        raise SelectorFailure(
            "graph_build_result_invalid",
            "detail=expected_incomplete_build",
        )
    expected = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
    raw_db_path = result.get("db_path")
    if not isinstance(raw_db_path, str) or not raw_db_path:
        raise SelectorFailure("graph_build_result_invalid", "detail=db_path_missing")
    candidate = Path(raw_db_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate_stat = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError:
        raise SelectorFailure(
            "graph_database_unavailable",
            f"path={expected}",
        ) from None
    if (
        resolved != expected_resolved
        or stat.S_ISLNK(candidate_stat.st_mode)
        or not stat.S_ISREG(candidate_stat.st_mode)
    ):
        raise SelectorFailure(
            "graph_database_identity_invalid",
            f"path={candidate}",
        )
    return resolved


def read_graph_acceptance_facts(
    database: Path,
) -> tuple[dict[str, str], dict[str, set[str]], list[dict[str, str]]]:
    """Read path, reachability, and diagnostic facts from one immutable graph."""
    uri = f"file:{quote(database.as_posix(), safe='/')}?mode=ro&immutable=1"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        node_paths: dict[str, str] = {}
        node_rows = cast(
            list[tuple[str, str]],
            connection.execute(
                "SELECT id, payload_json FROM nodes WHERE layer='source'"
            ).fetchall(),
        )
        for node_id, payload_json in node_rows:
            raw_payload: object = json.loads(payload_json)
            if not isinstance(raw_payload, dict):
                continue
            payload = cast(dict[str, object], raw_payload)
            path = payload.get("path")
            if isinstance(path, str):
                node_paths[node_id] = path
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_paths}
        edge_rows = cast(
            list[tuple[str, str]],
            connection.execute(
                "SELECT from_node_id, to_node_id FROM edges WHERE layer='source'"
            ).fetchall(),
        )
        for from_node, to_node in edge_rows:
            if from_node in adjacency and to_node in adjacency:
                adjacency[from_node].add(to_node)
                adjacency[to_node].add(from_node)
        diagnostics: list[dict[str, str]] = []
        diagnostic_rows = cast(
            list[tuple[str, str, str]],
            connection.execute(
                "SELECT rule, message, target_node_id FROM diagnostics WHERE layer='source'"
            ).fetchall(),
        )
        for rule, message, target_node_id in diagnostic_rows:
            source_path = diagnostic_source_path(
                target_node_id,
                message,
                node_paths,
            )
            diagnostics.append(
                {
                    "code": rule,
                    "message": message,
                    "source_path": source_path,
                    "target_path": diagnostic_target_path(
                        source_path,
                        rule,
                        message,
                    ),
                }
            )
    except (json.JSONDecodeError, sqlite3.Error):
        raise SelectorFailure(
            "graph_database_invalid",
            f"path={database}",
        ) from None
    finally:
        if connection is not None:
            connection.close()
    return node_paths, adjacency, diagnostics


def graph_reachable_paths(
    node_paths: Mapping[str, str],
    adjacency: Mapping[str, set[str]],
    changed_paths: Sequence[str],
    full_scope: bool,
) -> frozenset[str]:
    """Return the dependency/surface closure owned by the changed responsibility."""
    if full_scope:
        return frozenset(node_paths.values())
    pending = [
        node_id
        for node_id, path in node_paths.items()
        if path_is_changed(path, changed_paths)
    ]
    visited = set(pending)
    while pending:
        node_id = pending.pop()
        for adjacent in adjacency.get(node_id, set()):
            if adjacent not in visited:
                visited.add(adjacent)
                pending.append(adjacent)
    return frozenset(node_paths[node_id] for node_id in visited)


def base_source_is_unchanged(
    root: Path,
    diff: DiffEvidence,
    source_path: str,
) -> bool:
    """Confirm that a non-reachable diagnostic source is represented by the base."""
    if not source_path or path_is_changed(source_path, diff.changed_paths):
        return False
    direct = run_git(
        root,
        ["cat-file", "-e", f"{diff.base_sha}:{source_path}"],
    )
    if direct.returncode == 0:
        return True
    parts = source_path.split("/")
    for index in range(1, len(parts)):
        ancestor = "/".join(parts[:index])
        base_tree = run_git(root, ["ls-tree", diff.base_sha, "--", ancestor])
        head_tree = run_git(root, ["ls-tree", diff.head_sha, "--", ancestor])
        if (
            base_tree.returncode == 0
            and base_tree.stdout.startswith("160000 ")
            and base_tree.stdout == head_tree.stdout
        ):
            return True
    return False


def evaluate_built_graph(
    root: Path,
    graph_result_path: Path,
    environment: Mapping[str, str],
    trusted_base_sha: str | None = None,
) -> GraphAcceptance:
    """Gate only diagnostics reached from the exact changed responsibility."""
    diff = load_diff(root, environment, trusted_base_sha)
    database = graph_database_path(root, graph_result_path)
    node_paths, adjacency, diagnostics = read_graph_acceptance_facts(database)
    full_scope = migration_requested(environment)
    reachable_paths = graph_reachable_paths(
        node_paths,
        adjacency,
        diff.changed_paths,
        full_scope,
    )
    blocking: list[dict[str, str]] = []
    baseline: list[dict[str, str]] = []
    for diagnostic in diagnostics:
        source_path = diagnostic["source_path"]
        target_path = diagnostic["target_path"]
        if (
            full_scope
            or source_path in reachable_paths
            or path_is_changed(source_path, diff.changed_paths)
            or (target_path and path_is_changed(target_path, diff.changed_paths))
        ):
            blocking.append({**diagnostic, "classification": "changed_responsibility"})
            continue
        if not base_source_is_unchanged(root, diff, source_path):
            blocking.append({**diagnostic, "classification": "base_identity_unconfirmed"})
            continue
        baseline.append({**diagnostic, "classification": "unchanged_base_source"})
    report: dict[str, object] = {
        "schema": "agent-canon.pr-graph-acceptance.v1",
        "base_sha": diff.base_sha,
        "head_sha": diff.head_sha,
        "changed_paths": list(diff.changed_paths),
        "changed_paths_sha256": changed_paths_digest(diff.changed_paths),
        "full_scope": full_scope,
        "reachable_paths": sorted(reachable_paths),
        "blocking_diagnostics": blocking,
        "baseline_diagnostics": baseline,
    }
    report_digest = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence = (
        f"base={diff.base_sha};changed_paths_sha256={changed_paths_digest(diff.changed_paths)};"
        f"reachable={len(reachable_paths)};blocking={len(blocking)};"
        f"baseline_reported={len(baseline)};report_sha256={report_digest}"
    )
    if blocking:
        return GraphAcceptance(
            "fail",
            "changed_responsibility_graph_incomplete",
            evidence,
            report,
        )
    return GraphAcceptance(
        "pass",
        "unrelated_baseline_incompleteness_reported",
        evidence,
        report,
    )


def select(
    root: Path,
    source_root: Path,
    environment: Mapping[str, str],
    trusted_base_sha: str | None = None,
) -> Selection:
    """Return the strict graph selection for one parent PR."""
    diff = load_diff(root, environment, trusted_base_sha)
    surfaces = dependency_surface_paths(source_root)
    profiles = load_profiles(source_root, environment)
    touched_surfaces = tuple(path for path in diff.changed_paths if path in surfaces)
    manifest_touched = bool(MANIFEST_CHANGE_RE.search(diff.patch))
    explicit_migration = migration_requested(environment)

    reasons: list[str] = []
    evidence: list[str] = [
        f"base={diff.base_sha}",
        f"base_source={diff.base_source}",
        f"changed_paths_sha256={changed_paths_digest(diff.changed_paths)}",
        f"dependency_surface_owner={DEPENDENCY_SURFACE_OWNER.as_posix()}",
    ]
    if explicit_migration:
        reasons.append("parent_graph_migration")
        evidence.append("migration=explicit")
    if touched_surfaces:
        reasons.append("canonical_dependency_surface_touched")
        evidence.append(f"dependency_surfaces={','.join(touched_surfaces)}")
    if manifest_touched:
        reasons.append("dependency_manifest_touched")
        evidence.append("dependency_manifest_diff=yes")
    if profiles.graph_required:
        reasons.append("canonical_profile_requires_graph")
        evidence.append(f"graph_profiles={','.join(profiles.graph_required)}")
    evidence.append(
        f"selected_profiles={','.join(profiles.selected) if profiles.selected else 'none'}"
    )
    if reasons:
        return Selection("required", ",".join(reasons), ";".join(evidence))
    return Selection(
        "skipped",
        "parent_graph_completeness_not_selected",
        ";".join(evidence),
    )


def main() -> int:
    """Run the selector and emit a typed result."""
    args = build_parser().parse_args()
    if args.evaluate_built_graph:
        if not args.graph_result or not args.report_out:
            emit_acceptance(
                "fail",
                "graph_acceptance_arguments_missing",
                "required=graph_result,report_out",
            )
            return EXIT_FAILURE
        try:
            acceptance = evaluate_built_graph(
                Path(args.root).resolve(),
                Path(args.graph_result).resolve(),
                os.environ,
                args.trusted_base_sha,
            )
            report_out = Path(args.report_out)
            report_out.parent.mkdir(parents=True, exist_ok=True)
            report_out.write_text(
                json.dumps(acceptance.report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except (OSError, SelectorFailure) as error:
            if isinstance(error, SelectorFailure):
                reason = error.reason
                evidence = error.evidence
            else:
                reason = "graph_acceptance_report_write_failed"
                evidence = f"error={type(error).__name__}"
            emit_acceptance("fail", reason, evidence)
            return EXIT_FAILURE
        emit_acceptance(
            acceptance.status,
            acceptance.reason,
            acceptance.evidence,
        )
        return EXIT_REQUIRED if acceptance.status == "pass" else EXIT_FAILURE
    if args.prepare_ci_base:
        try:
            prepared = prepare_ci_base(Path(args.root).resolve(), os.environ)
        except SelectorFailure as error:
            emit_base("fail", error.reason, error.evidence)
            return EXIT_FAILURE
        reason = (
            "trusted_pr_base_fetched"
            if prepared.fetched
            else "trusted_pr_base_already_available"
        )
        fetch = "performed" if prepared.fetched else "skipped"
        emit_base(
            "pass",
            reason,
            f"source={prepared.base_source};fetch={fetch}",
            prepared.base_sha,
        )
        return EXIT_REQUIRED
    try:
        selection = select(
            Path(args.root).resolve(),
            Path(args.source_root).resolve(),
            os.environ,
            args.trusted_base_sha,
        )
    except SelectorFailure as error:
        emit("fail", error.reason, error.evidence)
        return EXIT_FAILURE
    emit(selection.status, selection.reason, selection.evidence)
    return EXIT_REQUIRED if selection.status == "required" else EXIT_SKIPPED


if __name__ == "__main__":
    raise SystemExit(main())
