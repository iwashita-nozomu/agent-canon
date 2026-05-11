#!/usr/bin/env python3
# @dependency-start
# responsibility Verifies repository convention compliance wiring and workflow gates.
# upstream design ../../documents/conventions/README.md convention index
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout prohibition policy
# upstream design ../../agents/templates/closeout_gate.md closeout gate policy
# upstream design ../../agents/evals/skill_workflow_prompt_eval.toml prompt eval gate
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../../documents/shared-runtime-surfaces.toml shared surface manifest
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream implementation ./tool_drift.py validates tool/convention drift
# upstream implementation ./surface_manifest.py validates shared surface manifest wiring
# downstream implementation ../../tools/ci/run_all_checks.sh runs convention compliance gate
# downstream implementation ../../tests/agent_tools/test_check_convention_compliance.py tests verifier  # noqa: E501
# @dependency-end
"""Verify that convention, workflow, and skill-routing gates are wired."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

CONVENTION_SOURCES = (
    "documents/conventions/README.md",
    "documents/conventions/common/01_principles.md",
    "documents/conventions/common/02_naming.md",
    "documents/conventions/common/03_comments.md",
    "documents/conventions/common/04_operators.md",
    "documents/conventions/common/05_docs.md",
    "documents/conventions/python/01_scope.md",
    "documents/conventions/python/04_type_annotations.md",
    "documents/conventions/python/06_comments.md",
    "documents/conventions/python/07_type_checker.md",
    "documents/conventions/python/09_file_roles.md",
    "documents/conventions/python/11_naming.md",
    "documents/conventions/python/15_jax_rules.md",
    "documents/conventions/python/20_benchmark_policy.md",
    "documents/conventions/python/30_experiment_directory_structure.md",
    "documents/coding-conventions-python.md",
    "documents/coding-conventions-cpp.md",
    "documents/coding-conventions-project.md",
    "documents/coding-conventions-house-style.md",
    "documents/coding-conventions-testing.md",
    "documents/coding-conventions-reviews.md",
    "documents/coding-conventions-experiments.md",
    "documents/coding-conventions-logging.md",
    "documents/algorithm-implementation-boundary.md",
    "documents/object-oriented-design.md",
    "documents/REVIEW_PROCESS.md",
    "agents/canonical/CODEX_WORKFLOW.md",
)

TOOL_GATES = {
    "dependency_review": (
        "tools/agent_tools/run_repo_dependency_review.sh",
        (
            "agents/canonical/CODEX_WORKFLOW.md",
            "agents/templates/closeout_gate.md",
        ),
    ),
    "code_dependency_scan": (
        "tools/agent_tools/scan_code_dependencies.sh",
        ("agents/workflows/hypothesis-validation-workflow.md",),
    ),
    "hardcoded_numbers": (
        "tools/agent_tools/check_hardcoded_numbers.py",
        (
            "tools/ci/run_all_checks.sh",
            "documents/conventions/common/01_principles.md",
        ),
    ),
    "static_any": (
        "tools/agent_tools/check_static_any.py",
        (
            "tools/ci/run_all_checks.sh",
            "documents/conventions/python/04_type_annotations.md",
            "documents/conventions/python/07_type_checker.md",
        ),
    ),
    "log_helper_names": (
        "tools/agent_tools/check_log_helper_names.py",
        (
            "tools/ci/run_all_checks.sh",
            "documents/coding-conventions-logging.md",
            "documents/conventions/common/02_naming.md",
        ),
    ),
    "oop_readability": (
        "tools/oop/python/readability.py",
        (
            "documents/object-oriented-design.md",
            "agents/workflows/comprehensive-refactoring-workflow.md",
        ),
    ),
    "oop_cpp_readability": (
        "tools/oop/cpp/readability.py",
        (
            "documents/object-oriented-design.md",
            "agents/workflows/comprehensive-refactoring-workflow.md",
        ),
    ),
    "prompt_eval": (
        "tools/agent_tools/evaluate_skill_workflow_prompts.py",
        (
            "agents/evals/skill_workflow_prompt_eval.toml",
            "agents/workflows/adaptive-improvement-workflow.md",
        ),
    ),
    "behavior_eval": (
        "tools/agent_tools/evaluate_agent_run.py",
        ("agents/evals/agent_behavior_eval.toml", "agents/templates/closeout_gate.md"),
    ),
    "convention_compliance": (
        "tools/agent_tools/check_convention_compliance.py",
        ("tools/ci/run_all_checks.sh", "agents/evals/skill_workflow_prompt_eval.toml"),
    ),
    "tool_catalog": (
        "tools/agent_tools/tool_catalog.py",
        (
            "tools/ci/run_all_checks.sh",
            "tools/README.md",
            "documents/tools/README.md",
        ),
    ),
    "tool_convention_drift": (
        "tools/agent_tools/tool_drift.py",
        (
            "tools/ci/run_all_checks.sh",
            "tools/README.md",
            "documents/tools/README.md",
        ),
    ),
    "github_workflow_pr_flow": (
        "tools/ci/check_github_workflows.py",
        (
            "tools/ci/run_all_checks.sh",
            "agents/workflows/agent-canon-pr-workflow.md",
        ),
    ),
    "container_config": (
        "tools/ci/container_config.py",
        (
            "tools/ci/run_all_checks.sh",
            "agents/skills/environment-maintenance.md",
            "documents/coding-conventions-project.md",
        ),
    ),
    "surface_manifest": (
        "tools/agent_tools/surface_manifest.py",
        (
            "tools/sync_agent_canon.sh",
            "documents/SHARED_RUNTIME_SURFACES.md",
        ),
    ),
}

SKILL_ROUTING_PROMPTS = (
    ".agents/skills/agent-orchestration/SKILL.md",
    "agents/skills/agent-orchestration.md",
    "agents/TASK_WORKFLOWS.md",
)

SKILL_ROUTING_MARKERS = (
    "$agent-orchestration",
    "$codex-task-workflow",
    "$subagent-bootstrap",
    "task-shape skill",
    "check_convention_compliance.py",
)

WORKFLOW_GATE_MARKER = "check_convention_compliance.py"
WORKFLOW_GATE_COMMAND_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?.*\brun\s+`?python3\s+"
    r"tools/agent_tools/check_convention_compliance\.py`?"
)
WORKFLOW_GATE_FORBIDDEN_RE = re.compile(
    r"(?is)(?:do\s+not|don't|never|skip|omit)\s+(?:\S+\s+){0,6}?"
    r"check_convention_compliance\.py|check_convention_compliance\.py"
    r"(?:\S+\s+){0,6}?(?:optional|not\s+required)"
)
CLOSEOUT_PROHIBITION_MARKERS = (
    "Close-Out Prohibitions",
    "user-facing completion",
    "repo_wide_static_analysis_complete",
    "repo_wide_dependency_tools_complete",
)
PROMPT_EVAL_MARKERS = (
    "check_convention_compliance",
    "CONVENTION-WORKFLOW",
    "CONVENTION-SKILL",
)
SURFACE_MANIFEST_FILES = (
    "documents/SHARED_RUNTIME_SURFACES.md",
    "documents/shared-runtime-surfaces.toml",
    "documents/agent-canon-parent-repo-latest-checklist.md",
    "tools/sync_agent_canon.sh",
    "tools/agent_tools/surface_manifest.py",
)
SURFACE_POLICY_MARKERS = (
    "documents/shared-runtime-surfaces.toml",
    "owner class",
    ".codex/hooks.json",
    ".codex/hooks",
    "documents/README.md",
    "documents/template-bootstrap.md",
    "memory/USER_PREFERENCES.md",
    "tests/agent_tools/",
)
SURFACE_MANIFEST_MARKERS = (
    'mode = "regular"',
    'owner = "template-or-derived-repo"',
    'path = "goal.md"',
    '"documents/README.md"',
    '"documents/template-bootstrap.md"',
    '".codex/hooks.json"',
    '"tests/agent_tools/test_check_convention_compliance.py"',
)
SURFACE_SYNC_MARKERS = (
    "surface_manifest.py",
    "build_regular_specs",
    "regular_path",
)
NORMATIVE_RE = re.compile(
    r"(?m)^\s*[-*]\s+.*(?:禁止|必須|しなければなりません|してはいけません|"
    r"must|must not|required|forbidden)",
    flags=re.IGNORECASE,
)
PROHIBITION_RE = re.compile(
    r"(?m)^\s*[-*]\s+.*(?:を禁止|禁止します|してはいけません|must not|forbidden)",
    flags=re.IGNORECASE,
)
VERIFICATION_RE = re.compile(
    r"(?:tools/|check_|pyright|pytest|ruff|make ci|make agent-checks|"
    r"CONVENTION_COMPLIANCE|EVAL_STATUS|AGENT_EVALUATION_STATUS)"
)
PROHIBITION_SECTION_RE = re.compile(r"(?m)^#{2,6}\s+(?:.*禁止事項|Close-Out Prohibitions)")


@dataclass(frozen=True)
class Finding:
    """One convention compliance wiring issue."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return f"CONVENTION_COMPLIANCE_FINDING={self.check}:{self.path}:{self.detail}"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify convention compliance tool, workflow, and skill prompt wiring."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def read_text(root: Path, relative_path: str) -> str:
    """Read a UTF-8 text file relative to root."""
    return (root / relative_path).read_text(encoding="utf-8")


def check_required_files(root: Path, paths: Sequence[str], check: str) -> list[Finding]:
    """Return findings for missing required files."""
    findings: list[Finding] = []
    for path in paths:
        if not (root / path).is_file():
            findings.append(Finding(check, path, "missing-required-file"))
    return findings


def check_tool_gates(root: Path) -> list[Finding]:
    """Verify each mechanical convention gate exists and is referenced."""
    findings: list[Finding] = []
    for gate_name, (tool_path, references) in TOOL_GATES.items():
        if not (root / tool_path).is_file():
            findings.append(
                Finding("tool_gate", tool_path, f"{gate_name}:missing-tool")
            )
            continue
        for reference in references:
            reference_path = root / reference
            if not reference_path.is_file():
                findings.append(
                    Finding("tool_gate", reference, f"{gate_name}:missing-reference")
                )
                continue
            tool_stem = Path(tool_path).stem
            if tool_stem not in reference_path.read_text(encoding="utf-8"):
                findings.append(
                    Finding(
                        "tool_gate",
                        reference,
                        f"{gate_name}:missing-{Path(tool_path).name}",
                    )
                )
    return findings


def workflow_docs(root: Path) -> list[Path]:
    """Return all workflow prompt documents."""
    return sorted((root / "agents" / "workflows").glob("*.md"))


def check_workflow_hooks(root: Path) -> list[Finding]:
    """Verify every workflow prompt calls the convention verifier."""
    findings: list[Finding] = []
    for path in workflow_docs(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if WORKFLOW_GATE_MARKER not in text:
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "missing-convention-compliance-gate",
                )
            )
            continue
        if not WORKFLOW_GATE_COMMAND_RE.search(text):
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "missing-positive-convention-compliance-command",
                )
            )
        if WORKFLOW_GATE_FORBIDDEN_RE.search(text):
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "forbidden-convention-compliance-suppression",
                )
            )
    return findings


def check_skill_routing(root: Path) -> list[Finding]:
    """Verify skill-routing prompts include required routing and verifier markers."""
    findings = check_required_files(root, SKILL_ROUTING_PROMPTS, "skill_routing")
    for path in SKILL_ROUTING_PROMPTS:
        full_path = root / path
        if not full_path.is_file():
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in SKILL_ROUTING_MARKERS:
            if marker not in text:
                findings.append(
                    Finding("skill_routing", path, f"missing-marker:{marker}")
                )
    return findings


def check_closeout_prohibitions(root: Path) -> list[Finding]:
    """Verify workflow prohibition sources remain wired into the canonical workflow."""
    path = "agents/canonical/CODEX_WORKFLOW.md"
    findings = check_required_files(root, (path,), "workflow_prohibitions")
    if findings:
        return findings
    text = read_text(root, path)
    for marker in CLOSEOUT_PROHIBITION_MARKERS:
        if marker not in text:
            findings.append(
                Finding("workflow_prohibitions", path, f"missing-marker:{marker}")
            )
    return findings


def check_prompt_eval_wiring(root: Path) -> list[Finding]:
    """Verify prompt evals cover convention verifier and skill-call routing."""
    path = "agents/evals/skill_workflow_prompt_eval.toml"
    findings = check_required_files(root, (path,), "prompt_eval")
    if findings:
        return findings
    text = read_text(root, path)
    for marker in PROMPT_EVAL_MARKERS:
        if marker not in text:
            findings.append(Finding("prompt_eval", path, f"missing-marker:{marker}"))
    return findings


def check_surface_manifest_wiring(root: Path) -> list[Finding]:
    """Verify shared surface ownership has one manifest-backed route."""
    findings = check_required_files(root, SURFACE_MANIFEST_FILES, "surface_manifest")
    readable_files = {
        path: (root / path).read_text(encoding="utf-8")
        for path in SURFACE_MANIFEST_FILES
        if (root / path).is_file()
    }
    policy_text = readable_files.get("documents/SHARED_RUNTIME_SURFACES.md", "")
    for marker in SURFACE_POLICY_MARKERS:
        if marker not in policy_text:
            findings.append(
                Finding("surface_manifest", "documents/SHARED_RUNTIME_SURFACES.md", f"missing-marker:{marker}")
            )
    manifest_text = readable_files.get("documents/shared-runtime-surfaces.toml", "")
    for marker in SURFACE_MANIFEST_MARKERS:
        if marker not in manifest_text:
            findings.append(
                Finding("surface_manifest", "documents/shared-runtime-surfaces.toml", f"missing-marker:{marker}")
            )
    sync_text = readable_files.get("tools/sync_agent_canon.sh", "")
    for marker in SURFACE_SYNC_MARKERS:
        if marker not in sync_text:
            findings.append(
                Finding("surface_manifest", "tools/sync_agent_canon.sh", f"missing-marker:{marker}")
            )
    return findings


def check_convention_assertions(root: Path) -> list[Finding]:
    """Verify convention documents expose checkable normative assertions."""
    findings: list[Finding] = []
    for path in CONVENTION_SOURCES:
        full_path = root / path
        if not full_path.is_file():
            continue
        text = full_path.read_text(encoding="utf-8")
        normative_lines = NORMATIVE_RE.findall(text)
        if normative_lines and not VERIFICATION_RE.search(text):
            findings.append(
                Finding(
                    "convention_assertions",
                    path,
                    "normative-lines-without-verification-route",
                )
            )
        if PROHIBITION_RE.search(text) and not PROHIBITION_SECTION_RE.search(text):
            findings.append(
                Finding(
                    "convention_assertions",
                    path,
                    "prohibition-lines-without-prohibition-section",
                )
            )
    return findings


def run_checks(root: Path) -> list[Finding]:
    """Run all convention compliance wiring checks."""
    findings: list[Finding] = []
    findings.extend(
        check_required_files(root, CONVENTION_SOURCES, "convention_sources")
    )
    findings.extend(check_tool_gates(root))
    findings.extend(check_workflow_hooks(root))
    findings.extend(check_skill_routing(root))
    findings.extend(check_closeout_prohibitions(root))
    findings.extend(check_prompt_eval_wiring(root))
    findings.extend(check_surface_manifest_wiring(root))
    findings.extend(check_convention_assertions(root))
    return sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )


def render_json(root: Path, findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    workflows = [path.relative_to(root).as_posix() for path in workflow_docs(root)]
    payload = {
        "status": "pass" if not findings else "fail",
        "findings": [asdict(finding) for finding in findings],
        "convention_sources": len(CONVENTION_SOURCES),
        "tool_gates": len(TOOL_GATES),
        "workflow_prompts": len(workflows),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run convention compliance checks."""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = run_checks(root)

    if args.format == "json":
        print(render_json(root, findings))
    else:
        for finding in findings:
            print(finding.render())
        print(f"CONVENTION_COMPLIANCE_SOURCES={len(CONVENTION_SOURCES)}")
        print(f"CONVENTION_COMPLIANCE_TOOL_GATES={len(TOOL_GATES)}")
        print(f"CONVENTION_COMPLIANCE_WORKFLOWS={len(workflow_docs(root))}")
        print(f"CONVENTION_COMPLIANCE_FINDINGS={len(findings)}")
        print(f"CONVENTION_COMPLIANCE={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
