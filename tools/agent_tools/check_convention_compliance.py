#!/usr/bin/env python3
# @dependency-start
# responsibility Verifies repository convention compliance wiring and workflow gates.
# upstream design ../../documents/conventions/README.md convention index
# upstream design ../../agents/canonical/CODEX_WORKFLOW.md closeout prohibition policy
# upstream design ../../agents/templates/closeout_gate.md closeout gate policy
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml prompt eval gate
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared surface ownership policy
# upstream design ../../documents/shared-runtime-surfaces.toml shared surface manifest
# upstream design ../../documents/codex-configuration-reference.md Codex hook severity policy
# upstream design ../../.codex/README.md Codex runtime hook behavior summary
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream implementation ./tool_drift.py validates tool/convention drift
# upstream implementation ./check_skill_frontmatter.py validates runtime skill frontmatter
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
    "notebook_quality": (
        "tools/validation/notebook_quality.py",
        (
            "tools/ci/run_all_checks.sh",
            "tools/README.md",
            "documents/tools/README.md",
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
            "evidence/agent-evals/skill_workflow_prompt_eval.toml",
            "agents/workflows/adaptive-improvement-workflow.md",
        ),
    ),
    "behavior_eval": (
        "tools/agent_tools/evaluate_agent_run.py",
        ("evidence/agent-evals/agent_behavior_eval.toml", "agents/templates/closeout_gate.md"),
    ),
    "skill_frontmatter": (
        "tools/agent_tools/check_skill_frontmatter.py",
        (
            "tools/ci/run_all_checks.sh",
            "tools/ci/check_github_workflows.py",
        ),
    ),
    "convention_compliance": (
        "tools/agent_tools/check_convention_compliance.py",
        ("tools/ci/run_all_checks.sh", "evidence/agent-evals/skill_workflow_prompt_eval.toml"),
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
    "import_responsibility": (
        "tools/agent_tools/import_responsibility.py",
        (
            "tools/ci/run_all_checks.sh",
            "documents/responsibility-scope-management.md",
            "documents/coding-conventions-python.md",
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
    "runtime_profile_inventory": (
        "tools/agent_tools/check_runtime_profile_inventory.py",
        ("tools/ci/run_docs_checks.sh",),
    ),
}

AGENT_CANON_PR_WORKFLOW_PATH = "agents/workflows/agent-canon-pr-workflow.md"
AGENT_CANON_PUSH_REMOTE_MARKERS = (
    "remote_verified=yes",
    "tools/agent_tools/github_publish.py",
    "gh repo view",
    "git remote get-url origin",
    "NEXT_ACTION=fix_origin_remote_or_pass_the_correct_--repo_without_fallback_push",
    "literal URL push is not a standard route",
    "hardcoded repository name",
)

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
    ".devcontainer/",
    "documents/README.md",
    "documents/template-bootstrap.md",
    "documents/github-first-module-and-devcontainer-policy.md",
    "memory/USER_PREFERENCES.md",
    "tests/agent_tools/",
    "Root `tools/` is a symlink view",
    "vendor/agent-canon/tools/",
    "Project-local automation must stay in project-owned paths",
)
SURFACE_MANIFEST_MARKERS = (
    'mode = "standalone_only"',
    'owner = "agent-canon-standalone"',
    'path = "goal.md"',
    '"documents/README.md"',
    '"documents/template-bootstrap.md"',
    '".devcontainer"',
    '"documents/github-first-module-and-devcontainer-policy.md"',
    '".codex/hooks.json"',
    '"tests/agent_tools/test_check_convention_compliance.py"',
)
SURFACE_SYNC_MARKERS = (
    "surface_manifest.py",
    "build_regular_specs",
    "regular_path",
)
HOOK_GUARDRAIL_POLICY_MARKERS = {
    ".codex/hooks/hook_dispatcher.py": (
        "CRITICAL_BLOCKING_CHILD_HOOKS",
        "STRICT_BLOCKS_ENV",
        "STRICT_FAILURES_ENV",
        "downgraded_block_payload",
        "failure_warning_payload",
        "direct_rg_context_guard.py",
    ),
    ".codex/hooks/direct_rg_context_guard.py": (
        "DIRECT_RG_CONTEXT_RISK=warn",
        "rg -l",
        "--max-count",
        ".agent-canon/log-archive",
        "reports",
        "*.jsonl",
    ),
    ".codex/README.md": (
        "dispatcher は fail-open",
        "AGENT_CANON_HOOK_STRICT_BLOCKS",
        "systemMessage",
        "hookSpecificOutput.additionalContext",
    ),
    "documents/codex-configuration-reference.md": (
        "Hook Severity Policy",
        "fail-open",
        "CRITICAL_BLOCKING_CHILD_HOOKS",
        "warning/evidence",
    ),
    "ROOT_AGENTS.md": (
        "Mechanical Guardrail Policy",
        "原則 block しません",
        "hook 設定の退避や無効化ではなく",
        "strict block mode",
    ),
}
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
FORWARDER_WARNING_REQUIRED_MARKER = "LEGACY_FORWARDER_WARNING_REQUIRED"
FORWARDER_WARNING_MARKERS = (
    "FORWARDER_CALLER",
    "FORWARDER_ACTION",
    "FORWARDER_SEVERITY=fix-now",
    "FORWARDER_PROMPT",
    "caller_process_chain",
)
AGENTS_FORWARDER_POLICY_MARKERS = (
    "*_FORWARDER=deprecated",
    "*_FORWARDER_SEVERITY=fix-now",
    "caller chain",
    "canonical command",
)


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


def readable_path(root: Path, relative_path: str) -> Path | None:
    """Return the readable root path, falling back to vendored AgentCanon docs."""
    candidates = (root / relative_path, root / "vendor" / "agent-canon" / relative_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_text(root: Path, relative_path: str) -> str:
    """Read a UTF-8 text file relative to root."""
    resolved = readable_path(root, relative_path)
    if resolved is None:
        return (root / relative_path).read_text(encoding="utf-8")
    return resolved.read_text(encoding="utf-8")


def check_required_files(root: Path, paths: Sequence[str], check: str) -> list[Finding]:
    """Return findings for missing required files."""
    findings: list[Finding] = []
    for path in paths:
        if readable_path(root, path) is None:
            findings.append(Finding(check, path, "missing-required-file"))
    return findings


def check_tool_gates(root: Path) -> list[Finding]:
    """Verify each mechanical convention gate exists and is referenced."""
    findings: list[Finding] = []
    for gate_name, (tool_path, references) in TOOL_GATES.items():
        if readable_path(root, tool_path) is None:
            findings.append(
                Finding("tool_gate", tool_path, f"{gate_name}:missing-tool")
            )
            continue
        for reference in references:
            reference_path = readable_path(root, reference)
            if reference_path is None:
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


def check_agentcanon_push_remote_guard(root: Path) -> list[Finding]:
    """Verify AgentCanon PR workflow documents remote verification before push."""
    path = AGENT_CANON_PR_WORKFLOW_PATH
    findings = check_required_files(root, (path,), "agentcanon_push_remote_guard")
    if findings:
        return findings
    text = read_text(root, path)
    for marker in AGENT_CANON_PUSH_REMOTE_MARKERS:
        if marker not in text:
            findings.append(
                Finding(
                    "agentcanon_push_remote_guard",
                    path,
                    f"missing-marker:{marker}",
                )
            )
    return findings


def check_prompt_eval_wiring(root: Path) -> list[Finding]:
    """Verify prompt evals cover convention verifier and skill-call routing."""
    path = "evidence/agent-evals/skill_workflow_prompt_eval.toml"
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
        path: resolved.read_text(encoding="utf-8")
        for path in SURFACE_MANIFEST_FILES
        if (resolved := readable_path(root, path)) is not None
    }
    policy_text = readable_files.get("documents/SHARED_RUNTIME_SURFACES.md", "")
    for marker in SURFACE_POLICY_MARKERS:
        if marker not in policy_text:
            findings.append(
                Finding(
                    "surface_manifest",
                    "documents/SHARED_RUNTIME_SURFACES.md",
                    f"missing-marker:{marker}",
                )
            )
    manifest_text = readable_files.get("documents/shared-runtime-surfaces.toml", "")
    for marker in SURFACE_MANIFEST_MARKERS:
        if marker not in manifest_text:
            findings.append(
                Finding(
                    "surface_manifest",
                    "documents/shared-runtime-surfaces.toml",
                    f"missing-marker:{marker}",
                )
            )
    sync_text = readable_files.get("tools/sync_agent_canon.sh", "")
    for marker in SURFACE_SYNC_MARKERS:
        if marker not in sync_text:
            findings.append(
                Finding("surface_manifest", "tools/sync_agent_canon.sh", f"missing-marker:{marker}")
            )
    return findings


def check_hook_guardrail_policy(root: Path) -> list[Finding]:
    """Verify hook severity stays centralized and fail-open by default."""
    findings: list[Finding] = []
    for path, markers in HOOK_GUARDRAIL_POLICY_MARKERS.items():
        resolved = readable_path(root, path)
        if resolved is None:
            findings.append(
                Finding("hook_guardrail_policy", path, "missing-required-file")
            )
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "hook_guardrail_policy",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_convention_assertions(root: Path) -> list[Finding]:
    """Verify convention documents expose checkable normative assertions."""
    findings: list[Finding] = []
    for path in CONVENTION_SOURCES:
        full_path = readable_path(root, path)
        if full_path is None:
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


def check_legacy_forwarder_warning_policy(root: Path) -> list[Finding]:
    """Verify legacy forwarders emit caller/action migration warnings."""
    findings: list[Finding] = []
    tools_root = root / "tools"
    if tools_root.is_dir():
        for path in sorted(
            candidate
            for pattern in ("*.py", "*.sh")
            for candidate in tools_root.rglob(pattern)
            if candidate.is_file()
        ):
            text = path.read_text(encoding="utf-8", errors="replace")
            if FORWARDER_WARNING_REQUIRED_MARKER not in text:
                continue
            relative = path.relative_to(root).as_posix()
            for marker in FORWARDER_WARNING_MARKERS:
                if marker not in text:
                    findings.append(
                        Finding(
                            "legacy_forwarder_warning",
                            relative,
                            f"missing-marker:{marker}",
                        )
                    )

    policy_text = "\n".join(
        resolved.read_text(encoding="utf-8", errors="replace")
        for path in ("ROOT_AGENTS.md", "AGENTS.md")
        if (resolved := readable_path(root, path)) is not None
    )
    if policy_text:
        for marker in AGENTS_FORWARDER_POLICY_MARKERS:
            if marker not in policy_text:
                findings.append(
                    Finding(
                        "legacy_forwarder_warning",
                        "AGENTS.md",
                        f"missing-policy-marker:{marker}",
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
    findings.extend(check_agentcanon_push_remote_guard(root))
    findings.extend(check_prompt_eval_wiring(root))
    findings.extend(check_surface_manifest_wiring(root))
    findings.extend(check_hook_guardrail_policy(root))
    findings.extend(check_convention_assertions(root))
    findings.extend(check_legacy_forwarder_warning_policy(root))
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
