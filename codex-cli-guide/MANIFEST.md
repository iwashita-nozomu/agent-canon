<!--
@dependency-start
responsibility Documents the split-file manifest, source ranges, and integrity checks for the Codex CLI guide.
upstream content codex_cli_guide_config_deepdive.md generated from prior TeX/PDF artifact in this ChatGPT session.
downstream documentation codex-cli-guide/README.md links this file from the split guide index.
@dependency-end
-->

# Split manifest

This manifest records the source ranges used to split the Codex CLI guide into GitHub-readable Markdown files.

## Source

| Field | Value |
|---|---:|
| Source path before split | `codex_cli_guide_config_deepdive.md` |
| Source lines | 12,386 |
| Source bytes | 365,270 |
| Source sha256 | `3162bba298864e43fe175b85c52cbd4735d93b37479a7d6a847fd5e737bbc157` |

## Sections

| Path | Title | Source lines | Lines | Bytes | SHA-256 |
|---|---|---:|---:|---:|---|
| `sections/01-overview-and-basic-usage.md` | 概要・基本操作・設定リファレンス導入 | 1-1009 | 1,009 | 71,402 | `1f2224aa461c3680080e90aea5da5ba3d1c822e13d28a5448f2424c06f0c4e78` |
| `sections/02-project-operations-and-subagents.md` | プロジェクト内運用とサブエージェント設計 | 1010-2637 | 1,628 | 55,158 | `9dc5532ce0b9e0973bbbba35f153c570961fe93bd20c3f593ab1406d2933e1c7` |
| `sections/03-experimental-features.md` | 最新・実験的機能の徹底解説 | 2638-2976 | 339 | 11,663 | `efacd87ac2f3c80a0d5090d1dfa18a23ca3858d63517f85d5fa7361ea0e4f981` |
| `sections/04-mcp-deep-dive.md` | MCPの基礎から定義・運用・デバッグまで | 2977-3985 | 1,009 | 25,651 | `63e637de165c7203a483c9d66d5076d873301d370db12eae35ff6777e12edda4` |
| `sections/05-operation-pattern-diagrams.md` | MCPと実験機能の運用パターン図解 | 3986-4526 | 541 | 8,991 | `1232210f62464e8bb053dfedd83baf24c4b3290fdfbb4d0f637cd7ae361ebb6c` |
| `sections/06-practice-cards-mcp-experiments.md` | 実務カード集: MCPと実験機能パターン | 4527-5633 | 1,107 | 23,237 | `aac0698dd013797fc78718d0af953659319a1ff38a05a867f75c3c0e2e19a9e5` |
| `sections/07-configuration-writing-fundamentals-and-recipes-001-113.md` | 設定の書き方完全増補とレシピ001-113 | 5634-8964 | 3,331 | 90,328 | `f1ad25e66856eddd5526345c6c40852f3887de121399637c9d123c1f1a94eb2c` |
| `sections/08-additional-configuration-recipes-114-253.md` | 追加設定レシピ114-253 | 8965-11747 | 2,783 | 60,043 | `27b612a8da7bd9eb05559225bee2ad8d2e135d37871b8a6a88811eb1be89336b` |
| `sections/09-final-templates-and-references.md` | 最終追加テンプレート集と参考文献 | 11748-12386 | 639 | 18,797 | `e6b5487c3f3e0263fca9f54727a19a7959b9369e6153e68acd3677ddd78d9510` |

## Validation rule

`tools/validate_split.py` removes each generated dependency header and reads only the text after `<!-- split-content-start -->`.
It then concatenates all files in section order and compares the result with the full source body after the same marker.
