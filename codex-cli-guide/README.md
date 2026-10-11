<!--
@dependency-start
contract reference
responsibility Provides the root index and navigation for the retained OpenAI Codex CLI Japanese guide sections.
@dependency-end
-->

# OpenAI Codex CLI 実用ガイド（Markdown分割版）

このディレクトリは、OpenAI Codex CLI の設定実践ガイドを GitHub で読みやすい章単位に整理した静的スナップショットです。
配置先は `agent-canon` リポジトリのルート直下 `codex-cli-guide/` を想定しています。

## 収録方針

- 本文は `sections/` の9章で読めます。
- このREADMEや各ファイル冒頭の dependency manifest は、AgentCanon の文書運用に合わせて追加したメタ情報です。

## Runtime compatibility note

The split body is a preserved generated reference, not the template's current
configuration recommendation. Current project settings use stable Codex
defaults, `.codex/hooks.json` for hook declarations, automatic
`.agents/skills/` discovery, and user-level config for reusable profiles.

## スナップショット情報

- title: OpenAI Codex CLI 実用ガイド 設定実践完全版
- generated: 2026-05-08

## 章別ファイル

- [`sections/01-overview-and-basic-usage.md`](sections/01-overview-and-basic-usage.md) — 概要・基本操作・設定リファレンス導入
- [`sections/02-project-operations-and-subagents.md`](sections/02-project-operations-and-subagents.md) — プロジェクト内運用とサブエージェント設計
- [`sections/03-experimental-features.md`](sections/03-experimental-features.md) — 最新・実験的機能の徹底解説
- [`sections/04-mcp-deep-dive.md`](sections/04-mcp-deep-dive.md) — MCPの基礎から定義・運用・デバッグまで
- [`sections/05-operation-pattern-diagrams.md`](sections/05-operation-pattern-diagrams.md) — MCPと実験機能の運用パターン図解
- [`sections/06-practice-cards-mcp-experiments.md`](sections/06-practice-cards-mcp-experiments.md) — 実務カード集: MCPと実験機能パターン
- [`sections/07-configuration-writing-fundamentals-and-recipes-001-113.md`](sections/07-configuration-writing-fundamentals-and-recipes-001-113.md) — 設定の書き方完全増補とレシピ001-113
- [`sections/08-additional-configuration-recipes-114-253.md`](sections/08-additional-configuration-recipes-114-253.md) — 追加設定レシピ114-253
- [`sections/09-final-templates-and-references.md`](sections/09-final-templates-and-references.md) — 最終追加テンプレート集と参考文献
