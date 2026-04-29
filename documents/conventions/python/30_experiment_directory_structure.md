# 実験ディレクトリ構成
<!--
@dependency-start
responsibility Documents 実験ディレクトリ構成 for this repository.
upstream design ../README.md convention index
@dependency-end
-->


この章は、このリポジトリで experiment をどこへ置くかを定めます。
研究の問い、数式、比較設計、段階的改造の手順は `agents/workflows/research-workflow.md` を正本とします。

## 要約

- 再利用できる汎用 runtime は `python/experiment_runner/` に置きます。
- topic 固有のケース生成と実験本体は `experiments/` 配下に置きます。
- 長時間実行の生成物は topic ごとの `result/<run_name>/` に集約し、ライブラリ本体へ混ぜません。
- experiment run は 1 回の fresh 実行で完走させ、途中停止 run を継ぎ足して完了扱いにしません。

## 規約

### 1. 役割分担

- `python/experiment_runner/` は、topic 非依存の実験実行基盤を置く場所とします。
- ここには、subprocess 実行、resource scheduling、GPU 環境変数の受け渡し、context の整形のような汎用機能だけを置きます。
- 特定 topic に閉じたケース生成と CLI は `experiments/` 側へ置きます。

### 2. topic ごとの配置

- 単独で完結する experiment は `experiments/<topic>/` に置きます。
- `experiments/` 配下の topic ディレクトリには、少なくとも README、`cases.py`、`experimentcode.py`、`result/` を置ける形にします。
- topic ディレクトリ名は `snake_case` を使います。

### 3. 推奨レイアウト

```text
experiments/
├── registry.toml
└── <topic>/
    ├── README.md
    ├── cases.py
    ├── experimentcode.py
    └── result/
        └── <run_name>/
```

```text
experiments/report/
└── <run_name>.md
```

### 4. どこへ何を置くか

- topic をまたいで再利用する protocol や scheduler は `python/experiment_runner/` に置きます。
- その topic のためだけに存在する `cases.py` と `experimentcode.py` は `experiments/<topic>/` に置きます。
- `cases.py` には case 列の展開と `resource_estimate(case)` を置きます。
- `experimentcode.py` には `task(case, context)`、`context_builder(case)`、必要なら `initializer(context)` と `SkipController` を置きます。
- 可視化や report 用の生成物は `result/<run_name>/` にまとめます。
- topic 固有ディレクトリの README や note から、定式化と比較対象を必ず辿れるようにします。
- 長時間実行で生成される JSON、JSONL、HTML、SVG、ログは `result/<run_name>/` に集約します。
- 人が読む experiment report は `experiments/report/<run_name>.md` に置きます。
- 複数 run をまたぐ要約は `notes/experiments/<topic>.md` に置きます。
- top-level `reports/` は topic ごとの experiment report の正本にしません。
- JSONL は run 中の progress 記録として扱い、resume 用の canonical input にはしません。
- 生成物は `.gitignore` と `result/<run_name>/` 運用で管理し、安定ライブラリやテストディレクトリへ混ぜません。

### 4.5 naming

- run_name は `<topic>_<variant>_<YYYYMMDDTHHMMSSZ>` に固定します。
- `result/` の主要生成物は次でそろえます。
  - `result/<run_name>/run_manifest.json`
  - `result/<run_name>/eval_manifest.json`
  - `result/<run_name>/summary.json`
  - `result/<run_name>/cases.jsonl`
  - `result/<run_name>/run.log`
- topic README には、run_name 形式、report パス、result ディレクトリ構成を明記します。
- topic の canonical entrypoint と smoke / formal command は `experiments/registry.toml` にも書きます。
- server 実行では、`tools/experiments/run_managed_experiment.py` のような wrapper で host / command / commit metadata を残すことを推奨します。

### 5. テスト

- 汎用 runtime のテストは `tests/experiment_runner/` に置きます。
- topic 固有 helper のうち再利用価値が高いものは、対応する unit test を `tests/` 側へ追加します。
- 一回限りの実行スクリプトは、README の smoke command と集計結果の形式保証を優先し、無理にライブラリ級の API にしません。
- 実行スクリプトは、指定した条件を 1 回の invocation で完走する責務を持たせます。
- 途中停止した場合は、同じ結果ファイルへ継ぎ足さず、新しい run_name と出力先で 0 から再実行します。

### 6. `main` への統合

- `main` へ統合するときは、コードだけでなく test と document を同時にそろえます。
- 隔離環境で削除した冗長ファイルは、`main` 側でも不要なら削除します。
- 実行結果そのものは raw のまま全部を `main` へ戻さず、必要な最終 JSON と note を残します。
- `main` へ持ち帰るのは完走 run の `result/<run_name>/` と report だけにします。partial run は診断用に留めます。

## 補足

- `python/experiment/` という別の top-level package は、現時点では新設しません。
- 現在の repo では、汎用層はすでに `python/experiment_runner/` にあるため、そこへ責務を集約します。

## 更新手順

- benchmark の置き場と境界を変えた場合は [20_benchmark_policy.md](./20_benchmark_policy.md) を同時に更新します。
- worktree 運用や result / report の配置を変えた場合は [documents/coding-conventions-experiments.md](../../coding-conventions-experiments.md) も更新します。
