# report-review
<!--
@dependency-start
contract agent-runtime
responsibility Documents report-review for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

`experiments/<topic>/report/<run-id>.md` の reader-facing quality と evidence traceability を確認します。
report path は `agentcanon.experiment-run-identity/v2` の topic/run_name と一致させ、variant は
manifest metadataで確認します。別 variant の同名 run や旧 topic-only path を参照しません。

## Use When

- 実験 report を新規作成した
- 結果の要約や結論を書いた
- report を close する前

## Core References

- [documents/experiments/experiment-report-style.md](../../documents/experiments/experiment-report-style.md)
- [documents/experiments/experiment-critical-review.md](../../documents/experiments/experiment-critical-review.md)
- [templates/agents/experiment_report.md](../../templates/agents/experiment_report.md)

## Review criteria

問いに対する結論と判断理由を、対応する実験結果に照らします。比較に必要な対象、指標、
仮定、検証の範囲を確認し、手順や実行条件は既存の記録を参照します。
同名のrunやvariantを取り違えると判断が変わる場合は、実行記録から照合します。

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
- run 設計や rerun loop の進行は [`experiment-lifecycle`](../skills/experiment-lifecycle.md) または [単一変更の反復](experiment-change-loop.md) を使います。
