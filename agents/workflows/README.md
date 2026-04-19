# agent-canon workflow guide

この文書は `agent-canon` 自体を保守する人の入口です。
template 利用者向けの導線は root 側の `agents/workflows/README.md` を使います。

## ここで扱うもの

- workflow canon
- skill catalog
- subagent routing
- shared runtime helper
- shared review / validation helper
- shared canon の PR / subtree sync

## まず見るもの

- `ROOT_AGENTS.md`
- `agents/README.md`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_WORKFLOW.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`

## maintainer の作業型

- workflow / review policy を直す
- skill / subagent を追加・削除する
- shared runtime helper を更新する
- root surface の link / copy spec を更新する
- upstream `agent-canon` へ sync する

## maintainer の基本手順

1. 作業開始時に upstream `agent-canon` を最新化する
1. `vendor/agent-canon/` 側を編集する
1. root surface を再同期する
1. shared canon 用 check を流す
1. template 側 PR を作る
1. merge 後に upstream `agent-canon` へ push する

```bash
make agent-canon-ensure-latest
bash tools/update_agent_canon.sh plan
bash tools/update_agent_canon.sh apply
bash tools/update_agent_canon.sh refresh-remote
bash tools/update_agent_canon.sh proposal-branch
bash tools/update_agent_canon.sh push-proposal
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-pr-check
bash tools/sync_agent_canon.sh push
```

## 参照先

- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
