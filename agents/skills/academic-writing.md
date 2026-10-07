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

1. `claim contract`（central contribution、gap、reader、non-goal）を固定し、既存本文・根拠から `evidence map`、`notation ledger`、section contract を作る。
2. section/figure/table の順序や claim/evidence layout が未決定なら `structure-planning` を使う。discourse diagnostics は直接 review で解けない順序問題だけに使う。
3. reader order で draft し、結果・解釈・limitation を分ける。graph/DSL、固定 handoff、全 sentence の順序、finding 件数ゼロを通常の開始/完了 gate にしない。
4. draft 後に reverse outline を取り、`document_flow_reviewer`、`notation_definition_reviewer`、`logic_gap_reviewer`、docs-completeness review を別々に通す。
5. PDF-ready、dense math、figure が必要なら TeX plan を立て、明示環境の `latexmk`、pdfLaTeX/XeLaTeX、必要時 `dvisvgm`/`pdfcrop` で検証する。
6. `tools/bin/agent-canon docs check` で閉じる。一般 README/workflow/guide/migration/report は TeX route に送らない。

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
