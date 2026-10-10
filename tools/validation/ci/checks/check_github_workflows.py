# @dependency-start
# contract tool
# responsibility Runs native GitHub workflow validation and checks AgentCanon workflow and PR-template contracts.
# upstream design ../../../../agents/skills/agent-canon-update.md PR evidence rules
# upstream design ../../../../README.md AgentCanon surface index
# upstream design ../../../../.github/AGENTS.md GitHub agent entrypoint
# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE.md standalone PR checklist
# upstream design ../../../../.github/workflows/agent-improvement-guide.yml PR and push improvement guide workflow
# upstream design ../../../../.github/workflows/agent-runtime-dashboard.yml standalone AgentCanon runtime dashboard workflow
# upstream design ../../../../.github/workflows/agent-canon-static-gates.yml PR candidate gate workflow
# upstream implementation ../../semantic/skills/check_skill_frontmatter.py validates runtime skill frontmatter in static gates
# downstream implementation ../../../../tests/tools/test_check_github_workflows.py tests
# downstream implementation ../../../../bootstrap/container/image/dependencies.toml pins actionlint, ShellCheck, and zizmor
# @dependency-end

"""Run native GitHub workflow checks and validate AgentCanon PR-template contracts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ACTIONLINT_EXECUTABLE = Path("/usr/local/bin/actionlint")
ACTIONLINT_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "actionlint.yaml"
)
SHELLCHECK_EXECUTABLE = Path("/usr/local/bin/shellcheck")
ZIZMOR_EXECUTABLE = Path("/usr/local/bin/zizmor")

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
    "Copilot Configuration Impact",
    "Candidate Commit And Publication Identity",
    "GitHub Mirror / Submodule Evidence",
    "template submodule SHA:",
)
ROOT_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS = ("generate_agent_improvement_guide.py",)
STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS = (
    "workflow_dispatch:",
    "schedule:",
    "generate_agent_runtime_dashboard.py",
)
AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS = (
    "pull_request:",
    "workflow_dispatch:",
    "github.event.pull_request.head.sha || github.sha",
    "bootstrap.sh",
    "run_standalone_static_gate_unit.sh",
)


@dataclass(frozen=True)
class Finding:
    """One AgentCanon-owned workflow or PR-template finding."""

    severity: str
    path: Path
    message: str

    def line(self, root: Path) -> str:
        """Return a stable machine-readable line for an AgentCanon-owned finding."""
        return (
            f"GITHUB_WORKFLOW_FINDING severity={self.severity} "
            f"path={self.path.relative_to(root).as_posix()} message={self.message}"
        )


def read_text(path: Path) -> str:
    """Read text with repository-default encoding."""
    return path.read_text(encoding="utf-8")


def workflow_paths(root: Path) -> list[Path]:
    """Return the standalone AgentCanon workflow files to check."""
    return sorted((root / ".github" / "workflows").glob("*.y*ml"))


def run_native_command(name: str, command: Sequence[str], root: Path) -> int:
    """Run one pinned native command without capturing or translating its output."""
    try:
        result = subprocess.run(command, cwd=root, check=False)
    except OSError as exc:
        print(
            f"GITHUB_WORKFLOW_TOOL_START_ERROR tool={name} "
            f"executable={command[0]} error={exc}",
            file=sys.stderr,
            flush=True,
        )
        return 127
    print(f"GITHUB_WORKFLOW_TOOL_EXIT={name} code={result.returncode}", flush=True)
    return result.returncode


def run_native_workflow_checks(root: Path, workflows: list[Path]) -> list[int]:
    """Run actionlint and zizmor on the same explicit standalone workflow set."""
    if not workflows:
        return []

    workflow_args = [path.relative_to(root).as_posix() for path in workflows]
    print(f"GITHUB_WORKFLOW_NATIVE_INPUTS={','.join(workflow_args)}", flush=True)
    print(
        "GITHUB_WORKFLOW_NATIVE_TOOL=actionlint "
        f"executable={ACTIONLINT_EXECUTABLE} config={ACTIONLINT_CONFIG} "
        f"shellcheck={SHELLCHECK_EXECUTABLE}",
        flush=True,
    )
    actionlint_version_status = run_native_command(
        "actionlint-version",
        [str(ACTIONLINT_EXECUTABLE), "-version"],
        root,
    )
    shellcheck_version_status = run_native_command(
        "shellcheck-version",
        [str(SHELLCHECK_EXECUTABLE), "--version"],
        root,
    )
    actionlint_status = run_native_command(
        "actionlint",
        [
            str(ACTIONLINT_EXECUTABLE),
            "-no-color",
            "-config-file",
            str(ACTIONLINT_CONFIG),
            f"-shellcheck={SHELLCHECK_EXECUTABLE}",
            *workflow_args,
        ],
        root,
    )

    print(
        "GITHUB_WORKFLOW_NATIVE_TOOL=zizmor "
        f"executable={ZIZMOR_EXECUTABLE} policy=default",
        flush=True,
    )
    zizmor_version_status = run_native_command(
        "zizmor-version",
        [str(ZIZMOR_EXECUTABLE), "--version"],
        root,
    )
    zizmor_status = run_native_command(
        "zizmor",
        [
            str(ZIZMOR_EXECUTABLE),
            "--strict-collection",
            "--format=plain",
            "--color=never",
            "--no-progress",
            *workflow_args,
        ],
        root,
    )
    return [
        actionlint_version_status,
        shellcheck_version_status,
        actionlint_status,
        zizmor_version_status,
        zizmor_status,
    ]


def require_text(path: Path, required: Sequence[str]) -> list[Finding]:
    """Check an AgentCanon-owned workflow marker or PR-template phrase."""
    if not path.exists():
        return [Finding("error", path, "missing_file")]
    text = read_text(path)
    normalized_text = re.sub(r"/{2,}", "/", text)
    return [
        Finding("error", path, f"missing_text:{item}")
        for item in required
        if item not in text and item not in normalized_text
    ]


def workflow_header_requirement_specs(root: Path) -> list[tuple[Path, Sequence[str]]]:
    """Return optional workflow files and snippets that identify their contract."""
    workflow_dir = root / ".github" / "workflows"
    return [
        (
            workflow_dir / "agent-improvement-guide.yml",
            ROOT_IMPROVEMENT_GUIDE_WORKFLOW_REQUIREMENTS,
        ),
        (
            workflow_dir / "agent-runtime-dashboard.yml",
            STANDALONE_RUNTIME_DASHBOARD_WORKFLOW_REQUIREMENTS,
        ),
        (
            workflow_dir / "agent-canon-static-gates.yml",
            AGENT_CANON_STATIC_GATES_WORKFLOW_REQUIREMENTS,
        ),
    ]


def check_root_copy_headers(root: Path) -> list[Finding]:
    """Keep required source markers on standalone AgentCanon workflows."""
    findings: list[Finding] = []
    for path, required in workflow_header_requirement_specs(root):
        if path.exists():
            findings.extend(require_text(path, required))
    return findings


def pr_template_requirement_specs(root: Path) -> list[tuple[Path, Sequence[str]]]:
    """Return standalone AgentCanon PR-template requirement checks."""
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
    """Check PR template evidence fields independently from workflow tools."""
    findings: list[Finding] = []
    for path, required in pr_template_requirement_specs(root):
        findings.extend(require_text(path, required))
    semantic_templates = {
        root / "templates" / "documents" / "github" / "pull-request" / "agent_canon.md",
        root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md",
        root / ".github" / "PULL_REQUEST_TEMPLATE.md",
    }
    for path in sorted(semantic_templates):
        findings.extend(check_template_agentcanon_pr_gate(path))
    return findings


def github_workflow_findings(root: Path) -> tuple[list[Finding], list[Path]]:
    """Return AgentCanon-owned residual findings and the native tool input set."""
    workflows = workflow_paths(root)
    findings = [*check_root_copy_headers(root), *check_pr_templates(root)]
    return findings, workflows


def print_github_workflow_report(
    root: Path,
    findings: list[Finding],
    workflows: list[Path],
    native_statuses: list[int],
) -> None:
    """Print AgentCanon-owned residuals and combined native execution status."""
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    for finding in findings:
        print(finding.line(root))
    native_failures = sum(status != 0 for status in native_statuses)
    print(f"GITHUB_WORKFLOWS_CHECKED={len(workflows)}")
    print(f"GITHUB_WORKFLOW_ERRORS={len(errors)}")
    print(f"GITHUB_WORKFLOW_WARNINGS={len(warnings)}")
    print(f"GITHUB_WORKFLOW_NATIVE_FAILURES={native_failures}")
    print(
        "GITHUB_WORKFLOWS=fail"
        if errors or native_failures
        else "GITHUB_WORKFLOWS=pass"
    )


def github_workflow_exit_code(
    findings: list[Finding], native_statuses: list[int]
) -> int:
    """Preserve a native failure code, then report AgentCanon residual failures."""
    for status in native_statuses:
        if status != 0:
            return status
    return 1 if any(finding.severity == "error" for finding in findings) else 0


def run_github_workflow_checks(root: Path) -> int:
    """Run native workflow analyzers and the independent AgentCanon residuals."""
    root = root.resolve()
    findings, workflows = github_workflow_findings(root)
    native_statuses = run_native_workflow_checks(root, workflows)
    print_github_workflow_report(root, findings, workflows, native_statuses)
    return github_workflow_exit_code(findings, native_statuses)


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
