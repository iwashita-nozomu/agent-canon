# long-form-writing
<!--
@dependency-start
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
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
- 文書 task が prompt / routing / subagent-config canon も触るなら、prose を広く書き換える前に `prompt_config_reviewer` で prompt/config audit を切る
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
1. paragraph order / transition evidence が必要なら discourse-relations JSONL を構造 contract に添付する
1. roadmap と section contract を作る
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
