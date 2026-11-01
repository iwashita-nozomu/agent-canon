# @dependency-start
# contract tool
# responsibility Owns optional run-bundle creation and role/profile readback.
# upstream design ../../../README.md shared automation index
# upstream implementation ../values.py refines decoded command payloads
# @dependency-end

"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.agent.orchestration.agent_team import (
    PreparedRunBundle,
    dispatch_issue_worker,
    prepare_run_bundle,
)
from tools.agent.orchestration.implementation_dispatch import (
    format_agent_type_selections,
    parse_agent_type_selections,
    validate_agent_type_selections,
)
from tools.agent.orchestration.packets import (
    ACTIVE_DESIGN_PACKET_SCHEMA,
    MATHEMATICAL_INTENT_PACKET_SCHEMA,
    ActiveDesignPacketConfig,
    MathematicalIntentPacket,
    math_intent_route_id_from_context,
    mathematical_intent_route_config,
    mathematical_intent_route_for_task,
    normalize_mathematical_intent_packet,
    parse_active_design_packet_input,
    resolve_cross_cutting_document_packet,
    resolve_role_document_packet,
    role_specific_document_entries,
)
from tools.runtime.values import is_string_object_dict, is_string_object_mapping
from tools.agent.orchestration.team_config import (
    AgentTypeSelection,
    Role,
    RunBundleSpec,
    TaskCatalog,
    TeamConfig,
    codex_agent_model_matrix_for_roles,
    default_review_pack_ids_for_task,
    default_specialists_for_task,
    enable_choices,
    expand_enabled_specialists,
    load_task_catalog,
    load_team_config,
    resolve_task_spec,
    resolve_workflow_family,
    select_roles,
    task_ids,
)
from tools.agent.orchestration.workflow_context import (
    StoreResult,
    context_from_workflows,
    store_workflow_context,
)
from tools.repository.workspace.workspace_scope import (
    make_run_id,
    resolve_report_root,
    resolve_repository_roots,
)
from tools.runtime.artifacts.runtime_artifacts import (
    RuntimeArtifactBoundary,
    runtime_artifact_boundary,
)
from tools.runtime.authority.task_authority import (
    AUTHORITY_FILE_NAME,
    hash_baseline_bytes,
)
from tools.runtime.authority.writer_target import (
    WriterTarget,
    WriterTargetError,
    parse_writer_target,
)
from tools.runtime.lifecycle.workflow_monitor import append_monitoring
from tools.runtime.manifest.manifest_rendering import (
    checkout_identity_policy_output_lines,
    contract_complete_implementation_policy_output_lines,
    coordination_capability_policy_output_lines,
    default_quality_check_policy_output_lines,
    language_review_candidates,
    pre_handoff_gate_status_output_lines,
    pre_handoff_scope_policy_output_lines,
    public_command_for_layout,
    repo_tool_routing_policy_output_lines,
    suggested_public_skills,
    user_facing_language_policy_output_lines,
)
from tools.runtime.source.agent_canon_source_root import (
    RepositoryRoots,
    resolve_agent_canon_source_root,
)


@dataclass(frozen=True)
class BootstrapRunContext:
    """Resolved run metadata for bootstrap output and bundle creation."""

    created_at_iso: str
    report_root: Path
    run_id: str
    report_dir: Path
    manual_specialists: tuple[str, ...]
    enabled_specialists: tuple[str, ...]
    task_default_specialists: tuple[str, ...]
    language_review_candidates: tuple[str, ...]
    default_review_pack_ids: tuple[str, ...]
    workflow_family_id: str | None
    workflow_family_name: str | None
    adversarial_required: bool = False
    math_intent_route: str | None = None
    issue_worker_candidate: Mapping[str, object] | None = None
    repository_roots: RepositoryRoots | None = None


@dataclass(frozen=True)
class BootstrapRuntime:
    """Runtime objects created by bootstrap before output."""

    roles: tuple[Role, ...]
    created_files: tuple[str, ...]
    active_pointer: Path
    agent_type_selections: tuple[AgentTypeSelection, ...]
    active_design_packet: ActiveDesignPacketConfig
    math_intent_packet: MathematicalIntentPacket | None = None
    issue_worker_dispatch: Mapping[str, object] | None = None
    selected_skills: tuple[str, ...] = ()


def suggested_skills(
    task_id: str | None,
    workflow_family_id: str | None,
    task_text: str = "",
    *,
    source_root: Path | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return the public skills that should be read before work starts."""
    return suggested_public_skills(
        task_id,
        workflow_family_id,
        task_text,
        source_root=source_root,
        issue_worker_candidate=issue_worker_candidate,
    )


def codex_agents_for_role(config: TeamConfig, role_id: str) -> tuple[str, ...]:
    """Return Codex subagent candidates for one permanent role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role.id == role_id:
            return role.codex_agents
    return ()


def document_packet_output(
    config: TeamConfig,
    role_id: str,
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render one role's explicit document packet as a CSV-like path list."""
    role = next(
        role
        for role in config.always_on_roles + config.specialist_roles
        if role.id == role_id
    )
    packet = resolve_role_document_packet(
        config,
        role,
        report_dir,
        workspace_root,
        active_design_packet,
        agentcanon_source_root,
    )
    return ",".join(str(entry.path) for entry in packet.read_before_work)


def cross_cutting_document_packet_output(
    workspace_root: Path,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render the common cross-cutting document packet."""
    return ",".join(
        str(entry.path)
        for entry in resolve_cross_cutting_document_packet(
            workspace_root,
            agentcanon_source_root,
        )
    )


def build_parser(
    enable_names: tuple[str, ...], task_choices: tuple[str, ...]
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard external-runtime reports/agents/<run-id> bundle "
            "for one agent-team run."
        )
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Short task description for the run.",
    )
    parser.add_argument(
        "--owner",
        required=True,
        help="Human or agent responsible for the run.",
    )
    parser.add_argument(
        "--task-id",
        choices=task_choices,
        help=(
            "Optional task catalog id. Expands default specialists and review packs "
            "for that task."
        ),
    )
    parser.add_argument(
        "--issue-worker-candidate",
        metavar="JSON",
        help=(
            "Explicit JSON IssueWorker candidate that selects the T15 publisher "
            "role. Other workflows ignore this input."
        ),
    )
    parser.add_argument(
        "--run-id",
        help=("Optional explicit run id. Defaults to a timestamped slug."),
    )
    parser.add_argument(
        "--active-design-packet",
        metavar="JSON",
        help=(
            f"Atomic {ACTIVE_DESIGN_PACKET_SCHEMA} JSON object. All schema, path, "
            "document_flow_required, and clause_registry fields are required."
        ),
    )
    parser.add_argument(
        "--math-intent-packet",
        metavar="JSON",
        help=(
            f"Atomic {MATHEMATICAL_INTENT_PACKET_SCHEMA} JSON object. Required when "
            "the selected task declares a mathematical intent route."
        ),
    )
    parser.add_argument(
        "--writer-targets",
        metavar="JSON",
        help=(
            "Optional JSON object mapping role/instance identities to "
            "repository-topic-clone writer_target values for the run manifest."
        ),
    )
    parser.add_argument(
        "--enable",
        action="append",
        choices=enable_names,
        default=[],
        help="Enable a specialist role or review pack. Repeat the flag to enable multiple entries.",
    )
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help=(
            "Optional changed path hint. Repeat to populate explicit language-review "
            "candidates."
        ),
    )
    parser.add_argument(
        "--select-agent-type",
        action="append",
        default=[],
        metavar="ROLE_ID=AGENT_TYPE:EVIDENCE",
        help=(
            "Optional native pre-route role-to-agent selection with evidence; "
            "preserved in the selected route readback."
        ),
    )
    parser.add_argument(
        "--no-language-review-candidates",
        action="store_true",
        help=(
            "Disable language-review candidate discovery from changed paths or git status."
        ),
    )
    parser.add_argument(
        "--full-team",
        action="store_true",
        help="Enable every specialist role for this run.",
    )
    parser.add_argument(
        "--no-default-review-packs",
        action="store_true",
        help=(
            "When --task-id is set, skip review packs whose default_for_tasks "
            "contains that task."
        ),
    )
    parser.add_argument(
        "--report-root",
        help=(
            "Optional external directory that will contain per-run report folders. "
            "Defaults below --runtime-root."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        help=(
            "Explicit external runtime root for reports, active-run state, "
            "ledgers, and receipts. Defaults to AGENT_CANON_RUNTIME_ROOT."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve run-local reports and current-checkout path authority.",
    )
    return parser


def parse_issue_worker_candidate(value: str | None) -> Mapping[str, object] | None:
    """Parse one explicit IssueWorker candidate without inferring candidates."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("issue_worker_candidate:invalid_json") from exc
    if not is_string_object_dict(parsed) or not parsed:
        raise RuntimeError("issue_worker_candidate:must_be_nonempty_object")
    return parsed


def parse_math_intent_packet_input(value: str | None) -> Mapping[str, object] | None:
    """Parse one explicit math packet without inferring mathematical content."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("mathematical_intent_packet:invalid_json") from exc
    if not is_string_object_dict(parsed) or not parsed:
        raise RuntimeError("mathematical_intent_packet:must_be_nonempty_object")
    return parsed


def resolve_bootstrap_context(
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    workspace_root: Path,
    repository_roots: RepositoryRoots | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> BootstrapRunContext:
    """Resolve workflow family, specialists, and report paths for one run."""
    created_at = datetime.now(UTC).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    # The parent capability authorizes the eventual write; it does not replace
    # the caller's logical workspace/report-root selection.
    report_root = (
        repository_roots.report_root
        if repository_roots is not None
        else resolve_report_root(
            args.report_root,
            runtime_root=args.runtime_root,
        )
    )
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    manual_specialists = expand_enabled_specialists(config, catalog, tuple(args.enable))
    enabled_specialists = list(manual_specialists)
    task_default_specialists: tuple[str, ...] = ()
    default_review_pack_ids: tuple[str, ...] = ()
    workflow_family_id: str | None = None
    workflow_family_name: str | None = None
    adversarial_required = False
    if args.task_id is not None:
        task_spec = resolve_task_spec(catalog, args.task_id)
        workflow_family_id = str(task_spec["family"])
        workflow_family = resolve_workflow_family(catalog, workflow_family_id)
        workflow_family_name = str(workflow_family["name"])
        # The comprehensive family is the catalog-owned cross-owner route.
        # Bounded routes enable Terra explicitly through --enable terra.
        adversarial_required = workflow_family_id == "comprehensive_development"
        task_default_specialists = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=args.task_id,
            include_default_review_packs=not args.no_default_review_packs,
        )
        if not args.no_default_review_packs:
            default_review_pack_ids = default_review_pack_ids_for_task(
                catalog,
                args.task_id,
            )
        # Task-catalog specialists and default review packs remain candidates;
        # explicit enablement or an owner-critical route activates them.
    selected_route_skills = suggested_skills(
        args.task_id,
        workflow_family_id,
        args.task,
        source_root=(
            repository_roots.agentcanon_source_root if repository_roots else None
        ),
        issue_worker_candidate=issue_worker_candidate,
    )
    math_route = mathematical_intent_route_for_task(
        catalog,
        args.task_id,
        selected_route_skills,
    )
    math_route = math_intent_route_id_from_context(
        selected_route_skills,
        packet_present=bool(args.math_intent_packet),
        explicit_route_id=math_route,
    )
    if math_route is not None and args.math_intent_packet:
        reviewer = str(
            (mathematical_intent_route_config(catalog, math_route) or {}).get(
                "reviewer", ""
            )
        ).strip()
        if reviewer and reviewer not in enabled_specialists:
            enabled_specialists.append(reviewer)
    language_candidates: tuple[str, ...] = ()
    if not args.no_language_review_candidates:
        language_candidates = language_review_candidates(
            workspace_root=workspace_root,
            changed_paths=tuple(args.changed_path),
        )
    return BootstrapRunContext(
        created_at_iso=created_at_iso,
        report_root=report_root,
        run_id=run_id,
        report_dir=report_dir,
        manual_specialists=tuple(manual_specialists),
        enabled_specialists=tuple(enabled_specialists),
        task_default_specialists=task_default_specialists,
        language_review_candidates=language_candidates,
        default_review_pack_ids=default_review_pack_ids,
        workflow_family_id=workflow_family_id,
        workflow_family_name=workflow_family_name,
        adversarial_required=adversarial_required,
        math_intent_route=math_route,
        issue_worker_candidate=issue_worker_candidate,
        repository_roots=repository_roots,
    )


def selected_review_roles(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return role ids that should appear in the review declaration."""
    fixed_review_roles = {
        "reviewer",
        "verifier",
        "auditor",
        "docs_workflow_steward",
    }
    return tuple(
        role.id
        for role in roles
        if role.id.endswith("_reviewer")
        or role.id in fixed_review_roles
        or "adversarial_contradiction_validation" in role.owns
    )


def emit_bootstrap_output(
    *,
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    context: BootstrapRunContext,
    workspace_root: Path,
    runtime: BootstrapRuntime,
) -> None:
    """Print optional run metadata and links without controlling dispatch."""
    repository_roots = context.repository_roots
    if repository_roots is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    source_root = repository_roots.agentcanon_source_root
    selected_skills = runtime.selected_skills
    review_roles = selected_review_roles(runtime.roles)
    public_layout = getattr(repository_roots, "layout", None)
    if public_layout is None:
        raise RuntimeError("runtime_roots_invalid:layout_missing")
    print(f"RUN_ID={context.run_id}")
    print(f"REPORT_DIR={context.report_dir}")
    print(f"TASK_AUTHORITY={context.report_dir / 'task_authority.yaml'}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    print(f"REQUEST_CONTRACT={context.report_dir / 'user_request_contract.md'}")
    print("REQUEST_CONTRACT_REQUIRED=yes")
    print(f"SUGGESTED_SKILLS={','.join(selected_skills)}")
    if context.math_intent_route is None:
        print("MATH_INTENT_ROUTE_STATUS=not_applicable")
        print("MATH_INTENT_PACKET=absent")
    else:
        print("MATH_INTENT_ROUTE_STATUS=active")
        print(f"MATH_INTENT_PACKET_SCHEMA={MATHEMATICAL_INTENT_PACKET_SCHEMA}")
        math_route_config = mathematical_intent_route_config(
            catalog, context.math_intent_route
        )
        if math_route_config is None:
            raise RuntimeError("mathematical_intent_route:catalog_record_missing")
        print(f"MATH_INTENT_ROUTE_ID={context.math_intent_route}")
        print(f"MATH_INTENT_REVIEWER={math_route_config.get('reviewer', 'unknown')}")
        print("MATH_INTENT_PACKET=present")
    print(
        "START_DECLARATION="
        f"workflow={context.workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(selected_skills) or '-'}, "
        f"review={','.join(review_roles) or '-'}"
    )
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
        print("TASK_ID_ROUTE_STATUS=explicit")
        print(f"WORKFLOW_FAMILY={context.workflow_family_id}")
        print(f"WORKFLOW_FAMILY_NAME={context.workflow_family_name}")
        print(f"TASK_DEFAULT_SPECIALISTS={','.join(context.task_default_specialists)}")
    else:
        print("TASK_ID_ROUTE_STATUS=missing")
    if context.workflow_family_id == "issue_worker_publication":
        print(
            "ISSUE_WORKER_CANDIDATE_STATUS="
            + ("explicit" if context.issue_worker_candidate else "absent")
        )
        if runtime.issue_worker_dispatch is not None:
            print(
                "ISSUE_WORKER_DISPATCH_STATUS="
                + str(runtime.issue_worker_dispatch.get("status", "unknown"))
            )
            for field in ("spawn_tool_call", "tool_call"):
                tool_call = runtime.issue_worker_dispatch.get(field)
                if is_string_object_mapping(tool_call):
                    print(
                        f"ISSUE_WORKER_{field.upper()}_JSON="
                        + json.dumps(
                            tool_call,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
        print(
            "ISSUE_WORKER_DISPATCH_ROUTE="
            "tools/agent/orchestration/agent_team.py#dispatch_issue_worker"
        )
        print("ISSUE_WORKER_EXECUTION_ROLE=publisher")
        print(
            "ISSUE_WORKER_TOOL_CALL_ROUTE="
            "tools/agent/orchestration/tool_calls.py#materialize_issue_worker_tool_call"
        )
        print("ISSUE_WORKER_READBACK=URL,number,body,state")
    print(
        "SUBAGENT_AGENT_TYPE_SELECTIONS="
        f"{format_agent_type_selections(runtime.agent_type_selections)}"
    )
    for line in pre_handoff_scope_policy_output_lines():
        print(line)
    for line in checkout_identity_policy_output_lines():
        print(line)
    for line in coordination_capability_policy_output_lines():
        print(line)
    for line in pre_handoff_gate_status_output_lines():
        print(line)
    for line in user_facing_language_policy_output_lines():
        print(line)
    for line in contract_complete_implementation_policy_output_lines(args.task):
        print(line)
    for line in repo_tool_routing_policy_output_lines(
        selected_skills,
        source_root=source_root,
    ):
        print(line)
    for line in default_quality_check_policy_output_lines(
        runtime.roles,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        language_review_candidates=context.language_review_candidates,
        default_review_packs_enabled=False,
        default_review_pack_ids=context.default_review_pack_ids,
        layout=public_layout,
    ):
        print(line)
    if not args.no_language_review_candidates:
        print(
            f"LANGUAGE_REVIEW_CANDIDATES={','.join(context.language_review_candidates)}"
        )
    print(
        "IMPLEMENTATION_CODEX_AGENTS="
        f"{','.join(codex_agents_for_role(config, 'implementer'))}"
    )
    print(
        f"ROLE_MODEL_MATRIX={';'.join(codex_agent_model_matrix_for_roles(runtime.roles))}"
    )
    print("IMPLEMENTATION_SURFACE_ROUTE_STATUS=pending")
    print(
        "IMPLEMENTATION_SURFACE_ROUTE_COMMAND="
        + public_command_for_layout(
            "tools/bin/agent-canon agent-search "
            "--query-file <request-or-design-question.txt> "
            "--providers semantic "
            "--format json",
            public_layout,
        )
    )
    print("PRE_EDIT_REJECTION_PREDICTION_STATUS=optional_diagnostic")
    print(
        "PRE_EDIT_REJECTION_COMMAND="
        + public_command_for_layout(
            "tools/bin/agent-canon tool-rejection-preflight --root . <planned-edit-paths>",
            public_layout,
        )
    )
    print("AGENT_REPORT_COLLECTION_STATUS=available")
    print(
        "AGENT_REPORT_COLLECTION_STATUS_COMMAND="
        + public_command_for_layout(
            "python3 tools/runtime/archive/runtime_log_archive_git.py status",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_ARCHIVE_RUN_COMMAND="
        + public_command_for_layout(
            f"python3 tools/runtime/archive/runtime_log_archive_git.py archive-agent-report --report-dir {context.report_dir}",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_COLLECTION_SYNC_COMMAND="
        + public_command_for_layout(
            "python3 tools/runtime/archive/runtime_log_archive_git.py sync",
            public_layout,
        )
    )
    print(
        "CROSS_CUTTING_DOCUMENT_PACKET="
        f"{cross_cutting_document_packet_output(workspace_root, source_root)}"
    )
    print(
        "DESIGN_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'designer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(
        "IMPLEMENTATION_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'implementer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(f"ACTIVE_ROLES={','.join(role.id for role in runtime.roles)}")
    print(f"CREATED_FILES={','.join(runtime.created_files)}")
    print(f"AGENT_CANON_ACTIVE_RUN_POINTER={runtime.active_pointer}")


def record_bootstrap_monitoring(
    context: BootstrapRunContext,
    roles: tuple[Role, ...],
    selected_skills: tuple[str, ...],
    review_roles: tuple[str, ...],
    task_text: str,
    source_root: Path | None = None,
) -> None:
    """Record bootstrap monitoring evidence."""
    del task_text
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    append_monitoring(
        context.report_dir,
        signals=[
            (
                f"workflow={context.workflow_family_name or 'Unspecified'}, "
                f"skills={','.join(selected_skills) or '-'}, "
                f"review={','.join(review_roles) or '-'}"
            ),
            f"selected roles active_roles={','.join(role.id for role in roles)}",
            "web_research_not_required: bootstrap does not decide external research",
        ],
        interventions=[
            f"created run bundle and workflow_monitoring.md at {context.report_dir}"
        ],
        behavior_events=["token_efficiency_not_required reason=bootstrap_default"],
    )


def _read_optional_bytes(path: Path) -> bytes | None:
    """Read one prior file exactly, preserving absent state as ``None``."""
    return path.read_bytes() if path.is_file() else None


def _restore_runtime_file(
    boundary: RuntimeArtifactBoundary,
    path: Path,
    prior: bytes | None,
    purpose: str,
) -> None:
    """Restore one captured runtime file without touching source state."""
    del purpose
    if prior is not None:
        boundary.atomic_write_bytes(path, prior)
        return
    if not path.exists():
        return
    path.unlink()


def publish_prepared_run(
    spec: RunBundleSpec,
    prepared: PreparedRunBundle,
    report_root: Path,
    post_move: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    """Stage one prepared byte map, move it once, publish sidecars, and rollback."""
    report_root = report_root.resolve(strict=False)
    configured_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip() or None
    runtime_base = configured_runtime or report_root.parent
    source_root = spec.agentcanon_source_root
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    boundary = runtime_artifact_boundary(
        source_root,
        runtime_base,
        create=True,
    )
    report_root = boundary.resolve(report_root)
    boundary.ensure_directory(report_root.relative_to(boundary.root))
    final_run = spec.report_dir.resolve()
    expected_final_run = (report_root / spec.run_id).resolve()
    if final_run != expected_final_run:
        raise RuntimeError("runtime_roots_invalid:report_dir_mismatch")
    if final_run.exists():
        raise RuntimeError(f"bootstrap_run_id_collision:{spec.run_id}")
    pointer = report_root / ".active_run"
    pointer_baseline = report_root / ".active_run.sha256"
    authority_baseline = final_run / f"{AUTHORITY_FILE_NAME}.sha256"
    prior_files = {
        pointer: _read_optional_bytes(pointer),
        pointer_baseline: _read_optional_bytes(pointer_baseline),
        authority_baseline: _read_optional_bytes(authority_baseline),
    }
    prior_children: set[str] = (
        {child.name for child in report_root.iterdir()}
        if report_root.is_dir()
        else set()
    )
    stage_dir: Path | None = None
    moved = False
    try:
        stage_dir = Path(tempfile.mkdtemp(prefix=".stage-run-", dir=str(report_root)))
        for relative, payload in prepared.files:
            relative_path = Path(relative)
            if (
                relative_path.is_absolute()
                or not relative
                or any(part in {"", ".", ".."} for part in relative_path.parts)
            ):
                raise RuntimeError(f"runtime_artifact_path_invalid:stage:{relative}")
            target = stage_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if target.read_bytes() != payload:
                raise RuntimeError(f"bootstrap_stage_readback_failed:{relative}")
        os.replace(stage_dir, final_run)
        stage_dir = None
        moved = True
        pointer_bytes = (str(final_run.resolve()) + "\n").encode("utf-8")
        boundary.atomic_write_bytes(pointer, pointer_bytes)
        boundary.atomic_write_bytes(
            pointer_baseline, hash_baseline_bytes(pointer_bytes)
        )
        authority_path = final_run / AUTHORITY_FILE_NAME
        if authority_path.is_file():
            boundary.atomic_write_bytes(
                authority_baseline,
                hash_baseline_bytes(authority_path.read_bytes()),
            )
        if post_move is not None:
            post_move()
        for relative, payload in prepared.files:
            if relative == "workflow_monitoring.md":
                continue
            if (final_run / relative).read_bytes() != payload:
                raise RuntimeError(f"bootstrap_final_readback_failed:{relative}")
        monitoring_path = final_run / "workflow_monitoring.md"
        if not monitoring_path.is_file() or not monitoring_path.read_bytes().startswith(
            dict(prepared.files).get("workflow_monitoring.md", b"")
        ):
            raise RuntimeError("bootstrap_monitoring_readback_failed")
        if pointer.read_bytes() != pointer_bytes:
            raise RuntimeError("bootstrap_pointer_readback_failed")
        if pointer_baseline.read_bytes() != hash_baseline_bytes(pointer_bytes):
            raise RuntimeError("bootstrap_pointer_baseline_readback_failed")
        if (
            authority_path.is_file()
            and authority_baseline.read_bytes()
            != hash_baseline_bytes(authority_path.read_bytes())
        ):
            raise RuntimeError("bootstrap_authority_baseline_readback_failed")
        return prepared.created_files
    except Exception as primary_error:
        rollback_errors: list[str] = []
        try:
            if stage_dir is not None and stage_dir.exists():
                shutil.rmtree(stage_dir)
            if moved and final_run.exists():
                shutil.rmtree(final_run)
            for path, prior in prior_files.items():
                _restore_runtime_file(
                    boundary,
                    path,
                    prior,
                    "bootstrap-publish-rollback",
                )
            observed_children: set[str] = (
                {child.name for child in report_root.iterdir()}
                if report_root.is_dir()
                else set()
            )
            if observed_children != prior_children:
                raise RuntimeError(
                    f"child_delta:{sorted(observed_children ^ prior_children)}"
                )
            for path, prior in prior_files.items():
                if _read_optional_bytes(path) != prior:
                    raise RuntimeError(f"prior_bytes:{path}")
        except Exception as rollback_error:
            rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(
                "bootstrap_publish_rollback_failed:"
                f"{primary_error}:{';'.join(rollback_errors)}"
            ) from primary_error
        raise


PublisherSpawn = Callable[[str, str], str | None]


def main(
    argv: Sequence[str] | None = None,
    *,
    spawn: PublisherSpawn | None = None,
) -> int:
    """Create an optional run bundle and print role/profile guidance."""
    runtime_parser = argparse.ArgumentParser(add_help=False)
    runtime_parser.add_argument("--runtime-root")
    runtime_args, _ = runtime_parser.parse_known_args(argv)
    selected_runtime = (
        runtime_args.runtime_root
        or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    )
    if selected_runtime:
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = selected_runtime
        for name in (
            "TMPDIR",
            "TEMP",
            "TMP",
            "XDG_CACHE_HOME",
            "PYTHONPYCACHEPREFIX",
            "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "AGENT_CANON_CLI_TARGET_DIR",
            "RUSTUP_HOME",
            "ELAN_HOME",
        ):
            os.environ.pop(name, None)
    try:
        source_resolution = resolve_agent_canon_source_root(Path(__file__).resolve())
        source_root = source_resolution.source_root
        config = load_team_config(source_root / "agents" / "agents_config.json")
        catalog = load_task_catalog(config, root=source_root)
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1

    args = build_parser(enable_choices(config, catalog), task_ids(catalog)).parse_args(
        argv
    )
    try:
        issue_worker_candidate = parse_issue_worker_candidate(
            args.issue_worker_candidate
        )
        active_design_packet = parse_active_design_packet_input(
            args.active_design_packet
        )
        writer_targets: dict[str, WriterTarget] = {}
        if args.writer_targets:
            parsed_targets = json.loads(args.writer_targets)
            if not is_string_object_dict(parsed_targets):
                raise WriterTargetError("writer_targets:must_be_mapping")
            for owner, target in parsed_targets.items():
                if not is_string_object_mapping(target):
                    raise WriterTargetError(
                        "writer_targets:owner_target_must_be_mapping"
                    )
                writer_targets[owner] = parse_writer_target(target)
    except (RuntimeError, TypeError, json.JSONDecodeError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 2

    workspace_root = Path(args.workspace_root).resolve()
    try:
        repository_roots = resolve_repository_roots(
            workspace_root,
            args.report_root,
            source_root=source_root,
            canon_root=source_resolution.canon_root,
            runtime_root=args.runtime_root,
        )
        context = resolve_bootstrap_context(
            args,
            config,
            catalog,
            workspace_root,
            repository_roots,
            issue_worker_candidate,
        )
        math_packet_input = parse_math_intent_packet_input(args.math_intent_packet)
        if context.math_intent_route is not None and math_packet_input is None:
            raise RuntimeError("math_packet_missing")
        if context.math_intent_route is None and math_packet_input is not None:
            raise RuntimeError("math_packet_not_applicable")
        math_intent_packet = (
            normalize_mathematical_intent_packet(math_packet_input)
            if math_packet_input is not None
            else None
        )
        roles = select_roles(
            config,
            list(context.enabled_specialists),
            args.full_team,
            catalog=catalog,
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=context.issue_worker_candidate,
            adversarial_required=context.adversarial_required,
        )
        agent_type_selections = validate_agent_type_selections(
            config,
            roles,
            parse_agent_type_selections(tuple(args.select_agent_type)),
        )
    except (RuntimeError, OSError, ValueError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 1

    issue_worker_dispatch: Mapping[str, object] | None = None
    if (
        context.workflow_family_id == "issue_worker_publication"
        and issue_worker_candidate
    ):
        try:
            issue_worker_dispatch = dispatch_issue_worker(
                issue_worker_candidate,
                args.task,
                spawn,
                workspace_root=workspace_root,
                agentcanon_source_root=repository_roots.agentcanon_source_root,
            ).as_dict()
        except (RuntimeError, OSError) as exc:
            print(str(exc), flush=True)
            return 1

    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
        source_root=repository_roots.agentcanon_source_root,
        issue_worker_candidate=context.issue_worker_candidate,
    )
    manifest_issue_worker_dispatch = (
        {
            key: value
            for key, value in issue_worker_dispatch.items()
            if key not in {"tool_call", "spawn_tool_call"} or value is None
        }
        if issue_worker_dispatch is not None
        else None
    )
    run_spec = RunBundleSpec(
        config=config,
        report_dir=context.report_dir,
        run_id=context.run_id,
        task=args.task,
        owner=args.owner,
        created_at_iso=context.created_at_iso,
        roles=roles,
        workspace_root=workspace_root,
        agentcanon_source_root=repository_roots.agentcanon_source_root,
        report_root=repository_roots.report_root,
        repository_roots=repository_roots,
        active_design_packet=active_design_packet,
        workflow_family_id=context.workflow_family_id or "",
        issue_worker_candidate=context.issue_worker_candidate,
        issue_worker_dispatch=manifest_issue_worker_dispatch,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        language_review_candidates=context.language_review_candidates,
        default_review_packs_enabled=False,
        default_review_pack_ids=context.default_review_pack_ids,
        selected_skills=selected_skills,
        task_catalog=catalog,
        task_id=args.task_id,
        math_intent_route=context.math_intent_route,
        math_intent_packet=math_intent_packet,
        agent_type_selections=agent_type_selections,
        writer_targets=writer_targets,
    )
    try:
        prepared = prepare_run_bundle(run_spec)
    except (RuntimeError, OSError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 1

    review_roles = selected_review_roles(roles)
    workflow_context_result: StoreResult | None = None

    def post_move() -> None:
        nonlocal workflow_context_result
        if context.workflow_family_id is not None:
            workflow_context_result = store_workflow_context(
                context.report_dir / "skill_usage_context.json",
                context_from_workflows(
                    (context.workflow_family_id,), "bootstrap_agent_run.task_id"
                ),
            )
        record_bootstrap_monitoring(
            context,
            roles,
            selected_skills,
            review_roles,
            args.task,
            repository_roots.agentcanon_source_root,
        )

    try:
        created_files = publish_prepared_run(
            run_spec,
            prepared,
            context.report_root,
            post_move=post_move,
        )
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    if (
        workflow_context_result is not None
        and workflow_context_result.status == "stored"
    ):
        created_files = (*created_files, "skill_usage_context.json")

    runtime = BootstrapRuntime(
        roles=roles,
        created_files=created_files,
        active_pointer=context.report_root / ".active_run",
        agent_type_selections=agent_type_selections,
        active_design_packet=prepared.active_design_packet,
        math_intent_packet=math_intent_packet,
        issue_worker_dispatch=issue_worker_dispatch,
        selected_skills=selected_skills,
    )
    emit_bootstrap_output(
        args=args,
        config=config,
        catalog=catalog,
        context=context,
        workspace_root=workspace_root,
        runtime=runtime,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
