<!--
@dependency-start
contract reference
responsibility 実験計画、GPU admission、ExperimentRunner、結果保持の文書入口。
upstream design ../README.md documents 索引と正本境界。
downstream implementation ../../tools/experiments/ 実験 tool 群。
@dependency-end
-->

# 実験運用

この directory は実験の設計、レビュー、registry、GPU resource admission、
ExperimentRunner lifecycle、結果と可視化の保持を扱います。実験の実行結果そのものは
`experiments/` または `reports/` に保存し、ここへ混ぜません。

## 構成

- `experiment-registry.md`: 実験登録の契約。
- `experiment-runner-ff97-lifecycle.md`、`../design/experiment_runner.md`:
  ExperimentRunner の lifecycle と設計。
- `experiment-critical-review.md`、`experiment-report-style.md`: 実験レビューと報告。
- `gpu-admission-r5-*.md`、`gpu-admission-r5-ordered-integration-interface.json`:
  GPU admission の source packet と機械可読境界。
- `result-log-retention-and-visualization.md`: 結果・ログ・可視化の保持規約。
