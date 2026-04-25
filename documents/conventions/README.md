<!--
@dependency-start
upstream design ../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# コーディング規約索引

repo 全体で先に見るのは、言語非依存の規約です。
言語や実装系に固有の補足は、その後に必要なものだけ読みます。

## 先に読む

- [coding-conventions-project.md](../coding-conventions-project.md)
  - repo-wide の共通運用、Markdown 書式修正、Bash 配置ルールの正本
- [coding-conventions-testing.md](../coding-conventions-testing.md)
- [coding-conventions-reviews.md](../coding-conventions-reviews.md)
- [coding-conventions-experiments.md](../coding-conventions-experiments.md)

## 補足規約

- [coding-conventions-house-style.md](../coding-conventions-house-style.md)
- [coding-conventions-python.md](../coding-conventions-python.md)
- [coding-conventions-cpp.md](../coding-conventions-cpp.md)
- [coding-conventions-logging.md](../coding-conventions-logging.md)

## 参考補助

- [20_benchmark_policy.md](python/20_benchmark_policy.md)
- [30_experiment_directory_structure.md](python/30_experiment_directory_structure.md)

## 運用

- 新しい規約を追加する場合はこの索引へリンクを追加します。
- repo 全体の入口では、言語固有規約を既定にしません。
- framework 固有の補足は、実際にその framework を使う repo だけで参照します。
