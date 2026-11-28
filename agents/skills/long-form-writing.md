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

Write from established facts and their sources. In explanatory prose, link to
the relevant runbook or execution record for commands, setup, and conditions.
Put the steps for a requested how-to in its procedure.

設計文書では、節ごとに異なる内容を書きます。

- **目的**は利用者やシステムが必要とする結果の一文で完結させます。例は「長い集計の間も画面を使えるようにする」です。
- **責務と公開境界**に方式、構成要素の役割、受付や失敗時の保証を各一回書きます。
- **設計判断と根拠**は比較で観測した事実と採用理由に絞ります。方式を指すときは名称を使います。

提出前に目的を読み返し、方式・構成・API が何をするかの説明は公開境界にだけ残します。
同じ保証を言い換えた文も一か所にまとめます。未決事項は依頼で尋ねられたものだけを扱い、
観測結果の意味を左右する根拠の限界は該当する事実のそばに置きます。

If a diagram would clarify workflow, dependency, ownership, state, or handoff,
state the question it answers and use `code-visualization`. Route a
mathematical or implementation-derived claim through `formal-proof-workflow`
when that proof is part of the request; present its scope, assumptions,
limitations, and validation evidence accurately.

Review the reader path and completeness against the requested scope. Use
`document_flow_reviewer` for a structural gap and add docs-completeness or
cross-document consistency review only when the changed material requires it.
Run `tools/bin/agent-canon docs check` when selected for the document.

## Boundary

この skill は selected structure を prose にする owner です。構造 decision、paper/academic prose、report
evidence、Markdown の体裁だけの check はそれぞれ `structure-planning`、`paper-writing`/`academic-writing`、
`report-writing`、`md-style-check` に委譲します。Requested native Google Docs delivery と明示的な Yomiyasu
polish は [external handoffs](README.md#installed-external-skill-handoffs) を使い、本文の範囲・主張はこの owner に残します。
