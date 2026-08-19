# @dependency-start
# contract tool
# responsibility Checks GitHub workflow and PR template conventions.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md PR evidence rules
# upstream design ../../README.md AgentCanon surface index
# upstream design ../../.github/AGENTS.md GitHub agent entrypoint
# upstream design ../../issues/README.md durable operational issue conventions
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream design ../../templates/documents/github/pull-request/agent_canon.md canonical template-side AgentCanon PR checklist
# upstream design ../../.github/workflows/agent-improvement-guide.yml PR and push improvement guide workflow
# upstream design ../../.github/workflows/agent-runtime-dashboard.yml standalone AgentCanon runtime dashboard workflow
# upstream design ../../.github/workflows/issue-mirror.yml standalone local/GitHub issue mirror workflow
# upstream design ../../.github/workflows/agent-canon-static-gates.yml PR candidate gate workflow
# upstream design ../../documents/agent-canon/agent-canon-github-remote.md checkout auth policy
# upstream design ../../documents/contracts/template-github-remote.md credential boundary
# upstream implementation ./checkout_agent_canon_submodule.sh public/private submodule helper
# upstream implementation ../agent_tools/check_skill_frontmatter.py validates runtime skill frontmatter in static gates
# downstream implementation ../../tests/tools/test_check_github_workflows.py tests
# @dependency-end

"""Check GitHub workflow and PR template conventions."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

HELPER_PATHS = (
    ".github/scripts/checkout_agent_canon_submodule.sh",
    "tools/ci/checkout_agent_canon_submodule.sh",
)
AGENT_CANON_WORKFLOW_SURFACE_MARKERS = (
    "vendor/agent-canon",
)
LITERAL_ENV_REFERENCE_PATTERN = re.compile(
    r"\$\{\{\s*env\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}"
    r"|\$\{([A-Za-z_][A-Za-z0-9_]*)\}"
    r"|\$([A-Za-z_][A-Za-z0-9_]*)"
)
SHELL_LINE_CONTINUATION_PATTERN = re.compile(r"\\\r?\n")
AGENT_CANON_INDEPENDENT_WORKFLOWS: set[str] = {
    "agent-runtime-dashboard.yml",
    "issue-mirror.yml",
}
AGENT_CANON_CREDENTIALS = (
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
)
ISSUE_MIRROR_CHECK_JOB = "issue-mirror-check"
ISSUE_MIRROR_CHECKOUT_OUTCOME = "steps.checkout.outcome"
ISSUE_MIRROR_CHECKOUT_FAILURE_GUARD = "failure() && "
AGENT_CANON_PR_READ_CREDENTIAL = "AGENT_CANON_PR_READ_TOKEN"
GITHUB_TOKEN_EXPRESSION = "${{ github.token }}"
WORKFLOW_DISPATCH_INPUT_PATTERN = re.compile(
    r"\$\{\{\s*(?:inputs|github\.event\.inputs)"
    r"\s*(?:\.\s*[A-Za-z_][A-Za-z0-9_-]*|\[\s*['\"][^'\"]+['\"]\s*\])"
    r"\s*\}\}"
)
WORKFLOW_DISPATCH_INPUT_CHECK_WORKFLOW = "agent-coordination.yml"

# PR templates record only the evidence that changes the publication decision.
# The historical plan, issue-sweep, and fixed-checklist fields remain rejected
# by the semantic checker below instead of becoming another required checklist.
PR_TEMPLATE_REQUIRED_TEXT = (
    "## PR Essence",
    "Problem / user request:",
    "Canonical owner / responsibility unit:",
    "Behavior or contract delta:",
    "Evidence route:",
    "Explicit non-goals:",
    "canonical route",
    "changed surfaces:",
    "source_commit:",
    "template_pin:",
    "pr_head:",
    "identity relation (source_commit -> template_pin -> pr_head):",
    "changed-surface validation:",
    "mutation authority:",
    "risk:",
    "follow-up owner or issue:",
)
PR_TEMPLATE_FORBIDDEN_TEXT = (
    "Plan Mode Evidence",
    "Agent Orchestration Evidence",
    "paused until",
    "Existing durable findings were searched",
    "Issue Mirror artifact",
    "issue_sync.py --repo",
    "Copilot Configuration Impact",
    "Candidate Commit And Publication Identity",
    "GitHub Mirror / Submodule Evidence",
    "agentcanon_structure_followup=required",
    "template submodule SHA:",
)
SUBMODULE_CHECKOUT_SCRIPT_REQUIREMENTS = (
    "AGENT_CANON_SUBMODULE_AUTH=missing",
    "AGENT_CANON_SUBMODULE_AUTH=denied",
    "AGENT_CANON_SUBMODULE_AUTH=ssh_denied",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
    "unset AGENT_CANON_REPO_TOKEN AGENT_CANON_REPO_SSH_KEY",
    "Credentials are never written to GITHUB_ENV",
    "untrusted PR context",
    "exit 86",
)
SUBMODULE_CHECKOUT_WRAPPER_REQUIREMENTS = (
    ".github/scripts/checkout_agent_canon_submodule.sh",
    "exec bash",
)
ROOT_COORDINATION_WORKFLOW_REQUIREMENTS = (
    "Standalone AgentCanon coordination workflow",
    "selected roles",
    "team_manifest.yaml",
    "run.capacity_request.lineage.role_ids",
    "GITHUB_STEP_SUMMARY",
    "SCHEDULED_SPECIALISTS=",
    "executed_role=coordination",
    "finding=none at intake",
    "result=bundle_ready",
)
ROOT_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS = (
    "generate_agent_improvement_guide.py",
)
ROOT_IMPROVEMENT_GUIDE_WORKFLOW_ALLOWED_TAGS = (
    "Standalone AgentCanon improvement guidance workflow",
    "Template AgentCanon improvement guidance workflow",
)
STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS = (
    "workflow_dispatch:",
    "schedule:",
    "generate_agent_runtime_dashboard.py",
)
STANDALONE_ISSUE_MIRROR_WORKFLOW_REQUIREMENTS = (
    "push:",
    "- main",
    "workflow_dispatch:",
    "issue_sync.py",
    "--github-check",
    "--sync-github",
    "GITHUB_STEP_SUMMARY",
    "permissions:",
    "issues: write",
)
VENDOR_COORDINATION_WORKFLOW_REQUIREMENTS = (
    "agents/workflows/agent-canon-pr-workflow.md",
    "Standalone AgentCanon coordination workflow",
    "selected roles",
    "team_manifest.yaml",
    "run.capacity_request.lineage.role_ids",
    "GITHUB_STEP_SUMMARY",
    "SCHEDULED_SPECIALISTS=",
    "executed_role=coordination",
    "finding=none at intake",
    "result=bundle_ready",
)
VENDOR_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS = (
    "pull_request:",
    "paths:",
    "workflow_dispatch:",
    "Standalone AgentCanon improvement guidance workflow",
    "generate_agent_improvement_guide.py",
    "GITHUB_STEP_SUMMARY",
    "actions/upload-artifact@v4",
)
AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS = (
    "pull_request:",
    "workflow_dispatch:",
    "github.event.pull_request.head.sha || github.sha",
    "bash tools/ci/check_agent_canon_pr.sh",
)
PARENT_PROJECT_QUALITY_OWNER_ENV = "AGENT_CANON_PR_PROJECT_QUALITY_OWNER"
PARENT_PROJECT_QUALITY_OWNER = "parent_ci"
PARENT_PROJECT_QUALITY_COMMAND = "make ci"
AGENT_CANON_STATIC_GATE_DIRECT_COMMANDS = (
    "tool_catalog.py",
    "tool_drift.py",
    "responsibility_scope.py",
    "import_responsibility.py",
    "--baseline-ref",
    "issue_sync.py",
    "run_accumulated_agent_evals.py",
    "eval_accumulation_check.py",
    "check_agent_runtime_alignment.py",
    "check_skill_frontmatter.py",
    "smoke_test_research_perspective_pack.py",
    "check_convention_compliance.py",
    "cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check",
    "cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings",
    "cargo test --manifest-path rust/agent-canon/Cargo.toml",
    "run_repo_dependency_review.sh --fail-missing --cycle-report-only",
    "check_github_workflows.py",
    "container_config.py",
)


def is_template_or_derived_repo(root: Path) -> bool:
    """Return whether root is a template or derived repo with AgentCanon vendored."""
    return (root / "vendor" / "agent-canon").exists() and (
        root / ".gitmodules"
    ).is_file()


def agent_canon_root(root: Path) -> Path:
    """Return the AgentCanon source root for standalone or template mode checks."""
    if is_template_or_derived_repo(root):
        return root / "vendor" / "agent-canon"
    return root


@dataclass(frozen=True)
class Finding:
    """One workflow convention finding."""

    severity: str
    path: Path
    message: str

    def line(self, root: Path) -> str:
        """Return a stable machine-readable finding line."""
        return (
            f"GITHUB_WORKFLOW_FINDING severity={self.severity} "
            f"path={self.path.relative_to(root).as_posix()} message={self.message}"
        )


def read_text(path: Path) -> str:
    """Read text with repository-default encoding."""
    return path.read_text(encoding="utf-8")


def as_string_dict(value: object) -> dict[str, object] | None:
    """Return a string-keyed dictionary view when possible."""
    if not isinstance(value, Mapping):
        return None
    result: dict[str, object] = {}
    mapping = cast(Mapping[object, object], value)
    for key, item in mapping.items():
        if isinstance(key, str):
            result[key] = item
    return result


def load_workflow(path: Path) -> dict[str, object]:
    """Load one workflow YAML file."""
    data: object = yaml.safe_load(read_text(path))
    workflow = as_string_dict(data)
    if workflow is None:
        return {}
    return workflow


def is_false(value: object) -> bool:
    """Return whether a YAML value means false for GitHub action inputs."""
    return value is False or str(value).lower() == "false"


def workflow_paths(root: Path) -> list[Path]:
    """Return root and AgentCanon workflow files to check."""
    paths = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    vendor_workflows = root / "vendor" / "agent-canon" / ".github" / "workflows"
    if vendor_workflows.is_dir():
        paths.extend(sorted(vendor_workflows.glob("*.y*ml")))
    return paths


@dataclass(frozen=True)
class StepContext:
    """One workflow step with inherited job context."""

    index: int
    job_name: str
    job: dict[str, object]
    step: dict[str, object]


def job_items(workflow: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    """Return workflow jobs as string-keyed dictionaries."""
    items: list[tuple[str, dict[str, object]]] = []
    jobs = as_string_dict(workflow.get("jobs"))
    if jobs is None:
        return items
    for job_name, job_object in jobs.items():
        job = as_string_dict(job_object)
        if job is None:
            continue
        items.append((job_name, job))
    return items


def step_contexts(workflow: dict[str, object]) -> list[StepContext]:
    """Return every workflow step with job context."""
    contexts: list[StepContext] = []
    index = 0
    for job_name, job in job_items(workflow):
        job_steps = job.get("steps")
        if not isinstance(job_steps, list):
            continue
        for step_object in cast(list[object], job_steps):
            step = as_string_dict(step_object)
            if step is None:
                continue
            index += 1
            contexts.append(
                StepContext(index=index, job_name=job_name, job=job, step=step)
            )
    return contexts


def workflow_dispatch_input_interpolation_findings(
    path: Path,
    workflow: dict[str, object],
) -> list[Finding]:
    """Return findings for direct workflow-dispatch input use in shell blocks."""
    findings: list[Finding] = []
    for context in step_contexts(workflow):
        run = context.step.get("run")
        if isinstance(run, str) and WORKFLOW_DISPATCH_INPUT_PATTERN.search(run):
            findings.append(
                Finding(
                    "error",
                    path,
                    f"run_step_{context.index}_direct_workflow_dispatch_input_interpolation",
                )
            )
    return findings


def checkout_steps(workflow: dict[str, object]) -> list[StepContext]:
    """Return every actions/checkout step in one workflow."""
    steps: list[StepContext] = []
    for context in step_contexts(workflow):
        uses = context.step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/checkout@"):
            steps.append(context)
    return steps


def has_permissions(workflow: dict[str, object]) -> bool:
    """Return whether permissions are declared at workflow or every job level."""
    if "permissions" in workflow:
        return True
    jobs = job_items(workflow)
    return bool(jobs) and all("permissions" in job for _job_name, job in jobs)


def credential_env_names(source: dict[str, object]) -> set[str]:
    """Return AgentCanon credential names declared by one workflow object."""
    env = as_string_dict(source.get("env"))
    if env is None:
        return set()
    return {name for name in AGENT_CANON_CREDENTIALS if name in env}


def non_step_credential_env_names(workflow: dict[str, object]) -> set[str]:
    """Return AgentCanon credentials exposed beyond their helper step."""
    names = credential_env_names(workflow)
    for _job_name, job in job_items(workflow):
        names.update(credential_env_names(job))
    return names


def agent_canon_checkout_command_steps(
    workflow: dict[str, object],
) -> list[StepContext]:
    """Return steps that invoke the AgentCanon checkout helper."""
    steps: list[StepContext] = []
    for context in step_contexts(workflow):
        run_values = effective_step_execution_values(
            workflow,
            context,
            fields=("run",),
            include_env=False,
            include_working_directory=False,
        )
        if any(path in value for value in run_values for path in HELPER_PATHS):
            steps.append(context)
    return steps


def nested_string_values(value: object) -> list[str]:
    """Return string leaves from one workflow execution field."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for nested in cast(dict[object, object], value).values():
            values.extend(nested_string_values(nested))
        return values
    if isinstance(value, list):
        values = []
        for nested in cast(list[object], value):
            values.extend(nested_string_values(nested))
        return values
    return []


def literal_env_values(source: dict[str, object]) -> dict[str, str]:
    """Return literal environment values declared by one workflow scope."""
    env = as_string_dict(source.get("env"))
    if env is None:
        return {}
    return {name: value for name, value in env.items() if isinstance(value, str)}


def resolve_literal_env_references(value: str, env: dict[str, str]) -> str:
    """Resolve shell and GitHub env references whose values are literal."""

    def replace(match: re.Match[str]) -> str:
        name = next(group for group in match.groups() if group is not None)
        return env.get(name, match.group(0))

    resolved = value
    for _index in range(len(env) + 1):
        updated = LITERAL_ENV_REFERENCE_PATTERN.sub(replace, resolved)
        if updated == resolved:
            break
        resolved = updated
    return resolved


def effective_step_env(
    workflow: dict[str, object], context: StepContext
) -> dict[str, str]:
    """Return workflow, job, and step environment with child overrides."""
    env = literal_env_values(workflow)
    env.update(literal_env_values(context.job))
    env.update(literal_env_values(context.step))
    return {
        name: resolve_literal_env_references(value, env)
        for name, value in env.items()
    }


def default_run_working_directory(source: dict[str, object]) -> str | None:
    """Return one scope's defaults.run.working-directory value."""
    defaults = as_string_dict(source.get("defaults"))
    if defaults is None:
        return None
    run_defaults = as_string_dict(defaults.get("run"))
    if run_defaults is None:
        return None
    working_directory = run_defaults.get("working-directory")
    return working_directory if isinstance(working_directory, str) else None


def effective_step_working_directory(
    workflow: dict[str, object], context: StepContext
) -> str | None:
    """Return the step's explicit or inherited run working directory."""
    working_directory = default_run_working_directory(workflow)
    job_working_directory = default_run_working_directory(context.job)
    if job_working_directory is not None:
        working_directory = job_working_directory
    step_working_directory = context.step.get("working-directory")
    if isinstance(step_working_directory, str):
        working_directory = step_working_directory
    return working_directory


def effective_step_execution_values(
    workflow: dict[str, object],
    context: StepContext,
    *,
    fields: tuple[str, ...] = ("run", "uses", "with"),
    include_env: bool = True,
    include_working_directory: bool = True,
) -> list[str]:
    """Return normalized execution values after literal context resolution."""
    env = effective_step_env(workflow, context)
    values: list[str] = []
    for field in fields:
        values.extend(nested_string_values(context.step.get(field)))
    if include_working_directory:
        working_directory = effective_step_working_directory(workflow, context)
        if working_directory is not None:
            values.append(working_directory)
    if include_env:
        values.extend(env.values())
    return [
        SHELL_LINE_CONTINUATION_PATTERN.sub(
            "", resolve_literal_env_references(value, env)
        )
        for value in values
    ]


def agent_canon_surface_steps(workflow: dict[str, object]) -> list[StepContext]:
    """Return execution steps that consume an AgentCanon-owned path."""
    steps: list[StepContext] = []
    for context in step_contexts(workflow):
        execution_values = effective_step_execution_values(workflow, context)
        if any(
            marker in value
            for value in execution_values
            for marker in AGENT_CANON_WORKFLOW_SURFACE_MARKERS
        ):
            steps.append(context)
    return steps


def referenced_agent_canon_checkout_script_available(
    root: Path, workflow_text: str
) -> bool:
    """Return whether at least one helper path referenced by the workflow exists."""
    roots = (root, agent_canon_root(root))
    return any(
        path in workflow_text
        and any((candidate_root / path).is_file() for candidate_root in roots)
        for path in HELPER_PATHS
    )


def workflow_declared_findings(
    path: Path, workflow: dict[str, object]
) -> list[Finding]:
    """Return findings for workflow-level required declarations."""
    findings: list[Finding] = []
    if not has_permissions(workflow):
        findings.append(Finding("error", path, "missing_permissions"))
    if "concurrency" not in workflow:
        findings.append(Finding("warning", path, "missing_top_level_concurrency"))
    return findings


def agent_canon_checkout_policy_findings(
    root: Path,
    path: Path,
    workflow: dict[str, object],
    workflow_text: str,
) -> list[Finding]:
    """Return findings for AgentCanon checkout-helper policy."""
    findings: list[Finding] = []
    checkouts = checkout_steps(workflow)
    helpers = agent_canon_checkout_command_steps(workflow)
    helper_indexes = {context.index for context in helpers}
    checkout_indexes = {context.index for context in checkouts}
    consumers = [
        context
        for context in agent_canon_surface_steps(workflow)
        if context.index not in helper_indexes
        and context.index not in checkout_indexes
    ]
    agent_canon_independent = path.name in AGENT_CANON_INDEPENDENT_WORKFLOWS
    if not agent_canon_independent:
        if consumers and not helpers:
            findings.append(
                Finding("error", path, "missing_agent_canon_checkout_helper")
            )
        for helper in helpers:
            prior_checkouts = [
                checkout
                for checkout in checkouts
                if checkout.job_name == helper.job_name
                and checkout.index < helper.index
            ]
            if not prior_checkouts:
                findings.append(
                    Finding(
                        "error",
                        path,
                        "agent_canon_checkout_helper_missing_prior_repository_checkout:"
                        f"job={helper.job_name}",
                    )
                )
        for job_name in sorted({context.job_name for context in consumers}):
            first_consumer = min(
                context.index
                for context in consumers
                if context.job_name == job_name
            )
            prior_checkouts = [
                checkout
                for checkout in checkouts
                if checkout.job_name == job_name
                and checkout.index < first_consumer
            ]
            if not prior_checkouts:
                findings.append(
                    Finding(
                        "error",
                        path,
                        "agent_canon_consumer_missing_prior_repository_checkout:"
                        f"job={job_name}",
                    )
                )
            ordered_helpers = [
                helper
                for helper in helpers
                if helper.job_name == job_name
                and helper.index < first_consumer
                and any(
                    checkout.job_name == job_name
                    and checkout.index < helper.index
                    for checkout in checkouts
                )
            ]
            if not ordered_helpers:
                findings.append(
                    Finding(
                        "error",
                        path,
                        "agent_canon_consumer_missing_prior_checkout_helper:"
                        f"job={job_name}",
                    )
                )
    if agent_canon_independent:
        if helpers:
            findings.append(
                Finding("error", path, "agent_canon_checkout_helper_not_allowed")
            )
        if any(name in workflow_text for name in AGENT_CANON_CREDENTIALS):
            findings.append(
                Finding("error", path, "agent_canon_credentials_not_allowed")
            )
    if helpers and not referenced_agent_canon_checkout_script_available(
        root, workflow_text
    ):
        findings.append(
            Finding("error", path, "missing_referenced_agent_canon_checkout_helper")
        )
    non_step_credentials = non_step_credential_env_names(workflow)
    if helpers and non_step_credentials:
        findings.append(
            Finding(
                "error",
                path,
                "agent_canon_credentials_must_be_step_local:"
                + ",".join(sorted(non_step_credentials)),
            )
        )
    return findings


def checkout_step_findings(path: Path, workflow: dict[str, object]) -> list[Finding]:
    """Return findings for actions/checkout safety settings."""
    findings: list[Finding] = []
    checkouts = checkout_steps(workflow)
    for index, context in enumerate(checkouts, start=1):
        with_block = as_string_dict(context.step.get("with"))
        if with_block is None:
            findings.append(
                Finding("error", path, f"checkout_{index}_missing_with_block")
            )
            continue
        if not is_false(with_block.get("submodules")):
            findings.append(
                Finding("error", path, f"checkout_{index}_missing_submodules_false")
            )
        if not is_false(with_block.get("persist-credentials")):
            findings.append(
                Finding(
                    "error",
                    path,
                    f"checkout_{index}_missing_persist_credentials_false",
                )
            )
    return findings


def issue_mirror_checkout_policy_findings(
    path: Path,
    workflow: dict[str, object],
) -> list[Finding]:
    """Return findings for issue-mirror checkout failure truthfulness and fallback."""
    if path.name != "issue-mirror.yml":
        return []
    contexts = [
        context
        for context in step_contexts(workflow)
        if context.job_name == ISSUE_MIRROR_CHECK_JOB
    ]
    if not contexts:
        return []
    findings: list[Finding] = []
    findings.extend(issue_mirror_checkout_step_findings(path, contexts))
    findings.extend(issue_mirror_checker_step_findings(path, contexts))
    findings.extend(issue_mirror_fallback_step_findings(path, contexts))
    return findings


def issue_mirror_checkout_step_findings(
    path: Path,
    contexts: list[StepContext],
) -> list[Finding]:
    """Return issue-mirror checkout step-specific findings."""
    findings: list[Finding] = []
    for context in issue_mirror_checkout_steps(contexts):
        if context.step.get("continue-on-error"):
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_continue_on_error_not_allowed",
                )
            )
    return findings


def issue_mirror_checker_step_findings(
    path: Path,
    contexts: list[StepContext],
) -> list[Finding]:
    """Return issue-sync checker step-specific findings."""
    for context in issue_mirror_issue_sync_checker_steps(contexts):
        if context.step.get("if") != f"{ISSUE_MIRROR_CHECKOUT_OUTCOME} == 'success'":
            return [
                Finding(
                    "error",
                    path,
                    "issue_mirror_checker_step_must_require_checkout_success",
                )
            ]
    return []


def issue_mirror_fallback_step_findings(
    path: Path,
    contexts: list[StepContext],
) -> list[Finding]:
    """Return issue-mirror fallback step-specific findings."""
    fallback_steps = issue_mirror_checkout_failure_summary_steps(contexts)
    if not fallback_steps:
        return [
            Finding("error", path, "issue_mirror_checkout_failure_summary_missing")
        ]
    findings: list[Finding] = []
    for context in fallback_steps:
        run = context.step.get("run")
        if not isinstance(run, str):
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_failure_summary_missing_run",
                )
            )
            continue
        if not issue_mirror_failure_summary_guard_valid(context):
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_failure_summary_must_be_gated_by_failure",
                )
            )
        if "ISSUE_SYNC=pass" in run:
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_failure_fallback_must_fail",
                )
            )
        normalized_run = run.replace("\\`", "`")
        if (
            "status: `fail`" not in normalized_run
            or "reason: `checkout-failed`" not in normalized_run
        ):
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_failure_summary_must_be_fail",
                )
            )
        if "exit 1" not in run:
            findings.append(
                Finding(
                    "error",
                    path,
                    "issue_mirror_checkout_failure_must_be_nonzero",
                )
            )
    return findings


def issue_mirror_checkout_steps(contexts: list[StepContext]) -> list[StepContext]:
    """Return issue-mirror checkout steps in the check job."""
    return [
        context
        for context in contexts
        if context.step.get("uses") == "actions/checkout@v4"
    ]


def issue_mirror_issue_sync_checker_steps(
    contexts: list[StepContext],
) -> list[StepContext]:
    """Return issue-sync checker steps in the check job."""
    return [
        context
        for context in contexts
        if isinstance(context.step.get("run"), str)
        and "tools/agent_tools/issue_sync.py" in str(context.step.get("run"))
    ]


def issue_mirror_checkout_failure_summary_steps(
    contexts: list[StepContext],
) -> list[StepContext]:
    """Return issue-mirror fallback summary steps in the check job."""
    return [
        context
        for context in contexts
        if ISSUE_MIRROR_CHECKOUT_OUTCOME in str(context.step.get("if"))
        and " != 'success'" in str(context.step.get("if"))
    ]


def issue_mirror_failure_summary_guard_valid(context: StepContext) -> bool:
    """Return whether fallback summary step has the required failure guard."""
    step_if = context.step.get("if")
    return (
        isinstance(step_if, str)
        and ISSUE_MIRROR_CHECKOUT_FAILURE_GUARD in step_if
        and ISSUE_MIRROR_CHECKOUT_OUTCOME in step_if
        and " != 'success'" in step_if
    )


def check_workflow(root: Path, path: Path) -> list[Finding]:
    """Check one GitHub Actions workflow."""
    workflow = load_workflow(path)
    workflow_text = read_text(path)
    return [
        *workflow_declared_findings(path, workflow),
        *(
            workflow_dispatch_input_interpolation_findings(path, workflow)
            if path.name == WORKFLOW_DISPATCH_INPUT_CHECK_WORKFLOW
            else []
        ),
        *(
            agent_canon_static_gate_findings(path, workflow, workflow_text)
            if path.name == "agent-canon-static-gates.yml"
            else []
        ),
        *(
            improvement_guide_trigger_findings(path, workflow_text)
            if path.name == "agent-improvement-guide.yml"
            else []
        ),
        *(
            coordination_summary_findings(path, workflow_text)
            if path.name == "agent-coordination.yml"
            else []
        ),
        *(
            coordination_relay_findings(path, workflow)
            if path.name == "agent-coordination.yml"
            else []
        ),
        *agent_canon_checkout_policy_findings(root, path, workflow, workflow_text),
        *issue_mirror_checkout_policy_findings(path, workflow),
        *checkout_step_findings(path, workflow),
    ]


def coordination_relay_findings(
    path: Path, workflow: dict[str, object]
) -> list[Finding]:
    """Reject the fixed manager reviewer/response pass-through chain."""
    findings: list[Finding] = []
    jobs = dict(job_items(workflow))
    if "coordinate" not in jobs:
        findings.append(Finding("error", path, "coordination_job_missing"))
    if set(jobs) != {"coordinate"}:
        findings.append(
            Finding("error", path, f"coordination_job_count:{len(jobs)}")
        )
    if "manager" in jobs:
        findings.append(Finding("error", path, "fixed_manager_relay_job:manager"))
    for relay_job in ("manager_reviewer", "manager_response"):
        if relay_job in jobs:
            findings.append(Finding("error", path, f"fixed_manager_relay_job:{relay_job}"))
    for job_name, job in jobs.items():
        needs = job.get("needs")
        if isinstance(needs, str):
            need_names: set[str] = {needs}
        elif isinstance(needs, list):
            need_names = {
                item for item in cast(list[object], needs) if isinstance(item, str)
            }
        else:
            need_names = set()
        for relay_job in ("manager_reviewer", "manager_response"):
            if relay_job in need_names:
                findings.append(
                    Finding(
                        "error",
                        path,
                        f"fixed_manager_relay_dependency:{job_name}:{relay_job}",
                    )
                )
    coordinate = jobs.get("coordinate")
    if coordinate is not None:
        steps = coordinate.get("steps")
        upload_count = 0
        if isinstance(steps, list):
            for item in cast(list[object], steps):
                step = as_string_dict(item)
                if isinstance(step, dict) and str(step.get("uses", "")).startswith(
                    "actions/upload-artifact@"
                ):
                    upload_count += 1
        if upload_count != 1:
            findings.append(
                Finding("error", path, f"coordination_bundle_upload_count:{upload_count}")
            )
    return findings


def improvement_guide_trigger_findings(
    path: Path, workflow_text: str
) -> list[Finding]:
    """Keep improvement guidance bounded to selected paths or manual dispatch."""
    findings: list[Finding] = []
    if re.search(r"(?m)^  push:\s*$", workflow_text):
        findings.append(Finding("error", path, "improvement_guide_push_trigger_forbidden"))
    if not re.search(r"(?ms)^  pull_request:\s*\n\s+paths:\s*\n", workflow_text):
        findings.append(Finding("error", path, "improvement_guide_pull_request_paths_required"))
    if not re.search(r"(?m)^  workflow_dispatch:\s*$", workflow_text):
        findings.append(Finding("error", path, "improvement_guide_manual_dispatch_required"))
    return findings


def coordination_summary_findings(path: Path, workflow_text: str) -> list[Finding]:
    """Require truthful packet readback and one write-scope validation boundary."""
    findings: list[Finding] = []
    for required in (
        "team_manifest.yaml",
        "run.capacity_request.lineage.role_ids",
        "GITHUB_STEP_SUMMARY",
        "SCHEDULED_SPECIALISTS=",
        "executed_role=coordination",
        "finding=none at intake",
        "result=bundle_ready",
    ):
        if required not in workflow_text:
            findings.append(Finding("error", path, f"coordination_summary_missing:{required}"))
    role_validation_count = workflow_text.count("--role manager")
    if role_validation_count != 1:
        findings.append(
            Finding(
                "error",
                path,
                f"coordination_write_scope_validation_count:{role_validation_count}",
            )
        )
    return findings


def agent_canon_static_gate_findings(
    path: Path,
    workflow: dict[str, object],
    workflow_text: str,
) -> list[Finding]:
    """Require one candidate-tree gate consumer and reject duplicate gate loops."""
    findings: list[Finding] = []
    wrapper = "bash tools/ci/check_agent_canon_pr.sh"
    run_steps = [
        (context, run)
        for context in step_contexts(workflow)
        if isinstance((run := context.step.get("run")), str)
    ]
    wrapper_steps = [context for context, run in run_steps if wrapper in run]
    if len(wrapper_steps) != 1:
        findings.append(
            Finding(
                "error",
                path,
                f"canonical_candidate_gate_consumer_count:{len(wrapper_steps)}",
            )
        )
    non_step_read_credential = AGENT_CANON_PR_READ_CREDENTIAL in (
        set(as_string_dict(workflow.get("env")) or {})
        | {
            name
            for _job_name, job in job_items(workflow)
            for name in set(as_string_dict(job.get("env")) or {})
        }
    )
    if non_step_read_credential:
        findings.append(
            Finding(
                "error",
                path,
                "canonical_candidate_gate_read_credential_must_be_step_local",
            )
        )
    for context in wrapper_steps:
        step_env = as_string_dict(context.step.get("env")) or {}
        if step_env.get(AGENT_CANON_PR_READ_CREDENTIAL) != GITHUB_TOKEN_EXPRESSION:
            findings.append(
                Finding(
                    "error",
                    path,
                    f"run_step_{context.index}_missing_step_local_github_read_credential",
                )
            )
    if re.search(r"(?m)^  push:\s*$", workflow_text):
        findings.append(
            Finding("error", path, "duplicate_push_trigger_for_candidate_gate")
        )
    for context, run in run_steps:
        if wrapper in run:
            continue
        for command in AGENT_CANON_STATIC_GATE_DIRECT_COMMANDS:
            if command in run:
                findings.append(
                    Finding(
                        "error",
                        path,
                        f"run_step_{context.index}_duplicates_canonical_gate:{command}",
                    )
                )
    return findings


def project_quality_owner_value(source: Mapping[str, object]) -> object:
    """Return the project-quality owner marker from a workflow object."""
    env = as_string_dict(source.get("env"))
    if env is None:
        return None
    return env.get(PARENT_PROJECT_QUALITY_OWNER_ENV)


def has_canonical_project_quality_command(run: str) -> bool:
    """Return whether a workflow run invokes the canonical parent quality command."""
    return any(
        line.strip() == PARENT_PROJECT_QUALITY_COMMAND for line in run.splitlines()
    )


def parent_project_quality_findings(root: Path) -> list[Finding]:
    """Require a parent-owned quality route in derived repository workflows."""
    workflow_dir = root / ".github" / "workflows"
    owner_routes: list[tuple[Path, str | None]] = []
    declared_owner = False
    for path in sorted(workflow_dir.glob("*.y*ml")):
        workflow = load_workflow(path)
        for _job_name, job in job_items(workflow):
            job_owner = project_quality_owner_value(job)
            if job_owner is not None:
                declared_owner = True
            job_steps = job.get("steps")
            steps = cast(list[object], job_steps) if isinstance(job_steps, list) else []
            for step_object in steps:
                step = as_string_dict(step_object)
                if step is None:
                    continue
                step_owner = project_quality_owner_value(step)
                if step_owner is not None:
                    declared_owner = True
                owner = step_owner if step_owner is not None else job_owner
                if owner == PARENT_PROJECT_QUALITY_OWNER:
                    run = step.get("run")
                    owner_routes.append(
                        (
                            path,
                            run if isinstance(run, str) else None,
                        )
                    )
    if not owner_routes:
        message = (
            "parent_project_quality_owner_must_be_parent_ci"
            if declared_owner
            else "missing_parent_project_quality_owner"
        )
        return [Finding("error", workflow_dir, message)]
    if any(
        run is not None and has_canonical_project_quality_command(run)
        for _path, run in owner_routes
    ):
        return []
    return [
        Finding(
            "error",
            path,
            "parent_project_quality_route_missing_canonical_command",
        )
        for path, _run in owner_routes[:1]
    ]


def require_text(path: Path, required: Sequence[str]) -> list[Finding]:
    """Check that a file contains all required snippets."""
    if not path.exists():
        return [Finding("error", path, "missing_file")]
    text = read_text(path)
    normalized_text = re.sub(r"/{2,}", "/", text)
    return [
        Finding("error", path, f"missing_text:{item}")
        for item in required
        if item not in text and item not in normalized_text
    ]


def require_text_any_of(path: Path, options: Sequence[str]) -> list[Finding]:
    """Check that a file contains one of the allowed snippets."""
    if not path.exists():
        return [Finding("error", path, "missing_file")]
    text = read_text(path)
    normalized_text = re.sub(r"/{2,}", "/", text)
    if any(option in text or option in normalized_text for option in options):
        return []
    joined = " | ".join(options)
    return [Finding("error", path, f"missing_text_any_of:{joined}")]


def projected_template_requirements(
    root: Path, required: Sequence[str]
) -> tuple[str, ...]:
    """Map standalone tool commands to the parent projection view."""
    if not is_template_or_derived_repo(root):
        return tuple(required)
    return tuple(
        item.replace("tools/agent_tools/", "vendor/agent-canon/tools/agent_tools/")
        .replace("tools/ci/", "vendor/agent-canon/tools/ci/")
        .replace("tools/sync_agent_canon.sh", "vendor/agent-canon/tools/sync_agent_canon.sh")
        .replace(
            "tools/update_agent_canon.sh", "vendor/agent-canon/tools/update_agent_canon.sh"
        )
        for item in required
    )


def check_root_copy_headers(root: Path) -> list[Finding]:
    """Check synced root-copy workflow source markers."""
    findings: list[Finding] = []
    stale_template_dashboard = (
        root / ".github" / "workflows" / "agent-runtime-dashboard.yml"
    )
    if is_template_or_derived_repo(root) and stale_template_dashboard.exists():
        findings.append(
            Finding(
                "error",
                stale_template_dashboard,
                "template_runtime_dashboard_workflow_must_be_absent_use_agentcanon_repo",
            )
        )
    for path, required in workflow_header_requirement_specs(root):
        if path.exists():
            if path == root / ".github" / "workflows" / "agent-improvement-guide.yml":
                findings.extend(
                    require_text_any_of(
                        path, ROOT_IMPROVEMENT_GUIDE_WORKFLOW_ALLOWED_TAGS
                    )
                )
            findings.extend(require_text(path, required))
    return findings


def workflow_header_requirement_specs(root: Path) -> list[tuple[Path, Sequence[str]]]:
    """Return optional workflow files and snippets that identify their contract."""
    workflow_dir = root / ".github" / "workflows"
    vendor_workflow_dir = root / "vendor" / "agent-canon" / ".github" / "workflows"
    specs: list[tuple[Path, Sequence[str]]] = [
        (
            workflow_dir / "agent-coordination.yml",
            ROOT_COORDINATION_WORKFLOW_REQUIREMENTS,
        ),
        (
            workflow_dir / "agent-improvement-guide.yml",
            ROOT_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS,
        ),
        (
            workflow_dir / "agent-canon-static-gates.yml",
            AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS,
        ),
        (
            vendor_workflow_dir / "agent-coordination.yml",
            VENDOR_COORDINATION_WORKFLOW_REQUIREMENTS,
        ),
        (
            vendor_workflow_dir / "agent-improvement-guide.yml",
            VENDOR_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS,
        ),
        (
            vendor_workflow_dir / "agent-canon-static-gates.yml",
            AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS,
        ),
    ]
    if is_template_or_derived_repo(root):
        specs.append(
            (
                vendor_workflow_dir / "agent-runtime-dashboard.yml",
                STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS,
            )
        )
        specs.append(
            (
                vendor_workflow_dir / "issue-mirror.yml",
                STANDALONE_ISSUE_MIRROR_WORKFLOW_REQUIREMENTS,
            )
        )
    else:
        specs.append(
            (
                workflow_dir / "agent-runtime-dashboard.yml",
                STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS,
            )
        )
        specs.append(
            (
                workflow_dir / "issue-mirror.yml",
                STANDALONE_ISSUE_MIRROR_WORKFLOW_REQUIREMENTS,
            )
        )
    return specs


def pr_template_requirement_specs(root: Path) -> list[tuple[Path, Sequence[str]]]:
    """Return PR-template requirement checks for the active repository mode."""
    if is_template_or_derived_repo(root):
        specs: list[tuple[Path, Sequence[str]]] = [
            (
                root
                / "vendor"
                / "agent-canon"
                / ".github"
                / "PULL_REQUEST_TEMPLATE.md",
                PR_TEMPLATE_REQUIRED_TEXT,
            ),
        ]
        return specs
    return [
        (
            root / ".github" / "PULL_REQUEST_TEMPLATE.md",
            PR_TEMPLATE_REQUIRED_TEXT,
        )
    ]


def check_template_agentcanon_pr_gate(path: Path) -> list[Finding]:
    """Check the concise PR evidence contract and reject legacy gate loops."""
    if not path.exists():
        return [Finding("error", path, "missing_file")]
    text = read_text(path)
    findings: list[Finding] = []
    for item in PR_TEMPLATE_FORBIDDEN_TEXT:
        if item in text:
            findings.append(
                Finding(
                    "error",
                    path,
                    f"forbidden_universal_pr_gate:{item}",
                )
            )
    for field in ("source_commit", "template_pin", "pr_head"):
        count = len(re.findall(rf"(?m)^\s*-\s*{re.escape(field)}:", text))
        if count != 1:
            findings.append(
                Finding("error", path, f"identity_field_count:{field}:{count}")
            )
    relation_count = text.count(
        "identity relation (source_commit -> template_pin -> pr_head):"
    )
    if relation_count != 1:
        findings.append(
            Finding("error", path, f"identity_relation_count:{relation_count}")
        )
    return findings


def check_pr_templates(root: Path) -> list[Finding]:
    """Check PR template evidence fields."""
    findings: list[Finding] = []
    for path, required in pr_template_requirement_specs(root):
        findings.extend(require_text(path, required))
    canon_root = agent_canon_root(root)
    semantic_templates = {
        canon_root / "templates" / "documents" / "github" / "pull-request" / "agent_canon.md",
    }
    if not is_template_or_derived_repo(root):
        semantic_templates.add(root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md")
    if not is_template_or_derived_repo(root):
        optional_root_template = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
        semantic_templates.add(optional_root_template)
    for path in sorted(semantic_templates):
        findings.extend(check_template_agentcanon_pr_gate(path))
    return findings


def submodule_checkout_script_findings(root: Path) -> list[Finding]:
    """Return findings for template-mode private submodule checkout script docs."""
    if not is_template_or_derived_repo(root):
        return []
    findings: list[Finding] = []
    findings.extend(
        require_text(
            root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh",
            SUBMODULE_CHECKOUT_SCRIPT_REQUIREMENTS,
        )
    )
    wrapper_path = root / "tools" / "ci" / "checkout_agent_canon_submodule.sh"
    if not wrapper_path.is_file():
        wrapper_path = (
            root / "tools" / "agent-canon" / "ci" / "checkout_agent_canon_submodule.sh"
        )
    findings.extend(require_text(wrapper_path, SUBMODULE_CHECKOUT_WRAPPER_REQUIREMENTS))
    return findings


def check_github_support_surfaces(root: Path) -> list[Finding]:
    """Check GitHub support surfaces that are still active in Codex-only mode."""
    return submodule_checkout_script_findings(root)


def check_pr_flow_docs(root: Path) -> list[Finding]:
    """Check that the source PR lane binds typed identity, CAS, and readback."""
    workflow_path = (
        agent_canon_root(root) / "agents" / "workflows" / "agent-canon-pr-workflow.md"
    )
    return require_text(
        workflow_path,
        [
            "SourceMainRebindReceipt",
            "CandidateFreezeReceipt",
            "CandidateReviewReceipt",
            "CandidateCasReceipt",
            "PullRequestLifecycle",
            "user|fork|contributor",
            "PR Essence",
            "permission_state=unknown|verified_false",
            "PublicationReadbackReceipt",
            "QueueReceipt",
            "DependencyFrontier",
            "tools/agent_tools/github_publish.py",
            "parent pin/root sync before accepted frontier",
        ],
    )


def check_agentcanon_issues(root: Path) -> list[Finding]:
    """Check AgentCanon durable operational issue conventions."""
    canon_root = agent_canon_root(root)
    findings = require_text(
        canon_root / "issues" / "README.md",
        [
            "AgentCanon Operational Issues",
            "issues/open/AC-YYYYMMDD-short-slug.md",
            "issues/closed/",
            "Required Fields",
            "affected_surfaces:",
            "edit_scope:",
            "run_repo_dependency_review.sh",
            "--search-hits-file",
            "DEPENDENCY_EDIT_SCOPE_PATH",
        ],
    )
    for issue_path in sorted((canon_root / "issues").glob("*/*.md")):
        if issue_path.name == "README.md":
            continue
        findings.extend(
            require_text(
                issue_path,
                [
                    "issue_id:",
                    "status:",
                    "source:",
                    "severity:",
                    "evidence:",
                    "affected_surfaces:",
                    "edit_scope:",
                    "required_action:",
                    "close_condition:",
                ],
            )
        )
    return findings


def github_workflow_findings(root: Path) -> tuple[list[Finding], list[Path]]:
    """Return all workflow and PR-surface findings."""
    workflows = workflow_paths(root)
    findings: list[Finding] = []
    for path in workflows:
        findings.extend(check_workflow(root, path))
    if is_template_or_derived_repo(root):
        findings.extend(parent_project_quality_findings(root))
    findings.extend(check_root_copy_headers(root))
    findings.extend(check_pr_templates(root))
    findings.extend(check_github_support_surfaces(root))
    findings.extend(check_pr_flow_docs(root))
    findings.extend(check_agentcanon_issues(root))
    return findings, workflows


def print_github_workflow_report(
    root: Path,
    findings: list[Finding],
    workflows: list[Path],
) -> None:
    """Print a compact GitHub workflow convention report."""
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    for finding in findings:
        print(finding.line(root))
    print(f"GITHUB_WORKFLOWS_CHECKED={len(workflows)}")
    print(f"GITHUB_WORKFLOW_ERRORS={len(errors)}")
    print(f"GITHUB_WORKFLOW_WARNINGS={len(warnings)}")
    print("GITHUB_WORKFLOWS=fail" if errors else "GITHUB_WORKFLOWS=pass")


def github_workflow_exit_code(findings: list[Finding]) -> int:
    """Return a process exit code for GitHub workflow convention findings."""
    if any(finding.severity == "error" for finding in findings):
        return 1
    return 0


def run_github_workflow_checks(root: Path) -> int:
    """Run all checks and print a compact status report."""
    root = root.resolve()
    findings, workflows = github_workflow_findings(root)
    print_github_workflow_report(root, findings, workflows)
    return github_workflow_exit_code(findings)


def main() -> int:
    """Parse arguments and run the checker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to check",
    )
    args = parser.parse_args()
    return run_github_workflow_checks(args.root)


if __name__ == "__main__":
    sys.exit(main())
