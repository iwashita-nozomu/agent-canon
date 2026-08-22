<!--
@dependency-start
contract policy
responsibility Documents Python コメント for this repository.
upstream design ../common/03_comments.md common decision-comment policy
@dependency-end
-->

# Python コメント

この章は、Python 実装におけるコメント表記と、Python/JAX 固有の判断だけを補足します。
コメントが必要になる一般条件と変更時の同期は、共通コメント規約を正本とします。

## 要約

- 一般の意味判定は [コメント規約](../common/03_comments.md) に従います。
- 非自明な関数境界には `# 責務:`、処理内部の非自明な判断には短い理由コメントを使います。
- JAX 制御、shape/dtype、数値安定化、Python 固有の型抑制では、コードだけから復元できない制約を先に示します。
- 自明な処理へ機械的にコメントを付けず、処理変更時は関連コメントを同じ差分で同期します。

## 規約

- コメントの必須条件、保存する情報、配置、禁止事項、lifecycle は `documents/conventions/common/03_comments.md` を正本とします。
- 名前、型、配置から責務を安全に復元できない関数、メソッド、内部補助関数の直前には、`# 責務:` で担当する判断、変換、状態遷移、境界を 1 行程度で示すことを必須にします。
- 関数内部で共通規約の `needs_local_comment` を満たす判断は、その式、分岐、loop、resource operation の直前へ短い理由コメントを置くことを必須にします。
- `jax.lax.scan`、`while_loop`、`cond` のように trace 系の制御フローが見えにくくなる箇所では、loop state、停止条件、分岐の意味のうちコードから復元できないものを先にコメントで示します。
- shape の変換、dtype の正規化、数値安定化、tolerance、clipping、丸めのための分岐は、数理的前提または failure semantics が式だけで読めない場合に短い補足を付けます。
- concurrency、ordering、resource lifetime、cleanup、external library/runtime constraint は、Python 構文から理由を復元できない場合に共通規約どおり判断コメントを付けます。
- `cast`、`# type: ignore`、`pyright: ignore` を避けられない場合は、抑制対象の runtime invariant と、型設計だけでは閉じられない理由を直前に示します。
- 単純な property、stub、`Protocol` 宣言、`@overload`、dunder method、名前から責務が一意に読める小さな関数には、コメントを機械的に追加しません。
- コメントが説明する Python/JAX logic を変更した場合は、同じ差分でコメントを更新または削除します。現在の trace、shape、dtype、ordering と異なるコメントを残してはなりません。
