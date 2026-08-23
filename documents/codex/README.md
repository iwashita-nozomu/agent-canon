<!--
@dependency-start
contract reference
responsibility Codex、skill、prompt、GitHub automation の設定文書入口。
upstream design ../README.md documents 索引と正本境界。
downstream implementation ../../.codex/config.toml Codex runtime 設定。
@dependency-end
-->

# Codex 運用

この directory は Codex の設定、エージェント運用、skill 実装、prompt 評価、GitHub
Copilot 境界を説明します。実際の runtime 設定や skill の正本は `.codex/`、`.agents/`
および `agents/` にあり、ここは読者向けの設計・運用文書です。

## 構成

- `codex-configuration-reference.md`: 設定 surface の読者向け説明。
- `codex-configuration-slides.md`: 設定構造の視覚的説明。
- `AGENTS_COORDINATION.md`: エージェント運用の入口。
- `SKILL_IMPLEMENTATION_GUIDE.md`: skill 実装の方針。
- `prompt-skill-evaluation-checklist.md`: prompt と skill の評価契約。
- `github-copilot-configuration.md`: GitHub automation の設定境界。

runtime の詳細は workflow と canonical agent 文書から参照します。
