# Agent Task Workflows

この文書は、repo で使う workflow family の正本です。
task を細かく増やしすぎず、少数の family に寄せて運用します。

すべての family で、repo に持ち帰る実装パスは
[documents/implementation-waterfall-workflow.md](/mnt/l/workspace/project_template/documents/implementation-waterfall-workflow.md)
の段階ゲートに従います。
また、repo を編集する task では、stage ごとに適切な subagent / specialist を explicit に立てることを既定にします。

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
- `計画レビュー` と `詳細設計レビュー` は別エージェントで行います
- `詳細設計レビュー` を、実装前でもっとも重要な gate とみなします
- `文書通読レビュー` は `design_reviewer` と別エージェントで行い、上から順に読んだときに意味が通るかを確認します
- README、workflow、guide、migration 文書のような長文では `long-form-writing` を追加し、別 reviewer で `docs-completeness-review` も通します
- 学術文章では `academic-writing` を追加し、`notation_definition_reviewer`、`logic_gap_reviewer`、`docs-completeness-review` を別 reviewer で通します
- `詳細設計` の目標は、実装前提が十分に伝わる文書を起こすことです
- 実装では既存コード、既存の命名、既存の文書スタイル、既存の module boundary を徹底的に踏襲します
- 各 review の直後は、直前の execution role が feedback を反映してから次段へ進みます

## Activation Quick Start

repo-changing task の最小 bundle:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "scoped repo change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer
```

研究・実験つき変更:

```bash
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
```

環境変更:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "platform or environment change" \
  --owner "codex" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer \
  --enable infra_steward \
  --enable infra_reviewer
```

学術文章:

```bash
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
```

Codex parent が planning を行う session では、可能なら `/collab` の `Plan` mode を先に有効化します。

## Workflow Families

### 1. Scoped Change

対象:
- 局所バグ修正
- 小規模な docs/test 同期
- CI failure の切り分け

標準フロー:
1. 共通実装フローをそのまま 1 pass で通す
1. 小さい変更でも `scheduler`、`schedule_reviewer`、`designer`、`design_reviewer`、`document_flow_reviewer` を省略しない
1. 長文の docs task では `document_flow_reviewer` に加えて docs reviewer を省略しない
1. 学術文章では `notation_definition_reviewer` と `logic_gap_reviewer` を省略しない

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
- `report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り loop を閉じない
- ただし、1 回の repo 変更は 1 回の waterfall pass として閉じる
- 各 pass で計画レビュー、詳細設計レビュー、文書通読レビュー、checkpoint review、最終受け入れ review、audit review を省略しない
- agent が code change と run を継続反復する場合は `experiment-change-loop` を追加する
- methodology、artifact、reporting policy を大きく変える場合は `research-perspective-review` を追加する
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
- rollout と rollback を先に考える
- repo ルール、環境、automation を同時に更新する
- 実装前に environment design を凍結し、acceptance gate で transition readiness を確認する
- `infra_steward` と `infra_reviewer` は、実行計画と詳細設計の両方に入力を出す
- `infra_reviewer` を詳細設計レビューと最終受け入れ review の両方へ参加させる
- repo-wide な tool 導入案では理由、Docker 影響、validation、rollback を同時に残す

## 選び方

1. task が局所修正なら `Scoped Change`
1. 外部調査や比較実験が必要なら `Research-Driven Change`
1. chunk 設計が必要なら `Large Delivery`
1. 環境や automation を触るなら `Platform And Environment`

## 関連

- `agents/task_catalog.yaml`
- `agents/COMMUNICATION_PROTOCOL.md`
- `agents/canonical/ARTIFACT_PLACEMENT.md`
- `agents/canonical/CLI_ENTRYPOINTS.md`
- `documents/experiment-workflow.md`
- `documents/research-workflow.md`
