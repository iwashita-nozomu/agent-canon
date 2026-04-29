# Environment Setup
<!--
@dependency-start
responsibility Documents Environment Setup for this repository.
upstream design README.md notes lifecycle index
@dependency-end
-->


## Python

- 基本の import root は `PYTHONPATH=/workspace/python` を基準にします。
- `main` と worktree で code path が違う場合は、どの tree を使っているかを明示します。
- 子プロセスを起こす実験では、child に渡る Python path を明示します。

## JAX / GPU

- GPU を固定したい child では `CUDA_VISIBLE_DEVICES` を明示します。
- GPU の先取りを避けたいときは `XLA_PYTHON_CLIENT_PREALLOCATE=false` を使います。
- CPU に逃がしたいときは `JAX_PLATFORMS=cpu` を使います。
- JAX / XLA の標準 env は experiment script 側で ad hoc に組まず、共通 helper か runner 側で組み立てます。
- `jax` や `jax.numpy` を import する前に env を適用します。
- case ごとの fresh child process を前提にし、process-local state の再利用を期待しません。

## CPU thread

- worker の hidden thread が暴れないように CPU thread 制御が必要な場合は
  - `OMP_NUM_THREADS=1`
  - `OPENBLAS_NUM_THREADS=1`
  - `MKL_NUM_THREADS=1`
  - `NUMEXPR_NUM_THREADS=1`
  を使います。
- CPU affinity を切る場合は、worker 数と logical CPU 数を先に確認します。

## 実験前チェック

- 作業ツリーが期待した状態か確認します。
- 実験に使う worktree がある場合は clean か確認します。
- 出力先が意図したディレクトリか確認します。
- 実験条件と環境変数の前提を run 前に固定します。

## よくある失敗

- child process 側で backend 初期化に失敗する。
- 実験と編集で違う tree を見ていて、思ったコードが走っていない。
- CPU thread 数を放置して oversubscription が起きる。
