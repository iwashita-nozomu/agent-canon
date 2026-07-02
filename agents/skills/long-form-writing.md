# long-form-writing
<!--
@dependency-start
contract skill
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design formal-proof-workflow.md mathematical claim proof-obligation routing
@dependency-end
-->


## Reader Map

- Purpose: adapts a structure contract or reasoning graph into reader-facing
  prose for README, workflow, guide, migration, or specification documents.
- Use When: the file responsibility is explanatory prose and the reader path,
  claim support, or section projection must be written clearly.
- Section path: Purpose, Use When, and Core References set scope; Mandatory
  Checklist and Default Sequence are operational rules; Boundary limits prose
  ownership.
- Boundary: this skill projects approved structure into prose; it does not
  create the structure contract itself.

## Purpose

README、workflow、guide、migration、specification など、file responsibility が一般説明 prose の文書を
DSL / graph から reader-facing prose へ射影する adapter skill です。
skill 名は互換のため `long-form-writing` のままですが、選択基準は文章の長さではありません。

## Use When

- README、guide、workflow、migration 文書を書く
- 設計補助文書や reader-facing な説明文書を新規作成する
- section の並び、argument、手順、判断軸を伴う文書を書く
- file / document responsibility の判定結果が、report、academic paper、paper draft ではなく、一般説明 prose の projection adapter を要求している

## Core References

- `agents/workflows/long-form-writing-workflow.md`
- `documents/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`

## Mandatory Checklist

- `summary statement` で argument、purpose、reader を先に固定する
- 実質的な文書追記・修正では、reader-facing prose を足す前に対象文書の responsibility、reader path、section order、source map、上位 / 下位 canon との関係を構造解析する。typo、link、format-only、機械的な表記揺れ修正だけなら `md-style-check` で足りる。この handoff では runtime `SKILL.md` 読了を docs tool 実行や patching の前提にせず、owner boundary、existing-tool route、targeted validation を evidence に残す
- section order、reader path、source map、invalid interpretation が非自明な場合は `structure-planning` で構造 contract を先に固定する
- paragraph flow や transition choice が論点なら、`structure-planning` で `agent-canon semantic-index discourse-relations --profile general` または `--profile academic-argument` を使う
- 非自明な一般説明文書の新規作成・改稿では、reader-facing prose の前に `prose-reasoning-graph` の handoff を作るか受け取る。既存 repo Markdown なら `check-document` で prose diagnostics と document-canon diagnostics を同時に出す
- prose graph diagnostics / explanation / integration plan を section order、paragraph bridge、split / merge の evidence として使う
- 文書の分割、統合、inline 化、rename、現状維持を伴う場合は、`structure-planning` の `document_split_decision` を先に固定する。同じ owner、reader path、source map、validation route、update cadence を共有する内容は同じ文書の roadmap / section contract で処理し、本文量、token 量、chunking convenience、近い path、一時的な作業都合、同じ validation oracle を共有する連続説明を分割根拠にしない
- prose graph handoff に `selected_ordering.ordered_anchors` がある場合は、全文 sentence anchor の topological order を DSL-to-prose input sequence として使う
- graph responsibility は肯定形の prose contract に射影する。section、tool、workflow、document が何を担い、どの evidence が支えるかを直接書く。否定形の boundary は Boundary / Limitation / Non-Goal slot に集約し、`ad hoc` label は責務名、evidence gap、verification route、prompt-defect classification のいずれかへ置き換える
- 数学的 claim は、claim、assumptions、definitions、theorem target または
  proof obligation、`proof_status`、checker evidence に分解し、必要なら
  `$formal-proof-workflow` へ渡してから reader-facing prose に射影する。
  実装由来 claim では `program contract` を先に固定し、public entrypoint、
  入力 schema、runtime profile、return projection、observable effect、
  assumptions / preconditions、validation command を source map に入れる。
  provisional wording は run-local planning evidence として保持し、正本文書では
  scope、受け入れ条件、limitation、または validation route へ置換する
- reader-facing prose に入る前に DSL / projection 段階で `fix-now` finding を閉じる。structure contract または graph-backed rewrite packet を直し、graph-backed unit の追加・削除・分割・統合・順序変更を行い、graph diagnostics を再実行し、selected profile の active finding がなくなってから draft する
- DSL / projection から prose に射影した後、同じ graph check を再実行する。閉じた DSL/projection には無かった finding が射影後に出た場合は、通常の文書 finding ではなく `dsl_to_prose_prompt_defect` として prose-generation prompt を直す
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
1. 文書追記・修正が substantive かを判定する。section、責務、claim/support、reader path、source map、canonical route が変わるなら構造解析 gate を必須にし、typo / format-only ならその理由を残して省略する
1. 文書構造を変える、または現状維持を判断する場合は、`document_split_decision` を `keep:<reason>`、`split:<new-owner-boundary>`、`merge:<target>`、`inline:<target-section>`、`rename:<new-path>`、`not_applicable:format-only:<reason>` のいずれかとして固定する
1. 必要なら `structure-planning` で first section、source-to-structure map、section order、invalid interpretation を固定する
1. workflow、dependency、ownership、routing、state、review gate、handoff の説明がある場合は、first visual として Mermaid 図を置くか、`visual_plan=text-only` の理由を残す
1. paragraph order / transition evidence が必要なら discourse-relations JSONL を構造 contract に添付する
1. roadmap と section contract を作る
1. 非自明または substantive な一般説明文書の追記・修正なら prose graph handoff を作るか受け取り、DSL / projection finding closure loop を回してから reader-facing prose に入る
1. 必要なら `python3 tools/agent_tools/doc_start.py --kind long-form ...` で run bundle と review 宣言を先に起こす
1. reader order で draft する
1. DSL / projection から prose に射影した後、同じ graph check を再実行し、射影後だけの finding は `dsl_to_prose_prompt_defect` として記録する
1. reverse outline で section order と gap を確認する
1. `document_flow_reviewer` を通す
1. 別 reviewer で docs completeness review を通す
1. 必要なら docs consistency review を追加する
1. `tools/bin/agent-canon docs check` で閉じる

## Boundary

- 論文、thesis chapter、scholarly note のような学術文章は `academic-writing` を優先します
- 実験 report の review policy は report review を優先します
- Markdown の体裁だけなら `md-style-check` を使います
- 文書が短くても、責務が一般説明 prose ならこの adapter を使います。文書が長くても、責務が report、paper、academic note なら対応する adapter を使います
