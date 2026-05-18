# @dependency-start
# responsibility Checks GitHub workflow, PR template, and Copilot runtime conventions.
# upstream design ../../agents/workflows/github-copilot-workflow.md GitHub Actions rules
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md PR evidence rules
# upstream design ../../README.md AgentCanon surface index
# upstream design ../../.github/AGENTS.md GitHub agent entrypoint
# upstream design ../../.github/copilot-instructions.md Copilot instruction surface
# upstream design ../../.github/instructions/pr-processing.instructions.md PR processing surface
# upstream design ../../.github/agents/pr-maintainer.md PR maintainer surface
# upstream design ../../documents/github-copilot-configuration.md Copilot configuration catalog
# upstream design ../../issues/README.md durable operational issue conventions
# upstream design ../../.github/PULL_REQUEST_TEMPLATE.md standalone PR checklist
# upstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template AgentCanon PR checklist
# upstream design ../../.github/workflows/agent-coordination.yml workflow source
# upstream design ../../.github/workflows/agent-improvement-guide.yml PR and push improvement guide workflow
# upstream design ../../.github/workflows/agent-runtime-dashboard.yml standalone AgentCanon runtime dashboard workflow
# upstream design ../../.github/workflows/issue-mirror.yml standalone local/GitHub issue mirror workflow
# upstream design ../../.github/workflows/agent-canon-static-gates.yml PR and push static gate workflow
# upstream implementation ./checkout_agent_canon_submodule.sh private submodule helper
# downstream implementation ../../tests/tools/test_check_github_workflows.py tests
# @dependency-end

"""Check GitHub workflow, PR template, and Copilot runtime conventions."""

from __future__ import annotations

import argparse
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
AGENT_CANON_INDEPENDENT_WORKFLOWS: set[str] = {
    "agent-runtime-dashboard.yml",
    "issue-mirror.yml",
}
AGENT_CANON_CREDENTIALS = (
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
)
TEMPLATE_ROOT_PR_TEMPLATE_REQUIREMENTS = (
    "Validation Evidence",
    "Plan Mode Evidence",
    "PR Mutation Authority",
    "Authority / blocker notes",
    "Copilot / Automation Output",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "Operational Findings / Issues",
    "vendor/agent-canon/issues/README.md",
    "vendor/agent-canon/issues/closed/",
    "Agent Improvement Guide artifact",
    "Issue Mirror artifact",
    "run_repo_dependency_review.sh --search-hits-file",
    "Copilot Configuration Impact",
    "vendor/agent-canon/documents/github-copilot-configuration.md",
    "Template / derived project PR",
    "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
    "make ci",
    "AgentCanon Evidence",
    "template submodule SHA:",
)
TEMPLATE_AGENT_CANON_PR_TEMPLATE_REQUIREMENTS = (
    "make agent-canon-pr-check",
    "make agent-canon-ensure-latest",
    "Plan Mode Evidence",
    "PR Mutation Authority",
    "Authority / blocker notes",
    "Copilot / Automation Output",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "Branch And Change Route",
    "Operational Findings / Issues",
    "vendor/agent-canon/issues/README.md",
    "vendor/agent-canon/issues/open/AC-YYYYMMDD-<slug>.md",
    "vendor/agent-canon/issues/closed/",
    "Agent Improvement Guide artifact",
    "Issue Mirror artifact",
    "run_repo_dependency_review.sh --search-hits-file",
    "Copilot Configuration Impact",
    "documents/github-copilot-configuration.md",
    "AgentCanon source PR",
    "Direct `bash tools/sync_agent_canon.sh push` was not used",
    "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
    "Submodule Pin Change",
    "GitHub Mirror / Submodule Evidence",
    "template submodule SHA:",
)
STANDALONE_AGENT_CANON_PR_TEMPLATE_REQUIREMENTS = (
    "Validation Evidence",
    "Plan Mode Evidence",
    "PR Mutation Authority",
    "Authority / blocker notes",
    "Copilot / Automation Output",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "Branch And Change Route",
    "Operational Findings / Issues",
    "issues/README.md",
    "issues/open/AC-YYYYMMDD-<slug>.md",
    "issues/closed/",
    "Agent Improvement Guide artifact",
    "Issue Mirror artifact",
    "AgentCanon Static Gates",
    "run_repo_dependency_review.sh --search-hits-file",
    "Copilot Configuration Impact",
    "documents/github-copilot-configuration.md",
    "standalone AgentCanon repository",
    "make agent-canon-ensure-latest",
    "Submodule Pin Impact",
    "expected template submodule SHA:",
)
COPILOT_INSTRUCTIONS_REQUIREMENTS = (
    "agents/workflows/github-copilot-workflow.md",
    "vendor/agent-canon/documents/github-copilot-configuration.md",
    "documents/github-copilot-configuration.md",
    ".github/instructions/pr-processing.instructions.md",
    ".github/agents/pr-maintainer.md",
    "Plan mode",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
)
PR_PROCESSING_INSTRUCTIONS_REQUIREMENTS = (
    'applyTo: "**"',
    "vendor/agent-canon/documents/github-copilot-configuration.md",
    "documents/github-copilot-configuration.md",
    "Plan mode",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "AGENT_CANON_SUBMODULE_AUTH=missing",
    "private submodule authentication",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
)
PR_MAINTAINER_REQUIREMENTS = (
    "description:",
    "vendor/agent-canon/documents/github-copilot-configuration.md",
    "documents/github-copilot-configuration.md",
    "Plan mode",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "AGENT_CANON_SUBMODULE_AUTH=missing",
    "AGENT_CANON_SUBMODULE_AUTH=token_persisted",
    "AGENT_CANON_SUBMODULE_AUTH=ssh_persisted",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
    "Do not delete the AgentCanon submodule",
)
GITHUB_AGENTS_REQUIREMENTS = (
    "/.github/PULL_REQUEST_TEMPLATE/agent_canon.md",
    "vendor/agent-canon/documents/github-copilot-configuration.md",
    "documents/github-copilot-configuration.md",
    "Plan mode",
)
COPILOT_CONFIG_REQUIREMENTS = (
    "GitHub Copilot Configuration",
    ".github/copilot-instructions.md",
    ".github/instructions/**/*.instructions.md",
    "AGENTS.md",
    ".github/agents/*.md",
    "tools:",
    "mcp-servers:",
    ".github/workflows/copilot-setup-steps.yml",
    "standalone AgentCanon repository",
    "Template / derived",
    "Plan mode",
    "COPILOT_PR_DECISION",
    "github_copilot_merge_when_green",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
    "COPILOT_MCP_",
    "MCP",
)
SUBMODULE_CHECKOUT_SCRIPT_REQUIREMENTS = (
    "AGENT_CANON_SUBMODULE_AUTH=missing",
    "AGENT_CANON_SUBMODULE_AUTH=denied",
    "AGENT_CANON_SUBMODULE_AUTH=ssh_denied",
    "AGENT_CANON_SUBMODULE_AUTH=token_persisted",
    "AGENT_CANON_SUBMODULE_AUTH=ssh_persisted",
    "AGENT_CANON_REPO_TOKEN",
    "AGENT_CANON_REPO_SSH_KEY",
    "GITHUB_ENV",
    "url.${ssh_submodule_url}.insteadOf",
    "untrusted PR context",
    "exit 86",
)
ROOT_COORDINATION_WORKFLOW_REQUIREMENTS = (
    "Synced to /.github/workflows/agent-coordination.yml",
    "Edit vendor/agent-canon/.github/workflows/agent-coordination.yml",
)
ROOT_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS = (
    "Synced to /.github/workflows/agent-improvement-guide.yml",
    "Edit vendor/agent-canon/.github/workflows/agent-improvement-guide.yml",
    "generate_agent_improvement_guide.py",
)
STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS = (
    "Standalone-only workflow",
    "Template and derived repositories should not copy",
    "generate_agent_runtime_dashboard.py",
)
STANDALONE_ISSUE_MIRROR_WORKFLOW_REQUIREMENTS = (
    "Standalone-only workflow",
    "Template and derived repositories should not copy",
    "issue_sync.py",
    "--github-check",
    "--sync-github",
    "GITHUB_STEP_SUMMARY",
    "permissions:",
    "issues: read",
    "issues: write",
)
VENDOR_COORDINATION_WORKFLOW_REQUIREMENTS = (
    "agents/workflows/agent-canon-pr-workflow.md",
)
VENDOR_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS = (
    "pull_request:",
    "push:",
    "generate_agent_improvement_guide.py",
    "GITHUB_STEP_SUMMARY",
    "actions/upload-artifact@v4",
)
VENDOR_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS = (
    "pull_request:",
    "push:",
    "eval_accumulation_check.py",
    "evaluate_workflow_selection.py",
    "evaluate_report_quality.py",
    "generate_agent_runtime_dashboard.py",
    "GITHUB_STEP_SUMMARY",
    "actions/upload-artifact@v4",
)
AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS = (
    "tool_catalog.py",
    "tool_drift.py",
    "responsibility_scope.py",
    "issue_sync.py",
    "eval_accumulation_check.py",
    "local_llm_eval.py",
    "evaluate_workflow_selection.py",
    "evaluate_report_quality.py",
    "run_repo_dependency_review.sh --fail-missing",
    "check_github_workflows.py",
    "container_config.py",
)


def is_template_or_derived_repo(root: Path) -> bool:
    """Return whether root is a template or derived repo with AgentCanon vendored."""
    return (root / "vendor" / "agent-canon").exists() and (root / ".gitmodules").is_file()


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


def is_true(value: object) -> bool:
    """Return whether a YAML value means true for GitHub action inputs."""
    return value is True or str(value).lower() == "true"


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


def has_credential_env(
    workflow: dict[str, object],
    context: StepContext,
) -> bool:
    """Return whether a helper step receives AgentCanon credentials."""
    env_values: list[object] = []
    for source in (workflow, context.job, context.step):
        env = as_string_dict(source.get("env"))
        if env is not None:
            env_values.extend(env.keys())
    return any(name in env_values for name in AGENT_CANON_CREDENTIALS)


def agent_canon_checkout_command_steps(workflow: dict[str, object]) -> list[StepContext]:
    """Return steps that invoke the AgentCanon checkout helper."""
    steps: list[StepContext] = []
    for context in step_contexts(workflow):
        run = context.step.get("run")
        if isinstance(run, str) and any(path in run for path in HELPER_PATHS):
            steps.append(context)
    return steps


def referenced_agent_canon_checkout_script_available(root: Path, workflow_text: str) -> bool:
    """Return whether at least one helper path referenced by the workflow exists."""
    return any(path in workflow_text and (root / path).is_file() for path in HELPER_PATHS)


def workflow_declared_findings(path: Path, workflow: dict[str, object]) -> list[Finding]:
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
    requires_agent_canon_checkout = path.name not in AGENT_CANON_INDEPENDENT_WORKFLOWS
    if requires_agent_canon_checkout and checkouts and not helpers:
        findings.append(Finding("error", path, "missing_agent_canon_checkout_helper"))
    if requires_agent_canon_checkout and checkouts and not any(name in workflow_text for name in AGENT_CANON_CREDENTIALS):
        findings.append(Finding("error", path, "missing_agent_canon_repo_credential_env"))
    if not requires_agent_canon_checkout:
        if helpers:
            findings.append(Finding("error", path, "agent_canon_checkout_helper_not_allowed"))
        if any(name in workflow_text for name in AGENT_CANON_CREDENTIALS):
            findings.append(Finding("error", path, "agent_canon_credentials_not_allowed"))
    if helpers and not referenced_agent_canon_checkout_script_available(root, workflow_text):
        findings.append(Finding("error", path, "missing_referenced_agent_canon_checkout_helper"))
    for helper_index, context in enumerate(helpers, start=1):
        if not has_credential_env(workflow, context):
            findings.append(
                Finding(
                    "error",
                    path,
                    f"checkout_helper_{helper_index}_missing_agent_canon_repo_credential_env",
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


def check_workflow(root: Path, path: Path) -> list[Finding]:
    """Check one GitHub Actions workflow."""
    workflow = load_workflow(path)
    workflow_text = read_text(path)
    return [
        *workflow_declared_findings(path, workflow),
        *agent_canon_checkout_policy_findings(root, path, workflow, workflow_text),
        *checkout_step_findings(path, workflow),
    ]


def require_text(path: Path, required: Sequence[str]) -> list[Finding]:
    """Check that a file contains all required snippets."""
    if not path.exists():
        return [Finding("error", path, "missing_file")]
    text = read_text(path)
    return [
        Finding("error", path, f"missing_text:{item}")
        for item in required
        if item not in text
    ]


def check_root_copy_headers(root: Path) -> list[Finding]:
    """Check synced root-copy workflow source markers."""
    findings: list[Finding] = []
    stale_template_dashboard = root / ".github" / "workflows" / "agent-runtime-dashboard.yml"
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
                VENDOR_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS,
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
        return [
            (
                root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md",
                TEMPLATE_AGENT_CANON_PR_TEMPLATE_REQUIREMENTS,
            ),
            (
                root / "vendor" / "agent-canon" / ".github" / "PULL_REQUEST_TEMPLATE.md",
                STANDALONE_AGENT_CANON_PR_TEMPLATE_REQUIREMENTS,
            ),
        ]
    return [
        (
            root / ".github" / "PULL_REQUEST_TEMPLATE.md",
            STANDALONE_AGENT_CANON_PR_TEMPLATE_REQUIREMENTS,
        )
    ]


def check_pr_templates(root: Path) -> list[Finding]:
    """Check PR template evidence fields."""
    findings: list[Finding] = []
    for path, required in pr_template_requirement_specs(root):
        findings.extend(require_text(path, required))
    return findings


def copilot_readme_path(root: Path) -> Path:
    """Return the README path that should mention Copilot routing."""
    if is_template_or_derived_repo(root):
        return root / "README.md"
    return root / "README.md"


def copilot_requirement_specs(root: Path) -> list[tuple[Path, Sequence[str]]]:
    """Return Copilot discovery surface requirement checks."""
    copilot_config_path = agent_canon_root(root) / "documents" / "github-copilot-configuration.md"
    return [
        (root / ".github" / "copilot-instructions.md", COPILOT_INSTRUCTIONS_REQUIREMENTS),
        (
            root / ".github" / "instructions" / "pr-processing.instructions.md",
            PR_PROCESSING_INSTRUCTIONS_REQUIREMENTS,
        ),
        (root / ".github" / "agents" / "pr-maintainer.md", PR_MAINTAINER_REQUIREMENTS),
        (
            copilot_readme_path(root),
            (
                ".github/PULL_REQUEST_TEMPLATE/agent_canon.md"
                if is_template_or_derived_repo(root)
                else ".github/PULL_REQUEST_TEMPLATE.md",
                "vendor/agent-canon/documents/github-copilot-configuration.md"
                if is_template_or_derived_repo(root)
                else "documents/github-copilot-configuration.md",
            ),
        ),
        (root / ".github" / "AGENTS.md", GITHUB_AGENTS_REQUIREMENTS),
        (
            copilot_config_path,
            COPILOT_CONFIG_REQUIREMENTS,
        ),
    ]


def submodule_checkout_script_findings(root: Path) -> list[Finding]:
    """Return findings for template-mode private submodule checkout script docs."""
    if not is_template_or_derived_repo(root):
        return []
    return require_text(
        root / ".github" / "scripts" / "checkout_agent_canon_submodule.sh",
        SUBMODULE_CHECKOUT_SCRIPT_REQUIREMENTS,
    )


def check_copilot_surfaces(root: Path) -> list[Finding]:
    """Check Copilot and PR-template discovery surfaces."""
    findings: list[Finding] = []
    for path, required in copilot_requirement_specs(root):
        findings.extend(require_text(path, required))
    findings.extend(submodule_checkout_script_findings(root))
    return findings


def check_pr_flow_docs(root: Path) -> list[Finding]:
    """Check that PR flow docs route standalone and template PRs separately."""
    workflow_path = (
        agent_canon_root(root) / "agents" / "workflows" / "agent-canon-pr-workflow.md"
    )
    return require_text(
        workflow_path,
        [
            "standalone AgentCanon repo",
            "`.github/PULL_REQUEST_TEMPLATE.md`",
            "template / derived repo",
            "`.github/PULL_REQUEST_TEMPLATE/agent_canon.md`",
            "Freshness Gate Route",
            "Issues / Findings Gate",
            "issues/open/AC-YYYYMMDD-short-slug.md",
            "issues/closed",
            "Agent Improvement Guide",
            "run_repo_dependency_review.sh",
            "--search-hits-file",
            "tool addition",
            "memory addition",
            "AgentCanon PR merge 後にこの check を再実行します",
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
    findings.extend(check_root_copy_headers(root))
    findings.extend(check_pr_templates(root))
    findings.extend(check_copilot_surfaces(root))
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
