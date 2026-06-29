<!--
@dependency-start
contract policy
responsibility Documents 命名規約（Python） for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# 命名規約（Python）

対象: `python/` 配下の checked-in package と module。

## この文書の読み方

- この文書は、Python file、function、class、Protocol、contract family の命名を定めます。
- 主な順路は、要約、ファイル名、関数名、クラス名・Protocol名、
  契約 family の命名、例です。
- checked-in Python package/module の名前を追加または変更する前に読みます。
- 境界: 実装構造や API boundary の判断は、対応する設計/実装規約文書が所有します。

## 要約

- **ファイル名**は `snake_case.py`。
- **関数名**は `snake_case`。
- **公開API** と **内部実装** を名前で区別します。

## ファイル名

- `snake_case.py` を使ってください。
- 略語は一般的なもののみ許可します。
- 役割が分かる語を置き、意味のない接尾辞（`_util` の乱用等）は避けます。
- ファイル名は module が所有する概念を表します。実装手順や一時的な都合を
  表す `new_*`、`tmp_*`、`*_wrapper`、`*_bridge`、`*_misc`、`*_helpers` を
  安易に使いません。bridge や wrapper が本当に domain concept でない限り、
  その file は既存 module に吸収するか、変換元と変換先が読める名前にします。

### 禁止/注意

- 大文字を含むファイル名（例: `MyAlgo.py`）は避けます。
- OS差分が出やすい表記（空白・ハイフン混在）は避けます。

## 関数名

- `snake_case` を使ってください。
- **動詞で始める**ことを推奨します（例: `load_*`, `build_*`, `run_*`, `update_*`, `check_*`）。
- helper / local function では、推定 role に対応する action token を名前へ含めます。例: parser / loader は `parse_*` / `load_*`、collector は `collect_*` / `list_*`、validator は `check_*` / `validate_*`、writer は `write_*` / `persist_*`。
- role/action token alignment は `python3 tools/agent_tools/helper_function_inventory.py --changed --baseline-ref HEAD --only-name-gaps` で確認します。
- 関数名は、呼び出し側が読む契約です。`do_*`、`handle_*`、`process_*`、
  `manage_*` のような総称動詞だけで始める名前は、対象 object と結果が続く場合だけ
  許可します。
- 変換関数は `source_to_target` または `build_<target>_from_<source>` の形を
  優先します。判定関数は `is_*`、`has_*`、`check_*` のどれかに寄せ、
  戻り値が bool なのか finding / report なのかを名前から読めるようにします。
- 証明・IR・generated-code 周りの関数でも、proof workflow の都合ではなく
  runtime の public root、projection、または artifact の責務で命名します。
  例: `build_target_return_projection_tree` は許容できますが、
  `make_proof_bridge` は避けます。

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
