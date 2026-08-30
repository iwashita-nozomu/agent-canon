#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides smoke test research perspective pack agent workflow automation.
# upstream implementation ./packets.py owns active design packet types.
# upstream implementation ./team_config.py owns team and role configuration.
# upstream implementation ./agent_team.py owns run bundle orchestration.
# upstream implementation ./workspace_scope.py owns role write scope.
# @dependency-end

"""Smoke test the research perspective review pack runtime surfaces."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

if __package__:
    from tools.runtime.source.agent_canon_source_root import resolve_agent_canon_source_root
else:
    from tools.runtime.source.agent_canon_source_root import resolve_agent_canon_source_root

if __package__:
    from tools.agent.orchestration.packets import ActiveDesignPacketConfig
else:
    from tools.agent.orchestration.packets import ActiveDesignPacketConfig

if __package__:
    from tools.agent.orchestration.team_config import (
        RunBundleSpec,
        load_task_catalog,
        load_team_config,
        resolve_role,
    )
else:
    from tools.agent.orchestration.team_config import (
        RunBundleSpec,
        load_task_catalog,
        load_team_config,
        resolve_role,
    )

if __package__:
    from tools.agent.orchestration.agent_team import create_run_bundle, run_active_design_packet
else:
    from tools.agent.orchestration.agent_team import create_run_bundle, run_active_design_packet

if __package__:
    from tools.repository.workspace.workspace_scope import resolve_repository_roots, resolve_role_write_scope
else:
    from tools.repository.workspace.workspace_scope import resolve_repository_roots, resolve_role_write_scope

ROOT = Path(__file__).resolve().parents[2]
from tools.repository.workspace.parent_root_side_effects import (  # noqa: E402
    ParentRootAttestationReceipt,
    ParentRootAttestationRequest,
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    attest_parent_root,
)
from tools.runtime.artifacts.runtime_artifacts import runtime_artifact_boundary  # noqa: E402

BASE_RESEARCH_ROLE_IDS = (
    "researcher",
    "research_reviewer",
    "experimenter",
    "experiment_reviewer",
)
PERSPECTIVE_ROLE_IDS = (
    "reproducibility_reviewer",
    "scientific_computing_reviewer",
    "benchmark_reviewer",
    "artifact_reviewer",
    "fair_data_reviewer",
    "ml_science_reviewer",
)
TRIAGE_ROLE_IDS = (
    "reproducibility_reviewer",
    "artifact_reviewer",
)
ROLE_TO_ARTIFACT_KEY = {
    "reproducibility_reviewer": "reproducibility_review",
    "scientific_computing_reviewer": "scientific_computing_review",
    "benchmark_reviewer": "benchmark_review",
    "artifact_reviewer": "artifact_review",
    "fair_data_reviewer": "fair_data_review",
    "ml_science_reviewer": "ml_science_review",
}


def _parent_capability(
    purpose: str,
) -> tuple[ParentRootSideEffectBoundary, ParentRootAttestationReceipt]:
    configured = os.environ.get("AGENT_CANON_PARENT_ROOT", "").strip()
    if not configured:
        raise ParentRootSideEffectError(ParentRootReject.HANDOFF_INVALID, f"{purpose}: explicit parent root is required")
    parent = Path(configured)
    attestation = attest_parent_root(
        ParentRootAttestationRequest(cwd=parent, explicit_root=parent, purpose=purpose)
    )
    return ParentRootSideEffectBoundary(), attestation


def _ensure_parent(path: Path, purpose: str) -> None:
    boundary, attestation = _parent_capability(purpose)
    boundary.ensure_parent_owned_directory(attestation, path, purpose)


def _write_parent(path: Path, data: bytes, purpose: str) -> None:
    boundary, attestation = _parent_capability(purpose)
    boundary.write_parent_owned_file(attestation, path, data, purpose)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Create a temporary run bundle and verify the research perspective review pack."
    )
    parser.add_argument(
        "--task",
        default="research perspective pack smoke test",
        help="Task label to embed in the temporary bundle.",
    )
    parser.add_argument(
        "--owner",
        default="codex",
        help="Owner label to embed in the temporary bundle.",
    )
    parser.add_argument(
        "--run-id",
        default="smoke-research-perspective-pack",
        help="Run id to use inside the temporary bundle.",
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional fixture workspace root. Defaults to the current AgentCanon "
            "source root without preparing a fixture."
        ),
    )
    parser.add_argument(
        "--report-root",
        help="Optional report root. Defaults to a temporary report root.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep the temporary report directory when the default is used.",
    )
    return parser


def ensure(condition: bool, message: str) -> None:
    """Raise when one expected condition is not met."""
    if not condition:
        raise RuntimeError(message)


def find_by_id(entries: object, entry_id: str) -> dict[str, object]:
    """Return one mapping entry from a list of id-tagged items."""
    ensure(isinstance(entries, list), f"expected list while looking for {entry_id}")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return entry
    raise RuntimeError(f"missing entry with id={entry_id}")


def prepare_workspace(workspace_root: Path, source_root: Path) -> None:
    """Create a minimal workspace that satisfies manifest scope resolution."""
    for directory in (".codex", "python", "documents", "reports/runtime"):
        _ensure_parent(workspace_root / directory, "research-perspective-smoke")
    _write_parent(
        workspace_root / ".codex" / "config.toml",
        (source_root / ".codex" / "config.toml").read_bytes(),
        "research-perspective-smoke",
    )
    _write_parent(
        workspace_root / "WORKTREE_SCOPE.md",
        "\n".join(
            [
                "# Worktree Scope",
                "",
                "## Editable Directories",
                "- `python`",
                "- `documents`",
                "",
                "## Runtime Output Directories",
                "- `reports/runtime`",
                "",
            ]
        ).encode("utf-8"),
        "research-perspective-smoke",
    )


def validate_task_catalog(source_root: Path) -> None:
    """Check that the task catalog exposes the review pack."""
    data = yaml.safe_load(
        (source_root / "agents" / "task_catalog.yaml").read_text(encoding="utf-8")
    )
    ensure(isinstance(data, dict), "task catalog did not parse as a mapping")

    research_family = find_by_id(
        data.get("workflow_families"), "research_driven_change"
    )
    family_roles = research_family.get("roles", {})
    ensure(isinstance(family_roles, dict), "research family roles must be a mapping")
    family_specialists = family_roles.get("specialists", [])
    ensure(
        isinstance(family_specialists, list),
        "research family specialists must be a list",
    )
    ensure("T9" in research_family.get("tasks", []), "research family is missing T9")

    task_t9 = find_by_id(data.get("tasks"), "T9")
    t9_specialists = task_t9.get("specialists", [])
    ensure(isinstance(t9_specialists, list), "T9 specialists must be a list")

    review_pack = find_by_id(data.get("review_packs"), "research_perspective_review")
    pack_specialists = review_pack.get("specialists", [])
    ensure(isinstance(pack_specialists, list), "review pack specialists must be a list")
    optional_for_tasks = review_pack.get("optional_for_tasks", [])
    ensure(
        isinstance(optional_for_tasks, list),
        "review pack optional_for_tasks must be a list",
    )
    ensure("T4" in optional_for_tasks, "full review pack must be optional for T4")
    ensure("T5" in optional_for_tasks, "full review pack must be optional for T5")
    ensure("T9" in optional_for_tasks, "full review pack must be optional for T9")

    triage_pack = find_by_id(data.get("review_packs"), "research_perspective_triage")
    triage_specialists = triage_pack.get("specialists", [])
    ensure(
        isinstance(triage_specialists, list), "triage pack specialists must be a list"
    )
    triage_default_for_tasks = triage_pack.get("default_for_tasks", [])
    ensure(
        isinstance(triage_default_for_tasks, list),
        "triage default_for_tasks must be a list",
    )
    for task_id in ("T4", "T5", "T9", "T13"):
        ensure(
            task_id in triage_default_for_tasks,
            f"triage pack must default to {task_id}",
        )

    for role_id in PERSPECTIVE_ROLE_IDS:
        ensure(
            role_id in family_specialists,
            f"research family missing specialist {role_id}",
        )
        ensure(role_id in pack_specialists, f"review pack missing specialist {role_id}")
    for role_id in TRIAGE_ROLE_IDS:
        ensure(role_id in t9_specialists, f"T9 missing triage specialist {role_id}")
        ensure(
            role_id in triage_specialists, f"triage pack missing specialist {role_id}"
        )


def validate_runtime_surfaces(
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig,
    source_root: Path,
) -> None:
    """Check that config, agent inventory, templates, and bundle outputs align."""
    config = load_team_config(source_root / "agents" / "agents_config.json")
    manifest_path = report_dir / config.artifacts["team_manifest"]
    manifest_text = manifest_path.read_text(encoding="utf-8")

    for role_id in PERSPECTIVE_ROLE_IDS:
        role = resolve_role(config, role_id)
        artifact_key = ROLE_TO_ARTIFACT_KEY[role_id]
        artifact_name = config.artifacts[artifact_key]
        artifact_path = report_dir / artifact_name
        codex_agent_path = source_root / ".codex" / "agents" / f"{role_id}.toml"

        if not codex_agent_path.is_file():
            raise RuntimeError(f"missing Codex agent definition: {codex_agent_path}")
        if not artifact_path.is_file():
            raise RuntimeError(f"missing generated artifact: {artifact_path}")
        if role.required_outputs != (artifact_name,):
            raise RuntimeError(
                f"role {role_id} required_outputs mismatch: {role.required_outputs} vs {artifact_name}"
            )
        if role.write_policy.allowed_artifacts != (artifact_key,):
            raise RuntimeError(
                f"role {role_id} artifact policy mismatch: {role.write_policy.allowed_artifacts}"
            )

        scope = resolve_role_write_scope(
            config=config,
            role=role,
            report_dir=report_dir,
            workspace_root=workspace_root,
            active_design_packet=active_design_packet,
        )
        if scope.mode != "artifacts_only":
            raise RuntimeError(
                f"role {role_id} should be artifacts_only, got {scope.mode}"
            )
        if artifact_path.resolve() not in scope.allowed_files:
            raise RuntimeError(
                f"role {role_id} missing allowed file for {artifact_path}"
            )

        ensure(
            f"  - id: {role_id}" in manifest_text, f"manifest missing role {role_id}"
        )
        ensure(
            f"      - {artifact_name}" in manifest_text,
            f"manifest missing artifact {artifact_name}",
        )


def main() -> int:
    """Run the smoke test."""
    args = build_parser().parse_args()
    source_resolution = resolve_agent_canon_source_root(Path(__file__).resolve())
    source_root = source_resolution.source_root
    runtime_temp: tempfile.TemporaryDirectory[str] | None = None

    if args.workspace_root is None:
        workspace_root = source_root
    else:
        workspace_root = Path(args.workspace_root).resolve()
        _ensure_parent(workspace_root, "research-perspective-smoke")

    if args.report_root is None:
        runtime_boundary = runtime_artifact_boundary(source_root, create=True)
        temp_parent = runtime_boundary.ensure_directory(
            "tmp/research-perspective-smoke"
        )
        runtime_temp = tempfile.TemporaryDirectory(
            prefix="research-pack-", dir=temp_parent
        )
        report_root = Path(runtime_temp.name)
    else:
        report_root = Path(args.report_root).resolve()
        _ensure_parent(report_root, "research-perspective-smoke")

    primary_error: BaseException | None = None
    try:
        if args.workspace_root is not None:
            prepare_workspace(workspace_root, source_root)
        validate_task_catalog(source_root)

        config = load_team_config(source_root / "agents" / "agents_config.json")
        task_catalog = load_task_catalog(config, root=source_root)
        specialist_roles = tuple(
            resolve_role(config, role_id)
            for role_id in BASE_RESEARCH_ROLE_IDS + PERSPECTIVE_ROLE_IDS
        )
        roles = config.always_on_roles + specialist_roles
        created_at = datetime.now(UTC).replace(microsecond=0)
        created_at_iso = created_at.isoformat().replace("+00:00", "Z")
        report_dir = (report_root / args.run_id).resolve()
        repository_roots = resolve_repository_roots(
            workspace_root.resolve(),
            report_root,
            source_root=source_root,
            canon_root=source_resolution.canon_root,
        )

        run_spec = RunBundleSpec(
            config=config,
            report_dir=report_dir,
            run_id=args.run_id,
            task=args.task,
            owner=args.owner,
            created_at_iso=created_at_iso,
            roles=roles,
            workspace_root=workspace_root.resolve(),
            agentcanon_source_root=repository_roots.agentcanon_source_root,
            report_root=repository_roots.report_root,
            repository_roots=repository_roots,
            task_catalog=task_catalog,
        )
        active_design_packet = run_active_design_packet(run_spec)
        create_run_bundle(run_spec)

        validate_runtime_surfaces(
            report_dir,
            workspace_root.resolve(),
            active_design_packet,
            repository_roots.agentcanon_source_root,
        )

        print(f"RUN_ID={args.run_id}")
        print(f"REPORT_DIR={report_dir}")
        print(f"WORKSPACE_ROOT={workspace_root.resolve()}")
        print(f"ACTIVE_ROLES={','.join(role.id for role in roles)}")
        print("SMOKE_TEST=pass")
        return 0
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if not args.keep_temp:
            cleanup_error: OSError | None = None
            if runtime_temp is not None:
                try:
                    runtime_temp.cleanup()
                except OSError as exc:
                    cleanup_error = exc
            if cleanup_error is not None:
                if primary_error is not None:
                    raise cleanup_error from primary_error
                raise cleanup_error


if __name__ == "__main__":
    raise SystemExit(main())
