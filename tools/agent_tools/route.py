#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides short task routing helper for tool and skill selection.
# upstream design ../../documents/tool-skill-routing-refactor.md short tool and skill naming policy
# upstream design ../../agents/skills/task-routing.md task routing skill contract
# upstream design ../../agents/skills/catalog.yaml public skill catalog and related skill metadata
# upstream design ../../agents/skills/structure-refactor.md repository structure and personal runtime routing boundary
# upstream design ../../agents/skills/prose-reasoning-graph.md prose graph skill routing
# upstream design ../../agents/skills/pr-processing.md PR and Issue queue processing skill routing
# downstream design ../../documents/tools/route.md reader-facing route tool documentation
# downstream implementation ../../tests/agent_tools/test_route.py tests route output and aliases
# @dependency-end
"""Select short AgentCanon tool and skill routes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml
from skill_lane_detector import (
    structural_skill_lane_concept_matches,
    validation_failure_repair_concept_matches,
)

ROUTE_NAME = "task-routing"
SKILL_NAME = "task-routing"
TOOL_NAME = "route.py"
RISK_VALUES = ("routine", "focused", "profile", "shared", "large")
FORMAT_VALUES = ("text", "json", "markdown")
MODE_VALUES = ("routing-only", "repo-changing")

AreaData = tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]
JsonMapping = Mapping[str, object]
DEFAULT_ROOT = Path(__file__).resolve().parents[2]
SKILL_CATALOG_PATH = Path("agents/skills/catalog.yaml")
STAGE_POLICY_VALUES = ("active", "deferred")
PRIVATE_SKILL_PREFIX = "_"
SUBAGENT_BOOTSTRAP_SKILL = "subagent-bootstrap"
PRIVATE_SUBAGENT_ROUTE_ALIASES = (
    "subagent-beginning",
    "_subagent-beginning",
    "subagent-startup",
    "_subagent-startup",
)
PRIVATE_ROUTE_STRUCTURAL_FIELDS = (
    "subagent_startup_route",
    "internal_skill_routes",
)

IMPLEMENTATION_HANDOFF_TRIGGER_GROUPS: tuple[tuple[str, ...], ...] = (
    ("implementation",),
    ("implement",),
    ("実装",),
    ("patch",),
    ("パッチ",),
    ("fix",),
    ("修正",),
    ("refactor",),
    ("リファクタ",),
    ("doc-edit",),
    ("doc", "edit"),
    ("docs", "edit"),
    ("document", "edit"),
    ("ドキュメント", "編集"),
    ("文書", "編集"),
    ("文書", "修正"),
    ("write-capable", "handoff"),
    ("implementation", "handoff"),
    ("edit", "handoff"),
)
NON_IMPLEMENTATION_REVIEW_GROUPS: tuple[tuple[str, ...], ...] = (
    ("do", "not", "edit"),
    ("don't", "edit"),
    ("do-not-edit",),
    ("no", "edits"),
    ("no", "patch"),
    ("review-only",),
    ("review", "only"),
    ("read-only",),
    ("advisory",),
    ("do", "not", "implement"),
    ("編集しない",),
    ("修正しない",),
    ("実装しない",),
    ("レビューのみ",),
    ("読取専用",),
)
IMPLEMENTATION_DELEGATION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("サブエージェント", "依頼"),
    ("エージェント", "起動"),
)
NO_PATCH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:no|without)\s+(?:code\s+)?patch(?:es|ing)?(?![A-Za-z0-9])"
)
SUPPLEMENTAL_SKILL_ROUTE_GROUPS: Mapping[str, tuple[tuple[str, ...], ...]] = {}
BROAD_REFACTOR_ROUTE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("refactor",),
    ("リファクタ",),
)
USER_GUIDED_DEBUGGING_ROUTE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("one issue at a time",),
    ("user-guided debugging",),
    ("user-guided", "cadence"),
    ("one concrete issue",),
    ("no", "validation", "unless", "ask"),
    ("1", "issue", "1", "fix"),
    ("1", "problem", "1", "patch"),
    ("問題ごと",),
    ("一件ずつ",),
    ("一つずつ",),
    ("1件", "ずつ"),
    ("ユーザー主導",),
    ("問題点", "修正"),
)
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
        "structure",
        "repository structure",
        "Classify repo-root, shared-canon, project runtime view, and personal runtime surfaces before refactors.",
        "classify_structure_refactor_surface",
        (
            "python3 tools/agent_tools/repo_structure_contract.py --root <root> --format json",
            "python3 tools/agent_tools/responsibility_scope.py --root <root> --format json",
            "python3 tools/agent_tools/import_responsibility.py --root <root> --format json",
        ),
        (
            "structure-refactor",
            "repo-refactor",
            "repo_refactor_skill",
            "refactor",
            "repository-refactor",
            "repo-structure",
            "repository-structure",
            "structure-review",
            "structure-review-skill",
            "structural-review",
            "responsibility-scope",
            "personal-runtime-surface",
            "codex-personal-runtime",
            "codex-config-surface",
            "dot-codex-surface",
            "~/.codex",
        ),
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
        "Choose the validation set that covers the changed paths and risk.",
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
        "Keep GitHub-first remote rules separate from machine-local remote repair.",
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
        "Hide Codex or CLI examples when unavailable.",
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
        (
            "multi_agent_mode_selector.py",
            "agent-mode",
            "subagent-beginning",
            "_subagent-beginning",
            "subagent-startup",
            "_subagent-startup",
            "subagent_role_budget.py",
            "subagent-budget",
        ),
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
        ("agent-canon structured-analysis document-inventory --root .",),
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

REPO_CHANGING_TERMS = (
    "修正",
    "実装",
    "リファクタ",
    "移行",
    "移譲",
    "変更",
    "直して",
    "見直",
    "fix",
    "implement",
    "refactor",
    "repo-changing",
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
class SkillRoutingRule:
    """One catalog-backed prompt routing rule for a public skill."""

    skill: str
    reason: str
    stage_policy: str
    triggers: tuple[tuple[str, ...], ...]
    related_skills: tuple[str, ...]


@dataclass(frozen=True)
class SkillRouteMatch:
    """One prompt-derived public skill route."""

    skill: str
    reason: str


@dataclass(frozen=True)
class SkillRouteDecision:
    """Prompt-derived public skill selection decision."""

    route: str
    mode: str
    skills: tuple[str, ...]
    active_skills: tuple[str, ...]
    deferred_skills: tuple[str, ...]
    matched_skills: tuple[str, ...]
    related_skill_candidates: tuple[str, ...]
    related_skills: dict[str, tuple[str, ...]]
    reasons: tuple[str, ...]
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
        """Initialize route areas and aliases."""
        self._areas = {area.key: area for area in areas}
        self._aliases = self._build_aliases(areas)

    @classmethod
    def default(cls) -> RouteCatalog:
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
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="repository root for catalog-backed routing")
    parser.add_argument("--area", choices=[area.key for area in catalog.areas()])
    parser.add_argument("--name", action="append", default=[], help="long tool or skill name")
    parser.add_argument(
        "--prompt",
        "--request",
        "--purpose",
        "--task",
        action="append",
        default=[],
        help="prompt text to route into public skills",
    )
    parser.add_argument(
        "--prompt-file",
        "--request-file",
        "--query-file",
        action="append",
        default=[],
        help="read prompt text from a file relative to --root when not absolute",
    )
    parser.add_argument(
        "--prompt-stdin",
        "--request-stdin",
        "--query-stdin",
        action="store_true",
        help="read prompt text from stdin",
    )
    parser.add_argument("--mode", choices=MODE_VALUES, default="repo-changing")
    parser.add_argument("--list", action="store_true", help="list short routing areas")
    parser.add_argument("--format", choices=FORMAT_VALUES, default="text")
    parser.add_argument("--risk", choices=RISK_VALUES, default="focused")
    parser.add_argument("--changed", nargs="*", default=[], help="changed paths for evidence")
    parser.add_argument("prompt_parts", nargs="*", help="positional prompt text for prompt routing")
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


def text_matches_term(text: str, term: str) -> bool:
    """Return whether one trigger term appears without matching inside words."""
    normalized = term.lower()
    if re.fullmatch(r"[a-z0-9]+", normalized):
        suffix = "s?" if len(normalized) > 2 else ""
        return (
            re.search(
                rf"(?<![A-Za-z0-9]){re.escape(normalized)}{suffix}(?![A-Za-z0-9])",
                text,
            )
            is not None
        )
    return normalized in text


def text_matches_group(text: str, group: tuple[str, ...]) -> bool:
    """Return whether all group terms appear in text."""
    return all(text_matches_term(text, term) for term in group)


def object_mapping(value: object, field: str) -> JsonMapping:
    """Return one string-keyed mapping from parsed catalog data."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return cast(JsonMapping, value)


def object_sequence(value: object, field: str) -> Sequence[object]:
    """Return one sequence from parsed catalog data."""
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return cast(Sequence[object], value)


def load_skill_catalog(root: Path) -> JsonMapping:
    """Load the machine-readable public skill catalog."""
    path = root / SKILL_CATALOG_PATH
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{SKILL_CATALOG_PATH} YAML parse failed: {exc}") from exc
    return object_mapping(raw, str(SKILL_CATALOG_PATH))


def string_list(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of non-empty strings from one YAML sequence."""
    result: list[str] = []
    for item in object_sequence(value, field):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} entries must be non-empty strings")
        result.append(item)
    return tuple(result)


def trigger_groups(value: object, field: str) -> tuple[tuple[str, ...], ...]:
    """Return normalized trigger term groups from YAML."""
    if value is None:
        return ()
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(object_sequence(value, field)):
        groups.append(string_list(group, f"{field}[{index}]"))
    return tuple(groups)


def optional_string_list(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of strings from an optional YAML list."""
    if value is None:
        return ()
    return string_list(value, field)


def load_skill_route_rules(root: Path) -> tuple[SkillRoutingRule, ...]:
    """Load prompt-routing rules from the public skill catalog."""
    data = load_skill_catalog(root)
    families = object_sequence(data.get("skill_families"), "skill_families")
    rules: list[SkillRoutingRule] = []
    observed_skill_ids: set[str] = set()
    for index, entry in enumerate(families):
        entry_mapping = object_mapping(entry, f"skill_families[{index}]")
        skill_id = entry_mapping.get("id")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise ValueError(f"skill_families[{index}].id must be a non-empty string")
        if skill_id.startswith(PRIVATE_SKILL_PREFIX):
            raise ValueError(f"skill_families[{index}].id must be public: {skill_id}")
        if skill_id in observed_skill_ids:
            raise ValueError(f"duplicate skill catalog id: {skill_id}")
        observed_skill_ids.add(skill_id)
        routing = entry_mapping.get("routing")
        if routing is None:
            routing_mapping: JsonMapping = {}
        else:
            routing_mapping = object_mapping(routing, f"{skill_id}.routing")
        reason = routing_mapping.get("reason", "prompt explicitly names public skill")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{skill_id}.routing.reason must be a non-empty string")
        stage_policy = routing_mapping.get("stage_policy", "deferred")
        if stage_policy not in STAGE_POLICY_VALUES:
            raise ValueError(f"{skill_id}.routing.stage_policy must be one of {STAGE_POLICY_VALUES}")
        rules.append(
            SkillRoutingRule(
                skill=skill_id,
                reason=reason,
                stage_policy=str(stage_policy),
                triggers=trigger_groups(routing_mapping.get("triggers"), f"{skill_id}.routing.triggers"),
                related_skills=optional_string_list(
                    entry_mapping.get("related_skills"),
                    f"{skill_id}.related_skills",
                ),
            )
        )
    for rule in rules:
        for related_skill in rule.related_skills:
            if related_skill == rule.skill:
                raise ValueError(f"{rule.skill}.related_skills must not include itself")
            if related_skill.startswith(PRIVATE_SKILL_PREFIX):
                raise ValueError(f"{rule.skill}.related_skills must be public: {related_skill}")
            if related_skill not in observed_skill_ids:
                raise ValueError(f"{rule.skill}.related_skills unknown skill: {related_skill}")
    return tuple(rules)


def load_skill_related_map(root: Path) -> dict[str, tuple[str, ...]]:
    """Return catalog-backed related-skill candidates keyed by public skill id."""
    return {rule.skill: rule.related_skills for rule in load_skill_route_rules(root)}


def validation_failure_repair_rules(
    rules_by_skill: Mapping[str, SkillRoutingRule],
    prompt: str,
) -> tuple[SkillRoutingRule, ...]:
    """Return route-owned repair routing for validation-failure prompts."""
    matches = validation_failure_repair_concept_matches(prompt)
    if not matches:
        return ()
    catalog_rule = rules_by_skill.get("codex-task-workflow")
    related_skills = ("test-design",)
    if catalog_rule is not None:
        related_skills = ordered_unique((*catalog_rule.related_skills, "test-design"))
    return (
        SkillRoutingRule(
            skill="codex-task-workflow",
            reason=matches[0].reason(),
            stage_policy="active",
            triggers=(),
            related_skills=related_skills,
        ),
    )


def read_prompt_file(root: Path, raw_path: str) -> str:
    """Read one prompt file, resolving relative paths from the repository root."""
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise FileNotFoundError(f"prompt-file-not-found:{raw_path}")
    return path.read_text(encoding="utf-8")


def prompt_text_from_args(args: argparse.Namespace, root: Path) -> str:
    """Return normalized prompt text from CLI prompt sources."""
    parts: list[str] = []
    parts.extend(str(part) for part in args.prompt)
    parts.extend(str(part) for part in args.prompt_parts)
    for prompt_file in args.prompt_file:
        parts.append(read_prompt_file(root, str(prompt_file)))
    if args.prompt_stdin:
        parts.append(sys.stdin.read())
    return "\n".join(part.strip() for part in parts if part.strip())


def public_skill_name_mentioned(text: str, skill: str) -> bool:
    """Return whether prompt text explicitly names one public skill id."""
    return (
        re.search(
            rf"(?<![A-Za-z0-9_-])\$?{re.escape(skill)}(?![A-Za-z0-9_-])",
            text,
        )
        is not None
    )


def strip_private_route_aliases(text: str) -> str:
    """Remove private route labels before public prompt skill matching."""
    structural_field_pattern = "|".join(
        re.escape(field).replace("_", r"[-_]")
        for field in PRIVATE_ROUTE_STRUCTURAL_FIELDS
    )
    scrubbed = re.sub(
        rf"(?im)^\s*(?:{structural_field_pattern})\s*[:=].*$",
        " ",
        text,
    )
    for alias in PRIVATE_SUBAGENT_ROUTE_ALIASES:
        scrubbed = re.sub(
            rf"(?<![A-Za-z0-9_-])\$?{re.escape(alias)}(?![A-Za-z0-9_-])",
            " ",
            scrubbed,
            flags=re.IGNORECASE,
        )
    return scrubbed


def matched_skill_routes(prompt: str, rules: Sequence[SkillRoutingRule]) -> tuple[SkillRouteMatch, ...]:
    """Return public skill matches for one prompt."""
    text = prompt.lower()
    matches: list[SkillRouteMatch] = []
    observed: set[str] = set()
    for rule in rules:
        if rule.skill in observed:
            continue
        explicit = public_skill_name_mentioned(text, rule.skill)
        if explicit or any(text_matches_group(text, group) for group in rule.triggers):
            match_reason = "prompt explicitly names public skill" if explicit else rule.reason
            matches.append(SkillRouteMatch(rule.skill, match_reason))
            observed.add(rule.skill)
    return tuple(matches)


def structural_skill_lane_routes(prompt: str) -> tuple[SkillRouteMatch, ...]:
    """Return skill matches from structural project-owned skill lane evidence."""
    matches: list[SkillRouteMatch] = []
    for concept_match in structural_skill_lane_concept_matches(prompt):
        reason = concept_match.reason()
        for skill in concept_match.concept.route_skills:
            matches.append(SkillRouteMatch(skill, reason))
    return tuple(matches)


def validation_failure_repair_routes(prompt: str) -> tuple[SkillRouteMatch, ...]:
    """Return skill matches from same-intent validation repair evidence."""
    return tuple(
        SkillRouteMatch(match.concept.owner_skill, match.reason())
        for match in validation_failure_repair_concept_matches(prompt)
    )


def user_guided_debugging_requested(prompt: str) -> bool:
    """Return whether the prompt asks for one-issue-at-a-time debugging."""
    text = prompt.lower()
    return any(text_matches_group(text, group) for group in USER_GUIDED_DEBUGGING_ROUTE_GROUPS)


def broad_refactor_routes(prompt: str) -> tuple[SkillRouteMatch, ...]:
    """Return refactor-loop for broad refactor prompts outside user-guided cadence."""
    text = prompt.lower()
    if user_guided_debugging_requested(prompt):
        return ()
    if any(text_matches_group(text, group) for group in BROAD_REFACTOR_ROUTE_GROUPS):
        return (
            SkillRouteMatch(
                "refactor-loop",
                "broad refactor prompt needs behavior-preserving refactor loop",
            ),
        )
    return ()


def supplemental_skill_routes(prompt: str) -> tuple[SkillRouteMatch, ...]:
    """Return route-owned matches that are not yet expressible in catalog data."""
    text = prompt.lower()
    return tuple(
        SkillRouteMatch(skill, "supplemental route-owned prompt trigger")
        for skill, groups in SUPPLEMENTAL_SKILL_ROUTE_GROUPS.items()
        if any(text_matches_group(text, group) for group in groups)
    )


def dedupe_skill_route_matches(
    matches: Sequence[SkillRouteMatch],
) -> tuple[SkillRouteMatch, ...]:
    """Return first match per skill while preserving route order."""
    observed: set[str] = set()
    deduped: list[SkillRouteMatch] = []
    for match in matches:
        if match.skill in observed:
            continue
        observed.add(match.skill)
        deduped.append(match)
    return tuple(deduped)


def infer_mode(prompt: str, requested_mode: str) -> str:
    """Return repo-changing mode when the prompt clearly asks for edits."""
    if requested_mode == "repo-changing":
        return requested_mode
    text = prompt.lower()
    if any(term.lower() in text for term in REPO_CHANGING_TERMS):
        return "repo-changing"
    return requested_mode


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Return values in first-seen order without duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def implementation_handoff_required(prompt: str, mode: str = "repo-changing") -> bool:
    """Return whether prompt text asks for a write-capable implementation handoff."""
    if mode != "repo-changing":
        return False
    text = prompt.lower()
    if any(
        text_matches_group(text, group)
        for group in NON_IMPLEMENTATION_REVIEW_GROUPS
        if group != ("no", "patch")
    ):
        return False
    if NO_PATCH_RE.search(text):
        return False
    if any(text_matches_group(text, group) for group in IMPLEMENTATION_DELEGATION_GROUPS):
        return True
    return any(text_matches_group(text, group) for group in IMPLEMENTATION_HANDOFF_TRIGGER_GROUPS)


def is_current_stage_skill(
    skill: str,
    rules_by_skill: Mapping[str, SkillRoutingRule],
    prompt: str = "",
    mode: str = "repo-changing",
) -> bool:
    """Return whether one matched skill belongs in the initial routing wave."""
    if skill == SUBAGENT_BOOTSTRAP_SKILL:
        return implementation_handoff_required(prompt, mode)
    rule = rules_by_skill.get(skill)
    return rule is not None and rule.stage_policy == "active"


def related_skill_candidates(
    matched_skills: Sequence[str],
    rules_by_skill: Mapping[str, SkillRoutingRule],
    selected_skills: Sequence[str],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Return related skills for matched skills without activating them."""
    related_by_source: dict[str, tuple[str, ...]] = {}
    candidates: list[str] = []
    selected = set(selected_skills)
    for skill in matched_skills:
        rule = rules_by_skill.get(skill)
        if rule is None or not rule.related_skills:
            continue
        pending_related = tuple(
            related_skill
            for related_skill in rule.related_skills
            if related_skill not in selected
        )
        if not pending_related:
            continue
        related_by_source[skill] = pending_related
        candidates.extend(pending_related)
    return related_by_source, ordered_unique(candidates)


def decide_skills(prompt: str, mode: str, rules: Sequence[SkillRoutingRule]) -> SkillRouteDecision:
    """Create a prompt-derived public skill route decision."""
    public_prompt = strip_private_route_aliases(prompt)
    active_mode = infer_mode(public_prompt, mode)
    catalog_rules_by_skill = {rule.skill: rule for rule in rules}
    effective_rules = (
        *rules,
        *validation_failure_repair_rules(catalog_rules_by_skill, public_prompt),
    )
    rules_by_skill = {rule.skill: rule for rule in effective_rules}
    matches = dedupe_skill_route_matches(
        (
            *broad_refactor_routes(public_prompt),
            *matched_skill_routes(public_prompt, effective_rules),
            *structural_skill_lane_routes(public_prompt),
            *validation_failure_repair_routes(public_prompt),
            *supplemental_skill_routes(public_prompt),
        )
    )
    matched_skills = tuple(match.skill for match in matches)
    base_skills = ["agent-orchestration"]
    if active_mode == "repo-changing":
        base_skills.append("codex-task-workflow")
    handoff_required = implementation_handoff_required(public_prompt, active_mode)
    prompt_skills = matched_skills
    if handoff_required:
        prompt_skills = ordered_unique((*prompt_skills, SUBAGENT_BOOTSTRAP_SKILL))
    skills = ordered_unique((*base_skills, *prompt_skills))
    active_skill_inputs = ["agent-orchestration"]
    if handoff_required:
        active_skill_inputs.append(SUBAGENT_BOOTSTRAP_SKILL)
    active_skill_inputs.extend(
        match.skill
        for match in matches
        if (
            match.skill != SUBAGENT_BOOTSTRAP_SKILL
            and match.reason == "prompt explicitly names public skill"
        )
        or is_current_stage_skill(match.skill, rules_by_skill, public_prompt, active_mode)
    )
    active_skills = ordered_unique(active_skill_inputs)
    deferred_skills = tuple(skill for skill in skills if skill not in active_skills)
    related_by_source, related_candidates = related_skill_candidates(
        matched_skills,
        rules_by_skill,
        skills,
    )
    evidence = (
        f"mode={active_mode};matched={','.join(matched_skills) if matched_skills else 'none'};"
        f"active={','.join(active_skills)};"
        f"deferred={','.join(deferred_skills) if deferred_skills else 'none'};"
        f"related={','.join(related_candidates) if related_candidates else 'none'}"
    )
    return SkillRouteDecision(
        route="skill-selection",
        mode=active_mode,
        skills=skills,
        active_skills=active_skills,
        deferred_skills=deferred_skills,
        matched_skills=matched_skills,
        related_skill_candidates=related_candidates,
        related_skills=related_by_source,
        reasons=tuple(f"{match.skill}:{match.reason}" for match in matches),
        evidence=evidence,
    )


class RouteRenderer:
    """Render route catalog outputs."""

    def __init__(self, output_format: str) -> None:
        """Initialize the renderer for one output format."""
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

    def render_skill_decision(self, decision: SkillRouteDecision) -> str:
        """Render one prompt-derived skill selection decision."""
        if self._format == "json":
            payload = {"schema": "agent_canon.route.skill_route.v1", **asdict(decision)}
            return json.dumps(payload, indent=2, sort_keys=True)
        if self._format == "markdown":
            skills = ", ".join(f"`${skill}`" for skill in decision.skills)
            reasons = "<br>".join(f"`{reason}`" for reason in decision.reasons) or "`none`"
            return "\n".join(
                [
                    f"- Route: `{decision.route}`",
                    f"- Mode: `{decision.mode}`",
                    f"- Skills: {skills}",
                    "- Active skills: "
                    + ", ".join(f"`${skill}`" for skill in decision.active_skills),
                    "- Deferred skills: "
                    + (
                        ", ".join(f"`${skill}`" for skill in decision.deferred_skills)
                        if decision.deferred_skills
                        else "`none`"
                    ),
                    f"- Matched skills: `{','.join(decision.matched_skills) or 'none'}`",
                    "- Related skill candidates: "
                    + (
                        ", ".join(f"`${skill}`" for skill in decision.related_skill_candidates)
                        if decision.related_skill_candidates
                        else "`none`"
                    ),
                    f"- Reasons: {reasons}",
                    f"- Evidence: `{decision.evidence}`",
                ]
            )
        return "\n".join(
            [
                f"ROUTE={decision.route}",
                "SCHEMA=agent_canon.route.skill_route.v1",
                f"MODE={decision.mode}",
                f"SKILLS={','.join(f'${skill}' for skill in decision.skills)}",
                f"ACTIVE_SKILLS={','.join(f'${skill}' for skill in decision.active_skills)}",
                "DEFERRED_SKILLS="
                + (
                    ",".join(f"${skill}" for skill in decision.deferred_skills)
                    if decision.deferred_skills
                    else "-"
                ),
                f"MATCHED_SKILLS={','.join(decision.matched_skills) or '-'}",
                "RELATED_SKILL_CANDIDATES="
                + (
                    ",".join(f"${skill}" for skill in decision.related_skill_candidates)
                    if decision.related_skill_candidates
                    else "-"
                ),
                "RELATED_SKILLS="
                + (
                    ";".join(
                        f"{source}:{'|'.join(skills)}"
                        for source, skills in decision.related_skills.items()
                    )
                    if decision.related_skills
                    else "-"
                ),
                f"REASONS={';'.join(decision.reasons) or '-'}",
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

    root = Path(args.root).resolve()
    try:
        prompt_text = prompt_text_from_args(args, root)
    except OSError as exc:
        print(f"SKILL_ROUTER_ERROR={exc}", file=sys.stderr)
        return 2

    if prompt_text:
        try:
            rules = load_skill_route_rules(root)
        except (OSError, ValueError) as exc:
            print(f"SKILL_ROUTER_ERROR={exc}", file=sys.stderr)
            return 2
        print(renderer.render_skill_decision(decide_skills(prompt_text, str(args.mode), rules)))
        return 0

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
