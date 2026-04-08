# CLI Entrypoints

この文書は、agent ごとの入口差分をまとめた正本です。
共有ルールは `agents/` に寄せ、各 CLI では薄い入口だけを使います。

## 共通原則

- repo root で起動する
- まず `AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md` の対応入口を読む
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

## Claude Code

入口:
- `CLAUDE.md`
- `.claude/skills/`
- `.claude/agents/`

使いどころ:
- interactive session での task 実行
- Claude-native subagent の呼び出し

補足:
- `.claude/skills/` は `.agents/skills/` から生成する互換 mirror
- shared rules は `AGENTS.md` を参照し、Claude 固有差分だけを `CLAUDE.md` に置く
- subagent 管理は Claude Code の `/agents` を前提にする

## GitHub Copilot

入口:
- `.github/copilot-instructions.md`
- `AGENTS.md`
- `.agents/skills/`

使いどころ:
- GitHub Copilot CLI
- GitHub-hosted coding agent
- IDE / repository instructions

補足:
- repo instructions は `.github/copilot-instructions.md` に置く
- old `gh-copilot` extension 前提の説明は正本にしない
- GitHub-hosted agent は issue / PR 起点で使うことがあるため、repo 正本は特定ローカル wrapper に寄せすぎない

## Run Bootstrap

標準 bundle を作るときは次を使います。

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --owner "human-or-agent" \
  --workspace-root "$PWD" \
  --enable scheduler \
  --enable schedule_reviewer
```

specialist を明示するとき:

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

環境変更では `infra_steward` と `infra_reviewer` を追加します。

包括的開発では、次を起点にし、`project_reviewer`、`docs_workflow_steward`、`python_reviewer` を固定 stack として立てます。

```bash
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
```

包括的開発では、同一 worktree の writer を 1 人に固定します。複数 writer が必要な場合は worktree を分けます。

GitHub Actions から回すときは `.github/workflows/agent-coordination.yml` を使います。
