# 実験運用規約
<!--
@dependency-start
upstream design README.md durable document index
@dependency-end
-->


この文書は、`experiments/` 配下の実験コード、benchmark、実験結果、実行環境の運用を扱います。
研究の問い、数式、比較対象、逐次改造の記録方法は `agents/workflows/research-workflow.md` を正本とします。
準備、実装、静的チェック、実行、結果レポートの標準手順は `agents/workflows/experiment-workflow.md` を参照してください。

## 1. 対象

- 実験コード
- benchmark コード
- 実行ごとの生成物
- 実験 report

## 2. ディレクトリ構成

- 実験は `experiments/<topic>/` に置きます。
- topic ごとに `README.md`、`cases.*`、`experiment.*`、`result/` を基準にします。
- topic の正本 entrypoint と smoke / formal command は `experiments/registry.toml` に集約します。
- 1 回の run の report は `experiments/report/<run_name>.md` に置きます。
- 複数 run をまたぐ要約や知見は `notes/experiments/` や `notes/themes/` に置きます。
- server 上の formal run では `result/<run_name>/run_manifest.json`、`eval_manifest.json`、`run.log` を残します。

## 3. 実行原則

- 1 回の run は 1 つの `run_name` と 1 つの出力先に閉じた fresh 実行として扱います。
- partial run を正式結果として継ぎ足しません。
- 比較条件は run 開始前に固定します。
- 巨大な生成物や raw ログを `main` の入口文書へ混ぜません。
- main server host で実行する run は、topic README に exact command と wrapper の使い方を明記します。

## 4. report と notes

- 1 回の run の一次 report は `experiments/report/` に置きます。
- 複数 run の比較や再利用知識は `notes/` に残します。
- `Results` と `Discussion` を混ぜません。
- 解釈と limitation を同じ文書内で確認できるようにします。

## 5. branch 方針

- 実験も既定では `main` 基準で進めます。
- branch や worktree は隔離が必要な場合だけ使います。
- branch 固有の台帳を長期保存先にしません。
