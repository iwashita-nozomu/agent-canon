<!--
@dependency-start
contract reference
responsibility Documents the split-file manifest, source ranges, and integrity checks for the Codex CLI guide.
upstream design source/codex_cli_guide_config_deepdive.full.md preserved generated guide body with runtime hook flag normalization.
@dependency-end
-->

# Split manifest

This manifest records the source ranges used to split the Codex CLI guide into GitHub-readable Markdown files.

## Source

| Field | Value |
|---|---:|
| Source path before split | `codex_cli_guide_config_deepdive.md` |
| Source lines | 12,386 |
| Source bytes | 365,144 |
| Source sha256 | `67405e3d88280008c71e01d2cb3403d3842734bfb4ce9e27474a8a87e3988510` |

## Sections

| Path | Title | Source lines | Lines | Bytes | SHA-256 |
|---|---|---:|---:|---:|---|
| `sections/01-overview-and-basic-usage.md` | 概要・基本操作・設定リファレンス導入 | 1-1009 | 1,009 | 71,396 | `efef9894b76b37eabf4605a7dc89f86a50af8776c97cc06f3c3bcd2ee0d7e1db` |
| `sections/02-project-operations-and-subagents.md` | プロジェクト内運用とサブエージェント設計 | 1010-2637 | 1,628 | 55,128 | `b54f804cb0fb532f56c23e5546796b5a7afc7fd326115efb37b3e12a6930c8a3` |
| `sections/03-experimental-features.md` | 最新・実験的機能の徹底解説 | 2638-2976 | 339 | 11,657 | `55558ab47dfafd28d315543b1e0d72d0052c02bdec6cb84f7668542ddf2b3527` |
| `sections/04-mcp-deep-dive.md` | MCPの基礎から定義・運用・デバッグまで | 2977-3985 | 1,009 | 25,645 | `bf55330bf9141b953fc928d54c80fc6637f4e48fca820519c3c1f6cf0cc66abe` |
| `sections/05-operation-pattern-diagrams.md` | MCPと実験機能の運用パターン図解 | 3986-4526 | 541 | 8,991 | `1232210f62464e8bb053dfedd83baf24c4b3290fdfbb4d0f637cd7ae361ebb6c` |
| `sections/06-practice-cards-mcp-experiments.md` | 実務カード集: MCPと実験機能パターン | 4527-5633 | 1,107 | 23,237 | `aac0698dd013797fc78718d0af953659319a1ff38a05a867f75c3c0e2e19a9e5` |
| `sections/07-configuration-writing-fundamentals-and-recipes-001-113.md` | 設定の書き方完全増補とレシピ001-113 | 5634-8964 | 3,331 | 90,280 | `f8f5db773c16f803d8c363be84b2e2031b835479625e0884a203469770f594dd` |
| `sections/08-additional-configuration-recipes-114-253.md` | 追加設定レシピ114-253 | 8965-11747 | 2,783 | 60,019 | `cc6289eb3816b7ed64567bf7142b12c1ff733d352c8ef5e9f4c38a0c660c1243` |
| `sections/09-final-templates-and-references.md` | 最終追加テンプレート集と参考文献 | 11748-12386 | 639 | 18,791 | `6a74fc46a980bb27ce904141272a016d3469b68142f7c076fb3fcdd0f4d11bd7` |

## Validation rule

`tools/validate_split.py` removes each generated dependency header and reads only the text after `<!-- split-content-start -->`.
It then concatenates all files in section order and compares the result with the full source body after the same marker.
