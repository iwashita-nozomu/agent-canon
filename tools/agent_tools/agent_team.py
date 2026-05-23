#!/usr/bin/env python3
# @dependency-start
# responsibility Provides agent team agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared vendor-only document packet policy
# @dependency-end
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
TEAM_CONFIG_PATH = ROOT / "agents" / "agents_config.json"
DEFAULT_REPORT_ROOT = Path("reports") / "agents"
TEMPLATE_ROOT = ROOT / "agents" / "templates"
PYTHON_SUFFIXES = {".py", ".pyi"}
CPP_SUFFIXES = {
    ".c",
    ".cc",
    ".cp",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ixx",
    ".tpp",
    ".ipp",
}
CPP_PATH_MARKERS = (
    "CMakeLists.txt",
    "cmake/",
    "src/",
    "include/",
    "lib/",
)
DOC_SUFFIXES = {".md", ".rst", ".txt"}
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
DOC_OR_RUNTIME_PATH_MARKERS = (
    ".agents/",
    ".claude/",
    ".codex/",
    ".devcontainer/",
    ".github/",
    "agents/",
    "documents/",
    "memory/",
    "notes/",
    "tools/catalog.yaml",
)
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
ROLE_DOCUMENT_PACKET_SPECS: dict[str, dict[str, object]] = {
    "manager": {
        "artifact_keys": ["intent_brief", "user_request_contract", "schedule"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Requirements and planning start from explicit documented clauses and stage plan.",
    },
    "designer": {
        "artifact_keys": ["intent_brief", "user_request_contract", "schedule"],
        "workspace_paths": [
            "agents/workflows/implementation-waterfall-workflow.md",
            "agents/canonical/CODEX_WORKFLOW.md",
        ],
        "notes": (
            "Detailed design must read upstream documented requirements and waterfall rules before "
            "design begins."
        ),
    },
    "design_reviewer": {
        "artifact_keys": ["user_request_contract", "schedule", "design_brief"],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Design review checks the same upstream packet and the resulting design brief.",
    },
    "test_designer": {
        "artifact_keys": ["user_request_contract", "schedule", "design_brief", "design_review"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Test design derives cases from the approved design packet.",
    },
    "implementer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "document_flow_review",
            "test_plan",
        ],
        "workspace_paths": [
            "agents/workflows/implementation-waterfall-workflow.md",
            "agents/canonical/CODEX_WORKFLOW.md",
        ],
        "must_cite_before_edit": True,
        "notes": "Implementation must read and cite the approved design packet before editing.",
    },
    "change_reviewer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "test_plan",
            "change_review",
        ],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Checkpoint review verifies that implementation cited the approved packet.",
    },
    "final_reviewer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "test_plan",
            "final_review",
        ],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Final review verifies whole-request traceability back to the approved packet.",
    },
    "scheduler": {
        "artifact_keys": ["user_request_contract", "schedule"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Scheduling reads explicit requirement and plan surfaces.",
    },
}
COMMON_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = (
    "documents/REVIEW_PROCESS.md",
    "documents/AGENTS_COORDINATION.md",
    "documents/coding-conventions-python.md",
    "documents/notes-lifecycle.md",
    "agents/workflows/agent-learning-workflow.md",
    "documents/agent-canon-subtree-migration.md",
    "notes/guardrails/README.md",
    "notes/guardrails/engineering_avoidances.md",
    "memory/USER_PREFERENCES.md",
    "memory/AGENT_PHILOSOPHY.md",
)
OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = ("docker/README.md",)


def resolve_workspace_document_path(workspace_root: Path, relative_path: str) -> Path:
    """Resolve a document path through the root view or vendored AgentCanon source."""
    root_path = (workspace_root / relative_path).resolve()
    if root_path.exists():
        return root_path
    vendor_path = (workspace_root / "vendor" / "agent-canon" / relative_path).resolve()
    if vendor_path.exists():
        return vendor_path
    canon_path = (ROOT / relative_path).resolve()
    if canon_path.exists():
        return canon_path
    return root_path


def resolve_report_root(
    report_root: str | None,
    workspace_root: Path | None = None,
) -> Path:
    """Resolve the report root relative to the active workspace by default."""
    base_root = workspace_root.resolve() if workspace_root is not None else Path.cwd().resolve()
    if report_root is None:
        return (base_root / DEFAULT_REPORT_ROOT).resolve()
    candidate = Path(report_root)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_root / candidate).resolve()


@dataclass(frozen=True)
class WritePolicy:
    """Describe how one role may write to the filesystem."""

    mode: str
    allowed_artifacts: tuple[str, ...]
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
class RoleWriteScope:
    """Resolved write scope for one role in one workspace."""

    role_id: str
    mode: str
    allowed_files: tuple[Path, ...]
    allowed_directories: tuple[Path, ...]
    requires_worktree_scope: bool
    worktree_scope_file: Path | None
    unresolved_reason: str | None
    notes: str


@dataclass(frozen=True)
class DocumentPacketEntry:
    """One explicit path a role must read before work."""

    path: Path
    rationale: str


@dataclass(frozen=True)
class RoleDocumentPacket:
    """Resolved explicit document packet for one role."""

    role_id: str
    read_before_work: tuple[DocumentPacketEntry, ...]
    must_cite_before_edit: bool
    notes: str


def resolve_cross_cutting_document_packet(workspace_root: Path) -> tuple[DocumentPacketEntry, ...]:
    """Resolve the common cross-cutting document packet for one workspace."""
    required_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(workspace_root, relative_path),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in COMMON_CROSS_CUTTING_DOCUMENT_PATHS
    )
    optional_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(workspace_root, relative_path),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS
        if resolve_workspace_document_path(workspace_root, relative_path).exists()
    )
    return required_entries + optional_entries


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
    workflow_family_id: str = ""


def load_team_config(path: Path = TEAM_CONFIG_PATH) -> TeamConfig:
    """Load the canonical team config."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    team = dict(raw["team"])
    always_on_roles = tuple(_parse_role(role, "always") for role in raw["always_on_roles"])
    specialist_roles = tuple(_parse_role(role, "optional") for role in raw["specialist_roles"])
    handoffs = tuple(dict(item) for item in raw["handoffs"])
    context_policies = tuple(dict(item) for item in raw["context_policies"])
    activation_rules = tuple(dict(item) for item in raw["activation_rules"])
    quality_gates = tuple(str(item) for item in raw["quality_gates"])
    artifacts = {str(key): str(value) for key, value in dict(raw["artifacts"]).items()}
    return TeamConfig(
        raw=raw,
        team=team,
        always_on_roles=always_on_roles,
        specialist_roles=specialist_roles,
        handoffs=handoffs,
        context_policies=context_policies,
        activation_rules=activation_rules,
        quality_gates=quality_gates,
        artifacts=artifacts,
    )


def load_task_catalog(config: TeamConfig, root: Path = ROOT) -> TaskCatalog:
    """Load the task catalog referenced by the team config."""
    catalog_path = root / str(config.team["task_catalog"])
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"task catalog must parse as a mapping: {catalog_path}")
    return TaskCatalog(
        raw=raw,
        workflow_families=_as_mapping_tuple(raw.get("workflow_families"), "workflow_families"),
        tasks=_as_mapping_tuple(raw.get("tasks"), "tasks"),
        review_packs=_as_mapping_tuple(raw.get("review_packs"), "review_packs"),
    )


def specialist_role_ids(config: TeamConfig) -> tuple[str, ...]:
    """Return specialist role ids."""
    return tuple(role.id for role in config.specialist_roles)


def review_pack_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known review pack ids."""
    return tuple(str(pack["id"]) for pack in catalog.review_packs)


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


def discover_changed_paths(workspace_root: Path) -> tuple[str, ...]:
    """Return changed paths from git status when available."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()

    changed: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        path_part = line[3:]
        if " -> " in path_part:
            _, path_part = path_part.split(" -> ", 1)
        normalized = path_part.strip()
        if normalized and normalized not in changed:
            changed.append(normalized)
    return tuple(changed)


def auto_language_specialists(
    workspace_root: Path,
    changed_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Infer language-specific reviewers from changed paths."""
    candidate_paths = changed_paths or discover_changed_paths(workspace_root)
    normalized_paths = tuple(
        raw_path.replace("\\", "/").lstrip("./") for raw_path in candidate_paths
    )
    has_python = any(
        normalized.startswith("python/")
        or normalized.startswith("tests/")
        or Path(normalized).suffix.lower() in PYTHON_SUFFIXES
        for normalized in normalized_paths
    )
    has_cpp = any(
        Path(normalized).suffix.lower() in CPP_SUFFIXES
        or any(normalized == marker or normalized.startswith(marker) for marker in CPP_PATH_MARKERS)
        for normalized in normalized_paths
    )
    has_docs_or_runtime = any(
        Path(normalized).suffix.lower() in DOC_SUFFIXES | CONFIG_SUFFIXES
        or any(normalized == marker or normalized.startswith(marker) for marker in DOC_OR_RUNTIME_PATH_MARKERS)
        for normalized in normalized_paths
    )
    return tuple(
        role_id
        for role_id, enabled in (
            ("python_reviewer", has_python),
            ("cpp_reviewer", has_cpp),
            ("docs_workflow_steward", has_docs_or_runtime),
        )
        if enabled
    )


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


def workflow_spawn_budget(catalog: TaskCatalog, family_id: str) -> tuple[int, int]:
    """Return the active and write-capable spawn budget for one workflow family."""
    family = resolve_workflow_family(catalog, family_id)
    raw_budget = family.get("spawn_budget")
    if not isinstance(raw_budget, dict):
        raise RuntimeError(f"workflow family spawn_budget must be a mapping for {family_id}")
    active = raw_budget.get("active_subagents")
    max_write = raw_budget.get("max_write_subagents")
    if not isinstance(active, int) or active < 1:
        raise RuntimeError(f"workflow family active_subagents must be >= 1 for {family_id}")
    if not isinstance(max_write, int) or max_write < 1:
        raise RuntimeError(f"workflow family max_write_subagents must be >= 1 for {family_id}")
    return active, max_write


def codex_runtime_max_threads() -> int:
    """Return the configured runtime max_threads from .codex/config.toml."""
    config_path = ROOT / ".codex" / "config.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    agents = data.get("agents")
    if not isinstance(agents, dict):
        raise RuntimeError("missing [agents] section in .codex/config.toml")
    max_threads = agents.get("max_threads")
    if not isinstance(max_threads, int) or max_threads < 1:
        raise RuntimeError("agents.max_threads must be an integer >= 1")
    return max_threads


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
        raise RuntimeError(f"workflow family roles must be a mapping for {family['id']}")
    family_specialists = _as_string_tuple(
        family_roles.get("specialists"),
        f"workflow_families[{family['id']}].roles.specialists",
    )
    selected: list[str] = []

    for role_id in _as_string_tuple(task.get("specialists"), f"tasks[{task_id}].specialists"):
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
) -> tuple[Role, ...]:
    """Return the active roles for one run."""
    if full_team:
        return config.always_on_roles + config.specialist_roles
    always_on_roles = workflow_always_on_roles(config, catalog, workflow_family_id)
    enabled_roles = tuple(resolve_role(config, name) for name in enabled_specialists)
    selected_roles = list(always_on_roles)
    selected_ids = {role.id for role in selected_roles}
    for role in enabled_roles:
        if role.id not in selected_ids:
            selected_roles.append(role)
            selected_ids.add(role.id)
    enabled_set = {role.id for role in enabled_roles}
    enabled_activations = {
        role.activation for role in enabled_roles if role in config.specialist_roles
    }
    selected_specialists = tuple(
        role
        for role in config.specialist_roles
        if role.id in enabled_set or role.activation in enabled_activations
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
    role_ids = _as_string_tuple(
        family_roles.get("always_on"),
        f"workflow_families[{workflow_family_id}].roles.always_on",
    )
    if not role_ids:
        return config.always_on_roles
    return tuple(resolve_role(config, role_id) for role_id in role_ids)


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


def iter_artifacts(config: TeamConfig, roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return unique artifact filenames in deterministic order."""
    return tuple(
        dict.fromkeys(
            (
                *(output for role in roles for output in role.required_outputs),
                config.artifacts["team_manifest"],
                config.artifacts["verification"],
            )
        )
    )


def resolve_role_document_packet(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
) -> RoleDocumentPacket:
    """Resolve explicit read-before-work packet for one role."""
    spec = ROLE_DOCUMENT_PACKET_SPECS.get(role.id, {})
    artifact_keys = _as_string_tuple(
        spec.get("artifact_keys"),
        f"document_packet[{role.id}].artifact_keys",
    )
    workspace_paths = _as_string_tuple(
        spec.get("workspace_paths"),
        f"document_packet[{role.id}].workspace_paths",
    )
    entries: list[DocumentPacketEntry] = []
    seen_paths: set[Path] = set()

    def add_entry(entry: DocumentPacketEntry) -> None:
        resolved_path = entry.path.resolve()
        if resolved_path in seen_paths:
            return
        seen_paths.add(resolved_path)
        entries.append(
            DocumentPacketEntry(
                path=resolved_path,
                rationale=entry.rationale,
            )
        )

    for artifact_key in artifact_keys:
        if artifact_key not in config.artifacts:
            raise RuntimeError(
                f"document packet artifact key missing for role {role.id}: {artifact_key}"
            )
        add_entry(
            DocumentPacketEntry(
                path=(report_dir / config.artifacts[artifact_key]).resolve(),
                rationale=f"run artifact:{artifact_key}",
            )
        )
    for relative_path in workspace_paths:
        add_entry(
            DocumentPacketEntry(
                path=resolve_workspace_document_path(workspace_root, relative_path),
                rationale=f"workspace doc:{relative_path}",
            )
        )
    for entry in resolve_cross_cutting_document_packet(workspace_root):
        add_entry(entry)
    return RoleDocumentPacket(
        role_id=role.id,
        read_before_work=tuple(entries),
        must_cite_before_edit=bool(spec.get("must_cite_before_edit", False)),
        notes=str(spec.get("notes", "")),
    )


def render_template(template_name: str, replacements: dict[str, str]) -> str:
    """Load and fill a text template from agents/templates."""
    content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def has_template(artifact_name: str) -> bool:
    """Return whether a template exists for one artifact filename."""
    return (TEMPLATE_ROOT / artifact_name).is_file()


def required_output_templates_missing(
    config: TeamConfig,
    roles: tuple[Role, ...],
    allowed_missing: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return required output templates that are missing from agents/templates."""
    return tuple(
        dict.fromkeys(
            output
            for role in roles
            for output in role.required_outputs
            if output not in allowed_missing and not has_template(output)
        )
    )


def create_run_bundle(spec: RunBundleSpec) -> tuple[str, ...]:
    """Create the standard files for a run."""
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    spec.report_dir.mkdir(parents=True, exist_ok=True)
    created_files = list(iter_artifacts(spec.config, spec.roles))
    for artifact in created_files:
        if has_template(artifact):
            (spec.report_dir / artifact).write_text(
                render_template(artifact, replacements),
                encoding="utf-8",
            )
    (spec.report_dir / spec.config.artifacts["team_manifest"]).write_text(
        build_manifest(spec),
        encoding="utf-8",
    )
    (spec.report_dir / spec.config.artifacts["verification"]).write_text(
        "\n".join(
            [
                f"run_id={spec.run_id}",
                f"task={spec.task}",
                f"owner={spec.owner}",
                f"created_at_utc={spec.created_at_iso}",
                "status=pending",
                "user_completion_report=locked",
                "closeout_gate_status=pending",
                "",
            ]
        ),
        encoding="utf-8",
    )
    unique_created_files: list[str] = []
    for artifact in created_files:
        if artifact not in unique_created_files:
            unique_created_files.append(artifact)
    return tuple(unique_created_files)


def build_manifest(spec: RunBundleSpec) -> str:
    """Build the team manifest yaml."""
    workflow_family = None
    if spec.workflow_family_id:
        workflow_family = resolve_workflow_family(
            load_task_catalog(spec.config),
            spec.workflow_family_id,
        )
    lines = manifest_run_lines(spec, workflow_family)
    lines.extend(manifest_role_lines(spec, workflow_family))
    lines.extend(manifest_context_policy_lines(spec.config))
    lines.extend(manifest_quality_gate_lines(spec.config))
    lines.extend(manifest_artifact_lines(spec.config, spec.roles))
    return "\n".join(lines) + "\n"


def manifest_run_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render run-level manifest fields."""
    lines = [
        "run:",
        f"  id: {spec.run_id}",
        f"  task: {spec.task!r}",
        f"  owner: {spec.owner!r}",
        f"  created_at_utc: {spec.created_at_iso}",
        f"  report_dir: {str(spec.report_dir)!r}",
        f"  workspace_root: {str(spec.workspace_root)!r}",
        f"  team_config: {str(TEAM_CONFIG_PATH)!r}",
        f"  team_runtime: {str(ROOT / 'tools' / 'agent_tools' / 'agent_team.py')!r}",
        f"  task_catalog: {str(ROOT / str(spec.config.team['task_catalog']))!r}",
        "  subagent_lifecycle_policy:",
        "    fresh_subagents_required: true",
        "    reuse_for_new_task: forbidden",
        "    previous_task_subagent_reuse: forbidden",
        "    close_before_user_completion: true",
        "    closeout_gate_key: subagents_closed",
        "    closeout_evidence_section: 'Subagent Lifecycle Evidence'",
        "    handoff_rule: 'Do not send_input to agents from another user request; spawn a "
        "fresh run-local agent for each new task or stage wave.'",
    ]
    communication_protocol = spec.config.team.get("communication_protocol")
    if communication_protocol is not None:
        lines.append(f"  communication_protocol: {str(ROOT / str(communication_protocol))!r}")
    if workflow_family is not None:
        lines.append("  write_scope_policy:")
        lines.append("    parent_managed: true")
        lines.append("    disjoint_write_scopes_required: true")
        lines.append("    overlapping_write_scopes: serialize_or_split_worktree")
        _, max_write_subagents = workflow_spawn_budget(
            load_task_catalog(spec.config),
            spec.workflow_family_id,
        )
        lines.append(f"    max_write_subagents: {max_write_subagents}")
        lines.append("  workflow_family:")
        lines.append(f"    id: {spec.workflow_family_id}")
        lines.append(f"    name: {str(workflow_family['name'])!r}")
        lines.extend(render_subagent_prompt_packet(workflow_family, indent="  "))
    lines.append("  cross_cutting_document_packet:")
    cross_cutting_packet = resolve_cross_cutting_document_packet(spec.workspace_root)
    for entry in cross_cutting_packet:
        lines.append(f"    - path: {str(entry.path)!r}")
        lines.append(f"      rationale: {entry.rationale!r}")
    return lines


def manifest_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render role entries for the team manifest."""
    lines = ["roles:"]
    for role in spec.roles:
        lines.extend(manifest_one_role_lines(spec, workflow_family, role))
    return lines


def manifest_one_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    role: Role,
) -> list[str]:
    """Render one role entry for the team manifest."""
    lines = [
        f"  - id: {role.id}",
        f"    activation: {role.activation}",
        "    status: pending",
    ]
    if role.codex_agents:
        lines.append("    codex_agents:")
        for codex_agent in role.codex_agents:
            lines.append(f"      - {codex_agent}")
    lines.extend(manifest_prompt_contract_lines(role, workflow_family))
    lines.append("    owns:")
    for responsibility in role.owns:
        lines.append(f"      - {responsibility}")
    lines.append("    required_outputs:")
    for output in role.required_outputs:
        lines.append(f"      - {output}")
    lines.extend(manifest_write_policy_lines(spec, role))
    lines.extend(manifest_document_packet_lines(spec, role))
    return lines


def manifest_prompt_contract_lines(
    role: Role,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render prompt contract lines for one role."""
    lines = ["    prompt_contract:"]
    lines.append(
        "      assignment_prompt: "
        f"{role_prompt_contract(role, workflow_family).replace(chr(10), ' ')!r}"
    )
    lines.append("      prompt_must_include:")
    for item in role_prompt_must_include(role):
        lines.append(f"        - {item!r}")
    return lines


def manifest_write_policy_lines(spec: RunBundleSpec, role: Role) -> list[str]:
    """Render resolved write policy lines for one role."""
    scope = resolve_role_write_scope(
        config=spec.config,
        role=role,
        report_dir=spec.report_dir,
        workspace_root=spec.workspace_root,
    )
    lines = ["    write_policy:"]
    lines.append(f"      mode: {scope.mode}")
    lines.append(f"      requires_worktree_scope: {str(scope.requires_worktree_scope).lower()}")
    if scope.notes:
        lines.append(f"      notes: {scope.notes!r}")
    if scope.worktree_scope_file is not None:
        lines.append(f"      worktree_scope_file: {str(scope.worktree_scope_file)!r}")
    if scope.unresolved_reason is not None:
        lines.append(f"      unresolved_reason: {scope.unresolved_reason!r}")
    lines.append("      allowed_files:")
    for path in scope.allowed_files:
        lines.append(f"        - {str(path)!r}")
    lines.append("      allowed_directories:")
    for path in scope.allowed_directories:
        lines.append(f"        - {str(path)!r}")
    return lines


def manifest_document_packet_lines(spec: RunBundleSpec, role: Role) -> list[str]:
    """Render explicit document packet lines for one role."""
    document_packet = resolve_role_document_packet(
        spec.config,
        role,
        spec.report_dir,
        spec.workspace_root,
    )
    lines = ["    document_packet:"]
    lines.append(
        f"      must_cite_before_edit: {str(document_packet.must_cite_before_edit).lower()}"
    )
    if document_packet.notes:
        lines.append(f"      notes: {document_packet.notes!r}")
    lines.append("      read_before_work:")
    for entry in document_packet.read_before_work:
        lines.append(f"        - path: {str(entry.path)!r}")
        lines.append(f"          rationale: {entry.rationale!r}")
    return lines


def manifest_context_policy_lines(config: TeamConfig) -> list[str]:
    """Render context-sharing policy lines."""
    lines = ["context_policies:"]
    for policy in config.context_policies:
        lines.append("  - roles:")
        for role_name in tuple(policy["roles"]):
            lines.append(f"      - {role_name}")
        lines.append(f"    mode: {policy['mode']}")
        lines.append("    share_only:")
        for artifact in tuple(policy["share_only"]):
            lines.append(f"      - {artifact}")
        lines.append("    do_not_share:")
        for artifact in tuple(policy["do_not_share"]):
            lines.append(f"      - {artifact}")
    return lines


def manifest_quality_gate_lines(config: TeamConfig) -> list[str]:
    """Render quality gate lines."""
    lines = ["quality_gates:"]
    for gate in config.quality_gates:
        lines.append(f"  - {gate}")
    return lines


def manifest_artifact_lines(config: TeamConfig, roles: tuple[Role, ...]) -> list[str]:
    """Render artifact lines."""
    lines = ["artifacts:"]
    for artifact in iter_artifacts(config, roles):
        lines.append(f"  - {artifact}")
    return lines


def render_subagent_prompt_packet(
    workflow_family: dict[str, object],
    indent: str,
) -> list[str]:
    """Render workflow-specific subagent prompt instructions for the manifest."""
    prompt = workflow_family.get("subagent_prompt")
    if not isinstance(prompt, dict):
        return []
    lines = [f"{indent}subagent_prompt_packet:"]
    purpose = str(prompt.get("purpose", ""))
    if purpose:
        lines.append(f"{indent}  purpose: {purpose!r}")
    for key in ("prompt_preamble", "workflow_focus", "reviewer_prompt"):
        values = prompt.get(key, [])
        if not isinstance(values, list):
            values = []
        lines.append(f"{indent}  {key}:")
        for value in values:
            lines.append(f"{indent}    - {str(value)!r}")
    return lines


def role_prompt_contract(role: Role, workflow_family: dict[str, object] | None) -> str:
    """Return the reusable prompt contract for one manifest role entry."""
    family_name = (
        str(workflow_family["name"])
        if workflow_family is not None
        else "the selected workflow"
    )
    write_scope = (
        "write only in the manifest write_policy scope and avoid paths assigned to other writers"
        if role.write_policy.mode != "read_only"
        else "do not edit repository files"
    )
    return (
        f"You are the {role.id} role for {family_name}. Read the run-level "
        "subagent_prompt_packet, cross_cutting_document_packet, and your document_packet before "
        f"work. {write_scope}. Return findings or outputs tied to request_clause_ids, artifact "
        "paths, dependency-file headers for every edited or created text file, remaining planned "
        "work, and the next required gate."
    )


def role_prompt_must_include(role: Role) -> tuple[str, ...]:
    """Return handoff fields every invocation prompt should include for one role."""
    common = [
        "request_clause_ids",
        "run_report_dir",
        "team_manifest_path",
        "subagent_lifecycle_policy",
        "cross_cutting_document_packet",
        "role_document_packet",
        "expected_output_artifacts",
        "dependency_files_header_plan",
        "next_review_gate",
    ]
    if role.write_policy.mode != "read_only":
        common.extend(("write_policy", "allowed_files_or_directories"))
    if role.id == "implementer":
        common.extend(
            (
                "implementation_source_packet",
                "design_to_implementation_trace",
                "test_plan_item",
                "remaining_planned_work_units",
            )
        )
    if role.id.endswith("_reviewer") or role.id in {"change_reviewer", "final_reviewer"}:
        common.extend(("findings_first_output", "approve_revise_or_escalate_decision"))
    return tuple(common)


def resolve_role_write_scope(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
) -> RoleWriteScope:
    """Resolve concrete write paths for one role."""
    allowed_files = role_allowed_artifact_files(config, role, report_dir)
    scope_file = find_worktree_scope_file(workspace_root)
    allowed_directories = role_allowed_directories(role, workspace_root, scope_file)
    unresolved_reason = role_write_scope_unresolved_reason(role, scope_file, allowed_directories)
    return RoleWriteScope(
        role_id=role.id,
        mode=role.write_policy.mode,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
        requires_worktree_scope=role.write_policy.requires_worktree_scope,
        worktree_scope_file=scope_file,
        unresolved_reason=unresolved_reason,
        notes=role.write_policy.notes,
    )


def role_allowed_artifact_files(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
) -> tuple[Path, ...]:
    """Resolve generated artifact files one role may write."""
    return tuple(
        sorted(
            {
                (report_dir / config.artifacts[artifact_key]).resolve()
                for artifact_key in role.write_policy.allowed_artifacts
            },
            key=str,
        )
    )


def role_allowed_directories(
    role: Role,
    workspace_root: Path,
    scope_file: Path | None,
) -> tuple[Path, ...]:
    """Resolve worktree-scope directories one role may write."""
    section_heading = role_write_scope_section(role.write_policy.mode)
    if section_heading == "":
        return ()
    directories = _resolve_scope_directories(scope_file, workspace_root, section_heading)
    return tuple(sorted(directories, key=str))


def role_write_scope_section(mode: str) -> str:
    """Return the WORKTREE_SCOPE.md section used by one write-policy mode."""
    sections = {
        "worktree_scope_plus_artifacts": "## Editable Directories",
        "runtime_outputs_plus_artifacts": "## Runtime Output Directories",
    }
    return sections.get(mode, "")


def role_write_scope_unresolved_reason(
    role: Role,
    scope_file: Path | None,
    allowed_directories: tuple[Path, ...],
) -> str | None:
    """Return why a write policy requiring worktree scope is unresolved."""
    if not role.write_policy.requires_worktree_scope:
        return None
    if scope_file is None:
        return "WORKTREE_SCOPE.md is required but was not found in the workspace root."
    if allowed_directories:
        return None
    if role.write_policy.mode == "runtime_outputs_plus_artifacts":
        return "WORKTREE_SCOPE.md was found, but no runtime output directories could be parsed."
    return "WORKTREE_SCOPE.md was found, but no editable directories could be parsed."


def collect_changed_files(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Collect modified, staged, deleted, renamed, and untracked files."""
    changed: set[Path] = set()
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(_git_paths(workspace_root, ["ls-files", "--others", "--exclude-standard"]))
    ignored = tuple(root.resolve() for root in ignored_roots)
    filtered_paths = [
        path.resolve()
        for path in changed
        if not any(path.resolve() == root or root in path.resolve().parents for root in ignored)
    ]
    return tuple(sorted(filtered_paths, key=str))


def validate_role_write_scope(
    config: TeamConfig,
    role_name: str,
    report_dir: Path,
    workspace_root: Path,
    files: tuple[Path, ...] | None = None,
    report_dir_snapshot: dict[str, str] | None = None,
    workspace_snapshot: dict[str, str] | None = None,
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[RoleWriteScope, tuple[Path, ...]]:
    """Validate changed files against the role's allowed write scope."""
    role = resolve_role(config, role_name)
    resolved_report_dir = report_dir.resolve()
    resolved_workspace_root = workspace_root.resolve()
    scope = resolve_role_write_scope(config, role, resolved_report_dir, resolved_workspace_root)
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    if workspace_snapshot is None:
        changed_files = set(
            collect_changed_files(
                resolved_workspace_root,
                ignored_roots=(resolved_report_dir,),
            )
        )
        changed_files = {
            path
            for path in changed_files
            if not any(
                _matches_ignored_path(path.resolve(), ignored_path)
                for ignored_path in resolved_ignored_paths
            )
        }
    else:
        changed_files = set(
            collect_workspace_change_delta(
                resolved_workspace_root,
                workspace_snapshot,
                ignored_roots=(resolved_report_dir,),
                ignored_paths=resolved_ignored_paths,
            )
        )
    if report_dir_snapshot is not None:
        changed_files.update(collect_directory_changes(resolved_report_dir, report_dir_snapshot))
    changed_files.update(path.resolve() for path in (files or ()))
    violations = tuple(sorted(
        (path for path in changed_files if not _path_allowed(path.resolve(), scope)),
        key=str,
    ))
    return scope, violations


def slugify(value: str) -> str:
    """Return an ASCII slug that is safe for file paths."""
    ascii_only = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug or "task"


def make_run_id(task: str, created_at: datetime) -> str:
    """Build a stable default run id."""
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(task)[:40]}"


def _parse_role(raw_role: dict[str, object], default_activation: str) -> Role:
    """Parse a role from json."""
    raw_write_policy = dict(raw_role["write_policy"])
    write_policy = WritePolicy(
        mode=str(raw_write_policy["mode"]),
        allowed_artifacts=tuple(str(item) for item in raw_write_policy["allowed_artifacts"]),
        requires_worktree_scope=bool(raw_write_policy.get("requires_worktree_scope", False)),
        notes=str(raw_write_policy.get("notes", "")),
    )
    return Role(
        id=str(raw_role["id"]),
        owns=tuple(str(item) for item in raw_role["owns"]),
        required_outputs=tuple(str(item) for item in raw_role["required_outputs"]),
        activation=str(raw_role.get("activation", default_activation)),
        write_policy=write_policy,
        codex_agents=tuple(str(item) for item in raw_role.get("codex_agents", ())),
    )


def find_worktree_scope_file(workspace_root: Path) -> Path | None:
    """Return the worktree scope file if present."""
    candidate = workspace_root.resolve() / "WORKTREE_SCOPE.md"
    if candidate.is_file():
        return candidate
    return None


def _resolve_scope_directories(
    scope_file: Path | None,
    workspace_root: Path,
    section_heading: str,
) -> list[Path]:
    """Parse directories from one named WORKTREE_SCOPE.md section."""
    if scope_file is None:
        return []
    content = scope_file.read_text(encoding="utf-8")
    in_section = False
    directories: list[Path] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == section_heading
            continue
        if not in_section or not stripped.startswith("- "):
            continue
        path_text = _extract_markdown_code_or_bullet_value(stripped[2:])
        if not path_text:
            continue
        path_text = path_text.rstrip("/").strip()
        directories.append((workspace_root / path_text).resolve())
    return directories


def _extract_markdown_code_or_bullet_value(text: str) -> str:
    """Extract the primary path token from a markdown bullet."""
    code_match = re.search(r"`([^`]+)`", text)
    if code_match is not None:
        return code_match.group(1)
    plain_text = text.split(" -- ", 1)[0]
    plain_text = text.split(" - ", 1)[0] if plain_text == text else plain_text
    plain_text = text.split(" (", 1)[0] if plain_text == text else plain_text
    return plain_text.strip()


def _git_paths(workspace_root: Path, args: list[str]) -> set[Path]:
    """Run git and convert stdout paths into absolute Paths."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            paths.add((workspace_root / stripped).resolve())
    return paths


def capture_directory_snapshot(root: Path) -> dict[str, str]:
    """Return a content-hash snapshot for every file below one directory."""
    resolved_root = root.resolve()
    if not resolved_root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(resolved_root.rglob("*")):
        if path.is_file():
            snapshot[str(path.resolve())] = _file_sha256(path)
    return snapshot


def load_directory_snapshot(path: Path) -> dict[str, str]:
    """Load a directory snapshot from json."""
    return {
        str(snapshot_path): str(digest)
        for snapshot_path, digest in json.loads(path.read_text(encoding="utf-8")).items()
    }


def write_directory_snapshot(root: Path, output_path: Path) -> None:
    """Write the current directory snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(capture_directory_snapshot(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def capture_workspace_change_snapshot(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return a snapshot for the workspace's current git-visible changes."""
    changed_paths = collect_changed_files(workspace_root, ignored_roots=ignored_roots)
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    snapshot: dict[str, str] = {}
    for path in changed_paths:
        resolved_path = path.resolve()
        if any(
            _matches_ignored_path(resolved_path, ignored_path)
            for ignored_path in resolved_ignored_paths
        ):
            continue
        snapshot[str(resolved_path)] = _path_snapshot_digest(resolved_path)
    return snapshot


def write_workspace_change_snapshot(
    workspace_root: Path,
    output_path: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> None:
    """Write the current git-visible workspace change snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            capture_workspace_change_snapshot(
                workspace_root,
                ignored_roots=ignored_roots,
                ignored_paths=ignored_paths,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def collect_directory_changes(root: Path, before_snapshot: dict[str, str]) -> tuple[Path, ...]:
    """Return files that changed within one directory since the captured snapshot."""
    after_snapshot = capture_directory_snapshot(root)
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def collect_workspace_change_delta(
    workspace_root: Path,
    before_snapshot: dict[str, str],
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Return git-visible workspace paths that changed since the captured snapshot."""
    after_snapshot = capture_workspace_change_snapshot(
        workspace_root,
        ignored_roots=ignored_roots,
        ignored_paths=ignored_paths,
    )
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def _path_allowed(path: Path, scope: RoleWriteScope) -> bool:
    """Return whether one path falls within the resolved write scope."""
    if path in scope.allowed_files:
        return True
    for directory in scope.allowed_directories:
        if path == directory or directory in path.parents:
            return True
    return False


def _matches_ignored_path(path: Path, ignored_path: Path) -> bool:
    """Return whether a path should be ignored during write-scope collection."""
    if path == ignored_path:
        return True
    return ignored_path.is_dir() and ignored_path in path.parents


def _file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_snapshot_digest(path: Path) -> str:
    """Return a digest for one path, including deletions."""
    if path.is_file():
        return _file_sha256(path)
    return "__missing__"


def _as_mapping_tuple(value: object, field_name: str) -> tuple[dict[str, object], ...]:
    """Validate a list of mappings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError(f"{field_name} entries must be mappings")
        normalized.append(dict(item))
    return tuple(normalized)


def _as_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate a list of strings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{field_name} entries must be strings")
        normalized.append(item)
    return tuple(normalized)
