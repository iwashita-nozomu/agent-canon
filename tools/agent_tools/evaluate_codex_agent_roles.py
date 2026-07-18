#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates Codex subagent role configuration, routing, model settings, and runtime metrics.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent role inventory contract
# upstream design ../../evidence/agent-evals/README.md eval directory contract
# upstream implementation ./agent_team.py loads team and task routing metadata
# upstream implementation ./model_profile_registry.py owns canonical model/profile expectations
# upstream implementation ./capacity_handshake.py owns typed capacity provenance
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# downstream implementation ../../tests/agent_tools/test_evaluate_codex_agent_roles.py tests role eval behavior
# @dependency-end
"""Evaluate Codex custom agent role definitions and routing policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import model_profile_registry

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_team import (  # noqa: E402
    Role,
    default_specialists_for_task,
    declared_team_capacity_derivation,
    load_task_catalog,
    load_team_config,
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave,
    select_roles,
    workflow_spawn_budget,
    workflow_topology_policy_violations,
)
from runtime_log_paths import eval_results_dir  # noqa: E402

COMPACT_FINDING_SAMPLE_LIMIT = 25
DEFAULT_RESULTS_FAMILY = "codex-agent-role"
RUN_ID_DIGEST_LENGTH = 10
GIT_COMMAND_TIMEOUT_SECONDS = 5
VALID_REASONING_EFFORTS = {"low", "medium", "high", "xhigh"}
DEPRECATED_CODEX_MODELS = {"gpt-5.2", "gpt-5.3-codex"}
EVALUATOR_AGENT_ID = "skill_evaluator"
EVALUATOR_ACTIVATION = "explicit_empirical_skill_evaluation"
FORBIDDEN_AGENT_PROFILE_KEYS = {"tier", "service_tier", "flex"}
GENERATED_ROLE_VIEW_MATERIALIZER = "generate_role_views"


@dataclass(frozen=True)
class Finding:
    """One role eval finding."""

    check: str
    target: str
    detail: str

    def render(self) -> str:
        """Render a machine-readable finding line."""
        return f"CODEX_AGENT_ROLE_FINDING={self.check}:{self.target}:{self.detail}"


@dataclass(frozen=True)
class RuntimeSummary:
    """Aggregated runtime metrics for one agent role."""

    calls: int
    tokens: int
    latency_ms: int
    retries: int
    parent_interventions: int
    format_violations: int
    output_used: int


@dataclass(frozen=True)
class EvalRunMetadata:
    """Metadata recorded with one role eval run."""

    created_at: str
    eval_run_id: str
    run_id: str
    argv: tuple[str, ...]
    cwd: str
    root: str
    git_branch: str
    git_commit: str
    git_dirty: str


@dataclass(frozen=True)
class EvalReport:
    """Complete role eval report."""

    metadata: EvalRunMetadata
    status: str
    findings: tuple[Finding, ...]
    model_matrix: tuple[str, ...]
    runtime_metrics_status: str
    runtime_metrics: dict[str, RuntimeSummary]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--runtime-log",
        action="append",
        default=[],
        help="Optional JSONL file with role runtime metrics.",
    )
    parser.add_argument("--report-out", type=Path)
    parser.add_argument(
        "--compact-out",
        type=Path,
        help="Optional JSON summary path. When set, stdout omits full finding and model-matrix detail.",
    )
    parser.add_argument("--accumulate", action="store_true")
    parser.add_argument(
        "--results-dir",
        default="",
        help=(
            "Directory for accumulated reports. Defaults to the mounted "
            "AgentCanon log archive eval-results/codex-agent-role path."
        ),
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run bundle id recorded in accumulated reports.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon root for standalone or template invocation."""
    vendored = root / "vendor" / "agent-canon"
    if (vendored / ".codex" / "agents").is_dir():
        return vendored.resolve()
    return root.resolve()


def load_agent_configs(root: Path) -> dict[str, dict[str, object]]:
    """Load all project-scoped Codex custom agent TOML files."""
    configs: dict[str, dict[str, object]] = {}
    load_toml = cast(Callable[[str], dict[str, object]], getattr(tomllib, "loads"))
    for path in sorted((root / ".codex" / "agents").glob("*.toml")):
        payload = load_toml(path.read_text(encoding="utf-8"))
        payload["__path"] = path.relative_to(root).as_posix()
        payload["__stem"] = path.stem
        configs[str(payload.get("name", path.stem))] = payload
    return configs


def validate_no_legacy_model_policy(root: Path) -> list[Finding]:
    """Check that model settings are not duplicated in project config."""
    findings: list[Finding] = []
    config_path = root / ".codex" / "config.toml"
    if not config_path.is_file():
        return [Finding("model-settings", ".codex/config.toml", "missing-config")]
    load_toml = cast(Callable[[str], dict[str, object]], getattr(tomllib, "loads"))
    payload = load_toml(config_path.read_text(encoding="utf-8"))
    if "agent_model_policy" in payload:
        findings.append(Finding("model-settings", ".codex/config.toml", "legacy-agent-model-policy"))
    try:
        registry = model_profile_registry.load_model_profile_registry(root)
        parent = registry.by_profile("sol_parent_high")
        review = registry.by_profile("luna_reasoning_high")
    except model_profile_registry.ImplementationFeedback:
        return [Finding("model-settings", "agents/model_profiles.toml", "registry-unreadable")]
    for key, expected in (
        ("model", parent.model),
        ("model_reasoning_effort", parent.reasoning_effort),
        ("review_model", review.model),
    ):
        if payload.get(key) != expected:
            findings.append(
                Finding("model-settings", ".codex/config.toml", f"expected-{key}-{expected}")
            )
    for key in ("service_tier", "flex", "tier"):
        if key in payload:
            findings.append(
                Finding("model-settings", ".codex/config.toml", f"unsupported-profile-key-{key}")
            )
    return findings


def role_by_id(roles: tuple[Role, ...]) -> dict[str, Role]:
    """Return roles keyed by id."""
    return {role.id: role for role in roles}


def extract_stage_waves(catalog_raw: dict[str, object]) -> tuple[tuple[dict[str, object], ...], list[Finding]]:
    """Extract catalog stage_waves as typed mappings and report malformed topology."""
    findings: list[Finding] = []
    topology_raw = catalog_raw.get("role_topology_defaults")
    if not isinstance(topology_raw, dict):
        findings.append(Finding("routing", "role_topology_defaults", "missing-stage-waves"))
        return (), findings
    topology = cast(dict[str, object], topology_raw)
    stage_waves_raw = topology.get("stage_waves")
    if not isinstance(stage_waves_raw, list) or not stage_waves_raw:
        findings.append(Finding("routing", "role_topology_defaults", "missing-stage-waves"))
        return (), findings
    stage_waves: list[dict[str, object]] = []
    raw_stage_waves = cast(list[object], stage_waves_raw)
    for index, raw_wave in enumerate(raw_stage_waves):
        if not isinstance(raw_wave, dict):
            findings.append(Finding("routing", f"stage_waves[{index}]", "malformed-stage-wave"))
            continue
        stage_waves.append(cast(dict[str, object], raw_wave))
    same_role_raw = topology.get("same_role_parallel_instances")
    if not isinstance(same_role_raw, dict):
        findings.append(Finding("routing", "role_topology_defaults", "legacy-identity-key"))
    else:
        same_role = cast(dict[str, object], same_role_raw)
        if same_role.get("identity_key") != "role_id+instance_id+agent_type":
            findings.append(Finding("routing", "role_topology_defaults", "legacy-identity-key"))
    return tuple(stage_waves), findings


def evaluate_generated_role_projection(
    root: Path,
    configs: dict[str, dict[str, object]],
) -> list[Finding]:
    """Evaluate generated role views and topology-derived capacity attribution."""
    findings: list[Finding] = []
    try:
        team = json.loads((root / "agents" / "agents_config.json").read_text(encoding="utf-8"))
        registry = model_profile_registry.load_model_profile_registry(root)
        generated = {
            view.role_id: view
            for view in model_profile_registry.generate_role_views(registry, root=root)
        }
    except (OSError, ValueError, model_profile_registry.ImplementationFeedback) as exc:
        return [Finding("generated-view", "canonical", f"materializer-error-{type(exc).__name__}")]
    agent_views = team.get("agent_views")
    bindings = {entry.get("id"): entry for entry in team.get("roles", []) if isinstance(entry, dict)}
    if not isinstance(agent_views, dict) or set(agent_views) != set(configs) or set(bindings) != set(configs):
        findings.append(Finding("generated-view", "agents_config", "role-view-binding-set-mismatch"))
        return findings
    expected_fields = {"name", "description", "nickname_candidates", "sandbox_mode", "approval_policy", "model", "model_reasoning_effort", "developer_instructions"}
    for agent_id, config in sorted(configs.items()):
        source = agent_views.get(agent_id)
        binding = bindings.get(agent_id)
        if not isinstance(source, dict) or not isinstance(binding, dict):
            findings.append(Finding("generated-view", agent_id, "missing-source-record"))
            continue
        actual_fields = set(k for k in config if not k.startswith("__"))
        if actual_fields != expected_fields:
            findings.append(Finding("generated-view", agent_id, "closed-eight-field-projection-mismatch"))
        profile_id = source.get("profile_id")
        if not isinstance(profile_id, str):
            findings.append(Finding("profile-attribution", agent_id, "unknown-profile"))
            continue
        try:
            profile = registry.by_profile(profile_id)
        except model_profile_registry.ImplementationFeedback:
            findings.append(Finding("profile-attribution", agent_id, "unknown-profile"))
            continue
        if binding.get("profile_id") != profile_id:
            findings.append(Finding("profile-attribution", agent_id, "binding-divergence"))
        if (config.get("model"), config.get("model_reasoning_effort")) != (profile.model, profile.reasoning_effort):
            findings.append(Finding("profile-attribution", agent_id, "runtime-view-divergence"))
        for field in ("name", "description", "nickname_candidates", "sandbox_mode", "approval_policy"):
            if config.get(field) != source.get(field):
                findings.append(Finding("generated-view", agent_id, f"source-divergence-{field}"))
        expected_view = generated.get(agent_id)
        if expected_view is None or config.get("developer_instructions", "").strip() != expected_view.rendered_instructions.strip():
            findings.append(Finding("generated-view", agent_id, "developer-instructions-not-materialized"))
        if "generated_role_view_v1" not in (root / ".codex" / "agents" / f"{agent_id}.toml").read_text(encoding="utf-8"):
            findings.append(Finding("generated-view", agent_id, "missing-generated-header"))
    try:
        catalog = load_task_catalog(load_team_config(root / "agents" / "agents_config.json"), root=root)
        derivation = declared_team_capacity_derivation(catalog)
        peak = derivation.peak_family
        if derivation.requested_max_threads() != 26 or peak.workflow_family_id != "research_driven_change" or peak.direct_frontier_count != 20 or peak.nested_reservation_count != 6:
            findings.append(Finding("capacity-attribution", "role_topology_defaults", "declared-20-plus-6-does-not-derive-26"))
        for family in catalog.workflow_families:
            request = family.get("capacity_request")
            if not isinstance(request, dict) or request.get("topology_source") != "role_topology" or request.get("write_scope_source") != "team_manifest.run.write_scopes":
                findings.append(Finding("capacity-attribution", str(family.get("id")), "typed-capacity-request-mismatch"))
            if "spawn_budget" in family:
                findings.append(Finding("capacity-attribution", str(family.get("id")), "numeric-spawn-budget-duplicate"))
    except (OSError, KeyError, RuntimeError, TypeError, ValueError):
        findings.append(Finding("capacity-attribution", "task_catalog", "capacity-derivation-unreadable"))
    return findings


def evaluate_static_agent_configs(
    root: Path,
    configs: dict[str, dict[str, object]],
) -> list[Finding]:
    """Evaluate the closed generated role projection and executable settings."""
    findings = evaluate_generated_role_projection(root, configs)
    try:
        registry = model_profile_registry.load_model_profile_registry(root)
    except model_profile_registry.ImplementationFeedback:
        return findings + [Finding("model-settings", "agents/model_profiles.toml", "registry-unreadable")]
    for agent_id, config in configs.items():
        for key in sorted(FORBIDDEN_AGENT_PROFILE_KEYS & set(config)):
            findings.append(Finding("schema", agent_id, f"unsupported-profile-key-{key}"))
        for field in ("name", "description", "developer_instructions"):
            if not str(config.get(field, "")).strip():
                findings.append(Finding("schema", agent_id, f"missing-{field}"))
        if config.get("name") != config.get("__stem"):
            findings.append(Finding("schema", agent_id, "name-file-stem-mismatch"))
        model = config.get("model")
        effort = config.get("model_reasoning_effort")
        if not isinstance(model, str) or not model:
            findings.append(Finding("model-settings", agent_id, "missing-model"))
        elif model in DEPRECATED_CODEX_MODELS:
            findings.append(Finding("model-settings", agent_id, f"deprecated-model-{model}"))
        try:
            expected_profile = registry.profile_for_role(agent_id)
        except model_profile_registry.ImplementationFeedback:
            findings.append(Finding("profile-attribution", agent_id, "unknown-role-binding"))
            continue
        expected_model, expected_effort = expected_profile.model, expected_profile.reasoning_effort
        if model != expected_model:
            matching_profiles = [profile for profile in registry.model_profiles if profile.model == model]
            if any("fixed_packet" in profile.capabilities for profile in matching_profiles):
                findings.append(
                    Finding("model-settings", agent_id, "spark-model-reserved-for-spark-worker")
                )
            if any("skill_evaluation" in profile.capabilities for profile in matching_profiles):
                findings.append(
                    Finding(
                        "model-settings",
                        agent_id,
                        "skill-validation-model-reserved-for-skill-evaluator-t14",
                    )
                )
        if model != expected_model:
            findings.append(
                Finding("model-settings", agent_id, f"expected-model-{expected_model}")
            )
        if effort != expected_effort:
            findings.append(
                Finding(
                    "model-settings",
                    agent_id,
                    f"expected-{expected_effort}-reasoning",
                )
            )
        if not isinstance(effort, str) or effort not in VALID_REASONING_EFFORTS:
            findings.append(Finding("model-settings", agent_id, "invalid-model-reasoning-effort"))
        findings.extend(evaluate_role_behavior(root, agent_id, config))
    return findings
def evaluate_role_behavior(
    root: Path,
    agent_id: str,
    config: dict[str, object],
) -> list[Finding]:
    """Check executable role fields without re-owning registry prompt prose."""
    del root
    findings: list[Finding] = []
    read_only_role = agent_id.endswith("_reviewer") or agent_id in {"diff_triage_reviewer", "explorer", "literature_researcher", "reviewer", "ship_reviewer", "test_designer", EVALUATOR_AGENT_ID}
    if read_only_role and config.get("sandbox_mode") != "read-only":
        findings.append(Finding("behavior", agent_id, "read-only-role-not-read-only"))
    if agent_id == EVALUATOR_AGENT_ID:
        if config.get("sandbox_mode") != "read-only":
            findings.append(Finding("behavior", agent_id, "evaluator-not-read-only"))
        if config.get("approval_policy") != "never":
            findings.append(
                Finding("behavior", agent_id, "evaluator-approval-policy-not-never")
            )
    return findings
def evaluate_routing(root: Path) -> list[Finding]:
    """Evaluate task routing and role-to-Codex-agent ordering."""
    findings: list[Finding] = []
    config = load_team_config(root / "agents" / "agents_config.json")
    catalog = load_task_catalog(config, root=root)
    agent_root = root / ".codex" / "agents"
    roles = role_by_id(config.always_on_roles + config.specialist_roles)
    evaluator = roles.get(EVALUATOR_AGENT_ID)
    if evaluator is None:
        findings.append(Finding("registration", EVALUATOR_AGENT_ID, "missing-permanent-role"))
    else:
        if evaluator.activation != EVALUATOR_ACTIVATION:
            findings.append(Finding("registration", EVALUATOR_AGENT_ID, "activation-must-be-explicit"))
        if evaluator.id in {role.id for role in config.always_on_roles}:
            findings.append(Finding("registration", EVALUATOR_AGENT_ID, "must-not-be-always-on"))
        if evaluator.write_policy.mode != "artifacts_only":
            findings.append(Finding("registration", EVALUATOR_AGENT_ID, "must-be-artifacts-only"))
        if "skill_evaluation" not in evaluator.write_policy.allowed_artifacts:
            findings.append(Finding("registration", EVALUATOR_AGENT_ID, "missing-skill-evaluation-artifact"))
    for role_id, role in roles.items():
        if role_id != EVALUATOR_AGENT_ID and EVALUATOR_AGENT_ID in role.codex_agents:
            findings.append(
                Finding(
                    "registration",
                    role_id,
                    "skill-evaluator-candidate-reserved-for-skill-evaluator-role",
                )
            )
    project_config_path = root / ".codex" / "config.toml"
    project_config: dict[str, object] = {}
    if project_config_path.is_file():
        parsed_project_config = tomllib.loads(
            project_config_path.read_text(encoding="utf-8")
        )
        project_config = cast(dict[str, object], parsed_project_config)
    agent_registry_raw = project_config.get("agents", {})
    agent_registry = (
        cast(dict[str, object], agent_registry_raw)
        if isinstance(agent_registry_raw, dict)
        else {}
    )
    non_default_agent_types = tuple(
        dict.fromkeys(
            agent_type
            for role in roles.values()
            for agent_type in role.codex_agents
            if agent_type != "default"
        )
    )
    registration_agent_types = tuple(
        dict.fromkeys((*non_default_agent_types, EVALUATOR_AGENT_ID))
    )
    target_toml_stems = {
        path.stem
        for path in (root / ".codex" / "agents").glob("*.toml")
        if path.is_file()
    }
    for agent_type in registration_agent_types:
        registered_raw = agent_registry.get(agent_type)
        if not isinstance(registered_raw, dict):
            findings.append(
                Finding(
                    "registration",
                    agent_type,
                    "missing-project-registration",
                )
            )
        else:
            registered = cast(dict[str, object], registered_raw)
            expected_config_file = f"agents/{agent_type}.toml"
            if registered.get("config_file") != expected_config_file:
                findings.append(
                    Finding(
                        "registration",
                        agent_type,
                        "mismatched-config-file",
                    )
                )
        if agent_type not in target_toml_stems:
            findings.append(
                Finding(
                    "registration",
                    agent_type,
                    "missing-toml",
                )
            )
    tasks_with_evaluator = [
        str(task.get("id"))
        for task in catalog.tasks
        if EVALUATOR_AGENT_ID in cast(list[object], task.get("specialists", []))
    ]
    if tasks_with_evaluator != ["T14"]:
        findings.append(Finding("registration", EVALUATOR_AGENT_ID, "must-be-only-in-explicit-evaluation-task"))

    expected_agent_order = {
        "change_reviewer": ("diff_triage_reviewer", "python_reviewer", "cpp_reviewer", "reviewer"),
        "experimenter": ("experiment_runner", "worker"),
        "final_reviewer": ("ship_reviewer", "reviewer", "project_reviewer"),
        "implementer": ("worker", "spark_worker"),
    }
    for role_id, expected in expected_agent_order.items():
        observed = roles[role_id].codex_agents[: len(expected)]
        if observed != expected:
            findings.append(Finding("routing", role_id, f"role-candidate-order-expected-{expected}"))

    topology_raw = catalog.raw.get("role_topology_defaults")
    if isinstance(topology_raw, dict):
        topology = cast(dict[str, object], topology_raw)
        role_families_raw = topology.get("role_families")
        role_families = (
            cast(dict[str, object], role_families_raw)
            if isinstance(role_families_raw, dict)
            else None
        )
        if role_families is None or role_families.get("implementation") != [
            "worker",
            "spark_worker",
        ]:
            findings.append(
                Finding(
                    "routing",
                    "role_topology_defaults.role_families.implementation",
                    "implementation-role-family-order",
                )
            )
        if role_families is None or role_families.get("test_design") != ["test_designer"]:
            findings.append(
                Finding(
                    "routing",
                    "role_topology_defaults.role_families.test_design",
                    "test-design-role-family",
                )
            )
        design_family_raw: object = (
            role_families.get("design") if role_families is not None else None
        )
        design_family = (
            cast(list[object], design_family_raw)
            if isinstance(design_family_raw, list)
            else []
        )
        if "test_designer" in design_family:
            findings.append(Finding("routing", "role_topology_defaults.role_families.design", "test-designer-must-be-post-implementation"))

    stage_waves, topology_findings = extract_stage_waves(catalog.raw)
    findings.extend(topology_findings)
    role_stage: dict[str, tuple[int, str]] = {}
    stage_ids: set[str] = set()
    for stage_index, wave in enumerate(stage_waves):
        stage_id = str(wave.get("id", ""))
        if stage_id in stage_ids:
            findings.append(Finding("routing", stage_id, "duplicate-stage-id"))
        stage_ids.add(stage_id)
        role_ids_raw = wave.get("role_ids")
        if not isinstance(role_ids_raw, list):
            findings.append(Finding("routing", stage_id or f"stage-{stage_index}", "malformed-stage-role-ids"))
            continue
        role_ids = cast(list[object], role_ids_raw)
        for raw_role_id in role_ids:
            if not isinstance(raw_role_id, str):
                findings.append(Finding("routing", stage_id or f"stage-{stage_index}", "malformed-stage-role-id"))
                continue
            role_id = str(raw_role_id)
            previous_stage = role_stage.get(role_id)
            if previous_stage is not None:
                findings.append(Finding("routing", role_id, f"duplicate-stage-role-{previous_stage[1]}-{stage_id}"))
            role_stage[role_id] = (stage_index, stage_id)
    stage_required_roles = set(roles)
    missing_stage_roles = sorted(stage_required_roles - set(role_stage))
    for role_id in missing_stage_roles:
        findings.append(Finding("routing", role_id, "missing-stage-role"))
    implementer_stage = role_stage.get("implementer")
    test_designer_stage = role_stage.get("test_designer")
    change_reviewer_stage = role_stage.get("change_reviewer")
    if (
        implementer_stage is None
        or test_designer_stage is None
        or change_reviewer_stage is None
        or not (
            implementer_stage[0] < test_designer_stage[0] < change_reviewer_stage[0]
        )
    ):
        findings.append(Finding("routing", "test_designer", "test-design-must-follow-implementation"))
    if test_designer_stage is not None and test_designer_stage[1] != "test_design":
        findings.append(Finding("routing", "test_designer", "test-designer-stage-owner"))
    producer_reviewer_pairs = {
        "manager": ("manager_reviewer",),
        "researcher": ("research_reviewer",),
        "scheduler": ("schedule_reviewer",),
        "infra_steward": ("infra_reviewer",),
        "designer": ("design_reviewer", "document_flow_reviewer"),
        "experimenter": ("experiment_reviewer", "report_reviewer"),
        "implementer": ("test_designer", "change_reviewer", "python_reviewer", "cpp_reviewer"),
    }
    for producer, reviewers in producer_reviewer_pairs.items():
        for reviewer in reviewers:
            producer_stage = role_stage.get(producer)
            reviewer_stage = role_stage.get(reviewer)
            if producer_stage is None or reviewer_stage is None:
                continue
            if producer_stage[0] == reviewer_stage[0]:
                findings.append(Finding("routing", reviewer, f"producer-reviewer-same-stage-{producer}"))
            elif producer_stage[0] > reviewer_stage[0]:
                findings.append(Finding("routing", reviewer, f"producer-reviewer-stage-order-{producer}"))

    for task_id in ("T1", "T2"):
        task = next(task for task in catalog.tasks if task["id"] == task_id)
        if task.get("family") != "owner_bounded_change":
            findings.append(Finding("routing", task_id, "must-use-owner-bounded-change"))
        specialists = default_specialists_for_task(config, catalog, task_id)
        forbidden = {"scheduler", "schedule_reviewer", "document_flow_reviewer"}
        active_forbidden = sorted(forbidden & set(specialists))
        if active_forbidden:
            findings.append(Finding("routing", task_id, f"lite-route-heavy-specialists-{active_forbidden}"))

    t12_specialists = default_specialists_for_task(config, catalog, "T12")
    expected_t12 = (
        "scheduler",
        "schedule_reviewer",
        "project_reviewer",
        "docs_workflow_steward",
        "prompt_config_reviewer",
    )
    if t12_specialists != expected_t12:
        findings.append(Finding("routing", "T12", f"t12-overdefault-specialist-{t12_specialists}"))

    try:
        topology_violations = workflow_topology_policy_violations(catalog)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        findings.append(
            Finding(
                "routing",
                "role_topology_defaults",
                f"materialization-failed-{type(exc).__name__}",
            )
        )
    else:
        for family_id, code in topology_violations:
            findings.append(Finding("routing", family_id, code))

    review_pack = next(pack for pack in catalog.review_packs if pack["id"] == "research_perspective_review")
    if review_pack.get("default_for_tasks"):
        findings.append(Finding("routing", "research_perspective_review", "full-pack-must-not-default"))
    integration_pack = next(pack for pack in catalog.review_packs if pack["id"] == "repo_integration_review")
    if "T12" in cast(list[str], integration_pack.get("default_for_tasks", [])):
        findings.append(Finding("routing", "repo_integration_review", "t12-overdefault-specialist"))

    t14 = next(task for task in catalog.tasks if task.get("id") == "T14")
    if t14.get("family") != "skill_evaluation":
        findings.append(Finding("routing", "T14", "must-use-skill-evaluation-family"))
    else:
        t14_family = next(
            family
            for family in catalog.workflow_families
            if family.get("id") == "skill_evaluation"
        )
        t14_roles_raw = t14_family.get("roles", {})
        t14_roles = (
            cast(dict[str, object], t14_roles_raw)
            if isinstance(t14_roles_raw, dict)
            else None
        )
        if t14_roles is None or t14_roles.get("always_on") != []:
            findings.append(Finding("routing", "T14", "evaluation-route-has-default-roles"))
        if t14_roles is None or t14_roles.get("specialists") != [EVALUATOR_AGENT_ID]:
            findings.append(Finding("routing", "T14", "evaluation-route-specialists-must-be-evaluator-only"))
        try:
            t14_default_specialists = default_specialists_for_task(config, catalog, "T14")
            t14_roles_active = select_roles(
                config,
                list(t14_default_specialists),
                full_team=False,
                catalog=catalog,
                workflow_family_id="skill_evaluation",
            )
            t14_budget, _ = workflow_spawn_budget(catalog, "skill_evaluation")
            t14_initial_wave = recommended_initial_subagent_wave(
                t14_roles_active,
                t14_budget,
                catalog,
                agent_root=agent_root,
            )
            t14_waves = recommended_dynamic_expansion_wave_slots(
                t14_roles_active,
                t14_budget,
                t14_initial_wave,
                catalog,
                agent_root=agent_root,
            )
            if t14_initial_wave != (EVALUATOR_AGENT_ID,) or t14_waves:
                findings.append(Finding("routing", "T14", "evaluation-route-materialization-topology"))
        except (KeyError, RuntimeError, TypeError, ValueError):
            findings.append(Finding("routing", "T14", "evaluation-route-materialization-failed"))
    triage_pack = next(pack for pack in catalog.review_packs if pack["id"] == "research_perspective_triage")
    if set(cast(list[str], triage_pack.get("specialists", []))) != {
        "reproducibility_reviewer",
        "artifact_reviewer",
    }:
        findings.append(Finding("routing", "research_perspective_triage", "unexpected-triage-specialists"))
    for task in catalog.tasks:
        task_id = str(task["id"])
        try:
            task_specialists = default_specialists_for_task(config, catalog, task_id)
            task_roles = select_roles(
                config,
                list(task_specialists),
                False,
                catalog,
                str(task["family"]),
            )
            active_budget, _ = workflow_spawn_budget(catalog, str(task["family"]))
            initial_wave = recommended_initial_subagent_wave(
                task_roles,
                active_budget,
                catalog,
                agent_root=agent_root,
            )
            wave_slots = recommended_dynamic_expansion_wave_slots(
                task_roles,
                active_budget,
                initial_wave,
                catalog,
                agent_root=agent_root,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            findings.append(Finding("routing", task_id, f"materialization-failed-{exc}"))
            continue
        role_counts = Counter(slot.role_id for wave in wave_slots for slot in wave)
        fanout_roles = sorted(role_id for role_id, count in role_counts.items() if count > 1)
        if fanout_roles:
            findings.append(Finding("routing", task_id, f"role-candidate-fanout-{fanout_roles}"))
    return findings


def runtime_log_paths(root: Path, explicit_logs: list[str]) -> tuple[Path, ...]:
    """Resolve optional runtime metric logs."""
    paths = [Path(raw).resolve() for raw in explicit_logs]
    default_dir = root / "agents" / "evals" / "results" / "subagent-role-runtime"
    if default_dir.is_dir():
        paths.extend(sorted(default_dir.glob("*.jsonl")))
    return tuple(path for path in paths if path.is_file())


def runtime_metrics(root: Path, explicit_logs: list[str]) -> tuple[str, dict[str, RuntimeSummary], list[Finding]]:
    """Aggregate optional token, latency, retry, intervention, format, and output-use metrics."""
    paths = runtime_log_paths(root, explicit_logs)
    if not paths:
        return "missing", {}, []
    raw: dict[str, Counter[str]] = defaultdict(Counter)
    findings: list[Finding] = []
    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "invalid-json"))
                continue
            if not isinstance(entry, dict):
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "entry-not-object"))
                continue
            entry = cast(dict[str, object], entry)
            agent_id = str(entry.get("agent") or entry.get("codex_agent") or entry.get("role") or "")
            if not agent_id:
                findings.append(Finding("runtime-log", f"{path}:{line_no}", "missing-agent"))
                continue
            bucket = raw[agent_id]
            bucket["calls"] += 1
            for metric_name, keys in {
                "tokens": ("tokens", "total_tokens"),
                "latency_ms": ("latency_ms",),
                "retries": ("retry_count", "retries"),
            }.items():
                value, finding = int_metric(entry, *keys)
                bucket[metric_name] += value
                if finding is not None:
                    findings.append(
                        Finding(
                            "runtime-log",
                            f"{path}:{line_no}:{agent_id}:{finding}",
                            "invalid-int-metric",
                        )
                    )
            bucket["parent_interventions"] += int(bool(entry.get("parent_intervention")))
            bucket["format_violations"] += int(bool(entry.get("format_violation")))
            bucket["output_used"] += int(bool(entry.get("output_used")))
    summaries = {
        agent_id: RuntimeSummary(
            calls=counts["calls"],
            tokens=counts["tokens"],
            latency_ms=counts["latency_ms"],
            retries=counts["retries"],
            parent_interventions=counts["parent_interventions"],
            format_violations=counts["format_violations"],
            output_used=counts["output_used"],
        )
        for agent_id, counts in sorted(raw.items())
    }
    return "observed", summaries, findings


def int_metric(entry: dict[str, object], *keys: str) -> tuple[int, str | None]:
    """Return the first integer-like metric value found in one runtime entry."""
    for key in keys:
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return int(value), None
        if isinstance(value, int):
            return value, None
        if isinstance(value, float):
            return int(value), key if not value.is_integer() else None
        if isinstance(value, str):
            stripped = value.strip()
            try:
                return int(stripped), None
            except ValueError:
                try:
                    return int(float(stripped)), key
                except ValueError:
                    return 0, key
        return 0, key
    return 0, None


def model_matrix(configs: dict[str, dict[str, object]]) -> tuple[str, ...]:
    """Render agent executable model settings."""
    rows: list[str] = []
    for agent_id in sorted(configs):
        rows.append(
            f"{agent_id}:{configs[agent_id].get('model')}:{configs[agent_id].get('model_reasoning_effort')}"
        )
    return tuple(rows)


def git_output(root: Path, *args: str) -> str:
    """Return one git command output, or '-' outside a usable git checkout."""
    try:
        result = subprocess.run(
            ("git", "-C", root.as_posix(), *args),
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "-"
    if result.returncode != 0:
        return "-"
    return result.stdout.strip() or "-"


def build_eval_run_metadata(root: Path, run_id: str) -> EvalRunMetadata:
    """Build metadata with a unique, filename-safe eval run id."""
    now = datetime.now(UTC)
    created_at = now.isoformat()
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    digest_source = "|".join(("codex-agent-role", run_id.strip(), created_at, root.as_posix()))
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return EvalRunMetadata(
        created_at=created_at,
        eval_run_id=f"codex-agent-role-eval-{timestamp}-{digest}",
        run_id=run_id.strip(),
        argv=tuple(sys.argv),
        cwd=Path.cwd().as_posix(),
        root=root.as_posix(),
        git_branch=git_output(root, "rev-parse", "--abbrev-ref", "HEAD"),
        git_commit=git_output(root, "rev-parse", "HEAD"),
        git_dirty="yes" if git_output(root, "status", "--short", "--untracked-files=all") else "no",
    )


def evaluate(root: Path, runtime_logs: list[str], run_id: str = "") -> EvalReport:
    """Run the full role eval."""
    canon_root = agent_canon_root(root)
    configs = load_agent_configs(canon_root)
    findings = [
        *validate_no_legacy_model_policy(canon_root),
        *evaluate_static_agent_configs(canon_root, configs),
        *evaluate_routing(canon_root),
    ]
    metrics_status, metrics, metric_findings = runtime_metrics(canon_root, runtime_logs)
    findings.extend(metric_findings)
    return EvalReport(
        metadata=build_eval_run_metadata(canon_root, run_id),
        status="pass" if not findings else "fail",
        findings=tuple(findings),
        model_matrix=model_matrix(configs),
        runtime_metrics_status=metrics_status,
        runtime_metrics=metrics,
    )


def render_text(report: EvalReport, *, include_details: bool = True, compact_out: Path | None = None) -> str:
    """Render text output."""
    lines = [
        f"CODEX_AGENT_ROLE_EVAL_RUN_ID={report.metadata.eval_run_id}",
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
    ]
    if compact_out is not None:
        lines.append(f"CODEX_AGENT_ROLE_COMPACT_OUT={compact_out.as_posix()}")
    if not include_details:
        return "\n".join(lines) + "\n"
    lines.append(f"ROLE_MODEL_MATRIX={';'.join(report.model_matrix)}")
    for agent_id, summary in report.runtime_metrics.items():
        lines.append(
            "ROLE_RUNTIME_METRIC="
            f"{agent_id}:calls={summary.calls}:tokens={summary.tokens}:"
            f"latency_ms={summary.latency_ms}:retries={summary.retries}:"
            f"parent_interventions={summary.parent_interventions}:"
            f"format_violations={summary.format_violations}:output_used={summary.output_used}"
        )
    lines.extend(finding.render() for finding in report.findings)
    return "\n".join(lines) + "\n"


def compact_summary(report: EvalReport) -> dict[str, object]:
    """Return a bounded JSON-friendly role eval summary."""
    findings_by_check = Counter(finding.check for finding in report.findings)
    model_counts = Counter(row.split(":", 2)[1] for row in report.model_matrix)
    runtime_totals = {
        "calls": sum(summary.calls for summary in report.runtime_metrics.values()),
        "tokens": sum(summary.tokens for summary in report.runtime_metrics.values()),
        "latency_ms": sum(summary.latency_ms for summary in report.runtime_metrics.values()),
        "retries": sum(summary.retries for summary in report.runtime_metrics.values()),
        "parent_interventions": sum(
            summary.parent_interventions for summary in report.runtime_metrics.values()
        ),
        "format_violations": sum(summary.format_violations for summary in report.runtime_metrics.values()),
        "output_used": sum(summary.output_used for summary in report.runtime_metrics.values()),
    }
    return {
        "status": report.status,
        "finding_count": len(report.findings),
        "findings_by_check": dict(sorted(findings_by_check.items())),
        "model_counts": dict(sorted(model_counts.items())),
        "runtime_metrics_status": report.runtime_metrics_status,
        "runtime_totals": runtime_totals,
        "finding_samples": [
            asdict(finding) for finding in report.findings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
    }


def write_compact_summary(path: Path, report: EvalReport) -> None:
    """Write a bounded JSON summary for agent consumption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(compact_summary(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_markdown_report(path: Path, report: EvalReport) -> Path:
    """Write a Markdown role eval report."""
    lines = [
        "# Codex Agent Role Eval",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records one Codex subagent role eval run.",
        "upstream implementation ../../../../tools/agent_tools/evaluate_codex_agent_roles.py generates this report",
        "@dependency-end",
        "-->",
        "",
        f"CODEX_AGENT_ROLE_EVAL_RUN_ID={report.metadata.eval_run_id}",
        f"CODEX_AGENT_ROLE_EVAL={report.status}",
        f"CODEX_AGENT_ROLE_FINDINGS={len(report.findings)}",
        f"ROLE_RUNTIME_METRICS_STATUS={report.runtime_metrics_status}",
        f"run_id: `{report.metadata.run_id or '-'}`",
        f"git_branch: `{report.metadata.git_branch}`",
        f"git_commit: `{report.metadata.git_commit}`",
        f"git_dirty: `{report.metadata.git_dirty}`",
        "",
        "## Model Matrix",
        "",
    ]
    lines.extend(f"- `{row}`" for row in report.model_matrix)
    lines.extend(["", "## Runtime Metrics", ""])
    if report.runtime_metrics:
        for agent_id, summary in report.runtime_metrics.items():
            lines.append(f"- `{agent_id}`: `{asdict(summary)}`")
    else:
        lines.append("- `missing`: no role runtime metric JSONL was provided")
    lines.extend(["", "## Findings", ""])
    if report.findings:
        lines.extend(f"- `{finding.render()}`" for finding in report.findings)
    else:
        lines.append("- none")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path = path.with_name(f"{path.stem}-{report.metadata.eval_run_id}{path.suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def resolve_results_dir(root: Path, value: str) -> Path:
    """Resolve the CLI results directory or the default archive location."""
    stripped = value.strip()
    if stripped:
        path = Path(stripped)
        return path if path.is_absolute() else root / path
    return eval_results_dir(agent_canon_root(root), DEFAULT_RESULTS_FAMILY)


def accumulated_report_path(results_dir: Path, report: EvalReport) -> Path:
    """Return the unique accumulated report path."""
    return results_dir / f"{report.metadata.eval_run_id}-{report.status}.md"


def main() -> int:
    """Run the role eval."""
    args = build_parser().parse_args()
    report = evaluate(args.root, cast(list[str], args.runtime_log), str(args.run_id))
    report_paths: list[Path] = []
    if args.report_out is not None:
        report_paths.append(write_markdown_report(args.report_out, report))
    if args.compact_out is not None:
        write_compact_summary(args.compact_out, report)
    if args.accumulate:
        report_paths.append(
            write_markdown_report(
                accumulated_report_path(resolve_results_dir(args.root, str(args.results_dir)), report),
                report,
            )
        )
    if args.format == "json":
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(
            render_text(
                report,
                include_details=args.compact_out is None,
                compact_out=args.compact_out,
            ),
            end="",
        )
        for path in report_paths:
            print(f"CODEX_AGENT_ROLE_EVAL_REPORT={path}")
        if args.accumulate and report_paths:
            print(f"CODEX_AGENT_ROLE_EVAL_ACCUMULATED_REPORT={report_paths[-1]}")
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
