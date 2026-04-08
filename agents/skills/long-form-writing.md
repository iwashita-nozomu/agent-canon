# long-form-writing

## Purpose

長い説明文書を、先に reader path と review を固定したうえで書くための skill です。

## Use When

- README、guide、workflow、migration 文書を書く
- 設計補助文書や reader-facing な長文を新規作成する
- section の並び、argument、手順、判断軸を伴う文書を書く

## Core References

- `documents/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/docs-completeness-review.md`
- `agents/skills/docs-consistency-review.md`

## Mandatory Checklist

- `summary statement` で argument、purpose、reader を先に固定する
- 見出し列を roadmap として先に作る
- section ごとに `focus`、`purpose`、`support` を固定する
- draft 後に reverse outline を取る
- `document_flow_reviewer` を必ず通す
- 別 reviewer で `docs-completeness-review` を必ず通す
- 複数文書や entrypoint をまたぐなら `docs-consistency-review` を追加する
- wording より先に higher-order concerns を直す

## Default Sequence

1. `summary statement` を短く書く
1. roadmap と section contract を作る
1. reader order で draft する
1. reverse outline で section order と gap を確認する
1. `document_flow_reviewer` を通す
1. 別 reviewer で `docs-completeness-review` を通す
1. 必要なら `docs-consistency-review` を追加する
1. `make docs-check` で閉じる

## Boundary

- 論文、thesis chapter、scholarly note のような学術文章は `academic-writing` を優先します
- 実験 report の review policy は `report-review` を優先します
- repo-wide な workflow 改造は `agent-orchestration` も併用します
- Markdown の体裁だけなら `md-style-check` を使います
