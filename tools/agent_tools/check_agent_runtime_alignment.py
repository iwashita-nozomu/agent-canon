#!/usr/bin/env python3
# @dependency-start
# responsibility Checks agent runtime alignment agent workflow state.
# upstream design ../README.md shared automation index
# @dependency-end

"""Validate that agent runtime surfaces, task catalog, and bundle outputs align."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from agent_team import (
    ROOT,
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

PROJECT_CONFIG_PATH = ROOT / ".codex" / "config.toml"
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SKILL_SHIM_ROOT = ROOT / ".agents" / "skills"


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


def load_project_config_toml() -> dict[str, object]:
    """Load the shared Codex project config."""
    return tomllib.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))


def iter_model_policy_buckets(config: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    """Return model policy buckets from `.codex/config.toml`."""
    agents = config.get("agents", {})
    ensure(isinstance(agents, dict), "agents config must be a mapping")
    model_policy = agents.get("model_policy", {})
    ensure(isinstance(model_policy, dict), "agents.model_policy must be a mapping")
    ensure(model_policy, "agents.model_policy must not be empty")
    buckets: list[tuple[str, dict[str, object]]] = []
    for bucket_id, raw_bucket in sorted(model_policy.items()):
        ensure(isinstance(raw_bucket, dict), f"model policy {bucket_id} must be a mapping")
        model = raw_bucket.get("model")
        reasoning_effort = raw_bucket.get("model_reasoning_effort")
        roles = raw_bucket.get("roles")
        ensure(isinstance(model, str) and model, f"model policy {bucket_id} missing model")
        ensure(
            isinstance(reasoning_effort, str) and reasoning_effort,
            f"model policy {bucket_id} missing model_reasoning_effort",
        )
        ensure(
            isinstance(roles, list) and all(isinstance(role, str) and role for role in roles),
            f"model policy {bucket_id} roles must be a non-empty string list",
        )
        ensure(len(set(roles)) == len(roles), f"model policy {bucket_id} has duplicate roles")
        buckets.append((str(bucket_id), raw_bucket))
    return buckets


def validate_agent_model(
    configs: dict[str, dict[str, object]],
    role_id: str,
    *,
    model: str,
    reasoning_effort: str,
) -> None:
    """Check one Codex agent model bucket."""
    config = configs[role_id]
    ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
    ensure(
        config.get("model_reasoning_effort") == reasoning_effort,
        f"{role_id} model_reasoning_effort must be {reasoning_effort}",
    )
    ensure(config.get("model") == model, f"{role_id} model must be {model}")


def validate_project_config() -> None:
    """Check that the shared project config exposes the review route."""
    config = load_project_config_toml()
    profiles = config.get("profiles", {})
    ensure(isinstance(profiles, dict), "profiles must be a mapping")
    review_profile = profiles.get("review", {})
    ensure(isinstance(review_profile, dict), "review profile must be a mapping")
    review_model = review_profile.get("model")
    ensure(config.get("review_model") == review_model, "review_model must match profiles.review.model")
    ensure(
        isinstance(review_model, str) and review_model,
        "review profile model must be a non-empty string",
    )
    ensure(
        isinstance(review_profile.get("model_reasoning_effort"), str)
        and review_profile.get("model_reasoning_effort"),
        "review profile model_reasoning_effort must be a non-empty string",
    )
    ensure(
        review_profile.get("sandbox_mode") == "read-only",
        "review profile sandbox_mode must be read-only",
    )
    ensure(
        review_profile.get("approval_policy") == "never",
        "review profile approval_policy must be never",
    )
    _ = iter_model_policy_buckets(config)


def validate_codex_agent_settings() -> None:
    """Check that Codex agent settings use the expected model split."""
    project_config = load_project_config_toml()
    model_policy = iter_model_policy_buckets(project_config)
    configs = parse_codex_agents()
    required_role_ids: set[str] = set()
    owner_by_role: dict[str, str] = {}
    for bucket_id, bucket in model_policy:
        for role_id in bucket["roles"]:
            if str(role_id) in owner_by_role:
                raise RuntimeError(
                    f"role {role_id} appears in multiple model policy buckets: "
                    f"{owner_by_role[str(role_id)]}, {bucket_id}"
                )
            owner_by_role[str(role_id)] = bucket_id
            required_role_ids.add(str(role_id))
    missing = sorted(required_role_ids - set(configs))
    ensure(not missing, f"missing Codex agent definitions: {', '.join(missing)}")

    unassigned_agents = sorted(set(configs) - required_role_ids)
    ensure(
        not unassigned_agents,
        "Codex agents missing from agents.model_policy: " + ", ".join(unassigned_agents),
    )

    for bucket_id, bucket in model_policy:
        for role_id in sorted(str(role) for role in bucket["roles"]):
            try:
                validate_agent_model(
                    configs,
                    role_id,
                    model=str(bucket["model"]),
                    reasoning_effort=str(bucket["model_reasoning_effort"]),
                )
            except RuntimeError as exc:
                raise RuntimeError(f"model policy {bucket_id}: {exc}") from exc


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
        ensure(text.startswith("---\n"), f"{skill_id} shim must start with YAML frontmatter")
        ensure("\n---\n" in text[4:], f"{skill_id} shim YAML frontmatter must close")
        ensure(f"name: {skill_id}" in text, f"{skill_id} shim frontmatter name mismatch")


def validate_bundle_outputs() -> None:
    """Create temporary bundles for every catalog task and full-team run."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    created_at_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )

    with tempfile.TemporaryDirectory(prefix="agent-runtime-alignment-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        workspace_root = tmp_root / "workspace"
        report_root = tmp_root / "reports"
        workspace_root.mkdir(parents=True, exist_ok=True)
        report_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "python").mkdir()
        (workspace_root / "documents").mkdir()
        (workspace_root / "reports" / "runtime").mkdir(parents=True)
        (workspace_root / "WORKTREE_SCOPE.md").write_text(
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

        for task_id in task_ids(catalog):
            task = next(task for task in catalog.tasks if task["id"] == task_id)
            enabled = list(
                default_specialists_for_task(
                    config=config,
                    catalog=catalog,
                    task_id=task_id,
                    include_default_review_packs=True,
                )
            )
            roles = tuple(config.always_on_roles) + tuple(
                resolve_role(config, role_id) for role_id in enabled
            )
            report_dir = report_root / task_id
            create_run_bundle(
                config=config,
                report_dir=report_dir,
                run_id=task_id,
                task=f"alignment smoke for {task_id}",
                owner="codex",
                created_at_iso=created_at_iso,
                roles=roles,
                workspace_root=workspace_root,
                workflow_family_id=str(task["family"]),
            )
            missing_outputs = [
                output
                for role in roles
                for output in role.required_outputs
                if not (report_dir / output).is_file()
            ]
            ensure(
                not missing_outputs,
                "task "
                f"{task_id} did not generate required outputs: "
                f"{', '.join(sorted(set(missing_outputs)))}",
            )
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

        full_team_roles = config.always_on_roles + config.specialist_roles
        full_team_dir = report_root / "full-team"
        create_run_bundle(
            config=config,
            report_dir=full_team_dir,
            run_id="full-team",
            task="alignment smoke full team",
            owner="codex",
            created_at_iso=created_at_iso,
            roles=full_team_roles,
            workspace_root=workspace_root,
            workflow_family_id="comprehensive_development",
        )
        missing_outputs = [
            output
            for role in full_team_roles
            for output in role.required_outputs
            if not (full_team_dir / output).is_file()
        ]
        ensure(
            not missing_outputs,
            "full-team bundle did not generate required outputs: "
            + ", ".join(sorted(set(missing_outputs))),
        )


def main() -> int:
    """Run all runtime-alignment checks."""
    validate_project_config()
    validate_codex_agent_settings()
    validate_team_config_references()
    validate_task_catalog_references()
    validate_public_skill_shims()
    validate_bundle_outputs()
    print("AGENT_RUNTIME_ALIGNMENT=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
