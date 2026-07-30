# paper-writing
<!--
@dependency-start
contract skill
responsibility Documents paper-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable paper structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
@dependency-end
-->


## Reader Map

- Purpose: routes submission-paper or thesis-chapter drafting through section
  contracts, citation evidence, notation, and logic review.
- Use When: the artifact is a paper-style manuscript rather than general
  academic notes.
- Section path: Purpose, Use When, and Core References set scope; Mandatory
  Checklist, Default Sequence, and Standard Command are operational rules;
  Boundary limits the paper route.
- Boundary: broader scholarly prose outside paper ownership uses
  `academic-writing`.

## Purpose

file / document responsibility が submission paper、thesis chapter、または paper-style
manuscript の文書を、共通 graph/DSL 構造から paper prose へ射影する adapter skill です。
section contract と citation/evidence trace を先に固定し、複数 reviewer で検証します。
選択基準は長さではなく、paper section contract と citation/evidence review が必要な責務です。

## Use When

- 投稿論文や thesis chapter の draft を作る
- abstract、introduction、related work、method、results、discussion を持つ paper-like 文書を書く
- citation、figure、table、appendix、result の参照関係を author 1 人の勘に任せたくない
- academic-writing より一段 paper-specific な section discipline が欲しい
- file responsibility の判定結果が、一般説明 prose や report ではなく paper prose adapter を要求している

## Core References

- `agents/workflows/paper-writing-workflow.md`
- `agents/workflows/academic-writing-workflow.md`
- `agents/workflows/long-form-writing-workflow.md`
- `documents/conventions/REVIEW_PROCESS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/skills/academic-writing.md`

## Mandatory Checklist

- `paper intent brief` と `claim contract` を先に固定する
- section order、first figure/table、claim/evidence layout が非自明な場合は `structure-planning` で構造 contract を先に固定する
- paragraph-level claim flow、transition pair、logic gap が論点なら、`structure-planning` で `agent-canon semantic-index discourse-relations --profile academic-argument` を使う
- 非自明な paper prose の新規作成・改稿では、reader-facing prose の前に `prose-reasoning-graph` の handoff を作るか受け取る
- prose graph diagnostics は claim/evidence gaps、weak transitions、experiment-plan gaps、split/merge/bridge/reorder operations を section contract と reviewer handoff に入れる
- prose graph handoff に `selected_ordering.ordered_anchors` がある場合は、全文 sentence anchor の topological order を DSL-to-prose input sequence として使う
- graph responsibility は肯定形の paper prose contract に射影する。section role、claim、citation/evidence relation、result claim、limitation、reviewer handoff を直接書く。否定形の boundary は Boundary / Limitation / Non-Goal slot に集約し、`ad hoc` label は責務名、evidence gap、verification route、prompt-defect classification のいずれかへ置き換える
- reader-facing prose に入る前に DSL / projection 段階で `fix-now` finding を閉じる。section contract、citation/evidence matrix、paragraph claim map、graph-backed rewrite packet、または graph-backed unit を直し、graph diagnostics を再実行してから draft する
- DSL / projection から prose に射影した後、同じ graph check を再実行する。閉じた DSL/projection には無かった finding が射影後に出た場合は `dsl_to_prose_prompt_defect` として paper prose-generation prompt を直す
- `section contract` を `abstract`, `introduction`, `related work`, `method`, `results`, `discussion`, `limitations`, `conclusion` の粒度で決める
- `citation and evidence matrix` を作り、主要 claim がどの citation / figure / table / derivation / appendix に支えられるかを書く
- `notation ledger` と `paragraph claim map` を作る
- run bundle を先に作り、`citation_evidence_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、`document_flow_reviewer` を explicit に有効化する
- draft 後に reverse outline を取り、review 前に section role の重複を潰す
- `document_flow_reviewer`、citation review、notation review、logic-gap review、別 reviewer の docs completeness review を必ず通す

## Default Sequence

1. `paper intent brief` と `claim contract` を書く
1. 必要なら `structure-planning` で first section / figure / table、source-to-structure map、section order、invalid interpretation を固定する
1. paragraph claim map の順序に疑義がある場合は discourse-relations JSONL を構造 evidence として添付する
1. `section contract` を書く
1. `citation and evidence matrix` と `notation ledger` を作る
1. `paragraph claim map` を作る
1. 非自明な paper prose なら prose graph handoff を作るか受け取り、DSL / projection finding closure loop を回してから reader-facing prose に入る
1. run bundle を作る
1. reader order で draft する
1. reverse outline を取る
1. `document_flow_reviewer` を通す
1. `citation_evidence_reviewer` に citation review を通す
1. `notation_definition_reviewer` に notation review を通す
1. `logic_gap_reviewer` に logic-gap review を通す
1. 別 reviewer に docs completeness review を通す
1. higher-order revision を終えてから line edit に入る
1. `tools/bin/agent-canon docs check` で閉じる

## Standard Command

```bash
python3 tools/agent_tools/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Boundary

- paper-like でない学術文章や method note は `academic-writing` を使います
- 文献探索自体が主タスクなら `literature-survey` を先に使います
- rebuttal や report の evidence traceability を主に見たいなら report review を追加します

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/paper-writing.md`.
1. Read `agents/workflows/paper-writing-workflow.md`.
1. Read `agents/workflows/academic-writing-workflow.md`.
1. Select this as the DSL-to-prose projection adapter when file/document responsibility is submission paper, thesis chapter, or paper-style manuscript with paper section contracts and citation/evidence review; do not select it by length.
1. Use `$structure-planning` before drafting when section order, first figure/table, claim/evidence layout, source-to-structure map, or invalid interpretations are nontrivial.
1. For paragraph-level claim flow, transition pairs, or logic-gap triage, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile academic-argument` and treat it as advisory discourse evidence before prose drafting.
1. For nontrivial paper prose creation or revision, create or receive a `$prose-reasoning-graph` handoff before drafting; include its claim/evidence gaps, weak transitions, experiment-plan gaps, and split/merge/bridge/reorder operations in the section contract and reviewer handoff.
1. When the prose graph handoff includes `selected_ordering.ordered_anchors`, use that whole-document topological sentence order as the DSL-to-prose input sequence before drafting paper sections or paragraph transitions.
1. Project paper responsibilities into positive prose contracts: state each section role, claim, citation/evidence relation, result claim, limitation, and reviewer handoff directly. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Before writing paper prose, close `fix-now` findings at the DSL/projection stage: revise the section contract, citation/evidence matrix, paragraph claim map, graph-backed rewrite packet, or graph-backed units, rerun graph diagnostics, and only draft prose after the selected profile has no active findings.
1. After projecting DSL/projection state to paper prose, rerun the graph check. If new findings appear only after projection, record `dsl_to_prose_prompt_defect` against this skill's paper prose-generation prompt and repair it before continuing.
1. Fix the paper intent brief, claim contract, section contract, citation/evidence matrix, notation ledger, and paragraph claim map before drafting.
1. Route citation/evidence review, notation review, logic-gap review, and document-flow review as separate review passes before closeout.
