# report-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents report-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

`experiments/report/<topic>/<variant>/<run_name>.md` の reader-facing quality と evidence traceability を確認します。
report path は `agentcanon.experiment-run-identity/v2` の topic/variant/run_name と一致させ、
別 variant の同名 run や旧 topic-only path を参照しません。

## Use When

- 実験 report を新規作成した
- 結果の要約や結論を書いた
- report を close する前

## Core References

- `documents/experiments/experiment-report-style.md`
- `documents/experiments/experiment-critical-review.md`
- `templates/agents/experiment_report.md`

## Expected Outcome

- report が問い、結果、解釈、限界、artifact 導線を reader-facing に持っている
- major claim が figure、table、JSON、command へ辿れる
- outcome が `report_rewrite_required`、`extra_validation_required`、`rerun_required`、`approved` のどれかに落ちる

## Mandatory Checklist

- `Question`、`Protocol`、`Results`、`Discussion`、`Limitations`、`Critical Review` が埋まっている
- major claim ごとに supporting artifact へ辿れる
- branch、commit、command、result path、report path が再現可能な粒度で書かれている
- result の羅列ではなく、問いに対する判断文書になっている
- missing evidence や overclaim risk が report 内に残っている

## Default Sequence

1. 問い、比較対象、metrics が report 冒頭で分かるか確認します。
1. protocol と reproducibility record から rerun 可能性を確認します。
1. major claim が具体的な figure / table / JSON へ辿れるかを見ます。
1. limitations と critical review が結論を十分に抑制しているか見ます。
1. `rewrite / extra validation / rerun / approved` のいずれかで outcome を返します。

## Decision States

- `report_rewrite_required`
  - evidence は足りているが reader-facing 構成や表現が弱い
- `extra_validation_required`
  - report を閉じる前に追加の解析や比較が必要
- `rerun_required`
  - protocol や run 自体に問題がある
- `approved`
  - reader-facing report として閉じてよい

## Boundary

- 実験の比較妥当性そのものは `critical-review` を併用します。
- run 設計や rerun loop の進行は `experiment-lifecycle` または `experiment-change-loop` を使います。
