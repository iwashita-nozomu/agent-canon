# Agent Canonical Layout
<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Canonical Layout for this repository.
upstream design ../README.md agent canon overview
@dependency-end
-->


このディレクトリは、cross-agent で共有する人間向け正本の説明置き場です。
実行時に読まれる entrypoint は別にあっても、保守対象はここを基準にします。
ただし、この file 自体は first-reader hub ではなく layout appendix です。
通常の読順は `README.md` -> `documents/README.md` -> `agents/README.md` ->
`agents/workflows/README.md` を優先します。

## なぜ正本を分けるか

- Codex は `AGENTS.md` と `.agents/skills/` を読む

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
  - Codex の入口差分
- `agents/canonical/CODEX_WORKFLOW.md`
  - Codex の context-independent workflow
- `agents/canonical/CODEX_SUBAGENTS.md`
  - Codex の subagent routing
- `agents/skills/README.md`
  - 人間向け skill 正本
- `agents/skills/catalog.yaml`
  - skill family の機械可読カタログ
- `.agents/skills/`
  - Codex 向け canonical skill path
- `.codex/`
  - Codex project-scoped runtime config

## 保守ルール

- まず `agents/` 側の正本を更新する
- runtime entrypoint は短く保つ
