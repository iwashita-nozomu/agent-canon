#!/usr/bin/env python3
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
    create_run_bundle,
    default_specialists_for_task,
    load_task_catalog,
    load_team_config,
    required_output_templates_missing,
    resolve_role,
    task_ids,
)


CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SKILL_SHIM_ROOT = ROOT / ".agents" / "skills"
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
CODING_ROLE_IDS = {
    "explorer",
    "test_designer",
    "worker",
    "python_reviewer",
    "cpp_reviewer",
}
SPARK_CODING_ROLE_IDS = {
    "spark_worker",
}


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


def validate_codex_agent_settings() -> None:
    """Check that Codex agent settings use the expected model split."""
    configs = parse_codex_agents()
    required_role_ids = WRITING_AND_REVIEW_ROLE_IDS | CODING_ROLE_IDS | SPARK_CODING_ROLE_IDS
    missing = sorted(required_role_ids - set(configs))
    ensure(not missing, f"missing Codex agent definitions: {', '.join(missing)}")

    for role_id in sorted(WRITING_AND_REVIEW_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == "high",
            f"{role_id} model_reasoning_effort must be high",
        )
        ensure(config.get("model") == "gpt-5.4", f"{role_id} model must be gpt-5.4")

    for role_id in sorted(CODING_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == "high",
            f"{role_id} model_reasoning_effort must be high",
        )
        ensure(config.get("model") == "gpt-5.3-codex", f"{role_id} model must be gpt-5.3-codex")

    for role_id in sorted(SPARK_CODING_ROLE_IDS):
        config = configs[role_id]
        ensure(config.get("approval_policy") == "never", f"{role_id} approval_policy must be never")
        ensure(
            config.get("model_reasoning_effort") == "high",
            f"{role_id} model_reasoning_effort must be high",
        )
        ensure(
            config.get("model") == "gpt-5.3-codex-spark",
            f"{role_id} model must be gpt-5.3-codex-spark",
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


def validate_task_catalog_references() -> None:
    """Check task catalog roles and task-family relationships."""
    config = load_team_config()
    catalog = load_task_catalog(config)
    role_ids = {role.id for role in config.always_on_roles + config.specialist_roles}
    family_ids = {family["id"] for family in catalog.workflow_families}

    for family in catalog.workflow_families:
        roles = family.get("roles", {})
        ensure(isinstance(roles, dict), f"family {family['id']} roles must be a mapping")
        for bucket in ("always_on", "specialists"):
            members = roles.get(bucket, [])
            ensure(isinstance(members, list), f"family {family['id']} {bucket} must be a list")
            for role_id in members:
                ensure(role_id in role_ids, f"family {family['id']} references unknown role {role_id}")

    for task_id in task_ids(catalog):
        task = next(task for task in catalog.tasks if task["id"] == task_id)
        ensure(task["family"] in family_ids, f"task {task_id} references unknown family {task['family']}")
        _ = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=task_id,
            include_default_review_packs=True,
        )

    for pack in catalog.review_packs:
        for role_id in pack.get("specialists", []):
            ensure(role_id in role_ids, f"review pack {pack['id']} references unknown role {role_id}")
        for task_id in pack.get("default_for_tasks", []):
            ensure(task_id in task_ids(catalog), f"review pack {pack['id']} default task missing: {task_id}")
        for task_id in pack.get("optional_for_tasks", []):
            ensure(task_id in task_ids(catalog), f"review pack {pack['id']} optional task missing: {task_id}")


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
            enabled = list(
                default_specialists_for_task(
                    config=config,
                    catalog=catalog,
                    task_id=task_id,
                    include_default_review_packs=True,
                )
            )
            roles = tuple(config.always_on_roles) + tuple(resolve_role(config, role_id) for role_id in enabled)
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
            )
            missing_outputs = [
                output
                for role in roles
                for output in role.required_outputs
                if not (report_dir / output).is_file()
            ]
            ensure(
                not missing_outputs,
                f"task {task_id} did not generate required outputs: {', '.join(sorted(set(missing_outputs)))}",
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
    validate_codex_agent_settings()
    validate_team_config_references()
    validate_task_catalog_references()
    validate_public_skill_shims()
    validate_bundle_outputs()
    print("AGENT_RUNTIME_ALIGNMENT=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
