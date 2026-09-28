# Skill 実装ガイド
<!--
@dependency-start
contract reference
responsibility Documents Skill 実装ガイド for this repository.
upstream design README.md durable document index
@dependency-end
-->


この文書は、repo で使う project skill の実装指針です。
AgentCanon の正本は `agents/skills/` と catalog、project 固有 skill の正本はその repository の `.agents/skills/` です。

## 正本

- 人間向けハブ: [agents/README.md](../../agents/README.md)
- canonical layout: [agents/canonical/README.md](../../agents/canonical/README.md)
- skill registry: [agents/canonical/skills.md](../../agents/canonical/skills.md)
- human skill canon: [agents/skills/README.md](../../agents/skills/README.md)
- machine-readable skill catalog: `agents/skills/catalog.yaml`
- artifact placement canon: [agents/canonical/ARTIFACT_PLACEMENT.md](../../agents/canonical/ARTIFACT_PLACEMENT.md)
- CLI entrypoint canon: [agents/canonical/CLI_ENTRYPOINTS.md](../../agents/canonical/CLI_ENTRYPOINTS.md)
- Codex workflow canon: [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md)
- 生成先と Codex discovery の配置: [Skill Paths](../../agents/canonical/skills.md#skill-paths)

## 方針

- skill は少数の workflow-oriented unit に保ちます。
- numbered skill catalog は増やしません。
- AgentCanon の instructions は `agents/skills/<skill>.md`、project 固有 skill は `.agents/skills/<skill>/SKILL.md` に集約します。
- 再利用可能な workflow は skill にし、repo 全体の恒久ルールは `documents/` または `agents/` に置きます。
- `.codex/personal/skills/` は ignored な生成 view です。既存の [bootstrap / materializer 経路](../../README.md#source-and-artifact-boundary) を使い、手編集や別の同期スクリプトを追加しません。

## 推奨 skill directory

project 固有 skill は repository または対象 subtree に置きます。

```text
.agents/skills/<skill-name>/
└── SKILL.md
```

必要な場合だけ次を追加します。

```text
<skill-name>/
├── SKILL.md
├── scripts/
├── references/
└── assets/
```

## 書き方

- `name` と `description` を frontmatter に入れます。
- `description` には、いつ使うかと使わないかを明確に書きます。
- `SKILL.md` では、実行手順より判断手順を優先します。
- skill 内で repo 正本を再定義しません。必要な文書へリンクします。

## 整理ルール

- AgentCanon public skill の追加は `agents/skills/<skill>.md` と `catalog.yaml`、project 固有 skill の追加はその repository の `.agents/skills/` で行います。
- Skill 編集の検査は変更した契約から選びます。補助診断は [Optional Rejection Prediction](../../agents/COMMUNICATION_PROTOCOL.md#optional-rejection-prediction) に従い、文書編集の開始条件にしません。
- Skill 内の code fence に `KEY=value` 形式の機械出力例を追加・削除した場合は `python3 tools/runtime/archive/log_surface_inventory.py --root . --check --baseline documents/runtime/log-surface-inventory.json` を通し、意図した field change なら `documents/runtime/log-surface-inventory.json` を再生成します。
