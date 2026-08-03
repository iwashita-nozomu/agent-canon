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
import re
import sqlite3
import stat
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast
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
HEX_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FULL_HISTORY_DEEPEN = "2147483647"
GRAPH_PROFILE = "default"
SOURCE_DIAGNOSTIC_SCHEMA = "agent-canon.source-diagnostic.v1"
PRODUCER_IDENTITY_VERSION = "agent-canon.surface-manifest-producer.v1"
PRODUCER_IDENTITY_CONTRACT = "agent-canon.surface-manifest.v1"
CHANGED_PATH_PACKET_SCHEMA = "agent-canon.pr-changed-paths.v1"
GRAPH_STATUS_SCHEMA = "agent-canon.graph.status.v1"


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


@dataclass(frozen=True)
class FileIdentity:
    """Stable filesystem identity used to reject concurrent replacement."""

    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class GraphIntegrationIdentity:
    """Strictly typed identity fields from one graph integration record."""

    schema: str
    root: str
    db_path: str
    profile: str
    source_snapshot_profile: str
    snapshot_head: str
    input_fingerprint: str
    graph_fingerprint: str
    producer_identity: ProducerIdentity
    verified: bool


@dataclass(frozen=True)
class ProducerIdentity:
    """Authority and semantic identity of the current graph producer."""

    source_root: str
    producer_path: str
    version: str
    contract: str
    producer_sha256: str
    manifest_path: str
    manifest_sha256: str

    def json(self) -> dict[str, str]:
        """Return the exact JSON object bound into graph artifacts."""
        return {
            "source_root": self.source_root,
            "producer_path": self.producer_path,
            "version": self.version,
            "contract": self.contract,
            "producer_sha256": self.producer_sha256,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True)
class GraphBuildIdentity:
    """One command result bound to its canonical persisted graph identity."""

    result_path: Path
    result_file_identity: FileIdentity
    database: Path
    database_file_identity: FileIdentity
    root: str
    profile: str
    snapshot_head: str
    input_fingerprint: str
    graph_fingerprint: str
    producer_identity: ProducerIdentity
    publication: str
    durability: str
    integration_identity: GraphIntegrationIdentity
    build_status: str
    exit_code: int

    def report(self) -> dict[str, object]:
        """Return the identity fields preserved in the scoped receipt."""
        return {
            "root": self.root,
            "profile": self.profile,
            "snapshot_head": self.snapshot_head,
            "input_fingerprint": self.input_fingerprint,
            "graph_fingerprint": self.graph_fingerprint,
            "producer_identity": self.producer_identity.json(),
            "publication": self.publication,
            "durability": self.durability,
            "verified": self.integration_identity.verified,
            "build_status": self.build_status,
            "exit_code": self.exit_code,
            "db_path": str(self.database),
        }


@dataclass(frozen=True)
class GraphStatusBinding:
    """One status result bound to the exact graph candidate artifacts."""

    path: Path
    file_identity: FileIdentity
    payload: dict[str, object]


class DiagnosticRecord(TypedDict):
    """One validated persisted graph diagnostic."""

    code: str
    message: str
    source_path: str
    target_path: str
    declaration: str
    severity: str


class DiagnosticSourceSpan(TypedDict):
    """Source span carried by one producer-owned diagnostic payload."""

    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


class DiagnosticDeclarationComponents(TypedDict):
    """Typed manifest declaration components carried by a diagnostic payload."""

    direction: str
    kind: str
    target: str
    reason: str


class ClassifiedDiagnostic(DiagnosticRecord):
    """One diagnostic in the duplicate-free blocking/baseline partition."""

    identity: str
    base_match: bool
    worsened: bool
    classification: str


@dataclass(frozen=True)
class TrustedBaseGraph:
    """Diagnostics and identity facts built from the validated PR base."""

    snapshot_head: str
    input_fingerprint: str
    graph_fingerprint: str
    producer_identity: ProducerIdentity
    publication: str
    durability: str
    verified: bool
    build_status: str
    diagnostics: tuple[DiagnosticRecord, ...]

    def report(self, base_sha: str) -> dict[str, object]:
        """Return durable base-comparison evidence without the temp path."""
        identities = sorted(
            diagnostic_identity_key(diagnostic) for diagnostic in self.diagnostics
        )
        digest = hashlib.sha256(
            json.dumps(identities, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "base_sha": base_sha,
            "snapshot_head": self.snapshot_head,
            "input_fingerprint": self.input_fingerprint,
            "graph_fingerprint": self.graph_fingerprint,
            "producer_identity": self.producer_identity.json(),
            "publication": self.publication,
            "durability": self.durability,
            "verified": self.verified,
            "build_status": self.build_status,
            "diagnostic_count": len(identities),
            "diagnostic_identities_sha256": digest,
        }


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
        "--status-result",
        help="JSON result emitted by the bound graph status readback.",
    )
    parser.add_argument(
        "--report-out",
        help="Write changed-responsibility and baseline diagnostics as JSON.",
    )
    parser.add_argument(
        "--producer-identity",
        action="store_true",
        help="Print the authorized current producer identity as compact JSON.",
    )
    parser.add_argument(
        "--changed-path-packet",
        help="Write trusted base/head changed-path evidence for canonical scans.",
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


def write_changed_path_packet(
    root: Path,
    diff: DiffEvidence,
    packet_path: Path,
) -> None:
    """Persist the selector-owned trusted base/head path evidence."""
    merge_base = git_output(
        root,
        ["merge-base", diff.base_sha, diff.head_sha],
        "pr_changed_paths_merge_base_failed",
    ).strip()
    base_tree = git_output(
        root,
        ["rev-parse", "--verify", "--end-of-options", f"{diff.base_sha}^{{tree}}"],
        "pr_base_tree_unresolved",
    ).strip()
    head_tree = git_output(
        root,
        ["rev-parse", "--verify", "--end-of-options", f"{diff.head_sha}^{{tree}}"],
        "pr_head_tree_unresolved",
    ).strip()
    packet = {
        "schema": CHANGED_PATH_PACKET_SCHEMA,
        "root": str(root),
        "base_sha": diff.base_sha,
        "base_source": diff.base_source,
        "base_tree": base_tree,
        "head_sha": diff.head_sha,
        "head_tree": head_tree,
        "merge_base": merge_base,
        "changed_paths": list(diff.changed_paths),
        "changed_paths_sha256": changed_paths_digest(diff.changed_paths),
    }
    try:
        packet_path.parent.mkdir(parents=True, exist_ok=True)
        packet_path.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise SelectorFailure(
            "pr_changed_path_packet_write_failed",
            f"path={packet_path};error={type(error).__name__}",
        ) from error


def path_is_changed(path: str, changed_paths: Sequence[str]) -> bool:
    """Return whether an exact changed path owns the graph path."""
    return any(
        path == changed or path.startswith(f"{changed.rstrip('/')}/")
        for changed in changed_paths
    )


def diagnostic_payload_string(
    payload: Mapping[str, object],
    field: str,
    owner: str,
) -> str:
    """Read one required nonempty diagnostic payload string without coercion."""
    if field not in payload:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field={field};required=yes",
        )
    value = payload[field]
    if type(value) is not str:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field={field};expected_type=string",
        )
    if not value.strip():
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field={field};required_nonempty=yes",
        )
    return value


def diagnostic_payload_object(
    value: object,
    owner: str,
    expected_fields: frozenset[str],
) -> dict[str, object]:
    """Read one strict diagnostic payload object with an exact field set."""
    if type(value) is not dict:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};expected_type=object",
        )
    payload = cast(dict[str, object], value)
    actual_fields = frozenset(payload)
    if actual_fields != expected_fields:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};fields=expected:{','.join(sorted(expected_fields))};"
            f"actual:{','.join(sorted(actual_fields))}",
        )
    return payload


def validate_source_diagnostic(
    *,
    rule: object,
    message: object,
    target_node_id: object,
    severity: object,
    payload_value: object,
    node_paths: Mapping[str, str],
    owner: str,
) -> DiagnosticRecord:
    """Validate one producer-owned source diagnostic before classification."""
    if type(rule) is not str or not rule.strip():
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=rule;expected_type=nonempty_string",
        )
    if type(message) is not str or not message.strip():
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=message;expected_type=nonempty_string",
        )
    if type(target_node_id) is not str or not target_node_id.strip():
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=target_node_id;expected_type=nonempty_string",
        )
    if target_node_id not in node_paths:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=target_node_id;target_node=missing",
        )
    if type(severity) is not str or not severity.strip():
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=severity;expected_type=nonempty_string",
        )
    severity_rank(cast(str, severity))
    payload = diagnostic_payload_object(
        payload_value,
        f"{owner}.payload_json",
        frozenset(
            {
                "schema",
                "code",
                "source",
                "target",
                "declaration",
                "source_span",
                "declaration_components",
            }
        ),
    )
    schema = diagnostic_payload_string(payload, "schema", owner)
    if schema != SOURCE_DIAGNOSTIC_SCHEMA:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=schema;value={schema}",
        )
    code = diagnostic_payload_string(payload, "code", owner)
    source_path = diagnostic_payload_string(payload, "source", owner)
    target_path = diagnostic_payload_string(payload, "target", owner)
    declaration = diagnostic_payload_string(payload, "declaration", owner)
    if code != rule:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};fields=rule,code;values_differ=yes",
        )

    span_payload = diagnostic_payload_object(
        payload["source_span"],
        f"{owner}.source_span",
        frozenset({"path", "start_line", "start_column", "end_line", "end_column"}),
    )
    span = cast(DiagnosticSourceSpan, span_payload)
    span_path = diagnostic_payload_string(span_payload, "path", f"{owner}.source_span")
    if span_path != source_path or node_paths[target_node_id] != source_path:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};fields=source,source_span.path,target_node_id;values_differ=yes",
        )
    for field in ("start_line", "start_column", "end_line", "end_column"):
        value = span_payload[field]
        if type(value) is not int:
            raise SelectorFailure(
                "graph_diagnostic_invalid",
                f"owner={owner}.source_span;field={field};expected_type=integer",
            )
        if value < 1:
            raise SelectorFailure(
                "graph_diagnostic_invalid",
                f"owner={owner}.source_span;field={field};required_positive=yes",
            )
    if (
        cast(int, span["end_line"]) < cast(int, span["start_line"])
        or (
            span["end_line"] == span["start_line"]
            and span["end_column"] < span["start_column"]
        )
    ):
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner}.source_span;ordering=invalid",
        )

    components_payload = diagnostic_payload_object(
        payload["declaration_components"],
        f"{owner}.declaration_components",
        frozenset({"direction", "kind", "target", "reason"}),
    )
    components = cast(DiagnosticDeclarationComponents, components_payload)
    direction = diagnostic_payload_string(
        components_payload,
        "direction",
        f"{owner}.declaration_components",
    )
    kind = diagnostic_payload_string(
        components_payload,
        "kind",
        f"{owner}.declaration_components",
    )
    component_target = diagnostic_payload_string(
        components_payload,
        "target",
        f"{owner}.declaration_components",
    )
    reason = diagnostic_payload_string(
        components_payload,
        "reason",
        f"{owner}.declaration_components",
    )
    if component_target != target_path:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};fields=target,declaration_components.target;values_differ=yes",
        )
    canonical_declaration = " ".join((direction, kind, component_target, reason))
    if declaration != canonical_declaration:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};fields=declaration,declaration_components;values_differ=yes",
        )
    if any(value != " ".join(value.split()) for value in (direction, kind, component_target, reason)):
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"owner={owner};field=declaration_components;canonical_whitespace=no",
        )
    return {
        "code": code,
        "message": cast(str, message),
        "source_path": source_path,
        "target_path": target_path,
        "declaration": declaration,
        "severity": cast(str, severity),
    }


def diagnostic_identity_key(diagnostic: DiagnosticRecord) -> tuple[str, str, str, str]:
    """Return the canonical code/source/target/declaration diagnostic identity."""
    return (
        diagnostic["code"],
        diagnostic["source_path"],
        diagnostic["target_path"],
        diagnostic["declaration"],
    )


def diagnostic_identity_text(diagnostic: DiagnosticRecord) -> str:
    """Serialize one normalized identity without line numbers or counts."""
    return json.dumps(diagnostic_identity_key(diagnostic), separators=(",", ":"))


SEVERITY_RANK = {
    "info": 0,
    "notice": 1,
    "warning": 2,
    "error": 3,
    "blocker": 4,
}


def severity_rank(value: str) -> int:
    """Return a strict comparable severity rank."""
    if value not in SEVERITY_RANK:
        raise SelectorFailure(
            "graph_diagnostic_invalid",
            f"field=severity;value_sha256={hashlib.sha256(value.encode()).hexdigest()}",
        )
    return SEVERITY_RANK[value]


def deduplicate_diagnostics(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[DiagnosticRecord, ...]:
    """Collapse duplicate rows by normalized identity before base comparison."""
    selected: dict[tuple[str, str, str, str], DiagnosticRecord] = {}
    for diagnostic in diagnostics:
        for field in (
            "code",
            "message",
            "source_path",
            "target_path",
            "declaration",
            "severity",
        ):
            value = diagnostic.get(field)
            if type(value) is not str:
                raise SelectorFailure(
                    "graph_diagnostic_invalid",
                    f"field={field};expected_type=string",
                )
        key = diagnostic_identity_key(diagnostic)
        current = selected.get(key)
        if current is None or severity_rank(diagnostic["severity"]) > severity_rank(
            current["severity"]
        ):
            selected[key] = diagnostic
    return tuple(selected[key] for key in sorted(selected))


def classify_diagnostic(
    diagnostic: DiagnosticRecord,
    *,
    base_match: bool,
    worsened: bool,
    classification: str,
) -> ClassifiedDiagnostic:
    """Add typed classification fields to one validated diagnostic record."""
    return {
        "code": diagnostic["code"],
        "message": diagnostic["message"],
        "source_path": diagnostic["source_path"],
        "target_path": diagnostic["target_path"],
        "declaration": diagnostic["declaration"],
        "severity": diagnostic["severity"],
        "identity": diagnostic_identity_text(diagnostic),
        "base_match": base_match,
        "worsened": worsened,
        "classification": classification,
    }


def regular_file_identity(
    path: Path,
    unavailable_reason: str,
    invalid_reason: str,
) -> FileIdentity:
    """Read one non-symlink regular-file identity or fail closed."""
    try:
        metadata = path.lstat()
    except OSError:
        raise SelectorFailure(unavailable_reason, f"path={path}") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SelectorFailure(invalid_reason, f"path={path}")
    return FileIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def assert_file_identity(path: Path, expected: FileIdentity, artifact: str) -> None:
    """Reject removal, mutation, or replacement after identity capture."""
    try:
        current = regular_file_identity(
            path,
            "graph_identity_replaced",
            "graph_identity_replaced",
        )
    except SelectorFailure:
        raise SelectorFailure(
            "graph_identity_replaced",
            f"artifact={artifact};path={path}",
        ) from None
    if current != expected:
        raise SelectorFailure(
            "graph_identity_replaced",
            f"artifact={artifact};path={path}",
        )


def required_identity_string(
    payload: Mapping[str, object],
    field: str,
    owner: str,
    pattern: re.Pattern[str] | None = None,
) -> str:
    """Read one required canonical identity scalar."""
    if field not in payload:
        raise SelectorFailure(
            "graph_identity_missing",
            f"owner={owner};field={field}",
        )
    value = payload[field]
    if type(value) is not str:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field={field};expected_type=string",
        )
    if not value:
        raise SelectorFailure(
            "graph_identity_missing",
            f"owner={owner};field={field}",
        )
    if pattern is not None and not pattern.fullmatch(value):
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field={field}",
        )
    return value


def validate_integration_identity(
    payload: object,
    owner: str,
) -> GraphIntegrationIdentity:
    """Validate one integration record without coercion or record equality."""
    if type(payload) is not dict:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=integration_record;expected_type=object",
        )
    record = cast(dict[str, object], payload)
    schema = required_identity_string(record, "schema", owner)
    root = required_identity_string(record, "root", owner)
    db_path = required_identity_string(record, "db_path", owner)
    profile = required_identity_string(record, "profile", owner)
    source_snapshot_profile = required_identity_string(
        record,
        "source_snapshot_profile",
        owner,
    )
    snapshot_head = required_identity_string(
        record,
        "snapshot_head",
        owner,
        HEX_SHA_RE,
    )
    input_fingerprint = required_identity_string(
        record,
        "input_fingerprint",
        owner,
        HEX_FINGERPRINT_RE,
    )
    graph_fingerprint = required_identity_string(
        record,
        "graph_fingerprint",
        owner,
        HEX_FINGERPRINT_RE,
    )
    if "producer_identity" not in record:
        raise SelectorFailure(
            "graph_identity_missing",
            f"owner={owner};field=producer_identity",
        )
    producer_identity = validate_producer_identity(
        record["producer_identity"],
        f"{owner}.producer_identity",
    )
    if "verified" not in record:
        raise SelectorFailure(
            "graph_identity_missing",
            f"owner={owner};field=verified",
        )
    if record["verified"] is not True:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=verified;expected_type=bool_true",
        )
    if (
        schema != "agent-canon.graph.integration.v1"
        or source_snapshot_profile != "parent"
    ):
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=schema,source_snapshot_profile",
        )
    return GraphIntegrationIdentity(
        schema,
        root,
        db_path,
        profile,
        source_snapshot_profile,
        snapshot_head,
        input_fingerprint,
        graph_fingerprint,
        producer_identity,
        True,
    )


def integration_identity_mismatches(
    result: GraphIntegrationIdentity,
    persisted: GraphIntegrationIdentity,
) -> tuple[str, ...]:
    """Compare validated integration fields individually and without coercion."""
    mismatches: list[str] = []
    for field in (
        "schema",
        "root",
        "db_path",
        "profile",
        "source_snapshot_profile",
        "snapshot_head",
        "input_fingerprint",
        "graph_fingerprint",
        "producer_identity",
        "verified",
    ):
        result_value = getattr(result, field)
        persisted_value = getattr(persisted, field)
        if (
            type(result_value) is not type(persisted_value)
            or result_value != persisted_value
        ):
            mismatches.append(field)
    return tuple(mismatches)


def graph_build_identity(
    root: Path,
    graph_result_path: Path,
    *,
    allow_complete: bool = False,
    expected_producer_identity: ProducerIdentity | None = None,
) -> GraphBuildIdentity:
    """Validate one build result and capture its canonical database identity."""
    result_file_identity = regular_file_identity(
        graph_result_path,
        "graph_build_result_unavailable",
        "graph_build_result_invalid",
    )
    try:
        payload: object = json.loads(graph_result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SelectorFailure(
            "graph_build_result_invalid",
            f"path={graph_result_path}",
        ) from None
    assert_file_identity(graph_result_path, result_file_identity, "graph_build_result")
    if type(payload) is not dict:
        raise SelectorFailure("graph_build_result_invalid", "detail=not_object")
    result = cast(dict[str, object], payload)
    schema = required_identity_string(result, "schema", "graph_build_result")
    command = required_identity_string(result, "command", "graph_build_result")
    status_value = required_identity_string(result, "status", "graph_build_result")
    graph_status = required_identity_string(
        result,
        "graph_status",
        "graph_build_result",
    )
    if "exit_code" not in result or type(result["exit_code"]) is not int:
        raise SelectorFailure(
            "graph_identity_invalid",
            "owner=graph_build_result;field=exit_code;expected_type=integer",
        )
    expected_states = {"incomplete": 1}
    if allow_complete:
        expected_states["fresh"] = 0
    if (
        schema != "agent-canon.graph.build.v1"
        or command != "build"
        or status_value not in expected_states
        or graph_status != status_value
        or result["exit_code"] != expected_states.get(status_value)
    ):
        raise SelectorFailure(
            "graph_build_result_invalid",
            "detail=expected_incomplete_build"
            if not allow_complete
            else "detail=expected_build",
        )
    if "integration_record" not in result:
        raise SelectorFailure(
            "graph_identity_missing",
            "owner=graph_build_result;field=integration_record",
        )
    integration = validate_integration_identity(
        result["integration_record"],
        "graph_build_result.integration_record",
    )
    if "producer_identity" not in result:
        raise SelectorFailure(
            "graph_identity_missing",
            "owner=graph_build_result;field=producer_identity",
        )
    result_producer_identity = validate_producer_identity(
        result["producer_identity"],
        "graph_build_result.producer_identity",
        expected_producer_identity,
    )
    if result_producer_identity != integration.producer_identity:
        raise SelectorFailure(
            "graph_identity_mismatch",
            "fields=producer_identity",
        )

    canonical_root = root.resolve(strict=True)
    expected_database = (
        canonical_root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
    )
    result_root = required_identity_string(result, "root", "graph_build_result")
    result_profile = required_identity_string(result, "profile", "graph_build_result")
    result_database = required_identity_string(result, "db_path", "graph_build_result")
    result_input = required_identity_string(
        result,
        "input_fingerprint",
        "graph_build_result",
        HEX_FINGERPRINT_RE,
    )
    result_graph = required_identity_string(
        result,
        "graph_fingerprint",
        "graph_build_result",
        HEX_FINGERPRINT_RE,
    )
    publication = required_identity_string(
        result,
        "publication",
        "graph_build_result",
    )
    durability = required_identity_string(
        result,
        "durability",
        "graph_build_result",
    )
    if (
        result_root != str(canonical_root)
        or integration.root != result_root
        or result_profile != GRAPH_PROFILE
        or integration.profile != result_profile
        or result_database != str(expected_database)
        or integration.db_path != result_database
        or result_input != integration.input_fingerprint
        or result_graph != integration.graph_fingerprint
        or publication != "published"
        or durability != "durable"
    ):
        raise SelectorFailure(
            "graph_identity_mismatch",
            "fields=root,profile,db_path,input_fingerprint,graph_fingerprint,publication",
        )

    for field in ("unresolved_count", "ambiguous_count", "uncovered_count"):
        value = result.get(field)
        if field not in result:
            raise SelectorFailure(
                "graph_identity_missing",
                f"owner=graph_build_result;field={field}",
            )
        if type(value) is not int or value < 0:
            raise SelectorFailure(
                "graph_identity_invalid",
                f"owner=graph_build_result;field={field};"
                "expected_type=nonnegative_integer",
            )

    database_file_identity = regular_file_identity(
        expected_database,
        "graph_database_unavailable",
        "graph_database_identity_invalid",
    )
    try:
        resolved_database = expected_database.resolve(strict=True)
    except OSError:
        raise SelectorFailure(
            "graph_database_unavailable",
            f"path={expected_database}",
        ) from None
    if resolved_database != expected_database:
        raise SelectorFailure(
            "graph_database_identity_invalid",
            f"path={expected_database}",
        )
    return GraphBuildIdentity(
        graph_result_path,
        result_file_identity,
        resolved_database,
        database_file_identity,
        result_root,
        result_profile,
        integration.snapshot_head,
        result_input,
        result_graph,
        result_producer_identity,
        publication,
        durability,
        integration,
        status_value,
        result["exit_code"],
    )


def status_result_string(
    payload: Mapping[str, object],
    field: str,
    owner: str,
    pattern: re.Pattern[str] | None = None,
) -> str:
    """Read one exact nonempty string from a graph status result."""
    value = payload.get(field)
    if type(value) is not str or not value:
        raise SelectorFailure(
            "graph_status_result_invalid",
            f"owner={owner};field={field};expected_type=nonempty_string",
        )
    if pattern is not None and not pattern.fullmatch(value):
        raise SelectorFailure(
            "graph_status_result_invalid",
            f"owner={owner};field={field};format=invalid",
        )
    return value


def status_result_file_identity(path: Path) -> FileIdentity:
    """Capture one status result file identity with status-specific failures."""
    return regular_file_identity(
        path,
        "graph_status_result_unavailable",
        "graph_status_result_invalid",
    )


def assert_status_result_identity(path: Path, expected: FileIdentity) -> None:
    """Reject status replacement during candidate validation."""
    try:
        current = status_result_file_identity(path)
    except SelectorFailure:
        raise SelectorFailure(
            "graph_status_result_replaced",
            f"path={path}",
        ) from None
    if current != expected:
        raise SelectorFailure(
            "graph_status_result_replaced",
            f"path={path}",
        )


def validate_graph_status_binding(
    status_result_path: Path,
    build: GraphBuildIdentity,
    *,
    expected_status: str = "incomplete",
) -> GraphStatusBinding:
    """Validate status and bind it to build output plus persisted DB identity."""
    status_file_identity = status_result_file_identity(status_result_path)
    try:
        raw_status = status_result_path.read_text(encoding="utf-8")
    except OSError:
        raise SelectorFailure(
            "graph_status_result_unavailable",
            f"path={status_result_path}",
        ) from None
    if not raw_status.strip():
        raise SelectorFailure(
            "graph_status_result_unavailable",
            f"path={status_result_path};detail=empty",
        )
    try:
        status_value: object = json.loads(raw_status)
    except (TypeError, ValueError):
        raise SelectorFailure(
            "graph_status_result_invalid",
            f"path={status_result_path};detail=invalid_json",
        ) from None
    assert_status_result_identity(status_result_path, status_file_identity)
    if type(status_value) is not dict:
        raise SelectorFailure(
            "graph_status_result_invalid",
            "detail=not_object",
        )
    status = cast(dict[str, object], status_value)
    schema = status_result_string(status, "schema", "graph_status_result")
    command = status_result_string(status, "command", "graph_status_result")
    status_name = status_result_string(status, "status", "graph_status_result")
    if schema != GRAPH_STATUS_SCHEMA or command != "status":
        raise SelectorFailure(
            "graph_status_result_invalid",
            "fields=schema,command;expected=canonical_status",
        )
    if status_name == "unavailable":
        expected_fields = frozenset(
            {"schema", "command", "status", "reason", "exit_code"}
        )
        if frozenset(status) != expected_fields:
            raise SelectorFailure(
                "graph_status_result_invalid",
                "status=unavailable;fields=unexpected",
            )
        reason = status_result_string(status, "reason", "graph_status_result")
        exit_code = status.get("exit_code")
        if type(exit_code) is not int or exit_code != 1:
            raise SelectorFailure(
                "graph_status_result_invalid",
                "status=unavailable;field=exit_code;expected=1",
            )
        raise SelectorFailure(
            "graph_status_unavailable",
            f"reason={reason}",
        )

    expected_fields = frozenset(
        {
            "schema",
            "command",
            "status",
            "profile",
            "root",
            "db_path",
            "input_fingerprint",
            "graph_fingerprint",
            "integration_record",
            "unresolved_count",
            "ambiguous_count",
            "uncovered_count",
            "probe_reason",
            "reason",
            "exit_code",
        }
    )
    if frozenset(status) != expected_fields:
        raise SelectorFailure(
            "graph_status_result_invalid",
            "fields=expected_status_schema;exact=yes",
        )
    profile = status_result_string(status, "profile", "graph_status_result")
    root = status_result_string(status, "root", "graph_status_result")
    db_path = status_result_string(status, "db_path", "graph_status_result")
    input_fingerprint = status_result_string(
        status,
        "input_fingerprint",
        "graph_status_result",
        HEX_FINGERPRINT_RE,
    )
    graph_fingerprint = status_result_string(
        status,
        "graph_fingerprint",
        "graph_status_result",
        HEX_FINGERPRINT_RE,
    )
    if expected_status not in {"fresh", "incomplete"}:
        raise SelectorFailure(
            "graph_status_result_invalid",
            f"expected_status={expected_status}",
        )
    reason_value = status.get("reason")
    if reason_value is not None and (
        type(reason_value) is not str or not reason_value
    ):
        raise SelectorFailure(
            "graph_status_result_invalid",
            "field=reason;expected_type=null_or_nonempty_string",
        )
    probe_reason = status.get("probe_reason")
    if probe_reason is not None and (type(probe_reason) is not str or not probe_reason):
        raise SelectorFailure(
            "graph_status_result_invalid",
            "field=probe_reason;expected_type=null_or_nonempty_string",
        )
    counts: dict[str, int] = {}
    for field in ("unresolved_count", "ambiguous_count", "uncovered_count"):
        value = status.get(field)
        if type(value) is not int or value < 0:
            raise SelectorFailure(
                "graph_status_result_invalid",
                f"field={field};expected_type=nonnegative_integer",
            )
        counts[field] = value
    exit_code = status.get("exit_code")
    if type(exit_code) is not int:
        raise SelectorFailure(
            "graph_status_result_invalid",
            "field=exit_code;expected_type=integer",
        )
    if status_name == "stale":
        if probe_reason == "source_changed":
            raise SelectorFailure(
                "graph_status_source_changed",
                "probe_reason=source_changed",
            )
        raise SelectorFailure(
            "graph_status_stale",
            f"probe_reason={probe_reason or 'missing'}",
        )
    if status_name == "fresh":
        if expected_status != "fresh":
            raise SelectorFailure(
                "graph_status_fresh",
                "required_status=incomplete",
            )
        if exit_code != 0:
            raise SelectorFailure(
                "graph_status_exit_code_mismatch",
                f"expected=0;actual={exit_code}",
            )
        if reason_value is not None:
            raise SelectorFailure(
                "graph_status_reason_mismatch",
                f"expected=null;actual={reason_value}",
            )
        if probe_reason is not None:
            raise SelectorFailure(
                "graph_status_probe_reason_mismatch",
                "expected=null",
            )
    elif status_name == "incomplete":
        if expected_status != "incomplete":
            raise SelectorFailure(
                "graph_status_incomplete",
                "required_status=fresh",
            )
        if type(reason_value) is not str or not reason_value:
            raise SelectorFailure(
                "graph_status_result_invalid",
                "field=reason;expected_type=nonempty_string",
            )
        if exit_code != 2:
            raise SelectorFailure(
                "graph_status_exit_code_mismatch",
                f"expected=2;actual={exit_code}",
            )
        if reason_value != "source_completeness_incomplete":
            raise SelectorFailure(
                "graph_status_reason_mismatch",
                "expected=source_completeness_incomplete;"
                f"actual={reason_value}",
            )
        if probe_reason is not None:
            raise SelectorFailure(
                "graph_status_probe_reason_mismatch",
                "expected=null",
            )
    else:
        raise SelectorFailure(
            "graph_status_not_incomplete",
            f"status={status_name}",
        )
    integration_value = status.get("integration_record")
    if type(integration_value) is not dict:
        raise SelectorFailure(
            "graph_status_result_invalid",
            "field=integration_record;expected_type=object",
        )
    status_integration = validate_integration_identity(
        integration_value,
        "graph_status_result.integration_record",
    )

    try:
        assert_file_identity(
            build.result_path,
            build.result_file_identity,
            "graph_build_result",
        )
        build_result_value: object = json.loads(
            build.result_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owner=graph_build_result;detail=unavailable",
        ) from None
    if type(build_result_value) is not dict:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owner=graph_build_result;detail=not_object",
        )
    build_result = cast(dict[str, object], build_result_value)
    if "integration_record" not in build_result:
        raise SelectorFailure(
            "graph_identity_missing",
            "owner=graph_build_result;field=integration_record",
        )
    build_integration = validate_integration_identity(
        build_result["integration_record"],
        "graph_build_result.integration_record",
    )
    integration_mismatches = integration_identity_mismatches(
        status_integration,
        build_integration,
    )
    if integration_mismatches:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owners=graph_status_result,graph_build_result;fields="
            + ",".join(integration_mismatches),
        )
    integration_mismatches = integration_identity_mismatches(
        status_integration,
        build.integration_identity,
    )
    if integration_mismatches:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owners=graph_status_result,graph_build_identity;fields="
            + ",".join(integration_mismatches),
        )
    for field in ("unresolved_count", "ambiguous_count", "uncovered_count"):
        if field not in build_result:
            raise SelectorFailure(
                "graph_identity_missing",
                f"owner=graph_build_result;field={field}",
            )
        value = build_result[field]
        if type(value) is not int or value < 0:
            raise SelectorFailure(
                "graph_identity_invalid",
                f"owner=graph_build_result;field={field};"
                "expected_type=nonnegative_integer",
            )
        if counts[field] != value:
            raise SelectorFailure(
                "graph_status_counts_mismatch",
                f"field={field};build={value};status={counts[field]}",
            )

    try:
        assert_file_identity(build.database, build.database_file_identity, "graph_database")
        uri = f"file:{quote(build.database.as_posix(), safe='/')}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as connection:
            rows = connection.execute(
                "SELECT key, value FROM metadata WHERE key IN "
                "('integration_record','input_fingerprint','graph_fingerprint')"
            ).fetchall()
            diagnostic_count_rows = connection.execute(
                "SELECT rule, COUNT(*) FROM diagnostics WHERE layer='source' "
                "GROUP BY rule"
            ).fetchall()
        assert_file_identity(build.database, build.database_file_identity, "graph_database")
    except sqlite3.Error:
        raise SelectorFailure(
            "graph_status_unavailable",
            "owner=graph_database_metadata",
        ) from None
    metadata = {str(key): value for key, value in rows}
    if set(metadata) != {"integration_record", "input_fingerprint", "graph_fingerprint"}:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owner=graph_database_metadata;fields=integration_record,input_fingerprint,graph_fingerprint",
        )
    database_counts = {
        "unresolved_count": 0,
        "ambiguous_count": 0,
        "uncovered_count": 0,
    }
    for rule, count in diagnostic_count_rows:
        if type(rule) is not str or type(count) is not int or count < 0:
            raise SelectorFailure(
                "graph_status_result_invalid",
                "owner=graph_database;field=diagnostic_counts;"
                "expected_type=canonical_rows",
            )
        category = {
            "target-ambiguous": "ambiguous_count",
            "source-uncovered": "uncovered_count",
        }.get(rule, "unresolved_count")
        database_counts[category] += count
    for field, value in database_counts.items():
        if counts[field] != value:
            raise SelectorFailure(
                "graph_status_counts_mismatch",
                f"owner=graph_database;field={field};database={value};"
                f"status={counts[field]}",
            )
    try:
        persisted_integration_value = json.loads(metadata["integration_record"])
    except (TypeError, ValueError):
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owner=graph_database_metadata;field=integration_record;detail=invalid_json",
        ) from None
    persisted_integration = validate_integration_identity(
        persisted_integration_value,
        "graph_database_metadata.integration_record",
    )
    integration_mismatches = integration_identity_mismatches(
        status_integration,
        persisted_integration,
    )
    if integration_mismatches:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owners=graph_status_result,graph_database_metadata;fields="
            + ",".join(integration_mismatches),
        )
    integration_mismatches = integration_identity_mismatches(
        persisted_integration,
        build.integration_identity,
    )
    if integration_mismatches:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "owners=graph_database_metadata,graph_build_identity;fields="
            + ",".join(integration_mismatches),
        )
    if type(metadata["input_fingerprint"]) is not str or metadata["input_fingerprint"] != input_fingerprint:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "field=input_fingerprint",
        )
    if metadata["graph_fingerprint"] != graph_fingerprint:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            "field=graph_fingerprint",
        )
    expected_identity = {
        "root": build.root,
        "profile": build.profile,
        "db_path": str(build.database),
        "input_fingerprint": build.input_fingerprint,
        "graph_fingerprint": build.graph_fingerprint,
    }
    actual_identity = {
        "root": root,
        "profile": profile,
        "db_path": db_path,
        "input_fingerprint": input_fingerprint,
        "graph_fingerprint": graph_fingerprint,
    }
    mismatches = sorted(
        field for field, expected in expected_identity.items() if actual_identity[field] != expected
    )
    if mismatches:
        raise SelectorFailure(
            "graph_status_identity_mismatch",
            f"fields={','.join(mismatches)}",
        )
    return GraphStatusBinding(status_result_path, status_file_identity, status)


def read_bound_graph_acceptance_facts(
    build: GraphBuildIdentity,
    expected_head: str,
) -> tuple[dict[str, str], dict[str, set[str]], list[DiagnosticRecord]]:
    """Bind persisted integration metadata, then read classification facts."""
    uri = f"file:{quote(build.database.as_posix(), safe='/')}?mode=ro&immutable=1"
    connection: sqlite3.Connection | None = None
    pending_error: SelectorFailure | None = None
    node_paths: dict[str, str] = {}
    adjacency: dict[str, set[str]] = {}
    diagnostics: list[DiagnosticRecord] = []
    try:
        connection = sqlite3.connect(uri, uri=True)
        assert_file_identity(
            build.database, build.database_file_identity, "graph_database"
        )
        metadata_rows = cast(
            list[tuple[str, str]],
            connection.execute(
                "SELECT key, value FROM metadata WHERE key IN "
                "('integration_record','producer_identity','snapshot_head','input_fingerprint','graph_fingerprint')"
            ).fetchall(),
        )
        metadata = cast(
            dict[str, object],
            {key: value for key, value in metadata_rows},
        )
        required_keys = {
            "integration_record",
            "producer_identity",
            "snapshot_head",
            "input_fingerprint",
            "graph_fingerprint",
        }
        missing = sorted(required_keys.difference(metadata))
        if missing or len(metadata_rows) != len(required_keys):
            raise SelectorFailure(
                "graph_identity_missing",
                f"owner=graph_database_metadata;fields={','.join(missing) or 'duplicate'}",
            )
        integration_json = required_identity_string(
            metadata,
            "integration_record",
            "graph_database_metadata",
        )
        persisted = validate_integration_identity(
            json.loads(integration_json),
            "graph_database_metadata.integration_record",
        )
        persisted_producer_identity = validate_producer_identity(
            json.loads(
                required_identity_string(
                    metadata,
                    "producer_identity",
                    "graph_database_metadata",
                )
            ),
            "graph_database_metadata.producer_identity",
            build.producer_identity,
        )
        if persisted_producer_identity != persisted.producer_identity:
            raise SelectorFailure(
                "graph_identity_mismatch",
                "owners=integration_record,graph_database_metadata;fields=producer_identity",
            )
        mismatches = integration_identity_mismatches(
            build.integration_identity,
            persisted,
        )
        if mismatches:
            raise SelectorFailure(
                "graph_identity_mismatch",
                "owners=graph_build_result,graph_database_metadata;"
                f"fields={','.join(mismatches)}",
            )
        metadata_snapshot_head = required_identity_string(
            metadata,
            "snapshot_head",
            "graph_database_metadata",
            HEX_SHA_RE,
        )
        metadata_input_fingerprint = required_identity_string(
            metadata,
            "input_fingerprint",
            "graph_database_metadata",
            HEX_FINGERPRINT_RE,
        )
        metadata_graph_fingerprint = required_identity_string(
            metadata,
            "graph_fingerprint",
            "graph_database_metadata",
            HEX_FINGERPRINT_RE,
        )
        if (
            metadata_snapshot_head != build.snapshot_head
            or metadata_input_fingerprint != build.input_fingerprint
            or metadata_graph_fingerprint != build.graph_fingerprint
        ):
            raise SelectorFailure(
                "graph_identity_mismatch",
                "owners=integration_record,graph_database_metadata;fields=snapshot_head,input_fingerprint,graph_fingerprint",
            )
        if build.snapshot_head != expected_head:
            raise SelectorFailure(
                "graph_snapshot_head_stale",
                f"snapshot_head={build.snapshot_head};expected_head={expected_head}",
            )

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
            node_payload = cast(dict[str, object], raw_payload)
            path = node_payload.get("path")
            if isinstance(path, str):
                node_paths[node_id] = path
        adjacency = {node_id: set() for node_id in node_paths}
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
        diagnostic_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(diagnostics)").fetchall()
        }
        required_diagnostic_columns = {
            "rule",
            "message",
            "target_node_id",
            "severity",
            "payload_json",
        }
        missing_diagnostic_columns = sorted(
            required_diagnostic_columns.difference(diagnostic_columns)
        )
        if missing_diagnostic_columns:
            raise SelectorFailure(
                "graph_diagnostic_schema_missing",
                "owner=diagnostics;fields=" + ",".join(missing_diagnostic_columns),
            )
        diagnostic_rows = cast(
            list[tuple[object, object, object, object, object]],
            connection.execute(
                "SELECT rule, message, target_node_id, severity, payload_json "
                "FROM diagnostics WHERE layer='source'"
            ).fetchall(),
        )
        for index, (
            rule,
            message,
            target_node_id,
            severity,
            payload_json,
        ) in enumerate(diagnostic_rows):
            try:
                payload_value: object = json.loads(payload_json) if type(payload_json) is str else payload_json
            except (TypeError, json.JSONDecodeError) as error:
                raise SelectorFailure(
                    "graph_diagnostic_invalid",
                    f"owner=diagnostics[{index}].payload_json;json=invalid;"
                    f"error={type(error).__name__}",
                ) from error
            diagnostics.append(
                validate_source_diagnostic(
                    rule=rule,
                    message=message,
                    target_node_id=target_node_id,
                    severity=severity,
                    payload_value=payload_value,
                    node_paths=node_paths,
                    owner=f"diagnostics[{index}]",
                )
            )
    except SelectorFailure as error:
        pending_error = error
    except (json.JSONDecodeError, sqlite3.Error):
        pending_error = SelectorFailure(
            "graph_database_invalid",
            f"path={build.database}",
        )
    finally:
        if connection is not None:
            connection.close()
    assert_file_identity(
        build.result_path, build.result_file_identity, "graph_build_result"
    )
    assert_file_identity(build.database, build.database_file_identity, "graph_database")
    if pending_error is not None:
        raise pending_error
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


def selector_source_root() -> Path:
    """Return the source tree that owns this selector and its producer."""
    return Path(__file__).resolve().parents[2]


def authorized_source_root(source_root: Path | None) -> Path:
    """Canonicalize and authorize only this selector's current source tree."""
    authority = selector_source_root().resolve(strict=True)
    candidate = authority if source_root is None else source_root.resolve(strict=True)
    if candidate != authority or not candidate.is_dir():
        raise SelectorFailure(
            "trusted_base_graph_source_root_unauthorized",
            f"expected={authority};actual={candidate}",
        )
    return candidate


def producer_content_sha256(path: Path, owner: str) -> str:
    """Hash one canonical producer file while rejecting replacement types."""
    regular_file_identity(path, "trusted_base_graph_producer_unavailable", owner)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise SelectorFailure(
            "trusted_base_graph_producer_unavailable",
            f"path={path}",
        ) from None


def current_producer_identity(source_root: Path | None) -> ProducerIdentity:
    """Build the current producer authority and semantic content identity."""
    root = authorized_source_root(source_root)
    producer = surface_manifest_producer(root)
    manifest_candidate = (
        root / PROFILE_INVENTORY.parent / "shared-runtime-surfaces.toml"
    )
    try:
        manifest = manifest_candidate.resolve(strict=True)
    except OSError:
        raise SelectorFailure(
            "trusted_base_graph_producer_manifest_unavailable",
            f"path={manifest_candidate}",
        ) from None
    try:
        manifest.relative_to(root)
    except ValueError:
        raise SelectorFailure(
            "trusted_base_graph_producer_manifest_invalid",
            f"path={manifest}",
        ) from None
    return ProducerIdentity(
        source_root=str(root),
        producer_path=str(producer),
        version=PRODUCER_IDENTITY_VERSION,
        contract=PRODUCER_IDENTITY_CONTRACT,
        producer_sha256=producer_content_sha256(
            producer,
            "trusted_base_graph_producer_invalid",
        ),
        manifest_path=str(manifest),
        manifest_sha256=producer_content_sha256(
            manifest,
            "trusted_base_graph_producer_manifest_invalid",
        ),
    )


def validate_producer_identity(
    payload: object,
    owner: str,
    expected: ProducerIdentity | None = None,
) -> ProducerIdentity:
    """Validate exact producer identity shape, paths, and live content hashes."""
    if type(payload) is not dict:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=producer_identity;expected_type=object",
        )
    record = cast(dict[str, object], payload)
    expected_fields = {
        "source_root",
        "producer_path",
        "version",
        "contract",
        "producer_sha256",
        "manifest_path",
        "manifest_sha256",
    }
    if set(record) != expected_fields:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=producer_identity;detail=canonical_fields",
        )
    identity = ProducerIdentity(
        required_identity_string(record, "source_root", owner),
        required_identity_string(record, "producer_path", owner),
        required_identity_string(record, "version", owner),
        required_identity_string(record, "contract", owner),
        required_identity_string(record, "producer_sha256", owner, HEX_SHA256_RE),
        required_identity_string(record, "manifest_path", owner),
        required_identity_string(record, "manifest_sha256", owner, HEX_SHA256_RE),
    )
    if (
        identity.version != PRODUCER_IDENTITY_VERSION
        or identity.contract != PRODUCER_IDENTITY_CONTRACT
    ):
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=version,contract",
        )
    for path_value, label in (
        (identity.source_root, "source_root"),
        (identity.producer_path, "producer_path"),
        (identity.manifest_path, "manifest_path"),
    ):
        try:
            canonical = Path(path_value).resolve(strict=True)
        except OSError:
            raise SelectorFailure(
                "graph_identity_invalid",
                f"owner={owner};field={label};detail=unavailable",
            ) from None
        if str(canonical) != path_value:
            raise SelectorFailure(
                "graph_identity_invalid",
                f"owner={owner};field={label};detail=noncanonical",
            )
    source_root = Path(identity.source_root)
    try:
        Path(identity.producer_path).relative_to(source_root)
        Path(identity.manifest_path).relative_to(source_root)
    except ValueError:
        raise SelectorFailure(
            "graph_identity_invalid",
            f"owner={owner};field=producer_path,manifest_path;detail=outside_source_root",
        ) from None
    actual_producer_sha = producer_content_sha256(
        Path(identity.producer_path),
        "graph_identity_invalid",
    )
    actual_manifest_sha = producer_content_sha256(
        Path(identity.manifest_path),
        "graph_identity_invalid",
    )
    if (
        identity.producer_sha256 != actual_producer_sha
        or identity.manifest_sha256 != actual_manifest_sha
    ):
        raise SelectorFailure(
            "graph_identity_mismatch",
            f"owner={owner};field=producer_sha256,manifest_sha256",
        )
    if expected is not None and identity != expected:
        raise SelectorFailure(
            "graph_identity_mismatch",
            f"owner={owner};field=producer_identity",
        )
    return identity


def graph_executable(source_root: Path | None) -> Path:
    """Resolve the canonical graph builder used for trusted base evidence."""
    root = authorized_source_root(source_root)
    candidate = root / "tools" / "bin" / "agent-canon"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise SelectorFailure(
            "trusted_base_graph_builder_unavailable",
            f"path={candidate}",
        ) from None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SelectorFailure(
            "trusted_base_graph_builder_unavailable",
            f"path={resolved}",
        )
    return resolved


def surface_manifest_producer(source_root: Path | None) -> Path:
    """Resolve the current source producer injected into trusted-base builds."""
    root = authorized_source_root(source_root)
    candidate = root / "tools" / "agent_tools" / "surface_manifest.py"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise SelectorFailure(
            "trusted_base_graph_producer_unavailable",
            f"path={candidate}",
        ) from None
    if not resolved.is_file():
        raise SelectorFailure(
            "trusted_base_graph_producer_unavailable",
            f"path={resolved}",
        )
    return resolved


def base_gitlinks(root: Path, base_sha: str) -> tuple[tuple[str, str], ...]:
    """Read every submodule path and exact object recorded by the base tree."""
    output = git_output(
        root,
        ["ls-tree", "-r", "--full-tree", base_sha, "--"],
        "trusted_base_submodule_identity_unavailable",
    )
    gitlinks: list[tuple[str, str]] = []
    for line in output.splitlines():
        if "\t" not in line:
            raise SelectorFailure(
                "trusted_base_submodule_identity_invalid",
                "detail=malformed_ls_tree_record",
            )
        metadata, path = line.split("\t", 1)
        fields = metadata.split()
        if len(fields) != 3:
            raise SelectorFailure(
                "trusted_base_submodule_identity_invalid",
                "detail=malformed_ls_tree_metadata",
            )
        mode, object_type, object_id = fields
        if mode == "160000":
            if object_type != "commit" or not HEX_SHA_RE.fullmatch(object_id):
                raise SelectorFailure(
                    "trusted_base_submodule_identity_invalid",
                    f"path={path};detail=invalid_gitlink",
                )
            gitlinks.append((path, object_id.lower()))
    return tuple(gitlinks)


def materialize_base_submodules(root: Path, base_sha: str) -> None:
    """Materialize and verify every base-tree gitlink before graph build."""
    expected = base_gitlinks(root, base_sha)
    if not expected:
        return
    update = run_git(
        root,
        [
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
            "--recursive",
        ],
    )
    if update.returncode != 0:
        stderr = update.stderr.strip()
        raise SelectorFailure(
            "trusted_base_submodule_materialization_failed",
            f"exit={update.returncode};stderr_sha256="
            f"{hashlib.sha256(stderr.encode()).hexdigest()}",
        )
    for relative_path, expected_head in expected:
        submodule = root / relative_path
        if not submodule.is_dir() or submodule.is_symlink():
            raise SelectorFailure(
                "trusted_base_submodule_materialization_failed",
                f"path={relative_path};detail=missing_checkout",
            )
        actual_head = (
            git_output(
                submodule,
                ["rev-parse", "HEAD"],
                "trusted_base_submodule_identity_unavailable",
            )
            .strip()
            .lower()
        )
        if actual_head != expected_head:
            raise SelectorFailure(
                "trusted_base_submodule_identity_mismatch",
                f"path={relative_path};expected={expected_head};actual={actual_head}",
            )


def base_surface_manifest(root: Path, base_sha: str) -> str:
    """Resolve the sole surface manifest from the exact base filesystem."""
    submodule = root / "vendor" / "agent-canon"
    if submodule.is_dir() and not submodule.is_symlink():
        names = git_output(
            submodule,
            ["ls-tree", "-r", "--name-only", "HEAD", "--"],
            "trusted_base_surface_manifest_unavailable",
        ).splitlines()
    else:
        names = git_output(
            root,
            ["ls-tree", "-r", "--name-only", base_sha, "--"],
            "trusted_base_surface_manifest_unavailable",
        ).splitlines()
    matches = tuple(
        name for name in names if Path(name).name == "shared-runtime-surfaces.toml"
    )
    if len(matches) != 1:
        raise SelectorFailure(
            "trusted_base_surface_manifest_unavailable",
            f"match_count={len(matches)}",
        )
    manifest = (submodule if submodule.is_dir() else root) / matches[0]
    if not manifest.is_file() or manifest.is_symlink():
        raise SelectorFailure(
            "trusted_base_surface_manifest_unavailable",
            f"path={matches[0]};detail=not_regular_file",
        )
    return matches[0]


def validate_graph_build_exit_code(process_exit_code: int, output: str) -> None:
    """Require the builder process status and JSON result status to agree."""
    try:
        payload: object = json.loads(output)
    except ValueError:
        raise SelectorFailure(
            "trusted_base_graph_result_invalid",
            "detail=invalid_json",
        ) from None
    if type(payload) is not dict:
        raise SelectorFailure(
            "trusted_base_graph_result_invalid",
            "detail=not_object",
        )
    result = cast(dict[str, object], payload)
    result_exit_code = result.get("exit_code")
    if type(result_exit_code) is not int:
        raise SelectorFailure(
            "trusted_base_graph_exit_code_mismatch",
            "field=exit_code;expected_type=integer",
        )
    if result_exit_code != process_exit_code:
        raise SelectorFailure(
            "trusted_base_graph_exit_code_mismatch",
            f"process={process_exit_code};result={result_exit_code}",
        )


def build_trusted_base_graph(
    root: Path,
    base_sha: str,
    source_root: Path | None,
) -> TrustedBaseGraph:
    """Build and validate a complete/incomplete graph from the exact base tree."""
    authorized_root = authorized_source_root(source_root)
    producer_identity = current_producer_identity(authorized_root)
    executable = graph_executable(authorized_root)
    producer = surface_manifest_producer(authorized_root)
    with tempfile.TemporaryDirectory(
        prefix="agent-canon-pr-base-",
        dir=root.parent,
    ) as temp_dir:
        base_root = Path(temp_dir) / "checkout"
        clone = run_git(
            root,
            [
                "clone",
                "--local",
                "--no-hardlinks",
                "--no-checkout",
                "--",
                str(root),
                str(base_root),
            ],
        )
        if clone.returncode != 0:
            raise SelectorFailure(
                "trusted_base_graph_unavailable",
                f"operation=clone;exit={clone.returncode}",
            )
        checked_out = run_git(
            base_root,
            ["checkout", "--detach", "--quiet", base_sha],
        )
        if checked_out.returncode != 0:
            raise SelectorFailure(
                "trusted_base_graph_unavailable",
                f"operation=checkout;exit={checked_out.returncode}",
            )
        resolved_head = git_output(
            base_root,
            ["rev-parse", "HEAD"],
            "trusted_base_graph_unavailable",
        ).strip()
        if resolved_head != base_sha:
            raise SelectorFailure(
                "trusted_base_graph_identity_mismatch",
                f"expected={base_sha};actual={resolved_head}",
            )
        materialize_base_submodules(base_root, base_sha)
        manifest = base_surface_manifest(base_root, base_sha)

        build = subprocess.run(
            [
                str(executable),
                "graph",
                "build",
                "--root",
                str(base_root),
                "--profile",
                GRAPH_PROFILE,
                "--format",
                "json",
                "--surface-manifest-producer",
                str(producer),
                "--surface-manifest-producer-identity",
                json.dumps(
                    producer_identity.json(),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "--surface-manifest",
                manifest,
            ],
            cwd=base_root,
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if build.returncode not in {0, 1}:
            stderr = build.stderr.strip()
            raise SelectorFailure(
                "trusted_base_graph_build_failed",
                f"exit={build.returncode};stderr_sha256="
                f"{hashlib.sha256(stderr.encode()).hexdigest()}",
            )
        if not build.stdout.strip():
            raise SelectorFailure(
                "trusted_base_graph_build_failed",
                f"exit={build.returncode};stdout=empty",
            )
        validate_graph_build_exit_code(build.returncode, build.stdout)
        result_path = (
            base_root / ".agent-canon" / "knowledge-graph" / "graph-build.json"
        )
        try:
            result_path.write_text(build.stdout, encoding="utf-8")
        except OSError:
            raise SelectorFailure(
                "trusted_base_graph_build_failed",
                "result_write=failed",
            ) from None
        identity = graph_build_identity(
            base_root,
            result_path,
            allow_complete=True,
            expected_producer_identity=producer_identity,
        )
        status = subprocess.run(
            [
                str(executable),
                "graph",
                "status",
                "--root",
                str(base_root),
                "--profile",
                GRAPH_PROFILE,
                "--format",
                "json",
            ],
            cwd=base_root,
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if status.returncode not in {0, 2} or not status.stdout.strip():
            raise SelectorFailure(
                "trusted_base_graph_status_unavailable",
                f"exit={status.returncode};stdout=empty"
                if not status.stdout.strip()
                else f"exit={status.returncode}",
            )
        try:
            status_payload: object = json.loads(status.stdout)
        except ValueError:
            raise SelectorFailure(
                "trusted_base_graph_status_invalid",
                "detail=invalid_json",
            ) from None
        if (
            type(status_payload) is not dict
            or type(status_payload.get("exit_code")) is not int
            or status_payload["exit_code"] != status.returncode
        ):
            raise SelectorFailure(
                "trusted_base_graph_status_exit_code_mismatch",
                f"process={status.returncode}",
            )
        status_path = (
            base_root / ".agent-canon" / "knowledge-graph" / "graph-status.json"
        )
        try:
            status_path.write_text(status.stdout, encoding="utf-8")
        except OSError:
            raise SelectorFailure(
                "trusted_base_graph_status_unavailable",
                "result_write=failed",
            ) from None
        validate_graph_status_binding(
            status_path,
            identity,
            expected_status=identity.build_status,
        )
        _, _, diagnostics = read_bound_graph_acceptance_facts(
            identity,
            base_sha,
        )
        deduplicated = deduplicate_diagnostics(diagnostics)
        return TrustedBaseGraph(
            identity.snapshot_head,
            identity.input_fingerprint,
            identity.graph_fingerprint,
            identity.producer_identity,
            identity.publication,
            identity.durability,
            identity.integration_identity.verified,
            identity.build_status,
            deduplicated,
        )


def evaluate_built_graph(
    root: Path,
    graph_result_path: Path,
    environment: Mapping[str, str],
    trusted_base_sha: str | None = None,
    source_root: Path | None = None,
    status_result_path: Path | None = None,
) -> GraphAcceptance:
    """Compare head diagnostics with a graph built from the trusted base."""
    diff = load_diff(root, environment, trusted_base_sha)
    producer_identity = current_producer_identity(source_root)
    build_identity = graph_build_identity(
        root,
        graph_result_path,
        expected_producer_identity=producer_identity,
    )
    status_path = status_result_path or graph_result_path.with_name("graph-status.json")
    status_binding = validate_graph_status_binding(
        status_path,
        build_identity,
        expected_status="incomplete",
    )
    node_paths, adjacency, diagnostics = read_bound_graph_acceptance_facts(
        build_identity,
        diff.head_sha,
    )
    assert_status_result_identity(status_binding.path, status_binding.file_identity)
    full_scope = migration_requested(environment)
    reachable_paths = graph_reachable_paths(
        node_paths,
        adjacency,
        diff.changed_paths,
        full_scope,
    )
    base_graph = build_trusted_base_graph(root, diff.base_sha, source_root)
    if base_graph.producer_identity != build_identity.producer_identity:
        raise SelectorFailure(
            "graph_identity_mismatch",
            "owners=trusted_base_graph,graph_build_result;fields=producer_identity",
        )
    head_diagnostics = deduplicate_diagnostics(diagnostics)
    base_by_identity = {
        diagnostic_identity_key(diagnostic): diagnostic
        for diagnostic in base_graph.diagnostics
    }
    blocking: list[ClassifiedDiagnostic] = []
    baseline: list[ClassifiedDiagnostic] = []
    for diagnostic in head_diagnostics:
        source_path = diagnostic["source_path"]
        target_path = diagnostic["target_path"]
        related = (
            full_scope
            or source_path in reachable_paths
            or path_is_changed(source_path, diff.changed_paths)
            or (target_path and path_is_changed(target_path, diff.changed_paths))
        )
        base_diagnostic = base_by_identity.get(diagnostic_identity_key(diagnostic))
        worsened = bool(
            base_diagnostic is not None
            and severity_rank(diagnostic["severity"])
            > severity_rank(base_diagnostic["severity"])
        )
        if related and (base_diagnostic is None or worsened):
            blocking.append(
                classify_diagnostic(
                    diagnostic,
                    base_match=base_diagnostic is not None,
                    worsened=worsened,
                    classification="changed_responsibility",
                )
            )
            continue
        if not related and not base_source_is_unchanged(root, diff, source_path):
            blocking.append(
                classify_diagnostic(
                    diagnostic,
                    base_match=base_diagnostic is not None,
                    worsened=worsened,
                    classification="base_identity_unconfirmed",
                )
            )
            continue
        baseline.append(
            classify_diagnostic(
                diagnostic,
                base_match=base_diagnostic is not None,
                worsened=worsened,
                classification="unchanged_base_diagnostic",
            )
        )
    report: dict[str, object] = {
        "schema": "agent-canon.pr-graph-acceptance.v1",
        "base_sha": diff.base_sha,
        "head_sha": diff.head_sha,
        "graph_identity": build_identity.report(),
        "trusted_base_graph": base_graph.report(diff.base_sha),
        "changed_paths": list(diff.changed_paths),
        "changed_paths_sha256": changed_paths_digest(diff.changed_paths),
        "full_scope": full_scope,
        "reachable_paths": sorted(reachable_paths),
        "head_diagnostics": len(head_diagnostics),
        "blocking_diagnostics": blocking,
        "baseline_diagnostics": baseline,
    }
    report_digest = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence = (
        f"base={diff.base_sha};changed_paths_sha256={changed_paths_digest(diff.changed_paths)};"
        f"reachable={len(reachable_paths)};head_diagnostics={len(head_diagnostics)};"
        f"blocking={len(blocking)};"
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
    changed_path_packet: Path | None = None,
) -> Selection:
    """Return the strict graph selection for one parent PR."""
    source_root = authorized_source_root(source_root)
    diff = load_diff(root, environment, trusted_base_sha)
    if changed_path_packet is not None:
        write_changed_path_packet(root, diff, changed_path_packet)
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
    if changed_path_packet is not None:
        evidence.append(f"changed_path_packet={changed_path_packet}")
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
    if args.producer_identity:
        try:
            identity = current_producer_identity(Path(args.source_root).resolve())
        except (OSError, SelectorFailure) as error:
            if isinstance(error, SelectorFailure):
                print(
                    f"AGENT_CANON_PR_PRODUCER_IDENTITY=fail;reason={error.reason};evidence={error.evidence}"
                )
            else:
                print(
                    "AGENT_CANON_PR_PRODUCER_IDENTITY=fail;reason=producer_identity_unavailable"
                )
            return EXIT_FAILURE
        print(json.dumps(identity.json(), sort_keys=True, separators=(",", ":")))
        return EXIT_REQUIRED
    if args.evaluate_built_graph:
        if not args.graph_result or not args.status_result or not args.report_out:
            emit_acceptance(
                "fail",
                "graph_acceptance_arguments_missing",
                "required=graph_result,status_result,report_out",
            )
            return EXIT_FAILURE
        try:
            acceptance = evaluate_built_graph(
                Path(args.root).resolve(),
                Path(args.graph_result).resolve(),
                os.environ,
                args.trusted_base_sha,
                Path(args.source_root).resolve(),
                Path(args.status_result).resolve(),
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
            Path(args.changed_path_packet).resolve()
            if args.changed_path_packet
            else None,
        )
    except SelectorFailure as error:
        emit("fail", error.reason, error.evidence)
        return EXIT_FAILURE
    emit(selection.status, selection.reason, selection.evidence)
    return EXIT_REQUIRED if selection.status == "required" else EXIT_SKIPPED


if __name__ == "__main__":
    raise SystemExit(main())
