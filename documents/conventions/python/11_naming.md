<!--
@dependency-start
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 命名規約（Python）

対象: `python/` 配下の checked-in package と module。

## 要約

- **ファイル名**は `snake_case.py`。
- **関数名**は `snake_case`。
- **公開API** と **内部実装** を名前で区別します。

## ファイル名

- `snake_case.py` を使ってください。
- 略語は一般的なもののみ許可します。
- 役割が分かる語を置き、意味のない接尾辞（`_util` の乱用等）は避けます。

### 禁止/注意

- 大文字を含むファイル名（例: `MyAlgo.py`）は避けます。
- OS差分が出やすい表記（空白・ハイフン混在）は避けます。

## 関数名

- `snake_case` を使ってください。
- **動詞で始める**ことを推奨します（例: `load_*`, `build_*`, `run_*`, `update_*`, `check_*`）。

## クラス名・Protocol名

- クラス名と `Protocol` 名は `PascalCase` を使ってください。
- 役割語は末尾に置き、型空間や責務は先頭で明示します。
  - 例: `TaskContext`, `RemoteWorker`, `OptimizationProblem`
- 意味の薄い短縮形は避けます。
  - 例: `Mgr`, `TmpThing`, `Doer` のような短縮名は使いません。

## 契約 family の命名

- 共有契約の基底名は 1 つに固定し、特殊化ではその基底名を保存します。
  - 例: `TaskContext` -> `RemoteTaskContext`
  - 例: `OptimizationProblem` -> `VectorOptimizationProblem`
- 制約付きの family は prefix か suffix のどちらかに統一し、同一 repo で揺らしません。
  - 例: `ConstrainedOptimizationProblem`
  - 例: `RemoteExperimentTask`
- 旧命名と新命名を互換 alias で併存させません。命名変更は参照側も同じ change で更新します。

### 公開API と内部関数

- **公開API**: モジュールの `__all__` に載せる関数/クラス。
  - 名前は先頭 `_` なし。
  - 例: `load_registry`, `build_case_table`, `run_experiment`
- **内部実装**: 先頭 `_`。
  - 例: `_resolve_runtime`, `_normalize_case`, `_collect_metrics`

### テスト用補助

- テストファイルでは `test_*` を使います。
- `python file.py` 直実行用の補助を置く場合は、外部から使わないことが分かるよう `_run_*` を推奨します。

## 例

- `run_experiment`（公開）→ `_run_registered_command`（内部）
- `build_report`（公開）→ `_summarize_case_results`（内部）
- `OptimizationProblem`（汎用）→ `VectorOptimizationProblem`（空間特殊化）
- `TaskContext`（汎用）→ `RemoteTaskContext`（実行環境特殊化）
