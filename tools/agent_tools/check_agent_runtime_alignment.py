#!/usr/bin/env python3
# @dependency-start
# responsibility Checks agent runtime alignment agent workflow state.
# upstream design ../README.md shared automation index
# upstream implementation ./vendor_skill_adapters.py validates third-party skill adapter surface
# @dependency-end

"""Validate that agent runtime surfaces, task catalog, and bundle outputs align."""

from __future__ import annotations

import json
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml
from agent_team import (
    ROOT,
    Role,
    RunBundleSpec,
    TaskCatalog,
    TeamConfig,
    codex_runtime_max_depth,
    codex_runtime_max_threads,
    create_run_bundle,
    default_specialists_for_task,
    load_task_catalog,
    load_team_config,
    required_output_templates_missing,
    resolve_cross_cutting_document_packet,
    resolve_role,
    resolve_role_document_packet,
    task_ids,
    workflow_always_on_roles,
    workflow_spawn_budget,
)
from vendor_skill_adapters import VendorSkillValidator

PROJECT_CONFIG_PATH = ROOT / ".codex" / "config.toml"
HOOKS_JSON_PATH = ROOT / ".codex" / "hooks.json"
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SKILL_SHIM_ROOT = ROOT / ".agents" / "skills"
FRONTMATTER_OPEN_MARKER = "---\n"
MAX_VENDOR_SKILL_FINDINGS_IN_MESSAGE = 8
EXPECTED_MODEL_CONTEXT_WINDOW = 1_000_000
EXPECTED_TOOL_OUTPUT_TOKEN_LIMIT = 4096
EXPECTED_MAX_THREADS = 24
EXPECTED_MAX_DEPTH = 2
EXPECTED_JOB_MAX_RUNTIME_SECONDS = 3600
INITIAL_INTAKE_MARKERS = {
    "requirements_organizer": "Initial intake wave role: own user-request clauses",
    "explorer": "Initial intake wave role: own evidence, reuse, and stale-surface inventory",
    "execution_planner": "Initial intake wave role: own stage order",
}
SUBAGENT_PROTOCOL_DOCS = (
    ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md",
    ROOT / "agents" / "TASK_WORKFLOWS.md",
)
TOOL_RESULT_ROUTE_MARKERS = (
    "raw checker/stat artifacts -> artifact_reviewer",
    "reader-facing narrative interpretation -> report_reviewer",
    "OOP mechanical reports -> oop_readability_reviewer",
    "repo-wide drift and integration risk -> project_reviewer",
)
PERMANENT_TEAM_MAPPING_HEADING = "## Permanent Team To Codex Mapping"


@dataclass(frozen=True)
class AlignmentWorkspace:
    """Temporary workspace used for runtime bundle smoke checks."""

    workspace_root: Path
    report_root: Path


def resolve_packet_probe_workspace() -> Path:
    """Return the workspace root that should be used for packet path existence checks."""
    candidate = ROOT.parent.parent.resolve()
    try:
        if (candidate / "vendor" / "agent-canon").resolve() == ROOT.resolve():
            return candidate
    except FileNotFoundError:
        pass
    return ROOT.resolve()


def ensure(condition: bool, message: str) -> None:
    """Raise when one expected condition is not met."""
    if not condition:
        raise RuntimeError(message)


def parse_codex_agents() -> dict[str, dict[str, object]]:
    """Load every Codex agent config."""
    parsed: dict[str, dict[str, object]] = {}
    for path in sorted(CODEX_AGENT_ROOT.glob("*.toml")):
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        name = str(payload.get("name", path.stem))
        payload["__file_name"] = path.name
        payload["__file_stem"] = path.stem
        parsed[name] = payload
    return parsed


def load_project_config_toml() -> dict[str, object]:
    """Load the shared Codex project config."""
    return tomllib.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))


def validate_project_config() -> None:
    """Check that the shared project config exposes the review route."""
    config = load_project_config_toml()
    ensure(isinstance(config.get("review_model"), str), "review_model must be a string")
    ensure(
        config.get("model_context_window") == EXPECTED_MODEL_CONTEXT_WINDOW,
        f"model_context_window must remain {EXPECTED_MODEL_CONTEXT_WINDOW}",
    )
    ensure(
        config.get("tool_output_token_limit") == EXPECTED_TOOL_OUTPUT_TOKEN_LIMIT,
        f"tool_output_token_limit must remain {EXPECTED_TOOL_OUTPUT_TOKEN_LIMIT}",
    )
    features = config.get("features", {})
    ensure(isinstance(features, dict), "features must be a mapping")
    ensure(features.get("hooks") is True, "features.hooks must be true")
    ensure(features.get("goals") is True, "features.goals must be true")
    ensure(features.get("multi_agent") is True, "features.multi_agent must be true")
    ensure("codex_hooks" not in features, "deprecated features.codex_hooks must be absent")
    ensure("profiles" not in config, "project-local profiles must stay out of shared config")
    ensure(
        "agent_model_policy" not in config,
        "agent_model_policy must stay out of .codex/config.toml; use .codex/agents/*.toml",
    )
    validate_skill_config(config)
    agents = config.get("agents", {})
    ensure(isinstance(agents, dict), "agents must be a mapping")
    ensure(
        agents.get("max_threads") == EXPECTED_MAX_THREADS,
        f"agents.max_threads must remain {EXPECTED_MAX_THREADS}",
    )
    ensure(
        agents.get("max_depth") == EXPECTED_MAX_DEPTH,
        f"agents.max_depth must remain {EXPECTED_MAX_DEPTH}",
    )
    ensure(
        agents.get("job_max_runtime_seconds") == EXPECTED_JOB_MAX_RUNTIME_SECONDS,
        f"agents.job_max_runtime_seconds must remain {EXPECTED_JOB_MAX_RUNTIME_SECONDS}",
    )
    codex_agents = parse_codex_agents()
    registry = {
        key: value
        for key, value in agents.items()
        if isinstance(value, dict)
    }
    missing_registry = sorted(set(codex_agents) - set(registry))
    extra_registry = sorted(set(registry) - set(codex_agents))
    ensure(
        not missing_registry,
        f"missing .codex/config.toml agent registry: {', '.join(missing_registry)}",
    )
    ensure(
        not extra_registry,
        f"stale .codex/config.toml agent registry: {', '.join(extra_registry)}",
    )
    for role_id, agent_config in codex_agents.items():
        registered = registry[role_id]
        ensure(
            registered.get("config_file") == f"agents/{agent_config['__file_name']}",
            f"{role_id} config_file must point at agents/{agent_config['__file_name']}",
        )
        ensure(
            registered.get("description") == agent_config.get("description"),
            f"{role_id} registry description must match agent TOML",
        )


def expected_skill_config_paths() -> tuple[str, ...]:
    """Return the project-local skill paths that must be enabled in Codex config."""
    return tuple(
        sorted(
            f"../{path.relative_to(ROOT).as_posix()}"
            for path in SKILL_SHIM_ROOT.glob("*/SKILL.md")
        )
    )


def validate_skill_config(config: dict[str, object]) -> None:
    """Check that every local public skill is wired through official skills.config."""
    skills = config.get("skills", {})
    ensure(isinstance(skills, dict), "skills must be a mapping")
    entries = skills.get("config", [])
    ensure(isinstance(entries, list), "skills.config must be a list")
    observed: list[str] = []
    for entry in entries:
        ensure(isinstance(entry, dict), "skills.config entries must be mappings")
        path_value = str(entry.get("path", "")).strip()
        ensure(path_value, "skills.config entry path must be non-empty")
        ensure(entry.get("enabled") is True, f"skills.config {path_value} must be enabled")
        resolved = (PROJECT_CONFIG_PATH.parent / path_value).resolve()
        ensure(resolved.is_file(), f"skills.config path missing: {path_value}")
        ensure(resolved.name == "SKILL.md", f"skills.config path must point at SKILL.md: {path_value}")
        ensure(
            resolved.is_relative_to(SKILL_SHIM_ROOT.resolve()),
            f"skills.config path is outside .agents/skills: {path_value}",
        )
        observed.append(path_value)
    expected = expected_skill_config_paths()
    ensure(
        sorted(observed) == list(expected),
        "skills.config must enable every .agents/skills/*/SKILL.md path",
    )


def validate_project_hooks() -> None:
    """Check that project hooks cover active safety and completion guardrails."""
    hooks_payload = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    hooks = hooks_payload.get("hooks", {})
    ensure(isinstance(hooks, dict), "hooks.json hooks must be a mapping")

    for event in ("UserPromptSubmit", "PostToolUse", "Stop"):
        entries = hooks.get(event, [])
        ensure(isinstance(entries, list) and entries, f"{event} hook must be configured")

    hooks_text = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    ensure(
        "mcp_session_context.sh" not in hooks_text,
        "mcp_session_context.sh must not be wired as a startup hook",
    )
    for hook_script in (
        "log_archive_mount_warning.py",
        "prompt_secret_guard.py",
        "goal_completion_guard.py",
        "oop_readability_guard.py",
        "log_surface_inventory_guard.py",
        "notebook_quality_guard.py",
        "style_checker_guard.py",
        "skill_usage_logger.py",
    ):
        ensure(hook_script in hooks_text, f"{hook_script} must be wired in hooks.json")
        ensure((ROOT / ".codex" / "hooks" / hook_script).is_file(), f"{hook_script} must exist")


def validate_codex_agent_settings() -> None:
    """Check that Codex agent TOML files carry the executable model settings."""
    configs = parse_codex_agents()
    valid_efforts = {"low", "medium", "high", "xhigh"}
    for role_id, config in sorted(configs.items()):
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        model = config.get("model")
        effort = config.get("model_reasoning_effort")
        ensure(isinstance(model, str) and model, f"{role_id} model must be a non-empty string")
        ensure(
            isinstance(effort, str) and effort in valid_efforts,
            f"{role_id} model_reasoning_effort must be one of {sorted(valid_efforts)}",
        )

    for role_id, marker in INITIAL_INTAKE_MARKERS.items():
        instructions = str(configs[role_id].get("developer_instructions", ""))
        ensure(marker in instructions, f"{role_id} missing initial intake marker")


def validate_team_config_references() -> None:
    """Check role references inside the team config."""
    config = load_team_config()
    role_ids = {role.id for role in config.always_on_roles + config.specialist_roles}
    codex_agent_ids = set(parse_codex_agents())

    for role in config.always_on_roles + config.specialist_roles:
        ensure(role.required_outputs, f"{role.id} must declare required_outputs")
        ensure(role.write_policy.allowed_artifacts, f"{role.id} must declare allowed_artifacts")
        for codex_agent_id in role.codex_agents:
            ensure(
                codex_agent_id in codex_agent_ids,
                f"{role.id} references missing Codex agent: {codex_agent_id}",
            )
        for output in role.required_outputs:
            ensure(
                output.endswith((".md", ".yaml", ".txt")),
                f"{role.id} output has unsupported suffix: {output}",
            )
        for artifact_key in role.write_policy.allowed_artifacts:
            ensure(
                artifact_key in config.artifacts,
                f"{role.id} allowed_artifact key missing from artifacts: {artifact_key}",
            )
            mapped = config.artifacts[artifact_key]
            ensure(
                mapped in role.required_outputs,
                f"{role.id} artifact mapping mismatch: {artifact_key} -> {mapped}",
            )

    implementer = resolve_role(config, "implementer")
    ensure(
        implementer.codex_agents[:2] == ("spark_worker", "worker"),
        "implementer codex_agents must start with spark_worker,worker",
    )

    missing_templates = required_output_templates_missing(
        config,
        config.always_on_roles + config.specialist_roles,
        allowed_missing=(
            config.artifacts["team_manifest"],
            config.artifacts["verification"],
        ),
    )
    ensure(
        not missing_templates,
        f"missing required output templates: {', '.join(sorted(missing_templates))}",
    )

    for handoff in config.handoffs:
        ensure(handoff["from"] in role_ids, f"handoff references unknown role: {handoff['from']}")
        ensure(handoff["to"] in role_ids, f"handoff references unknown role: {handoff['to']}")

    for policy in config.context_policies:
        for role_id in policy["roles"]:
            ensure(role_id in role_ids, f"context policy references unknown role: {role_id}")

    for rule in config.activation_rules:
        ensure(rule["role"] in role_ids, f"activation rule references unknown role: {rule['role']}")

    packet_probe_workspace = resolve_packet_probe_workspace()
    packet_probe_report_dir = ROOT / "reports" / "agents" / "_packet_probe"
    for entry in resolve_cross_cutting_document_packet(packet_probe_workspace):
        ensure(entry.path.exists(), f"cross-cutting document packet path missing: {entry.path}")
    for role in config.always_on_roles + config.specialist_roles:
        packet = resolve_role_document_packet(
            config=config,
            role=role,
            report_dir=packet_probe_report_dir,
            workspace_root=packet_probe_workspace,
        )
        for entry in packet.read_before_work:
            if "/reports/agents/_packet_probe/" in str(entry.path):
                continue
            ensure(entry.path.exists(), f"{role.id} document packet path missing: {entry.path}")


def validate_task_catalog_references() -> None:
    """Check task catalog roles and task-family relationships."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    runtime_max_threads = codex_runtime_max_threads()
    role_ids = {role.id for role in config.always_on_roles + config.specialist_roles}
    family_ids = {family["id"] for family in catalog.workflow_families}

    for family in catalog.workflow_families:
        roles = family.get("roles", {})
        ensure(isinstance(roles, dict), f"family {family['id']} roles must be a mapping")
        prompt = family.get("subagent_prompt")
        ensure(isinstance(prompt, dict), f"family {family['id']} subagent_prompt must be a mapping")
        for key in ("purpose", "prompt_preamble", "workflow_focus", "reviewer_prompt"):
            ensure(key in prompt, f"family {family['id']} subagent_prompt missing {key}")
        ensure(
            str(prompt["purpose"]).strip(),
            f"family {family['id']} subagent_prompt purpose empty",
        )
        for key in ("prompt_preamble", "workflow_focus", "reviewer_prompt"):
            values = prompt[key]
            ensure(
                isinstance(values, list) and all(str(value).strip() for value in values),
                f"family {family['id']} subagent_prompt {key} must be a non-empty list",
            )
        for bucket in ("always_on", "specialists"):
            members = roles.get(bucket, [])
            ensure(isinstance(members, list), f"family {family['id']} {bucket} must be a list")
            for role_id in members:
                ensure(
                    role_id in role_ids,
                    f"family {family['id']} references unknown role {role_id}",
                )
        active_budget, max_write_budget = workflow_spawn_budget(catalog, str(family["id"]))
        ensure(
            active_budget <= runtime_max_threads,
            f"family {family['id']} active_subagents exceeds runtime max_threads",
        )
        ensure(
            max_write_budget >= 1,
            f"family {family['id']} max_write_subagents must be >= 1",
        )
        ensure(
            max_write_budget <= active_budget,
            f"family {family['id']} max_write_subagents exceeds active_subagents",
        )

    for task_id in task_ids(catalog):
        task = next(task for task in catalog.tasks if task["id"] == task_id)
        ensure(
            task["family"] in family_ids,
            f"task {task_id} references unknown family {task['family']}",
        )
        _ = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=task_id,
            include_default_review_packs=True,
        )

    for pack in catalog.review_packs:
        for role_id in pack.get("specialists", []):
            ensure(
                role_id in role_ids,
                f"review pack {pack['id']} references unknown role {role_id}",
            )
        for task_id in pack.get("default_for_tasks", []):
            ensure(
                task_id in task_ids(catalog),
                f"review pack {pack['id']} default task missing: {task_id}",
            )
        for task_id in pack.get("optional_for_tasks", []):
            ensure(
                task_id in task_ids(catalog),
                f"review pack {pack['id']} optional task missing: {task_id}",
            )


def validate_public_skill_shims() -> None:
    """Check that public skill catalog entries have discoverable SKILL.md shims."""
    catalog_path = ROOT / "agents" / "skills" / "catalog.yaml"
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    ensure(isinstance(data, dict), "skill catalog must parse as a mapping")
    families = data.get("skill_families", [])
    ensure(isinstance(families, list), "skill_families must be a list")

    for entry in families:
        ensure(isinstance(entry, dict), "skill_families entries must be mappings")
        skill_id = str(entry["id"])
        canonical_doc = ROOT / str(entry["canonical_doc"])
        shim = ROOT / str(entry["shim"])
        ensure(canonical_doc.is_file(), f"{skill_id} canonical doc missing: {canonical_doc}")
        ensure(shim.is_file(), f"{skill_id} shim missing: {shim}")
        ensure(
            shim.resolve().is_relative_to(SKILL_SHIM_ROOT.resolve()),
            f"{skill_id} shim is outside the Codex skill root: {shim}",
        )
        text = shim.read_text(encoding="utf-8")
        ensure(text.startswith(FRONTMATTER_OPEN_MARKER), f"{skill_id} shim must start with YAML frontmatter")
        ensure(
            "\n---\n" in text[len(FRONTMATTER_OPEN_MARKER) :],
            f"{skill_id} shim YAML frontmatter must close",
        )
        ensure(f"name: {skill_id}" in text, f"{skill_id} shim frontmatter name mismatch")


def validate_subagent_protocol_docs() -> None:
    """Check subagent routing docs keep machine-enforceable boundaries."""
    for path in SUBAGENT_PROTOCOL_DOCS:
        text = path.read_text(encoding="utf-8")
        ensure("Initial Intake Wave" in text, f"{path} missing initial intake contract")
        ensure("Wave Plan Contract" in text, f"{path} missing wave plan contract")
        ensure("Agent Wave Ledger" in text, f"{path} missing Agent Wave Ledger contract")
        for role_id in INITIAL_INTAKE_MARKERS:
            ensure(role_id in text, f"{path} missing initial intake role {role_id}")
        ensure(
            "max_depth = 2" in text and "delegated_spawn_policy" in text,
            f"{path} must state bounded nested spawn and delegated_spawn_policy",
        )
        ensure(
            "subagents do not spawn subagents" not in text,
            f"{path} must not prohibit bounded nested subagent spawn",
        )
        ensure("depth は固定しません" not in text, f"{path} must not allow unfixed depth wording")
    subagents_text = (ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md").read_text(
        encoding="utf-8"
    )
    for marker in TOOL_RESULT_ROUTE_MARKERS:
        ensure(marker in subagents_text, f"CODEX_SUBAGENTS.md missing tool route marker: {marker}")
    validate_permanent_team_mapping(load_team_config(), subagents_text)


def parse_permanent_team_mapping_roles(markdown_text: str) -> set[str]:
    """Return role IDs listed in the CODEX_SUBAGENTS permanent-team mapping table."""
    in_mapping = False
    roles: set[str] = set()
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped == PERMANENT_TEAM_MAPPING_HEADING:
            in_mapping = True
            continue
        if in_mapping and stripped.startswith("## "):
            break
        if not in_mapping or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "Permanent Team Role" or set(cells[0]) <= {"-", " "}:
            continue
        if cells[0].startswith("`") and cells[0].endswith("`"):
            roles.add(cells[0].strip("`"))
    return roles


def validate_permanent_team_mapping(config: TeamConfig, markdown_text: str) -> None:
    """Check every configured permanent-team role has a Codex route mapping row."""
    expected_roles = {
        role.id
        for role in config.always_on_roles + config.specialist_roles
    }
    mapped_roles = parse_permanent_team_mapping_roles(markdown_text)
    missing_roles = sorted(expected_roles - mapped_roles)
    stale_roles = sorted(mapped_roles - expected_roles)
    ensure(
        not missing_roles,
        "CODEX_SUBAGENTS.md permanent-team mapping missing roles: "
        + ", ".join(missing_roles),
    )
    ensure(
        not stale_roles,
        "CODEX_SUBAGENTS.md permanent-team mapping has stale roles: "
        + ", ".join(stale_roles),
    )


def validate_vendor_skill_adapters() -> None:
    """Check that third-party skill vendor adapters are manifest-backed."""
    findings = VendorSkillValidator(ROOT).validate(require_adapters=True)
    ensure(
        not findings,
        "vendor skill adapter findings: "
        + "; ".join(
            finding.render()
            for finding in findings[:MAX_VENDOR_SKILL_FINDINGS_IN_MESSAGE]
        ),
    )


def alignment_workspace(tmp_root: Path) -> AlignmentWorkspace:
    """Return the temporary workspace layout for bundle smoke checks."""
    return AlignmentWorkspace(
        workspace_root=tmp_root / "workspace",
        report_root=tmp_root / "reports",
    )


def initialize_alignment_workspace(workspace: AlignmentWorkspace) -> None:
    """Create the directories and scope file required by bundle smoke checks."""
    workspace.workspace_root.mkdir(parents=True, exist_ok=True)
    workspace.report_root.mkdir(parents=True, exist_ok=True)
    (workspace.workspace_root / "python").mkdir()
    (workspace.workspace_root / "documents").mkdir()
    (workspace.workspace_root / "reports" / "runtime").mkdir(parents=True)
    (workspace.workspace_root / "WORKTREE_SCOPE.md").write_text(
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
        ),
        encoding="utf-8",
    )


def current_utc_iso() -> str:
    """Return a second-granularity UTC timestamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def task_by_id(catalog: TaskCatalog, task_id: str) -> dict[str, object]:
    """Return one task-catalog row by id."""
    return next(task for task in catalog.tasks if task["id"] == task_id)


def roles_for_task(config: TeamConfig, catalog: TaskCatalog, task_id: str) -> tuple[Role, ...]:
    """Return always-on plus default specialist roles for one task."""
    enabled = default_specialists_for_task(
        config=config,
        catalog=catalog,
        task_id=task_id,
        include_default_review_packs=True,
    )
    task = task_by_id(catalog, task_id)
    always_on = workflow_always_on_roles(config, catalog, str(task["family"]))
    return tuple(always_on) + tuple(
        resolve_role(config, role_id) for role_id in enabled
    )


def missing_required_outputs(report_dir: Path, roles: tuple[Role, ...]) -> list[str]:
    """Return required role outputs not created in one report directory."""
    return [
        output
        for role in roles
        for output in role.required_outputs
        if not (report_dir / output).is_file()
    ]


def ensure_required_outputs(report_dir: Path, roles: tuple[Role, ...], label: str) -> None:
    """Ensure all role-required outputs exist in one report directory."""
    missing_outputs = missing_required_outputs(report_dir, roles)
    ensure(
        not missing_outputs,
        f"{label} bundle did not generate required outputs: "
        + ", ".join(sorted(set(missing_outputs))),
    )


def ensure_task_manifest(config: TeamConfig, report_dir: Path, task_id: str) -> None:
    """Ensure one generated task manifest preserves subagent handoff contracts."""
    manifest_text = (report_dir / config.artifacts["team_manifest"]).read_text(
        encoding="utf-8",
    )
    manifest = yaml.safe_load(manifest_text)
    ensure(isinstance(manifest, dict), f"task {task_id} manifest must be a mapping")
    run = manifest.get("run")
    ensure(isinstance(run, dict), f"task {task_id} manifest missing run mapping")
    spawn_budget = run.get("spawn_budget")
    ensure(
        isinstance(spawn_budget, dict),
        f"task {task_id} manifest missing run.spawn_budget",
    )
    catalog = load_task_catalog(config)
    task = task_by_id(catalog, task_id)
    expected_active, expected_max_write = workflow_spawn_budget(
        catalog,
        str(task["family"]),
    )
    expected_runtime_max_threads = codex_runtime_max_threads()
    expected_runtime_max_depth = codex_runtime_max_depth()
    ensure(
        spawn_budget.get("active_subagents") == expected_active,
        f"task {task_id} manifest run.spawn_budget.active_subagents mismatch",
    )
    ensure(
        spawn_budget.get("max_write_subagents") == expected_max_write,
        f"task {task_id} manifest run.spawn_budget.max_write_subagents mismatch",
    )
    ensure(
        spawn_budget.get("runtime_max_threads") == expected_runtime_max_threads,
        f"task {task_id} manifest run.spawn_budget.runtime_max_threads mismatch",
    )
    ensure(
        spawn_budget.get("runtime_max_depth") == expected_runtime_max_depth,
        f"task {task_id} manifest run.spawn_budget.runtime_max_depth mismatch",
    )
    ensure(
        spawn_budget.get("initial_three_agent_intake_is_total_cap") is False,
        f"task {task_id} manifest must state initial intake is not a total cap",
    )
    ensure(
        "workflow_families[].spawn_budget" in str(spawn_budget.get("source", "")),
        f"task {task_id} manifest run.spawn_budget source missing catalog reference",
    )
    ensure(
        spawn_budget.get("max_write_subagents_scope") == "write-capable subagents only",
        f"task {task_id} manifest run.spawn_budget max_write scope unclear",
    )
    delegated_spawn_policy = run.get("delegated_spawn_policy")
    ensure(
        isinstance(delegated_spawn_policy, dict),
        f"task {task_id} manifest missing run.delegated_spawn_policy",
    )
    ensure(
        delegated_spawn_policy.get("dynamic_mid_task_spawn") == "allowed",
        f"task {task_id} manifest must allow dynamic mid-task spawn",
    )
    ensure(
        delegated_spawn_policy.get("delegated_child_spawn") == "allowed_with_bounded_packet",
        f"task {task_id} manifest delegated child spawn policy mismatch",
    )
    required_fields = delegated_spawn_policy.get("handoff_required_fields")
    expected_handoff_fields = {
        "owner",
        "child_role",
        "input_packet",
        "expected_output",
        "write_scope",
        "validation_route",
        "review_gate",
        "remaining_spawn_budget",
    }
    ensure(
        isinstance(required_fields, list)
        and expected_handoff_fields.issubset({str(item) for item in required_fields}),
        f"task {task_id} manifest delegated spawn handoff fields incomplete",
    )
    spawn_wave_recommendation = run.get("spawn_wave_recommendation")
    ensure(
        isinstance(spawn_wave_recommendation, dict),
        f"task {task_id} manifest missing run.spawn_wave_recommendation",
    )
    initial_wave = spawn_wave_recommendation.get("initial_wave_agent_types")
    manifest_roles = manifest.get("roles")
    total_agent_candidates: list[str] = []
    if isinstance(manifest_roles, list):
        for role in manifest_roles:
            if not isinstance(role, dict):
                continue
            codex_agents = role.get("codex_agents")
            if not isinstance(codex_agents, list):
                continue
            for agent_type in codex_agents:
                if isinstance(agent_type, str) and agent_type not in total_agent_candidates:
                    total_agent_candidates.append(agent_type)
    ensure(
        isinstance(initial_wave, list) and len(initial_wave) >= 1,
        f"task {task_id} manifest must recommend at least one initial agent type",
    )
    if expected_active > 4 and len(total_agent_candidates) > 3:
        ensure(
            len(initial_wave) > 3,
            f"task {task_id} manifest must not collapse multi-agent tasks to three agents",
        )
    ensure(
        len(initial_wave) <= expected_active,
        f"task {task_id} manifest initial wave exceeds active spawn budget",
    )
    write_scope_policy = run.get("write_scope_policy")
    ensure(
        isinstance(write_scope_policy, dict),
        f"task {task_id} manifest missing run.write_scope_policy",
    )
    ensure(
        write_scope_policy.get("max_write_subagents") == expected_max_write,
        f"task {task_id} manifest run.write_scope_policy.max_write_subagents mismatch",
    )
    ensure(
        write_scope_policy.get("overlapping_write_scopes")
        == "serialize_current_checkout_waves",
        f"task {task_id} manifest overlapping write scope policy must serialize current checkout waves",
    )
    ensure(
        "active_subagents" not in write_scope_policy,
        f"task {task_id} manifest write_scope_policy must not carry active_subagents",
    )
    ensure(
        "subagent_prompt_packet:" in manifest_text,
        f"task {task_id} manifest missing subagent_prompt_packet",
    )
    ensure(
        "subagent_lifecycle_policy:" in manifest_text,
        f"task {task_id} manifest missing subagent_lifecycle_policy",
    )
    ensure(
        "fresh_subagents_required: true" in manifest_text
        and "reuse_for_new_task: forbidden" in manifest_text,
        f"task {task_id} manifest missing fresh subagent lifecycle policy",
    )
    ensure(
        "prompt_contract:" in manifest_text,
        f"task {task_id} manifest missing role prompt_contract",
    )
    ensure_manifest_abstract_design_prompt_contracts(manifest, task_id)


def ensure_manifest_abstract_design_prompt_contracts(
    manifest: dict[object, object],
    task_id: str,
) -> None:
    """Ensure generated role prompts preserve ADF trace contracts."""
    roles = manifest.get("roles")
    ensure(isinstance(roles, list), f"task {task_id} manifest missing roles list")

    def prompt_fields(role_id: str) -> set[str] | None:
        for role in roles:
            if not isinstance(role, dict) or role.get("id") != role_id:
                continue
            prompt_contract = role.get("prompt_contract")
            ensure(
                isinstance(prompt_contract, dict),
                f"task {task_id} role {role_id} missing prompt_contract",
            )
            raw_fields = prompt_contract.get("prompt_must_include")
            ensure(
                isinstance(raw_fields, list),
                f"task {task_id} role {role_id} missing prompt_must_include",
            )
            return {str(field) for field in raw_fields}
        return None

    expected_role_fields = {
        "designer": {
            "abstract_design_frame",
            "responsibility_model",
            "concept_or_layer_model",
        },
        "design_reviewer": {
            "abstract_design_frame_review",
            "adf_before_file_scope",
            "adf_to_implementation_trace",
        },
        "implementer": {
            "abstract_design_frame",
            "implementation_source_packet",
            "design_to_implementation_trace",
        },
        "change_reviewer": {
            "abstract_design_frame_trace",
            "implementation_source_packet_entry",
            "revise_if_slice_only_justified_by_nearest_file_helper_or_current_finding",
        },
        "final_reviewer": {
            "abstract_design_frame_trace",
            "spec_to_product_trace",
            "review_finding_incorporation_trace",
        },
    }
    for role_id, required_fields in expected_role_fields.items():
        fields = prompt_fields(role_id)
        if fields is None:
            continue
        ensure(
            required_fields.issubset(fields),
            f"task {task_id} role {role_id} missing abstract design prompt fields",
        )


def validate_task_bundle_output(
    config: TeamConfig,
    catalog: TaskCatalog,
    workspace: AlignmentWorkspace,
    task_id: str,
    created_at_iso: str,
) -> None:
    """Create and validate one catalog task bundle."""
    task = task_by_id(catalog, task_id)
    roles = roles_for_task(config, catalog, task_id)
    report_dir = workspace.report_root / task_id
    create_run_bundle(
        RunBundleSpec(
            config=config,
            report_dir=report_dir,
            run_id=task_id,
            task=f"alignment smoke for {task_id}",
            owner="codex",
            created_at_iso=created_at_iso,
            roles=roles,
            workspace_root=workspace.workspace_root,
            workflow_family_id=str(task["family"]),
        )
    )
    ensure_required_outputs(report_dir, roles, f"task {task_id}")
    ensure_task_manifest(config, report_dir, task_id)


def validate_full_team_bundle_output(
    config: TeamConfig,
    workspace: AlignmentWorkspace,
    created_at_iso: str,
) -> None:
    """Create and validate a full specialist-team bundle."""
    full_team_roles = config.always_on_roles + config.specialist_roles
    full_team_dir = workspace.report_root / "full-team"
    create_run_bundle(
        RunBundleSpec(
            config=config,
            report_dir=full_team_dir,
            run_id="full-team",
            task="alignment smoke full team",
            owner="codex",
            created_at_iso=created_at_iso,
            roles=full_team_roles,
            workspace_root=workspace.workspace_root,
            workflow_family_id="comprehensive_development",
        )
    )
    ensure_required_outputs(full_team_dir, full_team_roles, "full-team")


def validate_bundle_outputs() -> None:
    """Create temporary bundles for every catalog task and full-team run."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    created_at_iso = current_utc_iso()

    with tempfile.TemporaryDirectory(prefix="agent-runtime-alignment-") as tmp_dir:
        workspace = alignment_workspace(Path(tmp_dir))
        initialize_alignment_workspace(workspace)

        for task_id in task_ids(catalog):
            validate_task_bundle_output(
                config=config,
                catalog=catalog,
                workspace=workspace,
                task_id=task_id,
                created_at_iso=created_at_iso,
            )

        validate_full_team_bundle_output(
            config=config,
            workspace=workspace,
            created_at_iso=created_at_iso,
        )


def main() -> int:
    """Run all runtime-alignment checks."""
    validate_project_config()
    validate_project_hooks()
    validate_codex_agent_settings()
    validate_team_config_references()
    validate_task_catalog_references()
    validate_public_skill_shims()
    validate_subagent_protocol_docs()
    validate_vendor_skill_adapters()
    validate_bundle_outputs()
    print("AGENT_RUNTIME_ALIGNMENT=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
