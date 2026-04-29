# Experiment Notes
<!--
@dependency-start
responsibility Documents Experiment Notes for this repository.
upstream design ../README.md notes lifecycle index
@dependency-end
-->


このディレクトリには、`main` から辿れる形で残しておきたい実験メモを置きます。
1 回の run に対応する一次 report は `experiments/report/` に置き、このディレクトリは複数 run をまたぐ要約、比較、知見整理に使います。

研究の問い、比較設計、claim 更新は [agents/workflows/research-workflow.md](../../agents/workflows/research-workflow.md) を参照してください。
準備、実装、静的チェック、実行、結果レポートの標準手順は [agents/workflows/experiment-workflow.md](../../agents/workflows/experiment-workflow.md) を参照してください。
批判的レビューの観点は [documents/experiment-critical-review.md](../../documents/experiment-critical-review.md) を参照してください。
実験レポートの構成と体裁は [documents/experiment-report-style.md](../../documents/experiment-report-style.md) を参照してください。

## 基本ルール

- 実験メモは topic ごとに 1 ファイル以上を割り当てます。
- unrelated な実験を 1 枚に混ぜません。
- topic、日付、比較対象、関連 run が読める単位で分けます。
- raw JSON、JSONL、HTML、SVG、巨大ログはここへ複製しません。
- partial run は正式結果として扱いません。停止理由と再実行判断だけを残します。
- `main` に置いた過去の実験メモはむやみに書き換えません。補足が必要なら `Addendum:` または `Correction:` として追記します。

## 推奨構成

- `Abstract`
- `Question and Context`
- `Protocol`
- `Results`
- `Discussion`
- `Limitations`
- `Reproducibility Record`
- `Artifacts and Carry-Over`
- `Critical Review`
- `Conclusion`

テンプレートは [REPORT_TEMPLATE.md](./REPORT_TEMPLATE.md) を使えます。

## 最低限残すもの

- 問い
- 定式化
- 比較対象
- run 名または比較単位
- source artifact へのリンク
- 主要 metric
- 結果の要約
- 解釈と限界
- 次の action

## Result Links

- note 本文から、対応する `experiments/report/<run_name>.md` と `experiments/<topic>/result/<run_name>/` を辿れるようにします。
- raw JSONL や大量ログそのものは複製せず、結果ディレクトリを参照します。
- `main` に持ち帰る final JSON は [results/README.md](./results/README.md) の方針に従います。

## In-Worktree Drafting

- worktree で実験を進める場合も、最終的に `main` に置くのと同じ `notes/experiments/<topic>.md` を意識して書きます。
- 一挙手一投足は `notes/worktrees/` の action log に残し、この note には実験として意味のある条件変更と観測を要約します。
- 数式、比較対象、各改造の意図は worktree 側だけに閉じず、この note 側にも要約を残します。
