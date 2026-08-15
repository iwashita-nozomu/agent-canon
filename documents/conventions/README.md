<!--
@dependency-start
contract policy
responsibility Documents コーディング規約索引 for this repository.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md shared documents ownership policy
upstream design ../rule/README.md document rule canon
downstream design ./software-engineering-principles.md language- and paradigm-neutral engineering principles
downstream design ./object-oriented-design.md OOP and SOLID specialization
@dependency-end
-->

# コーディング規約索引

repo 全体で先に見るのは、言語・framework・programming paradigm に依存しない規約です。
言語や実装系に固有の補足は、その後に必要なものだけ読みます。

## 先に読む

- [ソフトウェア工学原則](software-engineering-principles.md)
  - contract、責務、依存、KISS / YAGNI / DRY、変更単位、検証、failure、traceability の正本
  - 原則が競合するときの判断順序と、原則を checklist 化しない evidence model
- [文書規約](../rule/README.md)
  - filename、配置、構成判断の共通規約
- [coding-conventions-project.md](coding-conventions-project.md)
  - repo-wide の共通運用、Markdown 書式修正、Bash 配置ルールの正本
- [coding-conventions-testing.md](coding-conventions-testing.md)
- [coding-conventions-reviews.md](coding-conventions-reviews.md)
- [coding-conventions-experiments.md](coding-conventions-experiments.md)

## 補足規約

- [オブジェクト指向設計方針](object-oriented-design.md)
  - class、state、inheritance、composition、`Protocol`、SOLID が実際に変更される場合の専門規約
- [DOCSTRING_GUIDE.md](DOCSTRING_GUIDE.md)
  - **最初に読む正本**: semantic contract、canonical template skeleton、sparse trace、
    projection route、review decision matrix
- [coding-conventions-house-style.md](coding-conventions-house-style.md)
- [coding-conventions-python.md](coding-conventions-python.md)
- [coding-conventions-cpp.md](coding-conventions-cpp.md)
- [coding-conventions-logging.md](coding-conventions-logging.md)

## 参考補助

- [20_benchmark_policy.md](python/20_benchmark_policy.md)
- [30_experiment_directory_structure.md](python/30_experiment_directory_structure.md)

## 運用

- 新しい規約を追加する場合はこの索引へリンクを追加します。
- repo 全体の入口では、言語固有規約や OOP / SOLID を既定にしません。
- framework 固有の補足は、実際にその framework を使う repo だけで参照します。
- 一般原則を skill、workflow、language convention へ全文複製せず、正本の clause を参照します。
