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
  --owner "human-or-agent"
```

specialist を明示するとき:

```bash
python3 scripts/agent_tools/bootstrap_agent_run.py \
  --task "research-backed change" \
  --owner "codex" \
  --enable researcher \
  --enable research_reviewer \
  --enable experimenter \
  --enable experiment_reviewer
```

GitHub Actions から回すときは `.github/workflows/agent-coordination.yml` を使います。
