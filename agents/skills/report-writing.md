# report-writing
<!--
@dependency-start
contract skill
responsibility Writes evidence-backed reader-facing reports with semantic claim/evidence, inference, limitation, and action boundaries.
upstream design ../../documents/design/responsibility-rationale.md report semantics and finding-closure rationale
upstream design ../internal-routines/verification-result-structuring.md reader reconstruction, pre-write structuring, and finding coverage
upstream design structure-planning.md pre-write outline and structural-decision owner
upstream design result-artifact-writeout.md raw result artifact placement skill
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

1. [reader reconstruction](../internal-routines/verification-result-structuring.md#reader-reconstruction) で source、audience/decision、requested next action、
   findings、counterevidence、corrections、limitations を読み直す。settled check の再実行や別の環境調査は、答えを変える具体的 gap がある場合だけ行う。
   タスク完了報告には [Completion reports](../internal-routines/verification-result-structuring.md#completion-reports) を適用し、重要な試行と採否の根拠も本文へ含める。
2. 外部 reference が material claim を支える場合は、URL/DOI、access date、source identity、採否を持つ既存 source note/packet を使う。
   evaluation/experiment report では denominator、metric direction、valid/invalid comparison、次 action を明記する。
3. draft前に [構成確認](structure-planning.md#before-prose) を行う。readerの問いに沿った要点・sectionの順序と役割、claim/evidenceの対応を、既存構成で満たせるなら再利用し、不足すれば先に作成・補完する。複数のtopology候補がなくても飛ばさない。
   数値計算の結果は [Numerical and runtime results](#numerical-and-runtime-results) の順序で構成する。
4. その構成からreader orderでdraftし、`Results/Observations`、`Interpretation`、`Limitations` を混同しない。各material claimをevidenceまたは明示したinferenceに結ぶ。
5. 図が理解を大きく改善する場合だけ `code-visualization`、HTML/PPTが明示された場合だけ `html-output`/`slides` を追加する。描画やlayoutで構成の欠落が見つかったら、該当構成を直して本文へ戻る。
6. material factual error、unsupported claim、broken mapping、missing context、omitted counterevidence を close してから finalize する。
   advisory/style、out-of-scope、accepted risk は理由を短く残せる。変更した claim/section に関係する review だけ再実行する。

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

## Boundary

読者向け本文の claim/evidence/limitation をこの skill が持ち、raw file・checksum・readback は `result-artifact-writeout`、
構造上の未決定は `structure-planning`、図の rendering/coverage は `code-visualization` に委譲します。
