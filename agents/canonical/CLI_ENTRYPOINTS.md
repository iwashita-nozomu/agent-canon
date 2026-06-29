# CLI Entrypoints
<!--
@dependency-start
contract agent-runtime
responsibility Documents CLI Entrypoints for this repository.
upstream design README.md canonical workflow index
@dependency-end
-->


この文書は、agent ごとの入口差分をまとめた正本です。
共有ルールは `agents/` に寄せ、各 CLI では薄い入口だけを使います。

## この文書の読み方

この文書は、CLI ごとの最初の入口と run bootstrap の使い分けを扱います。
まず `共通ルール` で全 CLI に共通する起動前提を確認し、Codex で作業する場合は
`Codex` を読みます。新しい run bundle を作る場合は `Run Bootstrap` の
標準 command を使います。共有 workflow、skill、subagent routing の詳細は
この文書に重複させず、参照先の `agents/` owner surface で保守します。

## 共通ルール

- repo root で起動する
- まず `AGENTS.md` を読む
- reusable workflow は `agents/` と skill directory で保守する
- task 固有の run artifact は `reports/agents/<run-id>/` に寄せる

## Codex

入口:
- `AGENTS.md`
- `.agents/skills/`

使いどころ:
- local repository 上の実装、review、文書整備
- `AGENTS.md` を起点に canonical docs を読む運用

補足:
- skill の discovery path は `.agents/skills/<skill>/SKILL.md`
- task 実行の標準順序は `agents/canonical/CODEX_WORKFLOW.md`
- subagent routing は `agents/canonical/CODEX_SUBAGENTS.md`
- repo-wide の正本変更は `agents/` を先に更新する
- 最初の作業 update で `workflow=<family>`, `skills=<...>`, `review=<...>` を宣言する
- planning を含む parent session では、parent session 側の plan-mode command を使う。official Codex CLI では `/plan`
- runtime が `/agent` を提供する場合は subagent inventory の確認に使い、使えない場合は `.codex/agents/*.toml` を直接見る
- `task_start.py` / `bootstrap_agent_run.py` の出力では
  `REPO_TOOL_ROUTING_SEQUENCE`、`REPO_TOOL_ROUTING_NEXT_COMMAND`、
  `REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES` を確認する

## Run Bootstrap

標準 bundle を作るときは次を使います。

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --task-id T1 \
  --owner "human-or-agent" \
  --workspace-root "$PWD"
```

task catalog の default specialist と default review pack をそのまま使うのが既定です。狭い例外だけ `--enable` で足します。
`--task` の文面は `route.py --prompt` にも使われ、prompt-derived skill は
`SUGGESTED_SKILLS` と `team_manifest.yaml` の `run.repo_tool_routing_policy`
へ反映されます。

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --task-id T4 \
  --owner "codex" \
  --workspace-root "$PWD"
```

環境変更では `--task-id T8`、学術文章では `--task-id T10` を起点にします。

包括的開発では、次を起点にし、`project_reviewer`、`docs_workflow_steward`、`python_reviewer`、必要に応じて `cpp_reviewer` を固定 stack として立てます。

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

包括的開発では、parent が writer ごとの path / directory を `team_manifest.yaml` の write policy で管理します。write scope が重なる場合は current checkout 内の後続 wave に serialize し、別 `git worktree` へ分けません。

GitHub Actions から回すときは `.github/workflows/agent-coordination.yml` を使います。
