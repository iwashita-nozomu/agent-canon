<!--
@dependency-start
responsibility Provides the root index and navigation for the split OpenAI Codex CLI Japanese guide.
upstream content codex_cli_guide_config_deepdive.md generated from prior TeX/PDF artifact in this ChatGPT session.
downstream documentation codex-cli-guide/README.md links this file from the split guide index.
@dependency-end
-->

# OpenAI Codex CLI 実用ガイド（Markdown分割版）

このディレクトリは、単一Markdown版 `codex_cli_guide_config_deepdive.md` を GitHub で読みやすい章単位に分割したものです。
配置先は `agent-canon` リポジトリのルート直下 `codex-cli-guide/` を想定しています。

## 収録方針

- 元のMarkdown本文は `source/codex_cli_guide_config_deepdive.full.md` に完全収録しています。
- 章別の本文は `sections/` に分割しています。
- `tools/validate_split.py` で、`sections/` を連結した本文が `source/` の完全版と一致することを検証できます。
- このREADMEや各ファイル冒頭の dependency manifest は、AgentCanon の文書運用に合わせて追加したメタ情報です。検証スクリプトは `<!-- split-content-start -->` 以降だけを本文として扱います。

## 原本情報

- title: OpenAI Codex CLI 実用ガイド 設定実践完全版
- generated: 2026-05-08
- source line count: 12,386
- source byte count: 365,270
- source sha256: `3162bba298864e43fe175b85c52cbd4735d93b37479a7d6a847fd5e737bbc157`

## 章別ファイル

- [`sections/01-overview-and-basic-usage.md`](sections/01-overview-and-basic-usage.md) — 概要・基本操作・設定リファレンス導入（source lines 1-1009）
- [`sections/02-project-operations-and-subagents.md`](sections/02-project-operations-and-subagents.md) — プロジェクト内運用とサブエージェント設計（source lines 1010-2637）
- [`sections/03-experimental-features.md`](sections/03-experimental-features.md) — 最新・実験的機能の徹底解説（source lines 2638-2976）
- [`sections/04-mcp-deep-dive.md`](sections/04-mcp-deep-dive.md) — MCPの基礎から定義・運用・デバッグまで（source lines 2977-3985）
- [`sections/05-operation-pattern-diagrams.md`](sections/05-operation-pattern-diagrams.md) — MCPと実験機能の運用パターン図解（source lines 3986-4526）
- [`sections/06-practice-cards-mcp-experiments.md`](sections/06-practice-cards-mcp-experiments.md) — 実務カード集: MCPと実験機能パターン（source lines 4527-5633）
- [`sections/07-configuration-writing-fundamentals-and-recipes-001-113.md`](sections/07-configuration-writing-fundamentals-and-recipes-001-113.md) — 設定の書き方完全増補とレシピ001-113（source lines 5634-8964）
- [`sections/08-additional-configuration-recipes-114-253.md`](sections/08-additional-configuration-recipes-114-253.md) — 追加設定レシピ114-253（source lines 8965-11747）
- [`sections/09-final-templates-and-references.md`](sections/09-final-templates-and-references.md) — 最終追加テンプレート集と参考文献（source lines 11748-12386）

## 検証

```bash
python3 codex-cli-guide/tools/validate_split.py
```

期待される出力は、source SHA、reconstructed SHA、section数、line数が一致することです。

## PR作成時の推奨タイトル

```text
Add split OpenAI Codex CLI guide
```

## PR作成時の要約

```text
Adds a split Markdown version of the generated OpenAI Codex CLI guide under codex-cli-guide/.
The full source Markdown is preserved, and section files are validated by tools/validate_split.py.
```
