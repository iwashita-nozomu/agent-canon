# report-writing
<!--
@dependency-start
contract skill
responsibility Writes evidence-backed reader-facing reports with semantic claim/evidence, inference, limitation, and action boundaries.
upstream design ../../documents/design/responsibility-rationale.md report semantics and finding-closure rationale
upstream design ../internal-routines/verification-result-structuring.md reader reconstruction, pre-write structuring, and finding coverage
upstream design structure-planning.md optional structural-decision owner
upstream design result-artifact-writeout.md raw result artifact placement skill
upstream design code-visualization.md sole public visualization owner and typed projection contract
downstream implementation ../../.codex/personal/skills/report-writing/SKILL.md exposes this workflow as a runtime skill
downstream implementation ../../eval/producers/evaluate_report_quality.py validates report prompt surfaces
downstream implementation ../../tools/validation/semantic/dependencies/check_dependency_headers.py validates this adapter dependency header
@dependency-end
-->

## Purpose

既存 evidence から status、audit、evaluation、experiment、review、decision、recommendation、presentation の
reader-facing prose を作ります。material claim は source に辿れ、observation と inference、limitation、next action を分けます。
raw artifact は `result-artifact-writeout` が所有し、report は第二の policy/source-of-truth になりません。

## Procedure

1. `reader-reproducible writing`（`../internal-routines/verification-result-structuring.md`）で source、audience/decision、requested next action、
   findings、counterevidence、corrections、limitations を読み直す。settled check の再実行や別の環境調査は、答えを変える具体的 gap がある場合だけ行う。
2. 外部 reference が material claim を支える場合は、URL/DOI、access date、source identity、採否を持つ既存 source note/packet を使う。
   evaluation/experiment report では denominator、metric direction、valid/invalid comparison、次 action を明記する。
3. reader order で draft し、`Results/Observations`、`Interpretation`、`Limitations` を混同しない。各 material claim を evidence または明示した inference に結ぶ。
4. report topology が本当に未決定なら `structure-planning`、図が理解を大きく改善する場合だけ `code-visualization`、HTML/PPT が明示された場合だけ `html-output`/`slides` を追加する。
5. material factual error、unsupported claim、broken mapping、missing context、omitted counterevidence を close してから finalize する。
   advisory/style、out-of-scope、accepted risk は理由を短く残せる。変更した claim/section に関係する review だけ再実行する。

## Output

Markdown が既定です。小さな内部 status は数段落や小表で足り、固定 heading 数や `finding_count == 0` は完了条件ではありません。
独立 reviewer は claim impact、外部公開、曖昧さ、evidence complexity が必要な場合だけ選びます。

## Boundary

読者向け本文の claim/evidence/limitation をこの skill が持ち、raw file・checksum・readback は `result-artifact-writeout`、
構造上の未決定は `structure-planning`、図の rendering/coverage は `code-visualization` に委譲します。
