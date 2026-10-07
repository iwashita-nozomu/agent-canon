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

## Purpose

submission paper、thesis chapter、paper-style manuscript を、既存本文・根拠・構成メモから作成/改稿します。
paper-specific section contract と citation/evidence trace が必要な場合に使い、一般の scholarly note は `academic-writing` に委譲します。

## Required working notes

必要な section だけを選び、`paper intent brief`、`claim contract`、`section contract`、`citation and evidence matrix`、
`notation ledger`、`paragraph claim map` を run bundle または linked note に置きます。標準 section の役割は次です。

- `abstract`: problem、method、main result、implication
- `introduction`: gap、contribution、paper map
- `related work`: known results と unresolved position
- `method`: setting、assumptions、notation、procedure
- `results`: observations と measured outcomes
- `discussion`/`limitations`: interpretation、scope、claim boundary
- `conclusion`: contribution と next step

## Procedure

1. intent/claim/section contract と citation/evidence matrix を固定する。section order、first figure/table、invalid interpretation が未決定なら `structure-planning` を先に使う。
2. notation ledger と paragraph claim map を確認して reader order で draft する。graph/DSL や zero-finding を開始/完了条件にしない。
3. reverse outline で section role の重複を除く。
4. `document_flow_reviewer`、`citation_evidence_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、docs-completeness review を別々に通す。
5. higher-order revision の後に line edit を行い、`tools/bin/agent-canon docs check` で閉じる。

## Standard command

```bash
python3 tools/analysis/documents/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Boundary

文献探索自体は `literature-survey`、一般 academic prose は `academic-writing`、rebuttal/report の evidence traceability は `report-writing` を追加します。
未使用の section/reviewer を checklist のためだけに要求しません。
