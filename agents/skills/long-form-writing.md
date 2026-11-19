# long-form-writing
<!--
@dependency-start
contract skill
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design ../../ROOT_AGENTS.md general documentation boundary
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design formal-proof-workflow.md mathematical claim proof-obligation routing
upstream design code-visualization.md visualization selection and native renderer delegation
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this adapter dependency header
@dependency-end
-->

## Purpose

README、workflow、guide、migration、specification などの一般説明 prose を、既存本文・根拠・構成メモから作成/改稿します。
文書の責務に応じて選び、paper、thesis、scholarly note、report は各 owner を優先します。

## Procedure

Read the request, existing text and headings, and canonical source. State the
purpose and reader in the amount of detail needed to guide the revision. Use
[structure-planning](structure-planning.md#before-prose) to settle section order
and source support before drafting. A bounded wording edit can retain the
existing structure; use `md-style-check` for a wording-independent typo, link,
or formatting fix.

Write explanatory prose from the selected structure using established facts and
their sources. Give the reader a link to the relevant runbook or execution record
as the entire treatment of commands, steps, setup, and execution conditions.
Before returning the text, replace any such details in the body, examples,
notes, or tables with that link. A requested how-to places the requested steps
in its own procedure.

設計文書の「目的」は、解く問題と達成したい状態を一文で示します。
方式の説明、構成要素の責務、API の振舞いと失敗時の保証は「責務と公開境界」にまとめ、
各項目を一度だけ書きます。「設計判断と根拠」は採用方式を名称で指し、比較で観測した
事実と、それが採用を支える理由に絞ります。観測の適用範囲は該当する事実のそばに置きます。
未決事項は依頼で尋ねられたものを扱います。提出前に各節を読み合わせ、同じ契約や方式を
目的や根拠で言い換えている箇所を削ります。

If a diagram would clarify workflow,
dependency, ownership, state, or handoff, explain the specific question it
answers and use `code-visualization` for its selected rendering. Route a
mathematical or implementation-derived claim through `formal-proof-workflow`
when that proof is part of the request; present its scope, assumptions,
limitations, and validation evidence accurately.
For the selected renderer, provide its native input and check the requested
output.

Review the reader path and completeness against the requested scope. Use
`document_flow_reviewer` for a structural gap and add docs-completeness or
cross-document consistency review only when the changed material requires it.
Run `tools/bin/agent-canon docs check` when selected for the document.

## Boundary

この skill は selected structure を prose にする owner です。構造 decision、paper/academic prose、report
evidence、Markdown の体裁だけの check はそれぞれ `structure-planning`、`paper-writing`/`academic-writing`、
`report-writing`、`md-style-check` に委譲します。Requested native Google Docs delivery と明示的な Yomiyasu
polish は [external handoffs](README.md#installed-external-skill-handoffs) を使い、本文の範囲・主張はこの owner に残します。
