#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Predicts tool and hook rejection gates before edits are handed to agents.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md defines handoff packet fields
# upstream design ../../agents/skills/codex-task-workflow.md owns implementation preflight routing
# upstream design ../../.agents/skills/codex-task-workflow/SKILL.md exposes implementation preflight routing
# upstream design ../../agents/skills/owner-bounded-routing.md owns owner-bounded preflight routing
# upstream design ../../.agents/skills/owner-bounded-routing/SKILL.md exposes owner-bounded preflight routing
# upstream design ../../agents/skills/experiment-lifecycle.md owns experiment execution lifecycle routing
# upstream design ../../.agents/skills/experiment-lifecycle/SKILL.md exposes experiment execution lifecycle routing
# upstream design ../../documents/experiment-registry.md defines managed experiment registry contract
# upstream design ../../tools/README.md documents tool entrypoints
# upstream design ../../documents/tools/README.md documents user-facing tool routes
# upstream implementation ./log_surface_inventory.py checks hook/tool/skill log-surface drift
# upstream implementation ../../.codex/hooks/cause_investigation_guard.py blocks code edits without cause evidence
# upstream implementation ../../.codex/hooks/oop_readability_guard.py blocks OOP readability failures
# upstream implementation ../../.codex/hooks/library_implementation_guard.py blocks library implementation rewrites
# upstream implementation ../../.codex/hooks/helper_first_guard.py blocks helper-first implementation drift
# upstream implementation ../../.codex/hooks/style_checker_guard.py blocks selected style checker failures
# upstream implementation ../../.codex/hooks/helper_inventory_guard.py blocks helper inventory findings
# upstream implementation ./responsibility_scope.py validates responsibility owner scopes
# downstream implementation ../../tools/agent_tools/agent_team.py injects preflight protocol into team manifests
# downstream implementation ../../tests/agent_tools/test_tool_rejection_preflight.py validates predicted gate routing
# @dependency-end
"""Predict edit-time tool/hook rejection gates from planned paths."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from responsibility_scope import (
    Scope,
    ScopeReport,
    scope_covers,
)
from responsibility_scope import (
    validate as validate_responsibility_scope,
)

PYTHON_SUFFIXES = {".py"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
NOTEBOOK_SUFFIXES = {".ipynb"}
MARKDOWN_SUFFIXES = {".md"}
TEXT_SUFFIXES = {
    ".bash",
    ".cfg",
    ".css",
    ".h",
    ".hpp",
    ".html",
    ".c",
    ".cc",
    ".cpp",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".zsh",
}
CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
HOOK_SURFACE_PREFIXES = (
    ".codex/hooks/",
)
HOOK_CONFIG_PATHS = frozenset({".codex/hooks.json"})
AGENT_CANON_HOOK_SURFACE_PREFIXES = (
    "vendor/agent-canon/.codex/hooks/",
)
AGENT_CANON_HOOK_CONFIG_PATHS = frozenset(
    {"vendor/agent-canon/.codex/hooks.json"}
)
STRICT_SCHEMA_JSON_PATHS = HOOK_CONFIG_PATHS | AGENT_CANON_HOOK_CONFIG_PATHS
SKILL_SURFACE_PREFIXES = (
    ".agents/skills/",
    "agents/skills/",
)
TOOL_SURFACE_PREFIXES = (
    "tools/",
)
LOG_SURFACE_PREFIXES = (
    HOOK_SURFACE_PREFIXES
    + AGENT_CANON_HOOK_SURFACE_PREFIXES
    + SKILL_SURFACE_PREFIXES
    + TOOL_SURFACE_PREFIXES
)
GITHUB_SURFACE_PREFIXES = (".github/workflows/", ".github/actions/")
AGENT_PROTOCOL_PATHS = frozenset(
    {
        "agents/COMMUNICATION_PROTOCOL.md",
        "agents/canonical/CODEX_WORKFLOW.md",
        "agents/canonical/CODEX_SUBAGENTS.md",
        "evidence/agent-evals/README.md",
        "agents/templates/workflow_monitoring.md",
        "agents/workflows/agent-learning-workflow.md",
    }
)
TOOL_CATALOG_PATHS = frozenset({"tools/catalog.yaml"})
EXPERIMENT_EXECUTION_SURFACE_PATHS = frozenset(
    {
        ".agents/skills/experiment-lifecycle/SKILL.md",
        "agents/skills/experiment-lifecycle.md",
        "agents/workflows/experiment-workflow.md",
        "documents/experiment-registry.md",
        "documents/experiment_runner.md",
        "experiments/registry.toml",
        "tools/ci/check_experiment_registry.py",
        "tools/experiments/publish_result_branch.py",
        "tools/experiments/registry_lib.py",
        "tools/experiments/run_managed_experiment.py",
    }
)
LIBRARY_SURFACE_PREFIXES = (
    "vendor/",
    "third_party/",
    "third-party/",
    "external/",
    "node_modules/",
    ".venv/",
)
AGENT_CANON_SUBMODULE_PREFIX = "vendor/agent-canon"
AGENT_CANON_TOOL_SOURCE_ROOT = f"{AGENT_CANON_SUBMODULE_PREFIX}/tools"
RESPONSIBILITY_SCOPE_COMMAND = (
    "python3 tools/agent_tools/responsibility_scope.py --root . --format json"
)


@dataclass(frozen=True, order=True)
class PredictedGate:
    """One likely rejection gate for a planned edit."""

    path: str
    gate: str
    command: str
    handoff: str


@dataclass(frozen=True)
class GateTemplate:
    """Reusable gate template with path interpolation."""

    gate: str
    command_template: str
    handoff: str

    def for_path(self, path: str) -> PredictedGate:
        """Materialize this gate for one planned path."""
        command = self.command_template.format(path=path)
        handoff = self.handoff.strip()
        return PredictedGate(
            path=path,
            gate=self.gate,
            command=command,
            handoff=handoff,
        )


CAUSE_INVESTIGATION_GATE_TEMPLATES = (
    GateTemplate(
        gate="cause_investigation_guard",
        command_template=(
            "printf '%s' "
            "'{{\"hookEventName\":\"PreToolUse\",\"tool_name\":\"apply_patch\","
            "\"tool_input\":{{\"patch\":\"*** Begin Patch\\n*** Update File: {path}\\n"
            "*** End Patch\\n\"}}}}' "
            "| python3 .codex/hooks/cause_investigation_guard.py"
        ),
        handoff=(
            "record Observation, Hypothesis or Root Cause, Expected Fix Surface "
            "or Selected Surface, and Validation Before Edit or Support Evidence "
            "before code edits; for validation failures include failing_contract, "
            "observation_level, cause_classification, intent_preservation, and "
            "evidence for same-intent repair or escalation before write-capable repair"
        ),
    ),
)


PYTHON_GATE_TEMPLATES = (
    GateTemplate(
        gate="import_responsibility",
        command_template=(
            "python3 tools/agent_tools/import_responsibility.py --root . {path}"
        ),
        handoff=(
            "include unused-import and responsibility-scope import boundary risk "
            "before implementation edits"
        ),
    ),
    GateTemplate(
        gate="module_boundary_guard",
        command_template=(
            "printf '%s' "
            "'{{\"hookEventName\":\"PostToolUse\",\"tool_name\":\"apply_patch\"}}' "
            "| python3 .codex/hooks/module_boundary_guard.py"
        ),
        handoff=(
            "include module boundary evidence before changing Python module "
            "internals or public surface"
        ),
    ),
    GateTemplate(
        gate="helper_first_guard",
        command_template=(
            "printf '%s' "
            "'{{\"hookEventName\":\"PostToolUse\",\"tool_name\":\"apply_patch\"}}' "
            "| python3 .codex/hooks/helper_first_guard.py"
        ),
        handoff=(
            "include ownership, module boundary, issue, docs, or test evidence "
            "before adding helper-like functions"
        ),
    ),
    GateTemplate(
        gate="oop_readability_guard",
        command_template=(
            "python3 tools/oop/python/readability.py --root . --min-score 95 {path}"
        ),
        handoff=(
            "include OOP readability risk and repair plan before implementation edits"
        ),
    ),
    GateTemplate(
        gate="solid_evidence_gate",
        command_template=(
            "python3 tools/agent_tools/check_solid_evidence.py --root . {path} "
            "--evidence <oop-readability-report>"
        ),
        handoff=(
            "attach a path-covered OOP readability JSON or Markdown report for "
            "SOLID-sensitive Python boundaries before closeout"
        ),
    ),
    GateTemplate(
        gate="helper_inventory_guard",
        command_template=(
            "python3 tools/agent_tools/helper_function_inventory.py "
            "--root . --changed --baseline-ref HEAD"
        ),
        handoff=(
            "avoid ad hoc helper creation or state why existing helper surfaces "
            "cannot be reused"
        ),
    ),
)
LIBRARY_GATE_TEMPLATES = (
    GateTemplate(
        gate="library_implementation_guard",
        command_template=(
            "printf '%s' "
            "'{{\"hookEventName\":\"PostToolUse\",\"tool_name\":\"apply_patch\"}}' "
            "| python3 .codex/hooks/library_implementation_guard.py"
        ),
        handoff=(
            "do not rewrite vendored or installed library internals; use wrapper, "
            "adapter, fork/upstream patch, or manifest-backed vendor import"
        ),
    ),
)
CPP_GATE_TEMPLATES = (
    GateTemplate(
        gate="oop_readability_guard",
        command_template=(
            "python3 tools/oop/cpp/readability.py --root . --min-score 95 {path}"
        ),
        handoff="include C/C++ OOP readability risk before edits",
    ),
)
STYLE_CHECK_GATE_TEMPLATES = (
    GateTemplate(
        gate="style_checker_guard",
        command_template=(
            "printf '%s' "
            "'{{\"hookEventName\":\"PostToolUse\",\"tool_name\":\"apply_patch\"}}' "
            "| python3 .codex/hooks/style_checker_guard.py"
        ),
        handoff=(
            "include selected style checker families and unchecked changed-file "
            "coverage before continuing"
        ),
    ),
)
DEPENDENCY_GATE_TEMPLATES = (
    GateTemplate(
        gate="dependency_review",
        command_template=(
            "bash tools/agent_tools/run_repo_dependency_review.sh "
            "--root . --fail-missing --list-changed-dependencies"
        ),
        handoff=(
            "include dependency header and related edit-scope plan for created "
            "or edited text files"
        ),
    ),
)
STRICT_SCHEMA_DEPENDENCY_GATE_TEMPLATES = (
    GateTemplate(
        gate="dependency_review",
        command_template=(
            "bash tools/agent_tools/run_repo_dependency_review.sh "
            "--root . --fail-missing --list-changed-dependencies"
        ),
        handoff=(
            "preserve the strict JSON schema with top-level hooks only; record "
            "dependency context in owner docs, tests, or review artifacts"
        ),
    ),
)
LOG_SURFACE_GATE_TEMPLATES = (
    GateTemplate(
        gate="log_surface_inventory_guard",
        command_template=(
            "python3 tools/agent_tools/log_surface_inventory.py --root . "
            "--check --baseline documents/log-surface-inventory.json"
        ),
        handoff=(
            "state whether emitted hook/tool/skill fields changed and regenerate "
            "the inventory baseline in the same branch"
        ),
    ),
)
GITHUB_GATE_TEMPLATES = (
    GateTemplate(
        gate="github_workflow_check",
        command_template="python3 tools/ci/check_github_workflows.py",
        handoff="include workflow checkout, permissions, and artifact evidence",
    ),
)
HOOK_RUNTIME_GATE_TEMPLATES = (
    GateTemplate(
        gate="codex_hook_runtime_alignment",
        command_template=(
            "python3 tools/agent_tools/check_agent_runtime_alignment.py && "
            "python3 -m pytest tests/agent_tools/test_codex_hooks.py -q"
        ),
        handoff=(
            "include hook wiring, quiet-pass behavior, and runtime alignment evidence"
        ),
    ),
)
SKILL_MIRROR_GATE_TEMPLATES: tuple[GateTemplate, ...] = ()
AGENT_PROTOCOL_GATE_TEMPLATES = (
    GateTemplate(
        gate="agent_protocol_convention",
        command_template="python3 tools/agent_tools/check_convention_compliance.py",
        handoff=(
            "include whether workflow, skill-routing, and hook/tool feedback "
            "protocol checks still pass"
        ),
    ),
)
TOOL_CATALOG_GATE_TEMPLATES = (
    GateTemplate(
        gate="tool_catalog",
        command_template="python3 tools/agent_tools/tool_catalog.py",
        handoff=(
            "include catalog/docs/tests wiring for changed canonical tool surfaces"
        ),
    ),
)
AGENT_CANON_NEW_TOOL_SOURCE_ROUTE_GATE_TEMPLATES = (
    GateTemplate(
        gate="agentcanon_new_tool_source_route",
        command_template=(
            "git -C vendor/agent-canon status --short --branch && "
            "git submodule status vendor/agent-canon"
        ),
        handoff=(
            "treat this planned path as new AgentCanon-owned tool source: add it "
            "on an AgentCanon branch/PR under vendor/agent-canon, then update "
            "the parent submodule pin; do not create a parent-local tools implementation"
        ),
    ),
)
AGENT_CANON_LOG_SURFACE_GATE_TEMPLATES = (
    GateTemplate(
        gate="log_surface_inventory_guard",
        command_template=(
            "cd vendor/agent-canon && "
            "python3 tools/agent_tools/log_surface_inventory.py --root . "
            "--check --baseline documents/log-surface-inventory.json"
        ),
        handoff=(
            "validate AgentCanon source log-surface inventory from "
            "vendor/agent-canon when a parent root tools/ view resolves there"
        ),
    ),
)
AGENT_CANON_TOOL_CATALOG_GATE_TEMPLATES = (
    GateTemplate(
        gate="tool_catalog",
        command_template=(
            "cd vendor/agent-canon && python3 tools/agent_tools/tool_catalog.py"
        ),
        handoff=(
            "validate AgentCanon tool catalog from vendor/agent-canon for "
            "shared tool source changes"
        ),
    ),
)
EXPERIMENT_EXECUTION_SURFACE_GATE_TEMPLATES = (
    GateTemplate(
        gate="experiment_execution_surface_guard",
        command_template=(
            "if [ -e experiments/registry.toml ]; then "
            "python3 tools/ci/check_experiment_registry.py; "
            "else echo EXPERIMENT_REGISTRY_CHECK=skipped_no_project_registry; "
            "fi && "
            "python3 -m pytest tests/tools/test_run_managed_experiment.py -q"
        ),
        handoff=(
            "route planned edits through $experiment-lifecycle and $test-design; "
            "preserve the managed runner, registry checker, registry contract, "
            "and result-branch publication contract with lightweight registry and "
            "runner validation evidence"
        ),
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Predict tool/hook rejection gates that should be run or explained "
            "before a write-capable subagent edits planned paths."
        )
    )
    parser.add_argument("paths", nargs="*", help="Planned edit paths.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Use git changed paths when explicit paths are not supplied.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def changed_paths(root: Path) -> tuple[str, ...]:
    """Return changed tracked and untracked paths."""
    commands = (
        ["git", "-C", str(root), "diff", "--name-only", "--diff-filter=ACMRT", "HEAD"],
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        paths.update(git_output_lines(command))
    return tuple(sorted(paths))


def git_output_lines(command: list[str]) -> tuple[str, ...]:
    """Return output lines for one read-only git command."""
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def planned_paths(root: Path, raw_paths: list[str], *, use_changed: bool) -> tuple[str, ...]:
    """Resolve planned paths relative to the workspace root."""
    if raw_paths:
        return tuple(dict.fromkeys(normalize_path(root, path) for path in raw_paths))
    if use_changed:
        return changed_paths(root)
    return ()


def normalize_path(root: Path, raw_path: str) -> str:
    """Return one path relative to root when possible."""
    candidate = (root / raw_path).resolve()
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return raw_path


def predict_gates(root: Path, paths: tuple[str, ...]) -> tuple[PredictedGate, ...]:
    """Predict rejection gates for planned paths."""
    scope_report = validate_responsibility_scope(root, "responsibility-scope.toml")
    gates: set[PredictedGate] = set()
    for path in paths:
        gates.update(path_gates(root, path, scope_report))
    return tuple(sorted(gates))


def path_gates(root: Path, path: str, scope_report: ScopeReport) -> tuple[PredictedGate, ...]:
    """Return predicted gates for one path."""
    suffix = Path(path).suffix
    templates: list[GateTemplate] = []
    gates = [render_responsibility_scope_gate(path, scope_report)]
    if suffix in CODE_SUFFIXES:
        templates.extend(CAUSE_INVESTIGATION_GATE_TEMPLATES)
    if suffix in PYTHON_SUFFIXES:
        templates.extend(PYTHON_GATE_TEMPLATES)
    if suffix in CPP_SUFFIXES:
        templates.extend(CPP_GATE_TEMPLATES)
    if suffix in PYTHON_SUFFIXES | CPP_SUFFIXES | NOTEBOOK_SUFFIXES | MARKDOWN_SUFFIXES:
        templates.extend(STYLE_CHECK_GATE_TEMPLATES)
    if suffix in TEXT_SUFFIXES:
        templates.extend(dependency_gate_templates(path))
    if hook_runtime_surface_path(path):
        templates.extend(HOOK_RUNTIME_GATE_TEMPLATES)
    if path.startswith(LOG_SURFACE_PREFIXES):
        templates.extend(LOG_SURFACE_GATE_TEMPLATES)
    if agent_canon_new_tool_source_path(root, path):
        templates.extend(AGENT_CANON_NEW_TOOL_SOURCE_ROUTE_GATE_TEMPLATES)
        templates.extend(AGENT_CANON_LOG_SURFACE_GATE_TEMPLATES)
    if path.startswith(SKILL_SURFACE_PREFIXES):
        templates.extend(SKILL_MIRROR_GATE_TEMPLATES)
    if path.startswith(GITHUB_SURFACE_PREFIXES):
        templates.extend(GITHUB_GATE_TEMPLATES)
    if path in AGENT_PROTOCOL_PATHS:
        templates.extend(AGENT_PROTOCOL_GATE_TEMPLATES)
    if experiment_execution_surface_path(path):
        templates.extend(EXPERIMENT_EXECUTION_SURFACE_GATE_TEMPLATES)
    if path in TOOL_CATALOG_PATHS or path.startswith(TOOL_SURFACE_PREFIXES):
        templates.extend(TOOL_CATALOG_GATE_TEMPLATES)
    if agent_canon_tool_source_path(path):
        templates.extend(AGENT_CANON_TOOL_CATALOG_GATE_TEMPLATES)
    if library_surface_path(path):
        templates.extend(LIBRARY_GATE_TEMPLATES)
    gates.extend(template.for_path(path) for template in templates)
    return tuple(gates)


def render_responsibility_scope_gate(path: str, report: ScopeReport) -> PredictedGate:
    """Return the owner-scope gate for one planned path."""
    if report.findings:
        handoff = (
            "repair responsibility-scope.toml or run from the repository owner "
            f"root before editing; findings:{len(report.findings)}"
        )
    else:
        scopes = tuple(scope for scope in report.scopes if scope_covers(scope, path))
        if len(scopes) == 1:
            handoff = " | ".join(render_scope_handoff(scope) for scope in scopes)
        elif scopes:
            handoff = (
                "resolve planned path responsibility overlap before editing; "
                + " | ".join(render_scope_handoff(scope) for scope in scopes)
            )
        else:
            handoff = (
                "assign this planned path to exactly one responsibility-scope.toml "
                "scope or move the edit to an existing owner surface before editing"
            )
    return PredictedGate(
        path=path,
        gate="responsibility_scope",
        command=RESPONSIBILITY_SCOPE_COMMAND,
        handoff=handoff,
    )


def render_scope_handoff(scope: Scope) -> str:
    """Render one responsibility scope as compact handoff text."""
    protecting_tools = ",".join(scope.protecting_tools)
    return (
        f"scope:{scope.scope_id} owner:{scope.owner} class:{scope.scope_class} "
        f"protecting_tools:{protecting_tools}"
    )


def agent_canon_tool_source_path(path: str) -> bool:
    """Return whether a parent-root path resolves to AgentCanon tool source."""
    return path == AGENT_CANON_TOOL_SOURCE_ROOT or path.startswith(
        AGENT_CANON_TOOL_SOURCE_ROOT + "/"
    )


def agent_canon_new_tool_source_path(root: Path, path: str) -> bool:
    """Return whether a planned path would create a new AgentCanon tool source."""
    if not agent_canon_tool_source_path(path):
        return False
    if (root / path).exists():
        return False
    source_relative = path.removeprefix(AGENT_CANON_SUBMODULE_PREFIX + "/")
    return not (root / source_relative).exists()


def dependency_gate_templates(path: str) -> tuple[GateTemplate, ...]:
    """Return dependency review templates for one planned path."""
    if path in STRICT_SCHEMA_JSON_PATHS:
        return STRICT_SCHEMA_DEPENDENCY_GATE_TEMPLATES
    return DEPENDENCY_GATE_TEMPLATES


def hook_runtime_surface_path(path: str) -> bool:
    """Return whether a planned path belongs to Codex hook runtime wiring."""
    return (
        path in HOOK_CONFIG_PATHS
        or path in AGENT_CANON_HOOK_CONFIG_PATHS
        or path.startswith(HOOK_SURFACE_PREFIXES)
        or path.startswith(AGENT_CANON_HOOK_SURFACE_PREFIXES)
    )


def library_surface_path(path: str) -> bool:
    """Return whether a planned path belongs to protected library surfaces."""
    if path == AGENT_CANON_SUBMODULE_PREFIX or path.startswith(AGENT_CANON_SUBMODULE_PREFIX + "/"):
        return False
    return path.startswith(LIBRARY_SURFACE_PREFIXES)


def agent_canon_logical_path(path: str) -> str:
    """Return the AgentCanon logical path for parent-submodule paths."""
    prefix = AGENT_CANON_SUBMODULE_PREFIX + "/"
    if path.startswith(prefix):
        return path.removeprefix(prefix)
    return path


def experiment_execution_surface_path(path: str) -> bool:
    """Return whether a path owns managed experiment execution semantics."""
    return agent_canon_logical_path(path) in EXPERIMENT_EXECUTION_SURFACE_PATHS


def text_output(gates: tuple[PredictedGate, ...]) -> str:
    """Render stable text output."""
    status = "warn" if gates else "pass"
    lines = [
        f"TOOL_REJECTION_PREFLIGHT={status}",
        f"TOOL_REJECTION_PREDICTED_GATES={len(gates)}",
    ]
    for gate in gates:
        lines.append(
            "TOOL_REJECTION_PREDICTED_GATE="
            f"path:{gate.path}\tgate:{gate.gate}\tcommand:{gate.command}\thandoff:{gate.handoff}"
        )
    return "\n".join(lines)


def json_output(gates: tuple[PredictedGate, ...]) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "warn" if gates else "pass",
            "predicted_gate_count": len(gates),
            "predicted_gates": [asdict(gate) for gate in gates],
        },
        indent=2,
        sort_keys=True,
    )


def main() -> int:
    """Run the preflight CLI."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    paths = planned_paths(root, list(args.paths), use_changed=args.changed)
    gates = predict_gates(root, paths)
    if args.format == "json":
        print(json_output(gates))
    else:
        print(text_output(gates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
