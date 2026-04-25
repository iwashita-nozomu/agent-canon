<!--
@dependency-start
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# JAX/Equinox の運用規約

この章は、JAX/Equinox 実装時の運用ルールをまとめます。

## 要約

- 反復は `jax.lax.while_loop` を使います。
- JIT 文脈での Python 変換を避けます。

## 規約

- 反復は `jax.lax.while_loop` を使い、Python の `if/for` に依存しません。
- JIT 文脈での `bool/int/float` 変換は避け、**JAX 配列のまま扱う**ことを優先します。
- デバッグ出力は `DEBUG` ガードと `jax.debug.print` を使います。
- **反復回数が動的に変わる処理**（収束判定つきソルバーなど）は `jax.lax.while_loop` を使います。
- **固定回数の反復**は `jax.lax.fori_loop` を使います。
- **毎回 state を返す反復**は `jax.lax.scan` を使います。
