// @dependency-start
// contract implementation
// responsibility Classifies immutable prompt evidence into workflow, skill, tool, and feedback signals.
// upstream implementation ../../../../../tools/agent/orchestration/prompt_classifier.py owns the current pure API contract.
// upstream implementation ./skill_lane_detector.rs owns structural and validation-repair lane evidence.
// upstream implementation ./python_json.rs owns Python-compatible JSON strings and values.
// upstream implementation ./python_text.rs owns Python-compatible Unicode whitespace.
// downstream implementation ../tests/prompt_classifier_native.rs checks the frozen CPython 3.12.3 classifier corpus.
// downstream evidence ../../../../../tests/fixtures/prompt_classifier/python_golden.json freezes old classifier inputs and outputs.
// @dependency-end
//! Pure prompt-intake classification over caller-injected evidence.

use crate::python_json::{JsonString, JsonValue};
use crate::python_text::is_python_whitespace;
use crate::skill_lane_detector::SkillLaneEvidence;
use icu_casemap::CaseMapper;
use regex::Regex;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::sync::LazyLock;

type SkillKeywordGroup = &'static [&'static str];
type SkillKeywordRule = (&'static str, &'static [SkillKeywordGroup]);
type SimpleKeywordRule = (&'static str, &'static [&'static str]);

const FIELD_NAMES: [&str; 16] = [
    "skill",
    "skills",
    "skill_invocation",
    "workflow",
    "workflow_family",
    "selected_workflow",
    "candidate_skill",
    "candidate_skills",
    "candidate_workflow",
    "candidate_workflows",
    "candidate_tool",
    "candidate_tools",
    "feedback_label",
    "feedback_labels",
    "feedback_action",
    "tool",
];
const FIELD_KEY_PATTERN: &str = r"\A(skills?|skill_invocation|workflow|workflow_family|selected_workflow|candidate_skills?|candidate_workflows?|candidate_tools?|feedback_labels?|feedback_action|tool)\z";
const SKILL_ID_PATTERN: &str = r"\A[a-z][a-z0-9]*(?:-[a-z0-9]+)*\z";
const SKILL_TOKEN_PATTERN: &str = r"\$([A-Za-z0-9][A-Za-z0-9_-]*)";

static FIELD_KEY_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(FIELD_KEY_PATTERN).expect("static field-key regex is valid"));
static SKILL_ID_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(SKILL_ID_PATTERN).expect("static skill-id regex is valid"));
static SKILL_TOKEN_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(SKILL_TOKEN_PATTERN).expect("static skill-token regex is valid"));

const SKILL_KEYWORDS: &[SkillKeywordRule] = &[
    (
        "agent-learning",
        &[
            &["人間からのフィードバック"],
            &["runtime feedback"],
            &["再発防止"],
            &["こういう止まり方"],
            &["フィードバック", "修正"],
            &["feedback", "repair"],
            &["memory", "feedback"],
            &["学習", "agent"],
        ],
    ),
    (
        "agent-orchestration",
        &[
            &["どのスキル"],
            &["どのskill"],
            &["スキル選択"],
            &["skill selection"],
            &["routing", "skill"],
            &["ルーティング", "スキル"],
            &["マルチエージェント"],
            &["サブエージェント", "起動"],
            &["subagent", "routing"],
            &["workflow=", "skills="],
        ],
    ),
    (
        "agent-log-analysis",
        &[
            &["routing miss"],
            &["selection gap"],
            &["generate_agent_runtime_dashboard.py"],
            &["runtime dashboard"],
            &["生ログ", "要約"],
            &["routing", "coverage"],
            &["toolcall", "skillcall", "coverage"],
            &["toolcall", "skillcall", "routing"],
            &["toolcall", "skillcall", "miss"],
            &["toolcall", "skillcall", "50"],
            &["toolcall", "skillcall", "されない"],
            &["ルーティング", "ログ"],
            &["ログ", "skill"],
            &["ログ", "tool"],
            &["toolcall", "skillcall", "ルーティング"],
        ],
    ),
    (
        "adaptive-improvement-loop",
        &[
            &["adaptive-improvement-loop"],
            &["next_action", "iteration"],
            &["改善ループ"],
            &["backlog", "iteration"],
        ],
    ),
    (
        "agent-canon-update",
        &[
            &["agentcanon", "update"],
            &["agent-canon", "update"],
            &["agent-canon pr"],
            &["agentcanon", "latest"],
            &["agent-canon", "latest"],
            &["サブモジュール", "agentcanon"],
            &["agentcanon", "最新"],
            &["agentcanon", "更新"],
        ],
    ),
    (
        "md-style-check",
        &[
            &["md-style"],
            &["docs-check"],
            &["agent-canon", "docs"],
            &["docs", "format"],
            &["docs", "check"],
            &["markdownlint"],
            &["markdown", "lint"],
            &["markdown", "heading"],
            &["markdown", "link"],
            &["markdown", "formatter"],
            &["docs format"],
            &["formatter", "adjacent"],
            &["フォーマッタ"],
            &["フォーマット", "周辺"],
            &["通してすらない"],
            &["マークダウン", "体裁"],
            &["マークダウン", "リンク"],
        ],
    ),
    (
        "computational-optimization",
        &[
            &["computational optimization"],
            &["計算最適化"],
            &["数値最適化"],
            &["optimizer"],
            &["optimization", "solver"],
            &["preconditioner"],
            &["kkt"],
            &["gradient", "hessian"],
            &["jacobian"],
            &["convergence", "tolerance"],
            &["収束", "tolerance"],
            &["solver", "residual"],
            &["residual"],
        ],
    ),
    (
        "gpu-execution",
        &[
            &["gpu", "実行"],
            &["gpu", "利用"],
            &["gpu", "検証"],
            &["cuda", "backend"],
            &["jax", "gpu"],
            &["xla", "gpu"],
            &["nvidia-smi"],
            &["cuda_visible_devices"],
            &["gpu_validation_blocker"],
            &["experimentrunner"],
            &["experiment_runner"],
            &["python", "experimentrunner"],
            &["xla_python_client_preallocate"],
            &["preallocation", "disable"],
            &["先取", "無効"],
            &["先取り", "無効"],
        ],
    ),
    (
        "result-artifact-writeout",
        &[
            &["結果書き出し"],
            &["結果を書き出"],
            &["result writeout"],
            &["runtime_log_archive_git.py"],
            &["artifact", "evidence"],
            &["artifact", "report"],
            &["run bundle", "evidence"],
            &["蓄積分析", "レポート"],
            &["ログ", "レポート", "残"],
        ],
    ),
    (
        "task-routing",
        &[
            &["tool", "skill", "routing"],
            &["tool", "skill", "ルーティング"],
            &["route.py"],
            &["public skill set"],
            &["skill set", "route"],
            &["skill selection"],
            &["workflow routing"],
            &["workflow=", "skills="],
            &["which workflow"],
            &["どのスキル"],
            &["ルーティング"],
        ],
    ),
    (
        "oop-readability-check",
        &[
            &["oop", "readability"],
            &["oop", "可読"],
            &["オブジェクト指向", "可読"],
            &["readability", "guard"],
            &["readability", "check"],
            &["可読性", "class"],
            &["可読性", "method"],
        ],
    ),
    (
        "academic-writing",
        &[
            &["academic writing"],
            &["scholarly note"],
            &["citation", "evidence"],
            &["logic gap"],
            &["学術文章"],
            &["notation", "logic"],
            &["記法", "論理"],
        ],
    ),
    (
        "codex-task-workflow",
        &[
            &["repo-changing"],
            &["実装", "修正"],
            &["コード", "直して"],
            &["implementation", "fix"],
            &["agent-canon", "docs"],
            &["patch", "repo"],
            &["bounded fix"],
            &["patch"],
            &["typo", "修正"],
            &["責務境界", "修正"],
            &["flaky test", "直して"],
            &["単一 file", "直して"],
            &["scoped-change"],
            &["実装して", "repo"],
            &["修正して", "repo"],
            &["直して", "repo"],
            &["public behavior"],
            &["bounded behavior"],
            &["regression case"],
            &["bounded scope"],
            &["仕様解釈", "修正"],
            &["optimizer", "修正"],
            &["solver", "直して"],
            &["repo-changing optimization patch"],
            &["収束しない"],
            &["tolerance", "直して"],
            &["failed", "validation"],
            &["validation", "failure"],
            &["failing", "contract"],
            &["do", "not", "delete", "tests"],
            &["weaken", "oracle"],
        ],
    ),
    (
        "change-review",
        &[
            &["change-review"],
            &["code review"],
            &["diff review"],
            &["review", "finding"],
            &["レビュー", "finding"],
        ],
    ),
    (
        "comprehensive-development",
        &[
            &["comprehensive development"],
            &["repo-wide", "workflow"],
            &["repo-wide", "tooling"],
            &["包括的", "整理"],
            &["500", "タスク"],
        ],
    ),
    (
        "environment-maintenance",
        &[
            &["docker"],
            &["devcontainer"],
            &["container"],
            &["github actions"],
            &["ci", "修正"],
            &["dependency", "upgrade"],
            &["lockfile"],
        ],
    ),
    (
        "dependency-analysis",
        &[
            &["dependency-analysis"],
            &["dependency review"],
            &["dependency graph"],
            &["run_repo_dependency_review.sh"],
            &["依存", "graph"],
            &["依存", "レビュー"],
        ],
    ),
    (
        "experiment-lifecycle",
        &[
            &["run", "experiment"],
            &["new", "experiment"],
            &["rerun", "experiment"],
            &["re-run", "experiment"],
            &["experiment", "execution"],
            &["benchmark", "run"],
            &["実験", "実行"],
            &["実験", "再実行"],
            &["再現", "実験"],
            &["experiment", "artifact", "evidence"],
            &["experiment", "result", "persist"],
            &["experiment", "result", "save"],
        ],
    ),
    (
        "html-output",
        &[
            &["html"],
            &["browser-readable"],
            &["ブラウザ"],
            &["dashboard"],
            &["web page"],
        ],
    ),
    (
        "literature-survey",
        &[
            &["literature survey"],
            &["prior art"],
            &["先行研究"],
            &["論文調査"],
        ],
    ),
    (
        "long-form-writing",
        &[
            &["readme", "guide"],
            &["workflow", "guide"],
            &["migration", "guide"],
            &["長文", "文書"],
            &["説明文書"],
        ],
    ),
    (
        "paper-writing",
        &[
            &["paper", "draft"],
            &["thesis chapter"],
            &["投稿論文"],
            &["論文", "draft"],
        ],
    ),
    (
        "pr-processing",
        &[
            &["pr #"],
            &["pull request"],
            &["merge", "pr"],
            &["checks", "pr"],
            &["レビュー", "pr"],
        ],
    ),
    (
        "prose-reasoning-graph",
        &[
            &["structure analysis"],
            &["構造解析"],
            &["prose graph"],
            &["文書", "構造"],
            &["claim", "evidence"],
        ],
    ),
    (
        "refactor-loop",
        &[
            &["refactor"],
            &["リファクタ"],
            &["behavior-preserving"],
            &["構造変更"],
        ],
    ),
    (
        "report-writing",
        &[
            &["report"],
            &["レポート"],
            &["decision brief"],
            &["summary", "evidence"],
            &["結果", "説明"],
        ],
    ),
    (
        "research-workflow",
        &[
            &["research-backed"],
            &["external research"],
            &["外部調査"],
            &["比較実験"],
            &["benchmark", "compare"],
        ],
    ),
    (
        "structure-planning",
        &[
            &["structure contract"],
            &["構造", "計画"],
            &["section order"],
            &["source map"],
            &["first figure"],
        ],
    ),
    (
        "structure-refactor",
        &[
            &["structure drift"],
            &["repo structure"],
            &["directory layout"],
            &["root view"],
            &["responsibility-scope"],
            &["構造", "drift"],
        ],
    ),
    (
        "subagent-bootstrap",
        &[
            &["マルチエージェント"],
            &["subagent"],
            &["spawn", "agent"],
            &["複数 agent"],
            &["agent", "fan-out"],
        ],
    ),
    (
        "test-design",
        &[
            &["test design"],
            &["nasty case"],
            &["regression case"],
            &["regression"],
            &["既存テスト"],
            &["テスト"],
            &["public behavior"],
            &["仕様解釈"],
            &["テスト設計"],
            &["test oracle"],
            &["oracle", "mismatch"],
            &["spec mismatch", "test"],
            &["brittle", "test"],
        ],
    ),
    (
        "tool-finding-report",
        &[
            &["tool finding"],
            &["checker finding"],
            &["static analysis", "finding"],
            &["finding packet"],
            &["run_repo_dependency_review.sh"],
            &["dependency graph"],
            &["complete report"],
            &["検出結果"],
        ],
    ),
    (
        "user-guided-debugging",
        &[
            &["one issue at a time"],
            &["user-guided debugging"],
            &["一つずつ", "debug"],
            &["デバッグ", "一件"],
            &["問題ごと", "修正"],
            &["原因説明", "patch"],
        ],
    ),
];

const WORKFLOW_KEYWORDS: &[SimpleKeywordRule] = &[
    (
        "adaptive-improvement-loop",
        &["next_action", "backlog", "iteration", "改善ループ"],
    ),
    (
        "agent-canon-update",
        &[
            "agent-canon pr",
            "external AgentCanon clone",
            "development clone",
            "parent/same-repository branch",
            "linked-worktree",
            "dependency repository",
            "independent-clone",
            "agentcanon 最新",
            "pull request",
            "pr #",
            "マージ",
            "merge",
        ],
    ),
    (
        "agent-canon-update-route",
        &[
            "external AgentCanon clone",
            "development clone",
            "parent/same-repository branch",
            "linked-worktree",
            "dependency repository",
            "independent-clone",
            "agentcanon 最新",
        ],
    ),
    (
        "codex-task-workflow",
        &[
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
        ],
    ),
    (
        "comprehensive-development",
        &[
            "comprehensive development",
            "repo-wide",
            "包括的",
            "500",
            "tooling rearchitecture",
        ],
    ),
    (
        "environment-maintenance",
        &[
            "docker",
            "devcontainer",
            "container",
            "github actions",
            "ci",
            "lockfile",
        ],
    ),
    (
        "large-delivery",
        &[
            "large-delivery",
            "large refactor",
            "大規模",
            "複数 chunk",
            "複数の関係ファイル",
            "milestone",
            "新機能",
            "structure drift",
            "repo structure",
            "directory layout",
            "root view",
            "responsibility-scope",
            "構造変更",
        ],
    ),
    (
        "platform-and-environment",
        &[
            "docker",
            "devcontainer",
            "container",
            "github actions",
            "ci",
            "dependency upgrade",
        ],
    ),
    (
        "research-driven-change",
        &[
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
        ],
    ),
    (
        "routing-only-advisory",
        &[
            "実装しないで",
            "patch しないで",
            "相談だけ",
            "advisory",
            "どのスキル",
            "which workflow",
        ],
    ),
    (
        "scoped-change",
        &[
            "public behavior",
            "bounded behavior",
            "regression case",
            "cross-module",
            "bounded scope",
            "仕様解釈",
            "既存テスト",
        ],
    ),
    (
        "owner-bounded-change",
        &[
            "owner-bounded-change",
            "bounded fix",
            "bounded patch",
            "one-file",
            "単一 file",
            "typo",
            "flaky test",
            "責務境界が閉じた",
            "責務境界が閉じた修正",
        ],
    ),
];

const TOOL_KEYWORDS: &[SimpleKeywordRule] = &[
    (
        "agent-canon-cli",
        &[
            "agent-canon docs",
            "docs check",
            "docs format",
            "docs links",
            "docs-check",
            "broken link",
            "link repair",
            "リンク切れ",
            "markdownlint",
            "agentcanon 最新",
            "checkout drift",
            "agent-canon pr",
        ],
    ),
    (
        "evaluate_workflow_selection.py",
        &[
            "evaluate_workflow_selection.py",
            "workflow selection eval",
            "routing eval",
        ],
    ),
    (
        "generate_agent_improvement_guide.py",
        &["improvement guide", "改善指南", "githubaction"],
    ),
    (
        "generate_agent_runtime_dashboard.py",
        &[
            "generate_agent_runtime_dashboard.py",
            "runtime dashboard",
            "agent dashboard",
            "dashboard",
        ],
    ),
    (
        "log_surface_inventory.rs",
        &["ログ項目", "log surface", "hook log"],
    ),
    (
        "run_repo_dependency_review.sh",
        &[
            "run_repo_dependency_review.sh",
            "dependency review",
            "dependency graph",
        ],
    ),
    (
        "runtime_log_archive_git.py",
        &[
            "runtime_log_archive_git.py",
            "agent report archive",
            "runbundle archive",
            "archive path",
        ],
    ),
    (
        "behavior_event_assembly.py",
        &[
            "入力プロンプト",
            "prompt",
            "behavior event",
            "behavior_events",
        ],
    ),
    (
        "tool_rejection_preflight.py",
        &["tool rejection", "preflight", "はじかれる"],
    ),
    (
        "workflow_monitor.py",
        &["workflow_monitor", "runtime-feedback", "runtime feedback"],
    ),
];

/// Caller-frozen inputs. The classifier never reads repo_root or routing_rules.
pub struct PromptClassifierInputs<'a> {
    pub prompt: &'a JsonString,
    pub repo_root: &'a Path,
    pub catalog: &'a JsonValue,
    pub routing_rules: &'a JsonValue,
    pub structural_lane_evidence: &'a [SkillLaneEvidence],
    pub validation_repair_evidence: &'a [JsonString],
}

/// One pure classification result.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct PromptIntakeSignals {
    pub skills: Vec<JsonString>,
    pub selected_workflows: Vec<JsonString>,
    pub candidate_skills: Vec<JsonString>,
    pub candidate_skill_reasons: Vec<JsonString>,
    pub candidate_workflows: Vec<JsonString>,
    pub candidate_tools: Vec<JsonString>,
    pub feedback_labels: Vec<JsonString>,
    pub feedback_action: JsonString,
}

impl PromptIntakeSignals {
    pub fn should_log(&self) -> bool {
        !self.skills.is_empty()
            || !self.selected_workflows.is_empty()
            || !self.candidate_skills.is_empty()
            || !self.candidate_workflows.is_empty()
            || !self.candidate_tools.is_empty()
            || !self.feedback_labels.is_empty()
    }

    pub fn feedback_targets(&self) -> Vec<JsonString> {
        self.feedback_labels.clone()
    }
}

pub fn should_log(signals: &PromptIntakeSignals) -> bool {
    signals.should_log()
}

pub fn feedback_targets(signals: &PromptIntakeSignals) -> Vec<JsonString> {
    signals.feedback_targets()
}

type FieldValues = BTreeMap<&'static str, Vec<JsonString>>;

fn python_whitespace(codepoint: u32) -> bool {
    char::from_u32(codepoint).is_some_and(is_python_whitespace)
}

fn field_values(prompt: &JsonString) -> FieldValues {
    let mut fields = BTreeMap::new();
    let mut index = 0;
    while index < prompt.0.len() {
        while index < prompt.0.len() && python_whitespace(prompt.0[index]) {
            index += 1;
        }
        let start = index;
        while index < prompt.0.len() && !python_whitespace(prompt.0[index]) {
            index += 1;
        }
        if start == index {
            continue;
        }
        let token = &prompt.0[start..index];
        let Some(separator) = token
            .iter()
            .position(|codepoint| *codepoint == u32::from(b'='))
        else {
            continue;
        };
        let key = JsonString(token[..separator].to_vec());
        let Some(key_text) = key.to_text() else {
            continue;
        };
        let Some(capture) = FIELD_KEY_RE.captures(&key_text) else {
            continue;
        };
        let Some(field_name) = capture.get(1).map(|value| value.as_str()) else {
            continue;
        };
        let Some(field_name) = FIELD_NAMES.iter().copied().find(|name| *name == field_name) else {
            continue;
        };
        let value = JsonString(token[separator + 1..].to_vec());
        if value.is_empty() {
            continue;
        }
        let value = strip_field_delimiters(&value);
        if !value.is_empty() {
            fields
                .entry(field_name)
                .or_insert_with(Vec::new)
                .push(value);
        }
    }
    fields
}

fn strip_field_delimiters(value: &JsonString) -> JsonString {
    let is_delimiter = |codepoint: u32| {
        codepoint == u32::from(b'[')
            || codepoint == u32::from(b']')
            || codepoint == u32::from(b'(')
            || codepoint == u32::from(b')')
            || codepoint == u32::from(b',')
    };
    let mut start = 0;
    while start < value.0.len() && is_delimiter(value.0[start]) {
        start += 1;
    }
    let mut end = value.0.len();
    while end > start && is_delimiter(value.0[end - 1]) {
        end -= 1;
    }
    JsonString(value.0[start..end].to_vec())
}

fn trim_python_whitespace(value: &JsonString) -> JsonString {
    let mut start = 0;
    while start < value.0.len() && python_whitespace(value.0[start]) {
        start += 1;
    }
    let mut end = value.0.len();
    while end > start && python_whitespace(value.0[end - 1]) {
        end -= 1;
    }
    JsonString(value.0[start..end].to_vec())
}

fn split_values(values: Vec<JsonString>) -> Vec<JsonString> {
    let mut output = Vec::new();
    for value in values {
        let mut start = 0;
        for index in 0..=value.0.len() {
            if index == value.0.len()
                || value.0[index] == u32::from(b',')
                || value.0[index] == u32::from(b';')
            {
                let part = trim_python_whitespace(&JsonString(value.0[start..index].to_vec()));
                if !part.is_empty() {
                    append_unique(&mut output, part);
                }
                start = index + 1;
            }
        }
    }
    output
}

fn values_for(fields: &FieldValues, keys: &[&'static str]) -> Vec<JsonString> {
    let mut values = Vec::new();
    for key in keys {
        if let Some(found) = fields.get(key) {
            values.extend(found.iter().cloned());
        }
    }
    split_values(values)
}

fn fold_json_string(value: &JsonString, case_mapper: &CaseMapper) -> JsonString {
    let mut output = Vec::new();
    let mut valid_run = String::new();
    for &codepoint in &value.0 {
        if let Some(character) = char::from_u32(codepoint) {
            valid_run.push(character);
        } else {
            output.extend(case_mapper.fold_string(&valid_run).chars().map(u32::from));
            valid_run.clear();
            output.push(codepoint);
        }
    }
    output.extend(case_mapper.fold_string(&valid_run).chars().map(u32::from));
    JsonString(output)
}

fn contains_substring(text: &JsonString, needle: &JsonString) -> bool {
    needle.is_empty()
        || (needle.0.len() <= text.0.len()
            && text
                .0
                .windows(needle.0.len())
                .any(|window| window == needle.0.as_slice()))
}

fn contains_folded(text: &JsonString, needle: &str, case_mapper: &CaseMapper) -> bool {
    contains_substring(
        text,
        &JsonString::from_text(&case_mapper.fold_string(needle)),
    )
}

fn skill_tokens(prompt: &JsonString) -> Vec<JsonString> {
    let mut output = Vec::new();
    let mut valid_run = String::new();
    for &codepoint in &prompt.0 {
        if let Some(character) = char::from_u32(codepoint) {
            valid_run.push(character);
        } else {
            output.extend(
                SKILL_TOKEN_RE
                    .captures_iter(&valid_run)
                    .filter_map(|capture| capture.get(1))
                    .map(|capture| JsonString::from_text(capture.as_str())),
            );
            valid_run.clear();
        }
    }
    output.extend(
        SKILL_TOKEN_RE
            .captures_iter(&valid_run)
            .filter_map(|capture| capture.get(1))
            .map(|capture| JsonString::from_text(capture.as_str())),
    );
    output
}

fn valid_skill_id(value: &JsonString) -> bool {
    value
        .to_text()
        .is_some_and(|text| SKILL_ID_RE.is_match(&text))
}

fn collect_catalog_skill_ids(catalog: &JsonValue) -> BTreeSet<JsonString> {
    let mut known = BTreeSet::new();
    let mut pending = vec![catalog];
    while let Some(value) = pending.pop() {
        match value {
            JsonValue::String(value) => {
                if valid_skill_id(value) {
                    known.insert(value.clone());
                }
            }
            JsonValue::Array(values) => pending.extend(values.0.iter().rev()),
            JsonValue::Object(values) => {
                let mut seen_keys = BTreeSet::new();
                for (key, value) in values.0.iter().rev() {
                    if seen_keys.insert(key) {
                        pending.push(value);
                    }
                }
            }
            JsonValue::Null | JsonValue::Bool(_) | JsonValue::Number(_) => {}
        }
    }
    known
}

fn is_known_skill(value: &JsonString, catalog_ids: &BTreeSet<JsonString>) -> bool {
    catalog_ids.contains(value)
        || SKILL_KEYWORDS
            .iter()
            .any(|(skill, _)| value.equals_text(skill))
}

fn has_ascii_skill_boundary(text: &JsonString, skill: &str) -> bool {
    let needle: Vec<u32> = skill.bytes().map(u32::from).collect();
    if needle.is_empty() || needle.len() > text.0.len() {
        return false;
    }
    for start in 0..=text.0.len() - needle.len() {
        if text.0[start..start + needle.len()] != needle {
            continue;
        }
        let left_boundary = start == 0 || !is_ascii_skill_word(text.0[start - 1]);
        let end = start + needle.len();
        let right_boundary = end == text.0.len() || !is_ascii_skill_word(text.0[end]);
        if left_boundary && right_boundary {
            return true;
        }
    }
    false
}

fn is_ascii_skill_word(codepoint: u32) -> bool {
    (u32::from(b'a')..=u32::from(b'z')).contains(&codepoint)
        || (u32::from(b'A')..=u32::from(b'Z')).contains(&codepoint)
        || (u32::from(b'0')..=u32::from(b'9')).contains(&codepoint)
        || codepoint == u32::from(b'_')
        || codepoint == u32::from(b'-')
}

fn keyword_matches(
    mapping: &[(&str, &[&[&str]])],
    text: &JsonString,
    case_mapper: &CaseMapper,
) -> Vec<JsonString> {
    mapping
        .iter()
        .filter_map(|(skill, groups)| {
            groups
                .iter()
                .any(|group| {
                    group
                        .iter()
                        .all(|term| contains_folded(text, term, case_mapper))
                })
                .then_some(JsonString::from_text(skill))
        })
        .collect()
}

fn simple_keyword_matches(
    mapping: &[(&str, &[&str])],
    text: &JsonString,
    case_mapper: &CaseMapper,
) -> Vec<JsonString> {
    mapping
        .iter()
        .filter_map(|(name, terms)| {
            terms
                .iter()
                .any(|term| contains_folded(text, term, case_mapper))
                .then_some(JsonString::from_text(name))
        })
        .collect()
}

fn append_unique(output: &mut Vec<JsonString>, value: JsonString) {
    if !output.contains(&value) {
        output.push(value);
    }
}

fn unique(values: Vec<JsonString>) -> Vec<JsonString> {
    let mut output = Vec::new();
    for value in values {
        append_unique(&mut output, value);
    }
    output
}

fn prefix_text(prefix: &str, value: &JsonString) -> JsonString {
    let mut output = JsonString::from_text(prefix);
    output.0.extend(value.0.iter().copied());
    output
}

fn string_text(value: &JsonString) -> String {
    value.to_text().unwrap_or_default()
}

pub fn prompt_intake_signals(inputs: &PromptClassifierInputs<'_>) -> PromptIntakeSignals {
    let case_mapper = CaseMapper::new();
    let lowered = fold_json_string(inputs.prompt, &case_mapper);
    let fields = field_values(inputs.prompt);
    let catalog_ids = collect_catalog_skill_ids(inputs.catalog);

    let mut skills = Vec::new();
    for value in values_for(&fields, &["skill", "skills", "skill_invocation"]) {
        let value = if value.0.first() == Some(&u32::from(b'$')) {
            JsonString(value.0[1..].to_vec())
        } else {
            value
        };
        if is_known_skill(&value, &catalog_ids) {
            skills.push(value);
        }
    }
    for skill in skill_tokens(inputs.prompt) {
        if is_known_skill(&skill, &catalog_ids) {
            skills.push(skill);
        }
    }
    // The old DEFAULT_SKILLS frozenset has no defined iteration order. Keep this
    // native inferred slice deterministic in the source declaration order.
    for (skill, _) in SKILL_KEYWORDS {
        if has_ascii_skill_boundary(&lowered, skill) {
            skills.push(JsonString::from_text(skill));
        }
    }

    let mut candidate_skills = Vec::new();
    let mut candidate_skill_reasons = Vec::new();
    for skill in keyword_matches(SKILL_KEYWORDS, &lowered, &case_mapper) {
        if !skills.contains(&skill) {
            candidate_skill_reasons.push(JsonString::from_text(&format!(
                "{}:keyword",
                string_text(&skill)
            )));
            candidate_skills.push(skill);
        }
    }
    for lane in inputs.structural_lane_evidence {
        if !lane.status.equals_text("observed") && !lane.status.equals_text("candidate") {
            continue;
        }
        candidate_skill_reasons.push(prefix_text("structural_concept=", &lane.lane));
        if lane.status.equals_text("observed") {
            skills.extend(lane.route_skills.iter().cloned());
        } else {
            candidate_skills.extend(lane.route_skills.iter().cloned());
        }
    }
    for evidence in inputs.validation_repair_evidence {
        if !evidence.is_empty() {
            candidate_skill_reasons.push(prefix_text("validation_repair=", evidence));
        }
    }
    candidate_skills.extend(values_for(
        &fields,
        &["candidate_skill", "candidate_skills"],
    ));

    let mut selected_workflows = values_for(
        &fields,
        &["workflow", "workflow_family", "selected_workflow"],
    );
    selected_workflows.retain(|value| value.0.first() != Some(&u32::from(b'$')));
    let mut candidate_workflows =
        values_for(&fields, &["candidate_workflow", "candidate_workflows"]);
    candidate_workflows.extend(simple_keyword_matches(
        WORKFLOW_KEYWORDS,
        &lowered,
        &case_mapper,
    ));
    let mut candidate_tools = values_for(&fields, &["candidate_tool", "candidate_tools", "tool"]);
    candidate_tools.extend(simple_keyword_matches(
        TOOL_KEYWORDS,
        &lowered,
        &case_mapper,
    ));
    let feedback_labels = values_for(&fields, &["feedback_label", "feedback_labels"]);
    let feedback_action = values_for(&fields, &["feedback_action"])
        .into_iter()
        .next()
        .unwrap_or_default();

    let skills = unique(skills);
    let candidate_skills = unique(
        candidate_skills
            .into_iter()
            .filter(|item| !skills.contains(item))
            .collect(),
    );

    PromptIntakeSignals {
        skills,
        selected_workflows: unique(selected_workflows),
        candidate_skills,
        candidate_skill_reasons: unique(candidate_skill_reasons),
        candidate_workflows: unique(candidate_workflows),
        candidate_tools: unique(candidate_tools),
        feedback_labels: unique(feedback_labels),
        feedback_action,
    }
}
