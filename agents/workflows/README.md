# Workflow Guide
<!--
@dependency-start
upstream design ../TASK_WORKFLOWS.md workflow routing contract
@dependency-end
-->

この文書は、`agents/workflows/` 配下の workflow catalog と routing guide の入口です。
repo 利用者も `agent-canon` maintainer も、まずここで「今回どの workflow を primary にし、どの overlay を重ねるか」を決めます。

## 使い方

- まず 1 つの primary workflow を選びます。
- 長文、学術文書、paper のように文書種別が強い task では overlay workflow を追加します。
- shared canon maintenance や `main` 統合のような特殊操作だけ、maintenance workflow を追加します。
- workflow family の選択は `agents/TASK_WORKFLOWS.md`、Codex の標準実行順は `agents/canonical/CODEX_WORKFLOW.md` を正本にします。

## Quick Routing

### Primary Workflow

- repo に持ち帰る通常の code / docs / environment change
  - `agents/workflows/implementation-waterfall-workflow.md`
- 問い、比較設計、段階的改造、claim 更新を含む研究系変更
  - `agents/workflows/research-workflow.md`
- 実験実務、run layout、result/report 運用
  - `agents/workflows/experiment-workflow.md`
- tuning、比較改善、探索的改造を backlog 付きで反復する
  - `agents/workflows/adaptive-improvement-workflow.md`

### Overlay Workflow

- README、guide、workflow、migration 文書のような長文
  - `agents/workflows/long-form-writing-workflow.md`
- 論文、thesis chapter、scholarly note、claim-heavy document
  - `agents/workflows/academic-writing-workflow.md`
- 投稿論文や paper-like draft
  - `agents/workflows/paper-writing-workflow.md`

### Maintenance Workflow

- branch 側の rename / move / delete / directory reorg を `main` に戻す
  - `agents/workflows/main-integration-workflow.md`
- shared canon 自体を更新して PR / upstream sync する
  - `agents/workflows/agent-canon-pr-workflow.md`
- 派生 repo の `vendor/agent-canon/` 差分を proposal / shared canon main / 派生 repo snapshot の順で閉じる
  - `agents/workflows/derived-agent-canon-diff-workflow.md`
- task から agent philosophy や durable observation を昇格する
  - `agents/workflows/agent-learning-workflow.md`

## Recommended Read Order

1. `agents/TASK_WORKFLOWS.md`
1. `agents/canonical/CODEX_WORKFLOW.md`
1. `agents/workflows/README.md`
1. 選んだ primary workflow
1. 必要な overlay workflow
1. task に当たる maintenance workflow

## Workflow Map

### Implementation And Delivery

- `implementation-waterfall-workflow.md`
  - repo に持ち帰る change 全般の共通実装パス
- `main-integration-workflow.md`
  - file 構成変更を含む branch を `main` に戻す手順

### Research And Experiment

- `research-workflow.md`
  - research-driven change の問い、比較設計、claim 更新
- `experiment-workflow.md`
  - run 実務、artifact layout、result/report 運用
- `adaptive-improvement-workflow.md`
  - backlog-driven outer loop と waterfall inner pass

### Writing Overlay

- `long-form-writing-workflow.md`
  - README、guide、workflow、migration 文書
- `academic-writing-workflow.md`
  - notation / logic を強く扱う scholarly writing
- `paper-writing-workflow.md`
  - citation / evidence trace を含む paper overlay

### Canon And Learning

- `agent-canon-pr-workflow.md`
  - shared canon change の branch、PR、upstream sync
- `derived-agent-canon-diff-workflow.md`
  - 派生 repo の agent-canon 差分を proposal branch、shared canon main、派生 repo snapshot へ順に反映する手順
- `agent-learning-workflow.md`
  - `memory/` と guardrail への learning promotion
- `workflow-references.md`
  - workflow 設計の外部根拠索引

## Maintainer Path

`agent-canon` 自体を保守する場合は、次を追加で見ます。

- `ROOT_AGENTS.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-subtree-migration.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `agents/workflows/derived-agent-canon-diff-workflow.md`

基本手順:

1. upstream `agent-canon` を最新化する
1. `vendor/agent-canon/` を source of truth として編集する
1. root surface を再同期する
1. shared canon 用 check を流す
1. template 側 PR を閉じる
1. merge 後に upstream `agent-canon` へ push する

```bash
make agent-canon-ensure-latest
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-pr-check
bash tools/sync_agent_canon.sh push
```

derived repo から shared canon だけ更新するときは、必要に応じて次を使います。

```bash
bash tools/update_agent_canon.sh plan
bash tools/update_agent_canon.sh apply
bash tools/update_agent_canon.sh proposal-branch
bash tools/update_agent_canon.sh push-proposal
```
