#!/usr/bin/env python3
# @dependency-start
# responsibility Provides short task routing helper for tool and skill selection.
# upstream design ../../documents/tool-skill-routing-refactor.md short tool and skill naming policy
# upstream design ../../agents/skills/task-routing.md task routing skill contract
# downstream design ../../documents/tools/route.md reader-facing route tool documentation
# downstream implementation ../../tests/agent_tools/test_route.py tests route output and aliases
# @dependency-end
"""Select short AgentCanon tool and skill routes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

ROUTE_NAME = "task-routing"
SKILL_NAME = "task-routing"
TOOL_NAME = "route.py"
RISK_VALUES = ("routine", "focused", "profile", "shared", "large")
FORMAT_VALUES = ("text", "json", "markdown")

AreaData = tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]

AREA_DATA: tuple[AreaData, ...] = (
    (
        "surface",
        "runtime surfaces",
        "Decide which AgentCanon root views are active, optional, or hidden.",
        "classify_runtime_surface",
        ("python3 tools/agent_tools/route.py --area surface",),
        ("profile_surface_resolver.py", "runtime-surface-minimize", "tool_profile_visibility.py"),
    ),
    (
        "profile",
        "optional profiles",
        "Select optional Docker, C++, experiment, GitHub, or memory profiles.",
        "select_active_profiles",
        ("python3 tools/agent_tools/route.py --area profile",),
        (
            "optional_profile_matrix.py",
            "profile-selection",
            "language_surface_detector.py",
            "language-profile",
        ),
    ),
    (
        "checks",
        "check plan",
        "Choose the smallest validation set for the changed paths and risk.",
        "run_selected_checks",
        ("make check-matrix",),
        (
            "workflow_step_router.py",
            "workflow-lite-routing",
            "validation_min_set.py",
            "validation-profile",
            "static_check_matrix.py",
            "static-check-lite",
            "github_check_matrix.py",
            "github-check-lite",
        ),
    ),
    (
        "env",
        "environment",
        "Classify host, container, devcontainer, and server environment needs.",
        "classify_environment_profile",
        ("python3 tools/ci/container_config.py",),
        (
            "environment_profile_detect.py",
            "environment-profile",
            "container_need_detector.py",
            "container-on-demand",
            "python_env_decider.py",
            "python-env-lite",
        ),
    ),
    (
        "read",
        "read order",
        "Return the shortest required document packet for the task.",
        "read_minimal_packet",
        ("python3 tools/agent_tools/route.py --area read",),
        ("read_order_compactor.py", "onboarding-lite"),
    ),
    (
        "remote",
        "remote policy",
        "Keep GitHub-first remote and compatibility mirror rules separate.",
        "route_remote_policy",
        ("bash tools/update_agent_canon.sh plan",),
        ("remote_policy_router.py", "remote-policy-cleanup", "pr_update_route.py", "pr-route-minimize"),
    ),
    (
        "canon",
        "AgentCanon update",
        "Route submodule update, local branch, and parent TODO state.",
        "route_agentcanon_update",
        ("bash tools/update_agent_canon.sh latest",),
        (
            "submodule_state_router.py",
            "submodule-routing",
            "agent_canon_update_planner.py",
            "canon-update-lite",
        ),
    ),
    (
        "mcp",
        "MCP",
        "Check MCP inventory without turning optional surfaces into default work.",
        "check_mcp_inventory_when_required",
        ("python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server",),
        ("mcp_optional_preflight.py", "mcp-profile"),
    ),
    (
        "goal",
        "goal loop",
        "Limit goal machinery to explicit goal-driven tasks.",
        "route_goal_loop",
        ("python3 tools/agent_tools/goal_loop.py status",),
        ("goal_contract_router.py", "goal-lite"),
    ),
    (
        "runtime",
        "runtime capability",
        "Hide Codex, Claude, Copilot, or CLI examples when unavailable.",
        "probe_runtime_capability",
        ("python3 tools/agent_tools/route.py --area runtime",),
        ("runtime_capability_probe.py", "runtime-capability-routing"),
    ),
    (
        "tokens",
        "token budget",
        "Pick light or full workflow gates from token budget and task risk.",
        "select_token_budget_gates",
        ("python3 tools/agent_tools/route.py --area tokens",),
        ("token_budget_gate.py", "token-lite"),
    ),
    (
        "skills",
        "skill map",
        "Collapse duplicate workflow and skill entrypoints into one selection.",
        "select_public_skills",
        ("python3 tools/agent_tools/route.py --area skills",),
        ("skill_workflow_mapper.py", "routing-single-source", "skill_dedupe.py", "skill-minimizer"),
    ),
    (
        "agents",
        "agent mode",
        "Choose parent-direct, read-only scout, or staged agents by risk.",
        "select_agent_mode",
        ("python3 tools/agent_tools/route.py --area agents",),
        ("multi_agent_mode_selector.py", "agent-mode", "subagent_role_budget.py", "subagent-budget"),
    ),
    (
        "closeout",
        "closeout",
        "Choose lightweight or full closeout evidence by risk.",
        "select_closeout_gate",
        ("python3 tools/agent_tools/task_close.py --run-id <run-id>",),
        (
            "closeout_profile_gate.py",
            "closeout-lite",
            "artifact_bundle_generator.py",
            "artifact-lite",
        ),
    ),
    (
        "deps",
        "dependency review",
        "Select changed-file or full dependency manifest checks.",
        "select_dependency_review",
        (
            "python3 tools/agent_tools/check_dependency_headers.py --changed",
            "bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing",
        ),
        (
            "dependency_manifest_scope.py",
            "dependency-manifest-lite",
            "dependency_tool_aggregator.py",
            "dependency-review-one-shot",
        ),
    ),
    (
        "conventions",
        "conventions",
        "Route convention subchecks without making every rule a prompt clause.",
        "run_convention_subchecks",
        ("python3 tools/agent_tools/check_convention_compliance.py",),
        (
            "convention_subcheck_router.py",
            "convention-gate-lite",
            "policy_risk_classifier.py",
            "policy-exception-routing",
        ),
    ),
    (
        "docs",
        "document canon",
        "Find canonical docs and route mirror/generated/stale docs away from edits.",
        "route_document_canon",
        ("python3 tools/agent_tools/noncanonical_document_inventory.py",),
        ("canon_doc_router.py", "doc-canon-flex", "docs_check_router.py", "docs-lite"),
    ),
    (
        "search",
        "coordinated search",
        "Find candidate tools, documents, code, and dependency context from a purpose string.",
        "run_coordinated_search",
        (
            "agent-canon local-llm search --purpose \"<goal>\"",
            "agent-canon local-llm build-index --surface tools --surface documents",
        ),
        (
            "vector_search.py",
            "tool-search",
            "llm-search",
            "semantic-search",
            "search-to-edit-scope",
            "dependency-expanded-search",
        ),
    ),
    (
        "logs",
        "logs and evals",
        "Route hook, skill, eval, and result evidence without overwriting logs.",
        "route_result_evidence",
        ("python3 tools/agent_tools/generate_agent_improvement_guide.py",),
        (
            "log_retention_decider.py",
            "log-retention-lite",
            "eval_trigger_router.py",
            "eval-on-demand",
            "evidence_compactor.py",
            "runtime-evidence-lite",
        ),
    ),
    (
        "tools",
        "tool catalog",
        "Keep tool lists short while preserving catalog and docs checks.",
        "check_tool_catalog",
        ("python3 tools/agent_tools/tool_catalog.py",),
        ("tool_catalog_summarizer.py", "tool-selection", "retired_tool_guard.py", "legacy-tool-cleanup"),
    ),
)


@dataclass(frozen=True)
class RouteArea:
    """One short routing area."""

    key: str
    label: str
    purpose: str
    next_action: str
    commands: tuple[str, ...]
    aliases: tuple[str, ...]

    def evidence_token(self, risk: str, changed_paths: Sequence[str]) -> str:
        """Return a compact evidence token."""
        changed = ",".join(changed_paths) if changed_paths else "none"
        return f"area={self.key};risk={risk};changed={changed}"


@dataclass(frozen=True)
class RouteDecision:
    """Rendered routing decision."""

    route: str
    area: str
    label: str
    tool: str
    skill: str
    next_action: str
    commands: tuple[str, ...]
    skip_reason: str
    evidence: str


@dataclass(frozen=True)
class NameResolution:
    """Compatibility resolution for one proposed tool or skill name."""

    name: str
    status: str
    canonical_area: str
    canonical_tool: str
    canonical_skill: str


def build_default_areas() -> tuple[RouteArea, ...]:
    """Build the default AgentCanon route areas."""
    return tuple(RouteArea(*row) for row in AREA_DATA)


class RouteCatalog:
    """Catalog of short routing areas and long-name aliases."""

    def __init__(self, areas: Sequence[RouteArea]) -> None:
        self._areas = {area.key: area for area in areas}
        self._aliases = self._build_aliases(areas)

    @classmethod
    def default(cls) -> "RouteCatalog":
        """Build the default catalog."""
        return cls(build_default_areas())

    def areas(self) -> tuple[RouteArea, ...]:
        """Return all areas in display order."""
        return tuple(self._areas.values())

    def area(self, key: str) -> RouteArea | None:
        """Return an area by key."""
        return self._areas.get(normalize_name(key))

    def resolve_name(self, name: str) -> NameResolution:
        """Resolve one proposed long tool or skill name to a short route."""
        normalized = normalize_name(name)
        area_key = self._aliases.get(normalized, normalized if normalized in self._areas else "")
        if not area_key:
            return NameResolution(name, "unknown", "", "", "")
        return NameResolution(
            name,
            "alias" if normalized != area_key else "canonical",
            area_key,
            f"{TOOL_NAME} --area {area_key}",
            SKILL_NAME,
        )

    @staticmethod
    def _build_aliases(areas: Sequence[RouteArea]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for area in areas:
            aliases[normalize_name(area.key)] = area.key
            for alias in area.aliases:
                aliases[normalize_name(alias)] = area.key
        return aliases


def normalize_name(value: str) -> str:
    """Normalize a tool or skill name for alias lookup."""
    name = value.strip().removeprefix("$")
    if "/" in name:
        name = name.rsplit("/", maxsplit=1)[-1]
    return name.removesuffix(".py").replace("_", "-")


def build_parser(catalog: RouteCatalog) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=[area.key for area in catalog.areas()])
    parser.add_argument("--name", action="append", default=[], help="long tool or skill name")
    parser.add_argument("--list", action="store_true", help="list short routing areas")
    parser.add_argument("--format", choices=FORMAT_VALUES, default="text")
    parser.add_argument("--risk", choices=RISK_VALUES, default="focused")
    parser.add_argument("--changed", nargs="*", default=[], help="changed paths for evidence")
    return parser


def decide(area: RouteArea, risk: str, changed_paths: Sequence[str]) -> RouteDecision:
    """Create one route decision."""
    return RouteDecision(
        route=ROUTE_NAME,
        area=area.key,
        label=area.label,
        tool=TOOL_NAME,
        skill=SKILL_NAME,
        next_action=area.next_action,
        commands=area.commands,
        skip_reason="",
        evidence=area.evidence_token(risk, changed_paths),
    )


class RouteRenderer:
    """Render route catalog outputs."""

    def __init__(self, output_format: str) -> None:
        self._format = output_format

    def render_areas(self, areas: Sequence[RouteArea]) -> str:
        """Render available areas."""
        if self._format == "json":
            return json.dumps([asdict(area) for area in areas], indent=2, sort_keys=True)
        if self._format == "markdown":
            rows = ["| Area | Label | Tool | Skill | Purpose |", "| ---- | ----- | ---- | ----- | ------- |"]
            rows.extend(
                f"| `{area.key}` | {area.label} | `{TOOL_NAME} --area {area.key}` | "
                f"`${SKILL_NAME}` | {area.purpose} |"
                for area in areas
            )
            return "\n".join(rows)
        return "\n".join(
            f"AREA={area.key}\tLABEL={area.label}\tTOOL={TOOL_NAME} --area {area.key}\t"
            f"SKILL={SKILL_NAME}\tNEXT_ACTION={area.next_action}"
            for area in areas
        )

    def render_decision(self, decision: RouteDecision) -> str:
        """Render one route decision."""
        if self._format == "json":
            return json.dumps(asdict(decision), indent=2, sort_keys=True)
        if self._format == "markdown":
            return self._render_markdown_decision(decision)
        return "\n".join(
            [
                f"ROUTE={decision.route}",
                f"AREA={decision.area}",
                f"LABEL={decision.label}",
                f"TOOL={decision.tool}",
                f"SKILL={decision.skill}",
                f"NEXT_ACTION={decision.next_action}",
                f"COMMANDS={' && '.join(decision.commands)}",
                f"SKIP_REASON={decision.skip_reason}",
                f"EVIDENCE={decision.evidence}",
            ]
        )

    def render_resolutions(self, resolutions: Sequence[NameResolution]) -> str:
        """Render compatibility name resolutions."""
        if self._format == "json":
            return json.dumps([asdict(item) for item in resolutions], indent=2, sort_keys=True)
        if self._format == "markdown":
            return self._render_markdown_resolutions(resolutions)
        return "\n".join(render_resolution_line(item) for item in resolutions)

    def _render_markdown_decision(self, decision: RouteDecision) -> str:
        commands = "<br>".join(f"`{command}`" for command in decision.commands)
        return "\n".join(
            [
                f"- Route: `{decision.route}`",
                f"- Area: `{decision.area}`",
                f"- Tool: `{decision.tool}`",
                f"- Skill: `${SKILL_NAME}`",
                f"- Next action: `{decision.next_action}`",
                f"- Commands: {commands}",
                f"- Evidence: `{decision.evidence}`",
            ]
        )

    def _render_markdown_resolutions(self, resolutions: Sequence[NameResolution]) -> str:
        rows = ["| Name | Status | Area | Tool | Skill |", "| ---- | ------ | ---- | ---- | ----- |"]
        rows.extend(
            f"| `{item.name}` | `{item.status}` | `{item.canonical_area}` | "
            f"`{item.canonical_tool}` | `{item.canonical_skill}` |"
            for item in resolutions
        )
        return "\n".join(rows)


def render_resolution_line(item: NameResolution) -> str:
    """Render one name resolution as machine-readable text."""
    return "\t".join(
        [
            f"NAME={item.name}",
            f"STATUS={item.status}",
            f"CANONICAL_AREA={item.canonical_area}",
            f"CANONICAL_TOOL={item.canonical_tool}",
            f"CANONICAL_SKILL={item.canonical_skill}",
        ]
    )


def has_unknown_resolution(resolutions: Iterable[NameResolution]) -> bool:
    """Return whether any name failed alias resolution."""
    return any(item.status == "unknown" for item in resolutions)


def main() -> int:
    """Run the route helper."""
    catalog = RouteCatalog.default()
    parser = build_parser(catalog)
    args = parser.parse_args()
    renderer = RouteRenderer(args.format)

    if args.name:
        resolutions = [catalog.resolve_name(name) for name in args.name]
        print(renderer.render_resolutions(resolutions))
        return 1 if has_unknown_resolution(resolutions) else 0

    if args.area:
        area = catalog.area(args.area)
        if area is None:
            print(f"ROUTE={ROUTE_NAME}\nSTATUS=unknown-area\nAREA={args.area}", file=sys.stderr)
            return 2
        print(renderer.render_decision(decide(area, args.risk, args.changed)))
        return 0

    print(renderer.render_areas(catalog.areas()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
