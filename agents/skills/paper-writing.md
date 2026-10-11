# paper-writing
<!--
@dependency-start
contract skill
responsibility Documents paper-writing for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable paper structure contract
upstream design prose-reasoning-graph.md prose graph diagnostics and rewrite handoff overlay
upstream design agent-canon-bootstrap.md registered-project shared-container command route
upstream design ../../documents/contracts/quarto-html-output.toml Quarto/Pandoc provider version
@dependency-end
-->

## Purpose

submission paper、thesis chapter、paper-style manuscript を、既存本文・根拠・構成メモから作成/改稿します。
paper-specific section contract と citation/evidence trace が必要な場合に使い、一般の scholarly note は `academic-writing` に委譲します。

## Required working notes

必要な section だけを選び、paper の判断に役立つ working note だけを既存の
run bundle または linked note に残します。material claim の根拠を追う
citation/evidence map と、数式を読むために必要な notation は明確にします。
paragraph map や細かな section contract は、実際の重複、欠落、順序の問題を
解く場合に限って作ります。標準 section の役割は次です。

- `abstract`: problem、method、main result、implication
- `introduction`: gap、contribution、paper map
- `related work`: known results と unresolved position
- `method`: setting、assumptions、notation、procedure
- `results`: observations と measured outcomes
- `discussion`/`limitations`: interpretation、scope、claim boundary
- `conclusion`: contribution と next step

## Procedure

既存の draft、source、要求された section と claim から必要な執筆・根拠メモを
選びます。section order、first figure/table、または invalid interpretation に
未決定の構造選択がある場合だけ `structure-planning` を先に使います。

Reader がたどる論理順で書き、section の役割が重なる場合は reverse outline
で整理します。レビューは実際のリスクに合わせます。構造上の断絶には
`document_flow_reviewer`、外部根拠には `citation_evidence_reviewer`、記号には
`notation_definition_reviewer`、推論の飛躍には `logic_gap_reviewer` を選びます。
docs-completeness review は要求された複数 section や関連文書の網羅性が問題に
なる場合に追加します。未使用の reviewer を checklist のためだけに呼びません。

大きな構造修正を済ませてから line edit を行い、`tools/bin/agent-canon docs
check` は選択された文書 check として使います。

## Standard command

```bash
python3 tools/analysis/documents/doc_start.py \
  --task "paper writing task" \
  --kind paper \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Citation rendering

When a paper needs formatted citations, keep the author-selected bibliography and
CSL style as local files and use Pandoc citation keys in the manuscript, such as
`[@source-key]`. Run Quarto's embedded Pandoc through the registered native
`quarto` tool route; manuscript, bibliography, and CSL paths are relative to the
registered project root. Keep output under the shared runtime's external tool
output directory rather than writing into the read-only project target. The route
uses the author-selected output format and preserves Pandoc's native exit status
and diagnostics:

```bash
# Choose a new output filename for each render.
OUTPUT=/var/lib/agent-canon/runtime/tool-output/paper.html
"$BOOTSTRAP" "${COMMON[@]}" tool run --root "$PROJECT_ROOT" quarto -- \
  pandoc "$MANUSCRIPT" \
  --citeproc \
  --bibliography "$BIBLIOGRAPHY" \
  --csl "$CSL_STYLE" \
  --to "$FORMAT" \
  --standalone \
  --output "$OUTPUT" \
  --fail-if-warnings
```

`BOOTSTRAP` and `COMMON` use the existing [AgentCanon bootstrap route](agent-canon-bootstrap.md),
and `PROJECT_ROOT` is the registered paper project. Keep bibliography and CSL
paths local; source discovery or DOI metadata retrieval remains with
`literature-survey`. A non-zero result or citeproc warning is a failed render,
including an unresolved citation key; preserve the native output instead of
normalizing it through a custom parser. Citeproc handles bibliographic lookup
and formatting only: claim support, limitations, and citation/evidence review
remain with the existing paper-writing notes and reviewer.

## Boundary

文献探索自体は `literature-survey`、一般 academic prose は `academic-writing`、rebuttal/report の evidence traceability は `report-writing` を追加します。
未使用の section/reviewer を checklist のためだけに要求しません。
