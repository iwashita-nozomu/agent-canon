<!--
@dependency-start
responsibility Documents 演算子記法（共通） for this repository.
upstream design ../../SHARED_RUNTIME_SURFACES.md root documents mirror is canon-owned
@dependency-end
-->

# 演算子記法（共通）

この章は、線形作用素と非線形作用素の表記を揃えるための基準をまとめます。

## 要約

### 線形作用素

- プロトコル `LinearOperator` に準拠します。
- 適用は `@`、合成は `*` を使います。
- 混在時は括弧で明示します。

### 非線形作用素

- 適用は `()`、合成は `*` を使います。
- 混在時は括弧で明示します。

## 規約

- 作用素の適用は `@`、合成は `*` を基本とします。
- 記法の混在は括弧で明示し、読み間違いを避けます。
- 線形と非線形の区別、禁止事項、投影・前処理の細かい表記は言語別規約で定めます。
