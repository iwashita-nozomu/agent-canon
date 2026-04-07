# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
会話の過去文脈に依存せず、毎回同じ順序で進められるようにします。

## Start Here

1. `AGENTS.md` を読む
1. `agents/README.md` を読む
1. `agents/skills/README.md` を読む
1. `documents/coding-conventions-python.md` を読む
1. `agents/TASK_WORKFLOWS.md` で task family を決める
1. 実装を伴う task では `documents/implementation-waterfall-workflow.md` を読む
1. subagent を使う task では `agents/canonical/CODEX_SUBAGENTS.md` を読む
1. `agents/canonical/ARTIFACT_PLACEMENT.md` で文書の置き場を決める
1. 必要なら `.agents/skills/` から該当 skill を読む

## Task Classification

次の 4 つから 1 つ選びます。

- `Scoped Change`
- `Research-Driven Change`
- `Large Delivery`
- `Platform And Environment`

迷った場合:
- 外部調査や比較実験が必要なら `Research-Driven Change`
- Docker / CI / dependency を触るなら `Platform And Environment`
- 大きくなければまず `Scoped Change`

## Minimal Skill Set

Codex では、まず `agents/skills/README.md` から必要最小限の skill だけ選びます。

- repo 入口確認:
  - `repo-onboarding`
- workflow 選択:
  - `agent-orchestration`
- 文書置き場:
  - `artifact-placement`
- run bundle / specialist 起動:
  - `subagent-bootstrap`
- validation:
  - `static-check`
  - `static-validation`
- code review:
  - `code-review`
- Python diff:
  - `python-review`
- docs completeness:
  - `docs-completeness-review`
- Markdown diff:
  - `md-style-check`
- review:
  - `change-review`
- worktree kickoff:
  - `worktree-start`
- worktree drift and cleanup:
  - `worktree-health`
- experiment inner loop:
  - `experiment-lifecycle`
- experiment/code-change loop:
  - `experiment-change-loop`
- literature and prior art:
  - `literature-survey`
- research outer loop:
  - `research-workflow`
- experiment report:
  - `report-review`
- research-wide review pack:
  - `research-perspective-review`
- repo-wide review:
  - `project-review`
- repo-wide integration review:
  - `comprehensive-review`
- maintenance monitoring:
  - `project-health`
- environment and tool rollout:
  - `environment-maintenance`

## Execution Flow

### 1. Intake

- 変更対象と acceptance criteria を短く固定する
- 不明点が多い場合だけ追加探索する

### 2. Workflow Selection

- `agents/TASK_WORKFLOWS.md` から family を 1 つ選ぶ
- family をまたぐ場合も、主 family を 1 つ決める

### 3. Placement

- run 固有のメモは `reports/agents/<run-id>/`
- repo-wide の恒久文書は `agents/` か `documents/`
- 知見の蓄積は `notes/`

### 4. Optional Run Bootstrap

次では bundle 作成と explicit subagent activation を既定にします。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

とくに、`scheduler`、`schedule_reviewer`、`designer`、`design_reviewer` は repo-changing task の標準構成とします。調査が必要なら `researcher` と `research_reviewer` も明示的に有効化します。
Codex subagent では、`requirements_organizer`、`execution_planner`、`plan_reviewer`、`detailed_designer`、`detailed_design_reviewer`、`worker` を stage ごとに明示し、計画レビュー用 reviewer と詳細設計レビュー用 reviewer を別 instance で立てます。
interactive Codex で要件整理と実行計画立案を行う場合は、可能なら parent session を `/collab` の `Plan` mode に切り替えてから planning specialist を起動します。
default の model split は、`gpt-5.4` が planning と final judgment、`gpt-5.4-mini` が狭い subtask を担当する形です。`gpt-5.3-codex` と `gpt-5.3-codex-spark` は parent が明示的に override するときだけ使います。

コマンド:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --owner "codex"

### 5. Implementation

- 実装は `documents/implementation-waterfall-workflow.md` の gate に従って進める
- `計画レビュー` と `詳細設計レビュー` は別 agent で行う
- `詳細設計レビュー` を通す前に実装を始めない
- まず既存 code path、既存 helper、既存 style を調べ、再利用を優先する
- role ごとの model policy は `agents/canonical/CODEX_SUBAGENTS.md` に従う
- default worker は `gpt-5.4-mini` で、`gpt-5.3-codex` / `gpt-5.3-codex-spark` は narrow override とみなす
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う

### 6. Validation

- agent runtime / skill 変更では `make agent-checks`
- まず `make ci-quick`
- 必要に応じて `make ci`
- Python 変更では `pyright`、`pytest python/tests/`、`ruff check python/ --select D,E,F,I,UP` を確認する
- 文書変更では markdown / link check を使う
- report を閉じる前には `documents/experiment-report-style.md` を確認する
- 研究系 task では `critical-review` と `report-review` の decision state を確認し、必要なら `research-perspective-review` を追加する

### 7. Closeout

- repo に残す差分がある task では、validation 後に commit を作る
- user が明示的に止めていなければ、final report の前に branch を push する
- final report には branch、commit、push の成否を短く残す
- push が失敗した、または意図的に skip した場合は、その理由を final report に明記する
- review-only task や no-change task では commit / push を要求しない

そのうえで、何を変えたか、何を確認したか、何を確認していないかを短く残して完了する

## Codex-Specific Rules

- `AGENTS.md` は Codex の最初の入口として保つ
- `.agents/skills/` を正規 skill path とする
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈にだけ依存する運用は repo 正本にしない
