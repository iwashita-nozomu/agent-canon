# report-writing
<!--
@dependency-start
contract skill
responsibility Writes evidence-backed reader-facing reports with semantic claim/evidence, inference, limitation, and action boundaries.
upstream design ../../documents/design/responsibility-rationale.md report semantics and finding-closure rationale
upstream design ../internal-routines/verification-result-structuring.md verification findings and completion reporting
upstream design structure-planning.md pre-write outline and structural-decision owner
upstream design academic-writing.md conditional mathematical preliminary preparation
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design result-visualize.md reusable result visualization contract
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/dependency_headers.rs validates this adapter dependency header
@dependency-end
-->

## Purpose

既存の検証結果や観測から、読者が判断に使える報告を作ります。

## Procedure

資料の仮定と判定基準を読み、結論のそばに決め手の事実と採用理由を書きます。
結論が当てはまる範囲を示し、コマンド、設定、手順は既存の実行記録を参照します。
検証結果と完了報告は [報告の指針](../internal-routines/verification-result-structuring.md#structure-before-writeout) に従います。

1. 章立てを決めます。使える構成は再利用し、不足する構成は
   [structure-planning](structure-planning.md#before-prose) で決めます。
2. 図が必要かを判断し、伝える結果と配置を決めます。
3. 必要な図を再利用するか、[result-visualize](result-visualize.md) や
   [code-visualization](code-visualization.md) で作ります。
4. [long-form-writing](long-form-writing.md)、[paper-writing](paper-writing.md)、
   [academic-writing](academic-writing.md) から文書に合う執筆スキルで本文を書きます。

実験branchを報告する場合は起点・目的・差分を示します。数理の仮定の選択が残る場合は
[数理予備検討](academic-writing.md#mathematical-preliminary-preparation) を参照します。

## Numerical and runtime results

数値結果を対象全体について先にまとめ、その後に実行時・アーキテクチャの結果を示します。
同じrunやcaseを対応づけます。数値結果が未取得または失敗の場合も、数値結果の節で状態を示します。

## Output

Markdownを既定とします。Google Docsでの納品は
[既存の連携手順](README.md#installed-external-skill-handoffs) を使います。

## Boundary

報告は結果と解釈を扱い、raw artifactの保存は [result-artifact-writeout](result-artifact-writeout.md) が担います。
