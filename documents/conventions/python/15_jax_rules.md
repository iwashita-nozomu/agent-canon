<!--
@dependency-start
contract policy
responsibility Documents JAX/Equinox の運用規約 for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md shared documents ownership policy
@dependency-end
-->

# JAX/Equinox の運用規約

この章は、JAX/Equinox 実装時の運用ルールをまとめます。

## 要約

- 早期終了する動的反復は `jax.lax.while_loop` を使います。
- JIT 文脈での Python 変換を避けます。
- JIT/lowering 対象の loop carry には、次状態の計算、停止判定、または戻り値に使う値だけを入れます。
- `lax.while_loop` の `cond` へ、反復本体で作った residual / convergence /
  breakdown などの status feedback を戻しません。
- GPU tracing では CUDA preallocation を無効にし、backend availability の問題を CPU fallback と混同しません。
- JAX / XLA / IREE lowering、solver、optimizer、convergence、residual、benchmark、
  experiment validation の計算テストを CPU で代替実行しません。
- backend LLVM witness を必要とする JIT root は、計算に使われる動的 tensor leaf を入力に含めます。

## 規約

- 早期終了する動的反復は `jax.lax.while_loop` を使い、Python の `if/for` に依存しません。
- JIT 文脈での `bool/int/float` 変換は避け、**JAX 配列のまま扱う**ことを優先します。
- Python scalar 設定を JIT/lowering 対象の body や carry で使う場合は、境界で
  `jnp.asarray(..., dtype=...)` に正規化し、loop 内で Python 型と JAX 配列型を
  混ぜません。
- デバッグ出力は `DEBUG` ガードと `jax.debug.print` を使います。
- **反復回数が動的に変わる処理**（収束判定つきソルバーなど）は `jax.lax.while_loop` を使います。
  `maxiter` は上限であり、条件に `done` / `breakdown` / residual 判定が入る場合は
  数学的には動的長さの反復です。
- **固定回数の反復**は `jax.lax.fori_loop` を使います。これは、反復本体を常に同じ
  回数だけ意味的に実行する場合に限ります。
- **固定回数で毎回 state を返す反復**は `jax.lax.scan` を使います。

## 再現性のための禁止事項

- JIT/lowering 対象の関数では、未使用、再計算可能、または diagnostic/log 専用の値を
  `lax.while_loop` carry に残しません。carry は loop-carried state、停止判定に必要な
  scalar、戻り値に直接接続する値へ限定します。
- GPU/IREE lowering 対象の `lax.while_loop` では、反復本体の reduction/compare で
  作った bool status を次反復の `cond` へ feedback しません。早期停止が必要な場合は、
  初期短絡は `active_maxiter` に畳み、反復中の停止状態は数値 sentinel と body 内の
  state freeze で表します。
- `lax.while_loop` 内で同じ shape/type の break/continue 値を返すだけの
  `lax.cond` を重ねません。値選択で表せる場合は JAX 配列上の selection に畳み込み、
  lowering 対象の while+case 複合制御フローを増やしません。
- GPU を既定とする tracing / experiment では `XLA_PYTHON_CLIENT_PREALLOCATE=false`
  を import 前に設定します。CUDA backend 自体が初期化できない場合は、GPU 実行失敗の
  evidence と `gpu_validation_blocker=<reason>` を残し、CPU tracing や CPU 計算テストへ
  切り替えません。
- LLVM backend witness を生成する JIT root を、全入力が static/constant になる形にしません。
  IREE が executable dispatch を生成せず、VM までは成功しても LLVM `.ll` が空になるためです。
