# Agent Canonical Layout

このディレクトリは、cross-agent で共有する人間向け正本の説明置き場です。
実行時に読まれる entrypoint は別にあっても、保守対象はここを基準にします。

## なぜ正本を分けるか

- Codex は `AGENTS.md` と `.agents/skills/` を読む
- Claude Code は `CLAUDE.md`、`.claude/skills/`、`.claude/agents/` を読む
- GitHub Copilot は `.github/copilot-instructions.md` と `AGENTS.md`、project skills を読む

単一の discovery path はないため、正本は `agents/` に集約し、各ランタイムには薄い互換入口だけを置きます。

## 現在の構成

- `agents/README.md`
  - 人間向けハブ
- `agents/agents_config.json`
  - 機械可読のチーム定義
- `agents/TASK_WORKFLOWS.md`
  - workflow family
- `agents/COMMUNICATION_PROTOCOL.md`
  - handoff / review ルール
- `agents/canonical/ARTIFACT_PLACEMENT.md`
  - task 文書と run artifact の置き分け
- `agents/canonical/CLI_ENTRYPOINTS.md`
  - Codex / Claude / Copilot の入口差分
- `agents/canonical/CODEX_WORKFLOW.md`
  - Codex の context-independent workflow
- `agents/canonical/CODEX_SUBAGENTS.md`
  - Codex の subagent routing
- `agents/skills/README.md`
  - 人間向け skill 正本
- `agents/skills/catalog.yaml`
  - skill family の機械可読カタログ
- `.agents/skills/`
  - Codex / Copilot 向け canonical skill path
- `.claude/skills/`
  - Claude compatibility mirror generated from `.agents/skills/`
- `.claude/agents/`
  - Claude-native subagents
- `.codex/`
  - Codex project-scoped runtime config

## 保守ルール

- まず `agents/` 側の正本を更新する
- runtime entrypoint は短く保つ
