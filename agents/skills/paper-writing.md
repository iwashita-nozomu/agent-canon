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
manuscript の文書を、既存の本文・根拠・構成メモから直接作成・改稿する skill です。
section contract と citation/evidence trace を先に固定し、複数 reviewer で検証します。
選択基準は長さではなく、paper section contract と citation/evidence review が必要な責務です。

## Use When

- 投稿論文や thesis chapter の draft を作る
- abstract、introduction、related work、method、results、discussion を持つ paper-like 文書を書く
- citation、figure、table、appendix、result の参照関係を author 1 人の勘に任せたくない
- academic-writing より一段 paper-specific な section discipline が欲しい
- file responsibility の判定結果が、一般説明 prose や report ではなく paper prose adapter を要求している

## Core References

- [agents/skills/academic-writing.md](academic-writing.md) (shared scholarly prose contract)
- [agents/skills/long-form-writing.md](long-form-writing.md) (general prose boundary)
- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)
- [agents/canonical/CODEX_SUBAGENTS.md](../canonical/CODEX_SUBAGENTS.md)

## Required Artifacts

- `paper intent brief`
- `claim contract`
- `section contract`
- `citation and evidence matrix`
- `notation ledger`
- `paragraph claim map`
- reverse outline

Artifacts may live in a run bundle or a linked note. Keep them readable by the
reviewers that use them; do not create a second canonical policy document.

## Standard Section Contract

Fix only the sections the paper needs, without merging distinct roles:

- `abstract`: problem, method, main result, and implication
- `introduction`: gap, contribution, and paper map
- `related work`: known results and the unresolved position
- `method`: setting, assumptions, notation, and procedure
- `results`: observations and measured outcomes
- `discussion`: interpretation, scope, and limitations
- `limitations`: material boundaries of the claims
- `conclusion`: contribution and next step

Each selected section records its purpose, main subclaim, prerequisites,
supporting citations or artifacts, and the message left to the reader.

## Mandatory Checklist

- 既存の本文・根拠・見出し・短い構成メモから直接執筆する。graph 分析は
  [任意の分析経路](prose-reasoning-graph.md#optional-analysis-boundary)であり、
  graph/DSL、固定 handoff、全 sentence の順序、finding 件数ゼロ、本文との往復診断を
  通常執筆の開始・完了条件にしない。主張と根拠の対応、引用、定義、構成は本文で確認する

- `paper intent brief` と `claim contract` を先に固定する
- section order、first figure/table、claim/evidence layout が非自明な場合は `structure-planning` で構造 contract を先に固定する
- paragraph-level claim flow、transition pair、logic gap が論点なら、`structure-planning` で `agent-canon semantic-index discourse-relations --profile academic-argument` を使う
- 文書の責務は肯定形の paper prose contract に射影する。section role、claim、citation/evidence relation、result claim、limitation、reviewer handoff を直接書く。否定形の boundary は Boundary / Limitation / Non-Goal slot に集約し、`ad hoc` label は責務名、evidence gap、verification route、prompt-defect classification のいずれかへ置き換える
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
1. run bundle を作る
1. reader order で draft する
1. reverse outline を取る
1. `document_flow_reviewer` を通す
1. `citation_evidence_reviewer` に [citation review](../internal-routines/citation-evidence-review.md) を通す
1. `notation_definition_reviewer` に notation review を通す
1. `logic_gap_reviewer` に logic-gap review を通す
1. 別 reviewer に docs completeness review を通す
1. higher-order revision を終えてから line edit に入る
1. `tools/bin/agent-canon docs check` で閉じる

## Standard Command

```bash
python3 tools/analysis/documents/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Boundary

- paper-like でない学術文章や method note は `academic-writing` を使います
- 文献探索自体が主タスクなら `literature-survey` を先に使います
- rebuttal や report の evidence traceability を主に見たいなら report review を追加します

## Closeout

Close only after the selected review passes and the changed Markdown has been
checked with `tools/bin/agent-canon docs check`. Do not require unused optional
sections or reviewers merely to satisfy a fixed checklist.

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Draft and revise directly from sources, existing text, headings, and brief structure notes. Graph analysis is optional under the [analysis boundary](prose-reasoning-graph.md#optional-analysis-boundary), not a writing prerequisite. Do not require a graph/DSL, fixed handoff, whole-document sentence order, zero graph findings, or a graph-to-prose round trip. Verify claims, citations, definitions, and reader flow in the document itself.

1. Read [agents/skills/paper-writing.md](paper-writing.md).
1. Select this as the writing skill when file/document responsibility is submission paper, thesis chapter, or paper-style manuscript with paper section contracts and citation/evidence review; do not select it by length.
1. Use `$structure-planning` before drafting when section order, first figure/table, claim/evidence layout, source-to-structure map, or invalid interpretations are nontrivial.
1. For paragraph-level claim flow, transition pairs, or logic-gap triage, have `$structure-planning` use `agent-canon semantic-index discourse-relations --profile academic-argument` and treat it as advisory discourse evidence before prose drafting.
1. Project paper responsibilities into positive prose contracts: state each section role, claim, citation/evidence relation, result claim, limitation, and reviewer handoff directly. Use negative boundary wording only inside an explicit Boundary, Limitation, or Non-Goal slot, and replace `ad hoc` labels with a named responsibility, evidence gap, verification route, or prompt-defect classification.
1. Fix the paper intent brief, claim contract, section contract, citation/evidence matrix, notation ledger, and paragraph claim map before drafting.
1. Route citation/evidence review, notation review, logic-gap review, and document-flow review as separate review passes before closeout.
