# @dependency-start
# responsibility Checks GitHub workflow, PR template, and Copilot runtime conventions.
# upstream design ../../agents/workflows/github-copilot-workflow.md GitHub Actions rules
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md PR evidence rules
# downstream implementation ../../tests/tools/test_check_github_workflows.py tests
# @dependency-end

"""Check GitHub workflow, PR template, and Copilot runtime conventions."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml


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


def checkout_steps(workflow: dict[str, object]) -> list[dict[str, object]]:
    """Return every actions/checkout step in one workflow."""
    steps: list[dict[str, object]] = []
    jobs = as_string_dict(workflow.get("jobs"))
    if jobs is None:
        return steps
    for job_object in jobs.values():
        job = as_string_dict(job_object)
        if job is None:
            continue
        job_steps = job.get("steps")
        if not isinstance(job_steps, list):
            continue
        for step_object in cast(list[object], job_steps):
            step = as_string_dict(step_object)
            if step is None:
                continue
            uses = step.get("uses")
            if isinstance(uses, str) and uses.startswith("actions/checkout@"):
                steps.append(step)
    return steps


def check_workflow(path: Path) -> list[Finding]:
    """Check one GitHub Actions workflow."""
    workflow = load_workflow(path)
    workflow_text = read_text(path)
    findings: list[Finding] = []
    if "permissions" not in workflow:
        findings.append(Finding("error", path, "missing_top_level_permissions"))
    if "concurrency" not in workflow:
        findings.append(Finding("warning", path, "missing_top_level_concurrency"))

    checkouts = checkout_steps(workflow)
    if checkouts and ".github/scripts/checkout_agent_canon_submodule.sh" not in workflow_text:
        findings.append(Finding("error", path, "missing_agent_canon_checkout_helper"))
    if checkouts and "AGENT_CANON_REPO_TOKEN" not in workflow_text:
        findings.append(Finding("error", path, "missing_agent_canon_repo_token_env"))

    for index, step in enumerate(checkouts, start=1):
        with_block = as_string_dict(step.get("with"))
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


def require_text(path: Path, required: list[str]) -> list[Finding]:
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
    root_workflow = root / ".github" / "workflows" / "agent-coordination.yml"
    if root_workflow.exists():
        findings.extend(
            require_text(
                root_workflow,
                [
                    "Synced to /.github/workflows/agent-coordination.yml",
                    "Edit vendor/agent-canon/.github/workflows/agent-coordination.yml",
                ],
            )
        )
    vendor_workflow = (
        root
        / "vendor"
        / "agent-canon"
        / ".github"
        / "workflows"
        / "agent-coordination.yml"
    )
    if vendor_workflow.exists():
        findings.extend(
            require_text(
                vendor_workflow,
                ["agents/workflows/agent-canon-pr-workflow.md"],
            )
        )
    return findings


def check_pr_templates(root: Path) -> list[Finding]:
    """Check PR template evidence fields."""
    template_mode = (root / "vendor" / "agent-canon").exists()
    if template_mode:
        checks = {
            root / ".github" / "PULL_REQUEST_TEMPLATE.md": [
                "Validation Evidence",
                "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
                "make ci",
                "AgentCanon Evidence",
                "template submodule SHA:",
            ],
            root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md": [
                "make agent-canon-pr-check",
                "bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing",
                "Submodule Pin Change",
                "GitHub Mirror / Submodule Evidence",
                "template submodule SHA:",
            ],
            root / "vendor" / "agent-canon" / ".github" / "PULL_REQUEST_TEMPLATE.md": [
                "Validation Evidence",
                "Submodule Pin Impact",
                "expected template submodule SHA:",
            ],
        }
    else:
        checks = {
            root / ".github" / "PULL_REQUEST_TEMPLATE.md": [
                "Validation Evidence",
                "Submodule Pin Impact",
                "expected template submodule SHA:",
            ],
        }
    findings: list[Finding] = []
    for path, required in checks.items():
        findings.extend(require_text(path, required))
    return findings


def check_copilot_surfaces(root: Path) -> list[Finding]:
    """Check Copilot and PR-template discovery surfaces."""
    readme_path = root / "README.md"
    if (root / "vendor" / "agent-canon").exists():
        readme_path = root / "vendor" / "agent-canon" / "README.md"
    return [
        *require_text(
            root / ".github" / "copilot-instructions.md",
            [
                "agents/workflows/github-copilot-workflow.md",
                "AGENT_CANON_REPO_TOKEN",
            ],
        ),
        *require_text(
            readme_path,
            [".github/PULL_REQUEST_TEMPLATE.md"],
        ),
        *require_text(
            root / ".github" / "AGENTS.md",
            ["/.github/PULL_REQUEST_TEMPLATE/agent_canon.md"],
        ),
    ]

def run(root: Path) -> int:
    """Run all checks and print a compact status report."""
    root = root.resolve()
    findings: list[Finding] = []
    workflows = workflow_paths(root)
    for path in workflows:
        findings.extend(check_workflow(path))
    findings.extend(check_root_copy_headers(root))
    findings.extend(check_pr_templates(root))
    findings.extend(check_copilot_surfaces(root))

    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    for finding in findings:
        print(finding.line(root))
    print(f"GITHUB_WORKFLOWS_CHECKED={len(workflows)}")
    print(f"GITHUB_WORKFLOW_ERRORS={len(errors)}")
    print(f"GITHUB_WORKFLOW_WARNINGS={len(warnings)}")
    if errors:
        print("GITHUB_WORKFLOWS=fail")
        return 1
    print("GITHUB_WORKFLOWS=pass")
    return 0


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
    return run(args.root)


if __name__ == "__main__":
    sys.exit(main())
