<!--
@dependency-start
responsibility Documents コメント for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# コメント

この章は、Python 実装におけるコメント規約を補足します。

## 要約

- 共通ルールに加えて、Python 実装で必要な差分だけを書きます。
- 内部補助関数にも責務コメントを付けます。
- 複雑な変換や JAX 制御フローの前に意図を残します。

## 規約

- 共通ルールは `documents/conventions/common/03_comments.md` を正本とします。
- トップレベル関数だけでなく、読み手が追う必要のある内部補助関数にも責務コメントを付けます。
- 責務コメントは実装の逐語説明ではなく、「この関数がどの判断や変換を担当するか」を簡潔に書きます。
- `jax.lax.scan`、`while_loop`、`cond` のように trace 系の制御フローが見えにくくなる箇所では、loop state や分岐の意味を先にコメントで示します。
- shape の変換、dtype の正規化、数値安定化のための分岐は、読み手が式だけで意図を追えない場合に短い補足を付けます。
