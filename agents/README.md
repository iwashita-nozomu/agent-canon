# Agent Hub

このディレクトリは、repo におけるエージェント運用の人間向け正本ハブです。
個別エージェント向けの runtime entrypoint は薄く保ち、詳細はここへ集約します。
この template では、Python 実装、pytest/pyright/ruff、Markdown 文書と report review を常設前提にします。

## 正本

- [canonical/README.md](/mnt/l/workspace/project_template/agents/canonical/README.md)
  - 共通レイアウトと正本の置き場
- [agents_config.json](/mnt/l/workspace/project_template/agents/agents_config.json)
  - チーム定義と write policy
- [TASK_WORKFLOWS.md](/mnt/l/workspace/project_template/agents/TASK_WORKFLOWS.md)
  - workflow family と task 選択
- [COMMUNICATION_PROTOCOL.md](/mnt/l/workspace/project_template/agents/COMMUNICATION_PROTOCOL.md)
  - handoff / review / escalation の正本
- [task_catalog.yaml](/mnt/l/workspace/project_template/agents/task_catalog.yaml)
  - machine-readable catalog
- [canonical/ARTIFACT_PLACEMENT.md](/mnt/l/workspace/project_template/agents/canonical/ARTIFACT_PLACEMENT.md)
  - task 文書と run artifact の置き分け
- [canonical/CLI_ENTRYPOINTS.md](/mnt/l/workspace/project_template/agents/canonical/CLI_ENTRYPOINTS.md)
  - agent ごとの入口差分と bootstrap 入口
- [canonical/CODEX_WORKFLOW.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_WORKFLOW.md)
  - Codex の標準 task 実行フロー
- [canonical/CODEX_SUBAGENTS.md](/mnt/l/workspace/project_template/agents/canonical/CODEX_SUBAGENTS.md)
  - Codex の subagent routing
- [skills/README.md](/mnt/l/workspace/project_template/agents/skills/README.md)
  - 人間向け skill 正本
- [skills/catalog.yaml](/mnt/l/workspace/project_template/agents/skills/catalog.yaml)
  - skill family の機械可読カタログ
- [skills/literature-survey.md](/mnt/l/workspace/project_template/agents/skills/literature-survey.md)
  - 文献調査と先行研究整理の入口
- [skills/research-workflow.md](/mnt/l/workspace/project_template/agents/skills/research-workflow.md)
  - 研究系変更の outer loop
- [skills/experiment-change-loop.md](/mnt/l/workspace/project_template/agents/skills/experiment-change-loop.md)
  - 実験結果に基づく改造 loop の自律実行
- [skills/worktree-start.md](/mnt/l/workspace/project_template/agents/skills/worktree-start.md)
  - worktree kickoff、scope 初期化、action log 起点の固定
- [skills/long-form-writing.md](/mnt/l/workspace/project_template/agents/skills/long-form-writing.md)
  - README、workflow、guide などの長文作成フロー
- [skills/from_another_agent.md](/mnt/l/workspace/project_template/agents/skills/from_another_agent.md)
  - 前回 agent run の carry-over note を current task へ接続
- [skills/project-review.md](/mnt/l/workspace/project_template/agents/skills/project-review.md)
  - repo-wide review と棚卸し
- [skills/research-perspective-review.md](/mnt/l/workspace/project_template/agents/skills/research-perspective-review.md)
  - 研究系変更の並列 review pack
- [skills/environment-maintenance.md](/mnt/l/workspace/project_template/agents/skills/environment-maintenance.md)
  - Docker、CI、tool 導入方針の正本

## Runtime Entry Points

- [AGENTS.md](/mnt/l/workspace/project_template/AGENTS.md)
  - Codex / Copilot agent mode の入口
- [CLAUDE.md](/mnt/l/workspace/project_template/CLAUDE.md)
  - Claude Code の入口
- [.github/copilot-instructions.md](/mnt/l/workspace/project_template/.github/copilot-instructions.md)
  - GitHub Copilot repository instructions
- [.github/AGENTS.md](/mnt/l/workspace/project_template/.github/AGENTS.md)
  - GitHub 側の薄い入口

## Skills And Subagents

- Canonical project skills: `.agents/skills/`
- Claude compatibility mirror: `.claude/skills/` (generated from `.agents/skills/`)
- Claude subagents: `.claude/agents/`
- Codex runtime config: `.codex/`

## 運用ルール

- 共通方針は `agents/` 配下に集約し、entrypoint へ重複記述しません。
- 新しい workflow や skill を追加するときは、まず `agents/canonical/` の文書を更新します。
- 実行環境固有の都合がある場合だけ、`AGENTS.md`、`CLAUDE.md`、`.github/copilot-instructions.md` に最小限の差分を持たせます。
