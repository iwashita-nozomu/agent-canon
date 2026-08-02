#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Selects parent PR strict dependency graph gating from canonical profiles, dependency surfaces, and a validated PR diff base.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json canonical validation profile owner
# upstream design ../../documents/design/dependency-manifest-design.md canonical dependency surface owner and parent gate contract
# downstream implementation ./check_agent_canon_pr.sh consumes the typed selector verdict
# downstream implementation ../../tests/tools/test_agent_canon_pr_graph_selector.py verifies required, skipped, and fail-closed selections
# @dependency-end
"""Select whether a parent AgentCanon PR requires strict graph completeness."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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


def build_parser() -> argparse.ArgumentParser:
    """Create the selector CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Parent repository root.")
    parser.add_argument(
        "--source-root",
        required=True,
        help="AgentCanon source root containing canonical owner manifests.",
    )
    return parser


def emit(status: str, reason: str, evidence: str) -> None:
    """Emit one line-safe typed verdict."""
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH={status}")
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH_REASON={reason}")
    print(f"AGENT_CANON_PR_DEPENDENCY_GRAPH_EVIDENCE={evidence}")


def run_git(root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one non-mutating Git command."""
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def git_output(
    root: Path,
    args: Sequence[str],
    failure_reason: str,
) -> str:
    """Return Git stdout or raise one typed failure."""
    result = run_git(root, args)
    if result.returncode != 0:
        command = args[0] if args else "unknown"
        stderr = result.stderr.strip().replace("\n", " ")
        evidence = f"command=git_{command};exit={result.returncode}"
        if stderr:
            evidence += f";stderr_sha256={hashlib.sha256(stderr.encode()).hexdigest()}"
        raise SelectorFailure(failure_reason, evidence)
    return result.stdout


def trusted_base_ref(environment: Mapping[str, str]) -> tuple[str, str]:
    """Resolve a CI event base or an explicit validated local/test override."""
    override = environment.get("AGENT_CANON_PR_BASE_REF", "").strip()
    github_actions = environment.get("GITHUB_ACTIONS", "").lower() == "true"
    if github_actions:
        if override:
            raise SelectorFailure(
                "ci_base_override_forbidden",
                "source=AGENT_CANON_PR_BASE_REF",
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


def load_diff(root: Path, environment: Mapping[str, str]) -> DiffEvidence:
    """Validate the selected base and load exact changed-path and patch evidence."""
    base_ref, base_source = trusted_base_ref(environment)
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


def select(
    root: Path,
    source_root: Path,
    environment: Mapping[str, str],
) -> Selection:
    """Return the strict graph selection for one parent PR."""
    diff = load_diff(root, environment)
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
    try:
        selection = select(
            Path(args.root).resolve(),
            Path(args.source_root).resolve(),
            os.environ,
        )
    except SelectorFailure as error:
        emit("fail", error.reason, error.evidence)
        return EXIT_FAILURE
    emit(selection.status, selection.reason, selection.evidence)
    return EXIT_REQUIRED if selection.status == "required" else EXIT_SKIPPED


if __name__ == "__main__":
    raise SystemExit(main())
