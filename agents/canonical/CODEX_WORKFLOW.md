# Codex Workflow

この文書は、Codex でこの repo を扱うときの標準フローです。
会話の過去文脈に依存せず、毎回同じ順序で進められるようにします。

## Start Here

1. `AGENTS.md` を読む
1. `agents/README.md` を読む
1. `notes/guardrails/README.md` を読む
1. `notes/guardrails/engineering_avoidances.md` を読む
1. `agents/skills/README.md` を読む
1. `documents/coding-conventions-python.md` を読む
1. `agents/TASK_WORKFLOWS.md` で task family を決める
1. 実装を伴う task では `documents/implementation-waterfall-workflow.md` を読む
1. subagent を使う task では `agents/canonical/CODEX_SUBAGENTS.md` を読む
1. `agents/canonical/ARTIFACT_PLACEMENT.md` で文書の置き場を決める
1. 必要なら `.agents/skills/` から該当 skill を読む

## Required Intake Sweep

### Context Sweep

実装、設計変更、文書改訂、実験計画の前に、会話だけを根拠に進めません。
次を topic keyword で探索し、該当 file を読んでから着手します。

- `documents/`
- `notes/knowledge/`
- `notes/guardrails/`
- `notes/failures/`
- `notes/themes/`
- `notes/branches/`
- `notes/worktrees/`
- `notes/experiments/`
- `references/`

### Library Sweep

新しい code path、module、helper、test、script を足す前に、既存の再利用候補を探索します。
対象は task に応じて次です。

- `python/`
- `tests/`
- `src/`
- `include/`
- `lib/`
- `scripts/`

既存実装があるのに別名の重複 module を新設しません。

## Task Classification

次の 5 つから 1 つ選びます。

- `Scoped Change`
- `Research-Driven Change`
- `Large Delivery`
- `Platform And Environment`
- `Comprehensive Development`

分類規則:
- code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`
- Docker / CI / dependency を触るなら `Platform And Environment`
- 外部調査や比較実験が必要なら `Research-Driven Change`
- chunk ごとの delivery なら `Large Delivery`
- それ以外は `Scoped Change`

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
- long-form docs:
  - `long-form-writing`
- academic docs:
  - `academic-writing`
- logic-heavy academic review:
  - `logic-gap-review`
- Markdown diff:
  - `md-style-check`
- notation-heavy academic review:
  - `notation-definition-review`
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
- 包括的 repo-wide delivery:
  - `comprehensive-development`
- maintenance monitoring:
  - `project-health`
- environment and tool rollout:
  - `environment-maintenance`

## Execution Flow

### 1. Intake

- context sweep と library sweep を先に行う
- 変更対象と acceptance criteria を短く固定する
- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する

### 2. Workflow Selection

- `agents/TASK_WORKFLOWS.md` から family を 1 つ選ぶ
- family をまたぐ場合も、主 family を 1 つ決める

### 3. Placement

- run 固有のメモは `reports/agents/<run-id>/`
- repo-wide の恒久文書は `agents/` か `documents/`
- 知見の蓄積は `notes/`

### 4. Run Bootstrap

repo-changing task では bundle 作成と explicit subagent activation を既定にします。
ただし stage の具体的な責務と禁止事項は prose ではなく `.codex/agents/*.toml` を正本にします。

- repo を編集する
- specialist handoff を明示したい
- review artifact を残したい
- 長めの task で run 単位の記録が必要
- subagent と parent の責務を分けたい

とくに、`scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer` は repo-changing task の標準構成とします。
Codex subagent では、`requirements_organizer`、`execution_planner`、`plan_reviewer`、`detailed_designer`、`detailed_design_reviewer`、`document_flow_reviewer`、`worker` を stage ごとに明示します。
学術文章では、これに `notation_definition_reviewer` と `logic_gap_reviewer` を追加します。
interactive Codex で要件整理と実行計画立案を行う場合は、可能なら parent session を `/collab` の `Plan` mode に切り替えてから planning specialist を起動します。
default の model split は、`gpt-5.4` が planning と final judgment、`gpt-5.4-mini` が狭い subtask を担当する形です。`gpt-5.3-codex` と `gpt-5.3-codex-spark` は parent が明示的に override するときだけ使います。

Codex runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見ます。

最小コマンド:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "short task summary" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer

研究・実験つき変更:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "research-backed change" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable experimenter \
      --enable experiment_reviewer

環境変更:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "platform or environment change" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable infra_steward \
      --enable infra_reviewer

学術文章:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "academic writing task" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable notation_definition_reviewer \
      --enable logic_gap_reviewer

包括的開発:

    python3 scripts/agent_tools/bootstrap_agent_run.py \
      --task "comprehensive development pass" \
      --owner "codex" \
      --workspace-root "$PWD" \
      --enable scheduler \
      --enable schedule_reviewer \
      --enable researcher \
      --enable research_reviewer \
      --enable infra_steward \
      --enable infra_reviewer \
      --enable critical_guardian

包括的開発の固定 Codex stack:

- `requirements_organizer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `project_reviewer`
- `docs_workflow_steward`
- `python_reviewer`
- `worker`

### 5. Implementation

- 実装は `documents/implementation-waterfall-workflow.md` の gate に従って進める
- `計画レビュー`、`詳細設計レビュー`、`文書通読レビュー` の分離や、implementation 着手条件は `.codex/agents/*.toml` を正本にする
- 包括的開発では `project_reviewer` を intake と closeout に追加し、repo-wide な integration risk を確認する
- 文書主体の成果物では `document_flow_reviewer` を通し、上から順に読んだときの意味の通り方を確認する
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を読み、別 reviewer で `docs-completeness-review` も通す
- 論文、thesis chapter、scholarly note のような学術文章では `academic-writing` を読み、`notation_definition_reviewer`、`logic_gap_reviewer`、別 reviewer の `docs-completeness-review` を通す
- まず既存 code path、既存 helper、既存 style を調べ、再利用を優先する
- role ごとの model policy は `agents/canonical/CODEX_SUBAGENTS.md` に従う
- default worker は `gpt-5.4-mini` で、`gpt-5.3-codex` / `gpt-5.3-codex-spark` は narrow override とみなす
- same-worktree single-writer rule は `worker.toml` と planning/reviewer TOML を正本にする
- 正本は `agents/` と `documents/` から先に直す
- runtime entrypoint は薄く保つ
- skill は repo 正本を置き換えず、導線だけを担う

### 6. Validation

- agent runtime / skill 変更では `make agent-checks`
- まず `make ci-quick`
- 必要に応じて `make ci`
- Python 変更では `pyright`、`pytest tests/`、`ruff check python tests --select D,E,F,I,UP` を確認する
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
- repo-changing task では、stage ごとの subagent / specialist を暗黙にせず明示する
- `plan_reviewer`、`detailed_design_reviewer`、`document_flow_reviewer` は別 instance にする
- 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` も別 instance にする
- 包括的開発では、同一 worktree の write role を `worker` 1 人に固定する
- 複数 writer を要する場合は、同一 worktree ではなく複数 worktree に分ける
- required review が unresolved のまま `worker` 相当の実装を始めない
- tracked repo change がある task では、required review、validation、commit、`origin` への push を経ずに完了扱いにしない
- Codex 専用事情でも、再利用可能なルールは `agents/` に昇格する
- 会話文脈にだけ依存する運用は repo 正本にしない
