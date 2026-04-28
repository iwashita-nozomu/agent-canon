<!--
@dependency-start
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
downstream design ./codex-configuration-reference.md Codex configuration reference
downstream design ./codex-configuration-slides.md Codex configuration slide deck
downstream design ./object-oriented-design.md general OOP coding policy
@dependency-end
-->

# documents/

`documents/` は repo 固有の文書置き場です。
template の初期状態では、ここを shared workflow のリンク集にしません。

派生 repo では、その repo に固有の規約、設計、contract、運用メモだけをここに置きます。

## Canon Runtime References

- [Codex Configuration Reference](./codex-configuration-reference.md): Codex CLI / config schema / hooks / MCP / skills / subagents の設定一覧。
- [Codex Configuration Slides](./codex-configuration-slides.md): 上記 reference から作成した Markdown slide deck。

## Coding Policy References

- [Object-Oriented Design Policy](./object-oriented-design.md): class、dataclass、Protocol、composition、継承の判断基準。
