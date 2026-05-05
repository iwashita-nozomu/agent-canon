# agent-canon
<!--
@dependency-start
responsibility Documents agent-canon for this repository.
upstream design AGENTS.md shared canon runtime contract
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
- `tools/`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `documents/agent-canon-github-remote.md`
- `documents/template-github-remote.md`
- `agents/workflows/README.md`
  - workflow catalog と routing guide の入口
- `agents/workflows/agent-canon-pr-workflow.md`
- `documents/agent-canon-subtree-migration.md`

## 利用時のディレクトリ / リンク構成

AgentCanon 単体 repo では、この tree 自体を source of truth として扱います。
Template や派生 repo では `vendor/agent-canon/` を source of truth にし、repo
root の入口は symlink view または明示的な synced copy にします。

標準構成:

- `vendor/agent-canon/`: AgentCanon submodule pin。shared workflow、skills、tools、MCP、docs の正本。
- `AGENTS.md -> vendor/agent-canon/ROOT_AGENTS.md`: Codex / Copilot 向けの薄い root entrypoint。
- `CLAUDE.md -> vendor/agent-canon/CLAUDE.md`: Claude Code 向けの薄い root entrypoint。
- `agents -> vendor/agent-canon/agents`: workflow、canonical docs、task catalog の root view。
- `.agents -> vendor/agent-canon/.agents`: Codex skill discovery 用の root view。
- `.claude -> vendor/agent-canon/.claude`: Claude skill / agent mirror の root view。
- `.codex/config.toml -> vendor/agent-canon/.codex/config.toml`: Codex runtime config の共有 view。
- `.codex/agents -> vendor/agent-canon/.codex/agents`: Codex subagent role TOML の共有 view。
- `mcp -> vendor/agent-canon/mcp`: repo MCP launcher / server の共有 view。
- `tools -> vendor/agent-canon/tools`: shared automation の共有 view。
- `documents/*`: `documents/SHARED_RUNTIME_SURFACES.md` に列挙された canon-owned docs だけを symlink view にします。
- `memory/*`、`notes/*`、`tests/*`: `documents/SHARED_RUNTIME_SURFACES.md` に従って shared surface だけを root view にします。
- `.github/copilot-instructions.md`: shared Copilot entrypoint の synced copy。
- `.github/workflows/agent-coordination.yml`: shared coordination workflow の synced copy。
- `.github/PULL_REQUEST_TEMPLATE.md`: standalone AgentCanon repository 用の独立 PR checklist。
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`: template 側で `vendor/agent-canon/` を変える PR 用 checklist。
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`: shared PR template の synced copy。

repo-local の正本として残すもの:

- `docker/`: Template / project の開発環境。AgentCanon や Template の remote 名は Dockerfile に焼かず、文書で管理します。
- `scripts/`: Template / project 固有の bootstrap と slug 置換。
- `python/`、`src/`、`include/`、`lib/`: project implementation。
- `experiments/`、`reports/`、`goal.md`: repo-local state。shared symlink には戻しません。

root view の修復と検証:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
```

remote の正本:

- AgentCanon canonical remote は `documents/agent-canon-github-remote.md` を見ます。
- Template canonical remote は `documents/template-github-remote.md` を見ます。
- local `/mnt/git/*.git` は compatibility mirror であり、source of truth ではありません。

## 検索導線

正確な symbol、path、error message はまず `rg` で探します。広い概念、近い tool、
既存 helper の再利用候補を探すときは AgentCanon の軽量 vector search を併用します。

```bash
python3 tools/agent_tools/vector_search.py --query "github remote safe directory"
python3 tools/agent_tools/vector_search.py --surface tools --query "dependency header graph"
```

この search は標準ライブラリだけの TF-IDF vector model です。embedding index や外部 API
key は Dockerfile に入れず、必要になった repo だけ optional layer として artifact
directory に生成します。

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
canonical remote の詳細は `documents/agent-canon-github-remote.md` を見ます。
