# academic-writing
<!--
@dependency-start
contract skill
responsibility Documents academic-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable document structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design ../../CONTAINER_OPERATIONS.md TeX devcontainer tooling boundary
downstream implementation ../../.codex/personal/skills/academic-writing/SKILL.md Codex skill shim
@dependency-end
-->

## Purpose

学術 prose、scholarly note、thesis chapter、method note、記号密度の高い claim-heavy 文書を、既存本文・根拠・構成メモから作成/改稿します。
paper-style manuscript は `paper-writing` を優先します。選択基準は長さではなく文書責務です。

## Use When

- notation、略語、仮定、technical term、evidence relation が reader の理解を左右する
- 一般 guide/report より、定義順・logic gap・claim support の review が必要な scholarly prose を扱う

## Procedure

Start from the requested claim, audience, existing draft, and sources. Make the
claim, evidence links, notation/assumptions, or section contract explicit to the
extent the document needs them; reuse an existing note when it already captures
that information.

Resolve section, figure, or table ordering with `structure-planning` only when a
real choice remains. Draft in a reader-friendly order and keep observations,
interpretation, and limitations distinct where the document makes evidence-based
claims. A graph or fixed handoff is not a prerequisite for ordinary drafting.

Choose review by the risk in the draft: reader flow for structural gaps,
notation review for undefined or inconsistent symbols, and logic review for
unsupported inferences. Add docs-completeness review when the requested scope
spans required sections or linked documents. A PDF-ready or dense-math artifact
may use the TeX route in an explicit environment; otherwise use the document
owner's applicable check.

Use `tools/bin/agent-canon docs check` when that check is selected for the
document. General README/workflow/guide/migration/report work does not need a
TeX route.

## Standard command

```bash
python3 tools/analysis/documents/doc_start.py \
  --task "academic writing task" \
  --kind academic \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Review outcomes

- `rewrite_required`: claim contract、logic chain、definition order の欠落
- `notation_fix_required`: symbol、term、unit、index の未定義/不整合
- `logic_fix_required`: support のない inference や飛躍
- `approved`: reader flow、notation、logic、information completeness が揃う

## Boundary

文献探索は `literature-survey`、paper-specific section/citation review は `paper-writing`、一般説明 prose は `long-form-writing` が所有します。
