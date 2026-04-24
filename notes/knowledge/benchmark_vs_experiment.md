# Benchmark vs Experiment

性能計測を始める前に benchmark と experiment のどちらを選ぶかを素早く判断するためのメモです。

## Benchmark を選ぶとき

- 同じマシンで前後比較したい。
- 数秒から数分で終わる結果が欲しい。
- 条件数が少なく、1 回の fresh 実行で完走できる。
- 実装変更の影響を小さく切り出して見たい。

## Experiment を選ぶとき

- dimension、level、dtype など複数条件をまとめて探索したい。
- JSONL を逐次保存し、run 内 progress と失敗分類を残したい。
- timeout、OOM、worker failure を記録したい。
- 可視化や最終集計を後段で再生成したい。

Experiment でも canonical な運用は resume ではなく fresh run です。途中で止まったら、停止理由を残して 0 から再実行します。

## この repo での置き場

- benchmark は topic に近い `experiments/` 配下に置く。
- topic 固有の experiment helper は `experiments/<topic>/` または `experiments/<area>/<topic>/` に置く。
- 汎用の実行基盤は `python/experiment_runner/` に置く。

## 判断の目安

- 「実装変更の前後比較」なら benchmark。
- 「条件 sweep と failure analysis」なら experiment。
- 迷ったら、まず benchmark で局所差分を見ます。追加の条件探索が必要になった時点で experiment に拡張します。

## 参照

- [documents/conventions/python/20_benchmark_policy.md](../../documents/conventions/python/20_benchmark_policy.md)
- [documents/conventions/python/30_experiment_directory_structure.md](../../documents/conventions/python/30_experiment_directory_structure.md)
- [documents/coding-conventions-experiments.md](../../documents/coding-conventions-experiments.md)
