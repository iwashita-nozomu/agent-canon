# experiment-change-loop
<!--
@dependency-start
contract agent-runtime
responsibility Documents experiment-change-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

実験結果から、採用、追加検証、手法の見直しを判断します。

## Canonical Loop

問いと比較対象を確認し、結論に必要な変更と証拠を選びます。比較条件を揃え、
作用を切り分けたい場合は変更を分けます。結果の違いまたは欠落があれば、
仮定を読み直し、既存結果の解析、追加検証、再実行から適切なものを選びます。
実行と保存は [experiment-lifecycle](../skills/experiment-lifecycle.md) に従います。

## Decision States

- `report_rewrite_required` は、既存の証拠で説明を修正します。
- `extra_validation_required` は、結論に必要な証拠を補います。
- `rerun_required` は、実装や比較条件を直し、新しいrunで確認します。
- `approved` は、合意した結果を根拠が支えている状態です。

既存の報告や記録に比較の根拠と判断を残します。依頼で雛形が必要な場合は
[実験変更の雛形](../../templates/agents/experiment_change_loop.md) を使います。
