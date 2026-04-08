# Agent Task Workflows

この文書は、repo で使う workflow family の正本です。
task を細かく増やしすぎず、少数の family に寄せて運用します。

すべての family で、repo に持ち帰る実装パスは
[documents/implementation-waterfall-workflow.md](/mnt/l/workspace/project_template/documents/implementation-waterfall-workflow.md)
の段階ゲートに従います。
また、repo を編集する task では、stage ごとに適切な subagent / specialist を explicit に立てることを既定にします。
stage ごとの具体的な禁止事項は prose ではなく `.codex/agents/*.toml` に寄せます。

## 共通実装フロー

1. 要件整理
   - `manager`
   - `manager_reviewer`
1. 調査
   - 必要に応じて `researcher`
   - 必要に応じて `research_reviewer`
1. 実行計画立案
   - `scheduler`
1. 計画レビュー
   - `schedule_reviewer`
1. 詳細設計
   - `designer`
1. 詳細設計レビュー
   - `design_reviewer`
1. 文書通読レビュー
   - `document_flow_reviewer`
1. テストケース設計
   - `test_designer`
1. 実装
   - `implementer`
1. 実装 checkpoint review
   - `change_reviewer`
1. 最終受け入れ review
   - `final_reviewer`
1. 監査と gate close
   - `auditor`
   - `verifier`

ルール:
- 着手前に `workflow=<family>`、`skills=<...>`、`review=<...>` を宣言します
- repo-changing task では run bundle を先に作り、stage ごとの specialist / subagent を明示します
- `計画レビュー` と `詳細設計レビュー` の分離、`詳細設計レビュー` の強い gate 性、`文書通読レビュー` の着手条件は各 reviewer TOML を正本にします
- code change では `test_designer` を独立に立て、static path と nasty case を先に固定します
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を追加し、別 reviewer で `docs-completeness-review` も通します
- 学術文章では `academic-writing` を追加し、`notation_definition_reviewer`、`logic_gap_reviewer`、`docs-completeness-review` を別 reviewer で通します
- 論文や thesis chapter では `paper-writing` を追加し、`citation_evidence_reviewer` も別 reviewer で通します
- `詳細設計` の目標は、実装前提が十分に伝わる文書を起こすことです
- 実装では既存コード、既存の命名、既存の文書スタイル、既存の module boundary を徹底的に踏襲します
- 各 review の直後は、直前の execution role が feedback を反映してから次段へ進みます

## Activation Quick Start

repo-changing task の最小 bundle:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --task-id T1 \
  --owner "codex" \
  --workspace-root "$PWD"
```

研究・実験つき変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --task-id T8 \
  --owner "codex" \
  --workspace-root "$PWD"
```

学術文章:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "academic writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

論文 draft:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "paper writing task" \
  --task-id T10 \
  --owner "codex" \
  --workspace-root "$PWD"
```

Codex parent が planning を行う session では、parent session 側の plan-mode command を先に有効化します。official Codex CLI では `/plan` です。

包括的開発:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

補足:
- `--task-id` を使うと、`agents/task_catalog.yaml` にある task-default specialist と `default_for_tasks` review pack を自動で有効化します
- cost を気にしない run では `--task-id` を基本にし、狭い例外だけ `--enable` で足します

包括的開発の固定 Codex stack:
- `requirements_organizer`
- `literature_researcher`
- `execution_planner`
- `plan_reviewer`
- `detailed_designer`
- `detailed_design_reviewer`
- `document_flow_reviewer`
- `test_designer`
- `project_reviewer`
- `docs_workflow_steward`
- `python_reviewer`
- `worker`

single-writer ルール:
- 同一 worktree では `worker` だけが repo file を編集します
- 同一 worktree で複数の write-capable subagent を走らせません
- 同一ディレクトリの並列 write も許可しません
- 複数 writer が必要な場合は worktree を分け、各 worktree に writer を 1 人だけ置きます
- parent は worktree ごとの結果を順番に統合します

## Workflow Families

### 1. Scoped Change

対象:
- 局所バグ修正
- 小規模な docs/test 同期
- CI failure の切り分け

標準フロー:
1. 共通実装フローをそのまま 1 pass で通す
1. 小さい変更でも `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer` を省略しない
1. code や test を触る task では `test_designer` を省略しない
1. 長文の docs task では `document_flow_reviewer` に加えて docs reviewer を省略しない
1. 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略しない
1. 論文や thesis chapter では `citation_evidence_reviewer` も省略しない

### 2. Research-Driven Change

対象:
- 外部調査を伴う実装
- benchmark や比較実験を根拠にした改善

追加ロール:
- `researcher`
- `research_reviewer`
- `experimenter`
- `experiment_reviewer`
- 必要に応じて `reproducibility_reviewer`
- 必要に応じて `scientific_computing_reviewer`
- 必要に応じて `benchmark_reviewer`
- 必要に応じて `artifact_reviewer`
- 必要に応じて `fair_data_reviewer`
- 必要に応じて `ml_science_reviewer`

特徴:
- research と experiment を evidence として回す
- overclaim review を明示的に挟む
- cost を気にしない default では、`report_reviewer` と research perspective reviewers を常時有効化します
- `report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り loop を閉じない
- ただし、1 回の repo 変更は 1 回の waterfall pass として閉じる
- 各 pass で計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review、最終受け入れ review、audit review を省略しない
- agent が code change と run を継続反復する場合は `experiment-change-loop` を追加する
- methodology、artifact、reporting policy を大きく変えなくても、research-driven change では `research-perspective-review` を default にします
- repo-wide な research cleanup では task catalog の `T9` を基準に perspective reviewers をまとめて有効化する

### 3. Large Delivery

対象:
- 新機能追加
- 大規模 refactor
- 複数 chunk に分ける delivery

追加ロール:
- `scheduler`
- `schedule_reviewer`

特徴:
- milestone と chunk 境界を先に固定する
- milestone ごとに実行計画と詳細設計を分ける
- 各 chunk は独立した waterfall pass として閉じる
- 各 chunk で checkpoint review を複数回に増やせる
- 逐次 review と最終 review を分ける

### 4. Platform And Environment

対象:
- Docker
- CI
- automation
- dependency / runtime upgrade

追加ロール:
- `infra_steward`
- `infra_reviewer`
- 必要に応じて `researcher`, `scheduler`, `experimenter`

特徴:
- `scheduler` と `schedule_reviewer` を省略せず、環境変更でも順序と handoff を固定する
- rollout と rollback を先に考える
- repo ルール、環境、automation を同時に更新する
- code requirement、blocked command、必要 runtime capability を `environment_change_proposal.md` に先に固定する
- 実装前に environment design を凍結し、acceptance gate で transition readiness を確認する
- `infra_steward` と `infra_reviewer` は、実行計画と詳細設計の両方に入力を出す
- `infra_reviewer` を詳細設計レビューと最終受け入れ review の両方へ参加させる
- Docker を変える task では source-of-truth surface、同期対象、rollout / rollback、validation matrix を必ず同じ pass に残す
- repo-wide な tool 導入案では理由、Docker 影響、validation、rollback を同時に残す

### 5. Comprehensive Development

対象:
- code、docs、tests、workflow、tools、Docker、CI をまたぐ repo-wide な整理
- agent canon、tooling、implementation convention を同時に触る rearchitecture
- 単一 chunk に閉じないが、1 つの umbrella plan で切りたい integrated delivery

追加ロール:
- `scheduler`
- `schedule_reviewer`
- `critical_guardian`
- `researcher`
- `research_reviewer`
- `infra_steward`
- `infra_reviewer`

固定 Codex stack:
- `project_reviewer`
- `docs_workflow_steward`
- `python_reviewer`

特徴:
- 背骨は共通実装フローと `documents/implementation-waterfall-workflow.md` の gate をそのまま使う
- task を docs / tools / runtime / implementation に分解しても、requirements、plan、design は 1 つの umbrella pass で閉じる
- `project_reviewer` を intake と closeout の両方で使い、repo-wide completeness と integration risk を確認する
- `docs_workflow_steward` は canon docs、workflow docs、entrypoint wrapper の整理に限定して使う
- `python_reviewer` を implementation chunk review と final integration review の両方で使う
- `test_designer` は実装前に static path、failure mode、nasty edge case を洗い、worker が既存 test style で落とし込む
- 同一 worktree では `worker` だけが repo file を編集する
- 同一 worktree では parallel write を許可しない
- 複数 writer が必要な場合は worktree を分け、各 worktree に writer を 1 人だけ置く
- `critical_guardian` は architecture、testing completeness、dependency conflict、implementation gap を cross-cutting に見る
- 最終 review では `final_reviewer` に加えて `project_reviewer` を使い、slice 単位ではなく全体の整合を確認する

## 選び方

1. task が局所修正なら `Scoped Change`
1. 外部調査や比較実験が必要なら `Research-Driven Change`
1. chunk 設計が必要なら `Large Delivery`
1. 環境や automation を触るなら `Platform And Environment`
1. code / docs / tools / runtime をまとめて rework するなら `Comprehensive Development`

## 関連

- `agents/task_catalog.yaml`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `documents/experiment-workflow.md`
- `documents/research-workflow.md`
