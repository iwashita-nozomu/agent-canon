#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Classifies prompt routing signals from immutable injected evidence.
# upstream design ../../../documents/design/agentcanon-hook-simplification-wave3.md owns the pure classifier contract.
# downstream implementation ../../../eval/producers/evaluate_workflow_selection.py supplies frozen catalog/routing inputs.
# downstream implementation ../../runtime/archive/behavior_event_assembly.py consumes PromptIntakeSignals.
# downstream implementation ../../../tests/agent_tools/test_prompt_classifier.py validates purity and field parity.
# @dependency-end
"""Pure prompt-intake classifier.

The classifier deliberately has no repository discovery, environment access, subprocess,
Git, network, or log side effects. Repository-dependent evidence is injected by callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import FrozenSet, Mapping, TypeAlias

from tools.agent.skills.skill_lane_detector import SkillLaneEvidence

FrozenValue: TypeAlias = str | int | float | bool | None | tuple["FrozenValue", ...] | Mapping[str, "FrozenValue"]
FrozenMapping = Mapping[str, FrozenValue]

SKILL_TOKEN_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9_-]*)")
FIELD_RE = re.compile(
    r"(?:^|\s)(skills?|skill_invocation|workflow|workflow_family|selected_workflow|"
    r"candidate_skills?|candidate_workflows?|candidate_tools?|feedback_labels?|"
    r"feedback_action|tool)=([^\s]+)"
)
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

SKILL_KEYWORDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "agent-learning": (
        ("人間からのフィードバック",),
        ("runtime feedback",),
        ("再発防止",),
        ("こういう止まり方",),
        ("フィードバック", "修正"),
        ("feedback", "repair"),
        ("memory", "feedback"),
        ("学習", "agent"),
    ),
    "agent-orchestration": (
        ("どのスキル",),
        ("どのskill",),
        ("スキル選択",),
        ("skill selection",),
        ("routing", "skill"),
        ("ルーティング", "スキル"),
        ("マルチエージェント",),
        ("サブエージェント", "起動"),
        ("subagent", "routing"),
        ("workflow=", "skills="),
    ),
    "agent-log-analysis": (
        ("routing miss",),
        ("selection gap",),
        ("generate_agent_runtime_dashboard.py",),
        ("runtime dashboard",),
        ("生ログ", "要約"),
        ("routing", "coverage"),
        ("toolcall", "skillcall", "coverage"),
        ("toolcall", "skillcall", "routing"),
        ("toolcall", "skillcall", "miss"),
        ("toolcall", "skillcall", "50"),
        ("toolcall", "skillcall", "されない"),
        ("ルーティング", "ログ"),
        ("ログ", "skill"),
        ("ログ", "tool"),
        ("toolcall", "skillcall", "ルーティング"),
    ),
    "adaptive-improvement-loop": (
        ("adaptive-improvement-loop",),
        ("next_action", "iteration"),
        ("改善ループ",),
        ("backlog", "iteration"),
    ),
    "agent-canon-update": (
        ("agentcanon", "update"),
        ("agent-canon", "update"),
        ("agent-canon pr",),
        ("agentcanon", "latest"),
        ("agent-canon", "latest"),
        ("サブモジュール", "agentcanon"),
        ("agentcanon", "最新"),
        ("agentcanon", "更新"),
    ),
    "md-style-check": (
        ("md-style",),
        ("docs-check",),
        ("agent-canon", "docs"),
        ("docs", "format"),
        ("docs", "check"),
        ("markdownlint",),
        ("markdown", "lint"),
        ("markdown", "heading"),
        ("markdown", "link"),
        ("markdown", "formatter"),
        ("docs format",),
        ("formatter", "adjacent"),
        ("フォーマッタ",),
        ("フォーマット", "周辺"),
        ("通してすらない",),
        ("マークダウン", "体裁"),
        ("マークダウン", "リンク"),
    ),
    "computational-optimization": (
        ("computational optimization",),
        ("計算最適化",),
        ("数値最適化",),
        ("optimizer",),
        ("optimization", "solver"),
        ("preconditioner",),
        ("kkt",),
        ("gradient", "hessian"),
        ("jacobian",),
        ("convergence", "tolerance"),
        ("収束", "tolerance"),
        ("solver", "residual"),
        ("residual",),
    ),
    "gpu-execution": (
        ("gpu", "実行"),
        ("gpu", "利用"),
        ("gpu", "検証"),
        ("cuda", "backend"),
        ("jax", "gpu"),
        ("xla", "gpu"),
        ("nvidia-smi",),
        ("cuda_visible_devices",),
        ("gpu_validation_blocker",),
        ("experimentrunner",),
        ("experiment_runner",),
        ("python", "experimentrunner"),
        ("xla_python_client_preallocate",),
        ("preallocation", "disable"),
        ("先取", "無効"),
        ("先取り", "無効"),
    ),
    "result-artifact-writeout": (
        ("結果書き出し",),
        ("結果を書き出",),
        ("result writeout",),
        ("runtime_log_archive_git.py",),
        ("artifact", "evidence"),
        ("artifact", "report"),
        ("run bundle", "evidence"),
        ("蓄積分析", "レポート"),
        ("ログ", "レポート", "残"),
    ),
    "task-routing": (
        ("tool", "skill", "routing"),
        ("tool", "skill", "ルーティング"),
        ("route.py",),
        ("public skill set",),
        ("skill set", "route"),
        ("skill selection",),
        ("workflow routing",),
        ("workflow=", "skills="),
        ("which workflow",),
        ("どのスキル",),
        ("ルーティング",),
    ),
    "oop-readability-check": (
        ("oop", "readability"),
        ("oop", "可読"),
        ("オブジェクト指向", "可読"),
        ("readability", "guard"),
        ("readability", "check"),
        ("可読性", "class"),
        ("可読性", "method"),
    ),
    "academic-writing": (
        ("academic writing",),
        ("scholarly note",),
        ("citation", "evidence"),
        ("logic gap",),
        ("学術文章",),
        ("notation", "logic"),
        ("記法", "論理"),
    ),
    "codex-task-workflow": (
        ("repo-changing",),
        ("実装", "修正"),
        ("コード", "直して"),
        ("implementation", "fix"),
        ("agent-canon", "docs"),
        ("patch", "repo"),
        ("bounded fix",),
        ("patch",),
        ("typo", "修正"),
        ("責務境界", "修正"),
        ("flaky test", "直して"),
        ("単一 file", "直して"),
        ("scoped-change",),
        ("実装して", "repo"),
        ("修正して", "repo"),
        ("直して", "repo"),
        ("public behavior",),
        ("bounded behavior",),
        ("regression case",),
        ("bounded scope",),
        ("仕様解釈", "修正"),
        ("optimizer", "修正"),
        ("solver", "直して"),
        ("repo-changing optimization patch",),
        ("収束しない",),
        ("tolerance", "直して"),
        ("failed", "validation"),
        ("validation", "failure"),
        ("failing", "contract"),
        ("do", "not", "delete", "tests"),
        ("weaken", "oracle"),
    ),
    "change-review": (
        ("change-review",),
        ("code review",),
        ("diff review",),
        ("review", "finding"),
        ("レビュー", "finding"),
    ),
    "comprehensive-development": (
        ("comprehensive development",),
        ("repo-wide", "workflow"),
        ("repo-wide", "tooling"),
        ("包括的", "整理"),
        ("500", "タスク"),
    ),
    "environment-maintenance": (
        ("docker",),
        ("devcontainer",),
        ("container",),
        ("github actions",),
        ("ci", "修正"),
        ("dependency", "upgrade"),
        ("lockfile",),
    ),
    "dependency-analysis": (
        ("dependency-analysis",),
        ("dependency review",),
        ("dependency graph",),
        ("run_repo_dependency_review.sh",),
        ("依存", "graph"),
        ("依存", "レビュー"),
    ),
    "experiment-lifecycle": (
        ("run", "experiment"),
        ("new", "experiment"),
        ("rerun", "experiment"),
        ("re-run", "experiment"),
        ("experiment", "execution"),
        ("benchmark", "run"),
        ("実験", "実行"),
        ("実験", "再実行"),
        ("再現", "実験"),
        ("experiment", "artifact", "evidence"),
        ("experiment", "result", "persist"),
        ("experiment", "result", "save"),
    ),
    "html-output": (
        ("html",),
        ("browser-readable",),
        ("ブラウザ",),
        ("dashboard",),
        ("web page",),
    ),
    "literature-survey": (
        ("literature survey",),
        ("prior art",),
        ("先行研究",),
        ("論文調査",),
    ),
    "long-form-writing": (
        ("readme", "guide"),
        ("workflow", "guide"),
        ("migration", "guide"),
        ("長文", "文書"),
        ("説明文書",),
    ),
    "paper-writing": (
        ("paper", "draft"),
        ("thesis chapter",),
        ("投稿論文",),
        ("論文", "draft"),
    ),
    "pr-processing": (
        ("pr #",),
        ("pull request",),
        ("merge", "pr"),
        ("checks", "pr"),
        ("レビュー", "pr"),
    ),
    "prose-reasoning-graph": (
        ("structure analysis",),
        ("構造解析",),
        ("prose graph",),
        ("文書", "構造"),
        ("claim", "evidence"),
    ),
    "refactor-loop": (
        ("refactor",),
        ("リファクタ",),
        ("behavior-preserving",),
        ("構造変更",),
    ),
    "report-writing": (
        ("report",),
        ("レポート",),
        ("decision brief",),
        ("summary", "evidence"),
        ("結果", "説明"),
    ),
    "research-workflow": (
        ("research-backed",),
        ("external research",),
        ("外部調査",),
        ("比較実験",),
        ("benchmark", "compare"),
    ),
    "structure-planning": (
        ("structure contract",),
        ("構造", "計画"),
        ("section order",),
        ("source map",),
        ("first figure",),
    ),
    "structure-refactor": (
        ("structure drift",),
        ("repo structure",),
        ("directory layout",),
        ("root view",),
        ("responsibility-scope",),
        ("構造", "drift"),
    ),
    "subagent-bootstrap": (
        ("マルチエージェント",),
        ("subagent",),
        ("spawn", "agent"),
        ("複数 agent",),
        ("agent", "fan-out"),
    ),
    "test-design": (
        ("test design",),
        ("nasty case",),
        ("regression case",),
        ("regression",),
        ("既存テスト",),
        ("テスト",),
        ("public behavior",),
        ("仕様解釈",),
        ("テスト設計",),
        ("test oracle",),
        ("oracle", "mismatch"),
        ("spec mismatch", "test"),
        ("brittle", "test"),
    ),
    "tool-finding-report": (
        ("tool finding",),
        ("checker finding",),
        ("static analysis", "finding"),
        ("finding packet",),
        ("run_repo_dependency_review.sh",),
        ("dependency graph",),
        ("complete report",),
        ("検出結果",),
    ),
    "user-guided-debugging": (
        ("one issue at a time",),
        ("user-guided debugging",),
        ("一つずつ", "debug"),
        ("デバッグ", "一件"),
        ("問題ごと", "修正"),
        ("原因説明", "patch"),
    ),
}
WORKFLOW_KEYWORDS: dict[str, tuple[str, ...]] = {
    "adaptive-improvement-loop": ("next_action", "backlog", "iteration", "改善ループ"),
    "agent-canon-update": (
        "agent-canon pr",
        "external AgentCanon clone",
        "development clone",
        "agentcanon 最新",
        "pull request",
        "pr #",
        "マージ",
        "merge",
    ),
    "agent-canon-update-route": ("external AgentCanon clone", "development clone", "agentcanon 最新"),
    "codex-task-workflow": (
        "codex-task-workflow",
        "repo-changing",
        "patch",
        "修正して",
        "直して",
        "実装して",
        "bounded fix",
        "bounded behavior",
        "regression case",
        "agent-canon docs",
        "docs check",
        "docs format",
        "generate_agent_runtime_dashboard.py",
        "run_repo_dependency_review.sh",
        "runtime_log_archive_git.py",
        "oop-readability-check",
        "mechanical verdict",
        "failed validation",
        "validation failure",
        "failing contract",
        "test failure",
        "tests are failing",
        "do not delete tests",
        "weaken oracle",
        "oracle weakening",
        "preserved-intent repair",
        "same-intent repair",
        "cause_classification",
        "デバッグ",
        "optimizer convergence",
        "solver regression",
        "収束しない",
        "tolerance 緩和せず",
    ),
    "comprehensive-development": ("comprehensive development", "repo-wide", "包括的", "500", "tooling rearchitecture"),
    "environment-maintenance": ("docker", "devcontainer", "container", "github actions", "ci", "lockfile"),
    "large-delivery": (
        "large-delivery",
        "large refactor",
        "大規模",
        "複数 chunk",
        "milestone",
        "新機能",
        "structure drift",
        "repo structure",
        "directory layout",
        "root view",
        "responsibility-scope",
        "構造変更",
    ),
    "platform-and-environment": ("docker", "devcontainer", "container", "github actions", "ci", "dependency upgrade"),
    "research-driven-change": (
        "research-driven-change",
        "research-backed",
        "external research",
        "外部調査",
        "比較実験",
        "benchmark",
        "先行研究",
        "prior art",
        "experiment result",
        "experiment report",
        "experiment lifecycle",
        "html eval report",
        "実験結果",
        "paper draft",
        "thesis chapter",
        "scholarly note",
        "投稿論文",
        "論文",
        "academic writing",
    ),
    "routing-only-advisory": (
        "実装しないで",
        "patch しないで",
        "相談だけ",
        "advisory",
        "どのスキル",
        "which workflow",
    ),
    "scoped-change": ("public behavior", "bounded behavior", "regression case", "cross-module", "bounded scope", "仕様解釈", "既存テスト"),
    "owner-bounded-change": ("owner-bounded-change", "bounded fix", "bounded patch", "one-file", "単一 file", "typo", "flaky test", "責務境界が閉じた", "責務境界が閉じた修正"),
}
TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "agent-canon-cli": (
        "agent-canon docs",
        "docs check",
        "docs format",
        "docs fix-math",
        "docs fix-mermaid",
        "docs-check",
        "markdownlint",
        "agentcanon 最新",
        "checkout drift",
        "agent-canon pr",
    ),
    "audit_and_fix_links.py": ("audit_and_fix_links.py", "broken link", "リンク切れ"),
    "evaluate_skill_workflow_prompts.py": ("evaluate_skill_workflow_prompts.py", "skill workflow eval", "prompt eval"),
    "evaluate_workflow_selection.py": ("evaluate_workflow_selection.py", "workflow selection eval", "routing eval"),
    "generate_agent_improvement_guide.py": ("improvement guide", "改善指南", "githubaction"),
    "generate_agent_runtime_dashboard.py": (
        "generate_agent_runtime_dashboard.py",
        "runtime dashboard",
        "agent dashboard",
        "dashboard",
    ),
    "log_surface_inventory.py": ("ログ項目", "log surface", "hook log"),
    "run_repo_dependency_review.sh": ("run_repo_dependency_review.sh", "dependency review", "dependency graph"),
    "runtime_log_archive_git.py": (
        "runtime_log_archive_git.py",
        "agent report archive",
        "runbundle archive",
        "archive path",
    ),
    "behavior_event_assembly.py": ("入力プロンプト", "prompt", "behavior event", "behavior_events"),
    "tool_rejection_preflight.py": ("tool rejection", "preflight", "はじかれる"),
    "workflow_monitor.py": ("workflow_monitor", "runtime-feedback", "runtime feedback"),
}
SHELL_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
SUBAGENT_TOOL_ACTIONS: dict[str, str] = {
    "task": "spawn",
    "spawn_agent": "spawn",
    "send_input": "send_input",
    "wait_agent": "wait",
    "close_agent": "close",
    "resume_agent": "resume",
}
PROMPT_EXCERPT_LIMIT = 600
PROMPT_FINGERPRINT_HEX_LENGTH = 16
SECRET_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----.*?-----END [^-]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"), "[REDACTED_API_KEY]"),
)
FEEDBACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "quality_gap": ("弱い", "足り", "浅い", "甘い", "まずい", "だめ", "ダメ"),
    "repair_request": ("直して", "修正", "改善", "見直", "組み込み", "入れたい"),
    "missing_mechanism": ("機構", "仕組み", "メカニズム", "ログに積む"),
}

DEFAULT_SKILLS: FrozenSet[str] = frozenset(SKILL_KEYWORDS)


@dataclass(frozen=True)
class PromptClassifierInputs:
    prompt: str
    repo_root: Path
    catalog: FrozenMapping
    routing_rules: FrozenMapping
    structural_lane_evidence: tuple[SkillLaneEvidence, ...] = ()
    validation_repair_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptIntakeSignals:
    skills: tuple[str, ...] = ()
    selected_workflows: tuple[str, ...] = ()
    candidate_skills: tuple[str, ...] = ()
    candidate_skill_reasons: tuple[str, ...] = ()
    candidate_workflows: tuple[str, ...] = ()
    candidate_tools: tuple[str, ...] = ()
    feedback_labels: tuple[str, ...] = ()
    feedback_action: str = ""

    def should_log(self) -> bool:
        return bool(
            self.skills
            or self.selected_workflows
            or self.candidate_skills
            or self.candidate_workflows
            or self.candidate_tools
            or self.feedback_labels
        )

    def feedback_targets(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.feedback_labels))


def freeze(value: object) -> FrozenValue:
    """Recursively freeze caller-provided data without reading it from disk."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in value.items()})  # type: ignore[return-value]
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        result: list[str] = []
        for item in value.values():
            result.extend(_strings(item))
        return tuple(result)
    if isinstance(value, (tuple, list)):
        result = []
        for item in value:
            result.extend(_strings(item))
        return tuple(result)
    return ()


def _catalog_skill_ids(inputs: PromptClassifierInputs) -> frozenset[str]:
    values = {value for value in _strings(inputs.catalog) if SKILL_ID_RE.fullmatch(value)}
    return frozenset(values | set(DEFAULT_SKILLS))


def _field_values(prompt: str) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for match in FIELD_RE.finditer(prompt):
        values.setdefault(match.group(1), []).append(match.group(2).strip("[](),"))
    return {key: tuple(item for item in items if item) for key, items in values.items()}


def _split_values(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in re.split(r"[,;]", value) if part.strip())
    return tuple(dict.fromkeys(result))


def _known_skill(value: str, known: frozenset[str]) -> bool:
    return value in known or value in DEFAULT_SKILLS


def _keyword_matches(
    mapping: Mapping[str, tuple[tuple[str, ...], ...]], text: str
) -> tuple[str, ...]:
    return tuple(
        key
        for key, groups in mapping.items()
        if any(all(needle.casefold() in text for needle in group) for group in groups)
    )


def _simple_keyword_matches(mapping: Mapping[str, tuple[str, ...]], text: str) -> tuple[str, ...]:
    return tuple(key for key, needles in mapping.items() if any(needle.casefold() in text for needle in needles))


def prompt_intake_signals(inputs: PromptClassifierInputs) -> PromptIntakeSignals:
    """Classify one immutable prompt input into the eight parity fields."""
    prompt = inputs.prompt if isinstance(inputs.prompt, str) else ""
    lowered = prompt.casefold()
    fields = _field_values(prompt)
    known = _catalog_skill_ids(inputs)
    skills: list[str] = []
    for value in _split_values(fields.get("skill", ()) + fields.get("skills", ()) + fields.get("skill_invocation", ())):
        value = value.removeprefix("$")
        if _known_skill(value, known):
            skills.append(value)
    for value in SKILL_TOKEN_RE.findall(prompt):
        if _known_skill(value, known):
            skills.append(value)
    selected_workflows = list(_split_values(fields.get("workflow", ()) + fields.get("workflow_family", ()) + fields.get("selected_workflow", ())))
    selected_workflows = [value for value in selected_workflows if value and not value.startswith("$")]
    candidate_skills: list[str] = []
    reasons: list[str] = []
    for skill in DEFAULT_SKILLS:
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(skill)}(?![A-Za-z0-9_-])", lowered):
            skills.append(skill)
    for skill in _keyword_matches(SKILL_KEYWORDS, lowered):
        if skill not in skills:
            candidate_skills.append(skill)
            reasons.append(f"{skill}:keyword")
    for lane in inputs.structural_lane_evidence:
        if lane.status not in {"observed", "candidate"}:
            continue
        reasons.append("structural_concept=" + lane.lane)
        destination = skills if lane.status == "observed" else candidate_skills
        destination.extend(lane.route_skills)
    for evidence in inputs.validation_repair_evidence:
        if evidence:
            reasons.append("validation_repair=" + evidence)
    candidate_skills.extend(_split_values(fields.get("candidate_skill", ()) + fields.get("candidate_skills", ())))
    candidate_workflows = list(_split_values(fields.get("candidate_workflow", ()) + fields.get("candidate_workflows", ())))
    candidate_workflows.extend(_simple_keyword_matches(WORKFLOW_KEYWORDS, lowered))
    candidate_tools = list(_split_values(fields.get("candidate_tool", ()) + fields.get("candidate_tools", ()) + fields.get("tool", ())))
    candidate_tools.extend(_simple_keyword_matches(TOOL_KEYWORDS, lowered))
    feedback_labels = list(_split_values(fields.get("feedback", ()) + fields.get("feedback_label", ()) + fields.get("feedback_labels", ())))
    feedback_action = next(iter(_split_values(fields.get("feedback_action", ()))), "")
    return PromptIntakeSignals(
        skills=tuple(dict.fromkeys(skills)),
        selected_workflows=tuple(dict.fromkeys(selected_workflows)),
        candidate_skills=tuple(dict.fromkeys(item for item in candidate_skills if item not in skills)),
        candidate_skill_reasons=tuple(dict.fromkeys(reasons)),
        candidate_workflows=tuple(dict.fromkeys(candidate_workflows)),
        candidate_tools=tuple(dict.fromkeys(candidate_tools)),
        feedback_labels=tuple(dict.fromkeys(feedback_labels)),
        feedback_action=feedback_action,
    )


def feedback_targets(signals: PromptIntakeSignals) -> tuple[str, ...]:
    return signals.feedback_targets()


def should_log(signals: PromptIntakeSignals) -> bool:
    return signals.should_log()
