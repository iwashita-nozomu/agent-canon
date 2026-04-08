# Shared Skill Canon

このディレクトリは、Codex を主 runtime としつつ、Claude や Copilot でも共有する skill 文書の人間向け正本です。
機械 discovery 用の `SKILL.md` は `.agents/skills/` を正本にし、`.claude/skills/` などの互換 path へ mirror します。

## Rules

- skill の目的、使う場面、関連正本は `agents/skills/` に書きます。
- `AGENTS.md` や `CLAUDE.md` には長い skill 説明を複製しません。
- `.agents/skills/` は Codex / Copilot の auto-discovery path です。
- `.claude/skills/` は `.agents/skills/` から生成する Claude 互換 mirror です。
- 人間が skill を明示する場合の第一推奨は plain text ではなく `$skill-name` です。
- 例: `$research-workflow`、`$adaptive-improvement-loop`、`$paper-writing`
- 新しい public skill を追加するときは `catalog.yaml` と対応文書を同時に更新します。

## Public Skill Surface

CLI に出す公開 skill は、user が直接選ぶ価値が高いものだけに絞ります。
review の細粒度 checklist、CLI adapter、artifact placement、subagent bootstrap、validation helper は public skill ではなく canonical docs と subagent routing に寄せます。

| Family | Purpose | Canonical Doc | Discovery Shim |
| ------ | ------- | ------------- | -------------- |
| `repo-onboarding` | unfamiliar repo の最短入口確認 | `agents/skills/repo-onboarding.md` | `.agents/skills/repo-onboarding/SKILL.md` |
| `codex-task-workflow` | Codex の context-independent task 実行 | `agents/skills/codex-task-workflow.md` | `.agents/skills/codex-task-workflow/SKILL.md` |
| `change-review` | findings-first の差分 review | `agents/skills/change-review.md` | `.agents/skills/change-review/SKILL.md` |
| `python-review` | pyright / pytest / ruff を前提にした Python review | `agents/skills/python-review.md` | `.agents/skills/python-review/SKILL.md` |
| `cpp-review` | build / header / ownership を前提にした C / C++ review | `agents/skills/cpp-review.md` | `.agents/skills/cpp-review/SKILL.md` |
| `test-design` | static 解析で nasty case と regression case を固定 | `agents/skills/test-design.md` | `.agents/skills/test-design/SKILL.md` |
| `long-form-writing` | README、workflow、guide などの長文作成フロー | `agents/skills/long-form-writing.md` | `.agents/skills/long-form-writing/SKILL.md` |
| `academic-writing` | 論文、thesis chapter、scholarly note の作成フロー | `agents/skills/academic-writing.md` | `.agents/skills/academic-writing/SKILL.md` |
| `paper-writing` | 投稿論文、thesis chapter、paper section の作成フロー | `agents/skills/paper-writing.md` | `.agents/skills/paper-writing/SKILL.md` |
| `md-style-check` | Markdown の体裁とリンク確認 | `agents/skills/md-style-check.md` | `.agents/skills/md-style-check/SKILL.md` |
| `worktree-start` | worktree 開始時の scope、action log、kickoff を整える | `agents/skills/worktree-start.md` | `.agents/skills/worktree-start/SKILL.md` |
| `worktree-health` | worktree の scope drift と cleanup risk を確認 | `agents/skills/worktree-health.md` | `.agents/skills/worktree-health/SKILL.md` |
| `experiment-lifecycle` | 単一 run と review / rerun 分岐 | `agents/skills/experiment-lifecycle.md` | `.agents/skills/experiment-lifecycle/SKILL.md` |
| `adaptive-improvement-loop` | 実験、調査、チューニングを backlog-driven に回す outer loop | `agents/skills/adaptive-improvement-loop.md` | `.agents/skills/adaptive-improvement-loop/SKILL.md` |
| `literature-survey` | 先行研究、関連文献、反証候補の整理 | `agents/skills/literature-survey.md` | `.agents/skills/literature-survey/SKILL.md` |
| `research-workflow` | 外部調査、比較設計、run loop、decision state の整理 | `agents/skills/research-workflow.md` | `.agents/skills/research-workflow/SKILL.md` |
| `comprehensive-development` | code / docs / tools / runtime をまたぐ包括的開発フロー | `agents/skills/comprehensive-development.md` | `.agents/skills/comprehensive-development/SKILL.md` |
| `environment-maintenance` | Docker / CI / dependency / runtime 更新 | `agents/skills/environment-maintenance.md` | `.agents/skills/environment-maintenance/SKILL.md` |

## Internal Review And Runtime Routines

- docs completeness、docs consistency、notation、logic gap、citation/evidence、critical/report、research perspective review は public skill ではなく、workflow が自動で要求する review pass として扱います。
- artifact placement、subagent bootstrap、CLI adapter、static validation は `agents/canonical/` と `documents/REVIEW_PROCESS.md` の責務に寄せます。
- carry-over の吸い上げは `notes/` と worktree log を正本にし、独立 public skill にはしません。

## Codex Defaults

- Codex では `AGENTS.md` と `agents/canonical/CODEX_WORKFLOW.md` を先に読みます。
- task ごとの skill 選択は、このディレクトリか `catalog.yaml` を見て決めます。
- user が skill を明示したい場合は `$skill-name` の形を既定にし、曖昧な prose より優先します。
- specialist を使う場合の Codex-specific routing は `agents/canonical/CODEX_SUBAGENTS.md` を見ます。
- 文献調査が主タスクなら `literature-survey` を先に見ます。
- 長めの README、workflow、guide、migration 文書では `long-form-writing` を先に見ます。
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を先に見ます。
- paper section まで含む論文 draft では `paper-writing` を先に見ます。
- 研究系の task では `research-workflow` を outer loop に使います。
- tuning、探索、比較改善を backlog 付きで継続反復する task では `adaptive-improvement-loop` を outer loop にします。
- code 変更では `test-design` を使い、実装前に nasty case と regression case を先に固定します。
- C / C++ 差分では `cpp-review` を既定候補にします。
- worktree を新設・再開するときは `worktree-start` で scope と action log を先に固定し、scope drift や cleanup 判断は `worktree-health` を使います。
- repo-wide な実装・文書・tooling・runtime の統合変更では `comprehensive-development` を使います。
- repo-wide な tool 導入や Docker / CI 更新案では `environment-maintenance` と `agents/templates/environment_change_proposal.md` を使います。

## Updating Skills

1. `agents/skills/<family>.md` を更新する
1. `agents/skills/catalog.yaml` を更新する
1. `.agents/skills/<family>/SKILL.md` を更新する
1. Claude mirror が必要なら `python3 scripts/tools/mirror_skill_shims.py --target .claude/skills --prune` を実行する
1. 必要なら `agents/canonical/CODEX_WORKFLOW.md` と `agents/canonical/CODEX_SUBAGENTS.md` の routing を更新する
