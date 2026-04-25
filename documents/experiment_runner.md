# `experiment_runner` 設計方針
<!--
@dependency-start
@dependency-end
-->


この文書は、`python/experiment_runner/` を採用するプロジェクトでの推奨設計を定義します。
テンプレート本体は `experiment_runner` 実装を同梱しないため、この文書は module layout と contract の正本として扱います。

想定する surface は次です。

- `protocols.py`
- `runner.py`
- `resource_scheduler.py`
- `execution_result.py`
- `child_runtime.py`
- `monitor.py`
- `result_io.py`

現在の実行経路は 1 本です。

- scheduler は `StandardFullResourceScheduler` だけを使います。
- runner は `StandardRunner` だけを使います。
- completion の正本は `ExecutionResult` だけです。
- legacy な `int exit_code` 契約や複数 scheduler を新設することを禁止します。

## 1. 実験側が実装するもの

`experiment_runner` を使う実験コードは、実質的に次の 5 点だけを実装します。

### 1.1 `task`

- `task(case, context)` は 1 case の研究ロジックです。
- `task` は case ごとの結果 record を自分で作り、自分で書き込みます。
- `task` は通常の payload を返してもよく、`ExecutionResult` を直接返してもよいです。
- `task` が通常の payload を返した場合、`StandardWorker` が `status="ok"` の `ExecutionResult` に正規化します。
- `task` が Python 例外を投げた場合、child runtime が structured diagnostics に変換します。
- `task` の責務は「研究ロジック」と「case ごとの結果出力」です。process 管理、timeout、signal 後始末を入れることを禁止します。

### 1.2 `cases`

- 実験側は実行したい case 列を先に展開して `list[T]` で渡します。
- 多重 `for`、直積展開、difficulty sweep の定義は実験コード側で行います。
- runner は case 生成を行いません。

### 1.3 環境初期化

- 環境初期化の差し込み点は 2 つです。
  - `context_builder(case) -> TaskContext`
  - `initializer(context) -> None`
- `context_builder` は case ごとの `TaskContext` を作ります。
- `initializer` は child process の先頭で実行されます。
- 既定の `initializer` は `apply_environment_variables()` のような環境反映 helper です。
- JAX / XLA の env dict は project-local helper で作り、`context["environment_variables"]` に載せます。
- 実験 script 側で `CUDA_VISIBLE_DEVICES`、`JAX_PLATFORMS`、`XLA_*` を場当たり的に直書きすることを禁止します。

### 1.4 ケースごとのリソース推定

- 現行 scheduler は `StandardFullResourceScheduler` だけなので、case ごとの resource estimate を必ず用意します。
- 入口は `resource_estimate(case) -> FullResourceEstimate` です。
- `resource_estimate` は `task` と同じ実装単位に寄せることを推奨します。
- `StandardWorker(..., resource_estimator=...)` を使うと、scheduler は `from_worker(...)` でその estimate を受け取れます。

### 1.5 `SkipController`（任意）

- 起動前 skip が必要な実験だけ `SkipController` を実装します。
- 契約は次の 2 つだけです。
  - `should_skip(case, context) -> str | None`
  - `update(case, context, result: ExecutionResult) -> None`
- `should_skip(...)` が文字列を返した場合、その case は child process を起動せず `status="skipped"` で記録します。
- `update(...)` は case 完了後に scheduler から呼ばれます。
- skip の判定基準と内部状態は実験コード側で持ちます。

## 2. runner 側が引き受ける責務

次は `experiment_runner` 側の責務です。実験コード側へ重複実装することを禁止します。

- case ごとの fresh child process 起動
- `spawn` 前提の実行
- timeout 管理
- `terminate()` と `kill()` と `finally` cleanup
- parent 側での completion 回収
- child が completion を返せない場合の diagnostics 合成
- resource estimate に基づく worker slot、host memory、GPU、GPU slot の割当
- `TaskContext["environment_variables"]` の child 反映
- CPU affinity、worker label、GPU assignment の metadata 付与
- progress callback
- monitor への worker start / finish / timeout / signal 通知

## 3. 実験コードに残る最小構成

`experiment_runner` を使う topic は、通常は次の構成で足ります。

- `cases.py`
  - case 列の展開
  - difficulty range
  - `resource_estimate(case)`
- `experimentcode.py`
  - `task(case, context)`
  - `context_builder(case)`
  - 必要なら `initializer(context)`
  - 必要なら `SkipController`
  - runner 起動と final summary 生成

実験ごとに worker class や scheduler class を増やすことを既定にしません。まずは `StandardWorker` と `StandardFullResourceScheduler` を使います。

## 4. 標準の組み立て方

    from experiment_runner import StandardFullResourceScheduler
    from experiment_runner import StandardRunner
    from experiment_runner import StandardWorker


    worker = StandardWorker(
        task=run_case,
        resource_estimator=estimate_case,
        initializer=initialize_context,
    )

    scheduler = StandardFullResourceScheduler.from_worker(
        cases=cases,
        worker=worker,
        context_builder=build_context,
        skip_controller=skip_controller,
        resource_capacity=resource_capacity,
    )

    runner = StandardRunner(scheduler)
    runner.run(worker)

この組み立てで実験側が差し替える場所は次だけです。

- `run_case`
- `estimate_case`
- `build_context`
- `initialize_context`
- `skip_controller`
- `cases`

## 5. `ExecutionResult` を正本にする

completion の正本は `ExecutionResult` です。

- `Scheduler.on_finish(...)` は `ExecutionResult` だけを受け取ります。
- `StandardCompletion` も `result: ExecutionResult` だけを持ちます。
- success / failure / skipped / timeout / signal / no completion は `ExecutionResult` で記録します。
- 実験側で独自の `exit_code` 契約を増やすことを禁止します。

runner diagnostics の一次情報は次です。

- `status`
- `failure_kind`
- `message`
- `raw_exit_code`
- `signal_name`
- `stdout`
- `stderr`
- `traceback`
- `source`

framework 固有の解釈は、この record を使って後段で行います。

## 6. resource scheduler の責務

`StandardFullResourceScheduler` は次を担当します。

- `max_workers`
- host memory 制約
- GPU 数
- GPU memory 制約
- GPU slot 制約
- worker slot id
- CPU affinity
- `runner_metadata`
- `environment_variables`
- `SkipController.update(...)`

GPU を使う case では、scheduler が `CUDA_VISIBLE_DEVICES` と `NVIDIA_VISIBLE_DEVICES` を `TaskContext["environment_variables"]` に入れます。
worker label、CPU affinity、GPU slot も context と環境変数の両方へ載せます。

JAX / XLA の allocator 設定は project-local helper で作り、scheduler の `context_builder` から渡します。

## 7. 実験コード側でやってはいけないこと

- `Popen` を直接並べること
- 独自の mini-runner を書くこと
- 独自の scheduler を topic ごとに増やすこと
- `CUDA_VISIBLE_DEVICES` や `XLA_*` を script 本体で case ごとに差し替えること
- timeout / signal / native crash の parent-side cleanup を script 側で持つこと
- `ExecutionResult` 以外の completion 契約を足すこと
- partial run を正式な resume protocol にすること

## 8. monitor

`RuntimeMonitor` は任意です。
必要な場合だけ `StandardRunner(..., monitor=...)` に渡します。

monitor の正規接続先は `StandardRunner` だけです。実験 script 側で別の pid registry や host-side polling loop を重ねることを禁止します。

monitor が扱う主要イベントは次です。

- case start
- case finish
- timeout
- worker terminated
- signal exit
- no completion

## 9. 非目標

現行の `experiment_runner` は次を目標にしません。

- 複数 scheduler 系統の共存
- legacy `exit_code` 互換
- topic ごとの独自 runner plugin 群
- partial run の再開機構
- framework 固有の error code テーブルを core runner に持つこと
