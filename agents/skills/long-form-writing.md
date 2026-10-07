# long-form-writing
<!--
@dependency-start
contract skill
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design formal-proof-workflow.md mathematical claim proof-obligation routing
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

README、workflow、guide、migration、specification などの一般説明 prose を、既存本文・根拠・構成メモから作成/改稿します。
選択基準は長さではなく file/document responsibility です。paper、thesis、scholarly note、report は各 owner を優先します。

## Procedure

1. `summary statement` で主張、目的、reader を短く固定し、既存本文・見出し・source map を読む。
2. section order、reader path、responsibility、canonical source、split/merge、invalid interpretation が未決定なら `structure-planning` を使う。typo/link/format-only は `md-style-check` で足りる。
3. roadmap と section contract を作り、reader order で draft する。workflow/dependency/ownership/state/handoff が読者判断の中心なら、図を選ぶ理由を決め、選択時だけ `code-visualization` に完全な source facts の rendering/readback を委譲する。
4. 数学的または implementation-derived claim は、必要なら `formal-proof-workflow` に渡し、scope・assumption・limitation・validation route として prose に射影する。
5. reverse outline を取り、`document_flow_reviewer` と docs-completeness review を通す。複数 entrypoint/文書を変えた場合だけ consistency review を追加する。
6. `tools/bin/agent-canon docs check` で閉じる。

## Boundary

この skill は approved structure を prose にする owner です。構造 decision、paper/academic prose、report evidence、Markdown の体裁だけの check はそれぞれ `structure-planning`、`paper-writing`/`academic-writing`、`report-writing`、`md-style-check` に委譲します。
