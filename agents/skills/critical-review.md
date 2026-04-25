# critical-review
<!--
@dependency-start
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

比較条件、根拠、サンプル不足、過大主張を批判的に確認します。

## Use When

- experimental claim
- benchmark conclusion
- fairness / overclaim の確認

## Core Reference

- `documents/experiment-critical-review.md`

## Expected Outcome

- 観測事実と解釈が分離されている
- fairness、missing evidence、overclaim risk が明示されている
- 次が report 書き直し、追加検証、rerun のどれか判断できる

## Mandatory Checklist

- 比較対象が同じ条件、同じ case set、同じ timeout / hardware / dtype policy で評価されている
- aggregate 指標だけでなく failure case と例外パターンを見ている
- baseline や prior method が抜けていない
- 観測した結果と speculative interpretation を分けている
- sample size、variance、unstable region、negative result を隠していない

## Decision Hints

- 根拠は足りているが表現が強すぎるだけなら `report_rewrite_required`
- 比較や補助解析が足りないなら `extra_validation_required`
- 実験条件そのものが崩れているなら `rerun_required`
- 主張と根拠が釣り合っていれば `approved`

## Boundary

- report の reader-facing 構成は `report-review` を使います。
- 実装差分そのものの回帰 review は `change-review` または `code-review` を使います。
