# report-writing
<!--
@dependency-start
contract skill
responsibility Writes evidence-backed reader-facing reports with semantic claim/evidence, inference, limitation, and action boundaries.
upstream design ../../documents/design/responsibility-rationale.md report semantics and finding-closure rationale
upstream design ../internal-routines/verification-result-structuring.md reader reconstruction, pre-write structuring, and finding coverage
upstream design structure-planning.md pre-write outline and structural-decision owner
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design result-visualize.md reusable result visualization contract
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

既存 evidence からタスク完了報告、status、audit、evaluation、experiment、review、decision、recommendation、presentation の
reader-facing prose を作ります。material claim は source に辿れ、observation と inference、limitation、next action を分けます。
raw artifact は `result-artifact-writeout` が所有し、report は第二の policy/source-of-truth になりません。

## Procedure

Use [reader reconstruction](../internal-routines/verification-result-structuring.md#reader-reconstruction)
to identify the source evidence, audience and decision, requested next action,
findings, counterevidence, corrections, and limitations. Reuse settled checks and
source notes; repeat a check or investigate the environment only to resolve a
specific gap that could change the answer. For branch-based experiment reports,
establish each branch's origin or baseline, purpose, and delta before synthesizing
the final paper-level report. Preserve material external references with their
URL/DOI, access date, source identity, and adoption status.

Follow this writing sequence:

1. **Outline.** Settle the reader-facing order of results and supporting evidence
   with [structure-planning](structure-planning.md#before-prose). Reuse a
   sufficient existing structure, especially for a short completion report; do
   not create a separate outline artifact when the task and existing material
   already establish the order. Include denominator, metric direction, and valid
   or invalid comparison where relevant to evaluation or experiment results.
2. **Decide figures.** Before producing an asset, decide whether a figure is
   needed and specify its message, supporting evidence, and placement in the
   outline. A short report may need no figure.
3. **Create or reuse figures as needed.** Reuse existing result assets where they
   answer the planned message. For a necessary plot or diagram, use the existing
   [result-visualize](result-visualize.md) and
   [code-visualization](code-visualization.md) owners and their selected
   providers. Preserve the source data and provenance; do not invent data to fill
   a visual. Update the outline if asset review exposes a material gap.
4. **Draft the body with the selected writing owner.** Explicitly read and use
   [paper-writing](paper-writing.md) for a scholarly manuscript or
   [long-form-writing](long-form-writing.md) for other reader-facing reports.
   Pass the settled outline, figure plan, and created or reused assets so the
   writing stage can proceed without restarting those decisions. Keep
   `Results/Observations`, `Interpretation`, and `Limitations` distinct, and tie
   each material claim to evidence or identify it as an inference. In numerical
   reports, follow [Numerical and runtime results](#numerical-and-runtime-results).

Before finalizing, close material factual errors, unsupported claims, broken
evidence mappings, missing context, and omitted counterevidence. Advisory/style,
out-of-scope, and accepted-risk findings may remain with a brief reason. For task
completion reports, apply [Completion reports](../internal-routines/verification-result-structuring.md#completion-reports)
and include important attempts and grounds for acceptance or rejection. Re-run
only reviews tied to changed claims or sections.

## Numerical and runtime results

数値計算のreportは、要約・結果本文とも数値結果を対象全体について先にまとめ、その後に実行時・アーキテクチャの結果をまとめます。分類は次のとおりです。

1. **数値結果**: 解・目的値・残差や誤差、制約充足、収束・成功/失敗、反復回数など、要求された数値的性質と到達条件を示す。
2. **実行時・アーキテクチャの結果**: 実行時間、compile/warmupや反復あたりの時間、メモリ、device/backend/並列化に関する観測を示す。

両者は段落・小節・表を分け、同じrun/caseと数値の到達条件を対応づけて比較します。
数値結果が未取得・失敗なら、その状態を数値結果の位置で示してから実行時の結果を書きます。
環境や設定の説明は比較条件として扱い、観測結果と区別します。

## Output

Markdown が既定です。小さな内部 status は数段落や小表で足り、固定 heading 数や `finding_count == 0` は完了条件ではありません。
独立 reviewer は claim impact、外部公開、曖昧さ、evidence complexity が必要な場合だけ選びます。
For requested native Google Docs delivery, use the
[Google Docs handoff](README.md#installed-external-skill-handoffs); this Skill
retains report claims, evidence, and interpretation.

## Boundary

読者向け本文の claim/evidence/limitation をこの skill が持ち、raw file・checksum・readback は `result-artifact-writeout`、
構造上の未決定は `structure-planning`、図の rendering/coverage は `code-visualization` に委譲します。
