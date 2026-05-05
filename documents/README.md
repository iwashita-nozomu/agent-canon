<!--
@dependency-start
responsibility Documents documents/ for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
downstream design ./algorithm-implementation-boundary.md algorithm math-to-code boundary policy
downstream design ./codex-configuration-reference.md Codex configuration reference
downstream design ./codex-configuration-slides.md Codex configuration slide deck
downstream design ./object-oriented-design.md general OOP coding policy
downstream design ./result-log-retention-and-visualization.md result artifact policy
downstream design ./repo-local-tool-imports.md repo-local tool import ledger
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

- [Algorithm Implementation Boundary Policy](./algorithm-implementation-boundary.md): 数理・仕様境界と implementation boundary の対応表、変更種別、review gate。
- [Object-Oriented Design Policy](./object-oriented-design.md): class、dataclass、Protocol、composition、継承の判断基準。

## Tooling And Artifact References

- [Result Log Retention And Visualization](./result-log-retention-and-visualization.md): run result、summary、visualization artifact、retention decision の正本ルール。
- [Repo-Local Tool Imports](./repo-local-tool-imports.md): 派生 repo で育った tool を AgentCanon に取り込むときの disposition 台帳。
