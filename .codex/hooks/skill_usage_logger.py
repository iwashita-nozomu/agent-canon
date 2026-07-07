#!/usr/bin/env python3
# @dependency-start
# contract agent-runtime
# responsibility Logs Codex skill, workflow, tool, and subagent routing signals from hook payloads.
# upstream implementation ../hooks.json invokes this hook at prompt and stop boundaries.
# upstream design ../../evidence/agent-evals/README.md requires skill-use eval evidence.
# upstream design ../../agents/skills/codex-task-workflow.md Codex task workflow routing boundary.
# upstream implementation ./hook_event_log.py assigns Canon-owned hook log paths and IDs.
# downstream implementation ../../tests/agent_tools/test_codex_hooks.py validates hook logging.
# @dependency-end

"""Append local JSONL records for skill usage observed by Codex hooks."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

AGENT_TOOLS_ROOT = Path(__file__).resolve().parents[2] / "tools" / "agent_tools"

LOG_PATH_ENV = "AGENT_CANON_SKILL_LOG_PATH"
CONTEXT_PATH_ENV = "AGENT_CANON_SKILL_CONTEXT_PATH"
WORKFLOW_MONITOR_REPORT_DIR_ENV = "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR"
ACTIVE_RUN_POINTER_ENV = "AGENT_CANON_ACTIVE_RUN_POINTER"
DISABLE_LOG_ENV = "AGENT_CANON_DISABLE_HOOK_LOG"
BASE_EXECUTION_SKILL_REASON = "repo-changing execution stage selects base workflow skill"
SKILL_TOKEN_RE = re.compile(r"\$([A-Za-z0-9][A-Za-z0-9_-]*)")
SKILLS_FIELD_RE = re.compile(r"(?:^|\s)(?:skills|skill_invocation)=([^\s]+)")
WORKFLOW_FIELD_RE = re.compile(
    r"(?:^|[^A-Za-z0-9_-])(?:workflow|workflow_family|selected_workflow)="
    r"([^\n\r]+?)(?=\s+(?:skills|skill_invocation|review|status|source|request_kind|"
    r"tool_preflight_required|mcp_inventory_required)=|$)"
)
SKILL_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
IGNORED_SKILL_IDS = frozenset(("skill-name",))
EXTERNAL_SKILL_IDS = frozenset(
    (
        "empirical-prompt-tuning",
        "imagegen",
        "openai-docs",
        "plugin-creator",
        "skill-creator",
        "skill-installer",
    )
)


def repo_skill_ids() -> frozenset[str]:
    """Return current AgentCanon skill ids from discoverable skill shims."""
    skills_root = Path(__file__).resolve().parents[2] / ".agents" / "skills"
    try:
        return frozenset(
            path.name
            for path in skills_root.iterdir()
            if path.is_dir() and SKILL_ID_RE.fullmatch(path.name)
        )
    except OSError:
        return frozenset()


KNOWN_SKILL_IDS = repo_skill_ids() | EXTERNAL_SKILL_IDS
GIT_ROOT_TIMEOUT_SECONDS = 5
SKILL_KEYWORD_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
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
        ("goal.md", "backlog"),
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
        ("agent-canon-ensure-latest",),
        ("vendor/agent-canon",),
        ("update_agent_canon.sh",),
        ("sync_agent_canon.sh",),
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
        ("run_docs_checks.sh",),
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
        ("experiment",),
        ("実験",),
        ("run", "result"),
        ("benchmark", "result"),
        ("再現", "実験"),
    ),
    "html-experiment-report": (
        ("html", "experiment"),
        ("html", "eval report"),
        ("ブラウザ", "実験"),
        ("browser-readable", "experiment"),
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
    "adaptive-improvement-loop": ("goal.md", "next_action", "backlog", "iteration", "改善ループ"),
    "agent-canon-pr-workflow": (
        "agent-canon pr",
        "agent-canon-ensure-latest",
        "vendor/agent-canon",
        "submodule pin",
        "agentcanon 最新",
        "parent pin",
        "sync_agent_canon.sh",
        "pull request",
        "pr #",
        "マージ",
        "merge",
    ),
    "agent-canon-update-route": ("agent-canon-ensure-latest", "vendor/agent-canon", "submodule pin", "親 pin", "agentcanon 最新"),
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
        "run_docs_checks.sh",
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
        "run_docs_checks.sh",
        "docs-check",
        "markdownlint",
        "agent-canon-ensure-latest",
        "sync_agent_canon.sh",
        "agentcanon 最新",
        "parent pin",
        "checkout drift",
        "agent-canon pr",
    ),
    "audit_and_fix_links.py": ("audit_and_fix_links.py", "broken link", "リンク切れ"),
    "docs check": ("docs check", "markdownlint", "markdown math"),
    "evaluate_skill_workflow_prompts.py": ("evaluate_skill_workflow_prompts.py", "skill workflow eval", "prompt eval"),
    "evaluate_workflow_selection.py": ("evaluate_workflow_selection.py", "workflow selection eval", "routing eval"),
    "docs format": ("docs format", "markdown format"),
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
    "skill_usage_logger.py": ("入力プロンプト", "prompt", "skill usage", "skill_usage"),
    "tool_rejection_preflight.py": ("tool rejection", "preflight", "はじかれる"),
    "workflow_monitor.py": ("workflow_monitor", "runtime-feedback", "runtime feedback"),
}
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
SKILL_TEXT_FIELDS = ("prompt", "last_assistant_message", "message")
ROUTING_CANDIDATE_TEXT_FIELDS = ("prompt",)
OBSERVED_TEXT_FIELDS = (*SKILL_TEXT_FIELDS, "tool_input")


def ensure_agent_tools_import_path() -> None:
    """Ensure local AgentCanon tools are importable when the hook runs directly."""
    if str(AGENT_TOOLS_ROOT) not in sys.path:
        sys.path.insert(0, str(AGENT_TOOLS_ROOT))


def hook_log_context_class() -> type:
    """Return HookLogContext from the local AgentCanon tool module."""
    ensure_agent_tools_import_path()
    from hook_event_log import HookLogContext

    return HookLogContext


def fingerprint_json_value(value: object) -> str:
    """Return the canonical hook-log fingerprint for one JSON-like value."""
    ensure_agent_tools_import_path()
    from hook_event_log import fingerprint_json

    return fingerprint_json(value)


def utc_now_value() -> str:
    """Return the canonical hook-log UTC timestamp."""
    ensure_agent_tools_import_path()
    from hook_event_log import utc_now

    return utc_now()


@dataclass(frozen=True)
class PromptIntakeSignals:
    """Classified prompt signals written by the skill usage hook."""

    skills: tuple[str, ...]
    selected_workflows: tuple[str, ...]
    candidate_skills: tuple[str, ...]
    candidate_skill_reasons: tuple[str, ...]
    candidate_workflows: tuple[str, ...]
    candidate_tools: tuple[str, ...]
    feedback_labels: tuple[str, ...]
    feedback_action: str

    def should_log(self) -> bool:
        """Return whether this payload contains durable prompt-intake evidence."""
        return bool(
            self.skills
            or self.selected_workflows
            or self.candidate_skills
            or self.candidate_skill_reasons
            or self.candidate_workflows
            or self.candidate_tools
            or self.feedback_labels
        )

    def feedback_targets(self) -> tuple[str, ...]:
        """Return concrete feedback targets for workflow monitor routing."""
        skill_targets = tuple(sorted(set(self.skills + self.candidate_skills)))
        targets = [
            *(f"skill:{item}" for item in skill_targets),
            *(f"workflow:{item}" for item in self.candidate_workflows),
            *(f"tool:{item}" for item in self.candidate_tools),
        ]
        return tuple(targets or (("agent-runtime",) if self.feedback_labels else ()))


@dataclass(frozen=True)
class PromptCapture:
    """Bounded prompt text capture for later routing analysis."""

    status: str
    excerpt_redacted: str
    fingerprint: str
    char_count: int
    truncated: bool

    def should_log(self) -> bool:
        """Return whether prompt evidence exists."""
        return self.status == "present"


@dataclass(frozen=True)
class ToolSelection:
    """PostToolUse tool selection evidence."""

    tool_name: str
    tool_input_fingerprint: str
    tool_input_key_count: int
    tool_input_keys: tuple[str, ...]
    command_verb: str
    selected_tools: tuple[str, ...]

    def should_log(self) -> bool:
        """Return whether tool selection evidence exists."""
        return bool(self.tool_name)


@dataclass(frozen=True)
class SubagentSelection:
    """PostToolUse subagent lifecycle evidence."""

    invoked: bool
    action: str
    tool_name: str
    agent_type: str
    target: str
    targets: tuple[str, ...]
    model: str
    reasoning_effort: str
    fork_context: bool
    prompt_fingerprint: str
    prompt_char_count: int
    item_count: int

    def should_log(self) -> bool:
        """Return whether this payload represents subagent activity."""
        return self.invoked


@dataclass(frozen=True)
class WorkflowContext:
    """Short-lived workflow context inherited by later hook events."""

    workflows: tuple[str, ...]
    report_dir: str
    timestamp: str
    source_event: str

    def has_workflow(self) -> bool:
        """Return whether this context contains workflow attribution."""
        return bool(self.workflows)


@dataclass(frozen=True)
class SkillUsageLogInputs:
    """Grouped inputs for one skill usage log append."""

    payload: dict[str, object]
    root: Path
    signals: PromptIntakeSignals
    prompt: PromptCapture
    tool: ToolSelection
    subagent: SubagentSelection
    workflow_context: WorkflowContext
    workflow_context_kind: str
    workflow_event_count: int
    workflow_feedback_count: int
    workflow_subagent_event_count: int


def load_payload() -> dict[str, object]:
    """Read one JSON hook payload from stdin."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def repo_root() -> Path:
    """Resolve the active repository root for hook logs."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def hook_event_name(payload: dict[str, object]) -> str:
    """Return the hook event name."""
    value = payload.get("hookEventName")
    return value if isinstance(value, str) and value else "UnknownHookEvent"


def text_values(value: object) -> list[str]:
    """Return text leaves from nested hook payload data."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for child in value.values():
            values.extend(text_values(child))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for child in value:
            values.extend(text_values(child))
        return values
    return []


def known_skill_id_mentioned(text: str, skill: str) -> bool:
    """Return whether prompt text explicitly names one known public skill id."""
    return (
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(skill)}(?![A-Za-z0-9_-])",
            text.lower(),
        )
        is not None
    )


def extract_skill_ids(text: str, *, include_plain_names: bool = False) -> set[str]:
    """Extract normalized skill ids from one text payload."""
    skills = {match.group(1).strip("-_") for match in SKILL_TOKEN_RE.finditer(text)}
    for match in SKILLS_FIELD_RE.finditer(text):
        raw_values = match.group(1).split(",")
        for raw_value in raw_values:
            value = raw_value.strip().strip("`'\"[](){}")
            value = value.removeprefix("$").strip("-_")
            if value and value != "-":
                skills.add(value)
    if include_plain_names:
        for skill in KNOWN_SKILL_IDS:
            if known_skill_id_mentioned(text, skill):
                skills.add(skill)
    return {
        skill
        for skill in skills
        if SKILL_ID_RE.fullmatch(skill)
        and skill not in IGNORED_SKILL_IDS
        and skill in KNOWN_SKILL_IDS
    }


def clean_routing_value(value: str) -> str:
    """Return a display-safe routing field value."""
    return value.strip().strip("`'\"[](){}<>.,;")


def extract_workflow_names(text: str) -> set[str]:
    """Extract declared workflow names from one text payload."""
    workflows: set[str] = set()
    for match in WORKFLOW_FIELD_RE.finditer(text):
        for raw_value in re.split(r"[,;|]", match.group(1)):
            value = clean_routing_value(raw_value)
            if value and value.casefold() not in {"family", "unspecified"}:
                workflows.add(value)
    return workflows


def observed_text_for_fields(payload: dict[str, object], fields: tuple[str, ...]) -> list[str]:
    """Return hook payload text fields from selected payload keys."""
    texts: list[str] = []
    for key in fields:
        if key in payload:
            texts.extend(text_values(payload[key]))
    return texts


def observed_text(payload: dict[str, object]) -> list[str]:
    """Return hook payload text fields relevant for general evidence discovery."""
    return observed_text_for_fields(payload, OBSERVED_TEXT_FIELDS)


def observed_skill_text(payload: dict[str, object]) -> list[str]:
    """Return text fields trusted for explicit skill and workflow declarations."""
    return observed_text_for_fields(payload, SKILL_TEXT_FIELDS)


def observed_routing_candidate_text(payload: dict[str, object]) -> list[str]:
    """Return text fields trusted for prompt-derived routing candidates."""
    return observed_text_for_fields(payload, ROUTING_CANDIDATE_TEXT_FIELDS)


def prompt_text(payload: dict[str, object]) -> str:
    """Return the raw UserPromptSubmit prompt text when present."""
    value = payload.get("prompt")
    return value if isinstance(value, str) else ""


def prompt_capture(payload: dict[str, object]) -> PromptCapture:
    """Return bounded redacted prompt evidence."""
    text = prompt_text(payload)
    if not text:
        return PromptCapture("missing", "", "", 0, False)
    redacted = redact_sensitive_text(text)
    excerpt = redacted[:PROMPT_EXCERPT_LIMIT]
    return PromptCapture(
        status="present",
        excerpt_redacted=excerpt,
        fingerprint=sha256(text.encode("utf-8")).hexdigest()[:PROMPT_FINGERPRINT_HEX_LENGTH],
        char_count=len(text),
        truncated=len(redacted) > PROMPT_EXCERPT_LIMIT,
    )


def redact_sensitive_text(text: str) -> str:
    """Redact high-confidence secret-like values from prompt excerpts."""
    redacted = text
    for pattern, replacement in SECRET_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def observed_text_sources(payload: dict[str, object]) -> list[str]:
    """Return payload field names that contributed text for skill discovery."""
    sources: list[str] = []
    for key in ("prompt", "last_assistant_message", "message", "tool_input"):
        if key in payload and text_values(payload[key]):
            sources.append(key)
    return sources


def observed_skills(payload: dict[str, object]) -> list[str]:
    """Return sorted unique skill ids observed in a hook payload."""
    skills: set[str] = set()
    for key in SKILL_TEXT_FIELDS:
        for text in text_values(payload.get(key)):
            skills.update(extract_skill_ids(text, include_plain_names=key == "prompt"))
    return sorted(skills)


def observed_workflows(payload: dict[str, object]) -> list[str]:
    """Return sorted unique declared workflow names observed in a hook payload."""
    workflows: set[str] = set()
    for text in observed_skill_text(payload):
        workflows.update(extract_workflow_names(text))
    return sorted(workflows)


def keyword_matches(texts: list[str], mapping: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Return mapping keys whose keywords appear in observed prompt text."""
    haystack = "\n".join(texts).lower()
    return tuple(
        key
        for key, needles in sorted(mapping.items())
        if any(needle.lower() in haystack for needle in needles)
    )


def grouped_keyword_matches(
    texts: list[str],
    mapping: dict[str, tuple[tuple[str, ...], ...]],
) -> tuple[str, ...]:
    """Return keys whose keyword groups all appear in observed prompt text."""
    haystack = "\n".join(texts).lower()
    return tuple(
        key
        for key, groups in sorted(mapping.items())
        if any(all(needle.lower() in haystack for needle in group) for group in groups)
    )


def structural_candidate_skill_reasons(
    texts: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return candidate skills and reasons from route-owned structural concepts."""
    ensure_agent_tools_import_path()
    from skill_lane_detector import structural_skill_lane_concept_matches

    skills: list[str] = []
    reasons: list[str] = []
    haystack = "\n".join(texts)
    for match in structural_skill_lane_concept_matches(haystack):
        reason = match.reason()
        for skill in match.concept.route_skills:
            skills.append(skill)
            reasons.append(f"{skill}:{reason}")
    return tuple(dict.fromkeys(skills)), tuple(dict.fromkeys(reasons))


def validation_repair_candidate_skill_reasons(
    texts: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return candidate skills and reasons from validation repair concepts."""
    ensure_agent_tools_import_path()
    from skill_lane_detector import validation_failure_repair_concept_matches

    skills: list[str] = []
    reasons: list[str] = []
    haystack = "\n".join(texts)
    for match in validation_failure_repair_concept_matches(haystack):
        skill = match.concept.owner_skill
        skills.append(skill)
        reasons.append(f"{skill}:{match.reason()}")
    return tuple(dict.fromkeys(skills)), tuple(dict.fromkeys(reasons))


def catalog_candidate_skill_reasons(
    root: Path,
    texts: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return route.py catalog-backed prompt skill candidates."""
    haystack = "\n".join(texts)
    if not haystack.strip():
        return (), ()
    ensure_agent_tools_import_path()
    from route import decide_skills, load_skill_route_rules

    catalog_root = root
    if not (catalog_root / "agents" / "skills" / "catalog.yaml").is_file():
        catalog_root = Path(__file__).resolve().parents[2]
    decision = decide_skills(haystack, "routing-only", load_skill_route_rules(catalog_root))
    base_execution_skills = (
        ("codex-task-workflow",)
        if decision.mode == "repo-changing" and "codex-task-workflow" in decision.skills
        else ()
    )
    skills = tuple(
        dict.fromkeys(
            (
                *base_execution_skills,
                *decision.matched_skills,
                *decision.related_skill_candidates,
            )
        )
    )
    base_reasons = tuple(
        f"{skill}:{BASE_EXECUTION_SKILL_REASON}"
        for skill in base_execution_skills
    )
    related_reasons = tuple(
        f"{related}:related_to={source}"
        for source, related_skills in decision.related_skills.items()
        for related in related_skills
    )
    return skills, (*base_reasons, *decision.reasons, *related_reasons)


def feedback_action(labels: tuple[str, ...]) -> str:
    """Return the workflow-monitor action for observed human feedback."""
    if not labels:
        return ""
    if "quality_gap" in labels or "repair_request" in labels:
        return "prompt_repair"
    return "memory_record"


def prompt_intake_signals(payload: dict[str, object]) -> PromptIntakeSignals:
    """Classify prompt text into explicit and candidate routing signals."""
    skill_texts = observed_skill_text(payload)
    candidate_texts = observed_routing_candidate_text(payload)
    skills = tuple(observed_skills(payload))
    labels = keyword_matches(skill_texts, FEEDBACK_KEYWORDS)
    catalog_skills, catalog_reasons = catalog_candidate_skill_reasons(repo_root(), candidate_texts)
    selected_skill_set = set(skills)
    if selected_skill_set:
        catalog_skills = tuple(
            dict.fromkeys(
                reason.split(":", 1)[0]
                for reason in catalog_reasons
                if reason.split(":", 1)[0] not in selected_skill_set
                and reason.split(":", 1)[1] != BASE_EXECUTION_SKILL_REASON
                and not any(
                    f"related_to={selected_skill}" in reason
                    for selected_skill in selected_skill_set
                )
            )
        )
    candidate_skills = tuple(
        dict.fromkeys(
            skill
            for skill in catalog_skills
            if skill not in skills
        )
    )
    raw_candidate_skill_reasons = tuple(
        dict.fromkeys(
            catalog_reasons
        )
    )
    candidate_skill_set = set(candidate_skills)
    candidate_skill_reasons = tuple(
        reason
        for reason in raw_candidate_skill_reasons
        if reason.split(":", 1)[0] in candidate_skill_set
    )
    return PromptIntakeSignals(
        skills=skills,
        selected_workflows=tuple(observed_workflows(payload)),
        candidate_skills=candidate_skills,
        candidate_skill_reasons=candidate_skill_reasons,
        candidate_workflows=keyword_matches(skill_texts, WORKFLOW_KEYWORDS),
        candidate_tools=keyword_matches(candidate_texts, TOOL_KEYWORDS),
        feedback_labels=labels,
        feedback_action=feedback_action(labels),
    )


def tool_selection(payload: dict[str, object]) -> ToolSelection:
    """Return PostToolUse tool selection evidence."""
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    keys = tuple(sorted(tool_input.keys())) if isinstance(tool_input, dict) else ()
    return ToolSelection(
        tool_name=tool_name,
        tool_input_fingerprint=fingerprint_json_value(tool_input) if tool_input is not None else "",
        tool_input_key_count=len(keys),
        tool_input_keys=keys,
        command_verb=command_verb(tool_input),
        selected_tools=command_selected_tools(tool_input),
    )


def normalized_tool_name(tool_name: str) -> str:
    """Return a normalized tool name without namespace prefixes."""
    normalized = tool_name.strip()
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    return normalized


def tool_input_dict(payload: dict[str, object]) -> dict[str, object]:
    """Return the tool input object when it is a mapping."""
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def string_input_field(tool_input: dict[str, object], *keys: str) -> str:
    """Return the first non-empty string value from tool input keys."""
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def string_sequence_input_field(tool_input: dict[str, object], *keys: str) -> tuple[str, ...]:
    """Return string values from the first list-like tool input key."""
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, list):
            return tuple(item for item in value if isinstance(item, str) and item)
    return ()


def subagent_prompt_text(tool_input: dict[str, object]) -> str:
    """Return subagent prompt-like text for fingerprint-only logging."""
    value = tool_input.get("message")
    if isinstance(value, str):
        return value
    return "\n".join(text_values(tool_input.get("items")))


def subagent_selection(payload: dict[str, object]) -> SubagentSelection:
    """Return subagent selection or lifecycle evidence from a PostToolUse payload."""
    tool_name = str(payload.get("tool_name") or "")
    normalized_name = normalized_tool_name(tool_name).casefold()
    tool_input = tool_input_dict(payload)
    action = SUBAGENT_TOOL_ACTIONS.get(normalized_name, "")
    prompt = subagent_prompt_text(tool_input)
    targets = string_sequence_input_field(tool_input, "targets")
    target = string_input_field(tool_input, "target", "id")
    return SubagentSelection(
        invoked=bool(action),
        action=action,
        tool_name=tool_name,
        agent_type=string_input_field(tool_input, "agent_type", "subagent_type"),
        target=target,
        targets=targets,
        model=string_input_field(tool_input, "model"),
        reasoning_effort=string_input_field(tool_input, "reasoning_effort"),
        fork_context=tool_input.get("fork_context") is True,
        prompt_fingerprint=(
            sha256(prompt.encode("utf-8")).hexdigest()[:PROMPT_FINGERPRINT_HEX_LENGTH]
            if prompt
            else ""
        ),
        prompt_char_count=len(prompt),
        item_count=len(tool_input.get("items")) if isinstance(tool_input.get("items"), list) else 0,
    )


def command_verb(tool_input: object) -> str:
    """Return the first command token for shell-like tool input."""
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return ""
    return command.strip().split()[0]


def command_selected_tools(tool_input: object) -> tuple[str, ...]:
    """Return repo tool script names observed in shell-like tool input."""
    if not isinstance(tool_input, dict):
        return ()
    command = tool_input.get("cmd") or tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return ()
    try:
        parts = tuple(part for part in shlex.split(command) if part)
    except ValueError:
        parts = tuple(command.strip().split())
    observed: list[str] = []
    for index, part in enumerate(parts):
        name = Path(part).name
        if name == "agent-canon" and parts[index + 1 : index + 2] == ("docs",):
            observed.append("agent-canon-cli")
            continue
        if index == 0 and name in TOOL_KEYWORDS:
            observed.append(name)
        if repo_tool_path_part(part) and name in TOOL_KEYWORDS:
            observed.append(name)
    return tuple(dict.fromkeys(observed))


def repo_tool_path_part(part: str) -> bool:
    """Return whether one shell token is an executable repo tool path."""
    executable_repo_path = "tools/" in part or ".codex/hooks/" in part
    return executable_repo_path and (
        part.endswith((".py", ".sh")) or part.endswith("tools/bin/agent-canon")
    )


def default_log_path(root: Path) -> Path:
    """Return the skill usage log path."""
    override = os.environ.get(LOG_PATH_ENV, "").strip()
    return hook_log_context_class()(root, "skill_usage", override).result_path()


def default_context_path(root: Path) -> Path:
    """Return the workflow context path paired with the skill usage log."""
    override = os.environ.get(CONTEXT_PATH_ENV, "").strip()
    if override:
        return Path(override)
    return default_log_path(root).with_name("skill_usage_context.json")


def load_workflow_context(root: Path) -> WorkflowContext:
    """Load inherited workflow context for later tool and subagent events."""
    path = default_context_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WorkflowContext((), "", "", "")
    if not isinstance(value, dict):
        return WorkflowContext((), "", "", "")
    workflows = tuple(
        item for item in value.get("workflows", []) if isinstance(item, str) and item
    )
    report_dir = value.get("report_dir")
    timestamp = value.get("timestamp")
    source_event = value.get("source_event")
    return WorkflowContext(
        workflows=workflows,
        report_dir=report_dir if isinstance(report_dir, str) else "",
        timestamp=timestamp if isinstance(timestamp, str) else "",
        source_event=source_event if isinstance(source_event, str) else "",
    )


def save_workflow_context(
    root: Path,
    signals: PromptIntakeSignals,
    payload: dict[str, object],
) -> None:
    """Persist workflow attribution for following PostToolUse events."""
    report_dir = workflow_monitor_report_dir(root)
    if not signals.selected_workflows and not report_dir:
        return
    context = {
        "workflows": list(signals.selected_workflows),
        "report_dir": report_dir,
        "timestamp": utc_now_value(),
        "source_event": hook_event_name(payload),
    }
    path = default_context_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(context, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return


def signals_with_workflow_context(
    signals: PromptIntakeSignals,
    context: WorkflowContext,
) -> tuple[PromptIntakeSignals, str]:
    """Return effective signals plus declared/inherited workflow attribution kind."""
    if signals.selected_workflows:
        return signals, "declared_workflow"
    if context.has_workflow():
        kind = (
            "inherited_workflow"
            if os.environ.get(CONTEXT_PATH_ENV, "").strip()
            else "context_workflow"
        )
        return (
            replace(signals, selected_workflows=context.workflows),
            kind,
        )
    return signals, ""


def _log_append_log(root: Path, entry: dict[str, object]) -> None:
    """Append one skill usage JSONL entry without blocking runtime progress."""
    if os.environ.get(DISABLE_LOG_ENV, "").strip() == "1":
        return
    try:
        context = hook_log_context_class()(root, "skill_usage", os.environ.get(LOG_PATH_ENV, "").strip())
        context.append(entry)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return


def workflow_monitor_path(root: Path) -> Path:
    """Return the canonical workflow monitor tool path."""
    return root / "tools" / "agent_tools" / "workflow_monitor.py"


def workflow_monitor_report_dir(root: Path | None = None) -> str:
    """Return the optional run-bundle report dir for behavior evidence."""
    explicit = os.environ.get(WORKFLOW_MONITOR_REPORT_DIR_ENV, "").strip()
    if explicit:
        return explicit
    if root is None:
        return ""
    pointer = os.environ.get(ACTIVE_RUN_POINTER_ENV, "").strip()
    pointer_path = Path(pointer) if pointer else default_active_run_pointer(root)
    try:
        value = pointer_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not value:
        return ""
    report_dir = Path(value)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    if (report_dir / "workflow_monitoring.md").is_file():
        return str(report_dir)
    return ""


def default_active_run_pointer(root: Path) -> Path:
    """Return the run pointer that should own hook workflow evidence."""
    parent_pointer = vendored_agent_canon_parent_pointer(root)
    if parent_pointer is not None:
        return parent_pointer
    return root / "reports" / "agents" / ".active_run"


def vendored_agent_canon_parent_pointer(root: Path) -> Path | None:
    """Return the parent repo active-run pointer for vendored AgentCanon checkouts."""
    resolved = root.resolve()
    if resolved.name != "agent-canon" or resolved.parent.name != "vendor":
        return None
    pointer = resolved.parent.parent / "reports" / "agents" / ".active_run"
    return pointer if pointer.is_file() else None


def workflow_monitor_behavior_event(root: Path, report_dir: str, event: str) -> bool:
    """Append one behavior event to the active workflow monitor artifact."""
    monitor = workflow_monitor_path(root)
    if not report_dir or not monitor.is_file():
        return False
    result = subprocess.run(
        [
            sys.executable,
            str(monitor),
            "--report-dir",
            report_dir,
            "--behavior-event",
            event,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    return result.returncode == 0


def workflow_monitor_runtime_feedback(root: Path, report_dir: str, event: str) -> bool:
    """Append one runtime feedback event to the active workflow monitor artifact."""
    monitor = workflow_monitor_path(root)
    if not report_dir or not monitor.is_file():
        return False
    result = subprocess.run(
        [
            sys.executable,
            str(monitor),
            "--report-dir",
            report_dir,
            "--runtime-feedback",
            event,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_ROOT_TIMEOUT_SECONDS,
    )
    return result.returncode == 0


def append_workflow_monitor_events(
    root: Path,
    signals: PromptIntakeSignals,
    subagent: SubagentSelection,
) -> tuple[int, int, int]:
    """Append skill invocation and feedback events when a run bundle is active."""
    report_dir = workflow_monitor_report_dir(root)
    if not report_dir or not workflow_monitor_path(root).is_file():
        return 0, 0, 0
    skill_event_count = 0
    feedback_event_count = 0
    subagent_event_count = 0
    for workflow in signals.selected_workflows:
        if workflow_monitor_behavior_event(
            root,
            report_dir,
            f"workflow_selection={workflow} status=observed source=codex_hook",
        ):
            skill_event_count += 1
    for skill in signals.skills:
        if workflow_monitor_behavior_event(
            root,
            report_dir,
            f"skill_invocation=${skill} status=observed source=codex_hook",
        ):
            skill_event_count += 1
    for skill in signals.candidate_skills:
        if skill in signals.skills:
            continue
        if workflow_monitor_behavior_event(
            root,
            report_dir,
            f"skill_candidate=${skill} status=observed source=codex_hook",
        ):
            skill_event_count += 1
    if subagent.should_log():
        if workflow_monitor_behavior_event(root, report_dir, subagent_monitor_event(subagent)):
            subagent_event_count += 1
    if signals.feedback_labels and signals.feedback_action:
        for target in signals.feedback_targets():
            if workflow_monitor_runtime_feedback(
                root,
                report_dir,
                (
                    "source=user "
                    f"target={target} "
                    f"action={signals.feedback_action} "
                    "evidence=codex_prompt_intake"
                ),
            ):
                feedback_event_count += 1
    return skill_event_count, feedback_event_count, subagent_event_count


def subagent_monitor_event(subagent: SubagentSelection) -> str:
    """Return one tokenized subagent lifecycle event for workflow monitoring."""
    targets = ",".join(subagent.targets) if subagent.targets else subagent.target
    target_count = len(subagent.targets) + int(bool(subagent.target))
    return (
        f"subagent_lifecycle_event={subagent.action} "
        f"subagent_tool={subagent.tool_name or 'unknown'} "
        f"subagent_agent_type={subagent.agent_type or 'unknown'} "
        f"subagent_target={targets or 'unknown'} "
        f"subagent_target_count={target_count} "
        f"subagent_model={subagent.model or 'unspecified'} "
        f"subagent_reasoning_effort={subagent.reasoning_effort or 'unspecified'} "
        f"subagent_fork_context={'yes' if subagent.fork_context else 'no'} "
        f"subagent_prompt_fingerprint={subagent.prompt_fingerprint or 'none'} "
        f"subagent_prompt_char_count={subagent.prompt_char_count} "
        f"subagent_item_count={subagent.item_count} "
        "source=codex_hook"
    )


def append_skill_usage_entry(inputs: SkillUsageLogInputs) -> None:
    """Append one skill usage hook log entry."""
    payload = inputs.payload
    signals = inputs.signals
    prompt = inputs.prompt
    tool = inputs.tool
    subagent = inputs.subagent
    workflow_context = inputs.workflow_context
    timestamp = utc_now_value()
    payload_fingerprint = fingerprint_json_value(payload)
    context = hook_log_context_class()(inputs.root, "skill_usage", os.environ.get(LOG_PATH_ENV, "").strip())
    text_sources = observed_text_sources(payload)
    text_values_seen = observed_text(payload)
    _log_append_log(
        inputs.root,
        {
            "hook_run_id": context.run_id(timestamp, payload_fingerprint),
            "hook_log_namespace": context.runtime_namespace(),
            "timestamp": timestamp,
            "event": hook_event_name(payload),
            "event_declared": hook_event_name(payload) != "UnknownHookEvent",
            "skills": list(signals.skills),
            "selected_skills": list(signals.skills),
            "skill_selection_kind": "declared_skill" if signals.skills else "",
            "skill_count": len(signals.skills),
            "selected_workflow": signals.selected_workflows[0] if signals.selected_workflows else "",
            "selected_workflows": list(signals.selected_workflows),
            "workflow": list(signals.selected_workflows),
            "workflow_family": signals.selected_workflows[0] if signals.selected_workflows else "",
            "workflow_selection_kind": inputs.workflow_context_kind,
            "workflow_context_kind": inputs.workflow_context_kind,
            "workflow_context_source": (
                "recent_log" if inputs.workflow_context_kind == "context_workflow" else ""
            ),
            "workflow_context_workflows": list(workflow_context.workflows),
            "workflow_context_timestamp": workflow_context.timestamp,
            "workflow_context_source_event": workflow_context.source_event,
            "selected_workflow_count": len(signals.selected_workflows),
            "candidate_skills": list(signals.candidate_skills),
            "candidate_skill_reasons": list(signals.candidate_skill_reasons),
            "candidate_skill_count": len(signals.candidate_skills),
            "candidate_workflows": list(signals.candidate_workflows),
            "candidate_workflow_count": len(signals.candidate_workflows),
            "candidate_tools": list(signals.candidate_tools),
            "candidate_tool_count": len(signals.candidate_tools),
            "prompt_capture_status": prompt.status,
            "prompt_excerpt_redacted": prompt.excerpt_redacted,
            "prompt_fingerprint": prompt.fingerprint,
            "prompt_char_count": prompt.char_count,
            "prompt_excerpt_truncated": prompt.truncated,
            "tool_name": tool.tool_name,
            "tool_selection_kind": "executed_tool" if tool.should_log() else "",
            "tool_input_fingerprint": tool.tool_input_fingerprint,
            "tool_input_key_count": tool.tool_input_key_count,
            "tool_input_keys": list(tool.tool_input_keys),
            "tool_command_verb": tool.command_verb,
            "selected_tools": list(tool.selected_tools),
            "selected_tool_count": len(tool.selected_tools),
            "subagent_invoked": subagent.invoked,
            "subagent_event_kind": subagent.action,
            "subagent_tool_name": subagent.tool_name,
            "subagent_agent_type": subagent.agent_type,
            "subagent_target": subagent.target,
            "subagent_targets": list(subagent.targets),
            "subagent_target_count": len(subagent.targets) + int(bool(subagent.target)),
            "subagent_model": subagent.model,
            "subagent_reasoning_effort": subagent.reasoning_effort,
            "subagent_fork_context": subagent.fork_context,
            "subagent_prompt_fingerprint": subagent.prompt_fingerprint,
            "subagent_prompt_char_count": subagent.prompt_char_count,
            "subagent_item_count": subagent.item_count,
            "prompt_feedback_detected": bool(signals.feedback_labels),
            "feedback_labels": list(signals.feedback_labels),
            "feedback_targets": list(signals.feedback_targets()),
            "feedback_action": signals.feedback_action,
            "skill_source_fields": text_sources,
            "observed_text_field_count": len(text_sources),
            "observed_text_value_count": len(text_values_seen),
            "payload_key_count": len(payload),
            "payload_fingerprint": payload_fingerprint,
            "status": "pass",
            "workflow_monitor_event_count": inputs.workflow_event_count,
            "workflow_monitor_feedback_count": inputs.workflow_feedback_count,
            "workflow_monitor_subagent_event_count": inputs.workflow_subagent_event_count,
            "workflow_monitor_report_dir": workflow_monitor_report_dir(inputs.root),
            "root": str(inputs.root),
        },
    )


def main() -> int:
    """Append one skill usage hook log entry."""
    payload = load_payload()
    root = repo_root()
    signals = prompt_intake_signals(payload)
    workflow_context = load_workflow_context(root)
    effective_signals, context_kind = signals_with_workflow_context(
        signals,
        workflow_context,
    )
    prompt = prompt_capture(payload)
    tool = tool_selection(payload)
    subagent = subagent_selection(payload)
    if not (signals.should_log() or prompt.should_log() or tool.should_log() or subagent.should_log()):
        return 0
    save_workflow_context(root, signals, payload)
    (
        workflow_event_count,
        workflow_feedback_count,
        workflow_subagent_event_count,
    ) = append_workflow_monitor_events(root, effective_signals, subagent)
    append_skill_usage_entry(
        SkillUsageLogInputs(
            payload=payload,
            root=root,
            signals=effective_signals,
            prompt=prompt,
            tool=tool,
            subagent=subagent,
            workflow_context=workflow_context,
            workflow_context_kind=context_kind,
            workflow_event_count=workflow_event_count,
            workflow_feedback_count=workflow_feedback_count,
            workflow_subagent_event_count=workflow_subagent_event_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
