#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates the canonical public-skill dependency dictionary and generates its complete Mermaid projection.
# upstream design ../../agents/skills/catalog.yaml enumerates every public skill identity
# upstream design ../../agents/skills/skill-dependencies.yaml owns typed prerequisites, successors, order, groups, and parallel relations
# upstream design ../../agents/skills/agent-orchestration.md owns canonical invocation and work-conservation policy
# upstream design ../../agents/skills/task-routing.md owns deterministic route consumption
# downstream implementation ../../tools/agent_tools/skill_route_catalog.py parses and validates the dependency dictionary
# downstream implementation ../../documents/runtime/skill-dependency-graph.md is the generated user-facing projection
# downstream implementation ../../tests/agent_tools/test_skill_dependency_map.py checks static and graph contracts
# @dependency-end
"""Validate and project the canonical public-skill dependency dictionary."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys

from skill_route_catalog import (
    SKILL_DEPENDENCY_MAP_PATH,
    SkillDependencyRule,
    build_skill_dependency_edges,
    load_skill_dependency_map,
)

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH_PATH = Path("documents/runtime/skill-dependency-graph.md")
GRAPH_HEADER = "<!-- Generated from agents/skills/skill-dependencies.yaml; do not edit this graph by hand. -->"
TOP_DEPENDENCY_MANIFEST = """<!--
@dependency-start
contract design
responsibility Generates the human-facing public-skill dependency graph from skill dependency definitions.
upstream implementation ../../agents/skills/skill-dependencies.yaml is the dictionary source of truth for edges.
upstream implementation ../../tools/agent_tools/skill_route_catalog.py consumes resolved dependency map for routing.
downstream implementation ../../tools/agent_tools/skill_route_catalog.py loads generated routing order from the public map projection.
@dependency-end
-->
"""


def _mermaid_id(skill: str) -> str:
    """Return a stable Mermaid node identifier for one public skill id."""
    return "skill_" + skill.replace("-", "_")


def _label(value: str) -> str:
    """Escape the small label alphabet used by the generated graph."""
    return value.replace('"', "'")


def _edge_labels(
    rules: dict[str, SkillDependencyRule],
) -> tuple[dict[tuple[str, str], set[str]], set[tuple[str, str]], set[tuple[str, str]]]:
    """Collect typed directed, routing-candidate, and parallel relations."""
    directed: dict[tuple[str, str], set[str]] = defaultdict(set)
    routing: set[tuple[str, str]] = set()
    for rule in rules.values():
        for prerequisite in rule.required_prerequisites:
            directed[(prerequisite, rule.skill)].add("prerequisite")
        for candidate in rule.routing_candidates:
            routing.add((rule.skill, candidate))
        for successor in rule.successors:
            directed[(rule.skill, successor)].add("successor")
        for constraint in rule.order_constraints:
            directed[(constraint.before, constraint.after)].add("order")
    parallel: set[tuple[str, str]] = set()
    for rule in rules.values():
        for other in rule.parallel_independent:
            parallel.add(tuple(sorted((rule.skill, other))))
    return directed, routing, parallel


def render_mermaid(rules: dict[str, SkillDependencyRule]) -> str:
    """Render every public skill in responsibility-grouped Mermaid form."""
    groups: dict[str, list[str]] = defaultdict(list)
    for rule in rules.values():
        groups[rule.responsibility_group].append(rule.skill)
    directed, routing, parallel = _edge_labels(rules)
    lines = [
        TOP_DEPENDENCY_MANIFEST.rstrip(),
        GRAPH_HEADER,
        "# Public Skill Dependency Graph",
        "",
        "```mermaid",
        "graph LR",
    ]
    for group, skills in groups.items():
        group_id = "group_" + group.replace("-", "_")
        lines.append(f'  subgraph {group_id}["{_label(group)}"]')
        for skill in skills:
            lines.append(f'    {_mermaid_id(skill)}["{_label(skill)}"]')
        lines.append("  end")
    for (before, after), labels in directed.items():
        label = "/".join(sorted(labels))
        lines.append(
            f'  {_mermaid_id(before)} -->|"{label}"| {_mermaid_id(after)}'
        )
    for before, after in sorted(routing):
        lines.append(
            f'  {_mermaid_id(before)} -.->|routing-candidate| {_mermaid_id(after)}'
        )
    for before, after in sorted(parallel):
        lines.append(
            f'  {_mermaid_id(before)} -.->|"parallel-independent"| '
            f'{_mermaid_id(after)}'
        )
    lines.extend(["```", ""])
    return "\n".join(lines)


def check(root: Path) -> tuple[int, int, int]:
    """Validate the map and return skill, directed-edge, parallel-edge counts."""
    rules = dict(load_skill_dependency_map(root))
    directed = build_skill_dependency_edges(rules)
    _, _, parallel = _edge_labels(rules)
    return len(rules), sum(len(targets) for targets in directed.values()), len(parallel)


def build_parser() -> argparse.ArgumentParser:
    """Build the typed dependency-map command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check", help="validate the dependency dictionary")
    check_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    graph_parser = subparsers.add_parser("graph", help="generate the Mermaid dependency graph")
    graph_parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    graph_parser.add_argument("--output", type=Path, default=DEFAULT_GRAPH_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one focused dependency-map operation."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        skill_count, directed_count, parallel_count = check(root)
        if args.command == "check":
            print(
                "SKILL_DEPENDENCY_MAP=pass "
                f"source={SKILL_DEPENDENCY_MAP_PATH} skills={skill_count} "
                f"directed_edges={directed_count} parallel_edges={parallel_count}"
            )
            return 0
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            render_mermaid(dict(load_skill_dependency_map(root))), encoding="utf-8"
        )
        try:
            display_output = output.relative_to(root)
        except ValueError:
            display_output = output
        print(
            "SKILL_DEPENDENCY_GRAPH=pass "
            f"source={SKILL_DEPENDENCY_MAP_PATH} output={display_output} "
            f"skills={skill_count}"
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"SKILL_DEPENDENCY_MAP=fail reason={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
