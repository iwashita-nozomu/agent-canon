# Benchmark Levels Analysis
<!--
@dependency-start
@dependency-end
-->


benchmark は、重さの異なる層を明示しておくと運用しやすくなります。

## Three Levels

- `Light`
  - 秒から数十秒で終わる日常確認用
- `Heavy`
  - 数分かけて傾向を見る比較用
- `Extreme`
  - 長時間で限界や failure frontier を見る設計判断用

## Interpretation

- 局所的な実装変更の確認は `Light` か `Heavy` で十分なことが多いです。
- 条件 sweep や failure analysis を見るなら benchmark ではなく experiment に切り替えるべきです。

## Related

- [Benchmark vs Experiment](/mnt/l/workspace/project_template/notes/knowledge/benchmark_vs_experiment.md)
