# long-form-writing
<!--
@dependency-start
contract skill
responsibility Documents long-form-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design formal-proof-workflow.md mathematical claim proof-obligation routing
upstream design code-visualization.md visualization selection and native renderer delegation
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

README、workflow、guide、migration、specification などの一般説明 prose を、既存本文・根拠・構成メモから作成/改稿します。
選択基準は長さではなく file/document responsibility です。paper、thesis、scholarly note、report は各 owner を優先します。

## Procedure

Read the request, existing text and headings, and canonical source. State the
purpose and reader in the amount of detail needed to guide the revision. Use
`structure-planning` only when the owner, reader path, section order,
split/merge, or invalid interpretation still has a material unresolved choice;
use `md-style-check` for a wording-independent typo, link, or formatting fix.

Draft from the selected structure. If a diagram would clarify workflow,
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

この skill は approved structure を prose にする owner です。構造 decision、paper/academic prose、report evidence、Markdown の体裁だけの check はそれぞれ `structure-planning`、`paper-writing`/`academic-writing`、`report-writing`、`md-style-check` に委譲します。
