# agent-canon
<!--
@dependency-start
@dependency-end
-->


このディレクトリは `agent-canon` 自体の committed snapshot です。
template や派生 repo に配布する shared agent canon の正本をここに置きます。

## このディレクトリの役割

- workflow canon の正本
- skill / subagent / runtime instruction の正本
- shared runtime helper と validation helper の正本
- shared canon の upstream sync と PR 運用の正本

## 主な入口

- `ROOT_AGENTS.md`
- `agents/`
- `.agents/skills/`
- `.codex/agents/`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `agents/workflows/README.md`
  - workflow catalog と routing guide の入口
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`

## 保守ルール

- template root の symlink view や synced copy を直接編集しません。
- shared canon を直すときはこの directory を source of truth にします。
- root surface を戻すときは次を使います。

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

## upstream sync

template 側で shared canon を直した変更を upstream `agent-canon` repo に戻すときは次を使います。

```bash
bash tools/sync_agent_canon.sh push
```

pull / push / PR の詳細は `agents/workflows/agent-canon-pr-workflow.md` を見ます。
