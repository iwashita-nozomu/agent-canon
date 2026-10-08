#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Verifies native convention-tool wiring and retained structured policies.
# upstream design ../../../../documents/conventions/README.md convention index
# upstream design ../../../../agents/canonical/CODEX_COMPLETION.md selected validation evidence policy
# upstream design ../../../../agents/skills/codex-task-workflow.md static/read validation route
# upstream design ../../../../documents/codex/codex-configuration-reference.md Codex hook severity policy
# upstream design ../../../../documents/conventions/coding-conventions-house-style.md source definition ordering
# upstream design ../../../../.codex/README.md Codex runtime hook behavior summary
# upstream design ../../../catalog.yaml structured tool catalog
# upstream implementation ../tools/tool_drift.py validates tool/convention drift
# upstream implementation ./convention_compliance_contracts.toml declares marker contracts
# upstream implementation ../skills/check_skill_frontmatter.py validates runtime skill frontmatter
# downstream implementation ../../ci/runners/run_all_checks.sh runs convention compliance gate
# downstream implementation ../../../../tests/agent_tools/test_check_convention_compliance.py tests verifier  # noqa: E501
# @dependency-end
"""Verify that convention, workflow, and skill-routing gates are wired."""

from __future__ import annotations

import argparse
import json
import re

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

MARKER_CONTRACTS_PATH = Path(
    "tools/validation/semantic/convention/convention_compliance_contracts.toml"
)


def load_marker_contracts() -> dict[str, dict[str, tuple[str, ...]]]:
    """Load declarative marker contracts from the checked-in manifest."""
    manifest = Path(__file__).resolve().parents[4] / MARKER_CONTRACTS_PATH
    payload = tomllib.loads(manifest.read_text(encoding="utf-8"))
    contracts: dict[str, dict[str, tuple[str, ...]]] = {}
    for contract in payload.get("contracts", []):
        contract_id = contract["id"]
        surfaces: dict[str, tuple[str, ...]] = {}
        for surface in contract.get("surfaces", []):
            path = surface["path"]
            if path.startswith(".codex/personal/skills/") and path.endswith(
                "/SKILL.md"
            ):
                raise ValueError(
                    "generated skill shims cannot own convention marker contracts: "
                    f"{path}"
                )
            surfaces[path] = tuple(surface.get("markers", []))
        contracts[contract_id] = surfaces
    return contracts


DECLARATIVE_MARKER_CONTRACTS = load_marker_contracts()

CONVENTION_SOURCES = (
    "documents/conventions/README.md",
    "documents/conventions/common/01_principles.md",
    "documents/rule/naming.md",
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
    "documents/conventions/coding-conventions-python.md",
    "documents/conventions/coding-conventions-cpp.md",
    "documents/conventions/coding-conventions-project.md",
    "documents/conventions/coding-conventions-house-style.md",
    "documents/conventions/coding-conventions-testing.md",
    "documents/conventions/coding-conventions-reviews.md",
    "documents/conventions/coding-conventions-experiments.md",
    "documents/conventions/coding-conventions-logging.md",
    "documents/design/algorithm-implementation-boundary.md",
    "documents/conventions/object-oriented-design.md",
    "documents/conventions/REVIEW_PROCESS.md",
    "agents/canonical/CODEX_WORKFLOW.md",
    "agents/canonical/CODEX_IMPLEMENTATION.md",
    "agents/canonical/CODEX_BOOTSTRAP.md",
    "agents/canonical/CODEX_COMPLETION.md",
    "agents/canonical/CODEX_INTAKE.md",
    "agents/canonical/CODEX_ROUTING.md",
)

TOOL_CATALOG_PATH = "tools/catalog.yaml"

# This table records execution surfaces and their owners.  It deliberately does
# not require every reader-facing document to repeat a tool filename: catalog,
# workflow, and runtime-profile checkers own those contracts independently.
TOOL_GATES = {
    "dependency_review": (
        "tools/analysis/dependencies/run_repo_dependency_review.sh",
        (TOOL_CATALOG_PATH,),
    ),
    "code_dependency_scan": (
        "tools/analysis/dependencies/scan_code_dependencies.sh",
        (TOOL_CATALOG_PATH,),
    ),
    "hardcoded_numbers": (
        "tools/validation/semantic/code/check_hardcoded_numbers.py",
        (TOOL_CATALOG_PATH,),
    ),
    "static_any": (
        "tools/validation/semantic/code/check_static_any.py",
        (TOOL_CATALOG_PATH,),
    ),
    "log_helper_names": (
        "tools/validation/semantic/logging/check_log_helper_names.py",
        (TOOL_CATALOG_PATH,),
    ),
    "notebook_quality": (
        "tools/validation/notebooks/notebook_quality.py",
        (TOOL_CATALOG_PATH,),
    ),
    "oop_readability": (
        "tools/validation/code/oop/python/readability.py",
        (TOOL_CATALOG_PATH,),
    ),
    "oop_cpp_readability": (
        "tools/validation/code/oop/cpp/readability.py",
        (TOOL_CATALOG_PATH,),
    ),
    "behavior_eval": (
        "eval/producers/evaluate_agent_run.py",
        (TOOL_CATALOG_PATH,),
    ),
    "skill_frontmatter": (
        "tools/validation/semantic/skills/check_skill_frontmatter.py",
        (TOOL_CATALOG_PATH,),
    ),
    "convention_compliance": (
        "tools/validation/semantic/convention/check_convention_compliance.py",
        (TOOL_CATALOG_PATH,),
    ),
    "tool_catalog": (
        "tools/runtime/manifest/tool_catalog.py",
        (TOOL_CATALOG_PATH,),
    ),
    "tool_convention_drift": (
        "tools/validation/semantic/tools/tool_drift.py",
        (TOOL_CATALOG_PATH,),
    ),
    "import_responsibility": (
        "tools/analysis/code/import_responsibility.py",
        (TOOL_CATALOG_PATH,),
    ),
    "github_workflow_pr_flow": (
        "tools/validation/ci/checks/check_github_workflows.py",
        (TOOL_CATALOG_PATH,),
    ),
    "bootstrap_container_runtime": (
        "bootstrap.sh",
        ("documents/runtime/bootstrap-runtime.md",),
    ),
}

STATIC_READ_VALIDATION_POLICY_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "static_read_validation_policy"
]

WORKFLOW_GATE_MARKER = "check_convention_compliance.py"
WORKFLOW_GATE_CONSUMERS = ("tools/validation/ci/checks/check_agent_canon_pr.sh",)
WORKFLOW_GATE_COMMAND_RE = re.compile(
    r'(?m)^\s*python3\s+"\$\{WORKSPACE_ROOT\}/tools/validation/semantic/convention/check_convention_compliance\.py"\s+'
    r'--root\s+"\$\{WORKSPACE_ROOT\}"\s+--format\s+json$'
)
WORKFLOW_GATE_FORBIDDEN_RE = re.compile(
    r"(?is)(?:do\s+not|don't|never|skip|omit)\s+(?:\S+\s+){0,6}?"
    r"check_convention_compliance\.py|check_convention_compliance\.py"
    r"(?:\S+\s+){0,6}?(?:optional|not\s+required)"
)
VALIDATION_FAILURE_RESPONSE_MARKERS = {
    "documents/operations/TROUBLESHOOTING.md": (
        "validation test/check failure",
        "failing_contract",
        "cause_classification",
        "intent_preservation",
        "documents/runtime/runtime-profiles-and-check-matrix.json",
        "documents/runtime/runtime-profiles-and-check-matrix.md",
    ),
    "documents/conventions/coding-conventions-testing.md": (
        "Validation test/check",
        "failing_contract",
        "cause_classification",
        "intent_preservation",
        "documents/runtime/runtime-profiles-and-check-matrix.json",
        "documents/runtime/runtime-profiles-and-check-matrix.md",
    ),
}
VALIDATION_FAILURE_RESPONSE_STALE_OWNER_PHRASES = (
    "runtime-profiles-and-check-matrix.md`、`agents/canonical/CODEX_WORKFLOW.md",
    "agents/canonical/CODEX_SUBAGENTS.md`、`documents/conventions/REVIEW_PROCESS.md",
)
MATHEMATICAL_NECESSITY_MARKERS = {
    "documents/conventions/common/05_docs.md": (
        "mathematical necessity gate",
        "Judgment / Mathematical Role / Necessity Evidence / Owner / Validation Route",
        "necessary-and-sufficient condition",
        "non-contractual mathematical judgment",
    ),
    "documents/conventions/coding-conventions-testing.md": (
        "mathematical necessity gate",
        "Numerical Trigger",
        "Non-Numerical Alternative",
        "checker-owned property",
    ),
    "agents/skills/computational-optimization.md": (
        "mathematical necessity gate",
        "iteration map",
        "stopping scalar",
        "failure semantics",
    ),
    "agents/skills/formal-proof-workflow.md": (
        "mathematical necessity gate",
        "program contract",
        "theorem surface",
        "proof obligation",
    ),
}
REVIEW_ISSUE_ROUTING_MARKERS = {
    "documents/conventions/REVIEW_PROCESS.md": (
        "Review Finding Issue Routing",
        "issue_route",
        "github_issue",
        "issue_sync.py",
        "private packet",
    ),
}
SOURCE_FILE_DEFINITION_ORDER_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "source_file_definition_order"
]
HOOK_GUARDRAIL_POLICY_MARKERS = {
    ".codex/hooks/hook_dispatcher.py": (
        "HOOK_EVENT_CONTRACTS",
        "HookEventContract",
        "ACTIVE_HOOK_HANDLERS",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "hook_safety",
        "validate_projection_bytes",
        "record_hook_invocation",
        "HookLogContext",
        "RETIRED_CHILD_TOMBSTONES",
        "MOVED_SOURCE_ABSENCES",
    ),
    "tools/runtime/authority/hook_safety.py": (
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY",
        "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY",
        "branch_block_payload",
        "command_sha256",
        "operation",
        "same-segment",
        "DESTRUCTIVE_GIT_GUARD=block",
        "BRANCH_WORKTREE_CREATION_GUARD=block",
    ),
    ".codex/README.md": (
        "active events",
        "active/inactive",
        "legacy `Stop`",
        "fail-open",
        "retired child tombstones",
        "bounded",
        "redacted",
    ),
    "documents/codex/codex-configuration-reference.md": (
        "Hook Severity Policy",
        "fail-open",
        "warning/evidence",
        "secret",
        "Active dispatcher failures",
    ),
}
OWNER_MAP_ENTRYPOINT_TABLE_ROWS = {
    "ROOT_AGENTS.md": (
        (
            "## Runtime Owner Map",
            (
                (
                    "workflow family, spawn budget, role topology",
                    "agents/task_catalog.yaml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "task bootstrap and CLI entrypoints",
                    "agents/canonical/CLI_ENTRYPOINTS.md",
                    "bootstrap_agent_run.py",
                ),
                (
                    "subagent lifecycle, same-role instances, wave ledger",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    "workflow_monitor.py",
                ),
                (
                    "role behavior and stage conditions",
                    ".codex/agents/*.toml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "skill routing and public skill surface",
                    "agents/skills/catalog.yaml",
                    "tools/agent/orchestration/route.py --prompt",
                ),
                (
                    "report and closeout structure",
                    "tools/runtime/lifecycle/task_close.py",
                    "closeout gate",
                ),
                (
                    "entrypoint responsibility grammar",
                    "documents/design/entrypoint-owner-map.md",
                    "check_entrypoint_owner_map.py",
                ),
                (
                    "bootstrap, image, and resident container",
                    "bootstrap.sh",
                    "bootstrap/container profile",
                ),
                (
                    "Python, Rust, and LSP tool dispatch",
                    "tools/runtime/dispatch/tool_dispatch.py",
                    "tool dispatch tests",
                ),
                (
                    "skill and agent installation",
                    "tools/agent/skills/skill_shim_materializer.py",
                    "skill materializer check",
                ),
                (
                    "source-side-effect boundary",
                    "documents/runtime/bootstrap-runtime.md",
                    "external runtime and source-unchanged checks",
                ),
                (
                    "eval archive",
                    "tools/runtime/archive/runtime_log_archive_git.py",
                    "archive readback",
                ),
                (
                    "source update",
                    "agents/skills/agent-canon-update.md",
                    "qualified PR and merged-main readback",
                ),
            ),
        ),
    ),
    "AGENTS.md": (
        (
            "## Runtime Owner Map",
            (
                (
                    "root runtime entrypoint",
                    "bootstrap.sh",
                    "bash bootstrap.sh --help",
                ),
                (
                    "workflow family, spawn budget, role topology",
                    "agents/task_catalog.yaml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "public skill registry",
                    "agents/skills/catalog.yaml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "AgentCanon update transaction",
                    "documents/agent-canon/agent-canon-update-route.md",
                    "update_lifecycle_contract.py",
                ),
            ),
        ),
    ),
    "agents/TASK_WORKFLOWS.md": (
        (
            "## Workflow Contract Owners",
            (
                (
                    "workflow family and spawn budget",
                    "agents/task_catalog.yaml",
                ),
                (
                    "role topology and same-role instance schema",
                    "agents/task_catalog.yaml",
                ),
                (
                    "default specialists and review packs",
                    "agents/task_catalog.yaml",
                    "agents/agents_config.json",
                ),
                (
                    "run bundle, declared workflow / skills / review, and dynamic wave ledger",
                    "bootstrap_agent_run.py",
                    "workflow_monitor.py",
                ),
                (
                    "skill selection",
                    "agents/skills/catalog.yaml",
                    "python3 tools/agent/orchestration/route.py --prompt",
                ),
                (
                    "implementation stage gate",
                    "agents/skills/codex-task-workflow.md",
                ),
                (
                    "active design packet schema",
                    "agents/COMMUNICATION_PROTOCOL.md",
                    "agents/agents_config.json#artifacts.active_design_packet",
                ),
                (
                    "closeout authority",
                    "task_close.py",
                    "report_artifact_checks.py",
                ),
            ),
        ),
    ),
}
OWNER_MAP_ENTRYPOINT_MARKERS = {
    path: tuple(
        dict.fromkeys(
            marker
            for heading, rows in section_rows
            for row in ((heading,), *rows)
            for marker in row
        )
    )
    for path, section_rows in OWNER_MAP_ENTRYPOINT_TABLE_ROWS.items()
}
NORMATIVE_RE = re.compile(
    r"(?m)^\s*[-*]\s+.*(?:禁止|必須|しなければなりません|してはいけません|"
    r"must|must not|required|forbidden)",
    flags=re.IGNORECASE,
)
VERIFICATION_RE = re.compile(
    r"(?:tools/|check_|pyright|pytest|ruff|make ci|make agent-checks|"
    r"CONVENTION_COMPLIANCE|EVAL_STATUS|AGENT_EVALUATION_STATUS)"
)
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
ENTRYPOINT_DELEGATED_SECTION_HEADINGS = (
    "## Subagent Usage",
    "## Plan Mode",
    "## Read Packets",
    "## Execution Priorities",
    "## Mechanical Guardrail Policy",
    "## Default Search And Routing",
    "## Runtime Profiles And Risk",
    "## Experiment And Log Diagnostics",
    "## AgentCanon Submodule Update Flow",
    "## PR Mutation Authority",
    "## Required Before Implementation",
)
ENTRYPOINT_DELEGATION_PATHS = ("ROOT_AGENTS.md", "AGENTS.md")


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
    """Return the readable root or vendored AgentCanon document path."""
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


def markdown_section_lines(text: str, heading: str) -> list[str] | None:
    """Return lines under a Markdown heading until the next peer heading."""
    lines = text.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == heading),
        None,
    )
    if heading_index is None:
        return None
    heading_level = len(heading) - len(heading.lstrip("#"))
    section: list[str] = []
    for line in lines[heading_index + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            next_level = len(stripped) - len(stripped.lstrip("#"))
            if next_level <= heading_level:
                break
        section.append(line)
    return section


def markdown_table_rows(lines: Sequence[str]) -> list[str]:
    """Return Markdown table data rows from a section."""
    rows: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(stripped)
    return rows


def same_resolved_file(left: Path, right: Path) -> bool:
    """Return whether two paths point to the same filesystem entry."""
    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return False


def owner_map_entrypoint_rows(
    root: Path, path: str
) -> Sequence[tuple[str, Sequence[tuple[str, ...]]]]:
    """Return owner-map rows for the entrypoint role active at ``path``."""
    agents_path = readable_path(root, "AGENTS.md")
    root_agents_path = readable_path(root, "ROOT_AGENTS.md")
    if (
        path == "AGENTS.md"
        and agents_path is not None
        and root_agents_path is not None
        and same_resolved_file(agents_path, root_agents_path)
    ):
        return OWNER_MAP_ENTRYPOINT_TABLE_ROWS["ROOT_AGENTS.md"]
    return OWNER_MAP_ENTRYPOINT_TABLE_ROWS[path]


def duplicate_root_view_entrypoint(root: Path, path: str) -> bool:
    """Return whether ``path`` is already covered by the root entrypoint view."""
    agents_path = readable_path(root, "AGENTS.md")
    root_agents_path = readable_path(root, "ROOT_AGENTS.md")
    return (
        path == "AGENTS.md"
        and agents_path is not None
        and root_agents_path is not None
        and same_resolved_file(agents_path, root_agents_path)
    )


def check_required_files(root: Path, paths: Sequence[str], check: str) -> list[Finding]:
    """Return findings for missing required files."""
    findings: list[Finding] = []
    for path in paths:
        if readable_path(root, path) is None:
            findings.append(Finding(check, path, "missing-required-file"))
    return findings


def check_tool_gates(root: Path) -> list[Finding]:
    """Verify each gate has an executable surface and one owning registry."""
    findings: list[Finding] = []
    for gate_name, (tool_path, references) in TOOL_GATES.items():
        if readable_path(root, tool_path) is None:
            findings.append(
                Finding("tool_gate", tool_path, f"{gate_name}:missing-tool")
            )
            continue
        for owner in references:
            owner_path = readable_path(root, owner)
            if owner_path is None:
                findings.append(
                    Finding("tool_gate", owner, f"{gate_name}:missing-owner-surface")
                )
                continue

            # The structured catalog is the owner for cataloged tools. Check
            # the path entry itself, not an incidental filename mention in a
            # README, workflow, or skill. Catalog shape and metadata remain
            # the responsibility of tool_catalog.py.
            if owner == TOOL_CATALOG_PATH:
                catalog_text = owner_path.read_text(encoding="utf-8")
                path_re = re.compile(
                    rf"(?m)^\s*path:\s*['\"]?{re.escape(tool_path)}['\"]?\s*(?:#.*)?$"
                )
                if not path_re.search(catalog_text):
                    findings.append(
                        Finding(
                            "tool_gate",
                            owner,
                            f"{gate_name}:missing-catalog-owner",
                        )
                    )
    return findings


def check_workflow_hooks(root: Path) -> list[Finding]:
    """Verify the canonical source gate owns convention verification."""
    findings = check_required_files(root, WORKFLOW_GATE_CONSUMERS, "workflow_hook")
    for relative in WORKFLOW_GATE_CONSUMERS:
        path = readable_path(root, relative)
        if path is None:
            continue
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


def collect_marker_contract_findings(
    root: Path, check: str, required_markers: dict[str, tuple[str, ...]]
) -> list[Finding]:
    """Verify a manifest-backed marker contract against repository files."""
    paths = tuple(required_markers)
    findings = check_required_files(root, paths, check)
    for path, markers in required_markers.items():
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(Finding(check, path, f"missing-marker:{marker}"))
    return findings


def check_validation_failure_response_owner_propagation(root: Path) -> list[Finding]:
    """Reject stale projection docs as validation-failure taxonomy owners."""
    findings: list[Finding] = []
    for path in VALIDATION_FAILURE_RESPONSE_MARKERS:
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for phrase in VALIDATION_FAILURE_RESPONSE_STALE_OWNER_PHRASES:
            if phrase in text:
                findings.append(
                    Finding(
                        "validation_failure_response",
                        path,
                        f"stale-taxonomy-owner:{phrase}",
                    )
                )
    return findings


def check_mathematical_necessity_gate(root: Path) -> list[Finding]:
    """Verify mathematical judgments stay wired to necessity evidence."""
    paths = tuple(MATHEMATICAL_NECESSITY_MARKERS)
    findings = check_required_files(root, paths, "mathematical_necessity_gate")
    for path, markers in MATHEMATICAL_NECESSITY_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "mathematical_necessity_gate",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_review_issue_routing(root: Path) -> list[Finding]:
    """Verify review findings stay connected to durable issue routes."""
    paths = tuple(REVIEW_ISSUE_ROUTING_MARKERS)
    findings = check_required_files(root, paths, "review_issue_routing")
    for path, markers in REVIEW_ISSUE_ROUTING_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "review_issue_routing",
                        path,
                        f"missing-marker:{marker}",
                    )
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


def check_owner_map_entrypoints(root: Path) -> list[Finding]:
    """Verify thin entrypoint docs keep required owner-map anchors."""
    findings = check_required_files(
        root,
        tuple(OWNER_MAP_ENTRYPOINT_TABLE_ROWS),
        "owner_map_entrypoints",
    )
    for path in OWNER_MAP_ENTRYPOINT_TABLE_ROWS:
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        if duplicate_root_view_entrypoint(root, path):
            continue
        section_rows = owner_map_entrypoint_rows(root, path)
        text = resolved.read_text(encoding="utf-8")
        for heading, expected_rows in section_rows:
            section = markdown_section_lines(text, heading)
            if section is None:
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-heading:{heading}",
                    )
                )
                continue
            table_rows = markdown_table_rows(section)
            if not table_rows:
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-owner-table:{heading}",
                    )
                )
                continue
            for row_markers in expected_rows:
                if any(
                    all(marker in row for marker in row_markers) for row in table_rows
                ):
                    continue
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-owner-row:{row_markers[0]}",
                    )
                )
    return findings


def check_entrypoint_delegated_sections(root: Path) -> list[Finding]:
    """Verify runtime entrypoints delegate detailed procedures to owner surfaces."""
    findings: list[Finding] = []
    for path in ENTRYPOINT_DELEGATION_PATHS:
        resolved = readable_path(root, path)
        if resolved is None:
            findings.append(
                Finding("entrypoint_delegation", path, "missing-required-file")
            )
            continue
        if duplicate_root_view_entrypoint(root, path):
            continue
        text = resolved.read_text(encoding="utf-8")
        for heading in ENTRYPOINT_DELEGATED_SECTION_HEADINGS:
            if markdown_section_lines(text, heading) is not None:
                findings.append(
                    Finding(
                        "entrypoint_delegation",
                        path,
                        f"delegated-section:{heading}",
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
        for path in (
            "documents/codex/codex-configuration-reference.md",
            ".codex/README.md",
        )
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
    findings.extend(
        collect_marker_contract_findings(
            root,
            "static_read_validation_policy",
            STATIC_READ_VALIDATION_POLICY_MARKERS,
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "validation_failure_response",
            VALIDATION_FAILURE_RESPONSE_MARKERS,
        )
    )
    findings.extend(check_validation_failure_response_owner_propagation(root))
    findings.extend(check_mathematical_necessity_gate(root))
    findings.extend(check_review_issue_routing(root))
    findings.extend(
        collect_marker_contract_findings(
            root,
            "source_file_definition_order",
            SOURCE_FILE_DEFINITION_ORDER_MARKERS,
        )
    )
    findings.extend(check_hook_guardrail_policy(root))
    findings.extend(check_convention_assertions(root))
    findings.extend(check_legacy_forwarder_warning_policy(root))
    return sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )


def render_json(root: Path, findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    workflows = [
        path
        for path in WORKFLOW_GATE_CONSUMERS
        if readable_path(root, path) is not None
    ]
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
        print(f"CONVENTION_COMPLIANCE_WORKFLOWS={len(WORKFLOW_GATE_CONSUMERS)}")
        print(f"CONVENTION_COMPLIANCE_FINDINGS={len(findings)}")
        print(f"CONVENTION_COMPLIANCE={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
