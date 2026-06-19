# Skill 実装ガイド
<!--
@dependency-start
contract reference
responsibility Documents Skill 実装ガイド for this repository.
upstream design README.md durable document index
@dependency-end
-->


この文書は、repo で使う project skill の実装指針です。
現在の正本は `agents/` と discovery path の skill directory です。

## 正本

- 人間向けハブ: `agents/README.md`
- canonical layout: `agents/canonical/README.md`
- skill registry: `agents/canonical/skills.md`
- human skill canon: `agents/skills/README.md`
- machine-readable skill catalog: `agents/skills/catalog.yaml`
- artifact placement canon: `agents/canonical/ARTIFACT_PLACEMENT.md`
- CLI entrypoint canon: `agents/canonical/CLI_ENTRYPOINTS.md`
- Codex workflow canon: `agents/canonical/CODEX_WORKFLOW.md`
- Codex discovery path: `.agents/skills/`

## 方針

- skill は少数の workflow-oriented unit に保ちます。
- numbered skill catalog は増やしません。
- skill ごとの instructions は `SKILL.md` に集約します。
- 再利用可能な workflow は skill にし、repo 全体の恒久ルールは `documents/` または `agents/` に置きます。
- shared discovery shim は `.agents/skills/` を正本にし、互換 path は同期スクリプトで更新します。

## 推奨 skill directory

```text
<skill-name>/
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

- 新しい skill を追加するときは `agents/canonical/skills.md` を更新します。
- Skill の `SKILL.md` や `agents/skills/*.md` を編集する前に `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` を実行し、`log_surface_inventory_guard` が予測された場合は log-surface baseline check を同じ変更内で通します。
- Skill 内の code fence に `KEY=value` 形式の機械出力例を追加・削除した場合は `python3 tools/agent_tools/log_surface_inventory.py --root . --check --baseline documents/log-surface-inventory.json` を通し、意図した field change なら `documents/log-surface-inventory.json` を再生成します。
