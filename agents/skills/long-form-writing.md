# long-form-writing
<!--
@dependency-start
contract skill
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design ../internal-routines/verification-result-structuring.md reader reconstruction and relevant qualifications
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

Draft from the selected structure, applying
[reader reconstruction](../internal-routines/verification-result-structuring.md#reader-reconstruction)
for necessary context and relevant qualifications. If a diagram would clarify workflow,
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
