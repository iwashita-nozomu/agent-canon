# @dependency-start
# contract tool
# responsibility AgentTeam team config owner module.
# upstream design ../../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# downstream implementation ./agent_team.py facade consumes config APIs.
# downstream implementation ../../runtime/lifecycle/bootstrap_agent_run.py consumes config APIs.
# @dependency-end
"""Own AgentTeam configuration, catalog, and role policy definitions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

from tools.agent.orchestration.route import implementation_handoff_required, load_skill_route_rules

if TYPE_CHECKING:
    if __package__:
        from .packets import ActiveDesignPacketConfig
        from .packets import MathematicalIntentPacket
        from tools.repository.workspace.workspace_scope import RepositoryRoots
        from tools.runtime.authority.writer_target import WriterTarget
    else:
        from tools.agent.orchestration.packets import ActiveDesignPacketConfig
        from tools.agent.orchestration.packets import MathematicalIntentPacket
        from tools.repository.workspace.workspace_scope import RepositoryRoots
        from tools.runtime.authority.writer_target import WriterTarget

ROOT = Path(__file__).resolve().parents[3]

TEAM_CONFIG_PATH = ROOT / "agents" / "agents_config.json"

CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"

CURRENT_STAGE_SKILLS = {
    "$agent-orchestration",
    "$task-routing",
    "$literature-survey",
    "$research-workflow",
    "$environment-maintenance",
    "$comprehensive-development",
    "$adaptive-improvement-loop",
    "$refactor-loop",
    "$paper-writing",
}


@dataclass(frozen=True)
class WritePolicy:
    """Describe how one role may write to the filesystem."""

    mode: str
    allowed_artifacts: tuple[str, ...]
    conditional_artifacts: dict[str, tuple[str, ...]]
    allowed_directories: tuple[str, ...] = ()
    requires_worktree_scope: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Role:
    """Describe one permanent team role."""

    id: str
    owns: tuple[str, ...]
    required_outputs: tuple[str, ...]
    activation: str
    write_policy: WritePolicy
    codex_agents: tuple[str, ...]


@dataclass(frozen=True)
class SubagentWaveSlot:
    """One executable subagent instance in a stage wave."""

    role_id: str
    instance_id: str
    agent_type: str
    write_capable: bool = False
    writer_target: WriterTarget | None = None
    math_intent_route_id: str | None = None

    def __post_init__(self) -> None:
        """Default the role instance id from the selected executable agent."""
        if not self.instance_id:
            object.__setattr__(self, "instance_id", f"{self.role_id}_{self.agent_type}")

    @property
    def executable_identity(self) -> str:
        """Return the authoritative executable role identity."""
        return f"{self.role_id}:{self.instance_id}:{self.agent_type}"

    @property
    def requires_math_intent(self) -> bool:
        """Return whether task selection bound this slot to the math route."""
        return self.math_intent_route_id is not None


@dataclass(frozen=True)
class AgentTypeSelection:
    """Explicit parent-packet selection of one executable agent for a role."""

    role_id: str
    agent_type: str
    evidence: str


@dataclass(frozen=True)
class StageWave:
    """One catalog-owned subagent stage wave."""

    id: str
    stage_class: str
    role_ids: tuple[str, ...]


@dataclass(frozen=True)
class TeamConfig:
    """Materialized team configuration."""

    raw: dict[str, object]
    team: dict[str, object]
    always_on_roles: tuple[Role, ...]
    specialist_roles: tuple[Role, ...]
    handoffs: tuple[dict[str, object], ...]
    context_policies: tuple[dict[str, object], ...]
    activation_rules: tuple[dict[str, object], ...]
    quality_gates: tuple[str, ...]
    artifact_registry: dict[str, object]
    artifacts: dict[str, str]


@dataclass(frozen=True)
class TaskCatalog:
    """Materialized task catalog."""

    raw: dict[str, object]
    workflow_families: tuple[dict[str, object], ...]
    tasks: tuple[dict[str, object], ...]
    review_packs: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class RunBundleSpec:
    """Inputs required to create a run bundle and team manifest."""

    config: TeamConfig
    report_dir: Path
    run_id: str
    task: str
    owner: str
    created_at_iso: str
    roles: tuple[Role, ...]
    workspace_root: Path
    agentcanon_source_root: Path | None = None
    report_root: Path | None = None
    repository_roots: "RepositoryRoots | None" = None
    workflow_family_id: str = ""
    issue_worker_candidate: Mapping[str, object] | None = None
    issue_worker_dispatch: Mapping[str, object] | None = None
    manual_specialists: tuple[str, ...] = ()
    task_default_specialists: tuple[str, ...] = ()
    language_review_candidates: tuple[str, ...] = ()
    default_review_packs_enabled: bool = False
    default_review_pack_ids: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()
    task_catalog: TaskCatalog | None = None
    task_id: str | None = None
    agent_type_selections: tuple[AgentTypeSelection, ...] = ()
    parent_lineage_id: str = ""
    decision_sufficiency_packet: dict[str, object] | None = None
    decision_sufficiency_packet_ref: str = ""
    active_design_packet: ActiveDesignPacketConfig | None = None
    math_intent_route: str | None = None
    math_intent_packet: "MathematicalIntentPacket | None" = None
    writer_targets: Mapping[str, object] = field(default_factory=dict)


def load_team_config(path: Path = TEAM_CONFIG_PATH) -> TeamConfig:
    """Load the canonical team config."""
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    raw = _as_object_mapping(parsed, "team config")
    team = _as_object_mapping(raw.get("team"), "team")
    always_on_roles = tuple(
        _parse_role(role, "always")
        for role in _as_mapping_tuple(raw.get("always_on_roles"), "always_on_roles")
    )
    specialist_roles = tuple(
        _parse_role(role, "optional")
        for role in _as_mapping_tuple(raw.get("specialist_roles"), "specialist_roles")
    )
    handoffs = _as_mapping_tuple(raw.get("handoffs"), "handoffs")
    context_policies = _as_mapping_tuple(
        raw.get("context_policies"), "context_policies"
    )
    activation_rules = _as_mapping_tuple(
        raw.get("activation_rules"), "activation_rules"
    )
    quality_gates = _as_string_tuple(raw.get("quality_gates"), "quality_gates")
    artifact_registry = _as_object_mapping(raw.get("artifacts"), "artifacts")
    artifacts = {
        key: _as_required_string(value, f"artifacts.{key}")
        for key, value in artifact_registry.items()
        if key != "active_design_packet"
    }
    return TeamConfig(
        raw=raw,
        team=team,
        always_on_roles=always_on_roles,
        specialist_roles=specialist_roles,
        handoffs=handoffs,
        context_policies=context_policies,
        activation_rules=activation_rules,
        quality_gates=quality_gates,
        artifact_registry=artifact_registry,
        artifacts=artifacts,
    )


def load_task_catalog(config: TeamConfig, root: Path = ROOT) -> TaskCatalog:
    """Load the task catalog referenced by the team config."""
    catalog_path = root / str(config.team["task_catalog"])
    parsed: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    raw = _as_object_mapping(parsed, f"task catalog {catalog_path}")
    return TaskCatalog(
        raw=raw,
        workflow_families=_as_mapping_tuple(
            raw.get("workflow_families"), "workflow_families"
        ),
        tasks=_as_mapping_tuple(raw.get("tasks"), "tasks"),
        review_packs=_as_mapping_tuple(raw.get("review_packs"), "review_packs"),
    )


def specialist_role_ids(config: TeamConfig) -> tuple[str, ...]:
    """Return specialist role ids."""
    return tuple(role.id for role in config.specialist_roles)


def normalized_public_skill_name(skill: str) -> str:
    """Return one public skill name without runtime sigils."""
    return skill.strip().removeprefix("$")


def review_pack_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known review pack ids."""
    return tuple(str(pack["id"]) for pack in catalog.review_packs)


def default_review_pack_ids_for_task(
    catalog: TaskCatalog,
    task_id: str,
) -> tuple[str, ...]:
    """Return review pack ids selected by default for one task."""
    selected: list[str] = []
    for pack in catalog.review_packs:
        default_tasks = _as_string_tuple(
            pack.get("default_for_tasks"),
            f"review_packs[{pack['id']}].default_for_tasks",
        )
        if task_id in default_tasks:
            selected.append(str(pack["id"]))
    return tuple(selected)


def enable_choices(config: TeamConfig, catalog: TaskCatalog) -> tuple[str, ...]:
    """Return valid --enable values for specialist roles and review packs."""
    return tuple(sorted((*specialist_role_ids(config), *review_pack_ids(catalog))))


def expand_enabled_specialists(
    config: TeamConfig,
    catalog: TaskCatalog,
    enabled_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Expand specialist role ids and named review packs into role ids."""
    specialist_ids = set(specialist_role_ids(config))
    review_packs = {str(pack["id"]): pack for pack in catalog.review_packs}
    expanded: list[str] = []
    for name in enabled_names:
        if name in specialist_ids:
            if name not in expanded:
                expanded.append(name)
            continue
        if name in review_packs:
            for role_id in _as_string_tuple(
                review_packs[name].get("specialists"),
                f"review_packs[{name}].specialists",
            ):
                resolve_role(config, role_id)
                if role_id not in expanded:
                    expanded.append(role_id)
            continue
        raise KeyError(f"unknown specialist or review pack: {name}")
    return tuple(expanded)


def resolve_role(config: TeamConfig, role_name: str) -> Role:
    """Resolve a role id to a role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role_name == role.id:
            return role
    raise KeyError(f"unknown role: {role_name}")


def task_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known task ids from the catalog."""
    return tuple(str(task["id"]) for task in catalog.tasks)


def resolve_task_spec(catalog: TaskCatalog, task_id: str) -> dict[str, object]:
    """Resolve one task id from the catalog."""
    for task in catalog.tasks:
        if task.get("id") == task_id:
            return task
    raise KeyError(f"unknown task id: {task_id}")


def resolve_workflow_family(catalog: TaskCatalog, family_id: str) -> dict[str, object]:
    """Resolve one workflow family from the catalog."""
    for family in catalog.workflow_families:
        if family.get("id") == family_id:
            return family
    raise KeyError(f"unknown workflow family: {family_id}")


def catalog_stage_waves(catalog: TaskCatalog) -> tuple[StageWave, ...]:
    """Return catalog-owned role topology stages."""
    topology = _as_object_mapping(
        catalog.raw.get("role_topology_defaults"),
        "role_topology_defaults",
    )
    waves = _as_mapping_tuple(
        topology.get("stage_waves"), "role_topology_defaults.stage_waves"
    )
    return tuple(
        StageWave(
            id=_as_required_string(wave.get("id"), "stage_waves[].id"),
            stage_class=_as_required_string(
                wave.get("stage_class"),
                "stage_waves[].stage_class",
            ),
            role_ids=_as_string_tuple(wave.get("role_ids"), "stage_waves[].role_ids"),
        )
        for wave in waves
    )


def current_stage_skills(
    selected_skills: tuple[str, ...],
    task_text: str = "",
    *,
    source_root: Path = ROOT,
    typed_route_required: bool = False,
) -> tuple[str, ...]:
    """Return public skills to declare for the current stage only."""
    active_skills = set(CURRENT_STAGE_SKILLS)
    active_skills.update(catalog_active_stage_skills(source_root))
    if implementation_handoff_required(task_text, typed_route_required=typed_route_required):
        active_skills.add("$subagent-bootstrap")
    return tuple(skill for skill in selected_skills if skill in active_skills)


def deferred_stage_skills(
    selected_skills: tuple[str, ...],
    task_text: str = "",
    *,
    source_root: Path = ROOT,
    typed_route_required: bool = False,
) -> tuple[str, ...]:
    """Return selected public skills that should wait for dynamic wave triggers."""
    active = set(
        current_stage_skills(
            selected_skills,
            task_text,
            source_root=source_root,
            typed_route_required=typed_route_required,
        )
    )
    return tuple(skill for skill in selected_skills if skill not in active)


def catalog_active_stage_skills(root: Path = ROOT) -> tuple[str, ...]:
    """Return public skills marked active in the skill catalog."""
    return tuple(
        f"${rule.skill}"
        for rule in load_skill_route_rules(root)
        if rule.stage_policy == "active"
    )


def default_specialists_for_task(
    config: TeamConfig,
    catalog: TaskCatalog,
    task_id: str,
    include_default_review_packs: bool = True,
) -> tuple[str, ...]:
    """Return task-default specialist ids including default review packs."""
    task = resolve_task_spec(catalog, task_id)
    family = resolve_workflow_family(catalog, str(task["family"]))
    family_roles = family.get("roles", {})
    if not isinstance(family_roles, dict):
        raise RuntimeError(
            f"workflow family roles must be a mapping for {family['id']}"
        )
    family_roles = _as_object_mapping(
        cast(object, family_roles), f"workflow_families[{family['id']}].roles"
    )
    family_specialists = _as_string_tuple(
        family_roles.get("specialists"),
        f"workflow_families[{family['id']}].roles.specialists",
    )
    selected: list[str] = []

    for role_id in _as_string_tuple(
        task.get("specialists"), f"tasks[{task_id}].specialists"
    ):
        if role_id not in family_specialists:
            raise RuntimeError(
                f"task {task_id} specialist {role_id} is not declared in family {family['id']}"
            )
        resolve_role(config, role_id)
        if role_id not in selected:
            selected.append(role_id)

    if include_default_review_packs:
        for pack in catalog.review_packs:
            default_tasks = _as_string_tuple(
                pack.get("default_for_tasks"),
                f"review_packs[{pack['id']}].default_for_tasks",
            )
            if task_id not in default_tasks:
                continue
            for role_id in _as_string_tuple(
                pack.get("specialists"),
                f"review_packs[{pack['id']}].specialists",
            ):
                resolve_role(config, role_id)
                if role_id not in selected:
                    selected.append(role_id)

    return tuple(selected)


def select_roles(
    config: TeamConfig,
    enabled_specialists: list[str],
    full_team: bool,
    catalog: TaskCatalog | None = None,
    workflow_family_id: str | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> tuple[Role, ...]:
    """Return the active roles for one run."""
    if full_team:
        all_roles = config.always_on_roles + config.specialist_roles
        if workflow_family_id == "skill_evaluation":
            return tuple(role for role in all_roles if role.id == "skill_evaluator")
        return tuple(role for role in all_roles if role.id != "skill_evaluator")
    always_on_roles = workflow_always_on_roles(config, catalog, workflow_family_id)
    selected_specialist_names = list(enabled_specialists)
    # T15 is publisher-only, but its publisher is conditional on an explicit
    # typed candidate.  Do not turn the task default into a global initial
    # wave or activate this role for unrelated workflow families.
    if (
        workflow_family_id == "issue_worker_publication"
        and isinstance(issue_worker_candidate, Mapping)
        and issue_worker_candidate
        and "publisher" not in selected_specialist_names
    ):
        selected_specialist_names.append("publisher")
    enabled_roles = tuple(resolve_role(config, name) for name in selected_specialist_names)
    selected_roles = list(always_on_roles)
    selected_ids = {role.id for role in selected_roles}
    for role in enabled_roles:
        if role.id not in selected_ids:
            selected_roles.append(role)
            selected_ids.add(role.id)
    enabled_set = {role.id for role in enabled_roles}
    selected_specialists = tuple(
        role
        for role in config.specialist_roles
        if role.id in enabled_set
        if role.id not in selected_ids
    )
    return tuple(selected_roles) + selected_specialists


def workflow_always_on_roles(
    config: TeamConfig,
    catalog: TaskCatalog | None,
    workflow_family_id: str | None,
) -> tuple[Role, ...]:
    """Return family-specific always-on roles when a workflow family declares them."""
    if catalog is None or not workflow_family_id:
        return config.always_on_roles
    family = resolve_workflow_family(catalog, workflow_family_id)
    family_roles = family.get("roles", {})
    if not isinstance(family_roles, dict):
        return config.always_on_roles
    family_roles = _as_object_mapping(
        cast(object, family_roles),
        f"workflow_families[{workflow_family_id}].roles",
    )
    if "always_on" not in family_roles:
        return config.always_on_roles
    role_ids = _as_string_tuple(
        family_roles.get("always_on"),
        f"workflow_families[{workflow_family_id}].roles.always_on",
    )
    return tuple(resolve_role(config, role_id) for role_id in role_ids)


def workflow_child_handoff_required(
    config: TeamConfig,
    catalog: TaskCatalog | None,
    workflow_family_id: str | None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> bool:
    """Return whether a selected typed family contains a write-capable child."""
    if catalog is None or not workflow_family_id:
        return False
    policy = _as_object_mapping(
        catalog.raw.get("workflow_activation_policy"),
        "workflow_activation_policy",
    )
    child_handoff = _as_object_mapping(
        policy.get("child_handoff"),
        "workflow_activation_policy.child_handoff",
    )
    if child_handoff.get("activation") != "selected_typed_route":
        return False
    family = resolve_workflow_family(catalog, workflow_family_id)
    if (
        workflow_family_id == "issue_worker_publication"
        and not isinstance(issue_worker_candidate, Mapping)
    ):
        return False
    roles = _as_object_mapping(
        family.get("roles", {}), f"workflow_families[{workflow_family_id}].roles"
    )
    role_ids = _as_string_tuple(
        roles.get("always_on"),
        f"workflow_families[{workflow_family_id}].roles.always_on",
    ) + _as_string_tuple(
        roles.get("specialists"),
        f"workflow_families[{workflow_family_id}].roles.specialists",
    )
    return any(
        resolve_role(config, role_id).write_policy.mode
        not in {"read_only", "artifacts_only"}
        for role_id in role_ids
    )


def load_codex_agent_configs() -> dict[str, dict[str, object]]:
    """Load Codex custom agent TOML files by declared agent name."""
    configs: dict[str, dict[str, object]] = {}
    for path in sorted(CODEX_AGENT_ROOT.glob("*.toml")):
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        name = parsed.get("name", path.stem)
        configs[str(name)] = parsed
    return configs


def codex_agent_model_matrix_for_roles(
    roles: tuple[Role, ...],
    configs: dict[str, dict[str, object]] | None = None,
) -> tuple[str, ...]:
    """Return role:agent:model:effort rows for active Codex agents."""
    agent_configs = configs if configs is not None else load_codex_agent_configs()
    rows: list[str] = []
    for role in roles:
        for agent_id in role.codex_agents:
            agent_config = agent_configs.get(agent_id, {})
            model = str(agent_config.get("model", "inherit"))
            effort = str(agent_config.get("model_reasoning_effort", "inherit"))
            rows.append(f"{role.id}:{agent_id}:{model}:{effort}")
    return tuple(dict.fromkeys(rows))


def _parse_role(raw_role: dict[str, object], default_activation: str) -> Role:
    """Parse a role from json."""
    role_id = _as_required_string(raw_role.get("id"), "role.id")
    raw_write_policy = _as_object_mapping(
        raw_role.get("write_policy"), f"roles[{role_id}].write_policy"
    )
    write_policy = WritePolicy(
        mode=_as_required_string(
            raw_write_policy.get("mode"), f"roles[{role_id}].write_policy.mode"
        ),
        allowed_artifacts=_as_string_tuple(
            raw_write_policy.get("allowed_artifacts"),
            f"roles[{role_id}].write_policy.allowed_artifacts",
        ),
        conditional_artifacts={
            str(condition): _as_string_tuple(
                artifacts,
                f"roles[{role_id}].write_policy.conditional_artifacts.{condition}",
            )
            for condition, artifacts in _as_object_mapping(
                raw_write_policy.get("conditional_artifacts", {}),
                f"roles[{role_id}].write_policy.conditional_artifacts",
            ).items()
        },
        allowed_directories=_as_string_tuple(
            raw_write_policy.get("allowed_directories"),
            f"roles[{role_id}].write_policy.allowed_directories",
        ),
        requires_worktree_scope=_as_bool(
            raw_write_policy.get("requires_worktree_scope", False),
            f"roles[{role_id}].write_policy.requires_worktree_scope",
        ),
        notes=_as_optional_string(
            raw_write_policy.get("notes"), f"roles[{role_id}].write_policy.notes"
        ),
    )
    raw_activation = raw_role.get("activation")
    activation = (
        default_activation
        if raw_activation is None
        else _as_required_string(raw_activation, f"roles[{role_id}].activation")
    )
    return Role(
        id=role_id,
        owns=_as_string_tuple(raw_role.get("owns"), f"roles[{role_id}].owns"),
        required_outputs=_as_string_tuple(
            raw_role.get("required_outputs"), f"roles[{role_id}].required_outputs"
        ),
        activation=activation,
        write_policy=write_policy,
        codex_agents=_as_string_tuple(
            raw_role.get("codex_agents"), f"roles[{role_id}].codex_agents"
        ),
    )


def _as_mapping_tuple(value: object, field_name: str) -> tuple[dict[str, object], ...]:
    """Validate a list of mappings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[dict[str, object]] = []
    for item in cast(list[object], value):
        normalized.append(_as_object_mapping(item, f"{field_name} entries"))
    return tuple(normalized)


def _as_object_mapping(value: object, field_name: str) -> dict[str, object]:
    """Validate a string-keyed mapping and return a typed copy."""
    if not isinstance(value, dict):
        raise RuntimeError(f"{field_name} must be a mapping")
    normalized: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise RuntimeError(f"{field_name} keys must be strings")
        normalized[key] = item
    return normalized


def _as_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate a list of strings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise RuntimeError(f"{field_name} entries must be strings")
        normalized.append(item)
    return tuple(normalized)


def _as_required_string(value: object, field_name: str) -> str:
    """Validate one required string field."""
    if not isinstance(value, str):
        raise RuntimeError(f"{field_name} must be a string")
    return value


def _as_optional_string(value: object, field_name: str) -> str:
    """Validate one optional string field."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"{field_name} must be a string")
    return value


def _as_bool(value: object, field_name: str) -> bool:
    """Validate one boolean field."""
    if not isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be a boolean")
    return value
