# エージェント運用の入口
<!--
@dependency-start
contract reference
responsibility Documents エージェント運用の入口 for this repository.
upstream design README.md durable document index
upstream design ../../ROOT_AGENTS.md template-root Codex runtime instruction surface
upstream design ../../AGENTS.md standalone AgentCanon Codex runtime instruction surface
@dependency-end
-->


この文書は repo 運用から見た agent 運用の薄い入口です。

## この文書の読み方

- この文書は、repo 運用から現在の agent 正本 surface へ誘導する入口です。
- 主な順路は、正本、Runtime Entry Points、Skills、実行入口、repo 側の運用ルールです。
- 古い [documents/codex/AGENTS_COORDINATION.md](AGENTS_COORDINATION.md) 参照を見つけたときや、
  runtime entrypoint の正本を確認するときに読みます。
- 境界: 新しい stage rule や skill policy はここではなく、リンク先の
  runtime instruction surface、`agents/`、skill owner surface が所有します。

## Codex Loading Priority

Codex loading-priority policy is owned by [ROOT_AGENTS.md](../../ROOT_AGENTS.md) and [AGENTS.md](../../AGENTS.md);
this file only maps legacy references to the current owner surfaces. Codex の
自動 instruction 読み込みは Codex home の global guidance から始まり、その後
project root から current working directory へ進む runtime chain で決まります。
各 directory では `AGENTS.override.md`、[AGENTS.md](../../AGENTS.md)、
`project_doc_fallback_filenames` の順に最大 1 file だけが入ります。current working
directory に近い file ほど後に結合され、広い guidance を局所的に上書きします。
この文書は legacy adapter であり、Codex が常に自動で読む runtime instruction
surface ではありません。

Parent root から Codex を開始した場合、parent の self-contained
[AGENTS.md](../../AGENTS.md) が instruction entrypoint です。AgentCanon source checkout 内を
current working directory として開始した場合、この tree の [AGENTS.md](../../AGENTS.md) が
standalone source-tree entrypoint になります。必要な AgentCanon tool runtime は
qualified source clone の `bootstrap.sh` と明示 runtime root から起動し、親へ
instruction view を投影しません。[.github/AGENTS.md](../../.github/AGENTS.md) は `.github/` subtree に
入ったときの parent overlay です。

Consumer root の [AGENTS.md](../../AGENTS.md) は、AgentCanon の [ROOT_AGENTS.md](../../ROOT_AGENTS.md) common base と
consumer-owned specific text を明示的に合成した通常の tracked file です。base の
source checkout、runtime、symlink、vendor、submodule は consumer の instruction
chain に必要ありません。AgentCanon source の [AGENTS.md](../../AGENTS.md) は standalone source-tree
編集用であり、consumer root へ直接コピーしたり、`AGENT.md` という singular alias
を追加したりしません。

Skills は repository instruction chain とは別 surface です。Codex は skill
metadata で候補を選び、選択後に該当 `SKILL.md` を読みます。hook、rules、MCP、
plugin、`.codex/config.toml` も runtime behavior の owner surface であり、この
legacy adapter に重複 policy を置きません。

## Runtime Instruction Surfaces

The executable policy projection is owned by the canonical runtime instructions,
role configuration, collaboration protocol, and selected operation owners. This
adapter only links to those surfaces; it does not duplicate their policy.

- [ROOT_AGENTS.md](../../ROOT_AGENTS.md)
- [AGENTS.md](../../AGENTS.md)
- [.github/AGENTS.md](../../.github/AGENTS.md)
- [.codex/README.md](../../.codex/README.md)

## Workflow And Skill Canon

- [agents/README.md](../../agents/README.md)
- [agents/canonical/README.md](../../agents/canonical/README.md)
- [agents/agents_config.json](../../agents/agents_config.json)
- [agents/TASK_WORKFLOWS.md](../../agents/TASK_WORKFLOWS.md)
- [agents/COMMUNICATION_PROTOCOL.md](../../agents/COMMUNICATION_PROTOCOL.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](../../agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/canonical/CLI_ENTRYPOINTS.md](../../agents/canonical/CLI_ENTRYPOINTS.md)
- [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md)
- [agents/canonical/CODEX_SUBAGENTS.md](../../agents/canonical/CODEX_SUBAGENTS.md)
- [agents/skills/README.md](../../agents/skills/README.md)
- [agents/skills/catalog.yaml](../../agents/skills/catalog.yaml)

## Skills

- Canonical path: `.codex/personal/skills/`

## 実行入口

Planning and collaboration use the current Codex session. The official Codex
CLI provides `/plan` for planning and `/agent` when subagent collaboration is
available. Role definitions remain in `agents/agents_config.json`; selected
skills and operation owners determine which roles apply. Native AgentCanon tools
are invoked through their existing `tools/bin/agent-canon` entrypoint when that
runtime is selected.

## repo 側の運用ルール

- role 定義と write policy は `agents/agents_config.json` を正本にします。
- handoff、review、response、escalation の書式は [agents/COMMUNICATION_PROTOCOL.md](../../agents/COMMUNICATION_PROTOCOL.md) を正本にします。
- 共通 workflow と skill routing は `agents/` 側で保守し、runtime entrypoint へ role 一覧を重複記載しません。
- 会話だけを根拠に実装へ進めず、`documents/`、`documents/notes/`、`references/` と local library の sweep を先に行います。
- review feedback は、直前の execution role が反映してから次段へ handoff します。
- 学術文章では `document_flow_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、completeness reviewer を兼務させません。
- 論文 draft では `citation_evidence_reviewer` も兼務させません。
- repo ファイルを直接編集する role は parent-assigned write policy を持つ write-capable role に限ります。
- role-specific write capability は `agents/agents_config.json` と current Codex assignment が所有します。
