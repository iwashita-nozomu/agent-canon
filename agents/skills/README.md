# Shared Skill Canon

このディレクトリは、Codex を主 runtime としつつ、Claude や Copilot でも共有する skill 文書の人間向け正本です。
機械 discovery 用の `SKILL.md` は `.agents/skills/` を正本にし、`.claude/skills/` などの互換 path へ mirror します。判断基準と使い分けはここに集約します。

## Rules

- skill の目的、使う場面、関連正本は `agents/skills/` に書きます。
- `AGENTS.md` や `CLAUDE.md` には長い skill 説明を複製しません。
- `.agents/skills/` は Codex / Copilot の auto-discovery path です。
- `.claude/skills/` は `.agents/skills/` から生成する Claude 互換 mirror です。
- 新しい skill を追加するときは `catalog.yaml` と対応文書を同時に更新します。
- この template では Python と Markdown を常に前提にするため、`python-review` と `md-style-check` は頻出 skill です。

## Skill Families

| Family | Purpose | Canonical Doc | Discovery Shim |
| ------ | ------- | ------------- | -------------- |
| `repo-onboarding` | unfamiliar repo の最短入口確認 | `agents/skills/repo-onboarding.md` | `.agents/skills/repo-onboarding/SKILL.md` |
| `agent-orchestration` | workflow family 選択と role/handoff 整理 | `agents/skills/agent-orchestration.md` | `.agents/skills/agent-orchestration/SKILL.md` |
| `artifact-placement` | task 文書、run artifact、repo 正本の置き分け | `agents/skills/artifact-placement.md` | `.agents/skills/artifact-placement/SKILL.md` |
| `from_another_agent` | 前回 run の carry-over と optional follow-up の取捨選択 | `agents/skills/from_another_agent.md` | `.agents/skills/from_another_agent/SKILL.md` |
| `subagent-bootstrap` | run bundle と specialist 起動 | `agents/skills/subagent-bootstrap.md` | `.agents/skills/subagent-bootstrap/SKILL.md` |
| `codex-cli` | Codex 用の入口と読順 | `agents/skills/codex-cli.md` | `.agents/skills/codex-cli/SKILL.md` |
| `codex-task-workflow` | Codex の context-independent task 実行 | `agents/skills/codex-task-workflow.md` | `.agents/skills/codex-task-workflow/SKILL.md` |
| `claude-code-cli` | Claude Code 用の入口差分 | `agents/skills/claude-code-cli.md` | `.agents/skills/claude-code-cli/SKILL.md` |
| `copilot-cli` | Copilot 用の入口差分 | `agents/skills/copilot-cli.md` | `.agents/skills/copilot-cli/SKILL.md` |
| `static-check` | 速い検査と基礎品質確認 | `agents/skills/static-check.md` | `.agents/skills/static-check/SKILL.md` |
| `static-validation` | lint / test / docs / links の確認 | `agents/skills/static-validation.md` | `.agents/skills/static-validation/SKILL.md` |
| `code-review` | correctness / 設計 / 保守性レビュー | `agents/skills/code-review.md` | `.agents/skills/code-review/SKILL.md` |
| `python-review` | pyright / pytest / ruff を前提にした Python review | `agents/skills/python-review.md` | `.agents/skills/python-review/SKILL.md` |
| `test-design` | static 解析で nasty case と regression case を固定 | `agents/skills/test-design.md` | `.agents/skills/test-design/SKILL.md` |
| `long-form-writing` | README、workflow、guide などの長文作成フロー | `agents/skills/long-form-writing.md` | `.agents/skills/long-form-writing/SKILL.md` |
| `academic-writing` | 論文、thesis chapter、scholarly note の作成フロー | `agents/skills/academic-writing.md` | `.agents/skills/academic-writing/SKILL.md` |
| `paper-writing` | 投稿論文、thesis chapter、paper section の作成フロー | `agents/skills/paper-writing.md` | `.agents/skills/paper-writing/SKILL.md` |
| `docs-completeness-review` | 文書の欠落や説明不足のレビュー | `agents/skills/docs-completeness-review.md` | `.agents/skills/docs-completeness-review/SKILL.md` |
| `citation-evidence-review` | 論文主張の citation / figure / table / evidence trace のレビュー | `agents/skills/citation-evidence-review.md` | `.agents/skills/citation-evidence-review/SKILL.md` |
| `logic-gap-review` | 学術文章の論理飛躍と根拠接続のレビュー | `agents/skills/logic-gap-review.md` | `.agents/skills/logic-gap-review/SKILL.md` |
| `md-style-check` | Markdown の体裁とリンク確認 | `agents/skills/md-style-check.md` | `.agents/skills/md-style-check/SKILL.md` |
| `docs-consistency-review` | 文書間の矛盾と stale route の確認 | `agents/skills/docs-consistency-review.md` | `.agents/skills/docs-consistency-review/SKILL.md` |
| `notation-definition-review` | 記号、略語、定義順、一貫性のレビュー | `agents/skills/notation-definition-review.md` | `.agents/skills/notation-definition-review/SKILL.md` |
| `change-review` | findings-first review | `agents/skills/change-review.md` | `.agents/skills/change-review/SKILL.md` |
| `worktree-start` | worktree 開始時の scope、action log、kickoff を整える | `agents/skills/worktree-start.md` | `.agents/skills/worktree-start/SKILL.md` |
| `worktree-health` | worktree の scope drift と cleanup risk を確認 | `agents/skills/worktree-health.md` | `.agents/skills/worktree-health/SKILL.md` |
| `experiment-workflow` | question, protocol, run, report の整理 | `agents/skills/experiment-workflow.md` | `.agents/skills/experiment-workflow/SKILL.md` |
| `experiment-lifecycle` | 単一 run と review / rerun 分岐 | `agents/skills/experiment-lifecycle.md` | `.agents/skills/experiment-lifecycle/SKILL.md` |
| `experiment-change-loop` | 実験結果で改造 loop を閉じるまで回す | `agents/skills/experiment-change-loop.md` | `.agents/skills/experiment-change-loop/SKILL.md` |
| `adaptive-improvement-loop` | 実験、調査、チューニングを backlog-driven に回す outer loop | `agents/skills/adaptive-improvement-loop.md` | `.agents/skills/adaptive-improvement-loop/SKILL.md` |
| `literature-survey` | 先行研究、関連文献、反証候補の整理 | `agents/skills/literature-survey.md` | `.agents/skills/literature-survey/SKILL.md` |
| `research-workflow` | 外部調査、比較設計、run loop、decision state の整理 | `agents/skills/research-workflow.md` | `.agents/skills/research-workflow/SKILL.md` |
| `critical-review` | 過大主張、比較条件、根拠不足の確認 | `agents/skills/critical-review.md` | `.agents/skills/critical-review/SKILL.md` |
| `report-review` | experiment report の reader-facing review | `agents/skills/report-review.md` | `.agents/skills/report-review/SKILL.md` |
| `research-perspective-review` | 研究系変更を複数視点で並列レビュー | `agents/skills/research-perspective-review.md` | `.agents/skills/research-perspective-review/SKILL.md` |
| `comprehensive-review` | docs / tools / workflow の横断レビュー | `agents/skills/comprehensive-review.md` | `.agents/skills/comprehensive-review/SKILL.md` |
| `project-health` | 継続運用、CI、drift の健全性確認 | `agents/skills/project-health.md` | `.agents/skills/project-health/SKILL.md` |
| `project-review` | repo-wide な棚卸しと全体レビュー | `agents/skills/project-review.md` | `.agents/skills/project-review/SKILL.md` |
| `comprehensive-development` | code / docs / tools / runtime をまたぐ包括的開発フロー | `agents/skills/comprehensive-development.md` | `.agents/skills/comprehensive-development/SKILL.md` |
| `environment-maintenance` | Docker / CI / dependency / runtime 更新 | `agents/skills/environment-maintenance.md` | `.agents/skills/environment-maintenance/SKILL.md` |

## Codex Defaults

- Codex では `AGENTS.md` と `agents/canonical/CODEX_WORKFLOW.md` を先に読みます。
- task ごとの skill 選択は、このディレクトリか `catalog.yaml` を見て決めます。
- specialist を使う場合の Codex-specific routing は `agents/canonical/CODEX_SUBAGENTS.md` を見ます。
- 前の agent の carry-over を吸う必要がある task では `from_another_agent` を最初に見ます。
- 文献調査が主タスクなら `literature-survey` を先に見ます。
- 長めの README、workflow、guide、migration 文書では `long-form-writing` を先に見ます。
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を先に見ます。
- paper section まで含む論文 draft では `paper-writing` を先に見ます。
- 研究系の task では `research-workflow` を outer loop、`research-perspective-review` を大きい review pack として使います。
- 実験結果を見ながら code change を継続反復する task では `experiment-change-loop` を使います。
- tuning、探索、比較改善を backlog 付きで継続反復する task では `adaptive-improvement-loop` を outer loop にします。
- code 変更では `test-design` を使い、実装前に nasty case と regression case を先に固定します。
- worktree を新設・再開するときは `worktree-start` で scope と action log を先に固定し、scope drift や cleanup 判断は `worktree-health` を使います。
- repo-wide な棚卸しや大きな workflow 整理では `project-review` と必要なら `comprehensive-review` を使います。
- repo-wide な実装・文書・tooling・runtime の統合変更では `comprehensive-development` を使います。
- repo-wide な tool 導入や Docker / CI 更新案では `environment-maintenance` と `agents/templates/environment_change_proposal.md` を使います。

## Updating Skills

1. `agents/skills/<family>.md` を更新する
1. `agents/skills/catalog.yaml` を更新する
1. `.agents/skills/<family>/SKILL.md` を更新する
1. Claude mirror が必要なら `python3 scripts/tools/mirror_skill_shims.py --target .claude/skills --prune` を実行する
1. 必要なら `agents/canonical/CODEX_WORKFLOW.md` と `agents/canonical/CODEX_SUBAGENTS.md` の routing を更新する
