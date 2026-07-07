#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Checks agent runtime alignment agent workflow state.
# upstream design ../README.md shared automation index
# upstream design ../../agents/skills/README.md public skill surface contract
# upstream design ../../agents/canonical/skills.md official system skill delegation boundary
# upstream design ../../agents/internal-routines/README.md internal routine surface contract
# upstream design ../../agents/skills/catalog.yaml public skill routing and related-skill catalog
# upstream implementation ./vendor_skill_adapters.py validates third-party skill adapter surface
# @dependency-end

"""Validate that agent runtime surfaces, task catalog, and bundle outputs align."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

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
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave,
    required_output_templates_missing,
    resolve_cross_cutting_document_packet,
    resolve_role,
    resolve_role_document_packet,
    select_roles,
    task_ids,
    workflow_spawn_budget,
)
from vendor_skill_adapters import VendorSkillValidator

PROJECT_CONFIG_PATH = ROOT / ".codex" / "config.toml"
PROJECT_SKILL_CONFIG_PATH = ROOT / ".codex" / "project-config.toml"
HOOKS_JSON_PATH = ROOT / ".codex" / "hooks.json"
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SKILL_SHIM_ROOT = ROOT / ".agents" / "skills"
PROJECT_SKILL_LANE = ".codex/project-skills"
PUBLIC_SKILL_DOC_ROOT = ROOT / "agents" / "skills"
INTERNAL_ROUTINE_ROOT = ROOT / "agents" / "internal-routines"
FRONTMATTER_OPEN_MARKER = "---\n"
MAX_VENDOR_SKILL_FINDINGS_IN_MESSAGE = 8
EXPECTED_MODEL_CONTEXT_WINDOW = 1_000_000
EXPECTED_TOOL_OUTPUT_TOKEN_LIMIT = 4096
EXPECTED_MAX_THREADS = 24
EXPECTED_MAX_DEPTH = 2
EXPECTED_JOB_MAX_RUNTIME_SECONDS = 3600
MIN_DYNAMIC_SPAWN_BUDGET = 4
INTAKE_AGENT_COUNT = 3
ALLOWED_AGENT_RUNTIME_KEYS = {
    "max_threads",
    "max_depth",
    "job_max_runtime_seconds",
}
SKILL_ROUTING_STAGE_POLICIES = {"active", "deferred"}
PRIVATE_SKILL_PREFIX = "_"
PUBLIC_SKILL_README_DUPLICATE_ROW = re.compile(
    r"^\|\s*`[^`]+`\s*\|.*`agents/skills/[^`]+\.md`.*`\.agents/skills/[^`]+/SKILL\.md`",
    re.MULTILINE,
)
OFFICIAL_SYSTEM_SKILLS = (
    "imagegen",
    "openai-docs",
    "plugin-creator",
    "skill-creator",
    "skill-installer",
)
OFFICIAL_SYSTEM_SKILL_DELEGATION_DOCS = (
    Path("agents/skills/README.md"),
    Path("agents/canonical/skills.md"),
)
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
NON_SPAWN_WAVE_ROLE_IDS = {"manager", "verifier", "auditor"}
PRE_FINAL_REVIEW_ROLE_IDS = {
    "change_reviewer",
    "research_reviewer",
    "experiment_reviewer",
    "report_reviewer",
    "reproducibility_reviewer",
    "artifact_reviewer",
    "scientific_computing_reviewer",
    "benchmark_reviewer",
    "fair_data_reviewer",
    "ml_science_reviewer",
    "citation_evidence_reviewer",
    "notation_definition_reviewer",
    "logic_gap_reviewer",
    "infra_reviewer",
    "python_reviewer",
    "cpp_reviewer",
}


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


def require_mapping(value: object, message: str) -> dict[str, object]:
    """Return a string-keyed mapping or raise with the supplied message."""
    if not isinstance(value, dict):
        raise RuntimeError(message)
    normalized: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise RuntimeError(message)
        normalized[key] = item
    return normalized


def require_list(value: object, message: str) -> list[object]:
    """Return a list or raise with the supplied message."""
    if not isinstance(value, list):
        raise RuntimeError(message)
    return list(cast(list[object], value))


def require_string_list(value: object, message: str) -> list[str]:
    """Return a list of strings or raise with the supplied message."""
    raw_items = require_list(value, message)
    items: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            raise RuntimeError(message)
        items.append(item)
    return items


def require_string(value: object, message: str) -> str:
    """Return a string or raise with the supplied message."""
    if not isinstance(value, str):
        raise RuntimeError(message)
    return value


def require_prompt_entries(value: object, message: str) -> list[str]:
    """Return prompt entries that are strings or string-valued mappings."""
    raw_items = require_list(value, message)
    entries: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            entries.append(item)
            continue
        if isinstance(item, dict):
            mapping = require_mapping(cast(object, item), message)
            ensure(bool(mapping), message)
            rendered: dict[str, str] = {}
            for key, mapping_value in mapping.items():
                rendered[key] = require_string(mapping_value, message)
            entries.append(str(rendered))
            continue
        raise RuntimeError(message)
    return entries


def parse_codex_agents() -> dict[str, dict[str, object]]:
    """Load every Codex agent config."""
    parsed: dict[str, dict[str, object]] = {}
    for path in sorted(CODEX_AGENT_ROOT.glob("*.toml")):
        raw_payload: object = tomllib.loads(path.read_text(encoding="utf-8"))
        payload = require_mapping(raw_payload, f"{path} must parse as a mapping")
        name = str(payload.get("name", path.stem))
        payload["__file_name"] = path.name
        payload["__file_stem"] = path.stem
        parsed[name] = payload
    return parsed


def load_project_config_toml() -> dict[str, object]:
    """Load the shared Codex project config."""
    raw_config: object = tomllib.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))
    return require_mapping(raw_config, ".codex/config.toml must parse as a mapping")


def load_project_skill_config_toml() -> dict[str, object]:
    """Load the optional parent-owned Codex skill overlay."""
    if not PROJECT_SKILL_CONFIG_PATH.is_file():
        return {}
    raw_config: object = tomllib.loads(PROJECT_SKILL_CONFIG_PATH.read_text(encoding="utf-8"))
    return require_mapping(
        raw_config,
        ".codex/project-config.toml must parse as a mapping",
    )


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
    features = require_mapping(config.get("features", {}), "features must be a mapping")
    ensure(features.get("hooks") is True, "features.hooks must be true")
    ensure(features.get("goals") is True, "features.goals must be true")
    ensure(features.get("multi_agent") is True, "features.multi_agent must be true")
    ensure("codex_hooks" not in features, "deprecated features.codex_hooks must be absent")
    ensure("profiles" not in config, "project-local profiles must stay out of shared config")
    ensure(
        "agent_model_policy" not in config,
        "agent_model_policy must stay out of .codex/config.toml; use .codex/agents/*.toml",
    )
    validate_skill_config(config, load_project_skill_config_toml())
    agents = require_mapping(config.get("agents", {}), "agents must be a mapping")
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
    unsupported_agent_scalars = sorted(
        key
        for key, value in agents.items()
        if key not in ALLOWED_AGENT_RUNTIME_KEYS and not isinstance(value, dict)
    )
    ensure(
        not unsupported_agent_scalars,
        "unsupported scalar keys under .codex/config.toml [agents]: "
        + ", ".join(unsupported_agent_scalars)
        + "; keep task policy in agents/task_catalog.yaml or generated team_manifest.yaml",
    )
    codex_agents = parse_codex_agents()
    registry: dict[str, dict[str, object]] = {}
    for key, value in agents.items():
        if isinstance(value, dict):
            registry[key] = require_mapping(
                cast(object, value),
                f"agents.{key} registry entry must be a mapping",
            )
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
    """Return public project-local skill paths that must be enabled in Codex config."""
    return tuple(
        sorted(
            f"../{path.relative_to(ROOT).as_posix()}"
            for path in SKILL_SHIM_ROOT.glob("*/SKILL.md")
            if is_public_skill_id(path.parent.name)
        )
    )


def is_private_skill_id(skill_id: str) -> bool:
    """Return whether one skill id is private and runtime-internal."""
    return skill_id.startswith(PRIVATE_SKILL_PREFIX)


def is_public_skill_id(skill_id: str) -> bool:
    """Return whether one skill id belongs to the user-facing public catalog."""
    return bool(skill_id) and not is_private_skill_id(skill_id)


def validate_skill_config(
    config: dict[str, object],
    project_config: dict[str, object] | None = None,
) -> None:
    """Check shared and parent-owned skill config lanes."""
    skills = require_mapping(config.get("skills", {}), "skills must be a mapping")
    entries = require_list(skills.get("config", []), "skills.config must be a list")
    observed_agentcanon: list[str] = []
    for entry in entries:
        entry = require_mapping(entry, "skills.config entries must be mappings")
        path_value = validate_skill_config_entry(entry, PROJECT_CONFIG_PATH)
        resolved = (PROJECT_CONFIG_PATH.parent / path_value).resolve()
        ensure(
            resolved.is_relative_to(SKILL_SHIM_ROOT.resolve()),
            "project-owned skills.config entries must live in .codex/project-config.toml: "
            f"{path_value}",
        )
        ensure(
            is_public_skill_id(resolved.parent.name),
            f"private skill shims must stay out of skills.config: {path_value}",
        )
        observed_agentcanon.append(path_value)
    expected = expected_skill_config_paths()
    ensure(
        sorted(observed_agentcanon) == list(expected),
        "skills.config must enable every .agents/skills/*/SKILL.md path",
    )
    validate_project_skill_config(project_config or {})


def validate_project_skill_config(project_config: dict[str, object]) -> None:
    """Check optional parent-owned project skill config entries."""
    skills = require_mapping(project_config.get("skills", {}), "project skills must be a mapping")
    entries = require_list(
        skills.get("config", []),
        "project skills.config must be a list",
    )
    observed_project: list[str] = []
    for entry in entries:
        entry = require_mapping(entry, "project skills.config entries must be mappings")
        path_value = validate_skill_config_entry(entry, PROJECT_SKILL_CONFIG_PATH)
        resolved = (PROJECT_SKILL_CONFIG_PATH.parent / path_value).resolve()
        ensure(
            is_project_skill_lane_path(resolved),
            f"skills.config path is outside allowed skill lanes: {path_value}",
        )
        ensure(
            is_public_skill_id(resolved.parent.name),
            f"private project skill shims must stay out of skills.config: {path_value}",
        )
        observed_project.append(path_value)
    ensure(
        len(observed_project) == len(set(observed_project)),
        "project-owned skills.config entries must not be duplicated",
    )


def validate_skill_config_entry(entry: dict[str, object], config_path: Path) -> str:
    """Validate one skills.config entry and return its path."""
    path_value = str(entry.get("path", "")).strip()
    ensure(bool(path_value), "skills.config entry path must be non-empty")
    ensure(entry.get("enabled") is True, f"skills.config {path_value} must be enabled")
    resolved = (config_path.parent / path_value).resolve()
    ensure(resolved.is_file(), f"skills.config path missing: {path_value}")
    ensure(resolved.name == "SKILL.md", f"skills.config path must point at SKILL.md: {path_value}")
    return path_value


def is_project_skill_lane_path(path: Path) -> bool:
    """Return whether one SKILL.md path belongs to the project-owned skill lane."""
    lane_root = (PROJECT_CONFIG_PATH.parent / "project-skills").resolve()
    try:
        return path.is_relative_to(lane_root)
    except ValueError:
        return False


def validate_project_hooks() -> None:
    """Check that project hooks cover active safety and completion guardrails."""
    raw_hooks_payload: object = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    hooks_payload = require_mapping(
        raw_hooks_payload, "hooks.json top-level must be a mapping"
    )
    ensure(set(hooks_payload) == {"hooks"}, "hooks.json top-level keys must match Codex hook schema")
    hooks = require_mapping(
        hooks_payload.get("hooks", {}), "hooks.json hooks must be a mapping"
    )

    for event in ("UserPromptSubmit", "PostToolUse", "Stop"):
        entries = require_list(hooks.get(event, []), f"{event} hook must be configured")
        ensure(bool(entries), f"{event} hook must be configured")

    hooks_text = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    ensure(
        "mcp_session_context.sh" not in hooks_text,
        "mcp_session_context.sh must not be wired as a startup hook",
    )
    ensure("hook_dispatcher.py" in hooks_text, "hooks.json must invoke hook_dispatcher.py")
    dispatcher_scripts = configured_dispatcher_scripts()
    for hook_script in (
        "log_archive_mount_warning.py",
        "prompt_secret_guard.py",
        "branch_worktree_guard.py",
        "goal_completion_guard.py",
        "oop_readability_guard.py",
        "log_surface_inventory_guard.py",
        "notebook_quality_guard.py",
        "style_checker_guard.py",
        "skill_usage_logger.py",
    ):
        ensure(hook_script in dispatcher_scripts, f"{hook_script} must be wired through hook_dispatcher.py")
        ensure((ROOT / ".codex" / "hooks" / hook_script).is_file(), f"{hook_script} must exist")


def configured_dispatcher_scripts() -> set[str]:
    """Return hook scripts declared by the project dispatcher."""
    scripts: set[str] = set()
    dispatcher = ROOT / ".codex" / "hooks" / "hook_dispatcher.py"
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        result = subprocess.run(
            ["python3", str(dispatcher), "--list", event],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        raw_payload: object = json.loads(result.stdout)
        payload = require_mapping(
            raw_payload, f"dispatcher list output for {event} must be a mapping"
        )
        events = require_mapping(
            payload.get("events", {}),
            f"dispatcher list output for {event} must contain events",
        )
        entries = require_list(
            events.get(event, []),
            f"dispatcher list output for {event} must be a list",
        )
        for entry in entries:
            entry = require_mapping(
                entry, f"dispatcher entry for {event} must be a mapping"
            )
            script = entry.get("script", "")
            ensure(
                isinstance(script, str) and bool(script),
                f"dispatcher entry for {event} must name a script",
            )
            scripts.add(require_string(script, f"dispatcher entry for {event} must name a script"))
    return scripts


def validate_codex_agent_settings() -> None:
    """Check that Codex agent TOML files carry the executable model settings."""
    configs = parse_codex_agents()
    valid_efforts = {"low", "medium", "high", "xhigh"}
    for role_id, config in sorted(configs.items()):
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        model = config.get("model")
        effort = config.get("model_reasoning_effort")
        ensure(
            isinstance(model, str) and bool(model),
            f"{role_id} model must be a non-empty string",
        )
        ensure(
            isinstance(effort, str) and effort in valid_efforts,
            f"{role_id} model_reasoning_effort must be one of {sorted(valid_efforts)}",
        )

    for role_id, marker in INITIAL_INTAKE_MARKERS.items():
        instructions = str(configs[role_id].get("developer_instructions", ""))
        ensure(marker in instructions, f"{role_id} missing intake responsibility marker")


def validate_team_config_references() -> None:
    """Check role references inside the team config."""
    config = load_team_config()
    role_ids = {role.id for role in config.always_on_roles + config.specialist_roles}
    codex_agent_ids = set(parse_codex_agents())

    for role in config.always_on_roles + config.specialist_roles:
        ensure(bool(role.required_outputs), f"{role.id} must declare required_outputs")
        ensure(
            bool(role.write_policy.allowed_artifacts),
            f"{role.id} must declare allowed_artifacts",
        )
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
        from_role = require_string(handoff.get("from"), "handoff from must be a string")
        to_role = require_string(handoff.get("to"), "handoff to must be a string")
        ensure(from_role in role_ids, f"handoff references unknown role: {from_role}")
        ensure(to_role in role_ids, f"handoff references unknown role: {to_role}")

    for policy in config.context_policies:
        for role_id in require_string_list(
            policy.get("roles"), "context policy roles must be a list"
        ):
            ensure(role_id in role_ids, f"context policy references unknown role: {role_id}")

    for rule in config.activation_rules:
        rule_role = require_string(rule.get("role"), "activation rule role must be a string")
        ensure(rule_role in role_ids, f"activation rule references unknown role: {rule_role}")

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
    family_ids = {
        require_string(family.get("id"), "workflow family id must be a string")
        for family in catalog.workflow_families
    }

    for family in catalog.workflow_families:
        family_id = require_string(family.get("id"), "workflow family id must be a string")
        roles = require_mapping(
            family.get("roles", {}), f"family {family_id} roles must be a mapping"
        )
        prompt = family.get("subagent_prompt")
        prompt = require_mapping(
            prompt, f"family {family_id} subagent_prompt must be a mapping"
        )
        for key in ("purpose", "prompt_preamble", "workflow_focus", "reviewer_prompt"):
            ensure(key in prompt, f"family {family_id} subagent_prompt missing {key}")
        purpose = require_string(
            prompt.get("purpose"), f"family {family_id} subagent_prompt purpose empty"
        )
        ensure(
            bool(purpose.strip()),
            f"family {family_id} subagent_prompt purpose empty",
        )
        for key in ("prompt_preamble", "workflow_focus", "reviewer_prompt"):
            values = require_prompt_entries(
                prompt.get(key),
                f"family {family_id} subagent_prompt {key} must be a non-empty list",
            )
            ensure(
                bool(values) and all(value.strip() for value in values),
                f"family {family_id} subagent_prompt {key} must be a non-empty list",
            )
        for bucket in ("always_on", "specialists"):
            members = require_string_list(
                roles.get(bucket, []), f"family {family_id} {bucket} must be a list"
            )
            for role_id in members:
                ensure(
                    role_id in role_ids,
                    f"family {family_id} references unknown role {role_id}",
                )
        active_budget, max_write_budget = workflow_spawn_budget(catalog, family_id)
        ensure(
            active_budget <= runtime_max_threads,
            f"family {family_id} active_subagents exceeds runtime max_threads",
        )
        ensure(
            max_write_budget >= 1,
            f"family {family_id} max_write_subagents must be >= 1",
        )
        ensure(
            max_write_budget <= active_budget,
            f"family {family_id} max_write_subagents exceeds active_subagents",
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
        pack_id = require_string(pack.get("id"), "review pack id must be a string")
        for role_id in require_string_list(
            pack.get("specialists", []), f"review pack {pack_id} specialists must be a list"
        ):
            ensure(
                role_id in role_ids,
                f"review pack {pack_id} references unknown role {role_id}",
            )
        for task_id in require_string_list(
            pack.get("default_for_tasks", []),
            f"review pack {pack_id} default_for_tasks must be a list",
        ):
            ensure(
                task_id in task_ids(catalog),
                f"review pack {pack_id} default task missing: {task_id}",
            )
        for task_id in require_string_list(
            pack.get("optional_for_tasks", []),
            f"review pack {pack_id} optional_for_tasks must be a list",
        ):
            ensure(
                task_id in task_ids(catalog),
                f"review pack {pack_id} optional task missing: {task_id}",
            )


def validate_dynamic_wave_policy() -> None:
    """Check generated waves preserve role instances and pre-final reviewers."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    for task_id in task_ids(catalog):
        task = task_by_id(catalog, task_id)
        roles = roles_for_task(config, catalog, task_id)
        active_budget, _ = workflow_spawn_budget(catalog, str(task["family"]))
        initial_wave = recommended_initial_subagent_wave(roles, active_budget)
        wave_slots = recommended_dynamic_expansion_wave_slots(roles, active_budget, initial_wave)
        flattened_slots = tuple(slot for wave in wave_slots for slot in wave)
        slot_keys = {(slot.role_id, slot.agent_type) for slot in flattened_slots}
        expected_slots = {
            (role.id, agent_type)
            for role in roles
            if role.id not in NON_SPAWN_WAVE_ROLE_IDS
            for agent_type in role.codex_agents
        }
        missing_slots = sorted(expected_slots - slot_keys)
        ensure(
            not missing_slots,
            f"task {task_id} dynamic waves collapsed role instances: {missing_slots}",
        )
        if any(role.id == "final_reviewer" for role in roles):
            final_wave_indexes = [
                index
                for index, wave in enumerate(wave_slots)
                if any(slot.role_id == "final_reviewer" for slot in wave)
            ]
            ensure(
                bool(final_wave_indexes),
                f"task {task_id} dynamic waves missing final_reviewer",
            )
            final_wave_index = min(final_wave_indexes)
            pre_final_role_ids = {
                slot.role_id
                for wave in wave_slots[:final_wave_index]
                for slot in wave
            }
            late_reviewers = sorted(
                role.id
                for role in roles
                if role.id in PRE_FINAL_REVIEW_ROLE_IDS and role.id not in pre_final_role_ids
            )
            ensure(
                not late_reviewers,
                f"task {task_id} review roles scheduled after final review: {late_reviewers}",
            )
def validate_public_skill_shims() -> None:
    """Check that public skill catalog entries have discoverable SKILL.md shims."""
    catalog_path = ROOT / "agents" / "skills" / "catalog.yaml"
    raw_data: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    data = require_mapping(raw_data, "skill catalog must parse as a mapping")
    families = require_list(data.get("skill_families", []), "skill_families must be a list")

    observed_skill_ids: set[str] = set()
    for entry in families:
        entry = require_mapping(entry, "skill_families entries must be mappings")
        skill_id = require_string(
            entry.get("id"), "skill_families id must be a string"
        )
        ensure(
            is_public_skill_id(skill_id),
            f"public skill catalog id must not start with {PRIVATE_SKILL_PREFIX}: {skill_id}",
        )
        ensure(skill_id not in observed_skill_ids, f"duplicate skill catalog id: {skill_id}")
        observed_skill_ids.add(skill_id)
        canonical_doc = ROOT / require_string(
            entry.get("canonical_doc"),
            f"{skill_id} canonical_doc must be a string",
        )
        shim = ROOT / require_string(entry.get("shim"), f"{skill_id} shim must be a string")
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
        validate_skill_routing_entry(skill_id, entry.get("routing"))
    validate_skill_related_entries(families, observed_skill_ids)
    observed_shim_ids = {
        path.parent.name
        for path in SKILL_SHIM_ROOT.glob("*/SKILL.md")
    }
    public_shim_ids = {skill_id for skill_id in observed_shim_ids if is_public_skill_id(skill_id)}
    private_catalog_ids = sorted(skill_id for skill_id in observed_skill_ids if is_private_skill_id(skill_id))
    extra_shims = sorted(public_shim_ids - observed_skill_ids)
    missing_shims = sorted(observed_skill_ids - observed_shim_ids)
    ensure(
        not private_catalog_ids,
        "private skill ids must stay out of public skill catalog: "
        + ", ".join(private_catalog_ids),
    )
    ensure(
        not extra_shims,
        "public skill shims missing catalog entries: " + ", ".join(extra_shims),
    )
    ensure(
        not missing_shims,
        "skill catalog entries missing public shims: " + ", ".join(missing_shims),
    )
    validate_public_skill_document_contract(data)
    validate_official_system_skill_delegation(data)


def validate_public_skill_document_contract(
    data: Mapping[str, object], root: Path | None = None
) -> None:
    """Check that agents/skills contains only catalog-backed public skills."""
    if root is None:
        root = ROOT
    public_doc_root = root / "agents" / "skills"
    internal_routine_root = root / "agents" / "internal-routines"
    ensure(public_doc_root.is_dir(), "public skill doc root missing: agents/skills")
    ensure(
        internal_routine_root.is_dir(),
        "internal routine root missing: agents/internal-routines",
    )
    ensure(
        (internal_routine_root / "README.md").is_file(),
        "internal routine README missing: agents/internal-routines/README.md",
    )
    families = require_list(data.get("skill_families", []), "skill_families must be a list")
    catalog_docs: set[str] = set()
    for entry in families:
        entry = require_mapping(entry, "skill_families entries must be mappings")
        canonical_doc = require_string(
            entry.get("canonical_doc"),
            "skill_families canonical_doc must be non-empty",
        ).strip()
        skill_id = require_string(
            entry.get("id"), "skill_families id must be a string"
        ).strip()
        ensure(
            is_public_skill_id(skill_id),
            f"public skill catalog id must not start with {PRIVATE_SKILL_PREFIX}: {skill_id}",
        )
        ensure(bool(canonical_doc), "skill_families canonical_doc must be non-empty")
        canonical_path = root / canonical_doc
        ensure(
            canonical_path.resolve().is_relative_to(public_doc_root.resolve()),
            f"{entry.get('id')} canonical doc must live under agents/skills: {canonical_doc}",
        )
        catalog_docs.add(canonical_path.relative_to(root).as_posix())
    public_docs = {
        path.relative_to(root).as_posix()
        for path in public_doc_root.rglob("*.md")
        if path.name != "README.md"
    }
    extra_public_docs = sorted(public_docs - catalog_docs)
    missing_public_docs = sorted(catalog_docs - public_docs)
    ensure(
        not extra_public_docs,
        "agents/skills contains non-catalog public docs: "
        + ", ".join(extra_public_docs),
    )
    ensure(
        not missing_public_docs,
        "skill catalog canonical docs missing from agents/skills: "
        + ", ".join(missing_public_docs),
    )
    validate_public_skill_readme_single_source(root)


def validate_public_skill_readme_single_source(root: Path) -> None:
    """Check that README does not duplicate the catalog-backed skill table."""
    readme = root / "agents" / "skills" / "README.md"
    ensure(readme.is_file(), "public skill README missing: agents/skills/README.md")
    text = readme.read_text(encoding="utf-8")
    ensure(
        PUBLIC_SKILL_README_DUPLICATE_ROW.search(text) is None,
        "agents/skills/README.md must not duplicate public skill catalog rows; "
        "keep the skill list in agents/skills/catalog.yaml",
    )


def validate_official_system_skill_delegation(
    data: Mapping[str, object], root: Path | None = None
) -> None:
    """Check that host-provided system skills stay in the delegation lane."""
    if root is None:
        root = ROOT
    families = require_list(data.get("skill_families", []), "skill_families must be a list")
    catalog_skill_ids: set[str] = set()
    for entry in families:
        if not isinstance(entry, dict):
            continue
        entry = require_mapping(cast(object, entry), "skill_families entries must be mappings")
        catalog_skill_ids.add(
            require_string(entry.get("id"), "skill_families id must be a string").strip()
        )
    catalog_official_skills = sorted(set(OFFICIAL_SYSTEM_SKILLS) & catalog_skill_ids)
    ensure(
        not catalog_official_skills,
        "move official system skills to the host-provided lane outside AgentCanon public catalog: "
        + ", ".join(catalog_official_skills),
    )

    for skill_id in OFFICIAL_SYSTEM_SKILLS:
        public_doc = root / "agents" / "skills" / f"{skill_id}.md"
        ensure(
            not public_doc.exists(),
            f"move official system skill public doc to host-provided delegation: {public_doc.relative_to(root)}",
        )
        shim = root / ".agents" / "skills" / skill_id / "SKILL.md"
        ensure(
            not shim.exists(),
            f"move official system skill local shim to host-provided delegation: {shim.relative_to(root)}",
        )

    for relative_path in OFFICIAL_SYSTEM_SKILL_DELEGATION_DOCS:
        path = root / relative_path
        ensure(path.is_file(), f"official system skill delegation doc missing: {relative_path}")
        text = path.read_text(encoding="utf-8")
        ensure(
            "Official System Skill Delegation" in text,
            f"{relative_path} missing official system skill delegation section",
        )
        for skill_id in OFFICIAL_SYSTEM_SKILLS:
            ensure(
                f"${skill_id}" in text,
                f"{relative_path} missing official system skill route: ${skill_id}",
            )


def validate_skill_routing_entry(skill_id: str, routing: object) -> None:
    """Check one optional catalog-backed prompt routing block."""
    if routing is None:
        return
    routing = require_mapping(routing, f"{skill_id} routing must be a mapping")
    stage_policy = routing.get("stage_policy", "deferred")
    ensure(
        isinstance(stage_policy, str) and stage_policy in SKILL_ROUTING_STAGE_POLICIES,
        f"{skill_id} routing.stage_policy must be one of {sorted(SKILL_ROUTING_STAGE_POLICIES)}",
    )
    reason = routing.get("reason")
    ensure(
        isinstance(reason, str) and bool(reason.strip()),
        f"{skill_id} routing.reason must be a non-empty string",
    )
    triggers = require_list(
        routing.get("triggers", []), f"{skill_id} routing.triggers must be a list"
    )
    for group_index, group in enumerate(triggers):
        group = require_string_list(
            group,
            f"{skill_id} routing.triggers[{group_index}] must be a non-empty list",
        )
        ensure(
            bool(group),
            f"{skill_id} routing.triggers[{group_index}] must be a non-empty list",
        )
        for term_index, term in enumerate(group):
            ensure(
                bool(term.strip()),
                f"{skill_id} routing.triggers[{group_index}][{term_index}] must be a non-empty string",
            )


def validate_skill_related_entries(families: object, observed_skill_ids: set[str]) -> None:
    """Check related-skill metadata points to public catalog entries."""
    families = require_list(families, "skill_families must be a list")
    for entry in families:
        entry = require_mapping(entry, "skill_families entries must be mappings")
        skill_id = require_string(
            entry.get("id"), "skill_families id must be a string"
        ).strip()
        related_skills = require_string_list(
            entry.get("related_skills", []),
            f"{skill_id} related_skills must be a list",
        )
        for related_index, related_skill in enumerate(related_skills):
            ensure(
                bool(related_skill.strip()),
                f"{skill_id} related_skills[{related_index}] must be a non-empty string",
            )
            ensure(
                related_skill != skill_id,
                f"{skill_id} related_skills[{related_index}] must not self-reference",
            )
            ensure(
                is_public_skill_id(related_skill),
                f"{skill_id} related_skills[{related_index}] must be public: {related_skill}",
            )
            ensure(
                related_skill in observed_skill_ids,
                f"{skill_id} related_skills[{related_index}] unknown skill: {related_skill}",
            )


def validate_subagent_protocol_docs() -> None:
    """Check subagent routing docs keep machine-enforceable boundaries."""
    for path in SUBAGENT_PROTOCOL_DOCS:
        text = path.read_text(encoding="utf-8")
        if path.name == "TASK_WORKFLOWS.md":
            for marker in (
                "Workflow Contract Owners",
                "agents/task_catalog.yaml",
                "agents/agents_config.json",
                ".codex/agents/*.toml",
                "task_start.py",
                "bootstrap_agent_run.py",
                "workflow_monitor.py",
                "python3 tools/agent_tools/route.py --prompt",
                "Implementation Flow Graph",
            ):
                ensure(marker in text, f"{path} missing owner-map marker: {marker}")
        else:
            ensure(
                "Intake Responsibility Wave" in text,
                f"{path} missing intake responsibility contract",
            )
            ensure("Wave Plan Contract" in text, f"{path} missing wave plan contract")
            ensure("Agent Wave Ledger" in text, f"{path} missing Agent Wave Ledger contract")
            for role_id in INITIAL_INTAKE_MARKERS:
                ensure(role_id in text, f"{path} missing intake responsibility role {role_id}")
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
    return select_roles(
        config=config,
        enabled_specialists=list(enabled),
        full_team=False,
        catalog=catalog,
        workflow_family_id=str(task["family"]),
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
    raw_manifest: object = yaml.safe_load(manifest_text)
    manifest = require_mapping(
        raw_manifest, f"task {task_id} manifest must be a mapping"
    )
    run = require_mapping(
        manifest.get("run"), f"task {task_id} manifest missing run mapping"
    )
    spawn_budget = require_mapping(
        run.get("spawn_budget"),
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
        f"task {task_id} manifest must state intake responsibility wave is not a total cap",
    )
    ensure(
        "workflow_families[].spawn_budget" in str(spawn_budget.get("source", "")),
        f"task {task_id} manifest run.spawn_budget source missing catalog reference",
    )
    ensure(
        spawn_budget.get("max_write_subagents_scope") == "write-capable subagents only",
        f"task {task_id} manifest run.spawn_budget max_write scope unclear",
    )
    delegated_spawn_policy = require_mapping(
        run.get("delegated_spawn_policy"),
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
    wave_record_command = str(delegated_spawn_policy.get("wave_record_command", ""))
    ensure(
        "workflow_monitor.py" in wave_record_command
        and "--subagent-wave" in wave_record_command,
        f"task {task_id} manifest missing subagent wave record command",
    )
    required_fields = require_string_list(
        delegated_spawn_policy.get("handoff_required_fields"),
        f"task {task_id} manifest delegated spawn handoff fields incomplete",
    )
    expected_handoff_fields = {
        "owner",
        "child_role",
        "child_instance_id",
        "input_packet",
        "allowed_paths",
        "do_not_read",
        "expected_output",
        "write_scope",
        "validation_route",
        "review_gate",
        "remaining_spawn_budget",
    }
    ensure(
        expected_handoff_fields.issubset(set(required_fields)),
        f"task {task_id} manifest delegated spawn handoff fields incomplete",
    )
    same_role_policy = require_mapping(
        delegated_spawn_policy.get("same_role_instances"),
        f"task {task_id} manifest missing delegated same-role instance policy",
    )
    ensure(
        same_role_policy.get("status") == "allowed_with_distinct_packets",
        f"task {task_id} manifest same-role instance policy status mismatch",
    )
    ensure(
        same_role_policy.get("identity_key") == "role_type+instance_id",
        f"task {task_id} manifest same-role identity key mismatch",
    )
    same_role_required_fields = require_string_list(
        same_role_policy.get("required_fields"),
        f"task {task_id} manifest same-role required fields incomplete",
    )
    expected_same_role_fields = {
        "role_type",
        "instance_id",
        "input_packet",
        "allowed_paths",
        "do_not_read",
        "expected_output",
        "write_scope",
        "validation_route",
        "review_gate",
    }
    ensure(
        expected_same_role_fields.issubset(set(same_role_required_fields)),
        f"task {task_id} manifest same-role required fields incomplete",
    )
    spawn_wave_recommendation = require_mapping(
        run.get("spawn_wave_recommendation"),
        f"task {task_id} manifest missing run.spawn_wave_recommendation",
    )
    initial_wave = require_string_list(
        spawn_wave_recommendation.get("initial_wave_agent_types"),
        f"task {task_id} manifest must recommend at least one initial agent type",
    )
    dynamic_expansion_waves = spawn_wave_recommendation.get("dynamic_expansion_waves")
    manifest_roles = manifest.get("roles")
    total_agent_candidates: list[str] = []
    if isinstance(manifest_roles, list):
        for role in require_list(
            cast(object, manifest_roles), f"task {task_id} manifest roles must be a list"
        ):
            if not isinstance(role, dict):
                continue
            role = require_mapping(cast(object, role), f"task {task_id} role must be a mapping")
            codex_agents = role.get("codex_agents")
            if not isinstance(codex_agents, list):
                continue
            for agent_type in require_string_list(
                cast(object, codex_agents),
                f"task {task_id} role codex_agents must be a list",
            ):
                if agent_type not in total_agent_candidates:
                    total_agent_candidates.append(agent_type)
    ensure(
        len(initial_wave) >= 1,
        f"task {task_id} manifest must recommend at least one initial agent type",
    )
    if (
        expected_active > MIN_DYNAMIC_SPAWN_BUDGET
        and len(total_agent_candidates) > INTAKE_AGENT_COUNT
    ):
        dynamic_agent_candidates: list[str] = []
        if isinstance(dynamic_expansion_waves, list):
            for wave in require_list(
                cast(object, dynamic_expansion_waves),
                f"task {task_id} manifest dynamic_expansion_waves must be a list",
            ):
                if not isinstance(wave, dict):
                    continue
                wave = require_mapping(
                    cast(object, wave),
                    f"task {task_id} dynamic expansion wave must be a mapping",
                )
                agent_types = wave.get("agent_types")
                if not isinstance(agent_types, list):
                    continue
                for agent_type in require_string_list(
                    cast(object, agent_types),
                    f"task {task_id} dynamic expansion agent_types must be a list",
                ):
                    if agent_type not in dynamic_agent_candidates:
                        dynamic_agent_candidates.append(agent_type)
        ensure(
            initial_wave == ["requirements_organizer", "explorer", "execution_planner"],
            f"task {task_id} manifest must use the stage-ready Intake Responsibility Wave",
        )
        ensure(
            len(dynamic_agent_candidates) >= 1,
            f"task {task_id} manifest must expose dynamic expansion waves",
        )
        ensure(
            len(set(initial_wave + dynamic_agent_candidates)) > INTAKE_AGENT_COUNT,
            f"task {task_id} manifest must not collapse multi-agent work to intake responsibility",
        )
    ensure(
        len(initial_wave) <= expected_active,
        f"task {task_id} manifest initial wave exceeds active spawn budget",
    )
    write_scope_policy = require_mapping(
        run.get("write_scope_policy"),
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
    lifecycle_policy = require_mapping(
        run.get("subagent_lifecycle_policy"),
        f"task {task_id} manifest missing run.subagent_lifecycle_policy object",
    )
    ensure(
        lifecycle_policy.get("mid_task_user_input_policy")
        == "parent_checkpoint_then_route_delta",
        f"task {task_id} manifest missing mid-task user input checkpoint policy",
    )
    ensure(
        lifecycle_policy.get("same_task_delta_reuse") == "allowed_with_updated_packet",
        f"task {task_id} manifest missing same-task delta reuse policy",
    )
    ensure(
        lifecycle_policy.get("scope_change_reuse") == "forbidden_spawn_fresh_wave",
        f"task {task_id} manifest missing scope-change fresh wave policy",
    )
    ensure(
        "prompt_contract:" in manifest_text,
        f"task {task_id} manifest missing role prompt_contract",
    )
    ensure_manifest_abstract_design_prompt_contracts(manifest, task_id)


def ensure_manifest_abstract_design_prompt_contracts(
    manifest: dict[str, object],
    task_id: str,
) -> None:
    """Ensure generated role prompts preserve ADF trace contracts."""
    roles = require_list(
        manifest.get("roles"), f"task {task_id} manifest missing roles list"
    )

    def prompt_fields(role_id: str) -> set[str] | None:
        common_fields: set[str] = set()
        run = manifest.get("run")
        if isinstance(run, dict):
            run = require_mapping(cast(object, run), f"task {task_id} run must be a mapping")
            context_policy = run.get("handoff_context_policy")
            if isinstance(context_policy, dict):
                context_policy = require_mapping(
                    cast(object, context_policy),
                    f"task {task_id} handoff_context_policy must be a mapping",
                )
                raw_common_fields = context_policy.get("common_prompt_must_include")
                if isinstance(raw_common_fields, list):
                    common_fields = set(
                        require_string_list(
                            cast(object, raw_common_fields),
                            f"task {task_id} common_prompt_must_include must be a list",
                        )
                    )
        for role in roles:
            if not isinstance(role, dict):
                continue
            role = require_mapping(cast(object, role), f"task {task_id} role must be a mapping")
            if role.get("id") != role_id:
                continue
            prompt_contract = require_mapping(
                role.get("prompt_contract"),
                f"task {task_id} role {role_id} missing prompt_contract",
            )
            raw_fields = prompt_contract.get("role_prompt_must_include")
            raw_fields = require_string_list(
                raw_fields,
                f"task {task_id} role {role_id} missing role_prompt_must_include",
            )
            return common_fields | set(raw_fields)
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
    validate_dynamic_wave_policy()
    validate_public_skill_shims()
    validate_subagent_protocol_docs()
    validate_vendor_skill_adapters()
    validate_bundle_outputs()
    print("AGENT_RUNTIME_ALIGNMENT=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
