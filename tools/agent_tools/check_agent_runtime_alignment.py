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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from agent_team import (
    ROOT,
    Role,
    RunBundleSpec,
    TaskCatalog,
    TeamConfig,
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
    workflow_spawn_budget,
)
from vendor_skill_adapters import VendorSkillValidator

PROJECT_CONFIG_PATH = ROOT / ".codex" / "config.toml"
HOOKS_JSON_PATH = ROOT / ".codex" / "hooks.json"
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SKILL_SHIM_ROOT = ROOT / ".agents" / "skills"
FRONTIER_MODEL = "gpt-5.5"
SPARK_CODING_MODEL = "gpt-5.3-codex-spark"
SPARK_REASONING_EFFORT = "low"
FRONTMATTER_OPEN_MARKER = "---\n"
WRITING_AND_REVIEW_ROLE_IDS = {
    "requirements_organizer",
    "manager_reviewer",
    "execution_planner",
    "detailed_designer",
    "long_form_writer",
    "plan_reviewer",
    "detailed_design_reviewer",
    "document_flow_reviewer",
    "citation_evidence_reviewer",
    "notation_definition_reviewer",
    "logic_gap_reviewer",
    "oop_readability_reviewer",
    "reviewer",
    "project_reviewer",
    "report_reviewer",
    "docs_workflow_steward",
    "reproducibility_reviewer",
    "scientific_computing_reviewer",
    "benchmark_reviewer",
    "artifact_reviewer",
    "fair_data_reviewer",
    "ml_science_reviewer",
    "literature_researcher",
}
SPARK_READ_ROLE_IDS = {
    "explorer",
    "test_designer",
    "python_reviewer",
    "cpp_reviewer",
}
FRONTIER_IMPLEMENTATION_ROLE_IDS = {
    "worker",
}
SPARK_CODING_ROLE_IDS = {
    "spark_worker",
}
MAX_VENDOR_SKILL_FINDINGS_IN_MESSAGE = 8


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
        parsed[path.stem] = tomllib.loads(path.read_text(encoding="utf-8"))
    return parsed


def validate_project_config() -> None:
    """Check that the shared project config exposes the review route."""
    config = tomllib.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))
    ensure(config.get("review_model") == FRONTIER_MODEL, f"review_model must be {FRONTIER_MODEL}")
    features = config.get("features", {})
    ensure(isinstance(features, dict), "features must be a mapping")
    ensure(features.get("hooks") is True, "features.hooks must be true")
    ensure(features.get("goals") is True, "features.goals must be true")
    ensure("codex_hooks" not in features, "deprecated features.codex_hooks must be absent")
    ensure("profiles" not in config, "project-local profiles must stay out of shared config")


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
    ensure(
        (ROOT / ".codex" / "hooks" / "mcp_session_context.sh").is_file(),
        "mcp_session_context.sh must exist as an optional context helper",
    )
    for hook_script in (
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
    """Check that Codex agent settings use the expected model split."""
    configs = parse_codex_agents()
    required_role_ids = (
        WRITING_AND_REVIEW_ROLE_IDS
        | SPARK_READ_ROLE_IDS
        | FRONTIER_IMPLEMENTATION_ROLE_IDS
        | SPARK_CODING_ROLE_IDS
    )
    missing = sorted(required_role_ids - set(configs))
    ensure(not missing, f"missing Codex agent definitions: {', '.join(missing)}")

    for role_id in sorted(WRITING_AND_REVIEW_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == "high",
            f"{role_id} model_reasoning_effort must be high",
        )
        ensure(config.get("model") == FRONTIER_MODEL, f"{role_id} model must be {FRONTIER_MODEL}")

    for role_id in sorted(SPARK_READ_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == SPARK_REASONING_EFFORT,
            f"{role_id} model_reasoning_effort must be {SPARK_REASONING_EFFORT}",
        )
        ensure(
            config.get("model") == SPARK_CODING_MODEL,
            f"{role_id} model must be {SPARK_CODING_MODEL}",
        )

    for role_id in sorted(FRONTIER_IMPLEMENTATION_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == "high",
            f"{role_id} model_reasoning_effort must be high",
        )
        ensure(config.get("model") == FRONTIER_MODEL, f"{role_id} model must be {FRONTIER_MODEL}")

    for role_id in sorted(SPARK_CODING_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == SPARK_REASONING_EFFORT,
            f"{role_id} model_reasoning_effort must be {SPARK_REASONING_EFFORT}",
        )
        ensure(
            config.get("model") == SPARK_CODING_MODEL,
            f"{role_id} model must be {SPARK_CODING_MODEL}",
        )


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
            max_write_budget == 1,
            f"family {family['id']} max_write_subagents must remain 1",
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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
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
    return tuple(config.always_on_roles) + tuple(
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
    validate_vendor_skill_adapters()
    validate_bundle_outputs()
    print("AGENT_RUNTIME_ALIGNMENT=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
