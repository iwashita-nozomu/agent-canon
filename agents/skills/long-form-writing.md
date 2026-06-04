# long-form-writing
<!--
@dependency-start
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
@dependency-end
-->


## Purpose

長い説明文書を、先に reader path と review を固定したうえで書くための skill です。

## Use When

- README、guide、workflow、migration 文書を書く
- 設計補助文書や reader-facing な長文を新規作成する
- section の並び、argument、手順、判断軸を伴う文書を書く

## Core References

- `agents/workflows/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`

## Mandatory Checklist

- `summary statement` で argument、purpose、reader を先に固定する
- section order、reader path、source map、invalid interpretation が非自明な場合は `structure-planning` で構造 contract を先に固定する
- paragraph flow や transition choice が論点なら、`structure-planning` で `agent-canon semantic-index discourse-relations --profile general` または `--profile academic-argument` を使う
- prose graph handoff がある場合は、diagnostics / explanation / integration plan を section order、paragraph bridge、split / merge の evidence として使う
- prose graph handoff から本文を書く場合は、reader-facing prose に入る前に DSL / projection 段階で `fix-now` finding を閉じる。structure contract または graph-backed rewrite packet を直し、graph diagnostics を再実行し、selected profile の active finding がなくなってから draft する
- process、dependency、ownership、routing、state transition、review gate、multi-step flow が読者理解の中心なら、`structure-planning` の `visual_plan` で Mermaid 図を既定候補にし、Markdown 内に fenced `mermaid` block として残す
- 見出し列を roadmap として先に作る
- section ごとに `focus`、`purpose`、`support` を固定する
- draft 後に reverse outline を取る
- `document_flow_reviewer` を必ず通す
- 別 reviewer で docs completeness review を必ず通す
- 複数文書や entrypoint をまたぐなら docs consistency review を追加する
- wording より先に higher-order concerns を直す

## Default Sequence

1. `summary statement` を短く書く
1. 必要なら `structure-planning` で first section、source-to-structure map、section order、invalid interpretation を固定する
1. workflow、dependency、ownership、routing、state、review gate、handoff の説明がある場合は、first visual として Mermaid 図を置くか、`visual_plan=text-only` の理由を残す
1. paragraph order / transition evidence が必要なら discourse-relations JSONL を構造 contract に添付する
1. roadmap と section contract を作る
1. prose graph handoff が active なら、DSL / projection finding closure loop を回してから reader-facing prose に入る
1. 必要なら `python3 tools/agent_tools/doc_start.py --kind long-form ...` で run bundle と review 宣言を先に起こす
1. reader order で draft する
1. reverse outline で section order と gap を確認する
1. `document_flow_reviewer` を通す
1. 別 reviewer で docs completeness review を通す
1. 必要なら docs consistency review を追加する
1. `make docs-check` で閉じる

## Boundary

- 論文、thesis chapter、scholarly note のような学術文章は `academic-writing` を優先します
- 実験 report の review policy は report review を優先します
- Markdown の体裁だけなら `md-style-check` を使います
